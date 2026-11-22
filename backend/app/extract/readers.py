"""Wybór czytnika po formacie pliku. Działa w procesie, który go woła: `extract` uruchamia go w piaskownicy."""

from app.extract import ocr
from app.extract.common import MAX_TEXT_CHARS, Reading, unreadable


def read_document(data: bytes, ext: str, *, language: str) -> Reading:
    """Tekst dokumentu w formacie `ext` (wynik `files.validate_upload`); `language` to język OCR."""
    # Biblioteki formatów (pypdf, olefile) ładujemy dopiero dla ich formatu: proces piaskownicy
    # startuje dla każdego pliku od nowa.
    if ext in ("jpg", "png"):
        reading = Reading(ocr.image_text(data, language), ocr_used=True)
    elif ext == "pdf":
        from app.extract import pdf

        reading = pdf.read(data, language)
    elif ext == "docx":
        from app.extract import docx

        reading = docx.read(data, language)
    elif ext == "doc":
        from app.extract.doc import doc_text

        reading = Reading(doc_text(data))
    elif ext in ("xlsx", "ods"):
        from app.extract import sheets

        reading = Reading(sheets.xlsx_text(data) if ext == "xlsx" else sheets.ods_text(data))
    else:
        raise unreadable()
    if not reading.text.strip() or len(reading.text) > MAX_TEXT_CHARS:
        raise unreadable()
    return reading
