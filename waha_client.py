"""
WAHA API Client for WhatsApp operations
"""

import os
import requests
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class WAHAClient:
    """WAHA API (WhatsApp) se baat karne wala client"""
    
    def __init__(self):
        self.base_url = os.getenv("WAHA_URL", "http://waha:3000")
        self.api_key = os.getenv("WAHA_API_KEY", "Yahoo")
        self.session_name = os.getenv("WAHA_SESSION", "default")
        
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["X-API-Key"] = self.api_key
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method=method, url=url, headers=self.headers, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"WAHA API mein gadbad: {e}")
            return None
    
    def get_all_groups(self) -> List[Dict[str, Any]]:
        """Saare WhatsApp groups nikaalo"""
        result = self._make_request("GET", f"/api/{self.session_name}/chats")
        if not result:
            result = self._make_request("GET", f"/api/{self.session_name}/groups")
        
        if not result:
            return []
        
        groups_list = []
        processed_items = list(result.values()) if isinstance(result, dict) else result
            
        for item in processed_items:
            chat_id = item.get("id", "")
            if "@g.us" in chat_id:
                name = item.get("subject") or item.get("name") or "Anjaan Group"
                member_count = item.get("size") or len(item.get("participants", []))
                
                groups_list.append({
                    "chat_id": chat_id,
                    "name": name,
                    "description": item.get("desc") or item.get("description", ""),
                    "member_count": member_count,
                    "avatar_url": item.get("profilePicUrl", "")
                })
        
        return groups_list
    
    def get_group_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Kisi ek group ki puri detail nikaalo"""
        result = self._make_request("GET", f"/api/{self.session_name}/chats/{chat_id}")
        if not result:
            return None
        
        return {
            "chat_id": result.get("id", chat_id),
            "name": result.get("name", "Anjaan Group"),
            "description": result.get("description", ""),
            "member_count": len(result.get("participants", [])),
            "avatar_url": result.get("profilePicUrl", "")
        }
    
    def send_message(self, chat_id: str, text: str, reply_to: Optional[str] = None) -> bool:
        """WhatsApp message bhejne wala function"""
        payload = {
            "chatId": chat_id,
            "text": text,
            "session": self.session_name
        }
        if reply_to:
            payload["reply_to"] = reply_to
        
        result = self._make_request("POST", "/api/sendText", json=payload)
        if result:
            logger.info(f"✅ Message chala gaya: {chat_id}")
            return True
        return False
    
    def forward_message(self, from_chat: str, to_chat: str, message_id: str) -> bool:
        """Message forward karne ke liye"""
        payload = {
            "chatId": to_chat,
            "messageId": message_id,
            "session": self.session_name
        }
        result = self._make_request("POST", "/api/forwardMessage", json=payload)
        return bool(result)
    
    def get_session_status(self) -> Dict[str, Any]:
        """Session ka status check karo (Connected hai ya nahi)"""
        result = self._make_request("GET", f"/api/{self.session_name}/status")
        return result or {"status": "unknown"}

waha_client = WAHAClient()
