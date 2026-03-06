import os
import warnings
import requests
import json  # Add json import
import re
from typing import Dict, Optional

# Fix macOS fork() crash with Objective-C runtime
os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

# Suppress warnings
warnings.filterwarnings('ignore', message='.*OpenSSL.*', category=Warning)
warnings.filterwarnings('ignore', category=FutureWarning)

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
from langchain_qdrant import QdrantVectorStore
from google import genai
from google.genai import types


load_dotenv()

embedding_model = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

# Use environment variable for Qdrant URL (Docker compatibility)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_QDRANT_COLLECTION = os.getenv("DEFAULT_QDRANT_COLLECTION", "").strip()

_vector_db_cache: Dict[str, QdrantVectorStore] = {}


def _get_vector_db(collection_name: str) -> QdrantVectorStore:
    if collection_name in _vector_db_cache:
        return _vector_db_cache[collection_name]

    try:
        vector_db = QdrantVectorStore.from_existing_collection(
            embedding=embedding_model,
            url=QDRANT_URL,
            collection_name=collection_name,
        )
    except Exception as e:
        raise ValueError(f"Qdrant collection '{collection_name}' load nahi ho payi: {e}") from e

    _vector_db_cache[collection_name] = vector_db
    return vector_db


def send_websocket_notification(client_id: str, result: str, job_id: str = None):
    """Send result to client via WebSocket through HTTP callback"""
    if not client_id:
        return
    
    try:
        # Get server URL from environment or use default
        server_url = os.getenv("SERVER_URL", "http://localhost:8000")
        
        # Send notification to internal endpoint
        response = requests.post(
            f"{server_url}/internal/notify",
            json={"client_id": client_id, "result": result, "job_id": job_id},
            timeout=5
        )
        print(f"WebSocket notification sent to client {client_id}: {response.status_code}")
    except Exception as e:
        print(f"Failed to send WebSocket notification: {e}")


def send_whatsapp_reply(client_id: str, result: str, whatsapp_message_id: str = None):
    """Send result directly to WhatsApp via WAHA API (replaces n8n workflow 2)"""
    if not client_id or "@g.us" not in client_id:
        print("Not a WhatsApp group message, skipping WAHA API")
        return
    
    try:
        # Get WAHA configuration from environment
        waha_url = os.getenv("WAHA_URL", "http://waha:3000")
        waha_api_key = os.getenv("WAHA_API_KEY", "")
        
        # Build request payload
        payload = {
            "chatId": client_id,
            "text": result,
            "session": "default"
        }
        
        # Add reply_to if message_id is available (to quote the original message)
        if whatsapp_message_id:
            payload["reply_to"] = whatsapp_message_id
        
        # Prepare headers
        headers = {"Content-Type": "application/json"}
        if waha_api_key:
            headers["X-API-Key"] = waha_api_key
        
        # Send to WAHA API
        response = requests.post(
            f"{waha_url}/api/sendText",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            print(f"✅ WhatsApp reply sent to {client_id}")
        else:
            print(f"⚠️ WAHA API error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Failed to send WhatsApp reply: {e}")


def process_query(
    query: str,
    client_id: str = None,
    conversation_history: str = "",
    whatsapp_message_id: str = None,
    collection_name: str = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
    emit_side_effects: bool = True,
):
    capability_query = bool(
        re.search(
            r"\b(what\s+(knowledge|information|info)\s+(do\s+you\s+have|you\s+have|you\s+provide)|"
            r"what\s+can\s+you\s+(answer|provide|do)|"
            r"what\s+do\s+you\s+know|"
            r"which\s+topics)\b",
            query.lower(),
        )
    )

    target_collection = (collection_name or DEFAULT_QDRANT_COLLECTION or "").strip()
    if not target_collection:
        raise ValueError("RAG ke liye collection_name missing hai. Workspace KB ya flow config check karo.")

    retrieval_query = query
    retrieval_k = 5
    if capability_query:
        # For "what can you answer" style queries, fetch broad KB overview chunks.
        retrieval_query = "table of contents topics sections syllabus overview departments course codes"
        retrieval_k = 8

    print(f"searching chunks in '{target_collection}':", retrieval_query)
    vector_db = _get_vector_db(target_collection)
    search_results = vector_db.similarity_search(query=retrieval_query, k=retrieval_k)
    context = "\n\n\n".join([
        (
            f"Page Content: {result.page_content}\n"
            f"Page Number: {result.metadata.get('page_label', result.metadata.get('page', 'N/A'))}\n"
            f"File Location: {result.metadata.get('source', 'N/A')}"
        )
        for result in search_results
    ])

    # Build system prompt with conversation history if available
    conversation_context = ""
    if conversation_history:
        conversation_context = f"""
Previous Conversation:
{conversation_history}

The user may be asking a follow-up question. Use the conversation history to understand the context and provide a more relevant answer.
"""

    default_system_prompt = f"""
    You are a helpful AI Assistant who answers user queries based on the available context retrieved from a PDF file along with page_contents and page number.

    You should only answer the user based on the following context and navigate the user to open the right page number to know more.
    If recent conversation contains explicit user-defined mappings (for example: "cs means computer science"),
    you may use those mappings to interpret follow-up questions before answering from PDF context.
    
    {conversation_context}

Context from PDF:
{context}
"""

    replacements = {
        "{{body}}": query,
        "{{query}}": query,
        "{{rag_result}}": context,
        "{{context}}": context,
        "{{conversation_history}}": conversation_history or "",
        "{{retrieval_query}}": retrieval_query,
        "{{is_capability_query}}": "true" if capability_query else "false",
    }

    effective_system_prompt = (system_prompt or "").strip() or default_system_prompt
    for key, value in replacements.items():
        effective_system_prompt = effective_system_prompt.replace(key, value)

    user_contents = query
    if (user_prompt_template or "").strip():
        user_contents = user_prompt_template
        for key, value in replacements.items():
            user_contents = user_contents.replace(key, value)
        user_contents = user_contents.strip() or query

    client = genai.Client()


    response = client.models.generate_content(
        model="gemini-2.5-flash", # Use a suitable model
        contents=user_contents,
        config=types.GenerateContentConfig(
            system_instruction=effective_system_prompt,
            # Optional: You can also set other parameters here, like temperature
            # temperature=0.7, 
        ),
    )
    response_text = response.text or ""

    print(response_text)
    
    # Get job_id from RQ context if available
    from rq import get_current_job
    job = get_current_job()
    job_id = job.id if job else None
    
    # Optional side effects (websocket + direct WhatsApp send) are used by /chat path.
    # Flow engine callers can disable this and use explicit send nodes instead.
    if emit_side_effects and client_id:
        send_websocket_notification(client_id, response_text, job_id)
    
    # Send WhatsApp reply if it's a WhatsApp message
    if emit_side_effects and client_id and "@g.us" in client_id:
        send_whatsapp_reply(client_id, response_text, whatsapp_message_id)
    
    return response_text
