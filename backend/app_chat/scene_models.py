# -*- coding: utf-8 -*-
"""场景模型配置：admin 可改，每次读文件，保存即生效。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'scene_models_config.json')
_MODEL_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config', 'model_config')

# type：config_abbr = 仅换 abbr，走 config_manager；raw = 直连 API 的 model 字符串
SCENE_SLOTS: Dict[str, Dict[str, Any]] = {
    # ── P0 ──
    'card_html': {
        'label': 'HTML助记卡生成',
        'group': 'P0',
        'type': 'config_abbr',
        'default': 'claude-opus-4.7',
        'options': ['claude-opus-4.7', 'claude-opus-4.6', 'claude-sonnet-4.6', 'claude-4-sonnet'],
    },
    'gxx_claude': {
        'label': '本体 Gxx.md 整理更新 · Claude',
        'group': 'P0',
        'type': 'config_abbr',
        'default': 'claude-sonnet-4.6',
        'options': ['claude-sonnet-4.6', 'claude-opus-4.6', 'claude-4-sonnet', 'claude-sonnet-4.5'],
    },
    'gxx_gemini': {
        'label': '本体 Gxx.md 整理更新 · Gemini',
        'group': 'P0',
        'type': 'raw',
        'default': 'gemini-3.1-pro-preview',
        'options': ['gemini-3.1-pro-preview', 'gemini-3-pro-preview'],
    },
    'card_image_gemini': {
        'label': '卡片生图 · Gemini 主模型',
        'group': 'P0',
        'type': 'raw',
        'default': 'gemini-3.1-flash-image-preview-X',
        'options': [
            'gemini-3.1-flash-image-preview-X',
            'gemini-3.1-flash-image-preview',
        ],
    },
    'card_image_gemini_fallback': {
        'label': '卡片生图 · Gemini 备用',
        'group': 'P0',
        'type': 'raw',
        'default': 'gemini-3.1-flash-image-preview',
        'options': ['gemini-3.1-flash-image-preview', 'gemini-3.1-flash-image-preview-X'],
    },
    'card_image_gpt': {
        'label': '卡片生图 · GPT 主模型',
        'group': 'P0',
        'type': 'raw',
        'default': 'gpt-image-2',
        'options': ['gpt-image-2', 'gpt-image-2-all'],
    },
    'card_image_gpt_fallback': {
        'label': '卡片生图 · GPT 备用',
        'group': 'P0',
        'type': 'raw',
        'default': 'gpt-image-2-all',
        'options': ['gpt-image-2-all', 'gpt-image-2'],
    },
    'card_image_claude_spec': {
        'label': '卡片生图前 · Claude 写生图描述',
        'group': 'P0',
        'type': 'raw',
        'default': 'claude-sonnet-4-6',
        'options': ['claude-sonnet-4-6', 'claude-sonnet-5', 'claude-sonnet-4-5-20250929'],
    },
    'dmt_overlay_claude': {
        'label': 'DMT 覆盖层 · Claude 写生成说明',
        'group': 'P0',
        'type': 'raw',
        'default': 'claude-sonnet-4-20250514',
        'options': ['claude-sonnet-4-20250514', 'claude-sonnet-4-6'],
    },
    'dmt_gemini': {
        'label': 'DMT 覆盖层 · Gemini 分析/质检（dmxapi）',
        'group': 'P0',
        'type': 'raw',
        'default': 'gemini-3.1-pro-preview',
        'options': ['gemini-3.1-pro-preview', 'gemini-3-pro-preview'],
    },
    # ── P1 ──
    'output_article_claude_1': {
        'label': '输出文章 · Claude 主选',
        'group': 'P1',
        'type': 'config_abbr',
        'default': 'claude-sonnet-4.5',
        'options': ['claude-sonnet-4.5', 'claude-opus-4.7', 'claude-4-sonnet', 'claude37'],
    },
    'output_article_claude_2': {
        'label': '输出文章 · Claude 备选1',
        'group': 'P1',
        'type': 'config_abbr',
        'default': 'claude-4-sonnet',
        'options': ['claude-4-sonnet', 'claude-sonnet-4.6', 'claude37'],
    },
    'output_article_claude_3': {
        'label': '输出文章 · Claude 备选2',
        'group': 'P1',
        'type': 'config_abbr',
        'default': 'claude37',
        'options': ['claude37', 'claude-4-sonnet', 'claude-sonnet-4.5'],
    },
    # ── P2 ──
    'ci_refine_gemini': {
        'label': '连续图片 · T层精修 · Gemini',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3.1-pro-preview',
        'options': ['gemini-3.1-pro-preview', 'gemini-3-pro-preview'],
    },
    'ci_refine_qwen': {
        'label': '连续图片 · T层精修 · Qwen',
        'group': 'P2',
        'type': 'raw',
        'default': 'qwen3.6-plus',
        'options': ['qwen3.6-plus', 'qwen3.5-plus', 'qwen3.5-flash'],
    },
    'ci_snippet_gemini': {
        'label': '局部裁切识字 · Gemini',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3.1-flash-image-preview',
        'options': ['gemini-3.1-flash-image-preview', 'gemini-3.1-flash-image-preview-X'],
    },
    'ci_snippet_qwen': {
        'label': '局部裁切识字 · Qwen',
        'group': 'P2',
        'type': 'raw',
        'default': 'qwen3.6-plus',
        'options': ['qwen3.6-plus', 'qwen3.5-plus'],
    },
    'ci_auto_local_image': {
        'label': '自动迭代生图 · 候选模型',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3.1-flash-image-preview',
        'options': ['gemini-3.1-flash-image-preview', 'gemini-3.1-flash-image-preview-X', 'gpt-image-2-all'],
    },
    'ci_auto_gemini_pro': {
        'label': '自动迭代 · 判断/复核 · Gemini',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3.1-pro-preview',
        'options': ['gemini-3.1-pro-preview', 'gemini-3-pro-preview'],
    },
    'ci_auto_qwen': {
        'label': '自动迭代 · 判断/复核 · Qwen',
        'group': 'P2',
        'type': 'raw',
        'default': 'qwen3.6-plus',
        'options': ['qwen3.6-plus', 'qwen3.5-plus'],
    },
    'ci_llm_qwen35_plus': {
        'label': '版面理解 · M/T层 · qwen3.5-plus',
        'group': 'P2',
        'type': 'raw',
        'default': 'qwen3.5-plus',
        'options': ['qwen3.5-plus', 'qwen3.6-plus'],
    },
    'ci_llm_qwen35_flash': {
        'label': '版面理解 · M层 · qwen3.5-flash',
        'group': 'P2',
        'type': 'raw',
        'default': 'qwen3.5-flash',
        'options': ['qwen3.5-flash', 'qwen3.6-plus'],
    },
    'ci_llm_claude_sonnet': {
        'label': '版面理解 · M/T层 · Claude Sonnet',
        'group': 'P2',
        'type': 'config_abbr',
        'default': 'claude-4-sonnet',
        'options': ['claude-4-sonnet', 'claude-sonnet-4.6', 'claude-sonnet-4.5'],
    },
    'ci_t_layer_gemini': {
        'label': 'T层降级 · Gemini',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3-pro-preview',
        'options': ['gemini-3-pro-preview', 'gemini-3.1-pro-preview'],
    },
    'ci_r_layer_gemini': {
        'label': '版面复现生图 · Gemini',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3.1-flash-image-preview-X',
        'options': ['gemini-3.1-flash-image-preview-X', 'gemini-3.1-flash-image-preview'],
    },
    'ci_overlay_dmt_gemini': {
        'label': '覆盖层分析 · DMT Gemini',
        'group': 'P2',
        'type': 'raw',
        'default': 'gemini-3.1-pro-preview',
        'options': ['gemini-3.1-pro-preview', 'gemini-3-pro-preview'],
    },
    'ci_overlay_sketch_qwen': {
        'label': '覆盖层草图估算 · Qwen',
        'group': 'P2',
        'type': 'raw',
        'default': 'qwen3.6-plus',
        'options': ['qwen3.6-plus', 'qwen3.5-plus'],
    },
    'ocr_model': {
        'label': 'PDF/图片 OCR 模型标识',
        'group': 'P2',
        'type': 'raw',
        'default': 'OCR',
        'options': ['OCR', 'OCR2'],
    },
    # ── P3 ──
    'homework_qwen': {
        'label': '批改识图 · Qwen',
        'group': 'P3',
        'type': 'raw',
        'default': 'qwen3.5-flash',
        'options': ['qwen3.5-flash', 'qwen3.6-plus', 'qwen3.5-plus'],
    },
    'homework_deepseek': {
        'label': '综合诊断/归纳 · DeepSeek',
        'group': 'P3',
        'type': 'raw',
        'default': 'deepseek-v4-flash',
        'options': ['deepseek-v4-flash', 'deepseek-chat'],
    },
    'homework_review_gemini': {
        'label': '批改结果自检',
        'group': 'P3',
        'type': 'raw',
        'default': 'gemini-3.1-pro-preview',
        'options': [
            'gemini-3.1-pro-preview',
            'gemini-3-pro-preview',
            'kimi-k3',
        ],
        'hint': '默认 Gemini（dmxapi）。',
    },
    # ── P4 · 语义梳理（任务簇等）──
    'task_cluster_semantic': {
        'label': '任务簇语义梳理',
        'group': 'P4',
        'type': 'llm_slot',
        'default': 'gemini-3.1-pro-preview',
        'options': [
            'gemini-3.1-pro-preview',
            'gemini-3-pro-preview',
            'claude-sonnet-4.6',
            'claude-opus-4.8',
            'claude-opus-4.6',
        ],
    },
    'card_semantic_keywords': {
        'label': '建卡语义关键词',
        'group': 'P4',
        'type': 'llm_slot',
        'default': 'kimi',
        'options': [
            'kimi',
            'kimi-k3',
            'claude-sonnet-5',
            'claude-opus-4.8',
            'deepseek-v4-flash',
        ],
        'hint': '建卡/钉卡时抽取 keyWords；Claude 走人性化思考协议；deepseek-v4-flash 走官方 API。',
    },
    'notebook_memory_write': {
        'label': '长短记忆·写/压',
        'group': 'P4',
        'type': 'llm_slot',
        'default': 'deepseek-v4-flash',
        'options': [
            'deepseek-v4-flash',
            'deepseek-chat',
            'claude-sonnet-5',
            'kimi',
        ],
        'hint': '问答后记忆萃取与窗口压缩用较快模型，默认 deepseek-v4-flash。',
    },
    'notebook_memory_dream': {
        'label': '长短记忆·AutoDream',
        'group': 'P4',
        'type': 'llm_slot',
        'default': 'claude-sonnet-5',
        'options': [
            'claude-sonnet-5',
            'claude-opus-4.8',
            'claude-sonnet-4.6',
            'deepseek-v4-flash',
        ],
        'hint': '定期整理记忆用更强模型；失败会降级到写记忆模型。',
    },
    # ── P5（仅 Admin 展示，暂不可改）──
    'volcano_tts': {
        'label': '语音合成 · volcano_tts',
        'group': 'P5',
        'type': 'display_only',
        'default': 'volcano_tts',
        'options': ['volcano_tts'],
        'hint': '暂不支持在此修改：各语音合成服务调用方式不同，后续再开放。',
    },
}


def _default_values() -> Dict[str, str]:
    return {
        key: str(meta.get('default') or '')
        for key, meta in SCENE_SLOTS.items()
        if meta.get('type') != 'display_only'
    }


def load_scene_models_config() -> Dict[str, str]:
    defaults = _default_values()
    try:
        if os.path.isfile(_CONFIG_FILE):
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                values = raw.get('values') if isinstance(raw.get('values'), dict) else raw
                if isinstance(values, dict):
                    merged = dict(defaults)
                    for key, val in values.items():
                        if key in SCENE_SLOTS and val is not None:
                            if SCENE_SLOTS[key].get('type') == 'display_only':
                                continue
                            merged[key] = str(val).strip()
                    return merged
    except Exception as e:
        print(f'[SceneModels] 加载配置失败，使用默认值: {e}')
    return defaults


def save_scene_models_config(values: Dict[str, str]) -> bool:
    try:
        payload = {'values': dict(load_scene_models_config())}
        for key, val in (values or {}).items():
            if key not in SCENE_SLOTS:
                continue
            if SCENE_SLOTS[key].get('type') == 'display_only':
                continue
            cleaned = str(val or '').strip()
            if not cleaned:
                continue
            err = validate_scene_value(key, cleaned)
            if err:
                raise ValueError(err)
            payload['values'][key] = cleaned
        with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'[SceneModels] 配置已保存: {payload["values"]}')
        return True
    except ValueError:
        raise
    except Exception as e:
        print(f'[SceneModels] 保存失败: {e}')
        return False


def validate_scene_value(key: str, value: str) -> Optional[str]:
    meta = SCENE_SLOTS.get(key)
    if not meta:
        return f'未知配置项: {key}'
    if meta.get('type') == 'display_only':
        return f'{meta.get("label")}: 暂不支持修改'
    val = str(value or '').strip()
    if not val:
        return f'{key} 不能为空'
    slot_type = meta.get('type')
    options = meta.get('options') or []
    if slot_type == 'config_abbr':
        cfg_path = os.path.join(_MODEL_CONFIG_DIR, f'{val}.json')
        if not os.path.isfile(cfg_path):
            return f'{meta.get("label")}: 配置缩写 {val} 无对应 json'
        return None
    if slot_type == 'llm_slot':
        if options and val not in options:
            return f'{meta.get("label")}: {val} 不在允许列表 {options}'
        if val.startswith('gemini'):
            return None
        # 建卡语义关键词：kimi 走 moonshot 专用路径，无需强制依赖 model_config json
        if key == 'card_semantic_keywords' and val.lower() in ('kimi', 'moonshot', 'kimi-legacy'):
            return None
        cfg_path = os.path.join(_MODEL_CONFIG_DIR, f'{val}.json')
        if not os.path.isfile(cfg_path):
            return f'{meta.get("label")}: 配置缩写 {val} 无对应 json'
        return None
    if options and val not in options:
        return f'{meta.get("label")}: {val} 不在允许列表 {options}'
    return None


def get_scene_value(key: str, default: Optional[str] = None) -> str:
    meta = SCENE_SLOTS.get(key)
    if meta and meta.get('type') == 'display_only':
        return str(meta.get('default') or '')
    fallback = default if default is not None else (str(meta.get('default')) if meta else '')
    cfg = load_scene_models_config()
    val = str(cfg.get(key) or fallback or '').strip()
    return val or str(fallback or '')


def get_scene_abbr_chain(keys: List[str], defaults: Optional[List[str]] = None) -> List[str]:
    defaults = defaults or []
    out: List[str] = []
    for idx, key in enumerate(keys):
        d = defaults[idx] if idx < len(defaults) else ''
        abbr = get_scene_value(key, d)
        if abbr and abbr not in out:
            out.append(abbr)
    return out


def resolve_openai_cfg_from_abbr(
    abbr: str,
    *,
    default_model: str = '',
    default_base: str = '',
    default_key: str = '',
) -> Dict[str, str]:
    """从 config_manager 或 model_config json 解析 OpenAI 兼容连接参数。"""
    abbr = str(abbr or '').strip()
    if abbr:
        try:
            from app_chat.config.config_manager import config_manager

            mc = config_manager.get_model_config(abbr)
            if mc:
                cur = mc.get_config() or {}
                model = str(mc.get_full_name() or cur.get('model_name') or default_model).strip()
                base = str(cur.get('openai_api_base') or default_base).strip().rstrip('/')
                key = str(cur.get('openai_api_key') or default_key).strip()
                return {
                    'model': model or default_model,
                    'base_url': base or default_base.rstrip('/'),
                    'api_key': key or default_key,
                }
        except Exception:
            pass
        cfg_path = os.path.join(_MODEL_CONFIG_DIR, f'{abbr}.json')
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                c = (raw or {}).get('config') or {}
                return {
                    'model': str(c.get('model_name') or default_model).strip(),
                    'base_url': str(c.get('openai_api_base') or default_base).strip().rstrip('/'),
                    'api_key': str(c.get('openai_api_key') or default_key).strip(),
                }
            except Exception:
                pass
    return {
        'model': default_model,
        'base_url': default_base.rstrip('/'),
        'api_key': default_key,
    }


def _dmxapi_default_cfg(model: str = 'gemini-3.1-pro-preview') -> Dict[str, str]:
    import os
    return {
        'model': model,
        'base_url': os.environ.get('NKCN_DMT_GEMINI_BASE_URL', 'https://www.dmxapi.cn/v1').rstrip('/'),
        'api_key': os.environ.get(
            'NKCN_DMT_GEMINI_API_KEY',
            os.environ.get("DMX_API_KEY", ""),
        ),
    }


def resolve_llm_slot_cfg(
    key: str,
    *,
    default_raw: str = 'gemini-3.1-pro-preview',
    default_abbr: str = 'claude-sonnet-4.6',
) -> Dict[str, str]:
    """解析 llm_slot：gemini* 走 dmxapi，其余走 config_abbr（cloudapi 等）。"""
    val = get_scene_value(key, default_raw)
    if str(val).startswith('gemini'):
        return _dmxapi_default_cfg(str(val))
    return resolve_openai_cfg_from_abbr(
        str(val or default_abbr),
        default_model='claude-sonnet-4-6',
        default_base='https://chat.cloudapi.vip/v1/',
        default_key=os.environ.get("NKCN_LLM_API_KEY", ""),
    )


def get_admin_payload() -> Dict[str, Any]:
    values = load_scene_models_config()
    slots: List[Dict[str, Any]] = []
    for key, meta in SCENE_SLOTS.items():
        is_display_only = meta.get('type') == 'display_only'
        slots.append({
            'key': key,
            'label': meta.get('label'),
            'group': meta.get('group'),
            'type': meta.get('type'),
            'default': meta.get('default'),
            'options': meta.get('options') or [],
            'value': meta.get('default') if is_display_only else values.get(key, meta.get('default')),
            'hint': meta.get('hint') or '',
            'editable': not is_display_only,
        })
    return {'values': values, 'slots': slots}
