import streamlit as st


def render_email_draft(draft: str, shipment_id: str):
    st.markdown("### 📧 Draft Amendment Email")
    st.warning("⚠️ Agent never sends on its own. Review and edit before sending.")
    edited = st.text_area(
        "Edit the draft:",
        value=draft,
        height=300,
        key=f"email_draft_{shipment_id}"
    )
    return edited


def render_email_preview(subject: str, body: str, to: str):
    st.markdown(f"""
    <div style="border:1px solid #ddd;border-radius:8px;padding:16px;background:#fafafa;">
        <p style="margin:0;color:#666;font-size:12px;">To: {to}</p>
        <p style="margin:4px 0;font-weight:bold;">Subject: {subject}</p>
        <hr style="margin:8px 0;">
        <div style="white-space:pre-wrap;font-size:14px;">{body}</div>
    </div>
    """, unsafe_allow_html=True)


def render_action_buttons(shipment_id: str):
    col1, col2, col3 = st.columns(3)
    with col1:
        approve = st.button("✅ Approve", key=f"btn_approve_{shipment_id}", type="primary")
    with col2:
        send = st.button("📧 Send Amendment", key=f"btn_send_{shipment_id}")
    with col3:
        reject = st.button("❌ Reject", key=f"btn_reject_{shipment_id}")

    if approve:
        st.success("Shipment approved by CG.")
    elif send:
        st.success("Amendment email sent (simulated).")
    elif reject:
        st.error("Shipment rejected.")

    return {"approved": approve, "sent": send, "rejected": reject}
