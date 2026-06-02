# Nexorel Brand Intelligence — Hyperspell POC Dataset
**Therapeutic Area:** Oncology (NSCLC / EGFR+)
**Fictional Brand:** Nexorel (nexoratinib) by Aether Oncology, Inc.
**Purpose:** Synthetic pharma brand intelligence documents for Hyperspell POC

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
