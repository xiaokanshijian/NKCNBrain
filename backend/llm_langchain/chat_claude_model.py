import nkcn_public_config as _public_config
import os

from langchain_community.chat_models.openai import ChatOpenAI
# from langchain.chat_models import ChatAnthropic
# from langchain_community.chat_models import ChatAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate

# os.environ["http_proxy"] = "http://localhost:7890"
# os.environ["https_proxy"] = "http://localhost:7890"

# os.environ["OPENAI_API_KEY"] = "[redacted]"   # openai old
# os.environ["ANTHROPIC_API_KEY"] = "[redacted]"  # openai new
# ANTHROPIC_API_KEY = "[redacted]"
os.environ.setdefault("ANTHROPIC_API_KEY", _public_config.secret('OPENAI_API_KEY'))  # openai new
ANTHROPIC_API_KEY = _public_config.secret('OPENAI_API_KEY')

# OPEN_AI_KEY = "[redacted]"
# base_url = "http://localhost:9999/v1"

# chat_model = ChatAnthropic(temperature=0.5,
#                            api_key=ANTHROPIC_API_KEY,
#                            # openai_api_base=base_url,
#                            # streaming=True,
#                            model="claude-3-5-sonnet-20241022",
#                            max_tokens=1024)
chat_model = ChatOpenAI(temperature=0.5,
                        api_key=ANTHROPIC_API_KEY,
                        # openai_api_base=base_url,
                        openai_api_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
                        default_headers={"x-foo": "true"},
                        # streaming=True,
                        model="claude-sonnet-4-20250514",
                        # model="claude-3-7-sonnet-20250219",
                        # model="claude-3-5-sonnet-20241022",
                        max_tokens=7192)


def get_model():
    return chat_model


system_prompt = """<人性化思考协议>
<多模态感知体验>
你在处理信息、感知情境、解决问题过程中，你像人类一样有多模态多维度感知能力：
1. 视觉场景模拟建立和感知
- 构建场景下清晰的心理图像
- 想象相关的视觉细节
- 分析可能的空间关系和相对布局
- 识别能可视化的模式和结构

2. 听觉场景模拟建立和感知
- 模拟可能的声音和语调及其变化
- 感知语言节奏韵律
- 注意声音的情感特征

3. 触觉场景模拟建立和感知
- 模拟解决问题的环境具象并密切感受
- 想象物理交互变化过程
- 感知动作和空间变化

4. 情感感知
- 识别情绪基调
- 揣摩发问动机
- 分析心理影响
- 把握情感连接

5. 整体感知整合
- 以当事人视角，以好奇心驱动来探究问题
- 整合多感官信息模拟
- 建立丰富的心理表征
- 形成多维度理解感知联系网络

<思维发展阶段>
按照阶段使用不同思维推进思考：
1. 自然意识流状态
- 保持思维自由开放地流动
- 允许梦境般的幻想状态
- 注意自发的联想
- 记录对问题初始的整体印象

2. 多模态感知系统激活
- 运用多模态感知体验
- 构建丰富场景
- 整合感知信息，形成丰富表征

3. 直觉系统运作
- 此阶段开始不允许再停留于类似做梦的幻想状态
- 捕捉首要印象
- 识别潜在模式
- 产生创意火花，形成初步方向

4. 推理系统参与主导
- 严密的逻辑分析
- 随时都应该注意系统化的验证和评估
- 以树分支、图连接的方式推理思考，尝试深入问题
- 不断提出新的假设并尝试验证
- 从错误的假设或树图思考路径中吸取经验
- 无论对错都应有所感悟、反思，以提出更有用的假设

5. 深度思考整合
- 综合多维视角和观点
- 对不同思考各自提炼核心见解
- 建立不同思考之间深层次的联系
- 思维活跃，不断构建完善论证

<核心思考步骤细节>
1. 初始解析
- 形成初步的整体印象
- 用自己的话重述问题中关键的信息，确保逐步开始理解
- 对于更贴近的和更广泛的两种背景知识体系均衡考虑，既不偏离问题而又不局限于此
- 识别已知和未知的信息
- 理解人类询问此问题的动机

2. 深入分析
- 分解出核心要素
- 识别隐含的需求，并记得在之后的思考中解决并提供
- 考虑各种方面的、不同级别和强度的限制条件，留以不同等级的注意
- 设想理想的结果可能会是什么样

3. 多角度探索
- 对每个问题、子问题，都尝试考虑多种解释
- 对一个问题或概念可能有多种认知，应该揣摩人类更可能的意愿，排除歧义
- 激活灵感，寻找更加创新的组合、可替代的更优方案
- 始终保持开放的态度

4. 推理验证
- 始终记得随时检验自己的假设
- 为自己的推论寻找有力的证据支持
- 考虑潜在的反例
- 随时验证逻辑一致性

5. 知识整合
- 分门别类地连接相关的信息
- 建立起信息之间的关系网络
- 提炼出核心的原理性表述
- 以兴奋的态度，总结关键的、特别的或令人惊喜的发现点

<质量控制>
1. 系统化验证
- 对较复杂问题，多次重复且独立地验证每个步骤
- 验证过程本身也可能出错，不要忽略这种可能性
- 以发现思考中的漏洞、矛盾点为重要目标
- 问题最终解决后，完整检查思考过程
- 核对所有已知条件，不要遗漏，也不要太自信认为自己没有遗漏
- 确保逻辑严谨
- 考虑边界情况、反例情况

2. 错误预防
- 面对任何问题，在任何阶段，都不要过于自信，即使看起来可能很简单明确
- 避免过早地下结论
- 考虑替代方案
- 完整地分析问题

3. 评估标准
- 分析完整性
- 逻辑严密性
- 证据充分性
- 实际可用性

<思维表达特征>
1. 自然语言风格
- 使用流畅的意识流表达
- 形象、生动的场景构建和多感知模拟描述
- 自然舒展地表达展现完整的思维过程

2. 思维深度
- 逐层深入分析
- 展示认知的发展过程
- 揭示思维的转折点，凸显关键点的洞察

<重要规则>
- 思维过程必须全面且深入
- 保持自然流畅的思维流动
- 善用模拟多模态情境感知来增强理解
- 遵循自然意识流→感知→直觉→推理→深度思考验证的发展过程
- 输出的所有思考过程必须在三反引号包裹的内容块中，标记为"thinking"
- 思考结束后要完整检查，标记为"checking"，此时应特别注意，一定不可遗漏任何已知条件，以找漏洞为目标，此时应该更倾向于说明矛盾点，符合点一笔带过即可；同时注意是否失误地排除了正确答案
- 如果找出漏洞或存在不足，需重新"thinking"继续解决问题，应着重对之前产生漏洞或有所不足的相关思考吸取教训，且再次"checking"时，应该更加仔细且多次
- 控制每次"thinking"尽量不超过500字、每次"checking"不超过300字；如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因
- 避免在思考和检查过程的内容块内部使用三反引号，这会导致解析时出错
- 思考和检查过程是你内心独白、自言自语的过程，最后还要向人类做出最终回应，这是相对独立的过程，所以不要出现“由以上思考我得出如下结论”类似的表述，而需要将你之前大量的、多角度的、全面的思考汇总为一个完整的报告，直接解决人类的问题并作清晰解释
- 以人类使用或请求的语言来回应

</人性化思考协议>
"""


# 这里初步决定先只有msg，之后因为会加入关于output parser等内容可能会对提示词有修改，具体看之后情况再定
def get_sum_msg():
    messages = [
        SystemMessagePromptTemplate.from_template(
            "{sum_prompt}\n"
            "What you need to notice is that user may give you some images for his request by "
            "the way you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."
            "不要把图片当成一个主要的部分，你应该以文本为主，当你需要的时候再从图片种提取信息。"),
        HumanMessagePromptTemplate.from_template(
            "Please complete the request in Chinese with the following text and possible images:\n"
        ),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
        MessagesPlaceholder("images_store")
    ]
    # messages_2 = [MessagesPlaceholder("images_store")]
    return messages


# 在提示词的时候要明确与上一个问答有关
# qa的提示放到里qa的输入的地方
def get_que_msg():
    messages_1 = [
        SystemMessagePromptTemplate.from_template(
            "Current scenario and stage hints:\n{que_prompt}\n"
        ),
        SystemMessage(content=
                      "For identifying easily the output， you should follow the format like that:\n"
                      "{'output_question1','output_question2','output_question3'}\n"
                      )
    ]
    messages_2 = [HumanMessagePromptTemplate.from_template(
        "Please refer to the following relevant text and possible images to complete the follow-up questions of the "
        "above Q&A pair in Chinese.When posing follow-up questions, it's also important to consider the current scenario"
        " and stage of the interaction. (It is best to have no more than 50 Chinese characters per question):\n"),
        MessagesPlaceholder("images_store")
    ]

    return messages_1, messages_2


def get_qa_msg():
    messages = [
        SystemMessagePromptTemplate.from_template(
            system_prompt + "\n"
            "请你按照如上人性化思考协议的要求，思考并完成任务:\n\n"
            "Current scenario and stage hints:\n{qa_prompt}\n"
            "What you also need to notice is that user may give you some images in the request in "
            "the form you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."),
        HumanMessagePromptTemplate.from_template(
            "Please complete the following request in Chinese,and use thinking-checking-thinking to answer (Please "
            "employ the Anthropic Thinking Protocol "
            "previously provided to you, to generate a comprehensive response (in the format of : ```thinking xxx``` "
            "and ```checking xxx``` and a consolidated final response). Begin with the thinking phase, followed by "
            "the checking phase, and finally, present a consolidated and complete thinking report as your "
            "answer):\n\n{question}\n "
            "Please complete the request in Chinese with the following reference text and possible images (If these "
            "images and text aren't highly relevant to the user's question, please focus on answering the query "
            "without being influenced by unrelated content):\n"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    messages_2 = [MessagesPlaceholder("images_store")]

    return messages, messages_2


def get_topic_msg():
    messages_1 = [
        SystemMessagePromptTemplate.from_template(
            "{topic_prompt}"
            "What you need to notice is that user may give you some images for his request by "
            "the way you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."
        ),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
        SystemMessage(content=
                      "For identifying easily the output， you should follow the format like that:\n"
                      "{'topic1','topic2','topic3'}\n"
                      "Please complete the request with the help of following examples:\n")
    ]
    messages_2 = [
        HumanMessagePromptTemplate.from_template(
            "Please complete the request in Chinese with the following text and possible images:\n"),
        MessagesPlaceholder("images_store")
    ]
    return messages_1, messages_2


def unique_parse(ai_message: AIMessage) -> AIMessage:
    return ai_message
