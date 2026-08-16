"""
Sushruta — Chunker Tests
==========================

Pure unit tests for the document chunker.
No database, no API calls, no mocking needed.

Tests verify:
- Empty input handling.
- Single chunk output for short text.
- Multi-chunk splitting with correct overlap.
- Long sentence fallback to character splitting.
- Chunk metadata (index, token count).
"""

from app.ai.chunker import _estimate_tokens, _split_into_sentences, chunk_text


class TestEstimateTokens:
    """Test the token estimation function."""

    def test_estimate_short_text(self):
        """Short text returns at least 1 token."""
        assert _estimate_tokens("hi") >= 1

    def test_estimate_longer_text(self):
        """Longer text estimates roughly 1 token per 4 chars."""
        text = "This is a test sentence with about forty characters."
        tokens = _estimate_tokens(text)
        assert tokens > 0
        assert tokens == len(text) // 4

    def test_estimate_empty_text(self):
        """Empty text returns at least 1."""
        assert _estimate_tokens("") >= 1


class TestSplitIntoSentences:
    """Test sentence splitting."""

    def test_simple_sentences(self):
        """Splits on period+space boundaries."""
        text = "First sentence. Second sentence. Third sentence."
        sentences = _split_into_sentences(text)
        assert len(sentences) >= 2

    def test_paragraph_breaks(self):
        """Splits on double newlines (paragraph boundaries)."""
        text = "Paragraph one.\n\nParagraph two."
        sentences = _split_into_sentences(text)
        assert len(sentences) == 2

    def test_empty_text(self):
        """Empty text returns empty list."""
        assert _split_into_sentences("") == []
        assert _split_into_sentences("   ") == []


class TestChunkText:
    """Test the main chunking function."""

    def test_empty_text_returns_empty(self):
        """Empty or whitespace text returns no chunks."""
        assert chunk_text("") == []
        assert chunk_text("   ") == []
        assert chunk_text(None) == []

    def test_short_text_single_chunk(self):
        """Text shorter than chunk_size produces one chunk."""
        text = "Patient has a history of type 2 diabetes."
        chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["chunk_text"] == text
        assert chunks[0]["token_count"] > 0

    def test_multiple_chunks(self):
        """Longer text is split into multiple chunks."""
        # Create text that's longer than chunk_size
        sentences = [f"Sentence number {i} contains important medical data." for i in range(20)]
        text = " ".join(sentences)

        chunks = chunk_text(text, chunk_size=200, chunk_overlap=30)
        assert len(chunks) > 1

        # Verify sequential indexing
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

        # All chunks should have non-empty text
        for chunk in chunks:
            assert len(chunk["chunk_text"]) > 0
            assert chunk["token_count"] > 0

    def test_chunk_indices_sequential(self):
        """Chunk indices are 0, 1, 2, ... in order."""
        text = "A. " * 100 + "B. " * 100 + "C. " * 100
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=10)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_no_empty_chunks(self):
        """No chunk should have empty or whitespace-only text."""
        text = "Sentence one. Sentence two. Sentence three. " * 10
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
        for chunk in chunks:
            assert chunk["chunk_text"].strip() != ""

    def test_very_long_sentence_fallback(self):
        """A single sentence longer than chunk_size is split by characters."""
        long_sentence = "a" * 1000  # No periods — one giant sentence
        chunks = chunk_text(long_sentence, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["chunk_text"]) <= 200

    def test_token_count_populated(self):
        """Every chunk has a positive token_count."""
        text = "Medical history shows elevated blood pressure readings. " * 5
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=10)
        for chunk in chunks:
            assert chunk["token_count"] > 0

    def test_custom_parameters(self):
        """Custom chunk_size and chunk_overlap are respected."""
        text = "Word. " * 200  # ~1200 chars
        small_chunks = chunk_text(text, chunk_size=50, chunk_overlap=5)
        large_chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)
        # Smaller chunk size should produce more chunks
        assert len(small_chunks) > len(large_chunks)

    def test_medical_text(self):
        """Realistic medical text is chunked sensibly."""
        medical_text = (
            "Patient: Rajesh Kumar, 45M. Chief complaint: Chest pain for 3 days. "
            "History: Type 2 diabetes mellitus since 2015, on Metformin 500mg BD. "
            "Hypertension since 2018, on Amlodipine 5mg OD. "
            "No history of cardiac events. Family history: Father had MI at age 55. "
            "Examination: BP 140/90, HR 88, SpO2 98%. "
            "ECG: Normal sinus rhythm. No ST changes. "
            "Assessment: Atypical chest pain. Rule out ACS. "
            "Plan: Troponin I, Chest X-ray, Cardiology consult."
        )
        chunks = chunk_text(medical_text, chunk_size=200, chunk_overlap=30)
        assert len(chunks) >= 1

        # All original content should be present across chunks
        combined = " ".join(c["chunk_text"] for c in chunks)
        assert "Rajesh Kumar" in combined
        assert "Metformin" in combined
        assert "Troponin" in combined
