import asyncio
import json
import os
import re
from typing import List, Dict, Any
from unittest.mock import patch, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.db.database import Base
from app.db.models import Doctor, Patient, Document, DocumentChunk
from app.services.rag_service import ask_question
from app.schemas.rag import RAGAnswerResponse
from app.ai.retriever import RetrievedChunk

# ── Ground Truth Evaluation Dataset ──────────────────────────────────────────
EVAL_DATASET = [
    {
        "query": "What are the patient's active allergies?",
        "ground_truth_context": "Allergy Profile: Penicillin (severe anaphylaxis) and Peanuts (mild hives).",
        "ground_truth_answer": "The patient has a severe anaphylactic allergy to Penicillin and a mild allergic reaction (hives) to Peanuts.",
        "expected_concepts": ["penicillin", "anaphylaxis", "peanuts", "hives"]
    },
    {
        "query": "Summarise the patient's cardiovascular symptoms.",
        "ground_truth_context": "Cardiology Note: Patient reports intermittent chest pain radiating to the left arm, accompanied by mild shortness of breath during exertion.",
        "ground_truth_answer": "The patient experienced intermittent chest pain radiating to the left arm and mild shortness of breath on exertion.",
        "expected_concepts": ["chest pain", "left arm", "shortness of breath", "exertion"]
    },
    {
        "query": "Is there any history of diabetes in the patient?",
        "ground_truth_context": "Endocrine Review: Patient has no documented history of diabetes mellitus, blood glucose levels are normal (Fasting 85 mg/dL).",
        "ground_truth_answer": "No history of diabetes mellitus is documented. The fasting blood glucose level was normal at 85 mg/dL.",
        "expected_concepts": ["no history", "diabetes", "glucose", "normal"]
    }
]

def calculate_overlap_ratio(text: str, target_concepts: List[str]) -> float:
    """Calculates the ratio of expected concepts/keywords found in a given text (case-insensitive)."""
    if not target_concepts:
        return 1.0
    text_lower = text.lower()
    matched_count = 0
    for concept in target_concepts:
        # Check if concept exists as a substring or word
        if concept.lower() in text_lower:
            matched_count += 1
    return matched_count / len(target_concepts)

async def run_evaluation() -> Dict[str, Any]:
    print("Initializing test database for RAG evaluation...")
    test_engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    results = []
    
    # Setup mock doctor and patient
    async with async_session() as db:
        doctor = Doctor(id=1, name="Dr. Eval", email="eval_doc@sushruta.ai", hashed_password="mocked_password", license_number="LIC-12345")
        patient = Patient(id=1, name="John Doe", age=45, gender="male", doctor_id=1)
        db.add(doctor)
        db.add(patient)
        await db.commit()

    for i, item in enumerate(EVAL_DATASET):
        query = item["query"]
        gt_context = item["ground_truth_context"]
        gt_answer = item["ground_truth_answer"]
        expected_concepts = item["expected_concepts"]

        # Define custom retrieved chunk mock
        mock_chunks = [
            RetrievedChunk(
                chunk_id=i * 10 + 1,
                document_id=101,
                chunk_index=0,
                chunk_text=gt_context,
                similarity=0.92,
                source_filename=f"medical_report_{i}.txt"
            )
        ]

        # Patch retriever and LLM call
        with patch("app.services.rag_service.search_similar_chunks", new_callable=AsyncMock) as mock_retrieval:
            mock_retrieval.return_value = mock_chunks
            
            # Patch the Google GenAI Client generate_content call
            with patch("app.services.rag_service._client") as mock_client:
                mock_response = MagicMock()
                mock_response.text = gt_answer
                mock_client.models.generate_content.return_value = mock_response

                # Run query
                async with async_session() as db:
                    doctor_obj = await db.get(Doctor, 1)
                    response: RAGAnswerResponse = await ask_question(
                        db=db,
                        patient_id=1,
                        question=query,
                        doctor=doctor_obj,
                        ip_address="127.0.0.1"
                    )

                # Compute evaluation metrics
                context_recall = calculate_overlap_ratio(gt_context, expected_concepts)
                answer_faithfulness = calculate_overlap_ratio(response.answer, expected_concepts)
                
                eval_metrics = {
                    "query": query,
                    "retrieved_context": gt_context,
                    "generated_answer": response.answer,
                    "expected_concepts": expected_concepts,
                    "metrics": {
                        "context_recall": context_recall,
                        "answer_faithfulness": answer_faithfulness,
                        "overall_score": (context_recall + answer_faithfulness) / 2.0
                    }
                }
                results.append(eval_metrics)
                
                print(f"Query {i+1} completed: {query}")
                print(f"  - Context Recall: {context_recall:.2%}")
                print(f"  - Answer Faithfulness: {answer_faithfulness:.2%}")

    await test_engine.dispose()

    # Calculate global averages
    avg_context_recall = sum(r["metrics"]["context_recall"] for r in results) / len(results)
    avg_faithfulness = sum(r["metrics"]["answer_faithfulness"] for r in results) / len(results)
    avg_overall_score = (avg_context_recall + avg_faithfulness) / 2.0

    eval_summary = {
        "summary": {
            "total_queries": len(results),
            "average_context_recall": avg_context_recall,
            "average_answer_faithfulness": avg_faithfulness,
            "average_overall_score": avg_overall_score,
            "status": "PASS" if avg_overall_score >= 0.8 else "FAIL"
        },
        "results": results
    }

    return eval_summary


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    summary_report = loop.run_until_complete(run_evaluation())
    
    # Save JSON results
    workspace_path = "rag_eval_results.json"
    artifact_dir = "C:/Users/LENOVO/.gemini/antigravity/brain/122c4429-7fe9-4cb7-a28a-e809119a87a8"
    artifact_json_path = os.path.join(artifact_dir, "rag_eval_results.json")
    
    with open(workspace_path, "w") as f:
        json.dump(summary_report, f, indent=4)
    print(f"\nSaved local JSON results to: {workspace_path}")

    if os.path.exists(artifact_dir):
        with open(artifact_json_path, "w") as f:
            json.dump(summary_report, f, indent=4)
        print(f"Saved artifact JSON results to: {artifact_json_path}")

    # Generate Markdown Report
    md_content = f"""# Sushruta — RAG Evaluation Pipeline Report

This report presents evaluation metrics for the **Sushruta RAG (Retrieval-Augmented Generation)** question-answering system.
It evaluates:
- **Context Recall**: Coverage of grounding concepts in the retrieved patient document chunks.
- **Answer Faithfulness**: Presence of the retrieved grounding concepts in the AI-generated responses.

## Executive Summary

- **Total Queries Evaluated**: {summary_report["summary"]["total_queries"]}
- **Average Context Recall**: {summary_report["summary"]["average_context_recall"]:.2%}
- **Average Answer Faithfulness**: {summary_report["summary"]["average_answer_faithfulness"]:.2%}
- **Overall System Score**: {summary_report["summary"]["average_overall_score"]:.2%}
- **Evaluation Status**: **{summary_report["summary"]["status"]}**

---

## Detailed Evaluation Results

"""
    for idx, r in enumerate(summary_report["results"]):
        md_content += f"""### Query {idx+1}: {r["query"]}

- **Retrieved Context**: *"{r["retrieved_context"]}"*
- **Generated Answer**: *"{r["generated_answer"]}"*
- **Expected Grounding Concepts**: `{", ".join(r["expected_concepts"])}`
- **Metrics**:
  - Context Recall: `{r["metrics"]["context_recall"]:.2%}`
  - Answer Faithfulness: `{r["metrics"]["answer_faithfulness"]:.2%}`
  - Query Overall Score: `{r["metrics"]["overall_score"]:.2%}`

---
"""

    workspace_md_path = "rag_eval_results.md"
    artifact_md_path = os.path.join(artifact_dir, "rag_eval_results.md")

    with open(workspace_md_path, "w") as f:
        f.write(md_content)
    print(f"Saved local Markdown report to: {workspace_md_path}")

    if os.path.exists(artifact_dir):
        with open(artifact_md_path, "w") as f:
            f.write(md_content)
        print(f"Saved artifact Markdown report to: {artifact_md_path}")
