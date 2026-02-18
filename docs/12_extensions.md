
# EXTENSIONS AND ADDITIONS
## Canonical Extension Specification Layer for Memory Steward
### Foundational Engineering Specification (Document 12 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 11 (Design Principles)](11_design_principles.md) | [Next: Whitepaper](WHITEPAPER.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Extension Model](#2-extension-model)
- [3. Extension Index](#3-extension-index)
- [4. Extension 12.1: Local Input Speech Transcriber (LIST)](#4-extension-121-local-input-speech-transcriber-list)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, extension implementers, operators
**Change policy:**
- Append-only
- No silent edits

This document defines the canonical mechanism by which additive capabilities are introduced without altering or contradicting Documents 00–11.

[Back to top](#navigation)

---

## 1. Purpose

This document defines the system’s **extension surface**.

An extension is a bounded subsystem or capability that:
- Adds functionality not present in the core specification set (Documents 00–11).
- MUST NOT alter core semantics, authority boundaries, or invariants.
- MUST be optional by design (the system MUST remain functional when the extension is absent).
- MUST integrate via explicit, versioned contracts.

Extensions documented here MUST:
- Declare responsibility boundaries.
- Declare external contracts.
- Declare runtime expectations.
- Declare telemetry expectations (aligned to Document 06 telemetry canon).

[Back to top](#navigation)

---

## 2. Extension Model

### 2.1 Extension Definition

An extension is an additive subsystem that MUST satisfy all of the following:
- **Additive:** Adds new capability without modifying core semantics.
- **Optional:** Can be disabled without breaking the system.
- **Bounded:** Has clear responsibility boundaries and non-goals.
- **Contracted:** Integrates only through explicit, versioned interfaces.

An extension MUST NOT:
- Bypass core control planes.
- Introduce implicit coupling (hidden dependencies).
- Redefine memory semantics or inference semantics.
- Expand the authority surface of existing components without explicit contract changes.

### 2.2 Document Structure Rules

All extensions MUST be specified within this document as numbered sections:
- New extensions MUST be appended as new top-level sections (e.g., `12.2`, `12.3`).
- Existing extensions MUST NOT be renumbered.
- Extensions MUST NOT create new foundational documents or reorder Documents 00–11.

[Back to top](#navigation)

---

## 3. Extension Index

- **12.1 Local Input Speech Transcriber (LIST)**

(Future extensions MUST be appended to this index.)

[Back to top](#navigation)

---

## 4. Extension 12.1: Local Input Speech Transcriber (LIST)

### 4.1 Purpose

Local Input Speech Transcriber (LIST) provides an input-plane capability that converts explicitly recorded user speech into plain UTF-8 text for insertion into a chat input field.

LIST exists to:
- Enable push-to-talk speech input with explicit start/stop control.
- Produce deterministic transcripts without streaming heuristics.
- Preserve strict separation from memory and inference pipelines.

### 4.2 Architectural Position

LIST sits strictly before message submission and outside memory and inference.

~~mermaid
graph TD
    User((User))
    UI[Chat UI]
    EXT[LIST Client Extension]
    LIST[memory-steward-list]
    LLM[LLM Pipeline]

    User -->|speech| UI
    UI -->|start/stop recording| EXT
    EXT -->|audio blob| LIST
    LIST -->|plain text| EXT
    EXT -->|insert text| UI
    UI -->|user sends| LLM
~~

> **Hard Invariant:** The LLM pipeline MUST NOT receive raw audio.
> **Hard Invariant:** LIST MUST NOT receive prompts, chat context, or memory payloads.

### 4.3 Responsibility Boundaries

LIST (service) MUST:
- Accept a complete audio recording as a single payload.
- Return plain UTF-8 text.
- Support transcription mode and translation mode.

LIST (service) MUST NOT:
- Stream partial transcripts.
- Perform silence-based end-of-speech detection.
- Submit messages to the LLM.
- Access memory, embeddings, or chat context.

The LIST client extension MUST:
- Provide explicit record and stop controls.
- Capture audio locally.
- Send the completed audio blob to LIST.
- Insert the returned text into the chat input field.
- Preserve the draft and allow user editing prior to send.

The LIST client extension MUST NOT:
- Auto-stop recording based on silence.
- Auto-send the transcript as a message.
- Overwrite existing draft text without deterministic insertion rules.

### 4.4 Interaction Model

Authoritative flow:
1. User explicitly starts recording.
2. User explicitly stops recording.
3. Client extension sends one audio blob to LIST.
4. LIST returns plain text.
5. Client extension inserts text into the input field.
6. User edits and sends manually.

Silence-based termination is forbidden.

### 4.5 External Contract Summary

LIST MUST expose a versioned HTTP interface:

- `POST /v1/list/transcribe`
- `POST /v1/list/translate`

Request requirements:
- `Content-Type: multipart/form-data`
- Field name: `file` (single audio file)

Response requirements (success):
- HTTP `200`
- JSON payload containing `text` (required)

Response requirements (error):
- Non-2xx status
- JSON payload containing `error` and `message`

### 4.6 Runtime Expectations

LIST runtime MUST be:
- Stateless
- Independently deployable
- Optional (absence MUST NOT break chat UI or LLM pipeline)

LIST runtime details (ports, health checks, payload limits, timeouts) MUST be defined in the Runtime Contract document.

### 4.7 Telemetry Expectations


LIST telemetry MUST align to Document 06 telemetry canon.

LIST MUST emit, at minimum:
- Request counts by mode (transcribe / translate)
- Error counts by error class
- Processing latency distributions

LIST SHOULD emit:
- Detected language distribution (when available)
- Audio duration distribution (when available)

LIST MUST NOT introduce a parallel telemetry schema.
LIST MUST use the canonical telemetry tables/steps defined in Document 06.

### 4.8 Non-Goals

LIST does not implement:
- Streaming ASR or incremental transcripts
- Speech synthesis (TTS)
- Speaker identification or diarization
- Content moderation or redaction
- Authentication / authorization (v1)

### 4.9 Failure Semantics

If LIST is unavailable or returns an error:
- The chat UI MUST remain functional.
- The client extension MUST preserve any existing draft input.
- The client extension MUST surface a user-visible error state.
- The client extension MUST NOT auto-retry without explicit user action.

[Back to top](#navigation)

---

## 5. Closing Statement

This document establishes a stable extension surface that preserves the authority and invariants of the foundational specification set (Documents 00–11). Extensions defined here are additive, optional, and contract-driven. LIST is the first canonical extension and defines the standard pattern for future additions.

---

**END OF DOCUMENT 12**
