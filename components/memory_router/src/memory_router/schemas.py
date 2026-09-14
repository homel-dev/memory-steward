from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


REFERENCE_FILTER_FIELDS: Dict[str, str] = {
    "product": "product",
    "version": "version",
    "scope": "scope",
    "provider": "provider",
    "source": "source",
}


def _validate_reference_filters(value: dict[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    unknown = sorted(set(value) - set(REFERENCE_FILTER_FIELDS))
    if unknown:
        raise ValueError(f"unsupported reference filter(s): {', '.join(unknown)}")
    return value


class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

    @property
    def text_content(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return " ".join(
            item.get("text", "")
            for item in self.content
            if item.get("type") == "text"
        )


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    stream: Optional[bool] = False
    mode: Optional[str] = None


class ArtifactSelector(BaseModel):
    artifact_type: str = Field(..., min_length=1, max_length=128)
    repository: Optional[str] = Field(default=None, max_length=1024)
    revision: Optional[str] = Field(default=None, max_length=256)
    schema_version: Optional[str] = Field(default=None, max_length=64)
    producer_type: Optional[str] = Field(default=None, max_length=32)
    content_hash: Optional[str] = Field(default=None, max_length=64)


class ContextRetrieveRequest(BaseModel):
    query: Optional[str] = Field(default=None, min_length=1)
    mode: Optional[str] = None
    model: Optional[str] = None
    recent_messages: List[ChatMessage] = Field(default_factory=list)
    artifact_selectors: List[ArtifactSelector] = Field(default_factory=list, max_length=32)
    reference_filters: dict[str, str] | None = None

    @field_validator("reference_filters")
    @classmethod
    def validate_reference_filters(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        return _validate_reference_filters(value)


class ReferenceSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    reference_filters: dict[str, str] | None = None
    limit: int = Field(default=8, ge=1, le=50)

    @field_validator("reference_filters")
    @classmethod
    def validate_reference_filters(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        return _validate_reference_filters(value)


@dataclass
class Candidate:
    id: str
    content: str
    vector: List[float]
    metadata: Dict[str, Any]
    token_count: int = 0
    score: Optional[float] = None
