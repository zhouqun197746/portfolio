"""
gui_component_renderer.py  v1.0.0-p2-gui-integration

Maps render adapter sections/component/props to Tkinter widgets.
Wraps the mapping logic so creative_studio_gui.py does NOT need
to interpret component types directly.

Usage:
    renderer = GuiComponentRenderer(parent_frame, state_manager, execute_callback)
    renderer.render_sections(render_model["sections"])

The execute_callback(action_request) is called when the user clicks
an action button. The callback should call
gui_backend_interface.execute_gui_action and feed the result
back into the state_manager and the renderer's result area.
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Any, Callable

from app.gui.action_response_parser import (
    summarize_action_response,
    format_debug_json,
)

# Import Chinese field label helpers (任务包14: 采集链中文主显示)
from app.core.gui_material_pipeline_bridge import cn_field, cn_term_help, cn_section_desc
import tkinter.font as tkfont


class GuiComponentRenderer:
    """Renders sections from a render model dict into Tkinter widgets."""

    def __init__(
        self,
        parent: tk.Widget,
        state_manager: Any,  # GuiStateManager
        execute_callback: Callable[[dict], None],
        log_callback: Callable[[str], None] = print,
    ):
        self._parent = parent
        self._state = state_manager
        self._execute_cb = execute_callback
        self._log = log_callback

        # Keep references to dynamic widgets so we can clear/replace
        self._section_frames: dict[str, ttk.LabelFrame] = {}
        self._result_texts: dict[str, tk.Widget] = {}
        self._debug_texts: dict[str, tk.Widget] = {}

    def clear_all(self):
        """Destroy all previously rendered section frames."""
        for frame in self._section_frames.values():
            frame.destroy()
        self._section_frames.clear()
        self._result_texts.clear()
        self._debug_texts.clear()

    def render_sections(self, sections: list[dict]):
        """Render all sections from a render model sections list."""
        self.clear_all()
        for section in sections:
            self._render_section(section)

    def refresh_result(self, action_id: str):
        """Re-render the result area for a specific action."""
        # Find the section that contains this action
        for sec_id, frame in self._section_frames.items():
            result_key = f"{sec_id}_result"
            if result_key in self._result_texts:
                response = self._state.get_result(action_id)
                summary = summarize_action_response(action_id, response)
                widget = self._result_texts.get(result_key)
                if widget and hasattr(widget, "delete"):
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", summary)

                # Debug area
                debug_widget = self._debug_texts.get(result_key)
                if debug_widget and hasattr(debug_widget, "delete"):
                    debug_widget.delete("1.0", tk.END)
                    if self._state.debug_mode:
                        debug_widget.insert("1.0", format_debug_json(response))
                    # If debug mode off, just show "(debug 模式关闭)"

    # ── Private helpers ─────────────────────────────────────

    def _render_section(self, section: dict):
        """Dispatch to the right renderer based on component type."""
        sec_id = section.get("section_id", "unknown")
        title = section.get("title", sec_id)
        component = section.get("component", "panel")
        props = section.get("props", {})

        frame = ttk.LabelFrame(self._parent, text=title, padding=8)
        frame.pack(fill=tk.BOTH, expand=False, padx=4, pady=4)
        self._section_frames[sec_id] = frame

        if component == "panel":
            self._render_panel_section(frame, sec_id, props)
        elif component == "search_panel":
            self._render_search_panel_section(frame, sec_id, props)
        elif component == "dashboard":
            self._render_dashboard_section(frame, sec_id, props)
        elif component == "metric_card":
            self._render_metric_card(frame, props)
        else:
            ttk.Label(frame, text=f"[未知组件类型: {component}]",
                      foreground="red").pack(anchor=tk.W)

    def _render_panel_section(self, frame: ttk.LabelFrame, sec_id: str, props: dict):
        """Render a generic panel section (e.g. bridge panel)."""
        inner = ttk.Frame(frame)
        inner.pack(fill=tk.BOTH, expand=True)

        # Show version and status
        version = props.get("version", "")
        if version:
            ttk.Label(inner, text=f"v: {version}", font=("Segoe UI", 8),
                      foreground="gray").pack(anchor=tk.W)

        # ── Bridge-specific: query entry ───────────────────────
        if sec_id == "bridge":
            self._render_bridge_query_entry(inner)

        # Input fields
        inputs = props.get("inputs", {})
        if isinstance(inputs, dict):
            for input_key, input_config in inputs.items():
                self._render_input_group(inner, input_key, input_config, sec_id)

        # Actions
        actions = props.get("actions", [])
        if isinstance(actions, list):
            self._render_action_buttons(inner, actions, sec_id)

        # Material/atom filters
        mat_filters = inputs.get("material_filters", [])
        atom_filters = inputs.get("atom_filters", [])
        if mat_filters or atom_filters:
            self._render_filter_fields(inner, mat_filters, atom_filters, sec_id)

        # Acceptance modes
        modes = inputs.get("metadata_acceptance_modes", [])
        if modes:
            self._render_acceptance_mode_selector(inner, modes, sec_id)

        # Result area
        self._render_result_area(inner, sec_id)

        # field_registry_ref
        ref = props.get("field_registry_ref", {})
        if isinstance(ref, dict):
            ttk.Label(inner, text=f"激活字段: {ref.get('active_field_count', 0)}",
                      font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W)

    def _render_search_panel_section(self, frame: ttk.LabelFrame, sec_id: str, props: dict):
        """Render the RAG search panel section."""
        inner = ttk.Frame(frame)
        inner.pack(fill=tk.BOTH, expand=True)

        # Query inputs
        queries = props.get("query_inputs", [])
        if isinstance(queries, list):
            for q in queries:
                self._render_query_input(inner, q, sec_id)

        # Facet groups (strict_filters / soft_preferences)
        facet_groups = props.get("facet_groups", [])
        if isinstance(facet_groups, list):
            for fg in facet_groups:
                self._render_facet_group(inner, fg, sec_id)

        # Rerank options
        rerank_opts = props.get("rerank_options", {})
        if rerank_opts:
            self._render_rerank_options(inner, rerank_opts, sec_id)

        # World context
        world_ctx = props.get("world_context", {})
        if world_ctx:
            self._render_world_context_selector(inner, world_ctx, sec_id)

        # Action buttons
        actions = props.get("actions", [])
        bridge_actions = [
            a for a in actions
            if isinstance(a, dict) and a.get("action_id") == "rerank_search_results"
        ]
        if not bridge_actions:
            # Fallback: create the search button ourselves
            search_btn = ttk.Button(
                inner, text="搜索并重排 (Rerank)",
                command=lambda: self._do_rerank(),
            )
            search_btn.pack(pady=4)
        else:
            self._render_action_buttons(inner, bridge_actions, sec_id)

        # World pack apply button (if supported)
        if world_ctx.get("supports_world_pack"):
            wp_frame = ttk.Frame(inner)
            wp_frame.pack(fill=tk.X, pady=2)
            ttk.Label(wp_frame, text="world_pack_id:").pack(side=tk.LEFT)
            wp_entry = ttk.Entry(wp_frame, width=30)
            wp_entry.pack(side=tk.LEFT, padx=4)
            wp_entry.insert(0, self._state.rag_selected_world_pack_id or "")
            wp_entry.bind("<KeyRelease>", lambda e: self._state.__setattr__(
                "rag_selected_world_pack_id", wp_entry.get() or None))

        # Result area
        self._render_result_area(inner, sec_id)

    def _render_dashboard_section(self, frame: ttk.LabelFrame, sec_id: str, props: dict):
        """Render the governance dashboard section."""
        inner = ttk.Frame(frame)
        inner.pack(fill=tk.BOTH, expand=True)

        # Section definitions — render with real data if available
        sections_list = props.get("sections", [])

        # Pull latest snapshot data from the state manager
        dash_result = self._state.get_result("refresh_governance_dashboard")
        snapshot_data = {}
        if dash_result and dash_result.get("status") == "pass":
            output = dash_result.get("output", {})
            snapshot_data = output.get("snapshot", {})

        if isinstance(sections_list, list):
            for s in sections_list:
                self._render_dashboard_subsection(inner, s, snapshot_data)

        # Drilldowns summary
        drilldowns = props.get("drilldowns", [])
        if isinstance(drilldowns, list) and drilldowns:
            dd_frame = ttk.LabelFrame(inner, text="可下钻", padding=4)
            dd_frame.pack(fill=tk.X, pady=2)
            for dd in drilldowns:
                dd_row = ttk.Frame(dd_frame)
                dd_row.pack(fill=tk.X)
                ttk.Label(dd_row, text=f"  {dd.get('from', '?')} → {dd.get('to', '?')}",
                         font=("Segoe UI", 8)).pack(side=tk.LEFT)
                btn = ttk.Button(dd_row, text="查看详情",
                                command=lambda d=dd: self._show_drilldown_detail(d))
                btn.pack(side=tk.RIGHT, padx=4)

        # Thresholds
        thresholds = props.get("thresholds", {})
        if isinstance(thresholds, dict) and thresholds:
            th_frame = ttk.LabelFrame(inner, text="阈值", padding=4)
            th_frame.pack(fill=tk.X, pady=2)
            for k, v in thresholds.items():
                ttk.Label(th_frame, text=f"  {k}: {v}",
                         font=("Segoe UI", 8)).pack(anchor=tk.W)

        # Refresh button
        btn = ttk.Button(
            inner, text="刷新仪表盘 (Refresh)",
            command=lambda: self._do_refresh_dashboard(),
        )
        btn.pack(pady=4)

        # Result area
        self._render_result_area(inner, sec_id)

    def _render_bridge_query_entry(self, parent: ttk.Frame):
        """Render the query entry for bridge panel (generate_task_cards)."""
        q_frame = ttk.LabelFrame(parent, text="创作需求 / Query", padding=4)
        q_frame.pack(fill=tk.X, pady=2)

        row = ttk.Frame(q_frame)
        row.pack(fill=tk.X)

        ttk.Label(row, text="查询文本:").pack(side=tk.LEFT)
        self._bridge_query_var = tk.StringVar(value=self._state.bridge_atom_filters.get("query", ""))
        query_entry = ttk.Entry(row, textvariable=self._bridge_query_var, width=60)
        query_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        query_entry.bind("<KeyRelease>", lambda e: self._state.bridge_atom_filters.__setitem__(
            "query", self._bridge_query_var.get()))

        # Creative level row
        cl_row = ttk.Frame(q_frame)
        cl_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(cl_row, text="创意等级 (0-3):").pack(side=tk.LEFT)
        self._bridge_cl_var = tk.StringVar(
            value=str(self._state.bridge_atom_filters.get("creative_level", 0)))
        cl_entry = ttk.Spinbox(cl_row, from_=0, to=3, textvariable=self._bridge_cl_var, width=5)
        cl_entry.pack(side=tk.LEFT, padx=2)
        cl_entry.bind("<KeyRelease>", lambda e: self._state.bridge_atom_filters.__setitem__(
            "creative_level", int(self._bridge_cl_var.get()) if self._bridge_cl_var.get().isdigit() else 0))

        # Count row
        ttk.Label(cl_row, text="生成数量:").pack(side=tk.LEFT, padx=(10, 0))
        self._bridge_count_var = tk.StringVar(
            value=str(self._state.bridge_atom_filters.get("count", 5)))
        count_entry = ttk.Spinbox(cl_row, from_=1, to=20, textvariable=self._bridge_count_var, width=5)
        count_entry.pack(side=tk.LEFT, padx=2)
        count_entry.bind("<KeyRelease>", lambda e: self._state.bridge_atom_filters.__setitem__(
            "count", int(self._bridge_count_var.get()) if self._bridge_count_var.get().isdigit() else 5))

    def _render_input_group(self, parent: ttk.Frame, key: str, config: Any, sec_id: str):
        """Render a single input group from bridge panel inputs."""
        if isinstance(config, list):
            # List of filter definitions
            sub = ttk.LabelFrame(parent, text=key, padding=4)
            sub.pack(fill=tk.X, pady=2)
            for item in config:
                if isinstance(item, dict):
                    fid = item.get("id", "?")
                    lbl = item.get("label", item.get("label_id", fid))
                    ttk.Label(sub, text=f"  {lbl} ({item.get('type', '?')})",
                             font=("Segoe UI", 8)).pack(anchor=tk.W)
        elif isinstance(config, dict):
            sub = ttk.LabelFrame(parent, text=key, padding=4)
            sub.pack(fill=tk.X, pady=2)
            for k, v in config.items():
                ttk.Label(sub, text=f"  {k}: {v}",
                         font=("Segoe UI", 8)).pack(anchor=tk.W)
        else:
            ttk.Label(parent, text=f"{key}: {config}",
                     font=("Segoe UI", 8)).pack(anchor=tk.W)

    def _render_filter_fields(
        self,
        parent: ttk.Frame,
        mat_filters: list,
        atom_filters: list,
        sec_id: str,
    ):
        """Render material and atom filter sections."""
        if mat_filters:
            mf = ttk.LabelFrame(parent, text="素材过滤条件", padding=4)
            mf.pack(fill=tk.X, pady=2)
            for fdef in mat_filters:
                self._render_single_filter(mf, fdef, "bridge_material_filters", sec_id)

        if atom_filters:
            af = ttk.LabelFrame(parent, text="原子过滤条件", padding=4)
            af.pack(fill=tk.X, pady=2)
            for fdef in atom_filters:
                self._render_single_filter(af, fdef, "bridge_atom_filters", sec_id)

    def _render_single_filter(self, parent: ttk.Frame, fdef: dict, target_attr: str, sec_id: str):
        """Render a single filter field with Entry widget."""
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=1)

        fid = fdef.get("id", "?")
        lbl = fdef.get("label", fdef.get("label_id", fid))

        if fdef.get("type") == "enum":
            ttk.Label(row, text=f"{lbl}:").pack(side=tk.LEFT)
            options = fdef.get("options", [])
            var = tk.StringVar(value=options[0] if options else "")
            combo = ttk.Combobox(row, textvariable=var, values=options, width=20)
            combo.pack(side=tk.LEFT, padx=2)
            combo.bind("<<ComboboxSelected>>",
                       lambda e, f=fid: self._update_filter_state(target_attr, f, var.get()))
        else:
            ttk.Label(row, text=f"{lbl}:").pack(side=tk.LEFT)
            entry = ttk.Entry(row, width=25)
            entry.pack(side=tk.LEFT, padx=2)
            entry.bind("<KeyRelease>",
                       lambda e, f=fid: self._update_filter_state(target_attr, f, entry.get()))

    def _update_filter_state(self, target_attr: str, field_name: str, value: str):
        """Update state manager filters."""
        filters = getattr(self._state, target_attr, {})
        if value:
            filters[field_name] = value
        else:
            filters.pop(field_name, None)

    def _render_acceptance_mode_selector(self, parent: ttk.Frame, modes: list, sec_id: str):
        """Render a Combobox for metadata_acceptance_mode selection."""
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="元数据接受模式:").pack(side=tk.LEFT)
        var = tk.StringVar(value=self._state.bridge_metadata_acceptance_mode)
        combo = ttk.Combobox(row, textvariable=var, values=modes, width=25)
        combo.pack(side=tk.LEFT, padx=2)
        combo.bind("<<ComboboxSelected>>",
                   lambda e: self._state.__setattr__("bridge_metadata_acceptance_mode", var.get()))

    def _render_query_input(self, parent: ttk.Frame, qdef: dict, sec_id: str):
        """Render a single query input row."""
        qid = qdef.get("id", "?")
        lbl = qdef.get("label", qdef.get("label_id", qid))

        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        if qdef.get("type") == "enum":
            ttk.Label(row, text=f"{lbl}:").pack(side=tk.LEFT)
            options = qdef.get("options", [])
            var = tk.StringVar(value=options[0] if options else "")
            combo = ttk.Combobox(row, textvariable=var, values=options, width=25)
            combo.pack(side=tk.LEFT, padx=2)
            if qid == "rag_query":
                combo.destroy()
                # rag_query should be a text entry, not enum
                ttk.Label(row, text="检索查询:").pack(side=tk.LEFT)
                q_entry = ttk.Entry(row, width=50)
                q_entry.pack(side=tk.LEFT, padx=2)
                q_entry.bind("<KeyRelease>",
                             lambda e: self._state.__setattr__("rag_query", q_entry.get()))
        else:
            ttk.Label(row, text=f"{lbl}:").pack(side=tk.LEFT)
            entry = ttk.Entry(row, width=50)
            entry.pack(side=tk.LEFT, padx=2)
            if qid == "rag_query":
                entry.bind("<KeyRelease>",
                           lambda e: self._state.__setattr__("rag_query", entry.get()))
            elif qid == "storyline_id":
                entry.bind("<KeyRelease>",
                           lambda e: self._state.__setattr__("rag_strict_filters",
                                                             {"storyline_slot": entry.get()}))

    def _render_facet_group(self, parent: ttk.Frame, fg: dict, sec_id: str):
        """Render a strict_filter / soft_preferences facet group."""
        group_id = fg.get("group_id", "?")
        lbl = fg.get("label", fg.get("label_id", group_id))
        fields = fg.get("fields", [])

        group_frame = ttk.LabelFrame(parent, text=lbl, padding=4)
        group_frame.pack(fill=tk.X, pady=2)

        target_attr = "rag_strict_filters" if group_id == "strict_filters" else "rag_soft_preferences"

        for field_name in fields:
            row = ttk.Frame(group_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"{field_name}:").pack(side=tk.LEFT)
            entry = ttk.Entry(row, width=30)
            entry.pack(side=tk.LEFT, padx=2)
            entry.bind("<KeyRelease>",
                       lambda e, fn=field_name: self._update_filter_state(
                           target_attr, fn, entry.get()))

    def _render_rerank_options(self, parent: ttk.Frame, opts: dict, sec_id: str):
        """Render rerank mode selector."""
        modes = opts.get("modes", [])
        default = opts.get("default_mode", "mmr")
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="重排模式:").pack(side=tk.LEFT)
        var = tk.StringVar(value=self._state.rag_rerank_mode or default)
        combo = ttk.Combobox(row, textvariable=var, values=modes, width=15)
        combo.pack(side=tk.LEFT, padx=2)
        combo.bind("<<ComboboxSelected>>",
                   lambda e: self._state.__setattr__("rag_rerank_mode", var.get()))

        # top_k
        ttk.Label(row, text="top_k:").pack(side=tk.LEFT, padx=(10, 0))
        tk_var = tk.StringVar(value=str(self._state.rag_top_k))
        k_entry = ttk.Entry(row, textvariable=tk_var, width=6)
        k_entry.pack(side=tk.LEFT, padx=2)
        k_entry.bind("<KeyRelease>",
                     lambda e: self._state.__setattr__(
                         "rag_top_k", int(tk_var.get()) if tk_var.get().isdigit() else 5))

    def _render_world_context_selector(self, parent: ttk.Frame, ctx: dict, sec_id: str):
        """Render a world pack selector in the RAG panel."""
        pass  # Handled inline in _render_search_panel_section

    def _render_action_buttons(self, parent: ttk.Frame, actions: list, sec_id: str):
        """Render action buttons for a section."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=4)

        for action_def in actions:
            if isinstance(action_def, str):
                aid = action_def
                lbl = aid
            elif isinstance(action_def, dict):
                aid = action_def.get("action_id", "?")
                lbl = action_def.get("label", action_def.get("label_id", aid))
            else:
                continue

            btn = ttk.Button(
                btn_frame,
                text=lbl,
                command=lambda a=aid: self._do_action(a),
            )
            btn.pack(side=tk.LEFT, padx=2)

    def _show_drilldown_detail(self, drilldown: dict):
        """Show drilldown detail in a popup window."""
        from_id = drilldown.get("from", "?")
        to_id = drilldown.get("to", "?")

        win = tk.Toplevel(self._parent)
        win.title(f"下钻详情: {from_id} → {to_id}")
        win.geometry("600x400")
        win.minsize(400, 300)

        text = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Fetch related data from state manager
        dash_result = self._state.get_result("refresh_governance_dashboard")
        snapshot = {}
        bundle_info = {}
        if dash_result and dash_result.get("status") == "pass":
            output = dash_result.get("output", {})
            snapshot = output.get("snapshot", {})
            model = output.get("dashboard_model", {})
            if isinstance(model, dict):
                bundle_info = {
                    "version": model.get("version", ""),
                    "bundle_id": model.get("gui_governance_dashboard_bundle_id", ""),
                    "timestamp": model.get("timestamp", ""),
                }

        lines = [f"下钻: {from_id} → {to_id}", "=" * 40, ""]

        # Section snapshot data
        if from_id in snapshot:
            lines.append(f"[{from_id}] 快照数据:")
            snap = snapshot[from_id]
            if isinstance(snap, dict):
                for k, v in snap.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"  {snap}")
            lines.append("")

        lines.append(f"目标 bundle 类型: {to_id}")
        if bundle_info:
            lines.append(f"数据版本: {bundle_info.get('version', '?')}")
            lines.append(f"Bundle ID: {bundle_info.get('bundle_id', '?')[:50]}...")
        lines.append("")
        lines.append("(实际 drilldown 数据待下游 bundle 就绪后填充)")

        text.insert(tk.END, "\n".join(lines))
        text.config(state=tk.DISABLED)

    def _render_metric_card(self, parent: ttk.Frame, props: dict):
        """Render a metric_card component (labels summary etc)."""
        labels = props.get("labels", [])
        total = props.get("total", 0)

        inner = ttk.Frame(parent)
        inner.pack(fill=tk.X, padx=4, pady=2)

        ttk.Label(inner, text=f"标签总数: {total}",
                 font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)

        if isinstance(labels, list):
            text_widget = scrolledtext.ScrolledText(
                inner, wrap=tk.WORD, font=("Consolas", 8), height=6)
            text_widget.pack(fill=tk.BOTH, expand=True, pady=2)
            for lbl in labels:
                lid = lbl.get("id", "?")
                zh = lbl.get("zh-CN", "")
                en = lbl.get("en-US", "")
                text_widget.insert(tk.END, f"{lid}: {zh} / {en}\n")
            text_widget.config(state=tk.DISABLED)

    def _render_dashboard_subsection(self, parent: ttk.Frame, subsection: dict,
                                      snapshot_data: dict | None = None):
        """Render a single dashboard subsection (audit, risk, lineage, ops) with real data."""
        sec_id = subsection.get("section_id", "?")
        lbl = subsection.get("label", subsection.get("label_id", sec_id))
        metrics = subsection.get("metrics", [])

        sub = ttk.LabelFrame(parent, text=lbl, padding=4)
        sub.pack(fill=tk.X, pady=2)

        # Get real snapshot values for this section
        snap_metrics = {}
        if snapshot_data:
            if sec_id in snapshot_data:
                snap_metrics = snapshot_data[sec_id]
            elif "meta" in snapshot_data:
                # If snapshot contains meta at top-level, try nested
                for top_key in ("audit", "risk", "lineage", "ops"):
                    if top_key == sec_id and top_key in snapshot_data:
                        snap_metrics = snapshot_data[top_key]
                        break

        # ── Chinese label mapping for UI display ────────────────
        CHINESE_LABELS: dict[str, str] = {
            "event_count": "事件总数",
            "recent_actions": "最近操作",
            "approval_pending_count": "待审批数量",
            "task_card_count": "任务卡数",
            "blueprint_count": "蓝图数",
            "scene_draft_count": "场景草稿数",
            "check_report_count": "质检报告数",
            "open_risks": "开放风险",
            "high_severity_risks": "高风险项",
            "risk_trend": "风险趋势",
            "legacy_fallback_count": "遗留回退数",
            "missing_refs": "缺失引用",
            "lineage_nodes": "流转节点数",
            "lineage_edges": "完整链路数",
            "latest_bundle_links": "链路详情",
            "queue_depth": "队列深度",
            "error_count": "错误数",
            "warning_count": "警告数",
            "freshness_status": "最近活跃度",
            "total_chains": "链路总数",
            "complete_chains": "完整链路",
            "broken_chains": "断链数",
            "worst_slot": "最薄弱环节",
        }

        # ── Governance section ID Chinese headings ───────
        SECTION_HEADINGS: dict[str, str] = {
            "audit": "审计摘要",
            "risk": "风险状态",
            "lineage": "流转链路",
            "ops": "运营状态",
        }

        # Use Chinese heading if available
        zh_heading: str = str(SECTION_HEADINGS.get(sec_id, lbl or sec_id))
        sub.configure(text=zh_heading)

        for metric in metrics:
            if metric in snap_metrics:
                value = snap_metrics[metric]
                cn_label = CHINESE_LABELS.get(metric, metric)
                display = f"  · {cn_label}: {value}"

                # Handle nested dicts (e.g. missing_refs, latest_bundle_links)
                if isinstance(value, dict):
                    # Display sub-fields
                    for sub_k, sub_v in value.items():
                        sub_cn = CHINESE_LABELS.get(sub_k, sub_k)
                        sub_display = f"    · {sub_cn}: {sub_v}"
                        if isinstance(sub_v, (int, float)) and sub_v > 0 and sub_k in (
                            "missing_blueprint_id", "missing_seed_bundle_id",
                            "broken_chains",
                        ):
                            ttk.Label(sub, text=sub_display,
                                     font=("Segoe UI", 8), foreground="#cc3300").pack(anchor=tk.W)
                        else:
                            ttk.Label(sub, text=sub_display,
                                     font=("Segoe UI", 8), foreground="#006600").pack(anchor=tk.W)
                elif isinstance(value, list) and metric == "recent_actions":
                    if value:
                        ttk.Label(sub, text=f"  · {cn_label}:",
                                 font=("Segoe UI", 8, "bold")).pack(anchor=tk.W)
                        for act in value[:5]:
                            act_id = act.get("draft_id", "?")
                            act_status = act.get("status", "?")
                            act_ts = act.get("timestamp", "")[:19]
                            ttk.Label(sub, text=f"    {act_id} → {act_status} @ {act_ts}",
                                     font=("Segoe UI", 7), foreground="gray").pack(anchor=tk.W)
                    else:
                        ttk.Label(sub, text=f"  · {cn_label}: (无)",
                                 font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W)
                elif metric == "risk_trend":
                    # Color-code risk trend
                    trend_color = {
                        "stable": "#006600",
                        "watch": "#cc6600",
                        "elevated": "#cc0000",
                    }.get(str(value), "#006600")
                    ttk.Label(sub, text=display,
                             font=("Segoe UI", 8, "bold"), foreground=trend_color).pack(anchor=tk.W)
                elif metric == "freshness_status":
                    freshness_color = {
                        "active": "#006600",
                        "stale": "#cc6600",
                        "cold": "#cc0000",
                        "unavailable": "gray",
                    }.get(str(value), "gray")
                    freshness_lbl = {
                        "active": "活跃",
                        "stale": "较旧",
                        "cold": "长期未活动",
                        "unavailable": "暂未接入",
                    }.get(str(value), str(value))
                    ttk.Label(sub, text=f"  · {cn_label}: {freshness_lbl}",
                             font=("Segoe UI", 8, "bold"), foreground=freshness_color).pack(anchor=tk.W)
                elif metric == "queue_depth" and isinstance(value, str):
                    ttk.Label(sub, text=f"  · {cn_label}: {value}",
                             font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W)
                else:
                    # Highlight important values
                    if isinstance(value, (int, float)) and value > 0 and metric in (
                        "open_risks", "high_severity_risks", "error_count", "warning_count",
                        "needs_review_count", "reject_count", "approval_pending_count",
                        "broken_chains", "legacy_fallback_count",
                    ):
                        ttk.Label(sub, text=display,
                                 font=("Segoe UI", 8, "bold"), foreground="red").pack(anchor=tk.W)
                    else:
                        ttk.Label(sub, text=display,
                                 font=("Segoe UI", 8), foreground="#006600").pack(anchor=tk.W)
            else:
                ttk.Label(sub, text=f"  · {CHINESE_LABELS.get(metric, metric)}: (未接入)",
                         font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W)

    def _render_result_area(self, parent: ttk.Frame, sec_id: str):
        """Render a result display area (summary text + optional debug JSON)."""
        result_key = f"{sec_id}_result"

        # Summary text
        result_frame = ttk.LabelFrame(parent, text="结果", padding=4)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        result_text = scrolledtext.ScrolledText(
            result_frame, wrap=tk.WORD, font=("Consolas", 9), height=5)
        result_text.pack(fill=tk.BOTH, expand=True)
        result_text.insert(tk.END, "(尚未执行操作)")
        self._result_texts[result_key] = result_text

        # Debug JSON (collapsible via debug mode toggle)
        debug_frame = ttk.LabelFrame(parent, text="Debug JSON", padding=4)
        debug_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        debug_text = scrolledtext.ScrolledText(
            debug_frame, wrap=tk.WORD, font=("Consolas", 8), height=4)
        debug_text.pack(fill=tk.BOTH, expand=True)
        debug_text.insert(tk.END, "(debug 模式关闭时隐藏)")
        self._debug_texts[result_key] = debug_text

    # ── Action execution ────────────────────────────────────

    def _do_action(self, action_id: str):
        """Dispatch action execution via callback."""
        self._log(f"[P2] 触发动作: {action_id}")
        if action_id == "rerank_search_results":
            self._do_rerank()
        elif action_id == "apply_world_content_pack":
            self._do_apply_world()
        elif action_id == "refresh_governance_dashboard":
            self._do_refresh_dashboard()
        elif action_id == "generate_task_cards":
            self._do_generate_task_cards()
        elif action_id == "generate_scene_seeds":
            self._do_generate_scene_seeds()
        else:
            self._log(f"[P2] 未知动作: {action_id}")

    def _do_rerank(self):
        from app.gui.action_request_builder import build_rerank_request
        snap = self._state.snapshot_rag_request()
        req = build_rerank_request(snap)
        self._execute_cb(req)

    def _do_apply_world(self):
        from app.gui.action_request_builder import build_apply_world_pack_request
        snap = self._state.snapshot_world_pack_request()
        req = build_apply_world_pack_request(snap)
        self._execute_cb(req)

    def _do_refresh_dashboard(self):
        from app.gui.action_request_builder import build_refresh_dashboard_request
        snap = self._state.snapshot_governance_request()
        req = build_refresh_dashboard_request(snap)
        self._execute_cb(req)

    def _do_generate_task_cards(self):
        from app.gui.action_request_builder import build_generate_task_cards_request
        snap = self._state.snapshot_bridge_task_cards_request()
        req = build_generate_task_cards_request(snap)
        self._execute_cb(req)

    def _do_generate_scene_seeds(self):
        from app.gui.action_request_builder import build_generate_scene_seeds_request
        snap = self._state.snapshot_bridge_scene_seeds_request()
        req = build_generate_scene_seeds_request(snap)
        self._execute_cb(req)
