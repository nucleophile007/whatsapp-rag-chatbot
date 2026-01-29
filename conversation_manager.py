import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from redis import Redis

logger = logging.getLogger(__name__)

class ConversationManager:
    """Baatcheet yaad rakhne wala system (Redis ya Memory)"""
    
    def __init__(self):
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        
        self.redis = Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        
        try:
            self.redis.ping()
            logger.info(f"✅ Redis se connection jud gaya: {redis_host}:{redis_port}")
        except Exception as e:
            logger.warning(f"⚠️ Redis nahi mila, memory use kar rahe hain: {e}")
            self.redis = None
            self.conversations: Dict[str, List[Dict]] = {}
    
    def add_message(self, client_id: str, role: str, content: str):
        """Naya message history mein daalte hain"""
        message = {
            "role": role, 
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if self.redis:
            key = f"conversation:{client_id}"
            self.redis.rpush(key, json.dumps(message))
            self.redis.ltrim(key, -10, -1) # Last 10 messages hi kaafi hain
            self.redis.expire(key, 86400) # 24 ghante mein gayab
        else:
            if client_id not in self.conversations:
                self.conversations[client_id] = []
            self.conversations[client_id].append(message)
            if len(self.conversations[client_id]) > 10:
                self.conversations[client_id] = self.conversations[client_id][-10:]
    
    def get_history(self, client_id: str, limit: int = 10) -> List[Dict]:
        """Purani baatein yaad karne ke liye"""
        if self.redis:
            key = f"conversation:{client_id}"
            messages = self.redis.lrange(key, -limit, -1)
            return [json.loads(msg) for msg in messages]
        else:
            history = self.conversations.get(client_id, [])
            return history[-limit:]
    
    def clear_history(self, client_id: str):
        """Sab kuch bhula dete hain"""
        if self.redis:
            self.redis.delete(f"conversation:{client_id}")
        else:
            if client_id in self.conversations:
                del self.conversations[client_id]
    
    def get_context_string(self, client_id: str, limit: int = 5) -> str:
        """History ko string mein convert karte hain LLM ke liye"""
        history = self.get_history(client_id, limit=limit)
        if not history:
            return ""
        
        context_parts = []
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}")
        
        return "\n\n".join(context_parts)

conversation_manager = ConversationManager()
