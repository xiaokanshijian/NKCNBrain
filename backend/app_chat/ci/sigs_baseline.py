# CI 模块外部依赖基准 (Phase 0 产物)
# 重构期间，此文件中列出的所有符号必须通过 `from app_chat.continuous_image_service import ...` 保持可访问。
#
# 搜索结果（截止 2026-03-31 refactor/ci-module-split 分支）：
#
# ── 导入来源文件 ──────────────────────────────────────────────────────────────
# 1. app_chat/views_continuous_image.py  L11-31  (顶层 import)
# 2. app_chat/views_continuous_image.py  L344    (inline import inside function)
# 3. app_chat/views_continuous_image.py  L450    (inline import inside function)
# 4. app_chat/ci_result_adapter.py       L26-33  (顶层 import)
# 5. app_chat/views_ci_feedback.py       L14     (顶层 import)
# 6. app_chat/views_ci_feedback.py       L327    (inline import inside function, 重复定义)
#
# ── 被外部引用的符号清单（共 21 个）──────────────────────────────────────────

EXTERNAL_SYMBOLS = {
    # ── 新架构主流程 ──────────────────────────────────────────────────────────
    "build_analysis_id": "def build_analysis_id(mode: str, files: List[str]) -> str",
    "CIIndexManager": "class CIIndexManager —— 线程安全索引管理，静态方法类",
    "query_ci_analyses": "def query_ci_analyses(username: str, files: List[str]) -> Dict[str, Any]",
    "run_ci_analysis": (
        "def run_ci_analysis(task_id: str, username: str, mode: str, selected_files: List[str], "
        "analysis_id: str, force_rebuild_mt: bool = False, model_id: Optional[str] = None, "
        "context_docs: Optional[List[str]] = None, context_card_ids: Optional[List[int]] = None) -> None"
    ),
    "redo_ci_analysis": (
        "def redo_ci_analysis(task_id: str, username: str, analysis_id: str, redo_scope: str = 'mt') -> None"
    ),
    "start_ci_reproduction": (
        "def start_ci_reproduction(task_id: str, username: str, analysis_id: str, "
        "force_rebuild: bool = False, use_sketch_input: bool = True, "
        "use_original_sketch_as_r: bool = False) -> None"
    ),
    "iterate_ci_reproduction_unit": (
        "def iterate_ci_reproduction_unit(task_id: str, username: str, analysis_id: str, unit_id: str, "
        "revision_instruction: Optional[str] = None, reference_image_b64: Optional[str] = None, "
        "reference_image_mime: str = 'image/png', image_quality: str = 'normal', "
        "iter_context_updates: Optional[Dict[str, Any]] = None) -> None"
    ),
    "save_ci_reproduction_iter_context": (
        "def save_ci_reproduction_iter_context(username: str, analysis_id: str, unit_id: str, "
        "iter_context_updates: Dict[str, Any]) -> Dict[str, Any]"
    ),
    "_is_reproduction_iterating": (
        "def _is_reproduction_iterating(username: str, analysis_id: str, unit_id: str) -> bool"
    ),
    "_parse_reference_image_payload": (
        "def _parse_reference_image_payload(reference_image: Any) -> Tuple[Optional[str], str]"
    ),
    "get_ci_result": "def get_ci_result(username: str, analysis_id: str) -> Dict[str, Any]",
    "rollback_ci_reproduction_unit": (
        "def rollback_ci_reproduction_unit(username: str, analysis_id: str, unit_id: str) -> Dict[str, Any]"
    ),
    # ── 路径工具（被 views 和 adapter 直接引用）─────────────────────────────
    "_ci_dmt_root": "def _ci_dmt_root(username: str) -> str",
    "_ci_d_cache_root": "def _ci_d_cache_root(username: str) -> str",
    # ── 旧架构兼容 ───────────────────────────────────────────────────────────
    "build_group_id": "def build_group_id(username: str, mode: str, selected_files: List[Any]) -> str",
    "get_continuous_image_result": (
        "def get_continuous_image_result(group_id: str, username: Optional[str] = None) -> Dict[str, Any]"
    ),
    "run_continuous_image_analysis": (
        "def run_continuous_image_analysis(task_id: str, username: str, mode: str, "
        "selected_files: List[Any], group_id: str, force_rebuild: bool = False, "
        "model_id: Optional[str] = None) -> None"
    ),
    # ── inline import（在函数体内部动态导入）────────────────────────────────
    "_set_reproduction_iterating": (
        "def _set_reproduction_iterating(username: str, analysis_id: str, unit_id: str, running: bool) -> None"
        "  # views_continuous_image.py L344 inline import"
    ),
    "_resolve_user_file_path": (
        "def _resolve_user_file_path(username: str, file_name: str) -> str"
        "  # views_continuous_image.py L450 inline import"
    ),
}

# ── ci_prompts.py 被 continuous_image_service.py 依赖的符号清单 ──────────────
# (ci_prompts.py 只被 continuous_image_service.py 导入，外部不直接用)
CI_PROMPTS_SYMBOLS = [
    "CI_M_LAYER_STRUCTURE_SYSTEM_PROMPT",
    "CI_M_LAYER_STRUCTURE_USER_PROMPT_TEMPLATE",
    "CI_M_LAYER_STRUCTURE_MERGE_SYSTEM_PROMPT",
    "CI_M_LAYER_STRUCTURE_MERGE_USER_PROMPT_TEMPLATE",
    "CI_M_LAYER_SUMMARY_SYSTEM_PROMPT",
    "CI_M_LAYER_SUMMARY_USER_PROMPT_TEMPLATE",
    "CI_M_LAYER_VERIFY_SYSTEM_PROMPT",
    "CI_M_LAYER_VERIFY_USER_PROMPT_TEMPLATE",
    "CI_M_LAYER_PATCH_SYSTEM_PROMPT",
    "CI_M_LAYER_PATCH_USER_PROMPT_TEMPLATE",
    "CI_M_LAYER_CONTEXT_FULL_TEMPLATE",
    "CI_M_LAYER_CONTEXT_BRIEF_TEMPLATE",
    "CI_T_LAYER_SYSTEM_PROMPT",
    "CI_T_LAYER_USER_PROMPT_TEMPLATE",
    "CI_D_GREY_REPAIR_SYSTEM_PROMPT",
    "CI_D_GREY_REPAIR_USER_PROMPT_TEMPLATE",
    "CI_D_BLACK_DESCRIBE_SYSTEM_PROMPT",
    "CI_D_BLACK_DESCRIBE_USER_PROMPT_TEMPLATE",
    "CI_R_REPRODUCTION_WITH_SKETCH_SYSTEM_PROMPT",
    "CI_R_REPRODUCTION_WITH_SKETCH_USER_PROMPT_TEMPLATE",
    "CI_R_REPRODUCTION_WITHOUT_SKETCH_SYSTEM_PROMPT",
    "CI_R_REPRODUCTION_WITHOUT_SKETCH_USER_PROMPT_TEMPLATE",
]
