"""
Pixel Agent - Chat Interface
Submit emails one at a time for RAG-augmented analysis.
"""

import streamlit as st
import requests
import os
import json

st.set_page_config(
    page_title="Pixel Chat - Email Analysis",
    page_icon="",
    layout="wide",
)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")


# --- Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_analysis" not in st.session_state:
    st.session_state.current_analysis = None
if "current_email_id" not in st.session_state:
    st.session_state.current_email_id = None
if "show_correction" not in st.session_state:
    st.session_state.show_correction = False
if "show_better_draft" not in st.session_state:
    st.session_state.show_better_draft = False


# --- Sidebar ---
with st.sidebar:
    st.markdown("### Pixel Chat")
    st.markdown("Paste an email to analyze")
    st.divider()

    # RAG stats
    try:
        resp = requests.get(f"{BACKEND_URL}/pst/training/stats", timeout=3)
        stats = resp.json()
        st.metric("Training Examples", stats.get("total_examples", 0))
        st.metric("Emails Labeled", stats.get("unique_emails", 0))
    except Exception:
        st.metric("Training Examples", "N/A")

    st.divider()

    # History
    st.markdown("#### Recent Analyses")
    try:
        resp = requests.get(f"{BACKEND_URL}/chat/history?limit=10", timeout=5)
        if resp.status_code == 200:
            history = resp.json().get("history", [])
            for item in history:
                priority_colors = {"P0": "red", "P1": "orange", "P2": "green"}
                p = item.get("priority", "P2")
                color = priority_colors.get(p, "gray")
                st.markdown(
                    f":{color}[**{p}**] {item.get('subject', 'No subject')[:40]}"
                )
        else:
            st.caption("No history yet")
    except Exception:
        st.caption("Backend unavailable")

    st.divider()
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.current_analysis = None
        st.session_state.current_email_id = None
        st.session_state.show_correction = False
        st.rerun()


# --- Main Area ---
st.title("Pixel - Display Specialist Agent")
st.caption("Paste an email below for RAG-augmented analysis")


# --- Helper Function (defined before use) ---
def _display_analysis(analysis: dict, email_id: str = None):
    """Render the 5-block analysis output."""

    # Priority badge
    priority = analysis.get("priority", "P2")
    intent = analysis.get("intent", "unknown")
    customer = analysis.get("customer_name", "Unknown")
    stage = analysis.get("opportunity_stage", "New")
    confidence = analysis.get("confidence_score")

    # Header row
    col_p, col_i, col_c, col_s = st.columns(4)
    with col_p:
        colors = {"P0": "red", "P1": "orange", "P2": "green"}
        st.markdown(f"**Priority:** :{colors.get(priority, 'gray')}[{priority}]")
    with col_i:
        st.markdown(f"**Intent:** {intent}")
    with col_c:
        st.markdown(f"**Customer:** {customer}")
    with col_s:
        st.markdown(f"**Stage:** {stage}")

    if confidence is not None:
        st.progress(confidence, text=f"Confidence: {confidence:.0%}")

    st.divider()

    # Block 1: Thread Summary
    st.markdown("#### Thread Summary")
    bullets = analysis.get("thread_summary_bullets", [])
    if bullets:
        for b in bullets:
            st.markdown(f"- {b}")
    else:
        st.markdown(f"- {analysis.get('summary', 'No summary')}")

    # Block 2: Key Specs Extracted
    st.markdown("#### Key Specs Extracted")
    specs = analysis.get("key_specs_extracted", [])
    if specs:
        for spec in specs:
            source_tag = ""
            if spec.get("source") == "inferred":
                source_tag = " *(inferred)*"
            st.markdown(f"- **{spec.get('parameter', '')}**: {spec.get('value', '')}{source_tag}")
    else:
        # Fallback to technical_analysis
        tech = analysis.get("technical_analysis", {})
        if tech:
            st.markdown(f"- **Application**: {tech.get('application', 'N/A')}")
            st.markdown(f"- **Brightness**: {tech.get('brightness_nits', 'N/A')}")
            st.markdown(f"- **Interface**: {tech.get('interface', 'N/A')}")
            st.markdown(f"- **Resolution**: {tech.get('resolution', 'N/A')}")
            if tech.get("customization_notes"):
                st.markdown(f"- **Customization**: {tech['customization_notes']}")

    # Part numbers
    parts = analysis.get("part_numbers", {})
    cust_parts = parts.get("customer_provided", [])
    rec_parts = parts.get("recommended_by_you", [])
    if cust_parts or rec_parts:
        st.markdown("**Part Numbers:**")
        for p in cust_parts:
            st.markdown(f"- Customer PN: `{p.get('pn', '')}` - {p.get('context', '')}")
        for p in rec_parts:
            st.markdown(f"- Recommended: `{p.get('pn', '')}` - {p.get('context', '')}")

    # Block 3: Risks / Missing Info
    st.markdown("#### Risks / Missing Info")
    risks = analysis.get("risks_missing_info", [])
    if risks:
        for r in risks:
            st.warning(r)
    else:
        tech_risks = analysis.get("technical_analysis", {}).get("risks", [])
        missing = analysis.get("action_plan", {}).get("missing_info_questions", [])
        for r in tech_risks:
            st.warning(r)
        for q in missing:
            st.info(f"Missing: {q}")

    # Block 4: Draft Reply
    st.markdown("#### Immediate Action Draft")
    draft = analysis.get("draft_reply", "")
    if draft:
        st.text_area("Draft Reply", draft, height=180, key=f"draft_{email_id}")
    else:
        st.info("No draft generated (outgoing email or insufficient context)")

    # Block 5: Follow-up Actions
    st.markdown("#### Follow-up Actions")
    followups = analysis.get("follow_up_actions", [])
    if followups:
        for fa in followups:
            st.markdown(
                f"- **{fa.get('owner', 'TBD')}**: {fa.get('action', '')} "
                f"(Due: {fa.get('due_date', 'TBD')}) [{fa.get('action_type', '')}]"
            )
    else:
        actions = analysis.get("action_plan", {}).get("suggested_actions", [])
        for a in actions:
            st.markdown(f"- {a}")


# Display chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and "analysis" in msg:
            _display_analysis(msg["analysis"], msg.get("email_id"))
        else:
            st.markdown(msg["content"])


# --- Chat Input ---
email_input = st.chat_input("Paste email text here...")

if email_input:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": email_input})

    with st.chat_message("user"):
        st.markdown(email_input[:200] + "..." if len(email_input) > 200 else email_input)

    # Call backend
    with st.chat_message("assistant"):
        with st.spinner("Analyzing email with Pixel..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/chat/analyze",
                    json={"email_text": email_input},
                    timeout=60,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    analysis = data.get("analysis", {})
                    email_id = data.get("email_id", "")
                    rag_count = data.get("rag_examples_used", 0)

                    st.session_state.current_analysis = analysis
                    st.session_state.current_email_id = email_id

                    # Show RAG info
                    if rag_count > 0:
                        st.success(f"RAG: Used {rag_count} training examples for context")
                    else:
                        st.info("No training examples found yet. Corrections will improve future analyses.")

                    # Display the analysis
                    _display_analysis(analysis, email_id)

                    # Store in messages for history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": analysis.get("summary", ""),
                        "analysis": analysis,
                        "email_id": email_id,
                    })

                elif resp.status_code == 503:
                    st.error("OpenAI API key not configured. Set OPENAI_API_KEY in your .env file.")
                else:
                    error_detail = resp.json().get("detail", resp.text)
                    st.error(f"Analysis failed: {error_detail}")

            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to backend. Is the backend container running?")
            except requests.exceptions.Timeout:
                st.error("Request timed out. The email may be too long or the API is slow.")
            except Exception as e:
                st.error(f"Error: {str(e)}")


# --- Feedback Section ---
if st.session_state.current_analysis and st.session_state.current_email_id:
    st.divider()
    st.markdown("### Feedback")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Good Analysis", key="btn_positive"):
            try:
                requests.post(
                    f"{BACKEND_URL}/chat/feedback",
                    json={
                        "email_id": st.session_state.current_email_id,
                        "rating": "positive",
                    },
                    timeout=5,
                )
                st.success("Thanks! Positive feedback saved.")
            except Exception:
                st.error("Failed to save feedback")

    with col2:
        if st.button("Needs Correction", key="btn_correction"):
            st.session_state.show_correction = True
            st.rerun()

    with col3:
        if st.button("Refine Draft", key="btn_refine"):
            st.session_state.show_refine = True
            st.rerun()

    with col4:
        if st.button("📝 Teach Better Draft", key="btn_better_draft"):
            st.session_state.show_better_draft = True
            st.rerun()

    # Correction form
    if st.session_state.get("show_correction"):
        st.markdown("---")
        st.markdown("### Correct This Analysis")

        analysis = st.session_state.current_analysis

        with st.form("correction_form"):
            corrected_priority = st.selectbox(
                "Priority",
                ["P0", "P1", "P2"],
                index=["P0", "P1", "P2"].index(analysis.get("priority", "P2")),
            )
            corrected_intent = st.selectbox(
                "Intent",
                ["quote_request", "technical_support", "order_status", "intro", "spam", "update"],
                index=0,
            )
            corrected_customer = st.text_input(
                "Customer Name",
                value=analysis.get("customer_name", ""),
            )
            corrected_stage = st.selectbox(
                "Opportunity Stage",
                ["New", "RFQ_Sent", "Quotes_Received", "Proposed", "Samples", "Evaluating", "Design_In", "Production"],
                index=0,
            )
            corrected_summary = st.text_area(
                "Summary",
                value=analysis.get("summary", ""),
                height=100,
            )
            corrected_draft = st.text_area(
                "Draft Reply",
                value=analysis.get("draft_reply", ""),
                height=150,
            )
            correction_notes = st.text_area("What was wrong?", height=80)

            submitted = st.form_submit_button("Submit Correction")

            if submitted:
                corrected_output = {
                    "priority": corrected_priority,
                    "intent": corrected_intent,
                    "customer_name": corrected_customer,
                    "opportunity_stage": corrected_stage,
                    "summary": corrected_summary,
                    "draft_reply": corrected_draft,
                }

                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/chat/correction",
                        json={
                            "email_id": st.session_state.current_email_id,
                            "original_output": analysis,
                            "corrected_output": corrected_output,
                            "correction_type": "full",
                            "notes": correction_notes,
                        },
                        timeout=10,
                    )

                    if resp.status_code == 200:
                        st.success("Correction saved! This will improve future analyses via RAG.")
                        st.session_state.show_correction = False
                    else:
                        st.error(f"Failed to save: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Refine form
    if st.session_state.get("show_refine"):
        st.markdown("---")
        st.markdown("### Refine Draft Reply")

        analysis = st.session_state.current_analysis

        with st.form("refine_form"):
            current_draft = st.text_area(
                "Current Draft",
                value=analysis.get("draft_reply", ""),
                height=150,
            )
            instruction = st.text_input(
                "Refinement Instruction",
                placeholder="e.g. Make it more formal, Add pricing info, Shorten it",
            )

            refine_submitted = st.form_submit_button("Refine")

            if refine_submitted and instruction:
                with st.spinner("Refining draft..."):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/chat/refine",
                            json={
                                "email_id": st.session_state.current_email_id,
                                "original_body": "",
                                "current_draft": current_draft,
                                "instruction": instruction,
                            },
                            timeout=30,
                        )

                        if resp.status_code == 200:
                            refined = resp.json().get("refined_draft", "")
                            st.markdown("#### Refined Draft:")
                            st.text_area("Result", refined, height=200, key="refined_result")
                            st.success("Draft refined! Copy the text above.")
                        else:
                            st.error(f"Refinement failed: {resp.text}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    # Better Draft Teaching Form
    if st.session_state.get("show_better_draft"):
        st.markdown("---")
        st.markdown("### 📝 Teach Pixel a Better Draft")
        st.info("Paste an improved draft response below. Pixel will learn from this example for similar future emails.")

        analysis = st.session_state.current_analysis
        current_draft = analysis.get("draft_reply", "")

        with st.form("better_draft_form"):
            # Show current draft (read-only for comparison)
            st.markdown("**Current Draft (AI-generated):**")
            st.text_area(
                "Current",
                value=current_draft,
                height=150,
                disabled=True,
                key="current_draft_readonly",
                label_visibility="collapsed"
            )

            st.markdown("**Paste Better Draft:**")
            better_draft = st.text_area(
                "Improved Draft",
                placeholder="Paste the improved draft response here...",
                height=200,
                help="Paste a better draft response that Pixel should learn from",
                label_visibility="collapsed"
            )

            notes = st.text_input(
                "Why is this better? (optional)",
                placeholder="e.g., More professional tone, includes pricing context, better structure",
                help="Optional notes to help you remember why this correction was made"
            )

            col_submit, col_cancel = st.columns([1, 1])

            with col_submit:
                submitted = st.form_submit_button("💾 Save as Training Example", type="primary")

            with col_cancel:
                cancel = st.form_submit_button("Cancel")

            if cancel:
                st.session_state.show_better_draft = False
                st.rerun()

            if submitted:
                if not better_draft or not better_draft.strip():
                    st.error("⚠️ Please provide an improved draft before submitting.")
                else:
                    with st.spinner("Saving training example..."):
                        try:
                            resp = requests.post(
                                f"{BACKEND_URL}/chat/save-better-draft",
                                json={
                                    "email_id": st.session_state.current_email_id,
                                    "better_draft": better_draft.strip(),
                                    "notes": notes,
                                },
                                timeout=10,
                            )

                            if resp.status_code == 200:
                                st.success("✅ Saved! Pixel will learn from this draft for similar emails.")
                                st.session_state.show_better_draft = False
                                # Don't rerun immediately to let user see success message
                            else:
                                st.error(f"❌ Failed to save: {resp.text}")
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Cannot connect to backend. Is Docker running?")
                        except Exception as e:
                            st.error(f"❌ Error saving draft: {str(e)}")
