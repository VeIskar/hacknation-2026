"""M1.3: obraz `api` zgodny z Treść pkt 5, sprawdzony statycznie (bramka nie buduje obrazów).

Budowę i uruchomienie sprawdza się ręcznie: `docker compose build api`, `whoami` → `app`
(PROGRESS.api.md, M1.3). Ten test pilnuje, żeby nikt po cichu nie cofnął tych ustaleń.
"""

import re

from compose import (
    COMPOSE,
    ROOT,
    as_list,
    build_context,
    environment,
    interpolation,
    security_opts,
    service,
    tmpfs_paths,
    volume_mounts,
)

DOCKERFILE = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")


def _instructions(name: str) -> list[str]:
    """Argumenty instrukcji Dockerfile (bez komentarzy, z połączonymi liniami `\\`)."""
    text = re.sub(r"\\\n", " ", DOCKERFILE)
    lines = [line.strip() for line in text.splitlines() if not line.lstrip().startswith("#")]
    return [line.split(None, 1)[1] for line in lines if line.upper().startswith(name + " ")]


def _assert_locked_down(name: str) -> None:
    """Treść pkt 5: bez uprawnień roota i bez zapisu poza /tmp w pamięci (i wolumenami)."""
    svc = service(name)
    assert svc.get("read_only") is True, f"{name}: read_only"
    assert "/tmp" in tmpfs_paths(name), f"{name}: /tmp w tmpfs"
    assert "ALL" in as_list(svc.get("cap_drop")), f"{name}: cap_drop ALL"
    assert "no-new-privileges" in security_opts(name), f"{name}: no-new-privileges"
    assert not svc.get("privileged"), f"{name}: privileged"
    assert "user" not in svc, f"{name}: user nadpisuje USER z Dockerfile"


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
    _assert_locked_down("api")
    assert not service("api").get("volumes"), "api: bez wolumenów (pliki tylko w pamięci)"


# M1.5: model w compose.
OLLAMA_DOCKERFILE = (ROOT / "ollama" / "Dockerfile").read_text(encoding="utf-8")


def test_ollama_image_is_pinned_and_runs_without_root() -> None:
    (image,) = re.findall(r"^FROM (\S+)", OLLAMA_DOCKERFILE, flags=re.MULTILINE)
    assert re.fullmatch(r"(docker\.io/)?ollama/ollama:\d+\.\d+\.\d+", image), image
    users = re.findall(r"^USER (\d+):(\d+)$", OLLAMA_DOCKERFILE, flags=re.MULTILINE)
    assert users and all(int(n) > 0 for n in users[-1]), users
    assert f"--uid {users[-1][0]}" in OLLAMA_DOCKERFILE


def test_ollama_keeps_models_in_volume_and_is_not_published() -> None:
    assert build_context("ollama") == "ollama"
    assert volume_mounts("ollama") == {"/home/ollama/.ollama": "ollama-models"}
    assert "ollama-models" in (COMPOSE.get("volumes") or {}), "wolumen nazwany, nie katalog hosta"
    assert "OLLAMA_MODELS=/home/ollama/.ollama/models" in OLLAMA_DOCKERFILE
    assert not service("ollama").get("ports"), "model tylko w sieci compose"


def test_ollama_context_fits_prompt_and_answer() -> None:
    """K1: prompt i odpowiedź to do ok. 4100 tokenów, a domyślny kontekst ma 4096."""
    parsed = interpolation(environment("ollama")["OLLAMA_CONTEXT_LENGTH"])
    assert parsed and parsed[0] == "LLM_CONTEXT_TOKENS" and int(parsed[1]) >= 16384, parsed


def test_ollama_has_no_root_privileges_or_persistent_writes_outside_volume() -> None:
    _assert_locked_down("ollama")


def test_ollama_cloud_is_off() -> None:
    assert environment("ollama")["OLLAMA_NO_CLOUD"].lower() in {"1", "true"}


def test_api_talks_to_ollama_service_by_default() -> None:
    assert interpolation(environment("api")["LLM_BASE_URL"]) == (
        "LLM_BASE_URL",
        "http://ollama:11434/v1",
    )


def test_compose_passes_d11_settings_to_api() -> None:
    api = environment("api")
    for name in ("LLM_ANALYSIS_BUDGET_S", "LLM_MAX_ATTEMPTS"):
        assert interpolation(api[name]) == (name, "")
