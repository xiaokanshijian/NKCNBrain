"""卡片高价值筛分辅助（都江堰式严格筛分，由 LLM 判定，无代码硬顶配额）。"""

# 与原先 card_analyzer 内联 prompt 保持一致
STRICT_VALUE_SYSTEM_PROMPT = """你是一个专业的卡片价值评估专家，擅长判断卡片是否有打上四色/DMT属性的价值。

判断标准：
1. **高价值卡片**应该具有以下特征之一或多个：
   - 内容质量高，贴合场景目标
   - 属于特定子场景，且内容与子场景目标高度相关
   - 字数篇幅颗粒度适中或较小（通常100-1500字）
   - 具有明确的价值和意义

2. **低价值/平庸卡片**通常具有以下特征：
   - 整体价值较低
   - 颗粒度太大（内容过于宽泛，缺乏聚焦）
   - 内容质量一般，与场景目标关联度低
   - 字数过多或过少且缺乏价值

3. **重要原则**：
   - 高价值卡片应占总卡片数量的较低比例（约10-15%），既筛出真正有价值内容，又不过度严苛
   - 低价值/平庸卡片应该占绝大多数，这样才能体现出类似都江堰飞沙堰的筛分价值
   - 请严格判断，只有真正特别高水准的卡片才判定为高价值，才有打上四色/DMT属性的必要

请根据以上标准，判断以下卡片是否有打上四色/DMT属性的价值。
只返回 "YES" 或 "NO"，不要有其他说明文字。"""


def card_has_four_color_or_dmt(card) -> bool:
    if isinstance(card, dict):
        fc = (card.get('four_color_type') or '').strip()
        dmt = (card.get('dmt_level') or '').strip()
    else:
        fc = (getattr(card, 'four_color_type', None) or '').strip()
        dmt = (getattr(card, 'dmt_level', None) or '').strip()
    return bool(fc or dmt)


def count_high_value_cards(all_cards_data, exclude_cid=None) -> int:
    if not all_cards_data:
        return 0
    count = 0
    for c in all_cards_data:
        if exclude_cid is not None and c.get('cid') == exclude_cid:
            continue
        if card_has_four_color_or_dmt(c):
            count += 1
    return count


def notebook_high_value_stats(all_cards_data, total_cards_count, include_pending_card=True,
                              exclude_cid=None):
    high_count = count_high_value_cards(all_cards_data, exclude_cid=exclude_cid)
    denom = max(int(total_cards_count or 0) + (1 if include_pending_card else 0), 1)
    ratio = high_count / denom
    return high_count, ratio


def build_value_scene_context(scene_name, sub_scene_name, scene_summary, notebook_description,
                              total_cards_count, all_cards_data, exclude_cid=None) -> str:
    """拼装场景上下文；主体与原先 card_analyzer 内联逻辑一致，并附带当前本子高价值占比供参考。"""
    scene_context = ""
    if scene_name:
        scene_context += f"\n\n**当前场景信息**：\n"
        scene_context += f"- 场景名称：{scene_name}\n"
        if sub_scene_name:
            scene_context += f"- 子场景名称：{sub_scene_name}\n"
        if scene_summary:
            summary_short = scene_summary[:300] + "..." if len(scene_summary) > 300 else scene_summary
            scene_context += f"- 场景内涵摘要：{summary_short}\n"
        if notebook_description:
            scene_context += f"- 本子描述：{notebook_description}\n"

    if total_cards_count:
        scene_context += f"\n**上下文信息**：\n"
        scene_context += f"- 本子中总卡片数量：{total_cards_count}\n"
        scene_context += (
            "- 高价值卡片占总数的比例宜控制在10-20%，"
            "有打上四色/DMT属性的价值的卡片判定要严苛，严格判断\n"
        )
        if all_cards_data:
            high_count, high_ratio = notebook_high_value_stats(
                all_cards_data, total_cards_count, include_pending_card=True, exclude_cid=exclude_cid
            )
            scene_context += (
                f"- （参考）当前已有高价值卡 {high_count} 张，占比约 {high_ratio:.1%}；"
                f"请结合上述 10-15% 原则从严筛分，但本卡内容确实突出时仍应独立判 YES\n"
            )
    return scene_context
