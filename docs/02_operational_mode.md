# OPERATIONAL MODE
## Current Router Semantics
### Foundational Engineering Specification (Document 02 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 01 (Architecture)](01_overview.md) | [Next: Document 03 (Reference Memory)](03_reference.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Current Contract](#1-current-contract)
- [2. What Is Not Implemented](#2-what-is-not-implemented)
- [3. Compatibility Values](#3-compatibility-values)
- [4. Future Work](#4-future-work)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIAL
**Audience:** Maintainers, Router/Steward developers, operators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

The repository contains mode-aware selection behavior, but no active mode classifier or hysteresis engine.

[Back to top](#navigation)

---

## 1. Current Contract

`mode` is optional caller-supplied metadata on Router requests.

The Router currently uses it in two places:

1. Static memory: active rows with `mode='global'` are always selected; a caller-supplied mode can additionally select matching mode-conditioned rows.
2. Reference retrieval eligibility: canonical reference retrieval is enabled for `engineering`, `implementation`, and `formal_spec`.

If no mode is supplied, the static lane does not synthesize a mode. The current reference-lane eligibility check uses `engineering` as its fallback mode.

[Back to top](#navigation)

---

## 2. What Is Not Implemented

The current tree does not contain:

- Steward mode classification;
- intent classification for reference retrieval;
- temporal mode state;
- hysteresis/decay logic;
- automatic mode transitions;
- a runtime consumer for `FORCE_MODE`;
- a runtime consumer for `HYSTERESIS_WINDOW`.

MCP compatibility tools can persist `FORCE_MODE` and `HYSTERESIS_WINDOW` in `runtime_config`; until a consumer is implemented, these values do not change Router/Steward behavior.

[Back to top](#navigation)

---

## 3. Compatibility Values

The MCP stability module recognizes these names:

- `engineering`
- `implementation`
- `brainstorming`
- `formal_spec`
- `casual`

Recognition by the configuration tool does not imply that a classifier exists.

[Back to top](#navigation)

---

## 4. Future Work

A future classifier/hysteresis design MAY be implemented, but it must arrive with executable tests and a defined authority boundary before documentation can describe it as runtime behavior.

[Back to top](#navigation)

---

## 5. Closing Statement

Operational mode is currently caller-supplied Router metadata, not a Steward classification subsystem. Documentation and operator tooling MUST preserve that distinction until classifier/hysteresis behavior exists in executable code.

[Back to top](#navigation)

---

**END OF DOCUMENT 02**
