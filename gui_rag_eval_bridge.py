"""
gui_rag_eval_bridge.py  v1.0.0-p2-rag-eval-frontend

增强包 E — multi-atom query / retrieval eval / rerank / rag eval 前台化

职责：
  把仅存在后端的 multi-atom 检索计划、retrieval eval、rerank、rag eval
  桥接成创作者可读的前台接口。

Spec 要求的 3 个核心接口：
  plan_multi_atom_query(query) → dict
  run_retrieval_and_rerank(plan) → dict
  build_rag_eval_summary(plan, results) → dict

后台承接（不改算法）：
  multi_atom_query_planner.build_multi_atom_query_plan()
  multi_atom_retrieval_evaluator.run_multi_atom_retrieval_and_eval()
  rag_advanced_reranker.build_reranked_multi_atom_result_bundle()
  rag_advanced_eval_builder.build_rag_eval_bundle()
  p2_rag_runner.run_p2_rag_pipeline()
"""
from __future__ import annotations

import datetime
from typing import Any


# ══════════════════════════════════════════════════════════
# Spec 要求的 3 个核心接口
# ══════════════════════════════════════════════════════════

def plan_multi_atom_query(query: str, storyline_context: dict | None = None) -> dict:
    """
    Spec 接口 1：返回 multi-atom 检索计划。
    至少包含：
    - atoms: list[dict]  每个 atom 的文本/标签/权重
    - slots: list[dict]  覆盖的叙事槽位/阶段
    - diagnostics: dict  coverage/diversity/distinct_atoms 等
    """
    try:
        from app.core.multi_atom_query_planner import build_multi_atom_query_plan
        plan = build_multi_atom_query_plan(query, storyline_context)
    except Exception:
        plan = _fallback_plan(query)

    # 重塑为 spec 要求的格式
    atoms: list[dict] = []
    slots: list[dict] = []
    for s in plan.get("slots", []):
        slots.append({
            "slot_id": s.get("slot_id", ""),
            "slot_name": s.get("slot_name", ""),
            "description": s.get("description", ""),
            "base_query": s.get("base_query", query),
        })
        atoms.append({
            "atom_text": s.get("description", ""),
            "tags": [s.get("slot_name", "")],
            "weight": s.get("expected_min_results", 5),
            "slot_id": s.get("slot_id", ""),
        })

    # 诊断指标（先定默认值，真实的由 evaluator 填充）
    diagnostics = {
        "coverage": "待评估",
        "diversity": 0.0,
        "distinct_atoms": 0,
        "total_slots": len(slots),
    }

    return {
        "status": plan.get("status", "ok"),
        "user_query": plan.get("user_query", query),
        "atoms": atoms,
        "slots": slots,
        "diagnostics": diagnostics,
        "raw_plan": plan,  # 保留原始数据供 evaluator 使用
    }


def run_retrieval_and_rerank(plan: dict, top_k: int = 5, rerank_mode: str = "mmr") -> dict:
    """
    Spec 接口 2：执行检索 + rerank，返回前后对比。
    返回：
    - before: list[dict]  原始排序结果（top N）
    - after: list[dict]   rerank 后结果（top N）
    - metrics: dict       命中质量、重排增益等
    """
    raw_plan = plan.get("raw_plan", plan)

    # 1) 检索 + eval
    try:
        from app.core.multi_atom_retrieval_evaluator import run_multi_atom_retrieval_and_eval
        eval_bundle = run_multi_atom_retrieval_and_eval(raw_plan, top_k=top_k)
    except Exception:
        eval_bundle = _fallback_eval_bundle(raw_plan)

    # 2) 提取 before（原始检索结果）
    before: list[dict] = []
    for sr in eval_bundle.get("slot_results", []):
        for r in sr.get("results", []):
            before.append({
                "rank": len(before) + 1,
                "atom_id": r.get("atom_id", ""),
                "snippet": r.get("snippet", "")[:80],
                "score": r.get("score", 0.0),
                "slot": sr.get("slot_name", sr.get("slot_id", "")),
            })

    # 3) Rerank
    try:
        from app.core.rag_advanced_reranker import build_reranked_multi_atom_result_bundle
        rerank_bundle = build_reranked_multi_atom_result_bundle(
            eval_bundle, rerank_mode=rerank_mode, top_k=top_k
        )
    except Exception:
        rerank_bundle = _fallback_rerank_bundle(eval_bundle)

    # 4) 提取 after（rerank 后结果）
    after: list[dict] = []
    for r in rerank_bundle.get("reranked_results", []):
        after.append({
            "rank": len(after) + 1,
            "atom_id": r.get("atom_id", ""),
            "snippet": r.get("snippet", "")[:80],
            "score": r.get("score", 0.0),
            "slot": r.get("_slot_id", ""),
        })

    # 5) 计算重排增益
    gain = _compute_rerank_gain(before, after)
    global_metrics = eval_bundle.get("global_metrics", {})

    metrics = {
        "total_input": len(before),
        "total_output": len(after),
        "rerank_gain": gain,
        "coverage": global_metrics.get("estimated_slot_coverage", 0.0),
        "diversity": global_metrics.get("diversity_score", 0.0),
        "distinct_atoms": global_metrics.get("distinct_atoms", 0),
        "diagnostics": global_metrics,
    }

    return {
        "status": rerank_bundle.get("status", "ok"),
        "before": before,
        "after": after,
        "metrics": metrics,
        "rerank_mode": rerank_mode,
        "raw_eval_bundle": eval_bundle,
    }


def build_rag_eval_summary(plan: dict, results: dict) -> dict:
    """
    Spec 接口 3：返回 eval 汇总，创作者可读。
    至少包含：
    - coverage_summary: str
    - diversity_summary: str
    - risk_summary: str
    - recommended_action: str
    """
    metrics = results.get("metrics", {})
    before = results.get("before", [])
    after = results.get("after", [])
    plan_diag = plan.get("diagnostics", {})

    # 构建覆盖总结
    total_slots = plan_diag.get("total_slots", 0) or metrics.get("total_slots", 0)
    coverage = metrics.get("coverage", 0.0)
    if coverage >= 0.8:
        coverage_summary = f"检索覆盖较好：{total_slots} 个槽位中大部分都有命中结果（覆盖率 {coverage:.0%}）。"
    elif coverage >= 0.5:
        coverage_summary = f"检索覆盖一般：{total_slots} 个槽位中约有 {int(total_slots * coverage)} 个有结果（覆盖率 {coverage:.0%}），建议补充部分槽位的素材。"
    else:
        coverage_summary = f"检索覆盖不足：{total_slots} 个槽位中只有少数有结果（覆盖率 {coverage:.0%}），需整体增加相关素材。"

    # 多样性总结
    diversity = metrics.get("diversity", 0.0)
    distinct = metrics.get("distinct_atoms", 0)
    if diversity >= 0.6:
        diversity_summary = f"Atom 多样性良好：检索结果中有 {distinct} 个不同的原子（多样性得分 {diversity:.2f}），素材分布较均衡。"
    elif diversity >= 0.3:
        diversity_summary = f"Atom 多样性一般：{distinct} 个不同原子（多样性得分 {diversity:.2f}），部分槽位存在重复素材，建议增加差异化的素材。"
    else:
        diversity_summary = f"Atom 多样性不足：仅 {distinct} 个不同原子（多样性得分 {diversity:.2f}），大量素材集中在少数槽位，需增加覆盖不同叙事阶段的素材。"

    # 风险总结
    before_count = len(before)
    after_count = len(after)
    gain = metrics.get("rerank_gain", 0.0)
    if before_count == 0:
        risk_summary = "⚠ 检索未返回任何结果，请检查素材库中是否有与查询匹配的内容。建议先用标签搜索确认素材存在。"
    elif after_count < before_count * 0.5:
        risk_summary = "⚠ Rerank 后结果显著减少，可能意味着大量低分素材被过滤。建议检查查询的精确性，或扩展检索参数。"
    else:
        risk_summary = f"Rerank 重排后保留 {after_count}/{before_count} 条结果，重排增益 {gain:+.2f}。结果集质量稳定。"

    # 建议动作
    actions = []
    if coverage < 0.5:
        actions.append(f"增加覆盖不足槽位的素材（当前覆盖率 {coverage:.0%}）")
    if diversity < 0.3:
        actions.append("增加不同叙事阶段的差异化素材，减少同质化")
    if diversity < 0.6 and distinct < 5:
        actions.append("增加主题/冲突/情绪类型的多样性")
    if before_count == 0:
        actions.append("在素材库中先确认存在相关素材，或调整查询词条")
    if not actions:
        actions.append("当前检索表现良好，无需特别调整。可尝试更多查询以进一步探索素材库。")

    return {
        "coverage_summary": coverage_summary,
        "diversity_summary": diversity_summary,
        "risk_summary": risk_summary,
        "recommended_action": "\n".join(f"• {a}" for a in actions),
        "diagnostics": {
            "coverage": round(coverage, 4),
            "diversity": round(diversity, 4),
            "distinct_atoms": distinct,
            "rerank_gain": round(gain, 4),
        },
    }


# ══════════════════════════════════════════════════════════
# 内部工具函数
# ══════════════════════════════════════════════════════════

def _compute_rerank_gain(before: list[dict], after: list[dict]) -> float:
    """计算重排前后平均分变化。"""
    b_scores = [r.get("score", 0.0) for r in before if r.get("score") is not None]
    a_scores = [r.get("score", 0.0) for r in after if r.get("score") is not None]
    if not b_scores:
        return 0.0
    b_avg = sum(b_scores) / len(b_scores)
    a_avg = sum(a_scores) / len(a_scores) if a_scores else 0.0
    return round(a_avg - b_avg, 4)


def _fallback_plan(query: str) -> dict:
    """当后端 planner 不可用时的降级计划。"""
    return {
        "version": "v1.0.0-p2-rag-eval-frontend-fallback",
        "user_query": query or "",
        "slots": [
            {
                "slot_id": "cause",
                "slot_name": "起因",
                "description": f"与「{query}」相关的起因类素材",
                "base_query": query,
                "expected_min_results": 3,
            },
            {
                "slot_id": "conflict",
                "slot_name": "冲突",
                "description": f"与「{query}」相关的冲突类素材",
                "base_query": query,
                "expected_min_results": 3,
            },
            {
                "slot_id": "emotion",
                "slot_name": "情感",
                "description": f"与「{query}」相关的情感类素材",
                "base_query": query,
                "expected_min_results": 3,
            },
        ],
        "status": "ready",
        "warnings": [],
        "timestamp": datetime.datetime.now().isoformat(),
    }


def _fallback_eval_bundle(raw_plan: dict) -> dict:
    """当 evaluator 不可用时的降级 eval bundle。"""
    slots = raw_plan.get("slots", [])
    return {
        "slot_results": [
            {
                "slot_id": s.get("slot_id", ""),
                "slot_name": s.get("slot_name", ""),
                "results": [],
                "metrics": {"hit_count": 0, "distinct_storylines": 0},
            }
            for s in slots
        ],
        "global_metrics": {
            "total_slots": len(slots),
            "slots_with_results": 0,
            "estimated_slot_coverage": 0.0,
            "distinct_atoms": 0,
            "diversity_score": 0.0,
        },
        "status": "fail",
        "warnings": ["FALLBACK_EVAL_BUNDLE"],
    }


def _fallback_rerank_bundle(eval_bundle: dict) -> dict:
    """当 reranker 不可用时的降级 rerank bundle。"""
    return {
        "reranked_results": [],
        "summary": {"input_result_count": 0, "output_result_count": 0},
        "status": "fail",
        "warnings": ["FALLBACK_RERANK_BUNDLE"],
    }