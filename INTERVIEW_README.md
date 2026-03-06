# WhatsApp RAG Chatbot - Interview Technical Guide

## 🎯 Project Overview

This is a **production-grade WhatsApp automation system** that combines **RAG (Retrieval-Augmented Generation)**, **visual workflow builder**, and **real-time messaging** to create intelligent chatbots. It's built using **FastAPI**, **PostgreSQL**, **Redis/Valkey**, **Qdrant vector database**, and **Google Gemini AI**.

### Key Business Problem Solved
Organizations need to automate WhatsApp customer support with context-aware AI responses based on their internal documents, without manually writing code for each use case.

---

## 🏗️ System Architecture

### High-Level Architecture
```
WhatsApp → WAHA API → FastAPI Backend → Flow/Workspace Engine → AI/RAG → Response
                           ↓
                    PostgreSQL (State)
                    Redis (Queues/Cache)
                    Qdrant (Vector DB)
```

### Components
1. **FastAPI Backend** (`server.py`, `main.py`)
2. **Flow Engine** - Visual workflow executor
3. **Workspace Engine** - RAG + Prompt orchestrator
4. **Database Layer** - PostgreSQL with SQLAlchemy
5. **Queue System** - Redis + RQ for async processing
6. **Vector Store** - Qdrant for semantic search
7. **Frontend** - React + Vite (flow builder UI)

---

## 🚀 FastAPI Concepts Used

### 1. **Application Initialization**
```python
from fastapi import FastAPI

app = FastAPI()
```
- Creates the main ASGI application
- Handles HTTP requests and WebSocket connections
- Auto-generates OpenAPI docs at `/docs`

### 2. **CORS Middleware**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**Why?** Allows frontend (running on different port) to call backend APIs.

**Interview Tip:** In production, replace `["*"]` with specific origins for security.

### 3. **Dependency Injection**
```python
from fastapi import Depends
from sqlalchemy.orm import Session

@app.get("/groups")
def get_groups(db: Session = Depends(get_db_session)):
    groups = db.query(WhatsAppGroup).all()
    return groups
```

**Key Concepts:**
- `Depends()` automatically injects database session
- Session is created per request and closed after
- Prevents resource leaks

**Interview Question:** *How does FastAPI handle database connections?*
> FastAPI uses dependency injection with `Depends()`. The `get_db_session()` generator function creates a new SQLAlchemy session for each request and automatically closes it when done, ensuring proper connection pooling.

### 4. **Pydantic Models for Request/Response Validation**
```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    query: str
    client_id: Optional[str] = None
    message_id: Optional[str] = None
```

**Benefits:**
- Automatic data validation
- Type hints for IDE support
- Auto-generated API documentation
- Serialization/deserialization

**Interview Tip:** Pydantic runs validation before route handler executes. Invalid data returns 422 status automatically.

### 5. **WebSocket Connections**
```python
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Process data
    except WebSocketDisconnect:
        manager.disconnect(client_id)
```

**Use Case:** Real-time updates to frontend when async job completes.

**ConnectionManager Pattern:**
- Maintains dict of active WebSocket connections
- Allows server to push messages to specific clients
- Handles cleanup on disconnect

### 6. **Async/Await for Concurrent Operations**
```python
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    result = await workspace_engine.execute_workspace(...)
    return {"response": result}
```

**Why Async?**
- Non-blocking I/O for external API calls (WAHA, Gemini AI)
- Handles multiple requests concurrently
- Better resource utilization

**Interview Question:** *When to use async vs sync in FastAPI?*
> Use `async def` for I/O-bound operations (API calls, database with async drivers). Use regular `def` for CPU-bound or when using synchronous libraries (SQLAlchemy ORM).

### 7. **Background Tasks with Redis Queue (RQ)**
```python
from client.rq_client import queue

@app.post("/query")
def submit_query(request: ChatRequest):
    job = queue.enqueue(
        process_query,
        args=(request.query, request.client_id),
        job_timeout=300
    )
    return {"job_id": job.id, "status": "queued"}
```

**Pattern Explanation:**
1. API receives request → Returns immediately
2. Job added to Redis queue
3. Separate worker process picks up job
4. Worker sends result via WebSocket
5. Frontend receives real-time update

**Why Not Just Async?**
- Decouples API from long-running tasks
- Worker can restart without losing jobs
- Easy horizontal scaling (add more workers)

**Deep Dive: Redis Queue vs Pure Async** (See detailed explanation below)

### 8. **File Upload Handling**
```python
@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    kb_id: str = Query(...)
):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    
    chunks = index_pdfs_to_collection(kb_name, [tmp_path])
    os.remove(tmp_path)
    return {"chunks_indexed": chunks}
```

**Concepts:**
- `UploadFile` streams large files efficiently
- Temporary file storage for processing
- Cleanup after processing

### 9. **Path Parameters and Query Parameters**
```python
# Path parameter
@app.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: str):
    ...

# Query parameter
@app.get("/flows")
def list_flows(workspace_id: Optional[str] = Query(None)):
    ...
```

**URL Examples:**
- `/workspaces/123-456-789` → Path param
- `/flows?workspace_id=abc` → Query param

### 10. **Exception Handling**
```python
from fastapi import HTTPException

@app.post("/flows/{flow_id}/execute")
async def execute_flow(flow_id: str, db: Session = Depends(get_db_session)):
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    try:
        result = await flow_engine.execute_flow(flow, payload, db)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Best Practice:** Use specific status codes (404, 400, 500) for proper REST semantics.

---

## 🔄 Complete Request Flow

### Scenario: WhatsApp User Sends Message

```
1. WhatsApp User → WAHA API
   - User sends: "@bot What is your refund policy?"

2. WAHA API → FastAPI Webhook (/whatsapp/webhook)
   POST /whatsapp/webhook
   {
     "event": "message",
     "payload": {
       "chatId": "120363xxxxx@g.us",
       "body": "@bot What is your refund policy?",
       "id": "msg123",
       "mentionedIds": ["35077249618150@lid"]
     }
   }

3. FastAPI Webhook Handler
   - Validates webhook payload (Pydantic)
   - Checks database for group (Dependency Injection)
   - Finds active workspace for group
   
4. Workspace Engine Execution
   a) Check if bot was mentioned → Yes
   b) Query vector database (Qdrant) for relevant docs
   c) Retrieve top 4 similar document chunks (RAG)
   d) Build prompt with context
   e) Call Google Gemini AI with augmented prompt
   f) Get AI response
   
5. Send Response Back
   - WAHA API sends message to WhatsApp
   - Log execution in database
   - Return success response

6. Frontend Update (WebSocket)
   - Execution log pushed to connected dashboard
   - Real-time update without page refresh
```

---

## 📊 Database Schema (Interview Perspective)

### Key Tables

#### 1. **workspaces** (Main configuration)
```sql
- id (UUID)
- name
- knowledge_base_id (FK) → Which documents to use
- system_prompt → AI personality
- user_prompt_template → Dynamic prompt with {{body}}, {{rag_result}}
```

**Purpose:** Centralized RAG + Prompt configuration

#### 2. **flows** (Visual workflows)
```sql
- id (UUID)
- name
- definition (JSONB) → Stores node/edge graph
- trigger_type → 'whatsapp_mention', 'whatsapp_message'
- workspace_id (FK) → Optional workspace link
```

**Purpose:** No-code automation rules (if-then logic, API calls)

#### 3. **whatsapp_groups**
```sql
- chat_id (unique) → Group identifier
- is_enabled → Active/inactive
- last_message_at → Tracking
```

**Purpose:** Manage which groups bot monitors

#### 4. **knowledge_bases**
```sql
- name → Maps to Qdrant collection name
```

**Purpose:** Track document collections for RAG

#### 5. **flow_executions** (Audit log)
```sql
- flow_id (FK)
- group_id (FK)
- trigger_data (JSONB)
- execution_log (JSONB)
- status → 'success', 'failed'
```

**Purpose:** Debugging and analytics

### Relationships
```
Workspace → KnowledgeBase (Many-to-One)
Workspace → Flows (One-to-Many)
Workspace ← WorkspaceGroup → WhatsAppGroup (Many-to-Many)
Flow → FlowExecutions (One-to-Many)
```

---

## 🧠 RAG (Retrieval-Augmented Generation) Implementation

### What is RAG?
**Problem:** LLMs don't know about your company's specific data.

**Solution:** 
1. Store company documents in vector database
2. Find relevant chunks for user query
3. Feed chunks + query to LLM
4. Get accurate, context-aware response

### Implementation Steps

#### 1. **Document Indexing** (`rag_utils.py`)
```python
def index_pdfs_to_collection(collection_name: str, file_paths: List[str]):
    # Load PDF
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    
    # Split into chunks (1000 chars, 200 overlap)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200
    )
    chunks = text_splitter.split_documents(docs)
    
    # Convert to embeddings and store in Qdrant
    QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=GoogleGenerativeAIEmbeddings(),
        collection_name=collection_name
    )
```

**Why Chunking?**
- Embeddings have token limits
- Smaller chunks = more precise retrieval
- Overlap ensures context continuity

#### 2. **Semantic Search** (`workspace_engine.py`)
```python
# User query: "What is your refund policy?"
embeddings = GoogleGenerativeAIEmbeddings()
vector_store = QdrantVectorStore(
    client=QdrantClient(url=QDRANT_URL),
    collection_name=kb_name,
    embedding=embeddings
)

# Find 4 most similar chunks
docs = await vector_store.asimilarity_search(user_query, k=4)
context_text = "\n\n".join([doc.page_content for doc in docs])
```

**What Happens:**
1. User query → Vector (768 dimensions)
2. Qdrant finds closest vectors (cosine similarity)
3. Returns original text chunks

#### 3. **Prompt Augmentation**
```python
system_prompt = "You are a helpful customer support agent."

user_prompt = f"""
Context from knowledge base:
{context_text}

User question: {user_query}

Answer based on the context provided.
"""

# Send to Gemini AI
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")
response = llm.invoke([
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
])
```

---

## ⚙️ Flow Engine (Visual Workflow System)

### Concept
Users drag-and-drop nodes to create automation without code.

### Example Flow: Auto-Reply Bot
```json
{
  "nodes": [
    {
      "id": "trigger_1",
      "type": "trigger",
      "subType": "whatsapp_message"
    },
    {
      "id": "condition_1",
      "type": "condition",
      "subType": "text_contains",
      "config": {"pattern": "help"}
    },
    {
      "id": "action_1",
      "type": "action",
      "subType": "send_whatsapp_message",
      "config": {
        "chat_id": "{{trigger.chatId}}",
        "text": "Here is the help menu..."
      }
    }
  ],
  "edges": [
    {"source": "trigger_1", "target": "condition_1"},
    {"source": "condition_1", "target": "action_1"}
  ]
}
```

### Execution Logic (`flow_engine.py`)
```python
class FlowEngine:
    async def execute_flow(self, flow: Flow, payload: Dict, db: Session):
        context = FlowContext(trigger_data=payload, db=db)
        
        # Find trigger node
        trigger_node = self._find_trigger_node(flow.definition)
        
        # Execute from trigger
        await self._execute_node(trigger_node, context, flow.definition)
        
        # Log to database
        self._log_execution(flow, context, db)
```

### Template Variable Resolution
```python
def resolve_template(self, template: str) -> str:
    # "{{trigger.body}}" → actual message text
    # "{{action_1.result}}" → previous node output
    
    pattern = r'\{\{([^}]+)\}\}'
    
    def replace_var(match):
        path = match.group(1)  # "trigger.body"
        parts = path.split(".")  # ["trigger", "body"]
        
        value = self.data
        for part in parts:
            value = value.get(part)
        return str(value)
    
    return re.sub(pattern, replace_var, template)
```

---

## 🔐 Environment Variables & Configuration

```bash
# .env file
GOOGLE_API_KEY=AIzaSy...        # Gemini AI access
QDRANT_URL=http://qdrant:6333   # Vector database
REDIS_HOST=valkey               # Queue/cache
DATABASE_URL=postgresql://...   # Main database
WAHA_URL=http://waha:3000       # WhatsApp API
```

**Interview Tip:** Never commit API keys. Use `.env` files + `.gitignore`.

---

## ⚡ Redis Queue vs Pure Async: Why Both?

### Common Interview Question: "If FastAPI supports async, why use Redis Queue?"

This is an **excellent architectural question**. Let's break it down:

### Scenario 1: When Async Alone is Sufficient ✅

**Use Case:** Quick I/O operations (< 5 seconds)

```python
@app.post("/send-message")
async def send_message(chat_id: str, text: str):
    # This is fine with just async - completes in ~1-2 seconds
    response = await waha_client.send_message(chat_id, text)
    return {"status": "sent", "message_id": response.id}
```

**Why Async Works Here:**
- Operation completes quickly
- User can wait for response
- Connection stays open briefly
- No risk of timeout

---

### Scenario 2: When You NEED Redis Queue 🚀

**Use Case:** Long-running operations (> 30 seconds)

```python
@app.post("/index-large-pdf")
async def index_pdf(file: UploadFile):
    # ❌ BAD: This could take 5+ minutes
    # await index_pdfs_to_collection(collection_name, [file_path])
    
    # ✅ GOOD: Queue it
    job = queue.enqueue(
        index_pdfs_to_collection,
        args=(collection_name, [file_path]),
        job_timeout=600  # 10 minutes allowed
    )
    return {"job_id": job.id, "status": "processing"}
```

### Key Differences Table

| Aspect | Pure Async (`async/await`) | Redis Queue (RQ/Celery) |
|--------|---------------------------|-------------------------|
| **Max Duration** | < 30 seconds (HTTP timeout) | Hours if needed |
| **Request Handling** | Holds connection open | Returns immediately |
| **Failure Recovery** | Lost if server restarts | Persisted in Redis |
| **Scaling** | Limited by single process | Unlimited workers |
| **Retry Logic** | Manual implementation | Built-in |
| **Monitoring** | Custom logging | Job status tracking |
| **Use Case** | API calls, DB queries | PDF processing, ML tasks |

---

### Real-World Problem: Why We Use Both

#### Problem 1: **HTTP Timeout** 🕐
```python
# User uploads 100MB PDF with 1000 pages
# Indexing takes 5 minutes
# Browser/client timeout = 30-60 seconds
# Result: Connection drops, user sees error, but processing continues!
```

**Solution with Queue:**
```python
# 1. API responds in < 1 second
# 2. Worker processes in background
# 3. WebSocket notifies user when done
```

#### Problem 2: **Server Restart** 🔄
```python
# Scenario:
# 1. User starts PDF indexing with pure async
# 2. 3 minutes in, server crashes (deploy, OOM, etc.)
# 3. Work is LOST - user has to restart
```

**Solution with Queue:**
```python
# Job is in Redis (separate process)
# Server restarts → Worker picks up where it left off
# Zero data loss
```

#### Problem 3: **Resource Exhaustion** 💻
```python
# Pure Async:
# 100 users upload PDFs simultaneously
# All 100 async tasks run in SAME process
# CPU/Memory spike → Server crashes

# With Queue:
# 100 jobs queued
# 5 workers process them sequentially
# Controlled resource usage
```

---

### Our Hybrid Architecture (Best of Both Worlds)

```python
# ✅ Use ASYNC for fast operations
@app.get("/groups")
async def get_groups(db: Session = Depends(get_db_session)):
    groups = await db.query(WhatsAppGroup).all()  # < 1 second
    return groups

# ✅ Use QUEUE for slow operations
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile, kb_name: str):
    # Save file (fast)
    file_path = await save_file(file)
    
    # Queue heavy processing (slow)
    job = queue.enqueue(
        index_pdfs_to_collection,
        args=(kb_name, [file_path]),
        job_timeout=600
    )
    
    return {"job_id": job.id}  # Returns in < 1 second

# 🔔 WebSocket for real-time updates
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    # Worker will push result here when done
```

---

### Code Comparison: The Same Task

#### ❌ Pure Async (Problematic for long tasks)
```python
@app.post("/process-query")
async def process_query(query: str):
    # All of this runs in the request lifecycle
    # If it takes > 30s, client times out
    
    # 1. Vector search (1-2 seconds)
    docs = await vector_store.search(query)
    
    # 2. LLM call (5-10 seconds) 
    response = await llm.generate(docs, query)
    
    # 3. Send WhatsApp (1-2 seconds)
    await waha_client.send_message(chat_id, response)
    
    return {"result": response}  # Waits 10-15 seconds total
```

**Problems:**
- Client waits 15 seconds (bad UX)
- If user closes browser, work is lost
- Server restart = lost progress
- No retry if LLM fails

#### ✅ Queue-Based (Production-ready)
```python
@app.post("/process-query")
async def process_query(query: str, client_id: str):
    # Queue the work (returns in 50ms)
    job = queue.enqueue(
        process_query_task,
        args=(query, client_id),
        job_timeout=300,
        retry=Retry(max=3)  # Auto-retry on failure
    )
    return {"job_id": job.id, "status": "queued"}

# Separate worker process
def process_query_task(query: str, client_id: str):
    try:
        # Same work, but in background
        docs = vector_store.search(query)
        response = llm.generate(docs, query)
        waha_client.send_message(chat_id, response)
        
        # Notify via WebSocket
        notify_client(client_id, {"status": "done", "result": response})
    except Exception as e:
        # Job automatically retries
        logger.error(f"Task failed: {e}")
        notify_client(client_id, {"status": "error", "error": str(e)})
```

**Benefits:**
- API responds instantly
- Work survives server restarts
- Auto-retry on failures
- Easy to monitor job status
- Can run 10 workers for parallel processing

---

### When We Use Each in This Project

| Component | Pattern | Why |
|-----------|---------|-----|
| **WhatsApp Webhook** | Async | Quick validation + trigger |
| **Workspace Execution** | Async | Usually < 5 seconds |
| **PDF Indexing** | Queue | Can take minutes |
| **Batch Operations** | Queue | Multiple files |
| **Database Queries** | Async | Fast with proper indexes |
| **LLM Calls** | Async | Usually 2-5 seconds (Gemini is fast) |
| **Flow Execution** | Hybrid | Simple flows = async, complex = queue |

---

### Interview Answer Template

**Q: "Why use Redis Queue if FastAPI supports async?"**

**A:** "Both serve different purposes:

1. **Async** handles concurrent I/O efficiently within a single request lifecycle - great for operations under 30 seconds

2. **Redis Queue** handles:
   - Long-running tasks that exceed HTTP timeouts
   - Job persistence across server restarts
   - Horizontal scaling with multiple workers
   - Built-in retry logic and monitoring

In our system, we use **async for real-time operations** (webhooks, DB queries, quick AI responses) and **queues for heavy lifting** (PDF indexing, batch processing). This hybrid approach gives us both **low latency** and **reliability**."

**Follow-up Q: "Why not just increase timeout?"**

**A:** "Increasing timeouts doesn't solve:
- User closing browser mid-request (work lost)
- Server restarts during deployment
- Resource exhaustion from too many concurrent operations
- Inability to check job status or cancel jobs
- Missing retry logic for transient failures

Queues provide a **distributed, fault-tolerant** architecture."

---

## 🐳 Docker & Deployment

### Services (`docker-compose.yml`)
1. **Valkey** (Redis fork) - Queue + Cache
2. **PostgreSQL** - Main database
3. **Qdrant** - Vector database
4. **WAHA** - WhatsApp API
5. **FastAPI Server** - Main backend
6. **RQ Worker** - Background job processor
7. **Frontend** - React app

### Why Docker Compose?
- Single command deployment
- Network isolation
- Environment consistency
- Easy scaling

---

## 🎤 Common Interview Questions

### 1. **"Why FastAPI over Flask/Django?"**
**Answer:**
- **Performance:** ASGI (async) vs WSGI (sync) → 2-3x faster
- **Type Safety:** Pydantic validation catches bugs early
- **Auto Documentation:** OpenAPI/Swagger built-in
- **WebSocket Support:** Native async websockets
- **Modern Python:** Native async/await support

### 2. **"How do you handle long-running tasks?"**
**Answer:**
- Use **Redis Queue (RQ)** with separate worker process
- API returns immediately with job ID
- Worker processes in background
- Result sent via WebSocket for real-time updates
- Alternative: Celery for more complex workflows

### 3. **"Explain your RAG implementation"**
**Answer:**
1. **Indexing:** PDFs → Chunks → Embeddings → Qdrant
2. **Retrieval:** User query → Vector search → Top K chunks
3. **Generation:** Chunks + Query → LLM → Answer
4. **Tech Stack:** LangChain + Qdrant + Google Gemini

### 4. **"How do you ensure database connection safety?"**
**Answer:**
- Use **dependency injection** with `Depends(get_db_session)`
- Generator pattern ensures session cleanup
- SQLAlchemy connection pooling
- Per-request session scope

### 5. **"How would you scale this system?"**
**Answer:**
- **Horizontal Scaling:** Load balancer → Multiple FastAPI instances
- **Worker Scaling:** Add more RQ workers for background jobs
- **Database:** Read replicas, connection pooling
- **Caching:** Redis for frequent queries
- **Vector DB:** Qdrant clustering for large datasets

### 6. **"Security considerations?"**
**Answer:**
- API key validation for webhooks
- HTTPS/TLS for production
- Environment variables for secrets
- Rate limiting on endpoints
- Input validation with Pydantic
- SQL injection prevention (ORM)

### 7. **"How do you debug production issues?"**
**Answer:**
- Structured logging with levels (INFO, ERROR)
- Execution logs in database
- WebSocket for real-time monitoring
- Health check endpoints
- Sentry/error tracking integration

---

## 🧪 Testing Strategy

### Unit Tests
```python
def test_flow_template_resolution():
    context = FlowContext(trigger_data={"body": "Hello"})
    result = context.resolve_template("{{trigger.body}}")
    assert result == "Hello"
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_workspace_execution():
    # Create test workspace
    # Mock Qdrant response
    # Execute workspace
    # Verify AI response
```

### API Tests
```python
def test_create_workspace(client):
    response = client.post("/workspaces", json={
        "name": "Test WS",
        "knowledge_base_id": "kb-123"
    })
    assert response.status_code == 200
```

---

## 📈 Performance Optimizations

1. **Async I/O:** Non-blocking API calls
2. **Connection Pooling:** Database + Redis
3. **Vector Search:** Indexed similarity search (O(log n))
4. **Caching:** Conversation history in Redis
5. **Batch Processing:** Multiple PDFs in one indexing job
6. **Lazy Loading:** Relationships loaded on-demand

---

## 🎓 Key Takeaways for Interview

1. **Architecture:** Microservices pattern with clear separation
2. **FastAPI:** Async, type-safe, auto-documented REST API
3. **RAG:** Vector search + LLM for context-aware responses
4. **Workflows:** Visual flow builder for non-technical users
5. **Scalability:** Queue-based async processing
6. **Real-time:** WebSocket for live updates
7. **Database:** Relational (PostgreSQL) + Vector (Qdrant)

---

## 🚀 Future Enhancements

- [ ] Multi-tenant support
- [ ] Advanced analytics dashboard
- [ ] A/B testing for prompts
- [ ] Voice message support
- [ ] Multi-language support
- [ ] Workflow versioning
- [ ] API rate limiting
- [ ] Webhook retry logic

---

## 📚 Tech Stack Summary

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Backend** | FastAPI | REST API + WebSocket |
| **Database** | PostgreSQL | Main data store |
| **Vector DB** | Qdrant | Semantic search |
| **Cache/Queue** | Redis/Valkey | Background jobs |
| **AI** | Google Gemini | LLM responses |
| **Embeddings** | Gemini Embeddings | Text vectorization |
| **ORM** | SQLAlchemy | Database abstraction |
| **Validation** | Pydantic | Request/response validation |
| **Frontend** | React + Vite | Flow builder UI |
| **Deployment** | Docker Compose | Container orchestration |
| **Worker** | RQ (Redis Queue) | Async task processing |

---

## 💡 Conclusion

This project demonstrates a **production-ready**, **scalable**, and **maintainable** system that combines multiple advanced concepts:
- **RAG** for intelligent responses
- **Visual workflow automation** for business users
- **Real-time communication** via WebSockets
- **Async processing** for performance
- **Modern Python** best practices

Perfect for discussing **system design**, **API architecture**, **AI integration**, and **scalability** in technical interviews! 🎯
