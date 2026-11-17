"""Configuração do pré-córtex: limites, tempos, modo (local ou distribuído) e onde cada neurônio roda.

Ordem de precedência: padrões do código < arquivo JSON (PRECORTEX_CONFIG) < variáveis de ambiente PRECORTEX_*. Valor fora da faixa NÃO é aceito: volta ao padrão e
o aviso fica em `Config.avisos` (aparece no painel e no relatório). A chave de sessão entre os processos (PRECORTEX_TOKEN) só vem do ambiente — um arquivo de
configuração com «token» é ignorado, para nenhum segredo parar no git.

Duas coisas NÃO são configuráveis, de propósito: a crítica independente é obrigatória (nenhuma chave a desliga) e nada que o aprendizado ajusta alcança os
limites de segurança. Tentar desligá-las pelo arquivo ou pelo ambiente só gera um aviso.
"""
import json
import os

PADROES = {
    "modo": "local",                     # local | distribuido
    "backend": "deterministico",         # único implementado; veja docs/PRE_CORTEX.md (modelo de linguagem opcional: ponto de extensão, não incluído)
    "timeout_msg_s": 15.0,               # espera por resposta em cada tentativa
    "tentativas_msg": 3,                 # reenvios (mesmo id) antes de dar o módulo por indisponível
    "espera_entre_tentativas_s": 0.2,
    "max_replanos": 3,                   # planos NOVOS depois do primeiro, por objetivo
    "max_revisoes_critica": 3,           # vezes que a crítica pode devolver o plano antes de o objetivo ser bloqueado
    "max_tempo_objetivo_s": 120.0,       # tempo total de um objetivo (sem contar a espera por autorização do dono)
    "max_nos_por_objetivo": 80,          # mensagens/etapas executadas por objetivo (recurso)
    "max_paralelo": 4,                   # etapas independentes ao mesmo tempo
    "timeout_execucao_s": 30.0,          # quanto o hub espera a execução pelo corretor antes de marcá-la «demorando»
    "ritmo_demo_s": 0.0,                 # pausa entre fases, só para um humano acompanhar na tela (0 = sem pausa); aparece nos eventos
    "saude_intervalo_s": 2.0,            # de quanto em quanto tempo o hub consulta a saúde dos trabalhadores
    "eventos_em_memoria": 3000,
    "workers": {},                       # distribuido: {"cognicao": {"url": "http://127.0.0.1:9101"}, "revisao": {"url": "http://127.0.0.1:9102"}}
}
FAIXAS = {
    "timeout_msg_s": (0.05, 600.0), "tentativas_msg": (1, 10), "espera_entre_tentativas_s": (0.0, 30.0), "max_replanos": (0, 10), "max_revisoes_critica": (0, 10),
    "max_tempo_objetivo_s": (1.0, 7200.0), "max_nos_por_objetivo": (5, 1000), "max_paralelo": (1, 16), "timeout_execucao_s": (0.5, 3600.0), "ritmo_demo_s": (0.0, 10.0),
    "saude_intervalo_s": (0.2, 600.0), "eventos_em_memoria": (100, 100000),
}
MODOS = ("local", "distribuido")
PROIBIDAS = ("critica_obrigatoria", "critica", "sem_critica", "desligar_critica", "autonomia", "nivel_max", "pular_autorizacao")


class Config(dict):
    def __init__(self, base=None):
        super().__init__(PADROES)
        self.avisos = []
        if base:
            self.aplicar(base, "arquivo")

    def aplicar(self, d, de):
        for k, v in d.items():
            if k in PROIBIDAS:
                self.avisos.append(f"{de}: «{k}» não é configurável (a crítica independente e os limites de segurança não se desligam por configuração); ignorado")
            elif k == "token":
                self.avisos.append(f"{de}: a chave de sessão só vem do ambiente (PRECORTEX_TOKEN), nunca de arquivo; ignorado")
            elif k not in PADROES:
                self.avisos.append(f"{de}: chave desconhecida «{str(k)[:30]}»; ignorada")
            else:
                self._definir(k, v, de)

    def _definir(self, k, v, de):
        if k == "modo":
            if v in MODOS:
                self[k] = v
            else:
                self.avisos.append(f"{de}: modo {str(v)[:20]!r} inválido (use {' ou '.join(MODOS)}); mantido {self[k]!r}")
        elif k == "backend":
            if v == "deterministico":
                self[k] = v
            else:
                self.avisos.append(f"{de}: backend {str(v)[:20]!r} não existe nesta versão (só «deterministico»); mantido")
        elif k == "workers":
            ok = isinstance(v, dict) and all(isinstance(n, str) and isinstance(x, dict) and isinstance(x.get("url"), str) and x["url"].startswith(("http://", "https://"))
                                             and (x.get("neuronios") is None or (isinstance(x["neuronios"], list) and all(isinstance(z, str) for z in x["neuronios"]))) for n, x in v.items())
            if ok:
                self[k] = {n: {"url": x["url"].rstrip("/"), **({"neuronios": list(x["neuronios"])} if x.get("neuronios") else {})} for n, x in v.items()}
            else:
                self.avisos.append(f"{de}: «workers» precisa ser {{nome: {{url: http://…, neuronios: […] (opcional)}}}}; ignorado")
        else:
            a, b = FAIXAS[k]
            tipo = type(PADROES[k])
            try:
                n = tipo(v) if not isinstance(v, bool) else None
            except (TypeError, ValueError):
                n = None
            if n is None or n != n or not a <= n <= b:
                self.avisos.append(f"{de}: {k}={str(v)[:20]!r} fora da faixa {a}–{b}; mantido {self[k]!r}")
            else:
                self[k] = n

    @classmethod
    def carregar(cls, env=None):
        env = os.environ if env is None else env
        c = cls()
        arq = (env.get("PRECORTEX_CONFIG") or "").strip()
        if arq:
            try:
                with open(arq, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    c.aplicar({k: v for k, v in d.items() if not k.startswith("_")}, "arquivo")
                else:
                    c.avisos.append("arquivo: o JSON de configuração precisa ser um objeto")
            except (OSError, ValueError) as e:
                c.avisos.append(f"arquivo: não consegui ler {os.path.basename(arq)}: {type(e).__name__}")
        e_env = {}
        for k in PADROES:
            v = env.get("PRECORTEX_" + k.upper())
            if v is not None and k != "workers":
                e_env[k] = v
        for k in PROIBIDAS:
            if env.get("PRECORTEX_" + k.upper()) is not None:
                c.avisos.append(f"ambiente: PRECORTEX_{k.upper()} não é aceito; ignorado")
        c.aplicar(e_env, "ambiente")
        ws = env.get("PRECORTEX_WORKERS")
        if ws:
            try:
                c.aplicar({"workers": json.loads(ws)}, "ambiente")
            except ValueError:
                c.avisos.append("ambiente: PRECORTEX_WORKERS não é JSON válido; ignorado")
        return c

    def publica(self):
        return {**self, "avisos": list(self.avisos)}
