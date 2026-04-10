import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Set
from sqlmodel import select
from sqlalchemy import or_
from database import (
    FlowGroupSQLModel,
    FlowSQLModel,
    WhatsAppContactSQLModel,
    WhatsAppGroupSQLModel,
    WorkspaceContactSQLModel,
    WorkspaceGroupSQLModel,
    WorkspaceSQLModel,
)
from database.db import SessionLocal
from flow_engine import flow_engine
from workspace_engine import workspace_engine
from conversation_manager import conversation_manager
from contact_identity import (
    normalize_contact_chat_id,
    extract_sender_id_candidates,
    choose_preferred_contact_id,
)
from workspace_contact_filter import workspace_sender_allowed


logger = logging.getLogger(__name__)

def _upsert_sender_contacts(db, sender_ids: Set[str], display_name: str) -> None:
    now = datetime.now()
    normalized_sender_ids = {
        normalized
        for normalized in (normalize_contact_chat_id(value) for value in sender_ids)
        if normalized and "@g.us" not in normalized
    }
    if not normalized_sender_ids:
        return

    clean_name = str(display_name or "").strip() or None
    lid_value = next((sid for sid in normalized_sender_ids if sid.endswith("@lid")), None)
    phone_jid_value = next((sid for sid in normalized_sender_ids if sid.endswith("@s.whatsapp.net")), None)
    c_us_value = next((sid for sid in normalized_sender_ids if sid.endswith("@c.us")), None)
    canonical_chat_id = lid_value or phone_jid_value or c_us_value or sorted(normalized_sender_ids)[0]
    phone_source = phone_jid_value or canonical_chat_id
    phone_digits = "".join(ch for ch in str(phone_source).split("@", 1)[0] if ch.isdigit())

    lookup_conditions = [
        WhatsAppContactSQLModel.chat_id.in_(normalized_sender_ids),
        WhatsAppContactSQLModel.lid.in_(normalized_sender_ids),
        WhatsAppContactSQLModel.phone_jid.in_(normalized_sender_ids),
        WhatsAppContactSQLModel.waha_contact_id.in_(normalized_sender_ids),
    ]
    if len(phone_digits) >= 8:
        lookup_conditions.append(WhatsAppContactSQLModel.phone_number == phone_digits)

    contact = db.execute(
        select(WhatsAppContactSQLModel).where(or_(*lookup_conditions))
    ).scalars().first()

    if contact:
        if clean_name and (not contact.display_name or str(contact.display_name).strip().isdigit()):
            contact.display_name = clean_name
        if len(phone_digits) >= 8:
            contact.phone_number = phone_digits
        contact.waha_contact_id = c_us_value or contact.waha_contact_id
        contact.lid = lid_value or contact.lid
        contact.phone_jid = phone_jid_value or contact.phone_jid
        # Keep chat_id canonical and stable (prefer lid) when no unique conflict exists.
        if lid_value and contact.chat_id != lid_value:
            chat_conflict = db.execute(
                select(WhatsAppContactSQLModel).where(
                    WhatsAppContactSQLModel.chat_id == lid_value,
                    WhatsAppContactSQLModel.id != contact.id,
                )
            ).scalars().first()
            if not chat_conflict:
                contact.chat_id = lid_value
        contact.last_seen_at = now
        contact.is_active = True
        return

    db.add(
        WhatsAppContactSQLModel(
            chat_id=canonical_chat_id,
            display_name=clean_name,
            phone_number=phone_digits or None,
            waha_contact_id=c_us_value,
            lid=lid_value,
            phone_jid=phone_jid_value,
            source="webhook",
            is_active=True,
            last_seen_at=now,
        )
    )


def _canonical_contact_chat_id(contact: WhatsAppContactSQLModel) -> str:
    """
    Resolve a stable canonical id for WhatsApp memory usage.
    Preference order: lid > phone_jid > waha_contact_id > chat_id.
    """
    return choose_preferred_contact_id(
        (contact.lid, contact.phone_jid, contact.waha_contact_id, contact.chat_id)
    )


def _resolve_canonical_sender_id(db, sender_ids: Set[str], fallback_client_id: str) -> str:
    normalized_sender_ids = {
        normalized
        for normalized in (normalize_contact_chat_id(value) for value in sender_ids)
        if normalized and "@g.us" not in normalized
    }
    normalized_fallback = normalize_contact_chat_id(fallback_client_id)
    if normalized_fallback and "@g.us" not in normalized_fallback:
        normalized_sender_ids.add(normalized_fallback)

    if normalized_sender_ids:
        rows = db.execute(
            select(WhatsAppContactSQLModel).where(
                or_(
                    WhatsAppContactSQLModel.chat_id.in_(normalized_sender_ids),
                    WhatsAppContactSQLModel.lid.in_(normalized_sender_ids),
                    WhatsAppContactSQLModel.phone_jid.in_(normalized_sender_ids),
                    WhatsAppContactSQLModel.waha_contact_id.in_(normalized_sender_ids),
                )
            )
        ).scalars().all()

        if rows:
            # Prefer richer, recently seen contact row as canonical source.
            best_contact = max(
                rows,
                key=lambda contact: (
                    int(bool(normalize_contact_chat_id(contact.lid))),
                    int(bool(normalize_contact_chat_id(contact.phone_jid))),
                    int(bool(normalize_contact_chat_id(contact.waha_contact_id))),
                    int(bool(normalize_contact_chat_id(contact.chat_id))),
                    contact.last_seen_at or datetime.min,
                    contact.updated_at or datetime.min,
                    contact.created_at or datetime.min,
                ),
            )
            canonical = _canonical_contact_chat_id(best_contact)
            if canonical:
                return canonical

    fallback_selected = choose_preferred_contact_id(normalized_sender_ids)
    if fallback_selected:
        return fallback_selected
    return normalized_fallback or str(fallback_client_id or "").strip()


def _workspace_contact_filters(db, workspace_ids: List[Any]) -> Dict[Any, Set[str]]:
    if not workspace_ids:
        return {}
    rows = db.execute(
        select(
            WorkspaceContactSQLModel.workspace_id,
            WhatsAppContactSQLModel.chat_id,
            WhatsAppContactSQLModel.lid,
            WhatsAppContactSQLModel.phone_jid,
            WhatsAppContactSQLModel.waha_contact_id,
        )
        .join(WhatsAppContactSQLModel, WhatsAppContactSQLModel.id == WorkspaceContactSQLModel.contact_id)
        .where(WorkspaceContactSQLModel.workspace_id.in_(workspace_ids))
    ).all()
    mapping: Dict[Any, Set[str]] = {}
    for workspace_id, chat_id, lid, phone_jid, waha_contact_id in rows:
        bucket = mapping.setdefault(workspace_id, set())
        for raw in (chat_id, lid, phone_jid, waha_contact_id):
            normalized = normalize_contact_chat_id(raw)
            if normalized and "@g.us" not in normalized:
                bucket.add(normalized)
    return mapping


def _workspace_sender_allowed(workspace: Any, sender_ids: Set[str], allowed_map: Dict[Any, Set[str]]) -> bool:
    allowed_ids = allowed_map.get(workspace.id, set())
    return workspace_sender_allowed(
        mode=getattr(workspace, "contact_filter_mode", "all"),
        sender_ids=sender_ids,
        allowed_ids=allowed_ids,
    )


def _active_direct_chat_workspaces(db) -> List[Any]:
    """
    For direct chats (non-group), run only explicitly contact-targeted active workspaces.
    """
    return db.execute(
        select(WorkspaceSQLModel)
        .join(WorkspaceContactSQLModel, WorkspaceContactSQLModel.workspace_id == WorkspaceSQLModel.id)
        .where(
            WorkspaceSQLModel.is_active == True,  # noqa: E712
            WorkspaceSQLModel.contact_filter_mode == "only",
        )
        .order_by(WorkspaceSQLModel.created_at.asc())
        .distinct()
    ).scalars().all()


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
    sender_ids = extract_sender_id_candidates(payload, chat_id)
    sender_display_name = (
        payload.get("_data", {}).get("pushName")
        or payload.get("pushName")
        or payload.get("notifyName")
        or ""
    )
    body = str(payload.get("body") or "").strip()
    from_me = bool(payload.get("fromMe"))
    conversation_ingested = bool(payload.get("_conversation_ingested"))
    db = SessionLocal()

    try:
        if sender_ids and not from_me:
            _upsert_sender_contacts(db, sender_ids=sender_ids, display_name=str(sender_display_name))
            db.flush()
        canonical_history_client_id = _resolve_canonical_sender_id(db, sender_ids, history_client_id)
        if canonical_history_client_id:
            payload["_memory_client_id"] = canonical_history_client_id

        # Keep webhook path conversation-aware so RAG follow-up questions can use prior turns.
        if (
            canonical_history_client_id
            and body
            and not from_me
            and not conversation_ingested
            and conversation_manager.get_default_memory_scope() != "client_workspace"
        ):
            conversation_manager.add_message(canonical_history_client_id, "user", body)

        group = db.execute(
            select(WhatsAppGroupSQLModel).where(
                WhatsAppGroupSQLModel.chat_id == chat_id,
                WhatsAppGroupSQLModel.is_enabled == True,  # noqa: E712
            )
        ).scalars().first()
        active_workspaces: List[Any] = []
        routing_mode = "group"

        if group:
            group.last_message_at = datetime.now()
            db.commit()
            active_workspaces = db.execute(
                select(WorkspaceSQLModel)
                .join(WorkspaceGroupSQLModel, WorkspaceGroupSQLModel.workspace_id == WorkspaceSQLModel.id)
                .where(
                    WorkspaceGroupSQLModel.group_id == group.id,
                    WorkspaceSQLModel.is_active == True,  # noqa: E712
                )
                .order_by(WorkspaceSQLModel.created_at.asc())
            ).scalars().all()
        else:
            routing_mode = "direct_chat"
            active_workspaces = _active_direct_chat_workspaces(db)

        if active_workspaces:
            workspace_contact_map = _workspace_contact_filters(
                db,
                workspace_ids=[workspace.id for workspace in active_workspaces],
            )
            workspace_results = []
            for workspace in active_workspaces:
                # Contact filter should apply only to direct/personal chats.
                # For group-routed workspaces, group assignment is the source of truth.
                if (
                    routing_mode == "direct_chat"
                    and sender_ids
                    and not _workspace_sender_allowed(workspace, sender_ids, workspace_contact_map)
                ):
                    workspace_results.append(
                        {
                            "workspace_id": str(workspace.id),
                            "workspace_name": workspace.name,
                            "result": {
                                "status": "skipped",
                                "reason": "contact_filter_no_match",
                            },
                        }
                    )
                    continue
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
                "routing_mode": routing_mode,
                "count": len(workspace_results),
                "results": workspace_results,
            }

        if not group:
            return {"status": "ignored", "reason": "direct chat not mapped to any active workspace"}

        flow_group = db.execute(
            select(FlowGroupSQLModel)
            .join(FlowSQLModel, FlowSQLModel.id == FlowGroupSQLModel.flow_id)
            .where(
                FlowGroupSQLModel.group_id == group.id,
                FlowSQLModel.is_enabled == True,  # noqa: E712
            )
        ).scalars().first()

        if flow_group:
            flow = db.execute(
                select(FlowSQLModel).where(FlowSQLModel.id == flow_group.flow_id)
            ).scalars().first()
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
