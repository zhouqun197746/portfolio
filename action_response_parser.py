"""
action_response_parser.py  v1.0.0-p2-gui-integration

Parses action response dicts into human-readable summary lines
suitable for display in a Tkinter Text widget or status bar.

Does NOT import any core module — only string formatting on dicts.
"""
from __future__ import annotations

import datetime
from typing import Any, Callable


def parse_rerank_response(response: dict | None) -> list[str]:
    """Summarise a rerank_search_results response."""
    if response is None:
        return ["(未执行)"]
    status = response.get("status", "unknown")
    if status != "pass":
        errs = response.get("errors", [])
        return [f"状态: 失败", *[f"  · {e}" for e in errs]]

    output = response.get("output", {})
    lines: list[str] = []
    lines.append(f"✅ 重排检索完成")

    # Top-level output fields
    reranked = output.get("reranked_results", output.get("results", []))
    if isinstance(reranked, list):
        lines.append(f"结果数: {len(reranked)}")
        for i, r in enumerate(reranked[:5]):
            title = r.get("title", r.get("content", ""))[:60]
            score = r.get("score", r.get("rerank_score", "?"))
            lines.append(f"  [{i+1}] score={score} {title}")
        if len(reranked) > 5:
            lines.append(f"  ... 还有 {len(reranked) - 5} 条")

    # Show mode and top_k used
    mode = output.get("rerank_mode", response.get("rerank_mode", "?"))
    top_k = output.get("top_k", response.get("top_k", "?"))
    lines.append(f"模式: {mode} | top_k={top_k}")

    return lines


def parse_apply_world_response(response: dict | None) -> list[str]:
    """Summarise an apply_world_content_pack response."""
    if response is None:
        return ["(未执行)"]
    status = response.get("status", "unknown")
    if status != "pass":
        errs = response.get("errors", [])
        return [f"状态: 失败", *[f"  · {e}" for e in errs]]

    output = response.get("output", {})
    lines: list[str] = []
    lines.append(f"状态: 成功")

    # Applied metadata context
    meta = output.get("metadata_context", output.get("world_pack_metadata_context", {}))
    if isinstance(meta, dict):
        fields = list(meta.keys())
        lines.append(f"影响元数据字段: {fields if fields else '(空)'}")

    # Applied RAG context
    rag = output.get("rag_context", output.get("world_content_rag_context", {}))
    if isinstance(rag, dict):
        keys = list(rag.keys())
        lines.append(f"RAG 上下文键: {keys if keys else '(空)'}")

    # Mode info
    mode = output.get("mode", response.get("mode", "both"))
    lines.append(f"应用模式: {mode}")

    return lines


def parse_refresh_dashboard_response(response: dict | None) -> list[str]:
    """
    Summarise a refresh_governance_dashboard response (4-state aware).

    Handles the 4-state refresh protocol:
      - loading: snapshot is being built (initial / in-progress)
      - ready:  snapshot completed with current data
      - failed: snapshot construction raised an exception
      - stale:  previous snapshot data shown, but refresh failed
    """
    if response is None:
        return ["(未执行)"]
    status = response.get("status", "unknown")

    output = response.get("output", {})
    snapshot = output.get("snapshot", {})
    snapshot_state = output.get("snapshot_state", "unknown")
    meta = snapshot.get("meta", {})
    snap_time = meta.get("snapshot_time", output.get("snapshot_time", "?"))
    error_msg = meta.get("error_message", "")

    lines: list[str] = []

    # ── State-aware header ──────────────────────────────────
    if snapshot_state == "loading":
        lines.append("⏳ 治理快照正在生成中...")
        lines.append(f"状态: loading | 时间: {snap_time}")
        return lines
    elif snapshot_state == "failed":
        lines.append("❌ 治理快照生成失败")
        lines.append(f"状态: failed | 时间: {snap_time}")
        if error_msg:
            lines.append(f"错误: {error_msg[:200]}")
        return lines
    elif snapshot_state == "stale":
        lines.append("⚠️ 快照为旧数据（上次刷新失败，仍显示上一份结果）")
        lines.append(f"状态: stale | 时间: {snap_time}")
        if error_msg:
            lines.append(f"上次失败: {error_msg[:200]}")
    else:
        lines.append("✅ 治理快照已刷新")
        lines.append(f"状态: ready | 时间: {snap_time}")

    # ── Audit ───────────────────────────────────────────────
    audit = snapshot.get("audit", {})
    if isinstance(audit, dict):
        lines.append(f"审计: {audit.get('event_count', 0)} 事件, "
                     f"{audit.get('pending_approval_count', 0)} 待审批, "
                     f"{audit.get('scene_draft_count', 0)} 草稿, "
                     f"{audit.get('check_report_count', 0)} 质检报告")

    # ── Risk ────────────────────────────────────────────────
    risk = snapshot.get("risk", {})
    if isinstance(risk, dict):
        lines.append(f"风险: {risk.get('open_risk_count', 0)} 开放, "
                     f"{risk.get('high_severity_count', 0)} 高危, "
                     f"趋势={risk.get('trend', '?')}, "
                     f"遗留={risk.get('legacy_fallback_count', 0)}, "
                     f"缺失引用={risk.get('missing_reference_count', 0)}")

    # ── Lineage ─────────────────────────────────────────────
    lineage = snapshot.get("lineage", {})
    if isinstance(lineage, dict):
        lines.append(f"流转链路: {lineage.get('node_count', 0)} 节点, "
                     f"{lineage.get('edge_count', 0)} 边, "
                     f"{lineage.get('complete_chain_count', 0)} 完整, "
                     f"{lineage.get('broken_chain_count', 0)} 断链")
        # Sample paths
        sample_paths = lineage.get("sample_paths", [])
        if sample_paths:
            lines.append(f"  路径样例 ({len(sample_paths)} 条):")
            for p in sample_paths[:4]:
                lines.append(f"    {p}")
        worst = lineage.get("top_broken_stage", "")
        if worst:
            lines.append(f"  最薄弱环节: {worst}")

    # ── Ops ─────────────────────────────────────────────────
    ops = snapshot.get("ops", {})
    if isinstance(ops, dict):
        freshness_lbl = {
            "active": "活跃",
            "stale": "较旧",
            "cold": "长期未活动",
            "unavailable": "暂未接入",
        }.get(str(ops.get("freshness_status", "")), ops.get("freshness_status", "?"))
        lines.append(f"运维: 队列={ops.get('queue_depth', 0)}, "
                     f"错误={ops.get('error_count', 0)}, "
                     f"警告={ops.get('warning_count', 0)}, "
                     f"活跃度={freshness_lbl}, "
                     f"延迟={ops.get('snapshot_latency_ms', 0)}ms")

    # ── Data sources ────────────────────────────────────────
    data_sources = meta.get("data_sources", {})
    if isinstance(data_sources, dict) and data_sources:
        statuses = []
        for source, info in data_sources.items():
            s = info.get("status", "?")
            statuses.append(f"{source}={s}")
        if statuses:
            lines.append(f"数据源: {', '.join(statuses)}")

    return lines


def parse_generate_task_cards_response(response: dict | None) -> list[str]:
    """Summarise a generate_task_cards response (real bridge action)."""
    if response is None:
        return ["(未执行)"]
    status = response.get("status", "unknown")
    if status != "pass":
        errs = response.get("errors", [])
        return [f"状态: 失败", *[f"  · {e}" for e in errs]]

    output = response.get("output", {})
    lines: list[str] = []
    lines.append(f"✅ 任务卡生成完成")

    cards = output.get("cards", [])
    if isinstance(cards, list):
        lines.append(f"共生成 {len(cards)} 张任务卡:")
        for i, card in enumerate(cards):
            title = (card.get("title", "") or "")[:60]
            ctype = card.get("card_type", "?")
            lines.append(f"  [{i+1}] ({ctype}) {title}")
        lines.append("")
        lines.append("下一步: 切换到「场景扩写」Tab 继续创作")
    else:
        lines.append(f"卡片数: {output.get('card_count', 0)}")

    query_used = output.get("query_used", "")
    if query_used:
        lines.append(f"基于需求: {query_used[:60]}...")

    creative_level = output.get("creative_level")
    if creative_level is not None:
        lines.append(f"创意等级: {creative_level}")

    return lines


def parse_generate_scene_seeds_response(response: dict | None) -> list[str]:
    """Summarise a generate_scene_seeds response (real material query)."""
    if response is None:
        return ["(未执行)"]
    status = response.get("status", "unknown")
    if status != "pass":
        errs = response.get("errors", [])
        return [f"状态: 失败", *[f"  · {e}" for e in errs]]

    output = response.get("output", {})
    lines: list[str] = []
    lines.append(f"✅ 场景种子生成完成")

    seeds = output.get("seeds", [])
    if isinstance(seeds, list):
        lines.append(f"共 {len(seeds)} 个候选种子（从 {output.get('total_filtered', 0)} 条素材中筛选）:")
        lines.append("")
        for i, seed in enumerate(seeds[:8]):
            title = seed.get("title", seed.get("text_preview", ""))[:60]
            source = seed.get("source_type", "?")
            cat = seed.get("category", "")
            cat_str = f" [{cat}]" if cat else ""
            lines.append(f"  [{i+1}] {title} ({source}){cat_str}")
        if len(seeds) > 8:
            lines.append(f"  ... 还有 {len(seeds) - 8} 条")
        lines.append("")
        lines.append("下一步: 挑选感兴趣的种子 → 切换到「场景扩写」")
    else:
        lines.append(f"种子数: {output.get('seed_count', 0)}")

    return lines


def parse_generic_response(response: dict | None, action_id: str = "") -> list[str]:
    """Fallback: show top-level keys and value previews."""
    if response is None:
        return ["(空)"]
    status = response.get("status", "unknown")
    if status != "pass":
        errs = response.get("errors", [])
        return [f"状态: 失败", *[f"  · {e}" for e in errs]]

    lines: list[str] = [f"状态: 成功"]
    output = response.get("output", {})
    if isinstance(output, dict):
        for k, v in output.items():
            preview = str(v)[:80]
            lines.append(f"  {k}: {preview}")
    else:
        lines.append(f"  output: {str(output)[:120]}")
    return lines


# ── Dispatcher ───────────────────────────────────────────────

ACTION_PARSERS: dict[str, Callable[..., list[str]]] = {
    "rerank_search_results": parse_rerank_response,
    "apply_world_content_pack": parse_apply_world_response,
    "refresh_governance_dashboard": parse_refresh_dashboard_response,
    "generate_task_cards": parse_generate_task_cards_response,
    "generate_scene_seeds": parse_generate_scene_seeds_response,
}


def summarize_action_response(action_id: str, response: dict | None) -> str:
    """
    Return a multi-line string summary of an action response.
    Suitable for displaying in a Tkinter Text widget.
    """
    parser = ACTION_PARSERS.get(action_id, parse_generic_response)
    lines = parser(response)
    return "\n".join(lines)


def format_debug_json(response: dict | None) -> str:
    """Return a formatted JSON string for debug display."""
    if response is None:
        return "{}"
    import json
    try:
        return json.dumps(response, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(response)
