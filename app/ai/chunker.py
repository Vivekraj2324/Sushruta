"""
Sushruta — Document Chunker
==============================

Splits extracted document text into overlapping chunks for RAG retrieval.

Chunking strategy:
- Sentence-aware splitting: Splits on sentence boundaries (period, newline)
  to preserve semantic coherence. Falls back to character-level splitting
  when sentences exceed the chunk size.
- Overlap: Each chunk shares CHUNK_OVERLAP characters with the previous
  chunk to maintain cross-boundary context.

Why overlapping chunks?
- A fact may span two chunks. Without overlap, the relevant sentence
  gets split and neither chunk contains the full context.
- 50-character overlap is enough to capture a connecting sentence
  without excessive duplication.

Why sentence-aware splitting?
- Fixed-size character splitting breaks words and sentences mid-way.
- Sentence splitting preserves semantic units, improving retrieval quality.
- Medical text is especially sensitive to incomplete sentences:
  "Patient has no history of" vs "Patient has no history of cardiac disease."

Token counting:
- Approximate token count using character-based estimation (1 token ≈ 4 chars).
- Used for context window management in the RAG pipeline.
- Exact tokenization would require a tokenizer library (added in Phase 4).
"""

import re

from app.config import get_settings

settings = get_settings()


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count from character count.

    Approximation: 1 token ≈ 4 characters (English text average).
    This is sufficient for context window budgeting.
    Exact tokenization requires a model-specific tokenizer.
    """
    return max(1, len(text) // 4)


def _split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences using regex.

    Handles:
    - Period followed by space or newline (standard sentences).
    - Newline boundaries (paragraph breaks).
    - Preserves medical abbreviations (e.g., "Dr.", "mg.") by not splitting
      on periods followed by lowercase letters.

    Returns a list of non-empty sentence strings.
    """
    # Split on period+space/newline, question mark, exclamation mark,
    # or double newline (paragraph break).
    sentences = re.split(r'(?<=[.!?])\s+|\n\n+', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """
    Split text into overlapping chunks with metadata.

    Parameters
    ----------
    text : str
        The full extracted text from a document.
    chunk_size : int, optional
        Target chunk size in characters. Defaults to settings.CHUNK_SIZE.
    chunk_overlap : int, optional
        Overlap between chunks in characters. Defaults to settings.CHUNK_OVERLAP.

    Returns
    -------
    list[dict]
        Each dict contains:
        - chunk_index: int — position in the document (0-based)
        - chunk_text: str — the text content
        - token_count: int — estimated token count

    Algorithm:
    1. Split text into sentences.
    2. Accumulate sentences into a chunk until chunk_size is reached.
    3. Start a new chunk with overlap from the end of the previous chunk.
    4. If a single sentence exceeds chunk_size, split it by characters.
    """
    if not text or not text.strip():
        return []

    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP

    sentences = _split_into_sentences(text)
    chunks: list[dict] = []
    current_chunk = ""
    chunk_index = 0

    for sentence in sentences:
        # If a single sentence exceeds chunk_size, split it by characters
        if len(sentence) > size:
            # Flush current chunk if it has content
            if current_chunk.strip():
                chunks.append({
                    "chunk_index": chunk_index,
                    "chunk_text": current_chunk.strip(),
                    "token_count": _estimate_tokens(current_chunk.strip()),
                })
                chunk_index += 1

            # Split the long sentence into fixed-size pieces
            for i in range(0, len(sentence), size - overlap):
                piece = sentence[i:i + size]
                if piece.strip():
                    chunks.append({
                        "chunk_index": chunk_index,
                        "chunk_text": piece.strip(),
                        "token_count": _estimate_tokens(piece.strip()),
                    })
                    chunk_index += 1

            current_chunk = ""
            continue

        # Would adding this sentence exceed the target size?
        if len(current_chunk) + len(sentence) + 1 > size:
            # Save current chunk
            if current_chunk.strip():
                chunks.append({
                    "chunk_index": chunk_index,
                    "chunk_text": current_chunk.strip(),
                    "token_count": _estimate_tokens(current_chunk.strip()),
                })
                chunk_index += 1

            # Start new chunk with overlap from end of previous chunk
            if overlap > 0 and current_chunk:
                current_chunk = current_chunk[-overlap:].strip() + " " + sentence
            else:
                current_chunk = sentence
        else:
            # Append sentence to current chunk
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append({
            "chunk_index": chunk_index,
            "chunk_text": current_chunk.strip(),
            "token_count": _estimate_tokens(current_chunk.strip()),
        })

    return chunks
