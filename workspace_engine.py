import logging
import os
import re
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from database import Workspace, KnowledgeBase, WhatsAppGroup, WorkspaceGroup, FlowExecution
from waha_client import waha_client
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from datetime import datetime

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class WorkspaceEngine:
    """RAG aur Prompts handle karne wala system"""
    
    def __init__(self):
        if not GOOGLE_API_KEY:
            logger.error("Bhai, GOOGLE_API_KEY hi nahi mil raha!")
            
    async def execute_workspace(self, workspace: Workspace, payload: Dict[str, Any], db: Session):
        """
        Workspace ke liye RAG aur LLM ka logic execute hota hai yahan.
        """
        chat_id = payload.get("chatId") or payload.get("from")
        message_id = payload.get("id")
        body = payload.get("body", "")
        mentioned_ids = payload.get("mentionedIds", [])
        
        # Bot mention check karna zaroori hai group groups mein.
        bot_lid = payload.get("me", {}).get("lid", "").split("@")[0] or "35077249618150"
        
        is_mentioned = any(bot_lid in m_id for m_id in mentioned_ids)
        if not is_mentioned and f"@{bot_lid}" not in body:
            # Deep check for NOWEB/multi-device
            try:
                deep_mentions = payload.get("_data", {}).get("message", {}).get("extendedTextMessage", {}).get("contextInfo", {}).get("mentionedJid", [])
                is_mentioned = any(bot_lid in m_id for m_id in deep_mentions)
            except:
                pass
        
        if not is_mentioned and "@" in body: # Text-based fallback
             if f"@{bot_lid}" in body:
                 is_mentioned = True

        if not is_mentioned:
            logger.info(f"⏭️ Workspace {workspace.name} skip kiya: Bot mention nahi mila.")
            return {"status": "skipped", "reason": "bot_not_mentioned"}

        # Check karte hain koi customized flows toh nahi hain is workspace ke liye.
        from flow_engine import flow_engine
        from database import Flow
        
        flows = db.query(Flow).filter(Flow.workspace_id == workspace.id, Flow.is_enabled == True).all()
        for flow in flows:
            if flow.trigger_type == "whatsapp_mention":
                logger.info(f"⚡ Flow trigger ho raha hai: {flow.name}")
                try:
                    execution = await flow_engine.execute_flow(flow, payload, db)
                    return {
                        "status": "success",
                        "triggered_flow": flow.name,
                        "execution_id": execution.id
                    }
                except Exception as e:
                    logger.error(f"Flow execution fail ho gaya ({flow.name}): {e}")

        # Agar documents hain toh wahan se knowledge nikaalte hain (RAG Retrieval)
        context_text = ""
        if workspace.knowledge_base:
            kb_name = workspace.knowledge_base.name
            logger.info(f"🔍 Knowledge Base mein search kar rahe hain: {kb_name}")
            try:
                embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
                vector_store = QdrantVectorStore(
                    client=QdrantClient(url=QDRANT_URL),
                    collection_name=kb_name,
                    embedding=embeddings
                )
                
                docs = await vector_store.asimilarity_search(body, k=4)
                context_text = "\n\n".join([doc.page_content for doc in docs])
            except Exception as e:
                logger.error(f"RAG search fail ho gaya ({kb_name}): {e}")
                context_text = "Knowledge base se context nahi mil paaya."

        # Prompt ko sahi dhang se set karte hain.
        user_prompt = workspace.user_prompt_template or "{{body}}"
        user_prompt = user_prompt.replace("{{body}}", body)
        user_prompt = user_prompt.replace("{{rag_result}}", context_text)
        
        system_prompt = workspace.system_prompt or "You are a helpful assistant."
        
        # Ab AI ka dimag chalate hain (LLM Generation).
        logger.info(f"🤖 AI response generate ho raha hai: {workspace.name}")
        try:
            llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
            messages = [
                ("system", system_prompt),
                ("user", user_prompt)
            ]
            response = await llm.ainvoke(messages)
            ai_text = response.content
        except Exception as e:
            logger.error(f"AI fail ho gaya: {e}")
            ai_text = "Maaf kijiye, abhi mera dimag thoda kaam nahi kar raha."

        # Final message bhej dete hain.
        logger.info(f"📤 Result bhej rahe hain {chat_id} ko.")
        success = waha_client.send_message(
            chat_id=chat_id,
            text=ai_text,
            reply_to=message_id
        )
        
        return {
            "status": "success" if success else "failed",
            "ai_text_preview": ai_text[:50]
        }

workspace_engine = WorkspaceEngine()
