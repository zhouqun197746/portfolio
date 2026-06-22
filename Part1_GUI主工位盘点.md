# Part 1：GUI 主工位盘点报告 — creative_studio_gui 视角

**执行范围：** `app/gui/creative_studio_gui.py`
**分析版本：** 基于 `_build_ui()` 调用顺序，场景核心 4 个 tab 在 notebook 的索引为 **5→8**（管道导航 tab_index 同为 5→8）

---

## 一、4 个 tab 的概览

| # | Tab 名称（显示文字） | Notebook 索引 | 构建函数 | 管道工位 |
|---|----|:-:|---|---|
| 1 | **④ 场景种子** | 5 | `_build_tab11_scene_seed` | station_scene_seed |
| 2 | **⑤ 场景扩写** | 6 | `_build_tab4_scene` | station_scene_write |
| 3 | **⑥ 质检与改写** | 7 | `_build_tab5_check` | station_quality_check |
| 4 | **⑦ 导出与同步** | 8 | `_build_tab6_export` | station_export_sync |

另外有两个"增强包"场景 tab 不在本次主盘点范围内（它们属于采集链闭环的扩展工位）：

- Tab **🎬 场景种子** (idx 15) — `_build_tab18_scene_seed`，完整的采集链收口+下游 handoff
- Tab **✍️ 场景写作** (idx 16) — `_build_tab19_scene_writing`，seed → scene_card / writer_draft

---

## 二、逐个 Tab 详细分析

### Tab 1：④ 场景种子（`_build_tab11_scene_seed`）

**调用的前端函数：**

| 函数 | 角色 |
|---|---|
| `_build_tab11_scene_seed` | 构建整个 tab 的 UI（种子数量 Spinbox + 2 个按钮 + ScrolledText） |
| `_build_station_help_block(frame, "station_scene_seed")` | 拉取帮助面板（标题、描述、上下游提示） |
| `_p2_do_generate_scene_seeds` | 点击「生成场景种子」→ 调用 `generate_scene_seeds_from_blueprint` |
| `_seed_send_to_scene_write` | 点击「发送到场景扩写」→ 切换 notebook 到包含"场景扩写"的 tab |

**用户当前能看到：**
- 一个 Spinbox（种子数量，1–20，默认 5）
- 按钮「生成场景种子」「发送到场景扩写」
- 一个巨大的 ScrolledText（`self.seed_text`），生成结果以 JSON 原样填入

**用户看不到但应该看到：**
- ❌ **来源信息**：种子是从哪里生成的？（蓝图？任务卡？素材检索？采集链？）当前代码硬编码 `blueprint_bundle={}`，用户完全不知道数据来源
- ❌ **当前状态**：当前有没有已生成的种子？种子批次的 ID / 时间 / 数量？
- ❌ **种子列表的结构化展示**：当前只是一个 JSON dump，用户无法逐条选中、查看详情、对比
- ❌ **下一步按钮**：除了一个简单的 tab 跳转，没有「选择一个种子 → 发送到某个下游」的交互
- ❌ **来源说明的文字提示**：蓝图集是从哪个任务卡/素材来的、origin_path 是什么

---

### Tab 2：⑤ 场景扩写（`_build_tab4_scene`）

**调用的前端函数：**

| 函数 | 角色 |
|---|---|
| `_build_tab4_scene` | 构建 UI（描述输入框 + 按钮 + 结果展示区） |
| `_build_station_help_block(frame, "station_scene_write")` | 帮助面板 |
| `_do_write_scene` | 点击「扩写场景」→ 读取 `scene_entry` 内容，调用 `write_scene` |
| `_send_to_export_sync("scene_draft")` | 点击「发送到导出与同步」→ 构建 ExportableObject 并切换 tab |

**用户当前能看到：**
- 一个 5 行高的场景描述输入框（`self.scene_entry`）
- 按钮「扩写场景」「发送到导出与同步」
- 一个 28 行高的结果展示区（`self.scene_text`），也是 JSON 原样输出

**用户看不到但应该看到：**
- ❌ **场景来源**：当前场景描述是从哪里来的？是上游（场景种子/任务卡/蓝图）推送过来的，还是必须用户手动粘贴？目前完全是手动输入
- ❌ **上游数据的自动填充**：如果从场景种子 tab 跳转过来，种子数据应该自动填入描述框，但 `_seed_send_to_scene_write` 只做了 tab 切换，没有传递数据
- ❌ **当前步骤指示器**：处于「草稿」还是「待质检」还是「已改写」？没有任何状态标签
- ❌ **场景草稿 ID 的显式展示**：`_last_created_scene_id` 存在但只存为内存变量，用户看不到
- ❌ **发送后的确认反馈**：「发送到导出与同步」只是构建了对象 + 切 tab，没有在 UI 上显示「已发送场景 xxx」的确认
- ❌ **下一步按钮**：扩写完就应该有「发送到质检」的按钮，而不是只有一条路径去导出

---

### Tab 3：⑥ 质检与改写（`_build_tab5_check`）

**调用的前端函数：**

| 函数 | 角色 |
|---|---|
| `_build_tab5_check` | 构建 UI（场景草稿 ID 输入框 + 3 个按钮 + 结果展示区） |
| `_build_station_help_block(frame, "station_quality_check")` | 帮助面板 |
| `_do_check_scene` | 点击「质检」→ 调用 `check_scene(scene_id)` |
| `_do_rewrite_scene` | 点击「改写」→ 调用 `rewrite_scene(scene_id)` |
| `_send_to_export_sync("approved_scene")` | 点击「发送到导出与同步」→ 构建 ExportableObject |

**用户当前能看到：**
- 一个文本输入框（`self.check_scene_id`）要求手动输入场景草稿 ID
- 按钮「质检」「改写」「发送到导出与同步」
- 一个 30 行高的结果展示区（`self.check_text`），JSON 输出

**用户看不到但应该看到：**
- ❌ **可用场景草稿列表**：用户根本不知道自己有哪些场景草稿可用，必须离开这个 tab 去记忆或搜日志来找 ID
- ❌ **当前选中场景的状态标签**：不知道这个场景当前处于草稿 / 已质检 / 已改写 / 最终稿哪个阶段
- ❌ **质检结果的结构化展示**：质检结果是一个 JSON blob，没有评分、要点、建议的结构化呈现
- ❌ **改写与质检的联动**：应该先质检再改写，但 UI 上没有流程约束（两个按钮可以任意顺序点）
- ❌ **版本对比**：改写后的结果和原始草稿之间没有 diff/对比视图
- ❌ **自动填入 ID**：如果从场景扩写 tab 跳转过来，应该自动把 `_last_created_scene_id` 填入输入框
- ❌ **下一步按钮**：除了导出，缺少「发送回场景扩写（修改后重新质检）」的回路

---

### Tab 4：⑦ 导出与同步（`_build_tab6_export`）

**调用的前端函数：**

| 函数 | 角色 |
|---|---|
| `_build_tab6_export` | 构建 UI（承接对象面板 + 导出区 + 同步区 + 历史区 + 结果区） |
| `_build_station_help_block(frame, "station_export_sync")` | 帮助面板 |
| `_update_export_object_display` | 更新承接对象标签（object_type / source_stage / approval_status / export_ready） |
| `_do_export_obsidian(target_type)` | 导出到 Obsidian |
| `_do_view_recent_exports` | 查看最近导出记录 |
| `_do_view_recent_syncs` | 查看最近同步记录 |
| `_do_notion_sync` | 同步到 Notion |
| `_append_export_history` | 追加历史记录到轻量历史区 |

**用户当前能看到：**
- **承接对象摘要面板**：显示 object_type、source_stage、approval_status、export_ready（标准 ExportableObject 模型）
- **A 区 — 导出**：按钮「导出到 Obsidian」「导出当前场景草稿」「查看最近导出」+ 导出目标 RadioButton（任务卡/场景草稿）
- **B 区 — 同步**：按钮「同步到 Notion」「查看最近同步」
- **轻量历史区**：最近的导出/同步操作日志
- **操作结果**：大 ScrolledText 区域展示 JSON 结果

**用户看不到但应该看到：**
- ⚠️ 这个 tab 相对已经是 4 个里面信息最完整的，因为任务包 11 已经重构过
- ❌ **承接对象的来源溯源链**：用户能知道 object_type 和 source_stage，但看不到完整的溯源链（来自哪个种子→哪个草稿→哪个质检批次的哪个版本）
- ❌ **版本号或场景管线标识**：字段 `scene_pipeline` 和 `version` 存在但在 UI 中只截取前 20 字符且没有被强调
- ❌ **多对象管理**：目前只支持当前一个 `_current_export_object`，不能同时看到多个待导出的场景
- ❌ **导出预览**：导出到 Obsidian 之前，没有预览生成的 Markdown 内容
- ❌ **同步状态指示**：Notion 同步有没有上次失败记录？当前同步进度？

---

## 三、跨 tab 的关键缺失汇总

| 缺失维度 | 具体问题 |
|---|---|
| **来源（From）** | 每个 tab 都不知道自己的数据从哪来。场景种子不知道来自哪个蓝图/任务卡；场景扩写不知道来自哪个种子；质检不知道来自哪个草稿；导出不知道溯源链 |
| **当前阶段（Where）** | 没有任何 tab 显示「当前场景处于管道的第几步」。用户无法一眼看出：草稿 → 待质检 → 已质检 → 已改写 → 最终稿 |
| **下一步（Next）** | 按钮是「薄薄的一层」，缺少「发送到质检」「发送回扩写」「查看与草稿的 diff」「标记为最终稿」等上下文相关的下一步按钮 |
| **状态持久化** | `_last_created_scene_id`、`_last_check_result`、`_current_export_object` 都只是内存变量，刷新或重启后丢失 |

---

## 四、关键数据流图（现状 vs 应有）

```
现状：

  ④ 场景种子  ──[tab 切换]──→  ⑤ 场景扩写  ──[send_to_export_sync]──→  ⑦ 导出与同步
                                    │
                                    ↓
                              ⑥ 质检与改写  ──[send_to_export_sync]──→  ⑦ 导出与同步
                              （需手动输入 ID）

应有（缺失的链路用 ❌ 标出）：

  ④ 场景种子
     │  ❌ 选择一条种子 → 自动填充到扩写
     ↓
  ⑤ 场景扩写
     │  ❌ 扩写完成 → 显示 scene_draft_id → 自动跳转质检 tab
     │  ❌ 自动填入 ID → 用户只需点「质检」
     ↓
  ⑥ 质检与改写
     │  ❌ 质检结果 → 如果通过 →「发送到导出」
     │  ❌ 质检结果 → 如果不通过 →「发送回扩写」回路
     │  ❌ 改写后 → 显示 before/after diff
     ↓
  ⑦ 导出与同步
     │  ❌ 展示完整溯源链
     │  ❌ 预览导出内容
     │  ❌ 多对象管理
```

---

## 五、额外发现：两份场景种子 / 写作 tab 的并存

`_build_ui()` 中按顺序构建了：

1. `_build_tab11_scene_seed` → 显示文字 **"④ 场景种子"**（idx=5，主工位，简单版）
2. `_build_tab18_scene_seed` → 显示文字 **"🎬 场景种子"**（idx=15，增强包版，有 Treeview + 4 个区块 + handoff）
3. `_build_tab19_scene_writing` → 显示文字 **"✍️ 场景写作"**（idx=16，增强包版，seed→scene_card/writer_draft）

这意味着同一个 GUI 中存在两套场景种子/写作工位——一套老的简单版（主工位 idx 5）和一套新的完整版（增强包 idx 15-16）。如果在重构时需要统一，建议确定是以哪一套为准。
