"""P3 sprawdzane na syntetycznych formularzach i lokalnych atrapach."""

import html
import importlib.util
import json
import logging
from pathlib import Path

import httpx
import pytest
from test_extract import docx, pdf

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("generate_forms", REPO / "scripts" / "generate_forms.py")
assert SPEC is not None and SPEC.loader is not None
generate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate)

TEXT = "Wniosek o zajęcia. Dyscyplina: piłkarze. Adres siedziby. Telefon klubu."


def _analysis(**decisions: object) -> dict:
    return {
        "title": "Wniosek testowy",
        "addressee": {"type": "URZAD", "name": "Urząd testowy"},
        "applicants": "BOTH",
        "applicant": {
            "proxy": False, "applicant_pesel": False, "person_address": False,
            "entity_ids": [], "entity_ids_one_of": False, "entity_address": False,
            "representative_proof": False, "correspondence_address": False,
            "contact": [], "applicant_extra_fields": [],
        } | decisions,
        "subject_pages": [{"title": "Zajęcia", "sections": [{"title": "Wybór", "fields": [
            {"label": "Dyscypliny", "type": "RADIO", "options": ["Piłka", "Curling"]},
            {"label": "Cel", "type": "TEXT_FIELD"},
        ]}]}],
    }


@pytest.fixture
def materials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "materialy"
    root.mkdir()
    monkeypatch.setattr(generate, "MATERIALS", root)
    monkeypatch.delenv("LLM_FIXTURE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://model.test/v1")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "10")

    def unexpected_request(*args: object) -> None:
        pytest.fail("Test P3 próbował użyć sieci")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", unexpected_request)
    return root


def _file(materials: Path, number: int, name: str, data: bytes) -> Path:
    folder = materials / f"{number}. Formularz testowy"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    return path


def _word(text: str = TEXT) -> bytes:
    return docx(f"<w:p><w:r><w:t>{html.escape(text)}</w:t></w:r></w:p>")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: dict | None = None) -> None:
    path = tmp_path / "synthetic-analysis.json"
    path.write_text(json.dumps(_analysis() if data is None else data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("LLM_FIXTURE", str(path))


def _run(out: Path, forms: str, *args: str, transport: httpx.BaseTransport | None = None) -> int:
    return generate.main(["--out", str(out), "--forms", forms, *args], transport=transport)


def _report(out: Path) -> list[dict]:
    return json.loads((out / "report.json").read_text(encoding="utf-8"))["forms"]


def _reply(
    content: str, *, finish_reason: str = "stop", prompt_tokens: int = 3000, completion_tokens: int = 30,
) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


def test_preference_and_extraction_fallback_call_api_pipeline(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(materials, 2, "A Wizualizacja.DOCX", _word())
    _file(materials, 2, "a.json", b"{}")
    _file(materials, 2, "pierwszy.DOCX", _word(""))
    _file(materials, 2, "drugi.pdf", pdf(TEXT))
    _fixture(tmp_path, monkeypatch)
    calls = []

    def record(owner, name: str) -> None:
        original = getattr(owner, name)

        def counted(*args, **kwargs):
            calls.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, counted)

    for owner, name in (
        (generate.files, "validate_upload"), (generate.extract, "extract"),
        (generate.analysis, "analyze"), (generate.generator, "build_form"), (generate.lint, "check"),
    ):
        record(owner, name)

    out = tmp_path / "out"
    assert _run(out, "2", "--prefer", "docx,pdf") == 0
    row, = _report(out)
    assert (row["file"], row["format"], row["status"]) == ("drugi.pdf", "pdf", "OK")
    assert [(item["file"], item["format"]) for item in row["inputs"]] == [
        ("pierwszy.DOCX", "docx"), ("drugi.pdf", "pdf"),
    ]
    assert row["inputs"][0]["error"]["class"] == "ExtractionError"
    assert row["inputs"][1]["error"] is None
    assert row["attempts"] == 0
    assert calls == ["validate_upload", "extract", "validate_upload", "extract", "analyze", "build_form", "check"]


def test_uses_detected_format_and_five_requires_opt_in(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(materials, 5, "formularz.DOC", _word())
    _fixture(tmp_path, monkeypatch)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as stopped:
        _run(out, "5")
    assert stopped.value.code == 2
    assert not out.exists()
    assert _run(out, "5", "--include-5") == 0
    row, = _report(out)
    assert (row["file"], row["format"]) == ("formularz.DOC", "docx")


def test_writes_coi_even_when_linter_reports_errors(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(materials, 2, "formularz.docx", _word())
    _fixture(tmp_path, monkeypatch)
    errors = [f"Treść błędu {number}" for number in range(6)]
    monkeypatch.setattr(generate.generator, "build_form", lambda analysis: {"title": "Uszkodzony wynik"})
    monkeypatch.setattr(generate.lint, "check", lambda form: errors)
    out = tmp_path / "out"

    assert _run(out, "2") == 0
    assert json.loads((out / "F2.coi.json").read_text(encoding="utf-8")) == {"title": "Uszkodzony wynik"}
    assert (out / "F2.analysis.json").is_file()
    assert _report(out)[0]["lint"] == {"count": 6, "first_errors": errors[:5]}
    assert "Treść błędu" not in (out / "report.md").read_text(encoding="utf-8")


def test_rejects_folder_one_before_search(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _file(materials, 1, "kontrolny.docx", _word())

    def unexpected_search(*args: object) -> None:
        pytest.fail("Odmowa F1 musi nastąpić przed wyszukiwaniem plików")

    monkeypatch.setattr(generate, "_candidates", unexpected_search)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as stopped:
        _run(out, "2,1", "--include-5")
    assert stopped.value.code == 2
    assert "Folder 1" in capsys.readouterr().err
    assert not out.exists()


def test_rejects_symlink_to_control_directory(materials: Path, tmp_path: Path) -> None:
    controlled = _file(materials, 1, "kontrolny.docx", _word())
    (materials / "2. Alias").symlink_to(controlled.parent, target_is_directory=True)
    out = tmp_path / "out"
    assert _run(out, "2") == 1
    row, = _report(out)
    assert row["error"]["stage"] == "selection"
    assert row["inputs"] == []
    assert not (out / "F2.coi.json").exists()


@pytest.mark.parametrize("location", ["env", "folder-one"])
def test_wont_use_protected_file_as_model_fixture(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str,
) -> None:
    if location == "folder-one":
        fixture = _file(materials, 1, "kontrolny.json", b"{}")
    else:
        fixture = tmp_path / ".env"
        fixture.write_text("Syntetyczna treść.", encoding="utf-8")
    alias = tmp_path / "alias.json"
    alias.symlink_to(fixture)
    monkeypatch.setenv("LLM_FIXTURE", str(alias))
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as stopped:
        _run(out, "2")
    assert stopped.value.code == 2
    assert not out.exists()


@pytest.mark.parametrize("via_link", [False, True])
def test_rejects_output_inside_repository(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_link: bool,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(generate, "REPO", repo)
    destination = repo
    if via_link:
        destination = tmp_path / "alias"
        destination.symlink_to(repo, target_is_directory=True)
    with pytest.raises(SystemExit) as stopped:
        _run(destination / "out", "2")
    assert stopped.value.code == 2
    assert not (repo / "out").exists()


def test_reports_failure_and_continues_with_next_form(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(materials, 2, "bez-tekstu.pdf", pdf(""))
    _file(materials, 9, "formularz.docx", _word())
    _fixture(tmp_path, monkeypatch)
    out = tmp_path / "out"

    assert _run(out, "2,9") == 1
    failed, passed = _report(out)
    assert (failed["form"], failed["status"], failed["error"]["class"]) == ("F2", "błąd", "ExtractionError")
    assert (failed["error"]["status_code"], failed["error"]["stage"]) == (400, "extract")
    assert failed["timings_s"]["extract"] > 0
    assert (passed["form"], passed["status"]) == ("F9", "OK")
    assert (out / "F9.coi.json").is_file()
    assert not (out / "F2.coi.json").exists()
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "| F2 | błąd |" in md and "| F9 | OK |" in md


class _TrackedTransport(httpx.MockTransport):
    def __init__(self, replies: list[httpx.Response]):
        super().__init__(self.reply)
        self.replies = iter(replies)
        self.sent: list[dict] = []
        self.closes = 0

    def reply(self, request: httpx.Request) -> httpx.Response:
        assert self.closes == 0
        self.sent.append(json.loads(request.content))
        return next(self.replies)

    def close(self) -> None:
        self.closes += 1


def test_telemetry_counts_both_k3_requests_before_closing(materials: Path, tmp_path: Path) -> None:
    _file(materials, 2, "formularz.docx", _word())
    invalid = _reply("{}", finish_reason="length", completion_tokens=2)
    transport = _TrackedTransport([
        httpx.Response(200, stream=httpx.ByteStream(invalid.content)),
        _reply(json.dumps(_analysis()), prompt_tokens=3200, completion_tokens=150),
    ])
    out = tmp_path / "out"
    assert _run(out, "2", transport=transport) == 0
    row, = _report(out)
    assert row["attempts"] == len(transport.sent) == 2
    assert transport.closes == 1
    assert [msg["role"] for msg in transport.sent[1]["messages"]] == ["system", "user", "assistant", "user"]
    requests = row["requests"]
    assert [item["status_code"] for item in requests] == [200, 200]
    assert [item["finish_reason"] for item in requests] == ["length", "stop"]
    assert [item["prompt_tokens"] for item in requests] == [3000, 3200]
    assert [item["completion_tokens"] for item in requests] == [2, 150]
    assert all(item["elapsed_s"] >= 0 and "body_excerpt" not in item for item in requests)
    assert "length" in (out / "report.md").read_text(encoding="utf-8")


def test_separates_k3_budget_from_model_failure_without_a_request(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(materials, 8, "dlugi.docx", _word("Długi fragment. " * 3000))
    _file(materials, 9, "krotki.docx", _word())
    monkeypatch.setenv("LLM_FIXTURE", str(tmp_path / "brak.json"))
    out = tmp_path / "out"
    assert _run(out, "8,9") == 1
    budget, model = _report(out)
    assert (budget["error"]["status_code"], budget["error"]["reason"]) == (503, "budżet K3 (do K3.1)")
    assert (model["error"]["status_code"], model["error"]["reason"]) == (503, "błąd modelu")
    assert budget["attempts"] == model["attempts"] == 0
    assert "budżet K3 (do K3.1)" in (out / "report.md").read_text(encoding="utf-8")


def test_redacts_key_from_body_artifacts_and_logs(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    for number in (2, 9):
        _file(materials, number, "formularz.docx", _word())
    key = "testowy-sekret-tylko-w-env"
    monkeypatch.setenv("LLM_API_KEY", key)
    caplog.set_level(logging.INFO, logger="app.analysis")
    data = _analysis()
    data["title"] = f"Wniosek {key}"
    replies = iter([
        httpx.Response(429, text="x" * 285 + key + "y" * 100, headers={"X-Test": "hidden-header"}),
        _reply(json.dumps(data), finish_reason=f"stop {key}"),
    ])

    def reply(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {key}"
        return next(replies)

    out = tmp_path / "out"
    assert _run(out, "2,9", transport=httpx.MockTransport(reply)) == 1
    failed, passed = _report(out)
    assert failed["requests"][0]["body_excerpt"] == "x" * 285 + "***" + "y" * 12
    assert failed["requests"][0]["status_code"] == 429
    assert passed["requests"][0]["finish_reason"] == "stop ***"
    assert "finish_reason=stop ***" in caplog.text
    assert key not in caplog.text
    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        assert key not in text
        assert "hidden-header" not in text
    for name in ("F9.analysis.json", "F9.coi.json"):
        assert json.loads((out / name).read_text(encoding="utf-8"))["title"] == "Wniosek ***"


def test_quality_uses_text_prefixes_and_checks_applicant_evidence(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(materials, 2, "formularz.docx", _word(
        "Ｄｙｓｃｙｐｌｉｎｉｅ PIŁKARZE cel. REGON-u, poprzedniknip, tel. e-mail, korespondencję, siedziby."
    ))
    _fixture(tmp_path, monkeypatch, _analysis(
        proxy=True, applicant_pesel=True, entity_ids=["NIP", "REGON", "KRS"],
        entity_address=True, correspondence_address=True, contact=["PHONE", "EMAIL"],
    ))
    out = tmp_path / "out"
    assert _run(out, "2") == 0
    quality = _report(out)[0]["quality"]
    assert quality["text_support"] == {
        "matched": 2, "total": 4, "percent": 50.0,
        "unsupported_labels": ["Cel"], "unsupported_options": ["Curling"],
    }
    assert quality["applicant_without_evidence"] == ["PESEL", "NIP", "KRS", "pełnomocnik"]
    assert "przybliżeni" in (out / "report.md").read_text(encoding="utf-8").casefold()


def test_flags_unknown_dictionary_and_counts_show_outside_literals(
    materials: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _analysis()
    page = data["subject_pages"][0]
    page["sections"][0]["fields"] = [
        {"label": "Źródło", "type": "RADIO", "options": ["a or and", "b", "c"]},
        {"label": "Decyzja", "type": "RADIO", "options": ["tak", "nie"]},
    ]
    page["sections"].append({
        "title": "Szczegóły",
        "show_if": {"field": "Źródło", "equals": "b", "any_of": ["c"]},
        "show_if_all": [{"field": "Decyzja", "equals": "tak"}],
        "fields": [
            {"label": "Opis", "type": "TEXT_FIELD", "show_if": {"field": "Źródło", "equals": "a or and"}},
        ],
    })
    _file(materials, 2, "formularz.docx", _word())
    _fixture(tmp_path, monkeypatch, data)
    build = generate.generator.build_form

    def include_extra_dictionary(analysis) -> dict:
        form = build(analysis)
        item = form["tabs"][1]["questions"][0]["field"]["repeatingSectionGrid"][0]["field"]
        item["dictionaryName"] = "Działki"
        return form

    monkeypatch.setattr(generate.generator, "build_form", include_extra_dictionary)
    out = tmp_path / "out"
    assert _run(out, "2") == 0
    row, = _report(out)
    assert row["stats"]["dictionaries"]["Działki"] == 1
    assert row["quality"]["unexpected_dictionaries"] == ["Działki"]
    # Trzeci SHOW pochodzi z sekcji standardowej strony Dane dla BOTH.
    assert row["stats"]["show"] == {"total": 3, "or": 1, "and": 1, "sections": 2}
    assert "Działki" in (out / "report.md").read_text(encoding="utf-8")
