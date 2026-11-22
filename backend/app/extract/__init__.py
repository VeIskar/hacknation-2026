"""Odczyt treści pliku formularza: `extract(data, ext)` (DELEGACJA.md, rozdz. 2.2).

Czytniki formatów są w `readers.py` i modułach obok. `extract` uruchamia je w osobnym procesie
z limitami zasobów (`sandbox.py`), bo plik pochodzi od użytkownika.
"""

from app.config import get_settings
from app.extract import sandbox
from app.models import ExtractedDocument, SourceFormat


def extract(data: bytes, ext: str) -> ExtractedDocument:
    reading = sandbox.read(data, ext, get_settings().ocr_lang)
    return ExtractedDocument(
        source_format=SourceFormat(ext), text=reading.text, ocr_used=reading.ocr_used, warnings=reading.warnings
    )
