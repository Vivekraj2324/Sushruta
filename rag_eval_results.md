# Sushruta — RAG Evaluation Pipeline Report

This report presents evaluation metrics for the **Sushruta RAG (Retrieval-Augmented Generation)** question-answering system.
It evaluates:
- **Context Recall**: Coverage of grounding concepts in the retrieved patient document chunks.
- **Answer Faithfulness**: Presence of the retrieved grounding concepts in the AI-generated responses.

## Executive Summary

- **Total Queries Evaluated**: 3
- **Average Context Recall**: 91.67%
- **Average Answer Faithfulness**: 91.67%
- **Overall System Score**: 91.67%
- **Evaluation Status**: **PASS**

---

## Detailed Evaluation Results

### Query 1: What are the patient's active allergies?

- **Retrieved Context**: *"Allergy Profile: Penicillin (severe anaphylaxis) and Peanuts (mild hives)."*
- **Generated Answer**: *"The patient has a severe anaphylactic allergy to Penicillin and a mild allergic reaction (hives) to Peanuts."*
- **Expected Grounding Concepts**: `penicillin, anaphylaxis, peanuts, hives`
- **Metrics**:
  - Context Recall: `100.00%`
  - Answer Faithfulness: `75.00%`
  - Query Overall Score: `87.50%`

---
### Query 2: Summarise the patient's cardiovascular symptoms.

- **Retrieved Context**: *"Cardiology Note: Patient reports intermittent chest pain radiating to the left arm, accompanied by mild shortness of breath during exertion."*
- **Generated Answer**: *"The patient experienced intermittent chest pain radiating to the left arm and mild shortness of breath on exertion."*
- **Expected Grounding Concepts**: `chest pain, left arm, shortness of breath, exertion`
- **Metrics**:
  - Context Recall: `100.00%`
  - Answer Faithfulness: `100.00%`
  - Query Overall Score: `100.00%`

---
### Query 3: Is there any history of diabetes in the patient?

- **Retrieved Context**: *"Endocrine Review: Patient has no documented history of diabetes mellitus, blood glucose levels are normal (Fasting 85 mg/dL)."*
- **Generated Answer**: *"No history of diabetes mellitus is documented. The fasting blood glucose level was normal at 85 mg/dL."*
- **Expected Grounding Concepts**: `no history, diabetes, glucose, normal`
- **Metrics**:
  - Context Recall: `75.00%`
  - Answer Faithfulness: `100.00%`
  - Query Overall Score: `87.50%`

---
