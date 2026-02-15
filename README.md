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

