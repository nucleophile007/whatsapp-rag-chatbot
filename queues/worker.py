import os
import warnings
import requests
import json  # Add json import

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

vector_db=QdrantVectorStore.from_existing_collection(
       embedding=embedding_model,
    url=QDRANT_URL,
    collection_name="hehe huhu"
)


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



def process_query(query: str, client_id: str = None, conversation_history: str = "", whatsapp_message_id: str = None):
    print("searching chunks:", query)
    search_results = vector_db.similarity_search(query=query)
    context = "\n\n\n".join([f"Page Content: {result.page_content}\nPage Number: {result.metadata['page_label']}\nFile Location: {result.metadata['source']}" for result in search_results])

    # Build system prompt with conversation history if available
    conversation_context = ""
    if conversation_history:
        conversation_context = f"""
Previous Conversation:
{conversation_history}

The user may be asking a follow-up question. Use the conversation history to understand the context and provide a more relevant answer.
"""

    SYSTEM_PROMPT = f"""
    You are a helpful AI Assistant who answers user queries based on the available context retrieved from a PDF file along with page_contents and page number.

    You should only answer the user based on the following context and navigate the user to open the right page number to know more.
    
    {conversation_context}

    Context from PDF:
    {context}
    """

    client = genai.Client()


    response = client.models.generate_content(
        model="gemini-2.5-flash", # Use a suitable model
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            # Optional: You can also set other parameters here, like temperature
            # temperature=0.7, 
        ),
    )
    print(response.text)
    
    # Get job_id from RQ context if available
    from rq import get_current_job
    job = get_current_job()
    job_id = job.id if job else None
    
    # Send WebSocket notification if client_id is provided
    if client_id:
        send_websocket_notification(client_id, response.text, job_id)
    
    # Send WhatsApp reply if it's a WhatsApp message
    if client_id and "@g.us" in client_id:
        send_whatsapp_reply(client_id, response.text, whatsapp_message_id)
    
    return response.text