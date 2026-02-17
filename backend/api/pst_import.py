"""
PST Import API endpoints.
Handles file upload, parsing, and training data collection.
"""

import os
import uuid
import json
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.connection import get_db
from services.pst_parser import PSTParser
from services.ai_engine import AIEngine
from services.rag_engine import RAGEngine
from config import settings

router = APIRouter(prefix="/pst", tags=["PST Import"])


class EnrichLabelsRequest(BaseModel):
    subject: str = ""
    body: str = ""
    from_name: str = ""
    sender_email: str = ""
    recipient_emails: List[str] = []
    cc_emails: List[str] = []
    sent_at: Optional[str] = None


@router.post("/import")
async def import_pst_file(
    file: UploadFile = File(...),
    mode: str = Query("training", enum=["training", "production"]),
    db: Session = Depends(get_db),
):
    """
    Upload and parse a PST file.

    Modes:
    - training: Returns parsed emails for human labeling (no AI processing)
    - production: Stores emails in DB and marks for AI processing
    """
    if not file.filename.lower().endswith(".pst"):
        raise HTTPException(status_code=400, detail="File must be a .pst file")

    # Create import record
    import_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO imports (id, filename, status, metadata)
            VALUES (:id, :filename, 'processing', :metadata)
        """),
        {
            "id": import_id,
            "filename": file.filename,
            "metadata": json.dumps({"mode": mode}),
        },
    )
    db.commit()

    # Save uploaded file temporarily
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, f"{import_id}.pst")

    try:
        contents = await file.read()
        with open(temp_path, "wb") as f:
            f.write(contents)

        # Parse PST
        parser = PSTParser(
            file_path=temp_path,
            db=db,
            import_id=import_id,
        )
        parser.open()

        if mode == "training":
            # Return emails for human labeling (don't insert into DB yet)
            stats = parser.parse(return_emails=True)
            emails = parser.get_parsed_emails()
            parser.close()

            # Update import record
            db.execute(
                text("""
                    UPDATE imports SET status = 'completed',
                    emails_processed = :count
                    WHERE id = :id
                """),
                {"count": stats["processed"], "id": import_id},
            )
            db.commit()

            # Return summary of each email for labeling
            email_summaries = []
            for i, email in enumerate(emails):
                email_summaries.append({
                    "index": i,
                    "subject": email.get("subject", ""),
                    "from_name": email.get("from_name", ""),
                    "sender_email": email.get("sender_email", ""),
                    "recipient_emails": email.get("recipient_emails", []),
                    "cc_emails": email.get("cc_emails", []),
                    "sent_at": email.get("sent_at", ""),
                    "body": email.get("body", "")[:5000],  # Limit body size for response
                    "folder_path": email.get("folder_path", ""),
                    "dedupe_hash": email.get("dedupe_hash", ""),
                })

            return {
                "status": "ready_for_labeling",
                "import_id": import_id,
                "mode": mode,
                "stats": stats,
                "email_count": len(email_summaries),
                "emails": email_summaries,
            }

        else:
            # Production mode: insert directly into DB
            stats = parser.parse(return_emails=False)
            parser.close()

            # Update import record
            db.execute(
                text("""
                    UPDATE imports SET status = 'completed',
                    emails_processed = :processed,
                    emails_skipped = :errors
                    WHERE id = :id
                """),
                {
                    "processed": stats["processed"],
                    "errors": stats["errors"],
                    "id": import_id,
                },
            )
            db.commit()

            return {
                "status": "completed",
                "import_id": import_id,
                "mode": mode,
                "stats": stats,
            }

    except Exception as e:
        # Update import record with failure
        db.execute(
            text("UPDATE imports SET status = 'failed' WHERE id = :id"),
            {"id": import_id},
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"PST import failed: {str(e)}")

    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/training/label")
async def save_training_label(
    email_data: dict,
    label_data: dict,
    db: Session = Depends(get_db),
):
    """
    Save a human-labeled training example from PST import.

    email_data: The raw parsed email record
    label_data: Human-provided labels (priority, intent, parts, draft, etc.)
    """
    # First, insert the email into the emails table
    email_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO emails (
                id, import_id, message_id, dedupe_hash, thread_id,
                subject, body, from_name, sender_email,
                recipient_emails, cc_emails, sent_at,
                timestamp_missing, folder_path, processed_by_ai
            ) VALUES (
                :id, :import_id, :message_id, :dedupe_hash, :thread_id,
                :subject, :body, :from_name, :sender_email,
                :recipient_emails, :cc_emails, :sent_at,
                :timestamp_missing, :folder_path, TRUE
            ) ON CONFLICT (dedupe_hash) DO UPDATE SET
                processed_by_ai = TRUE
            RETURNING id
        """),
        {
            "id": email_id,
            "import_id": email_data.get("import_id"),
            "message_id": email_data.get("message_id"),
            "dedupe_hash": email_data.get("dedupe_hash"),
            "thread_id": email_data.get("thread_id"),
            "subject": email_data.get("subject"),
            "body": email_data.get("body"),
            "from_name": email_data.get("from_name"),
            "sender_email": email_data.get("sender_email"),
            "recipient_emails": email_data.get("recipient_emails", []),
            "cc_emails": email_data.get("cc_emails", []),
            "sent_at": email_data.get("sent_at"),
            "timestamp_missing": email_data.get("timestamp_missing", False),
            "folder_path": email_data.get("folder_path"),
        },
    )

    # Get the actual email_id (could be existing if dedupe conflict)
    result = db.execute(
        text("SELECT id FROM emails WHERE dedupe_hash = :hash"),
        {"hash": email_data.get("dedupe_hash")},
    ).fetchone()

    if result:
        email_id = str(result[0])

    # Save training example
    training_id = str(uuid.uuid4())
    email_text = f"FROM: {email_data.get('from_name', '')} <{email_data.get('sender_email', '')}>\n"
    email_text += f"SUBJECT: {email_data.get('subject', '')}\n"
    email_text += f"BODY: {email_data.get('body', '')[:3000]}"

    db.execute(
        text("""
            INSERT INTO training_examples (
                id, email_id, original_email_text,
                original_ai_output, corrected_output,
                correction_type, corrected_by
            ) VALUES (
                :id, :email_id, :email_text,
                :original, :corrected,
                'full', 'human_label'
            )
        """),
        {
            "id": training_id,
            "email_id": email_id,
            "email_text": email_text,
            "original": json.dumps({}),  # No AI output for human-labeled data
            "corrected": json.dumps(label_data),
        },
    )

    db.commit()

    return {
        "status": "saved",
        "email_id": email_id,
        "training_example_id": training_id,
    }


@router.post("/enrich-labels")
async def enrich_labels(
    request: EnrichLabelsRequest,
    db: Session = Depends(get_db),
):
    """
    Run AI analysis on an email and return label suggestions
    mapped to the PST Import label form fields.
    """
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "sk-your-key-here":
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY in .env file.",
        )

    if not request.body.strip():
        raise HTTPException(status_code=400, detail="Email body is required for enrichment")

    # RAG augmentation (best-effort)
    rag_context = ""
    try:
        rag_engine = RAGEngine(db)
        email_text = f"FROM: {request.from_name} <{request.sender_email}>\nSUBJECT: {request.subject}\nBODY: {request.body}"
        rag_context = rag_engine.augment_prompt(email_text)
    except Exception as e:
        print(f"RAG augmentation skipped during enrichment: {e}")

    # Run AI analysis
    try:
        ai_engine = AIEngine()
        analysis = ai_engine.analyze_single_email(
            email_text=request.body,
            sender_name=request.from_name,
            sender_email=request.sender_email,
            to_list=", ".join(request.recipient_emails),
            cc_list=", ".join(request.cc_emails),
            sent_at=request.sent_at or "",
            subject=request.subject,
            rag_context=rag_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI enrichment failed: {str(e)}")

    # Extract specs from key_specs_extracted
    specs = {}
    for spec in analysis.key_specs_extracted:
        param = spec.parameter.lower()
        if ("display" in param and ("size" in param or "diagonal" in param)) or "screen size" in param:
            specs["display_size"] = spec.value
        elif "touch" in param or "pcap" in param:
            specs["touch"] = spec.value
        elif "temp" in param:
            specs["temp_range"] = spec.value

    # Fall back to technical_analysis direct fields
    if "display_size" not in specs:
        for spec in analysis.key_specs_extracted:
            if "diagonal" in spec.parameter.lower():
                specs["display_size"] = spec.value
                break

    brightness = analysis.technical_analysis.brightness_nits
    interface = analysis.technical_analysis.interface
    resolution = analysis.technical_analysis.resolution

    # Collect part numbers
    part_numbers = []
    for p in analysis.part_numbers.customer_provided:
        if p.pn and p.pn.strip():
            part_numbers.append(p.pn.strip())
    for p in analysis.part_numbers.recommended_by_you:
        if p.pn and p.pn.strip():
            part_numbers.append(p.pn.strip())

    # Format follow-ups
    follow_up_lines = []
    for fa in analysis.follow_up_actions:
        follow_up_lines.append(f"- {fa.action} ({fa.owner}, {fa.due_date})")

    # Format summary from bullets
    summary_lines = [f"- {b}" for b in analysis.thread_summary_bullets]
    summary_text = "\n".join(summary_lines) if summary_lines else analysis.summary

    # Format risks
    risk_lines = [f"- {r}" for r in analysis.risks_missing_info]

    # Map priority and stage to form values
    priority_map = {"P0": "P0 (Hot)", "P1": "P1 (Warm)", "P2": "P2 (Cold)"}
    stage = analysis.opportunity_stage
    if stage == "Samples":
        stage = "Samples_Requested"

    return {
        "status": "enriched",
        "labels": {
            "summary": summary_text,
            "priority": priority_map.get(analysis.priority, "P2 (Cold)"),
            "intent": analysis.intent,
            "customer_name": analysis.customer_name,
            "company_classification": analysis.company_classification,
            "opportunity_stage": stage,
            "part_numbers": "\n".join(part_numbers),
            "display_size": specs.get("display_size", ""),
            "brightness_nits": brightness if brightness != "Not specified" else "",
            "interface": interface if interface != "Not specified" else "",
            "resolution": resolution if resolution != "Not specified" else "",
            "touch": specs.get("touch", ""),
            "temp_range": specs.get("temp_range", ""),
            "risks": "\n".join(risk_lines),
            "draft_reply": analysis.draft_reply,
            "follow_ups": "\n".join(follow_up_lines),
        },
    }


@router.get("/imports")
async def list_imports(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """List recent PST import sessions."""
    result = db.execute(
        text("""
            SELECT id, filename, status, emails_processed,
                   emails_skipped, created_at, metadata
            FROM imports
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    columns = result.keys()
    imports = [dict(zip(columns, row)) for row in result.fetchall()]

    return {"imports": imports}


@router.get("/training/stats")
async def training_stats(db: Session = Depends(get_db)):
    """Get training data statistics."""
    result = db.execute(
        text("""
            SELECT
                COUNT(*) as total_examples,
                COUNT(DISTINCT email_id) as unique_emails,
                COUNT(CASE WHEN correction_type = 'full' THEN 1 END) as full_labels,
                COUNT(CASE WHEN corrected_by = 'human_label' THEN 1 END) as human_labels,
                MIN(created_at) as first_label,
                MAX(created_at) as last_label
            FROM training_examples
        """)
    ).fetchone()

    return {
        "total_examples": result[0],
        "unique_emails": result[1],
        "full_labels": result[2],
        "human_labels": result[3],
        "first_label": str(result[4]) if result[4] else None,
        "last_label": str(result[5]) if result[5] else None,
    }
