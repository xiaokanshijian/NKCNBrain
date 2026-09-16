import asyncio
import base64
import io
import json
import re
import os
import random
import time

import io
import tempfile
import cv2
from PIL import Image, ImageOps
import numpy as np

import fitz
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel, SimpleChatModel
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompt_values import PromptValue
from langchain_openai import ChatOpenAI

from app_chat import gpt4_api, qwen_vl_api, claude_api
from llm_langchain import global_var, chat_gpt_model, parse_input, util, get_rel_que
from dashscope import MultiModalConversation
from app_chat.dmt_utils import get_image_base64_with_mime

# zym
# db_path = r"F:\python_relate\pycharm workspace\notebooklm-master3\Backend\llm_langchain\instructor-large"
# zyr
db_path = "./received_dir/user_db_file"

image_retry_summary_prompt = """请分析以下原始图片描述文本以及图片本身，更新一份更准确完整的图片描述：

原始图片描述：
{old_content}

请首先查看、理解图片内容，并基于以上信息（其中对图片的理解可能存在缺失、遗漏、误解、错位、内容不准确等情况，也可能是完善度比较好的一份描述），你需要首先找出
原始描述中的错误、遗漏或误解等情况，区分判断其完善程度、准确度和质量高低，并综合这些信息，从优化提升的视角，构建更加完整、准确、流畅的新图片描述。

- 对于原始描述中理解得比较好的内容部分，你需要完整地保留
- 对于错误、遗漏或误解的，你可以试试延续理解得比较好那部分的思路再仔细观察图片本身，丰富、完善从图片中理解捕捉到的信息量，并犀利地深挖其更深刻的内涵；你也可以
试着进一步深入图片的整体版面关系和区域划分、将图片内容分层次进行解读、通过这些内在的关联更高质量地找出和理解原始描述中出错或遗漏的位置和可能原因，通过这些宏观
或微观或二者结合的技巧和视角加强理解

请你仔细观察、理解、思考，基于已有的原始图片描述，纠正和新增信息，完善提升理解的广度和深度，完成合适比例的增删改（对于原始描述完善度、准确度和质量，能够达到八成以上的，增删改比例不超过20%；介于五成和八成之间的，增删改比例不超过40%，低于五成的，最好完整思考后重新写一份）
请你直接返回更新后的完整描述，保持描述的专业性和连贯性，确保整合所有正确的宏观结构、分层深度、微观细节等。
不要包含任何判断、解释或分析过程！用中文描述，控制在1000字以内。"""

image_merge_summary_prompt = """请分析以下两段文本以及图片本身，并生成一个更新后的图片识别理解描述：

1. 原始图片描述：
{old_content}

2. 用户提问和回答（可能包含纠正或新增信息）：
{merge_content}

请首先查看、理解图片内容，并基于以上信息（请你优先信任上面问题的回答内容，这可能是比你更强的模型进行的回复，除非你能以很大概率下结论其回答中有错误成分），
找出原始描述中的错误、遗漏或误解等，并综合这些信息，创建一个完整、准确、流畅的新图片描述。

你可以试着分析图片的整体版面关系和区域划分、将图片内容分层次进行解读、通过这些内在的关联更高质量地推测和理解你最初出错或遗漏的位置等等，通过这些技巧和视角加强理解

请你虚心理解，学习接受纠正和新增信息，完成合适比例的增删改，但不超过20%。
直接返回更新后的完整描述，保持描述的专业性和连贯性，确保整合所有正确的细节。不要包含任何解释或分析过程。"""

# def encode_image(image_path):
#     with open(image_path, "rb") as image_file:
#         return base64.b64encode(image_file.read()).decode('utf-8')


def encode_image(image_path, max_size_mb=2, target_size_mb=1):
    """
    编码图片为base64，如果图片大小超过2MB会自动压缩到1MB以内
    优化版本：显著提升性能
    """
    # 检查文件大小
    file_size_mb = os.path.getsize(image_path) / (1024 * 1024)

    # 如果文件小于限制，直接编码
    if file_size_mb <= max_size_mb:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    print(f"图片文件 {image_path} 大小 {file_size_mb:.2f}MB 超过{max_size_mb}MB限制，正在压缩...")

    # 读取图片（处理中文路径）
    with open(image_path, 'rb') as f:
        file_bytes = f.read()

    nparr = np.frombuffer(file_bytes, np.uint8)
    img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_cv2 is None:
        raise Exception("无法读取图片文件")

    # 转换为RGB格式（cv2使用BGR）
    img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)

    # 目标大小（字节）
    target_size = target_size_mb * 1024 * 1024

    # 快速估算需要的缩放比例
    # 基于经验：JPEG压缩后大约是原始像素数据的1/10到1/20
    height, width = img_rgb.shape[:2]
    estimated_compression_ratio = 15  # 经验值
    current_pixels = width * height
    estimated_size = current_pixels * 3 / estimated_compression_ratio

    # 如果预估大小超过目标，先缩放图片
    if estimated_size > target_size:
        scale_factor = (target_size / estimated_size) ** 0.5
        new_width = max(int(width * scale_factor), 800)  # 最小800像素
        new_height = max(int(height * scale_factor), 800)

        # 使用cv2快速缩放
        img_rgb = cv2.resize(img_rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
        print(f"缩放图片: {width}x{height} -> {new_width}x{new_height}")

    # 转换为PIL Image（直接从numpy数组，避免文件I/O）
    pil_img = Image.fromarray(img_rgb)

    # 使用自适应质量压缩
    # 先用较高质量测试大小
    test_quality = 85
    buffer = io.BytesIO()
    pil_img.save(buffer, format='JPEG', quality=test_quality, optimize=True)
    test_size = buffer.tell()

    # 根据测试结果快速估算需要的质量
    if test_size <= target_size:
        # 如果85%质量就满足，直接返回
        compressed_data = buffer.getvalue()
    else:
        # 估算需要的质量（基于文件大小与质量的近似线性关系）
        size_ratio = target_size / test_size
        estimated_quality = int(test_quality * size_ratio * 0.9)  # 0.9是安全系数
        estimated_quality = max(30, min(85, estimated_quality))

        # 使用估算的质量进行压缩
        buffer = io.BytesIO()
        pil_img.save(buffer, format='JPEG', quality=estimated_quality, optimize=True)
        compressed_data = buffer.getvalue()

        # 如果还是太大，进一步降低质量
        if len(compressed_data) > target_size:
            # 简单的逐步降低质量，而不是二分查找
            for q in range(estimated_quality - 5, 30, -5):
                buffer = io.BytesIO()
                pil_img.save(buffer, format='JPEG', quality=q, optimize=True)
                compressed_data = buffer.getvalue()
                if len(compressed_data) <= target_size:
                    break

        # 如果通过质量调整仍无法满足，需要进一步缩小图片
        if len(compressed_data) > target_size:
            # 计算需要的额外缩放
            extra_scale = (target_size / len(compressed_data)) ** 0.5 * 0.9
            current_width, current_height = pil_img.size
            new_width = max(int(current_width * extra_scale), 600)
            new_height = max(int(current_height * extra_scale), 600)

            # 缩放并重新压缩
            pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 使用中等质量
            buffer = io.BytesIO()
            pil_img.save(buffer, format='JPEG', quality=70, optimize=True)
            compressed_data = buffer.getvalue()

    compressed_size_mb = len(compressed_data) / 1024 / 1024
    print(f"压缩完成: {file_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB")

    return base64.b64encode(compressed_data).decode('utf-8')


def summarize_image(image_path, pixel_limit=12000000, user_name="default_user"):
    """
        图片理解增强流程：
        1. 大模型先生成简要描述（版面/布局/DMT层次）
        2. 小模型基于描述给出深度建议
        3. 大模型根据建议生成最终高质量理解
    """
    # 打开图片
    image = Image.open(image_path)
    # 获取图片尺寸
    width, height = image.size

    # if width * height > pixel_limit:
    #     print("[summarize_image]: 处理复杂大图")
    #     return image_2_summary_enhance(image_path)
    # else:
    #     print("[summarize_image]: 处理普通图片")
    #     return image_2_summary_bypath(image_path)

    # 第一步：大模型生成简要描述
    print("[summarize_image]: 第一步 - 生成简要描述")
    if width * height > pixel_limit:
        initial_description = image_2_summary_initial(image_path, use_enhance=True)
    else:
        initial_description = image_2_summary_initial(image_path, use_enhance=True)

    # 第二步：小模型基于描述给出深度建议
    print("[summarize_image]: 第二步 - 获取小模型深度建议")
    depth_suggestion = get_image_depth_suggestion(initial_description, user_name)

    # 第三步：大模型根据建议生成最终高质量理解
    print("[summarize_image]: 第三步 - 生成最终高质量理解")
    if width * height > pixel_limit:
        return image_2_summary_final(image_path, initial_description, depth_suggestion, use_enhance=True)
    else:
        return image_2_summary_final(image_path, initial_description, depth_suggestion, use_enhance=False)


def image_2_summary_bypath(image_path):
    base64_image = encode_image(image_path)
    gpt_vision = chat_gpt_model.get_model()
    # vision_model = ChatOpenAI(
    #     temperature=0,
    #     openai_api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
    #     openai_api_base='https://dashscope.aliyuncs.com/compatible-mode/v1',
    #     default_headers={"x-foo": "true"},
    #     # openai_api_base=base_url,
    #     # streaming=True,
    #     model_name="qwen-vl-max-latest",
    #     max_tokens=2048)

    # print(gpt_vision)
    messages = [HumanMessage(content=[
        {
            "type": "text",
            "text": """请对图片进行专业多层次分析解读，图片可能有不同类型，但广义上都可以归为下面的【学习类文档】，因为图片都是需要学习、认知和理解的，
                    所以请你从此类型视角开始思考，主要是理解图片要分层的思路，再进一步细化落实到图片所属的具体类别。

                    【学习类文档分析】(作业/试卷/笔记等)
                    如果图片含有作业、试卷、笔记等纸质版面，你的表述中必须包含：【理解和陈述】、【评价和建议】这两对，一共四个要素，其中理解是整体性感知，
                    陈述是对主体中具体内容或文字的识别（类似OCR的文字识别），这一对很基础！至少要占你篇幅的70%以上；评价是对于其书写规范性、位置合理性
                    等的评述，建议是对书写者改进的建议等，这一对是拔高内容，占20%到30%左右，作为辅助。
                    请你一定注意不可以过于笼统！例如不能只说“手写层字迹工整，排版规范”，你必须要说具体写了什么内容，主题是什么、有标题吗、与哪些标注关联
                    之类的具体内容，你需要尽量表述全面、完整，少遗漏信息！如果图片较为复杂，你也需要尽可能地识别，并一定要说具体写了什么文字，这很重要！
                    方法上，请采用多层次分析法对此类图片进行专业解读（这里涉及的点都要包含）：
                    1. 版面结构：识别主要区域、是否有子版面划分等，分析空间关系与逻辑连接
                    2. 多层内容依次解读：
                       - 底图层：图片本身的整体感知性理解，即版面内一些显眼突出的形状，你需要通过一定意象感，做一做感知，例如“xx像是xx”这类的描述
                       - 印刷层：教材/试题等印刷，具体印了哪些文字
                       - 涂鸦层：批注符号、圈点、下划线等标记（涂鸦勾画等其实是思考过程的体现，也很重要，不可以忽视这层！），具体涂鸦了什么
                       - 手写层：有特点的、较为正式的手写字迹，务必涉及具体写了什么（即使认不清也要试着认）
                    3. 层间关联：分析各层次间的对应关系，特别关注手写、涂鸦、印刷内容的对应及关联关系
                    4. 另外注意：
                       - 对图中一些较为特别的点加以强调，例如图中如果有明确的【标题】（一般在版面最上方居中的位置，且黑色加粗）或【主题】，你一定要在最开头就把它识别出来并进行陈述！
                       - 涂鸦和手写层虽然都是书写，也有关联性，但你描述时需要分开（格式上分开，内容上要找关联），涂鸦层比较随意，偏向思考过程；手写层比较正式，偏向作答过程
                       - 你需要说明作业/试卷/笔记等学习类图片最可能是针对哪些对象的，如什么阶段（小学初中高中大学等）、什么年级等等
                       - 如果没有涂鸦笔迹，也需要简单说明一下

                    另外如果是原理图、绘画或其他类型的非明显分层图片，也可以用多层次注意的类似思路来深入理解
                    请直接给出自然、完整的图片描述，用中文描述，控制在1000字以内。
                    """
            # "text": """如果图片是作业、试卷、笔记等，请采用多层次分析法对此图片进行专业解读：
            #         【版面结构】识别主要区域、是否有子版面等，分析空间关系与逻辑连接
            #         【多层内容】依次解读：
            #         1.底图层（图片本身的整体性、局域性理解识别分析）
            #         2.是否有印刷层、涂鸦层（批注符号、圈点、下划线等标记）、有特点的手写字迹等（如果没有，请做出简单说明；如果有要特别关注手写与涂鸦、印刷内容的对应关系）
            #         如果是原理图或绘画等非明显分层图片，也可以用多层次注意的类似思路来深入理解
            #         请直接给出自然、完整的图片描述，无需列出分析过程，用中文描述，控制在1000字以内。
            #
            #                     【图表/信息图分析】
            #                     1. 结构解析：图表类型、主要组成部分、视觉层级
            #                     2. 数据呈现：关键数值、趋势、对比关系、异常点
            #                     3. 视觉元素：色彩运用、标注方式、图例说明
            #                     4. 信息传达：核心信息、数据故事、设计有效性
            #
            #                     【原理图/技术图解析】
            #                     1. 功能结构：整体框架、组件关系、工作流程
            #                     2. 技术要素：核心概念、关键参数、运行原理
            #                     3. 标注系统：符号含义、尺寸标注、专业术语
            #                     4. 实用价值：应用场景、教学目的、潜在问题
            #
            #                     【绘画/艺术作品分析】
            #                     1. 形式元素：构图、线条、色彩、质感、空间处理
            #                     2. 内容表达：主题、情感、象征、叙事性
            #                     3. 技法应用：绘画风格、技术手段、创作特点
            #                     4. 艺术价值：审美效果、创新点、文化背景
            #
            #                     【其他类型图片】(照片/截图/海报等)
            #                     1. 视觉内容：主体对象、环境背景、关键细节
            #                     2. 构成分析：空间安排、视觉重点、层次关系
            #                     3. 情境解读：时间场景、行为状态、情感氛围
            #                     4. 意图评估：拍摄/创建目的、传达信息、预期效果"""
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        }
    ])]
    # content = vision_model.invoke(messages).content
    content = gpt_vision.invoke(messages).content
    print(content)
    return content


def image_2_summary(image):
    gpt_vision = chat_gpt_model.get_model()
    # vision_model = ChatOpenAI(
    #     temperature=0,
    #     openai_api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
    #     openai_api_base='https://dashscope.aliyuncs.com/compatible-mode/v1',
    #     default_headers={"x-foo": "true"},
    #     # openai_api_base=base_url,
    #     # streaming=True,
    #     model_name="qwen-vl-max-latest",
    #     max_tokens=2048)

    # print(gpt_vision)
    messages = [HumanMessage(content=[
        {
            "type": "text",
            "text": """请对图片进行专业多层次分析解读，图片可能有不同类型，但广义上都可以归为下面的【学习类文档】，因为图片都是需要学习、认知和理解的，
                    所以请你从此类型视角开始思考，主要是理解图片要分层的思路，再进一步细化落实到图片所属的具体类别。

                    【学习类文档分析】(作业/试卷/笔记等)
                    如果图片含有作业、试卷、笔记等纸质版面，你的表述中必须包含：【理解和陈述】、【评价和建议】这两对，一共四个要素，其中理解是整体性感知，
                    陈述是对主体中具体内容或文字的识别（类似OCR的文字识别），这一对很基础！至少要占你篇幅的70%以上；评价是对于其书写规范性、位置合理性
                    等的评述，建议是对书写者改进的建议等，这一对是拔高内容，占20%到30%左右，作为辅助。
                    请你一定注意不可以过于笼统！例如不能只说“手写层字迹工整，排版规范”，你必须要说具体写了什么内容，主题是什么、有标题吗、与哪些标注关联
                    之类的具体内容，你需要尽量表述全面、完整，少遗漏信息！如果图片较为复杂，你也需要尽可能地识别，并一定要说具体写了什么文字，这很重要！
                    方法上，请采用多层次分析法对此类图片进行专业解读（这里涉及的点都要包含）：
                    1. 版面结构：识别主要区域、是否有子版面划分等，分析空间关系与逻辑连接
                    2. 多层内容依次解读：
                       - 底图层：图片本身的整体感知性理解，即版面内一些显眼突出的形状，你需要通过一定意象感，做一做感知，例如“xx像是xx”这类的描述
                       - 印刷层：教材/试题等印刷，具体印了哪些文字
                       - 涂鸦层：批注符号、圈点、下划线等标记（涂鸦勾画等其实是思考过程的体现，也很重要，不可以忽视这层！），具体涂鸦了什么
                       - 手写层：有特点的、较为正式的手写字迹，务必涉及具体写了什么（即使认不清也要试着认）
                    3. 层间关联：分析各层次间的对应关系，特别关注手写、涂鸦、印刷内容的对应及关联关系
                    4. 另外注意：
                       - 对图中一些较为特别的点加以强调，例如图中如果有明确的【标题】（一般在版面最上方居中的位置，且黑色加粗）或【主题】，你一定要在最开头就把它识别出来并进行陈述！
                       - 涂鸦和手写层虽然都是书写，也有关联性，但你描述时需要分开（格式上分开，内容上要找关联），涂鸦层比较随意，偏向思考过程；手写层比较正式，偏向作答过程
                       - 你需要说明作业/试卷/笔记等学习类图片最可能是针对哪些对象的，如什么阶段（小学初中高中大学等）、什么年级等等
                       - 如果没有涂鸦笔迹，也需要简单说明一下

                    另外如果是原理图、绘画或其他类型的非明显分层图片，也可以用多层次注意的类似思路来深入理解
                    请直接给出自然、完整的图片描述，用中文描述，控制在1000字以内。
                    """
            # "text": """如果图片是作业、试卷、笔记等，请采用多层次分析法对此图片进行专业解读：
            #         【版面结构】识别主要区域、是否有子版面等，分析空间关系与逻辑连接
            #         【多层内容】依次解读：
            #         1.底图层（图片本身的整体性、局域性理解识别分析）
            #         2.是否有印刷层、涂鸦层（批注符号、圈点、下划线等标记）、有特点的手写字迹等（如果没有，请做出简单说明；如果有要特别关注手写与涂鸦、印刷内容的对应关系）
            #         如果是原理图或绘画等非明显分层图片，也可以用多层次注意的类似思路来深入理解
            #         请直接给出自然、完整的图片描述，无需列出分析过程，用中文描述，控制在1000字以内。
            #
            #                     【图表/信息图分析】
            #                     1. 结构解析：图表类型、主要组成部分、视觉层级
            #                     2. 数据呈现：关键数值、趋势、对比关系、异常点
            #                     3. 视觉元素：色彩运用、标注方式、图例说明
            #                     4. 信息传达：核心信息、数据故事、设计有效性
            #
            #                     【原理图/技术图解析】
            #                     1. 功能结构：整体框架、组件关系、工作流程
            #                     2. 技术要素：核心概念、关键参数、运行原理
            #                     3. 标注系统：符号含义、尺寸标注、专业术语
            #                     4. 实用价值：应用场景、教学目的、潜在问题
            #
            #                     【绘画/艺术作品分析】
            #                     1. 形式元素：构图、线条、色彩、质感、空间处理
            #                     2. 内容表达：主题、情感、象征、叙事性
            #                     3. 技法应用：绘画风格、技术手段、创作特点
            #                     4. 艺术价值：审美效果、创新点、文化背景
            #
            #                     【其他类型图片】(照片/截图/海报等)
            #                     1. 视觉内容：主体对象、环境背景、关键细节
            #                     2. 构成分析：空间安排、视觉重点、层次关系
            #                     3. 情境解读：时间场景、行为状态、情感氛围
            #                     4. 意图评估：拍摄/创建目的、传达信息、预期效果"""
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image}"
            }
        }
    ])]
    # content = vision_model.invoke(messages).content
    content = gpt_vision.invoke(messages).content
    print(content)
    return content


def image_2_summary_enhance(image_path):
    user_prompt = """请对图片进行专业多层次分析解读，图片可能有不同类型，但广义上都可以归为下面的【学习类文档】，因为图片都是需要学习、认知和理解的，
所以请你从此类型视角开始思考，主要是理解图片要分层的思路，再进一步细化落实到图片所属的具体类别。

【学习类文档分析】(作业/试卷/笔记等)
如果图片含有作业、试卷、笔记等纸质版面，你的表述中必须包含：【理解和陈述】、【评价和建议】这两对，一共四个要素，其中理解是整体性感知，
陈述是对主体中具体内容或文字的识别（类似OCR的文字识别），这一对很基础！至少要占你篇幅的70%以上；评价是对于其书写规范性、位置合理性
等的评述，建议是对书写者改进的建议等，这一对是拔高内容，占20%到30%左右，作为辅助。
请你一定注意不可以过于笼统！例如不能只说“手写层字迹工整，排版规范”，你必须要说具体写了什么内容，主题是什么、有标题吗、与哪些标注关联
之类的具体内容，你需要尽量表述全面、完整，少遗漏信息！如果图片较为复杂，你也需要尽可能地识别，并一定要说具体写了什么文字，这很重要！
方法上，请采用多层次分析法对此类图片进行专业解读（这里涉及的点都要包含）：
1. 版面结构：识别主要区域、是否有子版面划分等，分析空间关系与逻辑连接
2. 多层内容依次解读：
    - 底图层：图片本身的整体感知性理解，即版面内一些显眼突出的形状，你需要通过一定意象感，做一做感知，例如“xx像是xx”这类的描述
    - 印刷层：教材/试题等印刷，具体印了哪些文字
    - 涂鸦层：批注符号、圈点、下划线等标记（涂鸦勾画等其实是思考过程的体现，也很重要，不可以忽视这层！），具体涂鸦了什么
    - 手写层：有特点的、较为正式的手写字迹，务必涉及具体写了什么（即使认不清也要试着认）
3. 层间关联：分析各层次间的对应关系，特别关注手写、涂鸦、印刷内容的对应及关联关系
4. 另外注意：
    - 对图中一些较为特别的点加以强调，例如图中如果有明确的【标题】（一般在版面最上方居中的位置，且黑色加粗）或【主题】，你一定要在最开头就把它识别出来并进行陈述！
    - 涂鸦和手写层虽然都是书写，也有关联性，但你描述时需要分开（格式上分开，内容上要找关联），涂鸦层比较随意，偏向思考过程；手写层比较正式，偏向作答过程
    - 你需要说明作业/试卷/笔记等学习类图片最可能是针对哪些对象的，如什么阶段（小学初中高中大学等）、什么年级等等
    - 如果没有涂鸦笔迹，也需要简单说明一下

另外如果是原理图、绘画或其他类型的非明显分层图片，也可以用多层次注意的类似思路来深入理解
请直接给出自然、完整的图片描述，用中文描述，控制在1000字以内。
"""
    base64_image = get_image_base64_with_mime(image_path=image_path, max_size_mb=5)
    messages = [{"role": "system",
                    "content": [{"text": "You are a helpful assistant."}]},
                    {'role':'user',
                    'content': [{"image": base64_image},
                                {'text': user_prompt}]}]
    response = MultiModalConversation.call(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
        api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        model='qwen-vl-max-latest',  # 此处以qwen-vl-max-latest为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/models
        messages=messages,
        vl_high_resolution_images=True
    )
    content = response["output"]["choices"][0]["message"].content[0]["text"]
    print(content)
    return content


def image_retry_summary(old_content, base64_image):
    # 构建提示词
    prompt = image_retry_summary_prompt.format(old_content=old_content)

    # # 构建提示词
    # prompt = f"""请基于原始图片描述和图片本身，生成更准确完整的图片描述：
    #
    #     原始图片描述：
    #     {old_content}
    #
    #     【评估与分析任务】
    #     1. 识别图片类型：学习类文档(作业/试卷/笔记)、图表/信息图、原理图/技术图、绘画/艺术作品、其他类型
    #     2. 评估原始描述质量：
    #        - 完整性：是否涵盖图片所有关键要素和区域
    #        - 准确性：描述与实际图片内容的符合度
    #        - 深度：对图片层次和细节的解读深度
    #        - 结构性：描述的逻辑组织和条理性
    #     3. 根据评估结果量化原始描述质量（10分制）
    #
    #     【更新策略】
    #     • 高质量描述(8-10分)：保留80%以上内容，微调补充细节，提升精准度
    #     • 中等质量描述(5-7分)：保留60%左右核心正确内容，重构逻辑，补充遗漏要素
    #     • 低质量描述(0-4分)：重新构建完整描述，仅参考原描述中确认正确的点
    #
    #     【关注要点】
    #     • 学习类文档：版面结构、内容层次(底图/印刷/涂鸦/手写)、层间关联
    #     • 图表/信息图：类型结构、数据关系、视觉元素、核心信息
    #     • 原理图/技术图：功能结构、技术要素、标注系统、实用价值
    #     • 绘画/艺术作品：形式元素、内容表达、技法应用、艺术价值
    #     • 其他类型：视觉内容、构成分析、情境解读、意图评估
    #
    #     请直接返回更新后的完整描述，保持专业性和连贯性，整合所有正确的结构、层次和细节。不包含分析过程，用中文描述，控制在1000字以内。"""

    # 调用支持图片的GPT4o API函数
    new_content = gpt4_api.make_gpt4o_image_text_requests(prompt, base64_image)

    return new_content


def image_merge_summary(old_content, merge_content, base64_image):
    # 构建提示词
    prompt = image_merge_summary_prompt.format(old_content=old_content, merge_content=merge_content)

    # 调用支持图片的GPT4o API函数
    new_content = gpt4_api.make_gpt4o_image_text_requests(prompt, base64_image)

    return new_content


def imageSum_2_HLScore(content, base64_image):
    # 构建提示词
    prompt = f"""请分析以下图片描述文本以及图片本身，对这份图片识别理解描述文本的质量进行得分评估及改进建议：

    【图片描述文本】：
    {content}
    
    首先注意，下面的红蓝融合不仅是军事政工领域，也适用于教育、学习、认知、研究、时事、科学等方面，是广义的红蓝融合。
    如果图片描述文本不涉及下面的红蓝融合理念第一层，但与前面说的认知、教育、群组学习、科学研究等有关，请你适当依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分，对于每一层的评判不必太死板，随图片场景、类型不同可以适当变通）、是否有利于认知水平提升、是否有利于实现目标等，综合给分！

    请根据图片类型进行针对性评估：
   【学习类图片】(作业/试卷/笔记等)：对版面区域划分的识别是否正确、印刷体与手写体区分是否清晰、对涂鸦勾画的识别与理解程度、对正式书写内容的理解深度、对不同部分关联性的分析是否到位。
   【图表/信息图】：对坐标轴、图例、数据点的识别是否准确，对趋势与关联性的解读是否深入，对背后概念与意义的阐释是否清晰。
   【原理图/技术图】：对各组件功能识别的准确性，对流程与连接关系解读的完整性，对技术原理理解的深度，对图中专业术语解释的准确性。
   【绘画/艺术作品图】：对构图、色彩、风格的识别与描述，对象征意义与情感表达的解读，对艺术技法与背景的理解，对作品主题的把握。
   【其他类型图片】(照片/截图/海报等)：对主体的识别准确性，对空间关系与环境的描述完整性，对图片意图的理解，对隐含信息的发掘。

    你可以试着分析图片的整体版面关系和区域特征、将图片内容分层次进行解读、通过这些内在的关联更高质量地评判前面图片描述文本的质量。
    然后你需要根据原图内容，对上面的图片描述文本质量进行红蓝融合度评估打分，红蓝融合度打分规则如下:
    
    1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
    第一层：人文<红>和科技<蓝>的融合（如仿人或为人的提升服务与新兴信息技术的有机结合）；
    第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
    第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中带领者向下进行示范牵引、跟随者执行及发挥创造，或其他协作形式，在教育、健康、研究中也有变通的适用）；
    第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务）；
    第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，来筛选出优质内容并扩散共生）
    
    2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
    （2）如果图片描述文本能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
    例如：图片描述能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），则不能达到3分，得2.5分
    补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
    注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
    （3）由于不能达到红蓝融合（红蓝分离）的情况普遍存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，图片描述文本若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
    小数分值参考标准：图片描述文本体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8
    （4）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
    具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
    （5）对图片描述文本判分的额外考量因素：
     - 描述对图片版面布局理解的准确性：+0.5分
     - 描述对图片各元素间关系理解的深度：+0.5分
     - 描述对图片特定类型特征的把握程度：+0.5分
     - 描述的针对性和专业性与图片类型匹配度：+0.5分
    
    3.注意，你只需且必须要按"分值_颜色_理由和改进建议"格式输出！
    分值方面，是你综合以上规则对给出的图片描述文本做出的打分；
    颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图片描述文本过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
    理由和改进建议方面，先用<80字左右>描述你给出分值和颜色的理由，依据包括：
    （1）主要：图片描述文本的内容是否具有针对性，对图片类型及层次特征的识别与理解程度如何，是否把握到了该类型图片的关键元素和内在关联关系；
    （2）次要：是否体现对应的红蓝融合五层理念，为什么；
    给出理由后，根据理由，针对上面的图片描述文本涉及到的不足点（不超过2到3个，选最重要、明显的不足点），分别提出<50字左右>的改进或矫正策略和建议，注意你给出改进建议一定要和原图本身及图片描述文本的主要、关键内容高度相关，给出高可执行性的改进建议，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。
    建议一定要具体，有真实行动上能够立即执行的清晰明确的指导，而不是泛泛而谈。格式模板为"建议xx不足点：xxx；建议xx不足点：xxx；......"。
    
    整体格式例如：0.4分_蓝色_具体理由和建议
    2.5分_紫色_具体理由和建议
    4.0分_紫色_具体理由和建议
    ...（其他分值，但一定要按以上要求，且严格按照此格式输出，分值范围为0.0到5.0之间）"""

    # 调用支持图片的GPT4o API函数
    # new_content = gpt4_api.make_gpt4o_image_text_requests(prompt, base64_image)
    new_content = claude_api.make_claude_image_text_requests(prompt, base64_image)
    # 使用Qwen-VL模型进行图片分析和评分
    # new_content = qwen_vl_api.make_image_text_requests(prompt, base64_image)

    # 去除x.x分_x色_xxx前的内容
    match = re.search(r'(\d+\.?\d*分_\w+色_.*)', new_content)
    if match:
        new_content = match.group(1)
    # 取前char_limit个字符，去除*和\n，以避免前端解析不出卡标分数（NAN）
    char_limit = 20
    prefix = new_content[:char_limit]
    suffix = new_content[char_limit:]
    # 去掉前缀中的*和\n，合并返回
    cleaned_prefix = prefix.replace('*', '').replace('\n', '')
    new_content = cleaned_prefix + suffix
    print(f"[imageSum_2_HLScore]: {new_content}")
    return new_content


def muExtractImages(file_name, usr_name="", realName="", task_id="", real_time_update=False):
    from zym.models import UserNotebook
    import fitz  # 确保导入
    import os
    import json

    pdf = file_name
    try:
        doc = fitz.open(pdf)
    except Exception as e:
        print(f"打开PDF文件失败: {e}")
        return [], []

    out_file_dir = pdf[:-4] + "_image" + "/"
    if not os.path.exists(out_file_dir):
        os.makedirs(out_file_dir)

    # 🔥 准备写入PreImageOrigin_pdf.md的路径（对于非扫描件PDF）
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

    # xref见解析似乎是行数
    # 它要相关的文档，就把和它页数相近地拿过去吧
    docs_out = []
    base_64_out = []
    img_count = 0
    begin_time = time.time()
    for page_num, page in enumerate(doc):
        processed_rects = [] # 用于存储每页已处理图片的区域，避免重复
        # --- 1. 提取常规位图 (Raster Images) ---
        try:
            image_list = page.get_images(full=True)
            for _, img in enumerate(image_list):
                xref = img[0]
                img_rect = page.get_image_bbox(img)

                # 检查是否与已处理区域重叠
                is_processed = False
                for r in processed_rects:
                    if r.intersects(img_rect):
                        is_processed = True
                        break
                if is_processed:
                    continue

                # 智能过滤
                page_height = page.rect.height
                # 过滤条件1: 尺寸太小
                if img_rect.width < 75 or img_rect.height < 75:
                    continue
                # 过滤条件2: 位于页眉或页脚区域 (顶部或底部10%)
                if img_rect.y1 < page_height * 0.1 or img_rect.y0 > page_height * 0.9:
                    continue

                img_data = doc.extract_image(xref)
                # 过滤条件3: 图片数据本身太小 (小于5KB)
                if len(img_data["image"]) < 5 * 1024:
                    continue

                img_count += 1
                image_filename = os.path.join(out_file_dir, f"{img_count}.{img_data['ext']}")
                print("pdf处理位图:", img_count, image_filename)
                with open(image_filename, 'wb') as f:
                    f.write(img_data["image"])

                processed_rects.append(img_rect) # 记录已处理区域
                # ... (后续处理逻辑) ...
                base64_image = encode_image(image_filename)
                base_64_out.append(base64_image)
                content = summarize_image(image_filename, user_name=usr_name)
                content = out_file_dir + "文件中的一张图片，内容为" + content

                # 🔥 提取图片所在页面的文本内容（前后各100字）
                context_before = ""
                context_after = ""
                try:
                    page_text = page.get_text()
                    # 找到图片在页面文本中的大致位置（通过图片的y坐标）
                    img_y_center = (img_rect.y0 + img_rect.y1) / 2
                    # 简单估算：假设文本按行排列，每行高度约20像素
                    estimated_line = int(img_y_center / 20)
                    lines = page_text.split('\n')
                    if estimated_line < len(lines):
                        # 提取图片位置前后的文本
                        before_lines = lines[max(0, estimated_line - 5):estimated_line]
                        after_lines = lines[estimated_line:min(len(lines), estimated_line + 5)]
                        context_before = ' '.join(before_lines)[-100:] if before_lines else ""
                        context_after = ' '.join(after_lines)[:100] if after_lines else ""
                except Exception as e:
                    print(f"[图片上下文提取] 提取第 {img_count} 张图片上下文失败: {e}")

                # 🔥 写入PreImageOrigin_pdf.md（每分析完一张图片就写入一次）
                if pre_image_origin_path:
                    try:
                        with open(pre_image_origin_path, 'a', encoding='utf-8') as f:
                            f.write(f"## 图片 {img_count}\n\n")
                            f.write(f"**页码**：第 {page_num + 1} 页\n\n")
                            if context_before:
                                f.write(f"**前文（100字）**：{context_before}\n\n")
                            if context_after:
                                f.write(f"**后文（100字）**：{context_after}\n\n")
                            f.write(f"**图片分析结果**：\n{content}\n\n")
                            f.write("---\n\n")
                        print(f"[图片分析结果写入] 第 {img_count} 张图片的分析结果已写入: {pre_image_origin_path}")
                    except Exception as e:
                        print(f"[图片分析结果写入] 写入第 {img_count} 张图片分析结果失败: {e}")

                # ... (保存数据库和创建Document对象的代码保持不变) ...
                if usr_name != "" and realName != "":
                    # ... (HLScore 和数据库保存逻辑) ...
                    # HLScore = imageSum_2_HLScore(content, base64_image)
                    # book_name = usr_name[len(realName) + 1:]
                    # notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                    # # 读取现有的JSON数据
                    # try:
                    #     existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
                    # except json.JSONDecodeError:
                    #     existing_data = {}
                    # # 更新JSON数据 - HLScore会被正确编码，处理特殊字符，避免HLScore中有""或者:之类符号
                    # existing_data[f"{os.path.basename(file_name)}-{img_count}"] = HLScore
                    # notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
                    # notebook.save()
                    # 异步保存HLScore到数据库
                    save_hlscore_to_db_async(usr_name, realName, file_name, img_count, content, base64_image)

                # docs_out.append(Document(page_content=content, metadata={...})) # 保持原有metadata结构
                doc_item = Document(
                    page_content=content,
                    metadata=dict(
                        {
                            "source": pdf,  # type: ignore[attr-defined]
                            "file_path": image_filename,  # type: ignore[attr-defined]
                            "page": page.number,
                            "total_pages": len(doc),
                            "type": "image",
                            "seq": img_count,
                        },
                        **{
                            k: doc.metadata[k]
                            for k in doc.metadata
                            if type(doc.metadata[k]) in [str, int]
                        },
                    ),
                )
                docs_out.append(doc_item)

                # 实时更新到global_var
                if real_time_update and usr_name != "":
                    try:
                        # 获取现有数据
                        existing_images = global_var.get_user_image(usr_name, os.path.basename(file_name)) or []
                        existing_docs = global_var.get_user_split(usr_name, os.path.basename(file_name)) or []

                        # 添加新数据
                        existing_images.append(base64_image)
                        existing_docs.append(doc_item)

                        # 更新到global_var
                        global_var.set_user_image(usr_name, os.path.basename(file_name), existing_images)
                        global_var.set_user_split(usr_name, os.path.basename(file_name), existing_docs)

                        print(f"[实时更新] 第 {img_count} 张图片已更新到global_var")
                    except Exception as e:
                        print(f"[实时更新] 更新第 {img_count} 张图片时出错: {e}")

        except Exception as e:
            print(f"处理位图时发生错误: {e}")

        # --- 2. 提取矢量图 (Vector Graphics) ---
        try:
            drawings = page.get_drawings()
            for path in drawings:
                # 过滤小的或线状的矢量图形
                if path['rect'].width < 75 or path['rect'].height < 75 or min(path['rect'].width, path['rect'].height) < 20:
                    continue
                # 检查是否与已处理区域重叠
                is_processed = False
                for r in processed_rects:
                    if r.intersects(path['rect']):
                        is_processed = True
                        break
                if is_processed:
                    continue

                # 渲染矢量图区域为图片
                pix = page.get_pixmap(clip=path['rect'], dpi=200) # 使用更高dpi以保证清晰度
                img_count += 1
                image_filename = os.path.join(out_file_dir, f"{img_count}.png")
                print("pdf处理矢量图:", img_count, image_filename)
                pix.save(image_filename)

                processed_rects.append(path['rect']) # 记录已处理区域
                # ... (后续处理逻辑) ...
                base64_image = encode_image(image_filename)
                base_64_out.append(base64_image)
                content = summarize_image(image_filename, user_name=usr_name)
                content = out_file_dir + "文件中的一张图片，内容为" + content

                # 🔥 提取图片所在页面的文本内容（前后各100字）
                context_before = ""
                context_after = ""
                try:
                    page_text = page.get_text()
                    # 找到图片在页面文本中的大致位置（通过图片的y坐标）
                    path_y_center = (path['rect'].y0 + path['rect'].y1) / 2
                    # 简单估算：假设文本按行排列，每行高度约20像素
                    estimated_line = int(path_y_center / 20)
                    lines = page_text.split('\n')
                    if estimated_line < len(lines):
                        # 提取图片位置前后的文本
                        before_lines = lines[max(0, estimated_line - 5):estimated_line]
                        after_lines = lines[estimated_line:min(len(lines), estimated_line + 5)]
                        context_before = ' '.join(before_lines)[-100:] if before_lines else ""
                        context_after = ' '.join(after_lines)[:100] if after_lines else ""
                except Exception as e:
                    print(f"[图片上下文提取] 提取第 {img_count} 张图片上下文失败: {e}")

                # 🔥 写入PreImageOrigin_pdf.md（每分析完一张图片就写入一次）
                if pre_image_origin_path:
                    try:
                        with open(pre_image_origin_path, 'a', encoding='utf-8') as f:
                            f.write(f"## 图片 {img_count}\n\n")
                            f.write(f"**页码**：第 {page_num + 1} 页\n\n")
                            if context_before:
                                f.write(f"**前文（100字）**：{context_before}\n\n")
                            if context_after:
                                f.write(f"**后文（100字）**：{context_after}\n\n")
                            f.write(f"**图片分析结果**：\n{content}\n\n")
                            f.write("---\n\n")
                        print(f"[图片分析结果写入] 第 {img_count} 张图片的分析结果已写入: {pre_image_origin_path}")
                    except Exception as e:
                        print(f"[图片分析结果写入] 写入第 {img_count} 张图片分析结果失败: {e}")

                # ... (保存数据库和创建Document对象的代码保持不变) ...
                if usr_name != "" and realName != "":
                    # ... (HLScore 和数据库保存逻辑) ...
                    # HLScore = imageSum_2_HLScore(content, base64_image)
                    # book_name = usr_name[len(realName) + 1:]
                    # notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                    # try:
                    #     existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
                    # except json.JSONDecodeError:
                    #     existing_data = {}
                    # existing_data[f"{os.path.basename(file_name)}-{img_count}"] = HLScore
                    # notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
                    # notebook.save()
                    # 异步保存HLScore到数据库
                    save_hlscore_to_db_async(usr_name, realName, file_name, img_count, content, base64_image)

                # docs_out.append(Document(page_content=content, metadata={...})) # 保持原有metadata结构
                doc_item = Document(
                    page_content=content,
                    metadata=dict(
                        {
                            "source": pdf,  # type: ignore[attr-defined]
                            "file_path": image_filename,  # type: ignore[attr-defined]
                            "page": page.number,
                            "total_pages": len(doc),
                            "type": "image",
                            "seq": img_count,
                        },
                        **{
                            k: doc.metadata[k]
                            for k in doc.metadata
                            if type(doc.metadata[k]) in [str, int]
                        },
                    ),
                )
                docs_out.append(doc_item)

                # 实时更新到global_var
                if real_time_update and usr_name != "":
                    try:
                        # 获取现有数据
                        existing_images = global_var.get_user_image(usr_name, os.path.basename(file_name)) or []
                        existing_docs = global_var.get_user_split(usr_name, os.path.basename(file_name)) or []

                        # 添加新数据
                        existing_images.append(base64_image)
                        existing_docs.append(doc_item)

                        # 更新到global_var
                        global_var.set_user_image(usr_name, os.path.basename(file_name), existing_images)
                        global_var.set_user_split(usr_name, os.path.basename(file_name), existing_docs)

                        print(f"[实时更新] 第 {img_count} 张图片已更新到global_var")
                    except Exception as e:
                        print(f"[实时更新] 更新第 {img_count} 张图片时出错: {e}")

        except Exception as e:
            print(f"处理矢量图时发生错误: {e}")

        # 更新进度
        if task_id != "":
            print("当前任务进度：", task_id, "页数：", page_num + 1, "/", len(doc), "已用时长：", time.time()-begin_time)
            # 保留旧的页数更新（兼容性）
            global_var.set_task_current_page(task_id, page_num + 1)

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

    print(f"[异步图片处理] 从数字原生PDF中提取到 {len(docs_out)} 张图片")
    return docs_out, base_64_out


def link_text(texts):
    text = ""
    for in_text in texts:
        text += in_text
        text += "\n\n"
    text += "\n"
    return text


# 废弃了
def get_random_docs(docs):
    len_docs = len(docs)
    random_num = []
    for i in range(min(3, len_docs)):
        random_num.append(random.randint(0, len_docs - 1))
    texts = []
    for i in range(min(3, len_docs)):
        texts.append(docs[random_num[i]])
    return texts


def construct_collection(user_name):
    return user_name + "_collection"


# id + text内容文本 + 字典属性，一块存在向量数据库里
def construct_ids(filepath, length):
    ids = []
    for i in range(length):
        ids.append(filepath + "_" + str(i))
    return ids


def back_file_path(file_path: str):
    final = file_path.rfind("/")
    return file_path[final + 1:]


def back_image_path(file_path: str):
    final = file_path.rfind("_")
    return file_path[:final] + ".pdf"


def construct_file_path(user_name, file_name):
    file_path = "./received_dir/"
    file_path += "user_raw_file/"
    file_path += user_name
    file_path += "/"
    file_path += file_name
    return file_path


def check_assign_dict(dict_name, str_name):
    if str_name not in dict_name:
        dict_name[str_name] = {}


def take_first(len_record):
    return len_record[0]


def take_second(len_record):
    return len_record[1]


# 这个应该是贪心，郭会朋说的
def get_Same_distance_docs(docs):
    len_doc = 0
    len_record = []
    i = 0
    for doc in docs:
        len_doc += len(doc.page_content) + 2  # 多加一个/n/n
        len_record.append([len(doc.page_content) + 2, i])
        i += 1
    # 根据总长度动态设定截取上限：≤22000 用原公式；22001~32000 用总长一半；>32000 固定 16000
    base_left = global_var.max_token_num[0] // global_var.token_per_char - global_var.left_char_for_prompt_answer
    if len_doc <= 22000:
        left_char = base_left
    elif len_doc <= 32000:
        left_char = int(len_doc / 2)
    else:
        left_char = 16000
    print(left_char)
    texts = []
    if len_doc < left_char:
        texts = docs
    else:
        len_record.sort(key=take_first)
        all_len = 0
        last_take = 0
        for len_record_i in len_record:
            all_len += len_record_i[0]
            if all_len < left_char:
                last_take += 1
            else:
                break
        print(all_len)
        len_record = len_record[:last_take]
        len_record.sort(key=take_second)
        for len_record_i in len_record:
            texts.append(docs[len_record_i[1]])
        print(len(texts))
    return texts


def chain_run(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.config
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_mixtral(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.mixtralConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_llama3(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.llama3Config
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_kimi(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.kimiConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_claude(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.claudeConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_deepseek(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.deepseekConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_dsreasoner(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.deepseekConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_Gemini(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.geminiConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


def chain_run_Qwq(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = step.invoke(
                chain_input,
                **global_var.qwqConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


async def chain_run_async(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # print(chain_input)
                # print(isinstance(chain_input, PromptValue))
                # print(datetime.now())
                # chain_input = await step.ainvoke(
                #     chain_input,
                #     **global_var.config
                # )
                chain_input = await asyncio.wait_for(
                    step.ainvoke(chain_input, **global_var.config),
                    timeout=120  # 设置超时时间为120秒
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


async def chain_run_async_Gemini(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # print(chain_input)
                # print(isinstance(chain_input, PromptValue))
                # print(datetime.now())
                chain_input = await step.ainvoke(
                    chain_input,
                    **global_var.geminiConfig
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


async def chain_run_async_Qwq(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # print(chain_input)
                # print(isinstance(chain_input, PromptValue))
                # print(datetime.now())
                chain_input = await step.ainvoke(
                    chain_input,
                    **global_var.qwqConfig
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})



async def chain_run_async_mixtral(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    for i, step in enumerate(chain.steps):
        if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
            # print(chain_input)
            # print(isinstance(chain_input, PromptValue))
            # print(datetime.now())
            chain_input = await step.ainvoke(
                chain_input,
                **global_var.mixtralConfig
            )
        else:
            # print(step.type())
            chain_input = step.invoke(
                chain_input,
            )
            # print(chain_input)
    return chain_input


async def chain_run_async_llama3(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # print(chain_input)
                # print(isinstance(chain_input, PromptValue))
                # print(datetime.now())
                # chain_input = await step.ainvoke(
                #     chain_input,
                #     **global_var.llama3Config
                # )
                # 使用 asyncio.wait_for 设置超时
                chain_input = await asyncio.wait_for(
                    step.ainvoke(chain_input, **global_var.llama3Config),
                    timeout=60  # 设置超时时间为60秒
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


async def chain_run_async_kimi(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # print(chain_input)
                # print(isinstance(chain_input, PromptValue))
                # print(datetime.now())
                # chain_input = await step.ainvoke(
                #     chain_input,
                #     **global_var.kimiConfig
                # )
                chain_input = await asyncio.wait_for(
                    step.ainvoke(chain_input, **global_var.kimiConfig),
                    timeout=60  # 设置超时时间为60秒
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


async def chain_run_async_claude(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    max_retries = 2  # 设置最大重试次数
    retry_delay = 5  # 设置重试间隔时间，单位为秒
    chain_input_backup = chain_input  # 留存副本以便越过conn Err进行第二次调用时不破坏chain_input含义（参数传入）
    for attempt in range(max_retries):
        try:
            for i, step in enumerate(chain.steps):
                # print(i)
                # print(step)
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    chain_input = await asyncio.wait_for(
                        step.ainvoke(chain_input, **global_var.claudeConfig),
                        timeout=120  # 设置超时时间为120秒
                    )
                else:
                    chain_input = step.invoke(
                        chain_input,
                    )
            return chain_input
        except Exception as e:
            print(f"尝试次数 {attempt + 1} 失败: {str(e)}")
            if attempt < max_retries - 1:
                print(f"等待 {retry_delay} 秒后重试...")
                chain_input = chain_input_backup
                time.sleep(retry_delay)  # 等待一段时间(5s)再重试
            else:
                # 达到最大重试次数后，返回出错信息
                print("重试次数2次已耗尽，操作仍失败")
                return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


async def chain_run_async_deepseek(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # 使用 asyncio.wait_for 设置超时
                chain_input = await asyncio.wait_for(
                    step.ainvoke(chain_input, **global_var.deepseekConfig),
                    timeout=60  # 设置超时时间为60秒
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


async def chain_run_async_dsreasoner(chain, chain_input, **kwargs):
    # 牛逼的bug
    # 加个逗号就会变成列表
    try:
        for i, step in enumerate(chain.steps):
            print(i)
            print(step)
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                # 使用 asyncio.wait_for 设置超时
                chain_input = await asyncio.wait_for(
                    step.ainvoke(chain_input, **global_var.deepseekConfig),
                    timeout=150  # 设置超时时间为150秒
                )
            else:
                # print(step.type())
                chain_input = step.invoke(
                    chain_input,
                )
                # print(chain_input)
        return chain_input
    except Exception as e:
        print(str(e))
        return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})


def get_seq_doc_by_name(user_name, file_names, vector_store):
    querys = []
    query = {}
    for doc_name in file_names:
        file_path = construct_file_path(user_name, doc_name)
        querys.append(file_path)
        print(file_path)
    query["source"] = {"$in": querys}
    docs = vector_store.get(where=query)
    len_docs = len(docs["ids"])
    order = []
    doc_new = []
    final_of = docs["ids"][0].rfind("_")
    for i in range(len_docs):
        seq = docs["ids"][i][final_of + 1:]
        seq = int(seq)
        order.append([seq, i])
    order.sort(key=take_first)
    for i in range(len_docs):
        seq = order[i][1]
        doc_new.append(Document(
                    page_content=docs["documents"][seq],
                    metadata=dict(
                        docs["metadatas"][seq]
                    ),))
    # print(doc_new)
    return doc_new


def _normalize_segment_get_way_list(docs_name_list, segment_get_way_list, default_way=3):
    """
    对分段获取策略做长度与取值兜底，避免 docs 与策略数组长度不一致导致越界。
    default_way:
      0=全量, 1=顺序限量, 2=按量更多, 3=相关检索
    """
    docs = list(docs_name_list or [])
    raw = list(segment_get_way_list or [])
    normalized = []
    for idx in range(len(docs)):
        way = raw[idx] if idx < len(raw) else default_way
        try:
            way_int = int(way)
        except Exception:
            way_int = default_way
        if way_int not in (0, 1, 2, 3):
            way_int = default_way
        normalized.append(way_int)
    return normalized


# FIXME
# 现在应该怎么拿到文件的那？就是重新设计获取文件的方式。按理来说，这一部分是说有模型判断利用agent的步骤是最好的，就是说，先是使用大模型对任务进行性质
# 的判断，在性质判断的基础上，再决定到底使用什么获取文件的方式。
# 现在，很明确的，我们对于任何的方式，都需要输入一个文件的列表，而不是文件，之前一直存在术语混用，接下来用segment表示分割后的片段，用doc表示一个
# 文档，现在对于每一个文档再不同的任务下（场景与任务的复合）要获取文档中文本的方式是不同的
# 现在，我们假定：
# 序号1代表着全部获取
# 序号2代表着按顺序多获取
# 序号3代表着按量多获取，建议选择2而不是3，不会差出很多的内容
# 序号4是相关性搜索，就需要给出相关问题。。。相关问题在哪里给出？？？？现在要做到整体的抽象似乎有一点难？？？
# 现在先默认，question一次最多只会有一个吧，就这样.....没问题
# 这个貌似是废弃了
def get_docs_all(user_name, docs_name_list, segment_get_way_list, text_for_search=None):
    segment_get_way_list = _normalize_segment_get_way_list(docs_name_list, segment_get_way_list, default_way=3)
    doc_all_get_list = []
    doc_seq_get_list = []
    doc_more_get_list = []
    doc_relevant_get_list = []
    doc_list = [doc_all_get_list, doc_seq_get_list, doc_more_get_list, doc_relevant_get_list]
    for i, segment_get_way in enumerate(segment_get_way_list):
        doc_list[segment_get_way].append(docs_name_list[i])
    all_segments = []
    # 这里目前还只有通过最后一种方式获取的文本没有分开文档的界限
    # 其实这么做不太对
    # 但是比较好的把文本和图片放在一起的方式我还没想好，到底该怎么放？
    # 很合理的一个想法是首先把这里所有segment的获取和文件建议起一一映射，要做的也就是要把最后获取相关文本的方式修改一下
    # 然后对segment做出第二次遍历，这是合理的，因为图片在获取的文本中的顺序显然是不确定的
    # 第二次获得图片在文本中的合理顺序，这个顺序一定是要和文档相关地，因此上面应该是这样的方式
    # 顺序的获取方式是通过图片所在的页数和文本所在的页数决定的，返回的segment里显然有这些东西
    # 在有了对于原文的正确反映之后（找一个合适地存储方式，例如字符串的列表，但是有的字符串被替换为一个列表：类型+base64+在文档中的序号）
    # 接着目前的对于文本和图片的链接方式要改变。
    # 首先每个文件的开头应该告诉是应该新的文件内容，接着将字符串链接起来直到遇到一个图片用图片的表达方式，似乎可以用一个human消息就能实现，也许？
    # 这样实现的方式是最好的！！！
    # 目前还先使用目前的糟糕方式：文本混乱（针对随机得到的，对它排序有点困难，这是一个二次排序过程，先分文档再内部排序即可，直接先用文档获取也可以）
    # 、图片混乱（和文档无关、顺序等）
    for doc_name in doc_list[0]:
        all_segments.extend(parse_input.get_split_by_user_docs(user_name, [doc_name]))
        all_segments.append(Document(page_content="\n<分割线>---------这是两个文件文本的分割线--------</分割线>\n"))
    for doc_name in doc_list[1]:
        all_segments.extend(get_docs_by_seq_limit(user_name, doc_name))
        all_segments.append(Document(page_content="\n<分割线>---------这是两个文件文本的分割线--------</分割线>\n"))
    for doc_name in doc_list[2]:
        all_segments.extend(get_docs_by_more(user_name, doc_name))
        all_segments.append(Document(page_content="\n<分割线>---------这是两个文件文本的分割线--------</分割线>\n"))
    if text_for_search is not None:
        vector = parse_input.get_vector_by_user(user_name)
        if len(doc_list[3]) != 0:
            all_segments.extend(get_relevant_docs(text_for_search, vector, doc_list[3], user_name))
            all_segments.append(Document(page_content="\n<分割线>---------这是两个文件文本的分割线--------</分割线>\n"))
    # 目前把所有的segment全放到一起，之后可以将不同文档的segment分开
    return all_segments


# 现在的输入没有区分文档，之后可以修改
# 之后的修改设计是，每次的输入的segments是属于一个文件的，再输入前先根据id排序吧，最好是id，但是好像id这里已经获取了了？
# 假设能够排序，从后往前处理图片（一次性先获取所有图片数量最后），再从后往前插入图片，插入看页数即可
# 目前，返回的是所有的segments中的图片列表（不区分顺序），和它在本文件中的顺序（由于有不同文件，可能会混用，目前先顺从之前设计）
def parse_image_in_segment(user_name, segments):
    images = []
    seqs = []
    for segment in segments:
        if "type" in segment.metadata and segment.metadata["type"] == "image":
            images.append(global_var.store_memory[user_name]["images"][back_file_path(segment.metadata["source"])]
                          [segment.metadata["seq"] - 1])
            seqs.append(segment.metadata["seq"])
    return images, seqs


# 🔥 为旧文档的segments补充页码信息（辅助函数）
def _ensure_page_info_in_content(segments):
    """确保segments的page_content中包含页码信息"""
    for segment in segments:
        if segment.metadata and "page" in segment.metadata:
            page_num = segment.metadata["page"]
            page_display = page_num + 1 if isinstance(page_num, int) else page_num
            # 如果page_content中没有页码信息，则补充
            if not segment.page_content.strip().startswith("[页码："):
                segment.page_content = f"[页码：第{page_display}页]\n{segment.page_content}"


def get_docs_by_more(user_name, doc_name):
    segments = parse_input.get_split_by_user_docs(user_name, [doc_name])
    segments = get_Same_distance_docs(segments)
    # 🔥 为旧文档的segments补充页码信息（如果page_content中没有）
    _ensure_page_info_in_content(segments)
    return segments


# 如果是, limit what?
def get_docs_by_seq_limit(user_name, doc_name):
    segments = parse_input.get_split_by_user_docs(user_name, [doc_name])
    len_doc = 0
    left_char = global_var.max_token_num[0] // global_var.token_per_char - global_var.left_char_for_prompt_answer
    return_segments = []
    for segment in segments:
        len_doc += len(segment.page_content) + 2
        if left_char <= len_doc:
            break
        return_segments.append(segment)
    # 🔥 为旧文档的segments补充页码信息（如果page_content中没有）
    _ensure_page_info_in_content(return_segments)
    return return_segments


def get_relevant_docs(question, vector_store, docs_name, user_name, use_tab_enhance=False):
    """
    获取相关文档segments

    参数:
        question: 问题
        vector_store: 向量存储
        docs_name: 文档名列表
        user_name: 用户名
        use_tab_enhance: 是否使用了Tab增强（如果使用了，k=5, fetch_k=10；否则k=8, fetch_k=16）
    """
    querys = []
    query = {}
    for doc_name in docs_name:
        file_path = construct_file_path(user_name, doc_name)
        querys.append(file_path)
    query["source"] = {"$in": querys}

    # 一段是500字符，汉字差不多tokens，10段5000-10000tokens
    # docs = vector_store.similarity_search(question, 8, filter=query)
    # texts = docs[0:min(8, len(docs))]

    # 使用MMR搜索替代简单的相似性搜索
    # 参数说明：
    # k=8: 最终返回8个文档
    # fetch_k=16: 先获取16个候选文档供MMR算法选择（通常设为k的2-3倍）
    # lambda_mult=0.7: 平衡相似性(0.7)和多样性(0.3)，可根据需要调整

    # 🔥 如果使用了Tab增强，使用10取5；否则使用16取8（保持原逻辑）
    if use_tab_enhance:
        k = 5
        fetch_k = 10
        print(f"[get_relevant_docs] 使用Tab增强模式：k={k}, fetch_k={fetch_k}")
    else:
        k = 8
        fetch_k = 16
        print(f"[get_relevant_docs] 使用正常模式：k={k}, fetch_k={fetch_k}")

    # 🔥 使用混合MMR查询（支持同时查询主库和从库）
    docs = parse_input.mmr_search_with_merge(
        vector_store=vector_store,
        user_name=user_name,
        query=question,
        k=k,
        fetch_k=fetch_k,
        lambda_mult=0.7,
        filter=query
    )
    # MMR已经返回了优化的结果，直接使用
    texts = docs  # 不需要再次切片，MMR已经返回了k个最优文档

    # images = []
    # seqs = []
    # for doc in docs:
    #    if "type" in doc.metadata and doc.metadata["type"] == "image":
    #        images.append(global_var.store_memory[user_name]["images"][util.back_file_path(doc.metadata["source"])]
    #                      [doc.metadata["seq"] - 1])
    #        seqs.append(doc.metadata["seq"])
    # for doc in docs:
    #    print(doc)

    return texts


def get_docs_all_split(user_name, docs_name_list, segment_get_way_list, text_for_search=None, core_keyword=None):
    segment_get_way_list = _normalize_segment_get_way_list(docs_name_list, segment_get_way_list, default_way=3)
    doc_all_get_list = []
    doc_seq_get_list = []
    doc_more_get_list = []
    doc_relevant_get_list = []
    doc_list = [doc_all_get_list, doc_seq_get_list, doc_more_get_list, doc_relevant_get_list]
    for i, segment_get_way in enumerate(segment_get_way_list):
        doc_list[segment_get_way].append(docs_name_list[i])
    all_segments = []
    # 把所有的文档的segments分隔开
    vector = parse_input.get_vector_by_user(user_name)
    for i, doc_name in enumerate(docs_name_list):
        cur_segments = []
        if segment_get_way_list[i] == 0:
            cur_segments = parse_input.get_split_by_user_docs(user_name, [doc_name])
        elif segment_get_way_list[i] == 1:
            cur_segments = get_docs_by_seq_limit(user_name, doc_name)
        elif segment_get_way_list[i] == 2:
            cur_segments = get_docs_by_more(user_name, doc_name)
        # elif segment_get_way_list[i] == 3:
        #     cur_segments = get_relevant_docs(text_for_search, vector, [doc_name], user_name)
        # 🔥 为旧文档的segments补充页码信息（如果page_content中没有）
        for segment in cur_segments:
            if segment.metadata and "page" in segment.metadata:
                page_num = segment.metadata["page"]
                page_display = page_num + 1 if isinstance(page_num, int) else page_num
                # 如果page_content中没有页码信息，则补充
                if not segment.page_content.strip().startswith("[页码："):
                    segment.page_content = f"[页码：第{page_display}页]\n{segment.page_content}"
        # cur_segments.append(Document(page_content="\n<分割线>---------这是两个文件文本的分割线--------</分割线>\n"))
        if cur_segments != []:
            all_segments.append(cur_segments)
    # 🔥 判断是否使用了Tab增强（有核心关键词即为使用了Tab增强）
    use_tab_enhance = core_keyword and core_keyword.strip() and core_keyword.strip().lower() not in ['无', 'none', '']

    # LUI1过来这里doc_list[3]是空的，要通过这个判断来分开LUI1和LUI2
    if doc_list[3] != []:
        # 🔥 根据是否使用Tab增强，决定相似搜索的参数（10取5 或 16取8）
        cur_segments = get_relevant_docs(text_for_search, vector, doc_list[3], user_name, use_tab_enhance=use_tab_enhance)
        # 🔥 为RAG检索到的segments补充页码信息（如果page_content中没有）
        for segment in cur_segments:
            if segment.metadata and "page" in segment.metadata:
                page_num = segment.metadata["page"]
                page_display = page_num + 1 if isinstance(page_num, int) else page_num
                # 如果page_content中没有页码信息，则补充
                if not segment.page_content.strip().startswith("[页码："):
                    segment.page_content = f"[页码：第{page_display}页]\n{segment.page_content}"
        all_segments.append(cur_segments)

    # 🔥 如果使用了Tab增强（提供了核心关键词），对每个勾选的文档进行关键词匹配增强
    if use_tab_enhance:
        print(f"[get_docs_all_split] 使用Tab增强模式，核心关键词: '{core_keyword}'，进行文档匹配增强")
        try:
            from llm_langchain.util_keyword_enhance import _enhance_segments_with_keyword
            enhanced_segments = _enhance_segments_with_keyword(
                user_name=user_name,
                docs_name_list=docs_name_list,
                core_keyword=core_keyword,
                vector=vector,
                existing_segments=all_segments
            )
            if enhanced_segments:
                # 合并增强后的segments：相似搜索的segments + 每个文档关键词匹配的前三segments
                all_segments = enhanced_segments
            else:
                print(f"[get_docs_all_split] ⚠️ 关键词匹配增强未返回结果，使用原有segments")
        except Exception as e:
            print(f"[get_docs_all_split] ⚠️ 关键词匹配增强失败: {e}，使用原有segments")
            import traceback
            traceback.print_exc()
    else:
        # 没有使用Tab增强，使用正常的相似搜索逻辑（16取8），直接返回
        print(f"[get_docs_all_split] 未使用Tab增强，使用正常相似搜索逻辑（16取8）")

    return all_segments


def catch_extend(file_path):
    _, ext = os.path.splitext(file_path)
    # 获取没有点的扩展名
    ext = ext[1:]
    return ext


def parse_image_in_segment_split(user_name, all_segments):
    images_all = []
    seqs_all = []
    exts_all = []
    sources_all = []
    pages_all = []
    for cur_doc_segment in all_segments:
        cur_images = []
        cur_seqs = []
        cur_exts = []
        cur_sources = []
        cur_pages = []
        for segment in cur_doc_segment:
            if "type" in segment.metadata and segment.metadata["type"] == "image":
                cur_images.append(global_var.store_memory[user_name]["images"]
                                  [back_file_path(segment.metadata["source"])]
                                  [segment.metadata["seq"] - 1])
                cur_seqs.append(segment.metadata["seq"])
                cur_exts.append(catch_extend(segment.metadata["file_path"]))
                cur_sources.append(segment.metadata["source"])
                cur_pages.append(segment.metadata["page"])
        images_all.append(cur_images)
        seqs_all.append(cur_seqs)
        exts_all.append(cur_exts)
        sources_all.append(cur_sources)
        pages_all.append(cur_pages)
    return images_all, seqs_all, exts_all, sources_all, pages_all


def get_seq_doc_by_path(file_names, vector_store):
    querys = []
    query = {}
    for doc_name in file_names:
        file_path = doc_name
        querys.append(file_path)
    query["source"] = {"$in": querys}
    docs = vector_store.get(where=query)
    # 这里的处理应该是只能对一个文件的获取起效果，所以file_names每次只传一个过来
    # 两个文件会导致ids不一样
    # 如果用上述的in直接查询两个文件，势必会造成文件的冲突，因为也分不清哪个是哪个的
    # 要一次性处理也就只能说是每个单独地做
    len_docs = len(docs["ids"])
    order = []
    doc_new = []
    final_of = docs["ids"][0].rfind("_")
    for i in range(len_docs):
        seq = docs["ids"][i][final_of + 1:]
        seq = int(seq)
        order.append([seq, i])
    order.sort(key=take_first)
    for i in range(len_docs):
        seq = order[i][1]
        doc_new.append(Document(
            page_content=docs["documents"][seq],
            metadata=dict(
                docs["metadatas"][seq]
            ), ))
    # print(doc_new)
    return doc_new


def save_hlscore_to_db_async(usr_name, realName, file_name, img_count, content, base64_image):
    """异步保存HLScore到数据库"""
    import threading
    from zym.models import UserNotebook

    def _save_hlscore():
        try:
            HLScore = imageSum_2_HLScore(content, base64_image)
            book_name = usr_name[len(realName) + 1:]
            notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
            # 读取现有的JSON数据
            try:
                existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
            except json.JSONDecodeError:
                existing_data = {}
            # 更新JSON数据 - HLScore会被正确编码，处理特殊字符，避免HLScore中有""或者:之类符号
            existing_data[f"{os.path.basename(file_name)}-{img_count}"] = HLScore
            notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
            notebook.save()
            print(f"[异步HLScore] 已保存 {file_name}-{img_count} 的评分")
        except Exception as e:
            print(f"[异步HLScore] 保存失败: {e}")

    # 在后台线程中执行
    thread = threading.Thread(target=_save_hlscore)
    thread.daemon = True
    thread.start()


def get_image_depth_suggestion(initial_description, user_name="default_user"):
    """获取小模型的图片深度理解建议"""
    try:
        # 调用get_rel_que中的深度建议函数(仅应用服务器方式可用)
        return get_rel_que.get_depth_suggestion(initial_description, user_name, "image")
    except Exception as e:
        print(f"[图片深度建议] 获取失败: {e}")
        return ""


def image_2_summary_initial(image_path, use_enhance=False):
    """第一步：大模型生成简要描述（版面/布局/DMT层次）"""
    user_prompt = """请简洁地描述图片的：
1. 版面结构：主要区域、空间关系
2. 布局信息：元素位置、分区情况
3. DMT层次：
   - D（Down立足）：具体内容、文字信息、元素位置
   - M（Middle面向）：内容间的逻辑关系、信息流
   - T（Top放眼）：整体意图、深层价值

格式要求：简洁直接，必须控制在300字以内。"""

    try:
        if use_enhance:
            base64_image = get_image_base64_with_mime(image_path=image_path, max_size_mb=5)
            messages = [{"role": "system",
                         "content": [{"text": "You are a helpful assistant."}]},
                        {'role': 'user',
                         'content': [{"image": base64_image},
                                     {'text': user_prompt}]}]
            response = MultiModalConversation.call(
                api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
                model='qwen-vl-max-latest',
                # model='qwen3.6-plus',
                messages=messages,
                vl_high_resolution_images=True
            )
            content = response["output"]["choices"][0]["message"].content[0]["text"]
        else:
            base64_image = encode_image(image_path)
            gpt_vision = chat_gpt_model.get_model()
            messages = [HumanMessage(content=[
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ])]
            response = gpt_vision.invoke(messages)
            content = response.content

        print(f"[图片简要描述] 生成成功，长度: {len(content)}")
        return content
    except Exception as e:
        print(f"[图片简要描述] 生成失败: {e}")
        return ""


def image_2_summary_final(image_path, initial_description, depth_suggestion, use_enhance=False):
    """第三步：大模型根据小模型建议生成最终高质量理解"""
    user_prompt = f"""请对图片进行专业多层次深度分析解读，生成高质量的、由“对”到“妙”的图片理解描述。

    【图片简要描述】
    {initial_description}

    【深度理解策略建议】（小模型提供，供你作为重要参考之一）：
    {depth_suggestion}

    【核心要求】
    请结合图片本身和上述描述、建议，生成符合以下要求的图片理解描述：

    一、DMT层次递进（立足→面向→放眼）
       ● D（Down立足）：识别图片的具体内容、版面结构、元素位置、文字信息
       ● M（Middle面向）：理解内容间的逻辑关系、空间布局、信息流
       ● T（Top放眼）：把握整体意图、深层价值、情境化理解

    二、精准与泛化平衡
       ● 精准：必须保留关键具体信息（标题、数据、规格、印刷文字、手写内容、涂鸦标注等）
       ● 泛化：从表层信息升至图景感知和真实情境化的高维理解

    三、三层结构输出
       ● 细节上：具体内容、数据、文字、标注
       ● 局部过渡上：版面关系、逻辑连接、空间布局
       ● 整体全局上：深层意图、情境价值、图景感知

    【图片类型判断】
    图片可能有不同类型，但广义上都可以归为【学习类文档】，因为图片都是需要学习、认知和理解的。
    请从此类型视角开始思考，采用分层的思路，再进一步细化落实到图片所属的具体类别。

    【学习类文档分析】(作业/试卷/笔记等)
    如果图片含有作业、试卷、笔记等纸质版面，你的表述中必须包含：【理解和陈述】、【评价和建议】这两对，一共四个要素，其中理解是整体性感知，
    陈述是对主体中具体内容或文字的识别（类似OCR的文字识别），这一对很基础！至少要占你篇幅的70%以上；评价是对于其书写规范性、位置合理性
    等的评述，建议是对书写者改进的建议等，这一对是拔高内容，占20%到30%左右，作为辅助。

    请你一定注意不可以过于笼统！例如不能只说"手写层字迹工整，排版规范"，你必须要说具体写了什么内容，主题是什么、有标题吗、与哪些标注关联
    之类的具体内容，你需要尽量表述全面、完整，少遗漏信息！如果图片较为复杂，你也需要尽可能地识别，并一定要说具体写了什么文字，这很重要！

    【多层次分析方法】（这里涉及的点都要包含）：
    1. 版面结构：识别主要区域、是否有子版面划分等，分析空间关系与逻辑连接
    2. 多层内容依次解读：
        - 底图层：图片本身的整体感知性理解，即版面内一些显眼突出的形状，你需要通过一定意象感，做一做感知，例如"xx像是xx"这类的描述
        - 印刷层：教材/试题等印刷，具体印了哪些文字
        - 涂鸦层：批注符号、圈点、下划线等标记（涂鸦勾画等其实是思考过程的体现，也很重要，不可以忽视这层！），具体涂鸦了什么
        - 手写层：有特点的、较为正式的手写字迹，务必涉及具体写了什么（即使认不清也要试着认）
    3. 层间关联：分析各层次间的对应关系，特别关注手写、涂鸦、印刷内容的对应及关联关系
    4. 另外注意：
        - 对图中一些较为特别的点加以强调，例如图中如果有明确的【标题】（一般在版面最上方居中的位置，且黑色加粗）或【主题】，你一定要在最开头就把它识别出来并进行陈述！
        - 涂鸦和手写层虽然都是书写，也有关联性，但你描述时需要分开（格式上分开，内容上要找关联），涂鸦层比较随意，偏向思考过程；手写层比较正式，偏向作答过程
        - 你需要说明作业/试卷/笔记等学习类图片最可能是针对哪些对象的，如什么阶段（小学初中高中大学等）、什么年级等等
        - 如果没有涂鸦笔迹，也需要简单说明一下

    另外如果是原理图、绘画或其他类型的非明显分层图片，也可以用多层次注意的类似思路来深入理解

    【输出格式】
    请按照以下三层结构输出（不要直接出现“D层”/“M层”/“T层”这类字眼，而是用下面这样自然易懂的说法）：
    1. 细节上：[具体内容、数据、文字、标注的具体信息]
    2. 局部过渡上：[版面关系、逻辑连接、空间布局的分析]
    3. 整体全局上：[深层意图、情境价值、图景感知的高维理解]

    【质量要求】
    - 必须精准：保留关键具体信息（标题、数据、规格、印刷文字、手写内容、涂鸦标注等）
    - 必须拔高：从表层信息升维至图景感知和真实情境化的高维理解
    - 必须兼顾：既精准又泛化，既能够抽象升维又保证具体内容完整

    请直接给出自然、完整的图片深度理解描述，由“对”到“妙”，要能激发读者“醍醐灌顶”、起到一定的“育人”作用、体现“成长”价值！不要列出分析过程，用中文描述，控制在800字以内，最好在600字以内。"""

    try:
        if use_enhance:
            base64_image = get_image_base64_with_mime(image_path=image_path, max_size_mb=5)
            messages = [{"role": "system",
                         "content": [{"text": "You are a helpful assistant."}]},
                        {'role': 'user',
                         'content': [{"image": base64_image},
                                     {'text': user_prompt}]}]
            response = MultiModalConversation.call(
                api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
                model='qwen-vl-max-latest',
                # model='qwen3.6-plus',
                messages=messages,
                vl_high_resolution_images=True
            )
            content = response["output"]["choices"][0]["message"].content[0]["text"]
        else:
            base64_image = encode_image(image_path)
            gpt_vision = chat_gpt_model.get_model()
            messages = [HumanMessage(content=[
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ])]
            response = gpt_vision.invoke(messages)
            content = response.content

        print(f"[图片深度理解] 生成成功，长度: {len(content)}")
        return content
    except Exception as e:
        print(f"[图片深度理解] 生成失败: {e}")
        return ""
