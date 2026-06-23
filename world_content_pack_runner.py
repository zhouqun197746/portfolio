"""
world_content_pack_runner.py  v1.0.0-p2-world-content-pack (P2_WORLD)

CLI orchestrator for world content pack operations.
"""
from app.core.world_content_pack_schema import PACK_FIELDS
from app.core.world_content_pack_bundle_builder import (
    build_world_content_pack_bundle,
    build_world_content_pack_schema_bundle,
    list_registered_world_content_packs,
    set_pack_directory,
)
from app.core.world_content_metadata_adapter import (
    build_world_pack_metadata_context,
)
from app.core.world_content_rag_integration import (
    build_world_content_rag_context,
    merge_world_rag_context,
)


def run_show_world_content_pack_schema() -> dict:
    return build_world_content_pack_schema_bundle()


def run_list_world_content_packs() -> list[dict]:
    return list_registered_world_content_packs()


def run_apply_world_content_pack(
    world_content_pack_bundle: dict,
    target_bundle: dict,
    mode: str = "both",
) -> dict:
    """
    Apply a world pack to a target bundle (metadata inference or RAG integration).

    Args:
        world_content_pack_bundle: validated pack bundle.
        target_bundle: metadata_inference_result_bundle or rag_integration_bundle.
        mode: 'metadata_inference', 'rag_integration', or 'both'.

    Returns:
        An output dict containing the applied context.
    """
    results: dict = {
        "world_content_pack_id": world_content_pack_bundle.get("world_content_pack_id", ""),
        "mode": mode,
    }

    if mode in ("metadata_inference", "both"):
        meta_ctx = build_world_pack_metadata_context(world_content_pack_bundle)
        results["metadata_context"] = meta_ctx

    if mode in ("rag_integration", "both"):
        rag_ctx = build_world_content_rag_context(world_content_pack_bundle)
        results["rag_context"] = rag_ctx

    return results
