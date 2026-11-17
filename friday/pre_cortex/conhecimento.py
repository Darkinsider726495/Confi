"""Conhecimento de domínio do backend determinístico: currículos-base e o gerador do plano de estudo.

Isto é um modelo de dados do código, não uma pesquisa: os currículos abaixo são um esqueleto razoável escrito à mão, SEM consulta à internet e SEM conferência por
fonte externa. Todo plano gerado carrega essa origem (`FONTE`). Assunto que não está aqui NÃO é inventado: a percepção avisa que falta conhecimento e o objetivo
fica esperando o dono (ou um currículo novo).
"""
import re

FONTE = "currículo-base interno do código (escrito à mão; não foi consultado na internet nem conferido por fonte externa)"
DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
MAX_SEMANAS = 6
MIN_MINUTOS, MAX_MINUTOS = 15, 600
PADRAO_MINUTOS = 60

CURRICULOS = {
    "python": {
        "nome": "Python",
        "semanas": [
            ("Fundamentos", ["Instalação, REPL e primeiro script", "Variáveis e tipos", "Operadores e condicionais", "Laços for e while", "Funções e parâmetros", "Exercícios de revisão", "Mini-projeto: calculadora"]),
            ("Estruturas de dados", ["Listas", "Tuplas e conjuntos", "Dicionários", "Compreensões", "Strings e formatação", "Exercícios de revisão", "Mini-projeto: agenda de contatos"]),
            ("Arquivos, erros e módulos", ["Leitura de arquivos", "Escrita e JSON", "Exceções", "Módulos e pacotes", "Ambientes virtuais e pip", "Exercícios de revisão", "Mini-projeto: leitor de logs"]),
            ("Projeto e boas práticas", ["Classes e objetos", "Herança e composição", "Testes com unittest", "Depuração e logging", "Estilo e PEP 8", "Ensaio do projeto final", "Projeto final: automação de rotina"]),
        ],
    },
    "sql": {
        "nome": "SQL",
        "semanas": [
            ("Consultas básicas", ["Modelo relacional e tabelas", "SELECT e WHERE", "ORDER BY e LIMIT", "Funções de agregação", "GROUP BY e HAVING", "Exercícios de revisão", "Mini-projeto: relatório de vendas"]),
            ("Junções", ["INNER JOIN", "LEFT e RIGHT JOIN", "Várias junções", "Subconsultas", "UNION e conjuntos", "Exercícios de revisão", "Mini-projeto: cruzar cadastros"]),
            ("Modificar dados", ["INSERT", "UPDATE e DELETE com cuidado", "Transações", "Restrições e chaves", "Índices", "Exercícios de revisão", "Mini-projeto: cadastro com regras"]),
            ("Análise e projeto", ["CTEs", "Funções de janela", "Datas e textos", "Planos de execução", "Boas práticas e segurança", "Ensaio do projeto final", "Projeto final: análise de um conjunto de dados"]),
        ],
    },
}
EXTRA = ("Revisão geral dos pontos fracos", "Projeto próprio (sem tópico novo no currículo-base)")


def topicos():
    return sorted(CURRICULOS)


def _divisao(minutos):
    estudo = max(5, int(round(minutos * 0.6 / 5.0)) * 5)
    estudo = min(estudo, minutos - 5) if minutos > 5 else minutos
    return estudo, minutos - estudo


def gerar_plano_estudo(topico, semanas, minutos_dia):
    """Plano determinístico: mesma entrada, mesmo texto. Domingo é mais leve (metade do tempo), então nenhum dia passa do limite.
    Devolve {titulo, texto, semanas, dias, minutos_dia, total_minutos, fonte, tamanho}."""
    if topico not in CURRICULOS:
        raise ValueError(f"sem currículo-base para «{topico}»")
    if not 1 <= semanas <= MAX_SEMANAS:
        raise ValueError(f"semanas fora de 1–{MAX_SEMANAS}")
    if not MIN_MINUTOS <= minutos_dia <= MAX_MINUTOS:
        raise ValueError(f"minutos por dia fora de {MIN_MINUTOS}–{MAX_MINUTOS}")
    cur = CURRICULOS[topico]
    titulo = f"PLANO DE ESTUDO — {cur['nome']} — {semanas} semana{'s' if semanas > 1 else ''} — limite {minutos_dia} min/dia"
    linhas, dias, total = [titulo], [], 0
    for s in range(1, semanas + 1):
        if s <= len(cur["semanas"]):
            nome_sem, itens = cur["semanas"][s - 1]
        else:
            nome_sem, itens = "Consolidação", [EXTRA[0]] * 6 + [EXTRA[1]]
        linhas.append(f"Semana {s} — {nome_sem}")
        for d in range(7):
            m = minutos_dia if d < 6 else max(MIN_MINUTOS // 3, (minutos_dia // 2) // 5 * 5)
            est, pra = _divisao(m)
            dias.append({"semana": s, "dia": DIAS[d], "tema": itens[d], "estudo": est, "pratica": pra, "minutos": est + pra})
            total += est + pra
            linhas.append(f"S{s} {DIAS[d]}: {itens[d]} ({est}+{pra}={est + pra}min)")
    texto = "\n".join(linhas)
    return {"titulo": titulo, "texto": texto, "semanas": semanas, "dias": dias, "minutos_dia": minutos_dia, "total_minutos": total, "fonte": FONTE, "tamanho": len(texto)}


_LINHA = re.compile(r"S(\d{1,2}) (Seg|Ter|Qua|Qui|Sex|Sáb|Dom): (.+?) \((\d{1,3})\+(\d{1,3})=(\d{1,3})min\)")
_SEMANA = re.compile(r"Semana (\d{1,2}) — ")


def analisar_texto(texto):
    """Lê de volta um plano no formato acima (inclusive se o armazenamento trocou quebras de linha por espaços). Serve à verificação independente."""
    t = " ".join(str(texto).split())
    dias = [{"semana": int(m[0]), "dia": m[1], "tema": m[2], "estudo": int(m[3]), "pratica": int(m[4]), "minutos": int(m[5])} for m in _LINHA.findall(t)]
    semanas = sorted({int(x) for x in _SEMANA.findall(t)})
    return {"dias": dias, "semanas_com_cabecalho": semanas, "tamanho": len(t)}


def faixa_de_tamanho(n):
    """Faixa grosseira do tamanho do texto: a ÚNICA condição de tamanho que as experiências usam (nada de limite «aprendido» escondido no código)."""
    return "ate_500" if n <= 500 else "ate_1000" if n <= 1000 else "ate_2000" if n <= 2000 else "acima_2000"


# ---------------------------------------------------------------------- texto em partes (estratégia «anotar_em_partes»)
PARTE_MAX = 900            # caracteres de CONTEÚDO por nota; com a marca «[parte i/n] » fica abaixo de 1000, o padrão que o corretor aplica a argumentos de texto
_MARCA_PARTE = re.compile(r"^\[parte (\d{1,3})/(\d{1,3})\] ")


def dividir_em_partes(texto, maximo=PARTE_MAX):
    """Divide o texto em partes de até `maximo` caracteres, sempre entre linhas (ou entre palavras, se uma linha sozinha passa do limite). Nada se perde: juntar as partes
    com um espaço e normalizar os espaços devolve o texto original normalizado."""
    linhas = str(texto).split("\n")
    partes, atual = [], ""
    for ln in linhas:
        ln = ln.strip()
        if not ln:
            continue
        while len(ln) > maximo:                                  # linha gigante: corta na última palavra que cabe
            corte = ln.rfind(" ", 0, maximo + 1)
            corte = corte if corte > 0 else maximo
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(ln[:corte].strip())
            ln = ln[corte:].strip()
        if not atual:
            atual = ln
        elif len(atual) + 1 + len(ln) <= maximo:
            atual += "\n" + ln
        else:
            partes.append(atual)
            atual = ln
    if atual:
        partes.append(atual)
    return partes


def marcar_parte(i, n, conteudo):
    return f"[parte {i}/{n}] {conteudo}"


def tirar_marca(texto):
    """(i, n, conteudo) se o texto começa com a marca de parte; senão (None, None, texto)."""
    m = _MARCA_PARTE.match(texto or "")
    return (int(m.group(1)), int(m.group(2)), texto[m.end():]) if m else (None, None, texto)
