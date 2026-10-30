# MEMORY STEWARD NEAR-TERM TODO
## Reference Catalog, RR Reference Preflight, and Durable Backups
### Engineering Proposal
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Current Implemented State](#2-current-implemented-state)
- [3. Reference Document Catalog](#3-reference-document-catalog)
- [4. Reference Ingestion Enrichment](#4-reference-ingestion-enrichment)
- [5. Existing Corpus Re-Cataloging](#5-existing-corpus-re-cataloging)
- [6. RR Reference Preflight](#6-rr-reference-preflight)
- [7. Reference Discovery and Catalog Lookup](#7-reference-discovery-and-catalog-lookup)
- [8. MCP Access Boundary](#8-mcp-access-boundary)
- [9. Durable Backup Path](#9-durable-backup-path)
- [10. Required Implementation Work](#10-required-implementation-work)
- [11. Explicit Non-Goals](#11-explicit-non-goals)
- [12. Open Decisions](#12-open-decisions)
- [13. Recommendations](#13-recommendations)
- [14. Closing Statement](#14-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PROPOSAL  
**Audience:** Memory Steward maintainers, RR maintainers, agent-runtime integrators  
**Change policy:** Working near-term implementation plan; unimplemented behavior MUST remain explicitly non-runtime until code, migrations, manifests, and affected documentation are updated.

The current Memory Steward repository implementation is authoritative for existing runtime behavior.

This document records agreed near-term work for:

- Reference Memory document cataloging;
- automatic document metadata enrichment;
- existing-corpus re-cataloging;
- RR-specific Reference preflight;
- Reference catalog discovery;
- durable Memory Steward backup publication and off-host replication.

The following items are proposals and are not current runtime capabilities:

- canonical Reference Document Catalog;
- `document_id` binding between catalog documents and Qdrant chunks;
- RR-specific Reference preflight;
- document catalog lookup tool;
- automatic publication of local backups to MinIO;
- automatic replication from MinIO to S3/R2.

> **Hard Invariant:** Canonical Reference Memory remains globally reusable knowledge and MUST NOT become project-scoped merely because RR supplies `project_id` or other run identity.

[Back to top](#navigation)

---

## 1. Purpose

The immediate work is intended to solve three problems.

First, Reference Memory currently has searchable chunks and ingestion provenance but does not have a canonical document-level catalog that tells an agent what documents exist and what each document contains.

Second, an RR worker should not begin with either no awareness of available Reference material or an unbounded dump of the whole corpus. Before an RR agent step begins, Memory Steward should select likely useful documents and expose the rest through a compact discovery view.

Third, Memory Steward persistent state currently has local backup generation, but the backup path must be completed so a recoverable copy exists outside the local Kubernetes failure domain.

[Back to top](#navigation)

---

## 2. Current Implemented State

### 2.1 Reference ingestion

Reference ingestion already supports a shared content path for current source types.

Current behavior includes:

- durable asynchronous URL ingestion through `reference_ingestion_jobs`;
- processing by `reference-ingest-worker`;
- synchronous direct-text ingestion;
- synchronous Git ingestion;
- shared normalization for URL and Git document bytes;
- text and Markdown ingestion;
- HTML extraction;
- PDF extraction using `pypdf`;
- page-aware PDF sections;
- explicit failure when a PDF has no extractable text layer;
- bounded document size;
- bounded embedding batches;
- successful-ingestion provenance written to `reference_ingestion`.

`reference_ingestion` is immutable ingestion provenance. It is not a document catalog.

`reference_ingestion_jobs` is a durable URL-ingestion queue. It is not a document catalog.

### 2.2 Current Qdrant Reference payload

Current Reference chunks contain payload fields including:

- `memory_type`;
- `ref_key`;
- `product`;
- `version`;
- `scope`;
- `doc_section`;
- `content`;
- `source`;
- `chunk_index`;
- `ingested_at`.

There is currently no canonical `document_id`.

### 2.3 Current Reference retrieval

Current agent-facing Reference retrieval already provides:

~~~text
memory.reference.search
memory.reference.get
~~~

These operations remain responsible for actual semantic chunk search and exact chunk retrieval.

No replacement Reference search operation is required by this proposal.

### 2.4 Current backup path

The current backup CronJob generates:

- PostgreSQL `pg_dump -Fc`;
- Qdrant collection snapshot.

The generated backup files are written to the in-cluster backup PVC.

The existing bootstrap restore path can consume a matching PostgreSQL dump and Qdrant snapshot from MinIO using a manifest containing hashes for the two objects.

Automatic transfer of the locally generated backup pair to MinIO is not currently part of the nightly backup path.

Automatic replication from MinIO to S3 or R2 is also not currently implemented.

[Back to top](#navigation)

---

## 3. Reference Document Catalog

Memory Steward SHOULD add a canonical document-level Reference Catalog in Postgres.

The catalog is separate from:

- `reference_ingestion`;
- `reference_ingestion_jobs`;
- Qdrant chunk storage;
- `agent_reference`.

The catalog represents logical source documents.

A document record should initially contain stable fields equivalent to:

- `document_id`;
- `source`;
- `product`;
- `version`;
- `title`;
- `content_hash`.

Variable document-level enrichment should be stored separately from those stable fields, preferably as structured metadata.

Initial enrichment may contain:

- summary;
- topics;
- keywords;
- outline or table of contents when reliably available.

The catalog is intended to answer:

> What Reference documents exist and what are they about?

Qdrant remains responsible for answering:

> Which chunks from those documents are semantically relevant to this query?

Document-level metadata SHOULD NOT be duplicated onto every Qdrant chunk unless a specific retrieval requirement later justifies that duplication.

### 3.1 Qdrant document binding

Reference chunks SHOULD gain:

~~~text
document_id
~~~

The field links each semantic chunk to its canonical Postgres document record.

The existing Qdrant payload remains otherwise conceptually unchanged.

> **Hard Invariant:** Adding document identity MUST NOT silently redefine existing chunk identity or deduplication behavior. The exact relationship between current content-derived point IDs and document provenance must be decided explicitly before implementation.

[Back to top](#navigation)

---

## 4. Reference Ingestion Enrichment

The existing ingestion path SHOULD be extended rather than replaced.

The desired proposed flow is:

~~~mermaid
flowchart LR
    Source[Reference Source]
    Normalize[Normalize Document]
    Metadata[Extract Document Metadata]
    Catalog[(Postgres Reference Catalog)]
    Chunk[Chunk Document]
    Embed[Embed Chunks]
    Qdrant[(Qdrant Reference Memory)]

    Source --> Normalize
    Normalize --> Metadata
    Metadata --> Catalog
    Normalize --> Chunk
    Catalog -->|document_id| Chunk
    Chunk --> Embed
    Embed --> Qdrant
~~~

Metadata extraction should occur once per logical document rather than once per chunk.

### 4.1 Deterministic extraction

The ingestion path SHOULD first use metadata available directly from the source.

Useful inputs include:

- filename and source path;
- source URL;
- repository identity and revision when available;
- Markdown/MDX/AsciiDoc headings;
- front matter;
- HTML title and headings;
- PDF metadata;
- PDF outline/bookmarks when available;
- content hash.

### 4.2 Model-assisted enrichment

When deterministic extraction does not provide enough useful catalog information, a bounded model pass MAY generate document-level metadata.

The intended generated information includes:

- concise summary;
- topics;
- keywords;
- normalized title when necessary.

The model MUST NOT establish document provenance, source identity, content hash, or immutable version identity.

The design SHOULD minimize manual catalog maintenance.

### 4.3 Existing ingestion behavior

The following current mechanisms SHOULD remain the basis of ingestion:

- current URL job lifecycle;
- current Git ingestion path;
- current document normalization;
- current PDF extraction;
- current chunking and embedding path;
- current provenance recording.

No separate Reference ingestion scheduler or second ingestion framework is required.

[Back to top](#navigation)

---

## 5. Existing Corpus Re-Cataloging

The existing Reference corpus needs to be converted into the same document-level catalog representation used by future ingestion.

The re-catalog operation SHOULD:

1. identify existing logical source documents;
2. create canonical document records;
3. generate document metadata using the same enrichment path as new ingestion;
4. establish `document_id`;
5. associate existing or regenerated Qdrant chunks with that document identity.

The resulting representation SHOULD be equivalent regardless of whether a document was:

- ingested after the catalog implementation;
- already present before the catalog implementation and later re-cataloged.

The implementation method for Qdrant backfill remains open.

In particular, it has not yet been decided whether existing chunks should be updated in place or regenerated through the canonical ingestion path.

[Back to top](#navigation)

---

## 6. RR Reference Preflight

RR SHOULD call a dedicated Reference preflight operation before each relevant RR agent step.

The preflight is RR-specific orchestration behavior.

A working tool name is:

~~~text
rr.reference.preflight
~~~

The final name is not yet normative.

### 6.1 Input

RR supplies the relevant context already available for the upcoming agent step.

The input should include, where applicable:

- agent role;
- execution stage;
- objective;
- actual task or instruction that will be given to the worker;
- relevant project/runtime facts;
- language;
- platform;
- technologies;
- constraints.

RR supplies task context.

RR does not select books, documents, or chunks.

### 6.2 Selection responsibility

Memory Steward compares the supplied task context with the Reference Catalog.

The intended proposed flow is:

~~~mermaid
sequenceDiagram
    participant RR
    participant MS as Memory Steward
    participant CAT as Reference Catalog
    participant SEL as Selector
    participant AG as RR Worker

    RR->>MS: Upcoming worker context
    MS->>CAT: Obtain candidate document descriptors
    CAT-->>MS: Catalog candidates
    MS->>SEL: Task context + bounded candidates
    SEL-->>MS: Ranked documents
    MS-->>RR: Detailed top-N + compact remainder
    RR->>AG: Start worker with Reference menu
~~~

A relatively small model MAY be used as the final selector/classifier.

The selector does not modify Reference Memory.

The selected count SHOULD be configuration- or budget-driven rather than hard-coded permanently to a literal value such as ten.

If the catalog later becomes too large to present directly to the selector, Memory Steward MAY first reduce the candidate set.

That candidate-reduction mechanism is an internal implementation concern and is not yet specified.

[Back to top](#navigation)

---

## 7. Reference Discovery and Catalog Lookup

The preflight result SHOULD contain two disclosure levels.

### 7.1 Selected documents

The selected top-N documents receive the richer catalog metadata needed by the worker.

This may include:

- `document_id`;
- title;
- product/version/source;
- summary;
- useful topics or keywords;
- useful structural metadata.

This is the detailed initial Reference menu.

It is not the document body and does not replace semantic chunk search.

### 7.2 Remaining documents

The remaining available documents are exposed compactly.

The purpose is discoverability: the worker should know that additional material exists even when it was not selected into the detailed top-N set.

The compact representation should contain only enough information to recognize and identify the document.

The exact compact fields remain to be finalized.

### 7.3 Catalog lookup

A second proposed tool allows the worker to expand one compact catalog entry.

Working name:

~~~text
memory.reference.catalog.get
~~~

Input:

~~~text
document_id
~~~

The operation returns the complete current catalog metadata for that document.

The resulting interaction is:

~~~mermaid
flowchart LR
    Preflight[RR Reference Preflight]
    Menu[Detailed Top-N + Compact Remainder]
    CatalogGet[Reference Catalog Get]
    Search[Existing Reference Search]
    ChunkGet[Existing Reference Get]

    Preflight --> Menu
    Menu --> CatalogGet
    Menu --> Search
    CatalogGet --> Search
    Search --> ChunkGet
~~~

The existing `memory.reference.search` remains the semantic search operation.

[Back to top](#navigation)

---

## 8. MCP Access Boundary

`rr.reference.preflight` is RR-specific.

It MUST NOT become available to unrelated MCP clients merely because those clients are allowed to read Reference Memory.

The intended policy is:

- authorized RR runtime: preflight allowed;
- ordinary Reference consumer: preflight unavailable;
- ordinary authorized agent: Reference catalog/search/get access according to its existing capability policy.

Tool visibility and direct-call authorization MUST agree.

Hiding a tool from discovery without preventing direct invocation is insufficient.

The exact gateway/capability implementation is outside this working note and remains subject to the existing MCP authorization design.

[Back to top](#navigation)

---

## 9. Durable Backup Path

The existing PostgreSQL dump and Qdrant snapshot mechanisms SHOULD remain the basis of Memory Steward backup.

The desired backup path is:

~~~mermaid
flowchart LR
    PG[(Postgres)]
    QD[(Qdrant)]
    Backup[Backup Generation]
    Local[(Local Backup Storage)]
    MinIO[(MinIO)]
    Remote[(S3 / R2)]

    PG --> Backup
    QD --> Backup
    Backup --> Local
    Local --> MinIO
    MinIO --> Remote
~~~

The intent is to provide multiple recovery boundaries:

- local retained backup for fast recovery;
- MinIO object-storage copy;
- independent S3/R2 copy outside the local infrastructure failure domain.

The external provider is not yet fixed.

AWS S3 and Cloudflare R2 are both acceptable target classes for later selection.

### 9.1 Existing restore compatibility

The current restore design already understands a manifest referring to:

- PostgreSQL dump;
- Qdrant snapshot;
- SHA-256 for each object.

The backup publication work SHOULD reuse this recovery representation rather than invent an unrelated backup format.

The manifest should become visible as the current recoverable backup only after the corresponding backup objects have been successfully published.

### 9.2 Backup scope

Postgres and Qdrant are definitely in scope.

The exact treatment of additional MinIO-resident Memory Steward data remains an open decision.

Reconstructible derived objects and non-reconstructible retained state should not be treated as equivalent without an explicit decision.

[Back to top](#navigation)

---

## 10. Required Implementation Work

### 10.1 Reference Catalog

Required work:

- define canonical document identity;
- add Postgres catalog schema;
- persist stable document metadata;
- persist generated document metadata;
- add `document_id` linkage to Reference chunks.

### 10.2 Ingestion

Required work:

- integrate catalog creation with the existing shared ingestion path;
- extract deterministic document metadata;
- add bounded enrichment where needed;
- preserve existing chunking/embedding behavior unless separately changed.

### 10.3 Existing corpus

Required work:

- re-catalog existing Reference documents;
- establish document identity;
- associate existing Reference chunks with catalog documents.

### 10.4 RR integration

Required work:

- define the RR preflight request contract;
- add RR-specific preflight tool;
- classify/rank catalog documents;
- return detailed top-N documents;
- return compact discovery information for remaining documents;
- invoke preflight before relevant RR worker steps.

### 10.5 Catalog access

Required work:

- add exact document catalog lookup by `document_id`;
- retain existing Reference semantic search/get tools.

### 10.6 MCP boundary

Required work:

- restrict RR preflight to authorized RR consumers;
- prevent unrelated MCP gateway clients from discovering or invoking it.

### 10.7 Backup

Required work:

- retain existing PostgreSQL and Qdrant backup generation;
- automate publication of the resulting backup set to MinIO;
- automate replication from MinIO to an independent S3-compatible destination;
- preserve compatibility with the existing restore manifest format.

[Back to top](#navigation)

---

## 11. Explicit Non-Goals

This proposal does not authorize:

- project-scoping canonical Reference Memory;
- duplicating Reference documents for individual RR projects;
- merging `agent_reference` with Reference Memory;
- replacing Qdrant semantic search with Postgres;
- replacing `memory.reference.search`;
- replacing `memory.reference.get`;
- copying full document metadata onto every Qdrant chunk;
- introducing a second Reference ingestion scheduler;
- adding OCR;
- changing existing chunk identity or deduplication semantics without a separate decision;
- selecting AWS S3 versus Cloudflare R2 in this document;
- silently changing backup scope beyond the explicitly approved persistent data.

[Back to top](#navigation)

---

## 12. Open Decisions

### 12.1 Document identity and current Qdrant point identity

Current Qdrant point identity is content-derived and does not include source-document identity.

Before one `document_id` is attached to every point, the required behavior for identical content appearing in multiple documents must be decided.

No behavior is selected by this document.

### 12.2 Exact MCP names

Working names are:

~~~text
rr.reference.preflight
memory.reference.catalog.get
~~~

The final names remain open.

### 12.3 Compact discovery representation

The exact fields returned for non-top-N documents remain open.

The representation must be compact enough for startup context while giving the worker enough information to recognize useful additional material.

### 12.4 Backup scope beyond Postgres and Qdrant

Need an explicit decision on whether additional MinIO-resident Memory Steward/CodeGraph artifacts require independent backup or may remain reconstructible derived state.

### 12.5 External object-storage target

Need a later deployment decision between:

- AWS S3;
- Cloudflare R2;
- another compatible independent target.

This decision does not need to alter the logical backup representation.

[Back to top](#navigation)

---

## 13. Recommendations

The Reference Catalog SHOULD be implemented as an extension of the existing ingestion content plane rather than as a separate ingestion system.

Postgres SHOULD own canonical document-level catalog metadata.

Qdrant SHOULD remain the semantic chunk index.

RR SHOULD supply authoritative upcoming-worker context but SHOULD NOT own Reference selection policy.

Memory Steward SHOULD own Reference classification and selection.

The initial agent context SHOULD contain detailed information for the selected top-N documents and compact discovery information for the rest.

Actual Reference content SHOULD continue to be retrieved on demand through the existing Reference search/get operations.

The backup work SHOULD extend the existing PostgreSQL dump, Qdrant snapshot, and restore-manifest design rather than replace it.

[Back to top](#navigation)

---

## 14. Closing Statement

The near-term Reference Memory work separates document discovery from semantic content retrieval.

Postgres provides a canonical document catalog.

Qdrant provides semantic chunk retrieval.

RR supplies the context of the upcoming agent step.

Memory Steward selects and describes likely useful Reference documents.

The worker receives a bounded initial menu while retaining visibility into the broader corpus and the existing ability to search it on demand.

The backup work extends the current local recovery mechanism into a multi-boundary recovery path using MinIO followed by an independent S3-compatible copy.

[Back to top](#navigation)

---

**END OF DOCUMENT**
