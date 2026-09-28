# PRD Part 1: Nova Platform — Multi-Agent Trade Document Pipeline

---

## 1. Nova Understanding

### What is Nova?
Nova is GoComet's AI-native logistics intelligence platform. Unlike traditional SaaS that digitizes existing workflows, Nova deploys AI agents that autonomously execute logistics tasks — document validation, shipment tracking, exception handling. Traditional SaaS gives you dashboards to look at; Nova gives you outcomes. It solves the problem of logistics being too fragmented, too manual, and too dependent on tribal knowledge for any single software tool to address. Each customer has different rules, different workflows, different exceptions. A traditional SaaS product would need infinite configuration. Nova deploys intelligent agents that learn and adapt to each customer's specific context.

### What is the FDE (Forward Deployed Engineer) model and why does GoComet use it?
Forward Deployed Engineers sit with the customer, understand their specific workflows, and configure/extend Nova for that customer's context. GoComet uses FDEs because logistics is not one-size-fits-all. Every customer has unique trade routes, document requirements, compliance rules, and exception handling procedures. An FDE bridges the gap between Nova's AI capabilities and the customer's specific operational reality. They don't just implement — they discover what the customer actually needs vs what they say they need. The FDE model turns Nova from a product into a service-wrapped outcome engine — each deployment is tuned to the customer's exact operational shape, which is why it outperforms horizontal SaaS tools that ship generic features.

### What does "System of Outcomes" mean?
- **System of Record** stores data (ERP, TMS). You look things up.
- **System of Engagement** helps people interact with data (dashboards, notifications, alerts). You look at things.
- **System of Outcomes** actually does the work and delivers results. You review what was done.

Nova is a System of Outcomes because it doesn't just show you that a document has a mismatch — it validates the document, identifies the discrepancy, drafts the amendment, and routes it for approval. The operator's job shifts from doing the work to reviewing the agent's work. The measure of success is not "did the user see the alert?" — it's "was the shipment cleared correctly and on time?"

---

## 2. Problem Statement

### Where does the current trade-doc validation flow break?
| Failure Mode | Impact | Frequency |
|---|---|---|
| Manual field-by-field reading | 3-5 minutes per document, error-prone under fatigue | Every document |
| Rules live in tribal knowledge | New CG hires make mistakes for weeks, inconsistent validation across team | Every new hire, every handoff |
| 2-4 amendment cycles per shipment | 4-24 hours delay per cycle, compounds across supply chain | 40-60% of shipments |
| No audit trail | Cannot prove why a document was approved/rejected; dispute risk | Every disputed shipment |
| No visibility into queue depth | Manager cannot answer "how many docs are pending?" without counting emails | Daily |
| CG bandwidth bottleneck | One person can validate ~50 docs/day max; throughput caps growth | Structural |
| Copy-paste errors in amendment emails | CG types wrong field reference, causing confusion for supplier | ~15% of amendments |

### What does success look like for a CG operator in their first 5 minutes?
1. Upload a document (or have it arrive via email)
2. See all fields extracted with confidence scores in <30 seconds
3. See a clear field-by-field validation result (match/mismatch/uncertain)
4. See exactly which fields failed and why — with found vs. expected values
5. Get a ready-to-send amendment email — or an auto-approval confirmation
6. All of this without typing a single keystroke

---

## 3. Users + Jobs-to-be-Done

### Personas

**CG Operator (Cargo/Control Group Validator)**
- Mid-career logistics professional, validates 50-100 documents per day
- Works primarily in email (Outlook/Gmail), opens PDFs manually
- Knows customer rules from memory — but can't transfer that knowledge
- Measured on accuracy (zero wrong approvals) and throughput (docs/day)
- Pain: repetitive work, afraid of missing a mismatch, no tools that actually help

**Supplier (SU) — Shipping Coordinator**
- Generates documents from their ERP/logistics system (SAP, Oracle, custom)
- Sends documents via email to CG as PDF attachments
- Considers the job done once the email is sent
- Pain: amendment requests are vague ("please fix the consignee"), causing multiple rounds
- Wants: one clear email listing exactly what to change, fix once, done

### JTBD Statements
1. **When** I receive a new batch of trade documents from a supplier, **I want** them automatically extracted and validated against the customer's rules, **so that** I can focus on exceptions instead of routine checking.
2. **When** a document has a discrepancy, **I want** to see exactly which field failed and what the correct value should be, **so that** I can send a precise amendment request in one email instead of multiple rounds.
3. **When** I am a new CG hire with no knowledge of customer-specific rules, **I want** the system to enforce those rules automatically, **so that** I don't approve incorrect documents while learning.
4. **When** I am a supplier and receive an amendment request, **I want** a clear, field-level list of exactly what needs to change, **so that** I can fix everything in one revision.
5. **When** my manager asks how many shipments are pending review, **I want** to query the system in plain English, **so that** I don't need to count emails manually.
6. **When** a document is clearly correct with high confidence, **I want** it auto-approved and stored, **so that** I don't waste time rubber-stamping clean documents.

---

## 4. Agent Architecture

### Why three agents? Why not one prompt? Why not five?
Three agents map to three distinct cognitive tasks with fundamentally different requirements:

| Agent | Cognitive Task | Model Need | Latency Tolerance | Failure Mode |
|---|---|---|---|---|
| Extractor | Visual comprehension | Vision LLM (GPT-4o) | High (2-5s OK) | Misread field |
| Validator | Rule comparison | Text LLM (GPT-4o-mini) | Low (<1s) | Wrong match/mismatch |
| Router | Judgment + drafting | Text LLM (GPT-4o-mini) | Low (<1s) | Wrong action |

**Why not one mega-prompt?**
- Cannot use different models (extraction needs vision, others don't)
- Cannot test/eval independently — one prompt means one black box
- Cannot attribute failure to a specific step
- Prompt becomes > 3000 tokens, increasing hallucination risk and cost

**Why not five or more agents?**
- The pipeline is linear (A→B→C), not a graph — no branching needed
- Adding agents for "parsing" or "formatting" just adds latency and coordination cost
- Three is the minimum viable decomposition that gives independent testability and model flexibility

### Agent Details

**Extractor Agent**
- Input: PDF or image file path
- Output: `ExtractionResult` — list of `ExtractedField` objects with `field_name`, `value`, `confidence` (0.0-1.0), `source_location`
- Model: GPT-4o (vision)
- Key behavior: returns `null` for fields not found, never fabricates

**Validator Agent**
- Input: `ExtractionResult` + customer rules (JSON)
- Output: `ValidationResult` — list of `FieldValidation` objects with `status` (match/mismatch/uncertain/missing), `extracted_value`, `expected_value`, `reasoning`
- Model: GPT-4o-mini (with local rule checks as first pass)
- Key behavior: any field with confidence < 0.6 → automatic "uncertain", never silently approved

**Router Agent**
- Input: `ValidationResult` + thresholds
- Output: `RoutingDecision` — `decision` (auto_approve/flag_for_review/draft_amendment), `reasoning`, `discrepancies`, `amendment_draft`
- Model: GPT-4o-mini
- Key behavior: explains every decision, drafts professional amendment emails

### Inter-Agent Communication
- Structured JSON handoff: output of agent N is the typed input for agent N+1
- No shared memory, no message bus, no event system
- Serializable at every boundary — enables checkpointing, debugging, replay
- State persisted as JSON checkpoint files after each agent step

### Crash Recovery
- Each pipeline run gets a UUID
- After each agent completes, a checkpoint file is written
- On restart, `StateManager.get_last_incomplete()` finds runs that didn't reach COMPLETED/FAILED
- Pipeline can resume from the last successful checkpoint

---

## 5. LLM & Tooling Choices

| Component | Choice | Why | Alternatives Considered |
|---|---|---|---|
| Extraction LLM | GPT-4o | Best-in-class vision, handles scans and photos | Claude 3.5 Sonnet (close second, but API less mature for vision) |
| Validation LLM | GPT-4o-mini | 30x cheaper than GPT-4o, sufficient for structured comparison | Local rules only (misses edge cases) |
| Routing LLM | GPT-4o-mini | Cost-efficient for decision + email drafting | GPT-4o (overkill for this task) |
| Query LLM | GPT-4o-mini | Text-to-SQL generation, cheap | Fine-tuned model (not worth it for POC) |
| Orchestration | Custom Python | 3-agent linear pipeline, no graph needed | LangGraph (too heavy), CrewAI (too opinionated) |
| Storage | SQLite | Zero setup, runs anywhere, sufficient for POC | Postgres (for production), DuckDB (for analytics) |
| UI | Streamlit | Fastest Python-native UI, no build step | React (too slow for POC), Gradio (less flexible) |
| PDF Processing | PyMuPDF (fitz) | Fast PDF→image conversion, no external deps | pdf2image+poppler (requires system install) |

### Structured Output
- All LLM calls use `response_format={"type": "json_object"}` for deterministic parsing
- Pydantic models validate every response before passing to next agent
- If JSON parsing fails, retry with explicit schema in prompt (up to 3 times)

### Fallback Strategy
1. First attempt: standard prompt with `json_object` response format
2. On failure: retry with explicit JSON schema embedded in prompt
3. On second failure: retry with simplified prompt
4. On third failure: mark field as "uncertain", flag for human review

---

## 6. Trust, Failure Handling & Evals

### Anti-Hallucination
- Extraction prompt explicitly states: "NEVER fabricate or guess a value"
- Fields not found → `null` value, `0.0` confidence
- Source location required — forces model to ground answers in document
- Post-extraction validation: if confidence < 0.3 for a "found" field, flag as suspicious

### Low-Confidence Handling
- Any field with extraction confidence < 0.6 → automatic "uncertain" status
- Uncertain fields are ALWAYS surfaced to CG operator — never silently approved
- The system would rather over-flag than under-flag

### Loop & Cost Prevention
- Max 3 retries per LLM call (exponential backoff: 2s, 4s, 8s)
- Timeout per call: 30 seconds
- Cost cap per document: \$0.50 (kills pipeline if exceeded)
- Pipeline timeout: 120 seconds total

### Evaluation Plan

**Offline Eval (pre-deployment)**
- Dataset: 50 known trade documents with ground-truth field labels
- Metrics: precision, recall, F1 per field
- Target: >90% extraction accuracy on clean docs, >80% on messy docs
- Run monthly against new model versions

**Online Metric (production)**
- **False Approval Rate**: % of auto-approved documents that required later amendment
- Target: <2% — if exceeded, tighten auto-approve threshold
- Tracked per customer, per document type

---

## 7. Metrics & Success Criteria

### North Star Metric
**Percentage of shipment documents validated correctly without human intervention.**
One number. If it goes up, the system is working. If it goes down, something broke.

### Supporting Metrics
| Metric | Type | Target |
|---|---|---|
| Extraction accuracy (field-level F1) | Agent quality | >90% clean, >80% messy |
| Validation precision (correct match/mismatch calls) | Agent quality | >95% |
| False approval rate | Trust | <2% |
| Average processing time per document | System health | <60 seconds |
| Cost per document | System health | <\$0.10 |
| CG time saved per day (hours) | Business outcome | >4 hours |
| Amendment cycles per shipment (before vs after) | Business outcome | 50% reduction |
| Query response accuracy | Agent quality | >85% |

### Go / No-Go Criteria for 2-Week Pilot
- [x] >90% extraction accuracy on customer's actual clean documents
- [x] Zero false approvals on documents with known mismatches
- [x] <60 seconds end-to-end processing time
- [x] CG operator rates the UI as "usable without training" (qualitative)
- [x] Cost per document < \$0.10

---

## 8. What's Next (After Part 1 Ships)

If I had two more weeks, in priority order:
1. **Real email integration** — Connect to IMAP/Gmail API, process incoming emails automatically. This is the #1 gap between POC and production.
2. **Customer rule learning** — When CG overrides a validation result, capture the correction and update rules automatically. Turns every human review into training data.
3. **Multi-language document support** — Many trade docs are in Chinese, Korean, or Arabic. Add OCR preprocessing and translation layer before extraction.
4. **Batch processing dashboard** — Process 100+ documents in parallel with progress tracking, error summaries, and bulk approve/reject actions.

Why this order? Email integration removes the biggest friction point (manual upload). Rule learning makes the system smarter over time. Multi-language expands addressable market. Batch processing scales throughput.
