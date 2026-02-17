"""
Pixel Agent - Streamlit Frontend
Main entry point with navigation.
"""

import streamlit as st

st.set_page_config(
    page_title="Pixel - Display Specialist Agent",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #888;
        margin-bottom: 2rem;
    }
    .stExpander {
        border: 1px solid #333;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### Pixel Agent")
    st.markdown("Display Specialist")
    st.divider()

    # Backend connection status
    import requests
    import os

    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")

    try:
        resp = requests.get(f"{backend_url}/health", timeout=3)
        health = resp.json()
        if health.get("status") == "healthy":
            st.success("Backend: Connected")
        else:
            st.warning(f"Backend: {health.get('status')}")
    except Exception:
        st.error("Backend: Disconnected")

    st.divider()

    # Training stats
    try:
        resp = requests.get(f"{backend_url}/pst/training/stats", timeout=3)
        stats = resp.json()
        st.metric("Training Examples", stats.get("total_examples", 0))
        st.metric("Unique Emails Labeled", stats.get("unique_emails", 0))
    except Exception:
        st.metric("Training Examples", "N/A")

# Main page
st.markdown('<div class="main-header">Pixel - Display Specialist Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Trainable email intelligence for display solutions</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### PST Import")
    st.markdown("Upload Outlook PST files to seed training data or bulk process emails.")
    st.page_link("pages/1_PST_Import.py", label="Go to PST Import")

with col2:
    st.markdown("### Chat")
    st.markdown("Submit emails one at a time for analysis with RAG-powered learning.")
    st.page_link("pages/2_Chat.py", label="Go to Chat")

with col3:
    st.markdown("### Training Review")
    st.markdown("Review, edit, and manage your training dataset.")
    st.page_link("pages/3_Training_Review.py", label="Go to Training Review")
