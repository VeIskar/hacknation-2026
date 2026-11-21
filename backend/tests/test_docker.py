"""M1.3: obraz `api` zgodny z Treść pkt 5, sprawdzony statycznie (bramka nie buduje obrazów).

Budowę i uruchomienie sprawdza się ręcznie: `docker compose build api`, `whoami` → `app`
(PROGRESS.api.md, M1.3). Ten test pilnuje, żeby nikt po cichu nie cofnął tych ustaleń.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")


def _instructions(name: str) -> list[str]:
    """Argumenty instrukcji Dockerfile (bez komentarzy, z połączonymi liniami `\\`)."""
    text = re.sub(r"\\\n", " ", DOCKERFILE)
    lines = [line.strip() for line in text.splitlines() if not line.lstrip().startswith("#")]
    return [line.split(None, 1)[1] for line in lines if line.upper().startswith(name + " ")]


def _compose_api_block() -> list[str]:
    """Linie serwisu `api` z docker-compose.yml (bez parsera YAML, który nie jest zależnością)."""
    lines = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    start = lines.index("  api:")
    block = []
    for line in lines[start + 1 :]:
        if re.match(r"^  \S", line):  # następny serwis
            break
        block.append(line)
    return block


def test_base_image_is_python_314_with_explicit_patch_version() -> None:
    (image,) = _instructions("FROM")
    assert re.fullmatch(r"(docker\.io/library/)?python:3\.14\.\d+-slim(-\w+)?", image), image


def test_runs_as_numeric_non_root_user() -> None:
    users = _instructions("USER")
    assert users, "brak USER: kontener działałby jako root"
    uid, _, gid = users[-1].partition(":")
    assert uid.isdigit() and int(uid) > 0, users[-1]
    assert gid == "" or (gid.isdigit() and int(gid) > 0), users[-1]
    assert f"--uid {uid}" in DOCKERFILE, "USER ma wskazywać użytkownika `app` z useradd"
    assert "useradd" in DOCKERFILE and " app" in DOCKERFILE


def test_user_switch_comes_after_install_and_before_cmd() -> None:
    order = [line.split()[0].upper() for line in DOCKERFILE.splitlines() if line[:1].isalpha()]
    last_user = len(order) - 1 - order[::-1].index("USER")
    assert "RUN" not in order[last_user:], "RUN po USER: instalacja jako app albo powrót do roota"
    assert order[-1] == "CMD"


def test_exposes_only_port_8000() -> None:
    assert _instructions("EXPOSE") == ["8000"]
    (cmd,) = _instructions("CMD")
    assert '"--port", "8000"' in cmd


def test_ocr_with_polish_data_is_installed() -> None:
    (apt,) = [run for run in _instructions("RUN") if "apt-get install" in run]
    assert "tesseract-ocr " in apt and "tesseract-ocr-pol" in apt
    assert "--no-install-recommends" in apt
    assert "rm -rf /var/lib/apt/lists/*" in apt


def test_compose_api_has_no_persistent_writes_and_no_privileges() -> None:
    block = "\n".join(_compose_api_block())
    assert re.search(r"^    read_only: true$", block, flags=re.MULTILINE)
    assert re.search(r"^    tmpfs:\n      - /tmp$", block, flags=re.MULTILINE)
    assert re.search(r"^    cap_drop:\n      - ALL$", block, flags=re.MULTILINE)
    assert "no-new-privileges:true" in block
    assert not re.search(r"^    (volumes|privileged|user):", block, flags=re.MULTILINE)
