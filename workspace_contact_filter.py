from typing import Any, Set


CONTACT_FILTER_MODES = {"all", "only", "except"}


def workspace_sender_allowed(mode: Any, sender_ids: Set[str], allowed_ids: Set[str]) -> bool:
    resolved_mode = str(mode or "all").strip().lower()
    if resolved_mode not in CONTACT_FILTER_MODES:
        resolved_mode = "all"

    has_match = any(sender_id in allowed_ids for sender_id in sender_ids)
    if resolved_mode == "only":
        return has_match
    if resolved_mode == "except":
        return not has_match
    return True
