"""
rag_advanced_reranker.py  v1.0.0-p2-rag-reranked-results (P2_RAG)

Advanced reranking for multi-atom retrieval results.

Implements:
  - MMR (Maximum Marginal Relevance) for diversity ranking
  - RRF (Reciprocal Rank Fusion) for multi-slot result fusion
"""
import datetime
from typing import Any


def build_reranked_multi_atom_result_bundle(
    multi_atom_retrieval_eval_bundle: dict,
    rerank_mode: str = "mmr",
    top_k: int = 5,
) -> dict:
    """
    Build reranked result bundle from a multi_atom_retrieval_eval_bundle.

    Args:
        multi_atom_retrieval_eval_bundle: output of A1-6 evaluator.
        rerank_mode: 'mmr' or 'rrf'.
        top_k: number of final results.

    Returns:
        reranked_multi_atom_result_bundle dict.
    """
    eval_bundle = multi_atom_retrieval_eval_bundle
    source_id = eval_bundle.get("multi_atom_retrieval_eval_bundle_id", "")
    warnings: list[str] = list(eval_bundle.get("warnings", []))
    slot_results = eval_bundle.get("slot_results", [])

    # Collect all results with their slot provenance
    all_results: list[dict] = []
    for sr in slot_results:
        slot_id = sr.get("slot_id", "")
        for r in sr.get("results", []):
            entry = dict(r)
            entry["_slot_id"] = slot_id
            all_results.append(entry)

    if not all_results:
        return {
            "version": "v1.0.0-p2-rag-reranked-results",
            "reranked_multi_atom_result_bundle_id": (
                f"rrb_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ),
            "source_multi_atom_retrieval_eval_bundle_id": source_id,
            "rerank_mode": rerank_mode,
            "top_k": top_k,
            "reranked_results": [],
            "summary": {"input_result_count": 0, "output_result_count": 0, "distinct_atoms": 0},
            "warnings": ["RAG_ADVANCED_NO_RESULTS"],
            "status": "fail",
            "timestamp": datetime.datetime.now().isoformat(),
        }

    input_count = len(all_results)

    if rerank_mode == "rrf":
        reranked = _apply_rrf(slot_results, top_k=top_k)
        warnings.append("RERANK_MODE_RRF")
    else:
        reranked = _apply_mmr(all_results, top_k=top_k)
        warnings.append("RERANK_MODE_MMR")

    output_count = len(reranked)
    distinct = len({r.get("atom_id", "") for r in reranked if r.get("atom_id")})

    bundle = {
        "version": "v1.0.0-p2-rag-reranked-results",
        "reranked_multi_atom_result_bundle_id": (
            f"rrb_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ),
        "source_multi_atom_retrieval_eval_bundle_id": source_id,
        "rerank_mode": rerank_mode,
        "top_k": top_k,
        "reranked_results": reranked,
        "summary": {
            "input_result_count": input_count,
            "output_result_count": output_count,
            "distinct_atoms": distinct,
        },
        "warnings": warnings,
        "status": "pass" if output_count > 0 else "fail",
        "timestamp": datetime.datetime.now().isoformat(),
    }

    return bundle


# ── MMR Implementation ────────────────────────────────────────────────


def _apply_mmr(
    all_results: list[dict],
    lambda_weight: float = 0.7,
    top_k: int = 5,
) -> list[dict]:
    """
    Maximum Marginal Relevance reranking.

    Since pairwise atom similarity is not computed by the existing search,
    we approximate diversity by penalizing repeated atom_ids from the same
    slot (diversity via slot_source diversity).

    MMR = lambda * score - (1-lambda) * max_similarity_to_selected
    We approximate max_similarity as 1.0 if the same atom_id appears,
    or 0.5 if same atom appears in a different slot, else 0.0.
    """
    if not all_results:
        return []

    selected: list[dict] = []
    selected_ids: set[str] = set()
    selected_slot_sets: list[set[str]] = []
    candidates = list(all_results)
    # Sort candidates by initial score descending
    candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    for _ in range(min(top_k, len(candidates))):
        best_score = -float("inf")
        best_idx = -1

        for i, cand in enumerate(candidates):
            aid = cand.get("atom_id", "")
            slot_id = cand.get("_slot_id", "")
            score = cand.get("score", 0.0)

            # Approximate similarity to selected set
            max_sim = 0.0
            if aid in selected_ids:
                max_sim = 1.0  # Same atom → high similarity, penalize
            else:
                for sel_slot_set in selected_slot_sets:
                    if slot_id in sel_slot_set:
                        max_sim = 0.5  # Same slot, different atom → moderate similarity
                        break

            mmr_val = lambda_weight * score - (1.0 - lambda_weight) * max_sim

            if mmr_val > best_score:
                best_score = mmr_val
                best_idx = i

        if best_idx >= 0:
            chosen = candidates.pop(best_idx)
            aid = chosen.get("atom_id", "")
            slot_id = chosen.get("_slot_id", "")
            selected.append(chosen)
            selected_ids.add(aid)
            selected_slot_sets.append({slot_id})

    # Build output format
    return _format_results(selected)


# ── RRF Implementation ────────────────────────────────────────────────


def _apply_rrf(
    slot_results: list[dict],
    k_rrf: int = 60,
    top_k: int = 5,
) -> list[dict]:
    """
    Reciprocal Rank Fusion.

    For each atom across all slots, accumulate RRF score = sum(1/(rank + k_rrf)).
    Higher k_rrf gives smoother influence across rank positions.
    """
    rrf_scores: dict[str, dict] = {}
    slot_map: dict[str, set[str]] = {}  # atom_id -> set of slot_ids

    for sr in slot_results:
        slot_id = sr.get("slot_id", "")
        for rank, r in enumerate(sr.get("results", []), start=1):
            aid = r.get("atom_id", "")
            if not aid:
                continue
            if aid not in rrf_scores:
                rrf_scores[aid] = {
                    "atom_id": aid,
                    "score": 0.0,
                    "snippet": r.get("snippet", ""),
                    "metadata": r.get("metadata", {}),
                    "source_slot_ids": [],
                    "_rrf_score": 0.0,
                }
                slot_map[aid] = set()
            rrf_scores[aid]["_rrf_score"] += 1.0 / (rank + k_rrf)
            slot_map[aid].add(slot_id)

    # Sort by RRF score descending
    sorted_atoms = sorted(rrf_scores.values(), key=lambda x: x["_rrf_score"], reverse=True)

    # Assign final score and source slots
    for entry in sorted_atoms:
        aid = entry["atom_id"]
        entry["score"] = round(entry["_rrf_score"], 4)
        entry["source_slot_ids"] = sorted(slot_map.get(aid, set()))

    top = sorted_atoms[:top_k]
    return _format_results(top)


# ── Output formatting ─────────────────────────────────────────────────


def _format_results(results: list[dict]) -> list[dict]:
    """Unify output format with rank."""
    output: list[dict] = []
    for rank, r in enumerate(results, start=1):
        entry = {
            "rank": rank,
            "atom_id": r.get("atom_id", ""),
            "score": round(r.get("score", 0.0), 4),
            "source_slot_ids": r.get("source_slot_ids", []),
            "snippet": r.get("snippet", ""),
            "metadata": r.get("metadata", {}),
        }
        output.append(entry)
    return output
