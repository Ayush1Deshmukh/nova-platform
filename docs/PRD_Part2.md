# PRD Part 2: CG Verification Workflow

---

## Personas

**CG Operator (Priya, 28, Cargo Verification Analyst)**
- Reviews 60+ document sets per day from supplier emails
- Cares about: speed (clear inbox fast), accuracy (zero wrong approvals), clarity (know exactly what's wrong without re-reading the doc)
- Frustration: typing the same amendment emails over and over, explaining the same errors to different suppliers

**Supplier Coordinator (Wei, 35, Shipping Documentation Manager)**
- Generates and sends trade documents to 12 different customers
- Cares about: getting approval fast, knowing exactly what to fix if something's wrong, never doing more than one revision
- Frustration: vague amendment requests ("please correct the consignee") that force 2-3 rounds

## Jobs-to-be-Done

1. **When** a supplier email with trade documents lands in my inbox, **I want** the system to automatically extract, validate, and cross-check all attachments against the customer's rules, **so that** I can review a ready-made verification result instead of opening each PDF manually.

2. **When** the system finds discrepancies across the documents, **I want** a pre-drafted amendment email listing every issue with field name, found value, and expected value, **so that** I can review, edit if needed, and send it back to the supplier in one click.

## North Star Metric

**Median time from SU email received to CG verification complete (approve or amendment sent).**

Today: 2-4 hours. Target with Nova: <10 minutes for clean shipments, <20 minutes for shipments needing amendments.

## Critical Failure Mode

**Worst case: agent auto-sends an amendment email with incorrect discrepancies, damaging the supplier relationship.**

Mitigation: Agent NEVER sends on its own. Draft is always presented to CG for review. CG must explicitly click "Send" after reviewing and optionally editing the draft. The system logs every CG edit to the draft for audit purposes. If CG sends an unmodified draft, the system records that too — building a trust score for the agent's drafts over time.
