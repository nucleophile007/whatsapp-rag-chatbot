import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from redis import Redis
from sqlmodel import select

from database import ConversationLongTermMemorySQLModel
from database.db import SessionLocal

logger = logging.getLogger(__name__)

MEMORY_SCOPE_CLIENT = "client"
MEMORY_SCOPE_CLIENT_WORKSPACE = "client_workspace"
MEMORY_SCOPES = {MEMORY_SCOPE_CLIENT, MEMORY_SCOPE_CLIENT_WORKSPACE}


_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}", flags=re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", flags=re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\-\s]{8,}\d)")

_STOPWORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "to",
    "of",
    "for",
    "and",
    "or",
    "in",
    "on",
    "at",
    "with",
    "from",
    "about",
    "please",
    "help",
    "can",
    "you",
    "me",
    "my",
    "i",
    "we",
    "our",
    "it",
    "this",
    "that",
}


class ConversationManager:
    """Baatcheet yaad rakhne wala system (Redis ya Memory)"""

    def __init__(self):
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.stm_raw_limit = max(20, int(os.getenv("STM_RAW_MESSAGE_LIMIT", "40")))
        self.stm_default_context_limit = max(6, int(os.getenv("STM_DEFAULT_CONTEXT_LIMIT", "24")))
        self.stm_context_token_budget = max(300, int(os.getenv("STM_CONTEXT_TOKEN_BUDGET", "1200")))
        self.stm_semantic_pool = max(20, int(os.getenv("STM_SEMANTIC_POOL", "80")))
        self.stm_semantic_top_k = max(2, int(os.getenv("STM_SEMANTIC_TOP_K", "6")))
        self.stm_summary_max_chars = max(200, int(os.getenv("STM_SUMMARY_MAX_CHARS", "900")))
        self.history_ttl_seconds = max(3600, int(os.getenv("CONVERSATION_HISTORY_TTL_SECONDS", "604800")))
        self.summary_ttl_seconds = max(3600, int(os.getenv("CONVERSATION_SUMMARY_TTL_SECONDS", "604800")))
        self.slots_ttl_seconds = max(3600, int(os.getenv("CONVERSATION_SLOTS_TTL_SECONDS", "604800")))
        self.ltm_enabled = os.getenv("CONVERSATION_LTM_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        self.ltm_max_items = max(2, int(os.getenv("CONVERSATION_LTM_MAX_ITEMS", "6")))
        self.ltm_min_confidence = float(os.getenv("CONVERSATION_LTM_MIN_CONFIDENCE", "0.72"))
        self.default_memory_scope = self._resolve_memory_scope(
            os.getenv("CONVERSATION_MEMORY_SCOPE", MEMORY_SCOPE_CLIENT)
        )

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
            self.summary_cache: Dict[str, str] = {}
            self.slots_cache: Dict[str, Dict[str, Any]] = {}

    def _resolve_memory_scope(self, memory_scope: Optional[str]) -> str:
        candidate = str(memory_scope or "").strip().lower()
        if candidate in MEMORY_SCOPES:
            return candidate
        return MEMORY_SCOPE_CLIENT

    def get_default_memory_scope(self) -> str:
        return self.default_memory_scope

    def _scoped_client_id(
        self,
        client_id: str,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> str:
        base_client_id = self._normalize_space(client_id)
        if not base_client_id:
            return ""

        resolved_scope = self._resolve_memory_scope(memory_scope or self.default_memory_scope)
        if resolved_scope != MEMORY_SCOPE_CLIENT_WORKSPACE:
            return base_client_id

        workspace_token = self._normalize_space(workspace_id or "")
        if not workspace_token:
            return base_client_id

        return f"{base_client_id}::ws:{workspace_token}"

    def _conversation_key(self, client_id: str) -> str:
        return f"conversation:{client_id}"

    def _summary_key(self, client_id: str) -> str:
        return f"conversation_summary:{client_id}"

    def _slots_key(self, client_id: str) -> str:
        return f"conversation_slots:{client_id}"

    def _normalize_space(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _clip_text(self, text: str, max_chars: int) -> str:
        value = self._normalize_space(text)
        if len(value) <= max_chars:
            return value
        clipped = value[: max(0, max_chars - 1)].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        return f"{clipped}…".strip()

    def _approx_tokens(self, text: str) -> int:
        if not text:
            return 0
        # Cheap approximation: 1 token ~= 0.75 words
        words = len(re.findall(r"\S+", text))
        return max(1, int(words * 1.3))

    def _tokenize(self, text: str) -> List[str]:
        tokens = [m.group(0).lower() for m in _TOKEN_PATTERN.finditer(str(text or ""))]
        return [tok for tok in tokens if tok not in _STOPWORDS]

    def _msg_line(self, message: Dict[str, Any]) -> str:
        role = "User" if str(message.get("role") or "").lower() == "user" else "Assistant"
        return f"{role}: {self._normalize_space(message.get('content') or '')}"

    def _load_slots(self, client_id: str) -> Dict[str, Any]:
        if self.redis:
            try:
                raw = self.redis.get(self._slots_key(client_id))
                if raw:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        return loaded
            except Exception as e:
                logger.warning("Failed to read slots for %s: %s", client_id, e)
        return dict(self.slots_cache.get(client_id, {})) if hasattr(self, "slots_cache") else {}

    def _save_slots(self, client_id: str, slots: Dict[str, Any]) -> None:
        clean_slots = {
            "current_topic": self._clip_text(str(slots.get("current_topic") or ""), 120),
            "open_tasks": [self._clip_text(str(item), 120) for item in (slots.get("open_tasks") or []) if str(item).strip()],
            "last_entities": [self._clip_text(str(item), 80) for item in (slots.get("last_entities") or []) if str(item).strip()],
        }
        clean_slots["open_tasks"] = list(dict.fromkeys(clean_slots["open_tasks"]))[-5:]
        clean_slots["last_entities"] = list(dict.fromkeys(clean_slots["last_entities"]))[-6:]

        if self.redis:
            try:
                self.redis.set(self._slots_key(client_id), json.dumps(clean_slots), ex=self.slots_ttl_seconds)
                return
            except Exception as e:
                logger.warning("Failed to write slots for %s: %s", client_id, e)
        if hasattr(self, "slots_cache"):
            self.slots_cache[client_id] = clean_slots

    def _extract_topic(self, content: str) -> str:
        text = self._normalize_space(content)
        if not text:
            return ""
        text = re.sub(r"^\s*(?:please|can you|could you|help me)\s+", "", text, flags=re.IGNORECASE)
        return self._clip_text(text, 90)

    def _extract_entities(self, content: str) -> List[str]:
        tokens = re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", str(content or ""))
        entities = [token.strip() for token in tokens if token.lower() not in _STOPWORDS]
        return list(dict.fromkeys(entities))[:6]

    def _extract_open_tasks(self, content: str) -> List[str]:
        text = self._normalize_space(content)
        if not text:
            return []
        patterns = [
            r"\b(?:i need to|i want to|please|help me|can you)\b\s+(.+)$",
            r"\b(?:todo|task)\b\s*[:\-]\s*(.+)$",
        ]
        tasks: List[str] = []
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                tasks.append(self._clip_text(match.group(1), 120))
        return [task for task in tasks if task]

    def _update_slots(self, client_id: str, role: str, content: str) -> None:
        if str(role).lower() != "user":
            return
        slots = self._load_slots(client_id)
        slots["current_topic"] = self._extract_topic(content)

        existing_tasks = list(slots.get("open_tasks") or [])
        existing_tasks.extend(self._extract_open_tasks(content))
        slots["open_tasks"] = existing_tasks

        existing_entities = list(slots.get("last_entities") or [])
        existing_entities.extend(self._extract_entities(content))
        slots["last_entities"] = existing_entities
        self._save_slots(client_id, slots)

    def _build_summary(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return ""
        selected = history[-8:]
        lines: List[str] = []
        for message in selected:
            role = "User" if str(message.get("role") or "").lower() == "user" else "Assistant"
            content = self._clip_text(str(message.get("content") or ""), 180)
            if not content:
                continue
            lines.append(f"- {role}: {content}")
        summary = "\n".join(lines).strip()
        if len(summary) <= self.stm_summary_max_chars:
            return summary
        truncated = summary[: max(0, self.stm_summary_max_chars - 1)].rstrip()
        if "\n" in truncated:
            truncated = truncated[: truncated.rfind("\n")].rstrip()
        return f"{truncated}\n- …".strip()

    def _save_summary(self, client_id: str, summary: str) -> None:
        if self.redis:
            try:
                self.redis.set(self._summary_key(client_id), summary, ex=self.summary_ttl_seconds)
                return
            except Exception as e:
                logger.warning("Failed to write summary for %s: %s", client_id, e)
        if hasattr(self, "summary_cache"):
            self.summary_cache[client_id] = summary

    def _get_summary(self, client_id: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
        if self.redis:
            try:
                existing = self.redis.get(self._summary_key(client_id))
                if existing:
                    return str(existing)
            except Exception as e:
                logger.warning("Failed to read summary for %s: %s", client_id, e)
        elif hasattr(self, "summary_cache"):
            existing = self.summary_cache.get(client_id)
            if existing:
                return existing

        summary = self._build_summary(history or self.get_history(client_id, limit=self.stm_raw_limit))
        if summary:
            self._save_summary(client_id, summary)
        return summary

    def _extract_memory_candidates(self, role: str, content: str) -> List[Dict[str, Any]]:
        if str(role).lower() != "user":
            return []

        text = self._normalize_space(content)
        if not text:
            return []

        candidates: List[Dict[str, Any]] = []

        name_match = re.search(r"\bmy name is\s+([A-Za-z][A-Za-z\s\-\']{1,40})", text, flags=re.IGNORECASE)
        if name_match:
            name_value = self._clip_text(name_match.group(1), 60)
            candidates.append(
                {
                    "memory_key": "profile:name",
                    "memory_text": f"User name is {name_value}",
                    "category": "profile",
                    "confidence": 0.95,
                }
            )

        for email in _EMAIL_PATTERN.findall(text):
            normalized_email = email.strip().lower()
            candidates.append(
                {
                    "memory_key": "contact:email",
                    "memory_text": f"User email is {normalized_email}",
                    "category": "contact",
                    "confidence": 0.95,
                }
            )

        for raw_phone in _PHONE_PATTERN.findall(text):
            digits = re.sub(r"\D", "", raw_phone)
            if len(digits) < 10:
                continue
            candidates.append(
                {
                    "memory_key": "contact:phone",
                    "memory_text": f"User phone is {digits}",
                    "category": "contact",
                    "confidence": 0.9,
                }
            )

        pref_patterns = [
            r"\bi prefer\s+(.+)$",
            r"\bi like\s+(.+)$",
            r"\bplease always\s+(.+)$",
        ]
        for pattern in pref_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            pref = self._clip_text(match.group(1), 120)
            if not pref:
                continue
            pref_key = hashlib.sha1(pref.lower().encode("utf-8")).hexdigest()[:12]
            candidates.append(
                {
                    "memory_key": f"preference:{pref_key}",
                    "memory_text": f"User preference: {pref}",
                    "category": "preference",
                    "confidence": 0.8,
                }
            )

        goal_patterns = [
            r"\bi want to\s+(.+)$",
            r"\bi need to\s+(.+)$",
            r"\bmy goal is to\s+(.+)$",
        ]
        for pattern in goal_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            goal = self._clip_text(match.group(1), 120)
            if not goal:
                continue
            goal_key = hashlib.sha1(goal.lower().encode("utf-8")).hexdigest()[:12]
            candidates.append(
                {
                    "memory_key": f"goal:{goal_key}",
                    "memory_text": f"User goal: {goal}",
                    "category": "goal",
                    "confidence": 0.78,
                }
            )

        deduped: Dict[str, Dict[str, Any]] = {}
        for item in candidates:
            deduped[item["memory_key"]] = item
        return list(deduped.values())

    def _upsert_long_term_memory(self, client_id: str, role: str, content: str) -> None:
        if not self.ltm_enabled:
            return
        candidates = self._extract_memory_candidates(role=role, content=content)
        if not candidates:
            return

        now = datetime.utcnow()
        try:
            with SessionLocal() as db:
                for candidate in candidates:
                    confidence = float(candidate.get("confidence") or 0.0)
                    if confidence < self.ltm_min_confidence:
                        continue

                    memory_key = str(candidate.get("memory_key") or "").strip()
                    if not memory_key:
                        continue
                    memory_text = self._clip_text(str(candidate.get("memory_text") or ""), 400)
                    if not memory_text:
                        continue

                    existing = db.execute(
                        select(ConversationLongTermMemorySQLModel).where(
                            ConversationLongTermMemorySQLModel.client_id == client_id,
                            ConversationLongTermMemorySQLModel.memory_key == memory_key,
                            ConversationLongTermMemorySQLModel.is_active == True,  # noqa: E712
                        )
                    ).scalars().first()
                    if existing:
                        existing.memory_text = memory_text
                        existing.memory_category = str(candidate.get("category") or existing.memory_category or "general")
                        existing.confidence = max(float(existing.confidence or 0.0), confidence)
                        existing.source_message = self._clip_text(content, 260)
                        existing.last_seen_at = now
                        existing.updated_at = now
                        existing.hit_count = int(existing.hit_count or 0) + 1
                        metadata = dict(existing.memory_metadata or {})
                        metadata["updated_from"] = "conversation_manager"
                        existing.memory_metadata = metadata
                    else:
                        db.add(
                            ConversationLongTermMemorySQLModel(
                                client_id=client_id,
                                memory_key=memory_key,
                                memory_text=memory_text,
                                memory_category=str(candidate.get("category") or "general"),
                                confidence=confidence,
                                source_message=self._clip_text(content, 260),
                                hit_count=1,
                                is_active=True,
                                memory_metadata={"source": "conversation_manager"},
                                last_seen_at=now,
                            )
                        )
                db.commit()
        except Exception as e:
            logger.warning("LTM upsert failed for %s: %s", client_id, e)

    def _score_semantic_message(
        self,
        message: Dict[str, Any],
        query_tokens: List[str],
        index: int,
        total: int,
    ) -> float:
        if not query_tokens:
            return 0.0
        content = str(message.get("content") or "")
        content_tokens = self._tokenize(content)
        if not content_tokens:
            return 0.0

        token_set = set(content_tokens)
        overlap = sum(1 for token in query_tokens if token in token_set)
        coverage = overlap / max(1, len(set(query_tokens)))
        tf = sum(min(3, content_tokens.count(token)) for token in set(query_tokens))
        tf_ratio = tf / max(1, len(set(query_tokens)) * 3)

        recency = (index + 1) / max(1, total)
        return (0.62 * coverage) + (0.23 * tf_ratio) + (0.15 * recency)

    def _retrieve_semantic_messages(
        self,
        history: List[Dict[str, Any]],
        query: str,
        top_k: int,
        recent_skip_count: int,
    ) -> List[Dict[str, Any]]:
        query_tokens = self._tokenize(query)
        if not query_tokens or not history:
            return []

        older_pool = history[:-recent_skip_count] if recent_skip_count > 0 else history
        if not older_pool:
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        total = len(older_pool)
        for idx, message in enumerate(older_pool):
            score = self._score_semantic_message(message, query_tokens=query_tokens, index=idx, total=total)
            if score >= 0.16:
                scored.append((score, message))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[: max(0, top_k)]]

    def _fetch_ltm_memories(self, client_id: str, query: str, limit: int) -> List[ConversationLongTermMemorySQLModel]:
        if not self.ltm_enabled or not client_id:
            return []
        try:
            with SessionLocal() as db:
                memories = db.execute(
                    select(ConversationLongTermMemorySQLModel).where(
                        ConversationLongTermMemorySQLModel.client_id == client_id,
                        ConversationLongTermMemorySQLModel.is_active == True,  # noqa: E712
                    )
                ).scalars().all()
        except Exception as e:
            logger.warning("LTM fetch failed for %s: %s", client_id, e)
            return []

        if not memories:
            return []

        q_tokens = self._tokenize(query)
        ranked: List[Tuple[float, ConversationLongTermMemorySQLModel]] = []
        for memory in memories:
            base = float(memory.confidence or 0.0)
            text_tokens = set(self._tokenize(memory.memory_text or ""))
            lexical = 0.0
            if q_tokens and text_tokens:
                overlap = sum(1 for token in set(q_tokens) if token in text_tokens)
                lexical = overlap / max(1, len(set(q_tokens)))
            score = (0.65 * base) + (0.35 * lexical)
            ranked.append((score, memory))
        def _memory_sort_key(item: Tuple[float, ConversationLongTermMemorySQLModel]) -> Tuple[float, float]:
            score, memory = item
            dt = memory.last_seen_at or memory.updated_at or memory.created_at
            ts = float(dt.timestamp()) if dt else 0.0
            return score, ts

        ranked.sort(key=_memory_sort_key, reverse=True)
        return [item[1] for item in ranked[: max(0, limit)]]

    def _trim_lines_to_budget(self, lines: List[str], token_budget: int) -> List[str]:
        selected: List[str] = []
        consumed = 0
        for line in reversed(lines):
            cost = self._approx_tokens(line)
            if selected and (consumed + cost) > token_budget:
                break
            if not selected and cost > token_budget:
                selected.append(self._clip_text(line, max(40, int(token_budget * 3))))
                break
            selected.append(line)
            consumed += cost
        selected.reverse()
        return selected

    def add_message(
        self,
        client_id: str,
        role: str,
        content: str,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ):
        """Naya message history mein daalte hain"""
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        if not scoped_client_id:
            return
        message = {
            "role": str(role or "").strip().lower() or "user",
            "content": self._normalize_space(content),
            "timestamp": datetime.now().isoformat()
        }

        if self.redis:
            key = self._conversation_key(scoped_client_id)
            self.redis.rpush(key, json.dumps(message))
            self.redis.ltrim(key, -self.stm_raw_limit, -1)
            self.redis.expire(key, self.history_ttl_seconds)
        else:
            if scoped_client_id not in self.conversations:
                self.conversations[scoped_client_id] = []
            self.conversations[scoped_client_id].append(message)
            if len(self.conversations[scoped_client_id]) > self.stm_raw_limit:
                self.conversations[scoped_client_id] = self.conversations[scoped_client_id][-self.stm_raw_limit:]

        history_for_summary = self.get_history(
            client_id,
            limit=min(self.stm_raw_limit, 30),
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        summary = self._build_summary(history_for_summary)
        if summary:
            self._save_summary(scoped_client_id, summary)
        self._update_slots(client_id=scoped_client_id, role=message["role"], content=message["content"])
        self._upsert_long_term_memory(client_id=scoped_client_id, role=message["role"], content=message["content"])

    def get_history(
        self,
        client_id: str,
        limit: int = 10,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> List[Dict]:
        """Purani baatein yaad karne ke liye"""
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        if not scoped_client_id:
            return []
        safe_limit = max(1, int(limit or 10))
        if self.redis:
            key = self._conversation_key(scoped_client_id)
            messages = self.redis.lrange(key, -safe_limit, -1)
            parsed: List[Dict[str, Any]] = []
            for msg in messages:
                try:
                    loaded = json.loads(msg)
                except Exception:
                    continue
                if isinstance(loaded, dict):
                    parsed.append(loaded)
            return parsed
        else:
            history = self.conversations.get(scoped_client_id, [])
            return history[-safe_limit:]

    def clear_history(
        self,
        client_id: str,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ):
        """Sab kuch bhula dete hain"""
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        if not scoped_client_id:
            return
        if self.redis:
            self.redis.delete(
                self._conversation_key(scoped_client_id),
                self._summary_key(scoped_client_id),
                self._slots_key(scoped_client_id),
            )
        else:
            if scoped_client_id in self.conversations:
                del self.conversations[scoped_client_id]
            if hasattr(self, "summary_cache") and scoped_client_id in self.summary_cache:
                del self.summary_cache[scoped_client_id]
            if hasattr(self, "slots_cache") and scoped_client_id in self.slots_cache:
                del self.slots_cache[scoped_client_id]

        if self.ltm_enabled:
            try:
                with SessionLocal() as db:
                    memories = db.execute(
                        select(ConversationLongTermMemorySQLModel).where(
                            ConversationLongTermMemorySQLModel.client_id == scoped_client_id
                        )
                    ).scalars().all()
                    for memory in memories:
                        memory.is_active = False
                    db.commit()
            except Exception as e:
                logger.warning("Failed to clear LTM for %s: %s", scoped_client_id, e)

    def get_summary(
        self,
        client_id: str,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> str:
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        history = self.get_history(
            client_id,
            limit=self.stm_raw_limit,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        return self._get_summary(scoped_client_id, history=history) if scoped_client_id else ""

    def get_slots(
        self,
        client_id: str,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        return self._load_slots(scoped_client_id) if scoped_client_id else {}

    def list_long_term_memories(
        self,
        client_id: str,
        include_inactive: bool = False,
        limit: int = 50,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.ltm_enabled:
            return []
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        if not scoped_client_id:
            return []

        safe_limit = max(1, int(limit or 50))
        rows: List[ConversationLongTermMemorySQLModel] = []
        try:
            with SessionLocal() as db:
                query = select(ConversationLongTermMemorySQLModel).where(
                    ConversationLongTermMemorySQLModel.client_id == scoped_client_id
                )
                if not include_inactive:
                    query = query.where(ConversationLongTermMemorySQLModel.is_active == True)  # noqa: E712
                rows = db.execute(query).scalars().all()
        except Exception as e:
            logger.warning("Failed to list LTM for %s: %s", scoped_client_id, e)
            return []

        def sort_key(item: ConversationLongTermMemorySQLModel) -> Tuple[float, float]:
            dt = item.last_seen_at or item.updated_at or item.created_at
            ts = float(dt.timestamp()) if dt else 0.0
            return float(item.confidence or 0.0), ts

        rows.sort(key=sort_key, reverse=True)
        serialized: List[Dict[str, Any]] = []
        for row in rows[:safe_limit]:
            serialized.append(
                {
                    "memory_key": row.memory_key,
                    "memory_text": row.memory_text,
                    "memory_category": row.memory_category,
                    "confidence": float(row.confidence or 0.0),
                    "hit_count": int(row.hit_count or 0),
                    "is_active": bool(row.is_active),
                    "source_message": row.source_message,
                    "metadata": row.memory_metadata or {},
                    "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return serialized

    def upsert_long_term_memory(
        self,
        client_id: str,
        memory_key: str,
        memory_text: str,
        memory_category: Optional[str] = None,
        confidence: Optional[float] = None,
        is_active: Optional[bool] = None,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.ltm_enabled:
            raise ValueError("Long-term memory is disabled")
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        if not scoped_client_id:
            raise ValueError("client_id is required")

        key = self._normalize_space(memory_key)
        text_value = self._normalize_space(memory_text)
        if not key:
            raise ValueError("memory_key is required")
        if not text_value:
            raise ValueError("memory_text is required")

        now = datetime.utcnow()
        safe_confidence = float(confidence) if confidence is not None else None
        if safe_confidence is not None:
            safe_confidence = max(0.0, min(1.0, safe_confidence))
        safe_category = self._normalize_space(memory_category or "") or "general"

        try:
            with SessionLocal() as db:
                existing = db.execute(
                    select(ConversationLongTermMemorySQLModel).where(
                        ConversationLongTermMemorySQLModel.client_id == scoped_client_id,
                        ConversationLongTermMemorySQLModel.memory_key == key,
                    )
                ).scalars().first()

                if existing:
                    existing.memory_text = text_value
                    existing.memory_category = safe_category
                    if safe_confidence is not None:
                        existing.confidence = safe_confidence
                    if is_active is not None:
                        existing.is_active = bool(is_active)
                    existing.last_seen_at = now
                    existing.updated_at = now
                    existing.hit_count = int(existing.hit_count or 0) + 1
                    metadata = dict(existing.memory_metadata or {})
                    metadata["updated_from"] = "memory_debug_api"
                    existing.memory_metadata = metadata
                    db.commit()
                    db.refresh(existing)
                    row = existing
                else:
                    row = ConversationLongTermMemorySQLModel(
                        client_id=scoped_client_id,
                        memory_key=key,
                        memory_text=text_value,
                        memory_category=safe_category,
                        confidence=safe_confidence if safe_confidence is not None else self.ltm_min_confidence,
                        is_active=True if is_active is None else bool(is_active),
                        hit_count=1,
                        source_message="manual memory debug update",
                        memory_metadata={"source": "memory_debug_api"},
                        last_seen_at=now,
                    )
                    db.add(row)
                    db.commit()
                    db.refresh(row)

                return {
                    "memory_key": row.memory_key,
                    "memory_text": row.memory_text,
                    "memory_category": row.memory_category,
                    "confidence": float(row.confidence or 0.0),
                    "hit_count": int(row.hit_count or 0),
                    "is_active": bool(row.is_active),
                    "source_message": row.source_message,
                    "metadata": row.memory_metadata or {},
                    "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
        except Exception as e:
            logger.warning("Failed to upsert LTM for %s/%s: %s", scoped_client_id, key, e)
            raise

    def deactivate_long_term_memory(
        self,
        client_id: str,
        memory_key: str,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> bool:
        if not self.ltm_enabled:
            return False
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=memory_scope,
        )
        if not scoped_client_id:
            return False
        key = self._normalize_space(memory_key)
        if not key:
            return False
        try:
            with SessionLocal() as db:
                row = db.execute(
                    select(ConversationLongTermMemorySQLModel).where(
                        ConversationLongTermMemorySQLModel.client_id == scoped_client_id,
                        ConversationLongTermMemorySQLModel.memory_key == key,
                        ConversationLongTermMemorySQLModel.is_active == True,  # noqa: E712
                    )
                ).scalars().first()
                if not row:
                    return False
                row.is_active = False
                row.updated_at = datetime.utcnow()
                metadata = dict(row.memory_metadata or {})
                metadata["deactivated_from"] = "memory_debug_api"
                row.memory_metadata = metadata
                db.commit()
                return True
        except Exception as e:
            logger.warning("Failed to deactivate LTM for %s/%s: %s", scoped_client_id, key, e)
            return False

    def get_memory_debug_snapshot(
        self,
        client_id: str,
        query: str = "",
        history_limit: int = 24,
        token_budget: Optional[int] = None,
        ltm_limit: int = 50,
        include_inactive: bool = False,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_scope = self._resolve_memory_scope(memory_scope or self.default_memory_scope)
        effective_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        history = self.get_history(
            client_id,
            limit=max(1, int(history_limit)),
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        summary = self.get_summary(
            client_id,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        slots = self.get_slots(
            client_id,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        context_preview = self.get_context_string(
            client_id,
            limit=max(2, int(history_limit)),
            query=query,
            token_budget=token_budget,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        ltm_items = self.list_long_term_memories(
            client_id=client_id,
            include_inactive=include_inactive,
            limit=ltm_limit,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        return {
            "client_id": client_id,
            "workspace_id": self._normalize_space(workspace_id or "") or None,
            "memory_scope": resolved_scope,
            "effective_client_id": effective_client_id,
            "history_count": len(history),
            "ltm_count": len(ltm_items),
            "summary": summary,
            "slots": slots,
            "history": history,
            "context_preview": context_preview,
            "ltm_items": ltm_items,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def get_context_string(
        self,
        client_id: str,
        limit: int = 5,
        query: str = "",
        token_budget: Optional[int] = None,
        workspace_id: Optional[str] = None,
        memory_scope: Optional[str] = None,
    ) -> str:
        """History ko string mein convert karte hain LLM ke liye"""
        resolved_scope = self._resolve_memory_scope(memory_scope or self.default_memory_scope)
        scoped_client_id = self._scoped_client_id(
            client_id=client_id,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        if not scoped_client_id:
            return ""
        recent_limit = max(2, int(limit or self.stm_default_context_limit))
        total_pool_limit = max(recent_limit, self.stm_semantic_pool)
        history = self.get_history(
            client_id,
            limit=total_pool_limit,
            workspace_id=workspace_id,
            memory_scope=resolved_scope,
        )
        if not history:
            return ""

        effective_budget = max(180, int(token_budget or self.stm_context_token_budget))
        summary = self._get_summary(scoped_client_id, history=history)
        slots = self._load_slots(scoped_client_id)
        semantic_messages = self._retrieve_semantic_messages(
            history=history,
            query=query,
            top_k=self.stm_semantic_top_k,
            recent_skip_count=recent_limit,
        )
        ltm_memories = self._fetch_ltm_memories(client_id=scoped_client_id, query=query, limit=self.ltm_max_items)

        recent_messages = history[-recent_limit:]
        recent_lines = [self._msg_line(msg) for msg in recent_messages]
        recent_text = "Recent Conversation:\n" + "\n".join(recent_lines)

        sections: List[str] = []
        consumed = 0

        recent_cost = self._approx_tokens(recent_text)
        if recent_cost > effective_budget:
            trimmed_recent = self._trim_lines_to_budget(recent_lines, token_budget=max(90, effective_budget - 16))
            recent_text = "Recent Conversation:\n" + "\n".join(trimmed_recent)
            recent_cost = self._approx_tokens(recent_text)

        consumed += recent_cost
        sections.append(recent_text)

        def try_add_section(text: str) -> None:
            nonlocal consumed
            if not text.strip():
                return
            cost = self._approx_tokens(text)
            if consumed + cost > effective_budget:
                return
            sections.insert(0, text)
            consumed += cost

        if summary:
            try_add_section(f"Conversation Summary:\n{summary}")

        slot_lines: List[str] = []
        current_topic = self._normalize_space(str(slots.get("current_topic") or ""))
        if current_topic:
            slot_lines.append(f"- current_topic: {self._clip_text(current_topic, 120)}")
        open_tasks = [self._clip_text(str(item), 120) for item in (slots.get("open_tasks") or []) if str(item).strip()]
        if open_tasks:
            slot_lines.append(f"- open_tasks: {', '.join(open_tasks[-3:])}")
        last_entities = [self._clip_text(str(item), 80) for item in (slots.get("last_entities") or []) if str(item).strip()]
        if last_entities:
            slot_lines.append(f"- last_entities: {', '.join(last_entities[-4:])}")
        if slot_lines:
            try_add_section("Conversation Slots:\n" + "\n".join(slot_lines))

        if semantic_messages:
            semantic_lines = [self._msg_line(msg) for msg in semantic_messages]
            try_add_section("Relevant Past Turns:\n" + "\n".join(semantic_lines))

        if ltm_memories:
            memory_lines = [
                f"- {self._clip_text(str(memory.memory_text or ''), 180)}"
                for memory in ltm_memories
                if str(memory.memory_text or "").strip()
            ]
            if memory_lines:
                try_add_section("Long-Term Memory:\n" + "\n".join(memory_lines))

        return "\n\n".join(section for section in sections if section.strip())

conversation_manager = ConversationManager()
