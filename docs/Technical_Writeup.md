# Technical Write-up: Nova Platform

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TRIGGER LAYER                                │
│  [Email Inbox / Folder Watch] ──→ [Email Trigger (watchdog)]       │
│  [UI Upload] ──→ [FastAPI /api/process]                            │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PIPELINE ORCHESTRATOR                             │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│  │ State    │    │ Extractor│    │ Validator│    │ Router   │     │
│  │ Manager  │◄──►│ Agent    │──►│ Agent    │──►│ Agent    │     │
│  │(JSON     │    │(GPT-4o   │    │(GPT-4o-  │    │(GPT-4o-  │     │
│  │ ckpts)   │    │ vision)  │    │ mini +   │    │ mini)    │     │
│  └──────────┘    └──────────┘    │ local    │    └──────────┘     │
│                       │          │ rules)   │         │            │
│                       │          └──────────┘         │            │
│                       │               │               │            │
│                  ExtractionResult  ValidationResult  RoutingDecision│
│                  (JSON handoff)   (JSON handoff)    (JSON handoff) │
└──────────────────────┬────────────────────────────────┬────────────┘
                       │                                │
        ┌──────────────┼────────────────┐               │
        ▼              ▼                ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  SQLite DB   │ │  Checkpoint  │ │ Cross-Doc    │ │  Query       │
│  (pipeline_  │ │  Files       │ │ Validator    │ │  Engine      │
│  runs, fields│ │  (crash      │ │ (multi-doc   │ │  (NL→SQL     │
│  validations │ │  recovery)   │ │ consistency) │ │  via GPT-4o  │
│  shipments)  │ │              │ │              │ │  -mini)      │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
        │                                               │
        └───────────────────┬───────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         UI LAYER (Streamlit)                        │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐     │
│  │ Dashboard  │ │ Upload &   │ │ Pipeline   │ │ CG Verifi- │     │
│  │ (KPIs,     │ │ Process    │ │ View       │ │ cation     │     │
│  │  metrics)  │ │ (single    │ │ (run       │ │ (4 states, │     │
│  │            │ │  doc)      │ │  detail)   │ │  email     │     │
│  │            │ │            │ │            │ │  drafts)   │     │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘     │
│                                  ┌────────────┐                    │
│                                  │ NL Query   │                    │
│                                  │ (ask in    │                    │
│                                  │  English)  │                    │
│                                  └────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Three Nastiest Failure Modes (From Testing)

### 1. Corrupted/Unreadable PDF
- **Symptom:** PyMuPDF returns blank pages or throws `fitz.FileDataError`
- **Impact:** Extractor sends blank image to GPT-4o, which hallucinates a complete document
- **Fix:** Check pixmap pixel variance before sending — if all pixels are similar (blank page), skip that page. If zero valid pages, mark extraction as FAILED with confidence 0.0. Never send a blank image to the vision model.

### 2. LLM Returns Invalid JSON
- **Symptom:** GPT-4o returns markdown-wrapped JSON or adds commentary outside the JSON block
- **Impact:** `json.loads()` fails, pipeline crashes
- **Fix:** Three-layer defense:
  1. Use `response_format={"type": "json_object"}` (forces valid JSON)
  2. If that fails, regex-extract JSON from response (`{...}` pattern)
  3. If that fails, retry with explicit "output ONLY valid JSON, no other text" instruction
  4. After 3 failures, mark as FAILED — never guess

### 3. Field Present But Ambiguous
- **Symptom:** Document shows "Consignee: Meridian Global Imports Ltd. c/o ABC Logistics" — model extracts "Meridian Global Imports Ltd. c/o ABC Logistics" but rule expects "Meridian Global Imports Ltd."
- **Impact:** Fuzzy match might pass (0.78 ratio) or fail depending on threshold
- **Fix:** Validator uses both local fuzzy match AND LLM reasoning. If local check is borderline (0.75-0.90), falls back to LLM with the specific context. LLM can understand "c/o" is a care-of notation, not part of the company name. If still uncertain, flag as UNCERTAIN — never silently approve ambiguous matches.

---

## Observability (Production at 50 Customers)

### Tracing a Single Shipment
Every pipeline run gets a UUID (`run_id`). Every log line includes `[run_id]`. To trace from email to verified output:

```
1. Email arrives → EmailTrigger logs [shipment_id] with email metadata
2. Each document → PipelineOrchestrator logs [run_id] [shipment_id]
3. Each agent step → BaseAgent logs [run_id] with model, latency, cost
4. Final decision → Database stores with run_id as primary key
5. Query: SELECT * FROM pipeline_runs WHERE run_id = '<id>'
```

### Dashboard Metrics
| Panel | Metric | Source |
|---|---|---|
| Queue Depth | Documents pending processing | `SELECT COUNT(*) FROM pipeline_runs WHERE status IN ('pending','extracting','validating','routing')` |
| Error Rate (1h) | Failed runs / total runs | pipeline_runs table, last 1 hour |
| Avg Latency | P50, P95 processing time | `processing_time_ms` column |
| Cost Tracker | Daily/weekly cost by customer | `total_cost_usd` column, grouped by customer_id |
| Approval Rate | Auto-approved vs flagged vs amended | `decision` column distribution |
| Model Health | Token usage, error rate per model | Agent-level logging |

---

## Cost Analysis (Back-of-Envelope)

| Step | Model | Tokens (est.) | Cost |
|---|---|---|---|
| Extraction (1-page doc) | GPT-4o | ~1500 input (image) + ~500 output | ~\$0.015 |
| Extraction (3-page doc) | GPT-4o | ~4000 input + ~500 output | ~\$0.028 |
| Validation | GPT-4o-mini | ~800 input + ~400 output | ~\$0.0004 |
| Routing | GPT-4o-mini | ~600 input + ~300 output | ~\$0.0003 |
| Query (if used) | GPT-4o-mini | ~500 input + ~200 output | ~\$0.0002 |

**Total per document: ~\$0.02 - \$0.03 (clean) / ~\$0.04 - \$0.05 (with amendment drafting)**
**At 1000 docs/day: ~\$30/day**

### Where cost blows up:
- Multi-page scanned documents (each page = one vision API call)
- Retry loops on bad JSON (3x cost per retry)
- Cross-document validation on large shipments (N documents × M rules)

### Cost controls:
- Per-document cost cap (\$0.50)
- Per-customer daily budget
- Model downgrade for validation/routing (already using mini)
- Caching: identical documents (by hash) skip re-extraction

---

## Latency Analysis

| Step | Typical | Worst Case | Bottleneck |
|---|---|---|---|
| PDF→Image conversion | 200ms | 2s (large PDF) | CPU, disk I/O |
| Extraction (GPT-4o vision) | 2-5s | 15s | API latency, image size |
| Validation (GPT-4o-mini) | 0.5-1s | 3s | API latency |
| Routing (GPT-4o-mini) | 0.5-1s | 3s | API latency |
| DB write | 10ms | 50ms | Disk I/O |
| **Total** | **3-8s** | **25s** | **Extraction** |

### How to fix the slowest hop (Extraction):
1. **Parallel page processing** — send all pages simultaneously, aggregate results
2. **Image compression** — resize to max 2000px before sending (reduces token count)
3. **Caching** — hash the document, skip extraction if seen before
4. **Model selection** — use GPT-4o-mini for clearly typed documents, GPT-4o only for scans

---

## What I Would Do Differently With a Week

1. **Proper eval dataset** — Build 100+ annotated documents with ground-truth fields. Run automated precision/recall tests on every code change.
2. **Real email integration** — Connect to Gmail/Outlook API via OAuth, process incoming emails automatically, send amendment replies through the same channel.
3. **Multi-language OCR fallback** — Add Tesseract OCR as a pre-processing step for non-English documents, feed extracted text alongside the image to GPT-4o.
4. **Customer rule UI** — Let CG operators add/edit validation rules through a web interface instead of editing JSON files.
5. **Batch processing** — Process 50+ documents in parallel with a progress dashboard, bulk approve/reject.
6. **Proper error recovery** — Instead of just checkpointing, implement proper retry queues with dead-letter handling for persistently failing documents.
