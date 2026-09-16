"""
关键词匹配增强模块
用于根据核心关键词从md文件中查找相关段落，并获取对应的segments
"""
import os
import re
from langchain_core.documents import Document


def _find_keyword_in_md_sections(core_keyword, md_file_path, top_n=1):
    """
    从md文件中查找包含关键词的段落，返回得分前N的段落及其页数

    参数:
        core_keyword: 核心关键词
        md_file_path: md文件路径
        top_n: 返回前N个段落（默认1）

    返回:
        list: [(段落内容, 页数区间, 得分), ...] 或 []
    """
    try:
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 按---分割段落
        sections = content.split('---')

        # 生成关键词的所有连续子字符串
        def generate_substrings(keyword):
            substrings = []
            keyword_len = len(keyword)
            for length in range(keyword_len, 0, -1):
                for start in range(keyword_len - length + 1):
                    substr = keyword[start:start + length]
                    if substr not in substrings:
                        substrings.append(substr)
            return substrings

        keyword_substrings = generate_substrings(core_keyword)

        # 计算所有段落的得分
        section_scores = []
        for section in sections:
            if not section.strip():
                continue

            # 统计每个子字符串的出现次数
            total_score = 0
            for substr in keyword_substrings:
                pattern = re.escape(substr)
                count = len(re.findall(pattern, section, re.IGNORECASE))
                if count > 0:
                    total_score += len(substr) * count

            if total_score > 0:
                # 解析页数区间（格式：[页码：第X页] 或 [页码：第X页-第Y页]）
                page_match = re.search(r'\[页码：第(\d+)页(?:-第(\d+)页)?\]', section)
                if page_match:
                    start_page = int(page_match.group(1))
                    end_page = int(page_match.group(2)) if page_match.group(2) else start_page
                    page_range = (start_page, end_page)
                    section_scores.append((section, page_range, total_score))

        # 按得分排序，返回前N个
        section_scores.sort(key=lambda x: x[2], reverse=True)
        return section_scores[:top_n]

    except Exception as e:
        print(f"[_find_keyword_in_md_sections] 读取md文件失败 {md_file_path}: {e}")
        return []


def _get_segments_by_page_range(user_name, doc_name, page_range):
    """
    根据页数区间获取对应的segments

    参数:
        user_name: 用户名
        doc_name: 文档名
        page_range: 页数区间 (start_page, end_page)

    返回:
        list: Document对象列表
    """
    try:
        from llm_langchain import parse_input
        from llm_langchain.util import construct_file_path
        vector = parse_input.get_vector_by_user(user_name)

        # 构建文件路径用于查询
        file_path = construct_file_path(user_name, doc_name)

        # 从vector store中获取该文档的所有segments
        query = {"source": file_path}
        docs = vector.get(where=query)

        if not docs or not docs.get("ids"):
            return []

        # 筛选出页数在范围内的segments
        # 注意：metadata中的page是从0开始的，而md文件中的页数是从1开始的
        matching_segments = []
        for i, metadata in enumerate(docs.get("metadatas", [])):
            if metadata and "page" in metadata:
                page_num = metadata["page"]
                # 转换为从1开始的页码
                page_display = page_num + 1 if isinstance(page_num, int) else page_num

                if page_range[0] <= page_display <= page_range[1]:
                    segment = Document(
                        page_content=docs["documents"][i],
                        metadata=dict(metadata)
                    )
                    # 补充页码信息
                    if not segment.page_content.strip().startswith("[页码："):
                        segment.page_content = f"[页码：第{page_display}页]\n{segment.page_content}"
                    matching_segments.append(segment)

        return matching_segments

    except Exception as e:
        print(f"[_get_segments_by_page_range] 获取segments失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _rank_segments_by_keyword(segments, core_keyword, top_n=3):
    """
    对segments按关键词匹配度排序，返回前N个

    参数:
        segments: Document对象列表
        core_keyword: 核心关键词
        top_n: 返回前N个（默认3）

    返回:
        list: 排名前N的Document对象列表
    """
    if not segments or not core_keyword:
        return []

    # 生成关键词的所有连续子字符串
    def generate_substrings(keyword):
        substrings = []
        keyword_len = len(keyword)
        for length in range(keyword_len, 0, -1):
            for start in range(keyword_len - length + 1):
                substr = keyword[start:start + length]
                if substr not in substrings:
                    substrings.append(substr)
        return substrings

    keyword_substrings = generate_substrings(core_keyword)

    # 计算每个segment的得分
    segment_scores = []
    for segment in segments:
        content = segment.page_content
        total_score = 0
        for substr in keyword_substrings:
            pattern = re.escape(substr)
            count = len(re.findall(pattern, content, re.IGNORECASE))
            if count > 0:
                total_score += len(substr) * count

        if total_score > 0:
            segment_scores.append((segment, total_score))

    # 按得分排序，取前N个
    segment_scores.sort(key=lambda x: x[1], reverse=True)
    top_segments = [seg for seg, _ in segment_scores[:top_n]]

    return top_segments


def _enhance_segments_with_keyword(user_name, docs_name_list, core_keyword, vector, existing_segments):
    """
    使用核心关键词增强segments选择

    参数:
        user_name: 用户名
        docs_name_list: 文档名列表
        core_keyword: 核心关键词
        vector: 向量存储
        existing_segments: 现有的segments列表（按文档分组）

    返回:
        list: 增强后的segments列表（按文档分组）
    """
    try:
        # 1. 分离非相似搜索的segments（方式0、1、2）和相似搜索的segments（方式3）
        non_similarity_segments = []  # 方式0、1、2的segments
        similarity_segments = []  # 方式3的segments

        # existing_segments的结构：[[doc1方式0/1/2], [doc2方式0/1/2], ..., [similarity_segments方式3]]
        # 相似搜索的结果通常在最后一项
        for i, doc_segments in enumerate(existing_segments):
            if isinstance(doc_segments, list) and len(doc_segments) > 0:
                # 判断是否是最后一项（通常是相似搜索的结果）
                if i == len(existing_segments) - 1:
                    # 最后一项，检查是否是相似搜索的结果
                    # 相似搜索的结果通常包含多个文档的segments，且metadata中有source信息
                    # 为了更准确，我们检查segments是否来自多个不同的文档
                    sources = set()
                    for seg in doc_segments:
                        if isinstance(seg, Document) and seg.metadata and 'source' in seg.metadata:
                            sources.add(seg.metadata['source'])
                    # 如果来源超过1个文档，很可能是相似搜索的结果
                    if len(sources) > 1:
                        similarity_segments = doc_segments
                    else:
                        non_similarity_segments.append(doc_segments)
                else:
                    # 非最后一项，肯定是方式0、1、2的segments
                    non_similarity_segments.append(doc_segments)

        # 2. 根据文档数量动态决定策略
        num_docs = len(docs_name_list)
        if num_docs == 1:
            # 1个文档：md找前3段，每段找前2个segments = 3×2=6段
            top_md_sections = 3
            top_segments_per_section = 2
        elif num_docs == 2:
            # 2个文档：md找前2段，每段找前2个segments = 2×2×2=8段
            top_md_sections = 2
            top_segments_per_section = 2
        elif 3 <= num_docs < 5:
            # 3-4个文档：md找前1段（最高），每段找前3个segments = 1×3×文档数 = 9或12段
            top_md_sections = 1
            top_segments_per_section = 3
        else:  # num_docs >= 5
            # >=5个文档：md找前1段（最高），每段找前2个segments = 1×2×文档数
            top_md_sections = 1
            top_segments_per_section = 2

        print(f"[_enhance_segments_with_keyword] 文档数量: {num_docs}，策略: md找前{top_md_sections}段，每段找前{top_segments_per_section}个segments")

        # 3. 对每个勾选的文档，从md文件中查找包含关键词的段落
        keyword_enhanced_segments = []  # 存储所有文档的关键词匹配segments

        for doc_name in docs_name_list:
            # 解析username获取realName和bookName
            if '_' not in user_name:
                continue

            realName = user_name.split('_')[0]
            bookName = user_name[len(realName) + 1:]

            # 构建md文件路径
            # 去掉扩展名，构建md文件名
            doc_name_base = os.path.splitext(doc_name)[0]
            doc_ext = os.path.splitext(doc_name)[1].lstrip('.')
            md_file_path = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_summary/{doc_name_base}_Presummary_{doc_ext}.md'

            if not os.path.exists(md_file_path):
                print(f"[_enhance_segments_with_keyword] md文件不存在: {md_file_path}")
                continue

            # 查找包含关键词的前N个段落
            md_results = _find_keyword_in_md_sections(core_keyword, md_file_path, top_n=top_md_sections)
            if not md_results:
                print(f"[_enhance_segments_with_keyword] 文档 {doc_name} 的md文件中未找到包含关键词的段落")
                continue

            # 对每个匹配的段落，获取对应的segments并排序
            doc_segments = []
            for section_content, page_range, score in md_results:
                print(f"[_enhance_segments_with_keyword] 文档 {doc_name} 找到匹配段落，页数区间: {page_range}, 得分: {score}")

                # 根据页数区间获取对应的segments
                page_segments = _get_segments_by_page_range(user_name, doc_name, page_range)
                if not page_segments:
                    print(f"[_enhance_segments_with_keyword] 文档 {doc_name} 页数区间 {page_range} 未找到segments")
                    continue

                # 对segments按关键词匹配度排序，取前N个
                top_segments = _rank_segments_by_keyword(page_segments, core_keyword, top_n=top_segments_per_section)
                if top_segments:
                    doc_segments.extend(top_segments)

            if doc_segments:
                print(f"[_enhance_segments_with_keyword] 文档 {doc_name} 筛选出 {len(doc_segments)} 个关键词匹配segments")
                keyword_enhanced_segments.extend(doc_segments)

        # 4. 合并：保留原有的非相似搜索segments（方式0、1、2）+ 关键词匹配的segments + 相似搜索的segments（方式3）
        final_segments = non_similarity_segments.copy()  # 保留方式0、1、2的segments
        if keyword_enhanced_segments:
            # 添加关键词匹配的segments（根据文档数量动态调整，作为一个列表）
            final_segments.append(keyword_enhanced_segments)
        if similarity_segments:
            # 添加相似搜索的segments（方式3，10取5）
            final_segments.append(similarity_segments)

        print(f"[_enhance_segments_with_keyword] 增强完成：关键词匹配segments {len(keyword_enhanced_segments)} 个，相似搜索segments {len(similarity_segments)} 个")
        print(f"[_enhance_segments_with_keyword] 最终segments结构：{len(final_segments)} 个文档组，其中关键词匹配组包含 {len(keyword_enhanced_segments)} 个segments")
        
        return final_segments
        
    except Exception as e:
        print(f"[_enhance_segments_with_keyword] 错误: {e}")
        import traceback
        traceback.print_exc()
        return existing_segments  # 出错时返回原有segments

