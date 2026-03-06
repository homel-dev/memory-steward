import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastembed import TextEmbedding

MODEL_NAME = os.environ.get("MODEL_NAME", "BAAI/bge-small-en-v1.5")

app = FastAPI(title="homel-embeddings", version="0.1")
embedder = TextEmbedding(model_name=MODEL_NAME)

class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: bool = True

@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL_NAME}

@app.post("/embed")
def embed(req: EmbedRequest):
    if not req.texts:
        raise HTTPException(status_code=400, detail="texts is empty")
    vectors = []
    dim: Optional[int] = None
    for vec in embedder.embed(req.texts):
        arr = vec.tolist()
        if dim is None:
            dim = len(arr)
        vectors.append(arr)
    return {"model": MODEL_NAME, "dim": int(dim or 0), "vectors": vectors}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("embeddings.server:app", host="0.0.0.0", port=8000, reload=False)
