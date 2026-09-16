import base64
import random

from datetime import datetime

import fitz
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel, SimpleChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompt_values import PromptValue
from llm_langchain import global_var, chat_gpt_model, parse_input

import os
import re
import shutil
from zym.models import UserNotebook
from app_chat.models import Card, DeletedFile, AutomationRecord, AutomationTask, AutomationStatus, DMTAnalysisTask

db_path = "./received_dir/user_db_file"
raw_path = "./received_dir/user_raw_file"
dmt_path = "./dmt_analysis"


# 处理cardImage文件夹中的图片文件
def process_card_images(source_dir, target_dir, cid_mapping):
    """
    处理cardImage文件夹中的图片，根据cid_mapping重命名图片文件

    Args:
        source_dir: 源cardImage文件夹路径
        target_dir: 目标cardImage文件夹路径
        cid_mapping: 旧cid到新cid的映射字典
    """
    if not os.path.exists(source_dir):
        return

    # 获取源文件夹中的所有文件
    image_files = os.listdir(source_dir)

    for image_file in image_files:
        # 提取文件名（不含扩展名）
        file_name, file_ext = os.path.splitext(image_file)

        try:
            # 尝试将文件名转换为整数（cid）
            old_cid = int(file_name)

            # 检查是否存在于映射中
            if old_cid in cid_mapping:
                # 获取新的cid
                new_cid = cid_mapping[old_cid]

                # 创建新的文件名
                new_image_file = f"{new_cid}{file_ext}"

                # 复制并重命名图片
                src_file = os.path.join(source_dir, image_file)
                dst_file = os.path.join(target_dir, new_image_file)

                # 复制文件
                shutil.copy(src_file, dst_file)
                print(f"已复制并重命名图片：{image_file} -> {new_image_file}")
            else:
                # 如果在映射中找不到，仍然复制原始文件（可选择是否保留）
                src_file = os.path.join(source_dir, image_file)
                dst_file = os.path.join(target_dir, image_file)
                shutil.copy(src_file, dst_file)
                print(f"警告：找不到cid {old_cid}的映射，已直接复制图片：{image_file}")
        except ValueError:
            # 如果文件名不是纯数字，直接复制
            src_file = os.path.join(source_dir, image_file)
            dst_file = os.path.join(target_dir, image_file)
            shutil.copy(src_file, dst_file)
            print(f"复制非cid命名图片：{image_file}")


# 分享时复制用户本子文件夹到目标用户本子文件夹
def copyDir(sharedUser, user, sharedBookName, realSharedBookName, cid_mapping=None):
    # 创建目标文件夹路径
    target_folder = os.path.join(raw_path, f"{sharedUser}_{realSharedBookName}")
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    # 源文件夹路径
    source_folder = os.path.join(raw_path, f"{user}_{sharedBookName}")
    if os.path.exists(source_folder):
        # 列出源文件夹中的所有文件
        files = os.listdir(source_folder)

        # 遍历所有文件并复制到目标文件夹
        for file_name in files:
            doc_path = os.path.join(source_folder, file_name)
            if not os.path.isdir(doc_path):
                src_file = os.path.join(source_folder, file_name)
                dst_file = os.path.join(target_folder, file_name)
                shutil.copy(src_file, dst_file)
            else:
                # 检查是否是cardImage文件夹，需要特殊处理
                if file_name == "cardImage" and cid_mapping:
                    # 创建目标cardImage文件夹
                    dst_card_image_dir = os.path.join(target_folder, "cardImage")
                    if not os.path.exists(dst_card_image_dir):
                        os.makedirs(dst_card_image_dir)

                    # 处理cardImage文件夹内的图片
                    process_card_images(doc_path, dst_card_image_dir, cid_mapping)
                else:
                    # 创建目标文件夹中的子文件夹
                    dst_dir = os.path.join(target_folder, file_name)
                    # 如果目标文件夹中已存在同名文件夹，可以选择先删除它
                    if os.path.exists(dst_dir):
                        shutil.rmtree(dst_dir)
                    # 复制文件夹及其内容
                    shutil.copytree(doc_path, dst_dir)
    else:
        print(f"源文件夹 {source_folder} 不存在.")


def copyDirDMT(sharedUser, user, sharedBookName, realSharedBookName):
    import os
    import shutil

    # 源文件夹路径
    source_folder = os.path.join(dmt_path, f"{user}_{sharedBookName}")
    # 目标文件夹路径
    target_folder = os.path.join(dmt_path, f"{sharedUser}_{realSharedBookName}")

    if not os.path.exists(source_folder):
        print(f"源文件夹 {source_folder} 不存在.")
        return

    # 创建目标文件夹
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    # 定义替换函数
    def replace_name(name):
        old_pattern = f"{user}_{sharedBookName}"
        new_pattern = f"{sharedUser}_{realSharedBookName}"
        return name.replace(old_pattern, new_pattern)

    # 递归复制并重命名
    for root, dirs, files in os.walk(source_folder):
        # 计算相对路径
        rel_path = os.path.relpath(root, source_folder)

        # 如果是根目录
        if rel_path == '.':
            dest_root = target_folder
        else:
            # 替换路径中的每个部分
            path_parts = rel_path.split(os.sep)
            new_parts = [replace_name(part) for part in path_parts]
            dest_root = os.path.join(target_folder, *new_parts)

        # 创建目标目录
        if not os.path.exists(dest_root):
            os.makedirs(dest_root)

        # 复制文件并重命名
        for file_name in files:
            src_file = os.path.join(root, file_name)
            # 替换文件名
            new_file_name = replace_name(file_name)
            dst_file = os.path.join(dest_root, new_file_name)
            shutil.copy2(src_file, dst_file)  # copy2保留元数据


def copy(sharedUser, user, sharedBookName, sceneName):
    # 1.记录是否重复
    realSharedBookName = sharedBookName
    count = 1  # 初始化计数器

    # 循环直到找到一个不重复的bookName
    while UserNotebook.objects.filter(username=sharedUser, bookName=realSharedBookName).exists():
        if sharedUser != user:
            realSharedBookName = f"{sharedBookName}Shared{count}"  # 添加计数器到bookName
            count += 1
        else:
            realSharedBookName = f"{sharedBookName}Copy{count}"  # 添加计数器到bookName
            count += 1
    # while UserNotebook.objects.filter(username=sharedUser, bookName=realSharedBookName).exists():
    #     realSharedBookName += "Shared"

    # 2.mysql数据库复制
    userBookItem = UserNotebook.objects.filter(username=user, bookName=sharedBookName)
    cardItems = Card.objects.filter(username=user + "_" + sharedBookName)

    if userBookItem.exists():
        # 获取第一条匹配的记录，按理应该只有一条，models里加了限制
        item = userBookItem.first()
        new_item = None
        if sharedUser != user:
            new_item = UserNotebook(
                username=sharedUser,
                bookName=realSharedBookName,
                bookId=int(datetime.now().timestamp() * 1000),
                bookdescription=item.bookdescription,
                sid=item.sid,
                isShared=1,
                comments=item.comments,
                context_data=item.context_data,
                writer=user,
                MayImgDocHLScore=item.MayImgDocHLScore,
                documentFourColorDMT=item.documentFourColorDMT,  # 🔥 复制文档四色DMT属性
                keywordFourColorDMT=item.keywordFourColorDMT,  # 🔥 复制关键词四色DMT属性
                documentPreSummaryStatus=item.documentPreSummaryStatus  # 🔥 复制文档预处理章节摘要状态
            )
        else:
            new_item = UserNotebook(
                username=sharedUser,
                bookName=realSharedBookName,
                bookId=int(datetime.now().timestamp() * 1000),
                bookdescription=item.bookdescription,
                sid=item.sid,
                isShared=0,
                comments=item.comments,
                context_data=item.context_data,
                writer=sharedUser,
                MayImgDocHLScore=item.MayImgDocHLScore,
                documentFourColorDMT=item.documentFourColorDMT,  # 🔥 复制文档四色DMT属性
                keywordFourColorDMT=item.keywordFourColorDMT,  # 🔥 复制关键词四色DMT属性
                documentPreSummaryStatus=item.documentPreSummaryStatus  # 🔥 复制文档预处理章节摘要状态
            )
        new_item.save()
    else:
        return None

    # 创建一个映射字典来记录旧cid到新cid的映射关系
    cid_mapping = {}

    if cardItems.exists():
        # 自己复制给自己也改为带上卡片
        if sharedUser != user or sharedUser == user:
            for item in cardItems:
                # 保存原始cid
                original_cid = item.cid

                # 创建新卡片
                new_card = Card(
                    username=sharedUser + "_" + realSharedBookName,  # 修改 username 字段
                    model_id=item.model_id,
                    status=item.status,
                    content=item.content,
                    title=item.title,
                    score=item.score,
                    time_params=item.time_params,
                    history=item.history,
                    seed=item.seed,
                    color=item.color,
                    reason=item.reason,
                    keyWords=item.keyWords,
                    contentTitle=item.contentTitle,
                    scoreSFT=item.scoreSFT,
                    colorSFT=item.colorSFT,
                    reasonSFT=item.reasonSFT,
                    type=item.type,
                    preIndex=item.preIndex,
                    postIndex=item.postIndex,
                    lastContent=item.lastContent,
                    writer=item.writer
                )
                new_card.save()

                # 保存映射关系: 原始cid -> 新cid
                cid_mapping[original_cid] = new_card.cid

    # 正则表达式，用于匹配“卡片”后跟一个或多个数字，直到遇到非数字字符
    title_pattern = re.compile(r'卡片(\d+(?:,\d+)*)')
    username_condition = sharedUser + "_" + realSharedBookName
    cardItemsTarget = Card.objects.filter(username=username_condition)

    for item in cardItemsTarget:
        # 🔥 更新postIndex和preIndex：将旧cid映射为新cid
        if item.postIndex:
            try:
                import json
                post_index_list = json.loads(item.postIndex)
                if isinstance(post_index_list, list):
                    # 将旧cid映射为新cid
                    updated_post_index = []
                    for old_cid in post_index_list:
                        new_cid = cid_mapping.get(old_cid, old_cid)  # 如果映射存在则使用新cid，否则保留原值
                        updated_post_index.append(new_cid)
                    item.postIndex = json.dumps(updated_post_index, ensure_ascii=False)
                    print(f"[copy] 更新卡片{item.cid}的postIndex: {json.loads(item.postIndex) if item.postIndex else []}")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                # 如果不是JSON格式或解析失败，尝试按字符串处理
                print(f"[copy] postIndex解析失败，尝试字符串替换: {e}")
                # 尝试简单的字符串替换（如果postIndex是逗号分隔的字符串）
                try:
                    post_index_str = item.postIndex
                    for old_cid, new_cid in cid_mapping.items():
                        post_index_str = post_index_str.replace(str(old_cid), str(new_cid))
                    item.postIndex = post_index_str
                except Exception as e2:
                    print(f"[copy] postIndex字符串替换也失败: {e2}")

        # 🔥 更新preIndex：将旧cid映射为新cid
        if item.preIndex:
            try:
                import json
                pre_index_list = json.loads(item.preIndex)
                if isinstance(pre_index_list, list):
                    # 将旧cid映射为新cid
                    updated_pre_index = []
                    for old_cid in pre_index_list:
                        new_cid = cid_mapping.get(old_cid, old_cid)
                        updated_pre_index.append(new_cid)
                    item.preIndex = json.dumps(updated_pre_index, ensure_ascii=False)
                    print(f"[copy] 更新卡片{item.cid}的preIndex: {json.loads(item.preIndex) if item.preIndex else []}")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                print(f"[copy] preIndex解析失败，尝试字符串替换: {e}")
                try:
                    pre_index_str = item.preIndex
                    for old_cid, new_cid in cid_mapping.items():
                        pre_index_str = pre_index_str.replace(str(old_cid), str(new_cid))
                    item.preIndex = pre_index_str
                except Exception as e2:
                    print(f"[copy] preIndex字符串替换也失败: {e2}")

        # 使用正则表达式搜索匹配的数字
        match = title_pattern.search(item.title)
        if match:
            # 提取数字字符串，然后将其分割为数字列表
            numbers_str = match.group(1)
            numbers = [int(num) for num in numbers_str.split(',')]

            # 对于每个数字，查找匹配的 Card 对象
            for number in numbers:
                # 查找 cid 等于 number 的 Card 对象
                original_card = Card.objects.filter(cid=number).first()
                if original_card and original_card.content:
                    # 确保 content 包含数字，如果包含，则找到对应的 Card 对象
                    matching_cards = Card.objects.filter(
                        username=username_condition,
                        content=original_card.content
                    )
                    if matching_cards.exists():
                        # 替换原标题中的数字为找到的 Card 的 cid
                        new_title = item.title.replace(str(number), str(matching_cards[0].cid))
                        item.title = new_title
                        # item.save()

        # 🔥 保存更新后的卡片（包括postIndex、preIndex和title）
        item.save()

    # 3.文件夹复制
    copyDir(sharedUser, user, sharedBookName, realSharedBookName, cid_mapping)  # 添加cid_mapping参数
    copyDirDMT(sharedUser, user, sharedBookName, realSharedBookName)

    # # 4.场景预置文档spilt向量库复制
    # parse_input.split_scene_to_user(sceneName, sharedUser+"_"+realSharedBookName)
    #
    # # 5.用户split向量库互相复制
    # parse_input.split_user_to_user(user+"_"+sharedBookName, sharedUser+"_"+realSharedBookName)

    # 4.5.场景预置文档spilt向量库复制 & 用户split向量库互相复制 - 并行处理
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        # 提交两个并行任务
        future1 = executor.submit(parse_input.split_scene_to_user,
                                  scene_name=sceneName, user_name=sharedUser + "_" + realSharedBookName)
        future2 = executor.submit(parse_input.split_user_to_user,
                                  user_from_name=user + "_" + sharedBookName,
                                  user_name=sharedUser + "_" + realSharedBookName)
        futures.extend([future1, future2])

        # 等待所有任务完成
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f'[copy] 并行处理时出错: {e}')

    # 6.复制数据库里与此本子内删除文件、人工记录、自动任务、文件自动结果状态记录
    src_id = user+"_"+sharedBookName
    target_id = sharedUser + "_" + realSharedBookName

    # 6.1 复制DeletedFile记录
    deleted_files = DeletedFile.objects.filter(username=src_id)
    for deleted_file in deleted_files:
        new_deleted_file = DeletedFile(
            username=target_id,  # 修改username字段
            filename=deleted_file.filename,
            delete_time=deleted_file.delete_time,
            scene_name=deleted_file.scene_name
        )
        new_deleted_file.save()

    # 6.2 复制AutomationRecord记录
    automation_records = AutomationRecord.objects.filter(notebook_id=src_id)
    for record in automation_records:
        new_record = AutomationRecord(
            notebook_id=target_id,  # 修改notebook_id字段
            step_number=record.step_number,
            action_type=record.action_type,
            action_data=record.action_data,
            target_file=record.target_file,
            times=record.times
            # timestamp会自动设置为当前时间
        )
        new_record.save()

    # 6.3 复制AutomationTask记录
    automation_tasks = AutomationTask.objects.filter(notebook_id=src_id)
    for task in automation_tasks:
        new_task = AutomationTask(
            notebook_id=target_id,  # 修改notebook_id字段
            target_file=task.target_file,
            status=task.status,
            current_step=task.current_step,
            total_steps=task.total_steps,
            error_message=task.error_message
            # created_at会自动设置为当前时间
        )
        new_task.save()

    # 6.4 复制AutomationStatus记录
    automation_statuses = AutomationStatus.objects.filter(notebook_id=src_id)
    for status in automation_statuses:
        # 使用get_or_create避免重复记录（因为有unique_together约束）
        new_status, created = AutomationStatus.objects.get_or_create(
            notebook_id=target_id,  # 修改notebook_id字段
            file_name=status.file_name,
            defaults={
                'status': status.status,
                'task_id': status.task_id
                # created_at和updated_at会自动设置
            }
        )
        if not created:
            # 如果记录已存在，更新其他字段
            new_status.status = status.status
            new_status.task_id = status.task_id
            new_status.save()

    # 6.5 复制DMTAnalysisTask记录
    # 定义源和目标的标识符
    src_username = f"{user}_{sharedBookName}"
    target_username = f"{sharedUser}_{realSharedBookName}"
    # 查询所有相关的DMTAnalysisTask记录
    dmt_tasks = DMTAnalysisTask.objects.filter(username=src_username)
    for task in dmt_tasks:
        # 替换各字段中的源标识符
        new_image_name = task.image_name.replace(src_username, target_username)
        new_config_file_name = task.config_file_name.replace(src_username, target_username)
        new_result_file = task.result_file.replace(src_username, target_username)

        # 创建新的DMTAnalysisTask记录
        new_task = DMTAnalysisTask(
            task_id=task.task_id + f"_copy_{target_username}",  # 生成新的唯一task_id
            username=target_username,  # 替换为目标username
            image_name=new_image_name,  # 替换后的image_name
            config_file_name=new_config_file_name,  # 替换后的config_file_name
            status=task.status,
            progress=task.progress,
            current_stage=task.current_stage,
            result_file=new_result_file,  # 替换后的result_file
            error_message=task.error_message
            # created_at和updated_at会自动设置
        )
        new_task.save()

    print(f"数据复制完成: {src_id} -> {target_id}")
    return


# 计算两个字符串的相似度
def calculate_similarity(str1, str2):
    """
    使用简单的字符重叠计算相似度
    返回0到1之间的值，1表示完全匹配
    """
    # 将字符串转换为集合以计算重叠
    set1 = set(str1)
    set2 = set(str2)

    # 计算重叠的字符
    overlap = len(set1.intersection(set2))

    # 计算相似度
    total = len(set1) + len(set2) - overlap  # 两个集合的并集大小

    # 避免除以零
    if total == 0:
        return 0

    return overlap / total
