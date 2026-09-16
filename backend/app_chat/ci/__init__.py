# app_chat/ci/__init__.py
# Continuous Image (CI) 功能模块包
# Phase 7.3 起，这里作为 continuous_image_service.py 的薄转发目标，
# 统一重导出对外兼容符号与少量仍被内部惰性导入使用的 helper。

from app_chat.ci._utils import (
    _ci_dmt_root,
    _ci_d_cache_root,
    _resolve_user_file_path,
)
from app_chat.ci.index_manager import CIIndexManager
from app_chat.ci.d_layer import DCacheManager, build_d_layer  # Phase 3.5
from app_chat.ci.m_layer import (  # Phase 4.8 / 7.3
    _build_image_layout_visual,
    build_m_layer,
    build_m_layer_v2,
)
from app_chat.ci.t_layer import build_t_layer  # Phase 5.5
from app_chat.ci.r_layer import (  # Phase 6.5
    build_r_layer,
    iterate_ci_reproduction_unit,
    save_ci_reproduction_file,
    save_ci_reproduction_iter_context,
    rollback_ci_reproduction_unit,
    _is_reproduction_iterating,
    _set_reproduction_iterating,
    _parse_reference_image_payload,
)
from app_chat.ci.orchestrator import (  # Phase 7.3
    build_analysis_id,
    get_ci_result,
    prepare_analysis_workspace,
    query_ci_analyses,
    redo_ci_analysis,
    run_ci_analysis,
    run_ci_sketch_r_quickstart,
    start_ci_reproduction,
)
from app_chat.ci.legacy import (  # Phase 7.3
    build_group_id,
    build_image_units,
    get_continuous_image_result,
    prepare_group_workspace,
    render_pdf_pages_to_assets,
    run_continuous_image_analysis,
)


__all__ = [
    '_build_image_layout_visual',
    '_ci_d_cache_root',
    '_ci_dmt_root',
    '_is_reproduction_iterating',
    '_parse_reference_image_payload',
    '_resolve_user_file_path',
    '_set_reproduction_iterating',
    'CIIndexManager',
    'DCacheManager',
    'build_analysis_id',
    'build_d_layer',
    'build_group_id',
    'build_image_units',
    'build_m_layer',
    'build_m_layer_v2',
    'build_r_layer',
    'build_t_layer',
    'get_ci_result',
    'get_continuous_image_result',
    'iterate_ci_reproduction_unit',
    'prepare_analysis_workspace',
    'prepare_group_workspace',
    'query_ci_analyses',
    'redo_ci_analysis',
    'render_pdf_pages_to_assets',
    'rollback_ci_reproduction_unit',
    'run_ci_analysis',
    'run_ci_sketch_r_quickstart',
    'run_continuous_image_analysis',
    'save_ci_reproduction_file',
    'save_ci_reproduction_iter_context',
    'start_ci_reproduction',
]
