"""
world_content_rag_integration.py  v1.0.0-p2-world-content-pack (P2_WORLD)

Adapts world content pack data for RAG filter/boost configuration.

Merges world-level policy templates with per-target metadata inference
results to produce strict_filters / soft_boosts / ignored_fields.
"""
from app.core.world_content_pack_schema import extract_default_metadata_hints

# Fields where world pack provides strict filter templates
WORLD_STRICT_FILTER_FIELDS = {"storyline_slot", "beat_type", "conflict_type"}

# Fields where world pack provides soft boost templates
WORLD_SOFT_BOOST_FIELDS = {"primary_emotion", "mechanism_tags", "mood_tags"}


def build_world_content_rag_context(pack_bundle: dict) -> dict:
    """
    Build a RAG integration context dict from a world pack.

    Returns template strict_filters, soft_boosts, and ignored_field hints
    that the RAG integration layer can merge into per-target configs.
    """
    hints = extract_default_metadata_hints(pack_bundle)

    # Template strict_filters (world-level defaults, not per-target)
    strict_filter_templates: dict[str, list[str] | None] = {}
    for field in WORLD_STRICT_FILTER_FIELDS:
        if field == "storyline_slot":
            vals = hints.get("allowed_storyline_slots", [])
            strict_filter_templates[field] = vals if vals else None
        elif field == "beat_type":
            vals = hints.get("allowed_beat_types", [])
            strict_filter_templates[field] = vals if vals else None
        elif field == "conflict_type":
            vals = hints.get("default_conflict_types", [])
            strict_filter_templates[field] = vals if vals else None

    # Template soft_boosts (world-level defaults)
    soft_boost_templates: dict[str, list[str] | None] = {}
    for field in WORLD_SOFT_BOOST_FIELDS:
        if field == "primary_emotion":
            vals = hints.get("default_primary_emotions", [])
            soft_boost_templates[field] = vals if vals else None
        elif field == "mechanism_tags":
            vals = hints.get("mechanism_tags", [])
            soft_boost_templates[field] = vals if vals else None
        elif field == "mood_tags":
            vals = hints.get("default_mood_tags", [])
            soft_boost_templates[field] = vals if vals else None

    return {
        "world_content_pack_id": pack_bundle.get("world_content_pack_id", ""),
        "strict_filter_templates": strict_filter_templates,
        "soft_boost_templates": soft_boost_templates,
        "hard_constraints": hints.get("hard_constraints", []),
        "character_archetypes": hints.get("character_archetypes", []),
        "location_tags": hints.get("location_tags", []),
    }


def merge_world_rag_context(
    per_target_integration_item: dict,
    world_rag_context: dict,
) -> dict:
    """
    Merge a per-target RAG integration item with world-level templates.

    World-level templates fill in fields that are empty in the per-target config.
    Does NOT override existing per-target strict_filters or soft_boosts.
    """
    merged = dict(per_target_integration_item)

    sf: dict = dict(per_target_integration_item.get("strict_filters", {}))
    sb: dict = dict(per_target_integration_item.get("soft_boosts", {}))
    ig: list = list(per_target_integration_item.get("ignored_fields", []))

    templates = world_rag_context.get("strict_filter_templates", {})
    for field, vals in templates.items():
        if vals and field not in sf:
            # Use first allowed value as the strict filter
            if isinstance(vals, list) and vals:
                sf[field] = vals[0]

    boost_templates = world_rag_context.get("soft_boost_templates", {})
    for field, vals in boost_templates.items():
        if vals and field not in sb:
            if isinstance(vals, list) and vals:
                sb[field] = vals

    merged["strict_filters"] = sf
    merged["soft_boosts"] = sb
    merged["ignored_fields"] = ig
    merged["_world_pack_id"] = world_rag_context.get("world_content_pack_id", "")

    return merged
