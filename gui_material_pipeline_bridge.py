"""
gui_material_pipeline_bridge.py  v1.0.0-p2-gui-cap-audit  (任务包14: 采集链前台显化第一包)
=======================================================================================
采集链第一包前台显化桥接层 — 连接真实 MaterialStore / MaterialAtomStore。

职责：
1. 暴露 ingestion/cleaning/atomization 过程结果给 GUI （真实数据优先，降级时回退到报告/示例）
2. 提供来源类型中文映射
3. 构建清洗前后对比数据（原文 vs 当前文本）
4. 构建 atom 结果列表（含标签/分类: 剧情槽位, 情节拍类型, 冲突类型, 主情绪, 机制标签, 氛围标签）
5. 提供下游去向说明（可发往任务卡/种子/检索），含真实可点击路由
6. 提供发送到任务卡/场景种子的桥接动作

不改变后端核心算法，仅做已有数据的读取与重组。
"""
from __future__ import annotations

import os
import json
import datetime
from typing import Any, Optional

# ── 真实存储层 ──────────────────────────────────────────
from app.storage.material_store import MaterialStore
from app.storage.material_atom_store import MaterialAtomStore

# ── 来源类型 → 中文主标签 ──────────────────────────────
SOURCE_TYPE_CN_MAP = {
    "text": "文本素材",
    "obsidian": "Obsidian 笔记",
    "comment": "评论/短反馈",
    "rss": "RSS 资讯",
    "RSS": "RSS 资讯",
    "file": "文件导入",
    "batch": "批次导入",
    "manual": "手动输入",
    "api": "API 导入",
    "web": "网页抓取",
    "unknown": "未知来源",
    "material": "素材",
    "task_card": "任务卡",
    "scene_draft": "场景草稿",
    "blueprint": "蓝图",
}

# 来源渠道 → 中文映射（用于 source_channel 字段）
SOURCE_CHANNEL_CN_MAP = {
    "comments": "评论区",
    "workflowy": "Workflowy",
    "log": "日志",
    "inbox": "临时想法",
    "web_clip": "网页剪藏",
    "manual": "手动输入",
    "unknown": "未知渠道",
}

def cn_source_type(raw_type: str) -> str:
    """Return Chinese label for a source type."""
    return SOURCE_TYPE_CN_MAP.get(raw_type, raw_type)

def cn_source_channel(raw_channel: str) -> str:
    """Return Chinese label for a source channel."""
    return SOURCE_CHANNEL_CN_MAP.get(raw_channel, raw_channel)


# ── 字段中文标签映射（统一中文术语要求） ────────────────
# 中文主标签 + 英文括注 — 界面显示应以此为准
FIELD_CN_MAP = {
    # ── Step 3 必须覆盖核心术语 ──
    "rag_query": "RAG 检索描述 (rag_query)",
    "strict_filters": "强过滤条件 (strict_filters)",
    "soft_preferences": "软偏好条件 (soft_preferences)",
    "rerank_mode": "重排模式 (rerank_mode)",
    "top_k": "返回数量 (top_k)",
    "world_pack_id": "世界包编号 (world_pack_id)",
    "storyline_slot": "剧情槽位 (storyline_slot)",
    "beat_type": "情节拍类型 (beat_type)",
    "conflict_type": "冲突类型 (conflict_type)",
    "primary_emotion": "主情绪 (primary_emotion)",
    "mechanism_tags": "机制标签 (mechanism_tags)",
    "mood_tags": "氛围标签 (mood_tags)",
    # ── 扩展补充字段 ──
    "source_type": "来源类型 (source_type)",
    "raw_text": "原始文本 (raw_text)",
    "summary": "内容摘要 (summary)",
    "atom": "素材原子 (atom)",
    "dedup": "去重 (dedup)",
    "refine_status": "精炼状态 (refine_status)",
    "metadata": "元数据 (metadata)",
    # ── 已有映射（保留） ──
    "scene_pipeline": "场景流水线 (scene_pipeline)",
    "check_pipeline": "质检流水线 (check_pipeline)",
    "approval_status": "审批状态 (approval_status)",
    "blueprint_id": "蓝图编号 (blueprint_id)",
    "seed_bundle_id": "种子包编号 (seed_bundle_id)",
    "task_card_id": "任务卡编号 (task_card_id)",
    "source_stage": "来源工位 (source_stage)",
    "object_type": "对象类型 (object_type)",
    "source_trace": "来源追踪 (source_trace)",
    "atom_type": "Atom 类型 (atom_type)",
    "conflict_point": "冲突点 (conflict_point)",
    "emotion": "情绪 (emotion)",
    "duplicate_count": "重复数量 (duplicate_count)",
    "retention_strategy": "保留策略 (retention_strategy)",
    "cleaning_actions": "清洗操作 (cleaning_actions)",
    "ingestion": "素材接入 (ingestion)",
    "atomization": "原子化 (atomization)",
    "score": "匹配分数 (score)",
    "source_channel": "来源渠道 (source_channel)",
}

def cn_field(field_name: str) -> str:
    """Return Chinese label for a field name (中文主标签 + 英文括注)."""
    return FIELD_CN_MAP.get(field_name, field_name)


# ── 术语创作者解释映射 (Term Creator Explanation Map) ─────
# 每个术语对应一段"创作者视角"的中文解释，不是字面翻译
# 必须回答：这个字段对创作有什么实际意义？
TERM_HELP_MAP = {
    "rag_query": (
        "RAG 检索描述：告诉系统你想找什么类型的素材。用一句话描述你需要的场景氛围、人物关系或情节走向，"
        "系统会据此检索最相关内容。写得更具体，返回结果会更精准。"
        "\n创作者视角：你在写作中需要什么「感觉」的素材？把这感觉写出来给系统。"
    ),
    "strict_filters": (
        "强过滤条件：必须严格遵守的筛选规则。例如「只找仙侠类素材」「排除已用过的素材」。"
        "匹配结果必须完全满足这些条件，否则不会被纳入。建议把真正的硬性需求放这里。"
        "\n创作者视角：不可让步的条件。如果你写武侠世界，就别让系统返回科幻素材。"
    ),
    "soft_preferences": (
        "软偏好条件：优先考虑但可放宽的偏好。例如「最好含有对话」「如果可能带复仇元素」。"
        "系统会优先选择满足这些条件的素材，但如果不足，也会退而求其次。建议把锦上添花的需求放这里。"
        "\n创作者视角：想要但非必需的元素。有则更好，没有也不影响核心创作。"
    ),
    "rerank_mode": (
        "重排模式：决定检索结果的排序方式。不同模式影响哪些素材排在前面："
        "语义匹配（按意思相关度）、时间排序（按发布时间）、综合排序（多因素混合）。"
        "默认用语义模式，通常效果最好。"
        "\n创作者视角：你想要最新素材还是最相关素材？选时间模式找新鲜灵感，选语义模式找深度匹配。"
    ),
    "top_k": (
        "返回数量：希望系统一次性返回多少条候选素材。数量越大候选越多，但也会引入更多噪音。"
        "推荐 5-15 条，根据你的创作阶段调整：灵感搜集期用偏多，定稿期用偏少。"
        "\n创作者视角：你要多少选项来做决策？10 条左右是比较舒服的选择范围。"
    ),
    "world_pack_id": (
        "世界包编号：指定世界观/设定包的 ID。世界包是一套统一的人物、地点、规则设定，"
        "用于保证素材与当前创作世界的一致性。留空表示不限定世界观。"
        "\n创作者视角：你的故事发生在什么世界里？选对世界包，素材才能对味。"
    ),
    "storyline_slot": (
        "剧情槽位：说明这段素材更适合放在故事中的哪个位置。一段素材可能适合做开篇引子、"
        "中段冲突、高潮转折或结局收束。选择合适的槽位有助于素材的准确调用。"
        "\n创作者视角：想想你能在故事哪个阶段用上它——开头铺垫、中间推进、还是结尾收束？"
    ),
    "beat_type": (
        "情节拍类型：识别这段素材充当的是哪种叙事节奏。常用的拍类型包括：铺陈（建立背景）、"
        "冲突激化（制造矛盾）、转折（改变方向）、收束（达成结论）。匹配拍类型能让故事节奏更流畅。"
        "\n创作者视角：这段素材在你故事里是起「开始冲突」、「推进发展」还是「画上句号」的作用？"
    ),
    "conflict_type": (
        "冲突类型：标注素材涉及的核心矛盾类型，帮助系统理解这段素材适合用于何种冲突场景。"
        "常见的冲突类型有：人物 vs 人物、人物 vs 环境、人物 vs 自我、人物 vs 社会。"
        "\n创作者视角：你的故事核心是人际对抗、内心挣扎、还是面对天灾人祸？冲突类型决定了故事的张力方向。"
    ),
    "primary_emotion": (
        "主情绪：素材传达的核心情感基调，决定了读者阅读时的主要感受。"
        "常见的情绪标签：紧张、悲伤、喜悦、恐惧、希望、悬疑、浪漫等。"
        "\n创作者视角：你想让读者感受到什么？选对主情绪，事半功倍。"
    ),
    "mechanism_tags": (
        "机制标签：标注素材中包含的具体故事机制或手法，例如「时间跳跃」「多线叙事」「反转结局」。"
        "这些标签帮助识别素材用了哪些叙事技巧。"
        "\n创作者视角：这段素材靠什么手法推动故事？——误会、揭示、命运相遇、还是冲突升级？"
    ),
    "mood_tags": (
        "氛围标签：描述素材的整体氛围感，例如「黑暗」「轻快」「压抑」「梦幻」。"
        "氛围标签有助于将素材匹配到合适的场景情绪基调中。"
        "\n创作者视角：闭上眼睛感受这段素材给你什么心情——阴沉、温暖、紧迫、还是松弛？"
    ),
    "source_type": (
        "来源类型：素材是从哪里来的。不同来源类型的数据结构和可信度可能不同。"
        "例如 RSS 资讯偏时事、Obsidian 笔记偏创作思路、评论区偏用户氛围。"
        "\n创作者视角：知道素材来源有助于判断它的可靠性和可用场景。时事素材适合现实题材，笔记素材偏个人风格。"
    ),
    "raw_text": (
        "原始文本：素材的未经加工的原文内容。不经过任何清洗或精简处理的原始版本。"
        "通常内容较多且有冗余，需要经过清洗才能更好地使用。"
        "\n创作者视角：这是素材的「毛坯房」状态，你可以看到最原始的内容面貌。"
    ),
    "summary": (
        "内容摘要：素材的精简提炼版本，保留核心信息但去掉冗余表达。"
        "用于快速浏览素材要点，不必每次都读全文。"
        "\n创作者视角：不想读全文？看摘要就够了，核心信息都在。"
    ),
    "atom": (
        "原子化片段：将长素材拆解为更小、更聚焦的独立单元。每个 Atom 只关注一个核心要点"
        "（人物特质、事件片段、场景细节等），便于组合和复用。"
        "\n创作者视角：就像把一大块食材切成小块，每一块都是可独立使用的创作元素。"
    ),
    "dedup": (
        "去重：检查并移除内容重复或高度相似的素材，避免创作中重复使用同一来源。"
        "去重不会删除你的原始素材，只会标记哪些在创作中应避免重复引入。"
        "\n创作者视角：防止你在不同地方看到同一内容两次，保证素材库的「新鲜度」。"
    ),
    "refine_status": (
        "精炼状态：表示该素材经过了哪些精炼处理步骤。常见状态：原始（未处理）、"
        "已清洗（已去噪）、已原子化（已拆解）、已完成（全面处理）。"
        "\n创作者视角：一眼看出素材处理到了哪一步——是刚采集的毛坯，还是已经打磨好的精品。"
    ),
    "metadata": (
        "元数据：描述素材属性的结构化数据，包括来源时间、来源渠道、标签列表等。"
        "元数据帮助系统理解素材的上下文，而不仅仅是内容本身。"
        "\n创作者视角：素材的「身份证」——什么时间、从哪来、贴了什么标签。帮你理解素材的背景。"
    ),
    "source_channel": (
        "来源渠道：素材是通过什么途径收集进来的。例如网页剪藏、评论区、手动输入等。"
        "不同渠道的素材在格式和可信度上可能有所不同。"
        "\n创作者视角：素材是怎么到你手中的？不同渠道的质量和风格差异很大。"
    ),
    "score": (
        "匹配分数：表示素材与你的检索需求的匹配程度。分数越高代表与查询的相关性越强。"
        "85 分以上的通常非常相关，60-85 分可能部分相关，60 分以下建议忽略。"
        "\n创作者视角：分数告诉你这个素材「对不对味」。高分代表它和你当前想写的东西很接近。"
    ),
    "atom_type": (
        "Atom 类型：原子化片段的类别。不同类型表示素材适合用于创作的不同层面，"
        "例如人物特质类、场景氛围类、对话风格类、冲突设定类等。"
        "\n创作者视角：这个片段是「做什么用的」——塑造人物、渲染场景、还是设计对话？"
    ),
    "conflict_point": (
        "冲突点：标注素材中最核心的矛盾或冲突焦点。用于快速判断该素材能为场景冲突设计提供什么支撑。"
        "\n创作者视角：这段素材里「谁和谁在对抗」，抓住冲突核心，你就知道怎么用它。"
    ),
    "emotion": (
        "情绪：素材的情感基调。与主情绪的区别是，情绪可以是多重、复合的，"
        "而主情绪是素材最核心的那一个情感方向。"
        "\n创作者视角：这段素材给你什么情绪感受？喜悦、悲伤、愤怒……一个场景可以同时有多种情绪层次。"
    ),
    "ingestion": (
        "素材接入：将外部素材导入系统处理管道的第一步。包括原始文本获取、来源标记、时间戳记录。"
        "\n创作者视角：素材进入系统的「大门」，从这里开始系统会帮你加工打理。"
    ),
    "atomization": (
        "原子化：将长素材拆解为独立可用的小单元的加工过程。原子化后每个片段都聚焦一个要点，便于混搭重用。"
        "\n创作者视角：把一块大石头敲成可独立使用的小石子——每个小石子都能单独派上用场。"
    ),
    "cleaning_actions": (
        "清洗操作：系统对素材原文做的具体处理动作，例如去空格、合并空行、移除标记符号等。"
        "\n创作者视角：系统替你做了哪些「打扫」工作，让素材从杂乱变整洁。"
    ),
    "retention_strategy": (
        "保留策略：当发现重复或相似素材时，系统决定保留哪个版本、丢弃哪些版本的规则。"
        "\n创作者视角：系统怎么决定「留下谁、丢掉谁」——通常保留时间更新、信息更全的那个。"
    ),
    "duplicate_count": (
        "重复数量：系统检测到的内容重复或高度相似的素材条数。"
        "\n创作者视角：你的素材库里有多少条「长得差不多」的内容。"
    ),
}

def cn_term_help(field_name: str) -> str:
    """Return creator-facing Chinese explanation for a term."""
    return TERM_HELP_MAP.get(field_name, "")


# ── 区块说明映射 (Section Description Map) ─────────────────
# 每个采集链区块用一段中文说明 "这里是什么 + 对创作有什么用"
SECTION_DESC_MAP: dict[str, str] = {
    "pipeline_status": (
        "采集链概览：展示当前素材的接入、清洗、原子化、去重状态。"
        "这是素材进入创作管线的第一站，了解这里的数据情况，你就知道「手里有多少可用的写作材料」。"
    ),
    "cleaning_before_after": (
        "清洗对比：左侧是原文（未经处理的原始内容），右侧是系统清洗后的精简版本。"
        "清洗的目的是去噪声、保持核心信息，让素材更适合直接用于创作。"
        "如果清洗后丢失了重要信息，可以回到原始版本重新提取。"
    ),
    "atomization_results": (
        "原子化结果：系统将长素材拆解为独立可用的最小单位。每个「原子」只关注一个核心要点"
        "（某个人物特质、某个事件片段、某个场景细节）。你可以像搭积木一样组合这些原子来构建场景。"
    ),
    "tag_classification": (
        "标签与分类：从原子中提取的六个分类维度——剧情槽位（素材放在故事哪个位置）、"
        "情节拍类型（素材是铺垫还是高潮）、冲突类型（核心矛盾是什么）、主情绪（读者感受）、"
        "机制标签（推动故事的技巧）、氛围标签（整体感受）。"
        "这些维度帮助你快速判断一段素材「用在哪、怎么用、为什么用」。"
    ),
    "downstream_routes": (
        "下游去向：采集处理后的素材可以流向任务卡（生成具体写作任务）、场景种子（生成场景起点）、"
        "高级检索（被 RAG 系统再次调用）、创意组合（被十种创意方法调用）。"
        "每个去向都配有真实路由状态——已接通/规划中/暂不可用。"
    ),
    "dedup_summary": (
        "去重治理摘要：系统自动检查素材库中的重复或高度相似内容，避免你在创作中无意重复使用同一来源。"
        "这里显示去重状态、保留策略和具体数据。绿色的「已清洁」状态说明素材库很健康。"
    ),
}

def cn_section_desc(section_id: str) -> str:
    """Return Chinese description for a pipeline section."""
    return SECTION_DESC_MAP.get(section_id, "")

def cn_section_help(section_id: str) -> str:
    """Return creator-oriented Chinese help for a pipeline section."""
    return SECTION_DESC_MAP.get(section_id, "")


# ── 下游去向说明 ──────────────────────────────────────────
# 真实接入状态: 已接通 / 规划中 / 暂不可用
DOWNSTREAM_ROUTES = {
    "task_card": {
        "label": "任务卡 (Task Card)",
        "description": "采集处理后的素材可作为任务卡生成的候选来源，通过创意方法组合生成任务卡。"
                       "任务卡是具体的写作任务单元，包含场景描述、人物、冲突等要素。"
                       "创作者视角：把素材转化为「接下来要写的那个场景」的具体任务。",
        "status": "已接通",
        "connection_level": "真实当前路径",
        "connection_level_note": "send_to_task_card() 从当前选中素材构造 MaterialPipelineInput（含 source_ids, atom_ids, tag_summary, source_type, cleaning_summary, dedup_summary），送入 generate_task_cards() 时携带来源标记 material_pipeline_derived",
        "action_available": True,
    },
    "scene_seed": {
        "label": "场景种子 (Scene Seed)",
        "description": "原子化后的材料可进入场景种子生成流程，为种子提供标签/冲突/情绪维度支撑。"
                       "场景种子是场景扩写的起点——一个简短但结构完整的场景雏形。"
                       "创作者视角：素材成了「种子」的营养，帮种子长出完整的场景来。",
        "status": "已接通",
        "connection_level": "真实工位动作",
        "connection_level_note": "A-3: send_to_scene_seed() 直接调用 generate_scene_seeds_from_material_pipeline() 新入口（scene_seed_p2_bridge 原生入口），不再伪造 blueprint 包装。is_current_path=True, is_bridge=False。结构化输入包含 source_material_ids, selected_atom_ids, tag_summary 等完整字段。",
        "action_available": True,
    },
    "advanced_search": {
        "label": "高级检索 / RAG",
        "description": "清洗后的文本和原子化结果可用于复杂检索和 RAG 增强生成。"
                       "当你需要更精准的素材查找时，RAG 会理解你的意图而不是查关键词。"
                       "创作者视角：不只是搜关键词，而是让系统「理解你想要什么感觉」。",
        "status": "已接通",
        "action_available": False,
    },
    "creative_methods": {
        "label": "创意组合 (规划中)",
        "description": "标签化的原子结果可被十种创意方法（人物融合、世界观对冲等）调用作为组合素材。"
                       "这是素材的高级玩法——让不同素材碰撞出新的创作火花。"
                       "创作者视角：素材之间「互相认识」后，会产生你没想到的好点子。",
        "status": "规划中",
        "action_available": False,
    },
}

def get_downstream_routes() -> list[dict]:
    """Return downstream route descriptions with real connectivity status."""
    return [
        {
            "id": k,
            "label": v["label"],
            "description": v["description"],
            "status": v["status"],
            "action_available": v["action_available"],
        }
        for k, v in DOWNSTREAM_ROUTES.items()
    ]


# ══════════════════════════════════════════════════════════
# 后端真实数据读取（降级回退逻辑）
# ══════════════════════════════════════════════════════════

def get_material_pipeline_status() -> dict:
    """
    Return current material pipeline status from real storage.
    
    Reads:
      - MaterialStore for ingestion/material counts
      - MaterialAtomStore for atomization counts
      - material_refine_report files for refine run status
    """
    status = {
        "ingestion_count": 0,
        "cleaning_count": 0,
        "atomization_count": 0,
        "dedup_count": 0,
        "last_ingestion_time": "",
        "last_cleaning_time": "",
        "source_type_breakdown": {},
        "source_channel_breakdown": {},
        "pipeline_info": [],
    }

    # 1) Real counts from MaterialStore
    try:
        store = MaterialStore()
        total_materials = store.count()
        status["ingestion_count"] = total_materials
        status["source_type_breakdown"] = store.count_by_source_type()
        recent = store.list_all(limit=1)
        if recent:
            status["last_ingestion_time"] = recent[0].created_at or ""
    except Exception:
        pass

    # 2) Real atom counts from MaterialAtomStore
    try:
        astore = MaterialAtomStore()
        atom_counts = astore.count_by_status()
        total_atoms = sum(atom_counts.values())
        status["atomization_count"] = total_atoms
        status["atom_status_breakdown"] = atom_counts
    except Exception:
        pass

    # 3) material_refine_report files for last run time
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports",
    )
    if os.path.isdir(results_dir):
        for fname in sorted(os.listdir(results_dir), reverse=True):
            if fname.startswith("material_refine_report") and fname.endswith(".json"):
                fpath = os.path.join(results_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        started = data.get("started_at", "")
                        finished = data.get("finished_at", "")
                        if finished:
                            status["last_cleaning_time"] = finished[:19]
                        elif started:
                            status["last_cleaning_time"] = started[:19]
                        status["pipeline_info"].append({
                            "source_channel": data.get("source_channel", ""),
                            "dry_run": data.get("dry_run", False),
                            "atoms_created": data.get("atoms_created", 0),
                            "total_candidates": data.get("total_candidates", 0),
                            "time": finished or started or "",
                        })
                except Exception:
                    continue

    status["cleaning_count"] = status["atomization_count"]
    return status


def get_cleaning_before_after() -> dict:
    """
    Get real cleaning before/after comparison data.
    
    Strategy:
      1. Try to read from MaterialStore
      2. If no real data available, fall back to refine report sample previews
    """
    try:
        store = MaterialStore()
        all_materials = store.list_all(limit=5, source_type_filter=None)
        
        if all_materials:
            for m in all_materials:
                raw_text = (m.text or "").strip()
                if len(raw_text) > 20:
                    original_text = raw_text[:800]
                    if len(raw_text) > 800:
                        original_text += "\n…(内容截断)"
                    
                    cleaned_text = m.summary or raw_text[:500]
                    if m.summary:
                        actions = ["原文已通过摘要提取精简"]
                    else:
                        import re
                        cleaned = raw_text[:500]
                        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
                        cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
                        cleaned = cleaned.strip()
                        cleaned_text = cleaned
                        actions = [
                            "合并了连续空白行为单行",
                            "清理了多余空格和制表符",
                        ]
                    
                    return {
                        "original_text": original_text,
                        "cleaned_text": cleaned_text,
                        "actions": actions,
                        "source_material_id": m.id,
                        "source_type": m.source_type.value if hasattr(m.source_type, 'value') else str(m.source_type),
                        "source_type_cn": cn_source_type(str(m.source_type.value if hasattr(m.source_type, 'value') else m.source_type)),
                    }
    except Exception:
        pass
    
    # Fallback: try refine report for sample previews
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports",
    )
    try:
        report_path = os.path.join(results_dir, "material_refine_report.json")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            samples = data.get("scored_examples", [])
            if samples:
                original_text = samples[0].get("text_preview", "")
                import re
                cleaned_text = re.sub(r'#+\s*', '', original_text)
                cleaned_text = re.sub(r'>\s*', '', cleaned_text)
                cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
                return {
                    "original_text": original_text[:600],
                    "cleaned_text": cleaned_text[:600],
                    "actions": [
                        "移除了 Markdown 标题标记 (#)",
                        "移除了引用标记 (>)",
                        "合并了连续空白行",
                    ],
                    "source_material_id": "(来自精炼报告样本)",
                    "source_type": "batch",
                    "source_type_cn": "批次导入",
                }
    except Exception:
        pass
    
    return {
        "original_text": "(暂未接入素材。请先接入素材后查看清洗效果)",
        "cleaned_text": "(等待素材接入)",
        "actions": [],
        "source_material_id": "",
        "source_type": "",
        "source_type_cn": "",
    }


def get_atomization_atoms() -> list[dict]:
    """
    Get real atomized atoms list from MaterialAtomStore.
    """
    try:
        astore = MaterialAtomStore()
        mstore = MaterialStore()
        materials = mstore.list_all(limit=1)
        
        atoms = []
        if materials:
            source_id = materials[0].id
            raw_atoms = astore.get_atoms_by_source(source_id)
            for a in raw_atoms:
                mechanism_tags = []
                mood_tags = []
                if hasattr(a, 'method_tags') and a.method_tags:
                    mechanism_tags = a.method_tags
                if hasattr(a, 'tags') and a.tags:
                    mood_tags = [t for t in a.tags if any(kw in t.lower() for kw in
                        ("mood", "氛围", "情绪", "atmosphere", "tone", "dark", "light", "tense", "calm",
                         "joy", "sad", "angry", "fear", "hope", "mystery", "romance", "horror"))]
                
                atoms.append({
                    "atom_id": a.atom_id,
                    "title": a.title or a.summary[:60] if a.summary else f"Atom {a.atom_id[:16]}",
                    "atom_type": a.atom_type,
                    "tags": a.tags or [],
                    "method_tags": a.method_tags or [],
                    "mechanism_tags": mechanism_tags,
                    "mood_tags": mood_tags,
                    "conflict_type": a.conflict_point or "",
                    "primary_emotion": a.emotion or "",
                    "source": a.source_material_id or "",
                    "source_type_cn": "",
                    "refine_status": a.refine_status or "pending",
                })
        
        if atoms:
            return atoms
        
        # Try SQLite fallback
        import sqlite3
        try:
            with sqlite3.connect(astore.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM material_atoms ORDER BY created_at DESC LIMIT 20"
                )
                rows = cursor.fetchall()
                for row in rows:
                    d = dict(row)
                    tags = json.loads(d.get("tags", "[]")) if isinstance(d.get("tags"), str) else d.get("tags", [])
                    method_tags = json.loads(d.get("method_tags", "[]")) if isinstance(d.get("method_tags"), str) else d.get("method_tags", [])
                    mood_tags = [t for t in tags if isinstance(t, str) and any(kw in t.lower() for kw in
                        ("mood", "氛围", "情绪", "atmosphere", "tone", "dark", "light", "tense", "calm",
                         "joy", "sad", "angry", "fear", "hope", "mystery", "romance", "horror"))]
                    
                    atoms.append({
                        "atom_id": d["atom_id"],
                        "title": d.get("title", "") or d.get("summary", "")[:60] if d.get("summary") else f"Atom {d['atom_id'][:16]}",
                        "atom_type": d.get("atom_type", "unresolved_fragment"),
                        "tags": tags if isinstance(tags, list) else [],
                        "method_tags": method_tags if isinstance(method_tags, list) else [],
                        "mechanism_tags": method_tags if isinstance(method_tags, list) else [],
                        "mood_tags": mood_tags,
                        "conflict_type": d.get("conflict_point", ""),
                        "primary_emotion": d.get("emotion", ""),
                        "source": d.get("source_material_id", ""),
                        "source_type_cn": "",
                        "refine_status": d.get("refine_status", "pending"),
                    })
        except Exception:
            pass
        
        if atoms:
            return atoms
    except Exception:
        pass
    
    # Fallback: refine report
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports",
    )
    try:
        report_path = os.path.join(results_dir, "material_refine_report.json")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sample_atoms = data.get("sample_atoms", [])
            if sample_atoms:
                return [{
                    "atom_id": sa.get("atom_id", f"sample_{i}"),
                    "title": sa.get("title", "") or f"Atom {i}",
                    "atom_type": sa.get("atom_type", "sample"),
                    "tags": sa.get("tags", []),
                    "method_tags": sa.get("method_tags", []),
                    "mechanism_tags": sa.get("method_tags", []),
                    "mood_tags": [t for t in sa.get("tags", []) if isinstance(t, str) and any(kw in t.lower()
                        for kw in ("mood", "氛围", "情绪", "atmosphere", "tone", "dark", "tense"))],
                    "conflict_type": sa.get("conflict_point", sa.get("conflict_type", "")),
                    "primary_emotion": sa.get("emotion", ""),
                    "source": sa.get("source_material_id", ""),
                    "source_type_cn": "",
                    "refine_status": "sample",
                } for i, sa in enumerate(sample_atoms[:10])]
    except Exception:
        pass

    return []


def get_dedup_governance_summary() -> dict:
    """
    Get a lightweight dedup governance summary.
    READ-ONLY bridge. Does NOT run dedup algorithms.
    """
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports",
    )
    
    # 1) Try dedup_governance report files first
    dedup_report = None
    for fname in sorted(os.listdir(results_dir), reverse=True):
        if "dedup" in fname.lower() and fname.endswith(".json"):
            fpath = os.path.join(results_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    dedup_report = data
                    break
            except Exception:
                continue
    
    if dedup_report:
        duplicates_found = dedup_report.get("duplicates_found", False)
        duplicate_count = dedup_report.get("duplicate_count", 0)
        retention_strategy = dedup_report.get("retention_strategy", "未指定")
        dedup_conclusion = dedup_report.get("conclusion", "")
        return {
            "status": "detected" if duplicates_found else "clean",
            "duplicates_detected": duplicates_found,
            "duplicate_count": duplicate_count,
            "retention_strategy": retention_strategy,
            "conclusion": dedup_conclusion,
            "source": "dedup_report",
            "note": "" if duplicates_found else "当前未检测到疑似重复素材",
        }
    
    # 2) Try refine reports
    for fname in sorted(os.listdir(results_dir), reverse=True):
        if fname.startswith("material_refine_report") and fname.endswith(".json"):
            fpath = os.path.join(results_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    dup_sources = data.get("duplicate_sources", [])
                    if dup_sources:
                        return {
                            "status": "detected",
                            "duplicates_detected": True,
                            "duplicate_count": len(dup_sources),
                            "retention_strategy": "保留最新版本",
                            "conclusion": f"检测到 {len(dup_sources)} 个重复来源",
                            "source": "refine_report",
                        }
                    dedup_removed = data.get("dedup_removed", 0)
                    if dedup_removed > 0:
                        return {
                            "status": "clean_after_removal",
                            "duplicates_detected": False,
                            "duplicate_count": dedup_removed,
                            "retention_strategy": "自动去重（保留较新版本）",
                            "conclusion": f"已自动移除 {dedup_removed} 条重复素材",
                            "source": "refine_report",
                        }
            except Exception:
                continue
    
    # 3) Check governance
    try:
        from app.core.governance_dashboard_p2_bridge import build_governance_snapshot
        snap = build_governance_snapshot()
        risk_data = snap.get("risk", {})
        if isinstance(risk_data, dict):
            legacy_fallback = risk_data.get("legacy_fallback_count", 0)
            if legacy_fallback > 0:
                return {
                    "status": "attention",
                    "duplicates_detected": False,
                    "duplicate_count": legacy_fallback,
                    "retention_strategy": "遗留回退保留",
                    "conclusion": f"发现 {legacy_fallback} 条遗留回退",
                    "source": "governance_snapshot",
                }
    except Exception:
        pass
    
    return {
        "status": "not_connected",
        "duplicates_detected": False,
        "duplicate_count": 0,
        "retention_strategy": "（尚未接入去重服务）",
        "conclusion": "暂无去重结果",
        "source": "none",
        "note": "尚未接入",
    }


def get_tag_classification_summary() -> dict:
    """
    Get real tag/classification summary from atoms in MaterialAtomStore.
    """
    atoms = get_atomization_atoms()
    
    if not atoms:
        return {
            "total_atoms": 0, "total_unique_tags": 0, "tags": [],
            "conflict_types": [], "emotions": [], "atom_types": [],
            "refine_status_breakdown": {}, "tag_frequency": {},
            "storyline_slots": [], "beat_types": [],
            "mechanism_tags": [], "mood_tags": [],
            "mechanism_tag_frequency": {}, "mood_tag_frequency": {},
        }
    
    all_tags = {}
    conflict_types = set()
    emotions = set()
    atom_types = set()
    refine_statuses = {}
    storyline_slots = set()
    beat_types = set()
    mechanism_tags = {}
    mood_tags = {}
    
    for atom in atoms:
        for tag in atom.get("tags", []):
            if isinstance(tag, str):
                all_tags[tag] = all_tags.get(tag, 0) + 1
        for mtag in atom.get("method_tags", []):
            if isinstance(mtag, str):
                mechanism_tags[mtag] = mechanism_tags.get(mtag, 0) + 1
        for motag in atom.get("mood_tags", []):
            if isinstance(motag, str):
                mood_tags[motag] = mood_tags.get(motag, 0) + 1
        ct = atom.get("conflict_type", "")
        if ct:
            conflict_types.add(ct)
        em = atom.get("primary_emotion", "")
        if em:
            emotions.add(em)
        at = atom.get("atom_type", "")
        if at:
            atom_types.add(at)
        rs = atom.get("refine_status", "")
        if rs:
            refine_statuses[rs] = refine_statuses.get(rs, 0) + 1
    
    return {
        "total_atoms": len(atoms),
        "total_unique_tags": len(all_tags),
        "tags": sorted(all_tags.keys()),
        "tag_frequency": dict(sorted(all_tags.items(), key=lambda x: -x[1])),
        "conflict_types": sorted(conflict_types),
        "emotions": sorted(emotions),
        "atom_types": sorted(atom_types),
        "refine_status_breakdown": refine_statuses,
        "storyline_slots": sorted(storyline_slots) if storyline_slots else ["（暂缺）"],
        "beat_types": sorted(beat_types) if beat_types else ["（暂缺）"],
        "mechanism_tags": sorted(mechanism_tags.keys()),
        "mechanism_tag_frequency": dict(sorted(mechanism_tags.items(), key=lambda x: -x[1])),
        "mood_tags": sorted(mood_tags.keys()),
        "mood_tag_frequency": dict(sorted(mood_tags.items(), key=lambda x: -x[1])),
    }


# ══════════════════════════════════════════════════════════
# 下游路由动作桥接（发送到任务卡 / 发送到场景种子）
# ══════════════════════════════════════════════════════════

def send_to_task_card(
    atom_ids: Optional[list[str]] = None,
    count: int = 3,
    source_material_ids: Optional[list[str]] = None,
    tag_summary: Optional[dict] = None,
    source_type: str = "material_pipeline",
    source_channel: str = "",
    cleaning_summary: Optional[dict] = None,
    dedup_summary: Optional[dict] = None,
) -> dict:
    """
    【过渡桥接】发送结构化 MaterialPipelineInput 到任务卡工位。
    
    不再使用 query 字符串包装——下游工位收到的是结构化对象摘要，而非一段查询文本。
    构造的下游输入对象包含 source_material_ids / atom_ids / tag_summary / source_type / cleaning_summary / dedup_summary。
    每个字段标记其是否来自真实推导，哪些字段为空/待补。
    """
    material_ids = source_material_ids or []
    selected_atom_ids = atom_ids or []
    if not material_ids and not selected_atom_ids:
        try:
            from app.storage.material_store import MaterialStore
            from app.storage.material_atom_store import MaterialAtomStore
            mstore = MaterialStore()
            astore = MaterialAtomStore()
            recent = mstore.list_all(limit=count)
            material_ids = [m.id for m in recent if hasattr(m, 'id') and m.id]
            for mid in material_ids[:2]:
                atoms = astore.get_atoms_by_source(mid)
                selected_atom_ids.extend([a.atom_id for a in atoms])
            selected_atom_ids = selected_atom_ids[:20]
        except Exception:
            pass
    if not tag_summary:
        try:
            tag_data = get_tag_classification_summary()
            tag_summary = {
                "conflict_types": tag_data.get("conflict_types", []),
                "emotions": tag_data.get("emotions", []),
                "mechanism_tags": tag_data.get("mechanism_tags", []),
                "mood_tags": tag_data.get("mood_tags", []),
                "total_atoms": tag_data.get("total_atoms", 0),
                "total_unique_tags": tag_data.get("total_unique_tags", 0),
            }
        except Exception:
            tag_summary = {}
    if not cleaning_summary:
        try:
            clean_data = get_cleaning_before_after()
            cleaning_summary = {
                "has_original": bool(clean_data.get("original_text", "")),
                "has_cleaned": bool(clean_data.get("cleaned_text", "")),
                "actions_count": len(clean_data.get("actions", [])),
            }
        except Exception:
            cleaning_summary = {}
    if not dedup_summary:
        try:
            dedup_data = get_dedup_governance_summary()
            dedup_summary = {
                "status": dedup_data.get("status", "not_connected"),
                "duplicates_detected": dedup_data.get("duplicates_detected", False),
                "duplicate_count": dedup_data.get("duplicate_count", 0),
            }
        except Exception:
            dedup_summary = {}

    from app.core.task_card_pipeline_input_models import MaterialPipelineInput
    pipeline_input_obj = MaterialPipelineInput(
        source_stage="material_search",
        source_material_ids=material_ids,
        selected_atom_ids=selected_atom_ids,
        material_count=len(material_ids),
        atom_count=len(selected_atom_ids),
        tag_summary=tag_summary,
        source_type_summary={"primary_source_type": source_type, "source_channel": source_channel},
        cleaning_summary=cleaning_summary,
        dedup_summary=dedup_summary,
        user_selection_scope="all_recent",
        version="1.0.0-b",
        trace_id="",
    )
    pipeline_dict = pipeline_input_obj.to_pipeline_dict()

    try:
        from app.core.gui_p2_bridge_exports import generate_task_cards
        result = generate_task_cards(
            query="",
            count=count,
            creative_method="semantic",
            source_pipeline_input=pipeline_dict,
        )
        if isinstance(result, list):
            cards_count = len(result)
            return {
                "status": "ok",
                "action": "send_to_task_card",
                "action_level": "真实工位动作",
                "cards_count": cards_count,
                "cards": [{"id": c[0], "title": c[1], "card_type": c[2], "creative_methods": c[3]} for c in result[:5]],
                "detail": f"成功生成 {cards_count} 个任务卡（采集链结构化原生输入）",
                "pipeline_input_summary": pipeline_input_obj.to_brief_summary(),
            }
        return {
            "status": "ok",
            "action": "send_to_task_card",
            "action_level": "真实工位动作",
            "cards_count": 0,
            "detail": "已通过 source_pipeline_input 将结构化输入送入任务卡工位",
            "pipeline_input_summary": pipeline_input_obj.to_brief_summary(),
        }
    except Exception as e:
        return {
            "status": "transit",
            "action": "send_to_task_card",
            "action_level": "过渡桥接",
            "detail": f"已发送结构化输入（任务卡生成异常: {str(e)[:80]}）",
            "pipeline_input_summary": pipeline_input_obj.to_brief_summary(),
        }


def send_to_scene_seed(
    atom_ids: Optional[list[str]] = None,
    count: int = 5,
    source_material_ids: Optional[list[str]] = None,
    tag_summary: Optional[dict] = None,
    source_type: str = "material_pipeline",
    source_channel: str = "",
    cleaning_summary: Optional[dict] = None,
    dedup_summary: Optional[dict] = None,
) -> dict:
    """
    CURRENT PATH (A-3): 发送结构化采集链输入到场景种子工位。
    
    不再构造伪 blueprint 包装。直接调用
    generate_scene_seeds_from_material_pipeline() 新入口，
    标记 is_current_path=True, is_bridge=False。
    """
    material_ids = source_material_ids or []
    selected_atom_ids = atom_ids or []
    if not material_ids and not selected_atom_ids:
        try:
            from app.storage.material_store import MaterialStore
            from app.storage.material_atom_store import MaterialAtomStore
            mstore = MaterialStore()
            astore = MaterialAtomStore()
            recent = mstore.list_all(limit=count)
            material_ids = [m.id for m in recent if hasattr(m, 'id') and m.id]
            for mid in material_ids[:2]:
                atoms = astore.get_atoms_by_source(mid)
                selected_atom_ids.extend([a.atom_id for a in atoms])
            selected_atom_ids = selected_atom_ids[:20]
        except Exception:
            pass
    if not tag_summary:
        try:
            tag_data = get_tag_classification_summary()
            tag_summary = {
                "conflict_types": tag_data.get("conflict_types", []),
                "emotions": tag_data.get("emotions", []),
                "mechanism_tags": tag_data.get("mechanism_tags", []),
                "mood_tags": tag_data.get("mood_tags", []),
                "total_atoms": tag_data.get("total_atoms", 0),
                "total_unique_tags": tag_data.get("total_unique_tags", 0),
            }
        except Exception:
            tag_summary = {}
    if not cleaning_summary:
        try:
            clean_data = get_cleaning_before_after()
            cleaning_summary = {"has_original": bool(clean_data.get("original_text", "")), "has_cleaned": bool(clean_data.get("cleaned_text", "")), "actions_count": len(clean_data.get("actions", []))}
        except Exception:
            cleaning_summary = {}
    if not dedup_summary:
        try:
            dedup_data = get_dedup_governance_summary()
            dedup_summary = {"status": dedup_data.get("status", "not_connected"), "duplicates_detected": dedup_data.get("duplicates_detected", False), "duplicate_count": dedup_data.get("duplicate_count", 0)}
        except Exception:
            dedup_summary = {}
    
    pipeline_input = {
        "source_stage": "material_pipeline",
        "version": "v1",
        "source_material_ids": material_ids,
        "atom_ids": selected_atom_ids,
        "material_count": len(material_ids),
        "atom_count": len(selected_atom_ids),
        "tag_summary": tag_summary,
        "source_type": source_type,
        "source_channel": source_channel,
        "cleaning_summary": cleaning_summary,
        "dedup_summary": dedup_summary,
        "_origin": "material_pipeline",
        "_input_type": "MaterialPipelineInput",
        "_version": "1.0.0-p2-gui-flow",
    }
    
    try:
        from app.core.gui_p2_bridge_exports import generate_scene_seeds_from_material_pipeline
        
        result = generate_scene_seeds_from_material_pipeline(
            pipeline_input=pipeline_input,
            max_seeds=count,
        )
        
        if result.get("status") == "ok" and result.get("seed_pipeline") == "material_pipeline_current":
            seeds = result.get("seeds", [])
            return {
                "status": "ok",
                "action": "send_to_scene_seed",
                "action_level": "真实工位动作",
                "seeds_count": len(seeds),
                "seed_pipeline": "material_pipeline_current",
                "source_stage": "material_pipeline",
                "material_pipeline_derived": True,
                "material_count": len(material_ids),
                "atom_count": len(selected_atom_ids),
                "is_current_path": True,
                "is_bridge": False,
                "detail": f"成功生成 {len(seeds)} 个场景种子（采集链 current path）",
                "pipeline_input_summary": result.get("pipeline_input_summary", {
                    "material_count": len(material_ids),
                    "atom_count": len(selected_atom_ids),
                }),
            }
        return {
            "status": "fail",
            "action": "send_to_scene_seed",
            "action_level": "真实工位动作",
            "seeds_count": 0,
            "seed_pipeline": "material_pipeline_current",
            "source_stage": "material_pipeline",
            "material_pipeline_derived": True,
            "material_count": len(material_ids),
            "atom_count": len(selected_atom_ids),
            "is_current_path": True,
            "is_bridge": False,
            "detail": f"current path 返回: {result.get('error', 'unknown')}",
            "pipeline_input_summary": {"material_count": len(material_ids), "atom_count": len(selected_atom_ids)},
            "fail_reasons": [result.get("error", "CURRENT_PATH_FAILED")],
        }
    except Exception as e:
        return {
            "status": "fail",
            "action": "send_to_scene_seed",
            "action_level": "真实工位动作",
            "seeds_count": 0,
            "seed_pipeline": "material_pipeline_current",
            "source_stage": "material_pipeline",
            "material_pipeline_derived": True,
            "material_count": len(material_ids),
            "atom_count": len(selected_atom_ids),
            "is_current_path": True,
            "is_bridge": False,
            "detail": f"current path 异常: {str(e)[:80]}",
            "pipeline_input_summary": {"material_count": len(material_ids), "atom_count": len(selected_atom_ids)},
            "fail_reasons": [f"CURRENT_PATH_EXCEPTION:{str(e)[:80]}"],
        }


# ── 增强包 C + D Bridge 注册 ────────────────────────────────
_BRIDGE_REGISTRY: dict[str, str] = {
    "gui_ingestion_entry_bridge": "增强包C — 接入入口工位化",
    "gui_metadata_frontend_bridge": "增强包D — metadata 初始化/自动推断前台化",
}

def get_bridge_registry() -> dict[str, str]:
    """返回已注册的 Bridge 列表。"""
    return dict(_BRIDGE_REGISTRY)

def get_combined_pipeline_export() -> list[dict]:
    """返回采集链 + 增强包的组合导出清单。"""
    exports: list[dict] = []
    exports.append({"module": "gui_material_pipeline_bridge", "label": "采集链中文标签 / 术语帮助", "type": "core"})
    exports.append({"module": "gui_p2_bridge_exports", "label": "P2 合成出口 (检索/任务卡/场景/治理)", "type": "core"})
    try:
        from app.core.gui_ingestion_entry_bridge import get_ingestion_entries_config
        entries = get_ingestion_entries_config()
        exports.append({"module": "gui_ingestion_entry_bridge", "label": f"接入入口工位化 ({len(entries)} 类入口)", "type": "enhancement_C"})
    except Exception:
        exports.append({"module": "gui_ingestion_entry_bridge", "label": "接入入口工位化 (未加载)", "type": "enhancement_C"})
    try:
        from app.core.gui_metadata_frontend_bridge import get_metadata_field_registry
        fields = get_metadata_field_registry()
        exports.append({"module": "gui_metadata_frontend_bridge", "label": f"Metadata 前台化 ({len(fields)} 个活跃字段)", "type": "enhancement_D"})
    except Exception:
        exports.append({"module": "gui_metadata_frontend_bridge", "label": "Metadata 前台化 (未加载)", "type": "enhancement_D"})
    return exports