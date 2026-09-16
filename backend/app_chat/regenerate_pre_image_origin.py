#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单独脚本：从向量库中获取指定PDF的所有图片分析结果，并写入PreImageOrigin_pdf.md

使用方法：
python regenerate_pre_image_origin.py <username> <docs_name>

例如：
python regenerate_pre_image_origin.py marklee_ThreeBrainForEduHelath test.pdf
"""

import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')
django.setup()

from llm_langchain import global_var, util
from llm_langchain.pdf_ocr_utils import extract_image_context_from_ocr_txt, extract_images_from_ocr_txt


def regenerate_pre_image_origin(usr_name, docs_name):
    """
    从向量库中获取指定PDF的所有图片分析结果，并写入PreImageOrigin_pdf.md
    
    参数：
        usr_name: 用户名（格式：用户名_本子名）
        docs_name: 文档名（例如：test.pdf）
    """
    try:
        print(f"[重新生成图片分析结果] 开始处理: {usr_name}/{docs_name}")
        
        # 获取文件路径
        file_path = util.construct_file_path(usr_name, docs_name)
        if not os.path.exists(file_path):
            print(f"[重新生成图片分析结果] 文件不存在: {file_path}")
            return False, f"文件不存在: {file_path}"
        
        # 只处理PDF文件
        if not docs_name.lower().endswith('.pdf'):
            print(f"[重新生成图片分析结果] 只支持PDF文件: {docs_name}")
            return False, "只支持PDF文件"
        
        # 获取向量库中的图片分析结果
        image_docs = global_var.get_user_split(usr_name, docs_name)
        if not image_docs:
            print(f"[重新生成图片分析结果] 向量库中未找到图片分析结果: {docs_name}")
            return False, "向量库中未找到图片分析结果"
        
        # 筛选出图片类型的文档
        image_docs_filtered = []
        for doc in image_docs:
            if doc.metadata and doc.metadata.get('type') == 'image':
                image_docs_filtered.append(doc)
        
        if not image_docs_filtered:
            print(f"[重新生成图片分析结果] 未找到图片类型的文档: {docs_name}")
            return False, "未找到图片类型的文档"
        
        # 按序号排序
        image_docs_filtered.sort(key=lambda x: x.metadata.get('seq', 0))
        
        print(f"[重新生成图片分析结果] 找到 {len(image_docs_filtered)} 张图片的分析结果")
        
        # 准备写入PreImageOrigin_pdf.md的路径
        base_dir = f"./received_dir/user_raw_file/{usr_name}/pre_image_summary"
        os.makedirs(base_dir, exist_ok=True)
        
        file_base_name = os.path.splitext(docs_name)[0]
        pre_image_origin_path = os.path.join(base_dir, f"{file_base_name}_PreImageOrigin_pdf.md")
        
        # 检查是否是扫描件，获取OCR文件路径
        file_base = os.path.splitext(docs_name)[0]
        ocr_dir = os.path.join(os.path.dirname(file_path), f"{file_base}_ocr")
        txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")
        
        # 判断是否是扫描件
        is_scanned = os.path.exists(txt_path)
        
        # 如果OCR文件存在（扫描件），提取图片位置信息
        images_by_page = {}
        img_seq_to_page_info = {}
        if is_scanned:
            images_by_page = extract_images_from_ocr_txt(txt_path)
            # 构建图片序号到页码和页内序号的映射
            img_idx = 0
            for page_num in sorted(images_by_page.keys()):
                page_image_count = len(images_by_page[page_num])
                for seq_in_page in range(page_image_count):
                    img_idx += 1
                    img_seq_to_page_info[img_idx] = {
                        'page_num': page_num,
                        'seq_in_page': seq_in_page
                    }
        
        # 对于非扫描件PDF，需要打开PDF文件提取文本
        pdf_doc = None
        if not is_scanned:
            try:
                import fitz
                pdf_doc = fitz.open(file_path)
            except Exception as e:
                print(f"[重新生成图片分析结果] 打开PDF文件失败（非扫描件）: {e}")
        
        # 写入PreImageOrigin_pdf.md
        with open(pre_image_origin_path, 'w', encoding='utf-8') as f:
            for idx, doc in enumerate(image_docs_filtered, start=1):
                # 获取页码信息
                page_num = doc.metadata.get('page', 0)
                page_display = page_num + 1 if isinstance(page_num, int) else page_num
                
                # 提取图片位置的前后各100字文本和页数信息
                context_info = {'page_num': page_display, 'context_before': '', 'context_after': ''}
                
                if is_scanned:
                    # 扫描件：从OCR文件提取
                    page_info = img_seq_to_page_info.get(idx, {})
                    if page_info:
                        context_info = extract_image_context_from_ocr_txt(
                            txt_path,
                            page_info['page_num'],
                            page_info['seq_in_page']
                        )
                elif pdf_doc and page_num < len(pdf_doc):
                    # 非扫描件：从PDF页面提取文本
                    try:
                        page = pdf_doc[page_num]
                        page_text = page.get_text()
                        if page_text:
                            # 简单提取：取页面文本的前后各100字作为上下文
                            # 注意：这里无法精确定位图片位置，只能提取页面整体文本
                            lines = page_text.split('\n')
                            # 取前几行和后几行
                            before_lines = lines[:min(10, len(lines))]
                            after_lines = lines[max(0, len(lines) - 10):]
                            context_before = ' '.join(before_lines)[-100:] if before_lines else ""
                            context_after = ' '.join(after_lines)[:100] if after_lines else ""
                            context_info = {
                                'page_num': page_display,
                                'context_before': context_before,
                                'context_after': context_after
                            }
                    except Exception as e:
                        print(f"[重新生成图片分析结果] 提取第 {idx} 张图片的PDF页面文本失败: {e}")
                
                # 写入内容
                f.write(f"## 图片 {idx}\n\n")
                f.write(f"**页码**：第 {context_info['page_num']} 页\n\n")
                if context_info.get('context_before'):
                    f.write(f"**前文（100字）**：{context_info['context_before']}\n\n")
                if context_info.get('context_after'):
                    f.write(f"**后文（100字）**：{context_info['context_after']}\n\n")
                
                # 提取图片分析结果（去掉前缀）
                content = doc.page_content
                # 去掉可能的前缀（如"xxx_image/文件中的一张图片，内容为"）
                if "文件中的一张图片，内容为" in content:
                    content = content.split("文件中的一张图片，内容为", 1)[1]
                
                f.write(f"**图片分析结果**：\n{content}\n\n")
                f.write("---\n\n")
        
        print(f"[重新生成图片分析结果] 成功写入: {pre_image_origin_path}")
        
        # 关闭PDF文档（如果打开了）
        if pdf_doc:
            pdf_doc.close()
        
        # 如果PreImageSummary不存在，提示可以生成
        summary_filename = f"{file_base_name}_PreImageSummary_pdf.md"
        summary_path = os.path.join(base_dir, summary_filename)
        if not os.path.exists(summary_path):
            print(f"[重新生成图片分析结果] 提示：PreImageSummary不存在，可以调用process_pre_image_summary生成")
        
        return True, None
        
    except Exception as e:
        error_msg = f"重新生成图片分析结果失败: {str(e)}"
        print(f"[重新生成图片分析结果] {error_msg}")
        import traceback
        traceback.print_exc()
        return False, error_msg


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("使用方法: python regenerate_pre_image_origin.py <username> <docs_name>")
        print("例如: python regenerate_pre_image_origin.py marklee_ThreeBrainForEduHelath test.pdf")
        sys.exit(1)
    
    usr_name = sys.argv[1]
    docs_name = sys.argv[2]
    
    success, error_msg = regenerate_pre_image_origin(usr_name, docs_name)
    if success:
        print("✅ 重新生成图片分析结果成功")
    else:
        print(f"❌ 重新生成图片分析结果失败: {error_msg}")
        sys.exit(1)

