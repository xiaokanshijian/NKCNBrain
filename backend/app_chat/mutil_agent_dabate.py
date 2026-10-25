import nkcn_public_config as _public_config
import json

from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate, \
    AIMessagePromptTemplate, SystemMessagePromptTemplate
# from new_hwlattop import get_model
from langchain_openai import ChatOpenAI

from llm_langchain import util, chat_gpt_model, parse_input, global_var, red_bule_rate

debate_messages = [
    SystemMessage(content="你的身份是一个组织或小群组中的一员，稍后用户会告诉你你所在的组织和你在组织中的身份。\n"
                          "与你的身份相对应的还可能有你的其他性格特征，例如你的脾气，你的利益诉求等。\n"
                          "你现在将参加一场组织中关于一个问题的讨论，参与讨论的除了你之外还有组织中的其他人。\n"
                          "你需要根据自己的性格特点和利益诉求给出你对于本次问题的回答（当然如果当前问题与你的性格或者诉求不冲突，你应该尽可能"
                          "给出公正的评价），于此同时，其余的成员也会给出他们的回答。\n"
                          "你们将参加不止一轮的讨论，在讨论之前，会将其余成员的身份信息和他们的性格特征，以及你们之前轮次的对话"
                          "交给你。在讨论中，你需要权衡自己的性格和诉求以及其他人的性格和诉求，以便你们能够在这个问题中达成共识，"
                          "形成一个对于多方都满意的结果。（当然在第一轮讨论之前并不会给出你这些信息，你对于这方面并不需要担心。）\n"
                          "其他人的信息将会以这样的形式交给你：\n"
                          "轮次（表示这是第几轮的讨论）：\n"
                          "身份特征(性格特点或者利于诉求):本轮次的回答。\n"
                          "例如：\n"
                          "第一轮：\n"
                          "总经理(爱好赚钱):我认为你们这些员工应该加班。\n"
                          "员工1号(不喜欢上班):我觉得正常的工作时间已经足够。\n"
                          "你的曾经的回答当然也会提供给你，它的形式是：\n"
                          "轮次：\n"
                          "回答\n"
                          "例如：\n"
                          "第一轮：\n"
                          "我觉得最多加班一个小时就够了。\n"
                          "在讨论中不要永远保持自己的想法不变，在经过讨论了解别人的诉求之后，你应该尝试在不严重违背自己诉求的情况下进行可能的妥协，\n"
                          "期待你们在多次的讨论中拿到一个另大多数人都满意的结果。\n"),
    HumanMessagePromptTemplate.from_template(
        "这是你们此次任务已知的基础，是对这个问题的初步回答：{wen}，需要围绕此基础展开后续：{content}。\n"
        "这是你们所在的组织或群组信息：{groupInfo}，你们的群组目标是：{groupObjective}，这个群组目标非常重要，你的回答需要围绕它展开。\n"
        "这是你的身份信息：{identity}，这是你的性格特点或者利益诉求：{self_interest}。\n"
        "你们本次讨论需要解决的问题是：{question}\n"
        "请据理力争并适当妥协，拿到一个让所有人尽量满意的结果吧。\n"),
    AIMessagePromptTemplate.from_template(
        "这是组织中其余成员的信息和之前轮次的回答（在第一例对话中它将没有任何信息）：\n"
        "{all_other_info}\n"
    ),
    SystemMessagePromptTemplate.from_template(
        "这是你之前轮次的回答：{history}\n"
        "请给出你本轮的回答，100到150字，内容上不要脱离已知基础（即“{wen}”的初步回答），且务必考虑到你自己的身份、职能、特点和群组目标，"
        "并且要在之前轮次回答的基础上再深入讨论(只需要给出回答，不需要自己加上轮次信息)：\n"
    )
]

end_messages = [
    SystemMessage(
        "你目前的身份是一个组织中的一员，稍后会告诉你你所在的组织和你在组织中的身份。\n"
        "与你的身份相对应的还可能有你的其他性格特征，例如你的脾气，你的利益诉求等。\n"
        "你已经和组织中的其他若干成员根据任务已有的基础，对一个待解决的核心问题，完成了几轮辩论，相关信息将在之后给出。\n"
        "你在和其他若干成员的交谈中，进行了不断的意见发表，根据已有的基础内容进行发言，初步具备了解决问题并完成这个任务的能力。\n"
        "你们辩论发言的历史信息将以这样的格式告诉你：\n"
        "轮次（表示这是第几轮的讨论）：\n"
        "身份特征(性格特点或者利于诉求):本轮次的回答。\n"
        "例如：\n"
        "第一轮：\n"
        "总经理(爱好赚钱):我认为你们这些员工应该加班。\n"
        "员工1号(不喜欢上班):我觉得正常的工作时间已经足够。\n"
    ),
    HumanMessagePromptTemplate.from_template(
        "这是你们此次任务已有的基础，是对这个问题的回答：{wen}，你现在需要根据和其他若干成员的辩论发言发表意见历史聊天记录，重新修正这一段内容，视作完成了你的最终任务：{content}。\n"
        "除你们的辩论发言发表意见历史聊天记录外，你的修正还一定要考虑到群组目标，务必要比原先更加有利于群组目标！！为此你需要至少修改百分之10到百分之20的内容！但不能改变文本整体大意！\n"
        "这是你们所在的组织或群组信息：{groupInfo}，你们的群组目标是：{groupObjective}，这个群组目标非常重要，你的修正需要仔细考虑这个目标。\n"
        "这是你的身份信息：{identity}，这是你的性格特点或者利益诉求：{self_interest}。\n"
        "你的修正还需要对解决这个核心问题有帮助：{question}\n"
    ),
    AIMessagePromptTemplate.from_template(
        "这是你们的辩论发言发表意见历史聊天记录：\n"
        "{all_history}\n"
    ),
    SystemMessagePromptTemplate.from_template(
        "请给出你重新修正内容后的结果吧，修正最好是在原有基础上添加内容，尽量不要做删减！尽量都做新增。\n"
        "记得不要脱离“{wen}”这个问题！既要有整体宏观，也要有具体如何实现！避免说空话，务必考虑到辩论发言发表意见历史记录和群组目标等！"
        "并务必明确、显式地体现认知与行动结合、群组自治、成员共生生态、目标与任务结合！（给出修正结果即可，不要其他信息，例如身份）：\n"
    )
]

# OPEN_AI_KEY = "[redacted]"  # GPT
OPEN_AI_KEY = _public_config.secret('KIMI_API_KEY')  # kimi
base_url = "https://api.moonshot.cn/v1"


def agent_debate(roleCount, groupInfo, roles, groupObjective, coreProblem, maxRounds, wen, content, username):
    # chat_model = ChatOpenAI(temperature=0.2,
    #                         openai_api_key=OPEN_AI_KEY,
    #                         # openai_api_base=base_url,
    #                         # streaming=True,
    #                         model_name="gpt-3.5-turbo",
    #                         max_tokens=1000)
    chat_model = ChatOpenAI(temperature=0.2,
                            openai_api_key=OPEN_AI_KEY,
                            openai_api_base=base_url,
                            # streaming=True,
                            model_name="moonshot-v1-32k",
                            max_tokens=1000)
    debate_prompt = ChatPromptTemplate.from_messages(debate_messages)
    n_loop = maxRounds
    n_iden = roleCount
    identify_list = []
    interest_list = []
    for role in roles:
        identify_list.append(role.get('identity', '默认身份'))
    for role in roles:
        interest_list.append(role.get('function', '默认职能'))

    loop_info_list = []  # 记录本用户需要的关于其余用户的信息
    loop_history_list = []  # 记录本用户需要的关于自己历史记录的信息
    cur_list = []  # 记录本轮信息
    all_history = ""
    question = coreProblem
    for i in range(n_iden):
        loop_info_list.append("")
        loop_history_list.append("")
    for i in range(n_loop):
        all_history += "第" + str(i+1) + "轮\n"
        if i != 0:
            for j in range(n_iden):
                loop_info_list[j] += "第" + str(i) + "轮\n"
                for k in range(n_iden):
                    if k != j:
                        loop_info_list[j] += (
                                identify_list[k] + "(" + interest_list[k] + "):" + cur_list[k] + "\n")
                loop_history_list[j] += "第" + str(i) + "轮\n"
                loop_history_list[j] += (cur_list[j] + "\n")
        for j in range(n_iden):
            # print(loop_info_list[j])
            # print(loop_history_list[j])
            debate = debate_prompt.invoke({"wen": wen, "content": content, "groupInfo": groupInfo, "groupObjective": groupObjective,
                                           "identity": identify_list[j], "self_interest": interest_list[j],
                                           "question": question, "all_other_info": loop_info_list[j],
                                           "history": loop_history_list[j]})
            # print(debate)
            out = chat_model.invoke(debate)
            # print(out.content)
            all_history += (identify_list[j] + "(" + interest_list[j] + "):" + out.content + "\n")
            if i == 0:
                cur_list.append(out.content)
            else:
                cur_list[j] = out.content
    print("讨论完成：————————————————————————————————")

    end_prompt = ChatPromptTemplate.from_messages(end_messages)
    end = end_prompt.invoke({"wen": wen, "content": content, "groupInfo": groupInfo, "groupObjective": groupObjective,
                                   "identity": identify_list[0], "self_interest": interest_list[0],
                                   "question": question, "all_history": all_history})
    end_out = chat_model.invoke(end)
    all_history += ("问答追问最终修正结果:" + end_out.content + "\n")

    print("最终修正完成，准备红蓝卡标：————————————————————————————————")
    score, color, reason = red_bule_rate.get_rate(username, content)
    print(score, color, reason)
    scoreEnd, colorEnd, reasonEnd = red_bule_rate.get_rate(username, end_out.content)
    print(scoreEnd, colorEnd, reasonEnd)
    return all_history, score, color, reason, scoreEnd, colorEnd, reasonEnd