# RUNTIME CONFIGURATION AND STABILITY
## Implemented Dynamic Configuration and Inactive Compatibility Keys
### Foundational Engineering Specification (Document 05 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 04 (Optimizations)](04_optimizations.md) | [Next: Document 06 (Telemetry)](06_telemetry.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Runtime Configuration Store](#1-runtime-configuration-store)
- [2. MCP Configuration Tools](#2-mcp-configuration-tools)
- [3. Not Implemented](#3-not-implemented)
- [4. Safe Evolution](#4-safe-evolution)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIAL
**Audience:** Maintainers and operators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. Runtime Configuration Store

`memory-steward-mcp` persists operator configuration in the Postgres `runtime_config` table.

The Router currently reloads and consumes these keys:

- `MAX_CONTEXT_TOKENS`
- `BUILDER_BASE_URL`
- `BUILDER_MODEL`

The Router caches runtime-config reads for a bounded TTL to avoid a database read on every request.

[Back to top](#navigation)

---

## 2. MCP Configuration Tools

Implemented tools include:

- `config_set_budget`
- `config_force_mode`
- `config_set_hysteresis`
- `config_show`

`config_set_budget` has an active Router consumer.

`config_force_mode` and `config_set_hysteresis` currently persist compatibility keys only. The Router/Steward do not consume `FORCE_MODE` or `HYSTERESIS_WINDOW`; therefore those two operations MUST NOT be represented as changing live request behavior.

[Back to top](#navigation)

---

## 3. Not Implemented

There is currently no:

- mode transition state machine;
- hysteresis window enforcement;
- decay function;
- mode-jitter telemetry;
- forced-mode application in Router or Steward.

[Back to top](#navigation)

---

## 4. Safe Evolution

If mode stabilization is implemented later, the change MUST add a runtime consumer, tests proving transition semantics, bounded configuration validation, and telemetry showing the applied mode source.

[Back to top](#navigation)

---

## 5. Closing Statement

The live stability surface is the subset of runtime configuration that current components actually consume. Persisted compatibility keys MUST NOT be documented as effective behavior until a runtime reader exists.

[Back to top](#navigation)

---

**END OF DOCUMENT 05**
