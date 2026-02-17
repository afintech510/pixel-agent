"""
PST Import Page - Upload PST files for training or production processing.
"""

import streamlit as st
import requests
import json
import os

st.set_page_config(page_title="PST Import - Pixel", page_icon="1", layout="wide")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.title("PST Import - Training Data Collection")
st.markdown("Upload Outlook PST files to extract emails for training or production processing.")

# Initialize session state
if "pst_emails" not in st.session_state:
    st.session_state.pst_emails = []
if "current_email_idx" not in st.session_state:
    st.session_state.current_email_idx = 0
if "import_id" not in st.session_state:
    st.session_state.import_id = None
if "labels_saved" not in st.session_state:
    st.session_state.labels_saved = 0
if "enriched_labels" not in st.session_state:
    st.session_state.enriched_labels = {}
if "enrichment_error" not in st.session_state:
    st.session_state.enrichment_error = None

# ---- UPLOAD SECTION ----
st.markdown("## 1. Upload PST File")

col1, col2 = st.columns([3, 1])
with col1:
    uploaded_file = st.file_uploader(
        "Choose a .pst file",
        type=["pst"],
        help="Outlook PST files exported from your email client",
    )
with col2:
    mode = st.radio(
        "Import Mode",
        ["Training", "Production"],
        help="Training: Label emails manually. Production: Auto-process with AI.",
    )

if uploaded_file and st.button("Parse PST File", type="primary"):
    with st.spinner(f"Parsing {uploaded_file.name}..."):
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/octet-stream")}
            params = {"mode": mode.lower()}
            resp = requests.post(
                f"{BACKEND_URL}/pst/import",
                files=files,
                params=params,
                timeout=300,
            )

            if resp.status_code == 200:
                result = resp.json()
                st.session_state.import_id = result.get("import_id")

                if mode == "Training":
                    st.session_state.pst_emails = result.get("emails", [])
                    st.session_state.current_email_idx = 0
                    st.session_state.labels_saved = 0
                    st.session_state.enriched_labels = {}
                    st.success(
                        f"Parsed {result['email_count']} emails. "
                        f"Ready for labeling!"
                    )
                else:
                    stats = result.get("stats", {})
                    st.success(
                        f"Imported {stats.get('processed', 0)} emails. "
                        f"Errors: {stats.get('errors', 0)}"
                    )
            else:
                st.error(f"Import failed: {resp.text}")
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to backend. Is Docker running?")
        except Exception as e:
            st.error(f"Error: {str(e)}")

# ---- LABELING SECTION ----
if st.session_state.pst_emails and mode == "Training":
    st.divider()
    st.markdown("## 2. Label Emails for Training")

    emails = st.session_state.pst_emails
    idx = st.session_state.current_email_idx
    total = len(emails)

    if idx >= total:
        st.success(f"All {total} emails have been labeled! ({st.session_state.labels_saved} saved)")
        if st.button("Start Over"):
            st.session_state.current_email_idx = 0
            st.session_state.labels_saved = 0
            st.session_state.enriched_labels = {}
            st.rerun()
    else:
        # Progress bar
        progress = idx / total
        st.progress(progress, text=f"Email {idx + 1} of {total} ({st.session_state.labels_saved} labeled)")

        email = emails[idx]

        # Navigation
        nav_col1, nav_col2, nav_col3 = st.columns([1, 6, 1])
        with nav_col1:
            if st.button("< Prev", disabled=idx == 0):
                st.session_state.current_email_idx = max(0, idx - 1)
                st.session_state.enriched_labels = {}
                st.session_state.enrichment_error = None
                st.rerun()
        with nav_col3:
            if st.button("Skip >"):
                st.session_state.current_email_idx = min(total - 1, idx + 1)
                st.session_state.enriched_labels = {}
                st.session_state.enrichment_error = None
                st.rerun()

        # Display email
        st.markdown("### Email Content")
        email_col, label_col = st.columns([1, 1])

        with email_col:
            st.markdown(f"**From:** {email.get('from_name', 'Unknown')} <{email.get('sender_email', '')}>")
            st.markdown(f"**To:** {', '.join(email.get('recipient_emails', []))}")
            if email.get("cc_emails"):
                st.markdown(f"**CC:** {', '.join(email['cc_emails'])}")
            st.markdown(f"**Subject:** {email.get('subject', 'No subject')}")
            st.markdown(f"**Date:** {email.get('sent_at', 'Unknown')}")
            st.markdown(f"**Folder:** {email.get('folder_path', '')}")
            st.divider()
            # Copyable email body using st.code (has built-in copy button)
            st.markdown("**Email Body:**")
            body_text = email.get("body", "")[:5000]
            st.code(body_text, language=None)

        with label_col:
            st.markdown("### Labels")

            # --- AI Enrichment Button (OUTSIDE the form) ---
            enrich_col1, enrich_col2 = st.columns([1, 1])
            with enrich_col1:
                if st.button("Enrich with AI", key=f"enrich_{idx}", type="secondary"):
                    st.session_state.enrichment_error = None
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/pst/enrich-labels",
                            json={
                                "subject": email.get("subject", ""),
                                "body": email.get("body", "")[:5000],
                                "from_name": email.get("from_name", ""),
                                "sender_email": email.get("sender_email", ""),
                                "recipient_emails": email.get("recipient_emails", []),
                                "cc_emails": email.get("cc_emails", []),
                                "sent_at": email.get("sent_at"),
                            },
                            timeout=60,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.session_state.enriched_labels = result.get("labels", {})
                        elif resp.status_code == 503:
                            st.session_state.enrichment_error = "OpenAI API key not configured."
                        else:
                            st.session_state.enrichment_error = f"Enrichment failed: {resp.text}"
                    except requests.exceptions.Timeout:
                        st.session_state.enrichment_error = "AI enrichment timed out. Try again."
                    except requests.exceptions.ConnectionError:
                        st.session_state.enrichment_error = "Cannot connect to backend."
                    except Exception as e:
                        st.session_state.enrichment_error = f"Error: {str(e)}"

                    # Clear widget keys so form re-renders with new defaults
                    widget_keys = [
                        f"summary_{idx}", f"priority_{idx}", f"intent_{idx}",
                        f"customer_{idx}", f"class_{idx}", f"stage_{idx}",
                        f"parts_{idx}", f"size_{idx}", f"bright_{idx}",
                        f"iface_{idx}", f"res_{idx}", f"touch_{idx}",
                        f"temp_{idx}", f"risks_{idx}", f"draft_{idx}",
                        f"followups_{idx}",
                    ]
                    for wk in widget_keys:
                        if wk in st.session_state:
                            del st.session_state[wk]
                    st.rerun()

            with enrich_col2:
                if st.session_state.enriched_labels:
                    st.caption("AI suggestions loaded. Review and save.")

            if st.session_state.enrichment_error:
                st.error(st.session_state.enrichment_error)

            # Read defaults from enrichment (or empty dict)
            defaults = st.session_state.enriched_labels

            with st.form(f"label_form_{idx}", clear_on_submit=False):
                # Summary
                summary = st.text_area(
                    "Thread Summary (1-3 bullets)",
                    value=defaults.get("summary", ""),
                    height=100,
                    placeholder="- Customer needs 10.1\" high-bright display\n- Target 5k/year volume",
                    key=f"summary_{idx}",
                )

                # Priority & Intent
                pri_col, intent_col = st.columns(2)
                with pri_col:
                    priority_options = ["P0 (Hot)", "P1 (Warm)", "P2 (Cold)"]
                    priority_default = defaults.get("priority", "")
                    priority_idx = priority_options.index(priority_default) if priority_default in priority_options else 0
                    priority = st.selectbox(
                        "Priority",
                        priority_options,
                        index=priority_idx,
                        key=f"priority_{idx}",
                    )
                with intent_col:
                    intent_options = [
                        "quote_request",
                        "technical_support",
                        "order_status",
                        "sample_request",
                        "rfq_response",
                        "intro",
                        "follow_up",
                        "update",
                        "spam",
                    ]
                    intent_default = defaults.get("intent", "")
                    intent_idx = intent_options.index(intent_default) if intent_default in intent_options else 0
                    intent = st.selectbox(
                        "Intent",
                        intent_options,
                        index=intent_idx,
                        key=f"intent_{idx}",
                    )

                # Customer info
                cust_col, class_col = st.columns(2)
                with cust_col:
                    customer_name = st.text_input(
                        "Customer Name",
                        value=defaults.get("customer_name", ""),
                        key=f"customer_{idx}",
                    )
                with class_col:
                    class_options = ["Customer", "Supplier", "Internal", "Unclassified"]
                    class_default = defaults.get("company_classification", "")
                    class_idx = class_options.index(class_default) if class_default in class_options else 0
                    company_class = st.selectbox(
                        "Company Type",
                        class_options,
                        index=class_idx,
                        key=f"class_{idx}",
                    )

                # Opportunity stage
                stage_options = [
                    "New",
                    "RFQ_Sent",
                    "Quotes_Received",
                    "Proposed",
                    "Samples_Requested",
                    "Samples_Shipped",
                    "Evaluating",
                    "Design_In",
                    "Production",
                    "N/A",
                ]
                stage_default = defaults.get("opportunity_stage", "")
                stage_idx = stage_options.index(stage_default) if stage_default in stage_options else 0
                stage = st.selectbox(
                    "Opportunity Stage",
                    stage_options,
                    index=stage_idx,
                    key=f"stage_{idx}",
                )

                # Part numbers
                part_numbers = st.text_area(
                    "Part Numbers (one per line)",
                    value=defaults.get("part_numbers", ""),
                    height=80,
                    placeholder="AM-1280800N2TZQW-T48H\nWF70A2TIAGDNN0",
                    key=f"parts_{idx}",
                )

                # Technical specs
                specs_col1, specs_col2 = st.columns(2)
                with specs_col1:
                    display_size = st.text_input("Display Size", value=defaults.get("display_size", ""), placeholder="10.1\"", key=f"size_{idx}")
                    brightness = st.text_input("Brightness (nits)", value=defaults.get("brightness_nits", ""), placeholder="1000", key=f"bright_{idx}")
                    interface = st.text_input("Interface", value=defaults.get("interface", ""), placeholder="MIPI DSI", key=f"iface_{idx}")
                with specs_col2:
                    resolution = st.text_input("Resolution", value=defaults.get("resolution", ""), placeholder="1280x800", key=f"res_{idx}")
                    touch = st.text_input("Touch", value=defaults.get("touch", ""), placeholder="PCAP, USB", key=f"touch_{idx}")
                    temp_range = st.text_input("Temp Range", value=defaults.get("temp_range", ""), placeholder="-20~70C", key=f"temp_{idx}")

                # Risks / missing info
                risks = st.text_area(
                    "Risks / Missing Info",
                    value=defaults.get("risks", ""),
                    height=80,
                    placeholder="- Interface not confirmed\n- Volume unclear",
                    key=f"risks_{idx}",
                )

                # Draft reply
                draft_reply = st.text_area(
                    "Draft Reply",
                    value=defaults.get("draft_reply", ""),
                    height=150,
                    placeholder="Hi [Customer], Thank you for your inquiry...",
                    key=f"draft_{idx}",
                )

                # Follow-up actions
                follow_ups = st.text_area(
                    "Follow-up Actions",
                    value=defaults.get("follow_ups", ""),
                    height=80,
                    placeholder="- Send RFQ to Winstar/Ampire (3 days)\n- Follow up with customer on interface (5 days)",
                    key=f"followups_{idx}",
                )

                # Submit
                submitted = st.form_submit_button("Save Label & Next", type="primary")

                if submitted:
                    # Build label data
                    label_data = {
                        "summary": summary,
                        "priority": priority.split(" ")[0],  # "P0 (Hot)" -> "P0"
                        "intent": intent,
                        "customer_name": customer_name,
                        "company_classification": company_class,
                        "opportunity_stage": stage,
                        "part_numbers": [
                            pn.strip()
                            for pn in part_numbers.split("\n")
                            if pn.strip()
                        ],
                        "technical_specs": {
                            "display_size": display_size,
                            "brightness_nits": brightness,
                            "interface": interface,
                            "resolution": resolution,
                            "touch": touch,
                            "temp_range": temp_range,
                        },
                        "risks_missing_info": [
                            r.strip().lstrip("- ")
                            for r in risks.split("\n")
                            if r.strip()
                        ],
                        "draft_reply": draft_reply,
                        "follow_up_actions": [
                            f.strip().lstrip("- ")
                            for f in follow_ups.split("\n")
                            if f.strip()
                        ],
                    }

                    # Save to backend
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/pst/training/label",
                            json={
                                "email_data": email,
                                "label_data": label_data,
                            },
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            st.session_state.labels_saved += 1
                            st.session_state.current_email_idx = idx + 1
                            st.session_state.enriched_labels = {}
                            st.session_state.enrichment_error = None
                            st.rerun()
                        else:
                            st.error(f"Save failed: {resp.text}")
                    except Exception as e:
                        st.error(f"Error saving label: {str(e)}")

# ---- IMPORT HISTORY ----
st.divider()
st.markdown("## Import History")

try:
    resp = requests.get(f"{BACKEND_URL}/pst/imports", timeout=5)
    if resp.status_code == 200:
        imports = resp.json().get("imports", [])
        if imports:
            for imp in imports:
                with st.expander(
                    f"{imp['filename']} - {imp['status']} ({imp.get('emails_processed', 0)} emails)"
                ):
                    st.json(imp)
        else:
            st.info("No imports yet. Upload a PST file to get started.")
    else:
        st.warning("Could not load import history.")
except Exception:
    st.info("Connect to backend to see import history.")
