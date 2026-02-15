# Nexus Forensic

**Deterministic Compliance Engine for Medical Claims using MedGemma and Google HAI-DEF**

> A forensic medical audit system that validates clinical, facility, and operational claims against authoritative health protocols. Unlike LLM-centric systems, Nexus Forensic enforces deterministic logic gates to eliminate hallucinations in compliance adjudication. Currently being piloted within the Kenyan healthcare ecosystem to enforce Ministry of Health (MoH) clinical guidelines and KQMH quality standards through computable medical law.

---

## Beyond Hallucination: The Structural Limits of Clinical Verification

Medical language models fail not primarily through hallucination, but through **verification failure**:

- Language models cannot enforce temporal ordering of events
- They cannot guarantee evidence completeness  
- They cannot deterministically refuse verdicts when proof is missing
- They lack auditability in regulated healthcare environments
- They cannot bridge the gap between probabilistic prose and deterministic adjudication.

This creates systemic risk in clinical audit trails, insurance documentation, and post-hoc medical investigations.

**Nexus Forensic solves this by separating evidence interpretation (where LLMs help) from adjudication logic (where only deterministic code decides).**

---

## Deployment & Artifacts

| Component | Platform | Environment / Link |
|-----------|----------|-------------------|
| **Frontend** | Vercel | [Live Dashboard](https://nexus-forensic.vercel.app) |
| **Backend API** | GCP Cloud Run | `https://nexus-forensic-571147915643.us-central1.run.app` |
| **Database** | Cloud SQL | PostgreSQL 15 + pgvector (GCP Managed) |
| **Fine-Tuning Workspace** | Kaggle | [MedGemma Forensic Trainer](https://www.kaggle.com/code/zicohubb/medgemma-impact-challenge-finetuning) |
| **Structural Compiler** | Hugging Face | [Nexus-Forensic-MedGemma-4B](https://huggingface.co/zico-hubb/nexus-forensic-medgemma-4b) |
| **Edge Artifact (GGUF)** | Hugging Face | [Nexus-Forensic-4B-GGUF](https://huggingface.co/zico-hubb/nexus-forensic-medgemma-4b-gguf) |

## Project Structure

For a complete breakdown of the codebase organization, including all directories, modules, and their purposes, see [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

**Quick Overview:**
- `apps/forensic_domain/` — Deterministic logic gates (Layer 2)
- `apps/forensic_corpus/` — Knowledge base and ingestion (Layer 0)
- `apps/forensic_rag/` — Retrieval and embeddings (Layer 1)
- `apps/forensic_agent/` — Orchestration and workflows (Layer 3)
- `apps/llm_interface/` — MedGemma narrative generation (Layer 4)
- `scripts/` — Fine-tuning, conversion, and training utilities
- `data/` — Training datasets and SQL exports

---

## What Nexus Forensic Does

## Core Capabilities

Nexus Forensic operates in three distinct modes to ensure healthcare integrity:

* **Forensic Audit (The Verifier):** Digitally "checks the homework" of a medical claim. It ensures that what was documented actually follows the medical law (protocols) and that the timeline of events is physically possible. Compliance is a critical requirement in Health and Insurance sectors.
* **Clinical Research (The Library):** A specialized search engine for medical protocols. It allows auditors, medical students & researchers to ask complex questions about MoH guidelines and receive answers that are 100% grounded in official documents, with zero "creative writing" from the AI.
* **Smart IoT Compliance (The Heartbeat):** Real-time monitoring of facility infrastructure. It allows a single county auditor to monitor the "vital signs" (Oxygen pressure, Backup power, Water levels) of every hospital in the region simultaneously, triggering alerts the moment a safety standard is violated.

---

## Why "Forensic" Science for Clinical Auditing?

Someone may ask: *Why apply forensic rules to a medical guideline?* In regulated healthcare and insurance, a medical record is a legal document. Nexus Forensic treats every patient encounter like an "evidence set." We apply **10 Deterministic Forensic Rules** to bridge the gap between prose and proof:

1.  **Temporal Consistency:** Cause must precede effect. (You cannot treat a condition before it is diagnosed).
2.  **Evidence Sufficiency:** Mandatory artifacts must exist. (You cannot bill for surgery without an anesthesia record).
3.  **Threshold Logic:** Numerical safety limits. (Oxygen must be administered if saturation is below a specific MoH % limit).
4.  **Contraindication:** Mutually exclusive treatments.
5.  **Exclusivity:** Conflicting event detection.
6.  **Data Integrity:** Duplicate event detection.
7.  **Conditional Existence:** Assertion-to-Proof coupling.
8.  **Protocol Validity:** Temporal metadata checks.
9.  **Count Sanity:** Outlier and fraud detection.
10. **Monotonic Ordering:** Timeline stability and anti-tampering.

---

## The Protocol Vault (Immune Knowledge Base)

Nexus Forensic is powered by a high-volume, cloud-hosted repository of medical authority. We have versioned and vectorized an exhaustive corpus to ensure the system is "Constitutional":

* **Kenyan National Guidelines:** MoH Clinical Manuals, MCH Handbooks, and NASCOP HIV treatment protocols (2022/2024 editions).
* **Quality Standards:** Full ingestion of the Kenya Quality Model for Health (KQMH) for Levels 1 through 6.
* **Global Authority:** Integrated WHO essential medicine lists and ECS (Emergency Care Systems) frameworks.
* **Infrastructure Law:** Deterministic building and safety codes for facility licensing.

Every rule in the vault is **immutable and versioned**. When a protocol is updated by the Ministry, the system "time-travels" to ensure old claims are audited against the rules that were active at the time of care, not the rules of today.

---

## Core Architecture — Layered Model

Nexus Forensic organizes compliance evaluation as **five independent layers**, enabling new capabilities without changing core logic.

| Layer | Component | Purpose |
|-------|-----------|---------|
| **0** | Immutable Knowledge Base | Normalized protocols as executable rules |
| **1** | Context-Aware Retrieval | Hybrid semantic + keyword search |
| **2** | Deterministic Logic Gates | Compliance via code only (no ML) |
| **3** | Agentic Workflows | Audit/Research/IoT orchestration |
| **4** | Narrative Rendering | Base MedGemma Clinical Narrator |


## Key Components

### Clinical Embeddings (medlm-embeddings-v1)

- **Location**: apps/forensic_rag/utils.py
- **Function**: Vector representation of clinical text using Google's medical embedding model
- **Features**: Exponential backoff, fallback to zero-vectors on quota exhaustion. medlm-embeddings-v1 is a specialized HAI-DEF Callable Tool utilized for clinical semantic fidelity where general models fail.

## Neurosymbolic Innovation

Nexus Forensic debuts the concept of a **Neurosymbolic Structural Compiler**. Unlike standard LLM implementations that output conversational text, our fine-tuned MedGemma model acts as a compiler that synthesizes human-readable medical law into a machine-executable Knowledge Graph.

### 1. Structural Compiler (Fine-Tuned MedGemma)
- **Role**: Program Synthesis.
- **Function**: Transforms unstructured MoH protocols into atomic `ForensicRule` nodes and causal edges.
- **Graph Topology**: Identifies entities (e.g., "Fibrinolytic Therapy") and directed constraints (e.g., "If [Chest Pain] AND [ECG == ST-Elevation] -> MUST [Administer within 30m]").
- **Output**: Validated JSON logic schemas for the Python Domain Gate Layer.
- **Proof of Concept**: `data/knmp2024_knowledge_graph.json` (National Malaria Policy 2024).

### 2. Clinical Narrator (Base MedGemma)
- **Role**: Natural Language Rendering.
- **Function**: Translates the "Judgment Trace" (the mathematical path taken through the Knowledge Graph) back into professional human prose.
- **Constraint**: The Narrator is strictly forbidden from determining PASS/FAIL; it only describes the deterministic outcome generated by the Logic Gates.

---


### Why Fine-Tuning Matters

While Base MedGemma is optimized for clinical dialogue, we utilize a  **Fine-Tuned adapter** to function as a **high-precision Structural Compiler** for forensic logic extraction and forensic audit specificity*:

#### Use Case: Knowledge Graph Generation & Protocol Compilation (Structural Compiler)

- **Problem**: To achieve zero-hallucination compliance, the Structural Compiler is trained to perform deterministic mapping of clinical prose to codified logic schemas.
- **Solution**: Fine-tune MedGemma to convert unstructured text → deterministic JSON
- **Training Data**: Medical protocols + target rule JSON schemas
- **Validation Gate**: Automatically reject outputs that violate schema


### Fine-Tuning Methodology

- **Base Model**: MedGemma 4B instruction-tuned (`medgemma-1.5-4b-it`)
- **Approach**: Parameter-efficient LoRA (Low-Rank Adaptation)
- **Preservation**: Base model weights frozen; only lightweight adapter trained
- **Inference**: Adapter loaded at runtime alongside base—no base weight modification
- **Edge Deployment**: Full fine-tuned model converted to GGUF format for offline inference (no cloud calls required)

---

## Agentic Workflow Innovation 

### A Deterministic Auditing Agent

Rather than conversational chat, Nexus Forensic implements a **forensic auditing agent** that:

1. **Injects audit scope** (specialty, time window, evidence categories, protocol families)
2. **Traverses the Knowledge Graph** via constrained RAG (Layer 1). Rather than a standard text search, the agent uses the Neurosymbolic Compiler outputs to identify the path of compliance through the governing protocols.
3. **Executes forensic gates** on all evidence (Layer 2 deterministic logic)
4. **Invokes the Clinical Narrator (Base MedGemma) to translate deterministic logic traces into human-readable forensic reports.** or explicit refusal (Layer 4 MedGemma rendering)
5. **Communicates state changes** via web app and closed-loop notifications (Twilio WhatsApp / Email)

**Agentic ochestration**: The agent composes rule-based and neural components to achieve audit completion while maintaining full transparency and auditability.

### Workflow States & Communication

| State | Trigger | Output |
|-------|---------|--------|
| `STATE_CLEARED` | Verdict == VALID | Certified audit report + MedGemma summary |
| `STATE_HALTED` | Verdict == INVALID | Forensic violation notice + gate traces |
| `STATE_INSUFFICIENT` | Evidence gaps detected | Explicit refusal + missing evidence list |

## Closed-Loop Communication (Twilio WhatsApp)

The Agentic Workflow is finalized by a real-time notification layer. The system complements the web dashboard with a "Forensic Terminal" pushing critical state changes directly to auditors:

* **Certified Audit Reports:** Upon reaching `STATE_CLEARED`, a digital certificate and MedGemma-rendered summary are dispatched via WhatsApp.
* **Violation Alerts:** If the Logic Gates reach `STATE_HALTED`, the specific rule code (e.g., KQMH-7.5) and the reason for failure are sent immediately.
* **IoT Critical Failures:** If a facility sensor (Oxygen/Power) drops below legal safety limits, a high-priority alert is triggered, allowing for regional intervention before patient harm occurs.

### Why This is Critical

- Reimagines complex medical audit workflows using HAI-DEF models as **callable, constrained tools** (not autonomous reasoners)
- Every audit step is logged and auditable
- Human operators see real-time state transitions and reasoning
- Agent failure modes are explicit, not hidden in probabilistic outputs

---

## Technology Stack

- **Language**: Python 3.11
- **Framework**: Django 5.x + Django REST Framework
- **Database**: PostgreSQL 15 + pgvector extension
- **Tasks**: Celery + Redis  
- **Document parsing**: Docling + PyPdfium (with offline caching in Docker)
- **Cloud AI**: Google Vertex AI (MedGemma, MedLM embeddings)
- **Local inference**: `llama-cpp-python` (Medgemma GGUF models for edge deployments)
- **Cloud Infrastructure**: Google Cloud Platform (GCP)
  - **Compute**: Cloud Run (Containerized Backend)
  - **Database**: Cloud SQL for PostgreSQL (pgvector enabled)
  - **AI Ecosystem**: Vertex AI Endpoint Management
- **Frontend**: Next.js 14 + Vercel Deployment
- **AI Models**: 
  - **HAI-DEF medlm-embeddings-v1**: Used as a callable tool for high-fidelity clinical RAG.
  - **Nexus-Forensic-4B**: Fine-tuned structural compiler.
  - **MedGemma 4B IT**: Base clinical narrator.
- **Fine-tuning Workspace**: Kaggle Data Science
- **Communication**: Twilio WhatsApp Business API (Real-time Forensic Alerts)
- **Infrastructure**: GCP Cloud SQL for PostgreSQL (Multi-regional high availability)
- **Edge Deployment**: Medgemma GGUF Quantized models for offline facility use

## Frontend-Backend Integration

The frontend (Next.js 14) communicates with the Nexus Forensic backend via a standardized JSON API.

### Endpoint: `POST /forensic/reasoning/`
The primary entry point for all forensic operations.

**Request Payload (`ForensicPayload`):**
```typescript
{
  "case_id": "string",
  "query": "string",
  "mode": "audit" | "research" | "iot_stream",
  "scope": "clinical" | "facility" | "billing" | "legal",
  "claim_data": {
    "events": [
      {
        "name": "string",
        "timestamp": "ISO-8601",
        "value": "number | string",
        "unit": "string",
        "type": "string"
      }
    ]
  }
}
```
**Expected Response (`ForensicResponse`):**
- The backend returns a comprehensive audit artifact, including the narrative explanation, deterministic evidence, and the agent's internal "thought trace."

````audit_result:``` Human-readable certification statements and compliance matrices.

```forensic_evidence:``` Immutable pass/fail rules and specific violation traces retrieved from the Knowledge Graph.

```agent_trace:``` A step-by-step execution log (INIT -> PLANNING -> RETRIEVAL -> REASONING -> RENDERING) for 1:1 auditability.


## Installation

### Prerequisites

- Python 3.11
- PostgreSQL 15+ with pgvector
- GCP service account (for Vertex AI access)

### Local Setup

```bash
git clone <repo-url>
cd nexus-forensic
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Docker Setup (Recommended)

```bash
docker-compose up --build
```

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

```bash
python manage.py ingest_documents \
  --file data/moh_handbook.pdf \
  --title "MOH Handbook" \
  --specialty pediatrics \
  --valid_from 2024-01-01
```

### Generate Embeddings

```bash
python manage.py generate_embeddings
```

### Start Background Worker

```bash
celery -A medgate worker -l info
```

### Other Commands

- python manage.py generate_dataset - Export data for analysis
- python manage.py repair_rules - Validate and fix rule format
- python manage.py stitch_kqmh_versions - Merge rule versions

## Technical Details

### Knowledge Graph Topology

The system treats medical guidelines as a directed graph. The Structural Compiler ensures that:

- Nodes: Represent atomic clinical requirements (e.g., "Conduct ECG").

- Edges: Represent temporal constraints or causal triggers (e.g., "within 10 minutes of chest pain").

- Adjudication: Compliance is determined by validating if the patient's evidence path satisfies the constraints defined in the Knowledge Graph.

### Embedding Fallback

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
- **Audit trail**: All agent steps logged in agent_trace for replay and verification
- **Secret management**: Use environment variables or mounted secrets; do not commit credentials


## License

Project code, fine-tuned model and its edge variant are open source. Knowledge base is proprietary. Use of Google HAI-DEF and MedGemma models is subject to Google's and Hugging Face's licensing terms.
