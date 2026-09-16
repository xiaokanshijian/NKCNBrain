"""
增强版Topic生成 - 构建主题认知网络
基于现有get_topic_new.py扩展，不另起炉灶
"""

from llm_langchain import global_var, util
from llm_langchain.enhanced_prompts import get_enhanced_topic_prompt, ENHANCED_TOPIC_EXTRACTION_PROMPT, enhance_original_prompt
from app_chat.core.model_manager import model_manager
from langchain_core.messages import HumanMessage
import json
import re


def get_topic_enhanced(user_name, text=None, all_segments=None, images=None, seqs=None, use_full_enhancement=True):
    """
    增强版主题提取 - 生成主题认知网络
    
    Args:
        user_name: 用户名
        text: 文本内容（可选，优先使用all_segments）
        all_segments: 分段后的文档列表
        images: 图片列表
        seqs: 图片顺序
        use_full_enhancement: 是否使用完全增强模式
        
    Returns:
        主题认知网络（JSON格式或解析后的字符串）
    """
    # 1. 准备文本内容
    if all_segments:
        text = ""
        for i, doc_segments in enumerate(all_segments):
            text += util.link_text([segment.page_content for segment in doc_segments])
    elif not text:
        raise ValueError("必须提供text或all_segments")
    
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
                    "text": f"This is the {count}nd image of {len(images)}, its order in all images should be {seqs[count - 1]}."
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
        # 使用完全增强的JSON格式prompt
        topic_prompt = ENHANCED_TOPIC_EXTRACTION_PROMPT
        print("[增强Topic] 使用完全增强模式（JSON输出）")
    else:
        # 增强原有prompt
        original_prompt = global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"]
        topic_prompt = enhance_original_prompt(original_prompt, "topic")
        print("[增强Topic] 使用增强原prompt模式")
    
    # 4. 调用模型生成
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    out = cur_handler.chain_run("topic_chain", {
        "topic_prompt": topic_prompt,
        "text": text,
        "images_store": images_list
    })
    
    result = out.content if hasattr(out, 'content') else str(out)
    print("[增强Topic] 生成完成，长度:", len(result))
    
    # 5. 如果是完全增强模式，尝试解析JSON并格式化展示
    if use_full_enhancement:
        try:
            # 提取JSON内容（可能被包在markdown代码块中）
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            elif result.strip().startswith('{'):
                # 直接就是JSON
                json_str = result
            else:
                # 尝试从文本中提取JSON
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                json_str = json_match.group(0) if json_match else result
            
            # 解析JSON
            topic_network = json.loads(json_str)
            
            # 格式化为易读的文本形式
            formatted = format_topic_network(topic_network)
            return formatted
            
        except Exception as e:
            print(f"[增强Topic] JSON解析失败，返回原始内容: {e}")
            return result
    
    return result


def format_topic_network(topic_data):
    """
    将主题网络JSON格式化为易读的文本
    
    Args:
        topic_data: 主题网络JSON数据
        
    Returns:
        格式化后的文本
    """
    output = []
    output.append("📋 文档主题认知网络\n")
    output.append("=" * 50)
    
    # 核心主题
    if "核心主题" in topic_data:
        output.append("\n\n🎯 核心主题")
        for topic in topic_data["核心主题"]:
            output.append(f"\n• {topic['name']}")
            output.append(f"  本质：{topic.get('essence', '')}")
            output.append(f"  覆盖：{topic.get('coverage', '')}")
            output.append(f"  深度：{topic.get('depth', '')}")
    
    # 支撑主题
    if "支撑主题" in topic_data:
        output.append("\n\n🔗 支撑主题")
        for topic in topic_data["支撑主题"]:
            output.append(f"\n• {topic['name']}")
            output.append(f"  本质：{topic.get('essence', '')}")
            output.append(f"  与核心关系：{topic.get('relation_to_core', '')}")
    
    # 涌现主题
    if "涌现主题" in topic_data:
        output.append("\n\n✨ 涌现主题")
        for topic in topic_data["涌现主题"]:
            output.append(f"\n• {topic['name']}")
            output.append(f"  本质：{topic.get('essence', '')}")
            output.append(f"  涌现原因：{topic.get('why_emergent', '')}")
            output.append(f"  潜在价值：{topic.get('potential', '')}")
    
    # 主题关系网络
    if "主题关系网络" in topic_data:
        output.append("\n\n🕸️ 主题关系网络")
        output.append(f"\n{topic_data['主题关系网络']}")
    
    output.append("\n\n" + "=" * 50)
    
    return '\n'.join(output)


def get_topic_split_enhanced(user_name, all_segments, all_images=None, all_seqs=None, all_exts=None, use_full_enhancement=True):
    """
    增强版分段文档主题提取（多文档支持）
    
    Args:
        user_name: 用户名
        all_segments: 所有文档的分段列表
        all_images: 所有图片
        all_seqs: 图片顺序
        all_exts: 图片扩展名
        use_full_enhancement: 是否使用完全增强模式
        
    Returns:
        主题认知网络
    """
    return get_topic_enhanced(
        user_name=user_name,
        all_segments=all_segments,
        images=all_images,
        seqs=all_seqs,
        use_full_enhancement=use_full_enhancement
    )


def get_topic_auto(user_name, text=None, all_segments=None, images=None, seqs=None):
    """
    自动选择使用增强版或原版topic
    
    统一入口，自动决定使用哪个版本
    """
    # 默认使用增强版
    return get_topic_enhanced(
        user_name=user_name,
        text=text,
        all_segments=all_segments,
        images=images,
        seqs=seqs,
        use_full_enhancement=True
    )

