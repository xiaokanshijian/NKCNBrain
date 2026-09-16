import math
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import tiktoken
from django.utils import timezone
from django.db.models.functions import Length
from typing import List, Tuple, Dict

from app_chat import claude_api
from app_chat.models import Card, BgCard
from zym.models import UserNotebook, scene


def clean_emoji(text):
    # 保留以下字符：
    # 1. 中文字符（包括生僻字、扩展汉字）
    # 2. 英文字母（包括各种变体字母）
    # 3. 数字（包括上下标、分数等）
    # 4. 中英文标点符号
    # 5. 空格、回车、制表符等空白字符
    # 6. 常用数学符号
    pattern = (
        r'[^\u4e00-\u9fff'  # 基本汉字
        r'\u3400-\u4dbf'    # 扩展A区汉字
        r'\u20000-\u2a6df'  # 扩展B区汉字
        r'\u2a700-\u2b73f'  # 扩展C区汉字
        r'\u2b740-\u2b81f'  # 扩展D区汉字
        r'\u2b820-\u2ceaf'  # 扩展E区汉字
        r'\u2ceb0-\u2ebef'  # 扩展F区汉字
        r'\u3000-\u303f'    # 中文标点
        r'\uff00-\uff60'    # 全角字符
        r'\u0020-\u007e'    # 基本ASCII字符
        r'\u0000-\u001f'    # 控制字符（包括\n、\t等）
        r'\u2000-\u206f'    # 常用标点和符号
        r'\u2070-\u209f'    # 上标和下标
        r'\u2100-\u214f'    # 字母符号
        r'\u2150-\u218f'    # 数字形式（分数等）
        r'\u2190-\u21ff'    # 箭头
        r'\u2200-\u22ff'    # 数学运算符
        r'\u2500-\u257f'    # 制表符
        r'\ufb00-\ufb4f'    # 字母变体
        r'\u3040-\u309f'    # 平假名
        r'\u30a0-\u30ff'    # 片假名
        r'\u00a0-\u00ff'    # 带重音的拉丁字母
        r']'
    )
    return re.sub(pattern, '', text)


def count_tokens(text: str) -> int:
    """计算文本的tokens数量"""
    enc = tiktoken.encoding_for_model("gpt-4o")
    tokensNum = len(enc.encode(text))
    adjusted_tokens = tokensNum * 1.1  # 乘以 1.1
    return math.ceil(adjusted_tokens)  # 向上取整


def group_texts_by_tokens(texts: List[str], target_tokens: int = 4000,
                          tolerance: int = 1000) -> List[List[str]]:
    """将文本列表按照目标token数分组"""
    groups = []
    current_group = []
    current_tokens = 0

    for text in texts:
        text_tokens = count_tokens(text)
        if current_tokens + text_tokens <= target_tokens + tolerance:
            current_group.append(text)
            current_tokens += text_tokens
        else:
            if current_group:
                groups.append(current_group)
            current_group = [text]
            current_tokens = text_tokens

    if current_group:
        groups.append(current_group)

    return groups


def get_bgcard_cache(num: int, username: str = "", bookname: str = "", scenename: str = "") -> str:
    """查询摘要缓存
    Args:
        num: 1-群体摘要，2-场景摘要，3-用户摘要，4-本子摘要
        username: 用户名
        bookname: 本子名
        scenename: 场景名
    """
    # 构建username字段（存储格式为"用户名_本子名"）
    if num == 4:
        username_field = f"{username}_{bookname}"
    else:
        username_field = username if username else "NKCNGBrain"

    # 构建name和detail字段
    if num == 1:
        name = "全部场景背景摘要"
    elif num == 2:
        name = f"{scenename}场景背景摘要"
    elif num == 3:
        name = f"{username}全部笔记本背景摘要"
    elif num == 4:
        name = f"{username_field}笔记本背景摘要"
    else:
        return None

    detail = name

    # 查询缓存
    bgcard = BgCard.objects.filter(
        username=username_field,
        status=str(num),
        name=name
        # detail=detail
    ).first()

    print(username_field + " " + str(num) + " " + name)
    if bgcard:
        print("有记录")
    else:
        print("无记录")

    return bgcard.content if bgcard else None


def save_bgcard_cache(num: int, content: str, username: str = "",
                      bookname: str = "", scenename: str = "") -> None:
    """保存摘要缓存
    Args:
        num: 1-群体摘要，2-场景摘要，3-用户摘要，4-本子摘要
        content: 摘要内容
        username: 用户名
        bookname: 本子名
        scenename: 场景名
    """
    # 构建username字段（存储格式为"用户名_本子名"）
    if num == 4:
        username_field = f"{username}_{bookname}"
    else:
        username_field = username if username else "NKCNGBrain"

    # 构建name和detail字段
    if num == 1:
        name = "全部场景背景摘要"
    elif num == 2:
        name = f"{scenename}场景背景摘要"
    elif num == 3:
        name = f"{username}全部笔记本背景摘要"
    elif num == 4:
        name = f"{username_field}笔记本背景摘要"
    else:
        return

    detail = name

    # 在保存前清理内容
    content = clean_emoji(content)

    current_datetime = timezone.now()
    BgCard.objects.create(
        username=username_field,
        datetime=current_datetime,
        status=str(num),
        name=name,
        detail=detail,
        content=content
    )


def make_summary(text: str, target_length: str = "2000") -> str:
    """统一的摘要生成接口"""
    system_prompt = f"""你是一个专注于用户知识构建的AI助手。你的任务是将输入的大量文本转化为结构化的知识摘要，这份摘要将用于支持后续的对话系统。
        输入的文本集合中，每段文本都可能有其独特的侧重点和主题重心，你需要：
        1. 识别每段文本的独特价值和侧重点
        2. 确保不同主题的信息都得到合理关注，避免偏废
        3. 寻找不同主题间的关联和共性
        4. 在保持各自特色的同时构建统一的知识体系
        5. 对于重复或相似的内容，应从不同角度和层次进行整合
        6. 注意写摘要时不要机械地说文本1讲了什么、文本2讲了什么等等，应该构建一个相对连贯、系统的知识体系，是一份融会贯通的整体性摘要
        
        具体而言，请遵循以下要求：
        1. 内容组织
        - 识别并提取用户关注的核心主题
        - 按照时间顺序和逻辑关联组织信息
        - 突出用户的重要行为、决策和思考过程
        - 保留关键的背景信息和上下文
        
        2. 结构要求
        - 使用清晰的层级结构标注不同主题
        - 用简洁的关键词标记重要概念
        - 建立主题之间的关联关系
        - 确保信息的可追溯性
        
        3. 摘要原则
        - 使用中文，总字数控制在{target_length}字左右
        - 保持语言的简洁性和可理解性
        - 去除冗余但保留核心细节
        - 突出对话中可能涉及的重点话题
        
        4. 知识关联
        - 构建主题间的关系网络
        - 标注重要的时间节点
        - 保留用户的关键思维路径
        - 突出可能的讨论延展点
        
        请直接输出处理后的知识摘要，保持客观专业的语气，不需要添加任何元信息或说明性文字；如果文本中有与代码相关的，不要撰写或优化代码，
        你需要做的是整体理解、不遗漏关键信息的摘要总结。摘要既应该是一个完整的知识体系，又应该便于对话系统快速检索和理解。记得使用中文做摘要。"""

    text = "待摘要的文本集合（如果有空的/内容质量明显过低的文本，请忽略）：\n\n" + text
    return claude_api.make_claude_text_requests(text, system_prompt)


# 分层摘要函数
def summarize_card_group(cards_content: List[str]) -> str:
    """卡片组摘要（基础层）"""
    combined_content = "\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, cards_content)))
    combined_content_pure = "\n".join(cards_content)
    total_tokens = count_tokens(combined_content)

    if total_tokens <= 6000:
        if count_tokens(combined_content) > 1000:
            return make_summary(combined_content, "1000")
        else:
            return combined_content_pure
    else:
        groups = group_texts_by_tokens(cards_content)
        group_summaries = []
        for group in groups:
            combined_group = "\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, group)))
            combined_group_pure = "\n".join(group)
            if count_tokens(combined_group) > 1000:
                group_summaries.append(make_summary(combined_group, "1000"))
            else:
                group_summaries.append(combined_group_pure)

        return make_summary("\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, group_summaries))), "1000")


def summarize_notebook(username: str, bookname: str) -> str:
    """本子摘要（一级聚合）"""
    # 查询缓存
    cache = get_bgcard_cache(num=4, username=username, bookname=bookname)
    if cache:
        return cache

    # 获取本子的所有卡片内容
    username_book_name = f"{username}_{bookname}"
    # NOTE: 25-05-27新增部分
    # cards_content = list(Card.objects.filter(
    #     username=username_book_name
    # ).values_list('content', flat=True))
    # 排除 content 字段大于 20000 字符的记录(如制备数据集时生成的那些超大卡片)，__lte 是 "less than or equal to" 的缩写，表示小于等于
    cards_content = list(Card.objects.filter(
        username=username_book_name
    ).annotate(
        content_length=Length('content')
    ).filter(
        content_length__lte=20000
    ).values_list('content', flat=True))

    combined_content = "\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, cards_content)))
    combined_content_pure = "\n".join(cards_content)
    total_tokens = count_tokens(combined_content)

    if total_tokens <= 6000:
        if total_tokens <= 1500:
            summary = combined_content_pure
        else:
            summary = make_summary(combined_content, "1000-1500")
    else:
        groups = group_texts_by_tokens(cards_content)
        group_summaries = []
        for group in groups:
            group_summaries.append(summarize_card_group(group))
        summary = make_summary("\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, group_summaries))), "1000-1500")

    # 保存缓存
    save_bgcard_cache(
        num=4,
        content=summary,
        username=username,
        bookname=bookname
    )

    return summary


def summarize_scene(username: str, scene_name: str) -> str:
    """场景摘要（二级聚合）"""
    # 查询缓存
    cache = get_bgcard_cache(num=2, username=username, scenename=scene_name)
    if cache:
        return cache

    # 获取场景下的所有本子
    cur_scene = scene.objects.filter(sceneDescription=scene_name).first()
    if not cur_scene:
        return ""

    notebooks = UserNotebook.objects.filter(
        sid=cur_scene.sid,
        username=username
    ).values_list('username', 'bookName')

    # 获取每个本子的摘要
    notebook_summaries = []
    for _, book_name in notebooks:
        notebook_summaries.append(summarize_notebook(username, book_name))

    # 生成场景摘要
    combined_content = "\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, notebook_summaries)))
    summary = make_summary(combined_content, "1500-2000")

    # 保存缓存
    save_bgcard_cache(
        num=2,
        content=summary,
        username=username,
        scenename=scene_name
    )

    return summary


def summarize_user(username: str) -> str:
    """用户摘要（三级聚合）"""
    # 查询缓存
    cache = get_bgcard_cache(num=3, username=username)
    if cache:
        return cache

    # 获取用户的所有场景
    scenes = scene.objects.filter(
        sid__in=UserNotebook.objects.filter(
            username=username
        ).values_list('sid', flat=True)
    ).distinct().values_list('sceneDescription', flat=True)

    # 如果用户的所有卡片内容不多，直接摘要
    cards_content = list(Card.objects.filter(
        username__startswith=username
    ).values_list('content', flat=True))

    combined_content = "\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, cards_content)))
    if count_tokens(combined_content) <= 6000:
        summary = make_summary(combined_content, "2000-2500")
    else:
        # 获取每个场景的摘要
        scene_summaries = []
        for scene_name in scenes:
            scene_summaries.append(summarize_scene(username, scene_name))

        # 生成用户摘要
        summary = make_summary("\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, scene_summaries))), "2000-2500")

    # 保存缓存
    save_bgcard_cache(
        num=3,
        content=summary,
        username=username
    )

    return summary


def summarize_group() -> str:
    """群体摘要（最高层）"""
    # 查询缓存
    cache = get_bgcard_cache(num=1)
    if cache:
        return cache

    # 获取所有卡片内容
    cards_content = list(Card.objects.all().values_list('content', flat=True))
    combined_content = "\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, cards_content)))

    if count_tokens(combined_content) <= 6000:
        summary = make_summary(combined_content, "2500-3000")
    else:
        # 获取所有用户
        users = Card.objects.values_list(
            'username', flat=True
        ).distinct()
        users = set(u.split('_')[0] for u in users)

        # 获取每个用户的摘要
        user_summaries = []
        for username in users:
            print("User: "+username)
            user_summaries.append(summarize_user(username))

        # 生成群体摘要
        summary = make_summary("\n".join(f"【文本{i + 1}】：\n{text}" for i, text in enumerate(filter(None, user_summaries))), "2500-3000")

    # 保存缓存
    save_bgcard_cache(
        num=1,
        content=summary
    )

    return summary
