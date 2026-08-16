"""
Sushruta — V1 API Router Aggregation
======================================

Combines all v1 route modules into a single router
that is mounted at /api/v1 in main.py.

Adding a new route module:
1. Create the router file in app/api/v1/
2. Import and include it here.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.patients import router as patients_router
from app.api.v1.rag import router as rag_router
from app.api.v1.notes import router as notes_router
from app.api.v1.interactions import router as interactions_router

# Master v1 router — all sub-routers are mounted here
api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(patients_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(rag_router)
api_v1_router.include_router(notes_router)
api_v1_router.include_router(interactions_router)
