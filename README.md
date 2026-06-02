# Nexorel Brand Intelligence — Hyperspell POC Dataset
**Therapeutic Area:** Oncology (NSCLC / EGFR+)
**Fictional Brand:** Nexorel (nexoratinib) by Aether Oncology, Inc.
**Purpose:** Synthetic pharma brand intelligence documents for Hyperspell POC

---

## The Application

A Flask app that puts a brand-intelligence UI on top of the Hyperspell memory layer.
It's a single service — the frontend (server-rendered UI) and the backend (JSON API)
are the same app at the same origin.

- **Live demo:** https://hyperspellpharmapoc.vercel.app (open demo mode — no login)
- **Frontend (UI):** `/`
- **Backend (API):** `/query`, `/global-query`, `/upload`, `/brands`, `/me`

**Features**
- Per-brand Q&A with **numbered citations** + relevance-score bars (grounded in the memory layer)
- **🌐 Global chat** — ask across all brands at once (no brand filter)
- **⬆ Document upload** — push new docs into a brand's memory layer (file or pasted text)
- **Keycloak OIDC auth** with admin/viewer roles (bypassable via `DEMO_MODE`)
- **Langfuse** tracing on every query/ingest

---

## Running Locally

```bash
# 1. Clone
git clone https://github.com/apurva-ship-it/hyperspell-pharma-poc.git
cd hyperspell-pharma-poc

# 2. Create your .env (it is gitignored — never committed)
cp .env.example .env
#    then edit .env and fill in at least HYPERSPELL_API_KEY and FLASK_SECRET_KEY
#    generate a secret: python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# 3. Install dependencies
pip3 install -r requirements.txt

# 4. Start Keycloak (auth) in Docker
docker-compose up -d          # Keycloak on http://localhost:8080 (realm: pharma-poc)

# 5. Run the app
python3 app.py                # → http://localhost:5001
```

**Shortcut — skip Keycloak entirely** (same demo mode as the live site, auto-login as admin):

```bash
DEMO_MODE=1 python3 app.py    # → http://localhost:5001
```

> **Note:** there is **no Anthropic/OpenAI key** in this project — answer generation is
> handled server-side by Hyperspell via the `answer=True` flag. The only AI credential
> is `HYPERSPELL_API_KEY`. See `DEPLOY.md` for hosting on Vercel.

---

## Documents Included

| File | Document Type | Key Content |
|---|---|---|
| `brand_plan_2026.md` | Annual Brand Plan | Strategy, SWOT, KPIs, budget, competitive overview |
| `competitive_intelligence.md` | CI Report | Deep competitor profiles (Tagrisso, Lazertinib+Ami, Aumolertinib) |
| `key_messages.md` | MLR-Approved Messages | Core claims, objection handlers, safety information |
| `patient_journey.md` | Journey Map | 5-stage patient journey with quotes, pain points, brand opportunities |
| `hcp_segmentation.md` | Targeting Guide | Tier definitions, KOL map, call planning |
| `medical_affairs_strategy.md` | MA Strategy | Publications plan, MSL deployment, trial pipeline |
| `market_research_insights.md` | Brand Tracker | Awareness metrics, prescribing barriers, payer research |
| `field_force_briefing.md` | Q2 Field Briefing | ASCO prep, campaign details, compliance reminders |

---

## Sample Queries to Test in Hyperspell

### Brand Strategy Questions
- "What is Nexorel's market share target for 2026?"
- "What are Nexorel's three strategic imperatives?"
- "How much budget is allocated to digital and omnichannel?"

### Competitive Intelligence
- "How does Nexorel compare to Tagrisso in CNS efficacy?"
- "What is Lazertinib's key weakness vs. Nexorel?"
- "When is aumolertinib expected to get FDA approval?"

### Medical/Clinical
- "What was the intracranial PFS for Nexorel in NEXUS-1?"
- "What is the Grade 3+ rash rate for Nexorel vs. osimertinib?"
- "What are the warnings and precautions for Nexorel?"

### Customer/Patient
- "Who are the top KOLs for Nexorel?"
- "What are the top barriers to Nexorel adoption among oncologists?"
- "What does the patient journey look like for EGFR+ NSCLC?"

### Field Operations
- "What is the Q2 2026 campaign theme?"
- "What data is being presented at ASCO 2026?"
- "How do reps handle payer step edit denials?"

---

## Observability (Langfuse)

The Flask app and CLI emit traces to [Langfuse](https://langfuse.com) when these env vars are set:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # or self-hosted URL
```

Leave them blank to run with tracing disabled.

**What gets traced**

| Trace name | Triggered by | Input | Output | Tags |
|---|---|---|---|---|
| `brand-query` | `POST /query` | `{question, brand}` | `{answer, sources, brand}` | `brand:<id>`, `query` |
| `brand-ingest` | `POST /ingest` | `{brand}` | `{count, brand, success}` | `brand:<id>`, `ingest` |
| `cli-ingest-nexorel` | `python ingest.py --brand nexorel` | titles + count | doc count | `brand:nexorel`, `ingest`, `cli` |
| `cli-ingest-brand` | `python ingest.py --brand <name>` | brand title | doc count | `brand:<id>`, `ingest`, `cli` |
| `cli-query` | `python ingest.py --query …` | `{question, brand}` | `{answer, sources}` | `brand:<id>`, `query`, `cli` |

Each trace contains a nested `hyperspell.memories.search` or `hyperspell.memories.add_bulk` span recording the underlying Hyperspell call, document count, and (for ingests) per-item statuses. Validation failures (`No question provided`, unknown brand, missing file) are recorded as `WARNING`-level spans; exceptions are recorded as `ERROR`-level with the message in `status_message`.
