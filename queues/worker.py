import os
import warnings
import requests
import re
import time
import logging
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter
from sqlmodel import select
from database.db import SessionLocal
from database import KnowledgeBaseSQLModel, KnowledgeBaseRetrievalProfileSQLModel

# Fix macOS fork() crash with Objective-C runtime
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

# Suppress warnings
warnings.filterwarnings("ignore", message=".*OpenSSL.*", category=Warning)
warnings.filterwarnings("ignore", category=FutureWarning)

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from google import genai
from google.genai import types
from waha_client import waha_client


load_dotenv()
logger = logging.getLogger(__name__)

embedding_model = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

# Use environment variable for Qdrant URL (Docker compatibility)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_QDRANT_COLLECTION = os.getenv("DEFAULT_QDRANT_COLLECTION", "").strip()
RAG_MODEL = os.getenv("RAG_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
RAG_RETRIEVAL_CANDIDATES = max(8, int(os.getenv("RAG_RETRIEVAL_CANDIDATES", "16")))
RAG_FINAL_CONTEXT_K = max(3, int(os.getenv("RAG_FINAL_CONTEXT_K", "6")))
RAG_GROUNDING_THRESHOLD = float(os.getenv("RAG_GROUNDING_THRESHOLD", "0.40"))
RAG_MIN_CONTEXT_CHARS = max(80, int(os.getenv("RAG_MIN_CONTEXT_CHARS", "180")))
RAG_QUERY_VARIANTS_LIMIT = max(1, int(os.getenv("RAG_QUERY_VARIANTS_LIMIT", "4")))
RAG_CLARIFICATION_ENABLED = os.getenv("RAG_CLARIFICATION_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
RAG_CLARIFICATION_THRESHOLD = float(os.getenv("RAG_CLARIFICATION_THRESHOLD", "0.56"))
RAG_NO_ANSWER_TEXT = os.getenv(
    "RAG_NO_ANSWER_TEXT",
    "The provided document does not contain enough information to answer this question.",
).strip() or "The provided document does not contain enough information to answer this question."
RAG_LOW_QUALITY_CLARIFICATION_TEXT = os.getenv(
    "RAG_LOW_QUALITY_CLARIFICATION_TEXT",
    "I could not understand that message clearly. Please rephrase in one clear sentence and include the topic.",
).strip() or "I could not understand that message clearly. Please rephrase in one clear sentence and include the topic."
RAG_REQUIRE_CITATIONS = os.getenv("RAG_REQUIRE_CITATIONS", "true").strip().lower() in {"1", "true", "yes", "on"}

_vector_db_cache: Dict[str, QdrantVectorStore] = {}
_profile_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PROFILE_CACHE_TTL_SECONDS = max(5, int(os.getenv("RAG_PROFILE_CACHE_TTL_SECONDS", "60")))


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
    "you",
    "your",
    "what",
    "which",
    "who",
    "where",
    "when",
    "why",
    "how",
    "can",
    "could",
    "do",
    "does",
    "have",
    "has",
    "me",
    "my",
    "it",
    "this",
    "that",
}

_BASE_ACRONYM_MAP = {
    "cs": "computer science",
    "ep": "engineering physics",
    "me": "mechanical engineering",
    "ee": "electrical engineering",
    "ce": "civil engineering",
    "it": "information technology",
}

_FOLLOWUP_PRONOUN_PATTERN = re.compile(
    r"\b(his|her|their|him|he|she|it|its|them|that|those|these|this)\b",
    flags=re.IGNORECASE,
)

_GREETING_PATTERN = re.compile(
    r"^\s*(hi+|hello+|hey+|hii+|heyy+|namaste|good\s+(morning|afternoon|evening))\b[\s!.,?]*$",
    flags=re.IGNORECASE,
)
_THANKS_PATTERN = re.compile(
    r"^\s*(thanks|thank\s+you|thx|ok\s*thanks|okay\s*thanks)\b[\s!.,?]*$",
    flags=re.IGNORECASE,
)


def _small_talk_response(query: str) -> Optional[str]:
    text = str(query or "").strip()
    if not text:
        return None
    if _GREETING_PATTERN.match(text):
        return "Hi! Ask me a question about your knowledge base, and I will answer with context."
    if _THANKS_PATTERN.match(text):
        return "You're welcome. Ask your next question anytime."
    return None


def _is_low_signal_query(query: str) -> bool:
    value = str(query or "").strip().lower()
    if not value:
        return True

    compact = re.sub(r"[^a-z0-9]", "", value)
    if len(compact) < 3:
        return True

    tokens = re.findall(r"[a-z0-9]{2,}", value)
    if not tokens:
        return True

    alpha_tokens = [token for token in tokens if re.search(r"[a-z]", token)]
    if not alpha_tokens:
        return False

    # Detect random/gibberish-like short inputs such as "jhggggh"
    # while allowing normal short intents like "fees", "pricing", etc.
    if len(alpha_tokens) == 1:
        token = alpha_tokens[0]
        vowels = len(re.findall(r"[aeiou]", token))
        unique_chars = len(set(token))
        if re.search(r"(.)\1{2,}", token) and len(token) >= 5:
            return True
        if len(token) >= 6 and vowels == 0:
            return True
        if len(token) >= 7 and unique_chars <= 4 and vowels <= 1:
            return True

    return False


@dataclass
class RetrievalCandidate:
    doc: Document
    dense_raw_score: float
    dense_score: float
    sparse_score: float
    rerank_score: float


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


def _clean_query_text(raw_query: str) -> str:
    value = str(raw_query or "")
    value = re.sub(r"^\s*(?:@\S+\s*)+", "", value).strip()
    value = re.sub(r"@\d{6,20}(?:@(?:lid|c\.us|s\.whatsapp\.net))?", "", value).strip()
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_user_aliases(conversation_history: str) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    if not conversation_history:
        return aliases

    pattern = re.compile(
        r"\b([A-Za-z]{2,12})\b\s*(?:means|=|->|stands\s+for)\s*([^\n\r\.;,!?]{2,80})",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(conversation_history):
        short_form = match.group(1).strip().lower()
        expansion = re.sub(r"\s+", " ", match.group(2).strip())
        expansion = re.sub(r"^(user|assistant)\s*:\s*", "", expansion, flags=re.IGNORECASE).strip()
        expansion = re.sub(r"\s+(user|assistant)\s*$", "", expansion, flags=re.IGNORECASE).strip()
        if short_form and expansion:
            aliases[short_form] = expansion
    return aliases


def _expand_query_with_aliases(query: str, aliases: Dict[str, str]) -> Tuple[str, List[Tuple[str, str]]]:
    if not query:
        return "", []

    applied: List[Tuple[str, str]] = []

    def repl(match: re.Match) -> str:
        token = match.group(0)
        key = token.lower()
        expansion = aliases.get(key)
        if not expansion:
            return token
        applied.append((token, expansion))
        return f"{expansion} ({token})"

    rewritten = re.sub(r"\b[A-Za-z]{2,12}\b", repl, query)
    rewritten = re.sub(r"\s+", " ", rewritten).strip()
    return rewritten, applied


def _extract_query_tokens(text: str) -> List[str]:
    raw_tokens = re.findall(r"[a-z0-9]{2,}", (text or "").lower())
    return [token for token in raw_tokens if token not in _STOPWORDS]


def _parse_conversation_messages(conversation_history: str) -> List[Tuple[str, str]]:
    messages: List[Tuple[str, str]] = []
    if not conversation_history:
        return messages

    for raw_line in conversation_history.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("user:"):
            messages.append(("user", line.split(":", 1)[1].strip()))
        elif line.lower().startswith("assistant:"):
            messages.append(("assistant", line.split(":", 1)[1].strip()))
    return messages


def _sanitize_history_text(text: str) -> str:
    value = _clean_query_text(str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _contextualize_followup_query(query: str, conversation_history: str) -> Tuple[str, str]:
    clean_query = str(query or "").strip()
    if not clean_query:
        return clean_query, ""

    is_followup_pronoun = bool(_FOLLOWUP_PRONOUN_PATTERN.search(clean_query))
    short_query = len(clean_query.split()) <= 12
    if not (is_followup_pronoun and short_query):
        return clean_query, ""

    messages = _parse_conversation_messages(conversation_history)
    user_messages = [content for role, content in messages if role == "user"]
    previous_user = user_messages[-2] if len(user_messages) >= 2 else (user_messages[-1] if user_messages else "")
    previous_user = _sanitize_history_text(previous_user)
    if not previous_user:
        return clean_query, ""

    # Keep rewrite generic: do not lock to any single person/entity.
    contextual = f"{clean_query} (follow-up context: {previous_user})"
    return contextual, previous_user


def _answer_style_hint(query: str) -> str:
    q = str(query or "").lower()
    asks_explain = bool(re.search(r"\b(explain|describe|detail|elaborate)\b", q))
    asks_list = bool(re.search(r"\b(list|what|which|show)\b", q))
    asks_compare = bool(re.search(r"\b(compare|difference|vs|versus)\b", q))

    if asks_explain:
        return (
            "Answer style: explain with short bullets in this order - "
            "Summary, Key points, Practical takeaway."
        )
    if asks_compare:
        return "Answer style: compare side-by-side in concise bullets."
    if asks_list:
        return "Answer style: provide a concise bullet list, one line per item."
    return "Answer style: concise and directly relevant."


def _capability_query_retrieval_seed(query: str) -> Tuple[bool, str]:
    capability_query = bool(
        re.search(
            r"\b(what\s+(knowledge|information|info)\s+(do\s+you\s+have|you\s+have|you\s+provide)|"
            r"what\s+can\s+you\s+(answer|provide|do)|"
            r"what\s+do\s+you\s+know|"
            r"which\s+topics)\b",
            (query or "").lower(),
        )
    )
    if capability_query:
        return True, "table of contents topics sections syllabus overview departments course codes glossary index"
    return False, query


def _retrieve_dense_candidates(vector_db: QdrantVectorStore, retrieval_query: str, k: int) -> List[Tuple[Document, float]]:
    try:
        scored = vector_db.similarity_search_with_relevance_scores(query=retrieval_query, k=k)
        return [(doc, float(score)) for doc, score in scored]
    except Exception:
        scored = vector_db.similarity_search_with_score(query=retrieval_query, k=k)
        if not scored:
            return []
        raw_values = [float(score) for _, score in scored]
        lo = min(raw_values)
        hi = max(raw_values)
        high_better = raw_values[0] >= raw_values[-1]
        span = hi - lo if hi != lo else 1.0
        normalized: List[Tuple[Document, float]] = []
        for doc, raw_score in scored:
            score_value = float(raw_score)
            if high_better:
                score_01 = (score_value - lo) / span
            else:
                score_01 = (hi - score_value) / span
            normalized.append((doc, max(0.0, min(1.0, score_01))))
        return normalized


def _candidate_key(doc: Document) -> str:
    metadata = doc.metadata or {}
    chunk_id = str(metadata.get("chunk_id") or "").strip()
    if chunk_id:
        return f"chunk:{chunk_id}"

    source = str(metadata.get("source") or "").strip().lower()
    page = str(metadata.get("page_label", metadata.get("page", ""))).strip().lower()
    text_fingerprint = hashlib.sha1((doc.page_content or "").strip().encode("utf-8")).hexdigest()[:16]
    return f"src:{source}|page:{page}|fp:{text_fingerprint}"


def _merge_dense_candidate_lists(candidate_lists: List[List[Tuple[Document, float]]]) -> List[Tuple[Document, float]]:
    merged: Dict[str, Tuple[Document, float]] = {}
    for candidates in candidate_lists:
        for doc, score in candidates:
            key = _candidate_key(doc)
            prev = merged.get(key)
            if prev is None or float(score) > float(prev[1]):
                merged[key] = (doc, float(score))
    ranked = sorted(merged.values(), key=lambda item: float(item[1]), reverse=True)
    return ranked


def _build_retrieval_query_variants(
    cleaned_query: str,
    contextual_query: str,
    rewritten_query: str,
    capability_query: bool,
    capability_seed_query: str,
) -> List[str]:
    variants: List[str] = []

    def add_variant(value: str) -> None:
        candidate = re.sub(r"\s+", " ", str(value or "").strip())
        if not candidate:
            return
        if candidate not in variants:
            variants.append(candidate)

    if capability_query:
        add_variant(capability_seed_query)
    add_variant(rewritten_query)
    add_variant(contextual_query)
    add_variant(cleaned_query)
    return variants


def _load_collection_profile(collection_name: str) -> Dict[str, Any]:
    key = str(collection_name or "").strip()
    if not key:
        return {}

    now = time.time()
    cached = _profile_cache.get(key)
    if cached and (now - cached[0]) < _PROFILE_CACHE_TTL_SECONDS:
        return dict(cached[1])

    profile_data: Dict[str, Any] = {}
    try:
        with SessionLocal() as db:
            kb = db.execute(
                select(KnowledgeBaseSQLModel).where(KnowledgeBaseSQLModel.name == key)
            ).scalars().first()
            if kb:
                profile = db.execute(
                    select(KnowledgeBaseRetrievalProfileSQLModel).where(
                        KnowledgeBaseRetrievalProfileSQLModel.knowledge_base_id == kb.id
                    )
                ).scalars().first()
                if profile:
                    profile_data = {
                        "final_context_k": profile.final_context_k,
                        "retrieval_candidates": profile.retrieval_candidates,
                        "grounding_threshold": profile.grounding_threshold,
                        "require_citations": profile.require_citations,
                        "min_context_chars": profile.min_context_chars,
                        "query_variants_limit": profile.query_variants_limit,
                        "clarification_enabled": profile.clarification_enabled,
                        "clarification_threshold": profile.clarification_threshold,
                    }
    except Exception as profile_error:
        logger.debug("collection profile lookup failed for %s: %s", key, profile_error)
        profile_data = {}

    cleaned = {k: v for k, v in profile_data.items() if v is not None}
    _profile_cache[key] = (now, cleaned)
    return dict(cleaned)


def _lexical_sparse_score(query_tokens: List[str], doc_text: str) -> float:
    if not query_tokens:
        return 0.0

    doc_tokens = re.findall(r"[a-z0-9]{2,}", (doc_text or "").lower())
    if not doc_tokens:
        return 0.0

    doc_counter = Counter(doc_tokens)
    unique_query = list(dict.fromkeys(query_tokens))
    overlap = sum(1 for token in unique_query if token in doc_counter)
    coverage = overlap / max(1, len(unique_query))
    tf_ratio = sum(min(3, doc_counter[token]) for token in unique_query) / max(1, 3 * len(unique_query))

    query_phrase = " ".join(unique_query)
    doc_norm = re.sub(r"\s+", " ", (doc_text or "").lower())
    phrase_bonus = 0.12 if len(query_phrase) >= 6 and query_phrase in doc_norm else 0.0

    raw = (0.68 * coverage) + (0.32 * tf_ratio) + phrase_bonus
    return max(0.0, min(1.0, raw))


def _rerank_hybrid(retrieved: List[Tuple[Document, float]], retrieval_query: str) -> List[RetrievalCandidate]:
    if not retrieved:
        return []

    tokens = _extract_query_tokens(retrieval_query)
    total = len(retrieved)
    scored: List[RetrievalCandidate] = []

    for idx, (doc, dense_raw) in enumerate(retrieved):
        dense_rank_score = 1.0 if total == 1 else (1.0 - (idx / max(1, total - 1)))
        dense_score = (0.55 * max(0.0, min(1.0, dense_raw))) + (0.45 * dense_rank_score)
        sparse_score = _lexical_sparse_score(tokens, doc.page_content or "")
        hybrid_score = (0.60 * dense_score) + (0.40 * sparse_score)

        scored.append(
            RetrievalCandidate(
                doc=doc,
                dense_raw_score=dense_raw,
                dense_score=dense_score,
                sparse_score=sparse_score,
                rerank_score=hybrid_score,
            )
        )

    scored.sort(key=lambda item: item.rerank_score, reverse=True)
    return scored


def _build_cited_context(candidates: List[RetrievalCandidate], top_k: int) -> Tuple[str, List[str]]:
    blocks: List[str] = []
    citation_ids: List[str] = []
    for idx, candidate in enumerate(candidates[:top_k], start=1):
        doc = candidate.doc
        metadata = doc.metadata or {}
        citation_id = f"C{idx}"
        citation_ids.append(citation_id)

        source = str(metadata.get("source") or "N/A")
        title = str(metadata.get("title") or "")
        page = metadata.get("page_label", metadata.get("page", "N/A"))
        chunk_index = metadata.get("chunk_index", "N/A")
        text = re.sub(r"\s+", " ", (doc.page_content or "")).strip()

        blocks.append(
            (
                f"[{citation_id}] source={source} page={page} chunk={chunk_index} title={title}\n"
                f"{text}"
            ).strip()
        )

    return "\n\n".join(blocks), citation_ids


def _grounding_gate(
    candidates: List[RetrievalCandidate],
    context_text: str,
    threshold: float,
    min_context_chars: int,
) -> Tuple[bool, Dict[str, Any]]:
    if not candidates:
        return False, {"reason": "no_candidates", "score": 0.0, "margin": 0.0}

    top = candidates[0].rerank_score
    second = candidates[1].rerank_score if len(candidates) > 1 else 0.0
    margin = max(0.0, top - second)
    context_chars = len((context_text or "").strip())

    pass_gate = True
    reason = "ok"
    if top < threshold:
        pass_gate = False
        reason = "low_retrieval_confidence"
    if context_chars < int(min_context_chars):
        pass_gate = False
        reason = "insufficient_context"
    if top < (threshold + 0.06) and margin < 0.02:
        pass_gate = False
        reason = "ambiguous_top_match"

    return pass_gate, {
        "reason": reason,
        "score": round(float(top), 4),
        "margin": round(float(margin), 4),
        "context_chars": context_chars,
        "min_context_chars": int(min_context_chars),
        "threshold": threshold,
    }


def _build_clarification_question(
    cleaned_query: str,
    conversation_history: str,
    low_quality_clarification_text: str,
) -> Optional[str]:
    query = str(cleaned_query or "").strip()
    if not query:
        return None
    small_talk = _small_talk_response(query)
    if small_talk:
        return small_talk
    if _is_low_signal_query(query):
        return str(low_quality_clarification_text or "").strip() or RAG_LOW_QUALITY_CLARIFICATION_TEXT
    if not _FOLLOWUP_PRONOUN_PATTERN.search(query):
        return None

    messages = _parse_conversation_messages(conversation_history)
    has_prior_user_turn = any(role == "user" for role, _ in messages)
    if has_prior_user_turn:
        return (
            "Quick clarification: who or what are you referring to? "
            "Share the exact person/topic so I can answer precisely."
        )
    return (
        "Please clarify the subject first (person/topic/entity), "
        "then I will answer accurately."
    )


def _has_valid_citations(answer: str, valid_citation_ids: List[str], require_citations: bool) -> bool:
    if not require_citations:
        return True
    text = (answer or "").strip()
    if not text:
        return False
    if text == RAG_NO_ANSWER_TEXT:
        return True

    found = re.findall(r"\[(C\d+)\]", text)
    if not found:
        return False
    valid = set(valid_citation_ids)
    return all(citation in valid for citation in found)


def _strip_citation_tags(answer: str) -> str:
    text = str(answer or "")
    if not text:
        return ""
    cleaned = re.sub(r"\s*\[C\d+\]", "", text)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned.strip()


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
            timeout=5,
        )
        print(f"WebSocket notification sent to client {client_id}: {response.status_code}")
    except Exception as e:
        print(f"Failed to send WebSocket notification: {e}")


def send_whatsapp_reply(
    client_id: str,
    result: str,
    whatsapp_message_id: str = None,
    waha_session: Optional[str] = None,
):
    """Send result directly to WhatsApp via WAHA API (replaces n8n workflow 2)"""
    if not client_id or "@g.us" not in client_id:
        print("Not a WhatsApp group message, skipping WAHA API")
        return

    try:
        payload = {
            "chatId": client_id,
            "text": result,
        }
        if waha_session:
            payload["session"] = str(waha_session).strip()

        if whatsapp_message_id:
            payload["reply_to"] = whatsapp_message_id

        success, response = waha_client.send_dynamic_message("text", payload)

        if success:
            print(f"✅ WhatsApp reply sent to {client_id}")
        else:
            print(f"⚠️ WAHA API error: {response}")

    except Exception as e:
        print(f"❌ Failed to send WhatsApp reply: {e}")


def process_query(
    query: str,
    client_id: str = None,
    conversation_history: str = "",
    whatsapp_message_id: str = None,
    waha_session: Optional[str] = None,
    collection_name: str = None,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
    low_quality_clarification_text: Optional[str] = None,
    emit_side_effects: bool = True,
    return_debug: bool = False,
    rag_options: Optional[Dict[str, Any]] = None,
):
    started_at = time.perf_counter()
    raw_query = str(query or "")
    cleaned_query = _clean_query_text(raw_query)
    if not cleaned_query:
        cleaned_query = raw_query.strip()

    rag_options = rag_options or {}
    target_collection = (collection_name or DEFAULT_QDRANT_COLLECTION or "").strip()
    if not target_collection:
        raise ValueError("RAG ke liye collection_name missing hai. Workspace KB ya flow config check karo.")

    profile_options = _load_collection_profile(target_collection)
    explicit_options = {k: v for k, v in rag_options.items() if v is not None}
    effective_rag_options = {**profile_options, **explicit_options}

    final_context_k = max(2, int(effective_rag_options.get("final_context_k", RAG_FINAL_CONTEXT_K)))
    retrieval_candidates = max(
        final_context_k + 2,
        int(effective_rag_options.get("retrieval_candidates", RAG_RETRIEVAL_CANDIDATES)),
    )
    grounding_threshold = float(effective_rag_options.get("grounding_threshold", RAG_GROUNDING_THRESHOLD))
    require_citations = bool(effective_rag_options.get("require_citations", RAG_REQUIRE_CITATIONS))
    min_context_chars = max(40, int(effective_rag_options.get("min_context_chars", RAG_MIN_CONTEXT_CHARS)))
    query_variants_limit = min(
        8,
        max(1, int(effective_rag_options.get("query_variants_limit", RAG_QUERY_VARIANTS_LIMIT))),
    )
    clarification_enabled = bool(effective_rag_options.get("clarification_enabled", RAG_CLARIFICATION_ENABLED))
    clarification_threshold = float(effective_rag_options.get("clarification_threshold", RAG_CLARIFICATION_THRESHOLD))
    resolved_low_quality_text = (
        str(low_quality_clarification_text or "").strip() or RAG_LOW_QUALITY_CLARIFICATION_TEXT
    )
    has_custom_prompt = bool((system_prompt or "").strip() or (user_prompt_template or "").strip())
    is_small_talk = _small_talk_response(cleaned_query) is not None
    # If workspace provides custom prompt, let model handle greeting/thanks intent.
    # This prevents hardcoded small-talk response from overriding workspace behavior.
    bypass_gate_for_custom_small_talk = bool(has_custom_prompt and is_small_talk)
    answer_style_hint = _answer_style_hint(cleaned_query)
    contextual_query, followup_subject_hint = _contextualize_followup_query(cleaned_query, conversation_history)

    alias_map = {**_BASE_ACRONYM_MAP, **_extract_user_aliases(conversation_history)}
    rewritten_query, alias_hits = _expand_query_with_aliases(contextual_query, alias_map)
    rewritten_query = rewritten_query or contextual_query or cleaned_query or raw_query

    capability_query, capability_seed_query = _capability_query_retrieval_seed(rewritten_query)
    retrieval_query_variants = _build_retrieval_query_variants(
        cleaned_query=cleaned_query,
        contextual_query=contextual_query,
        rewritten_query=rewritten_query,
        capability_query=capability_query,
        capability_seed_query=capability_seed_query,
    )
    primary_retrieval_query = retrieval_query_variants[0] if retrieval_query_variants else (rewritten_query or cleaned_query)
    retrieval_k = max(retrieval_candidates, final_context_k + 2)
    if capability_query:
        retrieval_k = max(retrieval_k, 12)

    logger.info(
        "RAG search collection=%s queries=%s",
        target_collection,
        " || ".join(retrieval_query_variants[:query_variants_limit]),
    )
    vector_db = _get_vector_db(target_collection)
    dense_candidate_lists: List[List[Tuple[Document, float]]] = []
    per_variant_k = min(24, max(6, retrieval_k))
    for variant_query in retrieval_query_variants[:query_variants_limit]:
        dense_candidate_lists.append(
            _retrieve_dense_candidates(
                vector_db=vector_db,
                retrieval_query=variant_query,
                k=per_variant_k,
            )
        )
    dense_candidates = _merge_dense_candidate_lists(dense_candidate_lists)
    rerank_query = cleaned_query or primary_retrieval_query
    hybrid_candidates = _rerank_hybrid(dense_candidates, retrieval_query=rerank_query)
    context_text, citation_ids = _build_cited_context(hybrid_candidates, top_k=final_context_k)
    pass_gate, gate_data = _grounding_gate(
        hybrid_candidates,
        context_text,
        threshold=grounding_threshold,
        min_context_chars=min_context_chars,
    )
    clarification_text: Optional[str] = None
    if clarification_enabled and not bypass_gate_for_custom_small_talk and (
        _is_low_signal_query(cleaned_query)
        or float(gate_data.get("score") or 0.0) < clarification_threshold
        or not pass_gate
    ):
        clarification_text = _build_clarification_question(
            cleaned_query,
            conversation_history,
            low_quality_clarification_text=resolved_low_quality_text,
        )

    if clarification_text:
        response_text = clarification_text
        debug_payload = {
            "answer": response_text,
            "fallback_used": False,
            "clarification_requested": True,
            "grounding": {**gate_data, "passed": pass_gate},
            "citation_ok": True,
            "collection_name": target_collection,
            "raw_query": raw_query,
            "cleaned_query": cleaned_query,
            "contextual_query": contextual_query,
            "rewritten_query": rewritten_query,
            "followup_subject_hint": followup_subject_hint,
            "retrieval_query": primary_retrieval_query,
            "retrieval_query_variants": retrieval_query_variants,
            "capability_query": capability_query,
            "alias_hits": alias_hits,
            "collection_profile": profile_options,
            "rag_options": {
                "final_context_k": final_context_k,
                "retrieval_candidates": retrieval_candidates,
                "grounding_threshold": grounding_threshold,
                "require_citations": require_citations,
                "min_context_chars": min_context_chars,
                "query_variants_limit": query_variants_limit,
                "clarification_enabled": clarification_enabled,
                "clarification_threshold": clarification_threshold,
            },
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "retrieved_chunks": [
                {
                    "rank": idx + 1,
                    "score": round(float(candidate.rerank_score), 4),
                    "dense_score": round(float(candidate.dense_score), 4),
                    "sparse_score": round(float(candidate.sparse_score), 4),
                    "source": str((candidate.doc.metadata or {}).get("source") or "N/A"),
                    "page": (candidate.doc.metadata or {}).get("page_label", (candidate.doc.metadata or {}).get("page", "N/A")),
                }
                for idx, candidate in enumerate(hybrid_candidates[:final_context_k])
            ],
        }

    elif not pass_gate and not bypass_gate_for_custom_small_talk:
        response_text = RAG_NO_ANSWER_TEXT
        debug_payload = {
            "answer": response_text,
            "fallback_used": True,
            "clarification_requested": False,
            "grounding": {**gate_data, "passed": False},
            "citation_ok": True,
            "collection_name": target_collection,
            "raw_query": raw_query,
            "cleaned_query": cleaned_query,
            "contextual_query": contextual_query,
            "rewritten_query": rewritten_query,
            "followup_subject_hint": followup_subject_hint,
            "retrieval_query": primary_retrieval_query,
            "retrieval_query_variants": retrieval_query_variants,
            "capability_query": capability_query,
            "alias_hits": alias_hits,
            "bypass_gate_for_custom_small_talk": bypass_gate_for_custom_small_talk,
            "collection_profile": profile_options,
            "rag_options": {
                "final_context_k": final_context_k,
                "retrieval_candidates": retrieval_candidates,
                "grounding_threshold": grounding_threshold,
                "require_citations": require_citations,
                "min_context_chars": min_context_chars,
                "query_variants_limit": query_variants_limit,
                "clarification_enabled": clarification_enabled,
                "clarification_threshold": clarification_threshold,
            },
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "retrieved_chunks": [
                {
                    "rank": idx + 1,
                    "score": round(float(candidate.rerank_score), 4),
                    "dense_score": round(float(candidate.dense_score), 4),
                    "sparse_score": round(float(candidate.sparse_score), 4),
                    "source": str((candidate.doc.metadata or {}).get("source") or "N/A"),
                    "page": (candidate.doc.metadata or {}).get("page_label", (candidate.doc.metadata or {}).get("page", "N/A")),
                }
                for idx, candidate in enumerate(hybrid_candidates[:final_context_k])
            ],
        }
    else:
        conversation_context = ""
        if conversation_history:
            conversation_context = (
                "Previous Conversation:\n"
                f"{conversation_history}\n\n"
                "Use previous messages only to resolve references, acronyms, or pronouns."
            )

        if require_citations:
            grounding_contract = (
                "Grounding Contract:\n"
                "1) Use only the cited context blocks [C1], [C2], ...\n"
                f"2) If answer is not available in context, reply exactly: {RAG_NO_ANSWER_TEXT}\n"
                "3) Do not use outside knowledge or assumptions.\n"
                "4) Every factual line must include at least one citation tag like [C1].\n"
                "5) Use recent conversation only for follow-up resolution; if reference is ambiguous, ask one concise clarification.\n"
                "6) Keep answer concise and directly relevant."
            )
        else:
            grounding_contract = (
                "Grounding Contract:\n"
                "1) Use only the retrieved context blocks.\n"
                f"2) If answer is not available in context, reply exactly: {RAG_NO_ANSWER_TEXT}\n"
                "3) Do not use outside knowledge or assumptions.\n"
                "4) Do not include citation tags like [C1] in the final answer.\n"
                "5) Use recent conversation only for follow-up resolution; if reference is ambiguous, ask one concise clarification.\n"
                "6) Keep answer concise and directly relevant."
            )

        default_system_prompt = (
            "You are a retrieval-grounded assistant.\n\n"
            f"{answer_style_hint}\n\n"
            f"{grounding_contract}\n\n"
            f"{conversation_context}\n\n"
            f"Retrieved Context Blocks:\n{context_text}"
        ).strip()

        replacements = {
            "{{body}}": cleaned_query,
            "{{query}}": cleaned_query,
            "{{contextual_query}}": contextual_query,
            "{{rag_result}}": context_text,
            "{{context}}": context_text,
            "{{conversation_history}}": conversation_history or "",
            "{{retrieval_query}}": primary_retrieval_query,
            "{{rewritten_query}}": rewritten_query,
            "{{followup_subject_hint}}": followup_subject_hint,
            "{{is_capability_query}}": "true" if capability_query else "false",
            "{{collection_name}}": target_collection,
            "{{no_answer_text}}": RAG_NO_ANSWER_TEXT,
            "{{answer_style_hint}}": answer_style_hint,
        }

        effective_system_prompt = (system_prompt or "").strip() or default_system_prompt
        for key, value in replacements.items():
            effective_system_prompt = effective_system_prompt.replace(key, value)
        if "Retrieved Context Blocks:" not in effective_system_prompt:
            effective_system_prompt = (
                f"{effective_system_prompt}\n\n{grounding_contract}\n\nRetrieved Context Blocks:\n{context_text}"
            ).strip()

        user_contents = cleaned_query or raw_query
        if (user_prompt_template or "").strip():
            user_contents = user_prompt_template
            for key, value in replacements.items():
                user_contents = user_contents.replace(key, value)
            user_contents = user_contents.strip() or (cleaned_query or raw_query)

        client = genai.Client()
        response = client.models.generate_content(
            model=RAG_MODEL,
            contents=user_contents,
            config=types.GenerateContentConfig(system_instruction=effective_system_prompt),
        )
        response_text = (response.text or "").strip()

        first_model_response = response_text
        citation_ok = _has_valid_citations(response_text, citation_ids, require_citations=require_citations)
        if require_citations and not citation_ok:
            retry_user_contents = (
                f"{user_contents}\n\n"
                "Important: Return only grounded answer with citations [C1]/[C2]. "
                f"If unsure, output exactly: {RAG_NO_ANSWER_TEXT}"
            )
            retry_response = client.models.generate_content(
                model=RAG_MODEL,
                contents=retry_user_contents,
                config=types.GenerateContentConfig(system_instruction=effective_system_prompt),
            )
            retry_text = (retry_response.text or "").strip()
            if _has_valid_citations(retry_text, citation_ids, require_citations=require_citations):
                response_text = retry_text
                citation_ok = True
            elif retry_text and retry_text != RAG_NO_ANSWER_TEXT and citation_ids and not require_citations:
                response_text = retry_text
                citation_ok = True

        if not require_citations and response_text:
            response_text = _strip_citation_tags(response_text)

        if not response_text:
            response_text = RAG_NO_ANSWER_TEXT
        if require_citations and response_text != RAG_NO_ANSWER_TEXT and not _has_valid_citations(
            response_text,
            citation_ids,
            require_citations=require_citations,
        ):
            response_text = RAG_NO_ANSWER_TEXT

        debug_payload = {
            "answer": response_text,
            "fallback_used": response_text == RAG_NO_ANSWER_TEXT,
            "clarification_requested": False,
            "grounding": {**gate_data, "passed": True},
            "citation_ok": _has_valid_citations(response_text, citation_ids, require_citations=require_citations),
            "collection_name": target_collection,
            "raw_query": raw_query,
            "cleaned_query": cleaned_query,
            "contextual_query": contextual_query,
            "rewritten_query": rewritten_query,
            "followup_subject_hint": followup_subject_hint,
            "retrieval_query": primary_retrieval_query,
            "retrieval_query_variants": retrieval_query_variants,
            "capability_query": capability_query,
            "alias_hits": alias_hits,
            "bypass_gate_for_custom_small_talk": bypass_gate_for_custom_small_talk,
            "collection_profile": profile_options,
            "rag_options": {
                "final_context_k": final_context_k,
                "retrieval_candidates": retrieval_candidates,
                "grounding_threshold": grounding_threshold,
                "require_citations": require_citations,
                "min_context_chars": min_context_chars,
                "query_variants_limit": query_variants_limit,
                "clarification_enabled": clarification_enabled,
                "clarification_threshold": clarification_threshold,
            },
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "first_model_response": first_model_response,
            "retrieved_chunks": [
                {
                    "rank": idx + 1,
                    "score": round(float(candidate.rerank_score), 4),
                    "dense_score": round(float(candidate.dense_score), 4),
                    "sparse_score": round(float(candidate.sparse_score), 4),
                    "source": str((candidate.doc.metadata or {}).get("source") or "N/A"),
                    "page": (candidate.doc.metadata or {}).get("page_label", (candidate.doc.metadata or {}).get("page", "N/A")),
                }
                for idx, candidate in enumerate(hybrid_candidates[:final_context_k])
            ],
        }

    from rq import get_current_job

    job = get_current_job()
    job_id = job.id if job else None

    if emit_side_effects and client_id:
        send_websocket_notification(client_id, response_text, job_id)

    if emit_side_effects and client_id and "@g.us" in client_id:
        send_whatsapp_reply(
            client_id,
            response_text,
            whatsapp_message_id,
            waha_session=waha_session,
        )

    if return_debug:
        return debug_payload
    return response_text
