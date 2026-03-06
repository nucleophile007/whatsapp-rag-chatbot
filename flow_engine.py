"""
Flow Execution Engine
Handles the parsing and execution of automation flows defined in the database.
"""

import re
import json
import ast
import logging
import os
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
import asyncio

from database import Flow, FlowExecution, FlowGroup, WhatsAppGroup, Workspace, NodeType, get_db
from waha_client import waha_client
from conversation_manager import conversation_manager

logger = logging.getLogger(__name__)

class FlowContext:
    """Flow chalte waqt variables aur data yahan save rehta hai"""
    
    def __init__(self, trigger_data: Dict[str, Any], db: Session):
        self.data = {
            "trigger": trigger_data,
            "nodes": {},
            "variables": {}
        }
        self.db = db
    
    def set_node_output(self, node_id: str, output: Any):
        """Node ka result store karte hain"""
        self.data["nodes"][node_id] = output
        self.data[node_id] = output
    
    def get_node_output(self, node_id: str) -> Any:
        return self.data["nodes"].get(node_id)
    
    def resolve_template(self, template: str) -> str:
        """
        Template variables (matlab {{trigger.body}}) ko asli value se replace karte hain.
        """
        if not isinstance(template, str):
            return template

        def replace_var(match):
            path = match.group(1)
            parts = path.split(".")
            
            curr = self.data
            for i, part in enumerate(parts):
                if isinstance(curr, list):
                    if part.isdigit() and int(part) < len(curr):
                        curr = curr[int(part)]
                        continue
                    return f"{{{{MISSING:{path}}}}}"
                if not isinstance(curr, dict):
                    return f"{{{{MISSING:{path}}}}}"
                
                # Sahi key dhundne ka jugaad
                if part in curr:
                    curr = curr[part]
                elif "_" in part:
                    camel = "".join(x.capitalize() or "_" for x in part.split("_"))
                    camel = camel[0].lower() + camel[1:]
                    curr = curr.get(camel)
                else:
                    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', part).lower()
                    curr = curr.get(snake)
                
                if curr is None:
                    return f"{{{{MISSING:{path}}}}}"
            
            return str(curr)
        
        return re.sub(r'\{\{([^}]+)\}\}', replace_var, template)

    def resolve_value(self, value: Any) -> Any:
        """Resolve templates recursively for string/list/dict values."""
        if isinstance(value, str):
            return self.resolve_template(value)
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve_value(item) for key, item in value.items()}
        return value


class FlowEngine:
    """JSON format mein bane flows ko chalane wala engine"""
    
    def __init__(self):
        self.node_handlers = {
            "trigger": self._execute_trigger,
            "condition": self._execute_condition,
            "action": self._execute_action
        }
    
    async def _execute_trigger(self, node: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        return {"status": "triggered"}
    
    async def execute_flow(
        self,
        flow: Flow,
        trigger_data: Dict[str, Any],
        db: Session,
        workspace: Optional[Workspace] = None,
    ) -> FlowExecution:
        """
        Flow execute karne ki bheed-bharakka yahan hoti hai.
        """
        # Trigger data ko thoda saaf-suthra karte hain
        normalized_trigger = trigger_data.copy()
        if "body" not in normalized_trigger and "text" in normalized_trigger:
            normalized_trigger["body"] = normalized_trigger["text"]
        
        if "chatId" not in normalized_trigger:
            normalized_trigger["chatId"] = normalized_trigger.get("from") or normalized_trigger.get("to")
        if "chat_id" not in normalized_trigger:
            normalized_trigger["chat_id"] = normalized_trigger["chatId"]

        context = FlowContext(normalized_trigger, db)
        resolved_workspace_id = str(workspace.id) if workspace else (str(flow.workspace_id) if flow.workspace_id else None)
        context.data["flow"] = {
            "id": str(flow.id),
            "name": flow.name,
            "workspace_id": resolved_workspace_id,
        }
        if workspace:
            context.data["workspace"] = {
                "id": str(workspace.id),
                "name": workspace.name,
            }
        flow_definition = flow.definition
        
        # Execution log shuru karte hain
        execution = FlowExecution(
            flow_id=flow.id,
            trigger_data=normalized_trigger,
            status="running",
            nodes_executed=[],
            started_at=datetime.now(),
            group_id=None
        )
        
        try:
             chat_id = trigger_data.get("chat_id") or trigger_data.get("message", {}).get("chatId")
             if chat_id:
                 group = db.query(WhatsAppGroup).filter(WhatsAppGroup.chat_id == chat_id).first()
                 if group:
                     execution.group_id = group.id
        except Exception:
            pass

        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        try:
            if not flow_definition.get("nodes"):
                execution.status = "completed"
                execution.completed_at = datetime.now()
                db.commit()
                return execution

            current_node_id = flow_definition["nodes"][0]["id"]
            
            nodes_executed_log = []

            while current_node_id:
                node = self._find_node(flow_definition, current_node_id)
                
                if not node:
                    break
                
                logger.info(f"Node chal raha hai: {node.get('name', 'Unknown')}")
                
                handler = self.node_handlers.get(node.get("type"))
                if not handler:
                    raise ValueError(f"Bhai ye kaunsa node type hai: {node.get('type')}")
                
                result = await handler(node, context)
                context.set_node_output(node["id"], result)
                
                # Agla node kaunsa hai?
                next_node_id = self._get_next_node(node, result, flow_definition)
                
                nodes_executed_log.append({
                    "node_id": node["id"],
                    "node_name": node.get("name"),
                    "type": node.get("type"),
                    "result": str(result)[:500],
                    "next_node": next_node_id,
                    "timestamp": datetime.now().isoformat()
                })
                
                current_node_id = next_node_id
            
            execution.status = "completed"
            execution.completed_at = datetime.now()
            execution.nodes_executed = nodes_executed_log
            execution.context_data = str(context.data)[:1000]
            db.commit()
            
        except Exception as e:
            logger.error(f"Flow fail ho gaya: {e}")
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.now()
            execution.nodes_executed = nodes_executed_log if 'nodes_executed_log' in locals() else []
            db.commit()
            raise
        
        return execution
    
    def _find_node(self, flow: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
        for node in flow.get("nodes", []):
            if node["id"] == node_id:
                return node
        return None
    
    def _get_next_node(self, node: Dict[str, Any], result: Any, flow: Dict[str, Any]) -> Optional[str]:
        """Agla node dhundne ka logic"""
        node_id = node["id"]
        edges = flow.get("edges", [])
        
        if node.get("type") == "condition":
            condition_result = "true" if isinstance(result, dict) and result.get("condition_met") else "false"
            for edge in edges:
                if edge.get("source") == node_id and edge.get("sourceHandle") == condition_result:
                    return edge.get("target")
        else:
            for edge in edges:
                if edge.get("source") == node_id:
                    return edge.get("target")
        
        return node.get("next")
    
    async def _execute_condition(self, node: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        """Condition check karte hain (Sahi hai ya galat)"""
        config = node.get("config", {})
        data = node.get("data", {})
        if not config and "config" in data:
            config = data["config"]
            
        condition_type = node.get("condition_type") or data.get("subType")
        
        if condition_type == "text_not_empty":
            input_template = config.get("input", "")
            input_value = context.resolve_template(input_template)
            condition_met = bool(input_value and input_value.strip())
            return {"condition_met": condition_met, "input_value": input_value}
        
        elif condition_type == "text_contains":
            input_template = config.get("input", "")
            pattern = config.get("pattern", "")
            case_sensitive = config.get("case_sensitive", False)
            
            input_value = context.resolve_template(input_template)
            
            if not case_sensitive:
                input_value = input_value.lower()
                pattern = pattern.lower()
                
            condition_met = pattern in input_value
            return {"condition_met": condition_met, "input_value": input_value}
            
        raise ValueError(f"Unknown condition type: {condition_type}")
    
    async def _execute_action(self, node: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        """Action perform karte hain (Message bhejna, RAG wagera)"""
        config = node.get("config", {})
        data = node.get("data", {})
        if not config and "config" in data:
            config = data["config"]
            
        action_type = node.get("action_type") or data.get("subType")
        
        if action_type == "rag_query":
            return await self._execute_rag_query(config, context)
        
        elif action_type == "send_whatsapp_message":
            return await self._execute_send_whatsapp(config, context)
            
        elif action_type == "delay":
            seconds = int(config.get("seconds", 0))
            await asyncio.sleep(seconds)
            return {"status": "delayed", "seconds": seconds}
            
        elif action_type == "http_request":
            return await self._execute_http_request(config, context)
        
        raise ValueError(f"Unknown action type: {action_type}")
    
    async def _execute_http_request(self, config: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        import httpx
        
        url = context.resolve_template(config.get("url", ""))
        method = config.get("method", "GET").upper()
        headers_raw = config.get("headers", {})
        if isinstance(headers_raw, str):
            headers_text = context.resolve_template(headers_raw).strip()
            headers = json.loads(headers_text) if headers_text else {}
        else:
            headers = context.resolve_value(headers_raw)
        body = context.resolve_template(config.get("body", ""))
        
        if not url:
            raise ValueError("Bhai, URL toh de do!")
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body if method in ["POST", "PUT", "PATCH"] else None,
                    timeout=30.0
                )
                
                try:
                    response_data = response.json()
                except:
                    response_data = response.text
                    
                return {
                    "status_code": response.status_code,
                    "response": response_data,
                    "headers": dict(response.headers)
                }
        except Exception as e:
            logger.error(f"HTTP request fail ho gaya: {e}")
            raise

    def _resolve_trigger_client_id(self, context: FlowContext) -> str:
        trigger = context.data.get("trigger", {}) if isinstance(context.data, dict) else {}
        candidates = [
            trigger.get("participant"),
            trigger.get("author"),
            trigger.get("_data", {}).get("key", {}).get("participant"),
            trigger.get("_data", {}).get("key", {}).get("participantAlt"),
            trigger.get("from"),
            trigger.get("chatId"),
        ]
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return ""
    
    async def _execute_rag_query(self, config: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        """RAG se gyan nikaalte hain"""
        from queues.worker import process_query
        
        raw_query = context.resolve_template(config.get("query", ""))
        normalized_raw_query = str(raw_query)
        # Remove bot mentions from start of message (e.g., "@botu what is cs", "@12345 hello").
        query = re.sub(r"^\s*(?:@\S+\s*)+", "", normalized_raw_query).strip()
        # Also strip numeric WA mentions anywhere in the text.
        query = re.sub(r"@\d{6,20}(?:@lid)?", "", query).strip()
        if not query:
            query = normalized_raw_query.strip()
        collection_name = context.resolve_template(config.get("collection_name", "")).strip()
        workspace = None

        workspace_id = (
            context.data.get("workspace", {}).get("id")
            or context.data.get("flow", {}).get("workspace_id")
        )
        if workspace_id:
            try:
                workspace_uuid = uuid.UUID(workspace_id)
                workspace = context.db.query(Workspace).filter(Workspace.id == workspace_uuid).first()
            except Exception:
                workspace = None

        if not collection_name and workspace and workspace.knowledge_base:
            collection_name = workspace.knowledge_base.name

        if not collection_name:
            collection_name = os.getenv("DEFAULT_QDRANT_COLLECTION", "").strip()

        if not collection_name:
            raise ValueError(
                "RAG query ke liye collection resolve nahi hui. "
                "Workspace mein knowledge base attach karo ya flow action config mein `collection_name` set karo."
            )

        client_id = self._resolve_trigger_client_id(context)
        
        conversation_history = ""
        if config.get("include_conversation_history", True) and client_id:
             history_limit = int(config.get("context_limit", 5))
             conversation_history = conversation_manager.get_context_string(client_id, limit=history_limit)

        workspace_system_prompt = (workspace.system_prompt or "").strip() if workspace else ""
        workspace_user_prompt_template = (workspace.user_prompt_template or "").strip() if workspace else ""
        action_system_prompt = context.resolve_template(config.get("system_prompt", "")).strip()
        action_user_prompt_template = context.resolve_template(config.get("user_prompt_template", "")).strip()
        
        result = await asyncio.to_thread(
            process_query,
            query=query,
            client_id=client_id,
            conversation_history=conversation_history,
            whatsapp_message_id=context.data.get("trigger", {}).get("id"),
            collection_name=collection_name,
            system_prompt=(action_system_prompt or workspace_system_prompt or None),
            user_prompt_template=(action_user_prompt_template or workspace_user_prompt_template or None),
            emit_side_effects=False,
        )
        
        return {
            "rag_result": result,
            "query": query,
            "collection_name": collection_name
        }

    def _safe_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off", ""}:
                return False
        return default

    def _safe_float(self, value: Any, field_name: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} number hona chahiye")

    def _parse_json_field(self, raw_value: Any, field_name: str, default: Any) -> Any:
        if raw_value is None:
            return default
        if isinstance(raw_value, (dict, list)):
            return raw_value

        text = str(raw_value).strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} valid JSON nahi hai: {exc.msg}")

    def _normalize_text_payload(self, resolved_text: Any) -> str:
        """
        Prevent raw dict/object strings from being sent to WhatsApp text messages.
        If text resolves to a dict-like object containing `rag_result`, use only that field.
        """
        if isinstance(resolved_text, dict):
            rag_result = resolved_text.get("rag_result")
            return str(rag_result) if rag_result is not None else json.dumps(resolved_text, ensure_ascii=False)

        text = "" if resolved_text is None else str(resolved_text)
        compact = text.strip()
        if not compact:
            return text

        parsed: Any = None
        try:
            parsed = json.loads(compact)
        except Exception:
            try:
                parsed = ast.literal_eval(compact)
            except Exception:
                parsed = None

        if isinstance(parsed, dict) and parsed.get("rag_result") is not None:
            return str(parsed.get("rag_result"))

        return text
    
    async def _execute_send_whatsapp(self, config: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        """WhatsApp message bhejte hain"""

        message_type = str(context.resolve_template(str(config.get("message_type", "text")))).strip().lower() or "text"
        chat_id = context.resolve_template(config.get("chat_id", ""))
        reply_to = context.resolve_template(config.get("reply_to", ""))

        payload: Dict[str, Any] = {}
        if chat_id:
            payload["chatId"] = chat_id
        if reply_to:
            payload["reply_to"] = reply_to

        if message_type == "text":
            resolved_text = context.resolve_template(config.get("text", ""))
            payload["text"] = self._normalize_text_payload(resolved_text)
            if "link_preview" in config:
                payload["linkPreview"] = self._safe_bool(config.get("link_preview"), default=True)
            if "link_preview_high_quality" in config:
                payload["linkPreviewHighQuality"] = self._safe_bool(config.get("link_preview_high_quality"), default=False)

        elif message_type in {"image", "file", "voice", "video"}:
            file_url = context.resolve_template(config.get("file_url", ""))
            file_data = context.resolve_template(config.get("file_data", ""))
            file_mimetype = context.resolve_template(config.get("file_mimetype", ""))
            file_filename = context.resolve_template(config.get("file_filename", ""))
            caption = context.resolve_template(config.get("caption", ""))

            if not file_mimetype:
                raise ValueError("file_mimetype zaroori hai")
            if not (file_url or file_data):
                raise ValueError("file_url ya file_data (base64) dena zaroori hai")

            file_payload: Dict[str, Any] = {"mimetype": file_mimetype}
            if file_url:
                file_payload["url"] = file_url
            else:
                file_payload["data"] = file_data
            if file_filename:
                file_payload["filename"] = file_filename

            payload["file"] = file_payload
            if caption and message_type in {"image", "file", "video"}:
                payload["caption"] = caption
            if message_type in {"voice", "video"}:
                payload["convert"] = self._safe_bool(config.get("convert"), default=False)
            if message_type == "video":
                payload["asNote"] = self._safe_bool(config.get("as_note"), default=False)

        elif message_type == "location":
            payload["latitude"] = self._safe_float(
                context.resolve_template(config.get("latitude", "")),
                "latitude",
            )
            payload["longitude"] = self._safe_float(
                context.resolve_template(config.get("longitude", "")),
                "longitude",
            )
            payload["title"] = context.resolve_template(config.get("title", "")) or "Location"

        elif message_type == "poll":
            poll_name = context.resolve_template(config.get("poll_name", ""))
            poll_options = self._parse_json_field(
                context.resolve_template(config.get("poll_options_json", "[]")),
                "poll_options_json",
                [],
            )
            if not isinstance(poll_options, list):
                raise ValueError("poll_options_json array hona chahiye")

            payload["poll"] = {
                "name": poll_name,
                "options": [str(option) for option in poll_options],
                "multipleAnswers": self._safe_bool(config.get("poll_multiple_answers"), default=False),
            }

        elif message_type == "buttons":
            payload["header"] = context.resolve_template(config.get("buttons_header", ""))
            payload["body"] = context.resolve_template(config.get("buttons_body", ""))
            payload["footer"] = context.resolve_template(config.get("buttons_footer", ""))
            buttons = self._parse_json_field(
                context.resolve_template(config.get("buttons_json", "[]")),
                "buttons_json",
                [],
            )
            if not isinstance(buttons, list):
                raise ValueError("buttons_json array hona chahiye")
            payload["buttons"] = buttons

        elif message_type == "poll_vote":
            payload["pollMessageId"] = context.resolve_template(config.get("poll_message_id", ""))
            poll_server_id_raw = context.resolve_template(config.get("poll_server_id", ""))
            if poll_server_id_raw:
                payload["pollServerId"] = self._safe_float(poll_server_id_raw, "poll_server_id")
            votes = self._parse_json_field(
                context.resolve_template(config.get("votes_json", "[]")),
                "votes_json",
                [],
            )
            if not isinstance(votes, list):
                raise ValueError("votes_json array hona chahiye")
            payload["votes"] = votes

        elif message_type == "reaction":
            payload["messageId"] = context.resolve_template(config.get("message_id", ""))
            payload["reaction"] = context.resolve_template(config.get("reaction", "+1"))

        elif message_type == "forward":
            payload["messageId"] = context.resolve_template(config.get("message_id", ""))

        payload_json = config.get("payload_json", "")
        custom_payload = self._parse_json_field(
            context.resolve_template(payload_json if isinstance(payload_json, str) else json.dumps(payload_json)),
            "payload_json",
            {},
        )
        if isinstance(custom_payload, dict):
            payload.update(context.resolve_value(custom_payload))
        else:
            raise ValueError("payload_json object hona chahiye")

        if message_type == "text" and "text" in payload:
            payload["text"] = self._normalize_text_payload(payload.get("text"))

        if message_type not in {"reaction"} and not payload.get("chatId"):
            raise ValueError("Bhai, chatId/chat_id toh de do!")

        success, response = waha_client.send_dynamic_message(message_type=message_type, payload=payload)

        # Persist assistant text in conversation history for follow-up reasoning.
        if success and message_type == "text":
            history_client_id = self._resolve_trigger_client_id(context) or str(payload.get("chatId") or "").strip()
            text_value = str(payload.get("text") or "").strip()
            if history_client_id and text_value:
                conversation_manager.add_message(history_client_id, "assistant", text_value)

        return {
            "sent": success,
            "message_type": message_type,
            "chat_id": payload.get("chatId"),
            "endpoint_response": response
        }

# Singleton instance
flow_engine = FlowEngine()
