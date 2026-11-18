#!/usr/bin/env python3
"""Sincroniza o cofre da FRIDAY (no celular) com uma pasta no PC, direto pelo Wi-Fi. Só biblioteca padrão (Windows, Linux, Kali).

    1ª vez:   python sincronizar_pc.py --friday http://IP-DO-CELULAR:8090 --chave CHAVE --pasta "Cofre FRIDAY"
    depois:   python sincronizar_pc.py --pasta "Cofre FRIDAY"            (uma rodada)
              python sincronizar_pc.py --pasta "Cofre FRIDAY" --sempre   (a cada minuto, até você fechar)

Abra a pasta no Obsidian do PC («Abrir pasta como cofre»). Regras:
  - mudou só de um lado → copia para o outro;
  - mudou dos dois lados → as DUAS versões ficam (uma com «(conflito …)» no nome);
  - saiu de um lado → do outro lado vai para um arquivo morto (nada é apagado): no celular, FRIDAY/Arquivo/sincronia/;
    no PC, a pasta .sincronia-arquivo/ dentro do cofre.
A chave fica em <pasta>/.sync-friday.json (só para você). Pasta Privado/ não vem, a menos que você ligue SYNC_PRIVADO=1 na FRIDAY.
"""
import argparse, hashlib, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path, PurePosixPath

CONF = ".sync-friday.json"
ARQUIVO_PC = ".sincronia-arquivo"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def seguro(rel):
    p = PurePosixPath(rel)
    return bool(p.parts) and not p.is_absolute() and ".." not in p.parts and "\\" not in rel and not any(c < " " for c in rel)


class Friday:
    def __init__(self, url, chave):
        self.url, self.chave = url.rstrip("/"), chave

    def _req(self, metodo, caminho, q=None, dados=None):
        u = self.url + caminho + ("?" + urllib.parse.urlencode(q) if q else "")
        r = urllib.request.Request(u, data=dados, method=metodo, headers={"X-Sync-Chave": self.chave})
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.read()

    def lista(self):
        return json.loads(self._req("GET", "/sync/lista"))["arquivos"]

    def baixar(self, rel):
        return self._req("GET", "/sync/arquivo", {"rel": rel})

    def enviar(self, rel, dados, base, mtime):
        return json.loads(self._req("POST", "/sync/arquivo", {"rel": rel, "base": base or "", "mtime": mtime}, dados))

    def arquivar(self, rel):
        return json.loads(self._req("POST", "/sync/arquivar", {"rel": rel}, b""))


def locais(pasta):
    out = {}
    for f in pasta.rglob("*"):
        if not f.is_file() or f.is_symlink():
            continue
        rel = f.relative_to(pasta).as_posix()
        if rel == CONF or rel.startswith(ARQUIVO_PC + "/") or rel.endswith((".tmp", ".sync-tmp")) or PurePosixPath(rel).parts[0] == "Privado":
            continue
        if rel.startswith(".obsidian/workspace"):
            continue
        out[rel] = sha(f)
    return out


def gravar(pasta, rel, dados, mtime=None):
    alvo = pasta.joinpath(*PurePosixPath(rel).parts)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_name(alvo.name + ".sync-tmp")
    tmp.write_bytes(dados)
    os.replace(tmp, alvo)
    if mtime:
        os.utime(alvo, (float(mtime), float(mtime)))


def arquivar_local(pasta, rel):
    alvo = pasta.joinpath(*PurePosixPath(rel).parts)
    destino = pasta / ARQUIVO_PC / rel.replace("/", " - ")
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino = destino.with_name(f"{destino.stem} ({int(time.time())}){destino.suffix}")
    os.replace(alvo, destino)


def rodada(fr, pasta, estado):
    """Uma sincronização completa. `estado` = {rel: sha} da última vez em que os dois lados ficaram iguais. Devolve o resumo."""
    remoto = {r: v for r, v in fr.lista().items() if seguro(r)}
    local = locais(pasta)
    feito = {"baixados": 0, "enviados": 0, "conflitos": 0, "arquivados": 0}
    for rel in sorted(set(remoto) | set(local)):
        r = remoto.get(rel, [None, None, None])[2] if rel in remoto else None
        l, b = local.get(rel), estado.get(rel)
        if r == l:
            if r:
                estado[rel] = r
            continue
        if l is None:                                   # só no celular
            if b and b == r:
                fr.arquivar(rel); estado.pop(rel, None); feito["arquivados"] += 1          # você tirou do PC
            else:
                gravar(pasta, rel, fr.baixar(rel), remoto[rel][0]); estado[rel] = r; feito["baixados"] += 1
            continue
        if r is None:                                   # só no PC
            if b and b == l:
                arquivar_local(pasta, rel); estado.pop(rel, None); feito["arquivados"] += 1   # ela arquivou no celular
            else:
                caminho = pasta.joinpath(*PurePosixPath(rel).parts)
                fr.enviar(rel, caminho.read_bytes(), None, caminho.stat().st_mtime); estado[rel] = l; feito["enviados"] += 1
            continue
        caminho = pasta.joinpath(*PurePosixPath(rel).parts)
        if b == l:                                      # só o celular mudou
            gravar(pasta, rel, fr.baixar(rel), remoto[rel][0]); estado[rel] = r; feito["baixados"] += 1
        elif b == r:                                    # só o PC mudou
            fr.enviar(rel, caminho.read_bytes(), r, caminho.stat().st_mtime); estado[rel] = l; feito["enviados"] += 1
        else:                                           # os dois mudaram: guarda as duas versões
            minha = caminho.with_name(f"{caminho.stem} (conflito PC {time.strftime('%Y-%m-%d %H%M')}){caminho.suffix}")
            os.replace(caminho, minha)
            gravar(pasta, rel, fr.baixar(rel), remoto[rel][0]); estado[rel] = r
            rel_minha = minha.relative_to(pasta).as_posix()
            fr.enviar(rel_minha, minha.read_bytes(), None, minha.stat().st_mtime); estado[rel_minha] = sha(minha)
            feito["conflitos"] += 1
    return feito


def main():
    ap = argparse.ArgumentParser(description="Sincroniza o cofre da FRIDAY com o PC pelo Wi-Fi.")
    ap.add_argument("--pasta", required=True)
    ap.add_argument("--friday")
    ap.add_argument("--chave")
    ap.add_argument("--sempre", action="store_true")
    a = ap.parse_args()
    pasta = Path(a.pasta).expanduser().resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / CONF
    conf = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"estado": {}}
    if a.friday:
        conf["url"] = a.friday
    if a.chave:
        conf["chave"] = a.chave
    if not conf.get("url") or not conf.get("chave"):
        print("Na 1ª vez, passe --friday e --chave (rode «python scripts/parear_pc.py» no Termux para ver os dois).")
        return 2
    fr = Friday(conf["url"], conf["chave"])
    while True:
        try:
            r = rodada(fr, pasta, conf.setdefault("estado", {}))
            tmp = arq.with_suffix(".tmp")
            tmp.write_text(json.dumps(conf), encoding="utf-8")
            os.replace(tmp, arq)
            try:
                os.chmod(arq, 0o600)
            except OSError:
                pass
            print(time.strftime("%H:%M:%S"), "· sincronizado:", ", ".join(f"{v} {k}" for k, v in r.items()), flush=True)
        except urllib.error.HTTPError as e:
            print({401: "Chave errada.", 403: "A FRIDAY recusou: a sincronização está desligada ou você não está na mesma rede.",
                   429: "Muitas tentativas erradas: espere 1 minuto."}.get(e.code, f"Erro {e.code}."), flush=True)
            if e.code == 401:
                return 1
        except (urllib.error.URLError, OSError) as e:
            print("Não alcancei o celular (mesmo Wi-Fi? FRIDAY ligada?):", getattr(e, "reason", e), flush=True)
        if not a.sempre:
            return 0
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
