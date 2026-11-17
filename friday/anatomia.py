"""Anatomia da FRIDAY: as estruturas do cérebro descritas na página da UFES (https://citogenetica.ufes.br/pt-br/cerebro) viram regiões do cérebro dela.

É um MODELO inspirado no cérebro humano, para organizar e enxergar o sistema: não é consciência nem biologia.
  - cada região tem: o que a página diz que ela faz (campo `ufes`, quase literal) e o que ela é na FRIDAY (campo `friday`, escolha de projeto);
  - cada neurônio (nota do Obsidian) pertence a UMA região, decidida por uma regra fixa (`regiao_de`), nunca por um modelo de IA;
  - o lado (esquerdo/direito) é só visual: a página fala em dois hemisférios ligados pelo corpo caloso, mas aqui o lado não muda nada no funcionamento.
O que a página NÃO traz (e portanto não foi copiado dela): papel específico de cada neurotransmissor, sono, tálamo, hipotálamo, amígdala, gânglios da base."""
import re
import unicodedata

# pos = (x, y, z) num cérebro de tamanho 1: x = frente (+) / trás (-), y = baixo (+) / cima (-), z = lado (o sinal vem do lado do neurônio).
REGIOES = {
    "frontal": {
        "nome": "Lobo frontal", "cor": [255, 212, 59], "pos": [0.60, -0.20, 0.34], "lado": True,
        "ufes": "pensamento, planejamento e movimento",
        "friday": "planejar e decidir: decisões, projetos, tarefas e pedidos de evolução; no código, o raciocínio do modelo (cerebro.py), as rotinas e o pré-córtex (prefrontal.py: metas, atenção e a decisão de agir)",
        "modulos": ["cerebro.py", "autonomia.py", "prefrontal.py"]},
    "cortex_motor": {
        "nome": "Córtex motor", "cor": [255, 107, 61], "pos": [0.16, -0.58, 0.34], "lado": True,
        "ufes": "coordena os movimentos voluntários",
        "friday": "agir: as ferramentas que mexem no mundo (mensagem, ligação, relé, arquivo). Quem decide se o movimento acontece é o corretor",
        "modulos": ["broker.py", "catalogo.py", "android.py"]},
    "parietal": {
        "nome": "Lobo parietal", "cor": [64, 224, 208], "pos": [-0.30, -0.52, 0.36], "lado": True,
        "ufes": "processamento sensorial e espacial",
        "friday": "perceber o que vem de fora: sensores do celular, as ferramentas só de leitura e o que ela estuda na internet (dado não verificado)",
        "modulos": ["telemetria.py", "internet.py"]},
    "temporal": {
        "nome": "Lobo temporal", "cor": [108, 140, 255], "pos": [0.10, 0.30, 0.56], "lado": True,
        "ufes": "audição e memória",
        "friday": "o que ela sabe: fatos seus e os tópicos que ela consolidou das suas conversas",
        "modulos": ["memoria.py"]},
    "occipital": {
        "nome": "Lobo occipital", "cor": [150, 160, 182], "pos": [-0.74, -0.10, 0.28], "lado": True,
        "ufes": "visão",
        "friday": "ver: a câmera (do celular, do navegador, do servidor ou do corpo que você construir) vira texto e cada coisa que ela aprende a ver vira um neurônio aqui",
        "modulos": ["visao.py"]},
    "mesencefalo": {
        "nome": "Cérebro médio", "cor": [79, 209, 255], "pos": [-0.02, 0.38, 0.0], "lado": False,
        "ufes": "controle dos movimentos oculares e processamento auditivo",
        "friday": "escutar: o reconhecimento de voz (navegador, Android ou faster-whisper no seu servidor) e a voz que fala (Kokoro). Os olhos ficam no lobo occipital",
        "modulos": ["voz.py", "voz_remota.py"]},
    "cerebelo": {
        "nome": "Cerebelo", "cor": [91, 227, 160], "pos": [-0.58, 0.52, 0.22], "lado": True,
        "ufes": "coordenação motora e equilíbrio",
        "friday": "coordenar sequências e manter o equilíbrio: protocolos, hábitos, rotinas e o ajuste do sono que impede um neurônio de dominar a rede",
        "modulos": ["protocolos.py", "autonomia.py"]},
    "tronco": {
        "nome": "Tronco cerebral", "cor": [226, 240, 255], "pos": [-0.22, 0.80, 0.0], "lado": False,
        "ufes": "controla funções vitais, como respiração e batimentos cardíacos",
        "friday": "manter-se viva: identidade, regras de segurança, auditoria e os sinais vitais (laços ativos, trilha íntegra, cofre gravável)",
        "modulos": ["broker.py", "diagnostico.py", "vida.py"]},
    "hipocampo": {
        "nome": "Hipocampo", "cor": [178, 139, 255], "pos": [-0.12, 0.24, 0.26], "lado": True,
        "ufes": "envolvido no aprendizado e na formação de memórias",
        "friday": "aprender e formar memórias: os dias de conversa (episódios), o repasse e a consolidação durante o sono",
        "modulos": ["memoria.py", "neuronios.py"]},
    "limbico": {
        "nome": "Sistema límbico", "cor": [255, 95, 168], "pos": [0.12, 0.02, 0.15], "lado": True,
        "ufes": "processamento emocional, controle de comportamentos ligados às emoções, e memória",
        "friday": "o que importa para ela: as pessoas e as preferências, mais o estado interno (humor, energia, curiosidade) que muda o comportamento",
        "modulos": ["vida.py", "conversa.py"]},
}
ORDEM = ["frontal", "cortex_motor", "parietal", "temporal", "occipital", "mesencefalo", "cerebelo", "tronco", "hipocampo", "limbico"]

# o que a página cita e que NÃO é uma região de neurônios: vira mecanismo no código
SISTEMAS = {
    "corpo_caloso": {"nome": "Corpo caloso", "ufes": "permite a comunicação entre os dois hemisférios",
                     "friday": "a ponte entre os dois lados dela: nuvem e modelo local (Ollama), celular e servidor privado. Se um lado cai, o outro assume"},
    "autonomo": {"nome": "Sistema nervoso autônomo", "ufes": "regula funções automáticas, como respiração e digestão",
                 "friday": "os laços de fundo que rodam sem você pedir: sono, devaneio, rotinas, estudo, sinais vitais"},
    "sensorial": {"nome": "Sistema sensorial", "ufes": "processa estímulos de visão, audição, tato, paladar e olfato",
                  "friday": "as ferramentas de nível 0 (só leitura), o microfone e a câmera (visão.py). Tato, paladar e olfato não existem"},
    "plasticidade": {"nome": "Plasticidade neural", "ufes": "adapta-se e muda em resposta a estímulos, aprendizado e experiências",
                     "friday": "a regra de Hebb: o que é lembrado junto se liga mais; o que não se usa enfraquece no sono"},
    "neurotransmissores": {"nome": "Neurotransmissores", "ufes": "dopamina, serotonina e acetilcolina têm papéis no humor, na cognição e nas funções motoras",
                           "friday": "três níveis internos (vida.py). A página não diz o papel de cada um: o papel que dei a cada nível (motivação, humor, atenção) vem do conhecimento geral, não dela"},
}

_TIPO_PARA_REGIAO = {"decisao": "frontal", "projeto": "frontal", "tarefa": "frontal", "pedido": "frontal",
                     "fato": "temporal", "topico": "temporal", "estudo": "parietal", "visao": "occipital", "conversa": "hipocampo",
                     "pessoa": "limbico", "preferencia": "limbico"}

# notas da pasta Eu (o autoconhecimento): a região depende do assunto da nota
_EU_FIXAS = {"friday eu": "tronco", "regras de seguranca": "tronco", "memoria e cerebro": "hipocampo", "protocolos": "cerebelo",
             "autonomia e rotinas": "cerebelo", "pedidos de evolucao": "frontal", "voz e sentidos": "mesencefalo",
             "regioes do cerebro": "tronco", "vida e humor": "limbico", "curiosidade e estudo": "parietal", "conversa e brincadeiras": "limbico", "visao e lobo occipital": "occipital"}


def _dobrar(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


# cada ferramenta cai na região do que ela É: sentir, lembrar, aprender, planejar, coordenar ou agir (o nível de risco não define a região)
FERRAMENTA_REGIAO = {
    "parietal": "clima_agora hora_data leads_novos ler_pagina pesquisar_web resumo_do_dia status_celular status_sistema localizacao relatorio_sistemas listar_arquivos",
    "temporal": "lembrar ler_notas cerebro_status",
    "hipocampo": "guardar_memoria anotar consolidar_memoria esquecer_memoria",
    "frontal": "criar_lembrete listar_lembretes pedir_evolucao listar_pedidos_evolucao silenciar voltar_a_falar",
    "cerebelo": "listar_protocolos",
    "cortex_motor": "enviar_sms ligar rele lanterna vibrar notificar compartilhar_arquivo criar_arquivo preparar_whatsapp exportar_cerebro",
}
_POR_FERRAMENTA = {n: r for r, nomes in FERRAMENTA_REGIAO.items() for n in nomes.split()}


def regioes_das_ferramentas(ferramentas):
    """{'ferramenta ler pagina': 'parietal', ...}. Ferramenta nova, ainda sem lugar na tabela, cai pelo nível: leitura (0) = parietal, o resto = córtex motor."""
    r = {}
    for nome, f in ferramentas.items():
        nv = f.get("nivel")
        padrao = "parietal" if nv == 0 else "cortex_motor"
        r[_dobrar("ferramenta " + nome.replace("_", " "))] = _POR_FERRAMENTA.get(nome, padrao)
    return r


def regiao_de(grupo, titulo="", ferramentas=None):
    """Região (id) de um neurônio. `ferramentas` é o resultado de regioes_das_ferramentas(); sem ele, ferramenta vira córtex motor. Sempre devolve uma região válida."""
    if grupo in _TIPO_PARA_REGIAO:
        return _TIPO_PARA_REGIAO[grupo]
    t = _dobrar(titulo)
    if grupo == "eu":
        if t in _EU_FIXAS:
            return _EU_FIXAS[t]
        if t.startswith("protocolo"):
            return "cerebelo"
        if t.startswith("sentidos"):
            return "parietal"
        if t.startswith("acoes"):
            return "cortex_motor"
        if t.startswith("ferramenta"):
            return (ferramentas or {}).get(t, "cortex_motor")
        return "tronco"
    return "temporal"


def meta(contagem=None):
    """Descrição das regiões para o painel e o 3D: {id: {nome, cor, pos, lado, ufes, friday, n}}."""
    contagem = contagem or {}
    return {k: {"nome": v["nome"], "cor": v["cor"], "pos": v["pos"], "lado": v["lado"], "ufes": v["ufes"], "friday": v["friday"], "n": int(contagem.get(k, 0))}
            for k, v in REGIOES.items()}


def contar(regioes):
    c = {k: 0 for k in REGIOES}
    for r in regioes:
        if r in c:
            c[r] += 1
    return c


def falar(contagem, usos=None):
    """Resumo falado das regiões. `usos` = {região: disparos} para dizer qual ela mais usa."""
    vazias = [REGIOES[k]["nome"] for k in ORDEM if not contagem.get(k)]
    cheias = sorted((k for k in ORDEM if contagem.get(k)), key=lambda k: -contagem[k])
    if not cheias:
        return "Ainda não tenho neurônios em nenhuma região. Me conte coisas e eu começo a povoar o cérebro."
    topo = ", ".join(f"{REGIOES[k]['nome'].lower()} com {contagem[k]}" for k in cheias[:3])
    t = f"Meu cérebro tem {len(REGIOES)} regiões, inspiradas no humano. As mais povoadas: {topo}."
    if usos:
        mais = max(usos, key=usos.get)
        if usos[mais] > 0:
            t += f" A que mais uso é o {REGIOES[mais]['nome'].lower()}: {REGIOES[mais]['friday'].split(':')[0]}."
    if "Lobo occipital" in vazias:
        t += " O lobo occipital está vazio: ainda não aprendi a ver nada."
    return t


def descrever(chave):
    """Fala o que é uma região ou sistema, para 'o que é o hipocampo?'. None se não reconhecer."""
    c = _dobrar(chave)
    for k, v in REGIOES.items():
        if c in (k, _dobrar(v["nome"]), _dobrar(v["nome"]).replace("lobo ", "").replace("sistema ", "").replace("cerebro ", "")) or c == _dobrar(k.replace("_", " ")):
            return f"{v['nome']}: na página da UFES, {v['ufes']}. Em mim, {v['friday']}."
    for k, v in SISTEMAS.items():
        if c in (k, _dobrar(v["nome"]), _dobrar(k.replace("_", " "))):
            return f"{v['nome']}: na página da UFES, {v['ufes']}. Em mim, {v['friday']}."
    return None


_PERGUNTA_REGIAO = re.compile(r"^(?:o que e|o que faz|para que serve|pra que serve|fale d[oa]|me fale d[oa]|explique)\s+(?:o |a )?(?:seu |sua )?(.+)$")
_REGIOES_LISTA = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:quais (?:sao )?(?:as )?(?:suas )?regioes(?: do (?:seu )?cerebro)?|(?:me )?(?:fale|conte) (?:das|sobre as) (?:suas )?regioes(?: do (?:seu )?cerebro)?|como e (?:o )?seu cerebro por dentro|anatomia do seu cerebro|como (?:e )?(?:o )?seu cerebro (?:esta )?organizado)$")


def eh_lista(f):
    return bool(_REGIOES_LISTA.match(f))


def eh_pergunta_de_regiao(f):
    """f já vem dobrada (sem acento, minúscula). Devolve a resposta falada ou None."""
    m = _PERGUNTA_REGIAO.match(re.sub(r"^(?:friday|jarvis|fraide)[ ,]+", "", f))
    return descrever(m.group(1)) if m else None
