# Memory Steward Near-Term TODO: Reference Catalog, RR Reference Preflight, and Durable Backups

**Status:** PROPOSAL / NEAR-TERM TODO  
**Scope:** Memory Steward Reference Memory, RR integration, persistent-data backup  
**Implementation status:** Not implemented unless explicitly marked otherwise

---

## 1. Goal

Improve Reference Memory so that:

1. ingested documents are represented as first-class catalog objects;
2. document metadata is generated automatically during ingestion;
3. RR can request task-specific Reference Memory preparation before each agent step;
4. agents receive a bounded set of strongly relevant references while retaining visibility into additional available material;
5. existing semantic Reference Memory search remains available for deeper on-demand retrieval;
6. persistent Memory Steward data is backed up locally and replicated off-host.

The implementation MUST preserve the existing distinction between:

- canonical Reference Memory;
- dynamic memory;
- `agent_reference`;
- CodeGraph and other deterministic analyzers.

Reference Memory remains globally reusable source material and MUST NOT become project-scoped merely because an RR request contains a `project_id`.

---

## 2. Current State

Reference Memory content is currently stored in Qdrant as `memory_type=reference_memory`.

Current chunk payloads contain:

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

Postgres currently records Reference ingestion provenance in `reference_ingestion` and durable URL-ingestion work in `reference_ingestion_jobs`.

`reference_ingestion` is an ingestion history, not a canonical document catalog. Re-ingesting the same source creates another ingestion record.

There is currently no authoritative Postgres entity representing:

> this document exists, has this stable identity, this title, this source revision, and this generated catalog metadata.

The diagnostic snapshot showed approximately 31,798 current Reference Memory chunks in Qdrant across the existing documentation and book corpora.

The software-engineering book corpus is successfully ingested, but PDF chunks are currently primarily page-oriented (`Page N`, `Page N (part N)`) rather than represented by a durable document-level catalog and semantic document map.

---

## 3. Reference Document Catalog

Add a canonical Reference Document Catalog in Postgres.

There MUST be one current catalog record per ingested document identity.

The initial schema SHOULD remain deliberately small.

Required stable fields:

- `document_id`;
- `product`;
- `version`;
- `source`;
- `content_hash`;
- `title`;
- `metadata JSONB`;
- creation/update timestamps;
- ingestion/current-state marker if required by the final lifecycle design.

`metadata` MAY contain generated document-level information such as:

- short description / abstract;
- summary;
- keywords;
- topics;
- document type;
- outline or table of contents when reliably available;
- other enrichment added later.

These fields MUST NOT be duplicated onto every Qdrant chunk unless a concrete retrieval requirement justifies doing so.

The catalog is the authoritative answer to:

> What Reference documents do we have?

Qdrant remains the answer to:

> Which content inside those documents is semantically relevant to this query?

---

## 4. Qdrant Document Binding

Every Reference Memory chunk MUST carry a stable `document_id`.

The Qdrant payload therefore remains mostly unchanged, with `document_id` added to the current chunk metadata.

`document_id` binds semantic search results back to the canonical Postgres catalog record.

Document-level summary, keywords, outline, roles, collections, and similar metadata SHOULD NOT be copied to every chunk by default.

Existing chunk retrieval and semantic search MUST remain operational.

---

## 5. Ingestion Enrichment

The existing ingestion pipeline SHOULD be extended rather than replaced.

The desired flow is:

`source -> normalize -> document metadata extraction -> catalog upsert -> chunk -> embed -> Qdrant`

Supported source forms currently include text/Markdown, HTML, Git-backed documentation, and PDF.

The enrichment step MUST run once per document, not once per chunk.

### 5.1 Deterministic extraction first

The ingestion pipeline SHOULD extract whatever is available without an LLM:

- repository/source path;
- immutable source revision where available;
- filename;
- front matter;
- HTML title/metadata;
- Markdown/MDX headings;
- AsciiDoc headings;
- PDF metadata;
- PDF bookmarks/outline when available;
- document structure already present in the source.

### 5.2 Bounded model enrichment

A small model MAY be used when deterministic extraction does not provide sufficient catalog information.

The model SHOULD receive only bounded document evidence, for example:

- title/filename;
- extracted metadata;
- table of contents or headings;
- selected beginning/end excerpts;
- bounded representative sections.

The model may produce structured catalog metadata such as:

- normalized title;
- short abstract;
- summary;
- keywords/topics.

The model MUST NOT become the authority for document identity, source revision, content hash, or provenance.

Enrichment failure SHOULD NOT destroy otherwise valid Reference Memory ingestion. The failure/degraded state must remain observable.

### 5.3 PDF improvement

PDF ingestion already extracts text successfully.

The next improvement SHOULD attempt to preserve useful document structure:

1. PDF outline/bookmarks when present;
2. recognizable chapter/section structure where reliably extractable;
3. page-based sections as the fallback.

OCR remains out of scope unless separately approved.

### 5.4 Version identity

Mutable names such as `main` SHOULD NOT be treated as the preferred long-term version identity for authoritative Reference Memory.

Git-backed ingestion SHOULD retain the immutable source commit SHA and use it for exact document provenance.

---

## 6. RR Reference Preflight

RR SHOULD invoke a Memory Steward Reference preflight before starting each relevant agent step.

This is RR-specific behavior and SHOULD therefore have an RR-specific MCP tool name, for example:

`rr.reference.preflight`

The exact public name is still to be finalized.

The tool SHOULD be visible only to authorized RR runtimes/capability sessions and SHOULD NOT automatically appear through unrelated MCP gateway consumers.

### 6.1 Preflight input

RR sends the relevant context of the upcoming agent step.

The input may include:

- role;
- stage;
- objective;
- actual task/instructions being given to the worker;
- language;
- runtime/platform;
- relevant technologies/features;
- other bounded facts already known by RR about the work.

`project_id` MAY remain part of the surrounding transport/session contract, but Reference Memory MUST NOT use it as a corpus namespace or cause duplicate Reference data per project.

RR does not choose individual books or documents.

RR describes the work that is about to happen.

### 6.2 Preflight selection

Memory Steward evaluates the upcoming task against the Reference Catalog.

Selection SHOULD use a bounded pipeline:

1. construct a candidate document set from catalog metadata;
2. perform deterministic narrowing where useful;
3. run a small selector/classifier model over the bounded candidates;
4. rank the candidates;
5. select a configurable top-N set.

The selector model is advisory retrieval logic. It MUST NOT modify Reference Memory.

`top-N` MUST be configurable/budget-driven rather than permanently hard-coded to a specific number.

---

## 7. Preflight Response

The preflight response SHOULD expose two levels.

### 7.1 Selected references

The top-N selected documents receive richer catalog information sufficient for the agent to understand why they may be useful.

This may include:

- `document_id`;
- title;
- source/product/version;
- short abstract;
- summary;
- useful structure/topics where available.

This is the agent's initial Reference Memory "menu".

It is metadata, not bulk document content.

### 7.2 Additional available references

Documents not selected into top-N but still considered relevant candidates SHOULD remain discoverable through a compact representation.

The compact representation SHOULD contain only enough information for the agent to recognize that additional material exists.

It MUST NOT dump full summaries for the entire catalog into the agent context.

The response may group additional material when that reduces context size without hiding availability.

---

## 8. Catalog Lookup Tool

Add a general read-only catalog lookup tool, tentatively:

`memory.reference.catalog.get`

Input:

- `document_id`.

Output:

- the complete current catalog metadata for that document.

This allows an agent to expand one of the compact entries returned by preflight without retrieving arbitrary chunks yet.

This tool is general Reference Memory functionality and does not need to be RR-specific.

---

## 9. Existing Reference Search

The existing:

`memory.reference.search`

MUST remain the semantic content-search mechanism.

No duplicate search tool is required.

The intended interaction becomes:

1. RR calls `rr.reference.preflight`;
2. agent receives selected Reference metadata plus discovery information;
3. agent may expand catalog metadata using `memory.reference.catalog.get`;
4. agent searches actual document content using existing `memory.reference.search`;
5. exact chunks remain retrievable through the existing Reference get path.

Catalog discovery and semantic chunk search remain separate responsibilities.

---

## 10. Manual Configuration

The design SHOULD minimize hand-maintained classification.

Document title, abstract, summary, keywords, and structural metadata SHOULD be generated automatically during ingestion whenever practical.

Manual policy SHOULD be reserved for information that is genuinely organizational intent rather than derivable document content.

Examples may eventually include:

- named Reference collections;
- explicit exclusions;
- source trust policy;
- fixed version requirements;
- specialized RR routing policy.

Collections or role mappings SHOULD NOT be made mandatory for the first catalog implementation if direct catalog-based preflight selection is sufficient.

---

## 11. Re-Cataloging Existing Reference Memory

Existing Reference Memory MUST be migratable without requiring all source material to be manually re-entered.

A re-catalog operation SHOULD be provided.

Preferred behavior:

1. enumerate known sources from existing ingestion provenance and current Qdrant payloads;
2. reconstruct unique document identities;
3. obtain source content again where required for enrichment;
4. create catalog records;
5. assign stable `document_id` values;
6. update/re-ingest Qdrant chunks so each point carries `document_id`;
7. validate catalog-to-Qdrant consistency.

The process MUST be restartable and observable.

A partial failure MUST NOT silently leave catalog and chunk state appearing complete.

---

## 12. Required Diagnostics

Reference diagnostics SHOULD be extended to show at least:

- document count;
- chunk count;
- documents by product/version;
- chunks per document;
- documents lacking enrichment;
- documents lacking `document_id` chunk binding;
- orphaned catalog records;
- Qdrant chunks whose `document_id` does not resolve;
- duplicate/current-version anomalies;
- last catalog/enrichment time.

The existing distinction between ingestion history and current-state inventory MUST remain explicit.

---

## 13. Backup and Off-Host Replication

Memory Steward persistent state needs a real backup path.

The first priority is retained state whose loss would require expensive reconstruction or would lose non-reconstructible information.

At minimum this includes:

- Postgres;
- Qdrant.

This automatically covers the new Reference Catalog once implemented because it resides in Postgres.

Other persistent object data SHOULD be included when it contains non-reconstructible state. Derived CodeGraph generations may remain lower priority if they are reproducible from immutable source artifacts.

### 13.1 Backup flow

Preferred architecture:

`Postgres/Qdrant -> local MinIO backup set -> remote S3-compatible replication`

Remote destination may be:

- AWS S3;
- Cloudflare R2;
- another approved S3-compatible store.

The exact remote provider is configuration, not architecture.

### 13.2 Backup set

Each backup run SHOULD create an internally consistent backup set containing:

- Postgres dump;
- Qdrant snapshot;
- manifest;
- hashes;
- source/runtime version information necessary for restoration.

The backup set MUST be complete locally before remote synchronization begins.

Remote replication MUST NOT publish a partially generated backup as a successful complete backup.

### 13.3 Retention

Local and remote retention MUST be explicit and independently configurable.

The implementation SHOULD support:

- short local retention for fast recovery;
- longer remote retention for host/site loss.

### 13.4 Validation

Backup success MUST NOT mean only "upload command exited zero".

The system MUST validate:

- expected backup objects exist;
- hashes match;
- backup manifest is complete;
- remote synchronization completed.

Periodic restore testing SHOULD be implemented.

A restore procedure SHOULD be able to restore into an isolated environment and verify:

- Postgres schema/data;
- Reference Catalog;
- Qdrant collection;
- catalog/chunk consistency;
- Memory Steward health after restoration.

---

## 14. Security and Access

Reference ingestion and catalog mutation remain operator/control-plane operations.

Ordinary agents MUST receive only read capabilities.

`rr.reference.preflight` MUST be restricted to authorized RR callers.

MCP tool visibility and direct invocation authorization MUST enforce the same policy.

Backup credentials MUST NOT be stored in repository manifests.

Remote backup credentials SHOULD use the minimum permissions required for the configured backup prefix/bucket.

---

## 15. Near-Term Implementation Order

1. Add the Reference Document Catalog schema and migration.
2. Add stable `document_id` generation and Qdrant chunk binding.
3. Extend ingestion with deterministic document metadata extraction.
4. Add bounded optional model enrichment.
5. Improve PDF structure extraction where available.
6. Add re-catalog/re-ingest support for the existing corpus.
7. Add catalog consistency diagnostics.
8. Add `memory.reference.catalog.get`.
9. Add RR-specific `rr.reference.preflight`.
10. Add RR-side preflight invocation before relevant agent steps.
11. Restrict the RR-specific preflight tool through MCP capability/tool policy.
12. Add local Postgres + Qdrant backup generation into MinIO.
13. Add remote S3/R2 synchronization.
14. Add backup integrity checks and isolated restore validation.
15. Update canonical Reference Memory and extension documentation in the same implementation patches.

---

## 16. Acceptance Criteria

Reference Catalog work is complete only when:

- every newly ingested Reference document has one canonical catalog identity;
- every newly written Reference chunk resolves to a valid `document_id`;
- catalog metadata is generated without ordinary manual intervention;
- Reference semantic search behavior remains functional;
- repeated ingestion has defined, testable catalog/version behavior;
- existing Reference data can be re-cataloged;
- RR can obtain a task-specific Reference preflight result before an agent step;
- the preflight result contains a bounded selected set and bounded discovery information;
- ordinary agents can inspect catalog records and use existing semantic search;
- Reference Memory remains global rather than project-scoped;
- RR-specific preflight access is capability-restricted;
- Postgres and Qdrant have automated backups;
- backups are copied off-host;
- restoration is tested, not merely assumed.

---

## 17. Recommendations / Notes

The first implementation SHOULD stay deliberately narrow.

Do not introduce a new retrieval engine.

Do not duplicate document-level metadata across tens of thousands of Qdrant chunks.

Do not require humans to maintain summaries or keywords for every document.

Do not bind canonical Reference Memory to RR project identity.

Do not replace existing `memory.reference.search`.

Use Postgres as the canonical document/catalog store and Qdrant as the semantic chunk index.

Treat the selector model as a bounded classification/ranking component inside Memory Steward, not as another autonomous RR worker.

Keep deterministic extraction ahead of model-generated enrichment.

Make backup restoration a tested operational capability before treating remote replication as complete.
