"""
app.py -- Premium RAG Chatbot UI
=================================
A polished, ChatGPT-tier chat interface for document-grounded QA.
Features dual-theme, glassmorphism sidebar, streaming responses,
animated citations, conversation history, and responsive design.

Run with:
    streamlit run app.py
"""

import os
import time
import json
from datetime import datetime
from pathlib import Path
import streamlit as st
from rag_pipeline import query_rag_stream, get_chroma_collection
from ingest import ingest_single_document


# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="RAG Knowledge Assistant",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "theme" not in st.session_state:
    st.session_state.theme = "dark"
if "conversations" not in st.session_state:
    st.session_state.conversations = []
if "current_conv_id" not in st.session_state:
    st.session_state.current_conv_id = 0
if "show_settings" not in st.session_state:
    st.session_state.show_settings = False
if "query_count" not in st.session_state:
    st.session_state.query_count = 0
if "total_sources" not in st.session_state:
    st.session_state.total_sources = 0


# ---------------------------------------------------------------------------
# Theme CSS Variables
# ---------------------------------------------------------------------------

def get_theme_css():
    """Generate CSS custom properties for the active theme."""
    is_dark = st.session_state.theme == "dark"

    if is_dark:
        return """
        :root {
            --bg-primary: #0B1120;
            --bg-secondary: #111827;
            --bg-tertiary: #1E293B;
            --bg-surface: #0F172A;
            --bg-hover: #1E293B;
            --bg-input: #1E293B;
            --bg-sidebar: rgba(15, 23, 42, 0.85);
            --bg-card: rgba(30, 41, 59, 0.6);
            --bg-user-msg: #1D4ED8;
            --bg-ai-msg: rgba(30, 41, 59, 0.5);
            --bg-code: #0D1117;
            --border-primary: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(99, 102, 241, 0.4);
            --border-focus: rgba(37, 99, 235, 0.5);
            --text-primary: #F1F5F9;
            --text-secondary: #94A3B8;
            --text-tertiary: #64748B;
            --text-muted: #475569;
            --text-user-msg: #FFFFFF;
            --text-on-primary: #FFFFFF;
            --accent-primary: #2563EB;
            --accent-secondary: #7C3AED;
            --accent-gradient: linear-gradient(135deg, #2563EB 0%, #7C3AED 100%);
            --success: #10B981;
            --warning: #F59E0B;
            --error: #EF4444;
            --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
            --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.5);
            --shadow-glow: 0 0 20px rgba(37, 99, 235, 0.15);
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 20px;
            --radius-full: 9999px;
        }
        """
    else:
        return """
        :root {
            --bg-primary: #FFFFFF;
            --bg-secondary: #F8FAFC;
            --bg-tertiary: #F1F5F9;
            --bg-surface: #FFFFFF;
            --bg-hover: #F1F5F9;
            --bg-input: #F8FAFC;
            --bg-sidebar: rgba(248, 250, 252, 0.9);
            --bg-card: rgba(241, 245, 249, 0.7);
            --bg-user-msg: #2563EB;
            --bg-ai-msg: #F8FAFC;
            --bg-code: #F6F8FA;
            --border-primary: rgba(0, 0, 0, 0.08);
            --border-hover: rgba(37, 99, 235, 0.3);
            --border-focus: rgba(37, 99, 235, 0.5);
            --text-primary: #0F172A;
            --text-secondary: #475569;
            --text-tertiary: #94A3B8;
            --text-muted: #CBD5E1;
            --text-user-msg: #FFFFFF;
            --text-on-primary: #FFFFFF;
            --accent-primary: #2563EB;
            --accent-secondary: #7C3AED;
            --accent-gradient: linear-gradient(135deg, #2563EB 0%, #7C3AED 100%);
            --success: #059669;
            --warning: #D97706;
            --error: #DC2626;
            --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.06);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.08);
            --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.1);
            --shadow-glow: 0 0 20px rgba(37, 99, 235, 0.08);
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 20px;
            --radius-full: 9999px;
        }
        """


# ---------------------------------------------------------------------------
# Complete Design System CSS
# ---------------------------------------------------------------------------

DESIGN_SYSTEM_CSS = f"""
<style>
    /* ===== FONTS ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    /* ===== THEME VARIABLES ===== */
    {{theme_css}}

    /* ===== ANIMATIONS ===== */
    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(12px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}

    @keyframes fadeIn {{
        from {{ opacity: 0; }}
        to {{ opacity: 1; }}
    }}

    @keyframes shimmer {{
        0% {{ background-position: -200% 0; }}
        100% {{ background-position: 200% 0; }}
    }}

    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.5; }}
    }}

    @keyframes pulseGlow {{
        0%, 100% {{ box-shadow: 0 0 4px var(--success); }}
        50% {{ box-shadow: 0 0 12px var(--success); }}
    }}

    @keyframes dotBounce {{
        0%, 80%, 100% {{ transform: scale(0); opacity: 0.4; }}
        40% {{ transform: scale(1); opacity: 1; }}
    }}

    @keyframes slideInLeft {{
        from {{ opacity: 0; transform: translateX(-16px); }}
        to {{ opacity: 1; transform: translateX(0); }}
    }}

    @keyframes gradientShift {{
        0% {{ background-position: 0% 50%; }}
        50% {{ background-position: 100% 50%; }}
        100% {{ background-position: 0% 50%; }}
    }}

    @keyframes scaleIn {{
        from {{ opacity: 0; transform: scale(0.95); }}
        to {{ opacity: 1; transform: scale(1); }}
    }}

    /* ===== GLOBAL RESET ===== */
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: var(--text-primary);
    }}

    .stApp {{
        background-color: var(--bg-primary);
    }}

    /* ===== MAIN CONTAINER ===== */
    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 6rem;
        max-width: 860px;
    }}

    /* ===== HIDE STREAMLIT CHROME ===== */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    .stDeployButton {{ display: none; }}
    header[data-testid="stHeader"] {{ background: transparent; }}

    /* ===== SIDEBAR ===== */
    [data-testid="stSidebar"] {{
        background: var(--bg-sidebar);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-right: 1px solid var(--border-primary);
    }}

    [data-testid="stSidebar"] [data-testid="stMarkdown"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] span,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] div,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] li,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] td,
    [data-testid="stSidebar"] label {{
        color: var(--text-secondary) !important;
    }}

    [data-testid="stSidebar"] [data-testid="stMarkdown"] strong {{
        color: var(--text-primary) !important;
    }}

    /* File uploader text fix */
    [data-testid="stFileUploadDropzone"] * {{
        color: var(--text-primary) !important;
    }}

    /* ===== SIDEBAR COMPONENTS ===== */
    .sidebar-brand {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.5rem 0 1.25rem 0;
        border-bottom: 1px solid var(--border-primary);
        margin-bottom: 1rem;
        animation: fadeIn 0.4s ease;
    }}

    .sidebar-brand-icon {{
        width: 40px;
        height: 40px;
        border-radius: var(--radius-md);
        background: var(--accent-gradient);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        box-shadow: var(--shadow-md);
        flex-shrink: 0;
    }}

    .sidebar-brand-text {{
        display: flex;
        flex-direction: column;
        gap: 0.1rem;
    }}

    .sidebar-brand-name {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.1rem;
        font-weight: 800;
        color: var(--text-primary) !important;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }}

    .sidebar-brand-tag {{
        font-size: 0.68rem;
        font-weight: 500;
        color: var(--text-tertiary) !important;
        letter-spacing: 0.02em;
    }}

    .sidebar-section {{
        margin-top: 1.25rem;
        animation: fadeIn 0.5s ease;
    }}

    .sidebar-label {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-tertiary) !important;
        margin-bottom: 0.6rem;
        padding-left: 0.1rem;
    }}

    .sidebar-divider {{
        height: 1px;
        background: var(--border-primary);
        margin: 1rem 0;
    }}

    /* Status badge */
    .status-badge {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.6rem 0.85rem;
        background: var(--bg-card);
        border: 1px solid var(--border-primary);
        border-radius: var(--radius-sm);
        font-size: 0.8rem;
        transition: all 0.2s ease;
    }}

    .status-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
    }}

    .status-online .status-dot {{
        background: var(--success);
        animation: pulseGlow 2s ease-in-out infinite;
    }}

    .status-offline .status-dot {{
        background: var(--error);
        box-shadow: 0 0 6px rgba(239, 68, 68, 0.5);
    }}

    .status-text {{
        font-weight: 600;
        color: var(--text-primary) !important;
    }}

    .status-count {{
        margin-left: auto;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: var(--text-tertiary) !important;
    }}

    /* Config grid */
    .config-grid {{
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 0.1rem 0.75rem;
        font-size: 0.78rem;
        padding: 0.5rem 0;
    }}

    .config-key {{
        color: var(--text-tertiary) !important;
        padding: 0.35rem 0;
        border-bottom: 1px solid var(--border-primary);
    }}

    .config-val {{
        text-align: right;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        font-size: 0.73rem;
        color: var(--text-primary) !important;
        padding: 0.35rem 0;
        border-bottom: 1px solid var(--border-primary);
    }}

    /* ===== WELCOME SCREEN ===== */
    .welcome-container {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 50vh;
        padding: 2rem 1rem;
        animation: fadeInUp 0.6s ease;
    }}

    .welcome-icon {{
        width: 64px;
        height: 64px;
        border-radius: var(--radius-lg);
        background: var(--accent-gradient);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.75rem;
        margin-bottom: 1.5rem;
        box-shadow: var(--shadow-glow), var(--shadow-md);
    }}

    .welcome-title {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        background: var(--accent-gradient);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: gradientShift 4s ease-in-out infinite;
        margin-bottom: 0.5rem;
        letter-spacing: -0.03em;
        text-align: center;
    }}

    .welcome-subtitle {{
        font-size: 1rem;
        color: var(--text-secondary);
        text-align: center;
        max-width: 460px;
        line-height: 1.6;
        margin-bottom: 2.5rem;
    }}

    /* ===== CHAT MESSAGES ===== */
    [data-testid="stChatMessage"] {{
        background: transparent !important;
        border: none !important;
        padding: 0.5rem 0 !important;
        animation: fadeInUp 0.3s ease;
    }}

    /* ===== SOURCE CITATIONS ===== */
    .source-pills {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-bottom: 0.5rem;
    }}

    .source-pill {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.25rem 0.65rem;
        background: var(--bg-card);
        border: 1px solid var(--border-primary);
        border-radius: var(--radius-full);
        font-size: 0.72rem;
        font-weight: 500;
        color: var(--text-secondary);
        transition: all 0.2s ease;
    }}

    .source-pill:hover {{
        border-color: var(--border-hover);
        color: var(--accent-primary);
    }}

    .source-pill-dot {{
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--success);
    }}

    .source-card {{
        background: var(--bg-surface);
        border: 1px solid var(--border-primary);
        border-radius: var(--radius-md);
        padding: 1rem 1.1rem;
        margin-bottom: 0.6rem;
        transition: all 0.2s ease;
        animation: scaleIn 0.3s ease;
    }}

    .source-card:hover {{
        border-color: var(--border-hover);
        box-shadow: var(--shadow-sm);
    }}

    .source-card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.65rem;
    }}

    .source-card-title {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }}

    .source-card-icon {{
        color: var(--accent-primary);
        font-size: 0.85rem;
    }}

    .source-card-name {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--accent-primary);
    }}

    .source-card-chunk {{
        font-size: 0.68rem;
        font-weight: 500;
        color: var(--text-tertiary);
        background: var(--bg-tertiary);
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
    }}

    .source-confidence {{
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}

    .confidence-bar-track {{
        width: 48px;
        height: 5px;
        background: var(--bg-tertiary);
        border-radius: 3px;
        overflow: hidden;
    }}

    .confidence-bar-fill {{
        height: 100%;
        border-radius: 3px;
        transition: width 0.5s ease;
    }}

    .confidence-label {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
    }}

    .confidence-high {{ color: var(--success); }}
    .confidence-med {{ color: var(--warning); }}
    .confidence-low {{ color: var(--error); }}

    .source-card-body {{
        font-size: 0.82rem;
        color: var(--text-secondary);
        line-height: 1.55;
        background: var(--bg-card);
        padding: 0.65rem 0.85rem;
        border-radius: var(--radius-sm);
        border-left: 3px solid var(--accent-primary);
        max-height: 120px;
        overflow: hidden;
    }}

    /* ===== THINKING / LOADING ===== */
    .thinking-indicator {{
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.75rem 1rem;
        color: var(--text-secondary);
        font-size: 0.85rem;
        animation: fadeIn 0.3s ease;
    }}

    .thinking-dots {{
        display: flex;
        gap: 4px;
    }}

    .thinking-dot {{
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--accent-primary);
        animation: dotBounce 1.4s ease-in-out infinite;
    }}

    .thinking-dot:nth-child(1) {{ animation-delay: 0s; }}
    .thinking-dot:nth-child(2) {{ animation-delay: 0.16s; }}
    .thinking-dot:nth-child(3) {{ animation-delay: 0.32s; }}

    /* ===== ERROR STATES ===== */
    .error-card {{
        display: flex;
        gap: 1rem;
        padding: 1.1rem 1.25rem;
        background: var(--bg-card);
        border: 1px solid rgba(239, 68, 68, 0.2);
        border-left: 3px solid var(--error);
        border-radius: var(--radius-md);
        animation: fadeInUp 0.3s ease;
    }}

    .error-icon {{
        font-size: 1.3rem;
        flex-shrink: 0;
        margin-top: 0.1rem;
    }}

    .error-body {{
        flex: 1;
    }}

    .error-title {{
        font-weight: 700;
        font-size: 0.88rem;
        color: var(--error);
        margin-bottom: 0.3rem;
    }}

    .error-description {{
        font-size: 0.82rem;
        color: var(--text-secondary);
        line-height: 1.5;
    }}

    .error-action {{
        margin-top: 0.6rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: var(--text-tertiary);
        background: var(--bg-tertiary);
        padding: 0.35rem 0.65rem;
        border-radius: 4px;
        display: inline-block;
    }}

    /* ===== SESSION METRICS ===== */
    .metrics-row {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.5rem;
        margin-top: 0.5rem;
    }}

    .metric-card {{
        background: var(--bg-card);
        border: 1px solid var(--border-primary);
        border-radius: var(--radius-sm);
        padding: 0.6rem 0.75rem;
        text-align: center;
    }}

    .metric-value {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-primary) !important;
    }}

    .metric-label {{
        font-size: 0.65rem;
        color: var(--text-tertiary) !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.15rem;
    }}

    /* ===== STREAMLIT OVERRIDES ===== */
    [data-testid="stChatInput"] {{
        border-color: var(--border-primary) !important;
    }}

    [data-testid="stChatInput"] textarea {{
        background-color: var(--bg-input) !important;
        color: var(--text-primary) !important;
        border-radius: var(--radius-md) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.92rem !important;
    }}

    [data-testid="stChatInput"] textarea::placeholder {{
        color: var(--text-tertiary) !important;
    }}

    [data-testid="stChatInput"] textarea:focus {{
        border-color: var(--border-focus) !important;
        box-shadow: var(--shadow-glow) !important;
    }}

    .stButton > button {{
        border-radius: var(--radius-sm) !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        transition: all 0.2s ease !important;
        border: 1px solid var(--border-primary) !important;
        background-color: var(--bg-card) !important;
        color: var(--text-primary) !important;
    }}

    .stButton > button:hover {{
        border-color: var(--border-hover) !important;
        box-shadow: var(--shadow-sm) !important;
        transform: translateY(-1px);
    }}

    .stButton > button[kind="primary"] {{
        background: var(--accent-gradient) !important;
        color: var(--text-on-primary) !important;
        border: none !important;
    }}

    .stButton > button[kind="primary"]:hover {{
        box-shadow: var(--shadow-glow), var(--shadow-md) !important;
    }}

    .stDownloadButton > button {{
        border-radius: var(--radius-sm) !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        border: 1px solid var(--border-primary) !important;
        background-color: var(--bg-card) !important;
        color: var(--text-primary) !important;
        transition: all 0.2s ease !important;
    }}

    .stDownloadButton > button:hover {{
        border-color: var(--border-hover) !important;
    }}

    [data-testid="stExpander"] {{
        border: 1px solid var(--border-primary) !important;
        border-radius: var(--radius-md) !important;
        background: var(--bg-surface) !important;
    }}

    [data-testid="stExpander"] summary {{
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }}

    .stSpinner > div {{
        border-top-color: var(--accent-primary) !important;
    }}

    .stAlert {{
        border-radius: var(--radius-sm) !important;
    }}

    /* ===== RESPONSIVE ===== */
    @media (max-width: 768px) {{
        .block-container {{
            padding-left: 1rem;
            padding-right: 1rem;
        }}

        .welcome-title {{
            font-size: 1.5rem;
        }}

        .prompt-grid {{
            grid-template-columns: 1fr;
        }}

        .metrics-row {{
            grid-template-columns: 1fr 1fr;
        }}

        .source-card-header {{
            flex-direction: column;
            align-items: flex-start;
            gap: 0.4rem;
        }}
    }}

    @media (max-width: 480px) {{
        .welcome-title {{
            font-size: 1.25rem;
        }}

        .welcome-subtitle {{
            font-size: 0.88rem;
        }}
    }}
</style>
"""

# Inject CSS with the current theme
st.markdown(
    DESIGN_SYSTEM_CSS.replace("{theme_css}", get_theme_css()),
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def get_timestamp():
    """Return current time formatted for message display."""
    return datetime.now().strftime("%I:%M %p")


def get_conversation_title(messages):
    """Extract a short title from the first user message."""
    for msg in messages:
        if msg["role"] == "user":
            title = msg["content"][:40]
            if len(msg["content"]) > 40:
                title += "..."
            return title
    return "New conversation"


def format_confidence(distance):
    """Convert cosine distance to confidence percentage and CSS class."""
    confidence = max(0, (1 - distance) * 100)
    if confidence >= 80:
        css_class = "confidence-high"
        bar_color = "var(--success)"
    elif confidence >= 60:
        css_class = "confidence-med"
        bar_color = "var(--warning)"
    else:
        css_class = "confidence-low"
        bar_color = "var(--error)"
    return confidence, css_class, bar_color


def render_error(title, description, action=None):
    """Render a styled error card."""
    action_html = f'<div class="error-action">{action}</div>' if action else ""
    html = (
        f'<div class="error-card">'
        f'<div class="error-icon" style="color:var(--error);font-weight:700;font-size:1.1rem;">!</div>'
        f'<div class="error-body">'
        f'<div class="error-title">{title}</div>'
        f'<div class="error-description">{description}</div>'
        f'{action_html}'
        f'</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def display_sources(sources: list[dict]):
    """Render retrieved source chunks as expandable citation cards."""
    if not sources:
        return

    # Build source pills as a single compact HTML string
    pills = []
    for s in sources:
        conf, _, _ = format_confidence(s["distance"])
        pills.append(
            f'<span class="source-pill">'
            f'<span class="source-pill-dot"></span>'
            f'{s["source"]} &middot; {conf:.0f}%'
            f'</span>'
        )
    pills_html = '<div class="source-pills">' + "".join(pills) + '</div>'
    st.markdown(pills_html, unsafe_allow_html=True)

    with st.expander(f"{len(sources)} sources retrieved", expanded=False):
        for source in sources:
            confidence, css_class, bar_color = format_confidence(source["distance"])

            display_text = source["text"][:350]
            if len(source["text"]) > 350:
                display_text += "..."
            # Escape HTML entities
            display_text = display_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            card_html = (
                f'<div class="source-card">'
                f'<div class="source-card-header">'
                f'<div class="source-card-title">'
                f'<span class="source-card-name">{source["source"]}</span>'
                f'<span class="source-card-chunk">Chunk #{source["chunk_index"]}</span>'
                f'</div>'
                f'<div class="source-confidence">'
                f'<div class="confidence-bar-track">'
                f'<div class="confidence-bar-fill" style="width:{confidence}%;background:{bar_color};"></div>'
                f'</div>'
                f'<span class="confidence-label {css_class}">{confidence:.1f}%</span>'
                f'</div>'
                f'</div>'
                f'<div class="source-card-body">{display_text}</div>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)


def export_chat_markdown():
    """Build a Markdown string from the current conversation."""
    lines = ["# RAG Chatbot — Conversation Export\n"]
    lines.append(f"Exported at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("---\n")
    for msg in st.session_state.messages:
        role = "**You**" if msg["role"] == "user" else "**Assistant**"
        timestamp = msg.get("timestamp", "")
        lines.append(f"### {role}  _{timestamp}_\n")
        lines.append(f"{msg['content']}\n")
        if "sources" in msg:
            lines.append("\n**Sources:**\n")
            for s in msg["sources"]:
                conf = max(0, (1 - s["distance"]) * 100)
                lines.append(f"- {s['source']} (Chunk #{s['chunk_index']}, {conf:.1f}% match)\n")
        lines.append("\n---\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    # Brand
    st.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-brand-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                <path d="M8 10h8"/><path d="M8 14h4"/>
            </svg>
        </div>
        <div class="sidebar-brand-text">
            <div class="sidebar-brand-name">RAG Assistant</div>
            <div class="sidebar-brand-tag">Knowledge-Grounded AI</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # New Chat button
    if st.button("+ New Chat", type="primary", use_container_width=True):
        # Save current conversation to history if it has messages
        if st.session_state.messages:
            title = get_conversation_title(st.session_state.messages)
            st.session_state.conversations.insert(0, {
                "title": title,
                "messages": st.session_state.messages.copy(),
                "timestamp": datetime.now().strftime("%b %d, %I:%M %p"),
            })
        st.session_state.messages = []
        st.session_state.query_count = 0
        st.session_state.total_sources = 0
        st.rerun()

    # Conversation history
    if st.session_state.conversations:
        st.markdown('<div class="sidebar-section"><div class="sidebar-label">Recent</div></div>', unsafe_allow_html=True)

        for i, conv in enumerate(st.session_state.conversations[:8]):
            if st.button(conv['title'], key=f"conv_{i}", use_container_width=True):
                # Save current first
                if st.session_state.messages:
                    current_title = get_conversation_title(st.session_state.messages)
                    st.session_state.conversations.insert(0, {
                        "title": current_title,
                        "messages": st.session_state.messages.copy(),
                        "timestamp": datetime.now().strftime("%b %d, %I:%M %p"),
                    })
                # Restore selected conversation
                restored = st.session_state.conversations.pop(
                    i + (1 if st.session_state.messages else 0)
                )
                st.session_state.messages = restored["messages"].copy()
                st.rerun()

    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

    # Upload section
    st.markdown('<div class="sidebar-section"><div class="sidebar-label">Add Knowledge</div></div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Upload .txt or .md",
        type=["txt", "md"],
        label_visibility="collapsed",
    )
    if uploaded_file is not None:
        if st.button("Index Document", type="primary", use_container_width=True):
            with st.spinner("Indexing document..."):
                save_path = Path("data") / uploaded_file.name
                save_path.parent.mkdir(exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                try:
                    ingest_single_document(save_path)
                    st.success(f"Indexed {uploaded_file.name} successfully.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to index: {e}")

    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

    # Index status
    st.markdown('<div class="sidebar-section"><div class="sidebar-label">Vector Index</div></div>', unsafe_allow_html=True)

    try:
        collection = get_chroma_collection()
        doc_count = collection.count()
        st.markdown(f"""
        <div class="status-badge status-online">
            <div class="status-dot"></div>
            <span class="status-text">Active</span>
            <span class="status-count">{doc_count} chunks</span>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.markdown("""
        <div class="status-badge status-offline">
            <div class="status-dot"></div>
            <span class="status-text">Offline</span>
        </div>
        """, unsafe_allow_html=True)
        st.caption("Run `python ingest.py` to build the index.")

    # Pipeline info (collapsible)
    with st.expander("Pipeline Settings", expanded=False):
        st.markdown("""
        <div class="config-grid">
            <span class="config-key">Embedding</span>
            <span class="config-val">gemini-embedding-001</span>
            <span class="config-key">LLM</span>
            <span class="config-val">gemini-flash-latest</span>
            <span class="config-key">Chunk Size</span>
            <span class="config-val">~500 tokens</span>
            <span class="config-key">Overlap</span>
            <span class="config-val">~50 tokens</span>
            <span class="config-key">Retrieval</span>
            <span class="config-val">Top-4 Cosine</span>
            <span class="config-key">Vector DB</span>
            <span class="config-val">ChromaDB</span>
        </div>
        """, unsafe_allow_html=True)

    # Session metrics
    with st.expander("Session", expanded=False):
        queries = st.session_state.query_count
        sources = st.session_state.total_sources
        msgs = len(st.session_state.messages)
        st.markdown(f"""
        <div class="metrics-row">
            <div class="metric-card">
                <div class="metric-value">{queries}</div>
                <div class="metric-label">Queries</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{sources}</div>
                <div class="metric-label">Sources</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{msgs}</div>
                <div class="metric-label">Messages</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

    # Theme toggle + Clear
    col_theme, col_clear = st.columns(2)
    with col_theme:
        theme_label = "Light" if st.session_state.theme == "dark" else "Dark"
        if st.button(theme_label, use_container_width=True):
            st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
            st.rerun()
    with col_clear:
        if st.button("Clear", use_container_width=True):
            st.session_state.messages = []
            st.session_state.query_count = 0
            st.session_state.total_sources = 0
            st.rerun()

    # Export
    if st.session_state.messages:
        export_md = export_chat_markdown()
        st.download_button(
            "Export Chat",
            data=export_md,
            file_name=f"rag_chat_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Main Chat Area
# ---------------------------------------------------------------------------

# Welcome screen (empty state)
if not st.session_state.messages:
    st.markdown("""
    <div class="welcome-container">
        <div class="welcome-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                <path d="M8 10h8"/><path d="M8 14h4"/>
            </svg>
        </div>
        <div class="welcome-title">What would you like to know?</div>
        <div class="welcome-subtitle">
            Ask questions grounded in your uploaded documents with verifiable source citations.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Suggested prompts as clickable buttons
    suggested = [
        "Summarize my skills",
        "What projects have I built?",
        "What is my background?",
        "What are my future plans?",
    ]

    cols = st.columns(2)
    for idx, prompt_text in enumerate(suggested):
        with cols[idx % 2]:
            if st.button(
                prompt_text,
                key=f"suggest_{idx}",
                use_container_width=True,
            ):
                st.session_state.suggested_prompt = prompt_text
                st.rerun()

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "sources" in msg:
            display_sources(msg["sources"])
        if "timestamp" in msg:
            st.caption(msg["timestamp"])


# ---------------------------------------------------------------------------
# Input Handler
# ---------------------------------------------------------------------------

# Check for suggested prompt
input_prompt = None
if "suggested_prompt" in st.session_state:
    input_prompt = st.session_state.suggested_prompt
    del st.session_state.suggested_prompt

# Chat input
if input_prompt is None:
    input_prompt = st.chat_input("Ask a question about your documents...")

if input_prompt:
    timestamp = get_timestamp()

    # Display user message
    with st.chat_message("user"):
        st.markdown(input_prompt)
        st.caption(timestamp)

    st.session_state.messages.append({
        "role": "user",
        "content": input_prompt,
        "timestamp": timestamp,
    })

    # Generate response
    with st.chat_message("assistant"):
        try:
            # Thinking indicator
            thinking = st.empty()
            thinking.markdown(
                '<div class="thinking-indicator">'
                '<div class="thinking-dots">'
                '<div class="thinking-dot"></div>'
                '<div class="thinking-dot"></div>'
                '<div class="thinking-dot"></div>'
                '</div>'
                '<span>Searching documents...</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            # Call backend (unchanged)
            result = query_rag_stream(input_prompt)
            sources = result["sources"]

            # Clear thinking indicator
            thinking.empty()

            # Stream response
            answer = st.write_stream(result["stream"])

            # Display sources
            display_sources(sources)

            # Timestamp
            resp_time = get_timestamp()
            st.caption(resp_time)

            # Update session state
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources,
                "timestamp": resp_time,
            })
            st.session_state.query_count += 1
            st.session_state.total_sources += len(sources)

        except FileNotFoundError:
            thinking.empty()
            render_error(
                "Index Not Found",
                "The document index hasn't been created yet. You need to run the ingestion pipeline first.",
                "python ingest.py",
            )
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Document index not found. Please run `python ingest.py` to initialize the database.",
                "timestamp": get_timestamp(),
            })

        except ValueError as e:
            thinking.empty()
            render_error(
                "Configuration Error",
                str(e),
                "Check your .env file",
            )
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Configuration error: {e}",
                "timestamp": get_timestamp(),
            })

        except Exception as e:
            thinking.empty()
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                render_error(
                    "Rate Limited",
                    "The Gemini API is temporarily rate-limited. Please wait a moment and try again.",
                    "Free tier: 15 req/min",
                )
            else:
                render_error(
                    "Something went wrong",
                    f"An unexpected error occurred: {error_str}",
                )
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Error: {error_str}",
                "timestamp": get_timestamp(),
            })
