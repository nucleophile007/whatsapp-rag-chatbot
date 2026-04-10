from dotenv import load_dotenv
import asyncio
import logging
import hashlib
import json
import time
import threading
import re
from collections import defaultdict
from datetime import datetime, timedelta
import os
import requests
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

# Ye lo, load ho gaya environment
load_dotenv()

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from client.rq_client import queue
from queues.worker import process_query
from queues.webhook_jobs import process_whatsapp_payload
from rq import Worker
from rq.registry import DeferredJobRegistry, FailedJobRegistry, FinishedJobRegistry, ScheduledJobRegistry, StartedJobRegistry
from sqlalchemy import or_, text, func, delete
from sqlalchemy.orm import Session
from sqlmodel import select
import shutil
import tempfile
import uuid

# Database aur engines ke saaman
from database import (
    get_db_session,
    SessionLocal,
    KnowledgeBaseSQLModel,
    KnowledgeBaseRetrievalProfileSQLModel,
    WorkspaceSQLModel,
    FlowSQLModel,
    WhatsAppGroupSQLModel,
    WhatsAppContactSQLModel,
    WorkspaceGroupSQLModel,
    WorkspaceContactSQLModel,
    WorkspaceFlowSQLModel,
    FlowGroupSQLModel,
    FlowExecutionSQLModel,
    RAGEvalScorecardSQLModel,
    RAGEvalCaseResultSQLModel,
)
from waha_client import waha_client
from rag_utils import (
    create_qdrant_collection,
    get_collection_point_count,
    index_pdfs_to_collection,
    index_urls_to_collection,
    list_qdrant_collections,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)
from contact_identity import normalize_contact_chat_id
from api.routers.contacts import build_contacts_router
from api.routers.memory import build_memory_router
from api.routers.rag import build_rag_router
from api.routers.workspaces import build_workspaces_router

# ============================================================================
# FLOW TEMPLATES LIBRARY
# ============================================================================

FLOW_TEMPLATES = [
    {
        "id": "tpl_rag_bot",
        "name": "RAG Knowledge Bot",
        "description": "Answers questions based on your documents using AI.",
        "trigger_type": "whatsapp_mention",
        "definition": {
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "data": {
                        "label": "On Mention",
                        "type": "trigger",
                        "subType": "whatsapp_mention",
                        "config": {"bot_lid": ""}
                    },
                    "position": {"x": 100, "y": 100}
                },
                {
                    "id": "action_1",
                    "type": "action",
                    "data": {
                        "label": "RAG Query",
                        "type": "action",
                        "subType": "rag_query",
                        "config": {"query": "{{trigger.body}}"}
                    },
                    "position": {"x": 100, "y": 250},
                    "next": "action_2"
                },
                {
                    "id": "action_2",
                    "type": "action",
                    "data": {
                        "label": "Send Reply",
                        "type": "action",
                        "subType": "send_whatsapp_message",
                        "config": {
                            "chat_id": "{{trigger.chatId}}", 
                            "text": "{{action_1.rag_result}}",
                            "reply_to": "{{trigger.message_id}}"
                        }
                    },
                    "position": {"x": 100, "y": 400}
                }
            ],
            "edges": [
                {"id": "e1-2", "source": "trigger_1", "target": "action_1"},
                {"id": "e2-3", "source": "action_1", "target": "action_2"}
            ]
        }
    },
    {
        "id": "tpl_echo_bot",
        "name": "Simple Echo Bot",
        "description": "Replies with exactly what the user sent.",
        "trigger_type": "whatsapp_message",
        "definition": {
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "data": {
                        "label": "On Message",
                        "type": "trigger",
                        "subType": "whatsapp_message",
                        "config": {}
                    },
                    "position": {"x": 100, "y": 100},
                    "next": "action_1"
                },
                {
                    "id": "action_1",
                    "type": "action",
                    "data": {
                        "label": "Echo Reply",
                        "type": "action",
                        "subType": "send_whatsapp_message",
                        "config": {
                            "chat_id": "{{trigger.chatId}}", 
                            "text": "You said: {{trigger.body}}"
                        }
                    },
                    "position": {"x": 100, "y": 250}
                }
            ],
            "edges": [
                {"id": "e1-2", "source": "trigger_1", "target": "action_1"}
            ]
        }
    },
    {
        "id": "tpl_keyword_reply",
        "name": "Keyword Auto-Reply",
        "description": "Replies if message contains specific text.",
        "trigger_type": "whatsapp_message",
        "definition": {
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "data": {
                        "label": "On Message",
                        "type": "trigger",
                        "subType": "whatsapp_message",
                        "config": {}
                    },
                    "position": {"x": 250, "y": 50}
                },
                {
                    "id": "cond_1",
                    "type": "condition",
                    "data": {
                        "label": "Check Keyword",
                        "type": "condition",
                        "subType": "text_contains",
                        "config": {"pattern": "help", "case_sensitive": False}
                    },
                    "position": {"x": 250, "y": 200},
                    "on_success": "action_yes"
                },
                {
                    "id": "action_yes",
                    "type": "action",
                    "data": {
                        "label": "Send Help Menu",
                        "type": "action",
                        "subType": "send_whatsapp_message",
                        "config": {
                            "chat_id": "{{trigger.chatId}}", 
                            "text": "Here is the help menu:\n1. Support\n2. Sales"
                        }
                    },
                    "position": {"x": 100, "y": 350}
                }
            ],
            "edges": [
                {"id": "e1-2", "source": "trigger_1", "target": "cond_1"},
                {"id": "e2-3", "source": "cond_1", "target": "action_yes", "sourceHandle": "true"}
            ]
        }
    }
]




app = FastAPI()
logger = logging.getLogger(__name__)

# Add CORS middleware to allow browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_private_network_preflight(request: Request, call_next):
    """
    Chrome blocks some cross-origin requests after successful OPTIONS preflight
    unless Access-Control-Allow-Private-Network is present.
    """
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


_workspace_flow_schema_ready = False
RQ_WORKER_DESIRED_KEY = os.getenv("RQ_WORKER_DESIRED_KEY", "rq:workers:desired_count")
RQ_WORKER_MANAGER_HEARTBEAT_KEY = os.getenv("RQ_WORKER_MANAGER_HEARTBEAT_KEY", "rq:workers:manager:heartbeat")
RQ_WORKER_MIN_COUNT = max(1, int(os.getenv("RQ_WORKER_MIN_COUNT", "1")))
RQ_WORKER_MAX_COUNT = max(RQ_WORKER_MIN_COUNT, int(os.getenv("RQ_WORKER_MAX_COUNT", "16")))
RQ_WORKER_DEFAULT_COUNT = min(
    RQ_WORKER_MAX_COUNT,
    max(RQ_WORKER_MIN_COUNT, int(os.getenv("RQ_WORKER_DEFAULT_COUNT", "1"))),
)
INDEX_JOB_TTL_SECONDS = max(300, int(os.getenv("INDEX_JOB_TTL_SECONDS", "7200")))

_index_jobs: Dict[str, Dict[str, Any]] = {}
_index_jobs_lock = threading.Lock()


def _utc_iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _purge_stale_index_jobs_locked(now_ts: float) -> None:
    stale_ids: List[str] = []
    for job_id, payload in _index_jobs.items():
        status = str(payload.get("status") or "").strip().lower()
        updated_epoch = float(payload.get("updated_epoch") or 0.0)
        if status in {"completed", "failed"} and (now_ts - updated_epoch) > INDEX_JOB_TTL_SECONDS:
            stale_ids.append(job_id)
    for stale_id in stale_ids:
        _index_jobs.pop(stale_id, None)


def _set_index_job(job_id: str, **updates: Any) -> Dict[str, Any]:
    now_ts = time.time()
    now_iso = _utc_iso_now()
    with _index_jobs_lock:
        _purge_stale_index_jobs_locked(now_ts)
        current = dict(_index_jobs.get(job_id) or {})
        previous_pct = float(current.get("progress_percent") or 0.0)
        next_pct = updates.get("progress_percent")
        if next_pct is not None:
            try:
                safe_pct = max(0.0, min(100.0, float(next_pct)))
            except (TypeError, ValueError):
                safe_pct = previous_pct
            # Keep progress monotonic unless explicitly resetting for a new job state.
            updates["progress_percent"] = max(previous_pct, safe_pct)
        current.update(updates)
        current["job_id"] = job_id
        current["updated_at"] = now_iso
        current["updated_epoch"] = now_ts
        _index_jobs[job_id] = current
        return dict(current)


def _get_index_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _index_jobs_lock:
        payload = _index_jobs.get(job_id)
        return dict(payload) if payload else None


def _public_index_job_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    public = dict(payload)
    public.pop("updated_epoch", None)
    public.pop("temp_dir", None)
    public.pop("file_paths", None)
    public.pop("urls", None)
    return public


def ensure_workspace_flow_schema(db: Session) -> None:
    """Create runtime support tables and backfill legacy assignments."""
    global _workspace_flow_schema_ready
    if _workspace_flow_schema_ready:
        return

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_flows (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            flow_id UUID REFERENCES flows(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, flow_id)
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workspace_flows_workspace_id ON workspace_flows(workspace_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workspace_flows_flow_id ON workspace_flows(flow_id)"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS whatsapp_contacts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            chat_id VARCHAR(255) UNIQUE NOT NULL,
            display_name VARCHAR(255),
            phone_number VARCHAR(32),
            waha_contact_id VARCHAR(255),
            lid VARCHAR(255),
            phone_jid VARCHAR(255),
            source VARCHAR(30) NOT NULL DEFAULT 'webhook',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_seen_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_contacts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            contact_id UUID REFERENCES whatsapp_contacts(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, contact_id)
        )
    """))
    db.execute(text("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS contact_filter_mode VARCHAR(20) NOT NULL DEFAULT 'all'"))
    db.execute(text("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS low_quality_clarification_text TEXT"))
    db.execute(text("ALTER TABLE whatsapp_contacts ADD COLUMN IF NOT EXISTS waha_contact_id VARCHAR(255)"))
    db.execute(text("ALTER TABLE whatsapp_contacts ADD COLUMN IF NOT EXISTS lid VARCHAR(255)"))
    db.execute(text("ALTER TABLE whatsapp_contacts ADD COLUMN IF NOT EXISTS phone_jid VARCHAR(255)"))

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge_base_retrieval_profiles (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            knowledge_base_id UUID UNIQUE REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            final_context_k INTEGER,
            retrieval_candidates INTEGER,
            grounding_threshold DOUBLE PRECISION,
            require_citations BOOLEAN,
            min_context_chars INTEGER,
            query_variants_limit INTEGER,
            clarification_enabled BOOLEAN DEFAULT TRUE,
            clarification_threshold DOUBLE PRECISION,
            chunk_size INTEGER,
            chunk_overlap INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS rag_eval_scorecards (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            collection_name VARCHAR(255) NOT NULL,
            knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
            total_cases INTEGER NOT NULL,
            fallback_rate DOUBLE PRECISION NOT NULL,
            citation_ok_rate DOUBLE PRECISION NOT NULL,
            grounding_pass_rate DOUBLE PRECISION NOT NULL,
            expectation_hit_rate DOUBLE PRECISION NOT NULL,
            avg_latency_ms DOUBLE PRECISION NOT NULL,
            rag_options JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS rag_eval_case_results (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            scorecard_id UUID REFERENCES rag_eval_scorecards(id) ON DELETE CASCADE,
            case_index INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            expected_contains JSONB,
            expectation_hit BOOLEAN NOT NULL,
            fallback_used BOOLEAN NOT NULL,
            citation_ok BOOLEAN NOT NULL,
            grounding JSONB,
            latency_ms DOUBLE PRECISION NOT NULL,
            retrieved_chunks JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS conversation_long_term_memories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            client_id VARCHAR(255) NOT NULL,
            memory_key VARCHAR(160) NOT NULL,
            memory_text TEXT NOT NULL,
            memory_category VARCHAR(50) NOT NULL DEFAULT 'general',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            source_message TEXT,
            metadata JSONB,
            hit_count INTEGER NOT NULL DEFAULT 1,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_seen_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(client_id, memory_key)
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_kb_retrieval_profiles_kb_id ON knowledge_base_retrieval_profiles(knowledge_base_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_rag_eval_scorecards_collection ON rag_eval_scorecards(collection_name)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_rag_eval_case_results_scorecard ON rag_eval_case_results(scorecard_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_ltm_client ON conversation_long_term_memories(client_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_ltm_active ON conversation_long_term_memories(client_id, is_active)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workspace_contacts_workspace_id ON workspace_contacts(workspace_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workspace_contacts_contact_id ON workspace_contacts(contact_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_whatsapp_contacts_chat_id ON whatsapp_contacts(chat_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_whatsapp_contacts_last_seen ON whatsapp_contacts(last_seen_at DESC)"))

    # Legacy support: migrate old single-owner mapping into reusable table.
    db.execute(text("""
        INSERT INTO workspace_flows (workspace_id, flow_id)
        SELECT workspace_id, id
        FROM flows
        WHERE workspace_id IS NOT NULL
        ON CONFLICT (workspace_id, flow_id) DO NOTHING
    """))
    db.commit()
    _workspace_flow_schema_ready = True


def _model_dump(payload: BaseModel) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)  # pydantic v2
    return payload.dict(exclude_unset=True)  # pydantic v1


def _parse_workspace_uuid_list(raw_values: List[str]) -> List[uuid.UUID]:
    parsed: List[uuid.UUID] = []
    seen = set()
    for value in raw_values:
        parsed_id = uuid.UUID(str(value))
        if parsed_id in seen:
            continue
        seen.add(parsed_id)
        parsed.append(parsed_id)
    return parsed


def _get_flow_workspace_usage(db: Session, flows: List[Any]) -> Dict[uuid.UUID, List[Dict[str, str]]]:
    usage: Dict[uuid.UUID, List[Dict[str, str]]] = {flow.id: [] for flow in flows}
    flow_ids = [flow.id for flow in flows]
    if not flow_ids:
        return usage

    rows = db.execute(
        select(WorkspaceFlowSQLModel.flow_id, WorkspaceSQLModel.id, WorkspaceSQLModel.name)
        .join(WorkspaceSQLModel, WorkspaceSQLModel.id == WorkspaceFlowSQLModel.workspace_id)
        .where(WorkspaceFlowSQLModel.flow_id.in_(flow_ids))
        .order_by(WorkspaceSQLModel.name.asc())
    ).all()
    for flow_id, workspace_id, workspace_name in rows:
        usage.setdefault(flow_id, []).append(
            {"id": str(workspace_id), "name": workspace_name}
        )

    # Fallback for older rows not backfilled yet.
    legacy_workspace_ids = [flow.workspace_id for flow in flows if getattr(flow, "workspace_id", None)]
    workspace_name_by_id: Dict[uuid.UUID, str] = {}
    if legacy_workspace_ids:
        legacy_rows = db.execute(
            select(WorkspaceSQLModel.id, WorkspaceSQLModel.name).where(WorkspaceSQLModel.id.in_(legacy_workspace_ids))
        ).all()
        workspace_name_by_id = {workspace_id: workspace_name for workspace_id, workspace_name in legacy_rows}

    for flow in flows:
        if usage.get(flow.id):
            continue
        if flow.workspace_id and flow.workspace_id in workspace_name_by_id:
            usage[flow.id] = [{"id": str(flow.workspace_id), "name": workspace_name_by_id[flow.workspace_id]}]

    return usage


def _serialize_flow(flow: Any, workspace_links: List[Dict[str, str]]) -> Dict[str, Any]:
    workspace_ids = [link["id"] for link in workspace_links]
    workspace_names = [link["name"] for link in workspace_links]
    return {
        "id": str(flow.id),
        "name": flow.name,
        "description": flow.description,
        "workspace_id": workspace_ids[0] if workspace_ids else None,
        "workspace_name": workspace_names[0] if workspace_names else None,
        "workspace_ids": workspace_ids,
        "workspace_names": workspace_names,
        "workspace_count": len(workspace_ids),
        "trigger_type": flow.trigger_type,
        "is_enabled": flow.is_enabled,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
    }


def _attach_flow_to_workspace(db: Session, workspace_uuid: uuid.UUID, flow_uuid: uuid.UUID) -> bool:
    existing = db.execute(
        select(WorkspaceFlowSQLModel).where(
            WorkspaceFlowSQLModel.workspace_id == workspace_uuid,
            WorkspaceFlowSQLModel.flow_id == flow_uuid,
        )
    ).scalars().first()
    if existing:
        return False
    db.add(WorkspaceFlowSQLModel(workspace_id=workspace_uuid, flow_id=flow_uuid))
    return True


def _waha_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = str(os.getenv("WAHA_API_KEY", "Yahoo") or "").strip()
    if api_key:
        headers["X-Api-Key"] = api_key
    return headers


def _waha_target() -> Dict[str, str]:
    return {
        "base_url": str(os.getenv("WAHA_URL", "http://waha:3000")).rstrip("/"),
        "session": str(os.getenv("WAHA_SESSION", "default") or "default").strip() or "default",
    }


def _waha_bootstrap_webhooks(session_name: str) -> List[Dict[str, Any]]:
    webhook_url = str(
        os.getenv("WAHA_WEBHOOK_URL", f"http://server:8000/whatsapp/webhook?waha_instance={session_name}")
    ).strip()
    if not webhook_url:
        return []
    return [{"url": webhook_url, "events": ["session.status", "message"]}]


def _waha_desired_start_payload(session_name: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": session_name,
        "config": {
            "noweb": {
                "store": {
                    "enabled": True,
                    "fullSync": True,
                }
            }
        },
    }
    webhooks = _waha_bootstrap_webhooks(session_name)
    if webhooks:
        payload["config"]["webhooks"] = webhooks
    return payload


def _ensure_waha_store_bootstrap() -> None:
    """
    Ensure WAHA default session is started with NOWEB store enabled.
    Safe behavior:
    - If session is missing or stopped -> start with required config.
    - If already running with wrong config -> warn only (no forced disconnect).
    """
    if str(os.getenv("WAHA_BOOTSTRAP_SESSION", "true")).strip().lower() not in {"1", "true", "yes", "on"}:
        return

    target = _waha_target()
    base_url = target["base_url"]
    session_name = target["session"]
    headers = _waha_headers()

    try:
        sessions_resp = requests.get(
            f"{base_url}/api/sessions",
            params={"all": "true"},
            headers=headers,
            timeout=20,
        )
        sessions_resp.raise_for_status()
        sessions = sessions_resp.json() if sessions_resp.content else []
    except Exception as exc:
        logger.warning("WAHA bootstrap skipped: unable to query sessions (%s)", exc)
        return

    existing = None
    if isinstance(sessions, list):
        existing = next((item for item in sessions if str(item.get("name") or "") == session_name), None)

    existing_config = existing.get("config") if isinstance(existing, dict) else None
    existing_noweb = (existing_config or {}).get("noweb") if isinstance(existing_config, dict) else {}
    existing_store = existing_noweb.get("store") if isinstance(existing_noweb, dict) else {}
    store_enabled = bool((existing_store or {}).get("enabled"))
    full_sync_enabled = bool((existing_store or {}).get("fullSync"))
    status = str((existing or {}).get("status") or "").strip().upper()

    if status in {"WORKING", "STARTING", "CONNECTING", "SCAN_QR_CODE"} and (not store_enabled or not full_sync_enabled):
        logger.warning(
            "WAHA session '%s' is active with store config disabled (enabled=%s fullSync=%s). "
            "Restart/recreate session to apply store settings.",
            session_name,
            store_enabled,
            full_sync_enabled,
        )
        return

    if status in {"WORKING", "STARTING", "CONNECTING", "SCAN_QR_CODE"}:
        return

    payload = _waha_desired_start_payload(session_name)
    try:
        start_resp = requests.post(
            f"{base_url}/api/sessions/start",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if start_resp.status_code not in {200, 201, 202}:
            logger.warning(
                "WAHA bootstrap start failed for session '%s': status=%s body=%s",
                session_name,
                start_resp.status_code,
                start_resp.text[:500],
            )
            return
        logger.info("WAHA bootstrap started session '%s' with NOWEB store enabled", session_name)
    except Exception as exc:
        logger.warning("WAHA bootstrap start error for session '%s': %s", session_name, exc)


@app.on_event("startup")
def startup_workspace_flow_schema() -> None:
    db = SessionLocal()
    try:
        ensure_workspace_flow_schema(db)
    except Exception as exc:
        print(f"⚠️ startup schema setup skipped: {exc}")
    finally:
        db.close()
    _ensure_waha_store_bootstrap()

# WebSocket handle karne wali class
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        print(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            print(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")

    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
                return True
            except Exception as e:
                print(f"Error sending message to {client_id}: {e}")
                self.disconnect(client_id)
                return False
        return False

manager = ConnectionManager()
from conversation_manager import conversation_manager


# Pydantic model for request body
class ChatRequest(BaseModel):
    query: str
    client_id: Optional[str] = None
    message_id: Optional[str] = None
    collection_name: Optional[str] = None


class RAGEvalCase(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    expected_contains: List[str] = Field(default_factory=list)


class RAGEvalRequest(BaseModel):
    collection_name: str = Field(min_length=1, max_length=255)
    cases: List[RAGEvalCase] = Field(default_factory=list)
    conversation_history: Optional[str] = ""
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    rag_options: Optional[Dict[str, Any]] = None


class ExecutionBulkDeleteRequest(BaseModel):
    execution_ids: List[str] = Field(default_factory=list)


class MemoryLTMUpdate(BaseModel):
    memory_key: str = Field(min_length=1, max_length=160)
    memory_text: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    memory_category: Optional[str] = Field(default=None, min_length=1, max_length=50)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None


@app.get("/")
def root():
    return {"message": "Bhai, server mast chal raha hai!"}


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """WhatsApp webhook fast-ack + async queue processing."""
    try:
        data = await request.json()
        waha_instance = (
            request.query_params.get("waha_instance")
            or request.query_params.get("instance")
            or data.get("session")
        )
        print(f"📩 Naya message aaya: {json.dumps(data, indent=2)}")
        
        # WAHA kabhi kabhi redundant events bhejta hai
        event_type = data.get("event")
        if event_type == "message.any":
            return {"status": "ignored", "reason": "redundant event type"}
            
        payload = data.get("payload", data)
        if "me" in data:
            payload["me"] = data["me"]
        payload["_waha"] = {
            "event": data.get("event"),
            "session": data.get("session"),
            "instance": waha_instance,
            "engine": data.get("engine"),
            "timestamp": data.get("timestamp"),
            "id": data.get("id"),
            "metadata": data.get("metadata", {}),
        }
        if "event" not in payload and data.get("event"):
            payload["event"] = data.get("event")
        if "chatId" not in payload:
            payload["chatId"] = payload.get("from")
        if "message_id" not in payload and payload.get("id"):
            payload["message_id"] = payload.get("id")
        # Memory ingestion is handled in worker webhook job so it can use canonical
        # contact identity mapping before writing STM/LTM keys.
        payload["_conversation_ingested"] = False

        # Full async: webhook just queues, worker does heavy processing.
        job_id = payload.get("message_id") or payload.get("id")
        resolved_job_id = _safe_webhook_job_id(job_id) if job_id else None
        try:
            if resolved_job_id:
                job = queue.enqueue(process_whatsapp_payload, payload, job_id=resolved_job_id)
            else:
                job = queue.enqueue(process_whatsapp_payload, payload)
        except Exception as enqueue_error:
            if resolved_job_id:
                existing_job = queue.fetch_job(resolved_job_id)
                if existing_job:
                    return {
                        "status": "queued",
                        "job_id": existing_job.id,
                        "duplicate": True,
                        "message_id": payload.get("message_id"),
                        "chat_id": payload.get("chatId") or payload.get("from"),
                    }
            raise enqueue_error

        return {
            "status": "queued",
            "job_id": job.id,
            "message_id": payload.get("message_id"),
            "chat_id": payload.get("chatId") or payload.get("from"),
        }
    except Exception as e:
        print(f"❌ Webhook process karne mein error aaya: {e}")
        return {"status": "error", "message": str(e)}



@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            # Keep connection alive and listen for any client messages
            await websocket.receive_text()
            await websocket.send_json({"type": "ack", "message": "Message received"})
    except WebSocketDisconnect:
        manager.disconnect(client_id)


@app.post("/chat")
def chat(
    request: ChatRequest = None,
    query: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    message_id: Optional[str] = Query(None),
    collection_name: Optional[str] = Query(None),
):
    # Support both JSON body and query parameters
    if request:
        query = request.query
        client_id = request.client_id
        message_id = request.message_id
        collection_name = request.collection_name
    
    if not query:
        return {"error": "query parameter is required"}, 422

    resolved_collection_name = (collection_name or os.getenv("DEFAULT_QDRANT_COLLECTION", "").strip() or "").strip()
    if not resolved_collection_name:
        return {
            "error": "collection_name is required when DEFAULT_QDRANT_COLLECTION is not configured"
        }, 422
    
    
    # Store user's message in conversation history
    if client_id:
        conversation_manager.add_message(client_id, "user", query)
        
        # Build query-aware context: recent turns + summary + relevant past turns + LTM.
        context_limit = max(6, int(os.getenv("CHAT_CONTEXT_TURN_LIMIT", "24")))
        context_token_budget = max(250, int(os.getenv("STM_CONTEXT_TOKEN_BUDGET", "1200")))
        conversation_history = conversation_manager.get_context_string(
            client_id,
            limit=context_limit,
            query=query,
            token_budget=context_token_budget,
        )
    else:
        conversation_history = ""
    
    # Enqueue with keyword arguments to avoid positional-argument drift bugs.
    job = queue.enqueue(
        process_query,
        query=query,
        client_id=client_id,
        conversation_history=conversation_history,
        whatsapp_message_id=message_id,
        collection_name=resolved_collection_name,
    )
    return {
        "status": "queued",
        "job_id": job.id,
        "client_id": client_id,
        "message_id": message_id,
        "collection_name": resolved_collection_name,
    }


@app.get("/job-status")
def get_result(
        job_id: str = Query(..., description="JOB_ID")
):
    job = queue.fetch_job(job_id=job_id)
    result = job.return_value()
    return {"result": result}


@app.post("/internal/notify")
async def notify_client(payload: dict):
    """Internal endpoint for worker to send WebSocket notifications"""
    client_id = payload.get("client_id")
    result = payload.get("result")
    
    if client_id and result:
        # Store assistant's response in conversation history
        conversation_manager.add_message(client_id, "assistant", result)
        
        success = await manager.send_message(client_id, {
            "type": "result",
            "data": result
        })
        return {"status": "sent" if success else "failed", "client_id": client_id}
    
    return {"status": "error", "message": "Missing client_id or result"}


@app.get("/conversation/{client_id}")
def get_conversation(client_id: str):
    """Get conversation history for a client"""
    history = conversation_manager.get_history(client_id)
    return {"client_id": client_id, "history": history, "message_count": len(history)}


@app.delete("/conversation/{client_id}")
def clear_conversation(client_id: str):
    """Clear conversation history for a client"""
    conversation_manager.clear_history(client_id)
    return {"status": "cleared", "client_id": client_id}


def get_memory_debug_snapshot(
    client_id: str,
    query: Optional[str] = Query(default=""),
    history_limit: int = Query(default=24, ge=1, le=200),
    token_budget: int = Query(default=1200, ge=120, le=8000),
    ltm_limit: int = Query(default=50, ge=1, le=400),
    include_inactive: bool = Query(default=False),
    workspace_id: Optional[str] = Query(default=None),
    memory_scope: Optional[str] = Query(default=None),
):
    snapshot = conversation_manager.get_memory_debug_snapshot(
        client_id=client_id,
        query=query or "",
        history_limit=history_limit,
        token_budget=token_budget,
        ltm_limit=ltm_limit,
        include_inactive=include_inactive,
        workspace_id=workspace_id,
        memory_scope=memory_scope,
    )
    return {"status": "success", **snapshot}


def upsert_memory_ltm(
    client_id: str,
    payload: MemoryLTMUpdate,
    workspace_id: Optional[str] = Query(default=None),
    memory_scope: Optional[str] = Query(default=None),
):
    memory_key = str(payload.memory_key or "").strip()
    if not memory_key:
        raise HTTPException(status_code=422, detail="memory_key is required")

    existing_items = conversation_manager.list_long_term_memories(
        client_id=client_id,
        include_inactive=True,
        limit=1000,
        workspace_id=workspace_id,
        memory_scope=memory_scope,
    )
    existing_by_key = {str(item.get("memory_key") or ""): item for item in existing_items}
    existing = existing_by_key.get(memory_key)

    effective_text = str(payload.memory_text or "").strip()
    if not effective_text:
        if not existing:
            raise HTTPException(status_code=404, detail=f"memory_key not found: {memory_key}")
        effective_text = str(existing.get("memory_text") or "").strip()
        if not effective_text:
            raise HTTPException(status_code=422, detail="memory_text is required for new memory item")

    effective_category = payload.memory_category
    if effective_category is None and existing:
        effective_category = str(existing.get("memory_category") or "general")

    effective_confidence = payload.confidence
    if effective_confidence is None and existing and existing.get("confidence") is not None:
        effective_confidence = float(existing.get("confidence"))

    updated_item = conversation_manager.upsert_long_term_memory(
        client_id=client_id,
        memory_key=memory_key,
        memory_text=effective_text,
        memory_category=effective_category,
        confidence=effective_confidence,
        is_active=payload.is_active,
        workspace_id=workspace_id,
        memory_scope=memory_scope,
    )
    return {
        "status": "success",
        "client_id": client_id,
        "workspace_id": workspace_id,
        "memory_scope": memory_scope or conversation_manager.get_default_memory_scope(),
        "item": updated_item,
    }


def deactivate_memory_ltm(
    client_id: str,
    memory_key: str = Query(..., min_length=1, max_length=160),
    workspace_id: Optional[str] = Query(default=None),
    memory_scope: Optional[str] = Query(default=None),
):
    success = conversation_manager.deactivate_long_term_memory(
        client_id=client_id,
        memory_key=memory_key,
        workspace_id=workspace_id,
        memory_scope=memory_scope,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Active memory not found: {memory_key}")
    return {
        "status": "success",
        "client_id": client_id,
        "memory_key": memory_key,
        "message": "Memory deactivated",
    }


def clear_memory_for_client(
    client_id: str,
    workspace_id: Optional[str] = Query(default=None),
    memory_scope: Optional[str] = Query(default=None),
):
    conversation_manager.clear_history(
        client_id,
        workspace_id=workspace_id,
        memory_scope=memory_scope,
    )
    return {
        "status": "success",
        "client_id": client_id,
        "workspace_id": workspace_id,
        "memory_scope": memory_scope or conversation_manager.get_default_memory_scope(),
        "message": "Conversation history and long-term memory cleared",
    }


def evaluate_rag_quality(payload: RAGEvalRequest, db: Session = Depends(get_db_session)):
    """Run a lightweight grounded-RAG evaluation set and return aggregated metrics."""
    collection_name = (payload.collection_name or "").strip()
    if not collection_name:
        raise HTTPException(status_code=422, detail="`collection_name` is required")
    if not payload.cases:
        raise HTTPException(status_code=422, detail="`cases` must contain at least one question")

    available = set(list_qdrant_collections())
    if collection_name not in available:
        raise HTTPException(status_code=404, detail=f"Collection not found: {collection_name}")

    case_results: List[Dict[str, Any]] = []
    fallback_count = 0
    citation_ok_count = 0
    grounded_pass_count = 0
    expectation_hit_count = 0
    total_latency_ms = 0.0

    for idx, case in enumerate(payload.cases, start=1):
        started = time.perf_counter()
        debug_result = process_query(
            query=case.question,
            client_id=None,
            conversation_history=payload.conversation_history or "",
            whatsapp_message_id=None,
            collection_name=collection_name,
            system_prompt=payload.system_prompt,
            user_prompt_template=payload.user_prompt_template,
            emit_side_effects=False,
            return_debug=True,
            rag_options=payload.rag_options or {},
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        total_latency_ms += latency_ms

        answer = str(debug_result.get("answer") or "")
        fallback_used = bool(debug_result.get("fallback_used"))
        citation_ok = bool(debug_result.get("citation_ok"))
        grounded_pass = bool((debug_result.get("grounding") or {}).get("passed"))

        if fallback_used:
            fallback_count += 1
        if citation_ok:
            citation_ok_count += 1
        if grounded_pass:
            grounded_pass_count += 1

        expected_contains = [item.strip() for item in (case.expected_contains or []) if item and item.strip()]
        expectation_hit = True
        answer_lower = answer.lower()
        for expected_fragment in expected_contains:
            if expected_fragment.lower() not in answer_lower:
                expectation_hit = False
                break
        if expectation_hit:
            expectation_hit_count += 1

        case_results.append(
            {
                "index": idx,
                "question": case.question,
                "answer": answer,
                "expected_contains": expected_contains,
                "expectation_hit": expectation_hit,
                "fallback_used": fallback_used,
                "citation_ok": citation_ok,
                "grounding": debug_result.get("grounding") or {},
                "latency_ms": latency_ms,
                "retrieved_chunks": debug_result.get("retrieved_chunks") or [],
            }
        )

    total_cases = len(payload.cases)
    avg_latency_ms = round(total_latency_ms / max(1, total_cases), 2)

    summary = {
        "total_cases": total_cases,
        "fallback_rate": round(fallback_count / total_cases, 4),
        "citation_ok_rate": round(citation_ok_count / total_cases, 4),
        "grounding_pass_rate": round(grounded_pass_count / total_cases, 4),
        "expectation_hit_rate": round(expectation_hit_count / total_cases, 4),
        "avg_latency_ms": avg_latency_ms,
    }

    kb = db.execute(
        select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == collection_name)
    ).scalars().first()
    scorecard = RAGEvalScorecardSQLModel(
        collection_name=collection_name,
        knowledge_base_id=kb.id if kb else None,
        total_cases=summary["total_cases"],
        fallback_rate=summary["fallback_rate"],
        citation_ok_rate=summary["citation_ok_rate"],
        grounding_pass_rate=summary["grounding_pass_rate"],
        expectation_hit_rate=summary["expectation_hit_rate"],
        avg_latency_ms=summary["avg_latency_ms"],
        rag_options=payload.rag_options or {},
    )
    db.add(scorecard)
    db.flush()

    for case_result in case_results:
        db.add(
            RAGEvalCaseResultSQLModel(
                scorecard_id=scorecard.id,
                case_index=case_result["index"],
                question=case_result["question"],
                answer=case_result["answer"],
                expected_contains=case_result["expected_contains"],
                expectation_hit=bool(case_result["expectation_hit"]),
                fallback_used=bool(case_result["fallback_used"]),
                citation_ok=bool(case_result["citation_ok"]),
                grounding=case_result.get("grounding") or {},
                latency_ms=float(case_result["latency_ms"]),
                retrieved_chunks=case_result.get("retrieved_chunks") or [],
            )
        )
    db.commit()

    return {
        "status": "success",
        "collection_name": collection_name,
        "scorecard_id": str(scorecard.id),
        "summary": summary,
        "results": case_results,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def list_rag_scorecards(
    collection_name: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db_session),
):
    query = select(RAGEvalScorecardSQLModel).order_by(RAGEvalScorecardSQLModel.created_at.desc())
    if collection_name:
        query = query.where(RAGEvalScorecardSQLModel.collection_name == collection_name.strip())
    scorecards = db.execute(query.limit(limit)).scalars().all()
    return {
        "status": "success",
        "count": len(scorecards),
        "scorecards": [
            {
                "id": str(card.id),
                "collection_name": card.collection_name,
                "knowledge_base_id": str(card.knowledge_base_id) if card.knowledge_base_id else None,
                "total_cases": card.total_cases,
                "fallback_rate": card.fallback_rate,
                "citation_ok_rate": card.citation_ok_rate,
                "grounding_pass_rate": card.grounding_pass_rate,
                "expectation_hit_rate": card.expectation_hit_rate,
                "avg_latency_ms": card.avg_latency_ms,
                "rag_options": card.rag_options or {},
                "created_at": card.created_at.isoformat() if card.created_at else None,
            }
            for card in scorecards
        ],
    }


def get_rag_scorecard(scorecard_id: str, db: Session = Depends(get_db_session)):
    try:
        scorecard_uuid = uuid.UUID(scorecard_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scorecard id")

    scorecard = db.execute(
        select(RAGEvalScorecardSQLModel).where(RAGEvalScorecardSQLModel.id == scorecard_uuid)
    ).scalars().first()
    if not scorecard:
        raise HTTPException(status_code=404, detail="Scorecard not found")

    cases = db.execute(
        select(RAGEvalCaseResultSQLModel)
        .where(RAGEvalCaseResultSQLModel.scorecard_id == scorecard.id)
        .order_by(RAGEvalCaseResultSQLModel.case_index.asc())
    ).scalars().all()

    return {
        "status": "success",
        "scorecard": {
            "id": str(scorecard.id),
            "collection_name": scorecard.collection_name,
            "knowledge_base_id": str(scorecard.knowledge_base_id) if scorecard.knowledge_base_id else None,
            "total_cases": scorecard.total_cases,
            "fallback_rate": scorecard.fallback_rate,
            "citation_ok_rate": scorecard.citation_ok_rate,
            "grounding_pass_rate": scorecard.grounding_pass_rate,
            "expectation_hit_rate": scorecard.expectation_hit_rate,
            "avg_latency_ms": scorecard.avg_latency_ms,
            "rag_options": scorecard.rag_options or {},
            "created_at": scorecard.created_at.isoformat() if scorecard.created_at else None,
        },
        "cases": [
            {
                "id": str(case.id),
                "index": case.case_index,
                "question": case.question,
                "answer": case.answer,
                "expected_contains": case.expected_contains or [],
                "expectation_hit": case.expectation_hit,
                "fallback_used": case.fallback_used,
                "citation_ok": case.citation_ok,
                "grounding": case.grounding or {},
                "latency_ms": case.latency_ms,
                "retrieved_chunks": case.retrieved_chunks or [],
                "created_at": case.created_at.isoformat() if case.created_at else None,
            }
            for case in cases
        ],
    }


class WorkerScaleUpdate(BaseModel):
    desired_count: int


def _clamp_worker_count(raw_value: int) -> int:
    return min(RQ_WORKER_MAX_COUNT, max(RQ_WORKER_MIN_COUNT, int(raw_value)))


def _safe_webhook_job_id(message_id: str) -> str:
    digest = hashlib.sha1(str(message_id).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"webhook_{digest}"


_CONTACT_FILTER_MODES = {"all", "only", "except"}


def _normalize_contact_chat_id(value: Any) -> str:
    return normalize_contact_chat_id(value)


def _extract_phone_number(chat_id: str) -> str:
    base = str(chat_id or "").split("@", 1)[0]
    digits = re.sub(r"\D", "", base)
    return digits


def _resolve_contact_filter_mode(raw_mode: Any) -> str:
    normalized = str(raw_mode or "all").strip().lower()
    if normalized not in _CONTACT_FILTER_MODES:
        raise HTTPException(status_code=422, detail="contact_filter_mode must be one of: all, only, except")
    return normalized


def _upsert_contact_by_chat_id(
    db: Session,
    chat_id: str,
    display_name: Optional[str] = None,
    source: str = "manual",
    waha_contact_id: Optional[str] = None,
    lid: Optional[str] = None,
    phone_jid: Optional[str] = None,
) -> Optional[WhatsAppContactSQLModel]:
    normalized_chat_id = _normalize_contact_chat_id(chat_id)
    normalized_waha_contact_id = _normalize_contact_chat_id(waha_contact_id) or None
    normalized_lid = _normalize_contact_chat_id(lid) or None
    normalized_phone_jid = _normalize_contact_chat_id(phone_jid) or None

    if not normalized_chat_id:
        normalized_chat_id = normalized_lid or normalized_phone_jid or normalized_waha_contact_id
    if not normalized_chat_id or "@g.us" in normalized_chat_id:
        return None

    lookup_conditions = [WhatsAppContactSQLModel.chat_id == normalized_chat_id]
    # If caller provides only one id format (manual add by lid/phone/c.us),
    # still match existing rows that stored that value in mapped columns.
    if normalized_chat_id.endswith("@lid"):
        lookup_conditions.append(WhatsAppContactSQLModel.lid == normalized_chat_id)
    if normalized_chat_id.endswith("@s.whatsapp.net"):
        lookup_conditions.append(WhatsAppContactSQLModel.phone_jid == normalized_chat_id)
    if normalized_chat_id.endswith("@c.us"):
        lookup_conditions.append(WhatsAppContactSQLModel.waha_contact_id == normalized_chat_id)

    if normalized_waha_contact_id:
        lookup_conditions.append(WhatsAppContactSQLModel.chat_id == normalized_waha_contact_id)
    if normalized_lid:
        lookup_conditions.append(WhatsAppContactSQLModel.chat_id == normalized_lid)
    if normalized_phone_jid:
        lookup_conditions.append(WhatsAppContactSQLModel.chat_id == normalized_phone_jid)
    if normalized_waha_contact_id:
        lookup_conditions.append(WhatsAppContactSQLModel.waha_contact_id == normalized_waha_contact_id)
    if normalized_lid:
        lookup_conditions.append(WhatsAppContactSQLModel.lid == normalized_lid)
    if normalized_phone_jid:
        lookup_conditions.append(WhatsAppContactSQLModel.phone_jid == normalized_phone_jid)

    now = datetime.now()
    display_value = str(display_name or "").strip() or None
    phone_base = normalized_phone_jid or normalized_chat_id
    phone_value = _extract_phone_number(phone_base) or None
    if phone_value and len(phone_value) >= 8:
        lookup_conditions.append(WhatsAppContactSQLModel.phone_number == phone_value)
    contact = db.execute(
        select(WhatsAppContactSQLModel).where(or_(*lookup_conditions))
    ).scalars().first()

    if contact:
        if display_value and (not contact.display_name or str(contact.display_name).strip().isdigit()):
            contact.display_name = display_value
        contact.phone_number = phone_value or contact.phone_number
        contact.waha_contact_id = normalized_waha_contact_id or (str(contact.waha_contact_id or "").strip() or None)
        contact.lid = normalized_lid or (str(contact.lid or "").strip() or None)
        contact.phone_jid = normalized_phone_jid or (str(contact.phone_jid or "").strip() or None)
        contact.source = source or contact.source
        contact.last_seen_at = now
        contact.is_active = True
        return contact

    canonical_chat_id = normalized_lid or normalized_phone_jid or normalized_waha_contact_id or normalized_chat_id
    contact = WhatsAppContactSQLModel(
        chat_id=canonical_chat_id,
        display_name=display_value,
        phone_number=phone_value,
        waha_contact_id=normalized_waha_contact_id,
        lid=normalized_lid,
        phone_jid=normalized_phone_jid,
        source=source,
        is_active=True,
        last_seen_at=now,
    )
    db.add(contact)
    db.flush()
    return contact


def _serialize_contact_ref(contact: WhatsAppContactSQLModel) -> Dict[str, Any]:
    return {
        "id": str(contact.id),
        "chat_id": contact.chat_id,
        "display_name": contact.display_name,
        "phone_number": contact.phone_number,
        "waha_contact_id": contact.waha_contact_id,
        "lid": contact.lid,
        "phone_jid": contact.phone_jid,
        "source": contact.source,
        "is_active": bool(contact.is_active),
        "last_seen_at": contact.last_seen_at.isoformat() if contact.last_seen_at else None,
    }


def _cleanup_stale_flow_executions(db: Session, stale_before: datetime) -> int:
    """Mark crashed/stale running executions as failed so dashboard counters stay accurate."""
    stale_executions = db.execute(
        select(FlowExecutionSQLModel).where(
            FlowExecutionSQLModel.status == "running",
            FlowExecutionSQLModel.started_at < stale_before,
        )
    ).scalars().all()

    if not stale_executions:
        return 0

    now_utc = datetime.utcnow()
    for execution in stale_executions:
        execution.status = "failed"
        execution.completed_at = now_utc
        if execution.started_at:
            execution.duration_ms = max(0, int((now_utc - execution.started_at).total_seconds() * 1000))
        if not execution.error_message:
            execution.error_message = "Execution marked failed by stale-run cleanup after worker interruption."

    db.commit()
    logger.warning("Auto-cleaned %s stale flow executions", len(stale_executions))
    return len(stale_executions)


def _worker_runtime_status() -> Dict[str, Any]:
    connection = queue.connection
    desired_raw = connection.get(RQ_WORKER_DESIRED_KEY)
    try:
        if desired_raw is None:
            desired_count = RQ_WORKER_DEFAULT_COUNT
        else:
            desired_text = desired_raw.decode("utf-8", errors="ignore") if isinstance(desired_raw, (bytes, bytearray)) else str(desired_raw)
            desired_count = _clamp_worker_count(int(desired_text.strip()))
    except Exception:
        desired_count = RQ_WORKER_DEFAULT_COUNT

    workers = Worker.all(connection=connection)
    worker_items = []
    scheduler_count = 0
    now_utc = datetime.utcnow()
    for worker in workers:
        worker_name = str(worker.name)
        queue_names = [str(name) for name in worker.queue_names()]
        state = str(worker.get_state() or "unknown")
        last_heartbeat = worker.last_heartbeat
        heartbeat_age_seconds = None
        if last_heartbeat:
            heartbeat_dt = last_heartbeat.replace(tzinfo=None) if last_heartbeat.tzinfo else last_heartbeat
            heartbeat_age_seconds = max(0, int((now_utc - heartbeat_dt).total_seconds()))

        if state in {"?", "unknown"} and not queue_names and (heartbeat_age_seconds is None or heartbeat_age_seconds > 120):
            continue

        is_scheduler = "scheduler" in worker_name.lower()
        if is_scheduler:
            scheduler_count += 1
        worker_items.append(
            {
                "name": worker_name,
                "state": state,
                "queues": queue_names,
                "current_job_id": str(worker.get_current_job_id() or ""),
                "heartbeat_age_seconds": heartbeat_age_seconds,
                "is_scheduler": is_scheduler,
            }
        )

    manager_heartbeat_raw = connection.get(RQ_WORKER_MANAGER_HEARTBEAT_KEY)
    manager_heartbeat = None
    if manager_heartbeat_raw:
        try:
            manager_heartbeat = json.loads(manager_heartbeat_raw)
        except Exception:
            manager_heartbeat = {"raw": manager_heartbeat_raw}

    queued_count = queue.count
    processing_count = StartedJobRegistry(queue=queue).count
    scheduled_count = ScheduledJobRegistry(queue=queue).count
    deferred_count = DeferredJobRegistry(queue=queue).count
    failed_count = FailedJobRegistry(queue=queue).count
    finished_count = FinishedJobRegistry(queue=queue).count

    flow_window_minutes = max(1, int(os.getenv("FLOW_RUNTIME_WINDOW_MINUTES", "15")))
    flow_running_stale_minutes = max(1, int(os.getenv("FLOW_RUNNING_STALE_MINUTES", "5")))
    flow_recent_total = 0
    flow_recent_completed = 0
    flow_recent_failed = 0
    flow_running_now = 0
    flow_stale_cleaned = 0
    flow_metrics_error = None
    now_utc = datetime.utcnow()
    window_start = now_utc - timedelta(minutes=flow_window_minutes)
    running_cutoff = now_utc - timedelta(minutes=flow_running_stale_minutes)

    db = SessionLocal()
    try:
        flow_stale_cleaned = _cleanup_stale_flow_executions(db, running_cutoff)
        flow_recent_total = db.execute(
            select(func.count()).select_from(FlowExecutionSQLModel).where(
                FlowExecutionSQLModel.started_at >= window_start
            )
        ).scalar() or 0
        flow_recent_completed = db.execute(
            select(func.count()).select_from(FlowExecutionSQLModel).where(
                FlowExecutionSQLModel.started_at >= window_start,
                FlowExecutionSQLModel.status == "completed",
            )
        ).scalar() or 0
        flow_recent_failed = db.execute(
            select(func.count()).select_from(FlowExecutionSQLModel).where(
                FlowExecutionSQLModel.started_at >= window_start,
                FlowExecutionSQLModel.status == "failed",
            )
        ).scalar() or 0
        flow_running_now = db.execute(
            select(func.count()).select_from(FlowExecutionSQLModel).where(
                FlowExecutionSQLModel.status == "running",
                FlowExecutionSQLModel.started_at >= running_cutoff,
            )
        ).scalar() or 0
    except Exception as metric_error:
        flow_metrics_error = str(metric_error)
    finally:
        db.close()

    return {
        "desired_count": desired_count,
        "active_count": len(worker_items),
        "scheduler_count": scheduler_count,
        "queued_count": queued_count,
        "processing_count": processing_count,
        "scheduled_count": scheduled_count,
        "deferred_count": deferred_count,
        "failed_count": failed_count,
        "finished_count": finished_count,
        "default_queue_depth": queued_count,  # legacy alias for older frontend builds
        "workers": worker_items,
        "manager_heartbeat": manager_heartbeat,
        "flow_runtime": {
            "window_minutes": flow_window_minutes,
            "recent_total": flow_recent_total,
            "recent_completed": flow_recent_completed,
            "recent_failed": flow_recent_failed,
            "running_now": flow_running_now,
            "stale_cleaned": flow_stale_cleaned,
            "error": flow_metrics_error,
        },
        "limits": {
            "min": RQ_WORKER_MIN_COUNT,
            "max": RQ_WORKER_MAX_COUNT,
            "default": RQ_WORKER_DEFAULT_COUNT,
        },
    }


@app.get("/api/workers/status")
def get_worker_status():
    """RQ worker pool status for dashboard/runtime control."""
    try:
        return {"status": "success", **_worker_runtime_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker status unavailable: {e}")


@app.patch("/api/workers/scale")
def set_worker_scale(data: WorkerScaleUpdate):
    """Set desired worker count; worker pool manager reconciles asynchronously."""
    try:
        desired_count = _clamp_worker_count(data.desired_count)
        queue.connection.set(RQ_WORKER_DESIRED_KEY, str(desired_count))
        runtime = _worker_runtime_status()
        return {
            "status": "success",
            "message": "Worker scale updated",
            **runtime,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker scale update failed: {e}")


# ============================================================================
# KNOWLEDGE BASE: Jahan saara gyan save hota hai
# ============================================================================

class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RetrievalProfileUpdate(BaseModel):
    final_context_k: Optional[int] = Field(default=None, ge=2, le=32)
    retrieval_candidates: Optional[int] = Field(default=None, ge=4, le=128)
    grounding_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    require_citations: Optional[bool] = None
    min_context_chars: Optional[int] = Field(default=None, ge=40, le=20000)
    query_variants_limit: Optional[int] = Field(default=None, ge=1, le=8)
    clarification_enabled: Optional[bool] = None
    clarification_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    chunk_size: Optional[int] = Field(default=None, ge=200, le=8000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=2000)


def _serialize_retrieval_profile(profile: Optional[KnowledgeBaseRetrievalProfileSQLModel]) -> Dict[str, Any]:
    if profile is None:
        return {
            "final_context_k": None,
            "retrieval_candidates": None,
            "grounding_threshold": None,
            "require_citations": None,
            "min_context_chars": None,
            "query_variants_limit": None,
            "clarification_enabled": None,
            "clarification_threshold": None,
            "chunk_size": None,
            "chunk_overlap": None,
            "updated_at": None,
        }
    return {
        "final_context_k": profile.final_context_k,
        "retrieval_candidates": profile.retrieval_candidates,
        "grounding_threshold": profile.grounding_threshold,
        "require_citations": profile.require_citations,
        "min_context_chars": profile.min_context_chars,
        "query_variants_limit": profile.query_variants_limit,
        "clarification_enabled": profile.clarification_enabled,
        "clarification_threshold": profile.clarification_threshold,
        "chunk_size": profile.chunk_size,
        "chunk_overlap": profile.chunk_overlap,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }

@app.get("/api/collections")
def get_collections(db: Session = Depends(get_db_session)):
    """Saari knowledge collections ki list"""
    collections = db.execute(select(KnowledgeBaseSQLModel)).scalars().all()
    profiles = db.execute(select(KnowledgeBaseRetrievalProfileSQLModel)).scalars().all()
    profile_by_kb_id = {profile.knowledge_base_id: profile for profile in profiles}
    return {"collections": [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "created_at": c.created_at.isoformat(),
            "retrieval_profile": _serialize_retrieval_profile(profile_by_kb_id.get(c.id)),
        } for c in collections
    ]}

@app.post("/api/collections")
def create_new_collection(data: CollectionCreate, db: Session = Depends(get_db_session)):
    """Nayi collection banate hain (DB aur Qdrant dono mein)"""
    existing = db.execute(
        select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == data.name)
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Bhai, ye collection toh pehle se hai!")
    
    kb = KnowledgeBaseSQLModel(name=data.name, description=data.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)

    existing_profile = db.execute(
        select(KnowledgeBaseRetrievalProfileSQLModel).where(
            KnowledgeBaseRetrievalProfileSQLModel.knowledge_base_id == kb.id
        )
    ).scalars().first()
    if not existing_profile:
        db.add(
            KnowledgeBaseRetrievalProfileSQLModel(
                knowledge_base_id=kb.id,
                clarification_enabled=True,
            )
        )
        db.commit()
    
    try:
        create_qdrant_collection(data.name)
    except Exception as e:
        print(f"⚠️ Qdrant mein warning: {e}")
    
    return kb

@app.post("/api/collections/sync")
def sync_collections_with_qdrant(db: Session = Depends(get_db_session)):
    """Sync collections from Qdrant to local DB (add missing, remove stale)."""
    try:
        qdrant_names = list_qdrant_collections()
        qdrant_name_set = set(qdrant_names)
        db_collections = db.execute(select(KnowledgeBaseSQLModel)).scalars().all()
        db_names = {c.name for c in db_collections}
        
        added_count = 0
        for name in qdrant_names:
            if name not in db_names:
                new_kb = KnowledgeBaseSQLModel(name=name, description="Imported from Qdrant")
                db.add(new_kb)
                db.flush()
                db.add(
                    KnowledgeBaseRetrievalProfileSQLModel(
                        knowledge_base_id=new_kb.id,
                        clarification_enabled=True,
                    )
                )
                added_count += 1

        removed_count = 0
        removed_names: List[str] = []
        for collection in db_collections:
            if collection.name in qdrant_name_set:
                continue
            db.delete(collection)
            removed_count += 1
            removed_names.append(collection.name)
        
        db.commit()
        return {
            "status": "success",
            "added_count": added_count,
            "removed_count": removed_count,
            "removed_names": removed_names,
            "total_found": len(qdrant_names),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@app.get("/api/collections/{kb_name}/retrieval-profile")
def get_collection_retrieval_profile(kb_name: str, db: Session = Depends(get_db_session)):
    kb = db.execute(
        select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == kb_name)
    ).scalars().first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")

    profile = db.execute(
        select(KnowledgeBaseRetrievalProfileSQLModel).where(
            KnowledgeBaseRetrievalProfileSQLModel.knowledge_base_id == kb.id
        )
    ).scalars().first()
    return {
        "status": "success",
        "knowledge_base": {"id": str(kb.id), "name": kb.name},
        "profile": _serialize_retrieval_profile(profile),
        "defaults": {
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
        },
    }


@app.put("/api/collections/{kb_name}/retrieval-profile")
def upsert_collection_retrieval_profile(
    kb_name: str,
    payload: RetrievalProfileUpdate,
    db: Session = Depends(get_db_session),
):
    kb = db.execute(
        select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == kb_name)
    ).scalars().first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")

    profile = db.execute(
        select(KnowledgeBaseRetrievalProfileSQLModel).where(
            KnowledgeBaseRetrievalProfileSQLModel.knowledge_base_id == kb.id
        )
    ).scalars().first()
    if not profile:
        profile = KnowledgeBaseRetrievalProfileSQLModel(
            knowledge_base_id=kb.id,
            clarification_enabled=True,
        )
        db.add(profile)
        db.flush()

    updates = _model_dump(payload)
    for key, value in updates.items():
        setattr(profile, key, value)

    if profile.chunk_size is not None and profile.chunk_overlap is not None and profile.chunk_overlap >= profile.chunk_size:
        raise HTTPException(status_code=422, detail="chunk_overlap must be less than chunk_size")

    db.commit()
    db.refresh(profile)
    return {
        "status": "success",
        "knowledge_base": {"id": str(kb.id), "name": kb.name},
        "profile": _serialize_retrieval_profile(profile),
    }


def _resolve_index_chunk_settings(
    *,
    profile: Optional[KnowledgeBaseRetrievalProfileSQLModel],
    chunk_size: Optional[int],
    chunk_overlap: Optional[int],
) -> tuple[int, int]:
    resolved_chunk_size = int(chunk_size) if chunk_size is not None else int(
        profile.chunk_size if profile and profile.chunk_size else DEFAULT_CHUNK_SIZE
    )
    resolved_chunk_overlap = int(chunk_overlap) if chunk_overlap is not None else int(
        profile.chunk_overlap if profile and profile.chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
    )
    if resolved_chunk_overlap >= resolved_chunk_size:
        resolved_chunk_overlap = max(0, resolved_chunk_size - 1)
    return resolved_chunk_size, resolved_chunk_overlap


def _collect_upload_sources(
    *,
    temp_dir: str,
    files: Optional[List[UploadFile]],
    urls: Optional[List[str]],
) -> tuple[List[str], List[str]]:
    file_paths: List[str] = []
    normalized_urls: List[str] = []
    seen_file_names: set[str] = set()

    for file in files or []:
        file_name = str(file.filename or "").strip()
        if not file_name.lower().endswith(".pdf"):
            continue
        safe_name = os.path.basename(file_name) or f"upload-{len(file_paths)+1}.pdf"
        if safe_name in seen_file_names:
            stem, ext = os.path.splitext(safe_name)
            safe_name = f"{stem}-{uuid.uuid4().hex[:6]}{ext or '.pdf'}"
        seen_file_names.add(safe_name)
        file_path = os.path.join(temp_dir, safe_name)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_paths.append(file_path)

    for raw in urls or []:
        for candidate in str(raw or "").replace(",", "\n").splitlines():
            clean = candidate.strip()
            if clean and clean not in normalized_urls:
                normalized_urls.append(clean)

    return file_paths, normalized_urls


def _source_progress_fraction(source: str, event: str, payload: Dict[str, Any]) -> float:
    if event in {"embedding_upload_done", "no_chunks", "no_documents"}:
        return 1.0
    if event == "chunking_done":
        return 0.64
    if event == "chunking_start":
        return 0.48
    if event == "embedding_prepare_done":
        return 0.46
    if event == "embedding_prepare_start":
        return 0.44
    if event == "embedding_upload_start":
        return 0.68
    if event == "embedding_upload_batch_done":
        total_batches = max(1, int(payload.get("total_batches") or 1))
        batch_index = max(0, min(total_batches, int(payload.get("batch_index") or 0)))
        return min(0.995, 0.68 + (batch_index / total_batches) * 0.31)

    if source == "pdf":
        if event == "pdf_loading_start":
            return 0.04
        if event in {"pdf_file_start", "pdf_file_done"}:
            total = max(1, int(payload.get("total") or payload.get("total_files") or 1))
            index = max(0, min(total, int(payload.get("index") or 0)))
            ratio = index / total
            return 0.08 + ratio * 0.30
        if event == "pdf_loading_done":
            return 0.40
    if source == "url":
        if event == "url_crawl_start":
            return 0.04
        if event == "url_fallback_start":
            return 0.36
        if event == "url_fallback_done":
            return 0.39
        if event in {"url_item_start", "url_item_done", "url_item_failed", "url_item_heartbeat"}:
            total = max(1, int(payload.get("total") or payload.get("total_urls") or 1))
            index = max(1, min(total, int(payload.get("index") or 1)))
            base_units = float(index - 1)
            if event == "url_item_done" or event == "url_item_failed":
                unit_ratio = (base_units + 1.0) / total
            elif event == "url_item_heartbeat":
                timeout_seconds = max(1, int(payload.get("timeout_seconds") or 1))
                elapsed_seconds = max(0, min(timeout_seconds, int(payload.get("elapsed_seconds") or 0)))
                crawl_progress = min(0.98, elapsed_seconds / timeout_seconds)
                unit_ratio = (base_units + crawl_progress) / total
            else:
                unit_ratio = base_units / total
            ratio = max(0.0, min(1.0, unit_ratio))
            return 0.08 + ratio * 0.30
        if event == "url_crawl_done":
            return 0.40
    return 0.08


def _source_progress_message(source: str, event: str, payload: Dict[str, Any]) -> str:
    if source == "pdf":
        if event == "pdf_loading_start":
            return "Reading PDF files..."
        if event in {"pdf_file_start", "pdf_file_done"}:
            index = int(payload.get("index") or 0)
            total = int(payload.get("total") or payload.get("total_files") or 0)
            return f"Processing PDF {index}/{total}..."
    if source == "url":
        if event == "url_crawl_start":
            return "Crawling website URLs..."
        if event == "url_fallback_start":
            return "Crawler slow. Switching to direct fetch fallback..."
        if event == "url_fallback_done":
            return "Fallback extraction complete. Chunking content..."
        if event == "url_item_start":
            index = int(payload.get("index") or 0)
            total = int(payload.get("total") or payload.get("total_urls") or 0)
            return f"Crawling URL {index}/{total}..."
        if event == "url_item_heartbeat":
            index = int(payload.get("index") or 0)
            total = int(payload.get("total") or payload.get("total_urls") or 0)
            elapsed = int(payload.get("elapsed_seconds") or 0)
            timeout_seconds = int(payload.get("timeout_seconds") or 0)
            if timeout_seconds > 0:
                return f"Crawling URL {index}/{total}... {elapsed}s/{timeout_seconds}s"
            return f"Crawling URL {index}/{total}..."
        if event == "url_item_failed":
            return "Some URLs could not be crawled. Continuing..."
        if event == "url_crawl_done":
            return "Website crawl complete. Chunking content..."

    if event == "chunking_start":
        return "Chunking extracted content..."
    if event == "chunking_done":
        prepared_chunk_count = int(payload.get("prepared_chunk_count") or 0)
        return f"Prepared {prepared_chunk_count} chunks..."
    if event == "embedding_prepare_start":
        return "Preparing embedding pipeline..."
    if event == "embedding_upload_start":
        total_chunks = int(payload.get("total_chunks") or 0)
        return f"Embedding and uploading {total_chunks} chunks..."
    if event == "embedding_upload_batch_done":
        batch_index = int(payload.get("batch_index") or 0)
        total_batches = int(payload.get("total_batches") or 0)
        return f"Uploading embeddings batch {batch_index}/{total_batches}..."
    if event == "embedding_upload_done":
        return "Embedding upload complete."
    return "Indexing in progress..."


def _run_upload_index_job(
    *,
    job_id: str,
    kb_name: str,
    file_paths: List[str],
    urls: List[str],
    force_recreate: bool,
    url_max_pages: Optional[int],
    url_use_sitemap: bool,
    pdf_use_ocr: bool,
    chunk_size: int,
    chunk_overlap: int,
    temp_dir: str,
) -> None:
    try:
        _set_index_job(
            job_id,
            status="running",
            phase="bootstrap",
            phase_label="Starting indexing pipeline",
            message="Starting indexing pipeline...",
            progress_percent=2.0,
        )

        source_plan: List[str] = []
        if file_paths:
            source_plan.append("pdf")
        if urls:
            source_plan.append("url")
        source_count = max(1, len(source_plan))
        source_progress_span = 88.0
        source_progress_start = 5.0

        def update_from_event(source: str, source_index: int, event: str, payload: Dict[str, Any]) -> None:
            segment_start = source_progress_start + (source_progress_span / source_count) * source_index
            segment_end = source_progress_start + (source_progress_span / source_count) * (source_index + 1)
            fraction = max(0.0, min(1.0, _source_progress_fraction(source, event, payload)))
            percent = segment_start + (segment_end - segment_start) * fraction
            _set_index_job(
                job_id,
                status="running",
                phase=f"{source}.{event}",
                phase_label=_source_progress_message(source, event, payload),
                message=_source_progress_message(source, event, payload),
                progress_percent=percent,
            )

        pdf_chunk_count = 0
        url_chunk_count = 0
        force_consumed = False
        source_idx = 0

        if file_paths:
            _set_index_job(
                job_id,
                status="running",
                phase="pdf.start",
                phase_label="Indexing PDF sources",
                message="Indexing PDF sources...",
                progress_percent=source_progress_start + 1.0,
            )
            pdf_chunk_count = index_pdfs_to_collection(
                kb_name,
                file_paths,
                force_recreate=force_recreate,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                use_ocr=pdf_use_ocr,
                progress_callback=lambda event, payload, idx=source_idx: update_from_event("pdf", idx, event, payload),
            )
            force_consumed = force_recreate
            source_idx += 1

        if urls:
            _set_index_job(
                job_id,
                status="running",
                phase="url.start",
                phase_label="Indexing website sources",
                message="Indexing website sources...",
                progress_percent=source_progress_start + (source_progress_span / source_count) * source_idx + 1.0,
            )
            url_chunk_count = index_urls_to_collection(
                kb_name,
                urls,
                force_recreate=(force_recreate and not force_consumed),
                max_pages_per_site=url_max_pages,
                use_sitemap=url_use_sitemap,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                progress_callback=lambda event, payload, idx=source_idx: update_from_event("url", idx, event, payload),
            )

        chunk_count = int(pdf_chunk_count) + int(url_chunk_count)
        if chunk_count == 0:
            raise ValueError(
                "No readable content was extracted from the provided sources. "
                "Try different URLs (or www variant), ensure pages are public HTML, "
                "and verify PDFs contain selectable text."
            )

        _set_index_job(
            job_id,
            status="running",
            phase="finalize",
            phase_label="Finalizing index",
            message="Finalizing index...",
            progress_percent=97.0,
        )

        points_count = get_collection_point_count(kb_name)
        result_payload = {
            "status": "success",
            "message": (
                f"Indexed {len(file_paths)} PDF file(s) and {len(urls)} URL(s) "
                f"with {chunk_count} chunks into '{kb_name}'"
            ),
            "file_count": len(file_paths),
            "url_count": len(urls),
            "chunk_count": chunk_count,
            "pdf_chunk_count": int(pdf_chunk_count),
            "url_chunk_count": int(url_chunk_count),
            "chunk_size_used": int(chunk_size),
            "chunk_overlap_used": int(chunk_overlap),
            "ocr_used": bool(pdf_use_ocr),
            "points_count": int(points_count),
        }
        _set_index_job(
            job_id,
            status="completed",
            phase="completed",
            phase_label="Indexing complete",
            message=result_payload["message"],
            progress_percent=100.0,
            result=result_payload,
            error=None,
        )
    except Exception as error:
        detail = str(error) or "Indexing failed."
        _set_index_job(
            job_id,
            status="failed",
            phase="failed",
            phase_label="Indexing failed",
            message=detail,
            progress_percent=100.0,
            error=detail,
        )
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            logger.warning("Failed to clean temp indexing directory: %s", temp_dir)


@app.post("/api/collections/{kb_name}/upload/start")
async def start_upload_documents_job(
    kb_name: str,
    force_recreate: bool = Query(default=False),
    url_max_pages: Optional[int] = Query(default=None, ge=1, le=2000),
    url_use_sitemap: bool = Query(default=True),
    pdf_use_ocr: bool = Query(default=False),
    chunk_size: Optional[int] = Query(default=None, ge=200, le=8000),
    chunk_overlap: Optional[int] = Query(default=None, ge=0, le=2000),
    files: Optional[List[UploadFile]] = File(default=None),
    urls: Optional[List[str]] = Form(default=None),
    db: Session = Depends(get_db_session),
):
    kb = db.execute(
        select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == kb_name)
    ).scalars().first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")

    profile = db.execute(
        select(KnowledgeBaseRetrievalProfileSQLModel).where(
            KnowledgeBaseRetrievalProfileSQLModel.knowledge_base_id == kb.id
        )
    ).scalars().first()

    resolved_chunk_size, resolved_chunk_overlap = _resolve_index_chunk_settings(
        profile=profile,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    temp_dir = tempfile.mkdtemp(prefix="index-job-")
    try:
        file_paths, normalized_urls = _collect_upload_sources(temp_dir=temp_dir, files=files, urls=urls)
        if not file_paths and not normalized_urls:
            shutil.rmtree(temp_dir)
            raise HTTPException(status_code=400, detail="Provide at least one PDF file or one website URL")
    except Exception:
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    job_id = f"index_{uuid.uuid4().hex}"
    created_at = _utc_iso_now()
    _set_index_job(
        job_id,
        status="queued",
        kb_name=kb_name,
        created_at=created_at,
        phase="queued",
        phase_label="Job queued",
        message="Indexing job queued.",
        progress_percent=0.0,
        force_recreate=bool(force_recreate),
        file_count=len(file_paths),
        url_count=len(normalized_urls),
        chunk_size_used=resolved_chunk_size,
        chunk_overlap_used=resolved_chunk_overlap,
        ocr_used=bool(pdf_use_ocr),
        url_max_pages=url_max_pages,
        url_use_sitemap=bool(url_use_sitemap),
        temp_dir=temp_dir,
        file_paths=file_paths,
        urls=normalized_urls,
    )

    thread = threading.Thread(
        target=_run_upload_index_job,
        kwargs={
            "job_id": job_id,
            "kb_name": kb_name,
            "file_paths": file_paths,
            "urls": normalized_urls,
            "force_recreate": bool(force_recreate),
            "url_max_pages": url_max_pages,
            "url_use_sitemap": bool(url_use_sitemap),
            "pdf_use_ocr": bool(pdf_use_ocr),
            "chunk_size": int(resolved_chunk_size),
            "chunk_overlap": int(resolved_chunk_overlap),
            "temp_dir": temp_dir,
        },
        daemon=True,
    )
    thread.start()

    payload = _get_index_job(job_id) or {}
    return _public_index_job_payload(payload)


@app.get("/api/collections/upload/jobs/{job_id}")
def get_upload_documents_job(job_id: str):
    payload = _get_index_job(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Indexing job not found")
    return _public_index_job_payload(payload)

@app.post("/api/collections/{kb_name}/upload")
async def upload_documents(
    kb_name: str,
    force_recreate: bool = Query(default=False),
    url_max_pages: Optional[int] = Query(default=None, ge=1, le=2000),
    url_use_sitemap: bool = Query(default=True),
    pdf_use_ocr: bool = Query(default=False),
    chunk_size: Optional[int] = Query(default=None, ge=200, le=8000),
    chunk_overlap: Optional[int] = Query(default=None, ge=0, le=2000),
    files: Optional[List[UploadFile]] = File(default=None),
    urls: Optional[List[str]] = Form(default=None),
    db: Session = Depends(get_db_session),
):
    """Upload and index PDFs and/or website URLs into a collection."""
    kb = db.execute(
        select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == kb_name)
    ).scalars().first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")
    
    temp_dir = tempfile.mkdtemp()
    file_paths = []
    normalized_urls: List[str] = []

    profile = db.execute(
        select(KnowledgeBaseRetrievalProfileSQLModel).where(
            KnowledgeBaseRetrievalProfileSQLModel.knowledge_base_id == kb.id
        )
    ).scalars().first()

    resolved_chunk_size = int(chunk_size) if chunk_size is not None else int(
        profile.chunk_size if profile and profile.chunk_size else DEFAULT_CHUNK_SIZE
    )
    resolved_chunk_overlap = int(chunk_overlap) if chunk_overlap is not None else int(
        profile.chunk_overlap if profile and profile.chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
    )
    if resolved_chunk_overlap >= resolved_chunk_size:
        resolved_chunk_overlap = max(0, resolved_chunk_size - 1)
    
    try:
        for file in files or []:
            if not file.filename.lower().endswith(".pdf"):
                continue
                
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_paths.append(file_path)

        # URLs can be submitted either as multiple `urls` fields or as comma/newline separated values.
        for raw in urls or []:
            for candidate in raw.replace(",", "\n").splitlines():
                clean = candidate.strip()
                if clean and clean not in normalized_urls:
                    normalized_urls.append(clean)

        if not file_paths and not normalized_urls:
            raise HTTPException(status_code=400, detail="Provide at least one PDF file or one website URL")

        pdf_chunk_count = 0
        url_chunk_count = 0
        force_consumed = False

        if file_paths:
            pdf_chunk_count = await asyncio.to_thread(
                index_pdfs_to_collection,
                kb_name,
                file_paths,
                force_recreate,
                resolved_chunk_size,
                resolved_chunk_overlap,
                pdf_use_ocr,
            )
            force_consumed = force_recreate

        if normalized_urls:
            url_chunk_count = await asyncio.to_thread(
                index_urls_to_collection,
                kb_name,
                normalized_urls,
                (force_recreate and not force_consumed),
                url_max_pages,
                url_use_sitemap,
                resolved_chunk_size,
                resolved_chunk_overlap,
            )

        chunk_count = pdf_chunk_count + url_chunk_count
        if chunk_count == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No readable content was extracted from the provided sources. "
                    "Try different URLs (or www variant), ensure pages are public HTML, "
                    "and verify PDFs contain selectable text."
                ),
            )
        
        return {
            "status": "success",
            "message": (
                f"Indexed {len(file_paths)} PDF file(s) and {len(normalized_urls)} URL(s) "
                f"with {chunk_count} chunks into '{kb_name}'"
            ),
            "file_count": len(file_paths),
            "url_count": len(normalized_urls),
            "chunk_count": chunk_count,
            "pdf_chunk_count": pdf_chunk_count,
            "url_chunk_count": url_chunk_count,
            "chunk_size_used": resolved_chunk_size,
            "chunk_overlap_used": resolved_chunk_overlap,
            "ocr_used": bool(pdf_use_ocr),
            "points_count": get_collection_point_count(kb_name),
        }
    except ValueError as e:
        print(f"❌ Upload/Indexing validation failed: {e}")
        status_code = 409 if "force_recreate" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload/Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(temp_dir)


# ============================================================================
# WORKSPACE: Jahan AI ki setting hoti hai
# ============================================================================

class WorkspaceCreate(BaseModel):
    name: str
    knowledge_base_id: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    low_quality_clarification_text: Optional[str] = None
    group_ids: List[str] = []
    contact_filter_mode: str = "all"
    contact_chat_ids: List[str] = []


class WorkspaceStatusUpdate(BaseModel):
    is_active: bool

def get_workspaces(db: Session = Depends(get_db_session)):
    """Saare workspaces ki list nikaalte hain"""
    ensure_workspace_flow_schema(db)
    _normalize_contacts_if_needed(db)
    workspaces = db.execute(select(WorkspaceSQLModel)).scalars().all()
    knowledge_base_ids = [ws.knowledge_base_id for ws in workspaces if ws.knowledge_base_id]
    kb_by_id = {}
    if knowledge_base_ids:
        kb_rows = db.execute(
            select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.id.in_(knowledge_base_ids))
        ).scalars().all()
        kb_by_id = {kb.id: kb for kb in kb_rows}

    result = []
    for ws in workspaces:
        kb = kb_by_id.get(ws.knowledge_base_id) if ws.knowledge_base_id else None
        # Get assigned groups.
        groups = db.execute(
            select(WhatsAppGroupSQLModel)
            .join(WorkspaceGroupSQLModel, WorkspaceGroupSQLModel.group_id == WhatsAppGroupSQLModel.id)
            .where(WorkspaceGroupSQLModel.workspace_id == ws.id)
        ).scalars().all()
        contacts = db.execute(
            select(WhatsAppContactSQLModel)
            .join(WorkspaceContactSQLModel, WorkspaceContactSQLModel.contact_id == WhatsAppContactSQLModel.id)
            .where(WorkspaceContactSQLModel.workspace_id == ws.id)
        ).scalars().all()
        result.append({
            "id": str(ws.id),
            "name": ws.name,
            "is_active": ws.is_active,
            "contact_filter_mode": str(getattr(ws, "contact_filter_mode", "all") or "all"),
            "knowledge_base": {
                "id": str(kb.id),
                "name": kb.name
            } if kb else None,
            "groups": [{"id": str(g.id), "name": g.name, "chat_id": g.chat_id} for g in groups],
            "contacts": [_serialize_contact_ref(contact) for contact in contacts],
        })
    return {"workspaces": result}

def create_workspace(data: WorkspaceCreate, db: Session = Depends(get_db_session)):
    """Create a new workspace and assign groups"""
    ensure_workspace_flow_schema(db)
    contact_filter_mode = _resolve_contact_filter_mode(data.contact_filter_mode)
    ws = WorkspaceSQLModel(
        name=data.name,
        knowledge_base_id=uuid.UUID(data.knowledge_base_id) if data.knowledge_base_id else None,
        system_prompt=data.system_prompt,
        user_prompt_template=data.user_prompt_template,
        low_quality_clarification_text=data.low_quality_clarification_text,
        contact_filter_mode=contact_filter_mode,
        is_active=True
    )
    db.add(ws)
    db.flush()  # Get ID.
    
    # Assign groups.
    for group_id in data.group_ids:
        db.add(WorkspaceGroupSQLModel(workspace_id=ws.id, group_id=uuid.UUID(group_id)))
    # Assign contact filters.
    _assign_workspace_contacts(db, ws.id, data.contact_chat_ids)
    
    db.commit()
    db.refresh(ws)
    return ws

def get_workspace(workspace_id: uuid.UUID, db: Session = Depends(get_db_session)):
    """Get a specific workspace with full details"""
    ensure_workspace_flow_schema(db)
    _normalize_contacts_if_needed(db)
    logger.debug("GET /api/workspaces/%s", workspace_id)
    ws = db.execute(
        select(WorkspaceSQLModel).where(WorkspaceSQLModel.id == workspace_id)
    ).scalars().first()
    
    if not ws:
        logger.debug("Workspace not found: %s", workspace_id)
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    logger.debug("Workspace found: %s", ws.name)
    # Get assigned groups
    groups = db.execute(
        select(WhatsAppGroupSQLModel)
        .join(WorkspaceGroupSQLModel, WorkspaceGroupSQLModel.group_id == WhatsAppGroupSQLModel.id)
        .where(WorkspaceGroupSQLModel.workspace_id == ws.id)
    ).scalars().all()
    contacts = db.execute(
        select(WhatsAppContactSQLModel)
        .join(WorkspaceContactSQLModel, WorkspaceContactSQLModel.contact_id == WhatsAppContactSQLModel.id)
        .where(WorkspaceContactSQLModel.workspace_id == ws.id)
    ).scalars().all()
    
    return {
        "id": str(ws.id),
        "name": ws.name,
        "knowledge_base_id": str(ws.knowledge_base_id) if ws.knowledge_base_id else None,
        "system_prompt": ws.system_prompt,
        "user_prompt_template": ws.user_prompt_template,
        "low_quality_clarification_text": ws.low_quality_clarification_text,
        "contact_filter_mode": str(getattr(ws, "contact_filter_mode", "all") or "all"),
        "is_active": ws.is_active,
        "groups": [{"id": str(g.id), "name": g.name, "chat_id": g.chat_id} for g in groups],
        "contacts": [_serialize_contact_ref(contact) for contact in contacts],
    }

def update_workspace(workspace_id: uuid.UUID, data: WorkspaceCreate, db: Session = Depends(get_db_session)):
    """Update an existing workspace"""
    logger.debug("PUT /api/workspaces/%s", workspace_id)
    ensure_workspace_flow_schema(db)
    ws = db.execute(
        select(WorkspaceSQLModel).where(WorkspaceSQLModel.id == workspace_id)
    ).scalars().first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    ws.name = data.name
    ws.knowledge_base_id = uuid.UUID(data.knowledge_base_id) if data.knowledge_base_id else None
    ws.system_prompt = data.system_prompt
    ws.user_prompt_template = data.user_prompt_template
    ws.low_quality_clarification_text = data.low_quality_clarification_text
    ws.contact_filter_mode = _resolve_contact_filter_mode(data.contact_filter_mode)
    
    # Update groups: Clear and re-assign
    db.execute(
        delete(WorkspaceGroupSQLModel).where(WorkspaceGroupSQLModel.workspace_id == ws.id)
    )
    for group_id in data.group_ids:
        db.add(WorkspaceGroupSQLModel(workspace_id=ws.id, group_id=uuid.UUID(group_id)))
    db.execute(
        delete(WorkspaceContactSQLModel).where(WorkspaceContactSQLModel.workspace_id == ws.id)
    )
    _assign_workspace_contacts(db, ws.id, data.contact_chat_ids)
        
    db.commit()
    logger.debug("Workspace updated: %s", ws.name)
    return {"status": "success", "message": "Workspace updated"}

def delete_workspace(workspace_id: uuid.UUID, db: Session = Depends(get_db_session)):
    """Delete a workspace and its group assignments"""
    logger.debug("DELETE /api/workspaces/%s", workspace_id)
    ensure_workspace_flow_schema(db)
    ws = db.execute(
        select(WorkspaceSQLModel).where(WorkspaceSQLModel.id == workspace_id)
    ).scalars().first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # Delete group assignments
    db.execute(
        delete(WorkspaceGroupSQLModel).where(WorkspaceGroupSQLModel.workspace_id == ws.id)
    )
    db.execute(
        delete(WorkspaceContactSQLModel).where(WorkspaceContactSQLModel.workspace_id == ws.id)
    )
    
    # Keep logic layers, just unassign from this workspace
    legacy_flows = db.execute(
        select(FlowSQLModel).where(FlowSQLModel.workspace_id == ws.id)
    ).scalars().all()
    for legacy_flow in legacy_flows:
        legacy_flow.workspace_id = None
        legacy_flow.updated_at = datetime.now()
        db.add(legacy_flow)

    db.execute(
        delete(WorkspaceFlowSQLModel).where(WorkspaceFlowSQLModel.workspace_id == ws.id)
    )
    
    db.delete(ws)
    db.commit()
    logger.debug("Workspace deleted: %s", workspace_id)
    return {"status": "success", "message": "Workspace deleted"}


# ============================================================================
# GROUPS: WhatsApp groups ka intejam
# ============================================================================

@app.get("/api/groups")
def get_groups(db: Session = Depends(get_db_session)):
    """Database se saare WhatsApp groups nikaalo"""
    groups = db.execute(select(WhatsAppGroupSQLModel)).scalars().all()
    
    result = []
    for group in groups:
        # Get assigned flows
        flow_groups = db.execute(
            select(FlowGroupSQLModel).where(FlowGroupSQLModel.group_id == group.id)
        ).scalars().all()
        assigned_flows = []
        for fg in flow_groups:
            flow = db.execute(
                select(FlowSQLModel).where(FlowSQLModel.id == fg.flow_id)
            ).scalars().first()
            if flow:
                assigned_flows.append({
                    "id": str(flow.id),
                    "name": flow.name
                })
        
        result.append({
            "id": str(group.id),
            "chat_id": group.chat_id,
            "name": group.name,
            "description": group.description,
            "member_count": group.member_count,
            "avatar_url": group.avatar_url,
            "is_enabled": group.is_enabled,
            "synced_at": group.synced_at.isoformat() if group.synced_at else None,
            "last_message_at": group.last_message_at.isoformat() if group.last_message_at else None,
            "assigned_flows": assigned_flows
        })
    
    return {"groups": result, "total": len(result)}


def _sync_contacts_from_conversation_keys(db: Session) -> int:
    """
    Backfill contacts from existing Redis conversation keys.
    Keys look like: conversation:<chat_id>
    """
    synced = 0
    try:
        raw_keys = queue.connection.keys("conversation:*")
    except Exception:
        return 0

    for raw_key in raw_keys or []:
        key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
        if key.startswith("conversation:ingress:"):
            continue
        chat_id = key.split("conversation:", 1)[-1].strip()
        if "::ws:" in chat_id:
            continue
        normalized = _normalize_contact_chat_id(chat_id)
        if not normalized or "@g.us" in normalized:
            continue
        contact = _upsert_contact_by_chat_id(db, normalized, source="conversation")
        if contact:
            synced += 1
    return synced


def _sync_contacts_from_waha(db: Session) -> Dict[str, int]:
    """
    Sync contacts directly from WAHA `/api/contacts/all?session=...`.
    Preference for contact id mapping:
    1) phoneNumber (@s.whatsapp.net)
    2) lid (@lid)
    3) id (@c.us)
    """
    fetched = 0
    synced = 0

    try:
        raw_contacts = waha_client.get_all_contacts(sort_by="name", sort_order="desc")
    except Exception as exc:
        logger.warning("WAHA contacts sync failed: %s", exc)
        return {"fetched": 0, "synced": 0}

    if not isinstance(raw_contacts, list):
        return {"fetched": 0, "synced": 0}

    fetched = len(raw_contacts)
    for item in raw_contacts:
        if not isinstance(item, dict):
            continue

        display_name = str(item.get("name") or item.get("pushname") or "").strip() or None
        normalized_id = _normalize_contact_chat_id(item.get("id")) or None
        normalized_lid = _normalize_contact_chat_id(item.get("lid")) or None
        normalized_phone_jid = _normalize_contact_chat_id(item.get("phoneNumber")) or None
        normalized_chat_id = normalized_lid or normalized_phone_jid or normalized_id

        if not normalized_chat_id:
            continue

        contact = _upsert_contact_by_chat_id(
            db,
            normalized_chat_id,
            display_name=display_name,
            source="waha",
            waha_contact_id=normalized_id,
            lid=normalized_lid,
            phone_jid=normalized_phone_jid,
        )
        if contact:
            synced += 1

    return {"fetched": int(fetched), "synced": int(synced)}


def _assign_workspace_contacts(
    db: Session,
    workspace_id: uuid.UUID,
    chat_ids: List[str],
) -> None:
    """
    Attach workspace contact filters while preventing identity duplicates.
    Multiple ids like @lid and @s.whatsapp.net for the same person map to one contact row.
    """
    attached_contact_ids: set[str] = set()
    for chat_id in chat_ids or []:
        contact = _upsert_contact_by_chat_id(db, chat_id, source="manual")
        if not contact:
            continue
        contact_key = str(contact.id)
        if contact_key in attached_contact_ids:
            continue
        attached_contact_ids.add(contact_key)
        db.add(WorkspaceContactSQLModel(workspace_id=workspace_id, contact_id=contact.id))


def _contact_identity_tokens(contact: WhatsAppContactSQLModel) -> List[str]:
    tokens: List[str] = []
    for raw_value in (
        contact.chat_id,
        contact.waha_contact_id,
        contact.lid,
        contact.phone_jid,
    ):
        normalized = _normalize_contact_chat_id(raw_value)
        if normalized and "@g.us" not in normalized:
            token = f"jid:{normalized}"
            if token not in tokens:
                tokens.append(token)
    phone_digits = _extract_phone_number(contact.phone_number or contact.phone_jid or contact.chat_id)
    if len(phone_digits) >= 8:
        token = f"phone:{phone_digits}"
        if token not in tokens:
            tokens.append(token)
    return tokens


def _contact_quality_score(contact: WhatsAppContactSQLModel) -> tuple:
    display_name = str(contact.display_name or "").strip()
    has_meaningful_name = bool(display_name and not display_name.isdigit())
    return (
        int(has_meaningful_name),
        int(bool(contact.waha_contact_id)),
        int(bool(contact.lid)),
        int(bool(contact.phone_jid)),
        int(bool(contact.phone_number)),
        int(bool(contact.last_seen_at)),
        contact.last_seen_at or datetime.min,
        contact.updated_at or datetime.min,
        contact.created_at or datetime.min,
    )


def _merge_contact_fields(target: WhatsAppContactSQLModel, source: WhatsAppContactSQLModel) -> None:
    target_name = str(target.display_name or "").strip()
    source_name = str(source.display_name or "").strip()
    if source_name and ((not target_name) or target_name.isdigit()):
        target.display_name = source_name

    target.phone_number = target.phone_number or source.phone_number
    target.waha_contact_id = target.waha_contact_id or source.waha_contact_id
    target.lid = target.lid or source.lid
    target.phone_jid = target.phone_jid or source.phone_jid

    if (target.source or "").strip().lower() != "waha" and (source.source or "").strip().lower() == "waha":
        target.source = "waha"

    if source.last_seen_at and (not target.last_seen_at or source.last_seen_at > target.last_seen_at):
        target.last_seen_at = source.last_seen_at

    target.is_active = bool(target.is_active) or bool(source.is_active)


def _normalize_contact_primary_chat_ids(db: Session) -> Dict[str, int]:
    """
    Ensure primary contact chat_id is canonical for WhatsApp identities.
    Preference: lid > phone_jid > waha_contact_id > existing chat_id.
    Also merges any chat_id conflicts safely before promotion.
    """
    merged = _dedupe_whatsapp_contacts(db)
    promoted = 0
    merged_conflicts = 0

    contacts = db.execute(
        select(WhatsAppContactSQLModel).where(~WhatsAppContactSQLModel.chat_id.like("%@g.us"))
    ).scalars().all()

    for contact in contacts:
        preferred_chat_id = (
            _normalize_contact_chat_id(contact.lid)
            or _normalize_contact_chat_id(contact.phone_jid)
            or _normalize_contact_chat_id(contact.waha_contact_id)
            or _normalize_contact_chat_id(contact.chat_id)
        )
        if not preferred_chat_id or preferred_chat_id == contact.chat_id:
            continue

        conflict = db.execute(
            select(WhatsAppContactSQLModel).where(
                WhatsAppContactSQLModel.chat_id == preferred_chat_id,
                WhatsAppContactSQLModel.id != contact.id,
            )
        ).scalars().first()

        if conflict:
            # Merge lower-quality row into higher-quality one, then keep canonical chat_id row.
            canonical = max([contact, conflict], key=_contact_quality_score)
            duplicate = conflict if canonical.id == contact.id else contact

            _merge_contact_fields(canonical, duplicate)

            duplicate_links = db.execute(
                select(WorkspaceContactSQLModel).where(WorkspaceContactSQLModel.contact_id == duplicate.id)
            ).scalars().all()
            for link in duplicate_links:
                existing_link = db.execute(
                    select(WorkspaceContactSQLModel).where(
                        WorkspaceContactSQLModel.workspace_id == link.workspace_id,
                        WorkspaceContactSQLModel.contact_id == canonical.id,
                    )
                ).scalars().first()
                if existing_link:
                    db.delete(link)
                else:
                    link.contact_id = canonical.id
                    db.add(link)

            db.delete(duplicate)
            db.add(canonical)
            merged_conflicts += 1
            continue

        contact.chat_id = preferred_chat_id
        db.add(contact)
        promoted += 1

    return {
        "deduped": int(merged),
        "promoted": int(promoted),
        "merged_conflicts": int(merged_conflicts),
    }


def _normalize_contacts_if_needed(db: Session) -> Dict[str, int]:
    normalized = _normalize_contact_primary_chat_ids(db)
    if any(int(normalized.get(key, 0)) > 0 for key in ("deduped", "promoted", "merged_conflicts")):
        db.commit()
    return normalized


def _dedupe_whatsapp_contacts(db: Session) -> int:
    """
    Merge duplicate contacts representing the same person across
    @lid / @s.whatsapp.net / @c.us identities.
    """
    contacts = db.execute(
        select(WhatsAppContactSQLModel).where(~WhatsAppContactSQLModel.chat_id.like("%@g.us"))
    ).scalars().all()
    if len(contacts) < 2:
        return 0

    by_id: Dict[str, WhatsAppContactSQLModel] = {str(contact.id): contact for contact in contacts}
    id_to_tokens: Dict[str, List[str]] = {}
    token_to_ids: Dict[str, set] = defaultdict(set)

    for contact in contacts:
        cid = str(contact.id)
        tokens = _contact_identity_tokens(contact)
        id_to_tokens[cid] = tokens
        for token in tokens:
            token_to_ids[token].add(cid)

    merged_count = 0
    visited: set = set()

    for cid in list(by_id.keys()):
        if cid in visited:
            continue
        stack = [cid]
        component_ids: set = set()

        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            component_ids.add(current_id)
            for token in id_to_tokens.get(current_id, []):
                for neighbor_id in token_to_ids.get(token, set()):
                    if neighbor_id not in visited:
                        stack.append(neighbor_id)

        if len(component_ids) <= 1:
            continue

        component_contacts = [by_id[item_id] for item_id in component_ids if item_id in by_id]
        if len(component_contacts) <= 1:
            continue
        canonical = max(component_contacts, key=_contact_quality_score)

        for duplicate in component_contacts:
            if duplicate.id == canonical.id:
                continue

            _merge_contact_fields(canonical, duplicate)

            duplicate_links = db.execute(
                select(WorkspaceContactSQLModel).where(WorkspaceContactSQLModel.contact_id == duplicate.id)
            ).scalars().all()
            for link in duplicate_links:
                existing_link = db.execute(
                    select(WorkspaceContactSQLModel).where(
                        WorkspaceContactSQLModel.workspace_id == link.workspace_id,
                        WorkspaceContactSQLModel.contact_id == canonical.id,
                    )
                ).scalars().first()
                if existing_link:
                    db.delete(link)
                else:
                    link.contact_id = canonical.id
                    db.add(link)

            db.delete(duplicate)
            by_id.pop(str(duplicate.id), None)
            merged_count += 1

        db.add(canonical)

    return int(merged_count)


def get_contacts(db: Session = Depends(get_db_session)):
    """Get known individual contacts (not groups)."""
    ensure_workspace_flow_schema(db)
    _normalize_contacts_if_needed(db)
    contacts = db.execute(
        select(WhatsAppContactSQLModel)
        .where(~WhatsAppContactSQLModel.chat_id.like("%@g.us"))
        .order_by(WhatsAppContactSQLModel.last_seen_at.desc().nullslast(), WhatsAppContactSQLModel.created_at.desc())
    ).scalars().all()
    return {
        "contacts": [_serialize_contact_ref(contact) for contact in contacts],
        "total": len(contacts),
    }


def sync_contacts(
    allow_fallback: bool = Query(default=False),
    db: Session = Depends(get_db_session),
):
    """Sync contacts from WAHA contacts store. Optional fallback to Redis conversation keys."""
    ensure_workspace_flow_schema(db)
    waha_stats = _sync_contacts_from_waha(db)
    fallback_synced = 0
    source = "waha"
    fallback_reason = None

    if int(waha_stats.get("fetched", 0)) == 0:
        if allow_fallback:
            fallback_synced = _sync_contacts_from_conversation_keys(db)
            source = "conversation_fallback"
        else:
            source = "waha_only_no_fallback"
            fallback_reason = "WAHA returned 0 contacts; fallback disabled"

    normalized = _normalize_contacts_if_needed(db)
    db.commit()
    contacts = db.execute(
        select(WhatsAppContactSQLModel).where(~WhatsAppContactSQLModel.chat_id.like("%@g.us"))
    ).scalars().all()
    return {
        "status": "success",
        "source": source,
        "fetched": int(waha_stats.get("fetched", 0)),
        "synced": int(waha_stats.get("synced", 0)) + int(fallback_synced),
        "fallback_synced": int(fallback_synced),
        "fallback_enabled": bool(allow_fallback),
        "fallback_reason": fallback_reason,
        "deduped": int(normalized.get("deduped", 0)),
        "promoted": int(normalized.get("promoted", 0)),
        "merged_conflicts": int(normalized.get("merged_conflicts", 0)),
        "total": len(contacts),
    }


@app.post("/api/groups/{group_id}/flows/{flow_id}")
def assign_flow(group_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Assign a flow to a group"""
    group_uuid = uuid.UUID(group_id)
    flow_uuid = uuid.UUID(flow_id)

    # Check if assignment already exists
    existing = db.execute(
        select(FlowGroupSQLModel).where(
            FlowGroupSQLModel.group_id == group_uuid,
            FlowGroupSQLModel.flow_id == flow_uuid,
        )
    ).scalars().first()
    
    if existing:
        return {"status": "success", "message": "Flow already assigned"}
    
    # Create new assignment
    new_assignment = FlowGroupSQLModel(group_id=group_uuid, flow_id=flow_uuid)
    db.add(new_assignment)
    db.commit()
    
    return {"status": "success", "message": "Flow assigned successfully"}

@app.delete("/api/groups/{group_id}/flows/{flow_id}")
def unassign_flow(group_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Remove a flow assignment from a group"""
    group_uuid = uuid.UUID(group_id)
    flow_uuid = uuid.UUID(flow_id)
    db.execute(
        delete(FlowGroupSQLModel).where(
            FlowGroupSQLModel.group_id == group_uuid,
            FlowGroupSQLModel.flow_id == flow_uuid,
        )
    )
    db.commit()
    
    return {"status": "success", "message": "Flow unassigned successfully"}


@app.post("/api/groups/sync")
def sync_groups(db: Session = Depends(get_db_session)):
    """WAHA se groups sync karte hain (naya mal-paani update status)"""
    try:
        # Fetch groups from WAHA
        waha_groups = waha_client.get_all_groups()
        
        if not waha_groups:
            return {"status": "error", "message": "No groups found or WAHA API error"}
        
        synced_count = 0
        updated_count = 0
        
        for waha_group in waha_groups:
            # Check if group exists
            existing_group = db.execute(
                select(WhatsAppGroupSQLModel).where(WhatsAppGroupSQLModel.chat_id == waha_group["chat_id"])
            ).scalars().first()
            
            if existing_group:
                # Update existing group
                existing_group.name = waha_group["name"]
                existing_group.description = waha_group["description"]
                existing_group.member_count = waha_group["member_count"]
                existing_group.avatar_url = waha_group["avatar_url"]
                existing_group.synced_at = datetime.now()
                updated_count += 1
            else:
                # Create new group
                new_group = WhatsAppGroupSQLModel(
                    chat_id=waha_group["chat_id"],
                    name=waha_group["name"],
                    description=waha_group["description"],
                    member_count=waha_group["member_count"],
                    avatar_url=waha_group["avatar_url"],
                    is_enabled=False,  # Disabled by default
                    synced_at=datetime.now()
                )
                db.add(new_group)
                synced_count += 1
        
        db.commit()
        
        return {
            "status": "success",
            "synced": synced_count,
            "updated": updated_count,
            "total": len(waha_groups)
        }
    
    except Exception as e:
        db.rollback()
        print(f"Error syncing groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/groups/{group_id}/toggle")
def toggle_group(group_id: str, db: Session = Depends(get_db_session)):
    """
    Toggle group enabled/disabled status
    
    Args:
        group_id: UUID of the group
    """
    try:
        group = db.execute(
            select(WhatsAppGroupSQLModel).where(WhatsAppGroupSQLModel.id == uuid.UUID(group_id))
        ).scalars().first()
        
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Toggle status
        group.is_enabled = not group.is_enabled
        db.commit()
        
        return {
            "status": "success",
            "group_id": str(group.id),
            "chat_id": group.chat_id,
            "name": group.name,
            "is_enabled": group.is_enabled
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error toggling group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/groups/{group_id}")
def get_group(group_id: str, db: Session = Depends(get_db_session)):
    """Get details of a specific group"""
    group = db.execute(
        select(WhatsAppGroupSQLModel).where(WhatsAppGroupSQLModel.id == uuid.UUID(group_id))
    ).scalars().first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return {
        "id": str(group.id),
        "chat_id": group.chat_id,
        "name": group.name,
        "description": group.description,
        "member_count": group.member_count,
        "avatar_url": group.avatar_url,
        "is_enabled": group.is_enabled,
        "synced_at": group.synced_at.isoformat() if group.synced_at else None,
        "last_message_at": group.last_message_at.isoformat() if group.last_message_at else None
    }


# ============================================================================
# FLOWS: Kaam karne ka tareeka (Custom Logic)
# ============================================================================

class FlowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_ids: Optional[List[str]] = None
    definition: Dict[str, Any]
    trigger_type: str = "whatsapp_mention"
    trigger_config: Dict[str, Any] = {}
    is_enabled: bool = True

class FlowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_ids: Optional[List[str]] = None
    definition: Optional[Dict[str, Any]] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


def infer_trigger_type_from_definition(definition: Dict[str, Any], fallback: str = "whatsapp_message") -> str:
    if not isinstance(definition, dict):
        return fallback

    nodes = definition.get("nodes", [])
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
        data_type = node_data.get("type")

        if node_type != "trigger" and data_type != "trigger":
            continue

        inferred = (
            node.get("trigger_type")
            or node_data.get("subType")
            or node_data.get("trigger_type")
        )
        if isinstance(inferred, str) and inferred.strip():
            return inferred.strip()

    return fallback


@app.get("/api/flows")
def get_flows(workspace_id: Optional[str] = None, db: Session = Depends(get_db_session)):
    """List all flows, optionally filtered by workspace"""
    ensure_workspace_flow_schema(db)
    stmt = select(FlowSQLModel)
    if workspace_id:
        workspace_uuid = uuid.UUID(workspace_id)
        stmt = stmt.outerjoin(
            WorkspaceFlowSQLModel, WorkspaceFlowSQLModel.flow_id == FlowSQLModel.id
        ).where(
            or_(
                WorkspaceFlowSQLModel.workspace_id == workspace_uuid,
                FlowSQLModel.workspace_id == workspace_uuid,  # legacy fallback
            )
        ).distinct()
    stmt = stmt.order_by(FlowSQLModel.created_at.asc())
    flows = db.execute(stmt).scalars().all()

    usage_map = _get_flow_workspace_usage(db, flows)
    result = [_serialize_flow(flow, usage_map.get(flow.id, [])) for flow in flows]
    return {"flows": result, "total": len(result)}


@app.get("/api/templates")
def get_templates():
    """Get processed flow templates"""
    return {"templates": FLOW_TEMPLATES, "total": len(FLOW_TEMPLATES)}


@app.post("/api/flows")
def create_flow(flow_data: FlowCreate, db: Session = Depends(get_db_session)):
    """Create a new flow"""
    ensure_workspace_flow_schema(db)
    # Create default definition if empty
    definition = flow_data.definition
    if not definition or not definition.get("nodes"):
        definition = {"nodes": [], "edges": []}

    inferred_trigger_type = infer_trigger_type_from_definition(definition, flow_data.trigger_type)
    requested_workspace_ids = list(flow_data.workspace_ids or [])
    if flow_data.workspace_id:
        requested_workspace_ids.append(flow_data.workspace_id)
    workspace_uuids = _parse_workspace_uuid_list(requested_workspace_ids) if requested_workspace_ids else []

    new_flow = FlowSQLModel(
        workspace_id=None,  # logic layer ownership is decoupled from workspace usage
        name=flow_data.name,
        description=flow_data.description,
        definition=definition,
        trigger_type=inferred_trigger_type,
        trigger_config=flow_data.trigger_config,
        is_enabled=flow_data.is_enabled
    )
    
    db.add(new_flow)
    db.flush()

    if workspace_uuids:
        existing_workspace_ids = {
            row[0]
            for row in db.execute(
                select(WorkspaceSQLModel.id).where(WorkspaceSQLModel.id.in_(workspace_uuids))
            ).all()
        }
        missing_workspace_ids = [str(ws_id) for ws_id in workspace_uuids if ws_id not in existing_workspace_ids]
        if missing_workspace_ids:
            raise HTTPException(status_code=404, detail=f"Workspace not found: {', '.join(missing_workspace_ids)}")
        for workspace_uuid in workspace_uuids:
            _attach_flow_to_workspace(db, workspace_uuid, new_flow.id)

    db.commit()
    db.refresh(new_flow)
    
    return {"status": "success", "flow_id": str(new_flow.id)}


@app.get("/api/flows/{flow_id}")
def get_flow(flow_id: str, db: Session = Depends(get_db_session)):
    """Get a specific flow with definition"""
    ensure_workspace_flow_schema(db)
    flow = db.execute(
        select(FlowSQLModel).where(FlowSQLModel.id == uuid.UUID(flow_id))
    ).scalars().first()
    
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    usage_map = _get_flow_workspace_usage(db, [flow])
    serialized = _serialize_flow(flow, usage_map.get(flow.id, []))
    return {
        **serialized,
        "definition": flow.definition,
        "trigger_config": flow.trigger_config,
    }


@app.put("/api/flows/{flow_id}")
def update_flow(flow_id: str, flow_data: FlowUpdate, db: Session = Depends(get_db_session)):
    """Update an existing flow"""
    ensure_workspace_flow_schema(db)
    flow = db.execute(
        select(FlowSQLModel).where(FlowSQLModel.id == uuid.UUID(flow_id))
    ).scalars().first()
    
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    update_payload = _model_dump(flow_data)

    if "name" in update_payload:
        flow.name = flow_data.name
    if "description" in update_payload:
        flow.description = flow_data.description
    if "definition" in update_payload:
        flow.definition = flow_data.definition
        flow.trigger_type = infer_trigger_type_from_definition(flow_data.definition or {}, flow.trigger_type)
    elif "trigger_type" in update_payload and flow_data.trigger_type is not None:
        flow.trigger_type = flow_data.trigger_type
    if "trigger_config" in update_payload and flow_data.trigger_config is not None:
        flow.trigger_config = flow_data.trigger_config
    if "is_enabled" in update_payload:
        flow.is_enabled = flow_data.is_enabled

    if "workspace_ids" in update_payload:
        workspace_uuids = _parse_workspace_uuid_list(flow_data.workspace_ids or [])
        existing_workspace_ids = {
            row[0]
            for row in db.execute(
                select(WorkspaceSQLModel.id).where(WorkspaceSQLModel.id.in_(workspace_uuids))
            ).all()
        }
        missing_workspace_ids = [str(ws_id) for ws_id in workspace_uuids if ws_id not in existing_workspace_ids]
        if missing_workspace_ids:
            raise HTTPException(status_code=404, detail=f"Workspace not found: {', '.join(missing_workspace_ids)}")
        db.execute(
            delete(WorkspaceFlowSQLModel).where(WorkspaceFlowSQLModel.flow_id == flow.id)
        )
        for workspace_uuid in workspace_uuids:
            _attach_flow_to_workspace(db, workspace_uuid, flow.id)

    elif "workspace_id" in update_payload:
        # Legacy compatibility: workspace_id now means "attach one" (or clear all if null).
        if flow_data.workspace_id:
            workspace_uuid = uuid.UUID(flow_data.workspace_id)
            workspace_exists = db.execute(
                select(WorkspaceSQLModel.id).where(WorkspaceSQLModel.id == workspace_uuid)
            ).first()
            if not workspace_exists:
                raise HTTPException(status_code=404, detail="Workspace not found")
            _attach_flow_to_workspace(db, workspace_uuid, flow.id)
        else:
            db.execute(
                delete(WorkspaceFlowSQLModel).where(WorkspaceFlowSQLModel.flow_id == flow.id)
            )

    # Legacy column is not the source of truth anymore.
    flow.workspace_id = None
    flow.updated_at = datetime.now()
    db.commit()
    
    return {"status": "success", "flow_id": str(flow.id)}


def attach_workspace_flow(workspace_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Attach a reusable logic layer to a workspace."""
    ensure_workspace_flow_schema(db)
    workspace_uuid = uuid.UUID(workspace_id)
    flow_uuid = uuid.UUID(flow_id)

    workspace_exists = db.execute(
        select(WorkspaceSQLModel.id).where(WorkspaceSQLModel.id == workspace_uuid)
    ).first()
    if not workspace_exists:
        raise HTTPException(status_code=404, detail="Workspace not found")

    flow_exists = db.execute(
        select(FlowSQLModel.id).where(FlowSQLModel.id == flow_uuid)
    ).first()
    if not flow_exists:
        raise HTTPException(status_code=404, detail="Flow not found")

    attached = _attach_flow_to_workspace(db, workspace_uuid, flow_uuid)
    db.commit()
    return {
        "status": "success",
        "message": "Logic layer attached to workspace",
        "workspace_id": workspace_id,
        "flow_id": flow_id,
        "attached": attached,
    }


def detach_workspace_flow(workspace_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Detach a logic layer from one workspace only."""
    ensure_workspace_flow_schema(db)
    workspace_uuid = uuid.UUID(workspace_id)
    flow_uuid = uuid.UUID(flow_id)

    deleted = db.execute(
        delete(WorkspaceFlowSQLModel).where(
            WorkspaceFlowSQLModel.workspace_id == workspace_uuid,
            WorkspaceFlowSQLModel.flow_id == flow_uuid,
        )
    )
    db.commit()

    return {
        "status": "success",
        "message": "Logic layer detached from workspace",
        "workspace_id": workspace_id,
        "flow_id": flow_id,
        "detached": bool(getattr(deleted, "rowcount", 0)),
    }


@app.delete("/api/flows/{flow_id}")
def delete_flow(flow_id: str, db: Session = Depends(get_db_session)):
    """Delete a flow"""
    flow = db.execute(
        select(FlowSQLModel).where(FlowSQLModel.id == uuid.UUID(flow_id))
    ).scalars().first()
    
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    db.delete(flow)
    db.commit()
    
    return {"status": "success", "deleted_id": flow_id}


@app.get("/api/executions")
def get_executions(
    flow_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session)
):
    """
    Get execution logs, optionally filtered by flow_id
    """
    count_stmt = select(func.count()).select_from(FlowExecutionSQLModel)
    stmt = select(FlowExecutionSQLModel)

    if flow_id:
        flow_uuid = uuid.UUID(flow_id)
        count_stmt = count_stmt.where(FlowExecutionSQLModel.flow_id == flow_uuid)
        stmt = stmt.where(FlowExecutionSQLModel.flow_id == flow_uuid)

    total = db.execute(count_stmt).scalar() or 0

    executions = db.execute(
        stmt.order_by(FlowExecutionSQLModel.started_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    
    result = []
    for exec in executions:
        result.append({
            "id": str(exec.id),
            "flow_id": str(exec.flow_id),
            "status": exec.status,
            "started_at": exec.started_at.isoformat() if exec.started_at else None,
            "completed_at": exec.completed_at.isoformat() if exec.completed_at else None,
            "trigger_data": exec.trigger_data, # JSON
            "nodes_executed": exec.nodes_executed # JSON
        })
        
    return {
        "executions": result,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.delete("/api/executions/{execution_id}")
def delete_execution_log(execution_id: str, db: Session = Depends(get_db_session)):
    """Delete a single execution log row by id."""
    try:
        execution_uuid = uuid.UUID(execution_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid execution id format")

    execution = db.execute(
        select(FlowExecutionSQLModel).where(FlowExecutionSQLModel.id == execution_uuid)
    ).scalars().first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    db.delete(execution)
    db.commit()
    return {"status": "success", "deleted_id": execution_id}


@app.post("/api/executions/bulk-delete")
def bulk_delete_execution_logs(payload: ExecutionBulkDeleteRequest, db: Session = Depends(get_db_session)):
    """Delete many execution logs in one request."""
    raw_ids = [str(item).strip() for item in payload.execution_ids if str(item).strip()]
    if not raw_ids:
        raise HTTPException(status_code=422, detail="execution_ids must contain at least one id")

    unique_ids = list(dict.fromkeys(raw_ids))
    parsed_ids: List[uuid.UUID] = []
    invalid_ids: List[str] = []
    for raw_id in unique_ids:
        try:
            parsed_ids.append(uuid.UUID(raw_id))
        except ValueError:
            invalid_ids.append(raw_id)

    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid execution id(s): {', '.join(invalid_ids)}",
        )

    delete_stmt = delete(FlowExecutionSQLModel).where(FlowExecutionSQLModel.id.in_(parsed_ids))
    result = db.execute(delete_stmt)
    db.commit()
    deleted_count = max(int(result.rowcount or 0), 0)
    return {
        "status": "success",
        "requested_count": len(parsed_ids),
        "deleted_count": deleted_count,
    }


@app.delete("/api/executions")
def clear_execution_logs(
    flow_id: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    """Clear all execution logs, optionally scoped to a specific flow."""
    delete_stmt = delete(FlowExecutionSQLModel)
    scope = "all"

    if flow_id:
        try:
            flow_uuid = uuid.UUID(flow_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid flow id format")
        delete_stmt = delete_stmt.where(FlowExecutionSQLModel.flow_id == flow_uuid)
        scope = f"flow:{flow_id}"

    result = db.execute(delete_stmt)
    db.commit()
    deleted_count = max(int(result.rowcount or 0), 0)
    return {"status": "success", "scope": scope, "deleted_count": deleted_count}

@app.get("/api/flows/{flow_id}/executions")
def get_flow_executions(
    flow_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session)
):
    """Get executions for a specific flow"""
    return get_executions(flow_id=flow_id, limit=limit, offset=offset, db=db)
@app.post("/api/flows/{flow_id}/test")
async def test_flow(flow_id: str, db: Session = Depends(get_db_session)):
    """Test a flow with a dummy payload"""
    flow = db.execute(
        select(FlowSQLModel).where(FlowSQLModel.id == uuid.UUID(flow_id))
    ).scalars().first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
        
    # Dummy WhatsApp group payload
    dummy_payload = {
        "id": f"test_{uuid.uuid4().hex[:8]}",
        "chatId": "123456789@g.us",
        "from": "123456789@c.us",
        "body": "Test query: What is the company policy?",
        "timestamp": int(datetime.now().timestamp()),
        "isGroup": True
    }
    
    try:
        from flow_engine import flow_engine
        execution = await flow_engine.execute_flow(flow, dummy_payload, db)
        return {
            "status": "success",
            "execution_id": str(execution.id),
            "flow_status": execution.status,
            "nodes": execution.nodes_executed
        }
    except Exception as e:
        print(f"❌ Test flow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def toggle_workspace(workspace_id: str, db: Session = Depends(get_db_session)):
    """Toggle workspace active status"""
    try:
        workspace = db.execute(
            select(WorkspaceSQLModel).where(WorkspaceSQLModel.id == uuid.UUID(workspace_id))
        ).scalars().first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        workspace.is_active = not workspace.is_active
        workspace.updated_at = datetime.now()
        db.commit()
        
        return {
            "status": "success",
            "workspace_id": str(workspace.id),
            "is_active": workspace.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error toggling workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def set_workspace_status(workspace_id: str, data: WorkspaceStatusUpdate, db: Session = Depends(get_db_session)):
    """Set workspace active status explicitly to avoid accidental inverse toggles."""
    try:
        workspace = db.execute(
            select(WorkspaceSQLModel).where(WorkspaceSQLModel.id == uuid.UUID(workspace_id))
        ).scalars().first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        workspace.is_active = data.is_active
        workspace.updated_at = datetime.now()
        db.commit()

        return {
            "status": "success",
            "workspace_id": str(workspace.id),
            "is_active": workspace.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error setting workspace status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def set_workspace_status_get(
    workspace_id: str,
    is_active: str = Query(...),
    db: Session = Depends(get_db_session),
):
    """
    CORS-safe fallback for environments where PATCH preflight is blocked and
    browser never sends the actual mutation request.
    """
    raw_flag = (is_active or "").strip().lower()
    if raw_flag in {"1", "true", "yes", "on"}:
        parsed_is_active = True
    elif raw_flag in {"0", "false", "no", "off"}:
        parsed_is_active = False
    else:
        raise HTTPException(
            status_code=422,
            detail="is_active must be one of: true/false/1/0/yes/no/on/off",
        )

    try:
        workspace = db.execute(
            select(WorkspaceSQLModel).where(WorkspaceSQLModel.id == uuid.UUID(workspace_id))
        ).scalars().first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        workspace.is_active = parsed_is_active
        workspace.updated_at = datetime.now()
        db.commit()

        return {
            "status": "success",
            "workspace_id": str(workspace.id),
            "is_active": workspace.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error setting workspace status via GET fallback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Feature routers (endpoint declarations) keep server.py smaller while handlers remain local.
app.include_router(
    build_memory_router(
        get_memory_debug_snapshot_handler=get_memory_debug_snapshot,
        upsert_memory_ltm_handler=upsert_memory_ltm,
        deactivate_memory_ltm_handler=deactivate_memory_ltm,
        clear_memory_for_client_handler=clear_memory_for_client,
        memory_ltm_update_model=MemoryLTMUpdate,
    )
)
app.include_router(
    build_rag_router(
        evaluate_rag_quality_handler=evaluate_rag_quality,
        list_rag_scorecards_handler=list_rag_scorecards,
        get_rag_scorecard_handler=get_rag_scorecard,
        rag_eval_request_model=RAGEvalRequest,
    )
)
app.include_router(
    build_contacts_router(
        get_contacts_handler=get_contacts,
        sync_contacts_handler=sync_contacts,
    )
)
app.include_router(
    build_workspaces_router(
        get_workspaces_handler=get_workspaces,
        create_workspace_handler=create_workspace,
        get_workspace_handler=get_workspace,
        update_workspace_handler=update_workspace,
        delete_workspace_handler=delete_workspace,
        attach_workspace_flow_handler=attach_workspace_flow,
        detach_workspace_flow_handler=detach_workspace_flow,
        toggle_workspace_handler=toggle_workspace,
        set_workspace_status_handler=set_workspace_status,
        set_workspace_status_get_handler=set_workspace_status_get,
        workspace_create_model=WorkspaceCreate,
        workspace_status_update_model=WorkspaceStatusUpdate,
    )
)
