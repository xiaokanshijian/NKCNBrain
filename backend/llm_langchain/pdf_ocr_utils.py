"""
PDF OCR处理工具模块

提供PDF OCR识别、扫描件判断、Markdown转PDF等功能
"""

import os
import json
import requests
import fitz  # PyMuPDF
import markdown
import pdfkit
import re
from typing import Tuple, Optional, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont


# 中转服务器配置
# 注意：OCR功能默认使用192.0.2.1，如果需要支持3007，需要传递model_id参数
def get_small_model_server_url(model_id=None):
    """
    根据小模型ID获取对应的服务器URL
    3007 -> 192.0.2.1
    3001-3006 -> 192.0.2.1
    """
    if model_id and str(model_id) == "3007":
        return "http://192.0.2.1:8000"
    else:
        return "http://192.0.2.1:8000"

RELAY_SERVER_URL = "http://192.0.2.1:8000/ocr_forward"  # 默认URL，可通过get_small_model_server_url动态获取
OCR_TIMEOUT = 1200  # 20分钟超时
PAGE_BREAK = '\n\n<div STYLE="page-break-after: always;"></div>\n\n'


def run_remote_ocr_asset(file_path: str, output_dir: str, input_type: str = 'auto', model_id: Optional[str] = None,
                         ocr_model: Optional[str] = None) -> Dict[str, Any]:
    """
    统一OCR客户端：支持PDF与图片资产，返回标准化结果结构。

    参数：
        file_path: 资产路径（pdf/png/jpg/jpeg/webp）
        output_dir: OCR产物保存目录
        input_type: auto|pdf|image
        model_id: 小模型ID（用于路由OCR中转服务）
        ocr_model: OCR模型标识（OCR|OCR2）

    返回：
        {
            "success": bool,
            "markdown": {...},
            "raw_text": str,
            "total_pages": int,
            "pages": list,
            "saved_files": {"md_origin_path": str, "md_path": str, "txt_path": str},
            "error": str
        }
    """
    default_result: Dict[str, Any] = {
        'success': False,
        'markdown': {
            'markdown_origin_content': '',
            'markdown_content': ''
        },
        'raw_text': '',
        'total_pages': 0,
        'pages': [],
        'saved_files': {},
        'token_logprobs': [],
        'error': ''
    }

    if ocr_model is None:
        try:
            from app_chat.scene_models import get_scene_value
            ocr_model = get_scene_value('ocr_model', 'OCR')
        except Exception:
            ocr_model = 'OCR'

    if not os.path.exists(file_path):
        default_result['error'] = f"文件不存在: {file_path}"
        print(f"[OCR-ASSET] {default_result['error']}")
        return default_result

    ext = os.path.splitext(file_path)[1].lower()
    if input_type not in ('auto', 'pdf', 'image'):
        input_type = 'auto'

    if input_type == 'auto':
        if ext == '.pdf':
            resolved_input_type = 'pdf'
        elif ext in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
            resolved_input_type = 'image'
        else:
            default_result['error'] = f"不支持的文件类型: {ext}"
            print(f"[OCR-ASSET] {default_result['error']}")
            return default_result
    else:
        resolved_input_type = input_type

    filename = os.path.basename(file_path)
    file_base = os.path.splitext(filename)[0]

    relay_base = get_small_model_server_url(model_id)
    relay_url = f"{relay_base}/ocr_forward"

    try:
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f)}
            data = {
                'input_type': resolved_input_type,
                'ocr_model': ocr_model,
            }

            response = requests.post(relay_url, files=files, data=data, timeout=OCR_TIMEOUT)

        if response.status_code != 200:
            default_result['error'] = f"请求失败: {response.status_code}"
            print(f"[OCR-ASSET] {default_result['error']}, response={response.text[:500]}")
            return default_result

        result = response.json()
        if not result.get('success'):
            default_result['error'] = result.get('error', 'OCR处理失败')
            print(f"[OCR-ASSET] 处理失败: {default_result['error']}")
            return default_result

        os.makedirs(output_dir, exist_ok=True)

        md_origin_content = result.get('markdown', {}).get('markdown_origin_content', '')
        md_content = result.get('markdown', {}).get('markdown_content', '')
        raw_text = result.get('raw_text', '')

        md_origin_path = os.path.join(output_dir, f"{file_base}_origin_ocr.md")
        md_path = os.path.join(output_dir, f"{file_base}_ocr.md")
        txt_path = os.path.join(output_dir, f"{file_base}_raw.txt")

        with open(md_origin_path, 'w', encoding='utf-8') as f_md_origin:
            f_md_origin.write(md_origin_content)
        with open(md_path, 'w', encoding='utf-8') as f_md:
            f_md.write(md_content)
        with open(txt_path, 'w', encoding='utf-8') as f_txt:
            f_txt.write(raw_text)

        normalized = {
            'success': True,
            'markdown': {
                'markdown_origin_content': md_origin_content,
                'markdown_content': md_content,
            },
            'raw_text': raw_text,
            'total_pages': result.get('total_pages', 1),
            'pages': result.get('pages', []),
            'saved_files': {
                'md_origin_path': md_origin_path,
                'md_path': md_path,
                'txt_path': txt_path,
            },
            'token_logprobs': result.get('token_logprobs', []),
            'error': ''
        }

        return normalized
    except requests.exceptions.ReadTimeout:
        default_result['error'] = '服务器处理超时'
        print(f"[OCR-ASSET] {default_result['error']}")
        return default_result
    except Exception as e:
        default_result['error'] = str(e)
        print(f"[OCR-ASSET] 发生错误: {default_result['error']}")
        return default_result


def run_remote_ocr(pdf_path: str, output_dir: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    发送PDF到中转服务器进行OCR，并保存返回的文本
    
    参数：
        pdf_path: PDF文件路径
        output_dir: 输出目录
        
    返回：
        (success, markdown_path, txt_path): 
            - success: 是否成功
            - markdown_path: Markdown文件路径
            - txt_path: 原始文本文件路径
    """
    if not os.path.exists(pdf_path):
        print(f"[OCR] 文件不存在: {pdf_path}")
        return False, None, None

    filename = os.path.basename(pdf_path)
    file_base = os.path.splitext(filename)[0]
    
    print(f"[OCR] 正在上传并处理: {filename} (可能需要较长时间)...")

    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (filename, f)}
            
            # 发送请求，设置长超时
            response = requests.post(RELAY_SERVER_URL, files=files, timeout=OCR_TIMEOUT)
            
            if response.status_code == 200:
                result = response.json()
                
                if not result.get('success'):
                    print(f"[OCR] 处理失败: {result.get('error')}")
                    return False, None, None

                # 确保输出目录存在
                os.makedirs(output_dir, exist_ok=True)

                # 1. 保存去重前后 Markdown
                md_origin_path = os.path.join(output_dir, f"{file_base}_origin_ocr.md")
                md_path = os.path.join(output_dir, f"{file_base}_ocr.md")
                md_origin_content = result.get('markdown', {}).get('markdown_origin_content', '')
                md_content = result.get('markdown', {}).get('markdown_content', '')
                # 图片路径改为绝对路径（与PDF同级目录的 document_image/ 文件夹）
                image_abs_path = os.path.abspath(os.path.join(os.path.dirname(pdf_path), f"{file_base}_image"))
                md_origin_content = md_origin_content.replace('![](images/', f'![]({image_abs_path}/')
                md_content = md_content.replace('![](images/', f'![]({image_abs_path}/')
                with open(md_origin_path, 'w', encoding='utf-8') as f_md:
                    f_md.write(md_origin_content)
                with open(md_path, 'w', encoding='utf-8') as f_md_proc:
                    f_md_proc.write(md_content)
                
                # 2. 保存 Raw Text
                txt_path = os.path.join(output_dir, f"{file_base}_raw.txt")
                with open(txt_path, 'w', encoding='utf-8') as f_txt:
                    f_txt.write(result.get('raw_text', ''))

                print(f"[OCR] 处理成功! 页数: {result.get('total_pages')}")
                print(f"[OCR] 去重前Markdown保存至: {md_origin_path}")
                print(f"[OCR] 去重后Markdown保存至: {md_path}")
                print(f"[OCR] 原始文本保存至: {txt_path}")
                
                return True, {'md_origin_path': md_origin_path, 'md_path': md_path}, txt_path
            else:
                print(f"[OCR] 请求失败: {response.status_code}")
                print(f"[OCR] 响应: {response.text}")
                return False, None, None

    except requests.exceptions.ReadTimeout:
        print("[OCR] 错误: 服务器处理超时 (文件可能过大或模型繁忙)")
        return False, None, None
    except Exception as e:
        print(f"[OCR] 发生错误: {str(e)}")
        return False, None, None


def check_pdf_type(file_path: str) -> str:
    """
    检测PDF是扫描件还是非扫描件（数字原生）
    
    参数：
        file_path: PDF文件路径
        
    返回:
        - 'scanned': 扫描件（几乎无文本，全是图片）
        - 'digital': 数字非扫描件（有大量可提取文本）
        - 'empty': 空文件或无法判断
        - 'error': 文件损坏或无法读取
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"[扫描件检测] 打开PDF失败: {e}")
        return 'error'

    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        return 'empty'

    text_content_length = 0
    image_count = 0
    
    # 为了提高效率，只检查前5页（或者全部，如果少于5页）
    pages_to_check = min(5, total_pages)
    
    for i in range(pages_to_check):
        page = doc.load_page(i)
        
        # 1. 提取文本
        text = page.get_text()
        # 去除空白字符，计算有效文本长度
        text_content_length += len(text.strip())
        
        # 2. 计算图片数量
        image_list = page.get_images(full=True)
        image_count += len(image_list)

    doc.close()

    # 判定逻辑：平均每页字符数
    avg_text_per_page = text_content_length / pages_to_check

    print(f"[扫描件检测] 平均每页字符数: {avg_text_per_page:.1f}, 图片数: {image_count}")

    # 如果几乎没有文本 (例如平均每页少于 50 个字符)
    if avg_text_per_page < 50:
        # 如果还有图片，那基本就是扫描件
        if image_count > 0:
            print(f"[扫描件检测] 判定为扫描件")
            return 'scanned'
        else:
            # 没文本也没图片，可能是包含矢量图的特殊文件，或者空白
            print(f"[扫描件检测] 判定为空白/未知")
            return 'empty'
    
    # 如果有大量文本，则是非扫描件
    print(f"[扫描件检测] 判定为数字原生PDF")
    return 'digital'


def check_pdf_type_by_word(pdf_path: str) -> str:
    """
    【推荐方法】通过转换为Word文档来准确检测PDF类型
    
    检测步骤：
    1. 剔除PDF中的图片层，只保留文字层
    2. 将纯净版PDF转换为Word
    3. 检查Word文档的文本内容量
    4. 删除所有中间文件
    
    参数：
        pdf_path: PDF文件路径
        
    返回：
        'scanned': 扫描件（几乎没有可提取的文本）
        'digital': 数字原生PDF（包含可编辑文本）
        'empty': 空文档
        'error': 检测出错
    """
    import tempfile
    from pdf2docx import Converter
    from docx import Document
    
    # 创建临时文件路径
    temp_dir = tempfile.mkdtemp()
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    cleaned_pdf = os.path.join(temp_dir, f"{base_name}_no_img.pdf")
    temp_docx = os.path.join(temp_dir, f"{base_name}_temp.docx")
    
    try:
        # 步骤1: 剔除PDF图片层（只处理前5页，避免页数过多）
        print(f"[精确PDF检测] 正在剔除图片背景...")
        doc = fitz.open(pdf_path)
        
        if len(doc) == 0:
            doc.close()
            return 'empty'
        
        # 🔥 限制只检查前5页，加快检测速度
        pages_to_check = min(5, len(doc))
        total_pages_in_pdf = len(doc)
        
        for page_idx in range(pages_to_check):
            page = doc[page_idx]
            image_list = page.get_images()
            for img in image_list:
                xref = img[0]
                page.delete_image(xref)
        
        doc.save(cleaned_pdf)
        doc.close()
        
        # 步骤2: 转换为Word（只转换前5页）
        print(f"[精确PDF检测] 正在转换为Word（只处理前{pages_to_check}页）...")
        cv = Converter(cleaned_pdf)
        cv.convert(temp_docx, start=0, end=pages_to_check)
        cv.close()
        
        # 步骤3: 检查Word文档内容
        print(f"[精确PDF检测] 正在分析文本内容...")
        word_doc = Document(temp_docx)
        total_text_length = 0
        
        # 提取所有段落文本
        for para in word_doc.paragraphs:
            text = para.text.strip()
            total_text_length += len(text)
        
        # 提取所有表格文本
        for table in word_doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = cell.text.strip()
                    total_text_length += len(text)
        
        # 🔥 使用实际检查的页数计算平均值
        avg_chars_per_page = total_text_length / pages_to_check
        
        print(f"[精确PDF检测] 总字符数: {total_text_length}, 检查页数: {pages_to_check}/{total_pages_in_pdf}, 平均每页: {avg_chars_per_page:.1f}字符")
        
        # 判断标准
        MIN_TOTAL_CHARS = 100
        MIN_AVG_CHARS_PER_PAGE = 50
        
        if total_text_length < MIN_TOTAL_CHARS:
            print(f"[精确PDF检测] 结论: 扫描件（总字符数 {total_text_length} < {MIN_TOTAL_CHARS}）")
            result = 'scanned'
        elif avg_chars_per_page < MIN_AVG_CHARS_PER_PAGE:
            print(f"[精确PDF检测] 结论: 扫描件（每页平均 {avg_chars_per_page:.1f} < {MIN_AVG_CHARS_PER_PAGE}）")
            result = 'scanned'
        else:
            print(f"[精确PDF检测] 结论: 数字原生PDF")
            result = 'digital'
        
        return result
        
    except Exception as e:
        print(f"[精确PDF检测] 检测失败: {e}")
        import traceback
        traceback.print_exc()
        return 'error'
        
    finally:
        # 步骤44: 清理所有中间文件
        try:
            if os.path.exists(cleaned_pdf):
                os.remove(cleaned_pdf)
                print(f"[精确PDF检测] 已删除: {cleaned_pdf}")
            if os.path.exists(temp_docx):
                os.remove(temp_docx)
                print(f"[精确PDF检测] 已删除: {temp_docx}")
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                print(f"[精确PDF检测] 已清理临时目录")
        except Exception as e:
            print(f"[精确PDF检测] 清理中间文件失败: {e}")


# def md_to_pdf(input_md_file: str, output_pdf_file: str, wkhtmltopdf_path: str = None) -> bool:
#     """
#     将 Markdown 文件转换为 PDF 文件 (支持 LaTeX 公式)
    
#     参数：
#         input_md_file: Markdown文件路径
#         output_pdf_file: 输出PDF文件路径
#         wkhtmltopdf_path: wkhtmltopdf可执行文件路径（可选）
        
#     返回：
#         是否转换成功
#     """
#     # 1. 检查输入文件
#     if not os.path.exists(input_md_file):
#         print(f"[MD2PDF] 错误：找不到文件 {input_md_file}")
#         return False

#     # 2. 读取 Markdown 内容
#     try:
#         with open(input_md_file, 'r', encoding='utf-8') as f:
#             md_content = f.read()
#             # md_content = md_content.replace(PAGE_BREAK, '')  # 移除分页符，PDF分页由wkhtmltopdf控制
#     except Exception as e:
#         print(f"[MD2PDF] 读取文件失败: {e}")
#         return False

#     # 3. 将 Markdown 转换为 HTML
#     extensions = [
#         'extra', 
#         'codehilite', 
#         'toc',
#         'pymdownx.arithmatex',
#         'pymdownx.superfences'
#     ]
    
#     extension_configs = {
#         'pymdownx.arithmatex': {
#             'generic': True,
#             'tex_inline_wrap': ['$','$'],
#             'tex_block_wrap': ['$$','$$']
#         }
#     }

#     try:
#         html_body = markdown.markdown(
#             md_content, 
#             extensions=extensions, 
#             extension_configs=extension_configs
#         )
#     except Exception as e:
#         print(f"[MD2PDF] Markdown转HTML失败: {e}")
#         # 如果pymdownx扩展不可用，使用基础转换
#         try:
#             html_body = markdown.markdown(md_content)
#         except Exception as e2:
#             print(f"[MD2PDF] 基础Markdown转换也失败: {e2}")
#             return False

#     # 4. MathJax 配置和脚本
#     mathjax_script = """
#     <script type="text/x-mathjax-config">
#       MathJax.Hub.Config({
#         tex2jax: {
#           inlineMath: [['$','$'], ['\\\\(','\\\\)']],
#           displayMath: [['$$','$$'], ['\\\\[','\\\\]']],
#           processEscapes: true
#         },
#         "HTML-CSS": { 
#             availableFonts: ["TeX"], 
#             scale: 150,
#             linebreaks: { automatic: true } 
#         },
#         SVG: { 
#             scale: 150 
#         }
#       });
#     </script>
#     <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-AMS_CHTML"></script>
#     """

#     # # 5. CSS 样式
#     # css_style = """
#     # <style>
#     #     body {
#     #         font-family: "Microsoft YaHei", "SimSun", sans-serif;
#     #         font-size: 20px;
#     #         line-height: 1.4;
#     #         color: #333;
#     #         margin: 0 auto;
#     #         padding: 10px;
#     #     }
        
#     #     .MathJax {
#     #         font-size: 150%;
#     #     }
#     #     .MathJax_Display { 
#     #         margin: 0.5em 0; 
#     #         overflow-x: auto; 
#     #         overflow-y: hidden;
#     #     }

#     #     h1, h2, h3 { 
#     #         color: #2c3e50; 
#     #         border-bottom: 1px solid #eaecef; 
#     #         padding-bottom: 0.2em; 
#     #         margin-top: 0.5em;
#     #         margin-bottom: 0.3em;
#     #     }
#     #     h1 { font-size: 26px; }
#     #     h2 { font-size: 24px; }
#     #     h3 { font-size: 22px; }
        
#     #     p { margin: 0.3em 0; }
        
#     #     code { 
#     #         background-color: #f6f8fa; 
#     #         padding: 2px 4px; 
#     #         border-radius: 3px; 
#     #         font-family: monospace;
#     #         font-size: 14px;
#     #     }
#     #     pre { 
#     #         background-color: #f6f8fa; 
#     #         padding: 10px; 
#     #         overflow: auto; 
#     #         border-radius: 6px;
#     #         margin: 0.5em 0;
#     #         font-size: 14px;
#     #     }
#     #     blockquote { 
#     #         border-left: 4px solid #dfe2e5; 
#     #         color: #6a737d; 
#     #         padding-left: 10px; 
#     #         margin: 0.5em 0;
#     #     }
#     #     table { 
#     #         border-collapse: collapse; 
#     #         width: 100%; 
#     #         margin-bottom: 10px;
#     #         font-size: 15px;
#     #     }
#     #     th, td { 
#     #         border: 1px solid #dfe2e5; 
#     #         padding: 4px 8px;
#     #     }
#     #     th { background-color: #f6f8fa; font-weight: bold; }
#     #     img { max-width: 100%; margin: 0.3em 0; }
        
#     #     ul, ol { 
#     #         margin: 0.3em 0; 
#     #         padding-left: 20px;
#     #     }
#     #     li { margin: 0.2em 0; }
#     # </style>
#     # """

#     # 5. CSS 样式 (优化版：显著加大加粗标题)
#     css_style = """
#     <style>
#         body {
#             font-family: "Microsoft YaHei", "SimSun", sans-serif;
#             font-size: 16px; /* 建议将正文从20px调小至16px，以便与标题形成对比，且更符合A4阅读习惯 */
#             line-height: 1.6;
#             color: #333;
#             margin: 0 auto;
#             padding: 20px;
#         }
        
#         .MathJax {
#             font-size: 120%;
#         }
#         .MathJax_Display { 
#             margin: 0.5em 0; 
#             overflow-x: auto; 
#             overflow-y: hidden;
#         }

#         /* 标题通用样式：显式加粗 */
#         h1, h2, h3 { 
#             color: #000000; /* 标题改用纯黑或深色，增强对比 */
#             font-weight: bold !important; /* 强制加粗 */
#             border-bottom: 1px solid #eaecef; 
#             padding-bottom: 0.3em; 
#             margin-top: 1.0em;
#             margin-bottom: 0.5em;
#             font-family: "Microsoft YaHei", "SimHei", sans-serif; /* 标题可优先使用黑体 */
#         }

#         /* 针对 title (一级标题) 的加大处理 */
#         h1 { 
#             font-size: 32px; /* 显著加大 (原26px) */
#             line-height: 1.2;
#         }

#         /* 针对 sub_title (二级标题) 的加大处理 */
#         h2 { 
#             font-size: 26px; /* 显著加大 (原24px) */
#             line-height: 1.25;
#             color: #333333;
#         }

#         /* 三级标题 */
#         h3 { 
#             font-size: 22px; 
#             border-bottom: none; /* 三级标题通常不需要下划线 */
#         }
        
#         p { margin: 0.5em 0; text-align: justify; }
        
#         code { 
#             background-color: #f6f8fa; 
#             padding: 2px 4px; 
#             border-radius: 3px; 
#             font-family: Consolas, "Courier New", monospace;
#             font-size: 90%;
#             color: #e83e8c;
#         }
#         pre { 
#             background-color: #f6f8fa; 
#             padding: 12px; 
#             overflow: auto; 
#             border-radius: 6px;
#             margin: 1em 0;
#             border: 1px solid #e1e4e8;
#         }
#         blockquote { 
#             border-left: 5px solid #dfe2e5; 
#             color: #6a737d; 
#             padding-left: 15px; 
#             margin: 1em 0;
#             background-color: #fafafa;
#         }
#         table { 
#             border-collapse: collapse; 
#             width: 100%; 
#             margin: 1em 0;
#             font-size: 14px;
#         }
#         th, td { 
#             border: 1px solid #dfe2e5; 
#             padding: 8px 12px;
#         }
#         th { 
#             background-color: #f6f8fa; 
#             font-weight: bold; 
#             text-align: left;
#         }
#         img { 
#             max-width: 95%; 
#             margin: 1em auto; 
#             display: block; 
#             border: 1px solid #eee; /* 给图片加个淡边框，看起来更正式 */
#         }
        
#         ul, ol { 
#             margin: 0.5em 0; 
#             padding-left: 25px;
#         }
#         li { margin: 0.3em 0; }
#     </style>
#     """

#     # 组装完整的 HTML
#     html_content = f"""
#     <!DOCTYPE html>
#     <html>
#     <head>
#         <meta charset="UTF-8">
#         <title>Document</title>
#         {css_style}
#         {mathjax_script}
#     </head>
#     <body>
#         {html_body}
#     </body>
#     </html>
#     """

#     # 临时文件
#     temp_html_file = os.path.join(os.path.dirname(input_md_file), "temp_md_conversion.html")

#     try:
#         with open(temp_html_file, 'w', encoding='utf-8') as f:
#             f.write(html_content)

#         # 6. 配置选项
#         options = {
#             'page-size': 'A4',
#             'encoding': "UTF-8",
#             'enable-local-file-access': None,
#             'javascript-delay': 3000,
#             'no-stop-slow-scripts': None
#         }

#         # 检测wkhtmltopdf路径
#         if wkhtmltopdf_path is None:
#             # 尝试常见路径
#             possible_paths = [
#                 r'D:\wkhtmltopdf\bin\wkhtmltopdf.exe',
#                 r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
#                 r'C:\wkhtmltopdf\bin\wkhtmltopdf.exe',
#                 '/usr/local/bin/wkhtmltopdf',
#                 '/usr/bin/wkhtmltopdf'
#             ]
            
#             for path in possible_paths:
#                 if os.path.exists(path):
#                     wkhtmltopdf_path = path
#                     break
        
#         if wkhtmltopdf_path and os.path.exists(wkhtmltopdf_path):
#             config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
#         else:
#             # 尝试使用系统PATH中的wkhtmltopdf
#             config = None
#             print("[MD2PDF] 警告: 未找到wkhtmltopdf路径，尝试使用系统默认配置")
        
#         print("[MD2PDF] 正在转换... (由于需要渲染公式，请耐心等待)")
#         pdfkit.from_file(temp_html_file, output_pdf_file, options=options, configuration=config)
#         print(f"[MD2PDF] 转换成功！PDF已保存至: {output_pdf_file}")
#         return True
        
#     except OSError as e:
#         print(f"[MD2PDF] 转换失败：请检查 wkhtmltopdf 路径是否正确")
#         print(f"[MD2PDF] 错误详情: {e}")
#         return False
#     except Exception as e:
#         print(f"[MD2PDF] 发生未知错误: {e}")
#         return False
#     finally:
#         # 清理临时文件
#         if os.path.exists(temp_html_file):
#             try:
#                 os.remove(temp_html_file)
#             except:
#                 pass


def md_to_pdf(input_md_file: str, output_pdf_file: str, wkhtmltopdf_path: str = None) -> bool:
    """
    将 Markdown 文件转换为 PDF 文件 (大字号、大行距、窄边距版)
    """
    # 1. 检查输入文件
    if not os.path.exists(input_md_file):
        print(f"[MD2PDF] 错误：找不到文件 {input_md_file}")
        return False

    # 2. 读取 Markdown 内容
    try:
        with open(input_md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
    except Exception as e:
        print(f"[MD2PDF] 读取文件失败: {e}")
        return False

    # 3. 将 Markdown 转换为 HTML
    extensions = [
        'extra', 
        'codehilite', 
        'toc',
        'pymdownx.arithmatex',
        'pymdownx.superfences'
    ]
    
    extension_configs = {
        'pymdownx.arithmatex': {
            'generic': True,
            'tex_inline_wrap': ['$','$'],
            'tex_block_wrap': ['$$','$$']
        }
    }

    try:
        html_body = markdown.markdown(
            md_content, 
            extensions=extensions, 
            extension_configs=extension_configs
        )
    except Exception as e:
        print(f"[MD2PDF] Markdown转HTML失败: {e}")
        try:
            html_body = markdown.markdown(md_content)
        except Exception as e2:
            print(f"[MD2PDF] 基础Markdown转换也失败: {e2}")
            return False

    # 4. MathJax 配置
    mathjax_script = """
    <script type="text/x-mathjax-config">
      MathJax.Hub.Config({
        tex2jax: {
          inlineMath: [['$','$'], ['\\\\(','\\\\)']],
          displayMath: [['$$','$$'], ['\\\\[','\\\\]']],
          processEscapes: true
        },
        "HTML-CSS": { 
            availableFonts: ["TeX"], 
            scale: 120, 
            linebreaks: { automatic: true } 
        },
        SVG: { 
            scale: 120 
        }
      });
    </script>
    <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-AMS_CHTML"></script>
    """

    # 5. CSS 样式 (【修改点】：调大行间距)
    css_style = """
    <style>
        body {
            font-family: "Microsoft YaHei", "SimSun", sans-serif;
            font-size: 30px; 
            /* 【修改点 1】增大行高，从 1.5 改为 1.8 (也可改为 2.0 更大) */
            line-height: 2.0;
            color: #000; 
            margin: 0 auto;
            padding: 0; 
        }
        
        .MathJax {
            font-size: 100%; 
        }
        .MathJax_Display { 
            margin: 0.5em 0; 
            overflow-x: auto; 
            overflow-y: hidden;
        }

        /* 标题样式 */
        h1, h2, h3 { 
            color: #000;
            font-weight: bold !important;
            border-bottom: 1px solid #eaecef; 
            padding-bottom: 0.2em; 
            margin-top: 1.0em; /* 标题上方间距微调 */
            margin-bottom: 0.6em;
            /* 标题行高也稍微增加一点，防止多行标题拥挤 */
            line-height: 1.4; 
        }

        h1 { font-size: 76px; } 
        h2 { font-size: 70px; } 
        h3 { font-size: 66px; border-bottom: none; } 
        
        /* 【修改点 2】增大段落间距，从 0.4em 改为 0.8em，让段落之间更分明 */
        p { 
            margin: 0.8em 0; 
            text-align: justify; 
        }
        
        code { 
            background-color: #f6f8fa; 
            padding: 2px 4px; 
            border-radius: 3px; 
            font-family: Consolas, "Courier New", monospace;
            font-size: 90%; 
            color: #c7254e;
        }
        pre { 
            background-color: #f6f8fa; 
            padding: 10px; 
            overflow: auto; 
            border-radius: 6px;
            margin: 1.0em 0; /* 代码块间距增加 */
            border: 1px solid #e1e4e8;
            line-height: 1.4; /* 代码块内部保持紧凑，方便阅读 */
        }
        
        table { 
            border-collapse: collapse; 
            width: 100%; 
            margin: 1.0em 0;
            font-size: 20px; 
        }
        th, td { 
            border: 1px solid #000; 
            padding: 8px 12px; /* 表格内边距微调 */
        }
        th { 
            background-color: #f0f0f0; 
            font-weight: bold; 
            text-align: center;
        }
        
        img { 
            max-width: 100%; 
            margin: 0.8em auto; 
            display: block; 
        }
        
        ul, ol { 
            margin: 0.8em 0; 
            padding-left: 1.5em;
        }
        /* 【修改点 3】增大列表项间距，从 0.2em 改为 0.5em */
        li { 
            margin: 0.5em 0; 
        }
    </style>
    """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Document</title>
        {css_style}
        {mathjax_script}
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """

    temp_html_file = os.path.join(os.path.dirname(input_md_file), "temp_md_conversion.html")

    try:
        with open(temp_html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 6. 配置选项
        options = {
            'page-size': 'A4',
            'encoding': "UTF-8",
            'margin-top': '8mm',
            'margin-bottom': '8mm',
            'margin-left': '8mm',
            'margin-right': '8mm',
            'enable-local-file-access': None,
            'javascript-delay': 3000,
            'no-stop-slow-scripts': None,
        }

        # 检测wkhtmltopdf路径
        if wkhtmltopdf_path is None:
            # 尝试常见路径
            possible_paths = [
                r'D:\wkhtmltopdf\bin\wkhtmltopdf.exe',
                r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
                r'C:\wkhtmltopdf\bin\wkhtmltopdf.exe',
                '/usr/local/bin/wkhtmltopdf',
                '/usr/bin/wkhtmltopdf'
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    wkhtmltopdf_path = path
                    break
        
        if wkhtmltopdf_path and os.path.exists(wkhtmltopdf_path):
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        else:
            # 尝试使用系统PATH中的wkhtmltopdf
            config = None
            print("[MD2PDF] 警告: 未找到wkhtmltopdf路径，尝试使用系统默认配置")

        print("[MD2PDF] 正在转换... (由于需要渲染公式，请耐心等待)")
        pdfkit.from_file(temp_html_file, output_pdf_file, options=options, configuration=config)
        print(f"[MD2PDF] 转换成功！PDF已保存至: {output_pdf_file}")
        return True
        
    except OSError as e:
        print(f"[MD2PDF] 转换失败：请检查 wkhtmltopdf 路径是否正确")
        print(f"[MD2PDF] 错误详情: {e}")
        return False
    except Exception as e:
        print(f"[MD2PDF] 发生未知错误: {e}")
        return False
    finally:
        # 清理临时文件
        if os.path.exists(temp_html_file):
            try:
                os.remove(temp_html_file)
            except:
                pass


def extract_images_from_ocr_txt(txt_path: str) -> dict:
    """
    从OCR识别的txt文件中提取图片位置信息
    
    参数：
        txt_path: OCR生成的txt文件路径
        
    返回：
        按页码组织的图片信息字典: {page_num: [{'bbox': [x1, y1, x2, y2], 'type': 'image'}, ...]}
    """
    if not os.path.exists(txt_path):
        print(f"[图片提取] txt文件不存在: {txt_path}")
        return {}
    
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[图片提取] 读取txt文件失败: {e}")
        return {}
    
    # 按页面分割内容
    page_pattern = r'={50,}\n第 (\d+) 页\n={50,}'
    page_splits = re.split(page_pattern, content)
    
    # 构建页面内容映射：{页码: 页面内容}
    page_contents = {}
    for i in range(1, len(page_splits), 2):
        if i < len(page_splits):
            page_num = int(page_splits[i])
            page_content = page_splits[i+1] if i+1 < len(page_splits) else ""
            page_contents[page_num] = page_content
    
    # 提取每页的图片信息
    images_by_page = {}
    pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
    
    for page_num, page_content in page_contents.items():
        matches = re.findall(pattern, page_content, re.DOTALL)
        page_images = []
        
        for match in matches:
            label_type = match[0]
            coordinates_str = match[1]
            
            # 如果是图片类型，提取坐标
            if label_type == 'image':
                try:
                    # 解析坐标列表
                    cor_list = eval(coordinates_str)
                    
                    # 遍历所有坐标框（可能有多个）
                    for points in cor_list:
                        if len(points) >= 4:
                            # 坐标是归一化的 0-999
                            x1, y1, x2, y2 = points[:4]
                            
                            page_images.append({
                                'bbox': [x1, y1, x2, y2],
                                'type': 'image',
                                'normalized': True  # 标记坐标已归一化
                            })
                except Exception as e:
                    print(f"[图片提取] 第{page_num}页解析坐标失败: {e}")
                    continue
        
        if page_images:
            images_by_page[page_num] = page_images
    
    total_images = sum(len(imgs) for imgs in images_by_page.values())
    print(f"[图片提取] 从OCR结果中提取到 {total_images} 个图片，分布在 {len(images_by_page)} 页")
    return images_by_page


def extract_image_context_from_ocr_txt(txt_path: str, page_num: int, image_seq_in_page: int) -> dict:
    """
    从OCR识别的txt文件中提取指定图片位置的前后各100字文本和页数信息

    参数：
        txt_path: OCR生成的txt文件路径
        page_num: 页码（从1开始）
        image_seq_in_page: 该页中图片的序号（从0开始）

    返回：
        {
            'page_num': 页码,
            'context_before': 图片位置前100字文本,
            'context_after': 图片位置后100字文本,
            'full_page_content': 完整页面内容（用于调试）
        }
    """
    if not os.path.exists(txt_path):
        return {'page_num': page_num, 'context_before': '', 'context_after': '', 'full_page_content': ''}

    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[图片上下文提取] 读取txt文件失败: {e}")
        return {'page_num': page_num, 'context_before': '', 'context_after': '', 'full_page_content': ''}

    # 按页面分割内容
    page_pattern = r'={50,}\n第 (\d+) 页\n={50,}'
    page_splits = re.split(page_pattern, content)

    # 找到指定页码的内容
    page_content = ""
    for i in range(1, len(page_splits), 2):
        if i < len(page_splits):
            current_page_num = int(page_splits[i])
            if current_page_num == page_num:
                page_content = page_splits[i + 1] if i + 1 < len(page_splits) else ""
                break

    if not page_content:
        return {'page_num': page_num, 'context_before': '', 'context_after': '', 'full_page_content': ''}

    # 提取该页的所有图片位置
    pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
    matches = list(re.finditer(pattern, page_content, re.DOTALL))

    # 找到指定序号的图片
    image_matches = []
    for match in matches:
        label_type = match.group(1).strip()
        if label_type == 'image':
            image_matches.append(match)

    if image_seq_in_page >= len(image_matches):
        # 如果序号超出范围，返回空上下文
        return {'page_num': page_num, 'context_before': '', 'context_after': '', 'full_page_content': page_content}

    # 获取指定图片的位置
    target_match = image_matches[image_seq_in_page]
    image_start_pos = target_match.start()
    image_end_pos = target_match.end()

    # 提取图片前的文本（去除标记）
    before_text = page_content[:image_start_pos]
    # 移除所有标记，只保留纯文本
    before_text_clean = re.sub(r'<\|ref\|>.*?<\|/ref\|><\|det\|>.*?<\|/det\|>', '', before_text, flags=re.DOTALL)
    before_text_clean = re.sub(r'={50,}', '', before_text_clean)
    before_text_clean = before_text_clean.strip()

    # 提取图片后的文本（去除标记）
    after_text = page_content[image_end_pos:]
    # 移除所有标记，只保留纯文本
    after_text_clean = re.sub(r'<\|ref\|>.*?<\|/ref\|><\|det\|>.*?<\|/det\|>', '', after_text, flags=re.DOTALL)
    after_text_clean = re.sub(r'={50,}', '', after_text_clean)
    after_text_clean = after_text_clean.strip()

    # 提取前后各100字（中文字符或英文单词）
    def extract_text_chars(text, max_chars=100):
        """提取指定数量的字符（中文按字符，英文按单词）"""
        result = []
        char_count = 0
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                result.append(char)
                char_count += 1
            elif char.isalnum() or char.isspace():  # 英文字母、数字、空格
                result.append(char)
                # 如果是单词边界，增加计数
                if char.isalnum():
                    # 检查是否是单词的开始
                    if len(result) == 1 or not result[-2].isalnum():
                        char_count += 1
            else:
                result.append(char)
            if char_count >= max_chars:
                break
        return ''.join(result)

    context_before = extract_text_chars(before_text_clean, 100)
    context_after = extract_text_chars(after_text_clean, 100)

    return {
        'page_num': page_num,
        'context_before': context_before,
        'context_after': context_after,
        'full_page_content': page_content
    }


def extract_and_save_images_from_ocr(pdf_path: str, ocr_txt_path: str, output_dir: str = None) -> Tuple[bool, int, str]:
    """
    从OCR结果中提取图片坐标，从PDF裁剪并保存图片
    
    参数：
        pdf_path: PDF文件路径
        ocr_txt_path: OCR生成的txt文件路径
        output_dir: 图片输出目录（可选，默认为 pdf路径_image/）
        
    返回：
        (success, image_count, output_dir): 是否成功, 图片数量, 输出目录
    """
    if not os.path.exists(pdf_path):
        print(f"[图片保存] PDF文件不存在: {pdf_path}")
        return False, 0, ""
    
    if not os.path.exists(ocr_txt_path):
        print(f"[图片保存] OCR文件不存在: {ocr_txt_path}")
        return False, 0, ""
    
    # 确定输出目录
    if output_dir is None:
        output_dir = pdf_path[:-4] + "_image/"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"[图片保存] 创建输出目录: {output_dir}")
    
    # 删掉输出目录下已有的图片文件
    existing_images = [f for f in os.listdir(output_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    for img_file in existing_images:
        try:
            os.remove(os.path.join(output_dir, img_file))
        except Exception as e:
            print(f"[图片保存] 删除旧图片失败: {e}")

    print(f"[图片保存] 开始从OCR结果提取并保存图片...")
    
    try:
        # 打开PDF
        doc = fitz.open(pdf_path)
        
        # 从OCR结果提取图片位置信息
        images_by_page = extract_images_from_ocr_txt(ocr_txt_path)
        
        if not images_by_page:
            print(f"[图片保存] 未找到任何图片信息")
            doc.close()
            return True, 0, output_dir
        
        img_count = 0
        
        # 遍历每一页
        for page_num in range(len(doc)):
            page = doc[page_num]
            ocr_page_num = page_num + 1  # OCR页码从1开始
            
            # 如果该页有图片
            if ocr_page_num in images_by_page:
                page_images = images_by_page[ocr_page_num]
                page_rect = page.rect
                
                for img_info in page_images:
                    bbox = img_info['bbox']
                    
                    # 坐标归一化转换（0-999 到实际像素）
                    x1 = int(bbox[0] / 999 * page_rect.width)
                    y1 = int(bbox[1] / 999 * page_rect.height)
                    x2 = int(bbox[2] / 999 * page_rect.width)
                    y2 = int(bbox[3] / 999 * page_rect.height)
                    
                    # 过滤太小的图片
                    if (x2 - x1) < 15 or (y2 - y1) < 15:
                        continue
                    
                    # 裁剪并保存图片
                    img_rect = fitz.Rect(x1, y1, x2, y2)
                    pix = page.get_pixmap(clip=img_rect, dpi=200)
                    
                    img_count += 1
                    image_filename = os.path.join(output_dir, f"{img_count}.png")
                    pix.save(image_filename)
                    print(f"[图片保存] 第{ocr_page_num}页提取图片 {img_count}: {image_filename}")
        
        doc.close()
        print(f"[图片保存] 完成！共保存 {img_count} 张图片到: {output_dir}")
        return True, img_count, output_dir
        
    except Exception as e:
        print(f"[图片保存] 提取图片失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, output_dir


def muExtractImages_with_ocr(file_name, ocr_txt_path, usr_name="", realName="", task_id="", real_time_update=False):
    """
    【改造版】使用已保存的图片文件生成文档对象
    
    新流程：
    1. 图片应该在OCR后已经提取并保存（通过 extract_and_save_images_from_ocr）
    2. 此函数只负责读取已保存的图片，生成Document对象和base64编码
    3. 不再从PDF裁剪图片
    
    参数：
        file_name: PDF文件路径
        ocr_txt_path: OCR生成的txt文件路径（用于获取图片页码信息）
        usr_name: 用户名
        realName: 真实姓名
        task_id: 任务ID
        real_time_update: 是否实时更新
        
    返回：
        (docs_out, base_64_out): 文档列表和base64图片列表
    """
    from langchain.docstore.document import Document
    import llm_langchain.global_var as global_var
    import time
    import glob
    
    # 导入工具函数
    from llm_langchain.util import encode_image, summarize_image, save_hlscore_to_db_async
    
    pdf = file_name
    out_file_dir = pdf[:-4] + "_image/"
    
    # 检查图片目录是否存在
    if not os.path.exists(out_file_dir):
        print(f"[OCR图片处理] 图片目录不存在: {out_file_dir}")
        print(f"[OCR图片处理] 图片应该在OCR阶段已经提取，请先调用 extract_and_save_images_from_ocr")
        return [], []
    
    # 获取目录下所有图片文件（按序号排序）
    image_files = sorted(glob.glob(os.path.join(out_file_dir, "*.png")), 
                        key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    
    if not image_files:
        print(f"[OCR图片处理] 未找到任何图片文件: {out_file_dir}")
        return [], []
    
    print(f"[OCR图片处理] 找到 {len(image_files)} 张已保存的图片")
    
    # 从OCR结果提取图片页码信息（用于标注页码）
    images_by_page = extract_images_from_ocr_txt(ocr_txt_path) if ocr_txt_path and os.path.exists(ocr_txt_path) else {}
    
    # 构建页码映射（图片序号 -> 页码）
    img_to_page = {}
    img_idx = 0
    for page_num in sorted(images_by_page.keys()):
        for _ in images_by_page[page_num]:
            img_idx += 1
            img_to_page[img_idx] = page_num - 1  # 转换为0-based索引
    
    docs_out = []
    base_64_out = []
    begin_time = time.time()

    # 🔥 准备写入PreImageOrigin_pdf.md的路径
    pre_image_summary_dir = None
    pre_image_origin_path = None
    if usr_name:
        # 构建路径：user_raw_file/用户名_本子名/pre_image_summary/文件名_PreImageOrigin_pdf.md
        base_dir = f"./received_dir/user_raw_file/{usr_name}/pre_image_summary"
        os.makedirs(base_dir, exist_ok=True)
        pre_image_summary_dir = base_dir

        file_base_name = os.path.splitext(os.path.basename(file_name))[0]
        pre_image_origin_path = os.path.join(base_dir, f"{file_base_name}_PreImageOrigin_pdf.md")

        # 如果文件已存在，清空（重新生成）
        if os.path.exists(pre_image_origin_path):
            with open(pre_image_origin_path, 'w', encoding='utf-8') as f:
                f.write("")  # 清空文件

    # 构建图片序号到页码和页内序号的映射
    img_seq_to_page_info = {}
    img_idx = 0
    for page_num in sorted(images_by_page.keys()):
        page_image_count = len(images_by_page[page_num])
        for seq_in_page in range(page_image_count):
            img_idx += 1
            img_seq_to_page_info[img_idx] = {
                'page_num': page_num,
                'seq_in_page': seq_in_page
            }
    
    # 处理每张已保存的图片
    for idx, image_filename in enumerate(image_files, start=1):
        try:
            # 获取图片对应的页码
            page_num = img_to_page.get(idx, 0)  # 默认第0页（0-based）
            page_display = page_num + 1  # 转换为1-based显示页码
            
            print(f"[OCR图片处理] 处理图片 {idx}/{len(image_files)}: {image_filename}")
            
            # 生成图片描述和base64编码
            base64_image = encode_image(image_filename)
            base_64_out.append(base64_image)
            
            content = summarize_image(image_filename, user_name=usr_name)
            content = out_file_dir + "文件中的一张图片，内容为" + content

            # 🔥 提取图片位置的前后各100字文本和页数信息
            context_info = {'page_num': page_display, 'context_before': '', 'context_after': ''}
            if ocr_txt_path and os.path.exists(ocr_txt_path):
                page_info = img_seq_to_page_info.get(idx, {})
                if page_info:
                    context_info = extract_image_context_from_ocr_txt(
                        ocr_txt_path,
                        page_info['page_num'],
                        page_info['seq_in_page']
                    )

            # 🔥 写入PreImageOrigin_pdf.md（每分析完一张图片就写入一次）
            if pre_image_origin_path:
                try:
                    with open(pre_image_origin_path, 'a', encoding='utf-8') as f:
                        f.write(f"## 图片 {idx}\n\n")
                        f.write(f"**页码**：第 {context_info['page_num']} 页\n\n")
                        if context_info.get('context_before'):
                            f.write(f"**前文（100字）**：{context_info['context_before']}\n\n")
                        if context_info.get('context_after'):
                            f.write(f"**后文（100字）**：{context_info['context_after']}\n\n")
                        f.write(f"**图片分析结果**：\n{content}\n\n")
                        f.write("---\n\n")
                    print(f"[图片分析结果写入] 第 {idx} 张图片的分析结果已写入: {pre_image_origin_path}")
                except Exception as e:
                    print(f"[图片分析结果写入] 写入第 {idx} 张图片分析结果失败: {e}")
            
            # 异步保存HLScore到数据库
            if usr_name != "" and realName != "":
                save_hlscore_to_db_async(usr_name, realName, file_name, idx, content, base64_image)
            
            # 创建Document对象
            doc_item = Document(
                page_content=content,
                metadata={
                    "source": pdf,
                    "file_path": image_filename,
                    "page": page_num,
                    "total_pages": len(images_by_page) if images_by_page else 1,
                    "type": "image",
                    "seq": idx,
                }
            )
            docs_out.append(doc_item)
            
            # 实时更新到global_var
            if real_time_update and usr_name != "":
                try:
                    existing_images = global_var.get_user_image(usr_name, os.path.basename(file_name)) or []
                    existing_docs = global_var.get_user_split(usr_name, os.path.basename(file_name)) or []
                    
                    existing_images.append(base64_image)
                    existing_docs.append(doc_item)
                    
                    global_var.set_user_image(usr_name, os.path.basename(file_name), existing_images)
                    global_var.set_user_split(usr_name, os.path.basename(file_name), existing_docs)
                    
                    print(f"[实时更新] 第 {idx} 张图片已更新到global_var")
                except Exception as e:
                    print(f"[实时更新] 更新第 {idx} 张图片时出错: {e}")
            
            # 更新进度
            if task_id != "":
                global_var.set_task_current_page(task_id, idx)
                
        except Exception as e:
            print(f"[OCR图片处理] 处理图片 {image_filename} 失败: {e}")
            continue
    
    print(f"[OCR图片处理] 完成！共处理 {len(docs_out)} 张图片，总用时：{time.time()-begin_time:.2f}秒")

    # 🔥 所有图片分析完成后，对PreImageOrigin_pdf.md进行分段摘要
    if pre_image_origin_path and os.path.exists(pre_image_origin_path) and len(docs_out) > 0:
        try:
            from llm_langchain.parse_input import process_pre_image_summary
            # 异步执行，不阻塞主流程
            import threading
            def _generate_summary():
                try:
                    process_pre_image_summary(usr_name, os.path.basename(file_name), pre_image_origin_path)
                except Exception as e:
                    print(f"[图片分析摘要] 生成PreImageSummary失败: {e}")
                    import traceback
                    traceback.print_exc()

            threading.Thread(target=_generate_summary, daemon=True).start()
        except Exception as e:
            print(f"[图片分析摘要] 启动摘要生成线程失败: {e}")
            import traceback
            traceback.print_exc()

    return docs_out, base_64_out


def extract_layout_elements_from_txt(txt_path: str) -> Dict[int, List[Dict]]:
    """
    从OCR识别的txt文件中提取所有版面元素（文本、图片、表格等）的位置信息
    
    参数：
        txt_path: OCR生成的txt文件路径
        
    返回：
        按页码组织的元素信息字典: {page_num: [{'bbox': [x1, y1, x2, y2], 'type': 'text/image/table', 'content': '...'}, ...]}
    """
    if not os.path.exists(txt_path):
        print(f"[布局提取] txt文件不存在: {txt_path}")
        return {}
    
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[布局提取] 读取txt文件失败: {e}")
        return {}
    
    # 按页面分割内容
    page_pattern = r'={50,}\n第 (\d+) 页\n={50,}'
    page_splits = re.split(page_pattern, content)
    
    # 构建页面内容映射：{页码: 页面内容}
    page_contents = {}
    for i in range(1, len(page_splits), 2):
        if i < len(page_splits):
            page_num = int(page_splits[i])
            page_content = page_splits[i+1] if i+1 < len(page_splits) else ""
            page_contents[page_num] = page_content
    
    # 提取每页的所有元素信息
    elements_by_page = {}
    pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
    
    for page_num, page_content in page_contents.items():
        matches = re.findall(pattern, page_content, re.DOTALL)
        page_elements = []
        
        for match in matches:
            label_type = match[0].strip()
            coordinates_str = match[1].strip()
            
            try:
                # 解析坐标列表
                cor_list = eval(coordinates_str)
                
                # 遍历所有坐标框
                for points in cor_list:
                    if len(points) >= 4:
                        # 坐标是归一化的 0-999
                        x1, y1, x2, y2 = points[:4]
                        
                        page_elements.append({
                            'bbox': [x1, y1, x2, y2],
                            'type': label_type,
                            'normalized': True  # 标记为归一化坐标
                        })
            except Exception as e:
                print(f"[布局提取] 解析坐标失败 (页 {page_num}, 类型 {label_type}): {e}")
                continue
        
        if page_elements:
            elements_by_page[page_num] = page_elements
    
    total_elements = sum(len(elems) for elems in elements_by_page.values())
    print(f"[布局提取] 从OCR结果中提取到 {total_elements} 个元素，分布在 {len(elements_by_page)} 页")
    return elements_by_page


def generate_layout_pdf(original_pdf_path: str, ocr_txt_path: str = None, output_pdf_path: str = None) -> Tuple[bool, Optional[str]]:
    """
    生成PDF的版面布局可视化PDF（在原PDF上绘制检测框）
    
    使用与 DeepSeek OCR 相同的绘制方式：
    - 随机颜色
    - 半透明填充
    - 标签带白色背景
    - 标题使用粗线
    
    参数：
        original_pdf_path: 原始PDF文件路径
        ocr_txt_path: OCR生成的txt文件路径（可选，如果不提供则尝试自动查找）
        output_pdf_path: 输出的布局PDF路径（可选，默认为 原文件名_layouts.pdf）
        
    返回：
        (success, layout_pdf_path): 是否成功, 布局PDF路径
    """
    import io
    import img2pdf
    import numpy as np
    
    if not os.path.exists(original_pdf_path):
        print(f"[布局PDF] 原始PDF不存在: {original_pdf_path}")
        return False, None
    
    # 自动查找OCR txt文件（应该在OCR目录下）
    if ocr_txt_path is None or not os.path.exists(ocr_txt_path):
        # 根据文件存储结构，txt应该在 document_ocr/document_raw.txt
        base_name = os.path.splitext(os.path.basename(original_pdf_path))[0]
        base_dir = os.path.dirname(original_pdf_path)
        ocr_dir = os.path.join(base_dir, f"{base_name}_ocr")
        
        # 尝试常见的命名模式（优先在OCR目录下查找）
        possible_paths = [
            os.path.join(ocr_dir, f"{base_name}_raw.txt"),      # 标准路径
            os.path.join(ocr_dir, f"{base_name}_ocr_raw.txt"),
            os.path.join(base_dir, f"{base_name}_raw.txt"),     # 兼容旧版本（同目录）
            os.path.join(base_dir, f"{base_name}_ocr_raw.txt"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                ocr_txt_path = path
                print(f"[布局PDF] 自动找到OCR文件: {ocr_txt_path}")
                break
        
        if ocr_txt_path is None or not os.path.exists(ocr_txt_path):
            print(f"[布局PDF] 未找到OCR txt文件，无法生成布局PDF")
            print(f"[布局PDF] 已尝试查找: {possible_paths}")
            return False, None
    
    # 确定输出路径（默认放在OCR目录下，命名为 _layouts.pdf）
    if output_pdf_path is None:
        base_name = os.path.splitext(os.path.basename(original_pdf_path))[0]
        base_dir = os.path.dirname(original_pdf_path)
        ocr_dir = os.path.join(base_dir, f"{base_name}_ocr")
        
        # 确保OCR目录存在
        if not os.path.exists(ocr_dir):
            try:
                os.makedirs(ocr_dir)
                print(f"[布局PDF] 创建OCR目录: {ocr_dir}")
            except Exception as e:
                print(f"[布局PDF] 创建OCR目录失败: {e}，使用原目录")
                ocr_dir = base_dir
        
        output_pdf_path = os.path.join(ocr_dir, f"{base_name}_layouts.pdf")
    
    print(f"[布局PDF] 开始生成版面布局PDF...")
    
    try:
        # 打开原始PDF
        doc = fitz.open(original_pdf_path)
        
        # 提取布局元素
        elements_by_page = extract_layout_elements_from_txt(ocr_txt_path)
        
        if not elements_by_page:
            print(f"[布局PDF] 未提取到任何布局元素")
            doc.close()
            return False, None
        
        # 🔥 IO优化：检测原始PDF文件大小，动态调整渲染参数以避免生成过大文件
        original_pdf_size = os.path.getsize(original_pdf_path) / (1024 * 1024)  # MB
        total_pages = len(doc)
        avg_page_size = original_pdf_size / total_pages if total_pages > 0 else 0

        # 如果平均每页小于0.1MB（高压缩PDF），使用较低的渲染质量
        # 如果原始PDF很小但页数多，可能是高压缩，需要降低质量
        is_high_compression = avg_page_size < 0.1 or (original_pdf_size < 10 and total_pages > 100)

        if is_high_compression:
            print(f"[布局PDF] 检测到高压缩PDF（原始{original_pdf_size:.2f}MB，{total_pages}页），使用优化参数避免生成过大文件")
            zoom = 1.0  # 降低放大倍数（从2.0降到1.0）
            jpeg_quality = 75  # 降低JPEG质量（从95降到75）
        else:
            zoom = 2.0  # 正常质量
            jpeg_quality = 95

        # 将PDF页面转换为PIL图片
        draw_images = []

        # 遍历每一页
        for page_num in range(len(doc)):
            page = doc[page_num]
            ocr_page_num = page_num + 1  # OCR页码从1开始

            # 将PDF页面渲染为图片（根据压缩情况调整DPI）
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # 转换为PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # 如果该页有布局元素，在图片上绘制
            if ocr_page_num in elements_by_page:
                page_elements = elements_by_page[ocr_page_num]
                img = _draw_layout_on_image(img, page_elements)

            draw_images.append(img)

            # 🔥 IO优化：仅在检测到高压缩PDF时，每处理10页后释放内存
            if is_high_compression and (page_num + 1) % 10 == 0:
                import gc
                gc.collect()  # 强制垃圾回收

        doc.close()

        # 将所有绘制后的图片转换为PDF
        if not draw_images:
            print(f"[布局PDF] 没有生成任何图片")
            return False, None

        # 保持原有日志格式（正常文件）或添加提示（高压缩文件）
        if is_high_compression:
            print(f"[布局PDF] 正在合成PDF（使用质量={jpeg_quality}）...")
        else:
            print(f"[布局PDF] 正在合成PDF...")
        _pil_images_to_pdf(draw_images, output_pdf_path, jpeg_quality=jpeg_quality, is_high_compression=is_high_compression)

        print(f"[布局PDF] 生成成功: {output_pdf_path}")
        return True, output_pdf_path

    except Exception as e:
        print(f"[布局PDF] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def _draw_layout_on_image(image: Image.Image, elements: List[Dict]) -> Image.Image:
    """
    在PIL图片上绘制布局元素（参考 DeepSeek OCR 的绘制方式）

    参数：
        image: PIL图片对象
        elements: 布局元素列表

    返回：
        绘制后的PIL图片
    """
    import numpy as np

    image_width, image_height = image.size
    img_draw = image.copy()
    draw = ImageDraw.Draw(img_draw)

    # 创建半透明填充层
    overlay = Image.new('RGBA', img_draw.size, (0, 0, 0, 0))
    draw2 = ImageDraw.Draw(overlay)

    # 尝试加载字体，如果失败使用默认字体
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()

    # 遍历所有元素
    for element in elements:
        bbox = element['bbox']
        elem_type = element['type']

        # 归一化坐标转换（0-999 到实际像素）
        if element.get('normalized', False):
            x1 = int(bbox[0] / 999 * image_width)
            y1 = int(bbox[1] / 999 * image_height)
            x2 = int(bbox[2] / 999 * image_width)
            y2 = int(bbox[3] / 999 * image_height)
        else:
            x1, y1, x2, y2 = [int(c) for c in bbox]

        # 🔥 坐标校验和修正
        # 确保 x1 <= x2, y1 <= y2
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        # 边界检查，确保坐标在图片范围内
        x1 = max(0, min(x1, image_width - 1))
        y1 = max(0, min(y1, image_height - 1))
        x2 = max(0, min(x2, image_width))
        y2 = max(0, min(y2, image_height))

        # 跳过无效的矩形（宽度或高度为0）
        if x2 <= x1 or y2 <= y1:
            continue

        # 生成随机颜色（与 DeepSeek OCR 相同）
        color = (np.random.randint(0, 200), np.random.randint(0, 200), np.random.randint(0, 255))
        color_a = color + (20,)  # 半透明填充颜色

        # 根据类型选择线宽（标题用粗线）
        line_width = 4 if elem_type == 'title' else 2

        # 绘制边界框和半透明填充
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)
        draw2.rectangle([x1, y1, x2, y2], fill=color_a, outline=(0, 0, 0, 0), width=1)

        # 在左上角添加类型标签（带白色背景）
        text_x = x1
        text_y = max(0, y1 - 15)

        # 计算文字边界框
        text_bbox = draw.textbbox((0, 0), elem_type, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # 绘制白色背景
        draw.rectangle(
            [text_x, text_y, text_x + text_width + 4, text_y + text_height + 2],
            fill=(255, 255, 255, 200)
        )

        # 绘制文字
        draw.text((text_x + 2, text_y), elem_type, font=font, fill=color)

    # 合并半透明层
    img_draw.paste(overlay, (0, 0), overlay)

    return img_draw


def _pil_images_to_pdf(pil_images: List[Image.Image], output_path: str, jpeg_quality: int = 95, is_high_compression: bool = False) -> None:
    """
    将PIL图片列表转换为PDF（参考 DeepSeek OCR 的方法）

    参数:
        pil_images: PIL图片列表
        output_path: 输出PDF路径
        jpeg_quality: JPEG质量（1-100，默认95）
        is_high_compression: 是否为高压缩PDF（影响写入策略）
    """
    import io
    import img2pdf
    import time

    if not pil_images:
        return

    image_bytes_list = []

    # 🔥 IO优化：对于高压缩PDF，分批处理图片，避免一次性将所有图片加载到内存
    if is_high_compression and len(pil_images) > 50:
        BATCH_SIZE = 50  # 每批处理50张图片
        print(f"[布局PDF] 高压缩PDF，分批处理图片（每批{BATCH_SIZE}张）...")

        for batch_idx in range(0, len(pil_images), BATCH_SIZE):
            batch_images = pil_images[batch_idx:batch_idx + BATCH_SIZE]
            batch_bytes = []

            for img in batch_images:
                # 转换为RGB模式
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # 转换为JPEG字节（使用动态质量）
                img_buffer = io.BytesIO()
                img.save(img_buffer, format='JPEG', quality=jpeg_quality)
                img_bytes = img_buffer.getvalue()
                batch_bytes.append(img_bytes)

            image_bytes_list.extend(batch_bytes)

            # 每处理一批后释放内存
            if (batch_idx // BATCH_SIZE + 1) % 5 == 0:
                import gc
                gc.collect()
                print(f"[布局PDF] 已处理 {batch_idx + len(batch_images)}/{len(pil_images)} 页...")
    else:
        # 正常处理（小文件或非高压缩PDF）
        for img in pil_images:
            # 转换为RGB模式
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 转换为JPEG字节
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=jpeg_quality)
            img_bytes = img_buffer.getvalue()
            image_bytes_list.append(img_bytes)

    # 使用img2pdf合成PDF（正常文件保持原样，不打印额外信息）
    if is_high_compression:
        print(f"[布局PDF] 正在将所有图片合成为PDF（共{len(image_bytes_list)}页）...")
    pdf_bytes = img2pdf.convert(image_bytes_list)

    # 🔥 IO优化：检查生成的PDF大小，如果异常大给出警告
    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    print(f"[布局PDF] 生成的PDF大小: {pdf_size_mb:.2f} MB")

    if pdf_size_mb > 100:  # 如果超过100MB，给出警告
        print(f"[布局PDF] ⚠️  警告：生成的PDF异常大({pdf_size_mb:.2f}MB)，可能影响性能")

    # 🔥 IO优化：分批写入PDF文件，避免一次性写入大文件导致IO瓶颈
    if pdf_size_mb > 50:  # 大于50MB使用分批写入
        print(f"[布局PDF] 使用分批写入以避免IO瓶颈...")
        CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks
        with open(output_path, 'wb') as f:
            for i in range(0, len(pdf_bytes), CHUNK_SIZE):
                chunk = pdf_bytes[i:i+CHUNK_SIZE]
                f.write(chunk)
                f.flush()
                time.sleep(0.1)  # 添加小延迟，避免IO过载
    else:
        # 小文件直接写入
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

# if __name__ == "__main__":
#     # 版面布局PDF测试
#     test_pdf = "/home/ubuntu/Backend/received_dir/user_raw_file/marklee_WangWeiGongPapers/王唯工【以肾为基：用现代科学看中医肾脉，解析传统气功养生源流】繁体竖版黑白扫描.pdf"
#     success, layout_pdf = generate_layout_pdf(test_pdf)
#     if success:
#         print(f"布局PDF生成成功: {layout_pdf}")
