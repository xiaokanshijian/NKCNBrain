"""Backward-compatible exports for the refactored homework grading LLM modules.

New code should import from prompts.py, llm_clients.py, grader_pass1.py,
grader_pass1_5.py, or grader_pass2.py directly. This module remains so older
callers that imported app_chat.homework_grading.llm keep working.
"""

from app_chat.homework_grading.grader_pass1 import (
    _default_boundary,
    _normalize_boundary,
    _normalize_pass1_result,
    detect_page_layout,
    detect_page_only,
    grade_page,
    grade_page_from_detect,
    grade_page_questions,
    pass1_two_stage_enabled,
)
from app_chat.homework_grading.grader_pass1_5 import grade_cross_page_group
from app_chat.homework_grading.grader_pass2 import (
    _build_diagnosis_from_ontology,
    _build_zone_classification_from_ontology,
    _call_pass2_feedback_llm,
    _flatten_ontology_evidence,
    _ontology_entry_to_zone_item,
    _overlay_ontology_zones,
    _slim_memory_for_pass2,
    _validate_pass2_result,
    _validate_unified_report,
    analyze_pass2,
    pass2_user_prompt,
)
from app_chat.homework_grading.llm_clients import (
    _call_qwen_json,
    _deepseek_client,
    _extract_first_json_object,
    _loads_json_with_retry_text,
    _qwen_client,
    _qwen_thinking_enabled,
    _strip_json_text,
    _write_text,
    homework_deepseek_model,
    homework_qwen_model,
)
from app_chat.homework_grading.prompts import (
    CHINESE_CROSS_PAGE_SUFFIX,
    CROSS_PAGE_SYSTEM,
    MATH_VERIFICATION_SUFFIX,
    PASS1_SYSTEM_BASE,
    PASS2_FEEDBACK_SYSTEM_BASE,
    PASS2_SYSTEM_BASE,
    PASS_L5_SYSTEM_BASE,
    _LABEL_SUFFIX_TEMPLATE,
    _SUBJECT_HINTS,
    _UNCERTAIN_RULES,
    _filter_curriculum_by_evidence,
    _filter_curriculum_by_memory,
    _format_curriculum_block,
    _format_goal_block,
    _format_ontology_zones_for_pass2,
    _format_profile_summary,
    _format_zone_table,
    build_prior_context,
    cross_page_user_prompt,
    ontology_system,
    ontology_user,
    pass1_detect_system,
    pass1_detect_user_prompt,
    pass1_grade_system,
    pass1_grade_user_prompt,
    pass1_system,
    pass1_user_prompt,
    pass2_feedback_system,
    pass2_feedback_user,
    pass2_system,
)

__all__ = [name for name in globals() if not name.startswith('__')]
