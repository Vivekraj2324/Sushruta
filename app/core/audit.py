"""
Sushruta — Audit Logging
=========================

Immutable audit trail for every data access and mutation.

Every action on patient data is logged:
- Who (doctor_id)
- What (action + resource_type + resource_id)
- When (created_at via server_default)
- Where (ip_address)
- Why (details JSON)

This is a legal requirement for clinical systems. The audit_logs
table is append-only — no UPDATE or DELETE operations.

Design decisions:
- Audit writes happen inside the same DB session as the action.
  If the action fails, the audit log is also rolled back — correct.
  If the action succeeds but audit fails, both roll back — safe.
- JSON details field is flexible: different actions store different
  context without schema changes.
- IP address captured for forensic analysis.

Usage:
    await create_audit_log(
        db=db,
        doctor_id=doctor.id,
        action="PATIENT_CREATED",
        resource_type="patient",
        resource_id=patient.id,
        details='{"name": "John Doe"}',
    )
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def create_audit_log(
    db: AsyncSession,
    *,
    doctor_id: int | None = None,
    patient_id: int | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Create an immutable audit log entry.

    Parameters
    ----------
    db : AsyncSession
        Database session (same session as the triggering action).
    doctor_id : int, optional
        ID of the doctor performing the action. None for system actions.
    patient_id : int, optional
        ID of the affected patient, if applicable.
    action : str
        Action identifier, e.g. DOCTOR_REGISTERED, PATIENT_CREATED,
        DOCUMENT_UPLOADED, DOCUMENT_DELETED, PATIENT_UPDATED, etc.
    resource_type : str, optional
        Type of resource affected: "doctor", "patient", "document".
    resource_id : int, optional
        Primary key of the affected resource.
    details : str, optional
        JSON string with additional context about the action.
    ip_address : str, optional
        Client IP address from the request.

    Returns
    -------
    AuditLog
        The created audit log entry (not yet committed — caller
        should commit the session after all mutations are done).
    """
    audit_entry = AuditLog(
        doctor_id=doctor_id,
        patient_id=patient_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(audit_entry)
    # Note: We do NOT commit here. The caller's session commit
    # will include this entry atomically with the main operation.
    return audit_entry


# ── Action Constants ─────────────────────────────────────────────
# Centralised action names prevent typos and enable grep-ability.

class AuditAction:
    """Namespace for audit action identifiers."""

    DOCTOR_REGISTERED = "DOCTOR_REGISTERED"
    DOCTOR_LOGIN = "DOCTOR_LOGIN"
    DOCTOR_PROFILE_VIEWED = "DOCTOR_PROFILE_VIEWED"

    PATIENT_CREATED = "PATIENT_CREATED"
    PATIENT_VIEWED = "PATIENT_VIEWED"
    PATIENT_UPDATED = "PATIENT_UPDATED"
    PATIENT_DELETED = "PATIENT_DELETED"
    PATIENT_LIST_VIEWED = "PATIENT_LIST_VIEWED"

    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_VIEWED = "DOCUMENT_VIEWED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    DOCUMENT_LIST_VIEWED = "DOCUMENT_LIST_VIEWED"
    DOCUMENT_TEXT_EXTRACTED = "DOCUMENT_TEXT_EXTRACTED"

    # Phase 2 — RAG Pipeline
    DOCUMENT_PROCESSED = "DOCUMENT_PROCESSED"  # Chunked + embedded
    RAG_QUERY = "RAG_QUERY"  # Doctor asked a question

    # Phase 3 — Agent Layer
    CLINICAL_NOTE_GENERATED = "CLINICAL_NOTE_GENERATED"
    CLINICAL_NOTE_CREATED = "CLINICAL_NOTE_CREATED"
    CLINICAL_NOTE_VIEWED = "CLINICAL_NOTE_VIEWED"
    CLINICAL_NOTE_UPDATED = "CLINICAL_NOTE_UPDATED"
    CLINICAL_NOTE_DELETED = "CLINICAL_NOTE_DELETED"
    CLINICAL_INTERACTION_RECORDED = "CLINICAL_INTERACTION_RECORDED"
    CLINICAL_INTERACTION_VIEWED = "CLINICAL_INTERACTION_VIEWED"
    DRUG_INTERACTION_CHECKED = "DRUG_INTERACTION_CHECKED"
    PATIENT_SUMMARY_GENERATED = "PATIENT_SUMMARY_GENERATED"
    REFERRAL_LETTER_GENERATED = "REFERRAL_LETTER_GENERATED"

