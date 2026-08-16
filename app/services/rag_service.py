"""
Sushruta — RAG Service (Phase 2)
==================================

Orchestrates the complete RAG pipeline:
1. Document processing: chunk text + create embeddings after upload.
2. Question answering: embed query → retrieve chunks → generate answer.

This is the core intelligence layer of Sushruta. It connects:
- Chunker (app/ai/chunker.py) — splits documents into searchable pieces.
- Embeddings (app/ai/embeddings.py) — creates vector representations.
- Retriever (app/ai/retriever.py) — finds relevant chunks.
- Gemini LLM — generates grounded answers with citations.

Design:
- Processing is synchronous in Phase 2 (called after upload).
  Phase 4 will move this to a background task queue.
- The LLM prompt is carefully constructed to:
  1. Ground answers in the provided context only.
  2. Cite specific document sources.
  3. Acknowledge when information is insufficient.
  4. Use clinical language appropriate for a doctor audience.
"""

import json
import logging

from google import genai
from google.genai import types
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session_factory
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.chunker import chunk_text
from app.ai.embeddings import create_embedding, create_embeddings_batch
from app.ai.prompts import get_prompt
from app.ai.retriever import search_similar_chunks
from app.config import get_settings
from app.core.audit import AuditAction, create_audit_log
from app.core.cache import AsyncTTLCache
from app.db.models import Doctor, Document, DocumentChunk
from app.schemas.rag import (
    ChunkListResponse,
    ChunkResponse,
    ProcessingStatusResponse,
    RAGAnswerResponse,
    SourceCitation,
)
from app.services.patient_service import get_patient_model

logger = logging.getLogger(__name__)

settings = get_settings()

# ── RAG Cache (In-Memory Async TTL) ──────────────────────────────
rag_cache = AsyncTTLCache(max_size=100, default_ttl_seconds=300)

# ── Gemini Client ────────────────────────────────────────────────
_client: genai.Client | None = None
if settings.GEMINI_API_KEY:
    _client = genai.Client(api_key=settings.GEMINI_API_KEY)


async def start_document_processing(
    db: AsyncSession,
    document_id: int,
    doctor: Doctor,
) -> ProcessingStatusResponse:
    """
    Validate and start document processing. Marks status as 'processing'.
    """
    # Step 1: Get the document
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.doctor_id == doctor.id,
            Document.is_active == True,
        )
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if not document.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no extracted text — cannot process for RAG.",
        )

    # Step 2: Delete existing chunks (re-processing)
    existing_chunks = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    for chunk in existing_chunks.scalars().all():
        await db.delete(chunk)
    
    # Step 3: Mark as processing
    document.processing_status = "processing"
    await db.flush()
    await db.commit()

    return ProcessingStatusResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        processing_status="processing",
        total_chunks=0,
        embedded_chunks=0,
    )


async def process_document_in_background(
    document_id: int,
    doctor_id: int,
) -> None:
    """
    Background task to process a document.
    """
    async with async_session_factory() as db:
        try:
            # Fetch doctor
            dr_result = await db.execute(
                select(Doctor).where(Doctor.id == doctor_id)
            )
            doctor = dr_result.scalar_one_or_none()
            if not doctor:
                logger.error(f"Background processing failed: Doctor {doctor_id} not found.")
                return

            # Fetch document
            doc_result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.doctor_id == doctor_id,
                    Document.is_active == True,
                )
            )
            document = doc_result.scalar_one_or_none()
            if not document:
                logger.error(f"Background processing failed: Document {document_id} not found.")
                return

            # Chunk the text
            chunks_data = chunk_text(document.extracted_text)
            if not chunks_data:
                document.processing_status = "failed"
                await db.commit()
                logger.warning(f"Background processing: Document {document_id} yielded 0 chunks.")
                return

            # Create embeddings (batched)
            chunk_texts = [c["chunk_text"] for c in chunks_data]
            embeddings = await create_embeddings_batch(chunk_texts)

            # Store chunks with embeddings
            embedded_count = 0
            for chunk_data, embedding in zip(chunks_data, embeddings):
                db_chunk = DocumentChunk(
                    document_id=document.id,
                    patient_id=document.patient_id,
                    doctor_id=doctor_id,
                    chunk_index=chunk_data["chunk_index"],
                    chunk_text=chunk_data["chunk_text"],
                    embedding=embedding,
                    token_count=chunk_data["token_count"],
                )
                db.add(db_chunk)
                if embedding is not None:
                    embedded_count += 1

            if embedded_count == len(chunks_data):
                document.processing_status = "embedded"
            elif embedded_count > 0:
                document.processing_status = "embedded"
            else:
                document.processing_status = "chunked"

            # Invalidate cached RAG queries for this patient
            await rag_cache.invalidate_prefix(f"rag:{document.patient_id}:")

            # Audit log
            await create_audit_log(
                db,
                doctor_id=doctor_id,
                patient_id=document.patient_id,
                action=AuditAction.DOCUMENT_PROCESSED,
                resource_type="document",
                resource_id=document.id,
                details=json.dumps({
                    "total_chunks": len(chunks_data),
                    "embedded_chunks": embedded_count,
                    "processing_status": document.processing_status,
                }),
            )
            await db.commit()
            logger.info(f"Background processing completed for Document {document_id}: status={document.processing_status}")

        except Exception as e:
            logger.exception(f"Background processing failed for Document {document_id}: {e}")
            try:
                # Retrieve fresh document to mark failed
                doc_result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                document = doc_result.scalar_one_or_none()
                if document:
                    document.processing_status = "failed"
                    await db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to mark document as failed: {inner_e}")


async def process_document_for_rag(
    db: AsyncSession,
    document_id: int,
    doctor: Doctor,
) -> ProcessingStatusResponse:
    """
    Process a document through the full RAG pipeline: chunk + embed.

    Called after document upload when text extraction is successful.

    Flow:
    1. Retrieve the document and its extracted text.
    2. Chunk the text using sentence-aware splitting.
    3. Create embeddings for all chunks (batched).
    4. Store chunks with embeddings in document_chunks table.
    5. Update document processing_status to 'embedded'.

    Parameters
    ----------
    db : AsyncSession
        Database session.
    document_id : int
        The document to process.
    doctor : Doctor
        The authenticated doctor (for ownership + audit).

    Returns
    -------
    ProcessingStatusResponse
        Status of the processing including chunk counts.
    """
    # Step 1: Get the document
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.doctor_id == doctor.id,
            Document.is_active == True,  # noqa: E712
        )
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if not document.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no extracted text — cannot process for RAG.",
        )

    # Step 2: Delete existing chunks (re-processing)
    existing_chunks = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    for chunk in existing_chunks.scalars().all():
        await db.delete(chunk)
    await db.flush()

    # Step 3: Chunk the text
    document.processing_status = "processing"
    await db.flush()

    chunks_data = chunk_text(document.extracted_text)

    if not chunks_data:
        document.processing_status = "failed"
        await db.commit()
        return ProcessingStatusResponse(
            document_id=document.id,
            original_filename=document.original_filename,
            processing_status="failed",
            total_chunks=0,
            embedded_chunks=0,
        )

    document.processing_status = "chunked"
    await db.flush()

    # Step 4: Create embeddings (batched)
    chunk_texts = [c["chunk_text"] for c in chunks_data]
    embeddings = await create_embeddings_batch(chunk_texts)

    # Step 5: Store chunks with embeddings
    embedded_count = 0
    for chunk_data, embedding in zip(chunks_data, embeddings):
        db_chunk = DocumentChunk(
            document_id=document.id,
            patient_id=document.patient_id,
            doctor_id=doctor.id,
            chunk_index=chunk_data["chunk_index"],
            chunk_text=chunk_data["chunk_text"],
            embedding=embedding,
            token_count=chunk_data["token_count"],
        )
        db.add(db_chunk)
        if embedding is not None:
            embedded_count += 1

    # Step 6: Update processing status
    if embedded_count == len(chunks_data):
        document.processing_status = "embedded"
    elif embedded_count > 0:
        document.processing_status = "embedded"  # Partial is still usable
    else:
        document.processing_status = "chunked"  # Chunks exist but no embeddings

    # Invalidate cached RAG queries for this patient
    await rag_cache.invalidate_prefix(f"rag:{document.patient_id}:")

    # Audit
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=document.patient_id,
        action=AuditAction.DOCUMENT_PROCESSED,
        resource_type="document",
        resource_id=document.id,
        details=json.dumps({
            "total_chunks": len(chunks_data),
            "embedded_chunks": embedded_count,
            "processing_status": document.processing_status,
        }),
    )

    await db.commit()

    return ProcessingStatusResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        processing_status=document.processing_status,
        total_chunks=len(chunks_data),
        embedded_chunks=embedded_count,
    )


async def ask_question(
    db: AsyncSession,
    patient_id: int,
    question: str,
    doctor: Doctor,
    ip_address: str | None = None,
) -> RAGAnswerResponse:
    """
    Answer a doctor's question using RAG over a patient's documents.

    Flow:
    1. Verify patient ownership.
    2. Retrieve relevant chunks via semantic search.
    3. Assemble context from retrieved chunks.
    4. Generate answer using Gemini LLM with grounding prompt.
    5. Return answer with source citations.

    Parameters
    ----------
    db : AsyncSession
        Database session.
    patient_id : int
        The patient whose documents to search.
    question : str
        The doctor's question.
    doctor : Doctor
        The authenticated doctor.
    ip_address : str, optional
        Client IP for audit logging.

    Returns
    -------
    RAGAnswerResponse
        AI-generated answer with source citations.
    """
    # Step 1: Verify patient ownership
    await get_patient_model(db, patient_id, doctor)

    # ── Cache Lookup ─────────────────────────────────────────────
    cache_key = f"rag:{patient_id}:{question.strip().lower()}"
    cached_response = await rag_cache.get(cache_key)
    if cached_response is not None:
        logger.info(f"RAG Cache Hit for patient {patient_id}, query: {question}")
        # Log audit even on cache hits
        await create_audit_log(
            db,
            doctor_id=doctor.id,
            patient_id=patient_id,
            action=AuditAction.RAG_QUERY,
            resource_type="patient",
            resource_id=patient_id,
            details=json.dumps({
                "question": question[:200],
                "chunks_retrieved": cached_response.chunks_retrieved,
                "model": cached_response.model,
                "cached": True,
            }),
            ip_address=ip_address,
        )
        await db.commit()
        return cached_response

    # Step 2: Retrieve relevant chunks
    retrieved_chunks = await search_similar_chunks(
        db=db,
        query=question,
        patient_id=patient_id,
        doctor_id=doctor.id,
    )

    if not retrieved_chunks:
        # No relevant chunks found — still return a helpful response
        fallback_response = RAGAnswerResponse(
            answer=(
                "No relevant information was found in this patient's documents. "
                "This could mean:\n"
                "- No documents have been uploaded for this patient.\n"
                "- Uploaded documents have not been processed yet.\n"
                "- The available documents do not contain information "
                "related to your question."
            ),
            sources=[],
            model=settings.LLM_MODEL,
            chunks_retrieved=0,
        )
        # Store in cache so duplicate empty queries are also cached
        await rag_cache.set(cache_key, fallback_response)
        
        await create_audit_log(
            db,
            doctor_id=doctor.id,
            patient_id=patient_id,
            action=AuditAction.RAG_QUERY,
            resource_type="patient",
            resource_id=patient_id,
            details=json.dumps({
                "question": question[:200],
                "chunks_retrieved": 0,
                "model": settings.LLM_MODEL,
                "cached": False,
            }),
            ip_address=ip_address,
        )
        await db.commit()
        return fallback_response

    # Step 3: Assemble context
    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk.source_filename}]\n{chunk.chunk_text}"
        )
    context = "\n\n---\n\n".join(context_parts)

    # Step 4: Generate answer with Gemini (wrapped in tenacity retry)
    user_prompt = f"""PATIENT DOCUMENT EXCERPTS:
{context}

---

DOCTOR'S QUESTION:
{question}

Please provide a comprehensive answer based on the document excerpts above."""

    try:
        system_prompt = get_prompt("rag_qa", "v1")
    except Exception:
        system_prompt = (
            "You are Sushruta, a clinical AI assistant for doctors. "
            "Answer ONLY based on the provided document excerpts. Do NOT hallucinate."
        )

    try:
        # Resilient wrapper for LLM call
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        def _call_gemini_api():
            if _client is None:
                raise RuntimeError("GEMINI_API_KEY not configured")
            return _client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=settings.LLM_TEMPERATURE,
                ),
            )
        response = _call_gemini_api()
        answer = response.text

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        answer = (
            "I was unable to generate a response at this time. "
            "The relevant document excerpts have been retrieved — "
            "please review them directly in the sources below."
        )

    # Step 5: Build source citations
    sources = [
        SourceCitation(
            document_id=chunk.document_id,
            filename=chunk.source_filename,
            chunk_index=chunk.chunk_index,
            chunk_text=chunk.chunk_text,
            similarity=round(chunk.similarity, 4),
        )
        for chunk in retrieved_chunks
    ]

    response_obj = RAGAnswerResponse(
        answer=answer,
        sources=sources,
        model=settings.LLM_MODEL,
        chunks_retrieved=len(retrieved_chunks),
    )

    # Store successful response in cache
    await rag_cache.set(cache_key, response_obj)

    # Audit
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.RAG_QUERY,
        resource_type="patient",
        resource_id=patient_id,
        details=json.dumps({
            "question": question[:200],  # Truncate for storage
            "chunks_retrieved": len(retrieved_chunks),
            "model": settings.LLM_MODEL,
            "cached": False,
        }),
        ip_address=ip_address,
    )
    await db.commit()

    return RAGAnswerResponse(
        answer=answer,
        sources=sources,
        model=settings.LLM_MODEL,
        chunks_retrieved=len(retrieved_chunks),
    )


async def get_document_chunks(
    db: AsyncSession,
    patient_id: int,
    document_id: int,
    doctor: Doctor,
) -> ChunkListResponse:
    """
    List all chunks for a specific document.

    Used for debugging and transparency — doctors can see
    how their documents were split.
    """
    # Verify patient ownership
    await get_patient_model(db, patient_id, doctor)

    result = await db.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.doctor_id == doctor.id,
        ).order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()

    return ChunkListResponse(
        chunks=[
            ChunkResponse(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                chunk_text=c.chunk_text,
                token_count=c.token_count,
                has_embedding=c.embedding is not None,
            )
            for c in chunks
        ],
        total=len(chunks),
        document_id=document_id,
    )


async def get_processing_status(
    db: AsyncSession,
    patient_id: int,
    document_id: int,
    doctor: Doctor,
) -> ProcessingStatusResponse:
    """Get the processing status for a specific document."""
    # Verify patient ownership
    await get_patient_model(db, patient_id, doctor)

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.doctor_id == doctor.id,
            Document.is_active == True,  # noqa: E712
        )
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Count chunks
    chunk_count = await db.execute(
        select(func.count()).select_from(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            ).subquery()
        )
    )
    total_chunks = chunk_count.scalar() or 0

    embedded_count = await db.execute(
        select(func.count()).select_from(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.embedding.isnot(None),
            ).subquery()
        )
    )
    embedded_chunks = embedded_count.scalar() or 0

    return ProcessingStatusResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        processing_status=document.processing_status,
        total_chunks=total_chunks,
        embedded_chunks=embedded_chunks,
    )
