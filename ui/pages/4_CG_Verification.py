import streamlit as st
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.database import Database
from pipeline.orchestrator import PipelineOrchestrator
from pipeline.email_trigger import EmailTrigger
from ui.components.field_card import render_field_table, render_validation_table, render_decision_badge

st.title("✅ CG Verification Dashboard")
st.markdown("Review incoming shipments, verify documents, and approve or request amendments.")

db = Database()
db.init_db()

# State: Incoming → Verification → Discrepancy Detail → Draft Reply
STATES = ["📥 Incoming", "✅ Verification Result", "🔍 Discrepancy Detail", "📧 Draft Reply"]

shipments = db.get_shipments()

if not shipments:
    st.info("No shipments to review. Simulate an email or upload documents first.")

    st.markdown("---")
    st.subheader("Simulate Email Arrival")
    email_dirs = []
    sample_dir = os.path.join(os.path.dirname(__file__), "..", "..", "sample_emails")
    if os.path.exists(sample_dir):
        for d in sorted(os.listdir(sample_dir)):
            full_path = os.path.join(sample_dir, d)
            if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, "metadata.json")):
                email_dirs.append((d, full_path))

    if email_dirs:
        selected_email = st.selectbox("Select simulated email:", [d[0] for d in email_dirs])
        if st.button("📨 Process Email", type="primary"):
            email_path = next(d[1] for d in email_dirs if d[0] == selected_email)
            with st.spinner("Processing shipment..."):
                try:
                    rules_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "customer_rules.json")
                    orchestrator = PipelineOrchestrator(customer_rules_path=rules_path, db=db)
                    shipment = orchestrator.process_shipment(email_path)
                    st.success(f"Shipment {shipment.shipment_id} processed. Status: {shipment.status.value}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Processing failed: {e}")
    st.stop()

# Display shipments
for shipment in shipments:
    ship_id = shipment.get("shipment_id", "unknown")
    status = shipment.get("status", "unknown")
    status_icon = {
        "processing": "⏳", "pending_review": "🟡",
        "approved": "🟢", "amendment_requested": "🔴", "failed": "❌"
    }.get(status, "❓")

    with st.expander(f"{status_icon} Shipment {ship_id} — {shipment.get('email_subject', 'No subject')} [{status.upper()}]", expanded=(status != "approved")):

        # Metadata
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"**From:** {shipment.get('email_from', 'N/A')}")
        col2.markdown(f"**Customer:** {shipment.get('customer_id', 'N/A')}")
        col3.markdown(f"**Documents:** {shipment.get('document_count', 0)}")

        # Tabs for the 4 states
        tab1, tab2, tab3, tab4 = st.tabs(STATES)

        # Tab 1: Incoming
        with tab1:
            st.markdown(f"**Subject:** {shipment.get('email_subject', 'N/A')}")
            st.markdown(f"**From:** {shipment.get('email_from', 'N/A')}")
            st.markdown(f"**Status:** {status}")
            if status == "processing":
                st.spinner("Agent is processing documents...")

        # Get related pipeline runs
        runs = db.get_runs_by_customer(shipment.get("customer_id", ""))

        # Tab 2: Verification Result
        with tab2:
            if runs:
                for run in runs:
                    run_detail = db.get_pipeline_run(run["run_id"])
                    if not run_detail:
                        continue

                    st.markdown(f"#### 📄 {run_detail.get('file_name', 'unknown')} ({run_detail.get('document_type', 'unknown')})")

                    fields = run_detail.get("extracted_fields", [])
                    validations = run_detail.get("validations", [])

                    if validations:
                        for v in validations:
                            status_map = {"match": "✅", "mismatch": "❌", "uncertain": "⚠️", "missing": "⬜"}
                            icon = status_map.get(v.get("status", ""), "❓")
                            conf = v.get("confidence", 0)
                            conf_color = "🟢" if conf >= 0.85 else "🟡" if conf >= 0.6 else "🔴"
                            st.markdown(
                                f"{icon} **{v.get('field_name', '')}** — "
                                f"`{v.get('extracted_value', 'N/A')}` "
                                f"{conf_color} ({conf:.2f})"
                            )
                    st.markdown("---")
            else:
                st.info("No documents processed for this shipment yet.")

        # Tab 3: Discrepancy Detail
        with tab3:
            has_discrepancies = False
            if runs:
                for run in runs:
                    run_detail = db.get_pipeline_run(run["run_id"])
                    if not run_detail:
                        continue
                    validations = run_detail.get("validations", [])
                    flagged = [v for v in validations if v.get("status") in ("mismatch", "uncertain", "missing")]
                    if flagged:
                        has_discrepancies = True
                        st.markdown(f"#### 📄 {run_detail.get('file_name', 'unknown')}")
                        for v in flagged:
                            status_map = {"mismatch": "❌ MISMATCH", "uncertain": "⚠️ UNCERTAIN", "missing": "⬜ MISSING"}
                            st.markdown(f"**{v.get('field_name', '')}** — {status_map.get(v.get('status', ''), v.get('status', ''))}")
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.markdown(f"**Found:** `{v.get('extracted_value', 'N/A')}`")
                            with col_b:
                                st.markdown(f"**Expected:** `{v.get('expected_value', 'N/A')}`")
                            st.caption(f"Reasoning: {v.get('reasoning', 'N/A')}")
                            st.markdown("---")
            if not has_discrepancies:
                st.success("No discrepancies found across all documents.")

        # Tab 4: Draft Reply
        with tab4:
            if shipment.get("amendment_draft"):
                st.markdown("**Agent-generated amendment email (editable):**")
                draft = st.text_area(
                    "Edit draft before sending:",
                    value=shipment["amendment_draft"],
                    height=300,
                    key=f"draft_{ship_id}"
                )
                st.warning("⚠️ Agent never sends on its own. CG must review and click Send.")
                col_send, col_approve = st.columns(2)
                with col_send:
                    if st.button("📧 Send Amendment (simulated)", key=f"send_{ship_id}", type="primary"):
                        st.success("Amendment email sent (simulated). Awaiting supplier response.")
                with col_approve:
                    if st.button("✅ Override & Approve", key=f"approve_{ship_id}"):
                        st.success("Shipment approved by CG override.")
            elif status == "approved":
                st.success("All documents verified and approved. No action needed.")
            elif status == "pending_review":
                st.info("Documents flagged for review. Check the Discrepancy Detail tab.")
                if st.button("✅ Approve After Review", key=f"approve_review_{ship_id}", type="primary"):
                    st.success("Shipment approved after CG review.")
            else:
                st.info("No draft reply generated for this shipment.")
