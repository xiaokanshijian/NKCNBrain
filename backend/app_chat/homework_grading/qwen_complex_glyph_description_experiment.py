"""Qwen-only runner for the isolated C-mode glyph-description probe.

It reuses C mode's image-only request schema and fixed p11 ROI, but writes to
its own output directory and invokes the existing non-thinking Qwen JSON
client.  It cannot invoke Gemini, B mode, A mode, or the formal review chain.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

from app_chat.homework_grading.blind_pinyin_review_experiment import _content_from_response
from app_chat.homework_grading.complex_glyph_description_experiment import (
    DEFAULT_CASE_PATH,
    DEFAULT_REPEATS,
    EXPERIMENT_MODE,
    _run_one,
    evaluate,
    prepare_case,
    write_report,
)
from app_chat.homework_grading.llm_clients import _call_qwen_json, homework_qwen_model
from app_chat.homework_grading.utils import safe_json_dump


BACKEND = 'qwen'
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'analysis_output' / 'qwen_complex_glyph_description_20260718'


def call_qwen_c_description_model(messages: List[Dict[str, Any]]) -> str:
    """Use Qwen non-thinking JSON mode; no model or prompt override is accepted."""
    response = _call_qwen_json(
        messages,
        {'enable_thinking': False},
        temperature=0.1,
    )
    return _content_from_response(response)


def run_qwen_c_mode() -> Dict[str, Any]:
    prepared = prepare_case(DEFAULT_CASE_PATH, DEFAULT_OUTPUT_DIR)
    retry_state = {'used': 0}
    results: List[Dict[str, Any]] = []
    for repeat in range(1, DEFAULT_REPEATS + 1):
        result = _run_one(
            prepared,
            DEFAULT_OUTPUT_DIR,
            repeat,
            retry_state,
            call_qwen_c_description_model,
        )
        results.append(result)
        if result.get('status') == 'quota_limited':
            break
    summary = {
        'experiment_mode': EXPERIMENT_MODE,
        'backend': BACKEND,
        'model': homework_qwen_model(),
        'physical_request_count': sum(len(item.get('attempts') or []) for item in results),
        'format_retries_used': retry_state['used'],
        'results': results,
    }
    safe_json_dump(str(DEFAULT_OUTPUT_DIR / 'run_summary.json'), summary)
    evaluation = evaluate(DEFAULT_CASE_PATH, results)
    evaluation.update({'backend': BACKEND, 'model': homework_qwen_model()})
    write_report(DEFAULT_OUTPUT_DIR, evaluation, summary['physical_request_count'], retry_state['used'])
    return {'summary': summary, 'evaluation': evaluation, 'prepared': prepared}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Qwen-only C-mode glyph-description shadow probe')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if args.prepare_only == args.run:
        raise SystemExit('choose exactly one of --prepare-only or --run')
    if args.prepare_only:
        prepared = prepare_case(DEFAULT_CASE_PATH, DEFAULT_OUTPUT_DIR)
        print(f"prepared Qwen C-mode ROI: {prepared['crop_path']}")
        return 0
    result = run_qwen_c_mode()
    print(f"Qwen C-mode evaluation: {'passed' if result['evaluation']['passed'] else 'not passed'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
