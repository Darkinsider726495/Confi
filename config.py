"""Leitura do arquivo de configuração (TOML)."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CoreConfig:
    name: str
    label: str
    uri: str = ""                 # ex.: qemu+ssh://root@10.10.10.1/system
    migrate_uri: str = ""         # ex.: tcp://10.10.10.1 (cabo 2.5GbE direto)
    ssh: str = ""                 # ex.: root@192.168.0.11 (para manutenção e desligar)
    hostname: str = ""            # nome esperado do host; vazio = não confere
    mac: str = ""                 # para acordar o CORE reserva (Wake-on-LAN)


@dataclass
class AuditConfig:
    path: str = "dados/historico.jsonl"
    key: str = "dados/chave_ed25519.pem"
    pq: bool = True               # assinatura pós-quântica (ML-DSA) se a liboqs existir
    ots: bool = False             # ancorar no Bitcoin com OpenTimestamps (comando `ots`)


@dataclass
class ControllerConfig:
    kind: str = "sim"             # "sim" ou "serial"
    port: str = "/dev/ttyACM0"
    baud: int = 115200


@dataclass
class Config:
    mode: str = "sim"             # "sim" ou "real"
    vm: str = "sessao-viva"
    storage: str = "shared"       # "shared" (NFS/DRBD) ou "copy" (copia o disco na migração)
    painel_host: str = "0.0.0.0"
    painel_port: int = 8080
    shutdown_after_eject: bool = False
    heat_limit_c: float = 85.0
    health_interval_s: float = 2.0
    wake_timeout_s: float = 180.0
    maintain_command: str = "apt-get update && apt-get -y upgrade"
    sim_speed: float = 1.0        # 1.0 = tempos realistas; menor = mais rápido (testes)
    audit: AuditConfig = field(default_factory=AuditConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    cores: dict[str, CoreConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("A", "B"):
            self.cores.setdefault(name, CoreConfig(name=name, label=f"CORE {name}"))


# ------------------------------------------------------- caminhos de dados

def _writable_dir(directory: Path) -> bool:
    """True se a pasta existe e é gravável, ou se pode ser criada."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(directory, os.W_OK)


def _resolve_data_path(value: str, base: Path, fallback_dir: Path) -> str:
    """Resolve um caminho de dados do histórico.

    Ordem de tentativa (usa a primeira pasta gravável):
      1. O caminho configurado. Se for relativo, é relativo à pasta do
         arquivo de configuração, não à pasta de onde o comando foi chamado.
      2. A pasta `dados/` ao lado da configuração.
      3. ~/.local/share/nr-continuum/dados (sempre do usuário atual).
    Assim um caminho como /dados nunca derruba a inicialização.
    """
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = base / p
    candidates = [
        p.parent,
        fallback_dir,
        Path.home() / ".local" / "share" / "nr-continuum" / "dados",
    ]
    for i, directory in enumerate(candidates):
        if _writable_dir(directory):
            final = directory / p.name
            if i > 0:
                print(f"[aviso] Sem permissão para gravar em {p.parent}. "
                      f"Usando {final} no lugar.", file=sys.stderr)
            return str(final)
    raise PermissionError(
        f"Nenhuma pasta gravável para {p.name}. Tentei: "
        + ", ".join(str(c) for c in candidates)
    )


def _fix_audit_paths(audit: AuditConfig, base: Path) -> None:
    fallback = base / "dados"
    audit.path = _resolve_data_path(audit.path, base, fallback)
    audit.key = _resolve_data_path(audit.key, base, fallback)


# ---------------------------------------------------------------- carregar

def load(path: str | Path | None) -> Config:
    """Carrega a configuração. Sem arquivo, devolve o modo simulação."""
    if path is None:
        cfg = Config()
        _fix_audit_paths(cfg.audit, Path.cwd())
        return cfg
    cfg_file = Path(path).expanduser().resolve()
    raw = tomllib.loads(cfg_file.read_text(encoding="utf-8"))
    cores = {
        name: CoreConfig(name=name, label=c.get("label", f"CORE {name}"),
                         uri=c.get("uri", ""), migrate_uri=c.get("migrate_uri", ""),
                         ssh=c.get("ssh", ""), hostname=c.get("hostname", ""),
                         mac=c.get("mac", ""))
        for name, c in raw.pop("cores", {}).items()
    }
    audit = AuditConfig(**raw.pop("audit", {}))
    _fix_audit_paths(audit, cfg_file.parent)
    controller = ControllerConfig(**raw.pop("controller", {}))
    cfg = Config(**raw, audit=audit, controller=controller, cores=cores)
    if set(cfg.cores) != {"A", "B"}:
        raise ValueError("A configuração precisa de exatamente dois COREs: [cores.A] e [cores.B].")
    if cfg.mode == "real":
        for c in cfg.cores.values():
            if not c.uri:
                raise ValueError(f"No modo real, [cores.{c.name}] precisa de 'uri'.")
    return cfg
