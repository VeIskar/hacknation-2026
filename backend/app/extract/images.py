"""Wymiary obrazu z nagłówka pliku oraz cięcie wysokiego skanu na pasy.

Wymiary czytamy sami, przed dekodowaniem, żeby limit pikseli zadziałał, zanim powstanie bitmapa.
Pasy tnie Leptonica (BSD-2-Clause) wołana przez ctypes: ta sama biblioteka, której używa Tesseract,
więc jest w każdym środowisku z OCR i nie jest nową zależnością.
"""

import ctypes
import ctypes.util
import struct
from collections.abc import Sequence
from functools import cache

from app.extract.common import unreadable

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_START = b"\xff\xd8"
_TIFF_ORDERS = {b"II*\x00": "<", b"MM\x00*": ">"}
_TIFF_WIDTH, _TIFF_HEIGHT = 256, 257
_TIFF_SHORT, _TIFF_LONG = 3, 4
# Znaczniki SOF0–SOF15 niosą wymiary; DHT (C4), JPG (C8) i DAC (CC) mają te same górne bity.
_JPEG_FRAME_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# Znaczniki bez długości: TEM oraz RST0–RST7, SOI, EOI.
_JPEG_BARE_MARKERS = frozenset({0x01, *range(0xD0, 0xDA)})
_LIBRARY_NAMES = ("libleptonica.so.6", "liblept.so.5")
_IFF_PNG = 3
_SEVERITY_NONE = 6
# L_JPEG_READ_LUMINANCE: dekoder JPEG oddaje od razu 8 bitów na piksel zamiast 32.
_JPEG_LUMINANCE = 1
_RGB_DEPTH = 32


def size(data: bytes) -> tuple[int, int] | None:
    """Szerokość i wysokość PNG, JPEG albo TIFF z nagłówka; None dla innego albo uszkodzonego pliku."""
    try:
        if data.startswith(_PNG_SIGNATURE):
            return _png_size(data)
        if data.startswith(_JPEG_START):
            return _jpeg_size(data)
        if data[:4] in _TIFF_ORDERS:
            return _tiff_size(data, _TIFF_ORDERS[data[:4]])
    except (struct.error, IndexError):
        pass
    return None


def _png_size(data: bytes) -> tuple[int, int] | None:
    length, kind, width, height = struct.unpack_from(">I4sII", data, len(_PNG_SIGNATURE))
    return (width, height) if kind == b"IHDR" and length == 13 and width and height else None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    position = len(_JPEG_START)
    while True:
        if data[position] != 0xFF:
            return None
        marker = data[position + 1]
        if marker == 0xFF:  # bajty wypełnienia przed znacznikiem
            position += 1
        elif marker in _JPEG_BARE_MARKERS:
            position += 2
        elif marker in _JPEG_FRAME_MARKERS:
            height, width = struct.unpack_from(">HH", data, position + 5)
            return (width, height) if width and height else None
        else:
            (length,) = struct.unpack_from(">H", data, position + 2)
            position += 2 + length


def _tiff_size(data: bytes, order: str) -> tuple[int, int] | None:
    """Wymiary z pierwszego katalogu TIFF. Taki plik powstaje z obrazu faksowego w PDF."""
    (directory,) = struct.unpack_from(f"{order}I", data, 4)
    (count,) = struct.unpack_from(f"{order}H", data, directory)
    found = {}
    for index in range(count):
        tag, kind = struct.unpack_from(f"{order}HH", data, directory + 2 + 12 * index)
        if tag in (_TIFF_WIDTH, _TIFF_HEIGHT) and kind in (_TIFF_SHORT, _TIFF_LONG):
            code = "H" if kind == _TIFF_SHORT else "I"
            (found[tag],) = struct.unpack_from(f"{order}{code}", data, directory + 2 + 12 * index + 8)
    width, height = found.get(_TIFF_WIDTH), found.get(_TIFF_HEIGHT)
    return (width, height) if width and height else None


@cache
def _library() -> ctypes.CDLL | None:
    names = [ctypes.util.find_library("leptonica"), ctypes.util.find_library("lept"), *_LIBRARY_NAMES]
    for name in filter(None, names):
        try:
            library = ctypes.CDLL(name)
        except OSError:
            continue
        _declare(library)
        library.setMsgSeverity(_SEVERITY_NONE)
        return library
    return None


def _declare(library: ctypes.CDLL) -> None:
    pointer, integer, size_t = ctypes.c_void_p, ctypes.c_int32, ctypes.c_size_t
    signatures = {
        "setMsgSeverity": (integer, [integer]),
        "pixReadMem": (pointer, [ctypes.c_char_p, size_t]),
        "pixReadMemJpeg": (pointer, [ctypes.c_char_p, size_t, integer, integer, ctypes.POINTER(integer), integer]),
        "pixGetDepth": (integer, [pointer]),
        "pixGetWidth": (integer, [pointer]),
        "pixGetHeight": (integer, [pointer]),
        "pixConvertRGBToLuminance": (pointer, [pointer]),
        "boxCreate": (pointer, [integer] * 4),
        "pixClipRectangle": (pointer, [pointer, pointer, pointer]),
        "pixWriteMem": (integer, [ctypes.POINTER(pointer), ctypes.POINTER(size_t), pointer, integer]),
        "pixDestroy": (None, [ctypes.POINTER(pointer)]),
        "boxDestroy": (None, [ctypes.POINTER(pointer)]),
        "lept_free": (None, [pointer]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(library, name)
        function.restype = result
        function.argtypes = arguments


def can_cut() -> bool:
    return _library() is not None


def strips(data: bytes, bands: Sequence[tuple[int, int]]) -> list[bytes]:
    """Pasy obrazu jako PNG w skali szarości; `bands` to pary (górny wiersz, dolny wiersz) w pikselach.

    Obraz jest dekodowany raz. W pamięci są naraz cała bitmapa i jeden pas.
    """
    library = _library()
    if library is None:
        raise unreadable()
    image = _gray(library, _decode(library, data))
    try:
        width = library.pixGetWidth(image)
        return [_strip(library, image, width, top, bottom) for top, bottom in bands]
    finally:
        library.pixDestroy(ctypes.byref(image))


def _decode(library: ctypes.CDLL, data: bytes) -> ctypes.c_void_p:
    if data.startswith(_JPEG_START):
        warnings = ctypes.c_int32()
        handle = library.pixReadMemJpeg(data, len(data), 0, 1, ctypes.byref(warnings), _JPEG_LUMINANCE)
    else:
        handle = library.pixReadMem(data, len(data))
    if not handle:
        raise unreadable()
    return ctypes.c_void_p(handle)


def _gray(library: ctypes.CDLL, image: ctypes.c_void_p) -> ctypes.c_void_p:
    """Obraz RGB jako 8 bitów na piksel: cztery razy mniej pamięci w pasach i w Tesserakcie."""
    if library.pixGetDepth(image) != _RGB_DEPTH:
        return image
    try:
        handle = library.pixConvertRGBToLuminance(image)
    finally:
        library.pixDestroy(ctypes.byref(image))
    if not handle:
        raise unreadable()
    return ctypes.c_void_p(handle)


def _strip(library: ctypes.CDLL, image: ctypes.c_void_p, width: int, top: int, bottom: int) -> bytes:
    box = ctypes.c_void_p(library.boxCreate(0, top, width, bottom - top))
    part = ctypes.c_void_p(library.pixClipRectangle(image, box, None))
    library.boxDestroy(ctypes.byref(box))
    if not part:
        raise unreadable()
    encoded, length = ctypes.c_void_p(), ctypes.c_size_t()
    try:
        if library.pixWriteMem(ctypes.byref(encoded), ctypes.byref(length), part, _IFF_PNG) or not encoded:
            raise unreadable()
        return ctypes.string_at(encoded, length.value)
    finally:
        library.lept_free(encoded)
        library.pixDestroy(ctypes.byref(part))
