# Memory Steward LIST

LIST (Local Input Speech Transcriber) is the optional speech-input extension for Memory Steward.

Implemented endpoints:

- `GET /healthz`
- `POST /v1/list/transcribe`
- `POST /v1/audio/transcriptions` (compatibility alias)
- `POST /v1/list/translate` currently returns HTTP 501

LIST accepts a completed audio upload and returns text. It does not receive chat context or memory payloads and does not submit messages automatically.
