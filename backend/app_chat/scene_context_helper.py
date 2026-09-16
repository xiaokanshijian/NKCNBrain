"""
场景上下文辅助工具
用于获取场景信息、场景摘要、本子描述等信息，用于DMT和四色判定
"""
import json
import os
from zym.models import UserNotebook, scene
from zym.util import calculate_similarity


def get_scene_summary(scene_name, sub_scene_name=None):
    """
    从summary.json获取场景和子场景的摘要信息
    返回：场景摘要、子场景摘要（如果提供）
    """
    try:
        summary_file_path = './received_dir/summary.json'
        if not os.path.exists(summary_file_path):
            return "", ""
        
        with open(summary_file_path, 'r', encoding='utf-8') as f:
            all_summaries = json.load(f)
        
        scene_match = None
        subscene_match = None
        
        # 寻找精确匹配的场景
        for s in all_summaries:
            if s.get("scene") == scene_name:
                scene_match = s
                break
        
        # 如果找不到精确匹配的场景，寻找最相似的场景
        if scene_match is None:
            max_similarity = 0
            for s in all_summaries:
                similarity = calculate_similarity(scene_name, s.get("scene", ""))
                if similarity > max_similarity:
                    max_similarity = similarity
                    scene_match = s
        
        # 获取场景摘要
        scene_summary = scene_match.get("summary", "") if scene_match else ""
        
        # 如果提供了子场景名，尝试获取子场景摘要
        subscene_summary = ""
        if sub_scene_name and scene_match:
            for sub in scene_match.get("subscenes", []):
                if sub.get("subscene") == sub_scene_name:
                    subscene_summary = sub.get("summary", "")
                    break
            
            # 如果找不到精确匹配，寻找最相似的子场景
            if not subscene_summary and scene_match.get("subscenes"):
                max_similarity = 0
                for sub in scene_match.get("subscenes", []):
                    similarity = calculate_similarity(sub_scene_name, sub.get("subscene", ""))
                    if similarity > max_similarity:
                        max_similarity = similarity
                        subscene_summary = sub.get("summary", "")
        
        # 优先返回子场景摘要，如果没有则返回场景摘要
        final_summary = subscene_summary if subscene_summary else scene_summary
        
        return scene_summary, final_summary
    except Exception as e:
        print(f"[scene_context_helper] 获取场景摘要失败: {e}")
        return "", ""


def get_notebook_description(username, scene_name=None):
    """
    获取本子的描述信息（bookdescription）
    参数：
        username: 用户名（可能是"用户名_本子名"格式）
        scene_name: 场景名（可选，用于查找）
    返回：本子描述（bookdescription）
    """
    try:
        # 解析username
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        
        # 如果没有从username解析出bookName，尝试通过scene_name查找
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass
        
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                return notebook.bookdescription
            except:
                pass
        
        return ""
    except Exception as e:
        print(f"[scene_context_helper] 获取本子描述失败: {e}")
        return ""


def get_scene_info_from_username(username, content_title=None):
    """
    从username获取场景信息
    返回：(scene_name, sub_scene_name, scene_summary, notebook_description)
    
    Args:
        username: 用户名（可能是"用户名_本子名"格式）
        content_title: 卡片标题（可选，用于提取子场景信息，格式：S1:标题）
    """
    try:
        from zym.models import UserNotebook, scene
        import re
        import os
        import pandas as pd
        
        # 解析username
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        
        scene_name = None
        sub_scene_name = None
        notebook_description = ""
        
        # 通过UserNotebook查找场景信息
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                notebook_description = notebook.bookdescription
                # 通过sid查找场景
                scene_obj = scene.objects.get(sid=notebook.sid)
                scene_name = scene_obj.sceneDescription
            except:
                pass
        else:
            # 如果没有book_name，尝试通过realName查找最近的notebook
            try:
                notebook = UserNotebook.objects.filter(username=realName).first()
                if notebook:
                    notebook_description = notebook.bookdescription
                    scene_obj = scene.objects.get(sid=notebook.sid)
                    scene_name = scene_obj.sceneDescription
            except:
                pass
        
        # 🔥 如果提供了content_title，尝试提取子场景名
        if content_title and scene_name:
            try:
                # 从contentTitle提取子场景编号（格式：S1:标题 或 S2:标题）
                subscene_match = re.search(r'^S(\d+)[:：]', content_title)
                if subscene_match:
                    subscene_index = int(subscene_match.group(1))  # S1 -> 1, S2 -> 2, etc.
                    
                    # 从prompt.xlsx读取子场景名列表
                    sceneDirPath = './received_dir/scene_excel/' + scene_name
                    if os.path.exists(sceneDirPath):
                        secenExcelPath = os.path.join(sceneDirPath, 'prompt.xlsx')
                        if os.path.exists(secenExcelPath):
                            try:
                                excel_data = pd.read_excel(secenExcelPath, sheet_name='LUI1')
                                subSceneCol = 1
                                firstSubSceneColName = excel_data.columns[subSceneCol]
                                subSceneNameListOrder = excel_data.iloc[:, 1].dropna().tolist()
                                subSceneNameListOrder.insert(0, firstSubSceneColName)
                                
                                # 根据编号获取子场景名（索引从1开始，S1对应索引0）
                                if subscene_index > 0 and subscene_index <= len(subSceneNameListOrder):
                                    sub_scene_name = subSceneNameListOrder[subscene_index - 1]
                                    print(f"[scene_context_helper] 从contentTitle提取子场景名: {sub_scene_name}")
                            except Exception as e:
                                print(f"[scene_context_helper] 读取prompt.xlsx获取子场景名失败: {e}")
            except Exception as e:
                print(f"[scene_context_helper] 从contentTitle提取子场景信息失败: {e}")
        
        # 获取场景摘要（如果提供了子场景名，会获取子场景摘要）
        scene_summary_info, subscene_summary_info = get_scene_summary(scene_name or "", sub_scene_name)
        final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        
        return scene_name or "", sub_scene_name or "", final_scene_summary, notebook_description
    except Exception as e:
        print(f"[scene_context_helper] 从username获取场景信息失败: {e}")
        return "", "", "", ""


def get_scene_four_color_examples(scene_name):
    """
    根据场景名获取该场景下四色的示例内涵
    参考：场景化应用_四色主体性适配.html
    返回：四色在该场景下的示例描述（用于prompt）
    """
    # 根据场景名匹配不同的场景类型
    scene_name_lower = scene_name.lower()
    
    # 体联场景
    if '体联' in scene_name or '升维示范' in scene_name:
        return {
            'R': 'DRG健康筛分（专业医疗分组术语）',
            'B': '代码、文档、GIT（技术工具与协作手段）',
            'P': '人体五时·年轮（生命周期思维框架）',
            'G': 'PSI、三零压（身体感知的通俗类比）'
        }
    
    # 纸联场景
    elif '纸联' in scene_name:
        return {
            'R': '交互纸张·群组认知（协作领域专业概念）',
            'B': '介质联通、代码、文档、GIT、微版面光标/输入法（多样化工具集成）',
            'P': '微版面·筛分手势（交互设计思维框架）',
            'G': '同学笔记·数字文具/教具（教育场景的日常类比）'
        }
    
    # 真实目标场景
    elif '真实目标' in scene_name:
        return {
            'R': 'VUCA·Aigle（复杂环境管理术语）',
            'B': 'SMART、OKR、红O/蓝O（目标管理工具矩阵）',
            'P': '开放、不确定、流变连接·共生·空石（复杂性思维框架）',
            'G': '凸透镜、火力/水力发电、DNA（物理生物的深刻类比）'
        }
    
    # 都江堰场景
    elif '都江堰' in scene_name:
        return {
            'R': '四六分水·二八分沙（水利工程专业比例）',
            'B': '卧铁、马桩、竹笼、闸、库（具体工程技术手段）',
            'P': '选址&借势，溪洄渡·低作堰（系统工程思维框架）',
            'G': '鱼嘴·飞沙堰·宝瓶口·岁修（形象化的自然语言）'
        }
    
    # 默认示例
    else:
        return {
            'R': '专业术语、行业规范、权威标准',
            'B': '技术工具、方法、手段、效率提升方式',
            'P': '逻辑框架、抽象模型、认知框架',
            'G': '自然语言、情感共鸣、人文关怀'
        }

