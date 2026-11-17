"""Estado pequeno em JSON dentro do cofre (.cerebro/<nome>.json), para os módulos que precisam lembrar entre reinícios (curiosidade, conversa).
Sempre validado ao ler (arquivo adulterado ou corrompido vira o padrão), escrito de forma atômica; com a memória desligada vive só no processo."""
import copy, json, threading
import memoria as M


class Arq:
    def __init__(self, nome, padrao, limpar):
        """`padrao` é o estado novo; `limpar(lido, padrao)` devolve o dicionário validado a partir do que veio do arquivo."""
        self.nome, self.padrao, self.limpar = nome, padrao, limpar
        self.trava = threading.RLock()
        self._v, self._raiz = None, None

    def _caminho(self):
        return M.base() / ".cerebro" / f"{self.nome}.json"

    def get(self):
        with self.trava:
            raiz = str(M.base()) if M.ativo() else ""
            if self._v is None or self._raiz != raiz:
                v = copy.deepcopy(self.padrao)
                if raiz:
                    try:
                        lido = json.loads(self._caminho().read_text(encoding="utf-8"))
                        if isinstance(lido, dict):
                            v = self.limpar(lido, copy.deepcopy(self.padrao))
                    except (OSError, ValueError):
                        pass
                self._v, self._raiz = v, raiz
            return self._v

    def salvar(self):
        with self.trava:
            if not M.ativo():
                return
            try:
                M._escrever(self._caminho(), json.dumps(self.get(), ensure_ascii=False))
            except OSError:
                pass

    def reiniciar(self):
        """Descarta o que está em memória (o próximo get() relê o arquivo). Usado em testes e ao trocar de cofre."""
        with self.trava:
            self._v, self._raiz = None, None
