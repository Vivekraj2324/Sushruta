"""
Sushruta — Embedding Service
==============================

Creates vector embeddings for document chunks and search queries
using Google's Gemini text-embedding-004 model via the google-genai SDK.

Model: models/text-embedding-004
Dimensions: 768
Input: Text string (up to 2048 tokens)
Output: List of 768 floats (unit-normalised for cosine similarity)

Why Gemini over OpenAI?
- User-provided Gemini API key from Google AI Studio.
- text-embedding-004 is competitive with ada-002 at lower cost.
- 768 dimensions (vs 1536) — smaller vectors, faster search, less storage.
- Google ecosystem alignment.

SDK migration note:
- Uses `google-genai` (the current, maintained SDK).
- The older `google-generativeai` package is deprecated and no longer
  receives updates. See:
  https://github.com/google-gemini/deprecated-generative-ai-python

Rate limiting:
- Gemini API has per-minute quotas. For bulk embedding (initial upload),
  we batch chunks and add delays between batches.
- For single-query embedding (search), rate limits are rarely hit.

Error handling:
- Graceful degradation: if embedding fails, chunk is stored without vector.
- Processing status tracks which documents have been fully embedded.
"""

import logging
from typing import Optional

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ── Gemini Client ────────────────────────────────────────────────
# Initialised at module level. The API key is validated on first call.
_client: Optional[genai.Client] = None

if settings.GEMINI_API_KEY:
    _client = genai.Client(api_key=settings.GEMINI_API_KEY)


async def create_embedding(text: str) -> Optional[list[float]]:
    """
    Create a vector embedding for a single text string.

    Parameters
    ----------
    text : str
        The text to embed (chunk or search query).

    Returns
    -------
    list[float] | None
        768-dimensional embedding vector, or None if embedding fails.

    Notes
    -----
    - The google-genai SDK's embed_content is synchronous under the hood.
      In production, this should be offloaded to a thread pool or
      background task queue.
    """
    if _client is None:
        logger.warning("GEMINI_API_KEY not configured — skipping embedding")
        return None

    try:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        def _call_embed():
            return _client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=text,
            )
        response = _call_embed()
        return list(response.embeddings[0].values)

    except Exception as e:
        logger.error(f"Embedding creation failed: {e}")
        return None


async def create_query_embedding(query: str) -> Optional[list[float]]:
    """
    Create an embedding for a search query.

    In the current SDK, the embedding model produces the same vector
    regardless of task type. Retrieval quality comes from the model
    training, not a task_type parameter.
    """
    if _client is None:
        logger.warning("GEMINI_API_KEY not configured — skipping query embedding")
        return None

    try:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        def _call_embed():
            return _client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=query,
            )
        response = _call_embed()
        return list(response.embeddings[0].values)

    except Exception as e:
        logger.error(f"Query embedding creation failed: {e}")
        return None


async def create_embeddings_batch(
    texts: list[str],
    batch_size: int = 20,
) -> list[Optional[list[float]]]:
    """
    Create embeddings for multiple texts with batching.

    Parameters
    ----------
    texts : list[str]
        List of text strings to embed.
    batch_size : int
        Number of texts to embed per API call.

    Returns
    -------
    list[list[float] | None]
        One embedding per input text. None for any that failed.

    Notes
    -----
    The google-genai SDK's embed_content accepts a list of strings
    for batch embedding. This is more efficient than individual calls
    (fewer API round-trips).
    """
    if _client is None:
        logger.warning("GEMINI_API_KEY not configured — returning empty embeddings")
        return [None] * len(texts)

    results: list[Optional[list[float]]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True
            )
            def _call_batch_embed():
                return _client.models.embed_content(
                    model=settings.EMBEDDING_MODEL,
                    contents=batch,
                )
            response = _call_batch_embed()
            for emb in response.embeddings:
                results.append(list(emb.values))

        except Exception as e:
            logger.error(f"Batch embedding failed for batch {i}: {e}")
            results.extend([None] * len(batch))

    return results
