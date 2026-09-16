"""Content-addressed identity matching for explicitly approved sample exceptions."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional


ACTION_SKIP_SELF_REVIEW = 'skip_self_review'
ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK = 'english_visual_transcription_lock'
ACTION_FIXED_ENGLISH_CHOICE_SLOTS = 'fixed_english_choice_slots'
ACTION_MATH_SLOT_PRESENCE_GUARD = 'math_slot_presence_guard'
ACTION_MATH_FIXED_SAMPLE_GUARD = 'math_fixed_sample_guard'
ACTION_CHINESE_FIXED_ANSWER = 'chinese_fixed_answer'
ACTION_CHINESE_PERSONIFICATION_VERIFIER = 'chinese_personification_verifier'

_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
_MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__),
    'data',
    'experiments',
    'fixed_document_special_cases_20260726.json',
)


def normalize_document_sha256(value: Any) -> str:
    normalized = str(value or '').replace(' ', '').strip().lower()
    return normalized if _SHA256_RE.fullmatch(normalized) else ''


def load_document_special_case_manifest() -> Dict[str, Any]:
    with open(_MANIFEST_PATH, 'r', encoding='utf-8') as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not isinstance(payload.get('cases'), list):
        raise ValueError('固定测试文档特例清单格式无效')
    return payload


def match_document_special_case(
    subject: str,
    page_num: int,
    action: str,
    *,
    source_document_sha256: str = '',
    sample_id: str = '',
    manifest: Optional[Dict[str, Any]] = None,
    feedback_runtime=None,
) -> Optional[Dict[str, Any]]:
    """Return an approved case and its match basis.

    A supplied source hash is authoritative: if it is invalid or does not match,
    legacy sample IDs are deliberately ignored. Legacy IDs are only a fallback
    for archived workspaces that have no source-document hash.
    """
    normalized_subject = str(subject or '').strip().lower()
    normalized_action = str(action or '').strip()
    raw_source_hash = str(source_document_sha256 or '').strip()
    normalized_source_hash = normalize_document_sha256(raw_source_hash)
    normalized_sample_id = str(sample_id or '').strip()
    if not normalized_subject or not normalized_action:
        return None
    if raw_source_hash and not normalized_source_hash:
        return None

    if feedback_runtime is not None:
        if not normalized_source_hash or not feedback_runtime.has_specialized(normalized_subject):
            return None
        payload = {'cases': [case for skill in feedback_runtime.dependencies['skills']
                            for case in skill['content']['resources'].get('fixed_documents', {}).get('cases', [])]}
    else:
        payload = manifest or load_document_special_case_manifest()
    for case in payload.get('cases') or []:
        if not isinstance(case, dict):
            continue
        if str(case.get('subject') or '').strip().lower() != normalized_subject:
            continue
        action_pages = (case.get('actions') or {}).get(normalized_action) or []
        if int(page_num or 0) not in {
            int(value) for value in action_pages if str(value).strip().isdigit()
        }:
            continue

        case_hash = normalize_document_sha256(case.get('source_document_sha256'))
        if normalized_source_hash:
            if not case_hash or case_hash != normalized_source_hash:
                continue
            matched_by = 'source_document_sha256'
        else:
            legacy_ids = {
                str(value or '').strip()
                for value in case.get('legacy_sample_ids') or []
                if str(value or '').strip()
            }
            if not normalized_sample_id or normalized_sample_id not in legacy_ids:
                continue
            matched_by = 'legacy_sample_id'

        return {
            'case_id': str(case.get('case_id') or ''),
            'subject': normalized_subject,
            'page': int(page_num or 0),
            'action': normalized_action,
            'matched_by': matched_by,
            'source_document_sha256': case_hash,
            'manifest_version': str(payload.get('version') or ''),
        }
    return None


def document_special_case_enabled(
    subject: str,
    page_num: int,
    action: str,
    *,
    source_document_sha256: str = '',
    sample_id: str = '',
    manifest: Optional[Dict[str, Any]] = None,
feedback_runtime=None) -> bool:
    return match_document_special_case(
        subject,
        page_num,
        action,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
        manifest=manifest,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) is not None
