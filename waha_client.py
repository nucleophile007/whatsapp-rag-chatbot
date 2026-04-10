"""
WAHA API Client for WhatsApp operations
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class WAHAClient:
    """WAHA API (WhatsApp) se baat karne wala client"""
    
    def __init__(self):
        self.base_url = os.getenv("WAHA_URL", "http://waha:3000")
        self.api_key = os.getenv("WAHA_API_KEY", "Yahoo")
        self.session_name = os.getenv("WAHA_SESSION", "default")
        self.instance_map = self._load_instance_map(os.getenv("WAHA_INSTANCE_MAP", ""))
        
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["X-API-Key"] = self.api_key

    def _load_instance_map(self, raw_value: str) -> Dict[str, Dict[str, str]]:
        """
        Optional multi-instance routing for WAHA Core users.
        Example:
        {
          "default": {"url": "http://waha:3000", "session": "default"},
          "default2": {"url": "http://waha2:3000", "session": "default"}
        }
        """
        if not raw_value or not str(raw_value).strip():
            return {}

        try:
            parsed = json.loads(raw_value)
        except Exception as exc:
            logger.warning("Invalid WAHA_INSTANCE_MAP JSON: %s", exc)
            return {}

        if not isinstance(parsed, dict):
            logger.warning("WAHA_INSTANCE_MAP must be a JSON object")
            return {}

        normalized: Dict[str, Dict[str, str]] = {}
        for alias, config in parsed.items():
            alias_name = str(alias or "").strip()
            if not alias_name:
                continue

            if isinstance(config, str):
                url = config.strip()
                if not url:
                    continue
                normalized[alias_name] = {"url": url.rstrip("/"), "session": alias_name}
                continue

            if not isinstance(config, dict):
                continue

            url = str(config.get("url") or "").strip()
            if not url:
                continue
            session = str(config.get("session") or alias_name).strip() or alias_name
            normalized[alias_name] = {"url": url.rstrip("/"), "session": session}

        return normalized

    def _resolve_target(self, session_alias: Optional[str]) -> Tuple[str, str]:
        requested = str(session_alias or self.session_name or "default").strip() or "default"
        mapped = self.instance_map.get(requested)
        if mapped:
            return mapped["url"], mapped["session"]
        return self.base_url.rstrip("/"), requested

    def _make_request(self, method: str, endpoint: str, base_url: Optional[str] = None, **kwargs) -> Optional[Dict[str, Any]]:
        url = f"{(base_url or self.base_url).rstrip('/')}{endpoint}"
        try:
            response = requests.request(method=method, url=url, headers=self.headers, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"WAHA API mein gadbad: {e}")
            return None

    def send_payload(self, method: str, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generic WAHA request for message-style endpoints."""
        data = dict(payload)
        requested_session = str(data.get("session") or self.session_name).strip() or self.session_name
        base_url, routed_session = self._resolve_target(requested_session)
        data["session"] = routed_session
        return self._make_request(method, endpoint, base_url=base_url, json=data)

    def _typing_request(
        self,
        start: bool,
        chat_id: str,
        session_alias: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        chat_value = str(chat_id or "").strip()
        if not chat_value:
            return False, {"error": "chat_id_missing"}

        payload: Dict[str, Any] = {"chatId": chat_value}
        if session_alias is not None and str(session_alias).strip():
            payload["session"] = str(session_alias).strip()

        endpoints = ["/api/starttyping", "/api/startTyping"] if start else ["/api/stoptyping", "/api/stopTyping"]
        methods = ["POST", "PUT"]

        for endpoint in endpoints:
            for method in methods:
                result = self.send_payload(method, endpoint, payload)
                if result is not None:
                    return True, {"endpoint": endpoint, "method": method, "response": result}

        return False, {
            "error": "waha_typing_request_failed",
            "action": "start" if start else "stop",
            "chatId": chat_value,
            "session": payload.get("session"),
            "endpoints_tried": endpoints,
            "methods_tried": methods,
        }

    def start_typing(self, chat_id: str, session_alias: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Trigger WAHA typing indicator for a chat."""
        return self._typing_request(start=True, chat_id=chat_id, session_alias=session_alias)

    def stop_typing(self, chat_id: str, session_alias: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Stop WAHA typing indicator for a chat."""
        return self._typing_request(start=False, chat_id=chat_id, session_alias=session_alias)

    def _get_session_endpoint(self, suffix: str, session_alias: Optional[str] = None) -> Tuple[str, str]:
        base_url, routed_session = self._resolve_target(session_alias or self.session_name)
        return base_url, f"/api/{routed_session}/{suffix.lstrip('/')}"
    
    def get_all_groups(self) -> List[Dict[str, Any]]:
        """Saare WhatsApp groups nikaalo"""
        base_url, chats_endpoint = self._get_session_endpoint("chats")
        result = self._make_request("GET", chats_endpoint, base_url=base_url)
        if not result:
            base_url, groups_endpoint = self._get_session_endpoint("groups")
            result = self._make_request("GET", groups_endpoint, base_url=base_url)
        
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

    def get_all_contacts(
        self,
        session_alias: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all known contacts from WAHA store.
        Requires NOWEB store enabled + session in WORKING state.
        """
        base_url, routed_session = self._resolve_target(session_alias or self.session_name)
        base_params: Dict[str, Any] = {"session": routed_session}
        if sort_by:
            base_params["sortBy"] = str(sort_by).strip()
        if sort_order:
            base_params["sortOrder"] = str(sort_order).strip()

        param_candidates: List[Dict[str, Any]] = [dict(base_params)]
        # Compatibility fallback for WAHA builds that don't support sort params.
        if "sortBy" in base_params or "sortOrder" in base_params:
            param_candidates.append({"session": routed_session})

        for params in param_candidates:
            result = self._make_request(
                "GET",
                "/api/contacts/all",
                base_url=base_url,
                params=params,
            )
            if isinstance(result, list):
                return [item for item in result if isinstance(item, dict)]
            if isinstance(result, dict):
                nested = result.get("contacts")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        return []
    
    def send_message(self, chat_id: str, text: str, reply_to: Optional[str] = None) -> bool:
        """WhatsApp message bhejne wala function"""
        payload = {
            "chatId": chat_id,
            "text": text,
            "session": self.session_name
        }
        if reply_to:
            payload["reply_to"] = reply_to

        result = self.send_payload("POST", "/api/sendText", payload)
        if result:
            logger.info(f"✅ Message chala gaya: {chat_id}")
            return True
        return False
    
    def send_dynamic_message(self, message_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Send WAHA message with dynamic endpoint selection.
        Returns (success, response_or_error_payload).
        """
        endpoint_map = {
            "text": ("POST", "/api/sendText"),
            "image": ("POST", "/api/sendImage"),
            "file": ("POST", "/api/sendFile"),
            "voice": ("POST", "/api/sendVoice"),
            "video": ("POST", "/api/sendVideo"),
            "location": ("POST", "/api/sendLocation"),
            "poll": ("POST", "/api/sendPoll"),
            "poll_vote": ("POST", "/api/sendPollVote"),
            "forward": ("POST", "/api/forwardMessage"),
            "reaction": ("PUT", "/api/reaction"),
            "buttons": ("POST", "/api/sendButtons"),
        }

        key = (message_type or "text").strip().lower()
        method, endpoint = endpoint_map.get(key, endpoint_map["text"])
        result = self.send_payload(method, endpoint, payload)
        if result is None:
            return False, {"error": "waha_request_failed", "method": method, "endpoint": endpoint}
        return True, result
    
waha_client = WAHAClient()
