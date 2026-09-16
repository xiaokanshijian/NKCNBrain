"""
增强版Topic追问生成 - 螺旋递进式认知激发
基于现有get_rel_que.py扩展，不另起炉灶
"""

from llm_langchain import global_var, util
from llm_langchain.enhanced_prompts import get_enhanced_topic_question_prompt, enhance_original_prompt
from app_chat.core.model_manager import model_manager
from langchain_core.messages import HumanMessage, AIMessage
from app_chat.utils import remove_thinking_and_checking_blocks
import json
import re


def get_question_enhanced(question, answer, user_name, all_segments, selected_topic, 
                         all_images=None, all_seqs=None, all_exts=None, 
                         depth_suggestion="", use_full_enhancement=True):
    """
    增强版topic追问生成 - 螺旋递进式问题链
    
    Args:
        question: 原始问题（"请列出主题"）
        answer: topic回答（主题列表或主题网络）
        user_name: 用户名
        all_segments: 文档分段
        selected_topic: 用户选择的topic
        all_images: 图片列表
        all_seqs: 图片顺序
        all_exts: 图片扩展名
        depth_suggestion: 小模型深度建议
        use_full_enhancement: 是否使用完全增强模式
        
    Returns:
        增强版追问问题（可能是JSON格式的问题链）
    """
    # 1. 清理回答中的thinking/checking内容
    cleaned_answer = remove_thinking_and_checking_blocks(answer)
    
    # 2. 准备图片内容
    images_list = []
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    
    if all_images and all_seqs and len(all_images) > 0:
        info_list = []
        for i, doc_images in enumerate(all_images):
            doc_segments = all_segments[i] if i < len(all_segments) else []
            
            # 添加文档首段
            if doc_segments:
                info_list.append({
                    "type": "text",
                    "text": doc_segments[0].page_content
                })
            
            # 添加图片
            if doc_images:
                for j, image in enumerate(doc_images):
                    ext = all_exts[i][j] if all_exts and i < len(all_exts) and j < len(all_exts[i]) else "jpeg"
                    info_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{ext};base64,{image}"
                        }
                    })
            
            # 添加文档尾段
            if doc_segments:
                info_list.append({
                    "type": "text",
                    "text": doc_segments[-1].page_content
                })
        
        images_list = [HumanMessage(content=info_list)]
    
    # 3. 优化文档选择（第一段+最后一段+中间随机一段）
    from llm_langchain import get_rel_que
    optimized_segments = get_rel_que.optimize_document_selection(all_segments)
    
    # 4. 构造文本内容
    text = ""
    for i, doc_segments in enumerate(optimized_segments):
        text += util.link_text([segment.page_content for segment in doc_segments])
    
    # 5. 添加选定主题的上下文
    text = f"【用户选择的主题】\n{selected_topic}\n\n【文档内容】\n{text}"
    
    # 6. 添加深度建议（如果有）
    if depth_suggestion:
        text += f"\n\n【追问策略建议】（小模型建议，供参考）：\n{depth_suggestion}"
    
    # 7. 获取增强prompt
    if use_full_enhancement:
        # 使用完全增强的新prompt
        que_prompt = get_enhanced_topic_question_prompt()
        print("[增强Topic追问] 使用完全增强模式（螺旋问题链）")
    else:
        # 增强原有prompt
        original_prompt = global_var.store_memory[user_name]["prompt"]["LUI2"]["topic_question"]
        que_prompt = enhance_original_prompt(original_prompt, "topic_question")
        print("[增强Topic追问] 使用增强原prompt模式")
    
    # 8. 构造对话历史
    chat_history = [
        HumanMessage(content=f"请列出文档的主题"),
        AIMessage(content=cleaned_answer),
        HumanMessage(content=f"我对「{selected_topic}」这个主题很感兴趣，请基于文档内容生成深度追问")
    ]
    
    # 9. 调用模型生成（固定使用Claude）
    claude_model_num = 4
    try:
        from llm_langchain.get_rel_que import que_chain
        
        if claude_model_num in que_chain:
            out = util.chain_run_claude(que_chain[claude_model_num], {
                "que_prompt": que_prompt,
                "text": text,
                "chat_history": chat_history,
                "images_store": images_list
            })
            
            # Claude可能第一次失败，给第二次机会
            if out is None:
                print("[增强Topic追问] 第一次调用失败，重试")
                out = util.chain_run_claude(que_chain[claude_model_num], {
                    "que_prompt": que_prompt,
                    "text": text,
                    "chat_history": chat_history,
                    "images_store": images_list
                })
            
            if out:
                result = out.content if hasattr(out, 'content') else str(out)
                print("[增强Topic追问] 生成完成，长度:", len(result))
                
                # 10. 如果是完全增强模式，尝试解析JSON格式的问题链
                if use_full_enhancement:
                    formatted = format_question_chain(result)
                    return formatted if formatted else result
                
                return result
        else:
            print("[增强Topic追问] Claude模型链未初始化，使用用户当前模型")
            cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
            out = cur_handler.chain_run("que_chain", {
                "que_prompt": que_prompt,
                "text": text,
                "chat_history": chat_history,
                "images_store": images_list
            })
            result = out.content if hasattr(out, 'content') else str(out)
            return result
            
    except Exception as e:
        print(f"[增强Topic追问] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return "追问生成失败"


def format_question_chain(response_text):
    """
    格式化问题链JSON为易读文本
    
    Args:
        response_text: 模型返回的文本（可能包含JSON）
        
    Returns:
        格式化后的问题链文本
    """
    try:
        # 提取JSON内容
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        elif response_text.strip().startswith('{'):
            json_str = response_text
        else:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            json_str = json_match.group(0) if json_match else None
        
        if not json_str:
            return None
        
        # 解析JSON
        question_data = json.loads(json_str)
        
        # 格式化输出
        output = []
        output.append("🌀 螺旋递进式追问问题链\n")
        output.append("=" * 50)
        
        if "question_chain" in question_data:
            for i, q_item in enumerate(question_data["question_chain"], 1):
                output.append(f"\n\n【问题{i}】{q_item['question']}")
                output.append(f"维度：{q_item.get('dimension', '')} | 层级：{q_item.get('level', '')}")
                output.append(f"设计意图：{q_item.get('intention', '')}")
                if 'expected_insight' in q_item:
                    output.append(f"预期洞察：{q_item['expected_insight']}")
        
        if "question_strategy" in question_data:
            output.append("\n\n" + "=" * 50)
            output.append(f"\n💡 追问策略：{question_data['question_strategy']}")
        
        output.append("\n\n" + "=" * 50)
        
        # 同时输出简洁的问题列表（供前端使用）
        simple_questions = []
        if "question_chain" in question_data:
            for q_item in question_data["question_chain"]:
                simple_questions.append(q_item['question'])
        
        # 组合：格式化说明 + 简洁列表
        final_output = '\n'.join(output)
        final_output += "\n\n【提取的问题列表】\n" + '\n'.join(f"{i+1}. {q}" for i, q in enumerate(simple_questions))
        
        return final_output
        
    except Exception as e:
        print(f"[格式化问题链] 失败: {e}")
        return None


def get_question_split_enhanced(question, answer, user_name, all_segments, selected_topic,
                                all_images=None, all_seqs=None, all_exts=None,
                                special_prompt="", depth_suggestion="", use_full_enhancement=True):
    """
    增强版分段文档topic追问（多文档支持）
    
    这是对外的主要接口，兼容原有调用方式
    """
    return get_question_enhanced(
        question=question,
        answer=answer,
        user_name=user_name,
        all_segments=all_segments,
        selected_topic=selected_topic,
        all_images=all_images,
        all_seqs=all_seqs,
        all_exts=all_exts,
        depth_suggestion=depth_suggestion,
        use_full_enhancement=use_full_enhancement
    )


def get_question_auto(question, answer, user_name, all_segments, selected_topic, **kwargs):
    """
    自动选择使用增强版或原版topic追问
    
    统一入口，自动决定使用哪个版本
    """
    # 默认使用增强版
    return get_question_enhanced(
        question=question,
        answer=answer,
        user_name=user_name,
        all_segments=all_segments,
        selected_topic=selected_topic,
        all_images=kwargs.get('all_images'),
        all_seqs=kwargs.get('all_seqs'),
        all_exts=kwargs.get('all_exts'),
        depth_suggestion=kwargs.get('depth_suggestion', ''),
        use_full_enhancement=True
    )

