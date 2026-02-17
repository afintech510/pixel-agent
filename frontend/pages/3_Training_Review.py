"""
Pixel Agent - Training Review
Review, edit, and manage training dataset for RAG learning.
"""

import streamlit as st
import requests
import os
import json
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Training Review - Pixel Agent",
    page_icon="📚",
    layout="wide",
)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")

# --- Session State Initialization ---
if "page_offset" not in st.session_state:
    st.session_state.page_offset = 0
if "show_detail" not in st.session_state:
    st.session_state.show_detail = False
if "selected_example_id" not in st.session_state:
    st.session_state.selected_example_id = None
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "Browse"


# --- Sidebar ---
with st.sidebar:
    st.markdown("### Training Review")
    st.divider()

    # Stats cards
    try:
        resp = requests.get(f"{BACKEND_URL}/training/stats", timeout=3)
        stats = resp.json()
        st.metric("Total Examples", stats.get("total_examples", 0))
        st.metric("PST Labeled", stats.get("pst_count", 0))
        st.metric("Chat Corrected", stats.get("chat_count", 0))
        st.metric("Full Corrections", stats.get("full_corrections", 0))
    except Exception as e:
        st.error("Backend unavailable")
        st.caption(str(e))

    st.divider()
    st.caption("Manage your training dataset for improved RAG learning.")


# --- Main Area ---
st.title("Training Review")
st.caption("Review, edit, and manage your training dataset")

# Tab navigation
tab1, tab2, tab3, tab4 = st.tabs(["📊 Browse", "🔍 Search", "📤 Import/Export", "🔧 Maintenance"])


# ============================================================
# TAB 1: BROWSE TRAINING DATA
# ============================================================
with tab1:
    st.markdown("### Browse Training Examples")

    # Filter controls
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filter_intent = st.selectbox(
            "Intent",
            ["All", "quote_request", "technical_support", "order_status", "sample_request",
             "rfq_response", "intro", "follow_up", "update", "spam"],
            key="filter_intent"
        )
    with col2:
        filter_priority = st.selectbox("Priority", ["All", "P0", "P1", "P2"], key="filter_priority")
    with col3:
        filter_correction_type = st.selectbox("Correction Type", ["All", "full", "partial"], key="filter_correction_type")
    with col4:
        filter_source = st.selectbox("Source", ["All", "pst", "chat"], key="filter_source")

    col5, col6 = st.columns(2)
    with col5:
        filter_customer = st.text_input("Customer Name (contains)", "", key="filter_customer")
    with col6:
        filter_search = st.text_input("Search in Subject/Body", "", key="filter_search")

    # Build filter params
    filter_params = {
        "limit": 50,
        "offset": st.session_state.page_offset,
    }
    if filter_intent != "All":
        filter_params["intent"] = filter_intent
    if filter_priority != "All":
        filter_params["priority"] = filter_priority
    if filter_correction_type != "All":
        filter_params["correction_type"] = filter_correction_type
    if filter_source != "All":
        filter_params["source"] = filter_source
    if filter_customer:
        filter_params["customer"] = filter_customer
    if filter_search:
        filter_params["search"] = filter_search

    # Fetch data
    try:
        resp = requests.get(f"{BACKEND_URL}/training/examples", params=filter_params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            examples = data.get("examples", [])
            total = data.get("total", 0)

            if examples:
                st.markdown(f"**Showing {len(examples)} of {total} examples**")

                # Display as table
                df = pd.DataFrame(examples)

                # Format display columns
                df_display = df[[
                    "subject", "sender_email", "priority", "intent",
                    "correction_type", "source", "created_at"
                ]].copy()

                df_display.columns = [
                    "Subject", "Sender", "Priority", "Intent",
                    "Type", "Source", "Created"
                ]

                # Add View button column
                for idx, row in df.iterrows():
                    col_btn, col_data = st.columns([1, 9])
                    with col_btn:
                        if st.button("View", key=f"view_{row['id']}", use_container_width=True):
                            st.session_state.selected_example_id = row['id']
                            st.session_state.show_detail = True
                            st.rerun()
                    with col_data:
                        st.markdown(
                            f"**{row['subject'][:60]}{'...' if len(row['subject']) > 60 else ''}** | "
                            f"{row['sender_email']} | "
                            f":{('red' if row['priority'] == 'P0' else 'orange' if row['priority'] == 'P1' else 'green')}[{row['priority']}] | "
                            f"{row['intent'] or 'N/A'} | "
                            f"{row['correction_type']} | "
                            f"{row['source']}"
                        )

                st.divider()

                # Pagination
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if st.button("← Previous", disabled=(st.session_state.page_offset == 0)):
                        st.session_state.page_offset = max(0, st.session_state.page_offset - 50)
                        st.rerun()
                with col2:
                    st.markdown(f"<center>Page {st.session_state.page_offset // 50 + 1} of {(total + 49) // 50}</center>", unsafe_allow_html=True)
                with col3:
                    if st.button("Next →", disabled=(st.session_state.page_offset + 50 >= total)):
                        st.session_state.page_offset += 50
                        st.rerun()

                # Bulk actions
                st.divider()
                st.markdown("### Bulk Actions")
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Export Current View (JSON)", use_container_width=True):
                        export_resp = requests.get(f"{BACKEND_URL}/training/examples/export", params={**filter_params, "format": "json"})
                        if export_resp.status_code == 200:
                            st.download_button(
                                label="Download JSON",
                                data=export_resp.content,
                                file_name=f"training_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                mime="application/json"
                            )
                with col2:
                    if st.button("Export Current View (CSV)", use_container_width=True):
                        export_resp = requests.get(f"{BACKEND_URL}/training/examples/export", params={**filter_params, "format": "csv"})
                        if export_resp.status_code == 200:
                            st.download_button(
                                label="Download CSV",
                                data=export_resp.content,
                                file_name=f"training_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )

            else:
                st.info("No training examples found with the current filters.")
                st.caption("Try adjusting your filters or add training data via PST Import or Chat corrections.")

        else:
            st.error(f"Failed to load training examples: {resp.status_code}")

    except Exception as e:
        st.error(f"Error loading training examples: {e}")


# ============================================================
# DETAIL VIEW MODAL (shown when user clicks "View")
# ============================================================
if st.session_state.get("show_detail") and st.session_state.selected_example_id:
    st.divider()
    st.markdown("---")
    st.markdown("## Training Example Details")

    try:
        detail_resp = requests.get(f"{BACKEND_URL}/training/examples/{st.session_state.selected_example_id}", timeout=10)
        if detail_resp.status_code == 200:
            example = detail_resp.json()

            # Email Details
            with st.expander("📧 Email Details", expanded=True):
                st.markdown(f"**Subject:** {example['email']['subject']}")
                st.markdown(f"**From:** {example['email']['from_name']} <{example['email']['sender_email']}>")
                st.markdown(f"**Sent:** {example['email']['sent_at']}")
                st.text_area("Email Body", example['email']['body'], height=200, disabled=True, key="email_body_display")

            col1, col2 = st.columns(2)

            # Original AI Output
            with col1:
                with st.expander("🤖 Original AI Output", expanded=False):
                    st.json(example['original_ai_output'])

            # Corrected Output (Editable)
            with col2:
                with st.expander("✏️ Corrected Output (Editable)", expanded=True):
                    corrected_json_str = st.text_area(
                        "Edit Corrected Output (JSON)",
                        value=json.dumps(example['corrected_output'], indent=2),
                        height=400,
                        key="corrected_output_editor"
                    )

                    if st.button("💾 Save Changes", type="primary"):
                        try:
                            updated_output = json.loads(corrected_json_str)
                            update_resp = requests.put(
                                f"{BACKEND_URL}/training/examples/{st.session_state.selected_example_id}",
                                json={"corrected_output": updated_output},
                                timeout=10
                            )
                            if update_resp.status_code == 200:
                                st.success("✅ Saved successfully! Embedding regenerated.")
                                st.rerun()
                            else:
                                st.error(f"Failed to save: {update_resp.status_code}")
                        except json.JSONDecodeError:
                            st.error("❌ Invalid JSON format. Please fix syntax errors.")
                        except Exception as e:
                            st.error(f"Error saving: {e}")

            # Metadata
            with st.expander("ℹ️ Metadata"):
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    st.markdown(f"**Correction Type:** `{example['correction_type']}`")
                    st.markdown(f"**Source:** `{example['corrected_by'] or 'chat'}`")
                with col_m2:
                    st.markdown(f"**Confidence Before:** `{example['confidence_before'] or 'N/A'}`")
                    st.markdown(f"**Embedding Exists:** `{example['embedding_exists']}`")
                with col_m3:
                    if example.get('feedback'):
                        st.markdown(f"**User Feedback:** `{example['feedback']['rating']}`")
                    st.markdown(f"**Created:** `{example['created_at']}`")

            # Action buttons
            st.divider()
            col_act1, col_act2, col_act3 = st.columns([1, 1, 4])
            with col_act1:
                if st.button("🔙 Close", use_container_width=True):
                    st.session_state.show_detail = False
                    st.session_state.selected_example_id = None
                    st.rerun()
            with col_act2:
                if st.button("🗑️ Delete Example", type="primary", use_container_width=True):
                    # Confirmation checkbox
                    if "delete_confirmed" not in st.session_state:
                        st.session_state.delete_confirmed = False

                    confirm = st.checkbox("⚠️ Confirm deletion (cannot be undone)", key="delete_confirm")
                    if confirm:
                        delete_resp = requests.delete(f"{BACKEND_URL}/training/examples/{st.session_state.selected_example_id}", timeout=10)
                        if delete_resp.status_code == 200:
                            st.success("✅ Example deleted successfully!")
                            st.session_state.show_detail = False
                            st.session_state.selected_example_id = None
                            st.rerun()
                        else:
                            st.error(f"Failed to delete: {delete_resp.status_code}")

        else:
            st.error(f"Failed to load example details: {detail_resp.status_code}")
            if st.button("Close"):
                st.session_state.show_detail = False
                st.session_state.selected_example_id = None
                st.rerun()

    except Exception as e:
        st.error(f"Error loading example details: {e}")
        if st.button("Close"):
            st.session_state.show_detail = False
            st.session_state.selected_example_id = None
            st.rerun()


# ============================================================
# TAB 2: SEARCH
# ============================================================
with tab2:
    st.markdown("### Search Training Examples")
    st.caption("Search by keywords in subject, body, or technical specs")

    search_query = st.text_input("Search Query", placeholder="e.g., 7-inch TFT display", key="search_query")
    search_fields = st.multiselect("Search In", ["subject", "body", "specs"], default=["subject", "body"], key="search_fields")

    if st.button("🔍 Search", type="primary"):
        if not search_query:
            st.warning("Please enter a search query")
        else:
            try:
                search_resp = requests.get(
                    f"{BACKEND_URL}/training/examples/search",
                    params={"q": search_query, "fields": search_fields},
                    timeout=10
                )
                if search_resp.status_code == 200:
                    st.session_state.search_results = search_resp.json()
                else:
                    st.error(f"Search failed: {search_resp.status_code}")
            except Exception as e:
                st.error(f"Search error: {e}")

    # Display search results
    if st.session_state.search_results:
        results = st.session_state.search_results
        st.markdown(f"### Found {results['total']} results")

        if results['total'] > 0:
            for result in results['results']:
                relevance_pct = int(result['relevance_score'] * 100)
                with st.expander(f"{result['subject']} (Relevance: {relevance_pct}%)"):
                    st.markdown(f"**Snippet:** {result['snippet']}")
                    st.caption(f"Created: {result['created_at']}")
                    if st.button("View Full Example", key=f"search_view_{result['id']}"):
                        st.session_state.selected_example_id = result['id']
                        st.session_state.show_detail = True
                        st.rerun()
        else:
            st.info("No results found. Try different keywords or search fields.")


# ============================================================
# TAB 3: IMPORT/EXPORT
# ============================================================
with tab3:
    st.markdown("### Export Training Data")
    st.caption("Download your training dataset as JSON or CSV")

    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        export_format = st.radio("Format", ["JSON", "CSV"], key="export_format")
    with col_exp2:
        include_embeddings = st.checkbox("Include embeddings (JSON only)", key="include_embeddings")

    if st.button("Generate Export", type="primary"):
        try:
            export_params = {
                "format": export_format.lower(),
                "include_embeddings": include_embeddings if export_format == "JSON" else False
            }
            export_resp = requests.get(f"{BACKEND_URL}/training/examples/export", params=export_params, timeout=30)

            if export_resp.status_code == 200:
                filename = f"training_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_format.lower()}"
                mime_type = "application/json" if export_format == "JSON" else "text/csv"

                st.download_button(
                    label=f"⬇️ Download {export_format}",
                    data=export_resp.content,
                    file_name=filename,
                    mime=mime_type,
                    use_container_width=True
                )
                st.success(f"✅ Export ready! Click the button above to download.")
            else:
                st.error(f"Export failed: {export_resp.status_code}")
        except Exception as e:
            st.error(f"Export error: {e}")

    st.divider()

    st.markdown("### Import Training Data")
    st.caption("Upload a CSV file to import training examples")

    st.markdown("""
    **Expected CSV format:**
    - `original_email_text` (required): Raw email text
    - `corrected_output_json` (required): JSON string with corrected fields
    - `correction_type` (optional): "full" or "partial"
    - `corrected_by` (optional): Source identifier (default: "csv_import")
    """)

    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"], key="import_csv_file")

    if uploaded_file and st.button("📤 Import", type="primary"):
        with st.spinner("Importing training data..."):
            try:
                files = {"file": uploaded_file}
                import_resp = requests.post(f"{BACKEND_URL}/training/examples/import", files=files, timeout=60)

                if import_resp.status_code == 200:
                    result = import_resp.json()
                    if result["success"]:
                        st.success(f"✅ Successfully imported {result['imported_count']} examples!")
                        if result['skipped_count'] > 0:
                            st.warning(f"⚠️ Skipped {result['skipped_count']} rows due to errors")
                        if result.get('errors'):
                            st.error("**Errors encountered:**")
                            for err in result['errors']:
                                st.markdown(f"- Row {err['row']}: {err['error']}")
                    else:
                        st.error("Import failed")
                else:
                    st.error(f"Import failed: {import_resp.status_code}")
            except Exception as e:
                st.error(f"Import error: {e}")


# ============================================================
# TAB 4: MAINTENANCE
# ============================================================
with tab4:
    st.markdown("### Regenerate Embeddings")
    st.caption("Regenerate vector embeddings for RAG retrieval. Useful after prompt or model changes.")

    regenerate_scope = st.radio(
        "Regeneration Scope",
        ["All examples", "Examples without embeddings"],
        key="regenerate_scope"
    )
    force_regenerate = st.checkbox("Force regenerate (overwrite existing embeddings)", key="force_regenerate")

    if st.button("🔄 Regenerate Embeddings", type="primary"):
        confirm_regen = st.checkbox("⚠️ Confirm regeneration (may take several minutes and incur API costs)", key="confirm_regen")
        if confirm_regen:
            with st.spinner("Regenerating embeddings... This may take a while."):
                try:
                    payload = {
                        "example_ids": None if regenerate_scope == "All examples" else [],
                        "force": force_regenerate
                    }
                    regen_resp = requests.post(
                        f"{BACKEND_URL}/training/examples/regenerate-embeddings",
                        json=payload,
                        timeout=300  # 5 minute timeout
                    )

                    if regen_resp.status_code == 200:
                        result = regen_resp.json()
                        if result["success"]:
                            st.success(f"✅ Successfully regenerated {result['regenerated_count']} embeddings!")
                            if result['failed_count'] > 0:
                                st.warning(f"⚠️ Failed to regenerate {result['failed_count']} embeddings")
                                if result.get('failed_ids'):
                                    st.caption(f"Failed IDs: {', '.join(result['failed_ids'][:5])}")
                        else:
                            st.error("Regeneration failed")
                    else:
                        st.error(f"Regeneration failed: {regen_resp.status_code}")
                except Exception as e:
                    st.error(f"Regeneration error: {e}")

    st.divider()

    st.markdown("### Database Indexes")
    st.caption("Recommended indexes for improved query performance")

    with st.expander("View SQL for Index Creation"):
        st.code("""
-- Add indexes for better training review performance
CREATE INDEX IF NOT EXISTS idx_training_correction_type ON training_examples(correction_type);
CREATE INDEX IF NOT EXISTS idx_training_created_at ON training_examples(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_training_email_id ON training_examples(email_id);
        """, language="sql")

    st.info("💡 These indexes can be added manually via psql or pgAdmin if query performance is slow.")

    st.divider()

    st.markdown("### Coming Soon")
    st.info("🔧 Duplicate detection and data quality metrics will be added in a future update.")
