from typing import Any, Callable, Dict, Type

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from database import get_db_session


def build_rag_router(
    evaluate_rag_quality_handler: Callable[..., Dict[str, Any]],
    list_rag_scorecards_handler: Callable[..., Dict[str, Any]],
    get_rag_scorecard_handler: Callable[..., Dict[str, Any]],
    rag_eval_request_model: Type[Any],
) -> APIRouter:
    router = APIRouter()
    RAGEvalRequestModel = rag_eval_request_model

    @router.post("/api/rag/evaluate")
    def evaluate_rag_quality(
        payload: Dict[str, Any] = Body(...),
        db: Session = Depends(get_db_session),
    ):
        parsed_payload = RAGEvalRequestModel(**payload)
        return evaluate_rag_quality_handler(payload=parsed_payload, db=db)

    @router.get("/api/rag/scorecards")
    def list_rag_scorecards(
        collection_name: str = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
        db: Session = Depends(get_db_session),
    ):
        return list_rag_scorecards_handler(collection_name=collection_name, limit=limit, db=db)

    @router.get("/api/rag/scorecards/{scorecard_id}")
    def get_rag_scorecard(scorecard_id: str, db: Session = Depends(get_db_session)):
        return get_rag_scorecard_handler(scorecard_id=scorecard_id, db=db)

    return router
