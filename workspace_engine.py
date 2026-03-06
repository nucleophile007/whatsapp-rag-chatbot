import logging
import os
import re
import time
from typing import Dict, Any, Optional, List, Set
from redis import Redis
from sqlalchemy.orm import Session
from database import Workspace

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class WorkspaceEngine:
    """RAG aur Prompts handle karne wala system"""
    
    def __init__(self):
        if not GOOGLE_API_KEY:
            logger.error("Bhai, GOOGLE_API_KEY hi nahi mil raha!")
        self.dedupe_ttl = max(0, int(os.getenv("WEBHOOK_DEDUP_TTL_SECONDS", "600")))

        self.redis = None
        self._memory_seen_messages: Dict[str, float] = {}

        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        try:
            self.redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
            self.redis.ping()
            logger.info(f"✅ WorkspaceEngine Redis connected: {redis_host}:{redis_port}")
        except Exception as e:
            logger.warning(f"⚠️ WorkspaceEngine Redis unavailable, using memory fallback: {e}")
            self.redis = None

    def _compact_memory_state(self):
        now = time.time()
        for key, expires_at in list(self._memory_seen_messages.items()):
            if expires_at <= now:
                del self._memory_seen_messages[key]

    def _is_new_message(self, workspace: Workspace, message_id: Optional[str]) -> bool:
        if not message_id or self.dedupe_ttl <= 0:
            return True
        dedupe_key = f"workspace:message:{workspace.id}:{message_id}"
        if self.redis:
            try:
                inserted = self.redis.set(dedupe_key, "1", ex=self.dedupe_ttl, nx=True)
                return bool(inserted)
            except Exception as e:
                logger.warning(f"Message dedupe check failed, fallback memory: {e}")
        now = time.time()
        expires_at = self._memory_seen_messages.get(dedupe_key)
        if expires_at and expires_at > now:
            return False
        self._memory_seen_messages[dedupe_key] = now + self.dedupe_ttl
        if len(self._memory_seen_messages) > 10000:
            self._compact_memory_state()
        return True

    def _normalize_bot_lid(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.lstrip("@")
        return text.split("@")[0].strip()

    def _as_bool(self, value: Any, default: bool) -> bool:
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

    def _split_tokens(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            parts = [str(item) for item in value]
        else:
            parts = re.split(r"[,\n;]+", str(value))
        return [part.strip() for part in parts if str(part).strip()]

    def _strict_text_mention(self, body: str, tag: str) -> bool:
        if not body or not tag:
            return False
        # Single @ only; @@tag should not match.
        pattern = rf"(?<![@\w])@{re.escape(tag)}(?!\w)"
        return re.search(pattern, body) is not None

    def _collect_mentioned_ids(self, payload: Dict[str, Any], top_level_mentioned_ids: List[Any]) -> Set[str]:
        normalized_ids: Set[str] = set()
        for m_id in top_level_mentioned_ids or []:
            normalized = self._normalize_bot_lid(m_id)
            if normalized:
                normalized_ids.add(normalized)

        try:
            deep_mentions = (
                payload.get("_data", {})
                .get("message", {})
                .get("extendedTextMessage", {})
                .get("contextInfo", {})
                .get("mentionedJid", [])
            )
        except Exception:
            deep_mentions = []

        for m_id in deep_mentions or []:
            normalized = self._normalize_bot_lid(m_id)
            if normalized:
                normalized_ids.add(normalized)

        return normalized_ids

    def _find_mention_node_config(self, flow: Any) -> Dict[str, Any]:
        definition = flow.definition if isinstance(flow.definition, dict) else {}
        for node in definition.get("nodes", []):
            node_data = node.get("data", {}) if isinstance(node, dict) else {}
            sub_type = node_data.get("subType") or node_data.get("type")
            if sub_type != "whatsapp_mention":
                continue
            node_config = node_data.get("config", {}) if isinstance(node_data, dict) else {}
            if isinstance(node_config, dict):
                return node_config
        return {}

    def _resolve_mention_match_config(self, flow: Any, default_bot_lid: str) -> Dict[str, Any]:
        trigger_config = flow.trigger_config if isinstance(flow.trigger_config, dict) else {}
        node_config = self._find_mention_node_config(flow)
        merged = {**trigger_config, **node_config}

        configured_bot_lid = self._normalize_bot_lid(merged.get("bot_lid")) or default_bot_lid
        specific_jids = [self._normalize_bot_lid(token) for token in self._split_tokens(merged.get("mention_specific_jids", ""))]
        specific_jids = [token for token in specific_jids if token]
        text_aliases = [token.lstrip("@") for token in self._split_tokens(merged.get("mention_text_aliases", ""))]
        text_aliases = [token for token in text_aliases if token]

        if configured_bot_lid and configured_bot_lid not in text_aliases:
            text_aliases.append(configured_bot_lid)

        match_self_lid = self._as_bool(merged.get("mention_match_self_lid"), True)
        match_specific_jids = self._as_bool(merged.get("mention_match_specific_jids"), False)
        match_text_aliases = self._as_bool(merged.get("mention_match_text_aliases"), True)

        if not (match_self_lid or match_specific_jids or match_text_aliases):
            # Safe fallback: keep trigger usable instead of silently disabling all checks.
            match_self_lid = True
            match_text_aliases = True

        return {
            "match_self_lid": match_self_lid,
            "match_specific_jids": match_specific_jids,
            "match_text_aliases": match_text_aliases,
            "configured_bot_lid": configured_bot_lid,
            "specific_jids": specific_jids,
            "text_aliases": text_aliases,
        }

    def _message_matches_mention_config(
        self,
        payload: Dict[str, Any],
        body: str,
        mentioned_ids: List[Any],
        mention_config: Dict[str, Any],
    ) -> bool:
        mentioned_tokens = self._collect_mentioned_ids(payload, mentioned_ids)

        if mention_config["match_self_lid"]:
            self_lid = self._normalize_bot_lid(payload.get("me", {}).get("lid"))
            if self_lid and self_lid in mentioned_tokens:
                return True

        if mention_config["match_specific_jids"]:
            for configured_jid in mention_config["specific_jids"]:
                if configured_jid in mentioned_tokens:
                    return True

        if mention_config["match_text_aliases"]:
            for alias in mention_config["text_aliases"]:
                if self._strict_text_mention(body, alias):
                    return True

        return False

    async def execute_workspace(self, workspace: Workspace, payload: Dict[str, Any], db: Session):
        """
        Workspace execution ab strictly logic layers (flows) par dependent hai.
        Agar workspace mein enabled flow nahi hai, to kuch execute nahi hota.
        """
        message_id = payload.get("message_id") or payload.get("id")
        body = payload.get("body") or ""
        mentioned_ids = payload.get("mentionedIds", [])
        default_bot_lid = self._normalize_bot_lid(payload.get("me", {}).get("lid")) or "35077249618150"

        if not self._is_new_message(workspace, message_id):
            logger.info(f"⏭️ Duplicate message skipped: workspace={workspace.name}, message_id={message_id}")
            return {"status": "skipped", "reason": "duplicate_message"}

        # Check karte hain koi customized flows toh nahi hain is workspace ke liye.
        from flow_engine import flow_engine
        from database import Flow, WorkspaceFlow
        
        try:
            flows = db.query(Flow).join(
                WorkspaceFlow, WorkspaceFlow.flow_id == Flow.id
            ).filter(
                WorkspaceFlow.workspace_id == workspace.id,
                Flow.is_enabled == True
            ).order_by(WorkspaceFlow.created_at.asc(), Flow.created_at.asc()).all()
        except Exception as mapping_error:
            logger.warning(f"workspace_flows lookup unavailable, fallback legacy mapping: {mapping_error}")
            flows = db.query(Flow).filter(
                Flow.workspace_id == workspace.id,
                Flow.is_enabled == True
            ).order_by(Flow.created_at.asc()).all()

        if not flows:
            logger.info(f"⏭️ Workspace {workspace.name} skip kiya: koi enabled logic layer attached nahi hai.")
            return {"status": "skipped", "reason": "no_logic_layers_attached"}

        attempted = 0
        failures = []
        for flow in flows:
            trigger_type = (flow.trigger_type or "").strip()
            should_run = False
            if trigger_type == "whatsapp_mention":
                mention_config = self._resolve_mention_match_config(flow, default_bot_lid)
                should_run = self._message_matches_mention_config(
                    payload=payload,
                    body=body,
                    mentioned_ids=mentioned_ids,
                    mention_config=mention_config,
                )
            elif trigger_type == "whatsapp_message":
                should_run = True

            if not should_run:
                continue

            attempted += 1
            logger.info(f"⚡ Flow trigger ho raha hai: {flow.name} ({trigger_type})")
            try:
                execution = await flow_engine.execute_flow(flow, payload, db, workspace=workspace)
                return {
                    "status": "success",
                    "triggered_flow": flow.name,
                    "execution_id": execution.id
                }
            except Exception as e:
                logger.error(f"Flow execution fail ho gaya ({flow.name}): {e}")
                failures.append({"flow": flow.name, "error": str(e)})

        if attempted == 0:
            logger.info(f"⏭️ Workspace {workspace.name} skip kiya: incoming message ke liye matching logic trigger nahi mila.")
            return {"status": "skipped", "reason": "no_matching_logic_trigger"}

        return {
            "status": "failed",
            "reason": "all_logic_layers_failed",
            "failures": failures
        }

workspace_engine = WorkspaceEngine()
