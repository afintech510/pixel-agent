"""
Pixel Agent - Chat API
Endpoints for single-email analysis with RAG augmentation.
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.connection import get_db
from config import settings
from services.ai_engine import AIEngine, EmailAnalysisSchema
from services.rag_engine import RAGEngine
from utils.parsing import parse_email_text

router = APIRouter(prefix="/chat", tags=["chat"])


# --- Request/Response Models ---

class AnalyzeRequest(BaseModel):
    email_text: str
    session_id: Optional[str] = None


class RefineRequest(BaseModel):
    email_id: str
    original_body: str
    current_draft: str
    instruction: str


class FeedbackRequest(BaseModel):
    email_id: str
    rating: str  # "positive" or "negative"
    comment: Optional[str] = None


class CorrectionRequest(BaseModel):
    email_id: str
    original_output: dict
    corrected_output: dict
    correction_type: Optional[str] = "full"
    notes: Optional[str] = ""


class BetterDraftRequest(BaseModel):
    email_id: str
    better_draft: str
    notes: Optional[str] = ""


# --- Endpoints ---

@router.post("/analyze")
async def analyze_email(request: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Analyze a single email with RAG-augmented context.

    Flow:
    1. Parse the raw email text into structured fields
    2. Generate embedding for RAG retrieval
    3. Retrieve similar training examples from pgvector
    4. Augment the system prompt with few-shot examples
    5. Call OpenAI for structured analysis
    6. Store email + results in database
    7. Return the 5-block analysis
    """
    if not request.email_text.strip():
        raise HTTPException(status_code=400, detail="Email text cannot be empty")

    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "sk-your-key-here":
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY in .env file.",
        )

    # 1. Parse email text
    parsed = parse_email_text(request.email_text)

    # 2. RAG augmentation
    rag_engine = RAGEngine(db)
    rag_context = ""
    rag_examples_count = 0

    try:
        rag_context = rag_engine.augment_prompt(request.email_text)
        if rag_context:
            # Count how many examples were used
            rag_examples_count = rag_context.count("EXAMPLE ")
    except Exception as e:
        print(f"RAG augmentation skipped: {e}")

    # 3. Run AI analysis
    try:
        ai_engine = AIEngine()
        analysis = ai_engine.analyze_single_email(
            email_text=parsed["body"],
            sender_name=parsed["sender_name"],
            sender_email=parsed["sender_email"],
            to_list=parsed["to_list"],
            cc_list=parsed["cc_list"],
            sent_at=parsed["sent_at"],
            subject=parsed["subject"],
            rag_context=rag_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")

    # 4. Store email in database
    new_email_id = str(uuid.uuid4())

    # Generate dedupe_hash from email content for duplicate detection
    import hashlib
    dedupe_content = f"{parsed['sender_email']}|{parsed['subject']}|{parsed['body'][:500]}"
    dedupe_hash = hashlib.sha256(dedupe_content.encode()).hexdigest()

    try:
        result = db.execute(
            text("""
                INSERT INTO emails (
                    id, dedupe_hash, subject, body, from_name, sender_email,
                    recipient_emails, cc_emails, sent_at,
                    processed_by_ai, folder_path
                ) VALUES (
                    :id, :dedupe_hash, :subject, :body, :from_name, :sender_email,
                    :recipient_emails, :cc_emails, :sent_at,
                    TRUE, 'chat_input'
                )
                ON CONFLICT (dedupe_hash) DO UPDATE SET
                    processed_by_ai = TRUE,
                    folder_path = 'chat_input'
                RETURNING id
            """),
            {
                "id": new_email_id,
                "dedupe_hash": dedupe_hash,
                "subject": parsed["subject"] or analysis.summary[:100],
                "body": parsed["body"][:50000],
                "from_name": parsed["sender_name"] or "",
                "sender_email": parsed["sender_email"] or "",
                "recipient_emails": parsed["to_list"] if isinstance(parsed["to_list"], list) else [],
                "cc_emails": parsed["cc_list"] if isinstance(parsed["cc_list"], list) else [],
                "sent_at": parsed["sent_at"] or None,
            },
        )
        db.commit()

        # Get the actual email_id (could be new or existing if there was a conflict)
        email_id_row = result.fetchone()
        email_id = str(email_id_row[0]) if email_id_row else new_email_id
    except Exception as e:
        db.rollback()
        print(f"Failed to store email: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to store email in database: {str(e)}"
        )

    # 5. Store analysis in email_insights
    try:
        specs_list = [f"- {s.label}: {s.value}" for s in analysis.technical_analysis.specs_detected]
        tech_summary = f"Application: {analysis.technical_analysis.application}\n" + "\n".join(specs_list)

        db.execute(
            text("""
                INSERT INTO email_insights (
                    email_id, summary, intent, priority,
                    quote_intent, quote_fields,
                    technical_analysis, technical_risks,
                    suggested_actions, missing_info_questions,
                    draft_reply, eau, target_price,
                    brightness_nits, interface, resolution,
                    customization_notes, raw_ai_output, model_metadata
                ) VALUES (
                    :email_id, :summary, :intent, :priority,
                    :quote_intent, :quote_fields,
                    :tech_analysis, :tech_risks,
                    :suggested_actions, :missing_info_questions,
                    :draft_reply, :eau, :target_price,
                    :brightness_nits, :interface, :resolution,
                    :customization_notes, :raw_ai_output, :model_metadata
                )
                ON CONFLICT (email_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    raw_ai_output = EXCLUDED.raw_ai_output
            """),
            {
                "email_id": email_id,
                "summary": analysis.summary,
                "intent": analysis.intent,
                "priority": analysis.priority,
                "quote_intent": analysis.quote_analysis.is_quote_request,
                "quote_fields": json.dumps(analysis.quote_analysis.extracted_fields.model_dump()),
                "tech_analysis": tech_summary,
                "tech_risks": analysis.technical_analysis.risks,
                "suggested_actions": analysis.action_plan.suggested_actions,
                "missing_info_questions": analysis.action_plan.missing_info_questions,
                "draft_reply": analysis.draft_reply,
                "eau": analysis.quote_analysis.extracted_fields.eau,
                "target_price": analysis.quote_analysis.extracted_fields.target_price,
                "brightness_nits": analysis.technical_analysis.brightness_nits,
                "interface": analysis.technical_analysis.interface,
                "resolution": analysis.technical_analysis.resolution,
                "customization_notes": analysis.technical_analysis.customization_notes,
                "raw_ai_output": json.dumps(analysis.model_dump()),
                "model_metadata": json.dumps({
                    "model": settings.OPENAI_MODEL,
                    "rag_examples": rag_examples_count,
                }),
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Failed to store insights: {e}")

    # 6. Generate embedding for future RAG
    try:
        embedding = rag_engine.generate_embedding(request.email_text)
        rag_engine.store_embedding(
            email_id=email_id,
            embedding=embedding,
            metadata={
                "intent": analysis.intent,
                "priority": analysis.priority,
                "customer": analysis.customer_name,
            },
        )
    except Exception as e:
        print(f"Embedding storage skipped: {e}")

    # 7. Return response
    return {
        "email_id": email_id,
        "analysis": analysis.model_dump(),
        "rag_examples_used": rag_examples_count,
        "parsed_headers": {
            "from": f"{parsed['sender_name']} <{parsed['sender_email']}>",
            "to": parsed["to_list"],
            "cc": parsed["cc_list"],
            "subject": parsed["subject"],
            "date": parsed["sent_at"],
        },
    }


@router.post("/refine")
async def refine_draft(request: RefineRequest):
    """Refine an AI-generated draft reply based on user instructions."""
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "sk-your-key-here":
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured.",
        )

    try:
        ai_engine = AIEngine()
        refined = ai_engine.refine_draft(
            original_body=request.original_body,
            current_draft=request.current_draft,
            instruction=request.instruction,
        )
        return {"refined_draft": refined}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refinement failed: {str(e)}")


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest, db: Session = Depends(get_db)):
    """Submit quick feedback (thumbs up/down) for an analysis."""
    try:
        db.execute(
            text("""
                INSERT INTO feedback_ratings (email_id, rating, comment)
                VALUES (:email_id, :rating, :comment)
            """),
            {
                "email_id": request.email_id,
                "rating": request.rating,
                "comment": request.comment,
            },
        )
        db.commit()
        return {"status": "saved"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/correction")
async def submit_correction(request: CorrectionRequest, db: Session = Depends(get_db)):
    """
    Submit a human correction for an AI analysis.
    Stores in training_examples for future RAG retrieval.
    """
    try:
        # Fetch original email text
        email_row = db.execute(
            text("SELECT body FROM emails WHERE id = :id"),
            {"id": request.email_id},
        ).fetchone()

        email_text = email_row[0] if email_row else ""

        # Store training example
        db.execute(
            text("""
                INSERT INTO training_examples (
                    email_id, original_email_text,
                    original_ai_output, corrected_output,
                    correction_type, corrected_by
                ) VALUES (
                    :email_id, :email_text,
                    :original_output, :corrected_output,
                    :correction_type, :corrected_by
                )
            """),
            {
                "email_id": request.email_id,
                "email_text": email_text,
                "original_output": json.dumps(request.original_output),
                "corrected_output": json.dumps(request.corrected_output),
                "correction_type": request.correction_type,
                "corrected_by": "chat_full_correction",
            },
        )
        db.commit()

        # Update embedding metadata with corrected labels
        try:
            rag_engine = RAGEngine(db)
            rag_engine.store_embedding(
                email_id=request.email_id,
                embedding=rag_engine.generate_embedding(email_text),
                metadata={
                    "intent": request.corrected_output.get("intent"),
                    "priority": request.corrected_output.get("priority"),
                    "customer": request.corrected_output.get("customer_name"),
                    "corrected": True,
                },
            )
        except Exception as e:
            print(f"Embedding update skipped: {e}")

        return {"status": "saved", "message": "Correction stored for RAG learning"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-better-draft")
async def save_better_draft(request: BetterDraftRequest, db: Session = Depends(get_db)):
    """
    Save a user-provided improved draft response as training data.
    Creates a partial correction with only the draft_reply field modified.

    This endpoint is used when users paste a better draft (e.g., from ChatGPT)
    to teach Pixel Agent without needing to validate all other analysis fields.
    """
    try:
        # 1. Fetch email body for embedding update
        email_row = db.execute(
            text("SELECT body FROM emails WHERE id = :id"),
            {"id": request.email_id},
        ).fetchone()

        if not email_row:
            raise HTTPException(status_code=404, detail="Email not found")

        email_text = email_row[0]

        # 2. Fetch original AI analysis from email_insights
        insight_row = db.execute(
            text("SELECT raw_ai_output FROM email_insights WHERE email_id = :id"),
            {"id": request.email_id},
        ).fetchone()

        if not insight_row or not insight_row[0]:
            raise HTTPException(status_code=404, detail="Original analysis not found")

        # Handle JSONB field (might be dict or JSON string)
        original_analysis = insight_row[0]
        if isinstance(original_analysis, str):
            original_analysis = json.loads(original_analysis)

        # 3. Build corrected_output with only draft_reply changed
        corrected_output = original_analysis.copy()
        corrected_output["draft_reply"] = request.better_draft

        # 4. Store training example
        db.execute(
            text("""
                INSERT INTO training_examples (
                    email_id, original_email_text,
                    original_ai_output, corrected_output,
                    correction_type, corrected_by
                ) VALUES (
                    :email_id, :email_text,
                    :original_output, :corrected_output,
                    :correction_type, :corrected_by
                )
            """),
            {
                "email_id": request.email_id,
                "email_text": email_text,
                "original_output": json.dumps(original_analysis),
                "corrected_output": json.dumps(corrected_output),
                "correction_type": "draft",
                "corrected_by": "chat_draft_correction",
            },
        )
        db.commit()

        # 5. Update embedding metadata with corrected flag
        try:
            rag_engine = RAGEngine(db)
            embedding = rag_engine.generate_embedding(email_text)

            db.execute(
                text("""
                    UPDATE email_embeddings
                    SET metadata = :metadata
                    WHERE email_id = :email_id
                """),
                {
                    "email_id": request.email_id,
                    "metadata": json.dumps({
                        "intent": original_analysis.get("intent"),
                        "priority": original_analysis.get("priority"),
                        "customer": original_analysis.get("customer_name"),
                        "corrected": True,
                        "correction_type": "draft",
                    }),
                },
            )
            db.commit()
        except Exception as e:
            print(f"Embedding metadata update skipped: {e}")

        return {
            "status": "saved",
            "message": "Better draft saved for RAG learning",
            "notes": request.notes,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_chat_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Get recent email analyses from chat."""
    try:
        rows = db.execute(
            text("""
                SELECT e.id, e.subject, e.sender_email, e.sent_at,
                       ei.summary, ei.priority, ei.intent,
                       ei.raw_ai_output, ei.created_at
                FROM emails e
                JOIN email_insights ei ON e.id = ei.email_id
                WHERE e.folder_path = 'chat_input'
                ORDER BY ei.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        ).fetchall()

        history = []
        for row in rows:
            history.append({
                "email_id": str(row[0]),
                "subject": row[1],
                "sender_email": row[2],
                "sent_at": str(row[3]) if row[3] else None,
                "summary": row[4],
                "priority": row[5],
                "intent": row[6],
                "created_at": str(row[8]) if row[8] else None,
            })

        return {"history": history, "count": len(history)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
