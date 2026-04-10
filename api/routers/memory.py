from typing import Any, Callable, Dict, Type

from fastapi import APIRouter, Body, Query


def build_memory_router(
    get_memory_debug_snapshot_handler: Callable[..., Dict[str, Any]],
    upsert_memory_ltm_handler: Callable[..., Dict[str, Any]],
    deactivate_memory_ltm_handler: Callable[..., Dict[str, Any]],
    clear_memory_for_client_handler: Callable[..., Dict[str, Any]],
    memory_ltm_update_model: Type[Any],
) -> APIRouter:
    router = APIRouter()
    MemoryLTMUpdateModel = memory_ltm_update_model

    @router.get("/api/memory/{client_id}")
    def get_memory_debug_snapshot(
        client_id: str,
        query: str = Query(default=""),
        history_limit: int = Query(default=24, ge=1, le=200),
        token_budget: int = Query(default=1200, ge=120, le=8000),
        ltm_limit: int = Query(default=50, ge=1, le=400),
        include_inactive: bool = Query(default=False),
        workspace_id: str = Query(default=None),
        memory_scope: str = Query(default=None),
    ):
        return get_memory_debug_snapshot_handler(
            client_id=client_id,
            query=query,
            history_limit=history_limit,
            token_budget=token_budget,
            ltm_limit=ltm_limit,
            include_inactive=include_inactive,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )

    @router.patch("/api/memory/{client_id}/ltm")
    def upsert_memory_ltm(
        client_id: str,
        payload: Dict[str, Any] = Body(...),
        workspace_id: str = Query(default=None),
        memory_scope: str = Query(default=None),
    ):
        parsed_payload = MemoryLTMUpdateModel(**payload)
        return upsert_memory_ltm_handler(
            client_id=client_id,
            payload=parsed_payload,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )

    @router.delete("/api/memory/{client_id}/ltm")
    def deactivate_memory_ltm(
        client_id: str,
        memory_key: str = Query(..., min_length=1, max_length=160),
        workspace_id: str = Query(default=None),
        memory_scope: str = Query(default=None),
    ):
        return deactivate_memory_ltm_handler(
            client_id=client_id,
            memory_key=memory_key,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )

    @router.delete("/api/memory/{client_id}")
    def clear_memory_for_client(
        client_id: str,
        workspace_id: str = Query(default=None),
        memory_scope: str = Query(default=None),
    ):
        return clear_memory_for_client_handler(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )

    return router
