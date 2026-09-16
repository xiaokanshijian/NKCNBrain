import json
import os
import re
import base64
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, Optional, Tuple


HOMEWORK_ANALYZER_VERSION = 'homework_classifier_v1'
HOMEWORK_TEXT_MIN_CHARS = 80

HOMEWORK_DEFAULTS: Dict[str, Any] = {
    'is_k12_homework': False,
    'is_homework_pdf': False,
    'homework_subject': 'unknown',
    'homework_stage': 'unknown',
    'homework_confidence': 0.0,
    'homework_reason': '',
    'homework_checked_at': '',
    'homework_analyzer_version': HOMEWORK_ANALYZER_VERSION,
}

HOMEWORK_ATTR_KEYS = tuple(HOMEWORK_DEFAULTS.keys())


def is_pdf_filename(filename: str) -> bool:
    return str(filename or '').lower().endswith('.pdf')


def has_homework_attrs(attrs: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(attrs, dict):
        return False
    return 'is_k12_homework' in attrs or 'is_homework_pdf' in attrs or bool(attrs.get('homework_checked_at'))


def normalize_homework_attrs(attrs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(HOMEWORK_DEFAULTS)
    if isinstance(attrs, dict):
        merged.update({key: value for key, value in attrs.items() if key in HOMEWORK_DEFAULTS})
    is_homework = bool(merged.get('is_k12_homework') or merged.get('is_homework_pdf'))
    merged['is_k12_homework'] = is_homework
    merged['is_homework_pdf'] = is_homework
    subject = str(merged.get('homework_subject') or 'unknown').strip().lower()
    if subject not in ('math', 'chinese', 'english', 'unknown'):
        subject = 'unknown'
    merged['homework_subject'] = subject
    try:
        merged['homework_confidence'] = round(float(merged.get('homework_confidence') or 0.0), 3)
    except (TypeError, ValueError):
        merged['homework_confidence'] = 0.0
    return merged


def merge_document_attributes(existing: Optional[Dict[str, Any]], incoming: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        merged[key] = value
    return merged


def _score_terms(text: str, terms: Tuple[str, ...]) -> int:
    return sum(1 for term in terms if term and term in text)


def _detect_subject(text: str) -> Tuple[str, str]:
    subject_terms = {
        'math': ('数学', '算式', '计算', '方程', '函数', '几何', '分数', '小数', '应用题', '解方程', '证明', '三角形', '圆', '角度'),
        'chinese': ('语文', '阅读理解', '作文', '拼音', '词语', '古诗', '默写', '造句', '课文', '修改病句', '病句', '现代文'),
        'english': ('英语', 'english', '单词', '完形填空', '阅读填空', 'reading', 'grammar', 'translation', 'write', 'choose the', 'fill in'),
    }
    scores = {subject: _score_terms(text, terms) for subject, terms in subject_terms.items()}
    subject, score = max(scores.items(), key=lambda item: item[1])
    if score <= 0:
        return 'unknown', '未识别出明确学科'
    labels = {'math': '数学', 'chinese': '语文', 'english': '英语'}
    return subject, f'识别到{labels.get(subject, subject)}相关特征 {score} 项'


def _detect_stage(text: str) -> str:
    if any(term in text for term in ('小学', '一年级', '二年级', '三年级', '四年级', '五年级', '六年级')):
        return 'primary'
    if any(term in text for term in ('初中', '七年级', '八年级', '九年级', '初一', '初二', '初三')):
        return 'junior'
    return 'unknown'


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or '').strip()
    if text.startswith('```'):
        text = text.strip('`').strip()
        if text.lower().startswith('json'):
            text = text[4:].strip()
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _read_text_file_if_exists(path: str, max_chars: int = 12000) -> str:
    if not path or not os.path.isfile(path):
        return ''
    for encoding in ('utf-8', 'utf-8-sig', 'gb18030'):
        try:
            with open(path, 'r', encoding=encoding) as file_obj:
                return file_obj.read(max_chars)
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            print(f'[homework_classifier] 读取OCR文本失败: {path}, {exc}')
            return ''
    return ''


def _clean_ocr_text(text: str) -> str:
    cleaned = text or ''
    cleaned = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', cleaned)
    cleaned = re.sub(r'<\|/?(?:ref|det)\|>', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def _get_ocr_text_candidates(pdf_path: str) -> Tuple[str, ...]:
    if not pdf_path:
        return tuple()
    pdf_dir = os.path.dirname(pdf_path)
    file_base = os.path.splitext(os.path.basename(pdf_path))[0]
    ocr_dir = os.path.join(pdf_dir, f'{file_base}_ocr')
    return (
        os.path.join(ocr_dir, f'{file_base}_raw.txt'),
        os.path.join(ocr_dir, f'{file_base}_ocr.md'),
        os.path.join(ocr_dir, f'{file_base}_origin_ocr.md'),
    )


def extract_existing_ocr_text_sample(pdf_path: str, max_chars: int = 12000) -> Tuple[str, str]:
    for candidate in _get_ocr_text_candidates(pdf_path):
        text = _clean_ocr_text(_read_text_file_if_exists(candidate, max_chars=max_chars))
        if text:
            return text[:max_chars], candidate
    return '', ''


def _build_homework_classification_content(full_content: str, pdf_path: str = '') -> Tuple[str, str]:
    extracted_text = (full_content or '').strip()
    ocr_text, ocr_source = extract_existing_ocr_text_sample(pdf_path) if pdf_path else ('', '')
    if ocr_text and (len(extracted_text) < HOMEWORK_TEXT_MIN_CHARS or len(ocr_text) > len(extracted_text)):
        source_name = os.path.basename(ocr_source)
        if extracted_text:
            return (
                f'PDF可提取文本抽样：\n{extracted_text[:3000]}\n\n'
                f'扫描件OCR文本（来源：{source_name}）：\n{ocr_text[:12000]}',
                ocr_source,
            )
        return f'扫描件OCR文本（来源：{source_name}）：\n{ocr_text[:12000]}', ocr_source
    return extracted_text, ''


def _build_homework_ai_prompts(full_content: str, filename: str, scene_name: str = '', sub_scene_name: str = '', scene_summary: str = '', notebook_description: str = '') -> Tuple[str, str]:
    content_sample = (full_content or '')[:8000]
    scene_context = ''
    if scene_name or sub_scene_name or scene_summary or notebook_description:
        scene_context = f'''

当前本子/场景信息：
- 场景名称：{scene_name or '未提供'}
- 子场景名称：{sub_scene_name or '未提供'}
- 场景摘要：{(scene_summary or '')[:300]}
- 本子描述：{(notebook_description or '')[:300]}'''

    system_prompt = '''你是一个中小学作业文档分类专家。你需要判断一个 PDF 是否应该进入“连续图片批改”通道。

判为 true 的条件要同时满足：
1. 文档是中小学阶段的语文、数学或英语作业、练习、试卷、周练、订正页、练习册页面等；
2. 文档天然适合逐页批改，通常包含题目、学生作答、待判答案、错题订正或评分痕迹；
3. 学科能归入 math、chinese、english 之一。

判为 false 的常见情况：
- 大学/研究生/成人教育材料；
- 普通论文、方案、会议纪要、技术文档；
- 纯教材、讲义、答案解析、知识点资料，但不是学生作业；
- 学科不是语文、数学、英语。

只输出 JSON 对象，不输出 Markdown 或解释。字段必须是：
{
  "is_k12_homework": true/false,
  "is_homework_pdf": true/false,
  "homework_subject": "math|chinese|english|unknown",
  "homework_stage": "primary|junior|senior|unknown",
  "homework_confidence": 0.0到1.0之间的小数,
  "homework_reason": "一句中文理由"
}
is_homework_pdf 必须与 is_k12_homework 保持一致。'''

    user_prompt = f'''请判断以下 PDF 是否属于中小学语数英作业，是否应该进入连续图片批改通道。

文件名：{filename}{scene_context}

PDF文本抽样：
{content_sample}

请只返回 JSON：'''
    return system_prompt, user_prompt


def _pdf_first_page_to_base64_jpeg(pdf_path: str, max_side: int = 1600) -> str:
    if not pdf_path or not os.path.isfile(pdf_path):
        return ''
    try:
        import fitz
        from PIL import Image

        with fitz.open(pdf_path) as document:
            if len(document) <= 0:
                return ''
            page = document.load_page(0)
            matrix = fitz.Matrix(2, 2)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
            image.thumbnail((max_side, max_side))
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=88)
            return base64.b64encode(buffer.getvalue()).decode('ascii')
    except Exception as exc:
        print(f'[homework_classifier] PDF首页渲染失败: {exc}')
        return ''


def analyze_homework_document_attributes_with_gpt_vision(pdf_path: str, filename: str = '', scene_name: str = '', sub_scene_name: str = '', scene_summary: str = '', notebook_description: str = '') -> Dict[str, Any]:
    if not is_pdf_filename(filename) or not pdf_path:
        return {}
    base64_image = _pdf_first_page_to_base64_jpeg(pdf_path)
    if not base64_image:
        return {}
    try:
        from app_chat import gpt4_api

        system_prompt, user_prompt = _build_homework_ai_prompts(
            '这是一个扫描版 PDF，文本不可提取。请主要根据首页图像判断。',
            filename,
            scene_name,
            sub_scene_name,
            scene_summary,
            notebook_description,
        )
        raw = gpt4_api.make_gpt4o_image_text_requests(
            user_prompt,
            base64_image,
            system_prompt=system_prompt,
            use_fixed_params=True,
        )
        attrs = _normalize_ai_homework_result(_extract_json_object(raw), 'GPT-4o视觉完成作业属性判定')
        print(f"[homework_classifier] GPT视觉判定作业属性: is_homework={attrs.get('is_homework_pdf')}, subject={attrs.get('homework_subject')}, confidence={attrs.get('homework_confidence')}")
        return attrs
    except Exception as exc:
        print(f'[homework_classifier] GPT视觉判定作业属性失败: {exc}')
        return {}


def _normalize_ai_homework_result(data: Dict[str, Any], fallback_reason: str = '') -> Dict[str, Any]:
    attrs = normalize_homework_attrs({
        'is_k12_homework': bool(data.get('is_k12_homework') or data.get('is_homework_pdf')),
        'is_homework_pdf': bool(data.get('is_k12_homework') or data.get('is_homework_pdf')),
        'homework_subject': data.get('homework_subject') or 'unknown',
        'homework_stage': data.get('homework_stage') or 'unknown',
        'homework_confidence': data.get('homework_confidence') or 0.0,
        'homework_reason': data.get('homework_reason') or fallback_reason,
        'homework_checked_at': datetime.now().isoformat(),
        'homework_analyzer_version': HOMEWORK_ANALYZER_VERSION,
    })
    if attrs['is_homework_pdf'] and attrs['homework_subject'] == 'unknown':
        attrs['is_k12_homework'] = False
        attrs['is_homework_pdf'] = False
        attrs['homework_confidence'] = min(attrs['homework_confidence'], 0.35)
        attrs['homework_reason'] = attrs.get('homework_reason') or '未识别出语文、数学或英语学科，不进入作业批改通道'
    return attrs


def analyze_homework_document_attributes_with_gpt(full_content: str = '', filename: str = '', scene_name: str = '', sub_scene_name: str = '', scene_summary: str = '', notebook_description: str = '') -> Dict[str, Any]:
    if not is_pdf_filename(filename) or not full_content:
        return {}
    try:
        from app_chat import gpt4_api
        from llm_langchain import global_var

        system_prompt, user_prompt = _build_homework_ai_prompts(
            full_content, filename, scene_name, sub_scene_name, scene_summary, notebook_description
        )
        original_temp = global_var.config.get('temperature', 0.7)
        original_max_tokens = global_var.config.get('max_tokens', 4096)
        try:
            global_var.config['temperature'] = 0.1
            global_var.config['max_tokens'] = 300
            raw = gpt4_api.make_gpt4o_text_requests(user_prompt, system_prompt)
        finally:
            global_var.config['temperature'] = original_temp
            global_var.config['max_tokens'] = original_max_tokens
        attrs = _normalize_ai_homework_result(_extract_json_object(raw), 'GPT-4o完成作业属性判定')
        print(f"[homework_classifier] GPT判定作业属性: is_homework={attrs.get('is_homework_pdf')}, subject={attrs.get('homework_subject')}, confidence={attrs.get('homework_confidence')}")
        return attrs
    except Exception as exc:
        print(f'[homework_classifier] GPT判定作业属性失败: {exc}')
        return {}


def analyze_homework_document_attributes_with_kimi(full_content: str = '', filename: str = '', scene_name: str = '', sub_scene_name: str = '', scene_summary: str = '', notebook_description: str = '') -> Dict[str, Any]:
    if not is_pdf_filename(filename) or not full_content:
        return {}
    try:
        from app_chat import kimi_api
        from llm_langchain import global_var

        system_prompt, user_prompt = _build_homework_ai_prompts(
            full_content, filename, scene_name, sub_scene_name, scene_summary, notebook_description
        )
        original_temp = global_var.kimiConfig.get('temperature', 0.7)
        original_max_tokens = global_var.kimiConfig.get('max_tokens', 4096)
        try:
            global_var.kimiConfig['temperature'] = 0.1
            global_var.kimiConfig['max_tokens'] = 300
            response = kimi_api.make_requests(f'{system_prompt}\n\n{user_prompt}', None, False, 0.1)
            raw = response.choices[0].message.content
        finally:
            global_var.kimiConfig['temperature'] = original_temp
            global_var.kimiConfig['max_tokens'] = original_max_tokens
        attrs = _normalize_ai_homework_result(_extract_json_object(raw), 'Kimi完成作业属性判定')
        print(f"[homework_classifier] Kimi判定作业属性: is_homework={attrs.get('is_homework_pdf')}, subject={attrs.get('homework_subject')}, confidence={attrs.get('homework_confidence')}")
        return attrs
    except Exception as exc:
        print(f'[homework_classifier] Kimi判定作业属性失败: {exc}')
        return {}


def analyze_homework_document_attributes_by_rules(full_content: str = '', filename: str = '') -> Dict[str, Any]:
    if not is_pdf_filename(filename):
        attrs = normalize_homework_attrs({})
        attrs['homework_checked_at'] = datetime.now().isoformat()
        attrs['homework_reason'] = '非PDF文件，不进入作业批改通道'
        return attrs

    compact = re.sub(r'\s+', ' ', f'{filename}\n{full_content or ""}'.lower())[:20000]
    homework_terms = ('作业', '练习', '练习册', '习题', '试卷', '周练', '单元测试', '课堂练习', '课后练习', '订正', '批改', '得分', '题号')
    k12_terms = ('小学', '初中', '年级', '班级', '学生', '姓名', '家长签字', '同学', '老师', '教材', '课时')
    answer_terms = ('答案', '解答', '选择题', '填空题', '判断题', '解答题', '计算题', '阅读题', '作文', '错题')

    homework_score = _score_terms(compact, homework_terms)
    k12_score = _score_terms(compact, k12_terms)
    answer_score = _score_terms(compact, answer_terms)
    subject, subject_reason = _detect_subject(compact)
    stage = _detect_stage(compact)

    raw_score = homework_score * 2 + k12_score + answer_score + (2 if subject != 'unknown' else 0)
    confidence = min(0.98, raw_score / 12.0)
    is_homework = raw_score >= 4 and (homework_score > 0 or answer_score > 1) and subject != 'unknown'

    reasons = []
    if homework_score:
        reasons.append(f'作业/练习特征 {homework_score} 项')
    if k12_score:
        reasons.append(f'中小学场景特征 {k12_score} 项')
    if answer_score:
        reasons.append(f'题目/答案特征 {answer_score} 项')
    reasons.append(subject_reason)
    if not reasons:
        reasons.append('未命中作业文档特征')

    return normalize_homework_attrs({
        'is_k12_homework': bool(is_homework),
        'is_homework_pdf': bool(is_homework),
        'homework_subject': subject,
        'homework_stage': stage,
        'homework_confidence': confidence,
        'homework_reason': '；'.join(reasons),
        'homework_checked_at': datetime.now().isoformat(),
        'homework_analyzer_version': HOMEWORK_ANALYZER_VERSION,
    })


def analyze_homework_document_attributes(full_content: str = '', filename: str = '', scene_name: str = '', sub_scene_name: str = '', scene_summary: str = '', notebook_description: str = '', pdf_path: str = '', allow_vision_fallback: bool = True) -> Dict[str, Any]:
    if not is_pdf_filename(filename):
        return analyze_homework_document_attributes_by_rules(full_content, filename)

    classification_content, ocr_source = _build_homework_classification_content(full_content, pdf_path)
    if ocr_source:
        print(f'[homework_classifier] 复用OCR文本判定作业属性: {ocr_source}')

    if len((classification_content or '').strip()) >= HOMEWORK_TEXT_MIN_CHARS:
        attrs = analyze_homework_document_attributes_with_gpt(
            classification_content, filename, scene_name, sub_scene_name, scene_summary, notebook_description
        )
        if attrs:
            return attrs

        attrs = analyze_homework_document_attributes_with_kimi(
            classification_content, filename, scene_name, sub_scene_name, scene_summary, notebook_description
        )
        if attrs:
            return attrs

    if allow_vision_fallback and pdf_path:
        attrs = analyze_homework_document_attributes_with_gpt_vision(
            pdf_path, filename, scene_name, sub_scene_name, scene_summary, notebook_description
        )
        if attrs:
            return attrs

    attrs = analyze_homework_document_attributes_by_rules(classification_content or full_content, filename)
    attrs['homework_reason'] = f"规则兜底判定：{attrs.get('homework_reason', '')}".strip('：')
    print(f"[homework_classifier] 规则兜底判定作业属性: is_homework={attrs.get('is_homework_pdf')}, subject={attrs.get('homework_subject')}, confidence={attrs.get('homework_confidence')}")
    return attrs


def _split_username_book(username: str) -> Tuple[str, Optional[str]]:
    real_name = username.split('_')[0] if '_' in username else username
    book_name = username[len(real_name) + 1:] if '_' in username and len(username) > len(real_name) + 1 else None
    return real_name, book_name


def _resolve_notebook(username: str, scene_name: str = ''):
    from zym.models import UserNotebook, scene

    real_name, book_name = _split_username_book(username)
    if book_name:
        try:
            return UserNotebook.objects.get(username=real_name, bookName=book_name)
        except Exception:
            return None
    if scene_name:
        try:
            scene_obj = scene.objects.get(sceneDescription=scene_name)
            return UserNotebook.objects.filter(username=real_name, sid=scene_obj.sid).first()
        except Exception:
            return None
    return None


def load_document_attrs(username: str, filename: str, scene_name: str = '') -> Dict[str, Any]:
    notebook = _resolve_notebook(username, scene_name=scene_name)
    if not notebook or not getattr(notebook, 'documentFourColorDMT', ''):
        return {}
    try:
        data = json.loads(notebook.documentFourColorDMT) if notebook.documentFourColorDMT else {}
    except json.JSONDecodeError:
        return {}
    attrs = data.get(filename, {})
    return attrs if isinstance(attrs, dict) else {}


def save_document_attrs(username: str, filename: str, attrs: Dict[str, Any], scene_name: str = '') -> bool:
    notebook = _resolve_notebook(username, scene_name=scene_name)
    if not notebook:
        return False
    try:
        data = json.loads(notebook.documentFourColorDMT) if notebook.documentFourColorDMT else {}
    except json.JSONDecodeError:
        data = {}
    existing = data.get(filename, {}) if isinstance(data.get(filename, {}), dict) else {}
    data[filename] = merge_document_attributes(existing, attrs)
    notebook.documentFourColorDMT = json.dumps(data, ensure_ascii=False)
    notebook.save()
    return True


def extract_pdf_text_sample(abs_path: str, max_pages: int = 3, max_chars: int = 12000) -> str:
    if not abs_path or not os.path.isfile(abs_path):
        return ''
    try:
        import fitz
        chunks = []
        with fitz.open(abs_path) as doc:
            for page_index in range(min(len(doc), max_pages)):
                chunks.append(doc.load_page(page_index).get_text('text') or '')
                if sum(len(chunk) for chunk in chunks) >= max_chars:
                    break
        return '\n'.join(chunks)[:max_chars]
    except Exception as exc:
        print(f'[homework_classifier] PDF文本抽样失败: {exc}')
        return ''


def ensure_homework_attrs_for_file(username: str, filename: str, scene_name: str = '', full_content: str = '') -> Dict[str, Any]:
    existing = load_document_attrs(username, filename, scene_name=scene_name)
    if has_homework_attrs(existing):
        return normalize_homework_attrs(existing)
    if not is_pdf_filename(filename):
        return normalize_homework_attrs({})

    content = full_content or ''
    if not content:
        try:
            from app_chat.ci._utils import _resolve_user_file_path
            abs_path = _resolve_user_file_path(username, filename)
            content = extract_pdf_text_sample(abs_path)
        except Exception:
            content = ''

    attrs = analyze_homework_document_attributes(content, filename, scene_name=scene_name, pdf_path=abs_path if 'abs_path' in locals() else '')
    save_document_attrs(username, filename, attrs, scene_name=scene_name)
    return attrs


def is_homework_pdf_attrs(attrs: Optional[Dict[str, Any]]) -> bool:
    normalized = normalize_homework_attrs(attrs)
    return bool(normalized.get('is_k12_homework') or normalized.get('is_homework_pdf'))