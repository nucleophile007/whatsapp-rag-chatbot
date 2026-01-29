import uuid
import json
from database.db import SessionLocal
from database.models import Flow

def seed_flow():
    """Bana-banaya flow database mein daalne ke liye"""
    db = SessionLocal()
    flow_id = "9a33a9f8-46ae-4b75-819b-604edf5de557"
    
    # Dekhte hain flow pehle se hai ya nahi
    flow = db.query(Flow).filter(Flow.id == uuid.UUID(flow_id)).first()
    if not flow:
        print(f"❌ Bhai, flow {flow_id} nahi mila. Pehle UI se bana lo.")
        return

    # 2. Define the requested flow
    definition = {
        "nodes": [
            {
                "id": "trigger_1",
                "type": "trigger",
                "data": {
                    "label": "On Mention",
                    "subType": "whatsapp_mention",
                    "config": {"bot_lid": ""}
                },
                "position": {"x": 100, "y": 100}
            },
            {
                "id": "rag_1",
                "type": "action",
                "data": {
                    "label": "RAG Query with Context",
                    "subType": "rag_query",
                    "config": {
                        "query": "{{trigger.body}}",
                        "include_conversation_history": True,
                        "context_limit": 5
                    }
                },
                "position": {"x": 100, "y": 250}
            },
            {
                "id": "reply_1",
                "type": "action",
                "data": {
                    "label": "Send Answer",
                    "subType": "send_whatsapp_message",
                    "config": {
                        "chat_id": "{{trigger.from}}",
                        "text": "{{rag_1.rag_result}}",
                        "reply_to": "{{trigger.id}}"
                    }
                },
                "position": {"x": 100, "y": 400}
            }
        ],
        "edges": [
            {"id": "e1-2", "source": "trigger_1", "target": "rag_1"},
            {"id": "e2-3", "source": "rag_1", "target": "reply_1"}
        ]
    }

    # 3. Update flow
    flow.definition = definition
    flow.trigger_type = "whatsapp_mention"
    flow.trigger_config = {"bot_lid": ""}
    flow.name = "AI RAG with 5-Msg Context"
    
    db.commit()
    print(f"✅ Flow {flow_id} update ho gaya, ab context wala logic chalega!")

if __name__ == "__main__":
    seed_flow()
