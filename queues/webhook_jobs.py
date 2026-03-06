import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from database import Flow, FlowGroup, WhatsAppGroup, Workspace, WorkspaceGroup
from database.db import SessionLocal
from flow_engine import flow_engine
from workspace_engine import workspace_engine
from conversation_manager import conversation_manager


logger = logging.getLogger(__name__)


def _resolve_history_client_id(payload: Dict[str, Any], chat_id: str) -> str:
    candidates = [
        payload.get("participant"),
        payload.get("author"),
        payload.get("_data", {}).get("key", {}).get("participant"),
        payload.get("_data", {}).get("key", {}).get("participantAlt"),
        payload.get("from"),
        chat_id,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def process_whatsapp_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full async processing path for WAHA webhook.
    This function is sync because RQ workers execute sync callables.
    """
    chat_id = payload.get("chatId") or payload.get("from")
    history_client_id = _resolve_history_client_id(payload, chat_id)
    body = str(payload.get("body") or "").strip()
    from_me = bool(payload.get("fromMe"))
    conversation_ingested = bool(payload.get("_conversation_ingested"))
    db = SessionLocal()

    try:
        # Keep webhook path conversation-aware so RAG follow-up questions can use prior turns.
        if history_client_id and body and not from_me and not conversation_ingested:
            conversation_manager.add_message(history_client_id, "user", body)

        group = db.query(WhatsAppGroup).filter(
            WhatsAppGroup.chat_id == chat_id,
            WhatsAppGroup.is_enabled == True,  # noqa: E712
        ).first()

        if not group:
            return {"status": "ignored", "reason": "group disabled or not in database"}

        group.last_message_at = datetime.now()
        db.commit()

        active_workspaces = (
            db.query(Workspace)
            .join(WorkspaceGroup)
            .filter(
                WorkspaceGroup.group_id == group.id,
                Workspace.is_active == True,  # noqa: E712
            )
            .order_by(Workspace.created_at.asc())
            .all()
        )

        if active_workspaces:
            workspace_results = []
            for workspace in active_workspaces:
                try:
                    result = _run_async(
                        workspace_engine.execute_workspace(
                            workspace=workspace,
                            payload=payload,
                            db=db,
                        )
                    )
                except Exception as workspace_error:
                    logger.exception("Workspace failed: %s", workspace.name)
                    result = {"status": "error", "message": str(workspace_error)}

                workspace_results.append(
                    {
                        "workspace_id": str(workspace.id),
                        "workspace_name": workspace.name,
                        "result": result,
                    }
                )

            return {
                "status": "workspaces_executed",
                "count": len(workspace_results),
                "results": workspace_results,
            }

        flow_group = (
            db.query(FlowGroup)
            .join(Flow)
            .filter(
                FlowGroup.group_id == group.id,
                Flow.is_enabled == True,  # noqa: E712
            )
            .first()
        )

        if flow_group:
            flow = db.query(Flow).filter(Flow.id == flow_group.flow_id).first()
            execution_result = _run_async(
                flow_engine.execute_flow(
                    flow=flow,
                    trigger_data=payload,
                    db=db,
                )
            )

            return {
                "status": "flow_executed",
                "flow_id": str(flow.id),
                "execution_id": str(execution_result.id),
            }

        return {"status": "ignored", "reason": "no workspace or flow assigned"}

    except Exception as e:
        logger.exception("Webhook job execution failed")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
