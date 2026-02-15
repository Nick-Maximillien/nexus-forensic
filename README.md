# Nexus Forensic

Forensic AI platform for validating clinical and operational claims against medical protocols.

## Overview

Nexus Forensic is a Django-based system that validates clinical, facility, and operational claims against medical protocols and standards. The platform separates evidence interpretation from adjudication logic:

- **Protocols**: Immutable medical standards stored as structured rules
- **Evidence**: Patient records, sensor telemetry, and administrative logs  
- **Judgment**: Deterministic Python logic gates for PASS/FAIL verdicts

Google's Health AI Developer Foundations (HAI-DEF) are used for document parsing and semantic retrieval, while Python logic gates control all final adjudication.

## Architecture

The system is organized in five layers:

| Layer | Component | Purpose |
|-------|-----------|---------|
| 0 | Knowledge Base | Store protocols as ForensicRule objects with embeddings |
| 1 | Retrieval (RAG) | Hybrid search: semantic + keyword matching |
| 2 | Logic Gates | Deterministic rule evaluation (no ML decisions) |
| 3 | Workflows | Audit, research, and IoT modes |
| 4 | Reporting | Generate audit reports and summaries |

## Key Components

### Clinical Embeddings (medlm-embeddings-v1)

- **Location**: pps/forensic_rag/utils.py
- **Function**: Vector representation of clinical text using Google's medical embedding model
- **Features**: Exponential backoff, fallback to zero-vectors on quota exhaustion

### Document Parser (MedGemma)

- **Location**: pps/forensic_corpus/ingestion/llm_normalizer.py
- **Function**: Parse unstructured medical text into structured logic rules
- **Output**: JSON with deterministic rule types (temporal, threshold, contraindication, etc.)
- **Validation**: Strict schema enforcement; malformed outputs rejected

### Report Generator (MedGemma)

- **Location**: pps/llm_interface/medgemma_renderer.py
- **Function**: Convert audit verdicts into human-readable reports
- **Modes**: Local (GGUF via llama-cpp-python) or cloud (Vertex AI endpoint)

## Technology Stack

- **Language**: Python 3.11
- **Framework**: Django 5.x + Django REST Framework
- **Database**: PostgreSQL 15 + pgvector extension
- **Tasks**: Celery + Redis
- **Document parsing**: Docling + PyPdfium
- **Cloud AI**: Google Vertex AI (MedGemma, MedLM embeddings)
- **Local inference**: llama-cpp-python (GGUF models)

## Installation

### Prerequisites

- Python 3.11
- PostgreSQL 15+ with pgvector
- Redis
- GCP service account (for Vertex AI access)

### Local Setup

`bash
git clone <repo-url>
cd nexus-forensic
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
`

### Docker Setup (Recommended)

`bash
docker-compose up --build
`

The Docker image includes:
- CPU PyTorch wheel pre-installed
- Docling asset caching ("bake" step) to avoid first-run delays
- pgvector PostgreSQL container

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| GOOGLE_APPLICATION_CREDENTIALS | Path to GCP service account JSON |
| GCP_PROJECT_ID | GCP project identifier |
| GCP_LOCATION | GCP region (e.g., us-central1) |
| GCP_MEDGEMMA_ENDPOINT_ID | Vertex AI endpoint ID |
| HF_HUB_OFFLINE | Set to 1 to use cached docling models |
| TWILIO_ACCOUNT_SID | Twilio API credentials |
| TWILIO_AUTH_TOKEN | Twilio API credentials |
| TWILIO_WHATSAPP_NUMBER | Notification phone number |
| DATABASE_URL | PostgreSQL connection string |
| REDIS_URL | Redis broker URL |

### OFFLINE_EDGE Toggle

Set OFFLINE_EDGE=True (default) to use local GGUF models. Set to False for cloud (Vertex AI) inference.

## Usage

### Ingest a Protocol

`bash
python manage.py ingest_documents \
  --file data/moh_handbook.pdf \
  --title "MOH Handbook" \
  --specialty pediatrics \
  --valid_from 2024-01-01
`

### Generate Embeddings

`bash
python manage.py generate_embeddings
`

### Start Background Worker

`bash
celery -A medgate worker -l info
`

### Other Commands

- python manage.py generate_dataset - Export data for analysis
- python manage.py repair_rules - Validate and fix rule format
- python manage.py stitch_kqmh_versions - Merge rule versions

## Technical Details

### Hybrid Retrieval Formula

`
hybrid_score = SearchRank + 1 / (L2_distance + 0.1)
`

Combines PostgreSQL full-text ranking with vector similarity to balance keyword and semantic matching.

### Embedding Fallback

If quota limits are hit after 6 retries, the system returns zero-vectors (768-dimensional) to maintain index consistency during bulk ingestion.

### Validation Schemas

The document parser enforces JSON schemas for:
- Temporal logic (event ordering)
- Threshold logic (vital sign ranges)
- Evidence sufficiency (required artifacts)
- Contraindications (unsafe combinations)
- Exclusivity (conflicting events)

Outputs that don't match schema are rejected.

## Compliance & Security

- **Data minimization**: LLMs receive extracted events only, not raw identifiers
- **Deterministic verdicts**: System refuses to judge if no governing protocol exists
- **Audit trail**: All agent steps logged in gent_trace for replay and verification
- **Secret management**: Use environment variables or mounted secrets; do not commit credentials

## File Structure

`
apps/
  forensic_domain/precision.py      - Logic gate implementations
  forensic_rag/utils.py              - Embedding and search
  forensic_agent/workflow.py         - Orchestration
  forensic_corpus/ingestion/         - Document parsing
  llm_interface/medgemma_renderer.py - Report generation
Dockerfile                           - Build with baked assets
docker-compose.yml                   - Orchestration
requirements.txt                     - Dependencies
`

## License

Project code is proprietary. Use of Google HAI-DEF and MedGemma models is subject to Google's and Hugging Face's licensing terms.
