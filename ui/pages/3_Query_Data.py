import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.database import Database
from storage.query_engine import QueryEngine

st.title("💬 Query Data")
st.markdown("Ask questions about processed documents in plain English.")

db = Database()
db.init_db()

query_engine = QueryEngine(db=db)

example_questions = [
    "How many documents were processed?",
    "Show all flagged shipments",
    "What is the average confidence score?",
    "How many mismatches were found?",
    "Show documents with amendments",
    "Which documents were auto-approved?",
]

st.markdown("**Example questions:**")
cols = st.columns(3)
for i, q in enumerate(example_questions):
    with cols[i % 3]:
        if st.button(q, key=f"ex_{i}", use_container_width=True):
            st.session_state["query_input"] = q

question = st.text_input(
    "Ask a question:",
    value=st.session_state.get("query_input", ""),
    placeholder="e.g., How many shipments were flagged this week?"
)

if question and st.button("🔍 Search", type="primary"):
    with st.spinner("Generating query and fetching results..."):
        result = query_engine.query(question)

    if result.get("error"):
        st.error(result.get("answer", "Query failed"))
    else:
        st.markdown("### Answer")
        st.markdown(result.get("answer", "No answer generated"))

        with st.expander("Generated SQL"):
            st.code(result.get("sql", ""), language="sql")
            st.caption(result.get("explanation", ""))

        with st.expander("Raw Results"):
            results_data = result.get("results", [])
            if results_data:
                import pandas as pd
                st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)
            else:
                st.info("No results returned")
