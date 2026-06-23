"""
创作操作台 GUI — 阶段10 (Notion同步 + Reports + 一键流水线)
=============================================================

9个 Tab:
  1. 系统状态
  2. 素材检索
  3. 任务卡
  4. 场景扩写
  5. 质检与改写
  6. Obsidian 导出
  7. Notion 同步 (新增)
  8. Reports (新增)
  9. 一键流水线 (新增)

v10 改动:
  - Tab7: Notion 同步 (配置检查 + 单条同步 + 批量同步)
  - Tab8: Reports 面板，直接查看 JSON 验收报告
  - Tab9: 一键流水线 + 配置检查 (DeepSeek/Notion/FAISS/Obsidian)
  - Tab9: 一键备份 creative.db / materials.db
"""

from __future__ import annotations

import os
import sys
import json
import time
import traceback
import threading
import shutil
from datetime import datetime
from threading import Lock
from tkinter import ttk, messagebox, scrolledtext, StringVar, BooleanVar, Listbox, END
import tkinter as tk

# ── 确保能找到项目根目录 ──────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")


# ============================================================
# 工具函数
# ============================================================

def _trunc(text: str, n: int = 80) -> str:
    if not text:
        return ""
    text = str(text)
    return text[:n] + "..." if len(text) > n else text


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ============================================================
# 导入后端模块（延迟）
# ============================================================

_backend_imported = False


def _import_backend():
    """延迟导入所有后端模块。"""
    global MaterialStore, SearchEngine, VectorIndex, Embedder
    global SceneTaskCard, SceneDraft, SceneCheckReport, MainBlueprint
    global add_task_card, get_task_card, list_task_cards
    global add_scene_draft, get_scene_draft, list_scene_drafts
    global add_report, get_report, list_reports
    global generate_cards_from_query
    global write_scene
    global SceneChecker
    global rewrite_scene_from_check
    global export_task_card, export_scene_draft, export_check_report, export_blueprint
    global list_blueprints
    global has_api_key
    global NotionSync, get_tracking_stats
    global cmd_health_check
    global _backend_imported

    if _backend_imported:
        return
    _backend_imported = True

    from app.storage.health_checker import cmd_health_check

    from app.storage.material_store import MaterialStore
    from app.rag.search_engine import SearchEngine
    from app.core.vector_index import VectorIndex
    from app.core.embedder import Embedder
    from app.models.task_card import SceneTaskCard
    from app.models.scene_draft import SceneDraft
    from app.models.scene_check import SceneCheckReport
    from app.models.blueprint import MainBlueprint
    from app.storage.task_store import add_task_card, get_task_card, list_task_cards
    from app.storage.scene_store import add_scene_draft, get_scene_draft, list_scene_drafts
    from app.storage.scene_check_store import add_report, get_report, list_reports
    from app.core.nine_grid_engine import generate_cards_from_query
    from app.generation.scene_writer import write_scene
    from app.quality.scene_checker import SceneChecker
    from app.generation.scene_rewriter import rewrite_scene_from_check
    from app.integrations.obsidian_exporter import (
        export_task_card, export_scene_draft, export_check_report, export_blueprint,
    )
    from app.storage.blueprint_store import list_blueprints
    from app.generation.llm_client import has_api_key
    from app.integrations.notion_sync import NotionSync, get_tracking_stats


# ============================================================
# 配置检查辅助
# ============================================================

def _check_deepseek_config() -> dict:
    """检查 DeepSeek API Key 配置。"""
    import importlib
    llm_client = importlib.import_module("app.generation.llm_client")
    try:
        ok = llm_client.has_api_key()
        return {"ok": ok, "message": "found" if ok else "missing"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:60]}


def _check_notion_config() -> dict:
    """检查 Notion 配置（不调远程 API）。"""
    return NotionSync(dry_run=True).config_status


def _check_faiss_index() -> dict:
    """检查 FAISS 索引状态。"""
    try:
        from app.core.vector_index import VectorIndex
        vi = VectorIndex()
        loaded = vi.ensure_loaded()
        return {"ok": bool(loaded), "size": vi.size, "path": vi.index_path}
    except Exception as e:
        return {"ok": False, "size": 0, "error": str(e)[:60]}


def _check_obsidian_path() -> dict:
    """检查 Obsidian 导出目录是否存在。"""
    base = "H:\\10_Obsidian\\90_System\\04_方法论\\小说剧本创作大师_完整知识体系"
    subdirs = ["_任务卡库", "_场景草稿库", "_检查报告库"]
    exist = [d for d in subdirs if os.path.isdir(os.path.join(base, d))]
    return {"base": base, "subdirs_ok": len(exist) == len(subdirs), "existing": exist}


def _do_backup_db() -> dict:
    """备份 creative.db 和 materials.db 到 data/backups/ 目录。"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {}
    for db_name in ["creative.db", "materials.db"]:
        src = os.path.join(DATA_DIR, db_name)
        dst = os.path.join(BACKUP_DIR, f"{db_name.replace('.db','')}_{stamp}.db")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            results[db_name] = {"ok": True, "path": dst, "size_mb": round(os.path.getsize(dst) / 1024 / 1024, 2)}
        else:
            results[db_name] = {"ok": False, "path": "", "size_mb": 0}
    return results


# ============================================================
# 一键流水线
# ============================================================

def _run_one_click_pipeline(query: str, count: int, use_llm: bool,
                            progress_cb, log_cb) -> dict:
    """执行完整流水线: 检索 -> 生成任务卡 -> 扩写 -> 质检 -> 改写 -> 导出 -> 同步."""
    from app.rag.search_engine import SearchEngine
    from app.storage.material_store import MaterialStore
    from app.storage.task_store import add_task_card, get_task_card
    from app.core.nine_grid_engine import generate_cards_from_query
    from app.generation.scene_writer import write_scene
    from app.quality.scene_checker import SceneChecker
    from app.generation.scene_rewriter import rewrite_scene_from_check
    from app.storage.scene_check_store import add_report
    from app.integrations.obsidian_exporter import export_scene_draft, export_task_card

    result = {
        "search_count": 0,
        "cards_created": 0,
        "scenes_created": 0,
        "checks_created": 0,
        "rewrites_created": 0,
        "exports_success": 0,
        "notion_syncs": 0,
        "errors": [],
        "summary": {},
    }

    def progress(msg):
        if progress_cb:
            progress_cb(msg)

    def log(msg):
        if log_cb:
            log_cb(msg)

    # 1. 检索
    progress("step 1/7: 检索素材...")
    try:
        engine = SearchEngine()
        search_result = engine.search(query, k=count + 3)
        result["search_count"] = len(search_result.results)
        log(f"搜索到 {len(search_result.results)} 条素材")
    except Exception as e:
        result["errors"].append(f"search: {str(e)[:60]}")
        log(f"检索失败: {str(e)[:60]}")
        return result

    # 2. 生成任务卡
    progress("step 2/7: 生成任务卡...")
    card_ids = []
    try:
        store = MaterialStore()
        cards = generate_cards_from_query(
            search_engine=engine, query=query, count=count, store=store)
        saved_ids = []
        for card in cards:
            cid = add_task_card(card)
            saved_ids.append(cid)
        card_ids = saved_ids
        result["cards_created"] = len(card_ids)
        log(f"生成了 {len(card_ids)} 张任务卡")
    except Exception as e:
        result["errors"].append(f"generate_cards: {str(e)[:60]}")
        log(f"生成任务卡失败: {str(e)[:60]}")
        return result

    # 3. 扩写场景
    progress("step 3/7: 扩写场景...")
    scene_ids = []
    try:
        for i, cid in enumerate(card_ids):
            card = get_task_card(cid)
            if not card:
                continue
            draft = write_scene(
                task_card=card,
                draft_type="novel",
                use_llm=use_llm,
                top_k=min(count, 3),
                save=True,
            )
            scene_ids.append(draft.id)
            log(f"场景 [{i+1}/{len(card_ids)}]: {_trunc(draft.title, 30)} ({len(draft.draft_text)}字)")
        result["scenes_created"] = len(scene_ids)
    except Exception as e:
        result["errors"].append(f"write_scene: {str(e)[:60]}")
        log(f"扩写场景失败: {str(e)[:60]}")

    # 4. 质检
    progress("step 4/7: AI 质检...")
    check_ids = []
    try:
        checker = SceneChecker(use_llm=use_llm)
        for i, sid in enumerate(scene_ids):
            draft = get_scene_draft(sid)
            if not draft:
                continue
            card = get_task_card(draft.task_card_id) if draft.task_card_id else None
            report = checker.check(draft, card)
            cid = add_report(report)
            check_ids.append(cid)
            log(f"质检 [{i+1}/{len(scene_ids)}]: AI感={report.ai_feel_score} 现实={report.reality_grain_score}")
        result["checks_created"] = len(check_ids)
    except Exception as e:
        result["errors"].append(f"check: {str(e)[:60]}")
        log(f"质检失败: {str(e)[:60]}")

    # 5. 改写
    progress("step 5/7: 场景改写...")
    rewrite_ids = []
    try:
        for i, sid in enumerate(scene_ids):
            if i >= len(check_ids):
                continue
            report = get_report(check_ids[i])
            if not report:
                continue
            revised = rewrite_scene_from_check(
                scene_id=sid, check_report=report,
                draft_type="novel", use_llm=use_llm, save=True)
            rewrite_ids.append(revised.id)
            log(f"改写 [{i+1}/{len(scene_ids)}]: v{revised.version} {len(revised.revision_notes)}修改")
        result["rewrites_created"] = len(rewrite_ids)
    except Exception as e:
        result["errors"].append(f"rewrite: {str(e)[:60]}")
        log(f"改写失败: {str(e)[:60]}")

    # 6. 导出 Obsidian
    progress("step 6/7: 导出 Obsidian...")
    export_count = 0
    try:
        for i, sid in enumerate(scene_ids):
            draft = get_scene_draft(sid)
            if draft:
                export_scene_draft(draft)
                export_count += 1
            if i < len(card_ids):
                card = get_task_card(card_ids[i])
                if card:
                    export_task_card(card)
                    export_count += 1
        result["exports_success"] = export_count
        log(f"导出 {export_count} 个文件到 Obsidian")
    except Exception as e:
        result["errors"].append(f"export: {str(e)[:60]}")
        log(f"导出失败: {str(e)[:60]}")

    # 7. Notion 同步
    progress("step 7/7: 同步 Notion...")
    sync_count = 0
    try:
        sync = NotionSync(dry_run=False)
        if sync.config_status.get("_all_ok"):
            for cid in card_ids:
                if sync.sync_task_card(cid):
                    sync_count += 1
            for sid in scene_ids:
                if sync.sync_scene_draft(sid):
                    sync_count += 1
            for cid in check_ids:
                if sync.sync_check_report(cid):
                    sync_count += 1
        else:
            log("Notion 未配置, 跳过同步")
        result["notion_syncs"] = sync_count
        log(f"Notion 同步 {sync_count} pages")
    except Exception as e:
        result["errors"].append(f"notion_sync: {str(e)[:60]}")
        log(f"Notion 同步失败: {str(e)[:60]}")

    # summary
    result["summary"] = {
        "cards": result["cards_created"],
        "scenes": result["scenes_created"],
        "checks": result["checks_created"],
        "rewrites": result["rewrites_created"],
        "exports": result["exports_success"],
        "notion": result["notion_syncs"],
        "errors": len(result["errors"]),
    }

    progress(f"流水线完成: {result['summary']}")
    return result


# ============================================================
# 主 GUI 类
# ============================================================

class CreativeStudioGUI:
    """创作操作台主窗口"""

    MAX_LOG_LINES = 100

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("小说剧本创作自动化系统 - 创作操作台 v10")
        self.root.geometry("1080x880")
        self.root.minsize(800, 640)

        # 后端状态
        self._backend_loaded = False
        self._api_key_status = "unknown"

        # 运行任务追踪
        self._running_tasks = set()
        self._task_lock = Lock()

        # 状态栏变量
        self.status_var = StringVar(value="正在加载后端模块...")
        self.task_var = StringVar(value="")
        self.duration_var = StringVar(value="")
        self.result_var = StringVar(value="")
        self.api_key_var = StringVar(value="API: ?")

        # 日志
        self._log_lines = []
        self._object_cache = {}

        # 构建 UI
        self._build_ui()

        # 异步加载后端
        self._load_backend_async()

    # ── 日志 ──────────────────────────────────────────────

    def _log(self, msg: str):
        stamp = _now_str()
        line = f"[{stamp}] {msg}"
        self._log_lines.append(line)
        if len(self._log_lines) > self.MAX_LOG_LINES:
            self._log_lines.pop(0)
        if hasattr(self, 'log_text') and self.log_text:
            self.root.after(0, lambda: self._update_log_display())

    def _update_log_display(self):
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", "\n".join(self._log_lines))
        self.log_text.see(tk.END)

    def _clear_log(self):
        self._log_lines.clear()
        self.log_text.delete("1.0", tk.END)

    # ── 运行任务管理器 ────────────────────────────────────

    def _task_begin(self, task_id: str) -> bool:
        with self._task_lock:
            if task_id in self._running_tasks:
                return False
            self._running_tasks.add(task_id)
        return True

    def _task_end(self, task_id: str):
        with self._task_lock:
            self._running_tasks.discard(task_id)

    # ── 状态栏更新 ───────────────────────────────────────

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_task(self, text: str):
        self.task_var.set(text)

    def _set_duration(self, sec: float):
        self.duration_var.set(f"{sec:.1f}s")

    def _set_result(self, ok: bool, obj_id: str = ""):
        tag = "OK" if ok else "FAIL"
        self.result_var.set(f"{tag}" + (f" id={obj_id[:20]}..." if obj_id else ""))

    def _clear_status(self):
        self.task_var.set("")
        self.duration_var.set("")
        self.result_var.set("")

    # ── 进度条控制 ───────────────────────────────────────

    def _start_progress(self, msg: str = "处理中..."):
        self.progress_label.config(text=msg)
        self.progress_bar.start(15)

    def _stop_progress(self):
        self.progress_bar.stop()
        self.progress_label.config(text="")

    # ── UI 构建 ──────────────────────────────────────────

    def _build_ui(self):
        main_paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ---- 状态栏（顶部） ----
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=(4, 0))

        row1 = ttk.Frame(status_frame)
        row1.pack(fill=tk.X)
        ttk.Label(row1, textvariable=self.status_var,
                  font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(row1, textvariable=self.api_key_var,
                  font=("Segoe UI", 9), foreground="gray").pack(side=tk.RIGHT, padx=5)

        row2 = ttk.Frame(status_frame)
        row2.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(row2, textvariable=self.task_var, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        ttk.Label(row2, textvariable=self.duration_var, font=("Segoe UI", 9),
                  foreground="gray").pack(side=tk.LEFT, padx=10)
        ttk.Label(row2, textvariable=self.result_var, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

        # ---- Notebook (Tab 区) ----
        top_frame = ttk.Frame(main_paned)
        main_paned.add(top_frame, weight=3)

        self.notebook = ttk.Notebook(top_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # 原有 6 个 Tab
        self._build_tab1_stats()
        self._build_tab2_search()
        self._build_tab3_cards()
        self._build_tab4_scene()
        self._build_tab5_check()
        self._build_tab6_export()
        # 新增 3 个 Tab (阶段10)
        self._build_tab7_notion()
        self._build_tab8_reports()
        self._build_tab16_rag_eval()
        self._build_tab9_pipeline()
        
        self._build_tab11_scene_seed()
        self._build_tab20_chapter_export()

        # ---- 日志面板（底部） ----
        log_frame = ttk.Frame(main_paned)
        main_paned.add(log_frame, weight=1)

        log_header = ttk.Frame(log_frame)
        log_header.pack(fill=tk.X)
        ttk.Label(log_header, text="运行日志", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(log_header, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 9), height=8,
            bg="white", fg="black")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ---- 底部进度条 ----
        self.progress_frame = ttk.Frame(self.root)
        self.progress_frame.pack(fill=tk.X, padx=10, pady=(0, 6))
        self.progress_label = ttk.Label(self.progress_frame, text="")
        self.progress_label.pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="indeterminate", length=200)
        self.progress_bar.pack(side=tk.RIGHT, padx=5)

    # ── 后端加载 ─────────────────────────────────────────

    def _load_backend_async(self):
        def load():
            try:
                _import_backend()
                self._backend_loaded = True
                try:
                    self._api_key_status = "found" if has_api_key() else "missing"
                except Exception:
                    self._api_key_status = "missing"
                self.root.after(0, self._on_backend_loaded)
            except Exception as e:
                self.root.after(0, lambda: self._on_backend_error(str(e)))

        t = threading.Thread(target=load, daemon=True)
        t.start()

    def _on_backend_loaded(self):
        self._set_status("后端就绪")
        self.api_key_var.set(f"API: {self._api_key_status}")
        self._log(f"后端模块加载完成, API Key: {self._api_key_status}")
        self._refresh_stats()

    def _on_backend_error(self, msg):
        self._set_status(f"后端加载失败: {_trunc(msg, 60)}")
        self._log(f"后端加载失败: {msg}")
        messagebox.showerror("后端加载失败", f"请检查项目结构和依赖:\n\n{msg}")

    def _require_backend(self) -> bool:
        if not self._backend_loaded:
            messagebox.showwarning("提示", "后端模块正在加载中，请稍后")
            return False
        return True

    def _api_status_text(self) -> str:
        return f"API Key: {self._api_key_status}"

    # ── 错误处理 ──────────────────────────────────────────

    def _show_error(self, title: str, msg: str):
        self._stop_progress()
        from app.utils.error_reporter import build_error_payload, write_error_report
        payload = build_error_payload(
            Exception(msg), context=f"GUI::{title}", step=title,
            hint="GUI 后台任务失败，查看 reports/last_error_report.json 获取详细 traceback"
        )
        write_error_report(payload)
        self._log(f"FAIL {title} -> reports/last_error_report.json [{msg[:60]}]")
        messagebox.showerror(title, f"任务失败，详情见 reports/last_error_report.json")

    # ── Tab1: 系统状态 ──────────────────────────────────

    def _build_tab1_stats(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  系统状态  ")

        self.stats_text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10), height=30)
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="刷新统计", command=self._refresh_stats).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="健康检查", command=self._do_health_check).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="健康检查(--fix-safe)", command=self._do_health_check_fix).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="打开最近报告", command=self._open_health_report).pack(side=tk.LEFT, padx=5)

    def _refresh_stats(self):
        if not self._require_backend():
            return
        task_id = "refresh_stats"
        if not self._task_begin(task_id):
            return
        self._start_progress("加载统计...")
        self._set_task("正在加载系统统计")
        self._clear_status()

        def load():
            start_t = time.time()
            try:
                store = MaterialStore()
                mats = store.list_all()
                cards = list_task_cards()
                drafts = list_scene_drafts()
                reports = list_reports()
                index = VectorIndex()
                embedder = Embedder()
                bps = list_blueprints()

                api_status = self._api_key_status

                lines = []
                lines.append("=" * 50)
                lines.append("  小说剧本创作自动化系统 - 系统统计")
                lines.append("=" * 50)
                lines.append("")
                lines.append(f"  素材总数:       {len(mats)}")
                lines.append(f"  任务卡总数:     {len(cards)}")
                lines.append(f"  场景草稿总数:   {len(drafts)}")
                lines.append(f"  检查报告总数:   {len(reports)}")
                lines.append(f"  主线蓝图总数:   {len(bps)}")
                lines.append("")
                lines.append(f"  数据库路径:     {os.path.join(PROJECT_ROOT, 'data', 'materials.db')}")
                lines.append(f"  向量索引大小:   {index.size}")
                lines.append(f"  索引路径:       {index.index_path}")
                lines.append(f"  Embedding 模型: {embedder.model_name or '未加载'}")
                lines.append(f"  向量维度:       {embedder.dimension}")
                lines.append(f"  设备:           {embedder.device}")
                lines.append(f"  DeepSeek Key:   {api_status}")
                lines.append("")
                lines.append("  Obsidian 根目录: H:\\10_Obsidian\\90_System\\04_方法论\\小说剧本创作大师_完整知识体系")
                lines.append("")

                categories = {}
                for m in mats:
                    raw_cat = m.category or "未分类"
                    if hasattr(raw_cat, 'value'):
                        cat = raw_cat.value
                    else:
                        cat = raw_cat
                    categories[cat] = categories.get(cat, 0) + 1
                if categories:
                    lines.append("  分类分布:")
                    for cat, cnt in sorted(categories.items()):
                        lines.append(f"    {cat:18s}: {cnt}")
                lines.append("")
                lines.append("=" * 50)

                text = "\n".join(lines)
                dur = time.time() - start_t
                self.root.after(0, lambda: self._display_stats(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True))
                self.root.after(0, lambda: self._set_task("系统统计已刷新"))
                self._log(f"系统统计刷新完成 ({len(mats)} 素材, {len(cards)} 任务卡, {dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._show_error("统计失败", str(e)))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"系统统计刷新失败: {e}")
            finally:
                self._task_end(task_id)
                self.root.after(0, self._stop_progress)

        threading.Thread(target=load, daemon=True).start()

    def _display_stats(self, text: str):
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.insert("1.0", text)

    # ── 健康检查（Tab1 按钮） ──────────────────────────────

    def _do_health_check(self):
        if not self._task_begin("health_check"):
            return
        self._start_progress("运行健康检查...")
        self._set_task("health-check")
        self._log("启动健康检查...")

        def run():
            start_t = time.time()
            try:
                cmd_health_check()
                dur = time.time() - start_t
                report_path = os.path.join(REPORTS_DIR, "health_check_report.json")
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True))
                self._log(f"健康检查完成 ({dur:.1f}s) -> {report_path}")
                # 刷新报告列表
                if hasattr(self, '_refresh_report_list'):
                    self.root.after(0, self._refresh_report_list)
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"健康检查失败: {e}")
            finally:
                self._task_end("health_check")
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _do_health_check_fix(self):
        """health-check --fix-safe"""
        if not self._task_begin("health_check_fix"):
            return
        self._start_progress("运行健康检查(--fix-safe)...")
        self._set_task("health-check --fix-safe")
        self._log("启动健康检查(--fix-safe)...")

        def run():
            start_t = time.time()
            try:
                import argparse
                sys.argv = ["health-check", "--fix-safe"]
                cmd_health_check()
                dur = time.time() - start_t
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True))
                self._log(f"健康检查(--fix-safe)完成 ({dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"健康检查(--fix-safe)失败: {e}")
            finally:
                self._task_end("health_check_fix")
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _open_health_report(self):
        """打开最近的健康检查报告。"""
        report_path = os.path.join(REPORTS_DIR, "health_check_report.json")
        if not os.path.exists(report_path):
            messagebox.showwarning("提示", "健康检查报告不存在，请先运行健康检查")
            return
        try:
            import subprocess
            if sys.platform == "win32":
                os.startfile(report_path)
            else:
                subprocess.call(["open" if sys.platform == "darwin" else "xdg-open", report_path])
            self._log(f"打开报告: {report_path}")
        except Exception as e:
            self._log(f"打开报告失败: {e}")

    # ── Tab2: 素材检索 ──────────────────────────────────

    def _build_tab2_search(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  素材检索  ")

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(top, text="查询:").pack(side=tk.LEFT)
        self.search_query = ttk.Entry(top, width=50)
        self.search_query.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Label(top, text="Top K:").pack(side=tk.LEFT, padx=(10, 0))
        self.search_topk = ttk.Spinbox(top, from_=1, to=20, width=5)
        self.search_topk.set(5)
        self.search_topk.pack(side=tk.LEFT, padx=5)
        self.search_btn = ttk.Button(top, text="检索", command=self._do_search)
        self.search_btn.pack(side=tk.LEFT, padx=5)

        # Advanced params
        ap = ttk.LabelFrame(frame, text="高级检索参数")
        ap.pack(fill=tk.X, padx=10, pady=2)
        r1 = ttk.Frame(ap)
        r1.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(r1, text="来源类型:").pack(side=tk.LEFT)
        self._src_type = ttk.Combobox(r1, width=12, values=["全部","text","obsidian","rss","file","batch"])
        self._src_type.set("全部")
        self._src_type.pack(side=tk.LEFT, padx=2)
        ttk.Label(r1, text="重排模式:").pack(side=tk.LEFT, padx=(5,0))
        self._rerank_mode = ttk.Combobox(r1, width=10, values=["none","mmr","rrf"])
        self._rerank_mode.set("none")
        self._rerank_mode.pack(side=tk.LEFT, padx=2)
        r2 = ttk.Frame(ap)
        r2.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(r2, text="严格筛选:").pack(side=tk.LEFT)
        self._strict_var = tk.StringVar(value='{"status": "active"}')
        e1 = ttk.Entry(r2, width=20, textvariable=self._strict_var)
        e1.pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="示例", command=lambda: self._strict_var.set('{"status": "active", "source_type": "rss"}')).pack(side=tk.LEFT)
        ttk.Label(r2, text="软偏好:").pack(side=tk.LEFT, padx=(5,0))
        self._soft_var = tk.StringVar(value='{"tone": "叙事"}')
        e2 = ttk.Entry(r2, width=20, textvariable=self._soft_var)
        e2.pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="示例", command=lambda: self._soft_var.set('{"tone": "叙事", "style": "轻松"}')).pack(side=tk.LEFT)
        ttk.Label(ap, text="参数说明: source_type / strict_filters 影响素材召回与过滤；soft_preferences / rerank_mode 影响排序偏好与重排方式。结果去向: 当前检索结果可发送到任务卡、场景种子继续创作链路。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=4, pady=1)
        
        # Eval button
        ef = ttk.Frame(frame)
        ef.pack(fill=tk.X, padx=10, pady=2)
        ttk.Button(ef, text="打开检索评估", command=self._go_to_eval_tab).pack(side=tk.LEFT)
        self._eval_btn = ttk.Button(ef, text="→ 执行检索+评估", command=self._do_search_and_eval)
        self._eval_btn.pack(side=tk.LEFT, padx=4)
        
        # World pack readonly entry
        wf = ttk.LabelFrame(frame, text="世界观包")
        wf.pack(fill=tk.X, padx=10, pady=2)
        wi = ttk.Frame(wf)
        wi.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(wi, text="选择世界观包:").pack(side=tk.LEFT)
        self._wp_combo = ttk.Combobox(wi, width=20, values=["未启用", "默认世界", "科幻世界", "奇幻世界"])
        self._wp_combo.set("未启用")
        self._wp_combo.pack(side=tk.LEFT, padx=2)
        ttk.Button(wi, text="应用", command=self._apply_world_pack).pack(side=tk.LEFT, padx=2)
        ttk.Button(wi, text="说明", command=lambda: self._log("[wp] 世界观包用于限定检索世界范围，并影响后续 RAG 引用的背景素材。")).pack(side=tk.LEFT, padx=2)
        ttk.Label(wi, text="用于限定检索世界范围，影响后续 RAG 引用。", font=("Segoe UI", 8), foreground="#888").pack(side=tk.LEFT, padx=10)
        
        # Narrative metadata summary
        nf = ttk.LabelFrame(frame, text="叙事元数据摘要")
        nf.pack(fill=tk.X, padx=10, pady=2)
        ni = ttk.Frame(nf)
        ni.pack(fill=tk.X, padx=4, pady=2)
        try:
            from app.core.narrative_metadata_schema import NARRATIVE_METADATA_FIELDS
            # Pick 4-6 user-friendly fields
            pick = ["theme", "tone", "setting", "conflict_type", "character_focus", "time_scope"]
            row_f = ttk.Frame(ni)
            row_f.pack(fill=tk.X)
            j = 0
            for fdef in NARRATIVE_METADATA_FIELDS:
                fname = fdef.get("name", fdef.get("field_name", ""))
                if fname in pick:
                    cn = fdef.get("label_cn", fdef.get("label", fname))
                    desc = fdef.get("description", "")
                    lbl = ttk.Label(row_f, text=cn + ": (待采集)", font=("Segoe UI", 9), wraplength=250)
                    lbl.grid(row=j//2, column=(j%2)*2, sticky=tk.W, padx=4, pady=1)
                    if desc:
                        ttk.Label(row_f, text=desc[:40], font=("Segoe UI", 7), foreground="#999").grid(row=j//2, column=(j%2)*2+1, sticky=tk.W, padx=2)
                    j += 1
        except Exception:
            ttk.Label(ni, text="(元数据加载中...)").pack(anchor=tk.W)
        ttk.Label(nf, text="这些元数据会被后续检索、原子筛选和 RAG 过程引用。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=4, pady=1)
        
        self.search_result = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10), height=22)
        self.search_result.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def _do_search(self):
        if not self._require_backend():
            return
        query = self.search_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入查询内容")
            return
        try:
            top_k = int(self.search_topk.get())
        except ValueError:
            top_k = 5

        task_id = "search"
        if not self._task_begin(task_id):
            return

        self.search_btn.config(state=tk.DISABLED)
        self._start_progress("正在检索素材...")
        self._set_task(f"检索: {_trunc(query, 40)}")
        self._clear_status()
        self._log(f"开始检索: '{query}' (top_k={top_k})")

        def search():
            start_t = time.time()
            try:
                engine = SearchEngine()
                result = engine.search(query, k=top_k)
                lines = []
                lines.append(f"=== 检索结果: '{query}' ({len(result.results)} 条) ===\n")
                for i, r in enumerate(result.results, 1):
                    lines.append(f"[{i}] 评分: {r.score:.4f} | {r.category}")
                    lines.append(f"    标签: {' | '.join(r.tags)}")
                    lines.append(f"    摘要: {r.summary or r.text[:80]}")
                    lines.append(f"    场所: {r.location or '-'} | 机制: {r.mechanism or '-'}")
                    lines.append(f"    用途: {'; '.join(r.creative_use) if r.creative_use else '-'}")
                    lines.append(f"    ID: {r.id[:24]}...")
                    lines.append(f"    正文: {r.text[:200]}")
                    lines.append("")
                text = "\n".join(lines)
                dur = time.time() - start_t
                self.root.after(0, lambda: self._display_search_result(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True))
                self.root.after(0, lambda: self._set_task(f"检索完成: {len(result.results)} 条"))
                self._log(f"检索完成: '{query}' -> {len(result.results)} 条 ({dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._show_error("检索失败", str(e)))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"检索失败: {e}")
            finally:
                self._task_end(task_id)
                self.root.after(0, lambda: self.search_btn.config(state=tk.NORMAL))
                self.root.after(0, self._stop_progress)

        threading.Thread(target=search, daemon=True).start()

    def _display_search_result(self, text: str):
        self.search_result.delete("1.0", tk.END)
        self.search_result.insert("1.0", text)

    # ── Tab3: 任务卡 ────────────────────────────────────

    def _build_tab3_cards(self):
        """Task card method workstation."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  \u2462 \u4efb\u52a1\u5361  ")
        # Top: input + method selection
        top = ttk.LabelFrame(frame, text="\u521b\u4f5c\u9700\u6c42\u4e0e\u65b9\u6cd5\u9009\u62e9")
        top.pack(fill=tk.X, padx=8, pady=2)
        r0 = ttk.Frame(top)
        r0.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(r0, text="\u4efb\u52a1\u63cf\u8ff0:").pack(side=tk.LEFT)
        self.card_query = ttk.Entry(r0, width=40)
        self.card_query.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Label(r0, text="\u6570\u91cf:").pack(side=tk.LEFT, padx=(5,0))
        self.card_count = ttk.Spinbox(r0, from_=1, to=10, width=3)
        self.card_count.set(1)
        self.card_count.pack(side=tk.LEFT, padx=2)
        # Method selection
        mf = ttk.Frame(top)
        mf.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(mf, text="\u65b9\u6cd5:").pack(side=tk.LEFT)
        self._creative_method_var = tk.StringVar(value="\u4eba\u7269\u878d\u5408")
        main_methods = ["\u4eba\u7269\u878d\u5408","\u4e16\u754c\u89c2\u5bf9\u51b2","\u51b2\u7a81\u5347\u7ea7","\u65f6\u95f4\u7ebf\u4ea4\u9519","\u53cd\u8f6c\u63a8\u5bfc","\u60c5\u611f\u9006\u8f6c","\u573a\u666f\u9519\u4f4d","\u52a8\u673a\u7f6e\u6362"]
        for i, m in enumerate(main_methods):
            rb = ttk.Radiobutton(mf, text=m, variable=self._creative_method_var, value=m, command=self._on_method_change)
            rb.grid(row=0, column=i+1, sticky=tk.W, padx=1)
        exp_methods = ["\u56e0\u679c\u5012\u7f6e", "\u7c7b\u578b\u6df7\u5408"]
        ttk.Label(mf, text="  | \u5b9e\u9a8c:", font=("Segoe UI", 8), foreground="#999").grid(row=0, column=len(main_methods)+1)
        for j, m in enumerate(exp_methods):
            rb = ttk.Radiobutton(mf, text=m, variable=self._creative_method_var, value=m, command=self._on_method_change)
            rb.grid(row=0, column=len(main_methods)+2+j, sticky=tk.W, padx=1)
        ttk.Button(mf, text="\u751f\u6210\u4efb\u52a1\u5361", command=self._do_generate_cards, width=14).grid(row=0, column=len(main_methods)+4, padx=5)
        # Middle: method explain + source + steps (horizontal split)
        mid = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)
        # Left: explain + source + steps
        left_p = ttk.Frame(mid)
        mid.add(left_p, weight=1)
        # Method explain
        self._method_explain_label = ttk.LabelFrame(left_p, text="\u65b9\u6cd5\u8bf4\u660e")
        self._method_explain_label.pack(fill=tk.X)
        self._method_explain_text = ttk.Label(self._method_explain_label, text="(\u9009\u62e9\u65b9\u6cd5\u540e\u663e\u793a)", foreground="#888", wraplength=500, justify="left")
        self._method_explain_text.pack(anchor=tk.W, padx=4, pady=2)
        # Source preview
        self._source_frame = ttk.LabelFrame(left_p, text="\u5019\u9009\u6765\u6e90")
        self._source_frame.pack(fill=tk.X, pady=2)
        self._source_text = scrolledtext.ScrolledText(self._source_frame, wrap=tk.WORD, font=("Consolas", 9), height=4)
        self._source_text.pack(fill=tk.X, padx=4, pady=2)
        # Combination steps
        self._combo_frame = ttk.LabelFrame(left_p, text="\u7ec4\u5408\u6b65\u9aa4")
        self._combo_frame.pack(fill=tk.X, pady=2)
        self._combo_text = scrolledtext.ScrolledText(self._combo_frame, wrap=tk.WORD, font=("Consolas", 9), height=4)
        self._combo_text.pack(fill=tk.X, padx=4, pady=2)
        # Right: preview + why + downstream
        right_p = ttk.Frame(mid)
        mid.add(right_p, weight=1)
        # Preview
        self._preview_frame = ttk.LabelFrame(right_p, text="\u5019\u9009\u9884\u89c8")
        self._preview_frame.pack(fill=tk.BOTH, expand=True)
        self._preview_text = scrolledtext.ScrolledText(self._preview_frame, wrap=tk.WORD, font=("Consolas", 9), height=6)
        self._preview_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        # Why
        self._why_frame = ttk.LabelFrame(right_p, text="\u4e3a\u4ec0\u4e48\u662f\u8fd9\u5f20\u5361")
        self._why_frame.pack(fill=tk.X, pady=2)
        self._why_text = scrolledtext.ScrolledText(self._why_frame, wrap=tk.WORD, font=("Segoe UI", 9), height=3)
        self._why_text.pack(fill=tk.X, padx=4, pady=2)
        # Downstream
        self._ds_frame = ttk.LabelFrame(right_p, text="\u4e0b\u6e38\u627f\u63a5")
        self._ds_frame.pack(fill=tk.X, pady=2)
        dr = ttk.Frame(self._ds_frame)
        dr.pack(fill=tk.X, padx=2, pady=2)
        ttk.Button(dr, text="\u53d1\u9001\u5230\u573a\u666f\u79cd\u5b50", command=self._do_send_to_scene_seed, width=16).pack(side=tk.LEFT, padx=2)
        ttk.Button(dr, text="\u53d1\u9001\u5230\u84dd\u56fe", command=self._do_send_to_blueprint, width=16).pack(side=tk.LEFT, padx=2)
        self._ds_status = ttk.Label(self._ds_frame, text="", foreground="#888")
        self._ds_status.pack(anchor=tk.W, padx=4, pady=2)
        self._card_list = []
        # Initial load
        self._on_method_change()

    def _on_method_change(self):
        """Refresh method explain, source, combos, preview, why."""
        m = self._creative_method_var.get()
        try:
            from app.core.task_card_p2_bridge import build_method_detail_view
            mv = build_method_detail_view(m)
            # Explain
            parts = ["[" + m + "] " + str(mv.get("summary",""))]
            eff = mv.get("effect_summary","")
            if eff: parts.append("\u53c2\u6570\u5f71\u54cd: " + str(eff))
            if not mv.get("is_effective"):
                parts.append("[\u5b9e\u9a8c] \u5f53\u524d\u4e3a\u5360\u4f4d\u5c55\u793a\uff0c\u4e0d\u53c2\u4e0e\u4e3b\u94fe\u751f\u6210")
            self._method_explain_text.config(text=chr(10).join(parts), foreground="#c33" if not mv.get("is_effective") else "#333")
            # Source
            src = mv.get("candidate_source_preview", [])
            sl = []
            if src:
                groups = {}
                for p in src:
                    st = p.get("source_type","other")
                    if st not in groups: groups[st] = []
                    groups[st].append(p)
                for st_type, items in sorted(groups.items()):
                    sl.append("  " + st_type + " (" + str(len(items)) + "):")
                    for item in items[:3]:
                        sl.append("    " + str(item.get("title",""))[:40] + " | " + str(item.get("role",""))[:20])
            else:
                sl.append("(\u6682\u65e0\u6765\u6e90\u6570\u636e)")
            self._source_text.delete("1.0", "end")
            self._source_text.insert("1.0", chr(10).join(sl))
            # Steps
            steps = mv.get("combination_steps", [])
            stl = []
            for s in steps:
                prefix = "  [\u5b9e\u9a8c] " if not mv.get("is_effective") else "  "
                stl.append(prefix + str(s.get("step","")) + ". " + str(s.get("label","")) + " \u2014 " + str(s.get("description",""))[:80])
            self._combo_text.delete("1.0", "end")
            self._combo_text.insert("1.0", chr(10).join(stl) if stl else "(\u6682\u65e0\u6b65\u9aa4)")
        except Exception as e:
            self._method_explain_text.config(text="\u52a0\u8f7d\u5931\u8d25: " + str(e)[:40], foreground="red")

    def _do_generate_cards(self):
        """Generate task cards with current method, then update view."""
        self._log("[\u4efb\u52a1\u5361] \u751f\u6210...")
        m = self._creative_method_var.get()
        q = self.card_query.get().strip()
        try:
            cnt = int(self.card_count.get())
        except:
            cnt = 1
        try:
            from app.core.gui_p2_bridge_exports import generate_task_cards_with_audit_data, get_method_explain_bundle
            cards, audit = generate_task_cards_with_audit_data(query=q, count=cnt, creative_method=m, use_llm=False)
            bundle = get_method_explain_bundle(method_name=m, cards_data=cards, query=q)
            # Preview
            self._preview_text.delete("1.0", "end")
            pcs = bundle.get("preview_cards", [])
            if pcs:
                for i, p in enumerate(pcs[:5]):
                    self._preview_text.insert("end", "--- #" + str(i+1) + " ---\n")
                    self._preview_text.insert("end", "  \u6807\u9898: " + str(p.get("title",""))[:60] + "\n")
                    self._preview_text.insert("end", "  \u7c7b\u578b: " + str(p.get("card_type","")) + "\n")
                    self._preview_text.insert("end", "  \u6982\u8981: " + str(p.get("one_line_bone",""))[:80] + "\n")
                    if p.get("conflict_point"): self._preview_text.insert("end", "  \u51b2\u7a81: " + str(p["conflict_point"])[:60] + "\n")
                    if p.get("character_focus"): self._preview_text.insert("end", "  \u89d2\u8272: " + str(p["character_focus"])[:40] + "\n")
                    if p.get("tags"): self._preview_text.insert("end", "  \u6807\u7b7e: " + ", ".join(p["tags"][:6]) + "\n")
            else:
                self._preview_text.insert("end", "\n".join([str(c[1])[:60] + " [" + str(c[2]) + "]" for c in cards]))
            # Why
            self._why_text.delete("1.0", "end")
            r = bundle.get("method_rationale", "")
            if isinstance(r, dict): r = r.get("summary", r.get("creator_facing_explanation", ""))
            self._why_text.insert("end", str(r)[:300] + "\n")
            cs = bundle.get("combination_summary", {})
            if isinstance(cs, dict):
                if cs.get("description_cn"): self._why_text.insert("end", "\n\u8bf4\u660e: " + str(cs.get("description_cn","")) + "\n")
            # Store card for downstream
            self._current_task_card = {}
            if cards:
                c0 = cards[0]
                self._current_task_card = {"task_card_id": str(c0[0]), "method_id": m, "method_name": m, "title": str(c0[1]) if len(c0) > 1 else "", "source_summary": {"source_stage": "task_card_gui"}, "_metadata": audit if isinstance(audit, dict) else {}}
            self._log("[\u4efb\u52a1\u5361] \u751f\u6210\u5b8c\u6210: " + str(len(cards)) + " cards, method=" + m)
        except Exception as e:
            self._log("[\u4efb\u52a1\u5361] \u5931\u8d25: " + str(e))

    def _do_send_to_scene_seed(self):
        self._log("[\u4e0b\u6e38] \u53d1\u9001\u5230\u573a\u666f\u79cd\u5b50...")
        try:
            tc = getattr(self, '_current_task_card', None)
            if tc and tc.get("task_card_id") and tc["task_card_id"] != "gui_current":
                from app.core.gui_p2_bridge_exports import send_task_card_to_scene_seed
                r = send_task_card_to_scene_seed(task_card=tc, max_seeds=3)
                card_id = str(tc.get("task_card_id", ""))[:16]
                m = str(tc.get("method_id", ""))
            else:
                m = self._creative_method_var.get()
                from app.core.gui_p2_bridge_exports import send_task_card_to_scene_seed
                r = send_task_card_to_scene_seed(task_card_id="gui_current", method_name=m, card_title=self.card_query.get().strip() or "", max_seeds=3)
                card_id = "gui_current"
            self._ds_status.config(text="\u53d1\u9001\u5b8c\u6210: card=" + card_id + " method=" + m + " status=" + str(r.get("status","?")) + " seeds=" + str(r.get("seed_count",0)), foreground="#060")
        except Exception as e:
            self._ds_status.config(text="\u53d1\u9001\u5931\u8d25: " + str(e)[:40], foreground="red")

    def _do_send_to_blueprint(self):
        self._log("[\u4e0b\u6e38] \u53d1\u9001\u5230\u84dd\u56fe...")
        try:
            tc = getattr(self, '_current_task_card', None)
            if tc and tc.get("task_card_id") and tc["task_card_id"] != "gui_current":
                from app.core.gui_p2_bridge_exports import send_task_card_to_blueprint
                r = send_task_card_to_blueprint(task_card=tc)
                card_id = str(tc.get("task_card_id", ""))[:16]
                m = str(tc.get("method_id", ""))
            else:
                m = self._creative_method_var.get()
                from app.core.gui_p2_bridge_exports import send_task_card_to_blueprint
                r = send_task_card_to_blueprint(task_card_id="gui_current", method_name=m, card_title=self.card_query.get().strip() or "")
                card_id = "gui_current"
            self._ds_status.config(text="\u53d1\u9001\u5b8c\u6210: card=" + card_id + " method=" + m + " status=" + str(r.get("status","?")) + " bp=" + str(r.get("blueprint_id",""))[:16], foreground="#060")
        except Exception as e:
            self._ds_status.config(text="\u53d1\u9001\u5931\u8d25: " + str(e)[:40], foreground="red")

    def _build_tab4_scene(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  场景扩写  ")

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(top, text="选择任务卡:").pack(side=tk.LEFT)
        self.scene_card_combo = ttk.Combobox(top, width=50)
        self.scene_card_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.refresh_scene_cards_btn = ttk.Button(top, text="刷新列表",
                                                  command=self._refresh_scene_card_list)
        self.refresh_scene_cards_btn.pack(side=tk.LEFT, padx=5)

        self.scene_api_label = ttk.Label(top, text="", font=("Segoe UI", 9, "italic"),
                                         foreground="gray")
        self.scene_api_label.pack(side=tk.LEFT, padx=10)

        opts = ttk.Frame(frame)
        opts.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(opts, text="风格:").pack(side=tk.LEFT)
        self.scene_style = ttk.Combobox(opts, values=["novel", "screenplay", "outline"], width=10)
        self.scene_style.set("novel")
        self.scene_style.pack(side=tk.LEFT, padx=5)
        self.scene_use_llm = BooleanVar(value=False)
        ttk.Checkbutton(opts, text="use-llm (DeepSeek)", variable=self.scene_use_llm).pack(
            side=tk.LEFT, padx=5)
        ttk.Label(opts, text="Top K:").pack(side=tk.LEFT, padx=(10, 0))
        self.scene_topk = ttk.Spinbox(opts, from_=1, to=20, width=5)
        self.scene_topk.set(3)
        self.scene_topk.pack(side=tk.LEFT, padx=5)
        self.write_btn = ttk.Button(opts, text="扩写场景", command=self._do_write_scene)
        self.write_btn.pack(side=tk.LEFT, padx=10)

        self.scene_result = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10))
        self.scene_result.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._scene_card_map = {}
        self.root.after(500, self._refresh_scene_card_list)

    def _refresh_scene_card_list(self):
        if not self._backend_loaded:
            self.root.after(500, self._refresh_scene_card_list)
            return
        try:
            cards = list_task_cards()
            self._scene_card_map = {}
            items = []
            for c in cards:
                label = f"[{c.card_type.upper()}] {c.title[:50]}  ({c.id[:12]}...)"
                self._scene_card_map[label] = c.id
                items.append(label)
            self.scene_card_combo["values"] = items
            if items:
                self.scene_card_combo.set(items[0])
            self.scene_api_label.config(text=self._api_status_text())
        except Exception:
            pass

    def _do_write_scene(self):
        if not self._require_backend():
            return
        label = self.scene_card_combo.get()
        if not label or label not in self._scene_card_map:
            messagebox.showwarning("提示", "请选择一个任务卡")
            return
        card_id = self._scene_card_map[label]
        style = self.scene_style.get()
        use_llm = self.scene_use_llm.get()

        if use_llm and self._api_key_status != "found":
            self._log("API Key missing, 自动切换为 no-llm 模式")
            use_llm = False
            self.scene_use_llm.set(False)

        try:
            top_k = int(self.scene_topk.get())
        except ValueError:
            top_k = 3

        task_id = "write_scene"
        if not self._task_begin(task_id):
            return

        self.write_btn.config(state=tk.DISABLED)
        self.refresh_scene_cards_btn.config(state=tk.DISABLED)
        self._start_progress("正在扩写场景..." + (" (LLM)" if use_llm else " (no-llm)"))
        self._set_task(f"扩写场景: {_trunc(label, 40)}")
        self._clear_status()
        mode = "LLM" if use_llm else "no-llm"
        self._log(f"开始扩写场景: card={card_id[:16]}... style={style} mode={mode}")

        def write():
            start_t = time.time()
            try:
                card = get_task_card(card_id)
                if not card:
                    raise ValueError("任务卡未找到")
                draft = write_scene(
                    task_card=card,
                    draft_type=style,
                    use_llm=use_llm,
                    top_k=top_k,
                    save=True,
                )
                dur = time.time() - start_t
                llm_used = draft.metadata.get('llm_used', False)
                self.root.after(0, lambda: self._display_scene_result(draft))
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True, draft.id))
                self.root.after(0, lambda: self._set_task(f"场景扩写完成: {draft.title[:30]}"))
                self._log(f"场景扩写完成: id={draft.id[:16]}... llm={llm_used} "
                          f"len={len(draft.draft_text)} ({dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._show_error("扩写失败", str(e)))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"扩写场景失败: {e}")
            finally:
                self._task_end(task_id)
                self.root.after(0, lambda: self.write_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.refresh_scene_cards_btn.config(state=tk.NORMAL))
                self.root.after(0, self._stop_progress)

        threading.Thread(target=write, daemon=True).start()

    def _display_scene_result(self, draft):
        lines = []
        lines.append(f"标题: {draft.title}")
        lines.append(f"ID:   {draft.id}")
        lines.append(f"类型: {draft.draft_type}")
        lines.append(f"状态: {draft.status} (v{draft.version})")
        lines.append(f"字数: {len(draft.draft_text)}")
        llm_used = draft.metadata.get('llm_used', False)
        lines.append(f"LLM:  {llm_used}  {'(use-llm)' if llm_used else '(no-llm)'}")
        lines.append(f"任务卡: {draft.task_card_id}")
        if draft.scene_summary:
            lines.append(f"\n摘要:\n{draft.scene_summary}")
        lines.append(f"\n{'='*50}")
        lines.append("正文预览:")
        lines.append(draft.draft_text[:1500] + ("\n\n...(截断)" if len(draft.draft_text) > 1500 else ""))
        self.scene_result.delete("1.0", tk.END)
        self.scene_result.insert("1.0", "\n".join(lines))

    # ── Tab5: 质检与改写 ────────────────────────────────

    def _build_tab5_check(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  质检与改写  ")

        left = ttk.Frame(frame)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        ttk.Label(left, text="选择场景草稿:").pack(anchor=tk.W)
        self.check_scene_combo = ttk.Combobox(left, width=45)
        self.check_scene_combo.pack(fill=tk.X, pady=5)

        self.check_api_label = ttk.Label(left, text="", font=("Segoe UI", 9, "italic"),
                                         foreground="gray")
        self.check_api_label.pack(anchor=tk.W)

        ctrl1 = ttk.Frame(left)
        ctrl1.pack(fill=tk.X, pady=5)
        self.check_use_llm = BooleanVar(value=False)
        ttk.Checkbutton(ctrl1, text="use-llm (DeepSeek)", variable=self.check_use_llm).pack(
            side=tk.LEFT)
        self.check_btn = ttk.Button(ctrl1, text="质检 (check-scene)", command=self._do_check)
        self.check_btn.pack(side=tk.LEFT, padx=10)
        self.refresh_check_list_btn = ttk.Button(ctrl1, text="刷新列表",
                                                 command=self._refresh_check_scene_list)
        self.refresh_check_list_btn.pack(side=tk.LEFT, padx=5)

        self.check_result = scrolledtext.ScrolledText(
            left, wrap=tk.WORD, font=("Consolas", 10), height=12)
        self.check_result.pack(fill=tk.BOTH, expand=True, pady=5)

        ctrl2 = ttk.Frame(left)
        ctrl2.pack(fill=tk.X, pady=5)
        self.rewrite_use_llm = BooleanVar(value=False)
        ttk.Checkbutton(ctrl2, text="use-llm (DeepSeek)", variable=self.rewrite_use_llm).pack(
            side=tk.LEFT)
        self.rewrite_btn = ttk.Button(ctrl2, text="改写 (rewrite)", command=self._do_rewrite)
        self.rewrite_btn.pack(side=tk.LEFT, padx=10)

        right = ttk.Frame(frame)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Provenance
        prov = ttk.LabelFrame(right, text="来源与演化路径")
        prov.pack(fill=tk.X)
        self.scene_provenance_label = ttk.Label(prov, text="来源: - → 尚未质检 → 尚未改写 → 未标记final",
            justify=tk.LEFT, foreground="#555555")
        self.scene_provenance_label.pack(anchor=tk.W, padx=4, pady=2)
        self.scene_prov_path_label = ttk.Label(prov, text="来源种子: -" + chr(10) + "草稿: -" + chr(10) + "质检: -" + chr(10) + "改写: -" + chr(10) + "最终稿: -", justify=tk.LEFT, foreground="#555", wraplength=500)
        self.scene_prov_path_label.pack(anchor=tk.W, padx=4, pady=2)
        mm = ttk.LabelFrame(right, text="质检问题 \u2192 改写动作")
        mm.pack(fill=tk.X, pady=1)
        self.rrw_label = ttk.Label(mm, text="(not run)", foreground="#888", wraplength=500, justify="left")
        self.rrw_label.pack(anchor=tk.W, padx=4, pady=2)
        rr = ttk.LabelFrame(right, text="改写说明")
        rr.pack(fill=tk.X, pady=1)
        self.rpl_label = ttk.Label(rr, text="(not run)", foreground="#888", wraplength=500, justify="left")
        self.rpl_label.pack(anchor=tk.W, padx=4, pady=2)
        # Review result
        rev = ttk.LabelFrame(right, text="质检结果")
        rev.pack(fill=tk.X, pady=2)
        self.review_status_label = ttk.Label(rev, text="检测结果: 未运行", foreground="#666666")
        self.review_status_label.pack(anchor=tk.W, padx=4, pady=2)
        self.review_issues_text = scrolledtext.ScrolledText(rev, wrap=tk.WORD, font=("Consolas", 9), height=5)
        self.review_issues_text.pack(fill=tk.X, padx=4, pady=2)
        self.review_issues_text.insert(tk.END, "(问题列表)")
        self.review_issues_text.config(state=tk.DISABLED)
        self.review_sugg_text = scrolledtext.ScrolledText(rev, wrap=tk.WORD, font=("Consolas", 9), height=3)
        self.review_sugg_text.pack(fill=tk.X, padx=4, pady=2)
        self.review_sugg_text.insert(tk.END, "(修改建议)")
        self.review_sugg_text.config(state=tk.DISABLED)
        # Rewrite result + diff
        ttk.Label(right, text="改写结果:").pack(anchor=tk.W)
        self.rewrite_result = scrolledtext.ScrolledText(right, wrap=tk.WORD, font=("Consolas", 10), height=6)
        self.rewrite_result.pack(fill=tk.X, expand=False, pady=2)
        # Rewrite diff
        diff = ttk.LabelFrame(right, text="改写对比")
        diff.pack(fill=tk.BOTH, expand=True, pady=2)
        dr = ttk.Frame(diff)
        dr.pack(fill=tk.BOTH, expand=True)
        bf = ttk.LabelFrame(dr, text="Before")
        bf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.rewrite_before_text = scrolledtext.ScrolledText(bf, wrap=tk.WORD, font=("Consolas", 9), height=4)
        self.rewrite_before_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        af = ttk.LabelFrame(dr, text="After")
        af.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.rewrite_after_text = scrolledtext.ScrolledText(af, wrap=tk.WORD, font=("Consolas", 9), height=4)
        self.rewrite_after_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.rewrite_changed_label = ttk.Label(diff, text="changed: -", foreground="#555555")
        self.rewrite_changed_label.pack(anchor=tk.W, padx=4, pady=2)

        self._check_scene_map = {}
        self._last_check_report_id = None
        self.root.after(500, self._refresh_check_scene_list)

    def _refresh_check_scene_list(self):
        if not self._backend_loaded:
            self.root.after(500, self._refresh_check_scene_list)
            return
        try:
            drafts = list_scene_drafts()
            self._check_scene_map = {}
            items = []
            for d in drafts:
                label = f"v{d.version} {d.title[:40]}  ({d.id[:12]}...)"
                self._check_scene_map[label] = d.id
                items.append(label)
            self.check_scene_combo["values"] = items
            if items:
                self.check_scene_combo.set(items[0])
            self.check_api_label.config(text=self._api_status_text())
        except Exception:
            pass

    def _do_check(self):
        if not self._require_backend():
            return
        label = self.check_scene_combo.get()
        if not label or label not in self._check_scene_map:
            messagebox.showwarning("提示", "请选择一个场景草稿")
            return
        scene_id = self._check_scene_map[label]
        use_llm = self.check_use_llm.get()

        if use_llm and self._api_key_status != "found":
            self._log("质检: API Key missing, 自动切换 no-llm")
            use_llm = False
            self.check_use_llm.set(False)

        task_id = "check_scene"
        if not self._task_begin(task_id):
            return

        self.check_btn.config(state=tk.DISABLED)
        self.refresh_check_list_btn.config(state=tk.DISABLED)
        self._start_progress("正在质检..." + (" (LLM)" if use_llm else " (no-llm)"))
        self._set_task(f"质检: {_trunc(label, 40)}")
        self._clear_status()
        mode = "LLM" if use_llm else "no-llm"
        self._log(f"开始质检: scene={scene_id[:16]}... mode={mode}")

        def check():
            start_t = time.time()
            try:
                draft = get_scene_draft(scene_id)
                if not draft:
                    raise ValueError("场景草稿未找到")
                from app.storage.task_store import get_task_card
                task_card = get_task_card(draft.task_card_id) if draft.task_card_id else None
                checker = SceneChecker(use_llm=use_llm)
                report = checker.check(draft, task_card)
                cid = add_report(report)
                self._last_check_report_id = cid
                dur = time.time() - start_t
                self.root.after(0, lambda: self._display_check_result(report))
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True, cid))
                self.root.after(0, lambda: self._set_task("质检完成"))
                self._log(f"质检完成: report={cid[:16]}... llm={report.llm_used} "
                          f"AI感={report.ai_feel_score} ({dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._show_error("质检失败", str(e)))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"质检失败: {e}")
            finally:
                self._task_end(task_id)
                self.root.after(0, lambda: self.check_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.refresh_check_list_btn.config(state=tk.NORMAL))
                self.root.after(0, self._stop_progress)

        threading.Thread(target=check, daemon=True).start()

    def _display_check_result(self, report):
        lines = []
        lines.append(f"报告 ID: {report.id}")
        lines.append(f"场景 ID: {report.scene_id}")
        lines.append(f"LLM:     {report.llm_used}")
        lines.append(f"状态:    {report.status}")
        if report.fallback_reason:
            lines.append(f"回退:    {report.fallback_reason}")
        lines.append("")
        lines.append(f"AI感:         {report.ai_feel_score}/100")
        lines.append(f"现实颗粒:     {report.reality_grain_score}/100")
        lines.append(f"连贯性:       {report.continuity_score}/100")
        lines.append(f"对话:         {report.dialogue_score}/100")
        lines.append(f"动作细节:     {report.action_detail_score}/100")
        if report.risk_flags:
            lines.append(f"\n风险: {' | '.join(report.risk_flags)}")
        if report.suggestions:
            lines.append("\n建议:")
            for s in report.suggestions:
                lines.append(f"  - {s}")
        if report.evidence:
            lines.append(f"\n证据 ({len(report.evidence)} 条):")
            for e in report.evidence[:5]:
                lines.append(f"  原文: {_trunc(e.text, 60)}")
                lines.append(f"  问题: {e.problem}")
                lines.append(f"  建议: {_trunc(e.suggestion, 80)}")
                lines.append("")
        self.check_result.delete("1.0", tk.END)
        self.check_result.insert("1.0", "\n".join(lines))

    def _do_rewrite(self):
        if not self._require_backend():
            return
        label = self.check_scene_combo.get()
        if not label or label not in self._check_scene_map:
            messagebox.showwarning("提示", "请选择一个场景草稿")
            return
        scene_id = self._check_scene_map[label]
        check_id = self._last_check_report_id
        if not check_id:
            messagebox.showwarning("提示", "请先执行质检")
            return
        use_llm = self.rewrite_use_llm.get()

        if use_llm and self._api_key_status != "found":
            self._log("改写: API Key missing, 自动切换 no-llm")
            use_llm = False
            self.rewrite_use_llm.set(False)

        task_id = "rewrite_scene"
        if not self._task_begin(task_id):
            return

        self.rewrite_btn.config(state=tk.DISABLED)
        self._start_progress("正在改写..." + (" (LLM)" if use_llm else " (no-llm)"))
        self._set_task(f"改写: {_trunc(label, 40)}")
        self._clear_status()
        mode = "LLM" if use_llm else "no-llm"
        self._log(f"开始改写: scene={scene_id[:16]}... report={check_id[:16]}... mode={mode}")

        def rewrite():
            start_t = time.time()
            try:
                report = get_report(check_id)
                if not report:
                    raise ValueError("质检报告未找到")
                revised = rewrite_scene_from_check(
                    scene_id=scene_id,
                    check_report=report,
                    draft_type="novel",
                    use_llm=use_llm,
                    save=True,
                )
                dur = time.time() - start_t
                self.root.after(0, lambda: self._display_rewrite_result(revised))
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(True, revised.id))
                self.root.after(0, lambda: self._set_task("改写完成"))
                self._log(f"改写完成: id={revised.id[:16]}... v{revised.version} "
                          f"({dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._show_error("改写失败", str(e)))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"改写失败: {e}")
            finally:
                self._task_end(task_id)
                self.root.after(0, lambda: self.rewrite_btn.config(state=tk.NORMAL))
                self.root.after(0, self._stop_progress)

        threading.Thread(target=rewrite, daemon=True).start()

    def _display_rewrite_result(self, revised):
        lines = []
        lines.append(f"新版本 ID: {revised.id}")
        lines.append(f"父版本 ID: {revised.parent_scene_id or '无'}")
        lines.append(f"版本: v{revised.version}")
        lines.append(f"字数: {len(revised.draft_text)}")
        lines.append(f"状态: {revised.status}")
        if revised.revision_notes:
            lines.append("\n修改点:")
            for n in revised.revision_notes:
                lines.append(f"  - {n}")
        if revised.revision_reason:
            lines.append(f"\n改写原因: {revised.revision_reason}")
        if revised.fallback_reason:
            lines.append(f"\n回退: {revised.fallback_reason}")
        lines.append(f"\n{'='*50}")
        lines.append("正文预览:")
        lines.append(revised.draft_text[:1500] + ("\n\n...(截断)" if len(revised.draft_text) > 1500 else ""))
        self.rewrite_result.delete("1.0", tk.END)
        self.rewrite_result.insert("1.0", "\n".join(lines))

    # ── Tab6: Obsidian 导出 ────────────────────────────

    def _build_tab6_export(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  Obsidian 导出  ")

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top, text="导出目标:").pack(side=tk.LEFT)
        self.export_type = ttk.Combobox(
            top, values=["任务卡", "场景草稿", "检查报告", "蓝图"], width=12)
        self.export_type.set("任务卡")
        self.export_type.pack(side=tk.LEFT, padx=5)
        self.export_type.bind("<<ComboboxSelected>>", lambda e: self._refresh_export_list())

        ttk.Label(top, text="选择条目:").pack(side=tk.LEFT, padx=(10, 0))
        self.export_item_combo = ttk.Combobox(top, width=50)
        self.export_item_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.refresh_export_list_btn = ttk.Button(top, text="刷新列表",
                                                  command=self._refresh_export_list)
        self.refresh_export_list_btn.pack(side=tk.LEFT, padx=5)
        self.export_btn = ttk.Button(top, text="导出", command=self._do_export)
        self.export_btn.pack(side=tk.LEFT, padx=10)

        self.export_result = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10))
        self.export_result.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        ttk.Label(frame, text="导出目录: H:\\10_Obsidian\\90_System\\04_方法论\\小说剧本创作大师_完整知识体系\\_任务卡库\\ / _场景草稿库\\ / _检查报告库\\",
                  font=("Segoe UI", 9, "italic"), foreground="gray").pack(anchor=tk.W, padx=10, pady=(0, 5))

        self._export_map = {}
        self.root.after(500, self._refresh_export_list)

    def _refresh_export_list(self):
        if not self._backend_loaded:
            self.root.after(500, self._refresh_export_list)
            return
        typ = self.export_type.get()
        self._export_map = {}
        items = []
        try:
            if typ == "任务卡":
                cards = list_task_cards()
                for c in cards:
                    label = f"[{c.card_type.upper()}] {c.title[:45]}  ({c.id[:12]}...)"
                    self._export_map[label] = ("card", c.id)
                    items.append(label)
            elif typ == "场景草稿":
                drafts = list_scene_drafts()
                for d in drafts:
                    label = f"v{d.version} {d.title[:40]}  ({d.id[:12]}...)"
                    self._export_map[label] = ("scene", d.id)
                    items.append(label)
            elif typ == "检查报告":
                reports = list_reports()
                for r in reports:
                    label = f"AI感:{r.ai_feel_score} 现实:{r.reality_grain_score}  ({r.id[:12]}...)"
                    self._export_map[label] = ("check", r.id)
                    items.append(label)
            elif typ == "蓝图":
                bps = list_blueprints()
                for bp in bps:
                    label = f"{bp.title[:45]}  ({bp.id[:12]}...)"
                    self._export_map[label] = ("blueprint", bp.id)
                    items.append(label)
        except Exception:
            pass
        self.export_item_combo["values"] = items
        if items:
            self.export_item_combo.set(items[0])

    def _do_export(self):
        if not self._require_backend():
            return
        label = self.export_item_combo.get()
        if not label or label not in self._export_map:
            messagebox.showwarning("提示", "请选择一个导出条目")
            return
        etype, eid = self._export_map[label]

        task_id = "export"
        if not self._task_begin(task_id):
            return

        self.export_btn.config(state=tk.DISABLED)
        self.refresh_export_list_btn.config(state=tk.DISABLED)
        self._start_progress("正在导出...")
        self._set_task(f"导出: {_trunc(label, 40)}")
        self._clear_status()
        self._log(f"开始导出: type={etype} id={eid[:16]}...")

        def export():
            start_t = time.time()
            try:
                path = ""
                if etype == "card":
                    from app.storage.task_store import get_task_card
                    card = get_task_card(eid)
                    if card:
                        path = export_task_card(card)
                elif etype == "scene":
                    draft = get_scene_draft(eid)
                    if draft:
                        path = export_scene_draft(draft)
                elif etype == "check":
                    report = get_report(eid)
                    if report:
                        path = export_check_report(report)
                elif etype == "blueprint":
                    from app.storage.blueprint_store import get_blueprint
                    bp = get_blueprint(eid)
                    if bp:
                        path = export_blueprint(bp)
                dur = time.time() - start_t
                if path:
                    exists = os.path.isfile(path)
                    self.root.after(0, lambda: self._display_export_result(
                        f"[OK] 导出成功\n\n路径: {path}\n文件存在: {exists}"))
                    self.root.after(0, lambda: self._set_result(True))
                    self.root.after(0, lambda: self._set_task(f"导出成功: {path[-50:]}"))
                    self._log(f"导出成功: {path} ({dur:.1f}s)")
                else:
                    self.root.after(0, lambda: self._display_export_result(
                        "[FAIL] 导出失败: 未找到条目"))
                    self.root.after(0, lambda: self._set_result(False))
                    self._log("导出失败: 未找到条目")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._show_error("导出失败", str(e)))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"导出失败: {e}")
            finally:
                self._task_end(task_id)
                self.root.after(0, lambda: self.export_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.refresh_export_list_btn.config(state=tk.NORMAL))
                self.root.after(0, self._stop_progress)

        threading.Thread(target=export, daemon=True).start()

    def _display_export_result(self, text: str):
        self.export_result.delete("1.0", tk.END)
        self.export_result.insert("1.0", text)

    # ════════════════════════════════════════════════
    # Tab7: Notion 同步 (阶段10 新增)
    # ════════════════════════════════════════════════

    def _build_tab7_notion(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  Notion 同步  ")

        # 配置检查区
        cfg_frame = ttk.LabelFrame(frame, text="配置检查", padding=5)
        cfg_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.notion_cfg_text = scrolledtext.ScrolledText(
            cfg_frame, height=4, font=("Consolas", 10), wrap=tk.WORD)
        self.notion_cfg_text.pack(fill=tk.X, pady=5)
        ttk.Button(cfg_frame, text="检查配置",
                   command=self._do_notion_check_config).pack(anchor=tk.W)

        # 追踪统计
        track_frame = ttk.LabelFrame(frame, text="同步追踪", padding=5)
        track_frame.pack(fill=tk.X, padx=10, pady=5)
        self.notion_track_text = scrolledtext.ScrolledText(
            track_frame, height=3, font=("Consolas", 10), wrap=tk.WORD)
        self.notion_track_text.pack(fill=tk.X, pady=5)
        ttk.Button(track_frame, text="刷新追踪",
                   command=self._do_notion_tracking_stats).pack(anchor=tk.W)

        # 操作区
        action_frame = ttk.LabelFrame(frame, text="同步操作", padding=5)
        action_frame.pack(fill=tk.X, padx=10, pady=5)

        # 单条同步
        row1 = ttk.Frame(action_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Card ID:").pack(side=tk.LEFT)
        self.notion_card_id = ttk.Entry(row1, width=40)
        self.notion_card_id.pack(side=tk.LEFT, padx=5)
        self.notion_sync_card_btn = ttk.Button(
            row1, text="同步任务卡", command=self._do_notion_sync_task)
        self.notion_sync_card_btn.pack(side=tk.LEFT, padx=5)

        row2 = ttk.Frame(action_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Scene ID:").pack(side=tk.LEFT)
        self.notion_scene_id = ttk.Entry(row2, width=40)
        self.notion_scene_id.pack(side=tk.LEFT, padx=5)
        self.notion_sync_scene_btn = ttk.Button(
            row2, text="同步场景", command=self._do_notion_sync_scene)
        self.notion_sync_scene_btn.pack(side=tk.LEFT, padx=5)

        row3 = ttk.Frame(action_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Check ID:").pack(side=tk.LEFT)
        self.notion_check_id = ttk.Entry(row3, width=40)
        self.notion_check_id.pack(side=tk.LEFT, padx=5)
        self.notion_sync_check_btn = ttk.Button(
            row3, text="同步检查报告", command=self._do_notion_sync_check)
        self.notion_sync_check_btn.pack(side=tk.LEFT, padx=5)

        # 批量同步
        row4 = ttk.Frame(action_frame)
        row4.pack(fill=tk.X, pady=5)
        ttk.Label(row4, text="批量同步 Limit:").pack(side=tk.LEFT)
        self.notion_limit = ttk.Spinbox(row4, from_=1, to=50, width=5)
        self.notion_limit.set(3)
        self.notion_limit.pack(side=tk.LEFT, padx=5)
        self.notion_sync_recent_btn = ttk.Button(
            row4, text="同步近期", command=self._do_notion_sync_recent)
        self.notion_sync_recent_btn.pack(side=tk.LEFT, padx=10)
        self.notion_demo_btn = ttk.Button(
            row4, text="Demo 同步", command=self._do_notion_demo)
        self.notion_demo_btn.pack(side=tk.LEFT, padx=5)

        self.notion_use_llm = BooleanVar(value=False)
        ttk.Checkbutton(row4, text="use-llm for demo",
                        variable=self.notion_use_llm).pack(side=tk.LEFT, padx=10)

        # dry-run
        self.notion_dry_run = BooleanVar(value=True)
        ttk.Checkbutton(row4, text="dry-run",
                        variable=self.notion_dry_run).pack(side=tk.LEFT, padx=5)

        # 结果输出
        self.notion_result = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10), height=12)
        self.notion_result.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

    def _display_notion(self, text: str):
        self.notion_result.delete("1.0", tk.END)
        self.notion_result.insert("1.0", text)

    def _display_notion_cfg(self, text: str):
        self.notion_cfg_text.delete("1.0", tk.END)
        self.notion_cfg_text.insert("1.0", text)

    def _display_notion_track(self, text: str):
        self.notion_track_text.delete("1.0", tk.END)
        self.notion_track_text.insert("1.0", text)

    def _do_notion_check_config(self):
        if not self._require_backend():
            return
        self._start_progress("检查 Notion 配置...")
        self._set_task("检查 Notion 配置")

        def run():
            start_t = time.time()
            try:
                sync = NotionSync(dry_run=self.notion_dry_run.get())
                result = sync.check_config()
                dur = time.time() - start_t
                lines = []
                lines.append(f"Token: {'OK' if result.get('token_ok') else 'FAIL'}")
                lines.append(f"Database: {'OK' if result.get('databases_ok') else 'FAIL'}")
                lines.append(f"Schema: {'OK' if result.get('schema_ok') else 'FAIL'}")
                lines.append(f"Errors: {len(result.get('errors', []))}")
                for db_key in ["task_card", "scene_draft", "check_report"]:
                    db = result.get("databases", {}).get(db_key, {})
                    if db:
                        lines.append(f"  {db_key}: reachable={db.get('reachable')} fields={db.get('properties_count')} missing={db.get('missing_fields', [])}")
                text = "\n".join(lines)
                self.root.after(0, lambda: self._display_notion_cfg(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self._log(f"Notion 配置检查完成: ok={result.get('ok')}")
            except Exception as e:
                self.root.after(0, lambda: self._display_notion_cfg(f"FAIL: {e}"))
                self._log(f"Notion 配置检查失败: {e}")
            finally:
                self._task_end("notion_check")
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _do_notion_tracking_stats(self):
        if not self._require_backend():
            return
        def run():
            try:
                stats = get_tracking_stats()
                lines = []
                lines.append(f"Total: {stats['total']}")
                for k, v in stats.get("by_status", {}).items():
                    lines.append(f"  {k}: {v}")
                for k, v in stats.get("by_type", {}).items():
                    lines.append(f"  {k}: {v}")
                self.root.after(0, lambda: self._display_notion_track("\n".join(lines)))
            except Exception as e:
                self.root.after(0, lambda: self._display_notion_track(f"FAIL: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def _do_notion_sync_task(self):
        card_id = self.notion_card_id.get().strip()
        if not card_id:
            messagebox.showwarning("提示", "请输入 Card ID")
            return
        self._do_notion_sync_generic(
            "sync_task", lambda sync: sync.sync_task_card(card_id))

    def _do_notion_sync_scene(self):
        scene_id = self.notion_scene_id.get().strip()
        if not scene_id:
            messagebox.showwarning("提示", "请输入 Scene ID")
            return
        self._do_notion_sync_generic(
            "sync_scene", lambda sync: sync.sync_scene_draft(scene_id))

    def _do_notion_sync_check(self):
        check_id = self.notion_check_id.get().strip()
        if not check_id:
            messagebox.showwarning("提示", "请输入 Check ID")
            return
        self._do_notion_sync_generic(
            "sync_check", lambda sync: sync.sync_check_report(check_id))

    def _do_notion_sync_generic(self, task_id_base, sync_fn):
        if not self._require_backend():
            return
        tid = f"notion_{task_id_base}"
        if not self._task_begin(tid):
            return
        self._start_progress(f"正在同步到 Notion...")
        self._set_task(f"{task_id_base}")

        def run():
            start_t = time.time()
            try:
                sync = NotionSync(dry_run=self.notion_dry_run.get())
                page_id = sync_fn(sync)
                dur = time.time() - start_t
                text = f"Notion page: {page_id}\nDuration: {dur:.1f}s"
                self.root.after(0, lambda: self._display_notion(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self.root.after(0, lambda: self._set_result(ok=bool(page_id)))
                self._log(f"Notion {task_id_base}: {page_id[:16] if page_id else 'FAIL'} ({dur:.1f}s)")
            except Exception as e:
                self.root.after(0, lambda: self._display_notion(f"FAIL: {e}"))
                self._log(f"Notion {task_id_base} 失败: {e}")
            finally:
                self._task_end(tid)
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _do_notion_sync_recent(self):
        if not self._require_backend():
            return
        try:
            limit = int(self.notion_limit.get())
        except ValueError:
            limit = 3
        tid = "notion_sync_recent"
        if not self._task_begin(tid):
            return
        self._start_progress(f"同步近期 {limit} 条...")
        self._set_task(f"sync-recent limit={limit}")

        def run():
            start_t = time.time()
            try:
                sync = NotionSync(dry_run=self.notion_dry_run.get())
                stats = sync.sync_recent(limit=limit)
                dur = time.time() - start_t
                text = json.dumps(stats, ensure_ascii=False, indent=2)
                self.root.after(0, lambda: self._display_notion(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self._log(f"Notion sync-recent: {stats.get('created')}创建 {stats.get('updated')}更新 ({dur:.1f}s)")
            except Exception as e:
                self.root.after(0, lambda: self._display_notion(f"FAIL: {e}"))
                self._log(f"Notion sync-recent 失败: {e}")
            finally:
                self._task_end(tid)
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _do_notion_demo(self):
        if not self._require_backend():
            return
        tid = "notion_demo"
        if not self._task_begin(tid):
            return
        self._start_progress("Notion demo...")
        self._set_task("notion demo sync")

        def run():
            start_t = time.time()
            try:
                sync = NotionSync(dry_run=self.notion_dry_run.get())
                result = sync.demo_sync(report_json=True)
                dur = time.time() - start_t
                text = json.dumps(result, ensure_ascii=False, indent=2)
                self.root.after(0, lambda: self._display_notion(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self._log(f"Notion demo sync complete ({dur:.1f}s)")
            except Exception as e:
                self.root.after(0, lambda: self._display_notion(f"FAIL: {e}"))
                self._log(f"Notion demo 失败: {e}")
            finally:
                self._task_end(tid)
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    # ════════════════════════════════════════════════
    # Tab8: Reports 面板 (阶段10 新增)
    # ════════════════════════════════════════════════

    def _build_tab8_reports(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  Reports  ")

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top, text="选择报告文件:").pack(side=tk.LEFT)
        self.report_combo = ttk.Combobox(top, width=60)
        self.report_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.refresh_reports_btn = ttk.Button(top, text="刷新列表",
                                              command=self._refresh_report_list)
        self.refresh_reports_btn.pack(side=tk.LEFT, padx=5)
        self.view_report_btn = ttk.Button(top, text="查看报告",
                                          command=self._do_view_report)
        self.view_report_btn.pack(side=tk.LEFT, padx=5)

        self.report_text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10))
        self.report_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._report_files = []
        self.root.after(500, self._refresh_report_list)

    def _refresh_report_list(self):
        self._report_files = []
        items = []
        if os.path.isdir(REPORTS_DIR):
            for f in sorted(os.listdir(REPORTS_DIR)):
                if f.endswith(".json"):
                    self._report_files.append(f)
                    items.append(f)
        self.report_combo["values"] = items
        if items:
            self.report_combo.set(items[0])

    def _do_view_report(self):
        fname = self.report_combo.get()
        if not fname or fname not in self._report_files:
            messagebox.showwarning("提示", "请选择一个报告文件")
            return
        fpath = os.path.join(REPORTS_DIR, fname)
        if not os.path.exists(fpath):
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert("1.0", f"文件不存在: {fpath}")
            return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert("1.0", text)
            self._log(f"已查看报告: {fname}")
        except Exception as e:
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert("1.0", f"读取失败: {e}")

    # ════════════════════════════════════════════════
    # Tab9: 一键流水线 + 配置检查 + 备份 (阶段10 新增)
    # ════════════════════════════════════════════════

    def _build_tab9_pipeline(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="  一键流水线  ")

        # 配置检查面板
        cfg_frame = ttk.LabelFrame(frame, text="配置检查", padding=5)
        cfg_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.cfg_check_text = scrolledtext.ScrolledText(
            cfg_frame, height=6, font=("Consolas", 10), wrap=tk.WORD)
        self.cfg_check_text.pack(fill=tk.X, pady=5)
        btn_row = ttk.Frame(cfg_frame)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="检查所有配置",
                   command=self._do_check_all_configs).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="备份数据库",
                   command=self._do_backup_db).pack(side=tk.LEFT, padx=5)

        # 流水线控制面板
        pipe_frame = ttk.LabelFrame(frame, text="一键流水线", padding=5)
        pipe_frame.pack(fill=tk.X, padx=10, pady=5)

        row1 = ttk.Frame(pipe_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="创作需求:").pack(side=tk.LEFT)
        self.pipeline_query = ttk.Entry(row1, width=60)
        self.pipeline_query.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        row2 = ttk.Frame(pipe_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="生成数量:").pack(side=tk.LEFT)
        self.pipeline_count = ttk.Spinbox(row2, from_=1, to=5, width=5)
        self.pipeline_count.set(1)
        self.pipeline_count.pack(side=tk.LEFT, padx=5)
        self.pipeline_use_llm = BooleanVar(value=False)
        ttk.Checkbutton(row2, text="use-llm (DeepSeek)",
                        variable=self.pipeline_use_llm).pack(side=tk.LEFT, padx=10)
        self.pipeline_btn = ttk.Button(row2, text="运行流水线",
                                       command=self._do_run_pipeline)
        self.pipeline_btn.pack(side=tk.LEFT, padx=10)

        ttk.Label(row2, text="流水线: 检索 -> 任务卡 -> 扩写 -> 质检 -> 改写 -> 导出 -> Notion",
                  font=("Segoe UI", 9, "italic"), foreground="gray").pack(side=tk.LEFT, padx=5)

        # 流水线进度
        self.pipeline_progress = ttk.Label(pipe_frame, text="", font=("Segoe UI", 9))
        self.pipeline_progress.pack(fill=tk.X, pady=2)

        # 结果输出
        self.pipeline_result = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 10))
        self.pipeline_result.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def _display_pipeline(self, text: str):
        self.pipeline_result.delete("1.0", tk.END)
        self.pipeline_result.insert("1.0", text)

    def _display_cfg_check(self, text: str):
        self.cfg_check_text.delete("1.0", tk.END)
        self.cfg_check_text.insert("1.0", text)

    def _do_check_all_configs(self):
        if not self._require_backend():
            return
        self._start_progress("检查所有配置...")
        self._set_task("检查所有配置")

        def run():
            start_t = time.time()
            try:
                lines = []

                # DeepSeek
                ds = _check_deepseek_config()
                lines.append(f"[DeepSeek]  ok={ds.get('ok')}  {ds.get('message', '')}")

                # Notion
                nc = _check_notion_config()
                nc_ok = all(v == "ok" for v in nc.values() if v != "_all_ok")
                lines.append(f"[Notion]   ok={nc_ok}")
                for k, v in nc.items():
                    if k != "_all_ok":
                        lines.append(f"           {k}={v}")

                # FAISS
                fi = _check_faiss_index()
                lines.append(f"[FAISS]   ok={fi.get('ok')}  size={fi.get('size')}")
                if fi.get("error"):
                    lines.append(f"           error: {fi.get('error')}")

                # Obsidian
                op = _check_obsidian_path()
                lines.append(f"[Obsidian] ok={op.get('subdirs_ok')}  base={op.get('base')}")
                lines.append(f"           subdirs: {op.get('existing')}")

                text = "\n".join(lines)
                dur = time.time() - start_t
                self.root.after(0, lambda: self._display_cfg_check(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self._log(f"配置检查完成 ({dur:.1f}s)")
            except Exception as e:
                self.root.after(0, lambda: self._display_cfg_check(f"FAIL: {e}"))
            finally:
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _do_backup_db(self):
        self._start_progress("备份数据库...")
        self._set_task("backup db")

        def run():
            start_t = time.time()
            try:
                result = _do_backup_db()
                dur = time.time() - start_t
                lines = []
                for db_name, info in result.items():
                    status = "OK" if info["ok"] else "FAIL"
                    lines.append(f"[{db_name}] {status}")
                    if info["ok"]:
                        lines.append(f"         path: {info['path']}")
                        lines.append(f"         size: {info['size_mb']} MB")
                text = "\n".join(lines)
                self.root.after(0, lambda: self._display_pipeline(text))
                self.root.after(0, lambda: self._set_duration(dur))
                self._log(f"备份完成: {json.dumps({k: v['ok'] for k, v in result.items()})} ({dur:.1f}s)")
            except Exception as e:
                self.root.after(0, lambda: self._display_pipeline(f"FAIL: {e}"))
                self._log(f"备份失败: {e}")
            finally:
                self.root.after(0, self._stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def _do_run_pipeline(self):
        if not self._require_backend():
            return
        query = self.pipeline_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入创作需求")
            return
        try:
            count = int(self.pipeline_count.get())
        except ValueError:
            count = 1
        use_llm = self.pipeline_use_llm.get()

        tid = "pipeline"
        if not self._task_begin(tid):
            return

        self.pipeline_btn.config(state=tk.DISABLED)
        self._start_progress("流水线运行中...")
        self._set_task(f"流水线: {_trunc(query, 30)}")
        self._log(f"启动一键流水线: query={_trunc(query, 40)} count={count} use_llm={use_llm}")

        def on_progress(msg: str):
            self.root.after(0, lambda: self.pipeline_progress.config(text=msg))

        def on_log(msg: str):
            self._log(msg)

        def run():
            start_t = time.time()
            try:
                result = _run_one_click_pipeline(
                    query=query, count=count, use_llm=use_llm,
                    progress_cb=on_progress, log_cb=on_log)
                dur = time.time() - start_t
                text = json.dumps(result, ensure_ascii=False, indent=2)
                self.root.after(0, lambda: self._display_pipeline(text))
                self.root.after(0, lambda: self._set_duration(dur))
                ok = len(result.get("errors", [])) == 0
                self.root.after(0, lambda: self._set_result(ok))
                s = result.get("summary", {})
                self._log(f"流水线完成: cards={s.get('cards')} scenes={s.get('scenes')} "
                          f"checks={s.get('checks')} rewrites={s.get('rewrites')} "
                          f"exports={s.get('exports')} notion={s.get('notion')} ({dur:.1f}s)")
            except Exception as e:
                dur = time.time() - start_t
                self.root.after(0, lambda: self._display_pipeline(f"FAIL: {e}"))
                self.root.after(0, lambda: self._set_result(False))
                self._log(f"流水线失败: {e}")
            finally:
                self.pipeline_btn.config(state=tk.NORMAL)
                self._task_end(tid)
                self.root.after(0, self._stop_progress)
                self.root.after(0, lambda: self.pipeline_progress.config(text=""))

        threading.Thread(target=run, daemon=True).start()

    # ── 主循环 ────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ============================================================
# 入口
# ============================================================

    def _build_tab11_scene_seed(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  ④ 场景种子  ")
        top = ttk.Frame(f)
        top.pack(fill=tk.X)
        ttk.Label(top, text="种子数量:").pack(side=tk.LEFT)
        self.seed_count_sb = ttk.Spinbox(top, from_=1, to=20, width=4)
        self.seed_count_sb.set(5)
        self.seed_count_sb.pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="生成场景种子", command=self._do_gen_seeds).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="→ 场景扩写", command=self._seed_to_write).pack(side=tk.LEFT, padx=8)
        lst = ttk.LabelFrame(f, text="种子列表")
        lst.pack(fill=tk.BOTH, expand=True, pady=2)
        cols = ("seed_id","title","source","pipeline")
        self.seed_tree = ttk.Treeview(lst, columns=cols, show="headings", height=6)
        for col, txt in [("seed_id","Seed ID"),("title","标题"),("source","来源"),("pipeline","管线")]:
            self.seed_tree.heading(col, text=txt)
            self.seed_tree.column(col, width=120)
        self.seed_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.seed_tree.bind("<<TreeviewSelect>>", self._on_seed_select)
        dtl = ttk.LabelFrame(f, text="种子详情")
        dtl.pack(fill=tk.X, pady=2)
        self.seed_dtl = ttk.Label(dtl, text="Seed ID: -\n标题: -\n来源: -\n管线: -\n摘要: -", justify=tk.LEFT)
        self.seed_dtl.pack(anchor=tk.W, padx=4, pady=2)
        ttk.Button(dtl, text="使用此种子创建场景草稿", command=self._seed_to_write).pack(anchor=tk.W, padx=4, pady=2)

    def _do_gen_seeds(self):
        self._log("[seed] gen seeds...")
        try:
            from app.core.gui_p2_bridge_exports import generate_scene_seeds_from_blueprint
            cnt = int(self.seed_count_sb.get())
            r = generate_scene_seeds_from_blueprint(blueprint_bundle={}, max_seeds=cnt, source_type="gui")
            for item in self.seed_tree.get_children(): self.seed_tree.delete(item)
            seeds = r.get("seeds", [])
            pipe = r.get("seed_pipeline", "legacy")
            for i, s in enumerate(seeds):
                ss = s.get("scene_seed", s)
                self.seed_tree.insert("", tk.END, iid=str(i), values=(
                    ss.get("seed_id",""), ss.get("title","")[:60], ss.get("origin_path",""), pipe))
            self._log("[seed] "+str(len(seeds))+" seeds")
        except Exception as e:
            self._log("[seed] fail: "+str(e))

    def _on_seed_select(self, evt):
        sel = self.seed_tree.selection()
        if not sel: return
        idx = int(sel[0])
        s = {}
        try:
            sd = getattr(self, '_seeds_data', [])
            if idx < len(sd): s = sd[idx]
        except: pass
        ss = s.get("scene_seed", s) if isinstance(s, dict) else {}
        sid = str(ss.get("seed_id", sel[0] if sel else ""))
        title = str(ss.get("title", ss.get("seed_title", "")))
        src = str(ss.get("origin_path", ss.get("source", "?")))
        pipe = str(ss.get("seed_pipeline", ss.get("pipeline", "?")))
        log = str(ss.get("logline", ss.get("text_preview", "")))[:200]
        scn = {"legacy":"来自旧链兼容","bridge":"桥接层","current":"当前主链","task_card":"来自任务卡","blueprint":"来自蓝图","material":"来自素材","pipeline":"来自素材管道"}
        sc = scn.get(src, src)
        pcn = {"legacy":"旧版管线","legacy_fallback":"旧版兼容","p2_mainline":"新主链(P2)","material_pipeline_current":"素材管线","task_card_current":"任务卡管线"}
        pc = pcn.get(pipe, pipe)
        lst = ["来源类型: " + sc, "来源对象: " + (sid if sid else "未提供来源对象编号"), "管线说明: " + pc, "Seed ID: " + sid, "标题: " + title, "摘要: " + log, "", "该种子将作为场景扩写的输入起点。"]
        self.seed_dtl.config(text=chr(10).join(lst), foreground="#333")

    def _seed_to_write(self):
        for i in range(self.notebook.index("end")):
            if "场景扩写" in self.notebook.tab(i, "text"): self.notebook.select(i); break

    def _send_draft_to_review(self):
        for i in range(self.notebook.index("end")):
            if "质检" in self.notebook.tab(i, "text"): self.notebook.select(i); break

    def _go_to_seed_tab(self):
        for i in range(self.notebook.index("end")):
            if "场景种子" in self.notebook.tab(i, "text"): self.notebook.select(i); break

    def _go_to_chapter_tab(self):
        for i in range(self.notebook.index("end")):
            if "章节" in self.notebook.tab(i, "text"): self.notebook.select(i); break


    def _build_tab20_chapter_export(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  ⑨ 章节与导出  ")
        # Source & package summary
        sf = ttk.LabelFrame(f, text="场景来源说明")
        sf.pack(fill=tk.X)
        self.ch_src_lbl = ttk.Label(sf, text="当前场景数: (加载中) | 来源: scene_chain_current")
        self.ch_src_lbl.pack(anchor=tk.W, padx=4, pady=2)
        self.ch_pkg_lbl = ttk.Label(sf, text="(尚未生成章节包)", foreground="#888")
        self.ch_pkg_lbl.pack(anchor=tk.W, padx=4, pady=2)
        # Chapter list
        clf = ttk.LabelFrame(f, text="一、章节列表")
        clf.pack(fill=tk.X, pady=2)
        r1 = ttk.Frame(clf)
        r1.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(r1, text="根据当前场景链生成章节包", command=self._do_chapter_pkg).pack(side=tk.LEFT)
        cols = ("ch_id", "title", "scenes", "status")
        self.ch_tree = ttk.Treeview(clf, columns=cols, show="headings", height=5)
        for col, txt in [("ch_id","章节ID"),("title","章节标题"),("scenes","场景数"),("status","状态")]:
            self.ch_tree.heading(col, text=txt)
            self.ch_tree.column(col, width=120, anchor="w")
        self.ch_tree.pack(fill=tk.X, padx=4, pady=2)
        self.ch_tree.bind("<<TreeviewSelect>>", self._on_chapter_select)
        ttk.Label(clf, text="这些章节由当前场景链自动打包而来，可在此查看每章包含哪些场景。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=4, pady=1)
        # Chapter preview
        prf = ttk.LabelFrame(f, text="二、章节预览")
        prf.pack(fill=tk.X, pady=2)
        self.ch_preview_lbl = ttk.Label(prf, text="(选中章节后显示预览)", foreground="#888", wraplength=800, justify="left")
        ttk.Label(prf, text="预览区展示所选章节的摘要与正文片段，用于导出前检查结构是否合理。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=4, pady=1)
        self.ch_preview_lbl.pack(anchor=tk.W, padx=4, pady=2)
        # Export
        exf = ttk.LabelFrame(f, text="三、结构化导出")
        exf.pack(fill=tk.X, pady=2)
        er = ttk.Frame(exf)
        er.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(er, text="导出 Markdown", command=lambda: self._do_chapter_export("markdown")).pack(side=tk.LEFT, padx=2)
        ttk.Button(er, text="导出 EPUB", command=lambda: self._do_chapter_export("epub")).pack(side=tk.LEFT, padx=2)
        ttk.Button(er, text="导出 DOCX", command=lambda: self._do_chapter_export("docx")).pack(side=tk.LEFT, padx=2)
        self.ch_exp_lbl = ttk.Label(exf, text="(尚未导出)", foreground="#888", wraplength=800, justify="left")
        ttk.Label(exf, text="导出结果会写入项目导出目录；你可以回到场景工位调整内容后重新打包并再次导出。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=4, pady=1)
        self.ch_exp_lbl.pack(anchor=tk.W, padx=4, pady=2)
        # Hints
        ttk.Label(f, text="导出文件已写入项目导出目录；Markdown 适合继续编辑，EPUB/DOCX 适合分发或审阅。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=8, pady=1)
        ttk.Label(f, text="当前章节来自 scene_chain_current，来源分类为 category3_scene_chain。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=8, pady=1)
        ttk.Label(f, text="可返回场景写作/质检 Tab 继续调整场景，再重新生成章节包。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=8, pady=2)
        # Publish & History
        phf = ttk.LabelFrame(f, text="四、发布与历史")
        phf.pack(fill=tk.X, pady=2)
        phr = ttk.Frame(phf)
        phr.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(phr, text="生成发布摘要", command=self._do_publish_summary).pack(side=tk.LEFT, padx=2)
        ttk.Button(phr, text="查看最近导出记录", command=self._do_history_preview).pack(side=tk.LEFT, padx=2)
        self.ch_pub_lbl = ttk.Label(phf, text="(尚未生成发布摘要)", foreground="#888", wraplength=800, justify="left")
        self.ch_pub_lbl.pack(anchor=tk.W, padx=4, pady=2)
        self.ch_hist_lbl = ttk.Label(phf, text="(尚未查看记录)", foreground="#888", wraplength=800, justify="left")
        self.ch_hist_lbl.pack(anchor=tk.W, padx=4, pady=2)
        ttk.Label(phf, text="发布摘要用于记录本次导出的结构化结果；最近记录帮助你回看已经生成过哪些版本。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=4, pady=1)
        # State
        self._ch_pkg = None
        self._chapters = []

    def _do_chapter_pkg(self):
        self._log("[chapter] building...")
        try:
            from app.core.gui_p2_bridge_exports import build_chapter_package_for_gui
            r = build_chapter_package_for_gui(scene_ids=None)
            self._ch_pkg = r
            st = r.get("source_trace", {})
            pkg_txt = "章节包ID: "+str(r.get("chapter_package_id",""))+" | 章节:"+str(r.get("chapter_count",0))+" | 场景:"+str(r.get("scene_total_count",0))+" | 来源:"+str(r.get("story_source_type",""))+" | 分类:"+str(st.get("from_category",""))
            self.ch_pkg_lbl.config(text=pkg_txt, foreground="#060")
            self.ch_src_lbl.config(text="当前场景数: "+str(r.get("scene_total_count",0))+" | 来源: "+str(r.get("story_source_type","")), foreground="#060")
            st2 = r.get("source_trace", {})
            fc = st2.get("from_category", "")
            ds = st2.get("draft_stage", "")
            sc2 = str(r.get("scene_total_count", 0))
            final_txt = "本次章节包基于当前场景链中的 " + sc2 + " 个场景草稿生成，来源属于第三大类场景主链。" + chr(10)
            final_txt += "当前使用的是当前场景链中的场景草稿集合，尚未区分最终稿批次。"
            self.ch_final_lbl.config(text=final_txt, foreground="#060")
            # Populate tree
            for item in self.ch_tree.get_children():
                self.ch_tree.delete(item)
            chapters = r.get("chapters_data", r.get("chapters", []))
            self._chapters = chapters
            for ch in chapters:
                self.ch_tree.insert("", tk.END, values=(
                    ch.get("chapter_id",""), ch.get("chapter_title","")[:40],
                    ch.get("scene_count",0), ch.get("status","ready")))
            self._log("[chapter] done: "+str(len(chapters))+" chapters")
        except Exception as e:
            self.ch_pkg_lbl.config(text="fail: "+str(e), foreground="#c60")

    def _do_chapter_export(self, etype):
        pkg = getattr(self, '_ch_pkg', None)
        if not pkg:
            self.ch_exp_lbl.config(text="请先生成章节包", foreground="#c60")
            return
        pkg_id = pkg.get("chapter_package_id", "")
        chapters = getattr(self, '_chapters', [])
        if not chapters:
            chapters = pkg.get("chapters_data", pkg.get("chapters", []))
        self._log("[export] "+str(etype)+" pkg="+str(pkg_id))
        try:
            from app.core.gui_p2_bridge_exports import export_chapter_package_for_gui
            r = export_chapter_package_for_gui(chapter_package_id=pkg_id, chapters_data=chapters, export_types=[etype])
            ed = r.get("details", {}).get(etype, {})
            lines = [
                "导出格式: " + str(ed.get("export_type", etype)),
                "状态: " + str(ed.get("status", "?")),
                "章节数: " + str(ed.get("chapter_count", 0)),
                "字符数: " + str(ed.get("chars_count", 0)),
                "路径: " + str(ed.get("file_path", "(内存)")),
            ]
            self.ch_exp_lbl.config(text=chr(10).join(lines), foreground="#060")
            self._log("[export] "+str(etype)+" done: "+str(ed.get("status","?")))
        except Exception as e:
            self.ch_exp_lbl.config(text="导出失败: "+str(e), foreground="red")
            self._log("[export] fail: "+str(e))

    def _on_chapter_select(self, event):
        sel = self.ch_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        chapters = getattr(self, '_chapters', [])
        if idx < 0 or idx >= len(chapters):
            return
        ch = chapters[idx]
        lines = [
            "章节标题: " + str(ch.get("chapter_title", "")),
            "包含场景: " + str(ch.get("scene_count", 0)),
        ]
        titles = ch.get("scene_titles", [])
        if titles:
            lines.append("场景列表:")
            for t in titles[:8]:
                lines.append("  - " + str(t)[:60])
        summary = ch.get("chapter_summary", "")
        if summary:
            lines.append("摘要: " + str(summary)[:200])
        text_preview = ch.get("chapter_text_preview", ch.get("chapter_text", ""))
        if text_preview:
            lines.append("正文预览:")
            lines.append(str(text_preview)[:500])
        self.ch_preview_lbl.config(text=chr(10).join(lines), foreground="#333")


    def _update_review_result_view(self, result, st_lbl, iss_txt, sug_txt):
        if not isinstance(result, dict): return
        s = result.get("status", "warn")
        cp = result.get("check_pipeline", "?")
        st_lbl.config(text="result: " + str(s) + " | pipeline: " + str(cp), foreground=("#060" if s == "pass" else "#c60"))
        iss = result.get("issues", result.get("last_check_issues", []))
        iss_txt.config(state="normal"); iss_txt.delete("1.0", "end")
        for i, v in enumerate(iss, 1): iss_txt.insert("end", "  " + str(i) + ". " + str(v) + chr(10))
        if not iss: iss_txt.insert("end", "(no issues)")
        iss_txt.config(state="disabled")
        sug = result.get("suggested_changes", result.get("rewrite_instructions", []))
        sug_txt.config(state="normal"); sug_txt.delete("1.0", "end")
        for s2 in sug[:5]: sug_txt.insert("end", "  - " + str(s2)[:100] + chr(10))
        if not sug: sug_txt.insert("end", "(no suggestions)")
        sug_txt.config(state="disabled")

    def _show_rewrite_diff(self, result, bt, at, cl):
        if not isinstance(result, dict): return
        before = result.get("before_snapshot", {})
        after = result.get("after_snapshot", {})
        changed = result.get("changed_fields", [])
        if not before and not after:
            o = result.get("_original_draft_text", ""); n = result.get("draft_text", "")
            if o and n and o != n: before = {"draft_text": o[:500]}; after = {"draft_text": n[:500]}; changed = ["draft_text"]
        bt.delete("1.0", "end")
        if before:
            for k in list(before.keys()):
                v = before[k]
                if isinstance(v, list): v = chr(10).join(str(x) for x in v[:3])
                bt.insert("end", "[" + str(k) + "]\n" + str(v)[:300] + "\n\n")
        at.delete("1.0", "end")
        if after:
            for k in list(after.keys()):
                v = after[k]
                if isinstance(v, list): v = chr(10).join(str(x) for x in v[:3])
                at.insert("end", "[" + str(k) + "]\n" + str(v)[:300] + "\n\n")
        if changed:
            cl.config(text="changed: " + ", ".join(changed), foreground="#060")

    def _build_tab16_rag_eval(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  _ 检索评估  ")
        # Query
        qf = ttk.Frame(f)
        qf.pack(fill=tk.X, padx=8, pady=2)
        ttk.Label(qf, text="查询:").pack(side=tk.LEFT)
        self._eval_query = ttk.Entry(qf, width=50)
        self._eval_query.pack(side=tk.LEFT, padx=5)
        self._eval_query.insert(0, "默认测试查询")
        ttk.Button(qf, text="执行检索评估", command=self._do_eval_run).pack(side=tk.LEFT, padx=5)
        self._eval_status = ttk.Label(qf, text="就绪", foreground="#888")
        self._eval_status.pack(side=tk.LEFT, padx=5)
        # Block 1: plan
        b1 = ttk.LabelFrame(f, text="① 检索计划")
        b1.pack(fill=tk.X, padx=8, pady=2)
        self._eval_plan_text = scrolledtext.ScrolledText(b1, wrap=tk.WORD, font=("Consolas", 9), height=4)
        self._eval_plan_text.pack(fill=tk.X, padx=4, pady=2)
        # Block 2: retrieval vs rerank
        b2 = ttk.LabelFrame(f, text="② 检索 vs 重排对比")
        b2.pack(fill=tk.X, padx=8, pady=2)
        b2r = ttk.Frame(b2)
        b2r.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(b2r, text="重排模式:").pack(side=tk.LEFT)
        self._eval_rerank = ttk.Combobox(b2r, width=8, values=["mmr","rrf","none"])
        self._eval_rerank.set("mmr")
        self._eval_rerank.pack(side=tk.LEFT, padx=2)
        self._eval_compare_text = scrolledtext.ScrolledText(b2, wrap=tk.WORD, font=("Consolas", 9), height=6)
        self._eval_compare_text.pack(fill=tk.X, padx=4, pady=2)
        # Block 3: RAG metrics
        b3 = ttk.LabelFrame(f, text="③ RAG 评估指标")
        b3.pack(fill=tk.X, padx=8, pady=2)
        b3r = ttk.Frame(b3)
        b3r.pack(fill=tk.X, padx=4, pady=2)
        self._eval_cov_lbl = ttk.Label(b3r, text="覆盖度: -", font=("Segoe UI", 9), foreground="#333", wraplength=250)
        self._eval_cov_lbl.pack(side=tk.LEFT, padx=4)
        self._eval_hal_lbl = ttk.Label(b3r, text="幻觉风险: -", font=("Segoe UI", 9), foreground="#333", wraplength=250)
        self._eval_hal_lbl.pack(side=tk.LEFT, padx=4)
        self._eval_irr_lbl = ttk.Label(b3r, text="无关度: -", font=("Segoe UI", 9), foreground="#333", wraplength=250)
        self._eval_irr_lbl.pack(side=tk.LEFT, padx=4)
        # Block 4: actions
        b4 = ttk.LabelFrame(f, text="④ 建议动作")
        b4.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)
        self._eval_action_text = scrolledtext.ScrolledText(b4, wrap=tk.WORD, font=("Segoe UI", 9), height=4)
        self._eval_action_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        ttk.Label(f, text="你可以返回素材检索 Tab 调整来源类型、重排模式和筛选条件，再重新评估。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=8, pady=2)
        # Eval tab flow hint
        ttk.Label(f, text="你可以返回素材检索 Tab 调整来源类型、重排模式和筛选条件，再重新评估。",
            font=("Segoe UI", 8), foreground="#666").pack(anchor=tk.W, padx=8, pady=2)

    def _do_eval_run(self):
        q = self._eval_query.get().strip()
        self._log("[eval] run: " + q)
        self._eval_status.config(text="执行中...", foreground="#c60")
        try:
            from app.core.gui_rag_eval_bridge import plan_multi_atom_query, run_retrieval_and_rerank, build_rag_eval_summary
            plan = plan_multi_atom_query(q)
            results = run_retrieval_and_rerank(plan, top_k=5, rerank_mode=self._eval_rerank.get())
            summary = build_rag_eval_summary(plan, results)
            # Block 1: plan
            self._eval_plan_text.delete("1.0", "end")
            atoms = plan.get("atoms", [])
            for a in atoms:
                self._eval_plan_text.insert("end", "  atom: " + str(a.get("atom_text",""))[:60] + " | weight=" + str(a.get("weight","")) + " | slot=" + str(a.get("slot_id","")) + chr(10))
            if not atoms:
                self._eval_plan_text.insert("end", "  (no atoms from plan)" + chr(10))
            strategies = plan.get("strategies", results.get("strategies", []))
            if strategies:
                for s in strategies:
                    self._eval_plan_text.insert("end", "  strategy: " + str(s.get("strategy_name","")) + " k=" + str(s.get("k","")) + " rerank=" + str(s.get("use_rerank","")) + " role=" + str(s.get("expected_role","")) + chr(10))
            else:
                self._eval_plan_text.insert("end", "  strategy: baseline k=5 rerank=False role=对照" + chr(10))
                self._eval_plan_text.insert("end", "  strategy: " + self._eval_rerank.get() + " k=5 rerank=True role=主用" + chr(10))
            # Block 2: compare
            self._eval_compare_text.delete("1.0", "end")
            mode = self._eval_rerank.get()
            self._eval_compare_text.insert("end", "重排模式: " + mode + " | 对比: 原始检索 vs " + mode + " 重排" + chr(10) + chr(10))
            before = results.get("before", [])
            after = results.get("after", [])
            for i in range(max(len(before), len(after))):
                b = before[i] if i < len(before) else {}
                a = after[i] if i < len(after) else {}
                b_score = str(b.get("score", "")) if b else "-"
                a_score = str(a.get("score", "")) if a else "-"
                snippet = str(b.get("snippet", a.get("snippet", "")))[:50]
                self._eval_compare_text.insert("end", "  rank=" + str(i+1) + " | " + snippet + " | before=" + b_score + " after=" + a_score + chr(10))
            # Block 3: metrics
            metrics = results.get("metrics", {})
            cov = metrics.get("coverage", summary.get("coverage_score", 0))
            div = metrics.get("diversity", summary.get("diversity_score", 0))
            risk = summary.get("risk_score", summary.get("hallucination_risk", 0))
            self._eval_cov_lbl.config(text="覆盖度: " + chr(10) + str(round(cov*100, 1)) + "%" + chr(10) + "越高越好")
            self._eval_hal_lbl.config(text="幻觉风险: " + chr(10) + str(round(div*100, 1)) + "%" + chr(10) + "越低越好")
            self._eval_irr_lbl.config(text="无关度: " + chr(10) + str(round(risk*100, 1)) + "%" + chr(10) + "越低越好")
            # Block 4: actions
            self._eval_action_text.delete("1.0", "end")
            self._eval_action_text.insert("end", summary.get("recommended_action", "(无建议)") + chr(10))
            self._eval_action_text.insert("end", "覆盖: " + summary.get("coverage_summary", "") + chr(10))
            self._eval_action_text.insert("end", "风险: " + summary.get("risk_summary", "") + chr(10))
            self._eval_status.config(text="完成", foreground="#060")
        except Exception as e:
            self._eval_status.config(text="失败: " + str(e), foreground="red")
            self._log("[eval] fail: " + str(e))

    def _go_to_eval_tab(self):
        for i in range(self.notebook.index("end")):
            if chr(26816)+chr(32034)+chr(35780)+chr(20272) in self.notebook.tab(i, "text"):
                self.notebook.select(i)
                break

    def _do_search_and_eval(self):
        self._do_search()
        self._go_to_eval_tab()


    def _apply_world_pack(self):
        wp = self._wp_combo.get()
        self._log("[wp] apply: " + str(wp))


    def _do_publish_summary(self):
        pkg = getattr(self, '_ch_pkg', None)
        if not pkg:
            self.ch_pub_lbl.config(text="请先生成章节包", foreground="#c60")
            return
        try:
            from app.core.publish_manifest_builder import build_publish_manifest_bundle
            manifest = build_publish_manifest_bundle(pkg)
            # Build a simple summary
            export_types = ["markdown", "epub", "docx"]
            lines = [
                "发布摘要 - 来自章节包: " + str(pkg.get("chapter_package_id", "")),
                "章节数: " + str(pkg.get("chapter_count", 0)),
                "支持格式: " + ", ".join(export_types),
                "生成时间: " + str(pkg.get("timestamp", "(本次会话)")) if pkg.get("timestamp") else "生成时间: (本次会话)",
                "场景总数: " + str(pkg.get("scene_total_count", 0)),
                "来源: " + str(pkg.get("story_source_type", "")),
            ]
            self.ch_pub_lbl.config(text=chr(10).join(lines), foreground="#060")
            self._log("[publish] summary generated")
        except Exception as e:
            # Fallback: build summary from pkg directly
            lines = [
                "发布摘要 (bridge) - 来自: " + str(pkg.get("chapter_package_id", "")),
                "章节数: " + str(pkg.get("chapter_count", 0)),
                "场景数: " + str(pkg.get("scene_total_count", 0)),
            ]
            self.ch_pub_lbl.config(text=chr(10).join(lines), foreground="#060")
            self._log("[publish] summary (bridge): " + str(e)[:60])

    def _do_history_preview(self):
        try:
            import glob, json, os
            reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reports")
            candidates = []
            if os.path.isdir(reports_dir):
                for fpath in sorted(glob.glob(os.path.join(reports_dir, "*.json")), reverse=True)[:10]:
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if isinstance(data, dict) and any(k in data for k in ("exported_count", "exports_success", "obsidian", "export")):
                            candidates.append({
                                "file": os.path.basename(fpath),
                                "status": data.get("status", "ok"),
                                "detail": {k: data[k] for k in ("exported_count", "exports_success", "export_type") if k in data},
                            })
                    except Exception:
                        pass
            if candidates:
                lines = ["最近导出记录 (最近 " + str(min(len(candidates), 3)) + " 条):"]
                for c_rec in candidates[:3]:
                    status_icon = chr(10003) if c_rec.get("status") == "ok" else chr(10007)
                    lines.append("  " + status_icon + " " + c_rec.get("file", "")[:40])
                    detail = c_rec.get("detail", {})
                    if detail:
                        lines.append("      " + str(detail)[:80])
                self.ch_hist_lbl.config(text=chr(10).join(lines), foreground="#060")
            else:
                self.ch_hist_lbl.config(text="(暂无历史导出记录)", foreground="#888")
        except Exception as e:
            self.ch_hist_lbl.config(text="(历史加载失败: " + str(e)[:40] + ")", foreground="#c60")

def main():
    app = CreativeStudioGUI()
    app.run()


if __name__ == "__main__":
    main()