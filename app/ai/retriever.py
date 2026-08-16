"""
Sushruta — Vector Retriever
==============================

Retrieves the most relevant document chunks for a given question
using cosine similarity search via pgvector.

Pipeline:
1. Embed the question using Gemini (RETRIEVAL_QUERY task type).
2. Search document_chunks via pgvector cosine distance (<=>).
3. Filter by patient_id and doctor_id (data isolation).
4. Return top-K chunks with similarity scores.

Cosine similarity vs Euclidean distance:
- Cosine similarity measures angle between vectors (direction).
- Euclidean measures absolute distance (magnitude).
- For text embeddings (normalised), cosine is standard and more stable.
- pgvector's <=> operator computes cosine distance (1 - similarity).

Fallback for SQLite (tests):
- When pgvector is unavailable (SQLite), retrieval returns an empty list.
- Unit tests mock this function to return predetermined chunks.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import create_query_embedding
from app.config import get_settings
from app.db.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class RetrievedChunk:
    """
    A document chunk retrieved by semantic search, with metadata.

    Attributes
    ----------
    chunk_id : int
        Primary key of the chunk.
    document_id : int
        Source document ID.
    chunk_index : int
        Position in the source document.
    chunk_text : str
        The actual text content.
    similarity : float
        Cosine similarity score (0.0 to 1.0).
    source_filename : str
        Original filename of the source document (for citations).
    """
    chunk_id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    similarity: float
    source_filename: str


async def search_similar_chunks(
    db: AsyncSession,
    query: str,
    patient_id: int,
    doctor_id: int,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """
    Find the most relevant chunks for a query within a patient's documents.

    Parameters
    ----------
    db : AsyncSession
        Database session.
    query : str
        The doctor's question in natural language.
    patient_id : int
        Restrict search to this patient's documents.
    doctor_id : int
        Restrict search to this doctor's documents (data isolation).
    top_k : int, optional
        Number of chunks to return. Defaults to settings.RAG_TOP_K.

    Returns
    -------
    list[RetrievedChunk]
        Top-K most similar chunks, sorted by similarity (descending).
        Empty list if embedding fails or no chunks exist.
    """
    k = top_k or settings.RAG_TOP_K

    # Step 1: Embed the query
    query_embedding = await create_query_embedding(query)
    if query_embedding is None:
        logger.warning("Query embedding failed — returning empty results")
        return []

    # Step 2: Search via pgvector cosine distance
    # The <=> operator computes cosine distance: 1 - cosine_similarity
    # We ORDER BY distance ASC to get most similar first.
    try:
        # Use raw SQL for pgvector's cosine distance operator.
        # SQLAlchemy doesn't natively support <=> without the pgvector extension.
        embedding_str = str(query_embedding)

        result = await db.execute(
            text("""
                SELECT
                    dc.id,
                    dc.document_id,
                    dc.chunk_index,
                    dc.chunk_text,
                    1 - (dc.embedding <=> :embedding) AS similarity,
                    d.original_filename
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.patient_id = :patient_id
                  AND dc.doctor_id = :doctor_id
                  AND dc.embedding IS NOT NULL
                  AND d.is_active = true
                ORDER BY dc.embedding <=> :embedding ASC
                LIMIT :limit
            """),
            {
                "embedding": embedding_str,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "limit": k,
            },
        )
        rows = result.fetchall()

        return [
            RetrievedChunk(
                chunk_id=row[0],
                document_id=row[1],
                chunk_index=row[2],
                chunk_text=row[3],
                similarity=float(row[4]),
                source_filename=row[5],
            )
            for row in rows
        ]

    except Exception as e:
        # SQLite or other non-pgvector databases will fail here.
        # This is expected in tests — retriever is mocked.
        logger.error(f"Vector search failed (expected in SQLite tests): {e}")
        return []
