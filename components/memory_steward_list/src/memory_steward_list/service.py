"""
Service layer for Whisper inference.
Handles model loading and audio processing.
"""

import logging
from faster_whisper import WhisperModel
from memory_steward_list.config import WHISPER_MODEL_SIZE, DEVICE, COMPUTE_TYPE

log = logging.getLogger("memory-steward-list.service")

class TranscriptionService:
    _model = None

    @classmethod
    def get_model(cls):
        """Lazy load the Whisper model as a singleton."""
        if cls._model is None:
            log.info(f"Loading Whisper model: size={WHISPER_MODEL_SIZE} device={DEVICE} compute={COMPUTE_TYPE}")
            try:
                cls._model = WhisperModel(
                    WHISPER_MODEL_SIZE, 
                    device=DEVICE, 
                    compute_type=COMPUTE_TYPE
                )
                log.info("Whisper model loaded successfully.")
            except Exception as e:
                log.critical(f"Failed to load Whisper model: {e}")
                raise e
        return cls._model

    @classmethod
    def transcribe(cls, file_obj) -> str:
        """
        Transcribes a file-like object (audio) to text.
        Returns combined text of all segments.
        """
        model = cls.get_model()
        
        # faster-whisper accepts a file-like object directly.
        # beam_size=5 is a good default for accuracy.
        segments, info = model.transcribe(file_obj, beam_size=5)
        
        # 'segments' is a generator. We must iterate to consume and generate text.
        text_segments = []
        for segment in segments:
            text_segments.append(segment.text)
        
        full_text = " ".join(text_segments).strip()
        return full_text, info.duration

