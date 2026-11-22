"""OCR obrazów: wymiary z nagłówka, limit pikseli, podział wysokiego skanu na pasy i scalanie wierszy."""

import re
import shutil
import subprocess
import zlib
from collections import Counter
from itertools import pairwise
from pathlib import Path
from unittest.mock import Mock

import pytest
from extract_builders import jpeg, png, png_file, png_pixels

from app.errors import ExtractionError
from app.extract import images, ocr, sandbox
from app.extract.common import SetupError
from app.extract.readers import read_document
from app.files import validate_upload

MATERIALS = Path(__file__).resolve().parents[2] / "materialy"
UNREADABLE = "Nie udało się odczytać treści pliku."
TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
# Szerokość skanów COI: kartka A4 ma przy niej 2339 pikseli wysokości.
WIDTH = 1654
needs_ocr_engine = pytest.mark.skipif(
    shutil.which("tesseract") is None or not images.can_cut(), reason="brak programu Tesseract albo biblioteki Leptonica"
)


def completed(output: bytes) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess("tesseract", 0, output)


def _unfiltered_first_row(pixels: bytes, width: int) -> bytes:
    """Pierwszy wiersz obrazu 8-bitowego: nad nim nie ma wiersza, więc filtry „góra” i „brak” dają to samo."""
    kind, row = pixels[0], pixels[1 : 1 + width]
    if kind in (0, 2):
        return row
    assert kind == 1, kind  # „lewy sąsiad”: każdy bajt to różnica od poprzedniego
    values, previous = [], 0
    for value in row:
        previous = (previous + value) % 256
        values.append(previous)
    return bytes(values)


def png_with_size(width: int, height: int) -> bytes:
    """Nagłówek PNG z podanymi wymiarami, bez pikseli: tyle czyta kontrola limitu."""
    small = png(1, 1)
    return small[:16] + width.to_bytes(4, "big") + height.to_bytes(4, "big") + small[24:]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (png(1654, 2339), (1654, 2339)),
        (jpeg(1654, 37424), (1654, 37424)),
        (jpeg(1137, 1576, frame=0xC2), (1137, 1576)),
        # Bajty wypełnienia i segment komentarza przed ramką.
        (jpeg(300, 200, prefix=b"\xff\xff\xfe\x00\x05abc"), (300, 200)),
        (b"II*\x00\x08\x00\x00\x00\x02\x00\x00\x01\x04\x00\x01\x00\x00\x00\xc0\x06\x00\x00\x01\x01\x03\x00\x01\x00\x00\x00\x23\x09\x00\x00", (1728, 2339)),
        (b"MM\x00*\x00\x00\x00\x08\x00\x02\x01\x00\x00\x03\x00\x00\x00\x01\x06\xc0\x00\x00\x01\x01\x00\x04\x00\x00\x00\x01\x00\x00\x09\x23", (1728, 2339)),
    ],
    ids=["png", "jpeg", "progressive-jpeg", "jpeg-with-fill-and-comment", "tiff-little-endian", "tiff-big-endian"],
)
def test_size_reads_dimensions_from_header(data: bytes, expected: tuple[int, int]) -> None:
    assert images.size(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF89a" + b"\x00" * 32,
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        png(10, 10)[:20],
        png(10, 10).replace(b"IHDR", b"IDAT", 1),
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32,
        jpeg(100, 100)[:25],
        jpeg(0, 100),
        b"II*\x00\xff\xff\xff\x7f",
        b"II*\x00\x08\x00\x00\x00\x00\x00",
    ],
    ids=[
        "empty",
        "other-format",
        "png-without-header-chunk",
        "truncated-png",
        "png-other-first-chunk",
        "jpeg-without-frame",
        "truncated-jpeg",
        "jpeg-zero-width",
        "tiff-directory-outside-file",
        "tiff-without-dimensions",
    ],
)
def test_size_of_unknown_or_damaged_image_is_none(data: bytes) -> None:
    assert images.size(data) is None


@pytest.mark.parametrize(
    ("filename", "data"),
    [("skan.JPG", jpeg(1654, 2339)), ("skan.jpeg", jpeg(1654, 2339)), ("skan.JPE", jpeg(1654, 2339)), ("skan.png", png(40, 40))],
    ids=["jpg", "jpeg", "jpe", "png"],
)
def test_image_goes_to_local_tesseract_whole(monkeypatch: pytest.MonkeyPatch, filename: str, data: bytes) -> None:
    runner = Mock(return_value=completed(" Wniosek\nZałączniki\n\x0c".encode()))
    monkeypatch.setattr(subprocess, "run", runner)

    reading = read_document(data, validate_upload(filename, data, max_bytes=len(data)), language="pol+eng")

    runner.assert_called_once()
    (command,), options = runner.call_args
    assert command == ["tesseract", "stdin", "stdout", "-l", "pol+eng"]
    assert options["input"] == data
    assert options["timeout"] == ocr.OCR_TIMEOUT_SECONDS
    assert options["check"] is True
    # Jeden wątek na proces: równoległość dają osobne procesy Tesseracta.
    assert options["env"]["OMP_THREAD_LIMIT"] == "1"
    assert reading.text == "Wniosek\nZałączniki"
    assert reading.ocr_used is True
    assert reading.warnings == []


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CalledProcessError(1, "tesseract"),
        subprocess.TimeoutExpired("tesseract", timeout=60),
        b" \n\x0c",
        b"\xff",
    ],
    ids=["engine-error", "timeout", "empty-text", "bad-encoding"],
)
def test_unreadable_image_uses_contract_error(monkeypatch: pytest.MonkeyPatch, outcome: bytes | Exception) -> None:
    runner = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=completed(outcome))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ExtractionError) as exc_info:
        read_document(png(40, 40), "png", language="pol")

    runner.assert_called_once()
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UNREADABLE


@pytest.mark.parametrize(
    "failure",
    [FileNotFoundError(2, "No such file or directory", "tesseract"), PermissionError(13, "Permission denied", "tesseract")],
    ids=["missing", "not-executable"],
)
def test_tesseract_that_cannot_start_uses_server_error(monkeypatch: pytest.MonkeyPatch, failure: OSError) -> None:
    runner = Mock(side_effect=failure)
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(SetupError) as exc_info:
        read_document(png(40, 40), "png", language="pol")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Coś poszło nie tak. Spróbuj ponownie."
    assert "Tesseract" in exc_info.value.reason


# Tak Tesseract 5 zgłasza brak pliku z danymi języka (sprawdzone na 5.3.4 i 5.5.0).
MISSING_LANGUAGE = (
    b"Error opening data file /usr/share/tesseract-ocr/5/tessdata/zzz.traineddata\n"
    b'Please make sure the TESSDATA_PREFIX environment variable is set to your "tessdata" directory.\n'
    b"Failed loading language 'zzz'\n"
)


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CalledProcessError(1, "tesseract", b"", MISSING_LANGUAGE + b"Tesseract couldn't load any languages!\n"),
        # „pol+zzz”: Tesseract czyta bez brakującego języka i kończy się kodem 0.
        subprocess.CompletedProcess("tesseract", 0, b"Wniosek\n", MISSING_LANGUAGE),
    ],
    ids=["no-language-loaded", "one-of-languages-missing"],
)
def test_missing_language_data_is_server_error_not_unreadable_file(
    monkeypatch: pytest.MonkeyPatch, outcome: subprocess.CalledProcessError | subprocess.CompletedProcess
) -> None:
    runner = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(SetupError) as exc_info:
        read_document(png(40, 40), "png", language="pol+zzz")

    assert exc_info.value.status_code == 500
    assert "pol+zzz" in exc_info.value.reason
    assert runner.call_args.kwargs["capture_output"] is True


def test_tesseract_errors_other_than_language_data_mean_unreadable_image(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tak kończy się Tesseract na pliku, którego Leptonica nie zdekoduje: to wina pliku, nie wdrożenia.
    failure = subprocess.CalledProcessError(1, "tesseract", b"", b"Error in pixReadMem: Unknown format: no pix returned\nError during processing.\n")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))

    with pytest.raises(ExtractionError, match=UNREADABLE):
        read_document(png(40, 40), "png", language="pol")


@needs_ocr_engine
def test_real_tesseract_without_language_data_is_server_error() -> None:
    with pytest.raises(SetupError) as exc_info:
        ocr.image_text(png(60, 400), "zzz")

    assert "zzz" in exc_info.value.reason


def test_single_image_ocr_limit_leaves_room_within_read_limit() -> None:
    # Limit jednego Tesseracta równy limitowi procesu odczytu nigdy by nie zadziałał: proces ginie pierwszy.
    assert ocr.OCR_TIMEOUT_SECONDS <= sandbox.TIMEOUT_SECONDS / 2


@pytest.mark.parametrize(
    "data",
    [
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        png_with_size(10_001, 10_000),
        jpeg(40_000, 100),
    ],
    ids=["no-dimensions", "over-pixel-limit", "wider-than-tesseract-accepts"],
)
def test_image_outside_limits_is_rejected_before_ocr(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    runner = Mock(side_effect=AssertionError("obraz ponad limit nie może trafić do Tesseracta"))
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr(images, "strips", Mock(side_effect=AssertionError("ani do dekodera")))

    with pytest.raises(ExtractionError, match=UNREADABLE):
        read_document(data, "png", language="pol")

    runner.assert_not_called()


def test_pixel_limit_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=completed(b"Wniosek")))
    monkeypatch.setattr(ocr, "MAX_IMAGE_PIXELS", 40 * 40)

    assert ocr.image_text(png(40, 40), "pol") == "Wniosek"
    assert ocr.image_text(png(40, 41), "pol") == ""


@pytest.mark.parametrize(
    ("height", "expected"),
    [
        (2339, [(0, 2339)]),
        (4678, [(0, 4678)]),
        # Do dwóch kartek i zakładki obraz idzie w całości: pas z samej zakładki nic by nie dał.
        (4678 + 206, [(0, 4884)]),
        (14034, [(0, 4781), (4575, 9459), (9253, 14034)]),
    ],
    ids=["one-page", "two-pages", "two-pages-and-margin", "six-pages"],
)
def test_strip_bands_follow_pairs_of_a4_pages(height: int, expected: list[tuple[int, int]]) -> None:
    assert ocr.strip_bands(WIDTH, height) == expected


@pytest.mark.parametrize(
    ("width", "height"),
    [(1654, 37424), (1654, 4885), (4960, 70160), (300, 30000), (9000, 11000), (32767, 30000), (1, 5000)],
)
def test_strip_bands_cover_image_with_overlap_and_fit_tesseract(width: int, height: int) -> None:
    bands = ocr.strip_bands(width, height)
    margin = max(100, width // 16)

    assert bands[0][0] == 0
    assert bands[-1][1] == height
    for (_, upper_end), (lower_start, _) in pairwise(bands):
        assert upper_end - lower_start == 2 * margin
    for top, bottom in bands:
        assert 2 * margin < bottom - top <= ocr.TESSERACT_MAX_SIDE
        assert (bottom - top) * width <= 40_000_000 + 2 * margin * width or bottom - top <= 6 * margin
    assert len(bands) > 1


class Page:
    """Model wysokiego skanu: wiersze tekstu z położeniem. Udaje Tesseracta na pasach tego skanu."""

    def __init__(self, height: int, lines: list[tuple[int, int, str]], *, jitter: int = 0, inset: int = 0) -> None:
        self.height = height
        self.lines = lines
        # Ten sam wiersz Tesseract widzi w dwóch pasach z ramką przesuniętą o parę pikseli,
        # a ramka uciętego wiersza nie zawsze dotyka krawędzi pasa.
        self.jitter = jitter
        self.inset = inset
        self.calls: list[tuple[int, int]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(images, "size", lambda data: (WIDTH, self.height))
        monkeypatch.setattr(images, "can_cut", lambda: True)
        monkeypatch.setattr(images, "strips", lambda data, bands: [f"{top}:{bottom}".encode() for top, bottom in bands])
        monkeypatch.setattr(subprocess, "run", self.tesseract)

    def tesseract(self, command: list[str], *, input: bytes, **options: object) -> subprocess.CompletedProcess:
        assert command[-1] == "tsv"
        top, bottom = map(int, input.decode().split(":"))
        self.calls.append((top, bottom))
        rows = [TSV_HEADER, f"1\t1\t0\t0\t0\t0\t0\t0\t{WIDTH}\t{bottom - top}\t-1\t"]
        number = 0
        for line_top, line_bottom, text in self.lines:
            if line_bottom <= top or line_top >= bottom:
                continue
            number += 1
            whole = top <= line_top and line_bottom <= bottom
            # Wiersz ucięty krawędzią pasa Tesseract czyta błędnie i daje mu przyciętą ramkę.
            words = text.split() if whole else ["#ucięty#"]
            shift = self.jitter if round(top / 4678) % 2 == 0 else -self.jitter
            clipped_top = max(line_top + shift, top + (0 if whole else self.inset))
            clipped_bottom = min(line_bottom + shift, bottom - (0 if whole else self.inset))
            for index, word in enumerate(words, start=1):
                box = f"{100 * index}\t{clipped_top - top}\t90\t{clipped_bottom - clipped_top}"
                rows.append(f"5\t1\t1\t1\t{number}\t{index}\t{box}\t96.5\t{word}")
        return completed("\n".join(rows).encode())


def numbered_lines(height: int, pitch: int, line_height: int, offset: int = 0) -> list[tuple[int, int, str]]:
    return [(top, top + line_height, f"Wiersz {number} formularza") for number, top in enumerate(range(offset, height - line_height, pitch))]


@pytest.mark.parametrize(
    ("pitch", "line_height", "offset"),
    [(60, 34, 0), (60, 34, 17), (41, 40, 3), (120, 90, 55), (37, 30, 0), (2339, 60, 2300)],
    ids=["typical", "shifted", "dense", "headings", "small-print", "line-on-every-page-edge"],
)
def test_tall_scan_is_read_in_strips_without_lost_or_repeated_lines(
    monkeypatch: pytest.MonkeyPatch, pitch: int, line_height: int, offset: int
) -> None:
    # Skan z folderu 9: 16 kartek A4 jedna pod drugą, 37424 piksele. Tesseract przyjmuje najwyżej 32767.
    page = Page(37424, numbered_lines(37424, pitch, line_height, offset))
    page.install(monkeypatch)

    text = ocr.image_text(b"skan", "pol")

    assert text.split("\n") == [line for _, _, line in page.lines]
    assert sorted(page.calls) == ocr.strip_bands(WIDTH, 37424)
    assert len(page.calls) == 8


@pytest.mark.parametrize("offset", [0, 3], ids=["line-ends-at-middle", "line-centered-at-middle"])
def test_line_crossing_the_cut_without_any_gap_is_taken_once(monkeypatch: pytest.MonkeyPatch, offset: int) -> None:
    # Ramki wierszy stykają się, więc w zakładce nie ma wolnego odstępu: granicą jest jej środek.
    # Jedyne odstępy to te przy krawędziach pasów, obok uciętych wierszy: tam granica stanąć nie może.
    page = Page(10000, numbered_lines(10000, 50, 50, offset), inset=3)
    page.install(monkeypatch)

    assert ocr.image_text(b"skan", "pol").split("\n") == [line for _, _, line in page.lines]


def test_line_seen_with_shifted_box_in_both_strips_is_taken_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # Środek wiersza wypada dokładnie w połowie zakładki, a oba pasy widzą jego ramkę o 2 piksele
    # inaczej. Granica w połowie zakładki zgubiłaby wiersz; granica w odstępie między wierszami nie.
    page = Page(10000, numbered_lines(10000, 60, 34, offset=41), jitter=2)
    page.install(monkeypatch)
    assert (4661, 4695, "Wiersz 77 formularza") in page.lines

    assert ocr.image_text(b"skan", "pol").split("\n") == [line for _, _, line in page.lines]


@pytest.mark.parametrize("jitter", [1, -1, 2], ids=["shift-1", "shift-minus-1", "shift-2"])
@pytest.mark.parametrize("offset", range(50))
def test_touching_lines_seen_with_shifted_boxes_are_taken_once(monkeypatch: pytest.MonkeyPatch, offset: int, jitter: int) -> None:
    # Recenzja K2-FINAL, nr 4: bez wolnego odstępu w zakładce i z ramkami przesuniętymi o piksel
    # wiersz przy granicy trafiał do wyniku dwa razy albo wcale. Każde przesunięcie wierszy względem
    # pasów, bo błąd dotyczył tylko wierszy ze środkiem przy połowie zakładki.
    page = Page(10000, numbered_lines(10000, 50, 50, offset), jitter=jitter, inset=3)
    page.install(monkeypatch)

    assert ocr.image_text(b"skan", "pol").split("\n") == [line for _, _, line in page.lines]


def strip_tsv(offset: int, *lines: tuple[int, int, int, int, str]) -> str:
    """Tabela TSV jednego pasa; wiersz (góra, dół, lewa, prawa, tekst) w pikselach całego obrazu, jako jedno słowo."""
    rows = [TSV_HEADER]
    for number, (top, bottom, left, right, text) in enumerate(lines, start=1):
        rows.append(f"5\t1\t{number}\t1\t1\t1\t{left}\t{top - offset}\t{right - left}\t{bottom - top}\t95.0\t{text}")
    return "\n".join(rows)


BANDS = [(0, 4781), (4575, 9459)]


def merged(upper: list[tuple[int, int, int, int, str]], lower: list[tuple[int, int, int, int, str]]) -> list[str]:
    return ocr._merge([ocr._lines(strip_tsv(0, *upper), 0), ocr._lines(strip_tsv(4575, *lower), 4575)], BANDS).split("\n")


def test_column_missed_by_one_strip_is_kept_beside_line_seen_in_both() -> None:
    # Dwie kolumny w jednym wierszu zakładki, a dolny pas nie rozpoznał prawej. Kopie łączymy po ramce
    # w pionie i w poziomie, więc prawa kolumna nie znika razem z kopią lewej.
    upper = [(4700, 4740, 100, 700, "Imię i nazwisko"), (4701, 4741, 900, 1500, "PESEL")]
    lower = [(4699, 4739, 100, 700, "Imię i nazwisko"), (4800, 4840, 100, 700, "Adres")]

    assert sorted(merged(upper, lower)) == ["Adres", "Imię i nazwisko", "PESEL"]


def test_copy_farther_from_its_strip_edge_wins_and_truncated_fragment_without_copy_is_dropped() -> None:
    upper = [
        (4590, 4630, 100, 900, "Wiersz z góry zakładki"),
        (4700, 4740, 100, 900, "Wiersz z dołu zakładki"),
        (4600, 4640, 1000, 1500, "Tylko w górnym pasie"),
        # Ucięty wiersz, którego dolny pas nie rozpoznał: ramka dotyka krawędzi pasa.
        (4760, 4781, 1000, 1500, "#ucięty#"),
    ]
    lower = [
        (4575, 4631, 100, 900, "#ucięty u góry#"),
        (4701, 4741, 100, 900, "Wiersz z dołu zakładki (dolny pas)"),
        (4575, 4590, 1000, 1500, "#ucięty bez kopii#"),
    ]

    assert merged(upper, lower) == [
        "Wiersz z góry zakładki",
        "Tylko w górnym pasie",
        "Wiersz z dołu zakładki (dolny pas)",
    ]


ROWS_IN_OVERLAP = (
    # Pierwszy wiersz przecina górną krawędź dolnego pasa, ostatni dolną krawędź górnego.
    [(4560, 4583, 100, 1500, "L1"), (4600, 4623, 100, 1500, "L2"), (4640, 4663, 100, 1500, "L3")]
    + [(4700, 4723, 100, 1500, "L4"), (4765, 4781, 100, 1500, "#ucięty L5#")],
    [(4575, 4583, 100, 1500, "#ucięty L1#"), (4600, 4623, 100, 1500, "L2"), (4640, 4663, 100, 1500, "L3")]
    + [(4700, 4723, 100, 1500, "L4"), (4765, 4788, 100, 1500, "L5")],
)


@pytest.mark.parametrize(
    ("tall_upper", "tall_lower"),
    [
        ((4576, 4778, 1100, 1400, "~pieczęć~"), (4576, 4778, 1100, 1400, "~pieczęć~")),
        # Linia tabeli przez całą zakładkę: każdy pas widzi ją uciętą swoją krawędzią.
        ((4570, 4781, 800, 804, "|"), (4575, 4790, 800, 804, "|")),
    ],
    ids=["stamp", "table-rule"],
)
def test_tall_box_across_rows_does_not_join_them_into_one_copy(
    tall_upper: tuple[int, int, int, int, str], tall_lower: tuple[int, int, int, int, str]
) -> None:
    # Recenzja K2-FINAL po poprawkach, nr 1: ramka pieczęci albo linii tabeli pokrywa kilka wierszy
    # i oba strzępy przy krawędziach. Łączyła je w jedną grupę, więc znikał L5, a zostawał jego strzęp.
    upper, lower = ROWS_IN_OVERLAP

    assert sorted(merged([*upper, tall_upper], [*lower, tall_lower])) == sorted(["L1", "L2", "L3", "L4", "L5", tall_upper[4]])


def test_stamp_centred_on_a_line_is_not_its_copy() -> None:
    # Dolny pas nie rozpoznał wiersza pod pieczęcią. Pieczęć ma ten sam środek, ale jest sześć razy
    # wyższa: gdyby uchodziła za kopię wiersza, wiersz zniknąłby razem z górną kopią pieczęci.
    upper = [(4695, 4715, 100, 1500, "Wiersz pod pieczęcią"), (4640, 4770, 1100, 1400, "~pieczęć~")]
    lower = [(4641, 4771, 1100, 1400, "~pieczęć~")]

    assert sorted(merged(upper, lower)) == ["Wiersz pod pieczęcią", "~pieczęć~"]


@pytest.mark.parametrize("jitter", [0, 1], ids=["exact", "shift-1"])
@pytest.mark.parametrize("offset", range(0, 50, 5))
def test_skewed_lines_with_overlapping_boxes_are_taken_once(monkeypatch: pytest.MonkeyPatch, offset: int, jitter: int) -> None:
    # Krzywo zeskanowany wiersz ma ramkę wyższą niż odstęp między wierszami: sąsiednie ramki
    # pokrywają się na ponad połowę, a to nadal różne wiersze.
    page = Page(10000, numbered_lines(10000, 50, 124, offset), jitter=jitter)
    page.install(monkeypatch)

    assert ocr.image_text(b"skan", "pol").split("\n") == [line for _, _, line in page.lines]


@pytest.mark.parametrize("offset", [0, 4, 9, 13])
def test_dense_skewed_lines_shifted_between_strips_pair_with_own_copy(monkeypatch: pytest.MonkeyPatch, offset: int) -> None:
    # Ramka 43 pikseli co 15 pikseli i przesunięcie o 6 między pasami: środek sąsiedniego wiersza też
    # mieści się w progu ramki, więc kopię wybieramy po najbliższym środku, nie po samym progu.
    page = Page(10000, numbered_lines(10000, 15, 43, offset), jitter=3)
    page.install(monkeypatch)

    assert ocr.image_text(b"skan", "pol").split("\n") == [line for _, _, line in page.lines]


def test_line_split_in_one_strip_forms_one_group_with_its_copy() -> None:
    # Tesseract podzielił wiersz na dwa tylko w dolnym pasie: obie części należą do kopii z górnego.
    upper = [(4600, 4630, 100, 1500, "Imię i nazwisko PESEL")]
    lower = [(4601, 4631, 100, 700, "Imię i nazwisko"), (4601, 4631, 900, 1500, "PESEL")]

    assert merged(upper, lower) == ["Imię i nazwisko PESEL"]


def test_line_taller_than_overlap_cut_in_both_strips_keeps_one_copy() -> None:
    # Obie kopie dochodzą do krawędzi swojego pasa. Wiersz zostaje raz, choć tylko w części.
    upper = [(4560, 4781, 100, 900, "Nagłówek, górna część")]
    lower = [(4575, 4800, 100, 900, "Nagłówek, dolna część")]

    assert merged(upper, lower) == ["Nagłówek, górna część"]


def test_strip_that_fails_makes_whole_image_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    page = Page(14034, numbered_lines(14034, 60, 34))
    page.install(monkeypatch)

    def failing(command: list[str], *, input: bytes, **options: object) -> subprocess.CompletedProcess:
        if input.startswith(b"4575:"):
            raise subprocess.CalledProcessError(1, "tesseract")
        return page.tesseract(command, input=input, **options)

    monkeypatch.setattr(subprocess, "run", failing)

    # Tekst bez środkowego pasa wyglądałby na kompletny, a nim nie jest.
    assert ocr.image_text(b"skan", "pol") == ""


def test_tall_image_without_cutting_library_goes_whole_only_when_tesseract_accepts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Mock(return_value=completed(b"Wniosek"))
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr(images, "can_cut", lambda: False)

    assert ocr.image_text(jpeg(WIDTH, 14034), "pol") == "Wniosek"
    assert runner.call_args.args[0] == ["tesseract", "stdin", "stdout", "-l", "pol"]
    # Bez Leptoniki skanu z folderu 9 nie da się odczytać: to brak w środowisku API, nie wina pliku.
    with pytest.raises(SetupError) as exc_info:
        ocr.image_text(jpeg(WIDTH, 37424), "pol")
    assert "Leptonica" in exc_info.value.reason
    assert runner.call_count == 1


def test_embedded_image_smaller_than_a_text_line_is_not_worth_reading() -> None:
    assert ocr.worth_reading(200, 100) is True
    assert ocr.worth_reading(31, 5000) is False
    assert ocr.worth_reading(5000, 31) is False
    assert ocr.worth_reading(141, 141) is False
    assert ocr.worth_reading(142, 141) is True


def test_texts_keep_input_order_and_empty_text_for_unreadable_image(monkeypatch: pytest.MonkeyPatch) -> None:
    def tesseract(command: list[str], *, input: bytes, **options: object) -> subprocess.CompletedProcess:
        return completed(f"obraz {images.size(input)[1]}".encode())

    monkeypatch.setattr(subprocess, "run", tesseract)

    assert ocr.texts([png(40, 41), b"to nie obraz", png(40, 43), png(40, 42)], "pol") == ["obraz 41", "", "obraz 43", "obraz 42"]


@needs_ocr_engine
def test_real_cut_gives_gray_strips_with_requested_rows() -> None:
    # Obraz RGB, w którym każdy wiersz ma inną jasność: po niej widać, które wiersze trafiły do pasa.
    rows = b"".join(b"\x00" + bytes([row % 251]) * 3 * 300 for row in range(1000))
    source = png_file(300, 1000, 8, 2, zlib.compress(rows, 1))

    parts = images.strips(source, [(0, 400), (350, 700), (650, 1000)])

    for part, (top, bottom) in zip(parts, [(0, 400), (350, 700), (650, 1000)], strict=True):
        header, pixels, _ = png_pixels(part)
        assert header == (300, bottom - top, 8, 0)
        # Pierwszy bajt wiersza PNG to rodzaj filtra; drugi wiersz pasa zdradza filtr inny niż „brak”.
        first_row = _unfiltered_first_row(pixels, 300)
        assert set(first_row) == {top % 251}


@needs_ocr_engine
def test_real_cut_of_damaged_image_is_unreadable() -> None:
    with pytest.raises(ExtractionError, match=UNREADABLE):
        images.strips(png(300, 1000)[:60], [(0, 400)])


@needs_ocr_engine
def test_real_ocr_reads_tallest_coi_scan_with_words_from_first_and_last_page() -> None:
    scans = sorted(path for directory in MATERIALS.glob("9. *") for path in directory.glob("*.jpg"))
    if not scans:
        pytest.skip(f"brak skanu JPG z folderu 9 w {MATERIALS}")
    data = scans[0].read_bytes()
    assert images.size(data) == (1654, 37424)

    text = " ".join(ocr.image_text(data, "pol").casefold().split())

    assert "wniosek o przyznanie stypendium sportowego" in text
    assert "klauzula informacyjna" in text or "administratorem" in text
    assert len(text) > 10_000


def words(text: str) -> Counter:
    return Counter(word.casefold() for word in re.findall(r"[^\W\d_]{4,}", text))


@needs_ocr_engine
def test_real_ocr_of_scan_cut_through_text_lines_matches_whole_image(monkeypatch: pytest.MonkeyPatch) -> None:
    # Recenzja K2-FINAL, nr 4: w skanie z folderu 9 granice pasów wypadają w pustych marginesach, więc
    # tniemy go sami. Cztery kartki Tesseract przyjmie w całości, a każdy z dwóch pasów ma wielkość pasa
    # produkcyjnego. Obie krawędzie zakładki przecinają wiersze tekstu.
    scans = sorted(path for directory in MATERIALS.glob("9. *") for path in directory.glob("*.jpg"))
    if not scans:
        pytest.skip(f"brak skanu JPG z folderu 9 w {MATERIALS}")
    height = 4 * 2339
    crop = images.strips(scans[0].read_bytes(), [(0, height)])[0]
    whole = ocr._lines(ocr._run((crop, "pol", True)), 0)
    margin = ocr._margin(WIDTH)

    def cuts_text(row: int) -> bool:
        return any(line.top < row < line.bottom for line in whole)

    middles = [row for row in range(height // 2 - 1200, height // 2 + 1200) if cuts_text(row - margin) and cuts_text(row + margin)]
    middle = middles[len(middles) // 2]
    monkeypatch.setattr(ocr, "strip_bands", lambda width, height_: [(0, middle + margin), (middle - margin, height)])

    merged = words(ocr.image_text(crop, "pol"))

    expected = words("\n".join(line.text for line in whole))
    in_overlap = words("\n".join(line.text for line in whole if line.bottom > middle - margin and line.top < middle + margin))
    assert len(in_overlap) >= 5
    # Słowo wiersza z zakładki dwa razy to dubel, brak słowa to wiersz zgubiony albo wzięty ze strzępu.
    assert {word: merged[word] for word in in_overlap} == {word: expected[word] for word in in_overlap}
    assert sum((expected & merged).values()) >= 0.97 * sum(expected.values())
