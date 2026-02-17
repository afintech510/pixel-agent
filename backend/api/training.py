"""
Pixel Agent - Training API
Endpoints for managing training examples and RAG dataset.
"""

import uuid
import json
import csv
import io
from datetime import datetime, timezone
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.connection import get_db, fetch_all, fetch_one, execute_query
from services.rag_engine import RAGEngine

router = APIRouter(prefix="/training", tags=["training"])


# --- Request/Response Models ---

class TrainingExampleSummary(BaseModel):
    """Summary view of a training example for list view."""
    id: str
    email_id: str
    subject: str
    sender_email: str
    sent_at: Optional[str]
    correction_type: str
    source: str  # "pst" or "chat"
    intent: Optional[str]
    priority: Optional[str]
    customer_name: Optional[str]
    confidence_before: Optional[float]
    created_at: str


class TrainingExampleDetail(BaseModel):
    """Detailed view of a training example."""
    id: str
    email_id: str
    email: dict
    original_email_text: str
    original_ai_output: dict
    corrected_output: dict
    correction_type: str
    corrected_by: Optional[str]
    confidence_before: Optional[float]
    embedding_exists: bool
    feedback: Optional[dict]
    created_at: str


class TrainingExampleUpdate(BaseModel):
    """Request body for updating a training example."""
    corrected_output: dict
    correction_type: Optional[str] = None
    notes: Optional[str] = None


class BulkDeleteRequest(BaseModel):
    """Request body for bulk delete operation."""
    ids: List[str]


class RegenerateEmbeddingsRequest(BaseModel):
    """Request body for regenerating embeddings."""
    example_ids: Optional[List[str]] = None
    force: bool = False


# --- Helper Functions ---

def _derive_source(corrected_by: Optional[str]) -> str:
    """Derive source type from corrected_by field."""
    if corrected_by == "human_label":
        return "pst"
    return "chat"


def _extract_field_from_jsonb(corrected_output: dict, field: str) -> Optional[str]:
    """Safely extract a field from corrected_output JSONB."""
    if not corrected_output:
        return None
    return corrected_output.get(field)


# --- Endpoints ---

@router.get("/examples")
async def list_training_examples(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    correction_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),  # "pst" or "chat"
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    intent: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    List training examples with filters and pagination.

    Query Parameters:
    - limit: Number of results per page (default 50, max 200)
    - offset: Pagination offset (default 0)
    - correction_type: Filter by correction type
    - source: Filter by source ("pst" or "chat")
    - date_from: Filter examples created after this date (ISO format)
    - date_to: Filter examples created before this date (ISO format)
    - search: Keyword search in email subject/body
    - intent: Filter by intent from corrected_output
    - priority: Filter by priority from corrected_output
    - customer: Filter by customer_name from corrected_output
    """

    # Build WHERE clauses
    where_clauses = []
    params = {}

    # Correction type filter
    if correction_type:
        where_clauses.append("te.correction_type = :correction_type")
        params["correction_type"] = correction_type

    # Source filter (derived from corrected_by)
    if source == "pst":
        where_clauses.append("te.corrected_by = 'human_label'")
    elif source == "chat":
        where_clauses.append("(te.corrected_by IS NULL OR te.corrected_by != 'human_label')")

    # Date range filters
    if date_from:
        where_clauses.append("te.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("te.created_at <= :date_to")
        params["date_to"] = date_to

    # Search filter (case-insensitive, searches subject and body)
    if search:
        where_clauses.append("(e.subject ILIKE :search OR e.body ILIKE :search)")
        params["search"] = f"%{search}%"

    # JSONB field filters (intent, priority, customer)
    if intent:
        where_clauses.append("te.corrected_output->>'intent' = :intent")
        params["intent"] = intent
    if priority:
        where_clauses.append("te.corrected_output->>'priority' = :priority")
        params["priority"] = priority
    if customer:
        where_clauses.append("te.corrected_output->>'customer_name' ILIKE :customer")
        params["customer"] = f"%{customer}%"

    # Build WHERE clause
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Count total matching records
    count_query = f"""
        SELECT COUNT(*) as total
        FROM training_examples te
        LEFT JOIN emails e ON te.email_id = e.id
        {where_sql}
    """
    count_result = fetch_one(count_query, params)
    total = count_result["total"] if count_result else 0

    # Fetch paginated results
    params["limit"] = limit
    params["offset"] = offset

    list_query = f"""
        SELECT
            te.id,
            te.email_id,
            e.subject,
            e.sender_email,
            e.sent_at,
            te.correction_type,
            te.corrected_by,
            te.corrected_output,
            te.confidence_before,
            te.created_at
        FROM training_examples te
        LEFT JOIN emails e ON te.email_id = e.id
        {where_sql}
        ORDER BY te.created_at DESC
        LIMIT :limit OFFSET :offset
    """

    rows = fetch_all(list_query, params)

    # Transform rows into response models
    examples = []
    for row in rows:
        corrected_output = row.get("corrected_output", {})

        examples.append({
            "id": str(row["id"]),
            "email_id": str(row["email_id"]) if row["email_id"] else None,
            "subject": row.get("subject", "No subject"),
            "sender_email": row.get("sender_email", "Unknown"),
            "sent_at": row["sent_at"].isoformat() if row.get("sent_at") else None,
            "correction_type": row.get("correction_type", "full"),
            "source": _derive_source(row.get("corrected_by")),
            "intent": _extract_field_from_jsonb(corrected_output, "intent"),
            "priority": _extract_field_from_jsonb(corrected_output, "priority"),
            "customer_name": _extract_field_from_jsonb(corrected_output, "customer_name"),
            "confidence_before": float(row["confidence_before"]) if row.get("confidence_before") else None,
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        })

    return {
        "examples": examples,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/examples/{example_id}")
async def get_training_example(
    example_id: str,
    db: Session = Depends(get_db),
):
    """
    Get detailed view of a single training example.

    Path Parameters:
    - example_id: UUID of the training example
    """

    # Fetch training example with email details
    query = """
        SELECT
            te.id,
            te.email_id,
            te.original_email_text,
            te.original_ai_output,
            te.corrected_output,
            te.correction_type,
            te.corrected_by,
            te.confidence_before,
            te.created_at,
            e.subject,
            e.sender_email,
            e.from_name,
            e.body,
            e.sent_at
        FROM training_examples te
        LEFT JOIN emails e ON te.email_id = e.id
        WHERE te.id = :example_id
    """

    row = fetch_one(query, {"example_id": example_id})

    if not row:
        raise HTTPException(status_code=404, detail="Training example not found")

    # Check if embedding exists
    embedding_query = """
        SELECT id FROM email_embeddings
        WHERE email_id = :email_id
        LIMIT 1
    """
    embedding_exists = fetch_one(embedding_query, {"email_id": row["email_id"]}) is not None

    # Fetch feedback if exists
    feedback_query = """
        SELECT rating, comment, created_at
        FROM feedback_ratings
        WHERE email_id = :email_id
        ORDER BY created_at DESC
        LIMIT 1
    """
    feedback_row = fetch_one(feedback_query, {"email_id": row["email_id"]})
    feedback = None
    if feedback_row:
        feedback = {
            "rating": feedback_row["rating"],
            "comment": feedback_row.get("comment"),
            "created_at": feedback_row["created_at"].isoformat() if feedback_row.get("created_at") else None,
        }

    # Build response
    return {
        "id": str(row["id"]),
        "email_id": str(row["email_id"]) if row["email_id"] else None,
        "email": {
            "subject": row.get("subject", "No subject"),
            "sender_email": row.get("sender_email", "Unknown"),
            "from_name": row.get("from_name", "Unknown"),
            "body": row.get("body", ""),
            "sent_at": row["sent_at"].isoformat() if row.get("sent_at") else None,
        },
        "original_email_text": row.get("original_email_text", ""),
        "original_ai_output": row.get("original_ai_output", {}),
        "corrected_output": row.get("corrected_output", {}),
        "correction_type": row.get("correction_type", "full"),
        "corrected_by": row.get("corrected_by"),
        "confidence_before": float(row["confidence_before"]) if row.get("confidence_before") else None,
        "embedding_exists": embedding_exists,
        "feedback": feedback,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


@router.get("/stats")
async def get_training_stats(db: Session = Depends(get_db)):
    """
    Get training dataset statistics.
    Extends the existing /pst/training/stats endpoint.
    """

    stats_query = """
        SELECT
            COUNT(*) as total_examples,
            COUNT(DISTINCT email_id) as unique_emails,
            COUNT(CASE WHEN corrected_by = 'human_label' THEN 1 END) as pst_count,
            COUNT(CASE WHEN corrected_by IS NULL OR corrected_by != 'human_label' THEN 1 END) as chat_count,
            COUNT(CASE WHEN correction_type = 'full' THEN 1 END) as full_corrections,
            COUNT(CASE WHEN correction_type != 'full' THEN 1 END) as partial_corrections
        FROM training_examples
    """

    stats = fetch_one(stats_query)

    if not stats:
        return {
            "total_examples": 0,
            "unique_emails": 0,
            "pst_count": 0,
            "chat_count": 0,
            "full_corrections": 0,
            "partial_corrections": 0,
        }

    return {
        "total_examples": stats["total_examples"],
        "unique_emails": stats["unique_emails"],
        "pst_count": stats["pst_count"],
        "chat_count": stats["chat_count"],
        "full_corrections": stats["full_corrections"],
        "partial_corrections": stats["partial_corrections"],
    }


@router.put("/examples/{example_id}")
async def update_training_example(
    example_id: str,
    update_data: TrainingExampleUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a training example's corrected_output.

    Path Parameters:
    - example_id: UUID of the training example

    Request Body:
    - corrected_output: Updated corrected output (JSONB)
    - correction_type: Optional correction type
    - notes: Optional notes (logged but not stored)
    """

    # Verify example exists
    check_query = "SELECT id, email_id FROM training_examples WHERE id = :example_id"
    existing = fetch_one(check_query, {"example_id": example_id})

    if not existing:
        raise HTTPException(status_code=404, detail="Training example not found")

    # Update training example
    update_query = """
        UPDATE training_examples
        SET
            corrected_output = :corrected_output,
            correction_type = COALESCE(:correction_type, correction_type)
        WHERE id = :example_id
    """

    execute_query(update_query, {
        "example_id": example_id,
        "corrected_output": json.dumps(update_data.corrected_output),
        "correction_type": update_data.correction_type,
    })

    # Regenerate embedding if it exists
    email_id = existing["email_id"]
    try:
        rag_engine = RAGEngine(db)
        # Check if embedding exists
        embedding_check = fetch_one(
            "SELECT id FROM email_embeddings WHERE email_id = :email_id",
            {"email_id": email_id}
        )
        if embedding_check:
            # Extract text from corrected_output for embedding
            email_text_query = "SELECT body FROM emails WHERE id = :email_id"
            email_data = fetch_one(email_text_query, {"email_id": email_id})
            if email_data and email_data.get("body"):
                embedding_vector = rag_engine.generate_embedding(email_data["body"])

                # Update embedding and metadata
                update_embedding_query = """
                    UPDATE email_embeddings
                    SET
                        embedding = :embedding,
                        metadata = :metadata
                    WHERE email_id = :email_id
                """
                execute_query(update_embedding_query, {
                    "email_id": email_id,
                    "embedding": str(embedding_vector),  # pgvector format
                    "metadata": json.dumps({
                        "intent": update_data.corrected_output.get("intent"),
                        "priority": update_data.corrected_output.get("priority"),
                        "customer_name": update_data.corrected_output.get("customer_name"),
                    })
                })
    except Exception as e:
        print(f"Warning: Failed to regenerate embedding: {e}")

    return {
        "success": True,
        "id": example_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/examples/{example_id}")
async def delete_training_example(
    example_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete a single training example.

    Path Parameters:
    - example_id: UUID of the training example
    """

    # Get email_id before deleting
    check_query = "SELECT email_id FROM training_examples WHERE id = :example_id"
    existing = fetch_one(check_query, {"example_id": example_id})

    if not existing:
        raise HTTPException(status_code=404, detail="Training example not found")

    email_id = existing["email_id"]

    # Delete training example
    delete_query = "DELETE FROM training_examples WHERE id = :example_id"
    execute_query(delete_query, {"example_id": example_id})

    # Delete associated embedding if exists
    delete_embedding_query = "DELETE FROM email_embeddings WHERE email_id = :email_id"
    execute_query(delete_embedding_query, {"email_id": email_id})

    return {
        "success": True,
        "deleted_id": example_id,
    }


@router.post("/examples/bulk-delete")
async def bulk_delete_training_examples(
    request: BulkDeleteRequest,
    db: Session = Depends(get_db),
):
    """
    Delete multiple training examples.

    Request Body:
    - ids: List of training example UUIDs to delete
    """

    if not request.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

    deleted_count = 0
    failed_ids = []

    for example_id in request.ids:
        try:
            # Get email_id
            check_query = "SELECT email_id FROM training_examples WHERE id = :example_id"
            existing = fetch_one(check_query, {"example_id": example_id})

            if existing:
                email_id = existing["email_id"]

                # Delete training example
                delete_query = "DELETE FROM training_examples WHERE id = :example_id"
                execute_query(delete_query, {"example_id": example_id})

                # Delete embedding
                delete_embedding_query = "DELETE FROM email_embeddings WHERE email_id = :email_id"
                execute_query(delete_embedding_query, {"email_id": email_id})

                deleted_count += 1
            else:
                failed_ids.append(example_id)
        except Exception as e:
            print(f"Failed to delete {example_id}: {e}")
            failed_ids.append(example_id)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "failed_ids": failed_ids,
    }


@router.get("/examples/export")
async def export_training_data(
    format: str = Query("json", regex="^(json|csv)$"),
    include_embeddings: bool = Query(False),
    limit: int = Query(1000, ge=1, le=10000),
    correction_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Export training data as JSON or CSV.

    Query Parameters:
    - format: Export format ("json" or "csv")
    - include_embeddings: Include embedding vectors (JSON only)
    - limit: Maximum number of examples to export (max 10000)
    - Other filter params same as list endpoint
    """

    # Build WHERE clauses (similar to list endpoint)
    where_clauses = []
    params = {}

    if correction_type:
        where_clauses.append("te.correction_type = :correction_type")
        params["correction_type"] = correction_type

    if source == "pst":
        where_clauses.append("te.corrected_by = 'human_label'")
    elif source == "chat":
        where_clauses.append("(te.corrected_by IS NULL OR te.corrected_by != 'human_label')")

    if date_from:
        where_clauses.append("te.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("te.created_at <= :date_to")
        params["date_to"] = date_to

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Fetch data
    params["limit"] = limit

    if include_embeddings and format == "json":
        query = f"""
            SELECT
                te.id,
                te.email_id,
                te.original_email_text,
                te.original_ai_output,
                te.corrected_output,
                te.correction_type,
                te.corrected_by,
                te.confidence_before,
                te.created_at,
                e.subject,
                e.sender_email,
                e.from_name,
                e.sent_at,
                ee.embedding
            FROM training_examples te
            LEFT JOIN emails e ON te.email_id = e.id
            LEFT JOIN email_embeddings ee ON te.email_id = ee.email_id
            {where_sql}
            ORDER BY te.created_at DESC
            LIMIT :limit
        """
    else:
        query = f"""
            SELECT
                te.id,
                te.email_id,
                te.original_email_text,
                te.original_ai_output,
                te.corrected_output,
                te.correction_type,
                te.corrected_by,
                te.confidence_before,
                te.created_at,
                e.subject,
                e.sender_email,
                e.from_name,
                e.sent_at
            FROM training_examples te
            LEFT JOIN emails e ON te.email_id = e.id
            {where_sql}
            ORDER BY te.created_at DESC
            LIMIT :limit
        """

    rows = fetch_all(query, params)

    if format == "json":
        # JSON export
        data = []
        for row in rows:
            item = {
                "id": str(row["id"]),
                "email_id": str(row["email_id"]) if row["email_id"] else None,
                "email": {
                    "subject": row.get("subject"),
                    "sender_email": row.get("sender_email"),
                    "from_name": row.get("from_name"),
                    "sent_at": row["sent_at"].isoformat() if row.get("sent_at") else None,
                },
                "original_email_text": row.get("original_email_text"),
                "original_ai_output": row.get("original_ai_output", {}),
                "corrected_output": row.get("corrected_output", {}),
                "correction_type": row.get("correction_type"),
                "corrected_by": row.get("corrected_by"),
                "confidence_before": float(row["confidence_before"]) if row.get("confidence_before") else None,
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            if include_embeddings and "embedding" in row:
                item["embedding"] = str(row["embedding"]) if row["embedding"] else None
            data.append(item)

        json_data = json.dumps(data, indent=2)
        return StreamingResponse(
            iter([json_data]),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="training_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
            }
        )

    else:
        # CSV export
        output = io.StringIO()
        writer = csv.writer(output)

        # CSV headers
        writer.writerow([
            "id", "subject", "sender", "intent", "priority", "customer",
            "correction_type", "source", "confidence_before", "created_at"
        ])

        # CSV rows
        for row in rows:
            corrected_output = row.get("corrected_output", {})
            writer.writerow([
                str(row["id"]),
                row.get("subject", ""),
                row.get("sender_email", ""),
                corrected_output.get("intent", ""),
                corrected_output.get("priority", ""),
                corrected_output.get("customer_name", ""),
                row.get("correction_type", ""),
                _derive_source(row.get("corrected_by")),
                row.get("confidence_before", ""),
                row["created_at"].isoformat() if row.get("created_at") else "",
            ])

        csv_data = output.getvalue()
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="training_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
            }
        )


@router.post("/examples/import")
async def import_training_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import training data from CSV file.

    Expected CSV columns:
    - original_email_text (required)
    - corrected_output_json (required, JSON string)
    - correction_type (optional, default "full")
    - corrected_by (optional, default "csv_import")
    """

    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Read CSV content
    content = await file.read()
    csv_content = content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(csv_content))

    imported_count = 0
    skipped_count = 0
    errors = []

    for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (after header)
        try:
            # Validate required fields
            if "original_email_text" not in row or not row["original_email_text"]:
                errors.append({"row": row_num, "error": "Missing original_email_text"})
                skipped_count += 1
                continue

            if "corrected_output_json" not in row or not row["corrected_output_json"]:
                errors.append({"row": row_num, "error": "Missing corrected_output_json"})
                skipped_count += 1
                continue

            # Parse corrected_output JSON
            try:
                corrected_output = json.loads(row["corrected_output_json"])
            except json.JSONDecodeError:
                errors.append({"row": row_num, "error": "Invalid JSON in corrected_output_json"})
                skipped_count += 1
                continue

            # Insert training example
            insert_query = """
                INSERT INTO training_examples (
                    id, email_id, original_email_text, original_ai_output,
                    corrected_output, correction_type, corrected_by, created_at
                )
                VALUES (
                    :id, NULL, :original_email_text, '{}',
                    :corrected_output, :correction_type, :corrected_by, NOW()
                )
            """

            new_id = str(uuid.uuid4())
            execute_query(insert_query, {
                "id": new_id,
                "original_email_text": row["original_email_text"],
                "corrected_output": json.dumps(corrected_output),
                "correction_type": row.get("correction_type", "full"),
                "corrected_by": row.get("corrected_by", "csv_import"),
            })

            imported_count += 1

        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})
            skipped_count += 1

    return {
        "success": True,
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "errors": errors[:10],  # Limit to first 10 errors
    }


@router.get("/examples/search")
async def search_training_examples(
    q: str = Query(..., min_length=1),
    fields: Optional[List[str]] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Search training examples by keyword.

    Query Parameters:
    - q: Search query (required)
    - fields: Fields to search in (default: ["subject", "body"])
    - limit: Maximum number of results (default 50)
    """

    if not fields:
        fields = ["subject", "body"]

    # Build search conditions
    search_conditions = []
    if "subject" in fields:
        search_conditions.append("e.subject ILIKE :search")
    if "body" in fields:
        search_conditions.append("e.body ILIKE :search")
    if "specs" in fields:
        search_conditions.append("te.original_email_text ILIKE :search")

    if not search_conditions:
        raise HTTPException(status_code=400, detail="No valid search fields specified")

    where_sql = "WHERE (" + " OR ".join(search_conditions) + ")"

    # Search query
    query = f"""
        SELECT
            te.id,
            te.email_id,
            e.subject,
            e.body,
            te.created_at,
            CASE
                WHEN e.subject ILIKE :search THEN 1.0
                WHEN e.body ILIKE :search THEN 0.8
                ELSE 0.6
            END as relevance_score
        FROM training_examples te
        LEFT JOIN emails e ON te.email_id = e.id
        {where_sql}
        ORDER BY relevance_score DESC, te.created_at DESC
        LIMIT :limit
    """

    params = {
        "search": f"%{q}%",
        "limit": limit,
    }

    rows = fetch_all(query, params)

    # Build results with snippets
    results = []
    for row in rows:
        body = row.get("body", "")
        # Create snippet around search term
        search_lower = q.lower()
        body_lower = body.lower()
        if search_lower in body_lower:
            idx = body_lower.index(search_lower)
            start = max(0, idx - 50)
            end = min(len(body), idx + len(q) + 50)
            snippet = ("..." if start > 0 else "") + body[start:end] + ("..." if end < len(body) else "")
        else:
            snippet = body[:100] + ("..." if len(body) > 100 else "")

        results.append({
            "id": str(row["id"]),
            "email_id": str(row["email_id"]) if row["email_id"] else None,
            "subject": row.get("subject", "No subject"),
            "snippet": snippet,
            "relevance_score": float(row["relevance_score"]),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        })

    return {
        "results": results,
        "total": len(results),
    }


@router.post("/examples/regenerate-embeddings")
async def regenerate_embeddings(
    request: RegenerateEmbeddingsRequest,
    db: Session = Depends(get_db),
):
    """
    Regenerate embeddings for training examples.

    Request Body:
    - example_ids: Optional list of example UUIDs (if empty, regenerate all)
    - force: If true, regenerate even if embedding exists (default false)
    """

    # Fetch training examples to regenerate
    if request.example_ids:
        # Specific examples
        ids_str = ", ".join([f"'{id}'" for id in request.example_ids])
        query = f"""
            SELECT te.id, te.email_id, e.body, te.corrected_output
            FROM training_examples te
            LEFT JOIN emails e ON te.email_id = e.id
            WHERE te.id IN ({ids_str})
        """
        rows = fetch_all(query)
    else:
        # All examples (or those without embeddings if not force)
        if request.force:
            query = """
                SELECT te.id, te.email_id, e.body, te.corrected_output
                FROM training_examples te
                LEFT JOIN emails e ON te.email_id = e.id
            """
        else:
            query = """
                SELECT te.id, te.email_id, e.body, te.corrected_output
                FROM training_examples te
                LEFT JOIN emails e ON te.email_id = e.id
                WHERE te.email_id NOT IN (SELECT email_id FROM email_embeddings)
            """
        rows = fetch_all(query)

    if not rows:
        return {
            "success": True,
            "regenerated_count": 0,
            "failed_count": 0,
            "failed_ids": [],
        }

    # Regenerate embeddings
    rag_engine = RAGEngine(db)
    regenerated_count = 0
    failed_count = 0
    failed_ids = []

    for row in rows:
        try:
            email_id = row["email_id"]
            body = row.get("body", "")

            if not body:
                failed_count += 1
                failed_ids.append(str(row["id"]))
                continue

            # Generate embedding
            embedding_vector = rag_engine.generate_embedding(body)

            # Extract metadata from corrected_output
            corrected_output = row.get("corrected_output", {})
            metadata = {
                "intent": corrected_output.get("intent"),
                "priority": corrected_output.get("priority"),
                "customer_name": corrected_output.get("customer_name"),
            }

            # Check if embedding exists
            check_query = "SELECT id FROM email_embeddings WHERE email_id = :email_id"
            exists = fetch_one(check_query, {"email_id": email_id})

            if exists:
                # Update existing
                update_query = """
                    UPDATE email_embeddings
                    SET embedding = :embedding, metadata = :metadata
                    WHERE email_id = :email_id
                """
                execute_query(update_query, {
                    "email_id": email_id,
                    "embedding": str(embedding_vector),
                    "metadata": json.dumps(metadata),
                })
            else:
                # Insert new
                insert_query = """
                    INSERT INTO email_embeddings (id, email_id, embedding, metadata, created_at)
                    VALUES (:id, :email_id, :embedding, :metadata, NOW())
                """
                execute_query(insert_query, {
                    "id": str(uuid.uuid4()),
                    "email_id": email_id,
                    "embedding": str(embedding_vector),
                    "metadata": json.dumps(metadata),
                })

            regenerated_count += 1

        except Exception as e:
            print(f"Failed to regenerate embedding for {row['id']}: {e}")
            failed_count += 1
            failed_ids.append(str(row["id"]))

    return {
        "success": True,
        "regenerated_count": regenerated_count,
        "failed_count": failed_count,
        "failed_ids": failed_ids[:10],  # Limit to first 10 failed IDs
    }
