import os
from threading import BoundedSemaphore
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
from pydantic import BaseModel

MODEL_NAME = os.environ.get("MODEL_NAME", "BAAI/bge-small-en-v1.5")
EMBEDDING_THREADS = int(os.environ.get("EMBEDDING_THREADS", "4"))
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "16"))
EMBEDDING_MAX_TEXTS = int(os.environ.get("EMBEDDING_MAX_TEXTS", "64"))
EMBEDDING_CONCURRENCY = int(os.environ.get("EMBEDDING_CONCURRENCY", "1"))

if EMBEDDING_THREADS < 1:
    raise RuntimeError("EMBEDDING_THREADS must be >= 1")
if EMBEDDING_BATCH_SIZE < 1:
    raise RuntimeError("EMBEDDING_BATCH_SIZE must be >= 1")
if EMBEDDING_MAX_TEXTS < 1:
    raise RuntimeError("EMBEDDING_MAX_TEXTS must be >= 1")
if EMBEDDING_CONCURRENCY < 1:
    raise RuntimeError("EMBEDDING_CONCURRENCY must be >= 1")

app = FastAPI(title="homel-embeddings", version="0.2")
embedder = TextEmbedding(model_name=MODEL_NAME, threads=EMBEDDING_THREADS)
_embed_slots = BoundedSemaphore(EMBEDDING_CONCURRENCY)


class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: bool = True


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "model": MODEL_NAME,
        "threads": EMBEDDING_THREADS,
        "batch_size": EMBEDDING_BATCH_SIZE,
        "max_texts": EMBEDDING_MAX_TEXTS,
        "concurrency": EMBEDDING_CONCURRENCY,
    }


@app.post("/embed")
def embed(req: EmbedRequest):
    if not req.texts:
        raise HTTPException(status_code=400, detail="texts is empty")
    if len(req.texts) > EMBEDDING_MAX_TEXTS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"too many texts: {len(req.texts)}; "
                f"maximum per request is {EMBEDDING_MAX_TEXTS}"
            ),
        )

    vectors = []
    dim: Optional[int] = None
    batch_size = min(EMBEDDING_BATCH_SIZE, len(req.texts))
    with _embed_slots:
        for vec in embedder.embed(req.texts, batch_size=batch_size, parallel=None):
            arr = vec.tolist()
            if dim is None:
                dim = len(arr)
            vectors.append(arr)
    return {"model": MODEL_NAME, "dim": int(dim or 0), "vectors": vectors}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("embeddings.server:app", host="0.0.0.0", port=8000, reload=False)
