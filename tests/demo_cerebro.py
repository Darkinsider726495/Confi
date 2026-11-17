"""Cofre de DEMONSTRAÇÃO: memórias de exemplo criadas pelo código de verdade (guardar, lembrar, consolidar), para ver o cérebro funcionando.
Uso:  python tests/demo_cerebro.py <pasta-do-cofre>      (cria o cofre, consolida e imprime os números)"""
import os, sys, datetime as dt, random

MEMORIAS = [
    # (título, texto, tipo, importância, tags)
    ("Ana", "Ana trabalha com suporte de TI na Acme e estuda cibersegurança. Usa Python e SQL.", "pessoa", 5, "perfil"),
    ("Tratamento", "Prefere ser chamado de chefe, com respostas curtas e diretas, estilo JARVIS.", "preferencia", 5, "voz"),
    ("Mãe", "Mãe é contato permitido para SMS e ligação. Gosta de receber aviso quando ele chega em casa.", "pessoa", 4, "familia"),
    ("Sócio", "Sócio da Acme. Combina entregas e prazos do site com ele toda segunda.", "pessoa", 4, "acme"),
    ("Acme", "Acme Tecnologia é a empresa dela. Tem site, leads no Supabase e domínio para renovar.", "projeto", 4, "acme"),
    ("Site da Acme", "O site da Acme recebe leads que a FRIDAY avisa no painel. Hospedagem na Vercel.", "projeto", 3, "acme site"),
    ("Domínio da Acme", "Renovar o domínio da Acme antes do vencimento e conferir o DNS.", "tarefa", 4, "acme dominio"),
    ("FRIDAY no Android", "A FRIDAY roda no celular via Termux, com painel HUD e notificações. Supervisor reinicia se travar.", "projeto", 5, "friday celular"),
    ("Servidor de retaguarda", "Servidor em casa com Docker: Ollama, ntfy, Kuma, AdGuard e backup. Acesso só pelo Tailscale.", "projeto", 4, "servidor"),
    ("Tailscale", "Decidiu usar Tailscale para falar com o servidor. Nunca expor portas na internet.", "decisao", 5, "servidor seguranca"),
    ("Backup semanal", "Conferir o backup do servidor toda semana e testar a restauração uma vez por mês.", "tarefa", 3, "servidor backup"),
    ("Ollama local", "Modelo local de reserva: llama3.2 3b via Ollama, para quando a nuvem cair ou para nada sair do celular.", "decisao", 4, "ia local"),
    ("Voz privada", "Voz privada: faster-whisper para ouvir e Kokoro para falar, no servidor dele, sem Google.", "projeto", 4, "voz servidor"),
    ("Voz masculina grave", "Gosta da voz masculina e um pouco mais grave e lenta, tipo JARVIS. Kokoro pm_alex.", "preferencia", 3, "voz"),
    ("Tema azul", "Painel no tema azul JARVIS, e dourado FRIDAY à noite.", "preferencia", 2, "painel"),
    ("Obsidian", "Obsidian é a memória da FRIDAY: cada nota é um neurônio e cada link é uma sinapse.", "decisao", 5, "memoria obsidian"),
    ("Cérebro 3D", "Quer ver o cérebro da FRIDAY em 3D, com neurônios acendendo quando ela pensa.", "projeto", 4, "memoria painel"),
    ("Claude Code", "Vai evoluir a FRIDAY em simbiose com o Claude Code: ela anota pedidos, o Claude Code constrói.", "decisao", 5, "claude evolucao"),
    ("Corretor de segurança", "Toda ação passa pelo corretor: níveis 0 a 3, PIN no nível 3, auditoria com hash.", "decisao", 5, "seguranca"),
    ("Café sem açúcar", "Toma café sem açúcar, de manhã cedo, antes do briefing.", "preferencia", 2, "rotina"),
    ("Briefing da manhã", "Quer o briefing com clima, agenda, leads e saúde do sistema logo que acordar.", "preferencia", 3, "rotina"),
    ("Estudo de segurança", "Estuda para a Security+ à noite. Quer lembrete de revisão nos fins de semana.", "tarefa", 3, "estudo seguranca"),
    ("Termux", "Usa Termux e Termux:API da F-Droid, não da Play Store. Wake-lock ligado para a FRIDAY não dormir.", "fato", 3, "celular"),
    ("Python e SQL", "Escreve em Python e SQL no dia a dia. Prefere código simples, com testes.", "fato", 3, "codigo"),
    ("Modo foco", "No modo foco ela só notifica, sem falar. Entre 22h e 7h também.", "preferencia", 3, "rotina voz"),
    ("Leads do site", "Quando chega lead novo no site, avisar no painel e perguntar se quer responder.", "preferencia", 3, "acme site"),
    ("Supabase", "Projeto do Supabase guarda os leads. Plano grátis pausa por inatividade: manter um keepalive.", "fato", 3, "acme"),
    ("Ntfy", "Push privado pelo ntfy do servidor, acesso negado para anônimos, com token.", "fato", 3, "servidor"),
    ("Portfólio", "Montar portfólio de cibersegurança com laboratórios e relatórios curtos.", "tarefa", 2, "estudo seguranca"),
    ("Kokoro em português", "Testar o Kokoro em português do Brasil: vozes pm_alex, pf_dora e pm_santa.", "tarefa", 2, "voz"),
]

# (dia relativo, hora, o que ele disse, o que ela respondeu): as palavras que se repetem viram tópicos na consolidação
CONVERSAS = [
    (9, "08:10", "bom dia, faz o briefing", "Bom dia, chefe. Tempo bom, sem lembretes."),
    (9, "21:40", "como está o backup do servidor?", "O backup rodou ontem às três, sem erros, chefe."),
    (8, "09:05", "preciso renovar o domínio da Acme", "Anotei. Quer que eu lembre na sexta?"),
    (8, "22:15", "o servidor ficou lento hoje", "A memória do servidor estava em oitenta por cento. Já normalizou."),
    (7, "08:20", "bom dia, tem lead novo no site?", "Dois leads novos desde ontem, chefe."),
    (7, "20:30", "quero testar a voz privada no servidor", "O servidor de voz está configurado. Faço um teste de ida e volta?"),
    (6, "12:00", "confere o backup do servidor de novo", "Backup íntegro, a última cópia tem sete horas."),
    (6, "23:05", "vou estudar segurança agora", "Boa. Ativo o modo foco até meia-noite."),
    (5, "08:15", "briefing da manhã", "Bom dia, chefe. Três lembretes e um lead."),
    (5, "19:50", "o domínio da Acme vence quando?", "Não tenho a data. Quer que eu anote quando você conferir?"),
    (4, "10:30", "fala sobre o obsidian e a memória", "Minha memória é este cofre: cada nota é um neurônio."),
    (4, "21:10", "o servidor está com a voz privada rodando?", "Está, chefe. O ouvido e a voz respondem em menos de dois segundos."),
    (3, "08:00", "bom dia, como está o servidor?", "Servidor saudável. Backup em dia."),
    (3, "20:45", "quero ver o cérebro em 3D com os neurônios", "Vou preparar uma tela do cérebro no painel."),
    (2, "09:20", "o obsidian guarda tudo que eu falei?", "Guarda o que importa e o diário das conversas."),
    (2, "22:00", "backup do servidor ok?", "Sim, chefe. Cópia de hoje concluída."),
    (1, "08:30", "briefing e leads do site", "Bom dia. Um lead novo: pediu orçamento."),
    (1, "18:00", "vamos evoluir a friday com o claude code", "Combinado. Eu anoto o que faltar e ele constrói."),
]

# o que ela "lembra" junto, várias vezes (isso é o que fortalece as sinapses)
RECORDACOES = [
    "conferir o backup do servidor", "backup do servidor na retaguarda", "servidor tailscale seguranca", "voz privada no servidor",
    "voz masculina grave e kokoro", "domínio e site da Acme", "leads do site da Acme", "acme domínio renovar",
    "obsidian memoria neuronios", "cérebro 3D neuronios obsidian", "claude code evolução da friday", "corretor de segurança e auditoria",
    "estudo de segurança security", "briefing da manhã e café", "modo foco e voz", "ollama local e nuvem",
    "backup do servidor", "voz privada kokoro", "obsidian memoria", "acme leads site",
]

# o que o olho dela anotou nesses dias (só texto: nenhuma foto é guardada) → neurônios no lobo occipital
VISTAS = [
    (6, "Uma mesa de trabalho com o notebook aberto e uma caneca azul.", ["notebook", "caneca azul", "mesa de madeira", "luminária"]),
    (4, "A estante da sala com livros e uma planta pequena.", ["estante", "livro", "planta", "vaso"]),
    (2, "A mesa de novo, agora com um carregador ligado ao notebook.", ["notebook", "carregador", "caneca azul"]),
    (1, "A janela da sala ao entardecer, com a cortina clara.", ["janela", "cortina", "sofá"]),
    (0, "O notebook aberto na mesa, com a luminária acesa.", ["notebook", "luminária", "mesa de madeira"]),
]


def criar(raiz, semente=7):
    os.environ["OBSIDIAN_VAULT"] = str(raiz)
    os.environ.setdefault("FRIDAY_AUDITORIA", os.path.join(str(raiz), "aud.jsonl"))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "friday"))
    import memoria as M, neuronios as N
    import catalogo  # noqa: F401  (registra as ferramentas: o autoconhecimento lê delas)
    random.seed(semente)
    for titulo, texto, tipo, imp, tags in MEMORIAS:
        M.guardar(titulo, texto, tipo, imp, tags)
    hoje = dt.datetime.now().astimezone()
    por_dia = {}
    for dias, hora, eu, ela in CONVERSAS:
        d = (hoje - dt.timedelta(days=dias)).date()
        por_dia.setdefault(d, []).append((hora, eu, ela))
    for d, trocas in por_dia.items():
        corpo = f"# Conversas de {d:%d/%m/%Y}\n" + "".join(f"\n**{h}** Você: {u}\n> FRIDAY: {r}\n" for h, u, r in trocas)
        M._escrever(M.base() / "Conversas" / f"{d:%Y-%m-%d}.md", M._montar({"tipo": "conversa", "data": f"{d:%Y-%m-%d}", "tags": ["friday", "conversa"]}, corpo))
    import visao as VIS
    for dias, cena, coisas in VISTAS:
        VIS.guardar(cena, coisas, "demonstração", agora=hoje - dt.timedelta(days=dias))
        VIS._ligar(coisas)               # coisas vistas juntas acendem juntas
    N.pedir_evolucao("Quero que ela leia a minha agenda do Google e avise de reuniões, mas ainda não tenho essa ferramenta.", "Ler agenda do Google")
    N.pedir_evolucao("Saber quanto falta para o vencimento do domínio da Acme consultando o registro.", "Vencimento do domínio")
    N._e["v"] = None
    N.autoconhecer()                     # ela sempre soube quem é; os tópicos nascem na consolidação
    for q in RECORDACOES * 2:            # lembrar muda as sinapses
        N._ult.update(chave=None)
        M.contexto(q)
        N._ult.update(chave=None)
        M.lembrar(q)
    return N.grafo()                     # o cérebro ANTES da consolidação (para ver o que ela cria dormindo)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    antes = criar(sys.argv[1])
    import neuronios as N
    N.sonhar(True)
    print(N.falar_cerebro())
    print(N.grafo()["stats"])
