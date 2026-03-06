"""
Telemetry alignment for LIST.
Implements structured logging to satisfy Document 06 (Diagnostics Plane).
"""

import logging
import json
import time
from typing import Optional

# Configure root logger to output JSON-friendly format if needed.
# For now, we use a standard logger but format the message as structured KV pairs.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
log = logging.getLogger("memory-steward-list")

def record_transcription(
    duration_ms: int,
    audio_duration_sec: float,
    model: str,
    status: str,
    error: Optional[str] = None
):
    """
    Emit a structured log event for the Diagnostics Plane (Log Aggregation).
    """
    payload = {
        "event": "transcription_complete",
        "duration_ms": duration_ms,
        "audio_duration_sec": round(audio_duration_sec, 2),
        "model": model,
        "status": status,
        "error": error
    }
    # Doc 06: Logs are the diagnostics plane for non-memory-mutating components.
    if status == "ok":
        log.info(json.dumps(payload))
    else:
        log.error(json.dumps(payload))

