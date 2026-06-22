# Part 3：核心场景 pipeline 能力盘点报告

**执行范围：** `scene_expansion_builder.py`、`scene_draft_builder.py`、`scene_rewrite_runner.py`、`scene_rewriter.py`、`scene_polisher.py`、`final_prose_bundle_builder.py`，及相关辅助文件

---

## 一、pipeline 步骤总览

```
seed_bundle ──[expansion builder]──→ expansion_bundle
  │                                      │
  │                                  [draft builder]
  │                                      ↓
  │                                 draft_bundle
  │                                      │
  │                              [check runner / rewriter]
  │                                      ↓
  │                             rewritten_draft_bundle
  │                                      │
  │                              [polish handoff builder]
  │                                      ↓
  │                             polish_task → [polisher]
  │                                      │
  │                              [approval refresh]
  │                                      ↓
  │                             approval_bundle
  │                                      │
  │                              [final prose builder]
  │                                      ↓
  │                             final_approved_scene ✅
```

**所有 6 个模块** 在 v1.6.0 中已完整实现，纯函数、无 LLM、确定性规则。

---

## 二、每一步的结构化字段大盘点

### Step 1：scene_expansion_builder → expansion_bundle

**已完整实现** ✅ — v1.6.0-scene-expansion-pre

**输出 bundle 顶层字段：**

| 字段 | 类型 | 说明 | 是否可用于 GUI |
|---|---|---|---|
| `expansion_bundle_id` | str | e.g. `ex_20250618_091730` | ✅ 批次标识 |
| `source_seed_bundle_id` | str | 来源种子 bundle | ✅ **来源说明** |
| `source_blueprint_id` | str | 来源蓝图 ID | ✅ 来源说明 |
| `source_variant_id` | str | 来源变体 ID | ✅ 来源说明 |
| `status` | str | `"ok"` / `"fail"` | ✅ 批次状态 |
| `warnings` | list[str] | 来自种子层级的警告 prefixed | ✅ |
| `scene_requests` | list[dict] | 扩展请求列表 | — |

**每条 `scene_request` 字段：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `request_id` | e.g. `REQ1` | ✅ |
| `seed_id` | 来源种子 ID | ✅ **来源** |
| `stage_id` | e.g. `S1` | ✅ **阶段标识** |
| `scene_title` | 场景标题 | ✅ |
| `scene_objective` | 场景目标 | ✅ |
| `dramatic_question` | 戏剧性问题 | ✅ |
| `conflict_core` | 核心冲突 | ✅ |
| `relationship_focus` | 关系焦点列表 | ✅ |
| `must_keep` / `must_not_break` | 约束列表 | ✅ |
| `opening_image` / `ending_button` | 开场/结尾钩子 | ✅ |
| `emotional_temperature` | `"low"` / `"medium"` / `"high"` | ✅ **阶段标记** |
| `source_refs` | dict: seed_bundle_id, blueprint_id, variant_id, seed_index, stage_id, beat_refs, card_refs | ✅ **完整来源溯源** |
| `writer_input` | dict: tone_anchor, narrative_distance, forbidden_generic_lines | — |

> **关键发现：** `source_refs` 已经包含完整的**来源溯源链**（seed → blueprint → variant → beat → card），GUI 可以直接展示"来自蓝图 xxx 的第 y 阶段第 z 种子"

---

### Step 2：scene_draft_builder → draft_bundle

**已完整实现** ✅ — v1.6.0-scene-expansion-pre

**输出 bundle 顶层字段：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `draft_bundle_id` | e.g. `sd_20250618_...` | ✅ 批次标识 |
| `source_expansion_bundle_id` | 来源扩展 bundle | ✅ **来源** |
| `source_seed_bundle_id` | 来源种子 bundle | ✅ 来源 |
| `source_blueprint_id` / `source_variant_id` | 蓝图/变体 | ✅ 来源 |
| `status` | `"ok"` / `"fail"` | ✅ 批次状态 |
| `scene_drafts` | list[dict] | — |

**每条 `scene_draft` 字段：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `draft_id` | e.g. `D1` | ✅ **草稿标识** |
| `request_id` / `stage_id` | 关联扩展请求/阶段 | ✅ 阶段标记 |
| `scene_title` | 场景标题 | ✅ |
| `opening_paragraph` | 开场段落（规则合成文本） | ✅ **内容预览** |
| `scene_body_outline` | list[str] | ✅ |
| `relationship_turn` | str | ✅ |
| `conflict_progression` | str | ✅ |
| `emotional_curve` | str e.g. `"平静不安 -> 逐渐聚焦"` | ✅ **情绪曲线** |
| `closing_beat` | str | ✅ |
| `dialogue_hints` | list[str] | ✅ |
| `symbolic_object` | str | ✅ |
| `must_keep_applied` / `must_not_break_checked` | list[str] | ✅ 约束追踪 |
| `draft_text` | 完整合成文本 | ✅ **全文预览** |
| `outline_text` | 大纲文本 | ✅ |
| `source_refs` | dict: expansion_bundle_id, seed_bundle_id, blueprint_id, variant_id, request_index, seed_id, beat_refs, card_refs | ✅ **完整来源溯源** |

> **关键发现：** 每条 draft 都有完整的 `source_refs`（包含 expansion → seed → blueprint → variant → beat → card 全链路）、`stage_id`（阶段标记），以及 `emotional_curve`（情感线状态标记）。

---

### Step 3：scene_rewriter + scene_rewrite_runner → rewritten_draft_bundle

**已完整实现** ✅ — v1.6.0-g1-rewriter-pre

**单个 `rewrite_scene_draft` 输出字段：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `draft_id` / `request_id` | 标识 | ✅ |
| `rewrite_applied` | bool 是否执行了改写 | ✅ **操作标记** |
| `rewrite_priority` | `"low"` / `"medium"` / `"high"` | ✅ **优先级** |
| `source_issue_codes` | list[str] 来源质检问题码 | ✅ **质检结论** |
| `rewrite_targets` | list[str] 改写了哪些字段 | ✅ |
| `before_snapshot` | dict（7 个可改写字段的旧快照） | ✅ **差异对比** |
| `after_snapshot` | dict（新快照） | ✅ **差异对比** |
| `changed_fields` | list[str] 发生变化的字段 | ✅ |
| `preserved_must_keep` / `preserved_must_not_break` | list[str] | ✅ |
| `rewritten_text` | str 改写后全文 | ✅ |
| `rewritten_outline_text` | str 改写后大纲 | ✅ |
| `status` | `"pass"` / `"warn"` / `"fail"` | ✅ **改写状态** |
| `warnings` | list[str] | ✅ |
| `source_refs` | dict: source_draft_bundle_id, source_check_bundle_id, source_rewrite_bundle_id, draft_id, request_id, stage_id, variant_id, blueprint_id | ✅ **完整溯源** |

**runner 输出 bundle 额外字段：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `rewritten_bundle_id` | e.g. `rwd_20260618_...` | ✅ |
| `source_draft_bundle_id` | ✅ 来源 |
| `source_check_bundle_id` | ✅ 来源 |
| `source_rewrite_bundle_id` | ✅ 来源 |
| `quality` | dict: total_drafts, rewrite_applied_count, no_op_count, pass/warn/fail counts, average_target_coverage, must_keep/must_not_break preservation rates | ✅ **质量摘要** |
| `status` / `timestamp` | ✅ |

> **关键发现：** `before_snapshot` + `after_snapshot` + `changed_fields` 三者组合可以直接在前端实现**改写差异视图**（diff 展示）。`quality` 聚合数据可以提供改写批次的统览。

---

### Step 4：scene_polisher → polished draft

**已完整实现** ✅ — v1.6.0-h2-polish-pre

**单条 polish 操作：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `polish_targets` | list[str] 要润色的字段 | ✅ |
| `before_snapshot` / `after_snapshot` | dict（同 rewrite 结构） | ✅ **差异** |
| `changed_fields` | list[str] | ✅ |
| `notes` | list[str] 具体做了哪些润色 | ✅ |
| `warnings` | list[str] | ✅ |

> **关键发现：** polisher 没有独立的 bundle 标记——它是 runner 流程中的一步，输出 feed 进 `scene_approval_refresh_runner`。润色状态标记在 `polish_notes` 和 `changed_fields` 中。

---

### Step 5：final_prose_bundle_builder → final_approved_scene

**已完整实现** ✅ — v1.6.0-j-pre-final-approved-prose

**`build_final_approved_scene` 输出字段（成功时）：**

| 字段 | 说明 | GUI 可用 |
|---|---|---|
| `final_scene_id` | e.g. `FSC_D1` | ✅ **最终稿标识** |
| `approval_id` | 审批 ID | ✅ |
| `scene_id` / `task_id` / `draft_id` / `request_id` | 原始标识链 | ✅ 完整溯源 |
| `stage_id` | ✅ **阶段标记** |
| `approval_status` | `"approved"` | ✅ **审批状态** |
| `approval_gate` | `"pass"` | ✅ **审批关卡** |
| `scene_title` / `story_function` | ✅ |
| `tone_anchor` / `narrative_distance` | ✅ |
| `must_keep` / `must_not_break` | ✅ |
| `opening_paragraph` / `body_paragraphs` / `closing_paragraph` / `full_scene_text` | ✅ **最终全文** |
| `final_notes` | list[str] 包含`approved via scene approval refresh` 和 `content_source: revised/original` | ✅ **最终稿说明** |
| `content_source` | `"revised"` / `"original"` | ✅ **内容来源** |
| `source_variant_id` | ✅ |
| `refresh_recommendation` | ✅ |
| `source_trace` | dict: scene_approval_refresh_bundle_id, revised_scene_prose_bundle_id, scene_prose_bundle_id, handoff_bundle_id, approval_id, revised_scene_id, scene_id, task_id, draft_id, request_id, stage_id, variant_id, blueprint_id, seed_id | ✅ **全链路溯源** |
| `status` | `"pass"` / `"warn"` / `"fail"` | ✅ |

> **关键发现：** 这是**最完整的终结模型**。`source_trace` 包含了从 seed → blueprint → draft → revised → approval → final 的**完整溯源链路**。`content_source: "revised"` 明确标示最终稿来自改写稿还是原始稿。

---

## 三、能力 → 可显化字段映射表

| 能力 | 已有字段 | 可用于 GUI | 是后端已有但 GUI 未展示？ |
|---|---|---|---|
| **来源说明（From）** | `source_refs.blueprint_id`, `.seed_id`, `.variant_id`, `.beat_refs`, `.card_refs`，加上 `source_seed_bundle_id`, `source_expansion_bundle_id`, `source_draft_bundle_id` | ✅「来自蓝图 BP-001 的 S2 阶段种子 SC-003」 | **✅ 是——后端每个 bundle 都带了，GUI 全部未用** |
| **当前阶段（Where）** | `stage_id`（S1/S2/...）、`stage_index`、`stage_function`（exposition/rising_action/climax/...）、`emotional_temperature` | ✅ 显示「S2·冲突升级·情绪高张力」 | **✅ 是——draft 级字段，GUI 全部未用** |
| **草稿版本（Version）** | `version`（在 SceneDraft 模型中递增）、`draft_bundle_id` 带时间戳、`rewritten_bundle_id` 带时间戳 | ✅ 显示「v3·2025-06-18 改写」 | **✅ 是——SceneDraft 有 version 字段但 GUI 不读取** |
| **审批状态（Approval）** | `approval_status`（pending/approved/rejected）在 `scene_review_p2_bridge.set_approval_status` 中持久化 | ✅ 显示「已审批 ✓ / 待审批 …」 | **✅ 是——后端已实现 set/get，GUI 无对应按钮** |
| **改写差异（Diff）** | `before_snapshot` + `after_snapshot`（7 个字段）+ `changed_fields` | ✅ 展示「开场段落已改写」「情绪曲线已优化」 | **✅ 是——每条 rewrite 都带，GUI 完全未展示** |
| **改写质量摘要** | `quality`（改写覆盖率、must_keep 保留率、pass/warn/fail 计数） | ✅ 展示「97% 覆盖率·3 项改写应用」 | **✅ 是——runner 聚合数据，GUI 不读取** |
| **内容来源（最终稿）** | `content_source`（"revised"/"original"） | ✅ 展示「最终稿来源：改写稿」 | **✅ 是——final_prose_bundle 字段，GUI 不读取** |
| **全链路溯源（最终稿）** | `source_trace`（approval → revised_prose → prose → handoff → seed → blueprint） | ✅ 展示完整路径 | **✅ 是——最完整的数据，GUI 完全未展示** |

---

## 四、backend_only 能力（值得前台化）

| 能力 | 所在模块 | 当前用途 | 前台化价值 |
|---|---|---|---|
| **改写质量摘要（bundle 级）** | `scene_rewrite_runner.build_rewritten_draft_bundle` → `quality` dict | 下游 runner 决策 | 让用户看到「7 条 draft 中 5 条已改写，2 条无需改写，覆盖率 83%」 |
| **改写差异快照（draft 级）** | `scene_rewriter.rewrite_scene_draft` → `before_snapshot` / `after_snapshot` | 后续 polisher 参考 | 逐字段展示 before/after diff |
| **最终稿来源选择逻辑** | `final_prose_bundle_builder.select_final_scene_source` | 自动选择 revised > original | 告知用户「该最终稿来自改写稿(revised) 或 原始稿(original fallback)」 |
| **审批状态持久化** | `scene_review_p2_bridge.set_approval_status` | 持久化到 SceneDraft.metadata | 审批按钮「批准」「拒绝」「标记待改写」 |
| **emotional_temperature + stage_function 组合** | `scene_draft_builder._build_emotional_curve` | draft 内容生成 | 可视化展示「这一幕的情绪曲线：平静不安 → 冲突升级 → 对决」 |
| **must_keep / must_not_break 约束保留率** | `scene_rewrite_runner._build_rewrite_quality_summary` | 改写质量评估 | 展示「约束保留率: must_keep 100% / must_not_break 100%」 |

---

## 五、总结

**后端 pipeline 的成熟度：**
- 6 个核心模块全部 v1.6.0 稳定实现，纯函数、无 LLM、确定性
- 每条数据都带有**完整溯源链**（source_refs 从 seed → expansion → draft → rewritten → final）
- 有**改动追踪**（before_snapshot/after_snapshot/changed_fields）
- 有**质量聚合**（quality dict 含覆盖率、保留率、通过/警告/失败计数）
- 有**内容来源声明**（content_source: revised/original）

**但 GUI 只用了：**
- `draft_id` / `scene_id` / `check_report_id` —— 不到全部字段的 10%

**可立即可显化的字段（不用改后端）：**
- 来源溯源（`source_refs` 全链路）
- 阶段标记（`stage_id` + `stage_function`）
- 草稿版本（`version`）
- 审批状态（`approval_status`）
- 改写差异（`before_snapshot` / `after_snapshot`）
- 质量摘要（`quality` bundle）
- 最终稿来源（`content_source` + `final_notes`）
