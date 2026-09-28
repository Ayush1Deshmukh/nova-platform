import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.database import Database
from ui.components.field_card import render_field_table, render_validation_table, render_decision_badge

st.title("🔍 Pipeline View")
st.markdown("View detailed pipeline execution for any processed document.")

db = Database()
db.init_db()

all_runs = db.get_all_runs()

if not all_runs:
    st.info("No pipeline runs yet. Upload a document first.")
    st.stop()

run_options = {f"{r['run_id']} — {r.get('file_name', 'unknown')} ({r.get('status', '?')})": r['run_id'] for r in all_runs}
selected = st.selectbox("Select Pipeline Run", list(run_options.keys()))

if selected:
    run_id = run_options[selected]
    run_detail = db.get_pipeline_run(run_id)

    if not run_detail:
        st.error("Run not found")
        st.stop()

    # Pipeline flow
    status = run_detail.get("status", "unknown")
    decision = run_detail.get("decision", "pending")

    col1, col2, col3, col4 = st.columns(4)
    stages = [
        ("📥 Extract", "extracting"),
        ("✅ Validate", "validating"),
        ("🔀 Route", "routing"),
        ("💾 Complete", "completed")
    ]
    completed_stages = {"pending": 0, "extracting": 1, "validating": 2, "routing": 3, "completed": 4, "failed": 0}
    progress = completed_stages.get(status, 0)

    for i, (col, (label, _)) in enumerate(zip([col1, col2, col3, col4], stages)):
        with col:
            if i < progress:
                st.success(label)
            elif i == progress and status != "completed":
                st.warning(f"⏳ {label}")
            elif status == "completed":
                st.success(label)
            else:
                st.info(label)

    st.markdown("---")

    # Details
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Processing Time", f"{run_detail.get('processing_time_ms', 0)}ms")
    with col_b:
        st.metric("Cost", f"${run_detail.get('total_cost_usd', 0):.4f}")

    # Extracted fields
    with st.expander("📋 Extracted Fields", expanded=True):
        fields = run_detail.get("extracted_fields", [])
        if fields:
            for f in fields:
                conf = f.get("confidence", 0)
                color = "🟢" if conf >= 0.85 else "🟡" if conf >= 0.6 else "🔴"
                st.markdown(f"{color} **{f.get('field_name', '')}**: `{f.get('value', 'N/A')}` (confidence: {conf:.2f})")
        else:
            st.info("No extracted fields available")

    # Validation results
    with st.expander("✅ Validation Results", expanded=True):
        validations = run_detail.get("validations", [])
        if validations:
            for v in validations:
                status_icon = {"match": "✅", "mismatch": "❌", "uncertain": "⚠️", "missing": "⬜"}.get(v.get("status", ""), "❓")
                st.markdown(
                    f"{status_icon} **{v.get('field_name', '')}** — {v.get('status', '').upper()}\n"
                    f"  - Found: `{v.get('extracted_value', 'N/A')}` | Expected: `{v.get('expected_value', 'N/A')}`\n"
                    f"  - {v.get('reasoning', '')}"
                )
        else:
            st.info("No validation results available")

    # Decision
    with st.expander("🔀 Routing Decision", expanded=True):
        if decision:
            render_decision_badge(decision)
            st.markdown(f"**Reasoning:** {run_detail.get('reasoning', 'N/A')}")
            if run_detail.get("amendment_draft"):
                st.markdown("**Amendment Draft:**")
                st.text_area("Draft", value=run_detail["amendment_draft"], height=150, disabled=True)
        else:
            st.info("No decision yet")
