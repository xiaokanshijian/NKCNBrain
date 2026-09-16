import json
import os
import asyncio
from langchain.chains.llm import LLMChain
from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate, \
    AIMessagePromptTemplate, SystemMessagePromptTemplate
# from new_hwlattop import get_model, chat_gpt_model
from llm_langchain import util, chat_gpt_model, parse_input, global_var, red_bule_rate

AI_User_messages = [
    SystemMessage(
        "你目前的身份是一个组织中的一员，稍后会告诉你你所在的组织和你在组织中的身份。\n"
        "与你的身份相对应的还可能有你的其他性格特征，例如你的脾气，你的利益诉求等。\n"
        "与此同时，你将和组织中的另一个成员进行交谈，共同完成一项具有难度的任务。具体任务将在之后给出，这位成员的身份和相关信息也会在之后给出。\n"
        "你在本次的交谈中，需要根据最终的任务和你与另一位成员的交谈历史信息，给出为了解决这个最终任务在当前已经做到的工作的基础上还需要解决的下一个问题。\n"
        "在提出这个问题之前请经过仔细地思考，保证这个问题是在之前工作的基础上可以简单达到的，而不能是一个非常困难的需要多个步骤实现的任务。"
        "你认为简单的问题可以不提出，只剩下简单问题的时候，可以选择结束。简单的度量可以这样：对方的回答不会超出你的预期，或能在原文中找到答案的问题\n"
        "你提出的问题应当是合理的，符合你的身份的，例如作为一个学生并不需要去考虑老师的事情，不要代替老师完成他的任务，不要关心与你的身份无关的东西。\n"
        "例如，当你是一个学习小组的组员，与你交谈的是你的组长。现在需要填一份学习表格，你的第一个问题可能是：在这份表格中我需要填写的项目有哪些？"
        "若现在需要完成一个代码项目，已经有了一份代码描述的摘要，你的第一个问题可能是：以我的组员身份来看，这份摘要怎么修改可以体现我需要注意的重点？\n"
        "请切记你的身份信息和其他信息，并且切记为了推动最终任务的完成你只需要提出目前需要解决的问题即可。\n"
        "需要注意的是，这个最终任务是你所代表的角色需要负责完成的任务，而另一位成员只是辅助你完成这个任务。\n"
        "当你认为这个最终任务已经完成的时候，只需要返回结束二字即可。记住只需要返回结束二字。\n"
        "你需要合理地判断任务是否结束，当你已经可以做到它或者只剩下一些不足以提问的小问题时，你就应该结束了！"
        "历史信息将以这样的格式告诉你：\n"
        "角色信息(角色特点或诉求):角色的发言。\n"
        "例如：\n"
        "组员(学习优秀):我有什么需要填写的项目呢？\n"
    ),
    HumanMessagePromptTemplate.from_template(
        "这是你们此次任务已知的基础，需要围绕此基础展开后续：{sumContent}。\n"
        "这是你们所在的组织或群组信息：{groupInfo}，你们的群组目标是：{groupObjective}，这个群组目标非常重要，你的提问需要围绕它展开。\n"
        "这是你的身份信息：{identity}，这是你的性格特点或者利益诉求：{self_interest}。\n"
        "你要解决的任务是：{question}\n"
        "这是另一位成员的身份信息：{identity_other}，这是他的性格特点或者利益诉求：{self_interest_other}。\n"
    ),
    AIMessagePromptTemplate.from_template(
        "这是你们的历史聊天记录（在第一次对话中它将没有任何信息），请一定记住不要重复提已经提过的问题：\n"
        "{all_info}\n"
    ),
    SystemMessagePromptTemplate.from_template(
        "请给出你认为为了解决这个任务当前需要解决的问题吧，务必考虑到你自己的身份、职能、特点和群组目标，并且要在之前问答的基础上再深入提问（给出问题即可，不要其他信息，例如身份）：\n"
    )
]

AI_Assistant_messages = [
    SystemMessage(
        "你目前的身份是一个组织中的一员，稍后会告诉你你所在的组织和你在组织中的身份。\n"
        "与你的身份相对应的还可能有你的其他性格特征，例如你的脾气，你的利益诉求等。\n"
        "与此同时，你将和组织中的另一个成员进行交谈，共同完成一项具有难度的任务。具体任务将在之后给出，这位成员的身份和相关信息也会在之后给出。\n"
        "另一位成员在交谈中将会给出在当前交谈信息的基础上为了解决最终任务当前需要解决的问题，而你的任务则是解决这个当前问题！\n"
        "请切记你的身份信息和其他信息，并且切记为了推动最终任务的完成你只需要解决另一位成员目前提出的问题即可。\n"
        "需要注意的是，这个最终任务是另一位成员需要负责完成的任务，而你只是辅助另一位成员完成这个任务。\n"
        "历史信息将以这样的格式告诉你：\n"
        "角色信息(角色特点或诉求):角色的发言。\n"
        "例如：\n"
        "组长(乐于助人):你需要填写姓名、联系方式、小组角色、最终任务、目前已完成任务、还需完成任务、任务规划、最终期限这些项目。\n"
    ),
    HumanMessagePromptTemplate.from_template(
        "这是你们此次任务已知的基础，需要围绕此基础展开后续：{sumContent}。\n"
        "这是你们所在的组织或群组信息：{groupInfo}，你们的群组目标是：{groupObjective}，这个群组目标非常重要，你的回答需要围绕它展开。\n"
        "这是你的身份信息：{identity}，这是你的性格特点或者利益诉求：{self_interest}。\n"
        "你们本次讨论需要解决的任务是：{question}\n"
        "这是另一位成员的身份信息：{identity_other}，这是他的性格特点或者利益诉求：{self_interest_other}。\n"
    ),
    AIMessagePromptTemplate.from_template(
        "这是你们的历史聊天记录（在第一次对话中它将没有任何信息）：\n"
        "{all_info}\n"
    ),
    HumanMessagePromptTemplate.from_template(
        "请你根据历史信息和最终目标解决如下问题（给出回答即可，不要其他信息，例如身份，回答150到200字左右）：{question_cur}\n"
    )
]

AI_User_end_messages = [
    SystemMessage(
        "你目前的身份是一个组织中的一员，稍后会告诉你你所在的组织和你在组织中的身份。\n"
        "与你的身份相对应的还可能有你的其他性格特征，例如你的脾气，你的利益诉求等。\n"
        "你已经和组织中的另一个成员完成了问答交谈，内容是另一个成员辅助你共同完成一项具有难度的任务，相关信息将在之后给出。\n"
        "你在和另一位成员的交谈中，进行了不断的问题和任务拆解，对已知内容进行裂解，初步具备了解决问题并完成这个任务的能力。\n"
        "你们问答交谈的历史信息将以这样的格式告诉你：\n"
        "角色信息(角色特点或诉求):角色的发言。\n"
        "例如：\n"
        "组员(学习优秀):我有什么需要填写的项目呢？\n"
    ),
    HumanMessagePromptTemplate.from_template(
        "这是你们此次任务已有的基础，你现在需要根据和另一位成员的问答交谈历史聊天记录，重新修正这一段内容，视作完成了你的最终任务：{sumContent}。\n"
        "除你们的问答交谈历史聊天记录外，你的修正还一定要考虑到群组目标，务必要比原先更加有利于群组目标！！为此你需要至少修改百分之10到百分之20的内容！但不能改变文本整体大意！\n"
        "这是你们所在的组织或群组信息：{groupInfo}，你们的群组目标是：{groupObjective}，这个群组目标非常重要，你的修正需要仔细考虑这个目标。\n"
        "这是你的身份信息：{identity}，这是你的性格特点或者利益诉求：{self_interest}。\n"
        "你的修正还需要对解决这个核心问题有帮助：{question}\n"
        "这是另一位辅助你的成员的身份信息：{identity_other}，这是他的性格特点或者利益诉求：{self_interest_other}。\n"
    ),
    AIMessagePromptTemplate.from_template(
        "这是你们的问答交谈历史聊天记录：\n"
        "{all_info}\n"
    ),
    SystemMessagePromptTemplate.from_template(
        "请给出你重新修正内容后的结果吧，修正最好是在原有基础上添加内容，尽量不要做删减！尽量都做新增。既要有整体宏观，也要有具体如何实现！避免说空话，"
        "务必考虑到问答交谈历史记录和群组目标等！并务必明确、显式地体现认知与行动结合、群组自治、成员共生生态、目标与任务结合！（给出修正结果即可，不要其他信息，例如身份）：\n"
    )
]


# OPEN_AI_KEY = os.environ.get("OPENAI_API_KEY", "")  # GPT
OPEN_AI_KEY = os.environ.get("KIMI_API_KEY", "")  # kimi
base_url = "https://api.moonshot.cn/v1"


def agent_loop(groupInfo, roleIdentity1, roleFeature1, roleIdentity2, roleFeature2, responseMethod, groupObjective, coreProblem, maxRounds, sumContent, username):
    # chat_model = get_model.get_chat(0)
    # chat_model = ChatOpenAI(temperature=0.3,
    #                         openai_api_key=OPEN_AI_KEY,
    #                         # openai_api_base=base_url,
    #                         # streaming=True,
    #                         model_name="gpt-3.5-turbo",
    #                         max_tokens=1000)
    chat_model = ChatOpenAI(temperature=0.3,
                            openai_api_key=OPEN_AI_KEY,
                            openai_api_base=base_url,
                            # streaming=True,
                            model_name="moonshot-v1-32k",
                            max_tokens=1000)
    ai_user_prompt = ChatPromptTemplate.from_messages(AI_User_messages)
    ai_assistant_prompt = ChatPromptTemplate.from_messages(AI_Assistant_messages)

    identify_list = [roleIdentity2, roleIdentity1]
    interest_list = [roleFeature2, roleFeature1]

    n_loop = maxRounds
    n_iden = 2
    loop_history = ""  # 记录本用户需要的关于自己历史记录的信息
    question = coreProblem
    question_record = []
    # 循环n_loop轮，生成对话
    for i in range(n_loop):
        # 调用chat_model生成agent user角色的提问
        user_p = ai_user_prompt.invoke({"sumContent": sumContent, "groupInfo": groupInfo, "groupObjective": groupObjective,
                                        "identity": identify_list[0], "self_interest": interest_list[0],
                                        "question": question, "all_info": loop_history,
                                        "identity_other": identify_list[1],
                                        "self_interest_other": interest_list[1]})
        question_cur = chat_model.invoke(user_p)
        if question_cur.content == "结束" or \
                (question_cur.content.find("结束") != -1 and len(question_cur.content) < 5):
            break
        # 避免重复提出相同的问题
        if question_cur.content in question_record:
            continue
        question_record.append(question_cur.content)
        # 调用chat_model生成agent 助手角色的回答
        ass_p = ai_assistant_prompt.invoke({"sumContent": sumContent, "groupInfo": groupInfo, "groupObjective": groupObjective,
                                            "identity": identify_list[1], "self_interest": interest_list[1],
                                            "question": question, "all_info": loop_history,
                                            "identity_other": identify_list[0],
                                            "self_interest_other": interest_list[0],
                                            "question_cur": question_cur.content})
        answer_cur = chat_model.invoke(ass_p)
        loop_history += (identify_list[0] + "(" + interest_list[0] + "):" + question_cur.content + "\n" +
                         identify_list[1] + "(" + interest_list[1] + "):" + answer_cur.content + "\n")
    print("loop_history历史：————————————————————————————————", username)

    ai_user_end_prompt = ChatPromptTemplate.from_messages(AI_User_end_messages)
    user_p_end = ai_user_end_prompt.invoke({"sumContent": sumContent, "groupInfo": groupInfo, "groupObjective": groupObjective,
                                    "identity": identify_list[0], "self_interest": interest_list[0],
                                    "question": question, "all_info": loop_history,
                                    "identity_other": identify_list[1],
                                    "self_interest_other": interest_list[1]})
    question_cur_end = chat_model.invoke(user_p_end)
    loop_history += ("主题裂解最终修正结果:" + question_cur_end.content + "\n")

    print("最终修正完成，准备红蓝卡标：————————————————————————————————")
    score, color, reason = red_bule_rate.get_rate(username, sumContent)
    print(score, color, reason)
    scoreEnd, colorEnd, reasonEnd = red_bule_rate.get_rate(username, question_cur_end.content)
    print(scoreEnd, colorEnd, reasonEnd)
    return loop_history, score, color, reason, scoreEnd, colorEnd, reasonEnd