"""Lokalny OCR przez Tesseract: obrazy czytane równolegle, wysoki skan pasami.

Tesseract odrzuca obraz o boku ponad 32767 pikseli, a pamięć i czas rosną z liczbą pikseli.
Skan wyższy niż dwie kartki A4 dzielimy więc na pasy z zakładką. Wiersz niższy niż zakładka widać
w całości przynajmniej w jednym z dwóch pasów. Kopie tego samego wiersza z obu pasów rozpoznajemy
po ramkach, które nakładają się w pionie i w poziomie, i bierzemy kopię leżącą dalej od krawędzi
swojego pasa: tam Tesseract widział cały wiersz.
"""

import math
import os
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import pairwise

from app.errors import ExtractionError
from app.extract import images
from app.extract.common import SetupError

TESSERACT_MAX_SIDE = 32767
# Największy skan COI (folder 9) ma 61,9 mln pikseli. Zdekodowany PNG RGB to 4 bajty na piksel.
MAX_IMAGE_PIXELS = 100_000_000
# Obraz mniejszy niż wiersz tekstu (ikona, pole wyboru) nie niesie treści formularza.
MIN_SIDE = 32
MIN_PIXELS = 20_000
# Limit jednego wywołania Tesseracta, wyraźnie poniżej limitu procesu odczytu (sandbox, 60 s): obraz,
# którego nie da się odczytać w tym czasie, daje pusty tekst, zanim zginie odczyt całego dokumentu.
# Pas skanu z folderu 9 Tesseract czyta w kilka sekund.
OCR_TIMEOUT_SECONDS = 30
MAX_WORKERS = 4
# Część pasa bez zakładek ma najwyżej dwie kartki A4 o szerokości skanu i najwyżej _STRIP_PIXELS
# pikseli, ale nie mniej niż cztery marginesy. Zakładki dokładają do pasa dwa marginesy, więc szeroki
# skan ma w pasie więcej pikseli: przy szerokości 12000 do 58 mln.
_A4_RATIO = 297 / 210
_STRIP_PIXELS = 40_000_000
_TSV_COLUMNS = 12
_TSV_WORD = "5"
# Ramka uciętego wiersza kończy się przy krawędzi pasa, ale nie zawsze na niej. Wiersz bez kopii
# w drugim pasie, którego ramka zbliża się do krawędzi bardziej niż ta część zakładki (10 pikseli przy
# skanie A4 w 200 dpi), uznajemy za strzęp: cały wiersz tak blisko krawędzi drugi pas widzi w całości.
_EDGE_SHARE = 20
# Tak Tesseract 5 zgłasza brak pliku z danymi języka. Gdy wczyta inny z podanych języków, czyta
# dalej i kończy się kodem 0.
_LANGUAGE_FAILURE = b"Failed loading language"


@dataclass(frozen=True)
class _Line:
    """Wiersz tekstu z ramką w pikselach całego obrazu."""

    top: int
    bottom: int
    left: int
    right: int
    text: str


def worth_reading(width: int, height: int) -> bool:
    """Czy obraz osadzony w dokumencie jest dość duży, żeby zawierał tekst."""
    return min(width, height) >= MIN_SIDE and width * height >= MIN_PIXELS


def image_text(data: bytes, language: str) -> str:
    return texts([data], language)[0]


def texts(pictures: Sequence[bytes], language: str) -> list[str]:
    """Tekst każdego obrazu, w kolejności wejścia. Obraz, którego nie da się odczytać, daje pusty tekst.

    Brak programu Tesseract, danych języka albo biblioteki do cięcia wysokiego skanu to SetupError.
    """
    plans = [_plan(picture) for picture in pictures]
    jobs = [(part, language, len(plan) > 1) for plan in plans for part, _, _ in plan]
    with ThreadPoolExecutor(max_workers=_workers()) as pool:
        outputs = iter(list(pool.map(_run, jobs)))
    results = []
    for plan in plans:
        parts = [next(outputs) for _ in plan]
        if not plan or any(part is None for part in parts):
            results.append("")
        elif len(plan) == 1:
            results.append(parts[0].strip())
        else:
            bands = [(top, bottom) for _, top, bottom in plan]
            results.append(_merge([_lines(part, top) for part, (top, _) in zip(parts, bands, strict=True)], bands))
    return results


def strip_bands(width: int, height: int) -> list[tuple[int, int]]:
    """Pasy (górny wiersz, dolny wiersz) pokrywające cały obraz; sąsiednie nakładają się o `2 * margines`."""
    margin = _margin(width)
    body = max(min(2 * round(width * _A4_RATIO), _STRIP_PIXELS // width), 4 * margin)
    cuts = [0, *range(body, height - 2 * margin, body), height]
    return [
        (max(top - margin, 0), min(bottom + margin, height)) for top, bottom in pairwise(cuts)
    ]


def _margin(width: int) -> int:
    """Pół cala przy typowym skanie: wiersz tekstu do tej wysokości widać w całości w obu pasach."""
    return max(100, width // 16)


def _workers() -> int:
    return max(1, min(MAX_WORKERS, os.cpu_count() or 1))


def _plan(picture: bytes) -> list[tuple[bytes, int, int]]:
    """Części obrazu do odczytu: (bajty, górny wiersz, dolny wiersz). Pusta lista to obraz nie do odczytu."""
    dimensions = images.size(picture)
    if dimensions is None:
        return []
    width, height = dimensions
    if width * height > MAX_IMAGE_PIXELS or width > TESSERACT_MAX_SIDE:
        return []
    bands = strip_bands(width, height)
    if len(bands) > 1 and images.can_cut():
        try:
            return [(part, top, bottom) for part, (top, bottom) in zip(images.strips(picture, bands), bands, strict=True)]
        except ExtractionError:
            return []
    # Jeden pas wychodzi tylko dla obrazu niższego niż limit Tesseracta, więc tu brakuje Leptoniki.
    if height > TESSERACT_MAX_SIDE:
        raise SetupError(reason=f"brak biblioteki Leptonica do cięcia obrazu wyższego niż {TESSERACT_MAX_SIDE} pikseli")
    return [(picture, 0, height)]


def _run(job: tuple[bytes, str, bool]) -> str | None:
    """Wynik Tesseracta dla jednej części: tekst albo tabela TSV z położeniem słów; None po błędzie."""
    picture, language, positions = job
    command = ["tesseract", "stdin", "stdout", "-l", language, *(["tsv"] if positions else [])]
    try:
        result = subprocess.run(
            command,
            input=picture,
            capture_output=True,
            check=True,
            timeout=OCR_TIMEOUT_SECONDS,
            # Równoległość dają osobne procesy, więc każdy liczy na jednym wątku.
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    except subprocess.CalledProcessError as exc:
        _check_languages(exc.stderr, language)
        return None
    except subprocess.TimeoutExpired:
        return None
    # Brak programu albo prawa do jego uruchomienia to błąd wdrożenia, nie pliku użytkownika.
    except OSError as exc:
        raise SetupError(reason="nie można uruchomić programu Tesseract") from exc
    _check_languages(result.stderr, language)
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _check_languages(errors: bytes | None, language: str) -> None:
    """Brak danych języka to błąd wdrożenia (OCR_LANG albo obraz bez pakietu języka), nie pliku."""
    if errors and _LANGUAGE_FAILURE in errors:
        raise SetupError(reason=f"Tesseract nie wczytał danych języka z OCR_LANG={language!r}")


def _lines(tsv: str, offset: int) -> list[_Line]:
    """Wiersze tekstu z tabeli TSV Tesseracta, z ramką w pikselach całego obrazu."""
    words: dict[tuple[str, ...], list[tuple[int, int, int, int, str]]] = {}
    for row in tsv.splitlines():
        cells = row.split("\t", _TSV_COLUMNS - 1)
        if len(cells) < _TSV_COLUMNS or cells[0] != _TSV_WORD or not cells[11].strip():
            continue
        try:
            left, top, width, height = map(int, cells[6:10])
        except ValueError:
            continue
        box = (top + offset, top + height + offset, left, left + width, cells[11].strip())
        words.setdefault(tuple(cells[1:5]), []).append(box)
    return [
        _Line(
            min(word[0] for word in line),
            max(word[1] for word in line),
            min(word[2] for word in line),
            max(word[3] for word in line),
            " ".join(word[4] for word in line),
        )
        for line in words.values()
    ]


def _merge(strips: list[list[_Line]], bands: list[tuple[int, int]]) -> str:
    """Wiersze wszystkich pasów od góry; wiersz z zakładki bierzemy z jednego pasa."""
    dropped: list[set[int]] = [set() for _ in strips]
    for index, ((_, overlap_end), (overlap_start, _)) in enumerate(pairwise(bands)):
        edge = (overlap_end - overlap_start) // _EDGE_SHARE
        upper = {number: line for number, line in enumerate(strips[index]) if line.bottom > overlap_start}
        lower = {number: line for number, line in enumerate(strips[index + 1]) if line.top < overlap_end}
        for ups, lows in _copies(upper, lower):
            upper_room = overlap_end - max(upper[number].bottom for number in ups) if ups else -math.inf
            lower_room = min(lower[number].top for number in lows) - overlap_start if lows else -math.inf
            if upper_room >= lower_room:
                dropped[index + 1].update(lows)
                kept, room = (index, ups), upper_room
            else:
                dropped[index].update(ups)
                kept, room = (index + 1, lows), lower_room
            # Wiersz widziany tylko w jednym pasie, ucięty jego krawędzią: strzęp, którego drugi pas
            # nie rozpoznał jako tekst. Cały wiersz widziany tylko w jednym pasie zostaje.
            if not (ups and lows) and room <= edge:
                dropped[kept[0]].update(kept[1])
    return "\n".join(
        line.text
        for lines, gone in zip(strips, dropped, strict=True)
        for number, line in enumerate(lines)
        if number not in gone
    )


def _copies(upper: dict[int, _Line], lower: dict[int, _Line]) -> list[tuple[list[int], list[int]]]:
    """Grupy kopii jednego wiersza z zakładki: numery wierszy górnego i dolnego pasa.

    Każdy wiersz łączymy tylko z najbliższą pasującą kopią z drugiego pasa, a grupa to wiersze
    połączone tymi łączami. Gęste wiersze krzywego skanu nie łączą się więc łańcuchem, a wiersz,
    który Tesseract w jednym pasie podzielił na dwa, trafia do jednej grupy.
    """
    links = {(number, _closest(line, lower)) for number, line in upper.items()}
    links |= {(_closest(line, upper), number) for number, line in lower.items()}
    groups: list[tuple[list[int], list[int]]] = [([number], []) for number in upper]
    for number in lower:
        linked = [group for group in groups if any((other, number) in links for other in group[0])]
        groups = [group for group in groups if all(group is not other for other in linked)]
        groups.append(([other for group in linked for other in group[0]], [other for group in linked for other in group[1]] + [number]))
    return groups


def _closest(line: _Line, others: dict[int, _Line]) -> int | None:
    """Numer pasującej ramki z drugiego pasa o środku najbliżej środka `line`; None, gdy żadna nie pasuje."""
    matching = [number for number, other in others.items() if _same(line, other)]
    return min(matching, key=lambda number: abs(others[number].top + others[number].bottom - line.top - line.bottom), default=None)


def _same(first: _Line, second: _Line) -> bool:
    """Ramki tego samego wiersza: wysokości różne najwyżej dwukrotnie, środki w pionie nie dalej niż
    ćwierć niższej ramki, a w poziomie wspólna ponad połowa węższej.

    Sama wspólna część w pionie nie wystarcza: ramka pieczęci, linii tabeli albo krzywo zeskanowanego
    wiersza pokrywa kilka wierszy i łączyłaby je w jedną grupę z obu krawędzi zakładki.
    """
    low, high = sorted((first.bottom - first.top, second.bottom - second.top))
    # Podwojona odległość środków: suma górnej i dolnej krawędzi to dwa razy środek.
    centres = abs(first.top + first.bottom - second.top - second.bottom)
    horizontal = min(first.right, second.right) - max(first.left, second.left)
    narrower = min(first.right - first.left, second.right - second.left)
    return high <= 2 * low and 2 * centres <= low and 2 * horizontal > narrower
