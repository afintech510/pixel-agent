"""
Pixel Agent - AI Engine
Ported from Future_Agent_1 with RAG augmentation and single-email mode.
"""

import json
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text

from config import settings
from prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    REFINEMENT_SYSTEM_PROMPT,
    REFINEMENT_USER_PROMPT_TEMPLATE,
)


# --- STRUCTURED OUTPUT MODELS ---

class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteFields(StrictBaseModel):
    quantity: str = Field(..., description="e.g. 10k/year. Use 'Not specified' if missing.")
    timeline: str = Field(..., description="e.g. MP Q3 2025. Use 'Not specified' if missing.")
    delivery_location: str = Field(..., description="e.g. HK. Use 'Not specified' if missing.")
    eau: str = Field(..., description="Estimated Annual Usage. e.g. 50k/yr.")
    target_price: str = Field(..., description="Customer's target price. e.g. $15.50.")


class QuoteAnalysis(StrictBaseModel):
    is_quote_request: bool
    extracted_fields: QuoteFields


class PartInfo(StrictBaseModel):
    pn: str = Field(..., description="The part number found")
    context: str = Field(..., description="Context or reasoning for this part")
    snippet: str = Field(..., description="Exact quote from the email")


class PartNumbers(StrictBaseModel):
    customer_provided: List[PartInfo]
    recommended_by_you: List[PartInfo]


class TechnicalSpec(StrictBaseModel):
    label: str = Field(..., description="e.g. Brightness, Interface, etc.")
    value: str = Field(..., description="The value of the spec")


class TechnicalAnalysis(StrictBaseModel):
    application: str = Field(..., description="The customer's end application. Use 'Unknown' if not mentioned.")
    specs_detected: List[TechnicalSpec] = Field(..., description="List of technical specs found.")
    brightness_nits: str = Field(..., description="Brightness in nits. e.g. 1000 nits.")
    interface: str = Field(..., description="Display interface. e.g. MIPI, LVDS, RGB.")
    resolution: str = Field(..., description="Display resolution. e.g. 1280x800.")
    customization_notes: str = Field(..., description="Any notes about PCAP, Cover Lens, or customization.")
    risks: List[str]


class Commitment(StrictBaseModel):
    task_type: str = Field(..., description="follow_up | waiting_on_client")
    description: str = Field(..., description="Summarized task")
    due_date_offset_days: int = Field(..., description="How many days from now should this be due?")


class CommitmentAnalysis(StrictBaseModel):
    detected: bool
    commitments: List[Commitment]


class ActionPlan(StrictBaseModel):
    suggested_actions: List[str]
    missing_info_questions: List[str]


class FollowUpAction(StrictBaseModel):
    action: str = Field(..., description="What needs to be done")
    owner: str = Field(..., description="Who should do it")
    due_date: str = Field(..., description="When it's due. e.g. '2025-03-15' or 'ASAP' or '3 business days'")
    action_type: str = Field(..., description="reminder | send_quote | send_samples | follow_up | internal")


class KeySpec(StrictBaseModel):
    parameter: str = Field(..., description="e.g. Display Type, Diagonal, Resolution")
    value: str = Field(..., description="The extracted value")
    source: str = Field(..., description="'explicit' if stated in email, 'inferred' if deduced")


class EmailAnalysisSchema(StrictBaseModel):
    # Original fields
    summary: str
    intent: str = Field(..., description="quote_request | technical_support | order_status | intro | spam | update")
    priority: str = Field(..., description="P0 | P1 | P2")
    priority_reason: str = Field(..., description="Why this priority was chosen based on triage rules")
    quote_analysis: QuoteAnalysis
    part_numbers: PartNumbers
    technical_analysis: TechnicalAnalysis
    draft_reply: str
    action_plan: ActionPlan
    commitment_analysis: CommitmentAnalysis
    company_classification: str = Field(..., description="Customer | Supplier | Unclassified")

    # New 5-block fields
    thread_summary_bullets: List[str] = Field(..., description="1-3 bullet point summary of the email thread")
    key_specs_extracted: List[KeySpec] = Field(..., description="Structured specs extracted from email")
    risks_missing_info: List[str] = Field(..., description="Risks and missing information")
    follow_up_actions: List[FollowUpAction] = Field(..., description="Follow-up actions with owners and dates")
    opportunity_stage: str = Field(..., description="New | RFQ_Sent | Quotes_Received | Proposed | Samples | Evaluating | Design_In | Production")
    customer_name: str = Field(..., description="Customer company name. Use 'Unknown' if not identifiable.")
    customer_email: str = Field(..., description="Primary customer email address. Use '' if not identifiable.")

    # Confidence
    confidence_score: Optional[float] = Field(None, description="0.0-1.0 confidence in this analysis")


class BatchEmailAnalysis(StrictBaseModel):
    results: List[EmailAnalysisSchema] = Field(..., description="List of analysis objects")


# --- AI ENGINE ---

class AIEngine:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("Missing OPENAI_API_KEY in configuration")
        self.openai = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def analyze_single_email(
        self,
        email_text: str,
        sender_name: str = "",
        sender_email: str = "",
        to_list: str = "",
        cc_list: str = "",
        sent_at: str = "",
        subject: str = "",
        rag_context: str = "",
    ) -> EmailAnalysisSchema:
        """Analyze a single email with optional RAG context."""

        # Build user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            sender_name=sender_name or "Unknown",
            sender_email=sender_email or "unknown@unknown.com",
            to_list=to_list or "Not specified",
            cc_list=cc_list or "None",
            sent_at=sent_at or "Not specified",
            subject=subject or "No subject",
            body=email_text[:10000],
        )

        # Build system prompt with optional RAG augmentation
        system_prompt = SYSTEM_PROMPT
        if rag_context:
            system_prompt = rag_context + "\n\n" + system_prompt

        completion = self.openai.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EmailAnalysisSchema,
        )

        return completion.choices[0].message.parsed

    def refine_draft(self, original_body: str, current_draft: str, instruction: str) -> str:
        """Refine an existing draft based on user instructions."""
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": REFINEMENT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": REFINEMENT_USER_PROMPT_TEMPLATE.format(
                            original_body=original_body,
                            current_draft=current_draft,
                            instruction=instruction,
                        ),
                    },
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Refinement failed: {e}")
            return current_draft
