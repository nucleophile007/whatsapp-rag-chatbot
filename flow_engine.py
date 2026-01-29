"""
Flow Execution Engine
Handles the parsing and execution of automation flows defined in the database.
"""

import re
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
import asyncio

from database import Flow, FlowExecution, FlowGroup, WhatsAppGroup, NodeType, get_db
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
    
    async def execute_flow(self, flow: Flow, trigger_data: Dict[str, Any], db: Session) -> FlowExecution:
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
        headers = json.loads(context.resolve_template(json.dumps(config.get("headers", {}))))
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
    
    async def _execute_rag_query(self, config: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        """RAG se gyan nikaalte hain"""
        from queues.worker import process_query
        
        query = context.resolve_template(config.get("query", ""))
        client_id = context.data.get("trigger", {}).get("from")
        
        conversation_history = ""
        if config.get("include_conversation_history", True) and client_id:
             history_limit = int(config.get("context_limit", 5))
             conversation_history = conversation_manager.get_context_string(client_id, limit=history_limit)
        
        result = await asyncio.to_thread(
            process_query,
            query=query,
            client_id=client_id,
            conversation_history=conversation_history,
            whatsapp_message_id=context.data.get("trigger", {}).get("id")
        )
        
        return {
            "rag_result": result,
            "query": query
        }
    
    async def _execute_send_whatsapp(self, config: Dict[str, Any], context: FlowContext) -> Dict[str, Any]:
        """WhatsApp message bhejte hain"""
        
        chat_id = context.resolve_template(config.get("chat_id", ""))
        text = context.resolve_template(config.get("text", ""))
        reply_to = context.resolve_template(config.get("reply_to", ""))
        
        if not chat_id:
            raise ValueError("Bhai, Chat ID toh de do!")

        success = waha_client.send_message(
            chat_id=chat_id, 
            text=text, 
            reply_to=reply_to if reply_to else None
        )
        
        return {
            "sent": success,
            "chat_id": chat_id,
            "text_preview": text[:50]
        }

# Singleton instance
flow_engine = FlowEngine()
