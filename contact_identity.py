import re
from typing import Any, Dict, Iterable, List, Set


def normalize_contact_chat_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "@" in raw:
        return raw.lower()

    digits = re.sub(r"\D", "", raw)
    if len(digits) < 8:
        return ""
    return f"{digits}@s.whatsapp.net"


def choose_preferred_contact_id(candidates: Iterable[Any]) -> str:
    normalized: List[str] = []
    seen: Set[str] = set()
    for value in candidates:
        chat_id = normalize_contact_chat_id(value)
        if not chat_id or chat_id in seen or "@g.us" in chat_id:
            continue
        seen.add(chat_id)
        normalized.append(chat_id)

    if not normalized:
        return ""

    for suffix in ("@lid", "@s.whatsapp.net", "@c.us"):
        match = next((item for item in normalized if item.endswith(suffix)), "")
        if match:
            return match
    return sorted(normalized)[0]


def extract_sender_id_candidates(payload: Dict[str, Any], chat_id: str) -> Set[str]:
    raw_values: List[Any] = [
        payload.get("participant"),
        payload.get("author"),
        payload.get("_data", {}).get("key", {}).get("participant"),
        payload.get("_data", {}).get("key", {}).get("participantAlt"),
        payload.get("from"),
        chat_id,
    ]
    results: Set[str] = set()
    for value in raw_values:
        normalized = normalize_contact_chat_id(value)
        if not normalized or "@g.us" in normalized:
            continue
        results.add(normalized)
    return results
