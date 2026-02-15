# Nexus Forensic — Project Structure

## Directory Tree

```
nexus-forensic/
├── README.md                          # Main project documentation
├── PROJECT_STRUCTURE.md               # Project Structure
├── manage.py                          # Django CLI entry point
├── requirements.txt                   # Python dependencies
├── Dockerfile                         # Container build specification
├── docker-compose.yml                 # Multi-container orchestration
├── .env                               # Environment variables (not in VCS)
├── .gitignore                         # Git ignore rules
├── .dockerignore                      # Docker build exclusions
│
├── nexus-forensic/                    # Django project configuration
│   ├── __init__.py
│   ├── settings.py                    # Django settings (DB, apps, middleware, etc.)
│   ├── urls.py                        # Root URL routing
│   ├── wsgi.py                        # WSGI application entry point
│   ├── asgi.py                        # ASGI application entry point
│   └── __pycache__/
│
├── apps/                              # Django applications
│   │
│   ├── forensic_agent/                # Orchestration & Workflow Management
│   │   ├── __init__.py
│   │   ├── apps.py                    # Django app config
│   │   ├── models.py                  # Audit task, evidence, verdict models
│   │   ├── views.py                   # API endpoints for audit operations
│   │   ├── urls.py                    # URL routing
│   │   ├── workflow.py                # Main auditor agent orchestration logic
│   │   ├── extraction.py              # Evidence extraction & parsing
│   │   ├── communication.py           # Twilio/WhatsApp notification dispatcher
│   │   ├── research.py                # Clinical research mode (no adjudication)
│   │   ├── iot_agent.py               # Real-time IoT telemetry processing
│   │   ├── migrations/                # Django migration history
│   │   └── __pycache__/
│   │
│   ├── forensic_domain/               # Core Compliance Logic (Layer 2)
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── precision.py               # Deterministic reasoning gates (CRITICAL)
│   │   │                              # - temporal_logic validator
│   │   │                              # - threshold validator
│   │   │                              # - evidence sufficiency checker
│   │   │                              # - contraindication enforcer
│   │   │                              # - exclusivity validator
│   │   │                              # - duplicate detection
│   │   │                              # - conditional existence logic
│   │   ├── contract.py                # Verdict data structures & contracts
│   │   └── __pycache__/
│   │
│   ├── forensic_corpus/               # Knowledge Base Management (Layer 0)
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py                  # ForensicRule, ClinicalProtocol, ProtocolVersion
│   │   ├── migrations/                # Django migration history
│   │   │
│   │   ├── ingestion/                 # Document parsing & structural compilation
│   │   │   ├── parser.py              # Docling-based PDF extraction
│   │   │   └── llm_normalizer.py      # MedGemma-powered rule compilation
│   │   │                              # - Supports local (GGUF) and cloud (Vertex AI)
│   │   │                              # - Outputs deterministic JSON rule schemas
│   │   │
│   │   ├── management/
│   │   │   └── commands/              # Django management commands
│   │   │       ├── ingest_documents.py    # Parse PDF → ForensicRule ingestion
│   │   │       ├── generate_embeddings.py # Batch vectorization via Vertex AI
│   │   │       ├── generate_dataset.py    # Export data for analysis/fine-tuning
│   │   │       ├── repair_rules.py        # Fix malformed rule schemas
│   │   │       └── stitch_kqmh_versions.py # Merge rule versions
│   │   │
│   │   └── __pycache__/
│   │
│   ├── forensic_rag/                  # Retrieval & Context (Layer 1)
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── utils.py                   # CRITICAL: HAI-DEF embedding loader
│   │   │                              # - Vertex AI medlm-embeddings-v1 initialization
│   │   │                              # - Exponential backoff & quota handling
│   │   │                              # - Batch embedding generation
│   │   │                              # - Zero-vector fallback on exhaustion
│   │   ├── retrieval.py               # Hybrid RAG engine
│   │   │                              # - Semantic search (pgvector L2 distance)
│   │   │                              # - Keyword search (PostgreSQL SearchRank)
│   │   │                              # - Deterministic rule filtering
│   │   │                              # - Scope & intent tagging
│   │   └── __pycache__/
│   │
│   ├── llm_interface/                 # Language Model Integration (Layer 4)
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── medgemma_renderer.py       # Fine-tuned MedGemma narrative generation
│   │   │                              # - Local inference (llama-cpp-python GGUF)
│   │   │                              # - Cloud inference (Vertex AI endpoint)
│   │   │                              # - OFFLINE_EDGE toggle for local/cloud switch
│   │   │                              # - Post-verdict rendering only (sandboxed)
│   │   └── __pycache__/
│   │
│   ├── users/                         # Authentication & User Management
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py                  # User, Token, Permission models
│   │   ├── views.py                   # Authentication endpoints
│   │   ├── urls.py                    # User URL routing
│   │   ├── serializers.py             # DRF serializers
│   │   ├── signals.py                 # User creation signals (e.g., key generation)
│   │   ├── admin.py                   # Django admin customization
│   │   ├── utils.py                   # Password, encryption utilities
│   │   ├── tests.py                   # Unit tests
│   │   │
│   │   ├── management/
│   │   │   └── commands/
│   │   │       └── fetch_drone_data.py # IoT data ingestion helper
│   │   │
│   │   ├── migrations/                # Django migration history
│   │   └── __pycache__/
│   │
│   └── [Future apps]                  # Additional modules as needed
│
├── scripts/                           # Standalone utilities & fine-tuning
│   ├── medgemma_training.py           # MedGemma fine-tuning trainer (standard)
│   ├── medgemma_training_v1.py        # MedGemma fine-tuning trainer (turbo variant)
│   ├── medgemma_conversion.py         # HuggingFace weights → GGUF converter
│   ├── push_to_hf.py                  # Upload fine-tuned models to Hugging Face
│   ├── rules.py                       # Batch rule parsing helper
│   ├── Refined.py                     # Refined rule extraction pipeline
│   ├── conversion.py                  # Data format conversion utilities
│   └── verification.py                # Validation & verification scripts
│
├── data/                              # Training & knowledge base datasets
│   ├── nexus_finetune_FINAL.jsonl     # Fine-tuning dataset (rules + examples)
│   ├── nexus_raw_audit.jsonl          # Raw audit log data
│   ├── clean_brain_v2.sql             # Full audit database export (v2)
│   ├── clean_brain.sql                # Full audit database export (v1)
│   ├── cleaned_surgical_data.sql      # Surgical specialty rules & traces
│   ├── surgical_data.sql              # Raw surgical data (before cleaning)
│   ├── local_data.sql                 # Local development snapshot
│   └── knmp2024_knowledge_graph.json  # Knowledge graph for clinical reasoning
│
├── base_models/                       # Pre-trained model artifacts (optional)
│   └── [Model checkpoints, weights]
│
└── corpus/                            # Clinical protocol document repository
    ├── kenyan_corpus/                 # Kenya-specific protocols & standards
    └── [Other regional protocols]
```

---

## Layer Mapping

### Layer 0 — Immutable Knowledge Base
**Directory**: `apps/forensic_corpus/`
- **models.py**: `ForensicRule`, `ClinicalProtocol`, `ProtocolVersion`
- **ingestion/parser.py**: Docling-based PDF extraction
- **ingestion/llm_normalizer.py**: MedGemma structural compilation
- **Database**: PostgreSQL (ForensicRule table with pgvector embeddings)

### Layer 1 — Context-Aware Retrieval
**Directory**: `apps/forensic_rag/`
- **utils.py**: Vertex AI embedding loader & batch generation
- **retrieval.py**: Hybrid search (semantic + keyword)
- **Database**: PostgreSQL with pgvector L2 distance search

### Layer 2 — Deterministic Reasoning Core
**Directory**: `apps/forensic_domain/`
- **precision.py**: ForensicGateLayer with all validation logic
- **contract.py**: ForensicVerdict and rule execution contracts
- **No external AI calls** — pure Python logic

### Layer 3 — Agentic Workflows
**Directory**: `apps/forensic_agent/`
- **workflow.py**: Main auditor agent orchestration
- **models.py**: AuditTask, EvidenceItem, VerdictResult
- **extraction.py**: Evidence parsing from PDFs/JSON
- **iot_agent.py**: Real-time telemetry processing
- **research.py**: Discovery mode (no adjudication)

### Layer 4 — Narrative & Human Interface
**Directory**: `apps/llm_interface/`
- **medgemma_renderer.py**: Fine-tuned MedGemma narrative generation
- **Local inference**: GGUF via llama-cpp-python
- **Cloud inference**: Vertex AI endpoint
- **Post-verdict rendering only** (sandboxed)

---

## Key Files by Function

### Configuration & Entry Points
- `manage.py` — Django CLI
- `nexus-forensic/settings.py` — Django configuration, installed apps, database, API keys
- `nexus-forensic/urls.py` — Root URL dispatcher
- `Dockerfile` — Container build with docling bake step
- `docker-compose.yml` — PostgreSQL + backend orchestration
- `requirements.txt` — Python dependencies (Django, Vertex AI, pgvector, etc.)

### Core Forensic Logic
- `apps/forensic_domain/precision.py` — **THE JUDGE** (all compliance verdicts)
- `apps/forensic_domain/contract.py` — Verdict & trace data structures
- `apps/forensic_rag/utils.py` — Embedding & retrieval initialization
- `apps/llm_interface/medgemma_renderer.py` — Narrative generation

### Orchestration & APIs
- `apps/forensic_agent/workflow.py` — Audit lifecycle management
- `apps/forensic_agent/views.py` — REST endpoints
- `apps/forensic_agent/models.py` — Audit task & verdict models
- `apps/forensic_agent/communication.py` — Notification dispatcher

### Knowledge Base Ingestion
- `apps/forensic_corpus/ingestion/parser.py` — Docling PDF extraction
- `apps/forensic_corpus/ingestion/llm_normalizer.py` — MedGemma rule compilation
- `apps/forensic_corpus/management/commands/ingest_documents.py` — Ingestion pipeline
- `apps/forensic_corpus/management/commands/generate_embeddings.py` — Batch vectorization

### Model Training & Conversion
- `scripts/medgemma_training.py` — Fine-tune MedGemma on domain data
- `scripts/medgemma_conversion.py` — Convert HF weights to GGUF
- `scripts/push_to_hf.py` — Upload fine-tuned models
- `data/nexus_finetune_FINAL.jsonl` — Fine-tuning dataset

---

## Database Schema (PostgreSQL)

### Core Tables
- `forensic_corpus_clinicalprotocol` — Protocol metadata (specialty, version, validity)
- `forensic_corpus_forensicrule` — Atomic rules with logic_config JSON and embeddings
- `forensic_agent_audittask` — Audit job tracking
- `forensic_agent_auditevidenceitem` — Evidence entries (PDFs, JSON, sensor data)
- `forensic_agent_auditverdict` — Final verdicts and traces
- `users_user` — User accounts and API keys

### Vector Tables
- `forensic_corpus_forensicrule` includes `embedding` (pgvector, 768-dim)
- Indexed for L2 distance nearest-neighbor search

---

## Environment Variables

### GCP Configuration
```
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp_sa.json
GCP_PROJECT_ID=your-gcp-project
GCP_LOCATION=us-central1
GCP_MEDGEMMA_ENDPOINT_ID=xyz123
```

### Database
```
DATABASE_URL=postgres://user:pass@db:5432/medgate_db
REDIS_URL=redis://redis:6379
```

### AI/ML
```
OFFLINE_EDGE=True                # Use local GGUF (True) or cloud Vertex (False)
HF_HUB_OFFLINE=1                 # Force docling to use baked cache
```

### Notifications
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

---

## Running the System

### Local Development
```bash
python manage.py migrate
python manage.py runserver
celery -A medgate worker -l info  # (in separate terminal)
```

### Docker Production
```bash
docker-compose up --build
```

### Data Ingestion
```bash
python manage.py ingest_documents --file data/protocol.pdf --title "Protocol Name"
python manage.py generate_embeddings
```

### Model Fine-Tuning
```bash
python scripts/medgemma_training.py --data data/nexus_finetune_FINAL.jsonl
python scripts/medgemma_conversion.py --input model.bin --output model.gguf
```

---

## MedGemma Impact Challenge Focus

### Key Innovation Points

1. **Fine-Tuned MedGemma as Constrained Renderer** (`apps/llm_interface/medgemma_renderer.py`)
   - Novel Task Prize candidate
   - Trained on forensic transformation only
   - Zero diagnostic reasoning

2. **Agentic Workflow** (`apps/forensic_agent/workflow.py`)
   - Deterministic agent orchestration
   - Closed-loop communication via Twilio
   - Agentic Workflow Prize candidate

3. **Edge AI** (`scripts/medgemma_conversion.py`)
   - GGUF conversion for local inference
   - llama-cpp-python integration
   - Edge AI Prize candidate

4. **HAI-DEF Integration**
   - MedLM embeddings (Layer 1)
   - MedGemma fine-tuning (Layer 4)
   - Vertex AI endpoints (fallback)

---

## Development Workflow

### Adding a New Feature
1. Create Django model in appropriate `models.py`
2. Generate migration: `python manage.py makemigrations`
3. Add business logic (e.g., gate validation in `precision.py`)
4. Expose via REST endpoint in `views.py`
5. Add URL routing in `urls.py`

### Testing
```bash
python manage.py test apps.forensic_domain  # Test forense gates
python manage.py test apps.forensic_rag     # Test retrieval
```

### Debugging Audits
- Check `apps/forensic_agent/models.py` for `AuditTask.agent_trace` (JSON)
- Each step logged with timestamp and status
- Fully reproducible from stored trace

---

## Notes

- **Never modify Layer 2** (`precision.py`) without understanding forensic implications
- **Layer 0 is append-only** — rules are never deleted, only versioned
- **All embeddings are 768-dimensional** (pgvector constraint)
- **Docling caching** is essential for reproducible builds (Dockerfile BAKE step)
- **OFFLINE_EDGE toggle** should be tested before production switches
- **Audit traces are immutable** — stored as JSON for completeness

---

**Last Updated:** February 16, 2026  
**Challenge Target:** Google MedGemma Impact Challenge  
**Tracks:** Agentic Workflow Prize, Novel Task Prize, Edge AI Prize
