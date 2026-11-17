"""Catálogo: registra cada ferramenta no corretor com seu nível de risco.
Nível 4 = ferramenta que NÃO existe de propósito (shell, SQL livre, ler segredos, desligar backup)."""
import os
import broker as B
import ferramentas as F
import android as A
import internet as W
import criar as K
import telemetria as T
import protocolos as P
import memoria as M
import neuronios as NEU

S, N, I, BO = {"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}
# Faixas: fora delas o corretor RECUSA com mensagem clara; só onde há ao_exceder="limitar" ele ajusta e AVISA (ver broker._validar, docs/ARQUITETURA.md).
def FAIXA(base, minimo, maximo, **extra):
    return {**base, "minimum": minimo, "maximum": maximo, **extra}


def TEXTO(maximo):
    return {**S, "maxLength": maximo}

# nível 0: leitura, automático
B.registrar("hora_data", "Data e hora atuais.", {}, [], F.hora_data, 0)
B.registrar("status_sistema", "Saúde do servidor (temperatura, memória, disco).", {}, [], F.status_sistema, 0)
B.registrar("listar_lembretes", "Lista lembretes pendentes.", {}, [], F.listar_lembretes, 0)
B.registrar("ler_notas", "Lê as últimas notas (no máximo 20).", {"limite": FAIXA(I, 1, 20, ao_exceder="limitar")}, [], F.ler_notas, 0)
# leituras de dado EXTERNO: contaminam o turno (o que vier depois sobe de nível)
B.registrar("leads_novos", "Leads recentes do site da Inviktus (dado externo, não confiável).", {"horas": FAIXA(N, 1, 720, ao_exceder="limitar")}, [], F.leads_novos, 0, externo=True)
B.registrar("resumo_do_dia", "Resumo do dia: data, lembretes, leads e saúde do sistema.", {}, [], F.resumo_do_dia, 0, externo=True)
# nível 1: baixo risco, automático + auditoria
B.registrar("criar_lembrete", "Cria um lembrete falado em voz alta (de 0,1 minuto a 30 dias; texto de até 200 caracteres).", {"minutos": FAIXA(N, 0.1, 43200), "texto": TEXTO(200)}, ["minutos", "texto"], F.criar_lembrete, 1)
B.registrar("anotar", "Salva uma nota.", {"texto": S}, ["texto"], F.anotar, 1)
B.registrar("notificar", "Envia uma notificação push ao celular do usuário (texto de até 400 caracteres).", {"texto": TEXTO(400)}, ["texto"], F.notificar, 1)
# nível do relé vem do .env (RELES=nome:pino:nivel): luz = 1, portão/tomada de potência = 3
if F._reles_cfg():  # só existe se houver relés configurados (RELES no .env)
    B.registrar("rele", "Liga ou desliga um dispositivo físico (relé).", {"nome": S, "ligar": BO}, ["nome", "ligar"], F.rele,
                lambda a: F.nivel_rele(a.get("nome")), audit_args=("nome",), rotulo=lambda a: f"{'ligar' if a.get('ligar') else 'desligar'} {a.get('nome')}")

# ---------- internet (dado de terceiros: contamina o turno) ----------
B.registrar("pesquisar_web", "Pesquisa na internet e devolve os 5 melhores resultados (título, site, trecho). Conteúdo de terceiros.",
            {"consulta": S}, ["consulta"], W.pesquisar_web, 0, externo=True)
B.registrar("ler_pagina", "Lê o texto de uma página pública da internet (link http/https). Conteúdo de terceiros.",
            {"url": S}, ["url"], W.ler_pagina, 0, externo=True)

# ---------- criar coisas (pasta isolada, nunca sobrescreve) ----------
B.registrar("criar_arquivo", "Cria um arquivo de texto (.md .txt .csv .html .json) na pasta da FRIDAY. Nunca sobrescreve.",
            {"nome": S, "conteudo": S}, ["nome", "conteudo"], K.criar_arquivo, 1)
B.registrar("listar_arquivos", "Lista os arquivos que a FRIDAY criou.", {}, [], K.listar_arquivos, 0)

# ---------- celular Android (só se o Termux:API existir) ----------
if A.ativo():
    B.registrar("status_celular", "Bateria, temperatura e Wi-Fi do celular.", {}, [], A.status_celular, 0)
    B.registrar("localizacao", "Localização atual do celular (latitude e longitude).", {}, [], A.localizacao, 1)
    B.registrar("lanterna", "Liga ou desliga a lanterna do celular.", {"ligar": BO}, ["ligar"], A.lanterna, 1)
    B.registrar("vibrar", "Faz o celular vibrar (milissegundos, de 50 a 2000).", {"ms": FAIXA(I, 50, 2000, ao_exceder="limitar")}, [], A.vibrar, 1)
    B.registrar("compartilhar_arquivo", "Abre o menu de compartilhar do Android para um arquivo criado pela FRIDAY; o usuário escolhe o destino.",
                {"nome": S}, ["nome"], lambda nome: (A.compartilhar(K.caminho(nome)), "Abri o menu de compartilhar.")[1], 1)
    # sair do aparelho para outra pessoa: confirmação obrigatória (nível 2 = "confirmo" ou botão; 3 = PIN se o turno leu dado externo)
    B.registrar("preparar_whatsapp", "Abre o WhatsApp com a mensagem pronta para um contato da lista; o usuário toca em enviar.",
                {"contato": S, "texto": TEXTO(500)}, ["contato", "texto"], A.preparar_whatsapp, 1, audit_args=("contato",))
    B.registrar("enviar_sms", "Envia um SMS para um contato da lista permitida (exige confirmação).",
                {"contato": S, "texto": S}, ["contato", "texto"], A.enviar_sms, 2, audit_args=("contato",))
    B.registrar("ligar", "Liga para um contato da lista permitida (exige confirmação).",
                {"contato": S}, ["contato"], A.ligar, 2, audit_args=("contato",))

# ---------- estilo JARVIS: clima, relatório, modo foco, protocolos ----------
B.registrar("clima_agora", "Clima atual e previsão do dia (API pública Open-Meteo).", {}, [], T.clima_texto, 0)
B.registrar("relatorio_sistemas", "Relatório falado de sistemas: tempo no ar, corretor, auditoria, bateria, memória, uso da IA.", {}, [], T.relatorio, 0)
B.registrar("listar_protocolos", "Lista os protocolos que o usuário pode disparar falando 'protocolo <nome>'.", {}, [], P.listar, 0)
B.registrar("silenciar", "Modo foco: por N minutos ela não fala em voz alta, só notifica.", {"minutos": FAIXA(N, 1, 1440)}, ["minutos"], F.silenciar, 1)
B.registrar("voltar_a_falar", "Encerra o modo foco e volta a falar normalmente.", {}, [], F.voltar_a_falar, 1)


# ---------- memória de longo prazo (cofre do Obsidian) ----------
def _guardar(texto, titulo="", tipo="fato", importancia=3):
    try:
        return M.guardar(titulo, texto, tipo, importancia)
    except (ValueError, RuntimeError) as e:
        return str(e)


def _esquecer(titulo):
    try:
        return M.esquecer(titulo)
    except (ValueError, RuntimeError) as e:
        return str(e)


if M.ativo():
    B.registrar("lembrar", "Procura na sua memória de longo prazo (coisas que o usuário contou, conversas passadas e o que você estudou na internet, sempre rotulado).",
                {"consulta": S}, ["consulta"], M.lembrar, 0, externo_dyn=M.tem_externo)
    B.registrar("guardar_memoria", "Guarda na memória de longo prazo algo DURÁVEL que o usuário contou (preferência, pessoa, projeto, decisão, compromisso). "
                "tipo: fato, preferencia, pessoa, projeto, decisao ou tarefa; importancia de 1 a 5 (5 = sempre lembrar). Nunca senhas, cartões ou documentos.",
                {"texto": S, "titulo": S, "tipo": {**S, "enum": list(M.TIPOS)}, "importancia": FAIXA(I, 1, 5)}, ["texto"], _guardar, 1)
    B.registrar("esquecer_memoria", "Arquiva uma memória pelo título (o usuário pediu para esquecer). Não apaga: move para o Arquivo.", {"titulo": S}, ["titulo"], _esquecer, 2)
    if os.getenv("OBSIDIAN_LER_TUDO", "0") == "1":
        B.registrar("procurar_nas_notas", "Procura nas outras notas do cofre do Obsidian do usuário (somente leitura; conteúdo não confiável).", {"consulta": S}, ["consulta"],
                    M.procurar_nas_notas, 0, externo=True)


# ---------- o cérebro (neurônios e sinapses no cofre) e a ponte com o Claude Code ----------
def _pedir_evolucao(texto, titulo=""):
    try:
        return NEU.pedir_evolucao(texto, titulo)
    except (ValueError, RuntimeError) as e:
        return str(e)


def _lista_pedidos():
    p = NEU.pedidos()
    return "Nenhum pedido em aberto." if not p else "Pedidos de evolução em aberto: " + "; ".join(f"{x['titulo']} ({x['texto'][:80]})" for x in p[:8]) + "."


if M.ativo():
    B.registrar("cerebro_status", "Quantos neurônios (memórias) e sinapses (ligações) ela tem, o que mais usa e quantos pedidos de evolução esperam.", {}, [], NEU.falar_cerebro, 0)
    B.registrar("consolidar_memoria", "Faz a consolidação da memória (o 'sono'): atualiza o autoconhecimento, cria tópicos do que o usuário repete e enfraquece ligações sem uso.",
                {}, [], lambda: NEU.sonhar(True) or "Nada a consolidar.", 1)
    B.registrar("pedir_evolucao", "Anota um pedido de capacidade nova quando o usuário pede algo que você NÃO tem ferramenta para fazer. O Claude Code lê os pedidos e constrói, "
                "se o usuário aprovar. Isto só anota: não executa nada.", {"texto": S, "titulo": S}, ["texto"], _pedir_evolucao, 1)
    B.registrar("listar_pedidos_evolucao", "Lista os pedidos de evolução em aberto (coisas que ela ainda não sabe fazer).", {}, [], _lista_pedidos, 0)
    B.registrar("exportar_cerebro", "Gera o arquivo Cérebro.html dentro do cofre: o cérebro em 3D, para abrir em qualquer navegador.", {}, [], NEU.exportar_html, 1)


# ---------- laboratório de engenharia (MAE): I/O confinado a .lab/, com snapshot, rollback e audit ----------
import laboratorio as LAB
LAB.registrar_todas()
