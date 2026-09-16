"""
增强版Summary生成 - 基于飞书启发的"螺旋认知增强框架"
基于现有get_suma_new.py扩展，不另起炉灶
"""

from llm_langchain import global_var, util
from llm_langchain.enhanced_prompts import get_enhanced_summary_prompt, enhance_original_prompt
from app_chat.core.model_manager import model_manager
from langchain_core.messages import HumanMessage


def get_summary_enhanced(user_name, docs=None, all_segments=None, images=None, seqs=None, use_full_enhancement=True):
    """
    增强版文档摘要生成
    
    Args:
        user_name: 用户名
        docs: 文档列表（可选，优先使用all_segments）
        all_segments: 分段后的文档列表
        images: 图片列表
        seqs: 图片顺序
        use_full_enhancement: 是否使用完全增强模式（True=使用新prompt，False=增强原prompt）
        
    Returns:
        增强版摘要内容
    """
    # 1. 准备文本内容
    text = ""
    if all_segments:
        for i, doc_segments in enumerate(all_segments):
            text += util.link_text([segment.page_content for segment in doc_segments])
    elif docs:
        text += util.link_text([doc.page_content for doc in docs])
    else:
        raise ValueError("必须提供docs或all_segments")
    
    # 2. 准备图片内容
    images_list = []
    count = 0
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    
    if cur_sequence == 0 and images and len(images) > 0:
        for image in images:
            count += 1
            images_list.append(HumanMessage(content=[
                {
                    "type": "text",
                    "text": f"This is the {count}nd image of {len(images)}, its order in all images should be {seqs[count - 1]}. If you use the image, use the order in all images as its reference."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image}"
                    }
                }
            ]))
    
    # 3. 获取增强prompt
    if use_full_enhancement:
        # 使用完全增强的新prompt
        sum_prompt = get_enhanced_summary_prompt()
        print("[增强Summary] 使用完全增强模式")
    else:
        # 增强原有prompt（保守方案）
        original_prompt = global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"]
        sum_prompt = enhance_original_prompt(original_prompt, "summary")
        print("[增强Summary] 使用增强原prompt模式")
    
    # 4. 调用模型生成
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    out = cur_handler.chain_run("sma_chain", {
        "sum_prompt": sum_prompt,
        "text": text,
        "images_store": images_list
    })
    
    print("[增强Summary] 生成完成，长度:", len(out.content))
    return out.content


def get_summary_split_enhanced(user_name, all_segments, all_images=None, all_seqs=None, all_exts=None, use_full_enhancement=True):
    """
    增强版分段文档摘要生成（多文档支持）
    
    Args:
        user_name: 用户名
        all_segments: 所有文档的分段列表
        all_images: 所有图片
        all_seqs: 图片顺序
        all_exts: 图片扩展名
        use_full_enhancement: 是否使用完全增强模式
        
    Returns:
        增强版摘要内容
    """
    # 复用单文档版本的逻辑
    return get_summary_enhanced(
        user_name=user_name,
        all_segments=all_segments,
        images=all_images,
        seqs=all_seqs,
        use_full_enhancement=use_full_enhancement
    )


# ==================== 兼容性函数 ====================

def should_use_enhanced_mode(user_name):
    """
    判断是否应该使用增强模式
    可以基于用户配置、场景等决定
    
    Args:
        user_name: 用户名
        
    Returns:
        bool: 是否使用增强模式
    """
    # 默认使用增强模式
    # 可以后续添加用户配置来控制
    return True


def get_summary_auto(user_name, docs=None, all_segments=None, images=None, seqs=None):
    """
    自动选择使用增强版或原版summary
    
    这个函数可以作为统一入口，自动决定使用哪个版本
    """
    if should_use_enhanced_mode(user_name):
        return get_summary_enhanced(
            user_name=user_name,
            docs=docs,
            all_segments=all_segments,
            images=images,
            seqs=seqs,
            use_full_enhancement=True
        )
    else:
        # 调用原版
        from llm_langchain.get_suma_new import get_summary_split
        return get_summary_split(user_name, all_segments, images, seqs, None)

