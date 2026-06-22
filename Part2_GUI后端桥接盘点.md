# Part 2：GUI → 后端桥接子包盘点报告

**执行范围：** `app/core/gui_p2_bridge_exports.py`、`app/core/scene_review_p2_bridge.py`、`app/core/scene_write_p2_bridge.py`、`app/core/scene_seed_p2_bridge.py`、`app/core/scene_writer.py`、`app/core/scene_rewriter.py`

---

## 一、动作路由总表

| # | 行为（GUI 触发点） | GUI 函数 | 桥接函数（gui_p2_bridge_exports） | 后端函数 | 路径类型 | 状态字段 |
|---|---|---|---|---|---|---|
| 1 | 生成场景种子（主工位 Tab ④） | `_p2_do_generate_scene_seeds` | `generate_scene_seeds_from_blueprint` | `scene_seed_p2_bridge.generate_scene_seeds_via_blueprint` → `scene_seed_builder` | **bridge**（实际走的是 `via_blueprint`，但 GUI 传入 `blueprint_bundle={}` 空字典，走的是 legacy fallback → `generate_scene_seeds_legacy`） | `seed_pipeline` = `"p2_mainline"` / `"legacy_fallback"`；`origin_path` = `"current"` / `"bridge"` / `"mixed"` |
| 2 | 生成场景种子（增强包 Tab 🎬） | `_do_refresh_scene_seeds` / `_do_generate_blueprint_seed` | `gui_category1_scene_seed_service.generate_scene_seed_for_gui` → `scene_seed_p2_bridge.generate_scene_seeds_legacy` | 同 1，但包装了 origin_path 判定 | **bridge**（`scene_seeds_legacy` 是旧路径包装） | `seed_pipeline`、`origin_path`、`warnings`、`material_ids` |
| 3 | 发送到场景扩写（Tab ④→⑤） | `_seed_send_to_scene_write` | 无桥接调用 —— **纯前端 tab 切换** | 无 | **none**（不传任何数据） | 无 |
| 4 | 种子 handoff（增强包 Tab 🎬 → writer/scene_card/draft） | `_do_seed_handoff` | `gui_scene_seed_bridge.handoff_scene_seed` | 后端不支持真正写入，**返回前端辅助结果** | **frontend_assisted**（文档里明说"当前后端不支持真正写入"） | `effect` = `"frontend_assisted"`（纯前端手递手） |
| 5 | 扩写场景（Tab ⑤） | `_do_write_scene` | `write_scene`（别名 = `write_scene_via_p2`） | `scene_write_p2_bridge.write_scene_via_p2` → `app.core.scene_writer.write_scene`（P2 结构化组装，无 LLM） | **current**（P2 主路径，失败时降级 `write_scene_legacy` → `app.generation.scene_writer.write_scene`） | `scene_pipeline` = `"p2_mainline"` / `"legacy"` / `"legacy_failed"`；`blueprint_id`；`stage_name`；`stage_index`；`seed_bundle_id`；`source_trace` |
| 6 | 质检（Tab ⑥） | `_do_check_scene` | `check_scene`（别名 = `check_scene_via_p2`） | `scene_review_p2_bridge.check_scene_via_p2` → `scene_check_runner.build_scene_check_bundle`（P2 质检器） | **current**（P2 主路径，失败时降级 `check_scene_legacy` → `app.quality.scene_checker.SceneChecker`） | `check_pipeline` = `"p2_mainline"` / `"legacy"` / `"legacy_failed"`；`check_report_id`；`last_check_status`；`last_check_issues` |
| 7 | 改写（Tab ⑥） | `_do_rewrite_scene` | `rewrite_scene`（别名 = `rewrite_scene_via_p2`） | `scene_review_p2_bridge.rewrite_scene_via_p2` → `app.core.scene_rewriter.rewrite_scene_draft`（P2 结构化改写，无 LLM） | **current**（P2 主路径，失败时降级 `rewrite_scene_legacy` → `app.generation.scene_rewriter.rewrite_scene_from_check`） | `scene_pipeline` = `"p2_mainline"` / `"legacy"` / `"legacy_failed"`；`version`；`blueprint_id` |
| 8 | 设置审批状态 | `_send_to_export_sync`（间接使用） | `set_approval_status` | `scene_review_p2_bridge.set_approval_status` → 更新 `SceneDraft.metadata["approval_status"]` | **current**（纯 metadata 字段更新） | `approval_status` = `"pending"` / `"approved"` / `"rejected"` |
| 9 | 发送到导出与同步（Tab ⑤/⑥ → ⑦） | `_send_to_export_sync(source_type)` | 无后端调用——**前端构建 ExportableObject + 切 tab** | 不调用任何后端 | **frontend_only** | `ExportableObject.object_type`、`source_stage`、`approval_status`、`export_ready` |
| 10 | 导出到 Obsidian（Tab ⑦） | `_do_export_obsidian` | `export_to_obsidian` | `app.integrations.obsidian_exporter.export_*` | **current**（独立集成层，非 P2 但稳定） | `status`、`target`、`type` |
| 11 | 同步到 Notion（Tab ⑦） | `_do_notion_sync` | `sync_to_notion` | `app.integrations.notion_sync_adapter.sync_to_notion` | **current**（独立集成层） | `status`、`target`、`type` |

---

## 二、路径类型判定依据

### 每个关键动作的详细分析

#### ① seed → expansion（种子→扩写）

| 维度 | 现状 |
|---|---|
| **GUI 是否有触发点？** | 主工位 Tab ④ 有「发送到场景扩写」按钮，但**只切 tab，不传种子数据**。增强包 Tab 🎬 有 handoff 按钮，但只是 **frontend_assisted**，后端不真正写入 |
| **走的路径类型** | **none → frontend_assisted**（无实际数据传递） |
| **已存在的状态字段可用于 GUI** | `seed_bundle_id`、`seed_title`、`seed_text_preview`、`origin_path`、`source_trace` 存在于 P2 bridge 的输出 dict 中，**但 GUI 从来不读取也不展示** |

#### ② expansion → draft（扩写→草稿）

| 维度 | 现状 |
|---|---|
| **GUI 是否有触发点？** | 有——「扩写场景」按钮（`_do_write_scene`）。但输入是**用户手动键入的描述**，不是上游种子/任务卡 |
| **走的路径类型** | **current**（P2 主路径 `write_scene_via_p2`，失败时 legacy fallback） |
| **已存在的状态字段** | `scene_pipeline`（`"p2_mainline"`/`"legacy"`）——这个字段**每个返回值都带了**；`blueprint_id`、`stage_name`、`seed_bundle_id`、`source_trace` 也在返回 dict 里但 GUI 只保存了 `_last_created_scene_id` 一个字段 |

#### ③ draft → review（草稿→质检）

| 维度 | 现状 |
|---|---|
| **GUI 是否有触发点？** | 有——「质检」按钮（`_do_check_scene`）。但需要**用户手动输入 scene ID** |
| **走的路径类型** | **current**（P2 主路径 `check_scene_via_p2`，失败时 legacy fallback） |
| **已存在的状态字段** | `check_pipeline`（`"p2_mainline"`/`"legacy"`）、`check_report_id`、`last_check_status`、`last_check_issues`。`SceneDraft.metadata` 写入了 `last_check_report_id`、`last_check_status`、`last_check_issues`，持久化了 |

#### ④ review → rewrite（质检→改写）

| 维度 | 现状 |
|---|---|
| **GUI 是否有触发点？** | 有——「改写」按钮（`_do_rewrite_scene`）。同样需要**手动输入 scene ID** |
| **走的路径类型** | **current**（P2 主路径 `rewrite_scene_via_p2`，失败时 legacy fallback） |
| **已存在的状态字段** | `scene_pipeline`、`version`、`blueprint_id`。**新 SceneDraft 自动递增 version**，可以做版本追踪 |

#### ⑤ rewrite → final（改写→最终稿 → 导出）

| 维度 | 现状 |
|---|---|
| **GUI 是否有触发点？** | 有——「发送到导出与同步」按钮（`_send_to_export_sync`）。但也是**前端级别**的 ExportableObject 构建 + tab 切换 |
| **走的路径类型** | **frontend_only**（不发后端），`ExportableObject` 只在 GUI 内存中存在 |
| **已存在的状态字段** | `approval_status`（"pending" / "approved" / "rejected"）可以持久化到 SceneDraft.metadata。**P2 bridge 的 `set_approval_status` 是 current 路径，但 GUI 没有对应的按钮** |

---

## 三、三套路径体系的分布现状

### Current（P2 主链路）—— 已有且可用

| 模块 | 函数 | GUI 使用了吗？ |
|---|---|---|
| `scene_write_p2_bridge.write_scene_via_p2` | ✅ strong | **部分**——按钮触发正确，但传递的是用户手动输入，不是 seed_bundle |
| `scene_review_p2_bridge.check_scene_via_p2` | ✅ strong | **部分**——触发正确，但需要手动输入 ID（不能自动取 `_last_created_scene_id`） |
| `scene_review_p2_bridge.rewrite_scene_via_p2` | ✅ strong | **部分**——同上 |
| `scene_review_p2_bridge.set_approval_status` | ✅ strong | **未使用**——GUI 没有对应的「批准/拒绝」按钮 |

### Bridge（但未达到 current）—— 有桥接但走旧路

| 模块 | 函数 | 问题 |
|---|---|---|
| `scene_seed_p2_bridge.generate_scene_seeds_via_blueprint` | 已包装为 `generate_scene_seeds_from_blueprint` | GUI 传入 `blueprint_bundle={}` 空字典，导致**必定降级到 legacy** |
| `gui_category1_scene_seed_service.generate_scene_seed_for_gui` | 调用 `generate_scene_seeds_legacy` | 文档自述：`"bridge"`（legacy 路径） |

### Legacy / frontend_only—— 还无 current

| 行为 | 模块 | 说明 |
|---|---|---|
| seed → expansion 数据传递 | 无 | **目前没有真正的后端数据传递** |

---

## 四、关键发现：已有状态字段汇总（GUI 目前完全没利用）

以下字段**已经存在于 P2 bridge 的返回值中**，但 GUI 只取了 `_last_created_scene_id` / `_last_check_result` 两个字段，其他信息全被浪费了：

```
scene_write_via_p2 返回 dict 中：
  ✓ scene_pipeline     → "p2_mainline" | "legacy" | "legacy_failed"
  ✓ blueprint_id       → 来源蓝图 ID
  ✓ stage_name         → 当前阶段名（如"开篇困境"）
  ✓ stage_index        → 当前阶段索引
  ✓ seed_bundle_id     → 来源种子 bundle ID
  ✓ source_trace       → 完整溯源链 dict（task_card_id, blueprint_id, node_id, stage_name, etc.）

check_scene_via_p2 返回 dict 中：
  ✓ check_pipeline     → "p2_mainline" | "legacy"
  ✓ check_report_id    → 质检报告 ID
  ✓ status (打平)      → "pass" / "warn" / "fail"
  ✓ issues             → issue_codes 列表
  ✓ suggested_changes  → 改写建议列表

rewrite_scene_via_p2 返回 dict 中：
  ✓ scene_pipeline     → "p2_mainline" | "legacy"
  ✓ version            → 新草稿的版本号
  ✓ blueprint_id       → 来源蓝图 ID

SceneDraft.metadata（持久化字段）：
  ✓ approval_status    → "pending" | "approved" | "rejected"（通过 set_approval_status）
  ✓ last_check_report_id
  ✓ last_check_status
  ✓ last_check_issues
  ✓ check_pipeline
  ✓ scene_pipeline
```

---

## 五、结论与改造建议

### 可立即利用（current 路径已有，GUI 改造即可）：

1. **scene_seed → expansion 数据传递**：主工位 Tab「发送到场景扩写」不应只是切 tab，应把 `seed_id` / `seed_title` / `seed_text_preview` 通过 `ExportableObject` 或直接携参传递到 Tab ⑤
2. **自动填入 scene ID**：点「质检」「改写」时，应该从 `_last_created_scene_id` 自动填入输入框
3. **展示 pipeline 路径标签**：每个 tab 的结果区应该显示 `scene_pipeline` / `check_pipeline` 字段
4. **approval 按钮**：Tab ⑥ 应增加「标记为最终稿」「标记为待改写」按钮，调用 `set_approval_status`

### 需要后端改造（bridge → current）：

5. **seed 生成**：`blueprint_bundle` 不应传空字典。要么 GUI 保存一个真实的 blueprint ID，要么 `generate_scene_seeds_from_blueprint` 暴露一个「不要求 blueprint」的入口
6. **seed handoff 写入**：`handoff_scene_seed` 需要后端真正的写入能力（目前声明了但只返回前端辅助结果）

### 已存在但 GUI 不可见的字段（优先展示）：

- `scene_pipeline`（current / legacy 标签）
- `check_pipeline`（current / legacy 标签）
- `origin_path`（current / bridge / mixed）
- `version`（版本号）
- `source_trace`（完整溯源链）
- `blueprint_id` / `stage_name` / `stage_index`（管道位置）
