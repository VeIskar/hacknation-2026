"""Binarny DOC (Word 97–2003): tekst z tablicy kawałków, historie, pola tekstowe i pliki uszkodzone."""

import random
import re
from pathlib import Path

import pytest
from extract_builders import (
    CLX,
    PLC_SPA_MOM,
    PLC_TXBX_TXT,
    TextBox,
    compound_file,
    word_document,
)

from app.errors import ExtractionError
from app.extract import doc
from app.extract.doc import doc_text
from app.extract.readers import read_document
from app.files import validate_upload

MATERIALS = Path(__file__).resolve().parents[2] / "materialy"
UNREADABLE = "Nie udało się odczytać treści pliku."
WORD = re.compile(r"[^\W\d_]{4,}")


def test_reads_paragraphs_line_breaks_and_page_breaks_in_document_order() -> None:
    data = word_document("Wniosek o wydanie zaświadczenia\rImię i nazwisko\x0bZażółć gęślą jaźń\x0cZałączniki\r")

    reading = read_document(data, validate_upload("wniosek.DOC", data, max_bytes=len(data)), language="pol")

    assert reading.text == "Wniosek o wydanie zaświadczenia\nImię i nazwisko\nZażółć gęślą jaźń\fZałączniki"
    assert reading.ocr_used is False
    assert reading.warnings == []


def test_reads_eight_bit_piece_and_drops_object_marks() -> None:
    # Kawałek „skompresowany” ma jeden bajt na znak. \x01 i \x08 to miejsca obrazu i kształtu.
    data = word_document("Urz\x01\x08ad Gminy – wnio\x1fsek\x1e2026\r", compressed=True)

    assert doc_text(data) == "Urzad Gminy – wniosek-2026"


def test_reads_piece_table_from_the_table_stream_named_in_header() -> None:
    # Bit fWhichTblStm wybiera strumień 0Table albo 1Table; drugi bywa pozostałością po edycji.
    data = word_document("Wniosek\r", flags=0x0000, streams={"1Table": b"\x05" * 64})

    assert doc_text(data) == "Wniosek"


def test_keeps_field_result_and_drops_field_code() -> None:
    main = "Strona \x13 PAGE \x141\x15 z \x13 NUMPAGES \x13 zagnieżdżony kod \x14 x \x15 \x142\x15\rPole bez wyniku: \x13 SEQ \x15koniec\r"

    assert doc_text(word_document(main)) == "Strona 1 z 2\nPole bez wyniku: koniec"


def test_table_cells_are_separated_and_double_cell_mark_ends_row() -> None:
    main = "Numer sprawy\x07Kwota\x07\x07R/1\x07100 zł\x07\x07Po tabeli\r"

    assert doc_text(word_document(main)) == "Numer sprawy | Kwota\nR/1 | 100 zł\nPo tabeli"


def test_appends_numbered_footnotes_endnotes_and_unique_header_lines() -> None:
    data = word_document(
        "Adres e-mail\x02)\rPodpis\x02)\r",
        footnotes="\x02) Dane nieobowiązkowe.\r\x02) Podpis własnoręczny.\r",
        endnotes="\x02 Przypis końcowy\r",
        # Znaki \x03 i \x04 to separatory przypisów; ta sama stopka stoi dla stron parzystych i nieparzystych.
        headers="\x03\r\r\x04\r\r* niepotrzebne skreślić\r\r* niepotrzebne skreślić\r\r",
    )

    assert doc_text(data) == (
        "Adres e-mail1)\nPodpis2)\n1) Dane nieobowiązkowe.\n2) Podpis własnoręczny.\n1 Przypis końcowy\n* niepotrzebne skreślić"
    )


def test_text_boxes_follow_page_layout_not_file_order() -> None:
    # Dokument przerobiony z PDF: każdy fragment wiersza to osobne pole, a plik trzyma je od dołu strony.
    main = "\x08\x08\x08\x08\x08\x0c\x08\r"
    boxes = [
        TextBox("Podpis", anchor=0, top=9000, left=500),
        TextBox("zł", anchor=1, top=3040, left=4000),
        TextBox("Kwota", anchor=2, top=3000, left=500),
        TextBox("WNIOSEK\rO ZWROT", anchor=3, top=1000, left=500),
        TextBox("100", anchor=4, top=3010, left=2000),
        TextBox("Strona druga", anchor=6, top=100, left=100),
    ]

    assert doc_text(word_document(main, boxes=boxes)) == "WNIOSEK\nO ZWROT\nKwota 100 zł\nPodpis\fStrona druga"


def test_text_box_stays_with_its_anchor_paragraph() -> None:
    main = "Imię i nazwisko\r\x08Adres\rPESEL\r"
    boxes = [TextBox("Urząd Miasta\rul. Dworcowa 29", anchor=16, top=292, left=5582)]

    assert doc_text(word_document(main, boxes=boxes)) == "Imię i nazwisko\nAdres\nUrząd Miasta\nul. Dworcowa 29\nPESEL"


def test_text_box_without_valid_anchor_is_appended() -> None:
    main = "Wniosek\r\x08\r"
    boxes = [
        TextBox("Bez kształtu"),
        TextBox("Kotwica poza tekstem", anchor=500),
        TextBox("Kotwica na literze", anchor=1),
        TextBox("Przy kotwicy", anchor=8),
    ]

    assert doc_text(word_document(main, boxes=boxes)) == "Wniosek\n\nPrzy kotwicy\nKotwica na literze\nKotwica poza tekstem\nBez kształtu"


def test_surrogate_pair_keeps_positions_of_following_text() -> None:
    # Para surogatów to dwie pozycje w Word: kotwica za nią musi trafić w swój znak.
    main = "A\U0001f600B\x08\r"
    boxes = [TextBox("Pole", anchor=4)]

    assert doc_text(word_document(main, boxes=boxes)) == "A\U0001f600B\nPole"


VALID = word_document("Wniosek o wydanie decyzji\r", boxes=[TextBox("Pole")])


@pytest.mark.parametrize(
    "data",
    [
        b"/etc/hostname",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504,
        VALID[: len(VALID) // 2],
        compound_file({"Inny": b"dane"}),
        word_document("Wniosek\r", ident=0xA5DC),
        word_document("Wniosek\r", version=0x0065),
        word_document("Wniosek\r", flags=0x0300),
        word_document("Wniosek\r", streams={"1Table": None}),
        word_document("Wniosek\r", table=b""),
        word_document("Wniosek\r", parts={CLX: (0, 3)}),
        word_document("Wniosek\r", parts={CLX: (10_000, 21)}),
        word_document("Wniosek\r", table=b"\x02" + (16).to_bytes(4, "little") + bytes(16)),
        word_document("Wniosek\r", table=b"\x05" * 64),
        word_document("Wniosek\r", lengths=[1_000_000, 0, 0, 0, 0, 0, 0, 0]),
        word_document("Wniosek\r", lengths=[-1, 0, 0, 0, 0, 0, 0, 0]),
        word_document("Wniosek\r", boxes=[TextBox("Pole")], parts={PLC_TXBX_TXT: (50_000, 56)}),
        word_document("Wniosek\r", boxes=[TextBox("Pole", anchor=0)], parts={PLC_SPA_MOM: (50_000, 34)}),
        word_document(" \r\x08\x0c\r"),
    ],
    ids=[
        "short-bytes-are-not-a-path",
        "empty-container",
        "truncated",
        "no-word-stream",
        "wrong-ident",
        "word-95",
        "encrypted",
        "missing-table-stream",
        "empty-table-stream",
        "clx-too-short",
        "clx-outside-table",
        "piece-table-without-pieces",
        "clx-garbage",
        "story-longer-than-text",
        "negative-story-length",
        "text-box-table-outside-stream",
        "shape-table-outside-stream",
        "no-text",
    ],
)
def test_unreadable_doc_uses_contract_error(data: bytes) -> None:
    with pytest.raises(ExtractionError) as exc_info:
        read_document(data, "doc", language="pol")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UNREADABLE


@pytest.mark.parametrize("location", [1024, (2 * 1024) | 0x40000000], ids=["two-byte-piece", "one-byte-piece"])
def test_piece_pointing_outside_stream_is_unreadable(location: int) -> None:
    # Kawałek deklaruje więcej znaków, niż ma strumień: bez kontroli wycinek byłby po cichu krótszy.
    pieces = (0).to_bytes(4, "little") + (9_000).to_bytes(4, "little") + bytes(2) + location.to_bytes(4, "little") + bytes(2)
    table = b"\x02" + len(pieces).to_bytes(4, "little") + pieces

    with pytest.raises(ExtractionError, match=UNREADABLE):
        doc_text(word_document("Wniosek\r", table=table, lengths=[8, 0, 0, 0, 0, 0, 0, 0]))


def test_text_longer_than_limit_is_rejected_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    data = word_document("Wniosek o wydanie decyzji\r")
    monkeypatch.setattr(doc, "MAX_TEXT_CHARS", 13)
    assert doc_text(data) == "Wniosek o wydanie decyzji"

    monkeypatch.setattr(doc, "MAX_TEXT_CHARS", 12)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        doc_text(data)


def test_corrupted_documents_never_escape_contract_error() -> None:
    # Losowo zmienione bajty poprawnego dokumentu: każdy wynik to tekst albo ExtractionError.
    source = word_document(
        "Wniosek \x13 PAGE \x141\x15\r\x08\x07\x07\x0c\r",
        footnotes="\x02 przypis\r",
        boxes=[TextBox("Pole", anchor=18, top=5, left=5), TextBox("Drugie")],
    )
    generator = random.Random(2026)
    outcomes = set()
    for _ in range(400):
        damaged = bytearray(source)
        for _ in range(generator.randint(1, 8)):
            damaged[generator.randrange(len(damaged))] = generator.randrange(256)
        try:
            doc_text(bytes(damaged))
            outcomes.add("text")
        except ExtractionError:
            outcomes.add("error")
    assert outcomes == {"text", "error"}


def _coi_doc(folder: int) -> bytes:
    candidates = sorted(
        path
        for directory in MATERIALS.glob(f"{folder}. *")
        for path in directory.iterdir()
        if path.suffix.lower() == ".doc"
    )
    if not candidates:
        pytest.skip(f"brak pliku .doc z folderu {folder} w {MATERIALS}")
    return candidates[0].read_bytes()


@pytest.mark.parametrize(
    ("folder", "keyword"),
    [(1, "numer"), (2, "opłat"), (3, "zaświadcz"), (4, "świetlic"), (6, "pasa drogowego"), (8, "odpad"), (9, "stypendi")],
)
def test_reads_binary_doc_from_coi_materials(folder: int, keyword: str) -> None:
    data = _coi_doc(folder)

    reading = read_document(data, validate_upload("wniosek.doc", data, 10 * 1024 * 1024), language="pol")

    folded = reading.text.casefold()
    assert "wniosek" in folded or "deklaracja" in folded
    assert keyword in " ".join(folded.split())
    assert not re.search(r"[\x00-\x08\x0b\x0e-\x1f]", reading.text)


@pytest.mark.parametrize("folder", [2, 8])
def test_coi_doc_made_of_text_boxes_matches_docx_of_same_form(folder: int) -> None:
    # Foldery 2 i 8 to formularze przerobione z PDF: cała treść jest w polach tekstowych.
    docx_files = sorted(path for directory in MATERIALS.glob(f"{folder}. *") for path in directory.glob("*.docx"))
    if not docx_files:
        pytest.skip(f"brak pliku .docx z folderu {folder} w {MATERIALS}")
    from_doc = read_document(_coi_doc(folder), "doc", language="pol").text
    from_docx = read_document(docx_files[0].read_bytes(), "docx", language="pol").text

    assert sorted(WORD.findall(from_doc)) == sorted(WORD.findall(from_docx))


def test_coi_doc_text_boxes_come_in_reading_order() -> None:
    lines = doc_text(_coi_doc(8)).splitlines()

    # W pliku pola tej strony zapisane są od dołu do góry (pierwsze to „16. Numer/y działki”).
    assert lines[0] == "DEKLARACJA O WYSOKOŚCI MIESIĘCZNEJ OPŁATY"
    assert lines.index("A. ORGAN, DO KTÓREGO SKŁADANA JEST DEKLARACJA") < lines.index("B.1 DANE IDENTYFIKACYJNE")
    assert "4. wspólnota mieszkaniowa 5. spółdzielnia mieszkaniowa 6. inny podmiot posiadający nieruchomość" in lines
