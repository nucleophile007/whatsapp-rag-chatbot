from typing import Any, Callable, Dict, Type

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from database import get_db_session


def build_workspaces_router(
    get_workspaces_handler: Callable[..., Dict[str, Any]],
    create_workspace_handler: Callable[..., Dict[str, Any]],
    get_workspace_handler: Callable[..., Dict[str, Any]],
    update_workspace_handler: Callable[..., Dict[str, Any]],
    delete_workspace_handler: Callable[..., Dict[str, Any]],
    attach_workspace_flow_handler: Callable[..., Dict[str, Any]],
    detach_workspace_flow_handler: Callable[..., Dict[str, Any]],
    toggle_workspace_handler: Callable[..., Dict[str, Any]],
    set_workspace_status_handler: Callable[..., Dict[str, Any]],
    set_workspace_status_get_handler: Callable[..., Dict[str, Any]],
    workspace_create_model: Type[Any],
    workspace_status_update_model: Type[Any],
) -> APIRouter:
    router = APIRouter()
    WorkspaceCreateModel = workspace_create_model
    WorkspaceStatusUpdateModel = workspace_status_update_model

    @router.get("/api/workspaces")
    def get_workspaces(db: Session = Depends(get_db_session)):
        return get_workspaces_handler(db=db)

    @router.post("/api/workspaces")
    def create_workspace(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db_session)):
        parsed_payload = WorkspaceCreateModel(**payload)
        return create_workspace_handler(data=parsed_payload, db=db)

    @router.get("/api/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str, db: Session = Depends(get_db_session)):
        return get_workspace_handler(workspace_id=workspace_id, db=db)

    @router.put("/api/workspaces/{workspace_id}")
    def update_workspace(
        workspace_id: str,
        payload: Dict[str, Any] = Body(...),
        db: Session = Depends(get_db_session),
    ):
        parsed_payload = WorkspaceCreateModel(**payload)
        return update_workspace_handler(workspace_id=workspace_id, data=parsed_payload, db=db)

    @router.delete("/api/workspaces/{workspace_id}")
    def delete_workspace(workspace_id: str, db: Session = Depends(get_db_session)):
        return delete_workspace_handler(workspace_id=workspace_id, db=db)

    @router.post("/api/workspaces/{workspace_id}/flows/{flow_id}")
    def attach_workspace_flow(workspace_id: str, flow_id: str, db: Session = Depends(get_db_session)):
        return attach_workspace_flow_handler(workspace_id=workspace_id, flow_id=flow_id, db=db)

    @router.delete("/api/workspaces/{workspace_id}/flows/{flow_id}")
    def detach_workspace_flow(workspace_id: str, flow_id: str, db: Session = Depends(get_db_session)):
        return detach_workspace_flow_handler(workspace_id=workspace_id, flow_id=flow_id, db=db)

    @router.patch("/api/workspaces/{workspace_id}/toggle")
    def toggle_workspace(workspace_id: str, db: Session = Depends(get_db_session)):
        return toggle_workspace_handler(workspace_id=workspace_id, db=db)

    @router.patch("/api/workspaces/{workspace_id}/status")
    def set_workspace_status(
        workspace_id: str,
        payload: Dict[str, Any] = Body(...),
        db: Session = Depends(get_db_session),
    ):
        parsed_payload = WorkspaceStatusUpdateModel(**payload)
        return set_workspace_status_handler(workspace_id=workspace_id, data=parsed_payload, db=db)

    @router.get("/api/workspaces/{workspace_id}/status/set")
    def set_workspace_status_get(
        workspace_id: str,
        is_active: str = Query(...),
        db: Session = Depends(get_db_session),
    ):
        return set_workspace_status_get_handler(workspace_id=workspace_id, is_active=is_active, db=db)

    return router
