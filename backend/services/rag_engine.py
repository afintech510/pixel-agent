"""
Pixel Agent - RAG Engine
Retrieval-Augmented Generation using pgvector for few-shot learning.
"""

import json
from typing import List, Dict, Optional
from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from prompts import RAG_AUGMENTATION_TEMPLATE


class RAGEngine:
    def __init__(self, db: Session):
        self.db = db
        self.openai = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = settings.OPENAI_EMBEDDING_MODEL
        self.top_k = settings.RAG_TOP_K

    def generate_embedding(self, text_input: str) -> List[float]:
        """Generate a 1536-dim embedding using OpenAI ada-002."""
        # Truncate to ~8000 tokens worth of text
        truncated = text_input[:16000]
        response = self.openai.embeddings.create(
            model=self.embedding_model,
            input=truncated,
        )
        return response.data[0].embedding

    def store_embedding(
        self,
        email_id: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ):
        """Store an embedding in the email_embeddings table."""
        self.db.execute(
            text("""
                INSERT INTO email_embeddings (email_id, embedding, metadata)
                VALUES (:email_id, :embedding, :metadata)
                ON CONFLICT (email_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
            """),
            {
                "email_id": email_id,
                "embedding": str(embedding),
                "metadata": json.dumps(metadata) if metadata else "{}",
            },
        )
        self.db.commit()

    def retrieve_similar_examples(
        self,
        query_embedding: List[float],
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """
        Query pgvector for the top-K most similar training examples.
        Returns training examples with their corrected outputs.
        """
        k = limit or self.top_k

        results = self.db.execute(
            text("""
                SELECT
                    te.id,
                    te.original_email_text,
                    te.corrected_output,
                    te.correction_type,
                    ee.embedding <=> :query_embedding AS distance
                FROM training_examples te
                JOIN email_embeddings ee ON te.email_id = ee.email_id
                ORDER BY ee.embedding <=> :query_embedding
                LIMIT :limit
            """),
            {
                "query_embedding": str(query_embedding),
                "limit": k,
            },
        ).fetchall()

        examples = []
        for row in results:
            examples.append({
                "id": str(row[0]),
                "email_text": row[1],
                "corrected_output": row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {},
                "correction_type": row[3],
                "distance": float(row[4]),
            })

        return examples

    def augment_prompt(self, email_text: str) -> str:
        """
        Generate embedding for the email, retrieve similar training examples,
        and build RAG augmentation context for the system prompt.

        Returns empty string if no training examples are found.
        """
        try:
            query_embedding = self.generate_embedding(email_text)
        except Exception as e:
            print(f"Embedding generation failed: {e}")
            return ""

        try:
            examples = self.retrieve_similar_examples(query_embedding)
        except Exception as e:
            print(f"RAG retrieval failed: {e}")
            return ""

        if not examples:
            return ""

        # Build examples block
        examples_block = ""
        for i, ex in enumerate(examples, 1):
            # Truncate email text for context
            email_snippet = ex["email_text"][:500] if ex["email_text"] else "N/A"
            corrected = ex["corrected_output"]

            examples_block += f"\nEXAMPLE {i} (similarity distance: {ex['distance']:.4f}):\n"
            examples_block += f"Email: {email_snippet}\n"

            if corrected:
                # Extract key fields from corrected output
                examples_block += f"Correct Priority: {corrected.get('priority', 'N/A')}\n"
                examples_block += f"Correct Intent: {corrected.get('intent', 'N/A')}\n"
                examples_block += f"Correct Customer: {corrected.get('customer_name', 'N/A')}\n"
                examples_block += f"Correct Stage: {corrected.get('opportunity_stage', 'N/A')}\n"
                if corrected.get('summary'):
                    examples_block += f"Correct Summary: {corrected['summary']}\n"

            examples_block += "\n"

        return RAG_AUGMENTATION_TEMPLATE.format(
            count=len(examples),
            examples_block=examples_block,
        )

    def get_training_stats(self) -> Dict:
        """Return stats about available training data."""
        try:
            result = self.db.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM training_examples) as total_examples,
                    (SELECT COUNT(*) FROM email_embeddings) as total_embeddings,
                    (SELECT COUNT(*) FROM feedback_ratings WHERE rating = 'positive') as positive_ratings,
                    (SELECT COUNT(*) FROM feedback_ratings WHERE rating = 'negative') as negative_ratings
            """)).fetchone()

            return {
                "total_examples": result[0],
                "total_embeddings": result[1],
                "positive_ratings": result[2],
                "negative_ratings": result[3],
            }
        except Exception:
            return {
                "total_examples": 0,
                "total_embeddings": 0,
                "positive_ratings": 0,
                "negative_ratings": 0,
            }
