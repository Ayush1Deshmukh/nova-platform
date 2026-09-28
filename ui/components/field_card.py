import streamlit as st
from typing import List, Optional


def render_confidence_badge(score: float) -> str:
    if score >= 0.85:
        color = "#10B981"
        label = "HIGH"
    elif score >= 0.60:
        color = "#F59E0B"
        label = "MED"
    else:
        color = "#EF4444"
        label = "LOW"
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:bold;">{label} {score:.2f}</span>'


def render_status_badge(status: str) -> str:
    colors = {
        "match": ("#10B981", "MATCH"),
        "mismatch": ("#EF4444", "MISMATCH"),
        "uncertain": ("#F59E0B", "UNCERTAIN"),
        "missing": ("#6B7280", "MISSING"),
    }
    color, label = colors.get(status.lower(), ("#6B7280", status.upper()))
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:bold;">{label}</span>'


def render_decision_badge(decision: str):
    badges = {
        "auto_approve": ("✅ AUTO-APPROVED", "#10B981"),
        "flag_for_review": ("🟡 FLAGGED FOR REVIEW", "#F59E0B"),
        "draft_amendment": ("🔴 AMENDMENT REQUIRED", "#EF4444"),
    }
    label, color = badges.get(decision, ("❓ " + decision.upper(), "#6B7280"))
    st.markdown(
        f'<div style="background:{color};color:white;padding:12px 20px;border-radius:8px;'
        f'font-size:18px;font-weight:bold;text-align:center;margin:10px 0;">{label}</div>',
        unsafe_allow_html=True
    )


def render_field_table(fields):
    if not fields:
        st.info("No fields extracted")
        return

    html = '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
    html += '<tr style="background:#1a1a2e;color:white;">'
    html += '<th style="padding:8px;text-align:left;">Field</th>'
    html += '<th style="padding:8px;text-align:left;">Value</th>'
    html += '<th style="padding:8px;text-align:center;">Confidence</th>'
    html += '<th style="padding:8px;text-align:left;">Source</th>'
    html += '</tr>'

    for i, field in enumerate(fields):
        if hasattr(field, 'field_name'):
            name = field.field_name
            value = field.value or "N/A"
            conf = field.confidence
            source = field.source_location or ""
        else:
            name = field.get("field_name", "")
            value = field.get("value", "N/A")
            conf = field.get("confidence", 0)
            source = field.get("source_location", "")

        bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
        badge = render_confidence_badge(conf)
        html += f'<tr style="background:{bg};">'
        html += f'<td style="padding:8px;font-weight:bold;">{name}</td>'
        html += f'<td style="padding:8px;"><code>{value}</code></td>'
        html += f'<td style="padding:8px;text-align:center;">{badge}</td>'
        html += f'<td style="padding:8px;font-size:12px;color:#666;">{source}</td>'
        html += '</tr>'

    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)


def render_validation_table(validations):
    if not validations:
        st.info("No validation results")
        return

    html = '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
    html += '<tr style="background:#1a1a2e;color:white;">'
    html += '<th style="padding:8px;text-align:left;">Field</th>'
    html += '<th style="padding:8px;text-align:center;">Status</th>'
    html += '<th style="padding:8px;text-align:left;">Found</th>'
    html += '<th style="padding:8px;text-align:left;">Expected</th>'
    html += '<th style="padding:8px;text-align:left;">Reasoning</th>'
    html += '</tr>'

    for i, v in enumerate(validations):
        if hasattr(v, 'field_name'):
            name = v.field_name
            status = v.status.value if hasattr(v.status, 'value') else str(v.status)
            found = v.extracted_value or "N/A"
            expected = v.expected_value or "N/A"
            reasoning = v.reasoning or ""
        else:
            name = v.get("field_name", "")
            status = v.get("status", "")
            found = v.get("extracted_value", "N/A")
            expected = v.get("expected_value", "N/A")
            reasoning = v.get("reasoning", "")

        bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
        badge = render_status_badge(status)
        html += f'<tr style="background:{bg};">'
        html += f'<td style="padding:8px;font-weight:bold;">{name}</td>'
        html += f'<td style="padding:8px;text-align:center;">{badge}</td>'
        html += f'<td style="padding:8px;"><code>{found}</code></td>'
        html += f'<td style="padding:8px;"><code>{expected}</code></td>'
        html += f'<td style="padding:8px;font-size:12px;">{reasoning[:100]}{"..." if len(reasoning) > 100 else ""}</td>'
        html += '</tr>'

    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)
