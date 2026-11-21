# Lokalny model (SPEC „Model”, Treść pkt 5): jawna wersja obrazu i użytkownik bez roota.
# Wersja 0.40.15 to ta, na której K1 mierzył qwen3.5:4b (DECISIONS.md, K1). Ollama: MIT.
# Modele leżą w wolumenie `ollama-models` (docker-compose.yml), montowanym w /home/ollama/.ollama.
FROM docker.io/ollama/ollama:0.40.15

# Katalog istnieje w obrazie z właścicielem `ollama`, więc nowy wolumen dostaje tego właściciela.
RUN groupadd --system --gid 10002 ollama \
    && useradd --system --uid 10002 --gid ollama --create-home --home-dir /home/ollama \
       --shell /usr/sbin/nologin ollama \
    && mkdir -p /home/ollama/.ollama/models \
    && chown -R 10002:10002 /home/ollama

ENV HOME=/home/ollama \
    OLLAMA_MODELS=/home/ollama/.ollama/models \
    OLLAMA_HOST=0.0.0.0:11434

USER 10002:10002
EXPOSE 11434
