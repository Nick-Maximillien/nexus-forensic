##  Overview

This Django service provides:

*  **Backend user models** and role-based profiles
*  **Persistent storage** for legal cases and documents
*  **REST APIs** for integration with frontend and auxiliary services
*  A **modular backend foundation** for experimentation and extension

It is intentionally **self-contained, stateless, and dockerised**, allowing it to be deployed independently or alongside other HakiChain services.

---

## 🎯 Purpose 

This backend is designed with specific boundaries to ensure modularity and scalability.

### ✅ What this backend IS
* A **domain backend** for legal workflows (users, cases, documents).
* A **system-of-record** for backend-managed entities.
* A service that can **mirror, enrich, or extend** auth and user data from external providers (e.g., Supabase).
* A clean **REST API layer** for frontend and service-to-service communication.

### ❌ What this backend IS NOT
* It does **not** replace Supabase.
* It is **not** a monolithic auth provider.
* It does **not** own frontend authentication UX.
* It does **not** orchestrate AI inference directly.

> **Note:** Supabase remains authoritative for primary user authentication, while Django handles backend domain logic, profiles, and workflows.

---

## ⚙️ Apps Overview

Each app is modular and isolated, enabling incremental evolution without tight coupling.

| App | Description |
| :--- | :--- |
| **users** | Backend user model, roles, profiles, and service-level auth. |
| **cases** | Legal case records, metadata, and lifecycle. |
| **documents** | Document uploads, metadata, and associations. |

---

## 🧠 Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Framework** | Django + DRF | Core backend logic and APIs. |
| **Database** | PostgreSQL | Relational persistence. |
| **Auth** | SimpleJWT | Service-level backend-to-backend authentication. |
| **Storage** | Local / Cloud | Document storage. |
| **Optional** | pgvector | Semantic retrieval / embeddings. |

---

## 🔌 API Structure

| Module | Base Endpoint | Purpose |
| :--- | :--- | :--- |
| **Users** | `/users/users/` | Profiles, roles, backend user data. |
| **Cases** | `/cases/cases/` | Case creation and retrieval. |
| **Documents** | `/documents/documents/` | Document management. |
| **Auth** | `/users/token/` | Service-level JWT access. |

---

## 🔑 Authentication Model 

1.  **Supabase** handles primary user authentication (email/password, OAuth).
2.  **Django** mirrors or enriches user data only when required.
3.  **JWTs** are used for service-level authentication, not frontend UX blocking.
4.  **Backend operations** are designed to be **eventually consistent**, avoiding synchronous dependencies.

This architecture prevents tight coupling and ensures frontend performance is not degraded if backend services are slow or temporarily unavailable.

---

## 📁 Project Structure

```text
medgate/
│
├── manage.py
├── medgate/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── users/
├── cases/
├── documents/
│
└── requirements.txt
⚙️ Environment VariablesCreate a .env file in the project root:Ini, TOMLSECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=postgres://user:password@localhost:5432/hakichain
ALLOWED_HOSTS=localhost,127.0.0.1
🧭 Setup InstructionsBash# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Run server
python manage.py runserver
🤝 Integration PointsServiceRoleInteractionSupabasePrimary AuthUser identity & sessions.Frontend (Next.js)UI / UXConsumes Django APIs.Web3 Service (Node.js)Wallet & SigningTriggered via HTTP.PostgreSQLPersistenceBackend storage.🛡️ Security NotesJWT-based service authentication.CORS & CSRF configured for trusted clients.No blocking external calls in the request lifecycle.Backend logic isolated from frontend auth latency.🌐 Architectural PositioningThis service represents the domain backend layer within HakiChain:Frontend: UX, auth flow, user interaction.Supabase: Identity & session management.Django: Domain logic, persistence, validation.Node.js Web3: Wallets, signing, blockchain I/O.AI / Agents: External or future services.🧭 SummaryThis Django backend is an exploratory but production-aware service designed to:Support legal domain workflows.Integrate cleanly with Supabase and other services.Remain deployable, dockerised, and loosely coupled.Evolve incrementally without architectural lock-in.It is a building block, not a replacement.