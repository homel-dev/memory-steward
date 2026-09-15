# Memory Steward LIST

LIST (Local Input Speech Transcriber) is the optional speech-input extension for Memory Steward.

Implemented endpoints:

- `GET /healthz`
- `POST /v1/list/transcribe`
- `POST /v1/audio/transcriptions` (compatibility alias)
- `POST /v1/list/translate` currently returns HTTP 501

LIST accepts a completed audio upload and returns text. It does not receive chat context or memory payloads and does not submit messages automatically.

## Purpose

Optional Local Input Speech Transcriber (LIST). It converts uploaded audio to text using faster-whisper and remains isolated from memory databases and chat payloads.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | LIST liveness |
| POST | /v1/audio/transcriptions | OpenAI-style transcription alias |
| POST | /v1/list/transcribe | Canonical LIST transcription route |
| POST | /v1/list/translate | Reserved translation route |

## Runtime

The checked-in manifest defaults to CPU/int8 and mounts the shared Hugging Face cache PVC. GPU settings are commented examples, not the active default.

## Isolation invariant

LIST should not need Postgres/Qdrant credentials. A transcription extension must not silently become a memory authority.
