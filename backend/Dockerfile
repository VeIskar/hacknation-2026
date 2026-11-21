# API (Treść pkt 5): jawna wersja obrazu, użytkownik bez roota, tylko port 8000.
# Kod należy do roota i jest tylko do odczytu dla `app`. Pliki z żądań żyją w pamięci (files.py),
# a docker-compose.yml montuje system plików tylko do odczytu, z /tmp w pamięci (tmpfs).
FROM docker.io/library/python:3.14.10-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OCR skanów (K2): tesseract 5 i dane języka polskiego, Apache-2.0 (DECISIONS.md, M1.3).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-pol \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin app

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

# Liczbowo, żeby Kubernetes z runAsNonRoot mógł to sprawdzić bez /etc/passwd.
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
