"""
LIST (Local Input Speech Transcriber) Extension Entrypoint.
Aligned with Document 12 Section 4.
"""

import time
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from memory_steward_list.service import TranscriptionService
from memory_steward_list.config import APP_VERSION, WHISPER_MODEL_SIZE
from memory_steward_list.telemetry import record_transcription

logging.getLogger("multipart").setLevel(logging.WARNING)
log = logging.getLogger("memory-steward-list.server")

app = FastAPI(
    title="Memory Steward LIST",
    version=APP_VERSION,
    description="Local Input Speech Transcriber Extension (Document 12.1)"
)

# CORS: Allow all for local integration flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    """Pre-load model on startup to ensure readiness."""
    try:
        TranscriptionService.get_model()
    except Exception:
        log.error("Model failed to load on startup. First request will retry.")

@app.get("/healthz")
def healthz():
    """Liveness probe."""
    return {"ok": True, "service": "memory-steward-list"}

@app.post("/v1/audio/transcriptions", status_code=200)
@app.post("/v1/list/transcribe", status_code=200)
async def transcribe(file: UploadFile = File(...)):
    """
    Contract: POST /v1/list/transcribe
    Input: multipart/form-data, field 'file'
    Output: JSON { 'text': string }
    """
    t0 = time.time()
    audio_duration = 0.0
    
    # Doc 12: "LIST MUST NOT receive prompts, chat context, or memory payloads."
    # We only process the raw audio blob.
    
    try:
        # We pass the file-like object directly to faster-whisper
        # This avoids reading large files entirely into RAM if possible,
        # though UploadFile implies SpooledTemporaryFile.
        text, audio_duration = TranscriptionService.transcribe(file.file)
        
        duration_ms = int((time.time() - t0) * 1000)
        
        record_transcription(
            duration_ms=duration_ms,
            audio_duration_sec=audio_duration,
            model=WHISPER_MODEL_SIZE,
            status="ok"
        )
        
        return {"text": text}

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        error_msg = str(e)
        
        log.error(f"Transcription failed: {error_msg}")
        
        record_transcription(
            duration_ms=duration_ms,
            audio_duration_sec=0.0, # Unknown if failed early
            model=WHISPER_MODEL_SIZE,
            status="error",
            error=error_msg
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {error_msg}"
        )

# Placeholder for future translation extension
@app.post("/v1/list/translate")
def translate_stub():
    raise HTTPException(status_code=501, detail="Translation not yet implemented")

if __name__ == "__main__":
    import uvicorn
    # Host 0.0.0.0 to allow container access
    uvicorn.run("memory_steward_list.server:app", host="0.0.0.0", port=8001, reload=False)

