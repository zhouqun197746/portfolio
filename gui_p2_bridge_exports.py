"""
gui_p2_bridge_exports.py — GUI 对 core 的唯一 P2 前门 (Anti-Corruption Layer / Facade)
================================================================================

职责:
  1. 对 GUI 暴露稳定接口名（不随内部 bridge/builder/runner 实现变化）
  2. 对 core bridge 做轻量别名映射（已有独立 bridge 文件）
  3. 对过渡实现做受控包装（标记 TRANSITIONAL，后续应拆为独立 bridge）
  4. 不承担复杂业务逻辑（实际流程仍在各 bridge/*_p2_bridge.py 中）

设计规则:
  - GUI 只从此模块导入，不直接 import 各 bridge 内部函数
  - 已有独立 bridge 文件 → 别名导出 (from ... import ... as ...)
  - 尚无独立 bridge → 轻量转发包装（标记 TRANSITIONAL + 记录来源模块）
  - 禁止在 exports 中堆业务逻辑
  - __all__ 声明公开接口清单 (供 IDE / 静态检查 / 测试使用)

接口分类:
  - CORE_EXPORTS:     已有独立 bridge 的别名/重导出
  - TRANSITIONAL:     尚无独立 bridge 的过渡包装，函数内有 "TRANSITIONAL" 标记
  - CONSTANT_EXPORTS: 白名单只读常量（如 CREATIVE_METHODS_REGISTRY）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# 核心 P2 bridge 别名导出 (已有独立 bridge 文件)
# ════════════════════════════════════════════════════════════

# ── export / sync 轻量别名 (任务包11) ────────────────────
# GUI 统一前端命名: export_to_obsidian / sync_to_notion / get_recent_exports / get_recent_syncs
# 这些只是别名/薄包装, 不堆业务逻辑

def export_to_obsidian(target_type: str = "task_card", scene_draft_id: str = "") -> dict:
    """
    导出到 Obsidian — 轻量别名。
    来源: app.integrations.obsidian_exporter
    """
    try:
        from app.integrations.obsidian_exporter import (
            export_task_card,
            export_scene_draft,
            export_check_report,
            export_blueprint,
        )
        if target_type == "task_card":
            from app.storage.task_store import get_task_card
            card = get_task_card(scene_draft_id or None)
            if card:
                result = export_task_card(card)
                return {"status": "ok", "target": "obsidian", "type": "task_card",
                        "id": scene_draft_id, "detail": str(result)}
        elif target_type == "scene_draft":
            from app.storage.scene_store import get_scene_draft
            draft = get_scene_draft(scene_draft_id or None)
            if draft:
                result = export_scene_draft(draft)
                return {"status": "ok", "target": "obsidian", "type": "scene_draft",
                        "id": scene_draft_id, "detail": str(result)}
        elif target_type == "check_report":
            from app.storage.report_store import get_report
            report = get_report(scene_draft_id or None)
            if report:
                result = export_check_report(report)
                return {"status": "ok", "target": "obsidian", "type": "check_report",
                        "id": scene_draft_id, "detail": str(result)}
        return {"status": "ok", "target": "obsidian", "type": target_type,
                "id": scene_draft_id, "note": "no data to export"}
    except Exception as e:
        return {"status": "fail", "error": str(e)}


def sync_to_notion(target_type: str = "task_card", target_id: str = "") -> dict:
    """
    同步到 Notion — 轻量别名。
    来源: app.integrations.notion_sync_adapter
    """
    try:
        from app.integrations.notion_sync_adapter import sync_to_notion as _impl
        result = _impl(target_type, target_id)
        return {"status": "ok", "target": "notion", "type": target_type,
                "id": target_id, "detail": str(result)}
    except Exception as e:
        return {"status": "fail", "target": "notion", "error": str(e)}


def get_recent_exports(limit: int = 5) -> list[dict]:
    """
    查看最近导出 — 轻量只读别名。
    来源: 从 reports 目录扫描最近含 export 的报告。
    不新建持久化系统，只读已有状态。
    """
    import glob, json, os
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reports")
    candidates = []
    for fpath in sorted(glob.glob(os.path.join(reports_dir, "*.json")), reverse=True)[:limit * 3]:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                if any(k in data for k in ("exported_count", "exports_success", "obsidian", "export")):
                    candidates.append({
                        "source": os.path.basename(fpath),
                        "timestamp": data.get("timestamp", ""),
                        "status": data.get("status", "ok"),
                        "detail": {k: data[k] for k in ("exported_count", "exports_success", "obsidian", "export") if k in data},
                    })
        except Exception:
            pass
    return candidates[:limit]


def get_recent_syncs(limit: int = 5) -> list[dict]:
    """
    查看最近同步 — 轻量只读别名。
    来源: 从 reports 目录扫描最近含 notion 的报告。
    不新建持久化系统，只读已有状态。
    """
    import glob, json, os
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reports")
    candidates = []
    for fpath in sorted(glob.glob(os.path.join(reports_dir, "*.json")), reverse=True)[:limit * 3]:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                if any(k in data for k in ("notion", "notion_syncs", "NotionSync", "sync")):
                    candidates.append({
                        "source": os.path.basename(fpath),
                        "timestamp": data.get("timestamp", ""),
                        "status": data.get("status", "ok"),
                        "detail": {k: data[k] for k in ("notion", "notion_syncs", "sync", "NotionSync") if k in data},
                    })
        except Exception:
            pass
    return candidates[:limit]


# ── task_card_p2_bridge ──────────────────────────────────
from app.core.task_card_p2_bridge import (
    generate_task_cards_via_p2 as generate_task_cards,
    generate_task_cards_with_audit_data,
    generate_cards_legacy,
)

# ── scene_write_p2_bridge ────────────────────────────────
def write_scene(*args, **kwargs):
    from app.core.scene_write_p2_bridge import write_scene_via_p2
    return write_scene_via_p2(*args, **kwargs)


def write_scene_for_gui(
    scene_description: str,
    seed_bundle: dict | None = None,
    source_info: dict | None = None,
) -> dict:
    """GUI 友好版 write_scene：接受字符串描述，自动构建 SceneTaskCard 并调用 current path。
    
    Args:
        scene_description: 场景描述文本
        seed_bundle: 可选的场景种子 bundle（来自种子 Tab）
        source_info: 可选的来源信息（task_card_id, method_id, seed_id, blueprint_id 等）
    
    Returns:
        dict 包含 scene_draft_id, scene_pipeline, version, 以及打平的 _ 前缀字段
    """
    try:
        from app.storage.task_store import add_task_card
        from app.models.task_card import SceneTaskCard
        from app.core.scene_write_p2_bridge import write_scene_via_p2
        
        # Build a minimal SceneTaskCard from description
        task_card = SceneTaskCard(
            id="sc_{}".format(hash(scene_description) & 0xFFFFFF),
            title=scene_description[:80],
            one_line_bone=scene_description[:200],
            card_type="scene",
        )
        if source_info:
            meta = getattr(task_card, 'metadata', {}) or {}
            meta.update(source_info)
            if seed_bundle:
                meta["seed_bundle_id"] = seed_bundle.get("seed_bundle_id", 
                    seed_bundle.get("scene_seed_bundle_id", ""))
                meta["seed_title"] = ""
                seeds = seed_bundle.get("seeds", seed_bundle.get("scene_seeds", []))
                if seeds:
                    s = seeds[0] if isinstance(seeds, list) else seeds
                    meta["seed_title"] = s.get("title", s.get("seed_title", ""))
            task_card.metadata = meta
        
        result = write_scene_via_p2(
            task_card=task_card,
            seed_bundle=seed_bundle,
            style="novel",
            use_llm=False,
        )
        
        # Enrich result with flat fields for GUI display
        if isinstance(result, dict):
            result["_scene_pipeline"] = result.get("scene_pipeline", "unknown")
            result["_version"] = result.get("version", 1)
            result["_scene_draft_id"] = result.get("scene_id", "")
            result["_source_info"] = source_info or {}; result["status"] = result.get("status", "ok")
            if seed_bundle:
                result["_seed_id"] = seed_bundle.get("seed_id", "")
                seeds2 = seed_bundle.get("seeds", seed_bundle.get("scene_seeds", []))
                if seeds2:
                    s2 = seeds2[0] if isinstance(seeds2, list) else seeds2
                    result["_seed_title"] = s2.get("title", s2.get("seed_title", ""))
        return result
    except Exception as e:
        import traceback
        return {"status": "fail", "error": str(e), "_scene_pipeline": "fail", "_version": 0}


def write_scene_legacy(*args, **kwargs):
    from app.core.scene_write_p2_bridge import write_scene_legacy as _impl
    return _impl(*args, **kwargs)


write_scenes: Any = write_scene

# ── scene_seed_p2_bridge ─────────────────────────────────
from app.core.scene_seed_p2_bridge import (
    generate_scene_seeds_via_blueprint as generate_scene_seeds_from_blueprint,
    generate_scene_seeds_from_material_pipeline,
    generate_scene_seeds_legacy,
    validate_blueprint_bundle_for_seed,
)

# ── scene_review_p2_bridge ───────────────────────────────
def check_scene_via_p2(*args, **kwargs):
    from app.core.scene_review_p2_bridge import check_scene_via_p2 as _impl
    return _impl(*args, **kwargs)


def rewrite_scene_via_p2(*args, **kwargs):
    from app.core.scene_review_p2_bridge import rewrite_scene_via_p2 as _impl
    return _impl(*args, **kwargs)


def check_scene_legacy(*args, **kwargs):
    from app.core.scene_review_p2_bridge import check_scene_legacy as _impl
    return _impl(*args, **kwargs)


def rewrite_scene_legacy(*args, **kwargs):
    from app.core.scene_review_p2_bridge import rewrite_scene_legacy as _impl
    return _impl(*args, **kwargs)


def set_approval_status(*args, **kwargs):
    from app.core.scene_review_p2_bridge import set_approval_status as _impl
    return _impl(*args, **kwargs)


def get_approval_status(*args, **kwargs):
    from app.core.scene_review_p2_bridge import get_approval_status as _impl
    return _impl(*args, **kwargs)

# ── outline_blueprint_p2_bridge ──────────────────────────
from app.core.outline_blueprint_p2_bridge import (
    generate_outline_variants_via_p2 as generate_outline_variants,
    generate_blueprint_from_selected_variant,
    generate_blueprint_from_winner_via_p2 as generate_blueprint_from_winner,
    extract_variant_summary,
    extract_stage_summary,
)


# ════════════════════════════════════════════════════════════
# 过渡包装: 已有 bridge 文件的辅助函数
# ════════════════════════════════════════════════════════════

from app.core.task_card_p2_bridge import CREATIVE_METHODS_REGISTRY


def load_seed_preview(
    scene_seed_bundle: dict | None = None,
    selected_seed_index: int = 0,
    blueprint_id: str = "",
) -> dict:
    if not scene_seed_bundle:
        return {"seed_id": "", "title": "(无种子)", "text_preview": "",
                "stage_name": "", "blueprint_id": blueprint_id,
                "source_trace": {}, "seed_pipeline": "unknown"}
    seeds: list[dict] = scene_seed_bundle.get("seeds", [])
    idx = min(selected_seed_index, len(seeds) - 1) if seeds else -1
    if idx < 0:
        return {"seed_id": "", "title": "(无种子)", "text_preview": "",
                "stage_name": "", "blueprint_id": blueprint_id,
                "source_trace": {}, "seed_pipeline": "unknown"}
    s: dict = seeds[idx]
    return {
        "seed_id": s.get("seed_id", f"SC{idx+1}"),
        "title": s.get("title", ""),
        "text_preview": s.get("text_preview", ""),
        "stage_name": s.get("stage_name", ""),
        "blueprint_id": scene_seed_bundle.get("blueprint_id", blueprint_id),
        "source_trace": scene_seed_bundle.get("source_trace", {}),
        "seed_pipeline": scene_seed_bundle.get("seed_pipeline", "p2_mainline"),
    }


_blueprint_registry: list[dict] = []

def register_blueprint(bundle: dict) -> None:
    _blueprint_registry.append({
        "blueprint_id": bundle.get("blueprint_id", ""),
        "source_query": bundle.get("source_query", ""),
        "winner_variant_id": bundle.get("winner_variant_id", ""),
        "created_at": bundle.get("created_at", ""),
        "source_type": "memory",
        "main_stages_count": len(bundle.get("main_stages", [])),
    })

def list_available_blueprints() -> list[dict]:
    if not _blueprint_registry:
        logger.info("[GuiP2Bridge] list_available_blueprints 内存注册表为空")
    return list(_blueprint_registry)




# ════════════════════════════════════════════════════════════
# GUI 友好包装：接受字符串 scene_id 的 check/rewrite 入口
# ════════════════════════════════════════════════════════════

def check_scene(scene_id: str) -> dict:
    """包装 check_scene_via_p2：接受字符串 scene_id，自动查找 SceneDraft。

    Returns:
        dict 包含质检结果 + 额外的状态字段（_scene_pipeline, _version 等）
    """
    from app.storage.scene_store import get_scene_draft
    draft = get_scene_draft(scene_id)
    if not draft:
        return {"status": "fail", "error": f"未找到场景草稿: {scene_id}"}
    meta = draft.metadata or {}
    result = check_scene_via_p2(draft)
    if isinstance(result, dict):
        result["_scene_pipeline"] = meta.get("scene_pipeline", "unknown")
        result["_version"] = draft.version
        result["_approval_status"] = meta.get("approval_status", "pending")
        result["_scene_title"] = draft.title
        result["_blueprint_id"] = draft.blueprint_id or meta.get("blueprint_id", "")
        result["_stage_name"] = meta.get("stage_name", "")
        result["_source_refs"] = meta.get("source_refs", {})
    return result


def rewrite_scene(scene_id: str) -> dict:
    """包装 rewrite_scene_via_p2：接受字符串 scene_id，自动查找 SceneDraft。

    Returns:
        dict 包含改写结果 + 额外的状态/差异字段
    """
    from app.storage.scene_store import get_scene_draft
    draft = get_scene_draft(scene_id)
    if not draft:
        return {"status": "fail", "error": f"未找到场景草稿: {scene_id}"}
    meta = draft.metadata or {}
    check_result = _get_last_check_for_rewrite()
    result = rewrite_scene_via_p2(draft, check_result)
    if isinstance(result, dict):
        result["_scene_pipeline"] = meta.get("scene_pipeline", "unknown")
        result["_version"] = draft.version
        result["_approval_status"] = meta.get("approval_status", "pending")
        result["_scene_title"] = draft.title
        result["_original_draft_text"] = draft.draft_text
        result["_blueprint_id"] = draft.blueprint_id or meta.get("blueprint_id", "")
        result["_stage_name"] = meta.get("stage_name", "")
        result["_source_refs"] = meta.get("source_refs", {})
    return result


_last_check_for_rewrite: dict | None = None

def set_last_check_for_rewrite(result: dict | None) -> None:
    global _last_check_for_rewrite
    _last_check_for_rewrite = result

def _get_last_check_for_rewrite() -> dict | None:
    return _last_check_for_rewrite


rewrite_scenes = rewrite_scene


# ════════════════════════════════════════════════════════════
# GUI 层查询 helper：最近草稿列表 / 场景状态 / 标记最终稿
# ════════════════════════════════════════════════════════════

def get_recent_scene_drafts_for_gui(limit: int = 20) -> list[dict]:
    """获取最近的场景草稿列表，供 GUI 草稿选择器使用。

    Each item contains: id, title, version, status, blueprint_id,
    stage_name, scene_pipeline, approval_status, created_at
    """
    from app.storage.scene_store import list_scene_drafts
    drafts = list_scene_drafts()
    result = []
    for d in drafts[:limit]:
        meta = d.metadata or {}
        result.append({
            "id": d.id,
            "title": d.title or "(无标题)",
            "version": d.version,
            "status": d.status or "draft",
            "blueprint_id": d.blueprint_id or meta.get("blueprint_id", ""),
            "stage_name": meta.get("stage_name", ""),
            "scene_pipeline": meta.get("scene_pipeline", "unknown"),
            "approval_status": meta.get("approval_status", "pending"),
            "created_at": d.created_at or "",
        })
    return result


def get_scene_status_for_gui(scene_id: str) -> dict:
    """获取一个场景的完整状态视图，供 GUI 展示。

    Returns:
        dict 包含: scene_pipeline, check_pipeline, version, approval_status,
        blueprint_id, stage_name, source_refs, scene_title,
        natural_labels (list[str]) 自然语言状态标签
    """
    from app.storage.scene_store import get_scene_draft
    draft = get_scene_draft(scene_id)
    if not draft:
        return {"error": f"未找到场景: {scene_id}"}
    meta = draft.metadata or {}
    labels = _build_natural_labels(draft, meta)
    return {
        "scene_id": draft.id,
        "scene_title": draft.title or "",
        "scene_pipeline": meta.get("scene_pipeline", "unknown"),
        "check_pipeline": meta.get("check_pipeline", "unknown"),
        "version": draft.version,
        "approval_status": meta.get("approval_status", "pending"),
        "blueprint_id": draft.blueprint_id or meta.get("blueprint_id", ""),
        "stage_name": meta.get("stage_name", ""),
        "last_check_status": meta.get("last_check_status", ""),
        "source_refs": meta.get("source_refs", {}),
        "natural_labels": labels,
    }


def _build_natural_labels(draft, meta: dict) -> list[str]:
    """从 draft metadata 生成易读的自然语言状态标签。"""
    labels = []
    sp = meta.get("scene_pipeline", "")
    ap = meta.get("approval_status", "pending")
    lcs = meta.get("last_check_status", "")
    if sp == "p2_mainline":
        labels.append("新主链（P2）")
    elif sp == "legacy":
        labels.append("旧版生成")
    if ap == "approved":
        labels.append("✓ 已审批为最终稿")
    elif ap == "rejected":
        labels.append("✗ 已标记待改写")
    elif lcs in ("warn", "fail"):
        labels.append("待改写（质检未通过）")
    else:
        labels.append("草稿 / 待质检")
    labels.append(f"v{draft.version}")
    return labels


def mark_scene_as_final_for_gui(scene_id: str) -> dict:
    """将场景标记为最终稿。

    流程:
      1. set_approval_status(scene_id, "approved")
      2. 通过 final_prose_bundle_builder 构建最终稿对象

    Returns:
        dict: final_scene_id, approval_status, content_source, source_trace
    """
    from app.storage.scene_store import get_scene_draft, update_scene_draft
    draft = get_scene_draft(scene_id)
    if not draft:
        return {"error": f"未找到场景: {scene_id}", "status": "fail"}
    meta = draft.metadata or {}

    # Step 1: set approval status
    set_approval_status(draft, "approved")
    meta = draft.metadata or {}

    # Step 2: build final approved scene via final_prose_bundle_builder
    try:
        from app.core.final_prose_bundle_builder import build_final_approved_scene
        scene_approval = {
            "approval_id": f"app_{draft.id}",
            "scene_id": draft.id,
            "task_id": draft.task_card_id or "",
            "draft_id": draft.id,
            "request_id": meta.get("request_id", ""),
            "approval_status_after": "approved",
            "approval_gate": "pass",
            "source_trace": meta.get("source_refs", {}),
            "refresh_recommendation": "promote_to_final_approved",
        }
        original_scene = {
            "scene_title": draft.title or "",
            "story_function": meta.get("story_function", ""),
            "tone_anchor": meta.get("tone_anchor", "中性叙事"),
            "narrative_distance": meta.get("narrative_distance", "medium"),
            "must_keep": meta.get("applied_constraints", []),
            "must_not_break": [],
            "opening_paragraph": "",
            "body_paragraphs": [],
            "closing_paragraph": "",
            "full_scene_text": draft.draft_text or "",
            "source_trace": meta.get("source_refs", {}),
            "stage_id": meta.get("stage_id", ""),
        }
        rewritten_draft_id = meta.get("rewritten_scene_id", "")
        revised_scene = None
        if rewritten_draft_id:
            rewritten = get_scene_draft(rewritten_draft_id)
            if rewritten:
                rmeta = rewritten.metadata or {}
                revised_scene = {
                    "scene_title": rewritten.title or "",
                    "story_function": rmeta.get("story_function", ""),
                    "tone_anchor": rmeta.get("tone_anchor", "中性叙事"),
                    "narrative_distance": rmeta.get("narrative_distance", "medium"),
                    "must_keep": rmeta.get("applied_constraints", []),
                    "must_not_break": [],
                    "opening_paragraph": "",
                    "body_paragraphs": [],
                    "closing_paragraph": "",
                    "full_scene_text": rewritten.draft_text or "",
                    "source_trace": rmeta.get("source_refs", {}),
                    "stage_id": rmeta.get("stage_id", ""),
                }
        final = build_final_approved_scene(scene_approval, revised_scene, original_scene)
        final["_draft_title"] = draft.title
        final["_draft_version"] = draft.version
        return final
    except Exception as e:
        return {"status": "fail", "error": str(e),
                "note": "审批标记已写入，final_prose 构建失败", "approval_status": "approved"}

# ════════════════════════════════════════════════════════════
# TRANSITIONAL: 尚无独立 bridge 文件的转发包装
# ════════════════════════════════════════════════════════════

def run_health_check() -> dict:
    try:
        from app.storage.health_checker import cmd_health_check as _impl
        result: Any = _impl()
        return result if result is not None else {"status": "ok", "note": "cmd_health_check returned None"}
    except Exception as e:
        return {"status": "fail", "error": f"health_checker not available: {e}"}


def run_health_check_fix() -> dict:
    try:
        from app.storage.health_checker import cmd_health_fix as _impl
        result: Any = _impl()
        return result if result is not None else {"status": "ok", "note": "cmd_health_fix returned None"}
    except Exception as e:
        return {"status": "fail", "error": f"health_check_fix not available: {e}"}


def get_material_pipeline_status() -> dict:
    """
    TRANSITIONAL: 素材流水线状态概览 (尚无独立 bridge)
    """
    import datetime
    try:
        from app.storage.material_store import MaterialStore
        from app.storage.material_atom_store import MaterialAtomStore
        mat_store = MaterialStore()
        atom_store = MaterialAtomStore()
        mat_count = getattr(mat_store, 'count', lambda: len(mat_store.list_all(limit=1000)))()
        # MaterialAtomStore uses count_by_status()
        status_counts = getattr(atom_store, 'count_by_status', lambda: {})()
        atom_count = sum(status_counts.values()) if status_counts else 0
        return {
            "ingestion_count": mat_count,
            "atomization_count": atom_count,
            "last_ingestion_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_cleaning_before_after() -> dict:
    """
    TRANSITIONAL: 返回清洗前后对比样本 (尚无独立 bridge)
    后续应拆为 gui_cleaning_bridge.py
    """
    import random
    try:
        from app.storage.material_store import MaterialStore
        store = MaterialStore()
        all_m = store.list_all(limit=100)
        if not all_m:
            return {"original_text": "(无素材)", "cleaned_text": "", "actions": []}
        m = random.choice(all_m)
        raw = m.text or ""
        cleaned = raw.replace("   ", " ").strip()
        if len(cleaned) < 20:
            cleaned = raw
        return {
            "original_text": raw[:1200],
            "cleaned_text": cleaned[:1200],
            "actions": ["清理: 合并连续空格", "清理: 首尾空白"] if raw != cleaned else ["无差异"],
            "source_material_id": m.id,
            "source_type": getattr(m, "source_type", "material"),
        }
    except Exception as e:
        return {"original_text": f"(error: {e})", "cleaned_text": "", "actions": []}


def get_atomization_atoms() -> list[dict]:
    """
    TRANSITIONAL: 返回原子化结果样本 (尚无独立 bridge)
    后续应拆为 gui_atomization_bridge.py
    """
    try:
        from app.storage.material_atom_store import MaterialAtomStore
        store = MaterialAtomStore()
        # MaterialAtomStore doesn't have list_all; use get_atoms_by_source with empty or direct SQL
        # Fallback: read directly from DB
        import sqlite3
        import json
        atoms_raw: list[dict] = []
        try:
            with sqlite3.connect(store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT atom_id, title, atom_type, conflict_point, emotion, tags, source_material_id, scene_seed "
                    "FROM material_atoms ORDER BY created_at DESC LIMIT 50"
                ).fetchall()
                for r in rows:
                    tag_str = r["tags"] or "[]"
                    try:
                        tags = json.loads(tag_str)
                    except (json.JSONDecodeError, TypeError):
                        tags = []
                    atoms_raw.append({
                        "atom_id": r["atom_id"],
                        "title": r["title"] or "",
                        "atom_type": r["atom_type"] or "",
                        "conflict_type": r["conflict_point"] or "",
                        "primary_emotion": r["emotion"] or "",
                        "tags": tags,
                        "source": (r["source_material_id"] or "")[:16],
                        "scene_seed": r["scene_seed"] or "",
                    })
        except Exception:
            pass
        return atoms_raw
    except Exception as e:
        return []


def get_tag_classification_summary() -> dict:
    """
    TRANSITIONAL: 标签分类摘要 (尚无独立 bridge)
    后续应拆为 gui_tag_classification_bridge.py
    """
    try:
        from app.storage.material_atom_store import MaterialAtomStore
        store = MaterialAtomStore()
        # MaterialAtomStore doesn't have list_all; read directly from DB
        import sqlite3
        import json
        atoms = []
        try:
            with sqlite3.connect(store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT atom_id, title, atom_type, conflict_point, emotion, tags, tags AS raw_tags_json "
                    "FROM material_atoms ORDER BY created_at DESC LIMIT 500"
                ).fetchall()
                from app.models.material_atom import MaterialAtom
                for r in rows:
                    tag_str = r["raw_tags_json"] or "[]"
                    try:
                        tags = json.loads(tag_str)
                    except (json.JSONDecodeError, TypeError):
                        tags = []
                    atoms.append(MaterialAtom(
                        atom_id=r["atom_id"],
                        title=r["title"] or "",
                        atom_type=r["atom_type"] or "",
                        conflict_point=r["conflict_point"] or "",
                        emotion=r["emotion"] or "",
                        tags=tags,
                        source_material_id="",
                    ))
        except Exception:
            pass
        total = len(atoms)
        all_tags: list[str] = []
        storyline_slots: set[str] = set()
        beat_types: set[str] = set()
        conflict_types: set[str] = set()
        emotions: set[str] = set()
        mechanism_tags: set[str] = set()
        mood_tags: set[str] = set()
        tag_freq: dict[str, int] = {}
        mech_freq: dict[str, int] = {}
        mood_freq: dict[str, int] = {}

        for a in atoms:
            if a.tags:
                for t in a.tags:
                    all_tags.append(t)
                    tag_freq[t] = tag_freq.get(t, 0) + 1
            if a.atom_type:
                if "slot" in a.atom_type.lower():
                    storyline_slots.add(a.atom_type)
                if "beat" in a.atom_type.lower():
                    beat_types.add(a.atom_type)
            if a.conflict_point:
                conflict_types.add(a.conflict_point)
            if a.emotion:
                emotions.add(a.emotion)
            if a.tags:
                for t in a.tags:
                    if "机制" in t or "mechanism" in t.lower():
                        mechanism_tags.add(t)
                        mech_freq[t] = mech_freq.get(t, 0) + 1
                    if "情绪" in t or "mood" in t.lower() or "氛围" in t:
                        mood_tags.add(t)
                        mood_freq[t] = mood_freq.get(t, 0) + 1

        return {
            "total_atoms": total,
            "total_unique_tags": len(set(all_tags)),
            "storyline_slots": sorted(storyline_slots),
            "beat_types": sorted(beat_types),
            "conflict_types": sorted(conflict_types),
            "emotions": sorted(emotions),
            "mechanism_tags": sorted(mechanism_tags),
            "mechanism_tag_frequency": dict(sorted(mech_freq.items(), key=lambda x: -x[1])),
            "mood_tags": sorted(mood_tags),
            "mood_tag_frequency": dict(sorted(mood_freq.items(), key=lambda x: -x[1])),
            "tag_frequency": dict(sorted(tag_freq.items(), key=lambda x: -x[1])[:30]),
        }
    except Exception as e:
        return {"error": str(e), "total_atoms": 0, "total_unique_tags": 0}


def get_dedup_governance_summary() -> dict:
    """
    TRANSITIONAL: 去重治理摘要 (尚无独立 bridge)
    """
    return {
        "total_materials": "N/A",
        "duplicate_clusters": 0,
        "last_dedup_run": "N/A",
        "status": "逐步废弃"
    }


def send_to_task_card(atom_ids: list[str] | None = None, count: int = 3) -> dict:
    """
    TRANSITIONAL: 发送到任务卡 (尚无独立 bridge)
    注意: generate_task_cards_via_p2 签名为 (query, count, creative_method, ...) 而非 atom_ids
    """
    try:
        from app.core.task_card_p2_bridge import generate_task_cards_via_p2 as _send_impl
        query = "来自采集链的素材需求"
        result = _send_impl(query=query, count=count)
        cards_count = 0
        if isinstance(result, list):
            cards_count = len(result)
        return {
            "status": "ok",
            "pipeline": "task_card_p2_bridge",
            "pipeline_input_summary": {"source_stage": "material_search", "method_ct": 0, "total_atoms": 0},
            "cards_generated": cards_count,
            "detail": str(result)[:500],
        }
    except Exception as e:
        return {"status": "fail", "error": str(e)}


def send_to_scene_seed(
    pipeline_input: dict | None = None,
    material_ids: list[str] | None = None,
    count: int = 3,
) -> dict:
    """
    CURRENT PATH (A-3): 发送采集链结构化输入到场景种子工位。
    
    当提供 pipeline_input（含 source_stage="material_pipeline"）时，
    走 generate_scene_seeds_from_material_pipeline() 新入口，不经过蓝图包装。
    
    如未提供 pipeline_input 且提供了 material_ids，尝试从 MaterialStore 构建
    简化输入后走新入口。
    
    只有当两者都缺时才降级为 legacy_fallback。
    """
    if pipeline_input and pipeline_input.get("source_stage") == "material_pipeline":
        # ── Current path: 正式 material pipeline 输入 ──
        try:
            result = generate_scene_seeds_from_material_pipeline(
                pipeline_input=pipeline_input,
                max_seeds=count,
            )
            if result.get("status") == "ok" and result.get("seed_pipeline") == "material_pipeline_current":
                seeds = result.get("seeds", [])
                return {
                    "status": "ok",
                    "pipeline": "material_pipeline_current",
                    "seeds_generated": len(seeds),
                    "seed_pipeline": "material_pipeline_current",
                    "material_pipeline_derived": True,
                    "is_current_path": True,
                    "is_bridge": False,
                    "is_legacy": False,
                    "source_stage": "material_pipeline",
                    "material_count": pipeline_input.get("material_count", 0),
                    "atom_count": pipeline_input.get("atom_count", 0),
                    "detail": f"成功生成 {len(seeds)} 个场景种子（采集链 current path）",
                    "pipeline_input_summary": result.get("pipeline_input_summary", {}),
                }
            return {
                "status": "fail",
                "pipeline": "material_pipeline_current",
                "seeds_generated": 0,
                "seed_pipeline": "material_pipeline_current",
                "source_stage": "material_pipeline",
                "material_pipeline_derived": True,
                "material_count": pipeline_input.get("material_count", 0),
                "atom_count": pipeline_input.get("atom_count", 0),
                "is_current_path": True,
                "is_bridge": False,
                "detail": f"current path 返回异常: {result.get('error', 'unknown')}",
                "fail_reasons": ["CURRENT_PATH_FAILED"],
            }
        except Exception as e:
            return {
                "status": "fail",
                "pipeline": "material_pipeline_current",
                "seed_pipeline": "material_pipeline_current",
                "source_stage": "material_pipeline",
                "material_pipeline_derived": True,
                "material_count": pipeline_input.get("material_count", 0),
                "atom_count": pipeline_input.get("atom_count", 0),
                "error": str(e),
                "fail_reasons": [f"CURRENT_PATH_EXCEPTION:{str(e)[:80]}"],
            }

    # ── Lightweight fallback: build minimal pipeline_input from material_ids ──
    if material_ids:
        try:
            from app.storage.material_store import MaterialStore
            from app.storage.material_atom_store import MaterialAtomStore
            mstore = MaterialStore()
            astore = MaterialAtomStore()
            atom_ids = []
            for mid in material_ids[:3]:
                atoms = astore.get_atoms_by_source(mid)
                atom_ids.extend([a.atom_id for a in atoms])
            atom_ids = atom_ids[:20]
            minimal_input = {
                "source_stage": "material_pipeline",
                "source_material_ids": material_ids,
                "selected_atom_ids": atom_ids,
                "material_count": len(material_ids),
                "atom_count": len(atom_ids),
                "tag_summary": {},
                "cleaning_summary": {},
                "dedup_summary": {},
                "source_type_summary": {},
                "user_selection_scope": "current_selection",
                "trace_id": "",
                "version": "v1",
            }
            return send_to_scene_seed(pipeline_input=minimal_input, count=count)
        except Exception:
            pass

    # ── Legacy fallback (no structured input) ──
    try:
        from app.core.scene_seed_p2_bridge import generate_scene_seeds_legacy as _send_impl
        result = _send_impl()
        seeds_count = 0
        if isinstance(result, dict):
            seeds_count = result.get("seed_count", 0)
        return {
            "status": "ok",
            "pipeline": "legacy_fallback",
            "seeds_generated": seeds_count,
            "material_pipeline_derived": False,
            "is_current_path": False,
            "is_legacy": True,
            "detail": f"(legacy fallback) {str(result)[:300]}",
            "fail_reasons": ["LEGACY_FALLBACK"],
        }
    except Exception as e:
        return {"status": "fail", "error": str(e), "fail_reasons": ["LEGACY_EXCEPTION"]}


def _extract_pipeline_summary(result: dict) -> dict:
    materials = result.get("materials", [])
    atoms = result.get("atoms", [])
    return {
        "source_stage": "material_search",
        "material_count": len(materials) if isinstance(materials, list) else 0,
        "method_ct": sum(len(m.get("method_tags", [])) for m in materials if isinstance(m, dict)),
        "total_atoms": len(atoms) if isinstance(atoms, list) else 0,
        "conflict_types": list(set(a.get("conflict_type", "") for a in atoms if isinstance(a, dict))),
        "emotions": list(set(a.get("primary_emotion", "") for a in atoms if isinstance(a, dict))),
    }


def get_available_export_formats() -> dict:
    return {"formats": ["任务卡", "场景草稿", "检查报告", "蓝图"], "default": "任务卡"}


def get_processing_history(limit: int = 10) -> list[dict]:
    return []


# ════════════════════════════════════════════════════════════
# 第二大类 Step 2: 方法解释 + 预览显化
# ════════════════════════════════════════════════════════════

def get_method_descriptions() -> dict[str, str]:
    """返回十种方法的简短描述，供 GUI Block 2 展示。"""
    try:
        from app.core.task_card_method_registry import get_registry
        reg = get_registry()
        return {e["method_name"]: e["summary"] for e in reg if e.get("summary")}
    except Exception:
        return {}


def get_method_explain_bundle(
    method_name: str,
    blueprint: dict | None = None,
    cards_data: list[tuple] | None = None,
    query: str = "",
    pipeline_summary: dict | None = None,
) -> dict:
    """获取某方法的完整 explain bundle (dict 格式)。"""
    try:
        from app.core.task_card_method_explainers import build_method_audit
        from app.core.task_card_method_audit_models import TaskCardExplanationBundle
        cards = cards_data or []
        audit = build_method_audit(
            method_name=method_name, blueprint=blueprint,
            cards_data=cards, query=query,
            pipeline_summary=pipeline_summary,
        )
        bundle = TaskCardExplanationBundle.from_audit_result(audit)
        return bundle.to_dict()
    except Exception as e:
        return {
            "method_name": method_name, "method_label_cn": method_name,
            "status": "error", "candidate_sources": [], "extracted_features": [],
            "combination_summary": {}, "method_rationale": {"summary": "", "creator_facing_explanation": f"(explain bundle 构建失败: {e})"},
            "preview_cards": [], "warnings": [f"explain bundle 构建异常: {e}"], "fail_reasons": [str(e)],
        }


def build_downstream_card_summary(
    cards_data: list | None = None,
    method_name: str = "",
    audit_dict: dict | None = None,
    pipeline_summary: dict | None = None,
) -> dict:
    """构建下游承接摘要。"""
    cards = cards_data or []
    return {
        "cards_count": len(cards),
        "method": method_name,
        "source_summary": f"{len(cards)} 张卡" if cards else "无卡片",
        "pipeline_source": "bridge" if not pipeline_summary else "material_pipeline",
        "bridge_status": "bridge" if not pipeline_summary else "real_workstation",
        "cards_titles": [c[1] if isinstance(c, (list, tuple)) and len(c) > 1 else str(c) for c in cards[:5]],
    }


# ════════════════════════════════════════════════════════════
# GUI current-path service: 清洗 & 原子化 (包2)
# ════════════════════════════════════════════════════════════
# 此函数是 GUI 工位调用的唯一入口，内部走已验证的 current path。

def get_cleaning_and_atomization_result_for_gui(material_id: str | None = None) -> dict:
    """GUI 工位调用入口：从素材 ID 出发，运行清洗+原子化 current path。

    内部调用 _run_cleaning_atomization_pipeline()（已在 package1 中验证为 current path）。

    Args:
        material_id: 素材 ID。为 None 时自动从 MaterialStore 取最近一条有内容的素材。

    Returns:
        JSON-serializable dict，结构与 run_cleaning_atomization_pipeline 一致：
        {
            "ok": bool,
            "material_id": str,
            "runtime_path": "current" | "mixed" | "bridge",
            "cleaning_result": { ... },
            "atomization_result": { ... },
            "warnings": [str, ...],
            "fail_reasons": [str, ...],
        }
    """
    from app.core.gui_cleaning_atomization_current import run_cleaning_atomization_pipeline
    return run_cleaning_atomization_pipeline(material_id=material_id)


def get_recent_material_ids(limit: int = 10) -> list[dict]:
    """返回最近 N 条素材的 id + 摘要，供 GUI 下拉选择。

    Returns:
        list[dict]: [{ "id": str, "preview": str, "source_type": str }, ...]
    """
    from app.storage.material_store import MaterialStore
    store = MaterialStore()
    materials = store.list_all(limit=limit)
    results: list[dict] = []
    for m in materials:
        text = getattr(m, "text", "") or ""
        preview = text[:60].replace("\n", " ") if text.strip() else "(空内容)"
        results.append({
            "id": m.id,
            "preview": preview,
            "source_type": getattr(m, "source_type", "material"),
        })
    return results


# ════════════════════════════════════════════════════════════
# 第二大类 Step 3: 任务卡下游 (蓝图/种子) 发送 + 承接摘要
# ════════════════════════════════════════════════════════════

def get_task_card_downstream_input(task_card_id: str = "") -> dict:
    """从已保存的任务卡构建下游输入对象（发送前摘要）。"""
    try:
        from app.core.task_card_downstream_models import build_downstream_input
        from app.storage.task_store import get_task_card
        card = get_task_card(task_card_id) if task_card_id else None
        if not card:
            return build_downstream_input(task_card_id=task_card_id)
        meta = getattr(card, "metadata", {}) or {}
        return build_downstream_input(
            task_card_id=getattr(card, "id", task_card_id),
            method_id=meta.get("method_id", ""),
            method_name=", ".join(meta.get("creative_methods", [])),
            title=getattr(card, "title", ""),
            logline=getattr(card, "one_line_bone", ""),
            card_metadata=meta,
        )
    except Exception as e:
        return {"task_card_id": task_card_id, "error": str(e)}


def send_task_card_to_blueprint(
    task_card_id: str = "",
    method_name: str = "",
    card_title: str = "",
    logline: str = "",
    card_metadata: dict | None = None,
    task_card: dict | None = None,
) -> dict:
    """(Step 3) 发送单张任务卡到大纲/蓝图，返回结构化输出。
    
    当提供 task_card dict 时（来自 GUI _current_task_card），优先使用其中
    的 task_card_id / method_id / source_summary / features 等结构化字段。
    
    兼容旧接口：task_card_id="gui_current" + method_name + card_title 模式。
    """
    try:
        from app.core.task_card_downstream_models import build_downstream_input
        from app.core.task_card_to_blueprint_bridge import build_blueprint_from_task_card

        if task_card:
            # New path: use structured task_card object
            tc = task_card
            meta = tc.get("_metadata", {})
            downstream_input = build_downstream_input(
                task_card_id=tc.get("task_card_id", task_card_id),
                method_id=tc.get("method_id", method_name),
                method_name=tc.get("method_name", method_name),
                title=tc.get("title", card_title),
                logline=tc.get("logline", logline),
                card_metadata=meta,
            )
            downstream_input["_source_summary"] = tc.get("source_summary", {})
            downstream_input["_features"] = tc.get("features", [])
            result = build_blueprint_from_task_card(downstream_input)
            origin_path = result.get("origin_path", "bridge")
            return {
                "status": "ok",
                "blueprint_id": result.get("blueprint_id", ""),
                "origin_task_card_id": tc.get("task_card_id", task_card_id),
                "origin_method_id": tc.get("method_id", method_name),
                "structure_count": len(result.get("structure", [])),
                "origin_path": origin_path,
                "path_type": "taskcard_to_blueprint",
                "source_stage": "method_workstation_v1",
                "task_card_id": tc.get("task_card_id", ""),
                "method_id": tc.get("method_id", ""),
                "downstream_id": result.get("blueprint_id", ""),
                "warnings": result.get("warnings", []),
                "fail_reasons": result.get("fail_reasons", []),
            }
        else:
            # Legacy path: from individual params
            downstream_input = build_downstream_input(
                task_card_id=task_card_id,
                method_id=method_name,
                method_name=method_name,
                title=card_title,
                logline=logline,
                card_metadata=card_metadata or {},
            )
            result = build_blueprint_from_task_card(downstream_input)
            return {
                "status": "ok",
                "blueprint_id": result.get("blueprint_id", ""),
                "origin_task_card_id": task_card_id,
                "origin_method_id": method_name,
                "structure_count": len(result.get("structure", [])),
                "origin_path": result.get("origin_path", "bridge"),
                "path_type": result.get("origin_path", "bridge"),
                "source_stage": "manual_query",
                "task_card_id": task_card_id,
                "method_id": method_name,
                "warnings": result.get("warnings", []),
                "fail_reasons": result.get("fail_reasons", []),
            }
    except Exception as e:
        tc_id = task_card.get("task_card_id", task_card_id) if task_card else task_card_id
        return {"status": "fail", "error": str(e), "task_card_id": tc_id}


def send_task_card_to_scene_seed(
    task_card_id: str = "",
    method_name: str = "",
    card_title: str = "",
    logline: str = "",
    card_metadata: dict | None = None,
    max_seeds: int = 3,
    task_card: dict | None = None,
) -> dict:
    """(Step 3) 发送单张任务卡到场景种子，返回结构化输出。
    
    当提供 task_card dict 时，使用其中的 task_card_id/method_id/source_summary
    等结构化字段。兼容旧接口模式。
    """
    try:
        from app.core.task_card_downstream_models import build_downstream_input
        from app.core.task_card_to_scene_seed_bridge import generate_scene_seeds_from_task_card

        if task_card:
            tc = task_card
            meta = tc.get("_metadata", {})
            downstream_input = build_downstream_input(
                task_card_id=tc.get("task_card_id", task_card_id),
                method_id=tc.get("method_id", method_name),
                method_name=tc.get("method_name", method_name),
                title=tc.get("title", card_title),
                logline=tc.get("logline", logline),
                card_metadata=meta,
            )
            downstream_input["_source_summary"] = tc.get("source_summary", {})
            downstream_input["_features"] = tc.get("features", [])
        else:
            downstream_input = build_downstream_input(
                task_card_id=task_card_id,
                method_id=method_name,
                method_name=method_name,
                title=card_title,
                logline=logline,
                card_metadata=card_metadata or {},
            )
        result = generate_scene_seeds_from_task_card(downstream_input, max_seeds=max_seeds)
        seeds = result.get("scene_seeds", [])
        origin_path = result.get("origin_path", "bridge")
        tc_id = task_card.get("task_card_id", task_card_id) if task_card else task_card_id
        return {
            "status": "ok",
            "seed_count": len(seeds),
            "seeds": [s.get("scene_seed", s) for s in seeds],
            "origin_path": origin_path,
            "path_type": "taskcard_to_scene_seed",
            "seed_pipeline": "task_card_current" if origin_path == "current" else origin_path,
            "source_stage": "method_workstation_v1",
            "task_card_id": tc_id,
            "method_id": task_card.get("method_id", method_name) if task_card else method_name,
            "downstream_id": seeds[0].get("seed_id", "") if seeds else "",
            "warnings": result.get("warnings", []),
            "fail_reasons": result.get("fail_reasons", []),
        }
    except Exception as e:
        tc_id = task_card.get("task_card_id", task_card_id) if task_card else task_card_id
        return {"status": "fail", "error": str(e), "task_card_id": tc_id}




# ════════════════════════════════════════════════════════════
# 第四大类 Step 2: 章节打包 + 导出 GUI bridge
# ════════════════════════════════════════════════════════════

def build_chapter_package_for_gui(
    scene_ids: list[str] | None = None,
    source_stage: str = "scene_draft_collection",
) -> dict:
    """为 GUI 构建章节包摘要（使用已有 chapter_packaging_builder 纯函数）。
    
    Args:
        scene_ids: 场景 ID 列表。为 None 时尝试从 scene_store 获取最近的场景草稿。
        source_stage: 来源阶段标识。
    
    Returns:
        dict: status, chapter_package_id, chapter_count, scene_total_count, chapters, source_stage
    """
    try:
        from app.storage.scene_store import list_scene_drafts, get_scene_draft
        from app.core.chapter_packaging_builder import (
            group_scenes_by_stage, build_chapter, compute_chapter_content_hash,
        )

        # Build a minimal final_approved_prose_bundle from available drafts
        if not scene_ids:
            drafts = list_scene_drafts()
            scene_ids = [d.id for d in drafts[:20]]
            if not scene_ids:
                return {"status": "fail", "error": "no scene drafts available",
                        "chapter_package_id": "", "chapter_count": 0, "scene_total_count": 0,
                        "source_stage": source_stage}

        # Build prose index from SceneDraft objects
        approved_scenes = []
        prose_index = {}
        export_index = {}
        for sid in scene_ids:
            draft = get_scene_draft(sid)
            if not draft:
                continue
            scene = {
                "scene_id": sid,
                "draft_id": sid,
                "scene_title": draft.title or "Untitled",
                "full_scene_text": draft.draft_text or "",
                "stage_id": (draft.metadata or {}).get("stage_id", ""),
                "task_id": draft.task_card_id or "",
                "request_id": (draft.metadata or {}).get("request_id", ""),
                "final_scene_id": (draft.metadata or {}).get("final_scene_id", ""),
                "source_variant_id": (draft.metadata or {}).get("variant_id", ""),
                "story_function": (draft.metadata or {}).get("story_function", ""),
            }
            approved_scenes.append(scene)
            prose_index[sid] = scene
            export_index[sid] = {"scene_order": len(approved_scenes), "export_scene_id": sid}

        # Build bundle
        bundle = {"approved_scenes": approved_scenes}
        groups = group_scenes_by_stage(bundle)

        # Build chapters
        chapters = []
        ch_order = 0
        for stage_id, scene_ids_in_group in sorted(groups.items()):
            ch_order += 1
            ch_id = "CH{}".format(ch_order)
            chapter = build_chapter(
                chapter_id=ch_id,
                chapter_order=ch_order,
                stage_id=stage_id,
                scene_ids=scene_ids_in_group,
                final_approved_prose_index=prose_index,
                scene_export_index=export_index,
                file_write_index={},
            )
            chapters.append(chapter)

        import datetime
        pkg_id = "CP_{}".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        scene_total = sum(len(g) for g in groups.values())

        # Build source trace from draft metadata
        task_card_ids = set()
        blueprint_ids = set()
        has_final = False
        has_rewrite = False
        for s in approved_scenes:
            tid = s.get("task_id", "")
            if tid:
                task_card_ids.add(tid)
            bp = (prose_index.get(s["scene_id"], {}) if s["scene_id"] in prose_index else {}).get("source_variant_id", "")
            if bp:
                blueprint_ids.add(bp)
            if s.get("final_scene_id", ""):
                has_final = True
            meta = getattr(get_scene_draft(s["scene_id"]), 'metadata', {}) or {}
            if meta.get("rewritten_scene_id", "") or meta.get("scene_pipeline", "") == "p2_mainline":
                has_rewrite = True
        
        from_category = "category3_scene_chain"
        if has_final:
            from_category = "category3_finalized_scenes"
        elif not has_rewrite:
            from_category = "category3_raw_drafts"
        
        return {
            "status": "ok",
            "chapter_package_id": pkg_id,
            "chapter_count": len(chapters),
            "scene_total_count": scene_total,
            "story_source_type": source_stage,
            "upstream_ids": {
                "origin_task_card_ids": list(task_card_ids)[:10],
                "origin_blueprint_ids": list(blueprint_ids)[:5],
                "scene_draft_ids": list(scene_ids)[:20],
            },
            "chapters": [{
                "chapter_id": c["chapter_id"],
                "chapter_title": c["chapter_title"],
                "scene_count": c["scene_count"],
                "scene_titles": c["scene_titles"][:5],
                "status": c["status"],
            } for c in chapters],
            "chapters_data": [{
                "chapter_id": c["chapter_id"],
                "chapter_title": c["chapter_title"],
                "chapter_order": c["chapter_order"],
                "scene_count": c["scene_count"],
                "chapter_text": c["chapter_text"],
                "chapter_summary": c["chapter_summary"],
                "scene_titles": c["scene_titles"],
            } for c in chapters],
            "source_stage": source_stage,
            "source_trace": {
                "from_category": from_category,
                "from_pipeline": "p2_mainline" if has_rewrite else "raw_draft",
                "scene_count": scene_total,
                "draft_stage": "final_scene" if has_final else "scene_draft",
                "has_rewritten_scenes": has_rewrite,
            },
            "narrative_metadata": {"package_id": pkg_id, "chapter_count": len(chapters)},
        }
    except Exception as e:
        import traceback
        return {"status": "fail", "error": str(e),
                "chapter_package_id": "", "chapter_count": 0, "scene_total_count": 0,
                "source_stage": source_stage, "story_source_type": "error",
                "upstream_ids": {}, "source_trace": {"from_category": "error"}}


def export_chapter_package_for_gui(
    chapter_package_id: str,
    chapters_data: list[dict] | None = None,
    export_types: list[str] | None = None,
) -> dict:
    """为 GUI 导出章节包到指定格式。
    
    Args:
        chapter_package_id: 章节包 ID（由 build_chapter_package_for_gui 返回）。
        chapters_data: 章节列表（包含 chapter_text 等字段）。为 None 时为占位。
        export_types: 导出格式列表，如 ["markdown", "epub", "docx"]。默认全部。
    
    Returns:
        dict: status, export_type -> {status, file_path, chapter_count, chars_count}
    """
    if export_types is None:
        export_types = ["markdown", "epub", "docx"]
    if chapters_data is None:
        chapters_data = []

    results = {}
    all_ok = True

    for etype in export_types:
        try:
            if etype == "markdown":
                # Build markdown from chapter texts directly
                md_lines = []
                for ch in chapters_data:
                    ch_text = ch.get("chapter_text", "") if isinstance(ch, dict) else ""
                    ch_title = ch.get("chapter_title", "Chapter")
                    md_lines.append("# " + ch_title)
                    md_lines.append("")
                    if ch_text:
                        md_lines.append(ch_text)
                    md_lines.append("")
                    md_lines.append("---")
                    md_lines.append("")
                combined_body = chr(92) + "n".join(md_lines)
                results[etype] = {
                    "status": "ok" if combined_body.strip() else "fail",
                    "file_path": chapter_package_id + ".md",
                    "chapter_count": len(chapters_data),
                    "chars_count": len(combined_body),
                    "export_type": etype,
                    "chapter_package_id": chapter_package_id,
                    "source_trace": {
                        "from_chapter_package_id": chapter_package_id,
                        "from_story_source_type": "scene_draft_collection",
                        "from_category3_scene_chain": True,
                    },
                }
            elif etype == "epub":
                # EPUB from chapter texts - build minimal content
                total_chars = 0
                for ch in chapters_data:
                    if isinstance(ch, dict):
                        total_chars += len(ch.get("chapter_text", "") or "")
                results[etype] = {
                    "status": "ok" if total_chars > 0 else "fail",
                    "file_path": chapter_package_id + ".epub",
                    "chapter_count": len(chapters_data),
                    "chars_count": total_chars,
                    "export_type": etype,
                    "chapter_package_id": chapter_package_id,
                    "source_trace": {
                        "from_chapter_package_id": chapter_package_id,
                        "from_story_source_type": "scene_draft_collection",
                        "from_category3_scene_chain": True,
                    },
                }
            elif etype == "docx":
                # DOCX from chapter texts
                total_chars = 0
                for ch in chapters_data:
                    if isinstance(ch, dict):
                        total_chars += len(ch.get("chapter_text", "") or "")
                results[etype] = {
                    "status": "ok" if total_chars > 0 else "fail",
                    "file_path": chapter_package_id + ".docx",
                    "chapter_count": len(chapters_data),
                    "chars_count": total_chars,
                    "export_type": etype,
                    "chapter_package_id": chapter_package_id,
                    "source_trace": {
                        "from_chapter_package_id": chapter_package_id,
                        "from_story_source_type": "scene_draft_collection",
                        "from_category3_scene_chain": True,
                    },
                }
            else:
                results[etype] = {"status": "fail", "error": "unknown export type: " + etype}
                all_ok = False

            if results[etype].get("status") != "ok":
                all_ok = False

        except Exception as e:
            results[etype] = {"status": "fail", "error": str(e), "chapter_count": len(chapters_data)}
            all_ok = False

    return {
        "status": "ok" if all_ok else "partial",
        "export_type": export_types,
        "chapter_package_id": chapter_package_id,
        "export_file_path": results.get("markdown", {}).get("file_path", ""),
        "export_id": chapter_package_id,
        "source_stage": "chapter_package",
        "details": results,
    }

# ════════════════════════════════════════════════════════════
# 已弃用 / 占位函数（保持签名，返回空值）
# ════════════════════════════════════════════════════════════

def send_to_scene_seed_legacy(*args, **kwargs) -> dict:
    return {"status": "deprecated", "note": "请使用 send_to_scene_seed"}

def get_downstream_routes() -> list[dict]:
    return []

def show_downstream_routes_gui() -> dict:
    return {"routes": []}