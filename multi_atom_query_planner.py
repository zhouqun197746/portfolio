"""
multi_atom_query_planner.py  v1.0.0-a1-multi-atom-query-plan (A1-6)

Rule-based multi-atom query planner. Decomposes a user query into
functional slots that can be independently searched via atom_search_engine.
"""
import datetime
from typing import Any

# Fixed slot definitions
DEFAULT_SLOTS = [
    {
        "slot_id": "slot_cause",
        "slot_name": "cause",
        "description": "导致当前事件的既往原因。",
        "expected_min_results": 3,
    },
    {
        "slot_id": "slot_trigger",
        "slot_name": "trigger",
        "description": "具体触发事件或时刻。",
        "expected_min_results": 3,
    },
    {
        "slot_id": "slot_mechanism",
        "slot_name": "mechanism",
        "description": "涉及的规则、机制、系统或设定。",
        "expected_min_results": 2,
    },
    {
        "slot_id": "slot_observation",
        "slot_name": "observation",
        "description": "细微观察、细节、五感信息。",
        "expected_min_results": 3,
    },
    {
        "slot_id": "slot_stakes",
        "slot_name": "stakes",
        "description": "利害关系、成本、可能失去的东西。",
        "expected_min_results": 2,
    },
    {
        "slot_id": "slot_twist",
        "slot_name": "twist",
        "description": "反转、意外、矛盾点。",
        "expected_min_results": 2,
    },
]

# Slot → metadata filter mapping for search
SLOT_METADATA_FILTERS: dict[str, dict[str, str | None]] = {
    "cause": {},
    "trigger": {},
    "mechanism": {},
    "observation": {},
    "stakes": {},
    "twist": {},
}


def build_multi_atom_query_plan(
    user_query: str,
    storyline_context: dict | None = None,
) -> dict:
    """
    Build a multi-atom query plan from a user query string.

    Args:
        user_query: natural language retrieval request.
        storyline_context: optional dict with storyline_id, timeline_phase, etc.

    Returns:
        multi_atom_query_plan_bundle dict.
    """
    if not user_query or not user_query.strip():
        return {
            "version": "v1.0.0-a1-multi-atom-query-plan",
            "multi_atom_query_plan_bundle_id": (
                f"maqp_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ),
            "user_query": user_query or "",
            "storyline_context": storyline_context or {},
            "slots": [],
            "status": "invalid",
            "warnings": ["MULTI_ATOM_QUERY_PLAN_EMPTY"],
            "timestamp": datetime.datetime.now().isoformat(),
        }

    storyline_context = storyline_context or {}
    storyline_id = storyline_context.get("storyline_id", "")
    timeline_phase = storyline_context.get("timeline_phase", "")

    slots: list[dict] = []
    for slot_def in DEFAULT_SLOTS:
        metadata_filters: dict[str, str | None] = {}
        if storyline_id:
            metadata_filters["storyline_id"] = storyline_id
        if timeline_phase:
            metadata_filters["timeline_phase"] = timeline_phase

        slot_entry = {
            "slot_id": slot_def["slot_id"],
            "slot_name": slot_def["slot_name"],
            "description": slot_def["description"],
            "base_query": user_query.strip(),
            "metadata_filters": metadata_filters,
            "expected_min_results": slot_def["expected_min_results"],
        }
        slots.append(slot_entry)

    bundle = {
        "version": "v1.0.0-a1-multi-atom-query-plan",
        "multi_atom_query_plan_bundle_id": (
            f"maqp_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ),
        "user_query": user_query.strip(),
        "storyline_context": storyline_context,
        "slots": slots,
        "status": "ready",
        "warnings": [],
        "timestamp": datetime.datetime.now().isoformat(),
    }

    return bundle
