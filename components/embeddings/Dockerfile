FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
  coreutils \
  util-linux \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Pre-download the default model into the image.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

EXPOSE 8000

CMD ["sh", "-c", "exec ionice -c3 nice -n 19 python -m embeddings.server"]
