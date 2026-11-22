"""scripts/bench_model.py offline: ocena odpowiedzi i cały przebieg na atrapie serwera, bez modelu."""

import copy
import importlib.util
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from env_proxy import record_proxy_use

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("bench_model", REPO / "scripts" / "bench_model.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

REFERENCE = json.loads((REPO / "backend" / "tests" / "fixtures" / "fields.json").read_text(encoding="utf-8"))
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(body_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", f"<w:document {W}><w:body>{body_xml}</w:body></w:document>")
    return buffer.getvalue()


def _cell(text: str) -> str:
    return f"<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"


def test_docx_text_keeps_paragraphs_and_table_rows_in_order() -> None:
    data = _docx(
        "<w:p><w:r><w:t>Wniosek o </w:t></w:r><w:r><w:t>coś</w:t></w:r></w:p>"
        f"<w:tbl><w:tr>{_cell('Kwota')}{_cell('……')}</w:tr></w:tbl>"
        "<w:p><w:r><w:t>Uzasadnienie</w:t></w:r></w:p>"
    )
    assert bench.docx_text(data) == "Wniosek o coś\nKwota | ……\nUzasadnienie"


def test_reference_answer_scores_as_valid_and_complete() -> None:
    result = bench.evaluate(json.dumps(REFERENCE, ensure_ascii=False), REFERENCE)
    assert (result["json_ok"], result["valid"], result["validation_errors"]) == (True, True, 0)
    assert (result["recall"], result["precision"], result["type_agreement"]) == (1.0, 1.0, 1.0)
    assert result["fields_matched"] == result["fields_reference"] == 7
    assert result["show_if_predicted"] == result["show_if_reference"] == 2
    assert result["missing_reference_labels"] == []
    assert result["applicants_ok"] and result["addressee_type_ok"]


def test_text_that_is_not_json_scores_nothing() -> None:
    result = bench.evaluate('{"title": "Wniosek"', REFERENCE)
    assert (result["json_ok"], result["valid"]) == (False, False)
    assert "recall" not in result


def test_invalid_analysis_is_counted_without_quoting_the_form() -> None:
    broken = copy.deepcopy(REFERENCE)
    radio = broken["subject_pages"][0]["sections"][1]["fields"][0]
    radio["options"] = []
    result = bench.evaluate(json.dumps(broken, ensure_ascii=False), REFERENCE)
    assert (result["json_ok"], result["valid"]) == (True, False)
    assert result["validation_errors"] >= 1
    assert result["error_types"]
    assert not any(radio["label"] in error for error in result["error_types"])
    # Zgodność pól liczymy także dla analizy, która nie przeszła walidacji.
    assert result["recall"] == 1.0


def test_missing_extra_and_retyped_fields_lower_the_scores() -> None:
    predicted = copy.deepcopy(REFERENCE)
    fields = predicted["subject_pages"][0]["sections"][0]["fields"]
    fields.pop(0)  # brak „Podatek, którego dotyczy nadpłata”
    fields[0]["type"] = "TEXT_FIELD"  # „Kwota” jako tekst zamiast NUMBER
    fields.append({"label": "Data złożenia", "type": "DATEPICKER"})
    predicted["applicants"] = "PERSON"

    result = bench.field_quality(predicted, REFERENCE)
    assert (result["fields_predicted"], result["fields_reference"], result["fields_matched"]) == (7, 7, 6)
    assert result["recall"] == round(6 / 7, 3)
    assert result["precision"] == round(6 / 7, 3)
    assert result["type_agreement"] == round(5 / 6, 3)
    assert result["missing_reference_labels"] == ["Podatek, którego dotyczy nadpłata"]
    assert result["applicants_ok"] is False


def test_missing_applicants_is_not_a_match() -> None:
    # Od P1.2a `applicants` jest wymagane, więc brak klucza nie znaczy już BOTH.
    predicted = copy.deepcopy(REFERENCE)
    del predicted["applicants"]
    assert REFERENCE["applicants"] == "BOTH"
    assert bench.field_quality(predicted, REFERENCE)["applicants_ok"] is False


def _analysis(*labels: str) -> dict:
    fields = [{"label": label, "type": "TEXT_FIELD"} for label in labels]
    return {"subject_pages": [{"title": "Strona", "sections": [{"title": "Sekcja", "fields": fields}]}]}


def test_one_predicted_field_matches_at_most_one_reference_field() -> None:
    result = bench.field_quality(_analysis("Kwota"), _analysis("Kwota", "Kwota nadpłaty"))
    assert (result["fields_matched"], result["recall"], result["precision"]) == (1, 0.5, 1.0)


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Numer rachunku", "Numer rachunku bankowego", True),
        ("Kwota nadpłaty:", "kwota  nadplaty", True),
        ("Uzasadnienie", "Uzasadnienie wniosku", True),
        ("Kwota", "Numer rachunku", False),
        ("", "Kwota", False),
    ],
)
def test_label_similarity_tolerates_wording_but_not_other_fields(a: str, b: str, same: bool) -> None:
    assert (bench.label_similarity(a, b) >= bench.LABEL_MATCH) is same


def test_control_folder_is_refused() -> None:
    with pytest.raises(SystemExit, match="Folder 1"):
        bench.check_input(bench.MATERIALS / "1. zbiór kontrolny" / "wniosek.docx")
    bench.check_input(bench.MATERIALS / "5. zbiór roboczy" / "wniosek.docx")


CONTROL_TEXT = "Wniosek kontrolny, którego model nie może zobaczyć."


def _control_materials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """materialy/ w tmp_path z jednym plikiem folderu 1, w podkatalogu, żeby kontrola szła rekurencyjnie."""
    materials = tmp_path / "materialy"
    control = materials / "1. zbiór kontrolny" / "załączniki" / "wizualizacja.txt"
    control.parent.mkdir(parents=True)
    control.write_text(CONTROL_TEXT, encoding="utf-8")
    monkeypatch.setattr(bench, "MATERIALS", materials)
    return materials


def test_copy_of_a_control_file_is_refused_wherever_it_lies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Materiały COI mają taką kopię: plik z folderu 1 leży też w katalogu z materiałami dodatkowymi.
    materials = _control_materials(tmp_path, monkeypatch)
    for copy_path in (materials / "Materiały dodatkowe" / "wizualizacja.txt", tmp_path / "poza" / "inna nazwa.txt"):
        copy_path.parent.mkdir(parents=True)
        copy_path.write_text(CONTROL_TEXT, encoding="utf-8")
        with pytest.raises(SystemExit, match="folderu 1"):
            bench.check_input(copy_path)

    working = materials / "5. zbiór roboczy" / "wniosek.txt"
    working.parent.mkdir(parents=True)
    working.write_text("Wniosek roboczy", encoding="utf-8")
    bench.check_input(working)


def test_benchmark_stops_on_a_control_copy_before_any_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _control_materials(tmp_path, monkeypatch)
    copy_path = tmp_path / "kopia.txt"
    copy_path.write_text(CONTROL_TEXT, encoding="utf-8")
    sent: list[httpx.Request] = []
    model = httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(503))

    with pytest.raises(SystemExit, match="folderu 1"):
        bench.main(["--input", str(copy_path), "--base-url", "http://model.test/v1"], transport=model)
    assert sent == []


def test_version_probe_ignores_proxy_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    used = record_proxy_use(monkeypatch, {"version": "0.40.15"})
    assert bench.ollama_version("http://ollama:11434/v1", None) == "0.40.15"
    assert used == [None]


def test_raw_answers_stay_out_of_git(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="materialy"):
        bench.check_output_dir(REPO / "backend" / "bench")
    bench.check_output_dir(bench.MATERIALS / "bench")
    bench.check_output_dir(tmp_path)


def test_image_input_is_sent_as_image_part(tmp_path: Path) -> None:
    scan = tmp_path / "skan.JPG"
    scan.write_bytes(b"\xff\xd8\xff")
    system, user = bench.build_messages(scan)
    assert "Schemat JSON" in system["content"]
    assert user["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    with pytest.raises(SystemExit, match="extract"):
        bench.build_messages(tmp_path / "wniosek.pdf")


def _fake_ollama(analysis: str, reasoning: str = "") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.15"})
        body = json.loads(request.content)
        warmup = body["response_format"]["json_schema"]["name"] == "Warmup"
        message = {"content": '{"ok": true}' if warmup else analysis, "reasoning": reasoning}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2000, "completion_tokens": 500},
            },
        )

    return httpx.MockTransport(handler)


def test_benchmark_reports_numbers_and_keeps_raw_answers_apart(tmp_path: Path) -> None:
    form = tmp_path / "wniosek.txt"
    form.write_text("Wniosek o stwierdzenie nadpłaty", encoding="utf-8")
    raw_dir = tmp_path / "raw"
    analysis = json.dumps(REFERENCE, ensure_ascii=False)

    report = bench.run_benchmark(
        [form],
        ["qwen3.5:4b"],
        runs=2,
        base_url="http://model.test/v1",
        timeout_s=5,
        max_tokens=4096,
        raw_dir=raw_dir,
        transport=_fake_ollama(analysis),
    )

    assert report["ollama_version"] == "0.40.15"
    entry = report["models"]["qwen3.5:4b"]
    assert "load_and_warmup_s" in entry
    summary = entry["inputs"]["wniosek.txt"]["summary"]
    assert (summary["runs"], summary["json_ok"], summary["valid"], summary["thinking_seen"]) == (2, 2, 2, 0)
    assert summary["recall_mean"] == 1.0
    first = entry["inputs"]["wniosek.txt"]["runs"][0]
    assert (first["prompt_tokens"], first["completion_tokens"], first["finish_reason"]) == (2000, 500, "stop")
    assert "content" not in json.dumps(report)
    saved = sorted(raw_dir.glob("*.json"))
    assert len(saved) == 2
    assert json.loads(saved[0].read_text(encoding="utf-8"))["content"] == analysis


def test_eden_uses_the_application_environment_without_probing_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    @dataclass(frozen=True)
    class EdenSettings(bench.Settings):
        llm_provider: str = "edenai"

    monkeypatch.setattr(bench, "Settings", EdenSettings)
    monkeypatch.setattr(bench, "MATERIALS", tmp_path / "materialy")
    monkeypatch.setenv("LLM_PROVIDER", "edenai")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.eu.edenai.run/v3")
    monkeypatch.setenv("LLM_MODEL", "ovhcloud/Qwen3.5-9B")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-eden-key")
    monkeypatch.setenv("LLM_MAX_TOKENS", "8100")
    monkeypatch.setenv("LLM_TIMEOUT_S", "12.5")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "off")
    monkeypatch.setenv("LLM_FIXTURE", "")
    form = tmp_path / "wniosek.txt"
    form.write_text("Przykładowy wniosek", encoding="utf-8")
    requests: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        assert (request.method, str(request.url)) == ("POST", "https://api.eu.edenai.run/v3/chat/completions")
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(REFERENCE)}}]})

    assert bench.main(["--input", str(form)], transport=httpx.MockTransport(reply)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ollama_version"] is None
    assert report["models"]["ovhcloud/Qwen3.5-9B"]["inputs"][form.name]["summary"]["valid"] == 1
    assert len(requests) == 2
    for request, expected_limit in zip(requests, (16, 8100), strict=True):
        assert request.headers["Authorization"] == "Bearer synthetic-eden-key"
        assert request.extensions["timeout"]["read"] == 12.5
        body = json.loads(request.content)
        assert body["model"] == "ovhcloud/Qwen3.5-9B"
        assert body["max_tokens"] == expected_limit
        assert "reasoning_effort" not in body


def test_invalid_answer_and_leftover_thinking_are_counted(tmp_path: Path) -> None:
    form = tmp_path / "wniosek.txt"
    form.write_text("Wniosek", encoding="utf-8")
    broken = copy.deepcopy(REFERENCE)
    broken["subject_pages"][0]["sections"][1]["fields"][0]["options"] = []
    report = bench.run_benchmark(
        [form],
        ["qwen3.5:4b"],
        runs=1,
        base_url="http://model.test/v1",
        timeout_s=5,
        max_tokens=4096,
        transport=_fake_ollama(json.dumps(broken), reasoning="Myślę..."),
    )
    summary = report["models"]["qwen3.5:4b"]["inputs"]["wniosek.txt"]["summary"]
    assert (summary["json_ok"], summary["valid"], summary["thinking_seen"]) == (1, 0, 1)


def test_unreachable_server_gives_no_numbers_and_exit_code_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    form = tmp_path / "wniosek.txt"
    form.write_text("Wniosek", encoding="utf-8")
    down = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("connection refused")))

    code = bench.main(["--input", str(form), "--base-url", "http://model.test/v1"], transport=down)

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    entry = report["models"]["qwen3.5:4b"]
    assert "niedostępny" in entry["error"]
    assert entry["inputs"] == {}
