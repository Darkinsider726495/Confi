"""Exploração controlada: antes de experimentar, avaliar benefício, custo, impacto, reversibilidade, risco e necessidade de autorização.

Módulo puro (sem importar o resto da FRIDAY): os mesmos números servem ao hub, à hipótese, ao planejador e à aprendizagem. Os perfis abaixo são ESCOLHAS DE PROJETO escritas
à mão a partir do que cada ferramenta faz no código (não são aprendidos, não se ajustam sozinhos e não valem como probabilidade). Servem para duas coisas:
  1. DESEMPATAR estratégias sem evidência: dentre as que ninguém testou, tenta-se primeiro a de menor impacto (a menos invasiva).
  2. DECIDIR o que uma exploração pode fazer: dentro do escopo do pedido do dono executa; o que não está no escopo vira simulação ou pedido de autorização; o que sai do
     aparelho ou não se desfaz nunca é automático.
Explorar NÃO é liberdade: internet, comandos, arquivos fora do pedido, instalação, compra e mensagens exigem autorização, e uma ferramenta sem perfil aqui é recusada.
"""

REVERSIBILIDADE = ("reversivel", "parcial", "irreversivel")
PERFIS = {
    "anotar": {"custo": 0.1, "impacto": 0.2, "reversibilidade": "parcial", "externo": False, "escopo": "banco local de notas",
               "descricao": "acrescenta uma linha ao banco de notas; o sistema não apaga notas, mas ela só aparece na lista de notas e pode ser ignorada"},
    "criar_arquivo": {"custo": 0.2, "impacto": 0.4, "reversibilidade": "parcial", "externo": False, "escopo": "pasta de documentos da FRIDAY",
                      "descricao": "cria um arquivo novo (nunca sobrescreve); o sistema não apaga arquivos, o dono pode"},
    "guardar_memoria": {"custo": 0.2, "impacto": 0.6, "reversibilidade": "parcial", "externo": False, "escopo": "memória de longo prazo (cofre)",
                        "descricao": "entra na memória de longo prazo e passa a influenciar o que ela lembra; pode ser arquivada, não apagada"},
    "criar_lembrete": {"custo": 0.2, "impacto": 0.3, "reversibilidade": "parcial", "externo": False, "escopo": "lembretes locais",
                       "descricao": "cria um aviso falado numa hora marcada"},
    "enviar_sms": {"custo": 0.3, "impacto": 0.9, "reversibilidade": "irreversivel", "externo": True, "escopo": "outra pessoa", "descricao": "envia um SMS; uma mensagem enviada não volta"},
    "ligar": {"custo": 0.3, "impacto": 0.9, "reversibilidade": "irreversivel", "externo": True, "escopo": "outra pessoa", "descricao": "faz uma ligação"},
    "preparar_whatsapp": {"custo": 0.2, "impacto": 0.6, "reversibilidade": "parcial", "externo": True, "escopo": "outra pessoa", "descricao": "abre o WhatsApp com a mensagem pronta"},
}
TESTE_ISOLADO = "simular"


def perfil_de(ferramenta):
    return PERFIS.get(ferramenta)


def beneficio_informacional(n_observacoes):
    """Quanto uma nova tentativa ensinaria: 1 sem nenhuma observação, caindo com cada uma (1/(n+1)). É uma regra de projeto, não uma medida."""
    return round(1.0 / (int(n_observacoes) + 1), 2)


def risco_de(perfil):
    if perfil["externo"] or perfil["reversibilidade"] == "irreversivel" or perfil["impacto"] >= 0.7:
        return "alto"
    return "medio" if perfil["impacto"] >= 0.4 else "baixo"


def avaliar(opcao, *, n_observacoes=0, no_escopo_do_pedido=True, experimento=False, simulacao_possivel=False):
    """Avalia UMA opção ({id, ferramentas}) e diz o que é permitido fazer com ela. `experimento` = não faz parte do que o dono pediu (só serve para aprender)."""
    perfis = [PERFIS.get(f) for f in opcao.get("ferramentas") or []]
    base = {"opcao": opcao.get("id"), "calibrada": False, "regra": "perfis escritos à mão no código; valores de 0 a 1 são ordem de grandeza, não probabilidade"}
    if not perfis or any(p is None for p in perfis):
        return {**base, "modo": "recusar", "exige_autorizacao": True, "risco": "desconhecido", "motivo": "ferramenta sem perfil de impacto: não sei avaliar, então não exploro",
                "beneficio_informacional": beneficio_informacional(n_observacoes), "custo": None, "impacto": None, "reversibilidade": None, "criterios_de_parada": []}
    impacto = max(p["impacto"] for p in perfis)
    custo = round(sum(p["custo"] for p in perfis), 2)
    rev = max((p["reversibilidade"] for p in perfis), key=REVERSIBILIDADE.index)
    externo = any(p["externo"] for p in perfis)
    risco = max((risco_de(p) for p in perfis), key=("baixo", "medio", "alto").index)
    motivos = []
    if externo:
        motivos.append("a ação alcança outra pessoa ou serviço fora do aparelho")
    if rev == "irreversivel":
        motivos.append("o efeito não pode ser desfeito")
    if experimento:
        motivos.append("é um teste que o dono não pediu")
    exige = bool(externo or rev == "irreversivel" or (experimento and not simulacao_possivel))
    if externo or rev == "irreversivel":
        modo = "pedir_autorizacao"
    elif experimento:
        modo = TESTE_ISOLADO if simulacao_possivel else "pedir_autorizacao"
    else:
        modo = "executar_no_escopo" if no_escopo_do_pedido else "pedir_autorizacao"
        if not no_escopo_do_pedido:
            exige = True
            motivos.append("fora do escopo do que o dono pediu")
    parada = ["se a leitura independente mostrar que o efeito não ocorreu por inteiro, parar e replanejar com a evidência",
              "não repetir a mesma estratégia nas mesmas condições", "respeitar os limites de tentativas, tempo e recursos do objetivo"]
    if experimento:
        parada.append("encerrar o teste ao primeiro resultado inesperado ou ao atingir o limite de tentativas do teste")
    return {**base, "modo": modo, "exige_autorizacao": exige, "motivo_autorizacao": motivos, "risco": risco, "beneficio_informacional": beneficio_informacional(n_observacoes),
            "custo": custo, "impacto": impacto, "reversibilidade": rev, "escopo": [p["escopo"] for p in perfis], "criterios_de_parada": parada,
            "motivo": ("dentro do que o dono pediu; baixo impacto" if modo == "executar_no_escopo" else "; ".join(motivos) or "precisa de autorização")}
