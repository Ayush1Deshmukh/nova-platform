# Nova Platform

**GoComet · Multi-Agent Trade Document Intelligence**

Three AI agents that extract, validate, and route trade documents — so CG operators review decisions, not PDFs.

---

## Prerequisites
- Python 3.10+
- Google Gemini API key (Free tier available at Google AI Studio)

## Quick Start

```bash
# 1. Clone and enter
git clone <repo-url> && cd nova-platform

# 2. Setup (creates venv, installs deps, inits DB)
chmod +x setup.sh && ./setup.sh

# 3. Add your API key
echo "GEMINI_API_KEY=your-key" >> .env

# 4. Generate sample documents
python3 scripts/generate_sample_docs.py

# 5. Run the UI
streamlit run ui/app.py --server.port 8501
```

## Running Each Component

### Streamlit UI (recommended)
```bash
streamlit run ui/app.py --server.port 8501
```
Open http://localhost:8501 — upload documents, view pipeline results, query data, and use the CG verification dashboard.

### FastAPI Server
```bash
python3 -m uvicorn api.server:app --reload --port 8000
```
API docs at http://localhost:8000/docs

### Email Trigger (simulated inbox)
```bash
python3 -c "
from pipeline.orchestrator import PipelineOrchestrator
from pipeline.email_trigger import EmailTrigger
from storage.database import init_db

db = init_db()
orch = PipelineOrchestrator(db=db)
trigger = EmailTrigger(orch)
trigger.simulate_email('sample_emails/email_1_clean')
"
```

## Architecture

```
Document → Extractor (Gemini Vision) → Validator (Gemini + rules) → Router (Gemini)
                                                                              ↓
                                                                    SQLite + Query Engine
                                                                              ↓
                                                                      Streamlit UI
```

- **Extractor Agent**: Takes PDF/image → outputs structured JSON with confidence scores per field
- **Validator Agent**: Compares extracted fields against customer rules → match/mismatch/uncertain per field
- **Router Agent**: Decides action → auto-approve, flag for review, or draft amendment email
- **Query Engine**: Natural language questions → SQL → human-readable answers

## Sample Queries

After processing documents, try these in the Query Data page:
- "How many documents were processed?"
- "Show all flagged shipments"
- "What is the average confidence score?"
- "Which documents were auto-approved?"
- "Show documents with mismatched HS codes"

## Sample Documents

| File | Type | Purpose |
|---|---|---|
| `sample_documents/clean_bill_of_lading.pdf` | Bill of Lading | Clean document, all fields valid |
| `sample_documents/clean_commercial_invoice.pdf` | Commercial Invoice | Clean document, matches all rules |
| `sample_documents/clean_packing_list.pdf` | Packing List | Clean document, consistent with BOL and invoice |
| `sample_documents/messy_commercial_invoice.pdf` | Commercial Invoice | Intentional errors: wrong consignee, invalid HS code, banned keywords, missing fields |

## Project Structure

```
nova-platform/
├── agents/                    # AI agents
│   ├── base_agent.py          # Base class with retry, cost tracking
│   ├── extractor_agent.py     # Vision LLM extraction
│   ├── validator_agent.py     # Rule-based validation
│   └── router_agent.py        # Decision + amendment drafting
├── pipeline/                  # Orchestration
│   ├── orchestrator.py        # Extract→Validate→Route pipeline
│   ├── state_manager.py       # Checkpoint/crash recovery
│   ├── email_trigger.py       # Folder watcher (simulated inbox)
│   └── cross_validator.py     # Multi-doc consistency check
├── storage/                   # Data layer
│   ├── models.py              # Pydantic models (shared)
│   ├── database.py            # SQLite via SQLAlchemy
│   └── query_engine.py        # NL → SQL → answer
├── api/
│   └── server.py              # FastAPI endpoints
├── ui/                        # Streamlit UI
│   ├── app.py                 # Dashboard
│   ├── pages/
│   │   ├── 1_Upload_Document.py
│   │   ├── 2_Pipeline_View.py
│   │   ├── 3_Query_Data.py
│   │   └── 4_CG_Verification.py
│   └── components/
│       ├── field_card.py       # Field rendering
│       └── email_draft.py      # Email draft component
├── config/
│   ├── customer_rules.json    # Validation rules
│   └── prompts.py             # All LLM prompts
├── docs/
│   ├── PRD_Part1.md
│   ├── PRD_Part2.md
│   └── Technical_Writeup.md
├── sample_documents/          # Generated test documents
├── sample_emails/             # Simulated inbox
├── scripts/
│   ├── generate_sample_docs.py
│   └── seed_rules.py
├── requirements.txt
├── setup.sh
└── .env.example
```

## Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| Extraction LLM | Gemini 2.5 Flash | Fast multimodal model with generous free tier |
| Validation/Routing LLM | Gemini 2.5 Flash | Free tier covers high volume pipeline processing |
| Orchestration | Custom Python | 3-agent linear pipeline, no framework needed |
| Storage | SQLite | Zero config, runs on laptop |
| UI | Streamlit | Fastest Python UI, no build step |
| API | FastAPI | Async, auto-docs |
| PDF Processing | PyMuPDF | Fast, no system deps |

## Cost Per Document
~\$0.02 - \$0.05 depending on page count and complexity.
