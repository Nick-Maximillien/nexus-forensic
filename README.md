Gemini said
Nexus Forensic
Overview
Nexus Forensic is a production-grade, Django-based forensic AI platform designed to validate clinical, facility, and operational claims against authoritative medical protocols (e.g., MoH, CMS, AHA).

The system operates on a neuro-symbolic architecture that enforces a strict separation between:

The Law (What must be true): Immutable Clinical Protocols and Facility Standards.

The Fact (What happened): Patient records, sensor telemetry, and administrative logs.

The Judgment (Adjudication): Deterministic Python logic gates that produce PASS/FAIL verdicts.

By using Google’s Health AI Developer Foundations (HAI-DEF) as specialized callable tools for structural compilation and semantic retrieval, Nexus Forensic eliminates LLM hallucinations in critical compliance outcomes.

High-Level Architecture (The Layered Model)
Nexus Forensic is organized into five foundational layers to ensure auditability and 1:1 reproducibility:

Layer 0 - Immutable Knowledge Base: Authoritative protocols are normalized into atomic ForensicRule objects with vector fingerprints stored in pgvector.

Layer 1 - Context-Aware Retrieval (RAG): Uses a hybrid search combining medlm-embeddings-v1 for clinical semantic fidelity and PostgreSQL SearchRank for symbolic keyword matching.

Layer 2 - Deterministic Reasoning Core: Rule-type-specific Python executors (Forensic Gates) process evidence against rules. LLMs are strictly forbidden from determining PASS/FAIL outcomes.

Layer 3 - Agentic Workflows: Orchestrates the system into three modes: Forensic Audit (Strict adjudication), Clinical Research (Discovery), and IoT Compliance (Real-time telemetry monitoring).

Layer 4 - Narrative and Human Interface: Utilizes the Base MedGemma model as a clinical narrator to convert machine-readable traces and evidence chains into legal-grade summaries.

HAI-DEF Integration and Callable Tools
Nexus Forensic utilizes Google's HAI-DEF models as modular, specialized components within the pipeline:

1. Clinical Semantic Retriever (medlm-embeddings-v1)
Generic embeddings often fail on medical abbreviations or jurisdictional nuances. We utilize medlm-embeddings-v1 to ensure that RAG retrieval captures specific clinical intent.

Location: apps/forensic_rag/utils.py

Implementation: Exponential backoff and jitter handle high-throughput ingestion quotas.

2. Structural Compiler (Fine-Tuned MedGemma)
The core neuro-symbolic bridge. This fine-tuned model converts raw, unstructured medical prose from PDFs into structured JSON logic compatible with the Layer 2 gates.

Location: apps/forensic_corpus/ingestion/llm_normalizer.py

Function: Compiles text into 10 deterministic types (Temporal, Threshold, Contraindication, etc.).

3. Clinical Narrator (Base MedGemma)
The narrator component. It receives the deterministic "Judgment Trace" from the Python logic gates and renders it into human-readable narratives for auditors.

Location: apps/llm_interface/medgemma_renderer.py

Technology Stack
Language: Python 3.11

Framework: Django 5.x + Django REST Framework

Database: PostgreSQL 15 + pgvector

Background Tasks: Celery + Redis

Document Parsing: Docling + PyPDFium (baked into Docker image)

Inference Engines:

Cloud: Google Vertex AI (MedGemma + MedLM Embeddings)

Edge: llama-cpp-python (8-bit quantized GGUF for offline research)
# Nexus Forensic

## Overview

Nexus Forensic is a production-grade, Django-based forensic AI platform that validates clinical, facility, and operational claims against authoritative medical protocols (e.g., MoH, CMS, AHA).

The system follows a neuro-symbolic architecture with a strict separation between:

- **The Law** (immutable clinical protocols and facility standards)
- **The Fact** (patient records, sensor telemetry, and administrative logs)
- **The Judgment** (deterministic Python logic gates that produce PASS/FAIL verdicts)

Google's Health AI Developer Foundations (HAI‑DEF) is used as specialized callable tools for structural compilation and clinical semantic retrieval—while deterministic logic gates always control final adjudication.

---

## High-Level Architecture (Layered Model)

1. **Layer 0 — Immutable Knowledge Base**: Authoritative protocols are normalized into `ForensicRule` objects with vector fingerprints stored in `pgvector`.
2. **Layer 1 — Context-Aware Retrieval (RAG)**: Hybrid search combining `medlm-embeddings-v1` for clinical semantic fidelity and PostgreSQL `SearchRank` for symbolic keyword matching.
3. **Layer 2 — Deterministic Reasoning Core**: Rule-type-specific Python executors (Forensic Gates) that process evidence against rules; LLMs do not decide PASS/FAIL.
4. **Layer 3 — Agentic Workflows**: Orchestrates Forensic Audit, Clinical Research, and IoT Compliance modes.
5. **Layer 4 — Narrative & Human Interface**: MedGemma renders machine-readable traces into legal-grade summaries and PDF reports.

---

## HAI-DEF Integration & Key Components

### Clinical Semantic Retriever — `medlm-embeddings-v1`

- Location: `apps/forensic_rag/utils.py`
- Notes: Uses Vertex AI's specialized medical embeddings. Batching with exponential backoff and jitter handles quota throttling. On repeated failure the system falls back to zero-vectors (768 dims) to preserve index alignment.

### Structural Compiler — Fine-tuned MedGemma

- Location: `apps/forensic_corpus/ingestion/llm_normalizer.py`
- Notes: Converts free-text clinical protocols into deterministic JSON logic (temporal, threshold, contraindication, etc.). The parser enforces strict JSON schemas and rejects malformed outputs.

### Clinical Narrator — MedGemma

- Location: `apps/llm_interface/medgemma_renderer.py`
- Notes: Produces human-readable audit reports and research summaries. Supports local (Ngrok / GGUF) and Vertex AI endpoint modes (`OFFLINE_EDGE` toggle).

---

## Technology Stack (short)

- Python 3.11
- Django 5.x + Django REST Framework
- PostgreSQL 15 + `pgvector`
- Celery + Redis (background tasks)
- Docling + PyPdfium (document parsing)
- Google Vertex AI (MedGemma, MedLM embeddings)
- Local edge option: `llama-cpp-python` + GGUF (medgate_brain_4b_Q8.gguf)

---

## Installation & Setup

### 1) Local (virtualenv)

Prerequisites: Python 3.11, PostgreSQL with `pgvector`, Redis.

```bash
git clone <repo-url>
cd nexus-forensic
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2) Database & migrations

```bash
# Copy or create a .env file with required env vars (see below)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### 3) Docker (recommended for reproducible builds)

- The `Dockerfile` installs a CPU PyTorch wheel and performs a BAKE step that runs a small Docling conversion to pre-download PyPdfium/docling models. This reduces first-run network calls and avoids runtime timeouts.
- `docker-compose.yml` uses `pgvector/pgvector:pg15` for Postgres + vector extension and mounts a GCP service account JSON for Vertex AI access.

```bash
docker-compose up --build
```

Important env vars to set (examples):

- `GOOGLE_APPLICATION_CREDENTIALS` — path to mounted GCP service account JSON
- `GCP_PROJECT_ID` — GCP project id
- `GCP_LOCATION` — e.g., `us-central1`
- `GCP_MEDGEMMA_ENDPOINT_ID` — Vertex AI endpoint id (for cloud MedGemma)
- `HF_HUB_OFFLINE` — set `1` in Docker to force docling to use baked cache
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER` — Twilio notifications

---

## Operational Pipelines & Common Commands

### Ingest a protocol (structural compilation)

```bash
python manage.py ingest_documents \
  --file data/moh_mch_handbook.pdf \
  --title "MOH Mother and Child Health Handbook" \
  --specialty pediatrics \
  --valid_from 2024-01-01
```

### Generate embeddings for corpus

```bash
python manage.py generate_embeddings
```

### Other management scripts

- `python manage.py generate_dataset` — dataset export for fine-tuning/analysis
- `python manage.py ingest_documents` — parse + compile PDFs into `ForensicRule`

### Start Celery worker (local)

```bash
# In a separate shell
celery -A medgate worker -l info
```

### Common Docker-related notes

- Docker BAKE step runs a minimal `DocumentConverter` pipeline to warm the docling cache. If you add/upgrade docling backends, rebuild the image.
- Docker Compose mounts the GCP SA JSON at `/app/secrets/gcp_sa.json` by default in `docker-compose.yml`.

---

## Retrieval & Embeddings — implementation notes

- Embeddings: `apps/forensic_rag/utils.py` uses Vertex AI `medlm-embeddings-v1` via `vertexai.language_models.TextEmbeddingModel`.
- Backoff strategy: exponential backoff with jitter; after retries the system returns zero-vectors of length 768 to preserve index alignment during bulk ingestion.
- Hybrid retrieval: the search combines PostgreSQL `SearchRank` on full-text fields with `pgvector` L2 distance. `hybrid_score = rank + 1/(vector_dist + 0.1)` is used to balance symbolic and semantic relevance.

---

## Local Edge Inference & MedGemma fine-tuning

- Local GGUF: The structural compiler supports an offline path that uses a local GGUF model (`medgate_brain_4b_Q8.gguf`) loaded via `llama-cpp-python`. The loader caps threads to avoid container thrashing.
- Conversion & training scripts:
  - `scripts/medgemma_conversion.py` — converts MedGemma HF weights → GGUF for local edge inference.
  - `scripts/medgemma_training.py` / `scripts/medgemma_training_v1.py` — training/fine-tuning helpers and notes. These scripts contain important licensing reminders (accept MedGemma license) and recommended tokenization/formatting.
  - `scripts/push_to_hf.py` — upload converted artifacts to a model hub (if permitted).

Toggle between local and cloud MedGemma with `OFFLINE_EDGE` in Django `settings.py` or via environment toggles in `apps/llm_interface/medgemma_renderer.py`.

---

## PHI & Compliance Guardrails

- **Data minimization**: LLMs only receive extracted events or sanitized excerpts, not raw patient identifiers.
- **Deterministic refusal**: If no governing protocol is found, the system refuses to return a verdict.
- **Audit logging**: Agent steps are recorded in `agent_trace` to allow exact 1:1 replay of a verdict for auditing.

Security note: Do not commit GCP service account keys or model artifacts into VCS. Use secrets manager or environment mounts for production.

---

## Important Files & Entry Points

- `apps/forensic_domain/precision.py` — Deterministic reasoning core (Forensic Gates)
- `apps/forensic_rag/utils.py` — HAI-DEF embedding loader and hybrid search
- `apps/forensic_agent/workflow.py` — Primary auditor agent orchestration
- `apps/forensic_corpus/ingestion/llm_normalizer.py` — Structural compiler and schema validation
- `apps/llm_interface/medgemma_renderer.py` — MedGemma-based narrative renderer
- `Dockerfile`, `docker-compose.yml` — build and orchestration with baked docling assets
- `requirements.txt` — pinned runtime dependencies (Docling, Vertex AI client, pgvector, llama-cpp-python, Celery)

---

## License & Model Use

Project code is proprietary. Use of Google's HAI‑DEF and MedGemma models is subject to Google's and Hugging Face's licensing terms — ensure you have accepted licenses before training or serving models.

