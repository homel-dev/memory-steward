"""
Static memory cache logic for operator plane (doc 7).
Supports refresh, eviction, and thread-safe access.
"""

import threading
import time
from typing import Any, Dict, List, Optional
from memory_steward_mcp.config import QDRANT_URL, QDRANT_COLLECTION, STATIC_MEMORY_REFRESH_SECONDS
import qdrant_client

qdrant = qdrant_client.QdrantClient(QDRANT_URL, timeout=5)

class StaticMemoryCacheManager:
    _static_global: Optional[List[Dict[str, Any]]] = None
    _static_mode: Dict[str, List[Dict[str, Any]]] = {}
    _lock = threading.Lock()
    _last_refresh: float = 0

    @classmethod
    def refresh(cls):
        """Refresh the static memory cache from Qdrant."""
        with cls._lock:
            cls._static_global = cls._load_static_memory("static_global")
            cls._static_mode = {}
            for mode in ["engineering", "casual"]:
                cls._static_mode[mode] = cls._load_static_memory("static_mode_conditioned", mode)
            cls._last_refresh = time.time()

    @classmethod
    def _load_static_memory(cls, memory_type: str, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        payload_filter = [
            FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
        ]
        if mode:
            payload_filter.append(FieldCondition(key="mode", match=MatchValue(value=mode)))
        filt = Filter(must=payload_filter)
        res = qdrant.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=filt,
            limit=1024
        )
        return [point.payload for point in res[0]]

    @classmethod
    def get_static_global(cls) -> List[Dict[str, Any]]:
        """Get current static global memory, refreshing if expired."""
        with cls._lock:
            if cls._static_global is None or time.time() - cls._last_refresh > STATIC_MEMORY_REFRESH_SECONDS:
                cls.refresh()
            return list(cls._static_global or [])

    @classmethod
    def get_static_mode_conditioned(cls, mode: str) -> List[Dict[str, Any]]:
        """Get static mode-conditioned memory for a given mode."""
        with cls._lock:
            if (mode not in cls._static_mode or
                time.time() - cls._last_refresh > STATIC_MEMORY_REFRESH_SECONDS):
                cls.refresh()
            return list(cls._static_mode.get(mode, []))

    @classmethod
    def evict_cache(cls):
        """Evict all static memory caches (global and mode-conditioned)."""
        with cls._lock:
            cls._static_global = None
            cls._static_mode = {}
            cls._last_refresh = 0

