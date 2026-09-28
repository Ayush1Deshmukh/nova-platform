import streamlit as st
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.orchestrator import PipelineOrchestrator
from storage.database import Database
from ui.components.field_card import render_field_table, render_validation_table, render_decision_badge

st.title("📤 Upload Document")
st.markdown("Upload a trade document (PDF or image) to run the full extraction → validation → routing pipeline.")

db = Database()
db.init_db()

customer_id = st.selectbox("Customer", ["CUST-001"], index=0)

uploaded_file = st.file_uploader(
    "Upload Trade Document",
    type=["pdf", "png", "jpg", "jpeg"],
    help="Supports: Bill of Lading, Commercial Invoice, Packing List, Certificate of Origin"
)

if uploaded_file and st.button("🚀 Process Document", type="primary"):
    with st.spinner("Running pipeline: Extract → Validate → Route..."):
        try:
            suffix = "." + uploaded_file.name.rsplit(".", 1)[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name

            rules_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "customer_rules.json")
            orchestrator = PipelineOrchestrator(customer_rules_path=rules_path, db=db)
            run = orchestrator.process_document(tmp_path, customer_id)

            os.unlink(tmp_path)

            st.success(f"Pipeline completed in {run.processing_time_ms}ms | Cost: ${run.total_cost_usd:.4f}")

            # Extraction Results
            with st.expander("📋 Extracted Fields", expanded=True):
                if run.extraction_result:
                    st.caption(f"Document Type: **{run.extraction_result.document_type}** | Model: {run.extraction_result.model_used}")
                    render_field_table(run.extraction_result.fields)
                else:
                    st.warning("No extraction result available")

            # Validation Results
            with st.expander("✅ Validation Results", expanded=True):
                if run.validation_result:
                    cols = st.columns(4)
                    cols[0].metric("Matched", run.validation_result.matched_fields)
                    cols[1].metric("Mismatched", run.validation_result.mismatched_fields)
                    cols[2].metric("Uncertain", run.validation_result.uncertain_fields)
                    cols[3].metric("Overall Score", f"{run.validation_result.overall_score:.2f}")
                    st.markdown("---")
                    render_validation_table(run.validation_result.validations)
                else:
                    st.warning("No validation result available")

            # Routing Decision
            with st.expander("🔀 Routing Decision", expanded=True):
                if run.routing_decision:
                    render_decision_badge(run.routing_decision.decision.value)
                    st.markdown(f"**Reasoning:** {run.routing_decision.reasoning}")

                    if run.routing_decision.discrepancies:
                        st.markdown("**Discrepancies:**")
                        for d in run.routing_decision.discrepancies:
                            severity_icon = "🔴" if d.severity == "critical" else "🟡"
                            st.markdown(f"{severity_icon} **{d.field_name}**: Found `{d.found}` → Expected `{d.expected}`")

                    if run.routing_decision.amendment_draft:
                        st.markdown("**Draft Amendment Email:**")
                        st.text_area("Edit before sending:", value=run.routing_decision.amendment_draft, height=200, key="amendment_draft")
                        st.button("📧 Send Amendment (simulated)", disabled=False)
                else:
                    st.warning("No routing decision available")

        except Exception as e:
            st.error(f"Pipeline failed: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
