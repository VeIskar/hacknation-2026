"""docker-compose.yml dla testów: parser YAML i zamiana równoważnych zapisów compose na jeden.

Compose pozwala zapisać to samo na kilka sposobów (`tmpfs: /tmp` albo lista, `environment` jako
słownik albo lista `NAZWA=wartość`, wolumen skrótem albo słownikiem). Testy sprawdzają znaczenie,
nie wcięcia ani kolejność kluczy.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

_INTERPOLATION = re.compile(r"\$\{([A-Z][A-Z0-9_]*):-([^}]*)\}")


def service(name: str) -> dict[str, Any]:
    return COMPOSE["services"][name]


def as_list(value: Any) -> list[Any]:
    """Klucz z jedną wartością albo listą (`tmpfs: /tmp` i `tmpfs: [/tmp]`) jako lista."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def environment(name: str) -> dict[str, str]:
    """`environment` serwisu jako słownik tekstów, bez względu na zapis w pliku."""
    env = service(name).get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, "") for item in env)
    return {key: "" if value is None else str(value) for key, value in env.items()}


def interpolation(value: str) -> tuple[str, str] | None:
    """`${NAZWA:-domyślna}` → (NAZWA, domyślna); inna wartość → None."""
    match = _INTERPOLATION.fullmatch(value.strip())
    return (match.group(1), match.group(2)) if match else None


def tmpfs_paths(name: str) -> list[str]:
    """Ścieżki z `tmpfs` bez opcji (`/tmp:size=64m` → `/tmp`)."""
    return [entry.split(":", 1)[0] for entry in as_list(service(name).get("tmpfs"))]


def security_opts(name: str) -> set[str]:
    """`no-new-privileges` i `no-new-privileges:true` znaczą to samo."""
    opts = {str(opt).replace("=", ":") for opt in as_list(service(name).get("security_opt"))}
    return {opt.removesuffix(":true") for opt in opts}


def volume_mounts(name: str) -> dict[str, str]:
    """Wolumeny serwisu jako {cel: źródło}, ze skrótu `źródło:cel[:opcje]` albo ze słownika."""
    mounts = {}
    for volume in as_list(service(name).get("volumes")):
        if isinstance(volume, dict):
            mounts[volume["target"]] = volume.get("source", "")
        else:
            source, target, *_ = f"{volume}:".split(":")
            mounts[target] = source
    return mounts


def build_context(name: str) -> str:
    build = service(name).get("build")
    context = build.get("context", ".") if isinstance(build, dict) else build
    return str(Path(context))
