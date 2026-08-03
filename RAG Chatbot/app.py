"""
app.py -- Enterprise RAG Chatbot UI
==================================
A minimal, ultra-professional chat interface for document-grounded QA.
Features real-time response streaming, strict source citation, and zero hallucination.

Run with:
    streamlit run app.py
"""

import os
import time
from pathlib import Path
import streamlit as st
from rag_pipeline import query_rag_stream, get_chroma_collection
from ingest import ingest_single_document


# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="RAG Knowledge Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Custom Enterprise Design System (CSS)
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Global Theme & Reset */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #E2E8F0;
        background-color: #090D16;
    }

    /* Main Container Padding */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 960px;
    }

    /* Header Banner */
    .brand-banner {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-left: 4px solid #6366f1;
        border-radius: 10px;
        padding: 1.5rem 1.75rem;
        margin-bottom: 2rem;
        box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.4);
    }

    .brand-title-row {
        display: flex;
        align-items: center;
        margin-bottom: 0.35rem;
    }

    .brand-badge {
        display: inline-flex;
        align-items: center;
        padding: 0.2rem 0.6rem;
        background: rgba(59, 130, 246, 0.12);
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 600;
        color: #60A5FA;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    .brand-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.5rem;
        font-weight: 800;
        color: #FFFFFF !important;
        margin: 0;
        letter-spacing: -0.02em;
    }

    .brand-subtitle {
        color: #94A3B8;
        font-size: 0.9rem;
        margin: 0;
        line-height: 1.5;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid rgba(255, 255, 255, 0.07);
    }

    [data-testid="stSidebar"] * {
        color: #CBD5E1 !important;
    }

    [data-testid="stFileUploadDropzone"] * {
        color: #000000 !important;
    }

    .sidebar-section-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748B !important;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }

    /* Architecture Grid Table */
    .config-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 0.5rem;
        font-size: 0.82rem;
    }

    .config-table td {
        padding: 0.5rem 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .config-label {
        color: #94A3B8 !important;
        font-weight: 400;
    }

    .config-value {
        color: #F1F5F9 !important;
        font-weight: 600;
        text-align: right;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
    }

    /* Status Indicator Badge */
    .status-card {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-top: 0.5rem;
    }

    .status-dot-container {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.82rem;
        font-weight: 600;
    }

    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
    }

    .status-ready .status-dot {
        background-color: #10B981;
        box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
    }

    .status-error .status-dot {
        background-color: #EF4444;
        box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
    }

    /* Source Citation Cards */
    .source-container {
        margin-top: 0.75rem;
        margin-bottom: 0.5rem;
    }

    .source-card {
        background: #0F172A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.6rem;
        transition: border-color 0.2s ease;
    }

    .source-card:hover {
        border-color: rgba(59, 130, 246, 0.3);
    }

    .source-header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.5rem;
    }

    .source-title-group {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        font-weight: 600;
        color: #60A5FA;
    }

    .source-tag {
        background: rgba(255, 255, 255, 0.06);
        color: #94A3B8;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 500;
    }

    .similarity-pill {
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.25);
        color: #34D399;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 0.15rem 0.5rem;
        border-radius: 12px;
        font-family: 'JetBrains Mono', monospace;
    }

    .source-content {
        font-size: 0.83rem;
        color: #CBD5E1;
        line-height: 1.5;
        background: rgba(0, 0, 0, 0.2);
        padding: 0.6rem 0.75rem;
        border-radius: 4px;
        border-left: 2px solid rgba(59, 130, 246, 0.4);
    }

    /* Workflow Step List */
    .step-list {
        list-style: none;
        padding: 0;
        margin: 0;
    }

    .step-item {
        display: flex;
        gap: 0.6rem;
        margin-bottom: 0.75rem;
        font-size: 0.82rem;
        line-height: 1.4;
    }

    .step-num {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        background: rgba(255, 255, 255, 0.08);
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 700;
        color: #38BDF8 !important;
        flex-shrink: 0;
    }

    /* Hide Default Streamlit Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper: Display Source Citations
# ---------------------------------------------------------------------------

def display_sources(sources: list[dict]):
    """Render retrieved source chunks in a clean enterprise citation view."""
    with st.expander("Retrieved Document Citations", expanded=False):
        for source in sources:
            similarity = max(0, (1 - source["distance"]) * 100)
            display_text = source["text"][:450]
            if len(source["text"]) > 450:
                display_text += "..."

            st.markdown(
                f"""
                <div class="source-card">
                    <div class="source-header-row">
                        <div class="source-title-group">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                                <polyline points="14 2 14 8 20 8"/>
                            </svg>
                            <span>{source['source']}</span>
                            <span class="source-tag">Chunk #{source['chunk_index']}</span>
                        </div>
                        <span class="similarity-pill">{similarity:.1f}% Match</span>
                    </div>
                    <div class="source-content">{display_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Sidebar -- Architecture & Index Diagnostics
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="sidebar-section-title">Add Knowledge</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload a .txt or .md file", type=["txt", "md"], label_visibility="collapsed")
    if uploaded_file is not None:
        if st.button("Index Document", type="primary", use_container_width=True):
            with st.spinner("Indexing new document..."):
                # Save file to data directory
                save_path = Path("data") / uploaded_file.name
                save_path.parent.mkdir(exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Ingest the single document
                try:
                    ingest_single_document(save_path)
                    st.success(f"Indexed {uploaded_file.name} successfully!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to index: {e}")

    st.markdown('<div class="sidebar-section-title">System Architecture</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <ul class="step-list">
        <li class="step-item">
            <span class="step-num">1</span>
            <div><strong>Document Ingestion</strong><br><span style="color:#64748B">Plain text chunking with 50-token overlap</span></div>
        </li>
        <li class="step-item">
            <span class="step-num">2</span>
            <div><strong>Vector Indexing</strong><br><span style="color:#64748B">Dense embeddings in local ChromaDB</span></div>
        </li>
        <li class="step-item">
            <span class="step-num">3</span>
            <div><strong>Semantic Retrieval</strong><br><span style="color:#64748B">Top-K=4 cosine similarity search</span></div>
        </li>
        <li class="step-item">
            <span class="step-num">4</span>
            <div><strong>Grounded Generation</strong><br><span style="color:#64748B">Gemini generation constrained strictly to context</span></div>
        </li>
    </ul>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">Pipeline Settings</div>', unsafe_allow_html=True)
    st.markdown("""
    <table class="config-table">
        <tr><td class="config-label">Embedding Model</td><td class="config-value">gemini-embedding-001</td></tr>
        <tr><td class="config-label">Generative LLM</td><td class="config-value">gemini-flash-latest</td></tr>
        <tr><td class="config-label">Target Chunk Size</td><td class="config-value">~500 tokens</td></tr>
        <tr><td class="config-label">Chunk Overlap</td><td class="config-value">~50 tokens</td></tr>
        <tr><td class="config-label">Retrieval Count</td><td class="config-value">Top-4 Chunks</td></tr>
        <tr><td class="config-label">Vector Store</td><td class="config-value">ChromaDB (Local)</td></tr>
    </table>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">Vector Index Status</div>', unsafe_allow_html=True)

    try:
        collection = get_chroma_collection()
        doc_count = collection.count()
        st.markdown(
            f"""
            <div class="status-card status-ready">
                <div class="status-dot-container">
                    <div class="status-dot"></div>
                    <span>Index Active</span>
                </div>
                <span style="font-family:'JetBrains Mono'; font-size:0.78rem; color:#94A3B8;">{doc_count} Chunks</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.markdown(
            """
            <div class="status-card status-error">
                <div class="status-dot-container">
                    <div class="status-dot"></div>
                    <span>Index Offline</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.error(f"Run `python ingest.py` to index documents.\n\n{e}")

    st.markdown('<br>', unsafe_allow_html=True)
    if st.button("Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ---------------------------------------------------------------------------
# Main Interface Header
# ---------------------------------------------------------------------------

st.markdown("""
<div class="brand-banner">
    <div class="brand-title-row">
        <h1 class="brand-title">RAG Chatbot</h1>
    </div>
    <p class="brand-subtitle">
        Query workspace documents with verifiable source citations and strict zero-hallucination constraints.
    </p>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Chat History Render
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and "sources" in message:
            display_sources(message["sources"])


# ---------------------------------------------------------------------------
# Input Handler & Real-Time Generation
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask a question based on uploaded repository documents..."):
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching document index..."):
                result = query_rag_stream(prompt)
                sources = result["sources"]

            answer = st.write_stream(result["stream"])
            display_sources(sources)

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources,
            })

        except FileNotFoundError:
            error_msg = (
                "Document index not found. "
                "Please run `python ingest.py` to initialize the database."
            )
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
            })

        except ValueError as e:
            error_msg = f"Configuration error: {e}"
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
            })

        except Exception as e:
            error_msg = f"An execution error occurred: {e}"
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
            })
