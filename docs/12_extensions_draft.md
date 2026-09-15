# EXTENSIONS
## Agent Memory Bootstrap, Run-Derived Memory, and CodeGraph Capability Routing
### Foundational Engineering Specification (Document 12 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 11 (Design Principles)](11_design_principles.md) | [Next: Document 13 (Admission Control Proposal)](13_admission_control.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Extension Surface Overview](#1-extension-surface-overview)
- [2. Current Implemented Surface](#2-current-implemented-surface)
  - [2.1 LIST](#21-list)
  - [2.2 Agent Retrieval and Outcome Operations](#22-agent-retrieval-and-outcome-operations)
  - [2.3 Reference Memory Operations](#23-reference-memory-operations)
  - [2.4 `agent_reference`](#24-agent_reference)
- [3. Agent Bootstrap Architecture](#3-agent-bootstrap-architecture)
  - [3.1 Purpose](#31-purpose)
  - [3.2 Bootstrap Is Discovery and Assembly](#32-bootstrap-is-discovery-and-assembly)
  - [3.3 Bootstrap Inputs](#33-bootstrap-inputs)
  - [3.4 Bootstrap Output](#34-bootstrap-output)
- [4. Bootstrap Memory Semantics](#4-bootstrap-memory-semantics)
  - [4.1 Static Memory](#41-static-memory)
  - [4.2 Reference Memory](#42-reference-memory)
  - [4.3 Procedures and Skills](#43-procedures-and-skills)
  - [4.4 Run-Derived Experience](#44-run-derived-experience)
  - [4.5 Reusable Run-Derived Objects](#45-reusable-run-derived-objects)
  - [4.6 Session Working Memory](#46-session-working-memory)
  - [4.7 CodeGraph Is Not Memory](#47-codegraph-is-not-memory)
- [5. RR Run Bundle as the Common Substrate](#5-rr-run-bundle-as-the-common-substrate)
  - [5.1 Run Bundle Authority](#51-run-bundle-authority)
  - [5.2 Required Run Bundle Contents](#52-required-run-bundle-contents)
  - [5.3 Accepted and Failed Runs](#53-accepted-and-failed-runs)
  - [5.4 Workspace Snapshot](#54-workspace-snapshot)
- [6. Post-Run Processing Pipeline](#6-post-run-processing-pipeline)
  - [6.1 Processing Trigger](#61-processing-trigger)
  - [6.2 Experience Extraction](#62-experience-extraction)
  - [6.3 Experience Reinforcement](#63-experience-reinforcement)
  - [6.4 Reusable Object Extraction](#64-reusable-object-extraction)
  - [6.5 Procedure and Skill Ingestion](#65-procedure-and-skill-ingestion)
  - [6.6 The Dean Integration Boundary](#66-the-dean-integration-boundary)
- [7. Bootstrap Assembly Pipeline](#7-bootstrap-assembly-pipeline)
  - [7.1 Static Retrieval](#71-static-retrieval)
  - [7.2 Reference Discovery](#72-reference-discovery)
  - [7.3 Procedure Candidate Retrieval and Selection](#73-procedure-candidate-retrieval-and-selection)
  - [7.4 Experience Discovery](#74-experience-discovery)
  - [7.5 Reusable Object Discovery](#75-reusable-object-discovery)
  - [7.6 Capability Discovery](#76-capability-discovery)
  - [7.7 Prompt Assembly](#77-prompt-assembly)
- [8. Capability Sessions](#8-capability-sessions)
  - [8.1 Virtual Session Model](#81-virtual-session-model)
  - [8.2 Session Identity](#82-session-identity)
  - [8.3 Session Persistence](#83-session-persistence)
  - [8.4 Session Lifecycle](#84-session-lifecycle)
  - [8.5 Tool Visibility Invariant](#85-tool-visibility-invariant)
- [9. Dynamic CodeGraph Integration](#9-dynamic-codegraph-integration)
  - [9.1 Architectural Position](#91-architectural-position)
  - [9.2 Graph Identity](#92-graph-identity)
  - [9.3 Worker Runtime](#93-worker-runtime)
  - [9.4 CodeGraph Registry](#94-codegraph-registry)
  - [9.5 Stable MCP Provider and Dynamic Backend Binding](#95-stable-mcp-provider-and-dynamic-backend-binding)
  - [9.6 Query Routing](#96-query-routing)
  - [9.7 Revision Readiness](#97-revision-readiness)
  - [9.8 Worker Recovery](#98-worker-recovery)
  - [9.9 Reverse RR Isolation](#99-reverse-rr-isolation)
- [10. Proposed MCP Surface](#10-proposed-mcp-surface)
  - [10.1 Bootstrap](#101-bootstrap)
  - [10.2 Reference](#102-reference)
  - [10.3 Procedures and Skills](#103-procedures-and-skills)
  - [10.4 Experience](#104-experience)
  - [10.5 Reusable Objects](#105-reusable-objects)
  - [10.6 Session Memory](#106-session-memory)
  - [10.7 CodeGraph](#107-codegraph)
- [11. FastMCP Integration Model](#11-fastmcp-integration-model)
  - [11.1 Stable Server](#111-stable-server)
  - [11.2 Providers](#112-providers)
  - [11.3 Request and Capability Middleware](#113-request-and-capability-middleware)
  - [11.4 Session-Scoped Visibility](#114-session-scoped-visibility)
  - [11.5 Proxying Dynamic Backends](#115-proxying-dynamic-backends)
- [12. Catalog and Storage Model](#12-catalog-and-storage-model)
  - [12.1 Reference Catalog](#121-reference-catalog)
  - [12.2 Procedure Catalog](#122-procedure-catalog)
  - [12.3 Experience Store](#123-experience-store)
  - [12.4 Reusable Object Store](#124-reusable-object-store)
  - [12.5 Capability Session Store](#125-capability-session-store)
- [13. Ranking, Reinforcement, and Effectiveness Statistics](#13-ranking-reinforcement-and-effectiveness-statistics)
  - [13.1 Experience Support](#131-experience-support)
  - [13.2 Procedure Effectiveness](#132-procedure-effectiveness)
  - [13.3 Reference Usage](#133-reference-usage)
  - [13.4 Object Reuse](#134-object-reuse)
  - [13.5 Bootstrap Funnel](#135-bootstrap-funnel)
- [14. Security and Authority Boundaries](#14-security-and-authority-boundaries)
- [15. Failure and Recovery Semantics](#15-failure-and-recovery-semantics)
- [16. Telemetry](#16-telemetry)
- [17. Required Implementation Work](#17-required-implementation-work)
- [18. Explicit Non-Goals](#18-explicit-non-goals)
- [19. Open Architectural Decisions](#19-open-architectural-decisions)
- [20. Extension Rule](#20-extension-rule)
- [21. Closing Statement](#21-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIAL
**Audience:** Maintainers, Memory Steward developers, RR developers, extension developers, agent-runtime integrators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

This document contains both current runtime behavior and proposed architecture.

The following capabilities are represented by the current implementation and are therefore current runtime behavior:

- LIST transcription service behavior described in Section 2.1;
- structured agent context retrieval;
- agent outcome submission;
- context feedback submission;
- Reference Memory semantic search;
- exact Reference Memory chunk retrieval;
- `agent_reference` persistence and exact selector-based retrieval.

The following capabilities are architectural proposals and MUST NOT be represented as implemented until corresponding code, migrations, manifests, tests, and runtime verification exist:

- agent bootstrap assembly;
- enriched Reference Memory catalog discovery;
- procedural/skill ingestion and recommendation;
- run-derived experience extraction;
- experience reinforcement;
- reusable-object extraction from completed runs;
- session working memory;
- capability sessions;
- dynamic run-scoped MCP visibility;
- CodeGraph controller, registry, workers, and dynamic MCP routing;
- bootstrap effectiveness statistics;
- automatic RR run-bundle processing;
- The Dean integration described in this document.

> **Hard Invariant:** Checked-in code, manifests, schemas, and executable tests remain authoritative for current runtime behavior. A proposal in this document MUST NOT be interpreted as an implemented capability.

[Back to top](#navigation)

---

## 1. Extension Surface Overview

Memory Steward extensions provide agent-facing capabilities without collapsing memory, orchestration, deterministic analysis, artifact storage, and model training into one authority domain.

The target extension architecture separates five concerns:

1. durable and governed memory;
2. discovery of useful external knowledge and procedures;
3. post-run extraction of reusable experience and objects;
4. ephemeral run/session capabilities;
5. deterministic analyzer capabilities such as CodeGraph.

Memory Steward acts as the agent-facing capability plane.

RR remains authoritative for:

- run state;
- objective state;
- workspace state;
- accepted revision;
- execution lifecycle;
- acceptance gates;
- run artifact production.

Memory Steward MUST NOT infer RR state transitions from memory contents, analyzer contents, object-storage events, or model output.

[Back to top](#navigation)

---

## 2. Current Implemented Surface

### 2.1 LIST

`memory-steward-list` is an optional FastAPI service.

Implemented endpoints include:

- `GET /healthz`;
- `POST /v1/audio/transcriptions`;
- `POST /v1/list/transcribe`.

`POST /v1/list/translate` exists but currently returns HTTP 501 and MUST NOT be represented as implemented translation capability.

LIST does not own memory admission, Builder inference, agent bootstrap, or CodeGraph lifecycle.

### 2.2 Agent Retrieval and Outcome Operations

Implemented Router operations include:

- `POST /v1/context/retrieve`.

Implemented Steward operations include:

- `POST /v1/agent/outcomes`;
- `POST /v1/context/feedback`.

Implemented MCP adapters include:

- `memory.retrieve_context`;
- `memory.submit_agent_outcome`;
- `memory.submit_context_feedback`.

`memory.retrieve_context` is a composite governed retrieval operation. It MUST NOT be treated as the only primitive for all future agent memory access.

### 2.3 Reference Memory Operations

Implemented Router operations include:

- `POST /v1/reference/search`;
- `GET /v1/reference/{chunk_id}`.

Implemented MCP adapters include:

- `memory.reference.search`;
- `memory.reference.get`.

Reference Memory is not project-scoped in Qdrant.

Reference chunks are identified through Reference Memory metadata such as:

- `memory_type`;
- `product`;
- `version`;
- `scope`;
- `source`;
- stable point identity.

A caller's `project_id` MUST NOT be silently converted into a Reference Memory namespace.

### 2.4 `agent_reference`

`agent_reference` stores reusable structured artifacts produced by agents, analyzers, or deterministic tools.

It is distinct from canonical `reference_memory`.

Exact `agent_reference` retrieval uses deterministic Postgres selectors.

Semantic Qdrant indexing MAY be added where useful, but semantic retrieval MUST NOT replace exact artifact identity.

`agent_reference` MAY be used as the persistence mechanism for reusable run-derived objects.

A CodeGraph index itself MUST NOT be classified as `agent_reference` merely because an agent can query it.

[Back to top](#navigation)

---

## 3. Agent Bootstrap Architecture

### 3.1 Purpose

**Status:** PROPOSAL

An agent MUST NOT require prior knowledge of every memory namespace, stored artifact, external reference, procedure, or analyzer available to the current task.

Memory Steward SHOULD provide a bootstrap operation that answers:

- what mandatory instructions apply;
- what authoritative references are available;
- what procedures or skills are likely to help;
- what prior experience is available;
- what reusable objects are available;
- what session capabilities are available;
- what deterministic analyzers are available;
- which MCP tools the agent is authorized to use.

The bootstrap operation is not a general-purpose context dump.

Its purpose is to provide a bounded heads-up and capability manifest for the current objective.

### 3.2 Bootstrap Is Discovery and Assembly

Bootstrap MUST distinguish between content that must be injected and content that merely needs to be announced.

The target behavior is:

| Class | Automatic discovery | Full content automatically injected | On-demand access |
| --- | --- | --- | --- |
| Static Memory | yes | yes | optional |
| Reference Memory | yes | no | search/get |
| Procedures/Skills | yes | no | exact get |
| Experience | yes | no | exact get/search |
| Reusable Objects | yes | no | exact get |
| Session Memory | session-bound | no | direct read/write |
| CodeGraph | readiness check | no | query tools |

> **Hard Invariant:** Discovery of an object MUST NOT imply automatic injection of that object's full content into the primary agent context.

### 3.3 Bootstrap Inputs

The bootstrap request SHOULD include at least:

- `project_id`;
- `run_id`;
- `realm`;
- `revision`;
- `role`;
- `objective`;
- execution stage when available;
- repository identity when available;
- known project technology metadata when available.

The bootstrap caller is expected to be RR, an RR bootstrapper, or another authorized orchestration runtime.

The bootstrap caller MUST provide authoritative run/revision identity.

Memory Steward MUST NOT guess the active revision from repository names, previously observed runs, or analyzer state.

### 3.4 Bootstrap Output

The bootstrap response SHOULD contain:

- mandatory Static Memory content;
- available Reference Memory descriptors;
- recommended Procedure/Skill descriptors;
- relevant Experience descriptors;
- relevant reusable-object descriptors;
- session-memory capability metadata;
- CodeGraph readiness and available query capabilities;
- capability-session identity;
- MCP endpoint information;
- capability-session credentials or an opaque capability handle;
- expiration metadata;
- bootstrap provenance and trace identity.

The response MAY also contain a preassembled Markdown prompt fragment suitable for direct inclusion in the agent bootstrap prompt.

That prompt fragment MUST contain descriptions and identifiers rather than automatically embedding all available payloads.

[Back to top](#navigation)

---

## 4. Bootstrap Memory Semantics

### 4.1 Static Memory

Static Memory represents mandatory or strongly authoritative instructions governing how the agent should operate.

Examples include:

- organization-wide engineering rules;
- security and compliance rules;
- project conventions;
- directory restrictions;
- build and verification requirements;
- role-specific instructions;
- mode-specific instructions.

Static Memory MUST be retrieved unconditionally during bootstrap.

Applicable Static Memory content MUST be injected directly into the primary agent context.

Static Memory retrieval SHOULD primarily use deterministic scope and precedence rather than semantic similarity.

Semantic retrieval MAY be used inside a large modular static corpus, but it MUST NOT cause mandatory higher-precedence rules to disappear.

The target precedence model SHOULD support deterministic applicability across relevant scopes.

The precise broader scope vocabulary beyond current project/mode semantics remains subject to Section 19.

### 4.2 Reference Memory

Reference Memory represents authoritative external sources.

Examples include:

- product documentation;
- API documentation;
- standards;
- protocol specifications;
- vendor manuals;
- language documentation;
- versioned software documentation.

Bootstrap MUST NOT automatically retrieve and inject arbitrary Reference Memory chunks.

Instead, bootstrap SHOULD perform low-cost catalog discovery and announce relevant Reference Memory namespaces or sources.

A bootstrap announcement SHOULD provide compact metadata such as:

- product;
- version;
- title;
- short description;
- scope;
- provider;
- source identity;
- tags or keywords when available.

The agent then uses:

- `memory.reference.search` to locate relevant chunks;
- `memory.reference.get` to retrieve exact full chunks.

The Reference Memory catalog is distinct from semantic Reference Memory search.

Catalog discovery SHOULD use Postgres metadata where possible and SHOULD NOT require embedding/vector search merely to determine that a relevant source exists.

The current `reference_ingestion` table provides ingestion provenance including product, version, scope, source URL, counts, and ingestion time.

The proposed bootstrap catalog requires richer searchable metadata than the existing ingestion audit record.

### 4.3 Procedures and Skills

Procedures and skills represent reusable operational methods.

Candidate sources include:

- curated GitHub repositories;
- organization-maintained runbooks;
- agent skill repositories;
- troubleshooting playbooks;
- domain-specific procedures;
- externally maintained procedural knowledge approved for ingestion.

Procedure content SHOULD be indexed for retrieval.

Procedure metadata SHOULD include at least:

- stable identifier;
- name;
- description;
- source repository;
- source revision;
- source path;
- content hash;
- applicable technologies;
- applicable roles;
- task categories;
- prerequisites when known;
- provenance;
- trust/source classification.

Procedure bootstrap selection SHOULD use two stages.

First, deterministic and/or semantic retrieval produces a candidate set.

Second, a bounded selector model receives:

- objective;
- role;
- stage;
- relevant project metadata;
- procedure names;
- procedure descriptions;
- procedure metadata.

The selector MUST NOT require the full procedure bodies merely to choose candidates.

The selector SHOULD return a bounded set of recommended procedure identifiers.

Bootstrap MUST announce only compact procedure descriptors.

The complete procedure is loaded only when the agent explicitly requests it.

> **Hard Invariant:** Procedure recommendation is probabilistic assistance. A recommended procedure MUST NOT become an execution requirement unless a separate policy explicitly makes it mandatory.

### 4.4 Run-Derived Experience

Experience is learned operational knowledge extracted from execution history.

Experience is derived from RR run evidence rather than written directly by the executing agent as durable truth.

Examples include:

- recurring failure patterns;
- root causes;
- successful repairs;
- ineffective attempted repairs;
- environment-specific pitfalls;
- version compatibility problems;
- verification strategies that proved useful;
- role-specific operational lessons.

Experience extraction and reusable-object extraction are separate processes.

Experience MAY be represented as a specialized form of learned/dynamic memory.

A stored experience item SHOULD contain:

- stable identity;
- normalized statement;
- conditions under which it applies;
- scope;
- applicable roles;
- applicable task classes;
- source run/objective identities;
- evidence references;
- successful verification references;
- support count;
- confidence or ranking metadata;
- creation time;
- last confirmation time.

Bootstrap SHOULD retrieve and rank potentially relevant experience.

Bootstrap SHOULD announce compact experience descriptors rather than automatically inject full historical run material.

The agent MAY request full experience records on demand.

### 4.5 Reusable Run-Derived Objects

A reusable object is a concrete result produced or discovered during a previous run that can be consumed again.

Examples include:

- structured analysis results;
- pin maps;
- validated mappings;
- generated machine-readable reports;
- normalized project descriptors;
- analyzer outputs;
- reusable manifests;
- validated intermediate representations.

Reusable-object extraction is separate from experience extraction.

The distinction is:

- experience captures what was learned;
- reusable objects capture what can be reused as an object.

A reusable object SHOULD have:

- stable identity;
- project/repository identity;
- source run/objective;
- source revision;
- object/artifact type;
- schema version;
- producer identity;
- content hash;
- payload or artifact-store reference;
- provenance;
- applicability metadata.

The existing `agent_reference` mechanism MAY be used for these objects where its identity and persistence semantics fit.

Bootstrap SHOULD announce likely relevant objects using descriptors.

Full payloads SHOULD be retrieved only when requested.

A second LLM selection pass is not mandatory for reusable objects.

Deterministic metadata filtering and ranking SHOULD be preferred initially.

### 4.6 Session Working Memory

Session working memory is ephemeral state associated with a current agent/run/session.

It is not durable learned memory.

It MAY contain:

- partial investigations;
- temporary hypotheses;
- intermediate tool outputs;
- scratch mappings;
- execution notes;
- handoff state;
- state needed across context compaction or model calls.

Session working memory MUST be scoped to an explicit session identity.

Session working memory MUST have bounded lifetime.

Session working memory MUST NOT become durable experience merely because the agent wrote it.

Promotion from session state into durable memory MUST use a separate post-run or admission process.

### 4.7 CodeGraph Is Not Memory

CodeGraph is a deterministic derived analyzer.

A graph is reproducible from an authorized workspace snapshot and analyzer version/configuration.

Therefore:

- CodeGraph MUST NOT be stored as canonical Reference Memory;
- CodeGraph MUST NOT be classified as experience;
- CodeGraph MUST NOT become durable learned memory;
- CodeGraph MUST NOT become an `agent_reference` merely because agents can query it;
- CodeGraph MUST NOT replace Git or RR revision authority.

A persisted CodeGraph archive MAY live in artifact/object storage.

Its lifecycle and identity MUST be tracked through a dedicated CodeGraph registry or equivalent analyzer registry.

[Back to top](#navigation)

---

## 5. RR Run Bundle as the Common Substrate

### 5.1 Run Bundle Authority

**Status:** PROPOSAL

RR SHOULD produce an immutable complete run bundle.

The run bundle is not merely a debugging export.

It is the common execution substrate from which:

- CodeGraph derives structural indexes;
- Memory Steward derives experience;
- Memory Steward discovers reusable objects;
- observability and auditing derive execution history;
- The Dean derives training/evaluation material.

The run bundle remains owned by RR.

Memory Steward and The Dean are consumers.

### 5.2 Required Run Bundle Contents

A complete run bundle SHOULD contain all available evidence needed to reconstruct the objective execution trajectory.

At minimum, where produced by the run, it SHOULD contain:

- run identity;
- project identity;
- objective identity;
- objective specification;
- run status;
- accepted/failed state;
- initial revision;
- final revision;
- realm;
- exact workspace snapshot or immutable workspace artifact;
- planning outputs;
- enrichment outputs;
- agent prompts;
- model responses;
- model routing metadata;
- token/accounting metadata;
- tool calls;
- tool results;
- command execution records;
- generated patches;
- rejected patches when retained;
- repair-loop iterations;
- failures;
- stderr/stdout evidence;
- gate results;
- predicate results;
- verification results;
- review/adjudication artifacts;
- final accepted outputs;
- artifact manifests;
- timestamps;
- producer versions;
- provenance;
- trace/span correlation metadata.

The bundle SHOULD preserve machine-readable original artifacts rather than replacing them with one generated summary.

### 5.3 Accepted and Failed Runs

Successful accepted objectives SHOULD be eligible as positive evidence for experience reinforcement.

A failed terminal run SHOULD still be exported.

Failed runs are valuable for:

- failure analysis;
- negative examples;
- ineffective-strategy analysis;
- The Dean datasets;
- reliability research;
- regression diagnosis.

A failed run MUST NOT automatically reinforce a positive experience item.

Repeated attempts within one run MUST NOT be counted as multiple independent confirmations of the same experience.

### 5.4 Workspace Snapshot

The workspace snapshot is a constituent of the complete run bundle.

CodeGraph consumes the workspace/revision portion.

The workspace artifact MUST be immutable for the revision it represents.

A workspace snapshot manifest SHOULD contain at least:

- schema version;
- project ID;
- run ID;
- realm;
- repository identity when available;
- revision;
- content hash;
- creation time;
- object-storage reference;
- producer identity.

> **Hard Invariant:** The complete RR run bundle is the post-run substrate. The workspace snapshot is one component of that bundle, not the entire export contract.

[Back to top](#navigation)

---

## 6. Post-Run Processing Pipeline

### 6.1 Processing Trigger

When RR publishes a fresh immutable run bundle, post-run consumers MAY begin processing immediately.

Object-storage notification MAY be used as a wake-up signal.

Object-storage notification MUST NOT establish RR run acceptance, run terminal state, or CodeGraph readiness.

The authoritative run state MUST come from RR metadata included in or associated with the bundle.

The processing pipeline SHOULD be asynchronous relative to the completed objective.

It MUST NOT block a completed objective merely because downstream enrichment is slow or unavailable, unless an explicit higher-level workflow requires the derived capability.

### 6.2 Experience Extraction

Experience extraction SHOULD analyze the complete run trajectory rather than only the final output.

A multi-pass extraction process SHOULD be preferred over one unconstrained summarization prompt.

A target extraction sequence is:

1. reconstruct the execution trajectory;
2. identify failures and unsuccessful attempts;
3. identify successful repairs or decisions;
4. identify reusable lessons;
5. identify conditions and applicability;
6. identify role/task relevance;
7. compare candidate lessons with existing experience;
8. consolidate, reinforce, reject, or create experience records.

A configured local large model SHOULD be suitable for this processing when available.

The extraction model is not the authority for whether an objective succeeded.

Objective/gate acceptance comes from RR evidence.

### 6.3 Experience Reinforcement

When newly extracted experience semantically matches an existing experience item, Memory Steward SHOULD reinforce the existing item rather than create uncontrolled duplicates.

Reinforcement MUST retain provenance.

The system MUST be able to identify which independent source runs support an experience item.

A minimum reinforcement record SHOULD track:

- unique supporting run/objective identities;
- support count;
- last confirmation time;
- applicable scope;
- evidence references;
- verification references.

Support count MUST increase at most once per independent source run/objective for the same derived lesson.

Repeated model statements inside one run MUST NOT inflate support.

Ranking SHOULD incorporate repeated independent confirmation.

An experience observed consistently across many accepted runs SHOULD rank above a similar experience observed once, all else being equal.

Contradictory evidence MUST NOT be silently discarded.

Conflicting experience SHOULD either:

- reduce confidence;
- produce condition-specific variants;
- remain as separate records with distinct applicability constraints.

The precise scoring formula is not defined by this document.

### 6.4 Reusable Object Extraction

Reusable-object extraction is independent from experience extraction.

The object extractor SHOULD inspect:

- generated artifacts;
- accepted workspace changes;
- deterministic analyzer outputs;
- machine-readable reports;
- final objective outputs.

It SHOULD identify objects that have standalone reuse value.

Object extraction SHOULD favor deterministic identification where possible.

LLM analysis MAY be used when determining whether a produced artifact has likely future reuse value.

Large object payloads SHOULD remain in artifact/object storage.

Memory Steward SHOULD store descriptors, identity, provenance, and object references.

### 6.5 Procedure and Skill Ingestion

Procedure/skill ingestion is not derived primarily from RR runs.

It SHOULD support curated external sources, including approved GitHub repositories.

An ingestion process SHOULD:

1. fetch an exact source revision;
2. identify skill/procedure units;
3. retain source provenance;
4. calculate content hashes;
5. extract/normalize metadata;
6. persist catalog metadata;
7. index searchable content;
8. support later refresh/versioning.

Untrusted external procedures MUST NOT silently become mandatory policy.

Procedure trust classification MUST remain separate from relevance ranking.

### 6.6 The Dean Integration Boundary

The Dean is a separate system.

The Dean consumes RR execution history at a broader corpus level.

Its responsibilities MAY include:

- dataset construction;
- trajectory comparison;
- successful/failed example selection;
- preference data;
- evaluation-set construction;
- curriculum generation;
- fine-tuning corpus construction.

Memory Steward focuses on operational reuse for subsequent agents.

The Dean focuses on corpus-scale learning and evaluation.

Both systems SHOULD consume the same immutable RR run-bundle format.

Memory Steward MUST NOT become The Dean.

The Dean MUST NOT become the runtime memory authority.

[Back to top](#navigation)

---

## 7. Bootstrap Assembly Pipeline

### 7.1 Static Retrieval

Static retrieval runs unconditionally.

The result is included as mandatory bootstrap context.

Static rules MUST preserve precedence and provenance.

### 7.2 Reference Discovery

Reference discovery runs during bootstrap.

Its purpose is to identify potentially relevant available authoritative sources.

Reference discovery SHOULD prefer catalog metadata over vector retrieval when answering only:

> "What authoritative material do we have that may be useful?"

The result is a bounded list of reference descriptors.

Reference chunk bodies are not automatically injected.

### 7.3 Procedure Candidate Retrieval and Selection

Procedure retrieval produces a candidate list using:

- objective;
- role;
- stage;
- technology metadata;
- project metadata;
- procedure metadata;
- semantic similarity where appropriate.

A bounded selector-model pass then evaluates the candidate descriptors.

The selector returns a smaller recommended list.

The bootstrap prompt announces those procedures.

The agent requests full procedure content only when needed.

### 7.4 Experience Discovery

Experience retrieval SHOULD consider:

- objective similarity;
- project scope;
- broader applicable scope when defined;
- role applicability;
- task type;
- support count;
- confidence;
- evidence quality;
- recency where relevant.

Bootstrap SHOULD announce relevant experience descriptors.

It MUST NOT automatically inject complete historical run traces.

### 7.5 Reusable Object Discovery

Reusable-object discovery SHOULD primarily use deterministic metadata and identity filters.

Potential inputs include:

- project;
- repository;
- objective class;
- role;
- revision compatibility;
- artifact type;
- producer;
- schema version.

A compact list of likely useful objects MAY be announced.

If object volume later requires probabilistic selection, an additional selector stage MAY be introduced.

It is not mandatory in the initial architecture.

### 7.6 Capability Discovery

Bootstrap MUST inspect runtime capabilities relevant to the requested run.

Examples include:

- Session Memory;
- CodeGraph;
- future deterministic analyzers;
- specialized domain adapters.

A capability MUST be announced only when authorization and readiness requirements are satisfied.

### 7.7 Prompt Assembly

The final bootstrap fragment SHOULD resemble the following conceptual structure:

~~~text
Mandatory Instructions
- [full applicable static rules]

Available Authoritative References
- [reference descriptor]
- [reference descriptor]
Use Memory Steward reference tools if these sources are needed.

Recommended Procedures / Skills
- [procedure name] — [short description]
- [procedure name] — [short description]
Request the full procedure before applying it.

Relevant Prior Experience
- [experience descriptor]
- [experience descriptor]
Retrieve an item before repeating substantial prior investigation.

Reusable Prior Objects
- [object descriptor]
- [object descriptor]
Retrieve an existing object before recreating equivalent work.

Available Runtime Capabilities
- Session working memory
- CodeGraph for revision <revision>
~~~

The exact wording MAY evolve.

The semantic distinction between mandatory content and available on-demand capability MUST remain explicit.

[Back to top](#navigation)

---

## 8. Capability Sessions

### 8.1 Virtual Session Model

**Status:** PROPOSAL

Memory Steward MUST NOT require a new Memory Steward MCP server process or Pod for every RR run.

Instead, bootstrap creates a virtual capability session.

A capability session represents:

- one authorized agent/runtime context;
- one project/run/realm/revision binding;
- one role/stage binding where applicable;
- one bounded set of visible MCP capabilities.

The Memory Steward MCP service remains a stable long-lived service.

### 8.2 Session Identity

A capability session SHOULD include at least:

- `capability_session_id`;
- `project_id`;
- `run_id`;
- `realm`;
- `revision`;
- `role`;
- stage when applicable;
- created time;
- expiration time;
- status;
- authorized capability set;
- CodeGraph binding when available;
- bootstrap trace/request identity.

The client MUST receive an opaque credential or authenticated session binding.

The client MUST NOT be trusted merely because it supplies `run_id` or `project_id` headers.

### 8.3 Session Persistence

Capability-session state SHOULD have two representations:

- hot runtime state for low-latency request handling;
- durable Postgres state for recovery and audit.

The in-memory representation is a cache, not the only authority.

If an MCP Pod restarts, another instance MUST be able to reconstruct active capability sessions from durable state.

The durable record SHOULD NOT depend on ephemeral Pod IP addresses as canonical identity.

Backend bindings SHOULD use stable workload identity or a registry indirection that can be repaired after worker restart.

### 8.4 Session Lifecycle

A capability session SHOULD transition through states equivalent to:

- `ACTIVE`;
- `RELEASING`;
- `RELEASED`;
- `EXPIRED`;
- `REVOKED`.

Creation occurs during successful bootstrap.

Release SHOULD occur when:

- RR reports terminal/release intent;
- the dependent stage ends and the session is stage-scoped;
- explicit revocation occurs;
- TTL expires.

Released sessions SHOULD remain available as audit/statistical records.

Released or expired sessions MUST NOT authorize tool calls.

### 8.5 Tool Visibility Invariant

The tools shown to an agent MUST correspond to the authorized capability manifest for that capability session.

If bootstrap announced a capability, the required read/query tools MAY be visible.

If bootstrap did not authorize a capability, its tools MUST NOT appear in `tools/list`.

Hidden tools MUST also be non-callable directly.

> **Hard Invariant:** Tool invisibility is not sufficient access control. Direct tool invocation MUST be authorized against the same capability session.

Operator/admin/destructive tools MUST NOT become visible to ordinary agent sessions merely because they are registered on the same server.

[Back to top](#navigation)

---

## 9. Dynamic CodeGraph Integration

### 9.1 Architectural Position

**Status:** PROPOSAL

The target runtime separates responsibilities as follows:

- RR owns run state and accepted workspace revision;
- artifact storage carries immutable run bundles;
- Memory Steward owns CodeGraph capability lifecycle and agent-facing MCP routing;
- CodeGraph performs deterministic structural analysis;
- Postgres stores CodeGraph registry/capability state;
- Qdrant is not required for CodeGraph query correctness.

~~~mermaid
graph TD
    Agent[Agent Runtime]
    RR[RR Orchestrator]
    Bundle[Immutable RR Run Bundle]
    Store[(Artifact Store)]
    MS[Memory Steward]
    MCP[Memory Steward MCP]
    Registry[(Postgres Capability and CodeGraph Registry)]
    Worker[Run-Scoped CodeGraph Worker]
    CG[CodeGraph MCP Process]

    RR -->|publish| Bundle
    Bundle --> Store

    RR -->|run / realm / revision intent| MS
    MS -->|ensure worker| Worker
    Worker -->|load workspace snapshot| Store
    Worker --> CG
    CG -->|indexed revision| MS
    MS --> Registry

    Agent -->|bootstrap| MS
    MS -->|capability session + MCP endpoint| Agent

    Agent -->|session-authenticated MCP| MCP
    MCP -->|resolve capability session| Registry
    MCP -->|route codegraph query| Worker
    Worker --> CG
    CG --> Worker
    Worker --> MCP
    MCP --> Agent
~~~

> **Hard Invariant:** CodeGraph remains a derived analyzer. It MUST NOT become repository authority, run authority, memory authority, or gate authority.

### 9.2 Graph Identity

A run-scoped graph MUST be revision-aware.

The minimum identity SHOULD contain:

~~~text
project_id
run_id
realm
revision
producer_name
producer_version
index_profile
~~~

`revision` identifies the exact workspace represented by the graph.

For Git-backed accepted workspace states, `revision` SHOULD be the full Git commit SHA where that SHA fully identifies the indexed workspace.

`realm` separates trust domains.

Initial required realm semantics include:

- `workspace` — ordinary forward execution;
- `oracle` — Reverse RR reference implementation;
- `candidate` — Reverse RR reconstruction workspace.

Two graphs MUST NOT be considered interchangeable solely because they belong to repositories with the same name.

### 9.3 Worker Runtime

A run-scoped CodeGraph worker SHOULD live for the lifetime of one active `run_id` and `realm`.

The preferred initial deployment is one Kubernetes worker Pod per active `run_id` and `realm`.

The worker SHOULD contain:

- a Memory Steward CodeGraph worker/adapter;
- the CodeGraph process;
- an ephemeral workspace area;
- ephemeral CodeGraph state.

The worker/adapter SHOULD launch CodeGraph using an upstream-supported transport.

Native MCP stdio MAY be used inside the worker.

The CodeGraph process itself SHOULD remain local to the worker rather than requiring a public cluster-wide endpoint.

The worker adapter MAY expose a bounded internal transport for Memory Steward routing.

Run-scoped graph state SHOULD initially use ephemeral storage.

The graph MUST remain reproducible from the immutable workspace snapshot and recorded producer configuration.

### 9.4 CodeGraph Registry

Memory Steward requires a runtime registry that maps graph identity to current worker state.

A registry record SHOULD include:

- graph identity;
- requested revision;
- indexed revision;
- worker identity;
- worker generation;
- backend transport/address metadata;
- state;
- created time;
- updated time;
- last successful readiness time;
- failure detail when applicable.

Suggested states include:

- `STARTING`;
- `INDEXING`;
- `READY`;
- `DEGRADED`;
- `FAILED`;
- `RELEASING`.

Ephemeral backend addresses MUST NOT become long-lived external agent contract.

Agents interact through Memory Steward MCP.

### 9.5 Stable MCP Provider and Dynamic Backend Binding

Memory Steward SHOULD register one stable CodeGraph-facing provider or adapter layer in the long-lived MCP server.

It MUST NOT add a new top-level MCP server process every time a run begins.

The visible CodeGraph tool definitions MAY remain stable.

The backend target is resolved dynamically from the capability session.

Conceptually:

~~~text
codegraph.call
    -> capability_session
    -> project/run/realm/revision
    -> CodeGraph registry
    -> READY worker for exact revision
    -> worker CodeGraph backend
~~~

The implementation MAY use a custom FastMCP provider plus proxy/client machinery.

The stable provider is Memory Steward code.

It is not an upstream component named `CodeGraphRouterProvider`.

### 9.6 Query Routing

For every CodeGraph tool call, Memory Steward MUST:

1. authenticate the capability session;
2. verify the requested tool is authorized;
3. load or resolve session identity;
4. resolve the expected `project_id`;
5. resolve `run_id`;
6. resolve `realm`;
7. resolve requested revision;
8. query the CodeGraph registry;
9. require `READY`;
10. require `indexed_revision == session.revision`;
11. route to the associated worker;
12. return the bounded result;
13. record telemetry.

The agent MUST NOT supply an arbitrary worker target.

### 9.7 Revision Readiness

CodeGraph readiness is revision-specific.

`READY` without an `indexed_revision` is insufficient.

An agent bound to revision `R` MUST NOT receive CodeGraph query capability when the available worker is indexed only at `R-1`.

When RR advances the accepted workspace:

1. RR publishes the new run/workspace artifact;
2. Memory Steward receives or discovers explicit lifecycle intent;
3. the existing worker MAY incrementally reindex when supported;
4. worker state becomes non-ready while indexing;
5. worker reports its new indexed revision;
6. capability becomes ready only when revisions match.

### 9.8 Worker Recovery

A worker Pod is disposable.

If a worker disappears:

1. the graph registry records loss/degradation;
2. existing capability sessions remain logically valid but CodeGraph capability becomes temporarily unavailable;
3. Memory Steward identifies the required immutable workspace snapshot;
4. a replacement worker is created;
5. the worker rebuilds or restores the graph;
6. the registry receives a new worker binding;
7. capability returns to `READY` only after revision verification.

Capability sessions MUST NOT require recreation solely because the worker Pod changed.

### 9.9 Reverse RR Isolation

Oracle and candidate graph realms MUST remain isolated.

A candidate-side agent MUST NOT:

- query an oracle graph;
- receive an oracle worker binding;
- receive oracle-only structural identifiers;
- fall back from a missing candidate graph to an oracle graph.

Oracle-side authorized stages MAY receive oracle capability.

> **Hard Invariant:** CodeGraph realm isolation MUST follow the same trust boundary as workspace isolation.

[Back to top](#navigation)

---

## 10. Proposed MCP Surface

### 10.1 Bootstrap

Proposed agent bootstrap tool:

- `memory.bootstrap`

The tool SHOULD accept the bootstrap identity and objective context defined in Section 3.

It SHOULD return:

- bootstrap content;
- capability-session identity;
- capability manifest;
- MCP connection information;
- expiration metadata.

A direct HTTP endpoint MAY exist beneath the MCP adapter.

MCP remains the preferred agent-facing integration surface.

### 10.2 Reference

Current tools:

- `memory.reference.search`;
- `memory.reference.get`.

A bootstrap catalog operation MAY remain internal rather than becoming an ordinary agent tool.

If exposed, it SHOULD be read-only and descriptor-oriented.

### 10.3 Procedures and Skills

Proposed read tools:

- `memory.procedure.get`;
- optionally `memory.procedure.search`.

Bootstrap SHOULD normally announce the selected procedure candidates first.

The agent SHOULD not need to enumerate the entire procedure corpus.

### 10.4 Experience

Proposed read tools:

- `memory.experience.get`;
- optionally `memory.experience.search`.

Ordinary agents MUST NOT directly create or reinforce durable experience records.

Experience writes belong to post-run processing and governed admission.

### 10.5 Reusable Objects

Proposed read tools MAY wrap the existing `agent_reference` storage contract.

Candidate agent-facing names include:

- `memory.object.get`;
- `memory.object.search`.

The exact naming is not yet normative.

Object lookup MUST preserve deterministic artifact identity.

### 10.6 Session Memory

Proposed tools include:

- `memory.session.get`;
- `memory.session.put`;
- `memory.session.list`;
- `memory.session.delete`.

Session tools MUST be automatically bound to the current capability/session identity.

An agent MUST NOT be allowed to select another run's session namespace through ordinary arguments.

### 10.7 CodeGraph

Operational lifecycle tools and agent query tools MUST remain separate.

Operational capability MAY include internal or authorized equivalents of:

- ensure;
- status;
- release;
- reindex.

Ordinary agents SHOULD receive only bounded query tools.

Initial query capabilities SHOULD include equivalents of:

- symbol search;
- callers;
- callees;
- call graph;
- dependency graph;
- impact analysis;
- related-test discovery;
- entry-point discovery;
- bounded graph traversal;
- edit/AI context derived from the authorized graph.

Memory Steward MAY namespace these tools as `codegraph.*`.

[Back to top](#navigation)

---

## 11. FastMCP Integration Model

### 11.1 Stable Server

**Status:** PROPOSAL

Memory Steward SHOULD continue to expose one stable FastMCP service.

Per-run specialization SHOULD occur through capability-session state and request-time routing.

Per-run Memory Steward server creation is not required.

### 11.2 Providers

The MCP server SHOULD use providers to separate capability sources.

Conceptual providers include:

- Memory Steward native tools;
- Reference Memory tools;
- Procedure tools;
- Experience/object tools;
- Session-memory tools;
- CodeGraph query provider.

The CodeGraph provider SHOULD expose stable tool definitions while resolving the actual backend at invocation time.

### 11.3 Request and Capability Middleware

MCP middleware SHOULD resolve:

- authenticated session identity;
- capability-session identity;
- project;
- run;
- realm;
- revision;
- role;
- allowed component set.

The middleware MUST reject:

- unknown sessions;
- released sessions;
- expired sessions;
- mismatched identities;
- unauthorized tools.

Session resolution MAY use hot in-memory cache first.

Durable Postgres state MUST permit recovery after process restart.

### 11.4 Session-Scoped Visibility

The tool list MUST be filtered per capability session.

A bootstrap-created capability manifest SHOULD determine which namespaces/tools are visible.

For example, an agent without CodeGraph readiness MUST NOT see CodeGraph query tools.

A session with announced Reference Memory SHOULD see the corresponding read tools.

Admin/operator/write tools SHOULD remain hidden unless separately authorized.

### 11.5 Proxying Dynamic Backends

CodeGraph workers are dynamic backends.

The MCP integration SHOULD resolve a backend client at request time from the CodeGraph registry.

Fresh or safely isolated backend sessions SHOULD be preferred unless the backend is explicitly designed for safe connection reuse.

The proxy layer MUST NOT permit cross-run or cross-realm backend-session leakage.

[Back to top](#navigation)

---

## 12. Catalog and Storage Model

### 12.1 Reference Catalog

The current Reference Memory implementation stores reference chunks in Qdrant and records ingestion provenance in Postgres.

The existing ingestion provenance is insufficient for rich bootstrap discovery.

A proposed Reference Catalog SHOULD add normalized metadata such as:

- reference source ID;
- title;
- description;
- product;
- version;
- scope;
- provider;
- source URL;
- tags;
- keywords;
- source content hash;
- ingestion/version state;
- created/updated time.

Catalog metadata MAY be populated during ingestion.

Bootstrap discovery SHOULD query the catalog.

Semantic chunk search remains a separate operation.

### 12.2 Procedure Catalog

Procedure metadata SHOULD live in Postgres or another deterministic catalog store.

Procedure searchable content MAY be indexed in Qdrant.

The catalog SHOULD preserve exact source provenance and content identity.

### 12.3 Experience Store

Experience SHOULD support semantic retrieval and deterministic metadata filtering.

A likely implementation uses:

- Postgres for canonical record/provenance/support metadata;
- Qdrant for semantic retrieval projection.

The canonical durable record MUST NOT exist only as a vector payload.

### 12.4 Reusable Object Store

Reusable object metadata SHOULD use structured durable storage.

Large payloads SHOULD live in object/artifact storage.

`agent_reference` MAY satisfy this role where its contract is appropriate.

### 12.5 Capability Session Store

Capability sessions SHOULD be durable in Postgres.

A logical record SHOULD contain:

- session ID;
- project ID;
- run ID;
- realm;
- revision;
- role;
- stage;
- status;
- created time;
- expiration time;
- released time;
- authorized capability manifest;
- CodeGraph graph identity/binding reference;
- bootstrap request identity;
- audit metadata.

Secrets SHOULD NOT be stored in plaintext when avoidable.

[Back to top](#navigation)

---

## 13. Ranking, Reinforcement, and Effectiveness Statistics

### 13.1 Experience Support

Experience ranking SHOULD track independent confirmation.

Metrics SHOULD include:

- support count;
- unique supporting runs;
- unique supporting objectives;
- last confirmation;
- contradiction count;
- retrieval count;
- announcement count;
- get/read count;
- successful downstream objective count when attributable.

An experience item observed independently in multiple successful runs SHOULD receive stronger ranking than an otherwise equivalent single-run item.

### 13.2 Procedure Effectiveness

Procedure recommendation telemetry SHOULD track the complete funnel:

- candidate retrieved;
- selector shortlisted;
- announced to agent;
- requested by agent;
- used when observable;
- associated objective outcome.

This enables later ranking based on demonstrated usefulness rather than similarity alone.

### 13.3 Reference Usage

Reference telemetry SHOULD distinguish:

- source available;
- source announced;
- semantic search performed;
- chunk returned;
- exact chunk retrieved;
- downstream usage when observable.

### 13.4 Object Reuse

Reusable object telemetry SHOULD distinguish:

- object matched;
- object announced;
- descriptor viewed;
- payload retrieved;
- object reused when observable.

### 13.5 Bootstrap Funnel

Every bootstrap SHOULD emit a traceable manifest containing the IDs of:

- static rules included;
- references announced;
- procedures considered;
- procedures shortlisted;
- experience announced;
- objects announced;
- runtime capabilities enabled.

This manifest SHOULD make later effectiveness analysis possible without reproducing the original selection process.

[Back to top](#navigation)

---

## 14. Security and Authority Boundaries

Memory Steward MUST treat all agent-supplied identity as untrusted until authenticated against an authorized capability session.

Capability-session authorization MUST bind at least:

- project;
- run;
- realm;
- revision;
- allowed capability set.

Reference Memory read access MAY follow broader policy than project-scoped learned memory, but the policy MUST be explicit.

Session Memory MUST remain isolated by authorized session identity.

Experience retrieval MUST obey its scope and authorization rules.

Reusable object retrieval MUST enforce project/repository/realm constraints where applicable.

CodeGraph MUST enforce exact graph identity and realm.

CodeGraph workers SHOULD receive:

- only their authorized workspace snapshot;
- bounded credentials;
- bounded network access;
- no unrelated database credentials;
- no host filesystem access;
- no access to other run/realm workspaces.

Ordinary agent capability sessions MUST NOT expose:

- reference ingestion;
- reference purge;
- administrative Static Memory mutation;
- unrestricted artifact mutation;
- CodeGraph lifecycle operations;
- capability-session administration.

[Back to top](#navigation)

---

## 15. Failure and Recovery Semantics

Bootstrap failure classes SHOULD distinguish:

- required Static Memory failure;
- Reference Catalog unavailable;
- Procedure retrieval unavailable;
- selector-model unavailable;
- Experience retrieval unavailable;
- object catalog unavailable;
- session store unavailable;
- CodeGraph unavailable;
- capability-session persistence failure.

Static policy retrieval failures MAY be fatal when required policy cannot be safely reconstructed.

Reference/procedure/experience/object discovery SHOULD generally degrade gracefully unless an explicit caller policy declares them required.

If the procedure selector model is unavailable, the system MAY:

- return deterministic top-ranked procedure descriptors;
- omit procedure recommendations;
- classify bootstrap as degraded.

It MUST NOT fabricate procedure recommendations.

CodeGraph failure semantics support caller-declared capability modes:

- `optional`;
- `required`.

For optional CodeGraph:

- indexing failure MUST NOT convert an otherwise valid code objective into a code correctness failure;
- bootstrap MAY continue without CodeGraph tools;
- degradation MUST remain observable.

For required CodeGraph:

- the dependent agent stage MUST NOT begin until the exact revision becomes ready;
- inability to establish capability is an infrastructure/capability failure.

[Back to top](#navigation)

---

## 16. Telemetry

The extension architecture MUST align with Memory Steward telemetry and distributed tracing.

Required bootstrap telemetry SHOULD include:

- bootstrap requests;
- bootstrap latency;
- project/run/role/revision correlation;
- Static Memory retrieval latency;
- Reference Catalog discovery latency;
- Procedure retrieval latency;
- procedure selector latency;
- Experience retrieval latency;
- reusable-object discovery latency;
- selected/announced item counts;
- capability-session creation;
- capability-session expiration/release;
- rejected session calls;
- hidden/unauthorized tool-call attempts.

Required CodeGraph telemetry SHOULD include:

- active workers;
- worker creation;
- worker deletion;
- startup failures;
- indexing attempts;
- indexing failures;
- full/incremental indexing counts;
- indexing duration;
- requested revision;
- indexed revision;
- revision mismatch count;
- rebuild count;
- query count;
- query latency;
- query failures;
- worker recovery count.

Distributed tracing SHOULD correlate:

~~~text
RR run
  -> run bundle publication
  -> post-run processing
  -> experience/object extraction
  -> bootstrap request
  -> capability session
  -> agent MCP request
  -> Memory Steward provider
  -> CodeGraph worker or memory backend
~~~

Telemetry labels MUST avoid leaking arbitrary repository content.

[Back to top](#navigation)

---

## 17. Required Implementation Work

This section is proposal work and MUST NOT be interpreted as implemented runtime capability.

### Memory Steward

Required work includes:

- bootstrap request/response contract;
- bootstrap MCP adapter;
- Static Memory scoped bootstrap retrieval;
- enriched Reference Catalog;
- procedure/skill catalog;
- procedure ingestion pipeline;
- procedure semantic retrieval;
- bounded procedure selector-model pass;
- experience canonical schema;
- experience semantic projection;
- experience extractor;
- experience matching/deduplication;
- experience reinforcement;
- reusable-object extractor;
- session working-memory store/tools;
- capability-session schema;
- capability-session service;
- hot capability cache;
- durable capability recovery;
- capability-aware MCP middleware;
- capability-aware `tools/list`;
- direct-call authorization;
- CodeGraph registry;
- CodeGraph extension controller;
- CodeGraph worker adapter;
- CodeGraph MCP provider/router;
- CodeGraph readiness enforcement;
- bootstrap/run/tool telemetry.

### RR

Required work includes:

- canonical immutable run-bundle export;
- full execution artifact collection;
- immutable workspace snapshot inside the bundle;
- explicit project/run/realm/revision metadata;
- terminal/accepted state metadata;
- post-run publication notification;
- CodeGraph capability intent;
- CodeGraph release intent;
- bootstrap invocation before agent startup;
- bootstrap/capability-session propagation to the agent;
- Reverse RR realm propagation.

### Artifact Infrastructure

Required work includes:

- canonical run-bundle object convention;
- immutable workspace object convention;
- artifact integrity hashes;
- optional event notification;
- lifecycle/retention policy.

### Procedure Sources

Required work includes:

- approved source registry;
- exact source revision capture;
- ingestion provenance;
- refresh/update policy;
- trust classification.

### The Dean

Required integration work includes:

- consumption of the canonical RR run bundle;
- independent corpus-scale processing;
- no dependency on Memory Steward operational experience records for source-of-truth run reconstruction.

[Back to top](#navigation)

---

## 18. Explicit Non-Goals

This architecture does not:

- make Memory Steward the RR orchestrator;
- make Memory Steward authoritative for objective success;
- make Qdrant the canonical store for every object;
- make every retrieved item part of the prompt;
- automatically inject all reference documentation;
- automatically inject all previous experience;
- automatically inject all procedures;
- let agents directly promote arbitrary durable experience;
- classify CodeGraph as memory;
- replace Git revision authority;
- replace RR gates;
- replace deterministic project predicates;
- require a new Memory Steward MCP Pod for every run;
- expose every registered MCP tool to every agent;
- require every agent to use CodeGraph;
- make The Dean part of agent bootstrap;
- make post-run enrichment a correctness dependency for already completed runs.

[Back to top](#navigation)

---

## 19. Open Architectural Decisions

The following decisions remain intentionally unresolved and MUST be finalized before their corresponding implementation is treated as normative.

### 19.1 Experience Scope Vocabulary

Project-local scope is required.

Broader reusable scopes are expected, but exact names and precedence remain open.

Candidate concepts include:

- software/product;
- technology;
- organization.

The implementation MUST NOT invent cross-project propagation semantics without an explicit contract.

### 19.2 Reusable Object Agent-Facing Naming

The existing `agent_reference` storage model may be reused internally.

The final public MCP naming between `agent_reference` and a more general `memory.object.*` interface remains open.

### 19.3 Bootstrap Transport

`memory.bootstrap` is the preferred agent-facing shape.

A corresponding HTTP endpoint may be used internally.

The exact REST path is not normative in this proposal.

### 19.4 Capability Endpoint Representation

A capability session may be represented to the agent as:

- stable MCP endpoint plus opaque session credential;
- virtual run/session-specific URI mapped internally to the same stable service.

A new listening process or dedicated Memory Steward Pod is not required.

The final external representation MUST preserve revocation, recovery, and per-session tool visibility.

### 19.5 Procedure Selector Model

The selector should be small and bounded.

The exact model/routing policy remains configurable.

### 19.6 Experience Scoring

Support count and provenance are required concepts.

The final ranking formula combining:

- semantic similarity;
- support;
- confidence;
- role relevance;
- scope;
- recency;
- contradiction evidence

remains an implementation decision.

[Back to top](#navigation)

---

## 20. Extension Rule

An extension is current only to the extent represented by current code, manifests, schemas, and executable tests.

Implemented sections and proposed sections MUST remain distinguishable.

New capability descriptions MUST NOT silently redefine existing Memory Steward authority boundaries.

Behavior-changing implementation work MUST update this document in the same change set.

When a proposal becomes implemented, its status text and required-work section MUST be updated accordingly.

[Back to top](#navigation)

---

## 21. Closing Statement

Memory Steward's agent-facing architecture SHOULD provide agents with a bounded understanding of what is available rather than preloading every potentially useful object into model context.

Static Memory supplies mandatory instructions.

Reference Memory supplies discoverable authoritative knowledge.

Procedures and skills supply curated methods selected for likely task relevance.

Run-derived Experience supplies reinforced operational lessons extracted from execution evidence.

Reusable run-derived objects preserve concrete outputs that should not be recreated unnecessarily.

Session Memory supplies ephemeral working state.

CodeGraph supplies revision-bound deterministic structural intelligence and remains separate from memory.

RR supplies the immutable execution substrate from which these capabilities are derived.

The Dean consumes the same run substrate at corpus scale for dataset and training/evaluation workflows without becoming part of runtime memory authority.

Capability sessions bind this material to a specific project, run, realm, revision, role, and authorized MCP surface without requiring a separate Memory Steward process for every run.

The resulting architecture separates:

- source evidence from derived knowledge;
- mandatory instructions from discoverable resources;
- semantic memory from deterministic analyzers;
- durable knowledge from ephemeral working state;
- operational reuse from corpus-scale learning;
- tool registration from per-session tool authorization.

---

**END OF DOCUMENT 12**
