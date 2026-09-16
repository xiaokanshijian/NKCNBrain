"""
文档总图生成 - 类似飞书智能纪要的总结图
基于Summary和Topic生成综合性的结构化理解图
"""

from llm_langchain import global_var
from app_chat.core.model_manager import model_manager


# 总图生成Prompt
OVERVIEW_MAP_PROMPT = """# 文档总图生成要求

你要生成一个**文字描述的结构图**，帮助用户一眼看清文档的整体结构和核心思想。

## 输入信息
你会收到：
1. 文档的Summary（深度摘要）
2. 文档的Topic列表（主题关键词）

## 任务目标
基于Summary和Topic，生成一个清晰的**文档认知地图**（文字形式）。

## 输出格式

```
┌─────────────────────────────────────┐
│  [文档核心]  一句话本质（15-20字）   │
└─────────────────────────────────────┘
              ↓
    ┌─────────┴─────────┐
    │                   │
[主线1]             [主线2]
关键要点            关键要点
    │                   │
    ↓                   ↓
[分支A]             [分支B]
具体内容            具体内容
```

### 具体要求：

**第一层：文档核心**（1句话，15-20字）
- 击穿文档本质，不是标题重复

**第二层：核心主线**（2-3个）
- 从Summary中提炼的主要论述线
- 每个主线用10字内概括+20字关键要点

**第三层：重要分支**（3-5个）
- 基于Topic和Summary的重要内容
- 每个分支：主题词+简要说明（15字内）

**关系箭头：**
- 用"→"、"↓"表示逻辑关系
- 用"├"、"└"表示层级关系
- 清晰展示内容如何展开

### 设计要点：

1. **简洁清晰**
   - 不超过300字
   - 结构一目了然
   - 逻辑关系明确

2. **抓住精髓**
   - 不是所有内容都塞进去
   - 而是抓住最核心的结构
   - 体现深度理解

3. **视觉化**
   - 用符号和缩进营造视觉层次
   - 像一张真正的图
   - 便于快速把握

4. **有洞察**
   - 不只是重复Summary
   - 而是以图的形式展现内在逻辑
   - 让用户"一眼看懂"文档结构

### 示例（参考格式，不需要照搬，可以自由发挥，只要符合要求即可）：

```
┌─────────────────────────────────────────┐
│   [文档核心本质的一句话概括]            │
└─────────────────────────────────────────┘
                  ↓
      ┌───────────┼───────────┐ ...
      │           │           │
  [主线1]     [主线2]     [主线3]
  关键要点     关键要点     关键要点
  支撑论述     支撑论述     支撑论述
      │           │           │
      ↓           ↓           ↓
  ┌───┴───┐   ┌───┴───┐   ┌───┴───┐
  │       │   │       │   │       │
[分支A] [分支B] [分支C] [分支D] [分支E] [分支F] ...
具体内容 具体内容 具体内容 具体内容 具体内容 具体内容
```

## 核心原则
- 忠实Summary和Topic
- 提炼结构化关系
- 简洁而有洞察
- 让人一眼看懂

## 多文档权重说明

如果Summary和Topic来自多个文档：
- **标注为【主文档】的文档**（用户点开的文档），总图必须**80%以上体现主文档结构**
- **标注为【辅助文档】的文档**是辅助参考，只在与主文档有直接关联时才体现在图中
- 总图的核心层、主线层都应优先展现主文档

生成一个让用户感叹"这张图把文档讲清楚了！"的认知地图。
"""


def generate_overview_map(summary_text, topic_list, user_name):
    """
    基于Summary和Topic生成文档总图
    
    Args:
        summary_text: Summary文本
        topic_list: Topic列表（字符串或列表）
        user_name: 用户名
        
    Returns:
        文档总图（文字形式）
    """
    try:
        # 1. 处理topic_list
        if isinstance(topic_list, str):
            # 可能是 "{'topic1', 'topic2', 'topic3'}" 格式
            import re
            topics = re.findall(r"'([^']+)'", topic_list)
            if not topics:
                # 尝试按逗号分割
                topics = [t.strip() for t in topic_list.split(',')]
        else:
            topics = topic_list
        
        topics_str = "、".join(topics[:7])  # 最多7个
        
        # 2. 构造输入
        input_text = f"""【文档Summary】
{summary_text[:800]}...

【文档Topic列表】
{topics_str}

请基于以上Summary和Topic，生成文档总图（文字形式的结构图）。
"""
        
        # 3. 调用模型生成
        cur_sequence = global_var.store_memory[user_name]["model_num"]
        cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
        
        # 使用summary chain（复用已有的）
        result = cur_handler.chain_run("sma_chain", {
            "sum_prompt": OVERVIEW_MAP_PROMPT,
            "text": input_text,
            "images_store": []
        })
        
        overview_map = result.content if hasattr(result, 'content') else str(result)
        
        print(f"[总图生成] 成功，长度: {len(overview_map)}")
        return overview_map
        
    except Exception as e:
        print(f"[总图生成] 失败: {e}")
        import traceback
        traceback.print_exc()
        return ""


def should_generate_overview_map():
    """
    判断是否应该生成总图
    可以通过配置控制
    """
    # 默认启用
    return True

