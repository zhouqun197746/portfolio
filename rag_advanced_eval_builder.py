"""
rag_advanced_eval_builder.py  v1.0.0-p2-rag-advanced-eval (P2_RAG)

Advanced retrieval evaluation: Precision@K, Recall@K, nDCG@K,
plus preserved basic metrics (slot_coverage, diversity_score).
"""
import datetime
import math
from typing import Any


def build_rag_advanced_eval_bundle(
    multi_atom_retrieval_eval_bundle: dict,
    relevance_judgments: dict | None = None,
    reranked_result_bundle: dict | None = None,
    top_k: int = 5,
) -> dict:
    """
    Build advanced eval bundle.

    Args:
        multi_atom_retrieval_eval_bundle: output of A1-6 evaluator.
        relevance_judgments: optional dict {judgments: [{atom_id, relevance}]}
        reranked_result_bundle: optional output of build_reranked_multi_atom_result_bundle.
        top_k: top_k for metric calculation.

    Returns:
        rag_advanced_eval_bundle dict.
    """
    source_retrieval_id = multi_atom_retrieval_eval_bundle.get(
        "multi_atom_retrieval_eval_bundle_id", ""
    )
    source_rerank_id = ""
    if reranked_result_bundle:
        source_rerank_id = reranked_result_bundle.get(
            "reranked_multi_atom_result_bundle_id", ""
        )

    warnings: list[str] = []
    global_metrics = multi_atom_retrieval_eval_bundle.get("global_metrics", {})
    slot_results = multi_atom_retrieval_eval_bundle.get("slot_results", [])

    # Extract all result atom IDs from reranked or raw results
    if reranked_result_bundle:
        results_list = reranked_result_bundle.get("reranked_results", [])
    else:
        results_list = []
        for sr in slot_results:
            for r in sr.get("results", []):
                results_list.append(r)

    # Unique atom IDs in the result set
    result_atom_ids = []
    seen = set()
    for r in results_list:
        aid = r.get("atom_id", "")
        if aid and aid not in seen:
            seen.add(aid)
            result_atom_ids.append(aid)

    result_atom_set = set(result_atom_ids)

    # ── Relevance judgments ──
    has_judgments = False
    judged_atom_count = 0
    judgments_map: dict[str, int] = {}
    if relevance_judgments and "judgments" in relevance_judgments:
        for j in relevance_judgments["judgments"]:
            aid = j.get("atom_id", "")
            rel = j.get("relevance", 0)
            if aid:
                judgments_map[aid] = min(max(rel, 0), 3)
                judged_atom_count += 1
        if judgments_map:
            has_judgments = True
            warnings.append("RAG_ADVANCED_EVAL_BUILT")
        else:
            warnings.append("RAG_ADVANCED_NO_JUDGMENTS")
    else:
        warnings.append("RAG_ADVANCED_NO_JUDGMENTS")

    # ── Basic metrics (always preserved) ──
    slot_coverage = global_metrics.get("estimated_slot_coverage", 0.0)
    diversity_score = global_metrics.get("diversity_score", 0.0)
    distinct_atoms = global_metrics.get("distinct_atoms", 0)

    # ── Advanced IR metrics ──
    precision_k = None
    recall_k = None
    ndcg_k = None

    if has_judgments and result_atom_ids:
        # Precision@K: fraction of top-k results that are relevant
        judged_ids_for_precision = [
            aid for aid in result_atom_ids[:top_k]
            if judgments_map.get(aid, 0) >= 1
        ]
        precision_k = len(judged_ids_for_precision) / min(top_k, len(result_atom_ids) or 1)

        # Recall@K: fraction of total relevant items found in top-k
        total_relevant = sum(1 for rel in judgments_map.values() if rel >= 1)
        if total_relevant > 0:
            recall_k = len(judged_ids_for_precision) / total_relevant
        else:
            recall_k = 0.0

        # nDCG@K
        ndcg_k = _compute_ndcg(result_atom_ids[:top_k], judgments_map, top_k)
    else:
        # No judgments: IR metrics remain None
        pass

    # Determine relevant items from judgments
    all_judged_count = len(judgments_map)

    status = "pass"
    if not result_atom_ids:
        warnings.append("RAG_ADVANCED_NO_RESULTS")
        status = "fail"
    elif has_judgments and all_judged_count < distinct_atoms:
        warnings.append("RAG_ADVANCED_PARTIAL_JUDGMENTS")
        status = "warn"

    bundle = {
        "version": "v1.0.0-p2-rag-advanced-eval",
        "rag_advanced_eval_bundle_id": (
            f"raeb_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ),
        "source_multi_atom_retrieval_eval_bundle_id": source_retrieval_id,
        "source_reranked_multi_atom_result_bundle_id": source_rerank_id,
        "top_k": top_k,
        "metrics": {
            "precision_at_k": round(precision_k, 4) if precision_k is not None else None,
            "recall_at_k": round(recall_k, 4) if recall_k is not None else None,
            "ndcg_at_k": round(ndcg_k, 4) if ndcg_k is not None else None,
            "slot_coverage": slot_coverage,
            "diversity_score": diversity_score,
            "distinct_atoms": distinct_atoms,
        },
        "judgment_summary": {
            "has_relevance_judgments": has_judgments,
            "judged_atom_count": judged_atom_count,
        },
        "warnings": warnings,
        "status": status,
        "timestamp": datetime.datetime.now().isoformat(),
    }

    return bundle


# ── nDCG Implementation ───────────────────────────────────────────────


def _compute_ndcg(
    ranked_ids: list[str],
    judgments: dict[str, int],
    k: int,
) -> float:
    """
    Compute nDCG@K from ranked atom IDs and relevance judgments.

    nDCG = DCG / IDCG
    DCG = sum((2^rel_i - 1) / log2(i + 1))
    """
    if not ranked_ids:
        return 0.0

    k = min(k, len(ranked_ids))
    dcg = 0.0
    for i, aid in enumerate(ranked_ids[:k], start=1):
        rel = judgments.get(aid, 0)
        dcg += (2 ** rel - 1) / math.log2(i + 1)

    # Ideal DCG: sort by relevance descending
    ideal_rels = sorted(
        [judgments.get(aid, 0) for aid in ranked_ids],
        reverse=True,
    )[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal_rels, start=1):
        idcg += (2 ** rel - 1) / math.log2(i + 1)

    if idcg == 0.0:
        return 0.0
    return dcg / idcg
