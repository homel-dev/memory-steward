FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml .
COPY src/ src/

# Install dependencies AND the package itself
RUN pip install --no-cache-dir .

# Pre-download the model (optional optimization, keeps it baked in image)
# This prevents downloading on every container start if using the default model
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

EXPOSE 8000

CMD ["python", "-m", "embeddings.server"]
