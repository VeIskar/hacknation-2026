"""M1.3: obraz `api` zgodny z Treść pkt 5, sprawdzony statycznie (bramka nie buduje obrazów).

Budowę i uruchomienie sprawdza się ręcznie: `docker compose build api`, `whoami` → `app`
(PROGRESS.api.md, M1.3). Ten test pilnuje, żeby nikt po cichu nie cofnął tych ustaleń.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _instructions(name: str) -> list[str]:
    """Argumenty instrukcji Dockerfile (bez komentarzy, z połączonymi liniami `\\`)."""
    text = re.sub(r"\\\n", " ", DOCKERFILE)
    lines = [line.strip() for line in text.splitlines() if not line.lstrip().startswith("#")]
    return [line.split(None, 1)[1] for line in lines if line.upper().startswith(name + " ")]


def _compose_block(service: str) -> str:
    """Serwis z docker-compose.yml (bez parsera YAML, który nie jest zależnością)."""
    lines = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    start = lines.index(f"  {service}:")
    block = []
    for line in lines[start + 1 :]:
        if re.match(r"^\S|^  \S", line):  # następny serwis albo sekcja
            break
        block.append(line)
    return "\n".join(block)


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
    block = _compose_block("api")
    assert re.search(r"^    read_only: true$", block, flags=re.MULTILINE)
    assert re.search(r"^    tmpfs:\n      - /tmp$", block, flags=re.MULTILINE)
    assert re.search(r"^    cap_drop:\n      - ALL$", block, flags=re.MULTILINE)
    assert "no-new-privileges:true" in block
    assert not re.search(r"^    (volumes|privileged|user):", block, flags=re.MULTILINE)


# M1.5: model w compose.
OLLAMA_DOCKERFILE = (ROOT / "ollama" / "Dockerfile").read_text(encoding="utf-8")


def test_ollama_image_is_pinned_and_runs_without_root() -> None:
    (image,) = re.findall(r"^FROM (\S+)", OLLAMA_DOCKERFILE, flags=re.MULTILINE)
    assert re.fullmatch(r"(docker\.io/)?ollama/ollama:\d+\.\d+\.\d+", image), image
    users = re.findall(r"^USER (\d+):(\d+)$", OLLAMA_DOCKERFILE, flags=re.MULTILINE)
    assert users and all(int(n) > 0 for n in users[-1]), users
    assert f"--uid {users[-1][0]}" in OLLAMA_DOCKERFILE


def test_ollama_keeps_models_in_volume_and_is_not_published() -> None:
    block = _compose_block("ollama")
    assert "    build: ./ollama" in block
    assert re.search(r"^      - ollama-models:/home/ollama/\.ollama$", block, flags=re.MULTILINE)
    assert "OLLAMA_MODELS=/home/ollama/.ollama/models" in OLLAMA_DOCKERFILE
    assert not re.search(r"^    ports:", block, flags=re.MULTILINE), "model tylko w sieci compose"
    assert re.search(r"^volumes:\n  ollama-models:", COMPOSE, flags=re.MULTILINE)


def test_ollama_context_fits_prompt_and_answer() -> None:
    """K1: prompt i odpowiedź to do ok. 4100 tokenów, a domyślny kontekst ma 4096."""
    match = re.search(r"OLLAMA_CONTEXT_LENGTH: \$\{OLLAMA_CONTEXT_LENGTH:-(\d+)\}", COMPOSE)
    assert match and int(match.group(1)) >= 16384


def test_ollama_has_no_root_privileges_or_persistent_writes_outside_volume() -> None:
    block = _compose_block("ollama")
    assert re.search(r"^    read_only: true$", block, flags=re.MULTILINE)
    assert re.search(r"^    cap_drop:\n      - ALL$", block, flags=re.MULTILINE)
    assert "no-new-privileges:true" in block


def test_ollama_cloud_is_off() -> None:
    assert 'OLLAMA_NO_CLOUD: "1"' in _compose_block("ollama")


def test_api_talks_to_ollama_service_by_default() -> None:
    assert "LLM_BASE_URL: ${LLM_BASE_URL:-http://ollama:11434/v1}" in _compose_block("api")
