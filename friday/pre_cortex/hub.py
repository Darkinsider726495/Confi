"""O hub do pré-córtex: guarda os objetivos, fala com os neurônios por mensagens e conduz o fluxo (as fases estão em fases.py).

Um objetivo roda numa linha (thread) própria. Quem espera o dono (autorização) ou o corretor (confirmação) SAI da linha com o estado gravado; o dono (ou o corretor) acorda o objetivo
depois — por isso reiniciar o programa no meio de uma espera não perde nada. Ações que não podem repetir passam pelo registro antes de agir (execucao.py).

Dois modos com o MESMO código e o MESMO contrato (contrato.py):
  local         os trabalhadores moram neste processo (cada um com a sua fila, seus tempos e a sua lista de mensagens já vistas); toda mensagem passa por JSON;
  distribuído   os trabalhadores são outros processos que falam HTTP local (127.0.0.1) com uma chave de sessão. Mesma máquina ≠ várias máquinas (docs/PRE_CORTEX.md).
Neurônios que precisam do corretor, das tarefas ou do cofre (contexto, aprendizagem, monitor) ficam sempre num trabalhador interno do hub.
"""
import collections
import concurrent.futures
import copy
import threading
import time

from . import armazem as AR
from . import catalogo_neuronios as K
from . import config as CF
from . import contrato as C
from . import dossie as D
from . import execucao as EX
from . import explicar as EXPL
from . import memoria_coletiva as MC
from . import transporte as TR
from .fases import Cancelado, ChamadaFalhou, Fases, LimiteExcedido, ModuloIndisponivel, Parar

PERSISTE_S = TR.PERSISTE_S
ATIVOS = ("recebido", "em_andamento", "aguardando_execucao")
ESPERANDO = ("aguardando_autorizacao", "aguardando_confirmacao_do_corretor")


_TRAVA_POOL = threading.Lock()

class Hub(Fases):
    def __init__(self, cfg=None, pasta=None, relogio=time.time, dormir=time.sleep, token=None, vigia=True):
        self.cfg = cfg if cfg is not None else CF.Config()
        self.rel, self.dormir = relogio, dormir
        self.token = token or ""
        self.arm = AR.Armazem(pasta, relogio, self.cfg["eventos_em_memoria"])
        self.memoria_coletiva = MC.MemoriaColetiva(pasta)
        self.memoria_coletiva.reconstruir(self.arm.eventos(0, None, self.cfg["eventos_em_memoria"]))
        self._pids_contexto = {}
        self.trava = threading.RLock()
        self.rot = TR.Roteador()
        self.trabalhadores = {}              # nome -> Worker (os que moram neste processo)
        self.destinos = {}                   # nome -> Destino
        self.local_de = {}                   # neurônio -> nome do trabalhador
        self.criticos = K.criticos()
        self._threads, self._cancelados = {}, set()
        self._em_voo = collections.Counter()
        self._ultimo_no = {}                 # neurônio -> (estado, instante, resumo)
        self._atual = None
        self._auto = collections.Counter()
        self.ultima_saude, self.ultimo_monitor = {"em": 0.0, "workers": {}}, None
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(2, self.cfg["max_paralelo"]), thread_name_prefix="pc-no")
        self._fim = threading.Event()
        self._vigia = None
        self.avisos = list(self.cfg.avisos)
        self._montar()
        if vigia:
            self.iniciar_vigia()

    # ------------------------------------------------------------------ montagem
    def _registrar_local(self, worker, nomes):
        d = TR.DestinoLocal(worker)
        self.trabalhadores[worker.nome], self.destinos[worker.nome] = worker, d
        self.rot.registrar(d, nomes)
        for n in nomes:
            self.local_de[n] = worker.nome
        # Workers locais nascem com contexto reconstituído, sem esperar novos eventos.
        self._replay_destino(worker.nome, d)

    def _montar(self):
        cfg = self.cfg
        self._registrar_local(TR.Worker("hub", K.novos(K.NO_HUB), max_paralelo=cfg["max_paralelo"], relogio=self.rel), K.NO_HUB)
        if cfg["modo"] == "local":
            for nome, neur in K.GRUPOS_PADRAO.items():
                self._registrar_local(TR.Worker(nome, K.novos(neur), max_paralelo=cfg["max_paralelo"], relogio=self.rel), neur)
        else:
            if not cfg["workers"]:
                self.avisos.append("modo distribuído sem trabalhadores configurados: nenhum módulo crítico está disponível, então nenhum objetivo avança")
            for nome, w in cfg["workers"].items():
                neur = w.get("neuronios") or list(K.GRUPOS_PADRAO.get(nome, ()))
                if not neur:
                    self.avisos.append(f"trabalhador «{nome}» sem lista de neurônios e fora do padrão; ignorado")
                    continue
                d = TR.DestinoHTTP(nome, w["url"], self.token)
                self.destinos[nome] = d
                self.rot.registrar(d, neur)
                for n in neur:
                    self.local_de[n] = nome

    def esperados(self):
        return {n: {"trabalhador": self.local_de.get(n), "critico": c} for n, c in self.criticos.items()}

    # ------------------------------------------------------------------ utilidades usadas pelas fases
    def _salvar(self):
        self.arm.salvar()

    def _evento(self, d, tipo, **campos):
        """Persiste o evento e o publica aos neurônios sem entrar na fila de objetivos.

        O fan-out contém apenas metadados permitidos (nunca descrição, texto, argumentos,
        plano ou conteúdo de memória). Cada destino recebe sua própria mensagem idempotente.
        A indisponibilidade de um assinante não afeta o fluxo principal.
        """
        registro = self.arm.evento(d["id"], tipo, fase=d["fase"], ciclo=d["ciclo"], **campos)
        self.memoria_coletiva.registrar(registro)
        permitidos = ("estado", "modulo", "recuperavel", "tipo_objetivo", "suportado", "neuronio", "acao", "ok", "codigo", "worker", "para", "de")
        dados = {k: v for k, v in campos.items() if k in permitidos and isinstance(v, (str, int, float, bool, type(None)))}
        evento = {"evento": str(tipo)[:48], "fase": str(d.get("fase", ""))[:40], "ciclo": int(d.get("ciclo", 0) or 0), "dados": dados,
                   "emitido_em": self.rel(), "seq": int(registro.get("seq", 0) or 0)}   # seq: o neurônio reconhece o mesmo evento se vier de novo pelo replay
        # Pool próprio: eventos não consomem vagas do escalonador de objetivos.
        if not hasattr(self, "_pool_eventos"):
            with _TRAVA_POOL:                    # dois eventos simultâneos não criam dois pools (um deles ficaria órfão)
                if not hasattr(self, "_pool_eventos"):
                    self._limite_eventos = threading.BoundedSemaphore(64)
                    self._eventos_descartados = 0
                    self._pool_eventos = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="pc-evento")

        def enviar(destino, msg):
            try:
                destino.enviar(msg, 0.5)
            except Exception:
                # Evento é informativo; indisponibilidade não bloqueia a fase nem muda sua decisão.
                pass
            finally:
                self._limite_eventos.release()

        for neuronio, destino in list(self.rot.rotas.items()):
            msg = C.criar("hub", neuronio, "notificar", evento, correlacao=d["id"], timeout_s=0.5, validade_s=30.0, tipo="evento")
            if not self._limite_eventos.acquire(blocking=False):
                self._eventos_descartados += 1
                continue
            try:
                self._pool_eventos.submit(enviar, destino, msg)
            except RuntimeError:
                self._limite_eventos.release()
                # Encerramento do hub: persistência do evento já foi concluída.
                pass
        return registro

    def _replay_destino(self, nome, destino, pid=None):
        """Reenvia os 8 eventos mais recentes do log (no total, não por neurônio) quando um worker inicia ou reinicia.
        Cada evento leva o `seq`; o neurônio ignora o que já recebeu, então replay repetido ou interrompido não duplica contexto."""
        try:
            registros = self.arm.eventos(0, None, 8)
            neuronios = [n for n, d in self.rot.rotas.items() if d.nome == nome]
            for n in neuronios:
                for registro in registros:
                    evento = MC.projetar_evento(registro)
                    if not evento:
                        continue
                    msg = C.criar("hub", n, "notificar", evento,
                                  correlacao="sistema", timeout_s=0.5,
                                  validade_s=30.0, tipo="evento")
                    try:
                        destino.enviar(msg, 0.5)
                    except (TR.Indisponivel, TR.Recusado):
                        return False
            if pid is not None:
                self._pids_contexto[nome] = pid
            return True
        except Exception:
            return False

    def memoria_compartilhada(self):
        """Resumo estatístico seguro; não expõe texto de eventos nem conteúdo de usuário."""
        return self.memoria_coletiva.resumo(limite=20)

    def _degradar(self, d, modulo, motivo, consequencia):
        with self.arm.trava:
            d["degradado"].append({"modulo": modulo, "motivo": motivo, "consequencia": consequencia, "em": self.rel()})
        self._salvar()
        self._evento(d, "modo_degradado", modulo=modulo, motivo=motivo, texto=f"«{modulo}» indisponível: {consequencia}")

    def _conferir(self, d, tolerar_tempo=False):
        if d["cancelado"] or d["id"] in self._cancelados:
            raise Cancelado()
        if self._fim.is_set():
            raise Parar()
        if tolerar_tempo:
            return
        u = d["uso"]
        agora = self.rel()
        pausa = u["pausas_s"] + ((agora - u["pausa_desde"]) if u.get("pausa_desde") else 0.0)
        ativo = agora - u["inicio"] - pausa
        if ativo > self.cfg["max_tempo_objetivo_s"]:
            raise LimiteExcedido("tempo", f"o objetivo usou {ativo:.0f}s de tempo ativo (limite {self.cfg['max_tempo_objetivo_s']:.0f}s)")
        if u["nos"] >= self.cfg["max_nos_por_objetivo"]:
            raise LimiteExcedido("nos", f"o objetivo já usou {u['nos']} etapas/mensagens (limite {self.cfg['max_nos_por_objetivo']})")

    def _no(self, d, fase, neuronio, acao, depende_de=()):
        with self.arm.trava:
            d["uso"]["nos"] += 1
            no = {"id": f"n{d['uso']['nos']:03d}", "ciclo": d["ciclo"], "fase": fase, "neuronio": neuronio, "acao": acao, "depende_de": list(depende_de), "estado": "pendente",
                  "criado_em": self.rel(), "inicio": None, "fim": None, "resumo": "", "worker": None, "pid": None, "duracao_ms": None}
            d["grafo"].append(no)
            del d["grafo"][:-80]
        return no

    def _no_iniciar(self, no):
        with self.arm.trava:
            no["estado"], no["inicio"] = "executando", self.rel()
        self._ultimo_no[no["neuronio"]] = ("processando", self.rel(), "")

    def _no_fim(self, no, estado, resumo=""):
        with self.arm.trava:
            no["estado"], no["fim"] = estado, self.rel()
            if resumo:
                no["resumo"] = resumo[:200]
        self._ultimo_no[no["neuronio"]] = ({"concluido": "concluido", "falhou": "erro", "aguardando": "aguardando"}.get(estado, "ocioso"), self.rel(), resumo[:120])

    def _paralelo(self, d, trabalhos):
        """Roda juntas as etapas independentes e espera todas. Devolve ({chave: resultado}, {chave: exceção})."""
        futs = {k: self.pool.submit(f) for k, f in trabalhos}
        res, err = {}, {}
        for k, fu in futs.items():
            try:
                res[k] = fu.result()
            except BaseException as e:                                        # noqa: BLE001  (a exceção é devolvida a quem chamou)
                err[k] = e
        return res, err

    def _chamar_no(self, d, no, neuronio, acao, corpo, *, plano=None):
        self._no_iniciar(no)
        try:
            r, meta = self._chamar(d, neuronio, acao, corpo, plano=plano, no=no)
        except (Cancelado, Parar):
            self._no_fim(no, "falhou", "interrompido")
            raise
        except Exception as e:
            self._no_fim(no, "falhou", str(e)[:160])
            raise
        with self.arm.trava:
            no["worker"], no["pid"], no["duracao_ms"] = meta.get("worker"), meta.get("pid"), meta.get("duracao_ms")
        self._no_fim(no, "concluido")
        return r

    def _chamar(self, d, neuronio, acao, corpo, *, plano=None, no=None, tentativas=None):
        """Manda um pedido a um neurônio. Reenvia com o MESMO id se o trabalhador não respondeu (timeout/indisponível): o trabalhador reconhece a duplicata e devolve o que já fez."""
        n_max = tentativas or self.cfg["tentativas_msg"]
        tmo = self.cfg["timeout_msg_s"]
        msg = C.criar("hub", neuronio, acao, corpo, correlacao=d["id"], plano={"id": plano["id"], "versao": plano["versao"]} if plano else None, timeout_s=tmo, validade_s=tmo * (n_max + 1) + 30,
                      agora=self.rel())
        ultimo = ""
        crit = self.criticos.get(neuronio, True)
        for t in range(1, n_max + 1):
            self._conferir(d)
            with self.arm.trava:
                d["uso"]["mensagens"] += 1
            msg["tentativa"], msg["estado"] = t, "enviada"
            self._evento(d, "mensagem_enviada", id=msg["id"], para=neuronio, acao=acao, tentativa=t, no=no["id"] if no else None,
                         texto=f"→ {neuronio}.{acao}" + (f" (tentativa {t}, mesmo id)" if t > 1 else ""))
            self._em_voo[neuronio] += 1
            resp, motivo = None, ""
            t0 = self.rel()
            try:
                resp = self.rot.enviar(msg, tmo)
            except TR.Indisponivel as e:
                motivo = str(e)
            except TR.Recusado as e:
                raise ChamadaFalhou(neuronio, "recusada", f"o trabalhador recusou a conversa ({e}); confira a chave de sessão") from None
            finally:
                self._em_voo[neuronio] -= 1
            if resp is not None and resp.get("ok"):
                pp, tp = resp.get("processado_por") or {}, resp.get("tempos") or {}
                meta = {"worker": pp.get("worker"), "pid": pp.get("pid"), "duracao_ms": tp.get("duracao_ms")}
                self._evento(d, "mensagem_recebida", id=msg["id"], de=neuronio, acao=acao, ok=True, worker=meta["worker"], pid=meta["pid"], duracao_ms=meta["duracao_ms"], duplicada=bool(resp.get("duplicada")),
                             tentativa=t, texto=f"← {neuronio}.{acao} ok" + (f" ({meta['duracao_ms']} ms, processo {meta['pid']})" if meta["duracao_ms"] is not None else "") + (" [duplicata reconhecida]" if resp.get("duplicada") else ""))
                self._registrar_atividade(neuronio, "concluido", acao)
                return resp["corpo"], meta
            if resp is not None:
                cod, txt = (resp.get("erro") or {}).get("codigo"), (resp.get("erro") or {}).get("mensagem", "")
                if cod == "cancelada":
                    raise Cancelado()
                if cod not in C.RECUPERAVEIS:
                    self._evento(d, "mensagem_recebida", id=msg["id"], de=neuronio, acao=acao, ok=False, codigo=cod, erro=txt, tentativa=t, texto=f"← {neuronio}.{acao} ERRO {cod}: {txt}")
                    self._registrar_atividade(neuronio, "erro", f"{cod}: {txt}")
                    raise ChamadaFalhou(neuronio, cod, txt)
                motivo = f"{cod}: {txt}"
            ultimo = motivo
            self._evento(d, "tentativa_falhou", id=msg["id"], para=neuronio, acao=acao, tentativa=t, motivo=motivo[:200], espera_s=self.cfg["espera_entre_tentativas_s"] * (2 ** (t - 1)),
                         texto=f"{neuronio}.{acao} não respondeu (tentativa {t} de {n_max}): {motivo[:120]}")
            if t < n_max:
                self.dormir(self.cfg["espera_entre_tentativas_s"] * (2 ** (t - 1)))
                self._conferir(d)
        self._registrar_atividade(neuronio, "erro", ultimo)
        self._evento(d, "modulo_indisponivel", modulo=neuronio, critico=crit, motivo=ultimo[:200],
                     texto=f"«{neuronio}» indisponível depois de {n_max} tentativa(s): {ultimo[:120]}" + (" — é crítico, o objetivo não avança sem ele" if crit else " — posso seguir em modo degradado"))
        raise ModuloIndisponivel(neuronio, ultimo)

    def _registrar_atividade(self, neuronio, estado, resumo=""):
        self._ultimo_no[neuronio] = (estado, self.rel(), str(resumo)[:120])

    # ------------------------------------------------------------------ vida de uma linha de objetivo
    def _rodar(self, pcid):
        d = self.arm.obter(pcid)
        try:
            with self.arm.trava:
                if d["estado"] in ("recebido",):
                    d["estado"] = "em_andamento"
                    self._salvar()
            while True:
                if d["estado"] in D.FINAIS or d["estado"] in D.PARADOS:
                    return
                self._conferir(d)
                fase = d["fase"]
                f = getattr(self, "_fase_" + fase, None)
                if f is None:
                    return
                self._evento(d, "fase_iniciada", texto=f"fase: {fase}")
                f(d)
                if self.cfg["ritmo_demo_s"] > 0 and d["fase"] not in ("fim",):
                    self._pausa_demo(d)
        except Parar:
            return
        except BaseException as e:                                            # noqa: BLE001  (a linha nunca morre calada)
            try:
                self._fim_com_excecao(d, e)
            except BaseException as e2:                                       # noqa: BLE001  (nem se o próprio tratamento falhar: o estado nunca fica «em andamento» à toa)
                with self.arm.trava:
                    d["estado"], d["bloqueio"] = "bloqueado", {"tipo": "erro_interno", "texto": f"erro ao tratar {type(e).__name__}: {type(e2).__name__}", "modulo": None, "recuperavel": False, "em": self.rel()}
                self._salvar()
        finally:
            with self.trava:
                if self._threads.get(pcid) is threading.current_thread():
                    self._threads.pop(pcid, None)

    def _fim_com_excecao(self, d, e):
        if isinstance(e, Cancelado):
            self._finalizar_cancelado(d)
        elif isinstance(e, LimiteExcedido):
            self._evento(d, "limite_atingido", limite=e.tipo, texto=e.texto)
            self._travar(d, "bloqueado", f"Limite atingido: {e.texto}.", tipo="limite_de_" + e.tipo, recuperavel=False)
        elif isinstance(e, ModuloIndisponivel):
            crit = self.criticos.get(e.modulo, True)
            self._travar(d, "bloqueado", f"O módulo «{e.modulo}» está indisponível ({e.texto[:120]}). Não avanço sem ele" + ("" if crit else " (mas ele poderia faltar)") + ".", tipo="modulo_indisponivel",
                         modulo=e.modulo, recuperavel=True)
        elif isinstance(e, ChamadaFalhou):
            self._travar(d, "bloqueado", f"«{e.modulo}» falhou: {e.codigo}: {e.texto[:200]}", tipo="falha_de_modulo", modulo=e.modulo, recuperavel=e.codigo in ("erro_interno",))
        else:
            self._evento(d, "erro_interno", erro=f"{type(e).__name__}: {str(e)[:200]}")
            self._travar(d, "bloqueado", f"Erro interno do hub: {type(e).__name__}: {str(e)[:160]}.", tipo="erro_interno", recuperavel=False)

    def _pausa_demo(self, d):
        t = self.cfg["ritmo_demo_s"]
        ini = self.rel()
        self._evento(d, "pausa_demo", segundos=t, texto=f"pausa de {t:g}s só para dar tempo de acompanhar na tela (configuração ritmo_demo_s)")
        fim = ini + t
        while self.rel() < fim:
            self._conferir(d, tolerar_tempo=True)
            self.dormir(min(0.05, max(0.0, fim - self.rel())))
        with self.arm.trava:
            d["uso"]["pausas_s"] += self.rel() - ini                           # a pausa de demonstração não gasta o tempo do objetivo

    def _travar(self, d, estado, texto, *, tipo, modulo=None, recuperavel=False):
        try:
            self._parar_com(d, estado, texto, tipo=tipo, modulo=modulo, recuperavel=recuperavel)
        except Parar:
            pass

    def _iniciar(self, pcid):
        with self.trava:
            t = self._threads.get(pcid)
            if t is not None and t.is_alive():
                return False
            t = threading.Thread(target=self._rodar, args=(pcid,), name=f"pc-{pcid}", daemon=True)
            self._threads[pcid] = t
            t.start()
            return True

    def _finalizar_cancelado(self, d):
        with self.arm.trava:
            reg_exec = [r for r in d["execucoes"].values() if r.get("tarefa")]
        achado = ""
        for r in reg_exec:
            obs = EX.observar(r)
            if obs["tarefa"] and not obs["final"]:
                EX.cancelar_tarefa(r, "objetivo cancelado pelo dono")
                achado = f" A tarefa {obs['tarefa']} foi cancelada."
            elif obs["final"] and obs["estado"] in ("CONCLUIDA", "EXECUTADA_SEM_VERIFICACAO"):
                achado += f" A tarefa {obs['tarefa']} já tinha terminado ({obs['rotulo']}): veja o efeito, não desfaço sozinha."
        with self.arm.trava:
            d["estado"], d["bloqueio"] = "cancelado", None
            d["proxima_etapa"] = "nada: cancelado pelo dono"
            d["atualizado_em"] = self.rel()
            d["uso"]["pausa_desde"] = None
            D.decisao(d, "dono", "objetivo cancelado", "o dono pediu o cancelamento" + achado, self.rel())
        self._salvar()
        self._evento(d, "cancelado", texto="objetivo cancelado pelo dono." + achado)

    # ------------------------------------------------------------------ o que o dono pode fazer
    def submeter(self, texto, *, origem="pedido_do_dono", prioridade="normal", so_planejar=False, meta=None, iniciar=True):
        texto = " ".join(str(texto or "").split())
        if not texto:
            return {"ok": False, "erro": "o objetivo está vazio"}
        if len(texto) > 1000:
            return {"ok": False, "erro": "o objetivo passou de 1000 caracteres; resuma"}
        if origem not in D.ORIGENS:
            return {"ok": False, "erro": "origem inválida"}
        with self.arm.trava:
            pcid = self.arm.proximo_id()
            d = D.novo(pcid, texto, agora=self.rel(), origem=origem, prioridade=prioridade, so_planejar=so_planejar, meta=meta,
                       limites={k: self.cfg[k] for k in ("max_replanos", "max_revisoes_critica", "max_tempo_objetivo_s", "max_nos_por_objetivo", "timeout_msg_s", "tentativas_msg")})
            if origem == "sugerido_pelo_sistema":
                d["estado"], d["proxima_etapa"] = "aguardando_aceite", "O dono precisa aceitar este objetivo antes de qualquer trabalho."
            self.arm.colocar(d)
            D.decisao(d, "dono" if origem == "pedido_do_dono" else "sistema", f"objetivo recebido ({origem})", "registrado no dossiê", self.rel())
            self._atual = pcid
        self._salvar()
        self._evento(d, "objetivo_recebido", origem=origem, so_planejar=bool(so_planejar), texto=f"objetivo {pcid} recebido: {texto[:120]}")
        if origem != "sugerido_pelo_sistema" and iniciar:
            self._iniciar(pcid)
        return {"ok": True, "id": pcid, "estado": d["estado"]}

    def _com_dossie(self, pcid):
        d = self.arm.obter(pcid) if isinstance(pcid, str) else None
        return d

    def aceitar(self, pcid):
        d = self._com_dossie(pcid)
        if d is None:
            return {"ok": False, "erro": "objetivo desconhecido"}
        if d["estado"] != "aguardando_aceite":
            return {"ok": False, "erro": f"este objetivo não está esperando aceite (estado: {d['estado']})"}
        with self.arm.trava:
            d["origem"], d["origem_aceita"], d["estado"] = "aceito_para_execucao", True, "em_andamento"
            D.decisao(d, "dono", "aceitou o objetivo sugerido pelo sistema", "a partir daqui ele pode ser planejado", self.rel())
        self._salvar()
        self._evento(d, "objetivo_aceito", texto="o dono aceitou o objetivo sugerido pelo sistema")
        self._iniciar(pcid)
        return {"ok": True, "id": pcid}

    def _acordar(self, d, motivo):
        with self.arm.trava:
            u = d["uso"]
            if u.get("pausa_desde") is not None:
                u["pausas_s"] += self.rel() - u["pausa_desde"]
                u["pausa_desde"] = None
            d["estado"], d["bloqueio"] = "em_andamento", None
            d["atualizado_em"] = self.rel()
        self._salvar()
        self._iniciar(d["id"])

    def autorizar(self, pcid, versao=None, plano_hash=None, via="painel"):
        d = self._com_dossie(pcid)
        if d is None:
            return {"ok": False, "erro": "objetivo desconhecido"}
        if d["estado"] != "aguardando_autorizacao" or not d.get("autorizacao"):
            return {"ok": False, "erro": f"este objetivo não está esperando autorização (estado: {d['estado']})"}
        pedido = d["autorizacao"]
        reg = self._plano_reg(d)
        if plano_hash is not None and plano_hash != pedido["plano_hash"]:
            return {"ok": False, "erro": "a autorização é para outro plano (o hash não confere); nada foi autorizado"}
        if versao is not None and int(versao) != pedido["plano_versao"]:
            return {"ok": False, "erro": "a autorização é para outra versão do plano; nada foi autorizado"}
        if pedido["plano_hash"] != reg["hash"] or d["plano_atual"] != pedido["plano_versao"]:
            return {"ok": False, "erro": "o plano mudou depois do pedido de autorização; peço de novo"}
        with self.arm.trava:
            d["autorizacao_concedida"] = {"plano_hash": reg["hash"], "plano_versao": reg["versao"], "via": via, "em": self.rel(), "motivo": "o dono autorizou este plano exato"}
            reg["autorizacao"] = {"estado": "concedida", **d["autorizacao_concedida"]}
            d["autorizacao"] = None
            D.decisao(d, "dono", f"autorizou o plano v{reg['versao']}", f"hash {reg['hash'][:8]}; vale só para este plano; o corretor ainda pode pedir a confirmação da ação", self.rel())
            d["fase"] = "execucao"
        self._evento(d, "autorizacao_concedida", versao=reg["versao"], plano_hash=reg["hash"], via=via, texto=f"o dono autorizou o plano v{reg['versao']} (hash {reg['hash'][:8]}); o corretor continua valendo")
        self._acordar(d, "autorizado")
        return {"ok": True, "id": pcid, "plano_hash": reg["hash"]}

    def negar(self, pcid, motivo="o dono negou"):
        d = self._com_dossie(pcid)
        if d is None:
            return {"ok": False, "erro": "objetivo desconhecido"}
        if d["estado"] != "aguardando_autorizacao":
            return {"ok": False, "erro": f"este objetivo não está esperando autorização (estado: {d['estado']})"}
        reg = self._plano_reg(d)
        with self.arm.trava:
            reg["autorizacao"] = {"estado": "negada", "em": self.rel(), "motivo": motivo[:200]}
            d["autorizacao"] = None
            D.decisao(d, "dono", f"negou o plano v{reg['versao']}", motivo[:200], self.rel())
            if d["uso"].get("pausa_desde") is not None:
                d["uso"]["pausas_s"] += self.rel() - d["uso"]["pausa_desde"]
                d["uso"]["pausa_desde"] = None
        self._evento(d, "autorizacao_negada", versao=reg["versao"], texto=f"o dono negou o plano v{reg['versao']}: nada será executado")
        try:
            self._parar_com(d, "bloqueado", "O dono negou a autorização; o plano não será executado.", tipo="autorizacao_negada", recuperavel=False, proxima="Nada foi executado. Faça outro pedido se quiser.")
        except Parar:
            pass
        return {"ok": True, "id": pcid}

    def executar(self, pcid):
        """Depois de um «só planejar»: pede para executar o plano pronto. Volta à fase de autorização (que ainda pode exigir o dono)."""
        d = self._com_dossie(pcid)
        if d is None:
            return {"ok": False, "erro": "objetivo desconhecido"}
        if d["estado"] != "plano_pronto":
            return {"ok": False, "erro": f"só dá para executar um plano pronto (estado: {d['estado']})"}
        reg = self._plano_reg(d)
        if not reg["plano"].get("executavel"):
            return {"ok": False, "erro": "este plano não tem nada para executar (o pedido não mandou guardar)"}
        with self.arm.trava:
            d["so_planejar"], d["resultado_final"] = False, None
            D.decisao(d, "dono", "pediu para executar o plano pronto", "volta à autorização", self.rel())
        self._ir_para(d, "autorizacao")
        self._acordar(d, "executar")
        return {"ok": True, "id": pcid}

    def cancelar(self, pcid, motivo="cancelado pelo dono"):
        d = self._com_dossie(pcid)
        if d is None:
            return {"ok": False, "erro": "objetivo desconhecido"}
        if d["estado"] in D.FINAIS:
            return {"ok": False, "erro": f"este objetivo já terminou (estado: {d['estado']})"}
        with self.arm.trava:
            d["cancelado"] = True
            self._cancelados.add(pcid)
        self.rot.cancelar(pcid)                                       # os trabalhadores param o que ainda não começou e avisam o que está rodando
        self._evento(d, "cancelamento_pedido", texto="cancelamento pedido; os trabalhadores foram avisados")
        t = self._threads.get(pcid)
        if t is None or not t.is_alive():
            self._finalizar_cancelado(d)
        return {"ok": True, "id": pcid}

    def retomar(self, pcid, auto=False):
        d = self._com_dossie(pcid)
        if d is None:
            return {"ok": False, "erro": "objetivo desconhecido"}
        b = d.get("bloqueio") or {}
        if d["estado"] == "bloqueado" and b.get("tipo") == "autorizacao_negada":
            with self.arm.trava:
                d["fase"] = "autorizacao"
            self._acordar(d, "retomar")
            return {"ok": True, "id": pcid, "nota": "vou pedir a autorização de novo"}
        if d["estado"] != "bloqueado" or not b.get("recuperavel"):
            return {"ok": False, "erro": "este objetivo não tem bloqueio recuperável (limites e rejeições da crítica não se retomam)"}
        self._evento(d, "retomada" + ("_automatica" if auto else ""), modulo=b.get("modulo"), texto=("retomada automática: " if auto else "retomada pelo dono: ") + f"o módulo «{b.get('modulo')}» voltou")
        self._acordar(d, "retomar")
        return {"ok": True, "id": pcid}

    def limpar_cenario(self):
        """Cancela o que está rodando e ARQUIVA dossiês e eventos temporários (os.replace para arquivo/<data>/). Experiências e notas do cofre não são tocadas. Nada é apagado."""
        for pcid in self.arm.ids():
            d = self.arm.obter(pcid)
            if d and d["estado"] not in D.FINAIS:
                self.cancelar(pcid, "cenário limpo")
        fim = time.time() + 5
        while time.time() < fim and any(t.is_alive() for t in list(self._threads.values())):
            time.sleep(0.05)
        with self.trava:
            self._cancelados.clear()
            self._auto.clear()
            self._ultimo_no.clear()
        destino = self.arm.arquivar_cenario()
        self._atual = None
        return {"ok": True, "arquivado_em": destino, "nota": "dossiês e eventos temporários foram movidos para a pasta de arquivo; experiências e memórias permanentes não foram tocadas"}

    # ------------------------------------------------------------------ saúde e vigia
    def atualizar_saude(self):
        self.ultima_saude = {"em": self.rel(), "workers": self.rot.saude()}
        # Em modo distribuído, PID novo indica reinício: reconstrói a janela do worker.
        for nome, estado in self.ultima_saude["workers"].items():
            pid = estado.get("pid") if estado.get("disponivel") else None
            marcador = (pid, estado.get("iniciado_em")) if pid is not None else None
            if marcador is not None and self._pids_contexto.get(nome) != marcador:
                destino = self.destinos.get(nome)
                if destino is not None:
                    self._replay_destino(nome, destino, pid=marcador)
        objs = [D.resumo(self.arm.obter(i)) for i in self.arm.ids()]
        try:
            msg = C.criar("hub", "monitor", "avaliar", {"saude": self.ultima_saude["workers"], "esperados": self.esperados(), "objetivos": objs, "agora": self.rel()}, correlacao="sistema",
                          timeout_s=3.0, agora=self.rel())
            r = self.rot.enviar(msg, 3.0)
            if r.get("ok"):
                self.ultimo_monitor = r["corpo"]
                self._registrar_atividade("monitor", "concluido", f"modo {r['corpo'].get('modo')}")
            else:
                self._registrar_atividade("monitor", "erro", str(r.get("erro", ""))[:80])
        except (TR.Indisponivel, TR.Recusado) as e:
            self._registrar_atividade("monitor", "erro", type(e).__name__)
        return self.ultimo_monitor

    def iniciar_vigia(self):
        if self._vigia is not None and self._vigia.is_alive():
            return
        self._vigia = threading.Thread(target=self._laco_vigia, name="pc-vigia", daemon=True)
        self._vigia.start()

    def _laco_vigia(self):
        while not self._fim.wait(self.cfg["saude_intervalo_s"]):
            try:
                self.vigiar()
            except Exception:                                              # noqa: BLE001  (o vigia nunca cai)
                pass

    def vigiar(self):
        """Uma volta do vigia: atualiza a saúde, acorda objetivos cuja espera acabou e retoma os que esperavam um módulo voltar."""
        self.atualizar_saude()
        mon = self.ultimo_monitor or {}
        for pcid in self.arm.ids():
            d = self.arm.obter(pcid)
            if d is None:
                continue
            t = self._threads.get(pcid)
            if t is not None and t.is_alive():
                continue
            if d["estado"] == "aguardando_confirmacao_do_corretor":
                self._conferir_espera_do_corretor(d)
            elif d["estado"] == "bloqueado" and (d.get("bloqueio") or {}).get("tipo") == "modulo_indisponivel":
                mod = d["bloqueio"].get("modulo")
                m = (mon.get("modulos") or {}).get(mod) or {}
                if m.get("estado") not in (None, "indisponivel") and self._auto[pcid] < 3:
                    self._auto[pcid] += 1
                    self.retomar(pcid, auto=True)

    def _conferir_espera_do_corretor(self, d):
        import tarefas as T
        regs = [r for r in d["execucoes"].values() if r.get("tarefa") and r["estado"] in ("aguardando_corretor", "executando")]
        if not regs:
            return
        r = regs[-1]
        if T.confirmacao_perdida(r["tarefa"]):
            self._evento(d, "confirmacao_perdida", tarefa=r["tarefa"], texto="a confirmação do corretor se perdeu (reinício ou expirou): nada foi executado")
            self._acordar(d, "confirmacao_perdida")
            return
        obs = EX.observar(r)
        if not obs["aguardando_corretor"]:
            self._evento(d, "corretor_respondeu", tarefa=r["tarefa"], estado=obs["estado"], texto=f"o corretor respondeu: tarefa {obs['tarefa']} {obs['rotulo']}")
            self._acordar(d, "corretor")

    # ------------------------------------------------------------------ recuperação depois de reinício
    def recuperar_tudo(self):
        """Chamada na partida: retoma o que estava no meio. Nunca repete uma execução (execucao.py)."""
        feitos = []
        for pcid in self.arm.ids():
            d = self.arm.obter(pcid)
            if d is None or d["estado"] in D.FINAIS:
                continue
            t = self._threads.get(pcid)
            if t is not None and t.is_alive():
                continue
            if d["estado"] in ("recebido", "em_andamento", "aguardando_execucao"):
                with self.arm.trava:
                    parado_s = max(0.0, self.rel() - d["atualizado_em"])
                    d["uso"]["pausas_s"] += parado_s                         # o tempo em que o programa esteve parado não gasta o orçamento do objetivo
                    d["estado"] = "em_andamento"
                self._salvar()
                self._evento(d, "recuperado", fase_retomada=d["fase"], parado_s=round(parado_s, 1), texto=f"recuperado depois de reinício; continuo da fase «{d['fase']}»")
                self._iniciar(pcid)
                feitos.append((pcid, "retomado", d["fase"]))
            elif d["estado"] == "aguardando_confirmacao_do_corretor":
                self._evento(d, "recuperado", fase_retomada=d["fase"], texto="recuperado: ainda esperando a confirmação do corretor")
                self._conferir_espera_do_corretor(d)
                feitos.append((pcid, "esperando_corretor", d["fase"]))
            elif d["estado"] == "aguardando_autorizacao":
                self._evento(d, "recuperado", fase_retomada=d["fase"], texto="recuperado: o plano continua esperando a autorização do dono")
                feitos.append((pcid, "esperando_dono", d["fase"]))
        return feitos

    # ------------------------------------------------------------------ leitura (painel, testes, voz)
    def esperar(self, pcid, timeout=30.0, ate=None):
        """Espera a linha do objetivo terminar (ou chegar a um dos estados de `ate`). Devolve o estado."""
        fim = time.time() + timeout
        while time.time() < fim:
            d = self.arm.obter(pcid)
            t = self._threads.get(pcid)
            vivo = t is not None and t.is_alive()
            if d is None:
                return None
            if (ate and d["estado"] in ate) or (not vivo and d["estado"] not in ATIVOS):
                return d["estado"]
            time.sleep(0.02)
        d = self.arm.obter(pcid)
        return d["estado"] if d else None

    def eventos(self, desde=0, objetivo=None, limite=500):
        return self.arm.eventos(desde, objetivo, limite)

    def dossie(self, pcid):
        return self.arm.copia(pcid)

    def detalhe(self, pcid):
        d = self.arm.copia(pcid)
        if d is None:
            return None
        return EXPL.detalhe(d, self.rel())

    def _estado_neuronios(self, agora):
        saude = self.ultima_saude["workers"]
        por_neuronio = {}
        for w, s in saude.items():
            if s.get("disponivel"):
                for n, e in (s.get("neuronios") or {}).items():
                    por_neuronio[n] = (w, e)
        nos_pendentes = collections.defaultdict(list)
        bloqueio_de = {}
        for pcid in self.arm.ids():
            d = self.arm.obter(pcid)
            if d is None:
                continue
            if d["estado"] == "bloqueado" and (d.get("bloqueio") or {}).get("modulo"):
                bloqueio_de[d["bloqueio"]["modulo"]] = pcid
            if d["estado"] in ATIVOS + ESPERANDO:
                for no in d["grafo"]:
                    if no["ciclo"] == d["ciclo"] and no["estado"] in ("pendente", "aguardando"):
                        nos_pendentes[no["neuronio"]].append(no["estado"])
        ativa_espera = any((self.arm.obter(i) or {}).get("estado") in ESPERANDO for i in self.arm.ids())
        saida = []
        for desc in K.descricoes():
            n = desc["nome"]
            w, e = por_neuronio.get(n, (self.local_de.get(n), None))
            sh = saude.get(w) if w else None
            fora = bool(w) and n != "coordenacao" and (sh is None or not sh.get("disponivel", False)) and bool(saude)
            ult = self._ultimo_no.get(n)
            recente = ult is not None and agora - ult[1] < PERSISTE_S
            if n == "coordenacao":
                estado = "aguardando" if ativa_espera else ("processando" if any(t.is_alive() for t in self._threads.values()) and not (ult and ult[0] in ("concluido", "erro") and recente) else
                                                              ult[0] if recente else "ocioso")
                w = "hub"
            elif fora:
                estado = "bloqueado" if desc["critico"] else "erro"
            elif n in bloqueio_de:
                estado = "bloqueado"
            elif self._em_voo[n] > 0:
                estado = "processando" if (e and e.get("em_andamento")) else "recebendo"
            elif nos_pendentes.get(n):
                estado = "aguardando"
            elif recente:
                estado = ult[0] if ult[0] in ("concluido", "erro", "aguardando", "processando") else "ocioso"
            else:
                estado = "ocioso"
            mon = ((self.ultimo_monitor or {}).get("modulos") or {}).get(n) or {}
            saida.append({"numero": desc["numero"], "nome": n, "papel": desc["papel"], "critico": desc["critico"], "trabalhador": w, "tipo": (sh or {}).get("tipo") if sh else ("hub" if n == "coordenacao" else None),
                          "estado": estado, "em_voo": self._em_voo[n], "recebidas": (e or {}).get("recebidas"), "concluidas": (e or {}).get("concluidas"), "falhas": (e or {}).get("falhas"),
                          "duplicadas": (e or {}).get("duplicadas"), "ultimo_erro": (e or {}).get("ultimo_erro") or "", "ultima_acao": (e or {}).get("ultima_acao") or "",
                          "tempo_medio_ms": (e or {}).get("tempo_medio_ms"), "tempo_p95_ms": (e or {}).get("tempo_p95_ms"), "pid": (sh or {}).get("pid") if sh else None,
                          "confianca": mon.get("confianca"), "ultimo_resumo": ult[2] if ult else ""})
        return saida

    def estado(self, selecionado=None, atualizar=True):
        agora = self.rel()
        if atualizar and agora - self.ultima_saude["em"] > 0.35:
            try:
                self.atualizar_saude()
            except Exception:                                                  # noqa: BLE001
                pass
        ids = self.arm.ids()
        objetivos = [D.resumo(self.arm.obter(i)) for i in ids]
        objetivos.sort(key=lambda o: o["criado_em"], reverse=True)
        atual = selecionado if selecionado in ids else (self._atual if self._atual in ids else (objetivos[0]["id"] if objetivos else None))
        erros = [e for e in self.arm.eventos(0, None, 400) if e["tipo"] in ("modulo_indisponivel", "tentativa_falhou", "erro_interno", "execucao_barrada", "limite_atingido", "laco_detectado")][-12:]
        contagem = collections.Counter(o["estado"] for o in objetivos)
        mon = self.ultimo_monitor or {}
        return {"agora": agora, "contrato": C.VERSAO, "modo": self.cfg["modo"], "backend": self.cfg["backend"], "persistente": self.arm.persistente, "seq": self.arm.seq,
                "neuronios": self._estado_neuronios(agora), "objetivos": objetivos[:30], "atual": atual, "detalhe": self.detalhe(atual) if atual else None,
                "operacional": {"modo_de_operacao": mon.get("modo", "desconhecido"), "alertas": mon.get("alertas", []), "trabalhadores": self.ultima_saude["workers"],
                                "trabalhadores_resumo": mon.get("trabalhadores", {}), "modulos": mon.get("modulos", {}), "por_estado": dict(contagem),
                                "pendentes": sum(contagem.get(k, 0) for k in ATIVOS + ESPERANDO), "erros_recentes": erros, "saude_em": self.ultima_saude["em"],
                                "objetivos_parados": (mon.get("objetivos") or {}).get("parados", []), "armazem": {"erros": self.arm.erros, "ultimo_erro": self.arm.ultimo_erro}},
                "config": self.cfg.publica(), "avisos": self.avisos}

    def encerrar(self, esperar_s=3.0):
        """Para as linhas e libera os recursos DESTE hub (testes e o lançador da demonstração). Não existe rota nem ferramenta que chame isto."""
        self._fim.set()
        fim = time.time() + esperar_s
        for t in list(self._threads.values()):
            t.join(max(0.0, fim - time.time()))
        self.pool.shutdown(wait=False, cancel_futures=True)
        for w in self.trabalhadores.values():
            w.encerrar_pool()
        self.memoria_coletiva.encerrar()
        if hasattr(self, "_pool_eventos"):
            self._pool_eventos.shutdown(wait=False, cancel_futures=True)
