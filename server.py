from dotenv import load_dotenv
import asyncio
import logging
import hashlib
import json
import hmac
import secrets
from datetime import datetime, timedelta
import os
from redis import Redis
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

# Ye lo, load ho gaya environment
load_dotenv()

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from client.rq_client import queue
from queues.worker import process_query
from queues.webhook_jobs import process_whatsapp_payload
from rq import Worker
from rq.registry import DeferredJobRegistry, FailedJobRegistry, FinishedJobRegistry, ScheduledJobRegistry, StartedJobRegistry
from sqlalchemy import or_, text
from sqlalchemy.orm import Session
import shutil
import tempfile
import uuid

# Database aur engines ke saaman
from database import (
    get_db_session,
    SessionLocal,
    WhatsAppGroup,
    Flow,
    FlowGroup,
    FlowExecution,
    KnowledgeBase,
    ClientApiKey,
    Workspace,
    WorkspaceGroup,
    WorkspaceFlow,
)
from waha_client import waha_client
from flow_engine import flow_engine
from rag_utils import (
    create_qdrant_collection,
    get_collection_point_count,
    index_pdfs_to_collection,
    index_urls_to_collection,
    list_qdrant_collections,
)

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


_workspace_flow_schema_ready = False
RQ_WORKER_DESIRED_KEY = os.getenv("RQ_WORKER_DESIRED_KEY", "rq:workers:desired_count")
RQ_WORKER_MANAGER_HEARTBEAT_KEY = os.getenv("RQ_WORKER_MANAGER_HEARTBEAT_KEY", "rq:workers:manager:heartbeat")
RQ_WORKER_MIN_COUNT = max(1, int(os.getenv("RQ_WORKER_MIN_COUNT", "1")))
RQ_WORKER_MAX_COUNT = max(RQ_WORKER_MIN_COUNT, int(os.getenv("RQ_WORKER_MAX_COUNT", "16")))
RQ_WORKER_DEFAULT_COUNT = min(
    RQ_WORKER_MAX_COUNT,
    max(RQ_WORKER_MIN_COUNT, int(os.getenv("RQ_WORKER_DEFAULT_COUNT", "1"))),
)
DIRECT_CHAT_MODEL = os.getenv("DIRECT_CHAT_MODEL", "gemini-2.5-flash")
DIRECT_CHAT_TEMPERATURE = float(os.getenv("DIRECT_CHAT_TEMPERATURE", "0.3"))
CLIENT_ID_SALT = os.getenv("CLIENT_ID_SALT", "async-rag-device-id")
CLIENT_CHAT_API_KEY = os.getenv("CLIENT_CHAT_API_KEY", "").strip()
CLIENT_CHAT_ADMIN_KEY = os.getenv("CLIENT_CHAT_ADMIN_KEY", "").strip()
CLIENT_CHAT_API_KEY_SALT = os.getenv("CLIENT_CHAT_API_KEY_SALT", CLIENT_ID_SALT).strip() or CLIENT_ID_SALT
CLIENT_CHAT_DEFAULT_PROMPT_TECHNIQUE = os.getenv("CLIENT_CHAT_DEFAULT_PROMPT_TECHNIQUE", "balanced").strip() or "balanced"
CLIENT_CHAT_DAILY_LIMIT_PER_DEVICE = int(os.getenv("CLIENT_CHAT_DAILY_LIMIT_PER_DEVICE", "0"))


def ensure_workspace_flow_schema(db: Session) -> None:
    """Create workspace-flow mapping table and backfill legacy assignments."""
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


def ensure_client_api_key_schema(db: Session) -> None:
    """Create tenant API key table for public client chat auth/scoping."""
    db.execute(text("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS client_api_keys (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(120) UNIQUE NOT NULL,
            description TEXT,
            key_hash VARCHAR(128) UNIQUE NOT NULL,
            key_prefix VARCHAR(24) NOT NULL,
            allow_all_collections BOOLEAN DEFAULT FALSE,
            allowed_collections JSONB DEFAULT '[]'::jsonb NOT NULL,
            default_collection_name VARCHAR(255),
            daily_limit_per_device INTEGER,
            default_system_prompt TEXT,
            default_user_prompt_template TEXT,
            default_prompt_technique VARCHAR(40) DEFAULT 'balanced',
            is_active BOOLEAN DEFAULT TRUE,
            last_used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("ALTER TABLE client_api_keys ADD COLUMN IF NOT EXISTS daily_limit_per_device INTEGER"))
    db.execute(text("ALTER TABLE client_api_keys ADD COLUMN IF NOT EXISTS default_system_prompt TEXT"))
    db.execute(text("ALTER TABLE client_api_keys ADD COLUMN IF NOT EXISTS default_user_prompt_template TEXT"))
    db.execute(text("ALTER TABLE client_api_keys ADD COLUMN IF NOT EXISTS default_prompt_technique VARCHAR(40) DEFAULT 'balanced'"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_client_api_keys_active ON client_api_keys(is_active)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_client_api_keys_name ON client_api_keys(name)"))
    db.execute(text("""
        DROP TRIGGER IF EXISTS update_client_api_keys_updated_at ON client_api_keys
    """))
    db.execute(text("""
        CREATE TRIGGER update_client_api_keys_updated_at
        BEFORE UPDATE ON client_api_keys
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """))
    db.commit()


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


def _get_flow_workspace_usage(db: Session, flows: List[Flow]) -> Dict[uuid.UUID, List[Dict[str, str]]]:
    usage: Dict[uuid.UUID, List[Dict[str, str]]] = {flow.id: [] for flow in flows}
    flow_ids = [flow.id for flow in flows]
    if not flow_ids:
        return usage

    rows = (
        db.query(WorkspaceFlow.flow_id, Workspace.id, Workspace.name)
        .join(Workspace, Workspace.id == WorkspaceFlow.workspace_id)
        .filter(WorkspaceFlow.flow_id.in_(flow_ids))
        .order_by(Workspace.name.asc())
        .all()
    )
    for flow_id, workspace_id, workspace_name in rows:
        usage.setdefault(flow_id, []).append(
            {"id": str(workspace_id), "name": workspace_name}
        )

    # Fallback for older rows not backfilled yet.
    for flow in flows:
        if usage.get(flow.id):
            continue
        if flow.workspace_id and flow.workspace:
            usage[flow.id] = [{"id": str(flow.workspace_id), "name": flow.workspace.name}]

    return usage


def _serialize_flow(flow: Flow, workspace_links: List[Dict[str, str]]) -> Dict[str, Any]:
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
    existing = db.query(WorkspaceFlow).filter(
        WorkspaceFlow.workspace_id == workspace_uuid,
        WorkspaceFlow.flow_id == flow_uuid,
    ).first()
    if existing:
        return False
    db.add(WorkspaceFlow(workspace_id=workspace_uuid, flow_id=flow_uuid))
    return True


@app.on_event("startup")
def startup_workspace_flow_schema() -> None:
    db = SessionLocal()
    try:
        ensure_workspace_flow_schema(db)
        ensure_client_api_key_schema(db)
    except Exception as exc:
        print(f"⚠️ startup schema setup skipped: {exc}")
    finally:
        db.close()

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


class ClientChatRequest(BaseModel):
    message: str
    client_id: Optional[str] = None
    collection_name: Optional[str] = None
    client_system: Optional[str] = None
    device_fingerprint: Optional[str] = None
    conversation_limit: int = Field(default=6, ge=1, le=20)
    clear_history: bool = False
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    prompt_technique: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: Optional[int] = Field(default=768, ge=64, le=8192)


class ClientApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: Optional[str] = None
    allow_all_collections: bool = False
    allowed_collections: List[str] = Field(default_factory=list)
    default_collection_name: Optional[str] = None
    daily_limit_per_device: Optional[int] = Field(default=None, ge=0, le=1000000)
    default_system_prompt: Optional[str] = None
    default_user_prompt_template: Optional[str] = None
    default_prompt_technique: Optional[str] = None
    is_active: bool = True


class ClientApiKeyUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    description: Optional[str] = None
    allow_all_collections: Optional[bool] = None
    allowed_collections: Optional[List[str]] = None
    default_collection_name: Optional[str] = None
    daily_limit_per_device: Optional[int] = Field(default=None, ge=0, le=1000000)
    default_system_prompt: Optional[str] = None
    default_user_prompt_template: Optional[str] = None
    default_prompt_technique: Optional[str] = None
    is_active: Optional[bool] = None
    rotate_key: bool = False


# WhatsApp webhook models
class WhatsAppPayload(BaseModel):
    chatId: str
    id: str
    body: Optional[str] = ""
    mentionedIds: Optional[List[str]] = []


class WAHAWebhook(BaseModel):
    payload: WhatsAppPayload


def _resolve_request_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return "0.0.0.0"


def _infer_client_system(user_agent: str, explicit_system: Optional[str]) -> str:
    manual = (explicit_system or "").strip()
    if manual:
        return manual[:120]

    ua = (user_agent or "").lower()
    if "windows" in ua:
        return "windows"
    if "android" in ua:
        return "android"
    if "iphone" in ua or "ipad" in ua or "ios" in ua:
        return "ios"
    if "mac os" in ua or "macintosh" in ua:
        return "macos"
    if "linux" in ua:
        return "linux"
    return "unknown"


def _derive_device_client_id(
    request: Request,
    explicit_system: Optional[str] = None,
    device_fingerprint: Optional[str] = None,
) -> str:
    ip_addr = _resolve_request_ip(request)
    user_agent = (request.headers.get("user-agent") or "").strip()
    system_label = _infer_client_system(user_agent, explicit_system)
    fingerprint = (device_fingerprint or "").strip()
    payload = f"{ip_addr}|{system_label}|{user_agent}|{fingerprint}"
    digest = hmac.new(
        key=CLIENT_ID_SALT.encode("utf-8"),
        msg=payload.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"dev_{digest[:32]}"


def _hash_client_api_key(raw_key: str) -> str:
    return hashlib.sha256(f"{CLIENT_CHAT_API_KEY_SALT}:{raw_key}".encode("utf-8")).hexdigest()


def _generate_client_api_key() -> str:
    return f"ck_live_{secrets.token_urlsafe(24)}"


def _normalize_collection_scope(raw_items: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for item in raw_items or []:
        value = (item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _validate_allowed_collections(allowed_collections: List[str]) -> None:
    if not allowed_collections:
        return
    known = set(list_qdrant_collections())
    unknown = [name for name in allowed_collections if name not in known]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection(s): {', '.join(unknown)}",
        )


def _serialize_client_api_key_record(record: ClientApiKey) -> Dict[str, Any]:
    return {
        "id": str(record.id),
        "name": record.name,
        "description": record.description,
        "key_prefix": record.key_prefix,
        "allow_all_collections": bool(record.allow_all_collections),
        "allowed_collections": list(record.allowed_collections or []),
        "default_collection_name": record.default_collection_name,
        "daily_limit_per_device": record.daily_limit_per_device,
        "default_system_prompt": record.default_system_prompt,
        "default_user_prompt_template": record.default_user_prompt_template,
        "default_prompt_technique": _normalize_prompt_technique(record.default_prompt_technique),
        "is_active": bool(record.is_active),
        "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _touch_client_api_key_usage(db: Session, record: ClientApiKey) -> None:
    record.last_used_at = datetime.utcnow()
    db.add(record)
    db.flush()


def _require_client_chat_admin_key(request: Request) -> None:
    admin_header = (request.headers.get("x-client-admin-key") or "").strip()
    api_header = (request.headers.get("x-client-api-key") or "").strip()

    if CLIENT_CHAT_ADMIN_KEY:
        if hmac.compare_digest(admin_header, CLIENT_CHAT_ADMIN_KEY):
            return
        raise HTTPException(status_code=401, detail="Invalid or missing X-Client-Admin-Key")

    if CLIENT_CHAT_API_KEY:
        if hmac.compare_digest(api_header, CLIENT_CHAT_API_KEY):
            return
        raise HTTPException(
            status_code=401,
            detail="Admin key not configured. Use global X-Client-Api-Key for management.",
        )


def _resolve_client_chat_auth_context(request: Request, db: Session) -> Dict[str, Any]:
    provided_key = (request.headers.get("x-client-api-key") or "").strip()
    active_tenant_count = db.query(ClientApiKey).filter(ClientApiKey.is_active.is_(True)).count()
    auth_required = bool(CLIENT_CHAT_API_KEY) or active_tenant_count > 0

    if provided_key:
        if CLIENT_CHAT_API_KEY and hmac.compare_digest(provided_key, CLIENT_CHAT_API_KEY):
            return {"mode": "global", "auth_required": auth_required, "tenant_key": None}

        key_hash = _hash_client_api_key(provided_key)
        tenant_key = db.query(ClientApiKey).filter(
            ClientApiKey.key_hash == key_hash,
            ClientApiKey.is_active.is_(True),
        ).first()
        if tenant_key:
            _touch_client_api_key_usage(db, tenant_key)
            return {"mode": "tenant", "auth_required": auth_required, "tenant_key": tenant_key}
        if not auth_required:
            # Open mode: ignore stale/unknown key headers to keep local UX forgiving.
            return {"mode": "open", "auth_required": False, "tenant_key": None}
        raise HTTPException(status_code=401, detail="Invalid X-Client-Api-Key")

    if auth_required:
        raise HTTPException(status_code=401, detail="Missing X-Client-Api-Key")

    return {"mode": "open", "auth_required": False, "tenant_key": None}


def _normalize_prompt_technique(raw_value: Optional[str]) -> str:
    value = (raw_value or "").strip().lower()
    allowed = {"balanced", "concise", "detailed", "strict_context", "socratic"}
    if value in allowed:
        return value
    return "balanced"


def _resolve_effective_prompt_technique(
    requested: Optional[str],
    auth_context: Dict[str, Any],
) -> str:
    tenant_key = auth_context.get("tenant_key")
    if requested:
        return _normalize_prompt_technique(requested)
    if tenant_key and getattr(tenant_key, "default_prompt_technique", None):
        return _normalize_prompt_technique(tenant_key.default_prompt_technique)
    return _normalize_prompt_technique(CLIENT_CHAT_DEFAULT_PROMPT_TECHNIQUE)


def _resolve_effective_system_prompt(
    requested: Optional[str],
    auth_context: Dict[str, Any],
) -> Optional[str]:
    provided = (requested or "").strip()
    if provided:
        return provided
    tenant_key = auth_context.get("tenant_key")
    fallback = (getattr(tenant_key, "default_system_prompt", "") or "").strip() if tenant_key else ""
    return fallback or None


def _resolve_effective_user_prompt_template(
    requested: Optional[str],
    auth_context: Dict[str, Any],
) -> Optional[str]:
    provided = (requested or "").strip()
    if provided:
        return provided
    tenant_key = auth_context.get("tenant_key")
    fallback = (getattr(tenant_key, "default_user_prompt_template", "") or "").strip() if tenant_key else ""
    return fallback or None


def _build_prompt_replacements(message: str, conversation_history: str, collection_name: Optional[str]) -> Dict[str, str]:
    return {
        "{{message}}": message,
        "{{body}}": message,
        "{{query}}": message,
        "{{conversation_history}}": conversation_history or "",
        "{{collection_name}}": collection_name or "",
    }


def _apply_replacements(template_text: str, replacements: Dict[str, str]) -> str:
    output = template_text
    for key, value in replacements.items():
        output = output.replace(key, value)
    return output


def _apply_prompt_technique(user_payload: str, technique: str) -> str:
    clean_payload = user_payload.strip()
    if technique == "concise":
        return (
            "Respond with high signal and minimal fluff. "
            "Prefer bullets where useful and keep it short.\n\n"
            f"{clean_payload}"
        )
    if technique == "detailed":
        return (
            "Provide a structured, complete answer with clear sections, examples, and caveats.\n\n"
            f"{clean_payload}"
        )
    if technique == "strict_context":
        return (
            "Use only the provided context/data. If data is missing, explicitly say what is missing.\n\n"
            f"{clean_payload}"
        )
    if technique == "socratic":
        return (
            "Answer directly and include one clarifying question if user intent is ambiguous.\n\n"
            f"{clean_payload}"
        )
    return clean_payload


def _build_effective_user_prompt(
    message: str,
    conversation_history: str,
    technique: str,
    user_prompt_template: Optional[str],
    collection_name: Optional[str],
) -> str:
    replacements = _build_prompt_replacements(message, conversation_history, collection_name)
    template = (user_prompt_template or "").strip() or "{{query}}"
    filled = _apply_replacements(template, replacements).strip() or message
    return _apply_prompt_technique(filled, technique)


def _get_daily_limit_for_context(auth_context: Dict[str, Any]) -> int:
    tenant_key = auth_context.get("tenant_key")
    if tenant_key and getattr(tenant_key, "daily_limit_per_device", None):
        return int(tenant_key.daily_limit_per_device)
    return max(0, int(CLIENT_CHAT_DAILY_LIMIT_PER_DEVICE))


def _build_rate_scope_id(auth_context: Dict[str, Any]) -> str:
    mode = auth_context.get("mode") or "open"
    tenant_key = auth_context.get("tenant_key")
    if mode == "tenant" and tenant_key:
        return f"tenant:{tenant_key.id}"
    return mode


def _resolve_rate_identity(request: Request, explicit_system: Optional[str]) -> str:
    ip_addr = _resolve_request_ip(request)
    user_agent = (request.headers.get("user-agent") or "").strip()
    system_label = _infer_client_system(user_agent, explicit_system)
    raw = f"{ip_addr}|{system_label}"
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return digest


def _seconds_until_utc_day_end() -> int:
    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


_memory_rate_counter: Dict[str, int] = {}


def _enforce_daily_rate_limit(
    request: Request,
    auth_context: Dict[str, Any],
    explicit_system: Optional[str],
) -> Dict[str, Any]:
    limit = _get_daily_limit_for_context(auth_context)
    if limit <= 0:
        return {"enabled": False, "limit": 0, "used": 0, "remaining": None, "scope": _build_rate_scope_id(auth_context)}

    day_key = datetime.utcnow().strftime("%Y%m%d")
    scope_id = _build_rate_scope_id(auth_context)
    identity = _resolve_rate_identity(request, explicit_system)
    redis_key = f"chat_rate:{scope_id}:{day_key}:{identity}"

    used = 0
    expires_in = _seconds_until_utc_day_end()
    redis_client = queue.connection
    try:
        if redis_client:
            used = int(redis_client.incr(redis_key))
            if used == 1:
                redis_client.expire(redis_key, expires_in + 60)
        else:
            raise RuntimeError("No redis connection")
    except Exception:
        used = _memory_rate_counter.get(redis_key, 0) + 1
        _memory_rate_counter[redis_key] = used

    if used > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily device rate limit exceeded ({limit}/day).",
        )

    remaining = max(0, limit - used)
    reset_at = (datetime.utcnow() + timedelta(seconds=expires_in)).replace(microsecond=0).isoformat() + "Z"
    return {
        "enabled": True,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "scope": scope_id,
        "reset_at": reset_at,
    }


def _generate_direct_chat_response(
    query: str,
    conversation_history: str = "",
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
) -> str:
    from google import genai
    from google.genai import types

    conversation_block = ""
    if conversation_history:
        conversation_block = f"\n\nRecent Conversation:\n{conversation_history}"

    default_system_prompt = (
        "You are a helpful, concise assistant for a production web application. "
        "Answer clearly, avoid hallucinations, and state assumptions when needed."
        f"{conversation_block}"
    )
    effective_system_prompt = (system_prompt or "").strip() or default_system_prompt
    effective_temperature = DIRECT_CHAT_TEMPERATURE if temperature is None else float(temperature)

    client = genai.Client()
    response = client.models.generate_content(
        model=DIRECT_CHAT_MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=effective_system_prompt,
            temperature=effective_temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    result = (response.text or "").strip()
    if not result:
        raise ValueError("Model returned an empty response")
    return result


def _iter_direct_chat_response_chunks(
    query: str,
    conversation_history: str = "",
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
):
    from google import genai
    from google.genai import types

    conversation_block = ""
    if conversation_history:
        conversation_block = f"\n\nRecent Conversation:\n{conversation_history}"

    default_system_prompt = (
        "You are a helpful, concise assistant for a production web application. "
        "Answer clearly, avoid hallucinations, and state assumptions when needed."
        f"{conversation_block}"
    )
    effective_system_prompt = (system_prompt or "").strip() or default_system_prompt
    effective_temperature = DIRECT_CHAT_TEMPERATURE if temperature is None else float(temperature)

    client = genai.Client()
    emitted_any = False
    stream = client.models.generate_content_stream(
        model=DIRECT_CHAT_MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=effective_system_prompt,
            temperature=effective_temperature,
            max_output_tokens=max_output_tokens,
        ),
    )

    for chunk in stream:
        chunk_text = getattr(chunk, "text", None)
        if not chunk_text:
            continue
        emitted_any = True
        yield chunk_text

    if emitted_any:
        return

    # Safety fallback: if upstream stream returns empty pieces.
    fallback = _generate_direct_chat_response(
        query=query,
        conversation_history=conversation_history,
        system_prompt=system_prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    if fallback:
        yield fallback


def _format_sse_event(event_name: str, data: Dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _normalize_collection_name(raw_name: Optional[str]) -> Optional[str]:
    clean = (raw_name or "").strip()
    return clean or None


def _filter_collections_by_scope(all_collections: List[str], auth_context: Dict[str, Any]) -> List[str]:
    tenant_key = auth_context.get("tenant_key")
    if not tenant_key:
        return list(all_collections)
    if tenant_key.allow_all_collections:
        return list(all_collections)
    allowed = set(_normalize_collection_scope(list(tenant_key.allowed_collections or [])))
    return [name for name in all_collections if name in allowed]


def _resolve_effective_collection_name(
    requested_collection_name: Optional[str],
    available_collections: List[str],
    auth_context: Dict[str, Any],
) -> Optional[str]:
    selected_collection_name = _normalize_collection_name(requested_collection_name)
    tenant_key = auth_context.get("tenant_key")

    if selected_collection_name and selected_collection_name not in available_collections:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge space '{selected_collection_name}' not found",
        )

    if not tenant_key:
        return selected_collection_name

    if not selected_collection_name:
        fallback = _normalize_collection_name(tenant_key.default_collection_name)
        if fallback and fallback in available_collections:
            selected_collection_name = fallback

    if tenant_key.allow_all_collections:
        return selected_collection_name

    allowed = set(_normalize_collection_scope(list(tenant_key.allowed_collections or [])))
    if not selected_collection_name and tenant_key.default_collection_name:
        # default exists but was not in available_collections; keep direct mode fallback.
        return None
    if selected_collection_name and selected_collection_name not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"API key does not allow collection '{selected_collection_name}'",
        )
    return selected_collection_name


def _build_client_chat_docs_payload(
    base_url: str,
    selected_collection_name: Optional[str],
    available_collections: List[str],
    auth_context: Dict[str, Any],
) -> Dict[str, Any]:
    tenant_key = auth_context.get("tenant_key")
    auth_mode = auth_context.get("mode") or "open"
    auth_required = bool(auth_context.get("auth_required"))
    docs_collection_name = selected_collection_name or "<your-knowledge-space>"
    request_collection_line = f'    "collection_name": "{docs_collection_name}",\n'
    api_key_header_line = (
        "\n  -H \"X-Client-Api-Key: <your-client-api-key>\""
        if auth_required
        else ""
    )
    js_api_key_header = (
        "      \"X-Client-Api-Key\": \"<your-client-api-key>\",\n"
        if auth_required
        else ""
    )
    widget_api_key_header = (
        "      'X-Client-Api-Key': '<your-client-api-key>',\n"
        if auth_required
        else ""
    )

    curl_example = (
        f"curl -X POST \"{base_url}/api/chat/respond\" \\\n"
        f"  -H \"Content-Type: application/json\"{api_key_header_line} \\\n"
        "  -d '{\n"
        "    \"message\": \"Hi, explain your platform in 3 bullets\",\n"
        f"{request_collection_line}"
        "    \"client_system\": \"web\",\n"
        "    \"device_fingerprint\": \"browser-fingerprint-v1\"\n"
        "  }'"
    )

    javascript_example = (
        f"const API_BASE_URL = \"{base_url}\";\n"
        "async function sendMessage(message) {\n"
        "  const response = await fetch(`${API_BASE_URL}/api/chat/respond`, {\n"
        "    method: \"POST\",\n"
        "    headers: {\n"
        "      \"Content-Type\": \"application/json\",\n"
        f"{js_api_key_header}"
        "    },\n"
        "    body: JSON.stringify({\n"
        "      message,\n"
        f"      collection_name: \"{docs_collection_name}\",\n"
        "      client_system: navigator.platform || \"web\",\n"
        "      device_fingerprint: [navigator.userAgent, navigator.language, Intl.DateTimeFormat().resolvedOptions().timeZone].join(\"|\")\n"
        "    })\n"
        "  });\n"
        "  if (!response.ok) throw new Error(`Chat request failed: ${response.status}`);\n"
        "  return response.json();\n"
        "}"
    )

    html_widget_template = (
        "<div id=\"async-rag-chat-widget\">\n"
        "  <input id=\"rag-input\" placeholder=\"Ask anything\" />\n"
        "  <button id=\"rag-send\">Send</button>\n"
        "  <pre id=\"rag-output\"></pre>\n"
        "</div>\n"
        "<script>\n"
        f"const API_BASE_URL = \"{base_url}\";\n"
        "document.getElementById('rag-send').onclick = async () => {\n"
        "  const message = document.getElementById('rag-input').value.trim();\n"
        "  if (!message) return;\n"
        "  const res = await fetch(`${API_BASE_URL}/api/chat/respond`, {\n"
        "    method: 'POST',\n"
        "    headers: {\n"
        "      'Content-Type': 'application/json',\n"
        f"{widget_api_key_header}"
        "    },\n"
        "    body: JSON.stringify({\n"
        "      message,\n"
        f"      collection_name: '{docs_collection_name}',\n"
        "      client_system: navigator.platform || 'web',\n"
        "      device_fingerprint: [navigator.userAgent, navigator.language].join('|')\n"
        "    })\n"
        "  });\n"
        "  const data = await res.json();\n"
        "  document.getElementById('rag-output').textContent = data.reply || data.detail || 'No response';\n"
        "};\n"
        "</script>"
    )

    sse_javascript_example = (
        f"const API_BASE_URL = \"{base_url}\";\n"
        "async function streamChat(message) {\n"
        "  const response = await fetch(`${API_BASE_URL}/api/chat/respond/stream`, {\n"
        "    method: \"POST\",\n"
        "    headers: {\n"
        "      \"Content-Type\": \"application/json\",\n"
        f"{js_api_key_header}"
        "    },\n"
        "    body: JSON.stringify({\n"
        "      message,\n"
        f"      collection_name: \"{docs_collection_name}\",\n"
        "      prompt_technique: \"balanced\"\n"
        "    })\n"
        "  });\n"
        "  const reader = response.body.getReader();\n"
        "  const decoder = new TextDecoder();\n"
        "  let buffer = \"\";\n"
        "  while (true) {\n"
        "    const { done, value } = await reader.read();\n"
        "    if (done) break;\n"
        "    buffer += decoder.decode(value, { stream: true });\n"
        "    const events = buffer.split(\"\\n\\n\");\n"
        "    buffer = events.pop() || \"\";\n"
        "    for (const rawEvent of events) {\n"
        "      const line = rawEvent.split(\"\\n\").find((entry) => entry.startsWith(\"data: \"));\n"
        "      if (!line) continue;\n"
        "      const payload = JSON.parse(line.slice(6));\n"
        "      if (payload.text) console.log(payload.text);\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

    return {
        "status": "success",
        "base_url": base_url,
        "endpoint": "/api/chat/respond",
        "stream_endpoint": "/api/chat/respond/stream",
        "method": "POST",
        "active_collection_name": selected_collection_name,
        "available_collections": available_collections,
        "auth": {
            "header": "X-Client-Api-Key",
            "required": auth_required,
            "mode": auth_mode,
        },
        "scope": {
            "allow_all_collections": bool(tenant_key.allow_all_collections) if tenant_key else True,
            "allowed_collections": _normalize_collection_scope(list(tenant_key.allowed_collections or [])) if tenant_key else [],
            "default_collection_name": tenant_key.default_collection_name if tenant_key else None,
            "key_name": tenant_key.name if tenant_key else None,
            "daily_limit_per_device": tenant_key.daily_limit_per_device if tenant_key else (CLIENT_CHAT_DAILY_LIMIT_PER_DEVICE or None),
            "default_prompt_technique": _normalize_prompt_technique(getattr(tenant_key, "default_prompt_technique", None)) if tenant_key else _normalize_prompt_technique(CLIENT_CHAT_DEFAULT_PROMPT_TECHNIQUE),
        },
        "supported_prompt_techniques": ["balanced", "concise", "detailed", "strict_context", "socratic"],
        "curl_example": curl_example,
        "javascript_example": javascript_example,
        "sse_javascript_example": sse_javascript_example,
        "html_widget_template": html_widget_template,
    }


@app.get("/")
def root():
    return {"message": "Bhai, server mast chal raha hai!"}


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """WhatsApp webhook fast-ack + async queue processing."""
    try:
        data = await request.json()
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
        if _should_ingest_conversation_message(payload):
            history_client_id = _resolve_whatsapp_client_id(payload)
            conversation_manager.add_message(history_client_id, "user", str(payload.get("body") or "").strip())
            payload["_conversation_ingested"] = True

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
            data = await websocket.receive_text()
            await websocket.send_json({"type": "ack", "message": "Message received"})
    except WebSocketDisconnect:
        manager.disconnect(client_id)


@app.post("/chat")
def chat(
    request: ChatRequest = None,
    query: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    message_id: Optional[str] = Query(None)
):
    # Support both JSON body and query parameters
    if request:
        query = request.query
        client_id = request.client_id
        message_id = request.message_id
    
    if not query:
        return {"error": "query parameter is required"}, 422
    
    
    # Store user's message in conversation history
    if client_id:
        conversation_manager.add_message(client_id, "user", query)
        
        # Get conversation history
        conversation_history = conversation_manager.get_context_string(client_id)
    else:
        conversation_history = ""
    
    # Enqueue job with conversation history and message_id
    job = queue.enqueue(process_query, query, client_id, conversation_history, message_id)
    return {"status": "queued", "job_id": job.id, "client_id": client_id, "message_id": message_id}


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


@app.post("/api/chat/respond")
def client_chat_respond(
    payload: ClientChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Synchronous chat API for client websites/apps."""
    auth_context = _resolve_client_chat_auth_context(request, db)
    rate_limit_info = _enforce_daily_rate_limit(request, auth_context, payload.client_system)

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="`message` is required")

    provided_client_id = (payload.client_id or "").strip()
    all_collections = list_qdrant_collections()
    selected_collection_name = _resolve_effective_collection_name(
        requested_collection_name=payload.collection_name,
        available_collections=all_collections,
        auth_context=auth_context,
    )
    resolved_client_id = provided_client_id or _derive_device_client_id(
        request=request,
        explicit_system=payload.client_system,
        device_fingerprint=payload.device_fingerprint,
    )
    strategy = "provided" if provided_client_id else "derived_ip_system"

    if payload.clear_history:
        conversation_manager.clear_history(resolved_client_id)

    conversation_manager.add_message(resolved_client_id, "user", message)
    conversation_history = conversation_manager.get_context_string(
        resolved_client_id,
        limit=payload.conversation_limit,
    )
    prompt_technique = _resolve_effective_prompt_technique(payload.prompt_technique, auth_context)
    effective_system_prompt = _resolve_effective_system_prompt(payload.system_prompt, auth_context)
    effective_user_prompt_template = _resolve_effective_user_prompt_template(payload.user_prompt_template, auth_context)
    effective_user_prompt = _build_effective_user_prompt(
        message=message,
        conversation_history=conversation_history,
        technique=prompt_technique,
        user_prompt_template=effective_user_prompt_template,
        collection_name=selected_collection_name,
    )

    try:
        if selected_collection_name:
            # Reuse existing RAG pipeline with selected knowledge space.
            reply = process_query(
                query=message,
                client_id=resolved_client_id,
                conversation_history=conversation_history,
                collection_name=selected_collection_name,
                system_prompt=effective_system_prompt,
                user_prompt_template=effective_user_prompt,
                emit_side_effects=False,
            )
            response_mode = "rag"
        else:
            reply = _generate_direct_chat_response(
                query=effective_user_prompt,
                conversation_history=conversation_history,
                system_prompt=effective_system_prompt,
                temperature=payload.temperature,
                max_output_tokens=payload.max_output_tokens,
            )
            response_mode = "direct"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Direct chat failed: {e}")

    conversation_manager.add_message(resolved_client_id, "assistant", reply)

    return {
        "status": "success",
        "reply": reply,
        "client_id": resolved_client_id,
        "client_id_strategy": strategy,
        "response_mode": response_mode,
        "collection_name": selected_collection_name,
        "prompt_technique": prompt_technique,
        "rate_limit": rate_limit_info,
        "model": DIRECT_CHAT_MODEL,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/chat/respond/stream")
def client_chat_respond_stream(
    payload: ClientChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """SSE streaming chat API for client websites/apps."""
    auth_context = _resolve_client_chat_auth_context(request, db)
    rate_limit_info = _enforce_daily_rate_limit(request, auth_context, payload.client_system)

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="`message` is required")

    provided_client_id = (payload.client_id or "").strip()
    all_collections = list_qdrant_collections()
    selected_collection_name = _resolve_effective_collection_name(
        requested_collection_name=payload.collection_name,
        available_collections=all_collections,
        auth_context=auth_context,
    )
    resolved_client_id = provided_client_id or _derive_device_client_id(
        request=request,
        explicit_system=payload.client_system,
        device_fingerprint=payload.device_fingerprint,
    )
    strategy = "provided" if provided_client_id else "derived_ip_system"

    if payload.clear_history:
        conversation_manager.clear_history(resolved_client_id)

    conversation_manager.add_message(resolved_client_id, "user", message)
    conversation_history = conversation_manager.get_context_string(
        resolved_client_id,
        limit=payload.conversation_limit,
    )
    prompt_technique = _resolve_effective_prompt_technique(payload.prompt_technique, auth_context)
    effective_system_prompt = _resolve_effective_system_prompt(payload.system_prompt, auth_context)
    effective_user_prompt_template = _resolve_effective_user_prompt_template(payload.user_prompt_template, auth_context)
    effective_user_prompt = _build_effective_user_prompt(
        message=message,
        conversation_history=conversation_history,
        technique=prompt_technique,
        user_prompt_template=effective_user_prompt_template,
        collection_name=selected_collection_name,
    )

    def event_stream():
        final_reply_parts: List[str] = []
        response_mode = "rag" if selected_collection_name else "direct"
        yield _format_sse_event(
            "meta",
            {
                "status": "streaming",
                "client_id": resolved_client_id,
                "client_id_strategy": strategy,
                "response_mode": response_mode,
                "collection_name": selected_collection_name,
                "prompt_technique": prompt_technique,
                "rate_limit": rate_limit_info,
                "model": DIRECT_CHAT_MODEL,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        try:
            if selected_collection_name:
                rag_reply = process_query(
                    query=message,
                    client_id=resolved_client_id,
                    conversation_history=conversation_history,
                    collection_name=selected_collection_name,
                    system_prompt=effective_system_prompt,
                    user_prompt_template=effective_user_prompt,
                    emit_side_effects=False,
                )
                chunk_size = 180
                for i in range(0, len(rag_reply), chunk_size):
                    chunk = rag_reply[i : i + chunk_size]
                    if not chunk:
                        continue
                    final_reply_parts.append(chunk)
                    yield _format_sse_event("token", {"text": chunk})
            else:
                for chunk in _iter_direct_chat_response_chunks(
                    query=effective_user_prompt,
                    conversation_history=conversation_history,
                    system_prompt=effective_system_prompt,
                    temperature=payload.temperature,
                    max_output_tokens=payload.max_output_tokens,
                ):
                    if not chunk:
                        continue
                    final_reply_parts.append(chunk)
                    yield _format_sse_event("token", {"text": chunk})

            full_reply = "".join(final_reply_parts).strip()
            if not full_reply:
                raise ValueError("Model returned empty stream")
            conversation_manager.add_message(resolved_client_id, "assistant", full_reply)
            yield _format_sse_event(
                "done",
                {
                    "status": "success",
                    "reply": full_reply,
                    "client_id": resolved_client_id,
                    "client_id_strategy": strategy,
                    "response_mode": response_mode,
                    "collection_name": selected_collection_name,
                    "prompt_technique": prompt_technique,
                    "rate_limit": rate_limit_info,
                    "model": DIRECT_CHAT_MODEL,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            )
        except Exception as exc:
            yield _format_sse_event("error", {"status": "error", "detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/chat/docs")
def get_client_chat_docs(
    request: Request,
    collection_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
):
    """Return quick integration docs/templates for client websites."""
    auth_context = _resolve_client_chat_auth_context(request, db)
    base_url = str(request.base_url).rstrip("/")
    all_collections = list_qdrant_collections()
    available_collections = _filter_collections_by_scope(all_collections, auth_context)
    selected_collection_name = _resolve_effective_collection_name(
        requested_collection_name=collection_name,
        available_collections=all_collections,
        auth_context=auth_context,
    )
    return _build_client_chat_docs_payload(
        base_url=base_url,
        selected_collection_name=selected_collection_name,
        available_collections=available_collections,
        auth_context=auth_context,
    )


@app.get("/api/chat/keys")
def list_client_api_keys(request: Request, db: Session = Depends(get_db_session)):
    _require_client_chat_admin_key(request)
    records = db.query(ClientApiKey).order_by(ClientApiKey.created_at.desc()).all()
    return {
        "status": "success",
        "total": len(records),
        "keys": [_serialize_client_api_key_record(record) for record in records],
    }


@app.post("/api/chat/keys")
def create_client_api_key(
    payload: ClientApiKeyCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    _require_client_chat_admin_key(request)
    clean_name = payload.name.strip()
    if len(clean_name) < 3:
        raise HTTPException(status_code=400, detail="name must be at least 3 visible characters")

    allowed_collections = _normalize_collection_scope(payload.allowed_collections)
    default_collection_name = _normalize_collection_name(payload.default_collection_name)
    default_prompt_technique = _normalize_prompt_technique(payload.default_prompt_technique)
    default_system_prompt = (payload.default_system_prompt or "").strip() or None
    default_user_prompt_template = (payload.default_user_prompt_template or "").strip() or None
    daily_limit_per_device = payload.daily_limit_per_device
    if daily_limit_per_device is not None and int(daily_limit_per_device) <= 0:
        daily_limit_per_device = None

    if not payload.allow_all_collections:
        if not allowed_collections and not default_collection_name:
            raise HTTPException(
                status_code=400,
                detail="Provide allowed_collections or a default_collection_name when allow_all_collections is false",
            )
        _validate_allowed_collections(allowed_collections)
        if default_collection_name:
            _validate_allowed_collections([default_collection_name])
            if allowed_collections and default_collection_name not in allowed_collections:
                raise HTTPException(
                    status_code=400,
                    detail="default_collection_name must be included in allowed_collections",
                )
    elif default_collection_name:
        _validate_allowed_collections([default_collection_name])

    existing_name = db.query(ClientApiKey).filter(ClientApiKey.name == clean_name).first()
    if existing_name:
        raise HTTPException(status_code=409, detail="A key with this name already exists")

    raw_key = _generate_client_api_key()
    key_prefix = raw_key[:18]
    record = ClientApiKey(
        name=clean_name,
        description=(payload.description or "").strip() or None,
        key_hash=_hash_client_api_key(raw_key),
        key_prefix=key_prefix,
        allow_all_collections=payload.allow_all_collections,
        allowed_collections=allowed_collections if not payload.allow_all_collections else [],
        default_collection_name=default_collection_name,
        daily_limit_per_device=daily_limit_per_device,
        default_system_prompt=default_system_prompt,
        default_user_prompt_template=default_user_prompt_template,
        default_prompt_technique=default_prompt_technique,
        is_active=payload.is_active,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "api_key": raw_key,
        "key": _serialize_client_api_key_record(record),
    }


@app.patch("/api/chat/keys/{key_id}")
def update_client_api_key(
    key_id: str,
    payload: ClientApiKeyUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    _require_client_chat_admin_key(request)
    try:
        key_uuid = uuid.UUID(str(key_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid API key id format")

    record = db.query(ClientApiKey).filter(ClientApiKey.id == key_uuid).first()
    if not record:
        raise HTTPException(status_code=404, detail="API key not found")

    if payload.name is not None:
        next_name = payload.name.strip()
        if not next_name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        name_conflict = db.query(ClientApiKey).filter(
            ClientApiKey.name == next_name,
            ClientApiKey.id != record.id,
        ).first()
        if name_conflict:
            raise HTTPException(status_code=409, detail="Another key already uses this name")
        record.name = next_name

    if payload.description is not None:
        record.description = (payload.description or "").strip() or None
    if payload.is_active is not None:
        record.is_active = payload.is_active
    if payload.allow_all_collections is not None:
        record.allow_all_collections = payload.allow_all_collections

    if payload.allowed_collections is not None:
        normalized_scope = _normalize_collection_scope(payload.allowed_collections)
        _validate_allowed_collections(normalized_scope)
        record.allowed_collections = normalized_scope

    if payload.default_collection_name is not None:
        next_default = _normalize_collection_name(payload.default_collection_name)
        if next_default:
            _validate_allowed_collections([next_default])
        record.default_collection_name = next_default

    if payload.daily_limit_per_device is not None:
        record.daily_limit_per_device = None if payload.daily_limit_per_device <= 0 else payload.daily_limit_per_device
    if payload.default_system_prompt is not None:
        record.default_system_prompt = (payload.default_system_prompt or "").strip() or None
    if payload.default_user_prompt_template is not None:
        record.default_user_prompt_template = (payload.default_user_prompt_template or "").strip() or None
    if payload.default_prompt_technique is not None:
        record.default_prompt_technique = _normalize_prompt_technique(payload.default_prompt_technique)

    if not record.allow_all_collections:
        allowed_scope = set(_normalize_collection_scope(list(record.allowed_collections or [])))
        if record.default_collection_name and record.default_collection_name not in allowed_scope:
            raise HTTPException(
                status_code=400,
                detail="default_collection_name must be included in allowed_collections when allow_all_collections is false",
            )

    rotated_api_key: Optional[str] = None
    if payload.rotate_key:
        rotated_api_key = _generate_client_api_key()
        record.key_hash = _hash_client_api_key(rotated_api_key)
        record.key_prefix = rotated_api_key[:18]

    db.add(record)
    db.commit()
    db.refresh(record)

    response: Dict[str, Any] = {"status": "success", "key": _serialize_client_api_key_record(record)}
    if rotated_api_key:
        response["api_key"] = rotated_api_key
    return response


@app.delete("/api/chat/keys/{key_id}")
def delete_client_api_key(key_id: str, request: Request, db: Session = Depends(get_db_session)):
    _require_client_chat_admin_key(request)
    try:
        key_uuid = uuid.UUID(str(key_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid API key id format")

    record = db.query(ClientApiKey).filter(ClientApiKey.id == key_uuid).first()
    if not record:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(record)
    db.commit()
    return {"status": "success", "deleted_id": str(key_uuid)}


class WorkerScaleUpdate(BaseModel):
    desired_count: int


def _clamp_worker_count(raw_value: int) -> int:
    return min(RQ_WORKER_MAX_COUNT, max(RQ_WORKER_MIN_COUNT, int(raw_value)))


def _safe_webhook_job_id(message_id: str) -> str:
    digest = hashlib.sha1(str(message_id).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"webhook_{digest}"


def _resolve_whatsapp_client_id(payload: Dict[str, Any]) -> str:
    """Resolve conversation key per sender (participant) instead of group chat id."""
    candidates = [
        payload.get("participant"),
        payload.get("author"),
        payload.get("_data", {}).get("key", {}).get("participant"),
        payload.get("_data", {}).get("key", {}).get("participantAlt"),
        payload.get("from"),
        payload.get("chatId"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _should_ingest_conversation_message(payload: Dict[str, Any]) -> bool:
    history_client_id = _resolve_whatsapp_client_id(payload)
    body = str(payload.get("body") or "").strip()
    from_me = bool(payload.get("fromMe"))
    message_id = (payload.get("message_id") or payload.get("id") or "").strip()
    if not history_client_id or not body or from_me:
        return False

    dedupe_ttl = max(0, int(os.getenv("WEBHOOK_DEDUP_TTL_SECONDS", "600")))
    if dedupe_ttl <= 0 or not message_id:
        return True

    dedupe_key = f"conversation:ingress:{message_id}"
    try:
        inserted = queue.connection.set(dedupe_key, "1", ex=dedupe_ttl, nx=True)
        return bool(inserted)
    except Exception:
        return True


def _cleanup_stale_flow_executions(db: Session, stale_before: datetime) -> int:
    """Mark crashed/stale running executions as failed so dashboard counters stay accurate."""
    stale_executions = db.query(FlowExecution).filter(
        FlowExecution.status == "running",
        FlowExecution.started_at < stale_before,
    ).all()

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
        flow_recent_total = db.query(FlowExecution).filter(
            FlowExecution.started_at >= window_start
        ).count()
        flow_recent_completed = db.query(FlowExecution).filter(
            FlowExecution.started_at >= window_start,
            FlowExecution.status == "completed",
        ).count()
        flow_recent_failed = db.query(FlowExecution).filter(
            FlowExecution.started_at >= window_start,
            FlowExecution.status == "failed",
        ).count()
        flow_running_now = db.query(FlowExecution).filter(
            FlowExecution.status == "running",
            FlowExecution.started_at >= running_cutoff,
        ).count()
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

@app.get("/api/collections")
def get_collections(db: Session = Depends(get_db_session)):
    """Saari knowledge collections ki list"""
    collections = db.query(KnowledgeBase).all()
    return {"collections": [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "created_at": c.created_at.isoformat()
        } for c in collections
    ]}

@app.post("/api/collections")
def create_new_collection(data: CollectionCreate, db: Session = Depends(get_db_session)):
    """Nayi collection banate hain (DB aur Qdrant dono mein)"""
    existing = db.query(KnowledgeBase).filter(KnowledgeBase.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bhai, ye collection toh pehle se hai!")
    
    kb = KnowledgeBase(name=data.name, description=data.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
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
        db_collections = db.query(KnowledgeBase).all()
        db_names = {c.name for c in db_collections}
        
        added_count = 0
        for name in qdrant_names:
            if name not in db_names:
                new_kb = KnowledgeBase(name=name, description="Imported from Qdrant")
                db.add(new_kb)
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

@app.post("/api/collections/{kb_name}/upload")
async def upload_documents(
    kb_name: str,
    force_recreate: bool = Query(default=False),
    url_max_pages: Optional[int] = Query(default=None, ge=1, le=2000),
    url_use_sitemap: bool = Query(default=True),
    chunk_size: int = Query(default=1000, ge=200, le=8000),
    chunk_overlap: int = Query(default=200, ge=0, le=2000),
    files: Optional[List[UploadFile]] = File(default=None),
    urls: Optional[List[str]] = Form(default=None),
    db: Session = Depends(get_db_session),
):
    """Upload and index PDFs and/or website URLs into a collection."""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.name == kb_name).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")
    
    temp_dir = tempfile.mkdtemp()
    file_paths = []
    normalized_urls: List[str] = []
    
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
                chunk_size,
                chunk_overlap,
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
                chunk_size,
                chunk_overlap,
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
    group_ids: List[str] = [] 


class WorkspaceStatusUpdate(BaseModel):
    is_active: bool

@app.get("/api/workspaces")
def get_workspaces(db: Session = Depends(get_db_session)):
    """Saare workspaces ki list nikaalte hain"""
    workspaces = db.query(Workspace).all()
    result = []
    for ws in workspaces:
        # Get assigned groups
        groups = db.query(WhatsAppGroup).join(WorkspaceGroup).filter(WorkspaceGroup.workspace_id == ws.id).all()
        result.append({
            "id": str(ws.id),
            "name": ws.name,
            "is_active": ws.is_active,
            "knowledge_base": {
                "id": str(ws.knowledge_base.id),
                "name": ws.knowledge_base.name
            } if ws.knowledge_base else None,
            "groups": [{"id": str(g.id), "name": g.name, "chat_id": g.chat_id} for g in groups]
        })
    return {"workspaces": result}

@app.post("/api/workspaces")
def create_workspace(data: WorkspaceCreate, db: Session = Depends(get_db_session)):
    """Create a new workspace and assign groups"""
    ws = Workspace(
        name=data.name,
        knowledge_base_id=data.knowledge_base_id,
        system_prompt=data.system_prompt,
        user_prompt_template=data.user_prompt_template,
        is_active=True
    )
    db.add(ws)
    db.flush() # Get ID
    
    # Assign groups
    for group_id in data.group_ids:
        db.add(WorkspaceGroup(workspace_id=ws.id, group_id=group_id))
    
    db.commit()
    db.refresh(ws)
    return ws

@app.get("/api/workspaces/{workspace_id}")
def get_workspace(workspace_id: uuid.UUID, db: Session = Depends(get_db_session)):
    """Get a specific workspace with full details"""
    print(f"DEBUG: >>> Hit GET /api/workspaces/[{workspace_id}] <<<")
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    
    if not ws:
        print(f"DEBUG: >>> Workspace [{workspace_id}] NOT found in DB <<<")
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    print(f"DEBUG: Found workspace {ws.name}")
    # Get assigned groups
    groups = db.query(WhatsAppGroup).join(WorkspaceGroup).filter(WorkspaceGroup.workspace_id == ws.id).all()
    
    return {
        "id": str(ws.id),
        "name": ws.name,
        "knowledge_base_id": str(ws.knowledge_base_id) if ws.knowledge_base_id else None,
        "system_prompt": ws.system_prompt,
        "user_prompt_template": ws.user_prompt_template,
        "is_active": ws.is_active,
        "groups": [{"id": str(g.id), "name": g.name, "chat_id": g.chat_id} for g in groups]
    }

@app.put("/api/workspaces/{workspace_id}")
def update_workspace(workspace_id: uuid.UUID, data: WorkspaceCreate, db: Session = Depends(get_db_session)):
    """Update an existing workspace"""
    print(f"DEBUG: Hit PUT /api/workspaces/{workspace_id}")
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    ws.name = data.name
    ws.knowledge_base_id = uuid.UUID(data.knowledge_base_id) if data.knowledge_base_id else None
    ws.system_prompt = data.system_prompt
    ws.user_prompt_template = data.user_prompt_template
    
    # Update groups: Clear and re-assign
    db.query(WorkspaceGroup).filter(WorkspaceGroup.workspace_id == ws.id).delete()
    for group_id in data.group_ids:
        db.add(WorkspaceGroup(workspace_id=ws.id, group_id=uuid.UUID(group_id)))
        
    db.commit()
    print(f"DEBUG: Updated workspace {ws.name}")
    return {"status": "success", "message": "Workspace updated"}

@app.delete("/api/workspaces/{workspace_id}")
def delete_workspace(workspace_id: uuid.UUID, db: Session = Depends(get_db_session)):
    """Delete a workspace and its group assignments"""
    print(f"DEBUG: Hit DELETE /api/workspaces/{workspace_id}")
    ensure_workspace_flow_schema(db)
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # Delete group assignments
    db.query(WorkspaceGroup).filter(WorkspaceGroup.workspace_id == ws.id).delete()
    
    # Keep logic layers, just unassign from this workspace
    db.query(Flow).filter(Flow.workspace_id == ws.id).update(
        {
            Flow.workspace_id: None,
            Flow.updated_at: datetime.now(),
        },
        synchronize_session=False,
    )

    db.query(WorkspaceFlow).filter(WorkspaceFlow.workspace_id == ws.id).delete(synchronize_session=False)
    
    db.delete(ws)
    db.commit()
    print(f"DEBUG: Deleted workspace {workspace_id}")
    return {"status": "success", "message": "Workspace deleted"}


# ============================================================================
# GROUPS: WhatsApp groups ka intejam
# ============================================================================

@app.get("/api/groups")
def get_groups(db: Session = Depends(get_db_session)):
    """Database se saare WhatsApp groups nikaalo"""
    groups = db.query(WhatsAppGroup).all()
    
    result = []
    for group in groups:
        # Get assigned flows
        flow_groups = db.query(FlowGroup).filter(FlowGroup.group_id == group.id).all()
        assigned_flows = []
        for fg in flow_groups:
            flow = db.query(Flow).filter(Flow.id == fg.flow_id).first()
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


@app.post("/api/groups/{group_id}/flows/{flow_id}")
def assign_flow(group_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Assign a flow to a group"""
    # Check if assignment already exists
    existing = db.query(FlowGroup).filter(
        FlowGroup.group_id == group_id,
        FlowGroup.flow_id == flow_id
    ).first()
    
    if existing:
        return {"status": "success", "message": "Flow already assigned"}
    
    # Create new assignment
    new_assignment = FlowGroup(group_id=group_id, flow_id=flow_id)
    db.add(new_assignment)
    db.commit()
    
    return {"status": "success", "message": "Flow assigned successfully"}

@app.delete("/api/groups/{group_id}/flows/{flow_id}")
def unassign_flow(group_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Remove a flow assignment from a group"""
    db.query(FlowGroup).filter(
        FlowGroup.group_id == group_id,
        FlowGroup.flow_id == flow_id
    ).delete()
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
            existing_group = db.query(WhatsAppGroup).filter(
                WhatsAppGroup.chat_id == waha_group["chat_id"]
            ).first()
            
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
                new_group = WhatsAppGroup(
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
        group = db.query(WhatsAppGroup).filter(WhatsAppGroup.id == group_id).first()
        
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
    group = db.query(WhatsAppGroup).filter(WhatsAppGroup.id == group_id).first()
    
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
    query = db.query(Flow)
    if workspace_id:
        workspace_uuid = uuid.UUID(workspace_id)
        query = query.outerjoin(
            WorkspaceFlow, WorkspaceFlow.flow_id == Flow.id
        ).filter(
            or_(
                WorkspaceFlow.workspace_id == workspace_uuid,
                Flow.workspace_id == workspace_uuid,  # legacy fallback
            )
        ).distinct()
    flows = query.order_by(Flow.created_at.asc()).all()

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

    new_flow = Flow(
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
            for row in db.query(Workspace.id).filter(Workspace.id.in_(workspace_uuids)).all()
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
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    
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
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    
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
            for row in db.query(Workspace.id).filter(Workspace.id.in_(workspace_uuids)).all()
        }
        missing_workspace_ids = [str(ws_id) for ws_id in workspace_uuids if ws_id not in existing_workspace_ids]
        if missing_workspace_ids:
            raise HTTPException(status_code=404, detail=f"Workspace not found: {', '.join(missing_workspace_ids)}")
        db.query(WorkspaceFlow).filter(WorkspaceFlow.flow_id == flow.id).delete(synchronize_session=False)
        for workspace_uuid in workspace_uuids:
            _attach_flow_to_workspace(db, workspace_uuid, flow.id)

    elif "workspace_id" in update_payload:
        # Legacy compatibility: workspace_id now means "attach one" (or clear all if null).
        if flow_data.workspace_id:
            workspace_uuid = uuid.UUID(flow_data.workspace_id)
            workspace_exists = db.query(Workspace.id).filter(Workspace.id == workspace_uuid).first()
            if not workspace_exists:
                raise HTTPException(status_code=404, detail="Workspace not found")
            _attach_flow_to_workspace(db, workspace_uuid, flow.id)
        else:
            db.query(WorkspaceFlow).filter(WorkspaceFlow.flow_id == flow.id).delete(synchronize_session=False)

    # Legacy column is not the source of truth anymore.
    flow.workspace_id = None
    flow.updated_at = datetime.now()
    db.commit()
    
    return {"status": "success", "flow_id": str(flow.id)}


@app.post("/api/workspaces/{workspace_id}/flows/{flow_id}")
def attach_workspace_flow(workspace_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Attach a reusable logic layer to a workspace."""
    ensure_workspace_flow_schema(db)
    workspace_uuid = uuid.UUID(workspace_id)
    flow_uuid = uuid.UUID(flow_id)

    workspace_exists = db.query(Workspace.id).filter(Workspace.id == workspace_uuid).first()
    if not workspace_exists:
        raise HTTPException(status_code=404, detail="Workspace not found")

    flow_exists = db.query(Flow.id).filter(Flow.id == flow_uuid).first()
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


@app.delete("/api/workspaces/{workspace_id}/flows/{flow_id}")
def detach_workspace_flow(workspace_id: str, flow_id: str, db: Session = Depends(get_db_session)):
    """Detach a logic layer from one workspace only."""
    ensure_workspace_flow_schema(db)
    workspace_uuid = uuid.UUID(workspace_id)
    flow_uuid = uuid.UUID(flow_id)

    deleted = db.query(WorkspaceFlow).filter(
        WorkspaceFlow.workspace_id == workspace_uuid,
        WorkspaceFlow.flow_id == flow_uuid,
    ).delete(synchronize_session=False)
    db.commit()

    return {
        "status": "success",
        "message": "Logic layer detached from workspace",
        "workspace_id": workspace_id,
        "flow_id": flow_id,
        "detached": bool(deleted),
    }


@app.delete("/api/flows/{flow_id}")
def delete_flow(flow_id: str, db: Session = Depends(get_db_session)):
    """Delete a flow"""
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    
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
    query = db.query(FlowExecution)
    
    if flow_id:
        query = query.filter(FlowExecution.flow_id == flow_id)
        
    total = query.count()
    
    executions = query.order_by(FlowExecution.started_at.desc()) \
                      .offset(offset).limit(limit).all()
    
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
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
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

@app.patch("/api/workspaces/{workspace_id}/toggle")
def toggle_workspace(workspace_id: str, db: Session = Depends(get_db_session)):
    """Toggle workspace active status"""
    try:
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
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


@app.patch("/api/workspaces/{workspace_id}/status")
def set_workspace_status(workspace_id: str, data: WorkspaceStatusUpdate, db: Session = Depends(get_db_session)):
    """Set workspace active status explicitly to avoid accidental inverse toggles."""
    try:
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
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
