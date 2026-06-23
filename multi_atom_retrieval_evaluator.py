"""
multi_atom_retrieval_evaluator.py  v1.0.0-a1-multi-atom-retrieval-eval (A1-6)

Executes searches for each slot in a multi_atom_query_plan_bundle using
the existing atom_search_engine, and produces a multi_atom_retrieval_eval_bundle
with slot-level and global metrics.
"""
import datetime
from typing import Any

from app.rag.atom_search_engine import AtomSearchEngine


def run_multi_atom_retrieval_and_eval(
    multi_atom_query_plan_bundle: dict,
    top_k: int = 5,
) -> dict:
    """
    Execute retrieval for each slot and compute evaluation metrics.

    Args:
        multi_atom_query_plan_bundle: output of build_multi_atom_query_plan().
        top_k: number of results to retrieve per slot.

    Returns:
        multi_atom_retrieval_eval_bundle dict.
    """
    plan = multi_atom_query_plan_bundle
    plan_id = plan.get("multi_atom_query_plan_bundle_id", "")
    slots = plan.get("slots", [])
    warnings: list[str] = list(plan.get("warnings", []))

    if not slots:
        return {
            "version": "v1.0.0-a1-multi-atom-retrieval-eval",
            "multi_atom_retrieval_eval_bundle_id": (
                f"mare_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ),
            "source_multi_atom_query_plan_bundle_id": plan_id,
            "slot_results": [],
            "global_metrics": {
                "total_slots": 0,
                "slots_with_results": 0,
                "slots_with_insufficient_results": 0,
                "estimated_slot_coverage": 0.0,
                "distinct_atoms": 0,
                "diversity_score": 0.0,
            },
            "warnings": ["MULTI_ATOM_RETRIEVAL_NO_RESULTS"],
            "status": "fail",
            "timestamp": datetime.datetime.now().isoformat(),
        }

    search_engine = AtomSearchEngine()
    slot_results: list[dict] = []
    slots_with_results = 0
    slots_with_insufficient = 0
    all_atom_ids: set[str] = set()

    for slot in slots:
        slot_id = slot.get("slot_id", "")
        slot_name = slot.get("slot_name", "")
        base_query = slot.get("base_query", "")
        expected_min = slot.get("expected_min_results", 3)
        metadata_filters = slot.get("metadata_filters", {})

        result_entries: list[dict] = []
        slot_hits = 0

        try:
            # Execute search via the existing engine
            raw_results = search_engine.search(
                query=base_query,
                top_k=top_k,
                category=metadata_filters.get("category", None),
                atom_type=metadata_filters.get("atom_type", None),
                source_channel=metadata_filters.get("source_channel", None),
            )

            for raw in raw_results:
                atom = raw.get("atom", {})
                atom_id = ""
                if hasattr(atom, "atom_id"):
                    atom_id = atom.atom_id
                elif isinstance(atom, dict):
                    atom_id = atom.get("atom_id", "")

                if not atom_id:
                    continue

                all_atom_ids.add(atom_id)
                slot_hits += 1

                # Extract metadata from atom
                atom_meta: dict = {}
                if isinstance(atom, dict):
                    atom_meta = {
                        "storyline_id": atom.get("storyline_id", ""),
                        "storyline_slot": atom.get("storyline_slot", ""),
                        "primary_emotion": atom.get("primary_emotion", ""),
                        "source_material_id": atom.get("source_material_id", ""),
                    }

                result_entries.append({
                    "atom_id": atom_id,
                    "score": round(raw.get("score", 0.0), 4),
                    "snippet": raw.get("snippet", ""),
                    "metadata": atom_meta,
                })

        except Exception as e:
            warnings.append(f"SLOT_EXECUTION_ERROR:{slot_id} - {str(e)[:100]}")

        # Compute slot metrics
        insufficient = slot_hits < expected_min and slot_hits > 0

        slot_result = {
            "slot_id": slot_id,
            "slot_name": slot_name,
            "top_k": top_k,
            "results": result_entries,
            "metrics": {
                "hit_count": slot_hits,
                "distinct_storylines": _count_distinct(
                    r.get("metadata", {}).get("storyline_id", "")
                    for r in result_entries
                ),
            },
        }
        slot_results.append(slot_result)

        if slot_hits > 0:
            slots_with_results += 1
        if insufficient:
            slots_with_insufficient += 1
            if not any(f"SLOT_INSUFFICIENT_RESULTS:{slot_id}" in w for w in warnings):
                warnings.append(f"SLOT_INSUFFICIENT_RESULTS:{slot_id}")

    # ── Global metrics ──
    total_slots = len(slots)
    estimated_slot_coverage = (
        slots_with_results / total_slots if total_slots > 0 else 0.0
    )
    distinct_atoms = len(all_atom_ids)
    diversity_score = _compute_diversity(distinct_atoms, total_slots)

    # Status
    if not all_atom_ids:
        status = "fail"
        if "MULTI_ATOM_RETRIEVAL_NO_RESULTS" not in warnings:
            warnings.append("MULTI_ATOM_RETRIEVAL_NO_RESULTS")
    elif slots_with_insufficient > 0:
        status = "warn"
    else:
        status = "pass"

    bundle = {
        "version": "v1.0.0-a1-multi-atom-retrieval-eval",
        "multi_atom_retrieval_eval_bundle_id": (
            f"mare_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ),
        "source_multi_atom_query_plan_bundle_id": plan_id,
        "slot_results": slot_results,
        "global_metrics": {
            "total_slots": total_slots,
            "slots_with_results": slots_with_results,
            "slots_with_insufficient_results": slots_with_insufficient,
            "estimated_slot_coverage": estimated_slot_coverage,
            "distinct_atoms": distinct_atoms,
            "diversity_score": diversity_score,
        },
        "warnings": warnings,
        "status": status,
        "timestamp": datetime.datetime.now().isoformat(),
    }

    return bundle


# ── Internal helpers ──────────────────────────────────────────────────


def _count_distinct(values: list[str]) -> int:
    """Count distinct non-empty values."""
    return len({v for v in values if v})


def _compute_diversity(distinct_count: int, total_slots: int) -> float:
    """
    Simple diversity score: ratio of distinct atoms to (slots × 3).
    Caps at 1.0. Higher = more diverse result set.
    """
    if total_slots == 0:
        return 0.0
    ideal = total_slots * 3
    if ideal == 0:
        return 0.0
    return min(round(distinct_count / ideal, 4), 1.0)
