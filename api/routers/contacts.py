from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db_session


def build_contacts_router(
    get_contacts_handler: Callable[..., Dict[str, Any]],
    sync_contacts_handler: Callable[..., Dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/contacts")
    def get_contacts(db: Session = Depends(get_db_session)):
        return get_contacts_handler(db=db)

    @router.post("/api/contacts/sync")
    def sync_contacts(
        allow_fallback: bool = Query(default=False),
        db: Session = Depends(get_db_session),
    ):
        return sync_contacts_handler(allow_fallback=allow_fallback, db=db)

    return router
