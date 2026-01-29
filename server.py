from dotenv import load_dotenv
import json
from datetime import datetime
import os
from redis import Redis
from pydantic import BaseModel
from typing import Dict, List, Any, Optional

# Ye lo, load ho gaya environment
load_dotenv()

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from client.rq_client import queue
from queues.worker import process_query
from sqlalchemy.orm import Session
import shutil
import tempfile
import uuid

# Database aur engines ke saaman
from database import get_db_session, WhatsAppGroup, Flow, FlowGroup, FlowExecution, KnowledgeBase, Workspace, WorkspaceGroup
from waha_client import waha_client
from flow_engine import flow_engine
from workspace_engine import workspace_engine
from rag_utils import create_qdrant_collection, index_pdfs_to_collection, list_qdrant_collections

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
                            "text": "{{action_1.result}}",
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

# Add CORS middleware to allow browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# WhatsApp webhook models
class WhatsAppPayload(BaseModel):
    chatId: str
    id: str
    body: Optional[str] = ""
    mentionedIds: Optional[List[str]] = []


class WAHAWebhook(BaseModel):
    payload: WhatsAppPayload


@app.get("/")
def root():
    return {"message": "Bhai, server mast chal raha hai!"}


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """WhatsApp se messages yahan aate hain (n8n ki zaroorat nahi)"""
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
            
        chat_id = payload.get("chatId") or payload.get("from")
        
        # Database check karte hain manually
        from database.db import SessionLocal
        db = SessionLocal()
        
        try:
            # 1. Pehle dekho group enabled hai ya nahi
            group = db.query(WhatsAppGroup).filter(
                WhatsAppGroup.chat_id == chat_id,
                WhatsAppGroup.is_enabled == True
            ).first()
            
            if not group:
                return {"status": "ignored", "reason": "group disabled or not in database"}
            
            print(f"✅ Group mil gaya: {group.name}")
            group.last_message_at = datetime.now()
            db.commit()

            # 2. Workspace wala logic (Naya architecture)
            workspace_group = db.query(WorkspaceGroup).join(Workspace).filter(
                WorkspaceGroup.group_id == group.id,
                Workspace.is_active == True
            ).first()
            
            if workspace_group:
                workspace = db.query(Workspace).filter(Workspace.id == workspace_group.workspace_id).first()
                print(f"🏢 Workspace execute kar rahe hain: {workspace.name}")
                
                result = await workspace_engine.execute_workspace(
                    workspace=workspace,
                    payload=payload,
                    db=db
                )
                
                return {
                    "status": "workspace_executed",
                    "workspace_id": str(workspace.id),
                    "result": result
                }

            # 3. Flow wala logic (Purana/Fallback)
            flow_group = db.query(FlowGroup).join(Flow).filter(
                FlowGroup.group_id == group.id,
                Flow.is_enabled == True
            ).first()
            
            if flow_group:
                flow = db.query(Flow).filter(Flow.id == flow_group.flow_id).first()
                print(f"🌊 Fallback Flow chal raha hai: {flow.name}")
                
                execution_result = await flow_engine.execute_flow(
                    flow=flow,
                    trigger_data=payload,
                    db=db
                )
                
                return {
                    "status": "flow_executed", 
                    "flow_id": str(flow.id),
                    "execution_id": str(execution_result.id)
                }
            
            print(f"⚠️ Is group ({group.name}) ke liye kuch nahi mila.")
            return {"status": "ignored", "reason": "no workspace or flow assigned"}
                
        except Exception as e:
            print(f"❌ Kuch gadbad ho gayi execution mein: {e}")
            return {"status": "error", "message": f"Execution error: {str(e)}"}
        finally:
            db.close()
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
    """Sync collections from Qdrant to local DB"""
    try:
        qdrant_names = list_qdrant_collections()
        db_collections = db.query(KnowledgeBase).all()
        db_names = {c.name for c in db_collections}
        
        added_count = 0
        for name in qdrant_names:
            if name not in db_names:
                new_kb = KnowledgeBase(name=name, description="Imported from Qdrant")
                db.add(new_kb)
                added_count += 1
        
        db.commit()
        return {"status": "success", "added_count": added_count, "total_found": len(qdrant_names)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@app.post("/api/collections/{kb_name}/upload")
async def upload_documents(kb_name: str, files: List[UploadFile] = File(...), db: Session = Depends(get_db_session)):
    """Upload and index multiple PDFs into a collection"""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.name == kb_name).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")
    
    temp_dir = tempfile.mkdtemp()
    file_paths = []
    
    try:
        for file in files:
            if not file.filename.lower().endswith(".pdf"):
                continue
                
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_paths.append(file_path)
            
        if not file_paths:
            raise HTTPException(status_code=400, detail="No PDF files provided")
            
        # Index files
        chunk_count = index_pdfs_to_collection(kb_name, file_paths)
        
        return {
            "status": "success",
            "message": f"Successfully indexed {len(file_paths)} files with {chunk_count} chunks into '{kb_name}'",
            "file_count": len(file_paths),
            "chunk_count": chunk_count
        }
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
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # Delete group assignments
    db.query(WorkspaceGroup).filter(WorkspaceGroup.workspace_id == ws.id).delete()
    
    # Delete flows associated with workspace
    db.query(Flow).filter(Flow.workspace_id == ws.id).delete()
    
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
    definition: Dict[str, Any]
    trigger_type: str = "whatsapp_mention"
    trigger_config: Dict[str, Any] = {}
    is_enabled: bool = True

class FlowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    definition: Optional[Dict[str, Any]] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


@app.get("/api/flows")
def get_flows(workspace_id: Optional[str] = None, db: Session = Depends(get_db_session)):
    """List all flows, optionally filtered by workspace"""
    query = db.query(Flow)
    if workspace_id:
        query = query.filter(Flow.workspace_id == uuid.UUID(workspace_id))
    flows = query.all()
    
    result = []
    for flow in flows:
        result.append({
            "id": str(flow.id),
            "name": flow.name,
            "description": flow.description,
            "trigger_type": flow.trigger_type,
            "is_enabled": flow.is_enabled,
            "created_at": flow.created_at.isoformat() if flow.created_at else None,
            "updated_at": flow.updated_at.isoformat() if flow.updated_at else None
        })
    
    return {"flows": result, "total": len(result)}


@app.get("/api/templates")
def get_templates():
    """Get processed flow templates"""
    return {"templates": FLOW_TEMPLATES, "total": len(FLOW_TEMPLATES)}


@app.post("/api/flows")
def create_flow(flow_data: FlowCreate, db: Session = Depends(get_db_session)):
    """Create a new flow"""
    # Create default definition if empty
    definition = flow_data.definition
    if not definition or not definition.get("nodes"):
        definition = {"nodes": [], "edges": []}
        
    new_flow = Flow(
        workspace_id=uuid.UUID(flow_data.workspace_id) if flow_data.workspace_id else None,
        name=flow_data.name,
        description=flow_data.description,
        definition=definition,
        trigger_type=flow_data.trigger_type,
        trigger_config=flow_data.trigger_config,
        is_enabled=flow_data.is_enabled
    )
    
    db.add(new_flow)
    db.commit()
    db.refresh(new_flow)
    
    return {"status": "success", "flow_id": str(new_flow.id)}


@app.get("/api/flows/{flow_id}")
def get_flow(flow_id: str, db: Session = Depends(get_db_session)):
    """Get a specific flow with definition"""
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    return {
        "id": str(flow.id),
        "name": flow.name,
        "description": flow.description,
        "definition": flow.definition,
        "trigger_type": flow.trigger_type,
        "trigger_config": flow.trigger_config,
        "is_enabled": flow.is_enabled,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None
    }


@app.put("/api/flows/{flow_id}")
def update_flow(flow_id: str, flow_data: FlowUpdate, db: Session = Depends(get_db_session)):
    """Update an existing flow"""
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    if flow_data.name is not None:
        flow.name = flow_data.name
    if flow_data.description is not None:
        flow.description = flow_data.description
    if flow_data.workspace_id is not None:
        flow.workspace_id = uuid.UUID(flow_data.workspace_id) if flow_data.workspace_id else None
    if flow_data.definition is not None:
        flow.definition = flow_data.definition
    if flow_data.trigger_type is not None:
        flow.trigger_type = flow_data.trigger_type
    if flow_data.trigger_config is not None:
        flow.trigger_config = flow_data.trigger_config
    if flow_data.is_enabled is not None:
        flow.is_enabled = flow_data.is_enabled
        
    flow.updated_at = datetime.now()
    db.commit()
    
    return {"status": "success", "flow_id": str(flow.id)}


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
