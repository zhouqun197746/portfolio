"""
gui_rag_search_runner.py  v1.0.0-p2-gui-rag-search-panel (P2_GUI)
"""
from app.core.gui_rag_search_panel_model import build_gui_rag_search_panel_bundle


def run_preview_gui_rag_search_panel() -> dict:
    return build_gui_rag_search_panel_bundle()
