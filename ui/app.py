import streamlit as st
import sys
import os
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(
    page_title="Nova Platform",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Global CSS applied to all pages
st.markdown("""
<style>
    /* Sidebar Navigation Improvements */
    [data-testid="stSidebarNav"]::before {
        content: "MENU";
        margin-left: 20px;
        margin-top: 20px;
        font-size: 13px;
        color: #94A3B8;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        display: block;
        margin-bottom: 12px;
    }
    
    /* Active States: Distinct highlight, lighter background, vertical accent line */
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background-color: rgba(56, 189, 248, 0.1) !important;
        border-left: 4px solid #38BDF8 !important;
        border-radius: 0 8px 8px 0;
        margin-left: 0;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] span {
        color: #38BDF8 !important;
        font-weight: 700 !important;
    }
    [data-testid="stSidebarNav"] a {
        border-left: 4px solid transparent;
        transition: all 0.2s ease;
    }
    [data-testid="stSidebarNav"] a:hover {
        background-color: rgba(255, 255, 255, 0.05);
    }
    
    /* KPI Containment & Visual Hierarchy */
    .metric-card {
        background-color: #1E293B; /* Dark slate gray */
        border: 1px solid #334155;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        margin-bottom: 24px;
    }
    .metric-card h3 {
        color: #94A3B8;
        font-size: 1rem !important; /* Increased font size */
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.1em; /* Wider letter spacing */
        margin: 0 0 12px 0 !important;
        padding: 0 !important;
    }
    .metric-card h2 {
        color: #F8FAFC;
        font-size: 3rem !important;
        font-weight: 800 !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1;
    }
    
    /* Header Polish & Framing */
    .header-bar {
        display: flex;
        align-items: center;
        background-color: transparent;
        padding: 10px 0 30px 0;
        margin-bottom: 30px; /* Space below the boundary */
        border-bottom: 1px solid #334155; /* Subtle horizontal divider */
    }
    .header-icon {
        margin-right: 16px;
    }
    .header-title {
        margin: 0;
        color: #F8FAFC;
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }
    .header-subtitle {
        margin: 4px 0 0 0;
        color: #94A3B8;
        font-size: 1.1rem;
        font-weight: 400;
    }
    
    /* Table Styling & Contrast */
    .table-container {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        overflow: hidden;
        margin-top: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .nova-table { 
        width: 100%; 
        border-collapse: collapse; 
        color: #F1F5F9; 
        font-size: 0.95rem;
    }
    .nova-table th { 
        background-color: #0F172A;
        color: #CBD5E1; /* Lightened header contrast */
        font-weight: 600; 
        text-align: left; 
        padding: 16px 24px; 
        border-bottom: 1px solid #334155; 
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    .nova-table td { 
        padding: 20px 24px; /* Added vertical padding to rows */
        border-bottom: 1px solid #334155; 
        vertical-align: middle;
    }
    .nova-table tr:last-child td {
        border-bottom: none;
    }
    .nova-table tr:hover {
        background-color: rgba(255, 255, 255, 0.03);
    }
    
    /* Status Pills & Badges */
    .status-pill { 
        padding: 6px 14px; 
        border-radius: 9999px; /* Fully rounded pill */
        font-size: 0.75rem; 
        font-weight: 700; 
        text-transform: uppercase; 
        display: inline-block;
        letter-spacing: 0.05em;
    }
    
    /* Specific badge colors */
    .status-completed { background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.25); }
    .status-pending { background: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.25); }
    .status-failed { background: rgba(239, 68, 68, 0.15); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.25); }
    
    .decision-approve { background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.25); }
    .decision-review { background: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.25); }
    .decision-amend { background: rgba(239, 68, 68, 0.15); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.25); }
    .decision-none { background: rgba(148, 163, 184, 0.15); color: #94A3B8; border: 1px solid rgba(148, 163, 184, 0.25); }
</style>
""", unsafe_allow_html=True)


def dashboard_view():
    """Main dashboard logic mapped to the 'Dashboard' page."""
    from storage.database import Database

    db = Database()
    db.init_db()

    # Header with clean vector SVG icon and framing
    st.markdown("""
    <div class="header-bar">
        <div class="header-icon">
            <svg width="42" height="42" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="3" y="3" width="18" height="18" rx="4" stroke="#38BDF8" stroke-width="2"/>
                <path d="M3 9H21" stroke="#38BDF8" stroke-width="2"/>
                <path d="M9 21V9" stroke="#38BDF8" stroke-width="2"/>
                <circle cx="15" cy="15" r="2" fill="#38BDF8"/>
            </svg>
        </div>
        <div>
            <h1 class="header-title">Nova Platform</h1>
            <p class="header-subtitle">Multi-Agent Trade Document Intelligence</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        all_runs = db.get_all_runs()
        
        total_docs = len(all_runs)
        completed = [r for r in all_runs if r.get("status") == "completed"]
        approved = [r for r in all_runs if r.get("decision") == "auto_approve"]
        flagged = [r for r in all_runs if r.get("decision") == "flag_for_review"]
        amendments = [r for r in all_runs if r.get("decision") == "draft_amendment"]

        # KPIs enclosed in subtle rounded-corner cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><h3>Total Documents</h3><h2>{total_docs}</h2></div>', unsafe_allow_html=True)
        with col2:
            rate = f"{(len(approved)/len(completed)*100):.0f}%" if completed else "0%"
            st.markdown(f'<div class="metric-card"><h3>Auto-Approval Rate</h3><h2>{rate}</h2></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><h3>Flagged for Review</h3><h2>{len(flagged)}</h2></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><h3>Amendments Drafted</h3><h2>{len(amendments)}</h2></div>', unsafe_allow_html=True)

        if all_runs:
            st.markdown("<h3 style='color: #F8FAFC; margin-top: 24px; font-weight: 600;'>Recent Pipeline Runs</h3>", unsafe_allow_html=True)
            
            # Use strict dedent and standard formatting to prevent markdown parsing issues
            html_table = textwrap.dedent("""
            <div class="table-container">
                <table class="nova-table">
                    <thead>
                        <tr>
                            <th>Run ID</th>
                            <th>File Name</th>
                            <th>Document Type</th>
                            <th>Status</th>
                            <th>Decision</th>
                            <th>Score</th>
                            <th>Processed Date</th>
                        </tr>
                    </thead>
                    <tbody>
            """)
            
            for run in all_runs[:15]:  # Show recent 15
                status = run.get('status', 'unknown')
                decision = run.get('decision') or 'none'
                
                status_class = f"status-{status.lower()}" if status.lower() in ['completed', 'pending', 'failed'] else "status-pending"
                
                if decision.lower() == "auto_approve":
                    dec_class = "decision-approve"
                    dec_text = "Approved"
                elif decision.lower() == "flag_for_review":
                    dec_class = "decision-review"
                    dec_text = "Review"
                elif decision.lower() == "draft_amendment":
                    dec_class = "decision-amend"
                    dec_text = "Amendment"
                else:
                    dec_class = "decision-none"
                    dec_text = "Pending"
                    
                score = run.get('overall_score')
                if score is not None:
                    score_str = f"{(score*100):.0f}%"
                else:
                    score_str = "-"
                
                date_str = run.get('created_at', '')[:16].replace('T', ' ')
                doc_type = run.get('document_type', 'unknown').replace('_', ' ').title()
                
                row_html = f"""
                <tr>
                    <td style="font-family: monospace; color: #94A3B8;">{run['run_id'][:8]}</td>
                    <td style="font-weight: 500; color: #F8FAFC;">{run.get('file_name', 'unknown')}</td>
                    <td style="color: #CBD5E1;">{doc_type}</td>
                    <td><span class="status-pill {status_class}">{status}</span></td>
                    <td><span class="status-pill {dec_class}">{dec_text}</span></td>
                    <td style="font-weight: 700; color: #F8FAFC;">{score_str}</td>
                    <td style="color: #94A3B8; font-size: 0.85rem;">{date_str}</td>
                </tr>
                """
                # Removing any leading whitespace from the row so Markdown doesn't parse it as code
                html_table += textwrap.dedent(row_html).strip()
                
            html_table += "</tbody></table></div>"
            
            # st.html safely renders HTML without applying Markdown rules (like code blocks)
            st.html(html_table)
            
        else:
            st.info("No documents processed yet. Go to **Upload Document** to get started.")

    except Exception as e:
        st.warning(f"Database not initialized or empty. Upload a document to get started. ({e})")

# Setup Streamlit Navigation (st.Page and st.navigation fix the "app" lowercase sidebar issue)
base_dir = os.path.dirname(__file__)

dashboard_page = st.Page(dashboard_view, title="Dashboard", icon="📊", default=True)
upload_page = st.Page(os.path.join(base_dir, "pages/1_Upload_Document.py"), title="Upload Document", icon="📤")
pipeline_page = st.Page(os.path.join(base_dir, "pages/2_Pipeline_View.py"), title="Pipeline View", icon="🔍")
query_page = st.Page(os.path.join(base_dir, "pages/3_Query_Data.py"), title="Query Data", icon="💬")
cg_page = st.Page(os.path.join(base_dir, "pages/4_CG_Verification.py"), title="CG Verification", icon="✅")

# Create navigation menu
pg = st.navigation([dashboard_page, upload_page, pipeline_page, query_page, cg_page])

# Minimal sidebar footer
st.sidebar.info("Nova Platform v1.0 · Built for GoComet")

# Run the selected page
pg.run()
