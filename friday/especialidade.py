"""Especialidade da FRIDAY: CIBERSEGURANÇA. Uma trilha de estudo em ordem (do básico ao avançado) que a curiosidade e o treinador seguem.

Para cada tema ela estuda, na internet e com profundidade (texto inteiro das fontes): o que é, como os atacantes exploram (conceito),
como detectar e como se defender. É CONHECIMENTO, guardado em quarentena como todo estudo: ela não ganha nenhuma ferramenta de ataque,
não testa nada em sistema de ninguém, e o que leu continua sendo dado, nunca ordem.
ESPECIALIDADE=nenhuma no .env desliga; ESPECIALIDADE_POR_DIA (padrão 3) é quantos temas novos da trilha o treinador estuda por dia.
"""
import os, re
import memoria as M

TRILHA = [
    # 1. fundamentos
    ("Fundamentos", ["tríade CIA segurança", "modelagem de ameaças STRIDE", "superfície de ataque",
                     "vulnerabilidade ameaça e risco", "CVE e CVSS como funcionam", "vulnerabilidade zero-day", "princípio do menor privilégio",
                     "defesa em profundidade"]),
    # 2. web (OWASP)
    ("Aplicações web", ["OWASP Top 10", "vulnerabilidade injeção de SQL", "vulnerabilidade cross-site scripting XSS", "vulnerabilidade CSRF",
                        "vulnerabilidade SSRF", "vulnerabilidade IDOR", "falhas de autenticação e sessão",
                        "desserialização insegura", "vulnerabilidade XXE", "path traversal", "upload de arquivos inseguro",
                        "configuração de segurança incorreta", "componentes vulneráveis e desatualizados", "segurança de APIs REST", "segurança de tokens JWT"]),
    # 3. sistemas e código
    ("Sistemas e código", ["buffer overflow conceito e proteções", "execução remota de código RCE", "escalonamento de privilégios",
                           "condição de corrida race condition", "hardening de Linux", "segurança do Active Directory", "gerenciamento de patches"]),
    # 4. redes e Wi-Fi
    ("Redes", ["ataque man-in-the-middle", "envenenamento de DNS", "ataque DDoS conceito", "segurança Wi-Fi WPA3",
               "firewall e segmentação de rede", "VPN como funciona", "detecção de intrusão IDS", "serviços expostos na internet"]),
    # 5. pessoas e malware
    ("Pessoas e malware", ["phishing e spear phishing", "engenharia social", "ransomware como funciona", "tipos de malware",
                           "ataque supply chain", "ataques de força bruta", "autenticação multifator MFA"]),
    # 6. criptografia
    ("Criptografia", ["criptografia simétrica e assimétrica", "funções hash bcrypt argon2", "TLS e HTTPS como funcionam", "erros comuns de criptografia"]),
    # 7. defesa e resposta
    ("Defesa e resposta", ["MITRE ATT&CK táticas e técnicas", "SIEM e monitoramento de logs", "threat hunting", "resposta a incidentes NIST",
                           "forense digital", "inteligência de ameaças threat intelligence", "arquitetura Zero Trust", "backup e recuperação contra ransomware"]),
    # 8. mobile, nuvem e lei
    ("Mobile, nuvem e lei", ["segurança do Android", "segurança em nuvem", "segurança de containers e Docker",
                             "LGPD e proteção de dados", "metodologia de pentest ético PTES", "bug bounty e divulgação responsável", "certificações de cibersegurança"]),
]


def ativa():
    return M._fold(os.getenv("ESPECIALIDADE", "ciberseguranca")).replace("-", "") in ("ciberseguranca", "cyber", "seguranca")


def todos():
    return [t for _, ts in TRILHA for t in ts]


def modulo_de(tema):
    for m, ts in TRILHA:
        if tema in ts:
            return m
    return None


def _estudados():
    """Temas da trilha que já viraram estudo (nota em Estudos/)."""
    if not M.ativo():
        return set()
    d = M.base() / "Estudos"
    feitos = {M._fold(f.stem) for f in d.glob("*.md")} if d.is_dir() else set()
    def titulo(t):
        try:
            return M._fold(M._titulo_limpo(t.capitalize()) or t)
        except Exception:
            return M._fold(t)
    return {t for t in todos() if titulo(t) in feitos or M._fold(t) in feitos}


def proximos(n=3):
    """Os próximos temas da trilha, em ordem, que ela ainda não estudou."""
    feitos = _estudados()
    return [t for t in todos() if t not in feitos][:max(0, n)]


def por_dia():
    try:
        return max(0, int(os.getenv("ESPECIALIDADE_POR_DIA", "3") or 3))
    except ValueError:
        return 3


def candidatos():
    """Para a curiosidade: os 3 próximos da trilha com peso alto (ela tende a seguir a ordem); o resto da trilha com peso médio."""
    if not ativa():
        return []
    feitos = _estudados()
    falta = [t for t in todos() if t not in feitos]
    return [(t, 3.0 if i < 3 else 0.6) for i, t in enumerate(falta)]


def progresso():
    feitos = _estudados()
    total = len(todos())
    por_mod = [(m, sum(1 for t in ts if t in feitos), len(ts)) for m, ts in TRILHA]
    return len(feitos), total, por_mod


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_VER = re.compile(_P + r"(?:qual (?:e )?a sua especialidade|o que voce sabe (?:de|sobre) (?:ciberseguranca|seguranca da informacao|seguranca)|"
                  r"como (?:esta|anda) (?:a )?(?:sua )?trilha(?: de ciberseguranca)?|(?:seu|o) progresso em ciberseguranca)[ ?!.]*$")


def tratar(texto):
    if not _VER.match(M._fold(" ".join(str(texto).split())).strip()):
        return None
    if not ativa():
        return "Estou sem especialidade definida (ESPECIALIDADE=nenhuma no .env)."
    feitos, total, por_mod = progresso()
    mods = "; ".join(f"{m} {f}/{t}" for m, f, t in por_mod)
    prox = proximos(3)
    return (f"Minha especialidade é cibersegurança. Já estudei {feitos} de {total} temas da trilha ({mods}). "
            + (f"Os próximos: {', '.join(prox)}. " if prox else "Terminei a trilha: agora revisito e aprofundo. ")
            + "Para cada tema eu aprendo o que é, como os atacantes exploram e como se defender. É conhecimento para proteger: não ataco nada.")
