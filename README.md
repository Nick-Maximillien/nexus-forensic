# Nexus Forensic

Overview
--------

Nexus Forensic is a Django-based forensic AI platform focused on extracting, normalizing, and adjudicating clinical and administrative evidence from source documents (audits, medical records, policies). The project combines classical document parsing with Retrieval-Augmented Generation (RAG) and constrained LLM workflows to produce verifiable forensic outputs that respect domain rules and compliance constraints.

Key goals:
- Convert heterogeneous clinical documents into structured evidence
- Provide deterministic, auditable reasoning pipelines (domain validators, refusal/acceptance rules)
- Use medically specialized embeddings and RAG to ensure clinical semantic accuracy
- Support local and cloud deployments (Docker, GCP Vertex AI)

High-level architecture
-----------------------

- Django backend (apps/): modular apps for agent workflows, corpus ingestion, domain precision, RAG retrieval, and LLM interfaces.
- Document conversion & parsing: `docling`-based conversion baked into the Docker image for offline model use.
- Embeddings & semantic search: Google Vertex AI-based medical embeddings (referred to internally as HAI-DEF / MedLM) + `pgvector` for vector storage and hybrid search.
- Post-processing: Domain precision layer applies symbolic rules (forensic_domain) and validation engines to ensure outputs are compliant and citable.
- Optional: Anchoring / evidence proofs (blockchain) hooks exist but are kept as optional 'proof' rather than decision-making logic.

Technology stack
----------------

- Language: Python 3.10
- Web framework: Django 5.x
- REST: Django REST Framework + Simple JWT
- Database: PostgreSQL with pgvector extension
- Background jobs: Celery + Redis
- Document conversion: docling + PyPDFium (used in Docker BAKE step)
- Local LLM inference (optional): `llama-cpp-python` (CPU) for research/offline needs
- Cloud LLM & embeddings: Google Vertex AI (specialized MedLM embeddings: `medlm-embeddings-v1`) — within codebase this integration is labeled as HAI-DEF
- Storage: Cloudinary (media), optional local media storage
- Containerization: Docker / docker-compose (development deployment)

Why HAI-DEF (MedLM) here
------------------------

This project requires clinical-grade semantic retrieval to differentiate fine-grained clinical/legal terms. To achieve that, the codebase integrates a specialized Vertex AI embeddings model (referenced as HAI-DEF / MedLM in code). Benefits:

- Clinical semantics: better handling of domain abbreviations (STAT vs PRN), protocols, and regulatory language
- Higher precision in RAG stage when combined with domain validators
- Robust batching & backoff logic for large corpus ingestion (see `apps/forensic_rag/utils.py`)

Quick evidence from repo
-----------------------

- HAI-DEF initialization and batch embedding handling: `apps/forensic_rag/utils.py` (lazy init, backoff, 768-dim fallback vector)
- RAG hybrid retrieval combining `pgvector` L2 distance and PostgreSQL `SearchRank`: `search_forensic_rules` in `apps/forensic_rag/utils.py`
- Domain precision / validators: `apps/forensic_domain/precision.py`
- Document ingestion helpers and normalizers: `apps/forensic_corpus/ingestion` (parser, llm_normalizer)
- Management commands for dataset/embedding generation and ingestion: `apps/forensic_corpus/management/commands/` (e.g., `generate_embeddings.py`, `ingest_documents.py`)

Installation (local, recommended)
--------------------------------

Prerequisites
- Python 3.10
- PostgreSQL with `pgvector` extension (or use the Docker Compose below)
- Redis (for Celery) — optional for async features
- Google Cloud service account (if using Vertex AI): save JSON key and set `GOOGLE_APPLICATION_CREDENTIALS`

Create virtualenv and install

```bash
python -m venv .venv
source .venv/bin/activate   # powershell: .venv\\Scripts\\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Environment
- Copy `.env.example` (if available) to `.env` and set keys. Important variables:
	- `DATABASE_URL` or `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT`
	- `GOOGLE_APPLICATION_CREDENTIALS` (path to GCP JSON key) and `GCP_PROJECT_ID`
	- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (optional; WhatsApp notifications)
	- `REDIS_URL` (if Celery is used)

Run locally (database & migrations)

```bash
# create DB and enable pgvector (if not using docker)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Docker / docker-compose (recommended for consistent dev)
------------------------------------------------------

The repository includes a `Dockerfile` and `docker-compose.yml` to run the backend and a Postgres+pgvector image. The Dockerfile explicitly bakes document-conversion assets and installs CPU PyTorch and docling dependencies for offline parsing.

Start the stack

```bash
docker-compose up --build
```

Notes:
- The compose file mounts a GCP service account JSON into the container and sets `GOOGLE_APPLICATION_CREDENTIALS` and `GCP_PROJECT_ID`. If you use Vertex AI, ensure the service account has the required Vertex permissions.
- The Dockerfile runs a small bake step for docling to pre-populate necessary conversion models.

Configuration and environment variables
-------------------------------------

Important env vars the project reads (non-exhaustive):

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT` (or `DATABASE_URL`)
- `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `ENV`
- `REDIS_URL` (Celery broker)
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`, `AUDITOR_WHATSAPP_NUMBER`

Embedding & Vertex AI (HAI-DEF) setup
------------------------------------

1. Create a GCP service account with Vertex AI permissions and download the JSON key.
2. Set `GOOGLE_APPLICATION_CREDENTIALS` to the key path and `GCP_PROJECT_ID` to your project id.
3. The code lazy-loads Vertex AI embeddings from `medlm-embeddings-v1` in `apps/forensic_rag/utils.py`.

Batching and quotas
- The embedding ingestion uses exponential backoff and jitter to handle quota errors (ResourceExhausted / ServiceUnavailable). See `get_batch_embeddings` for retry logic and null-vector fallback behavior.

Data and corpus
---------------

Data and training material are located under the `data/` folder. Notable files:
- `nexus_raw_audit.jsonl`, `nexus_finetune_FINAL.jsonl` — curated examples and fine-tune candidates
- `clean_brain_v2.sql`, `surgical_data.sql` — SQL dumps with rules and domain content
- `knmp2024_knowledge_graph.json` — example knowledge graph

Corpus ingestion
- The ingestion pipeline lives in `apps/forensic_corpus/ingestion/` (parser.py, llm_normalizer.py).
- Use management commands to load data:

```bash
python manage.py ingest_documents  # implementation-specific args may apply
python manage.py generate_embeddings
```

Scripts & utilities
-------------------

- `scripts/` contains helper scripts for conversion, training, pushing assets to HF, and other research utilities.
- `apps/forensic_agent/` contains workflow and agent orchestration code for running audits and notifications.
- Management commands are in `apps/forensic_corpus/management/commands/` and `apps/users/management/commands/`.

Search & RAG behavior
---------------------

- The hybrid search combines Vertex AI embeddings (MedLM) stored in `pgvector` with PostgreSQL full-text search ranking to create a `hybrid_score`. The implementation is in `apps/forensic_rag/utils.py` (function `search_forensic_rules`).
- This hybrid approach ensures both semantic similarity and deterministic keyword matches.

Developer notes & conventions
-----------------------------

- Embedding dimensionality: The code treats embedding outputs as length-768 vectors; fallback vectors of zeros are used if Vertex fails.
- Model initialization: `_get_embedding_model()` lazily initializes the Vertex AI client; ensure `GCP_PROJECT_ID` is set.
- Docker bake step: The `Dockerfile` runs a warm-up conversion to download docling assets for offline operation. This makes container images larger but ensures deterministic parsing offline.

Security & PHI handling (important)
----------------------------------

- This repository processes clinical documents. Treat data in `data/` and uploads as sensitive: store and transmit under secure infrastructure, follow your organization's data protection rules, and remove or redact PHI when necessary.
- Use restricted GCP service accounts and follow least-privilege principles. Do not commit keys to source control.

Troubleshooting
---------------

- Vertex AI rate limits: watch logs for quota warnings; the code uses exponential backoff but you may need to request quota increases for large ingests.
- pgvector setup: ensure your Postgres instance has the `pgvector` extension enabled (the docker-compose image `pgvector/pgvector:pg15` is provided).
- Docling failures: the Dockerfile pre-bakes docling models; if parsing fails locally, confirm Tesseract and system libs are installed (Dockerfile lists apt packages).

How to contribute
-----------------

- Fork the repo, run tests (add tests when modifying core functionality), open PRs, and describe changes clearly.
- For model or data changes, include dataset provenance and intended use.

Useful file references
----------------------

- `apps/forensic_rag/utils.py` — HAI-DEF embedding and hybrid search implementation
- `apps/forensic_corpus/ingestion/parser.py` — document parsing entrypoints
- `apps/forensic_domain/precision.py` — domain precision and rule application
- `Dockerfile`, `docker-compose.yml` — containerized dev and bake steps
- `requirements.txt` — pinned Python dependencies

License
-------

Specify your project's license here (e.g., MIT, Apache-2.0). If none, add one to the repository.

Contact
-------

For questions about architecture or to request access to private services used for Vertex AI, contact the project owner or ops team.

----

This README is intended as a comprehensive starting point. If you want, I can now:
- Add architecture diagrams (Mermaid) to the README
- Generate a shorter quickstart `README_quick.md`
- Expand security & compliance checklist with PHI handling SOPs

System Snapshot (Med Gate Forensic Architecture V3)
-------------------------------------------------

No pages inside
Med Gate Forensic Architecture V3
Version: v2.1 (System Grade)
Status: 🟢 Production Ready
Type: Layered Deterministic Compliance Engine
Core: Immutable Knowledge Base + Context-Aware Retrieval + Deterministic Logic Gates

Executive summary
-----------------

MedGate is a forensic medical audit and compliance system designed to validate clinical, facility, and operational claims against authoritative medical protocols (NCCN, AHA, CMS, etc.). The platform intentionally separates Law (protocols), Fact (evidence), and Judgment (deterministic logic) so verdicts are auditable and hallucination-free. MedGemma (HAI-DEF) models are used for structural compilation, translation, and rendering — but NEVER to decide PASS/FAIL outcomes.

Key differentiators
-------------------

- Zero Hallucination by Construction: PASS / FAIL decisions are produced only by deterministic Python logic (Forensic Gates).
- Layered Architecture: Immutable knowledge, retrieval, reasoning, agentic workflows, and narrative are stratified so UI/agents can change independently of correctness.
- Scope- and Intent-Aware Enforcement: Clinical safety, facility/infrastructure compliance, and administrative concerns are separated to avoid false failures and prioritize safety.

Layered Model (detailed)
------------------------

MedGate uses four foundational layers plus an execution plane:

- Layer 0 — Immutable Knowledge Base (Ground Truth)
	- Contents: ClinicalProtocol documents, normalized `ForensicRule` objects, scope/intent tags, versioning and time windows, vector embeddings in `pgvector`.
	- Properties: Versioned, immutable, auditable, time-travel safe.

- Layer 1 — Context-Aware Retrieval & Cross-Referencing
	- Purpose: Determine which rules apply given scope, specialty, and time window.
	- Components: Audit planning, constrained RAG retrieval (structure + metadata only), deterministic filters on scope/specialty/temporal validity.
	- Models: Structural compiler uses a fine-tuned MedGemma (translator) to normalize ingested protocols into typed rules and logic-ready fragments.

- Layer 2 — Deterministic Reasoning Core (Forensic Gates)
	- Purpose: Execute rule-specific Python executors that apply math/logic to evidence.
	- Outputs: PASS / FAIL verdicts, executable traces, evidence chains, and machine-verifiable audit trails.
	- Note: This layer is data-source agnostic — PDFs, structured JSON, streaming IoT signals are treated uniformly as evidence.

- Layer 3 — Agentic Workflows (Thin Orchestration)
	- Purpose: Orchestrate audits, research queries, IoT streaming, and notification flows.
	- Modes: Forensic Audit (Strict Mode), Clinical Research (Discovery Mode), IoT Compliance Agent (continuous streaming). Agents compose layers but do not implement adjudication logic.

- Layer 4 — Narrative & Human Interface
	- Purpose: Render legal-grade explanations, human summaries, and PDF compliance reports.
	- Components: Fine-tuned MedGemma renderer(s) (MedGemma-Fine), MedGemma translator for structural compilation, and optional LLM fallbacks for non-decision text.

Core capabilities (expanded)
---------------------------

- Forensic Audit — Strict Mode
	- Accepts: PDFs, JSON, IoT streams
	- Produces: Deterministic PASS / FAIL with detailed evidence chains and a compliance matrix.

- Clinical Research — Discovery Mode
	- Purpose: Explore authoritative protocols without patient data and produce immutable clinical truths, with scope/intent metadata.

- Intelligent Protocol Ingestion
	- Pipeline: OCR (Docling / RapidOCR) → Structural Compiler (Fine-Tuned MedGemma translator) → Deterministic rule-typing (10 supported types) → Vector embedding (text-embedding-004) → Insert into Immutable KB.

- Smart IoT Compliance
	- Ingests facility sensors and patient-monitoring streams as evidence; applies forensic gates continuously or on schedule.

Data model (the constitution)
----------------------------

- `ClinicalProtocol`:
	- `specialty`, `version`, `validity_window`, provenance metadata
- `ForensicRule`:
	- `rule_code`, `rule_type`, `logic_config` (JSON), `scope_tags`, `intent_tags`, `embedding` (pgvector), `protocol` (FK)

MedGemma & HAI-DEF usage (what I missed and added)
-----------------------------------------------

- MedGemma roles in the system:
	- Structural Compiler (MedGemma-Translator): used in ingestion to convert raw protocol text into typed structured fragments and rule metadata. This is a fine-tuned MedGemma model optimized to emit deterministic schema outputs that feed the ForensicRule builder.
	- MedGemma Renderer (MedGemma-Fine): fine-tuned renderer that converts machine traces and evidence chains into professional PDF reports and legal-grade summaries (Layer 4).
	- Translation / Normalization: a separate MedGemma instance acts as translator to normalize local abbreviations and jurisdictional variants into canonical protocol language before embedding.

- Where the models live in repo:
	- `apps/llm_interface/medgemma_renderer.py` — renderer integrations and helper wrappers
	- `scripts/medgemma_training.py` and `scripts/medgemma_training_v1.py` — fine-tuning utilities and training harnesses

- Important rules:
	- LLMs (MedGemma or other HAI-DEF models) are used only for structuring, translation, and human-facing text; they are NOT used for adjudication.
	- All PASS/FAIL logic is executed by Python executors in the `forensic_domain` layer.

Model & embedding details
------------------------

- Embeddings: `text-embedding-004` is used for producing vector fingerprints inserted into `pgvector`. The repo also contains a specialized MedLM fallback (HAI-DEF medlm embeddings via Vertex). See `apps/forensic_rag/utils.py` for combined usage.
- LLM fallbacks: `Gemini 2.5 Flash` is used optionally as a fallback for non-critical rendering tasks.

Technology stack (reconciled)
----------------------------

Frontend
- Next.js 14 (App Router), TypeScript, Tailwind CSS

Backend
- Django + DRF, Python 3.11, Celery + Redis

Storage
- PostgreSQL 15 + pgvector, Google Cloud Storage (optional), Cloudinary

AI & ML
- Google Vertex AI (HAI-DEF): MedGemma (fine-tuned variants), medlm embeddings, `text-embedding-004`
- Local / Edge: `llama-cpp-python` (optional), CPU PyTorch targets for edge research

Integration points
------------------

- Vertex AI: Embeddings, MedGemma fine-tuning, rendering, and translator inference.
- IoT Gateways: Evidence ingestion endpoints for streaming telemetry.
- PostgreSQL: Rules, auditable trails, and vector indexes.
- WhatsApp / Twilio: Safety alerts and notification channels (mockable for tests).

MedGemma Impact Challenge — submission notes
-------------------------------------------

You are optimizing to win the MedGemma Impact Challenge. This repo is a strong baseline — to maximize judging criteria, ensure you supply:

- High-quality writeup (3 pages or less) that clearly documents:
	- Which HAI-DEF models you used and why (MedGemma-Translator, MedGemma-Fine, medlm embeddings)
	- Reproducible code and the exact training/fine-tuning commands and datasets (link to `scripts/medgemma_training.py`)
	- Quantitative evidence of model performance (retrieval precision, ingestion correctness, renderer fidelity)
- Public code repo or reproducible Docker container
- Short demo video (≤ 3 minutes) showing Strict Mode audit, ingestion pipeline, and rendered compliance report
- Optional: Hugging Face model trace to show open-weight lineage to HAI-DEF (if you publish a derived model)

Suggested deliverables I can prepare for the submission
------------------------------------------------------

- A concise 3-page writeup following the Kaggle template (I'll draft)
- A 3-minute demo script and suggested screencast plan
- A `README_quick.md` with only the commands needed for reviewers to run the demo (I can generate)
- A model-trace checklist for Hugging Face publishing (if you plan to publicize fine-tuned weights)

Next steps I can take now
------------------------

- Finalize README additions (this change)
- Produce `README_quick.md` with minimal run commands
- Draft the 3-page Kaggle writeup and a demo storyboard
- Generate Mermaid diagram SVG/PNG for inclusion in slide / writeup

If you'd like, I'll now:
- Generate `README_quick.md` and commit it
- Draft the 3-page writeup skeleton (first pass)
- Produce an SVG from the Mermaid diagram and add it to `docs/`


Architecture diagram
--------------------

```mermaid
flowchart LR
	subgraph Users
		U[Auditors / Engineers / Agents]
	end

	subgraph API
		A[Gunicorn / Uvicorn -> Django REST API]
	end

	subgraph Backend
		DA[apps.forensic_agent]
		DC[apps.forensic_corpus]
		DR[apps.forensic_rag]
		DD[apps.forensic_domain]
		LL[apps.llm_interface]
	end

	subgraph Infra
		PG[(Postgres + pgvector)]
		REDIS[Redis / Celery]
		CLOUD[Cloudinary]
		VERTEX[Vertex AI (HAI-DEF / MedLM)]
		DOC[Docling / PyPDFium]
		CHAIN[Optional: Blockchain Anchoring]
	end

	U --> A
	A --> DA
	A --> DC
	A --> DR
	A --> DD
	A --> LL
	DC --> DOC
	DR --> PG
	DR --> VERTEX
	DA --> REDIS
	DD --> PG
	LL --> VERTEX
	A --> CLOUD
	DD --> CHAIN
	style VERTEX fill:#fef3c7,stroke:#f59e0b
	style PG fill:#ecfeff,stroke:#06b6d4
```

Quickstart (Docker, minimal)
----------------------------

Follow these steps for a reproducible local dev environment using Docker Compose. These commands assume you're in the repository root.

1) Build & bring up containers (backend + postgres)

```bash
docker-compose up --build -d
```

2) Run migrations and create a superuser inside the running container (or run locally after installing deps):

```bash
docker-compose exec backend python manage.py migrate --noinput
docker-compose exec backend python manage.py createsuperuser
```

3) Optional: ingest a small sample or run the management commands

```bash
docker-compose exec backend python manage.py ingest_documents --help
docker-compose exec backend python manage.py generate_embeddings
```

4) Open the app at http://localhost:8000 (or whichever host/port you expose)

Quickstart (local, venv, Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

PHI handling & compliance checklist (expanded)
--------------------------------------------

The system processes clinical and administrative records. Follow these controls before using real PHI:

- Data minimization: only ingest fields required for the forensic task. Strip or redact unnecessary PHI at ingestion when possible.
- Access control & IAM:
	- Use least-privilege service accounts for GCP (Vertex AI) and database users.
	- Store service account JSON keys in a secrets manager (GCP Secret Manager, Vault) — do not commit keys.
- Network protection:
	- Run production services in a private VPC or behind a VPN.
	- Use private IPs for managed DB and restrict inbound access.
- Encryption:
	- Enable encryption at rest for Postgres storage and cloud buckets.
	- Enforce TLS for all network traffic and internal API calls.
- Audit logging & monitoring:
	- Enable DB audit logs and GCP audit logs for Vertex and storage access.
	- Centralize logs and monitor for anomalous access patterns.
- Data retention & deletion:
	- Define retention policies for ingested documents and embeddings.
	- Implement secure deletion / shredding procedures for expired data.
- Anonymization & pseudonymization:
	- When sharing datasets, remove direct identifiers and apply one-way pseudonymization for linking if needed.
- Local dev safety:
	- Never use production PHI in local dev containers. Use synthetic or sanitized datasets from `data/` for testing.
- Embeddings caution:
	- Embeddings can leak information if models or indexes are shared. Treat the `pgvector` store as sensitive; restrict access.
- Vertex AI keys & quotas:
	- Limit service account scopes, rotate keys regularly, and audit usage.
- Operational runbook:
	- Document who may approve PHI ingestion, contact for incident response, and recovery steps.
- Legal & compliance:
	- Obtain any necessary Data Processing Agreements (DPA) and ensure local/regional regulatory compliance (HIPAA, GDPR, etc.) before production use.

If you'd like, I can:
- Generate an SVG/PNG architecture diagram from the Mermaid and add it to the repo
- Create `README_quick.md` containing only the Quickstart steps
- Produce a formal PHI SOP template (approval flow, accounts, checklist)

