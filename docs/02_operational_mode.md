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

## 5. Exact Current Decision Path

The current implementation has no mode-classification call in Router or Steward. The mode path is therefore deterministic and caller-driven:

~~~text
caller supplies mode? ---- no ----> req.mode = null
       |                              |
      yes                             +-> static loader selects global rules only
       |                              +-> reference lane uses engineering fallback eligibility
       v
req.mode = exact string
       |
       +-> static loader may select exact static_mode_conditioned rows
       +-> reference lane checks membership in {engineering, implementation, formal_spec}
       +-> telemetry records decided_mode=req.mode
~~~

The word `decided_mode` in telemetry is a historical/schema name; it does not imply the current Router classified the request.

## 6. Router Effects of `mode`

| Area | When mode is absent | When mode is supplied |
| --- | --- | --- |
| Static global memory | Included when active | Included when active |
| Static mode-conditioned memory | Not selected | Exact matching mode may be selected |
| Dynamic memory | Unaffected by mode at the schema boundary | Unaffected by mode at the schema boundary |
| Reference-memory eligibility | Fallback eligibility mode is `engineering` | Enabled only for engineering/implementation/formal_spec when global reference retrieval is enabled |
| Builder model | No mode-specific model switch in current code | No mode-specific model switch in current code |
| Steward admission | No classifier invocation | Mode is not an admission-policy engine |
| Telemetry | `decided_mode` null | Records caller value |

## 7. Compatibility Configuration

`config_force_mode` and `config_set_hysteresis` remain MCP tools so existing operator workflows and stored configuration do not break abruptly. Their persistence does **not** make them active policy.

| Key/tool | Can be stored? | Current consumer | Runtime effect today |
| --- | --- | --- | --- |
| FORCE_MODE / config_force_mode | Yes | None in Router/Steward | None |
| HYSTERESIS_WINDOW / config_set_hysteresis | Yes | None in mode engine | None |
| MAX_CONTEXT_TOKENS / config_set_budget | Yes | Router effective_max_context_tokens() | Changes retrieval context budget after cache refresh |

This distinction is important: operator visibility of a key is not evidence of active behavior.

## 8. Canonical Mode Vocabulary

The historical design vocabulary remains useful for callers that want explicit posture tags:

- `engineering`
- `implementation`
- `brainstorming`
- `formal_spec`
- `casual`

Only three values currently affect **reference-memory eligibility**: `engineering`, `implementation`, and `formal_spec`. Other values may still be meaningful to caller-side logic or exact static-memory rows but do not activate a hidden classifier.

## 9. Safe Defaults and Failure Semantics

The safe current behavior is intentionally conservative:

- no inferred mode means no exact mode-conditioned static rule selection;
- reference eligibility falls back to `engineering` only inside the reference-lane eligibility check;
- invalid/free-form mode strings are not silently normalized into another mode;
- absence of a mode classifier is documented instead of being emulated by heuristics;
- persisted compatibility keys are shown as inactive rather than misrepresented as enforcement.

## 10. What Would Be Required for a Real Mode Engine

A future implementation MUST NOT be documented as implemented until code and tests provide all of the following:

1. an explicit classifier input contract;
2. a bounded output vocabulary;
3. deterministic fallback behavior;
4. transition/hysteresis state ownership;
5. concurrency semantics for simultaneous requests;
6. telemetry distinguishing proposed vs applied mode;
7. failure behavior when classifier inference fails;
8. tests for stable transitions and forced overrides;
9. a documented interaction with static mode-conditioned rules;
10. a documented interaction with reference eligibility;
11. a security analysis for prompt-controlled mode manipulation.

## 11. Recommended Caller Contract

Callers that require a particular posture SHOULD send it explicitly in `mode`. Callers that do not require posture-specific static rules SHOULD omit the field rather than guessing. Agent workflows SHOULD treat mode as an input to retrieval policy, not as a product/topic classifier.

Example structured retrieval request:

~~~json
{
  "query": "How does KiCad encode hierarchical labels?",
  "mode": "engineering",
  "reference_filters": {
    "product": "kicad",
    "version": "9.0"
  }
}
~~~

The product/version information belongs in `reference_filters`, not in `mode`.

## 12. Regression Checklist

Mode-related changes require tests proving at minimum:

- no-mode requests do not gain mode-conditioned static rows;
- exact supplied modes select only matching static rows;
- reference eligibility remains bounded to the implemented set;
- `reference_filters` are orthogonal to mode;
- compatibility keys do not accidentally become active through an unrelated refactor;
- telemetry records the input mode without claiming classifier provenance.

---

## 5. Closing Statement

Operational mode is currently caller-supplied Router metadata, not a Steward classification subsystem. Documentation and operator tooling MUST preserve that distinction until classifier/hysteresis behavior exists in executable code.

[Back to top](#navigation)

---

**END OF DOCUMENT 02**

## Appendix A. Mode Behavior Matrix

| Input mode | Static selection | Reference lane | Telemetry interpretation |
| --- | --- | --- | --- |
| <absent> | global only | eligible (engineering fallback) | recorded as input; no classifier provenance |
| engineering | global + exact `engineering` rows if present | eligible | recorded as input; no classifier provenance |
| implementation | global + exact `implementation` rows if present | eligible | recorded as input; no classifier provenance |
| formal_spec | global + exact `formal_spec` rows if present | eligible | recorded as input; no classifier provenance |
| brainstorming | global + exact `brainstorming` rows if present | not eligible | recorded as input; no classifier provenance |
| casual | global + exact `casual` rows if present | not eligible | recorded as input; no classifier provenance |
| custom-value | global + exact `custom-value` rows if present | not eligible | recorded as input; no classifier provenance |

## Appendix B. Operational Scenarios

### B.1 Engineering request with versioned reference corpus

A caller that wants engineering posture and KiCad 9 documentation should send both dimensions explicitly:

~~~json
{
  "query": "Explain the board setup rules used by this project",
  "mode": "engineering",
  "reference_filters": {"product": "kicad", "version": "9.0"}
}
~~~

`mode` controls posture-dependent policy/eligibility. `product` and `version` control corpus narrowing. Neither substitutes for the other.

### B.2 Casual request without mode

If the caller omits `mode`, the Router does not run a classifier. Global static rules remain eligible. No exact static mode row is selected. Reference eligibility uses the documented engineering fallback internally, which is not equivalent to rewriting the request mode field.

### B.3 Custom mode value

The request schema accepts a string rather than a closed enum. A custom value may match a custom static row, but it will not make Reference Memory eligible unless it is one of the implemented reference modes. This is why clients should not assume every mode string has identical cross-lane effects.

### B.4 Persisted FORCE_MODE

An operator may persist `FORCE_MODE` through compatibility tooling. Current Router code does not read it. A successful tool result proves persistence only; it does not prove request override behavior.

### B.5 HYSTERESIS_WINDOW

The checked-in runtime contract contains `HYSTERESIS_WINDOW=8`. No current classifier transition engine consumes it. Documentation and dashboards should label it compatibility/diagnostics rather than live control.

## Appendix C. Non-Implemented Classifier Design Constraints

If automatic mode inference is introduced later, the implementation should answer all of these before promotion to IMPLEMENTED:

1. classifier ownership: Router, Steward, or a dedicated service;
2. exact input: current message only, bounded history, or structured task metadata;
3. exact output vocabulary;
4. confidence representation;
5. low-confidence fallback;
6. forced-override precedence;
7. transition state persistence location;
8. hysteresis window definition (requests, turns, time, or score history);
9. concurrency behavior across simultaneous requests for one project/session;
10. cache invalidation semantics;
11. telemetry for proposed/applied/previous mode;
12. reference-lane interaction;
13. static-memory selection interaction;
14. timeout/error behavior;
15. model/provider replacement behavior;
16. replayability for incident analysis;
17. prompt-injection resistance;
18. tests proving no topic->mode conflation.

## Appendix D. Mode-Sensitive Regression Examples

| Case | Input | Expected observation |
| --- | --- | --- |
| No mode + global static | `mode=null` | global static can appear |
| No mode + mode-only static | `mode=null` | mode-only row excluded |
| Engineering + engineering static | `mode=engineering` | exact row eligible |
| Engineering + casual static | `mode=engineering` | casual row excluded |
| Brainstorming reference | `mode=brainstorming` | reference lane excluded |
| Formal spec reference | `mode=formal_spec` | reference lane eligible |
| Custom mode reference | `mode=custom-value` | reference lane excluded |
| Product filter without mode | no mode, product=kicad | engineering fallback may activate reference lane, exact product filter narrows corpus |
| FORCE_MODE persisted | runtime_config contains FORCE_MODE | no change unless code consumer is added |
| HYSTERESIS_WINDOW persisted | runtime_config contains HYSTERESIS_WINDOW | no transition behavior |

## Appendix E. Documentation Language Rules for Modes

Use **"caller-supplied mode"** for the current request field. Do not say "the Steward classified the request" or "the Router chose engineering" unless a future implementation actually does so. Use **"reference eligibility fallback"** for the no-mode engineering behavior, because the request mode remains absent.
