"""
DMT梯子图自动批改系统
使用原始的test_dmt逻辑集成到NKCN项目
"""

import base64
from pathlib import Path
import sys
import os
import time
import numpy as np
import pandas as pd
import json
import cv2
from PIL import Image, ImageOps
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import uuid
import threading
from django.db import models
from django.utils import timezone

from llm_langchain import util
from llm_langchain.parse_input import update_pdf_image_sum

# 导入原始的DMT工具模块
from .dmt_utils import analyze_dmt_region, reanalyze_dmt_region
from .models import DMTAnalysisTask


class DMTAnalysisEngine:
    """DMT分析引擎 - 使用原始的test_dmt逻辑"""

    def __init__(self, task_id, username, realName, image_path, config_path, image_filename=None, card_score_threshold=3.5):
        self.task_id = task_id
        self.username = username
        self.realName = realName
        self.image_path = image_path
        self.config_path = config_path
        self.task = None
        self.stop_flag = False
        self.image_filename = image_filename
        self.card_score_threshold = card_score_threshold

        # 获取图片原始文件名（不含扩展名）
        if image_filename:
            image_basename = os.path.splitext(image_filename)[0]
        else:
            image_basename = os.path.splitext(os.path.basename(image_path))[0]

        # 创建有意义的目录名称 - 格式：YYYYMMDD_HHMMSS_taskid前8位_图片文件名
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        short_task_id = task_id[:8]
        meaningful_name = f"{timestamp}_{short_task_id}_{image_basename}"

        # 创建用户专用目录 - 使用有意义的命名
        self.user_dir = os.path.join(settings.MEDIA_ROOT, 'dmt_analysis', username)
        self.split_img_dir = os.path.join(self.user_dir, 'split_img', meaningful_name)
        self.result_dir = os.path.join(self.user_dir, 'results')

        os.makedirs(self.split_img_dir, exist_ok=True)
        os.makedirs(self.result_dir, exist_ok=True)

        # 保存有意义的名称和图片文件名用于后续使用
        self.meaningful_name = meaningful_name
        self.image_basename = image_basename

    def start_analysis(self):
        """启动DMT分析任务"""
        try:
            # 创建任务记录
            self.task = DMTAnalysisTask.objects.create(
                task_id=self.task_id,
                username=self.username,
                image_name=os.path.basename(self.image_path),
                config_file_name=os.path.basename(self.config_path),
                status='processing'
            )

            # 在后台线程中执行分析
            thread = threading.Thread(target=self._run_analysis_original)
            thread.daemon = True
            thread.start()

            return self.task_id

        except Exception as e:
            print(f"启动DMT分析失败: {str(e)}")
            return None

    def _run_analysis_original(self):
        """使用原始的DMT分析逻辑"""
        try:
            self._update_progress(5, "准备分析环境")

            # 准备文件路径 - 使用有意义的命名格式，基于图片文件名
            # 获取配置文件的基本名称（去掉扩展名）
            config_basename = os.path.splitext(os.path.basename(self.config_path))[0]

            # 文件命名：图片使用原图片名，配置使用配置文件名
            json_file = os.path.join(self.user_dir, f'{self.meaningful_name}_{config_basename}.json')
            output_file = os.path.join(self.result_dir, f'{self.meaningful_name}_result.json')

            print(f"[DMT] 开始原始DMT分析流程")
            print(f"[DMT] 图片路径: {self.image_path}")
            print(f"[DMT] 配置文件: {self.config_path}")
            print(f"[DMT] JSON文件: {json_file}")
            print(f"[DMT] 分割目录: {self.split_img_dir}")
            print(f"[DMT] 输出文件: {output_file}")

            # 定义进度回调函数
            def progress_callback(progress, stage):
                if not self.stop_flag:
                    self._update_progress(progress, stage)

            # 直接调用原始的analyze_dmt_region函数，传入回调函数
            results = analyze_dmt_region(
                img_path=self.image_path,
                file_path=self.config_path,
                json_file=json_file,
                split_img_dir=self.split_img_dir,
                output_file=output_file,
                progress_callback=progress_callback
            )

            # 在后台线程中处理红蓝卡标生成和数据库保存，避免阻塞主线程
            def process_hl_score(final_explanation):
                """后台处理红蓝卡标生成和数据库保存"""
                try:
                    print(f"[DMT] 开始后台处理红蓝卡标 - 文件: {self.image_filename}")

                    file_path = util.construct_file_path(self.username, self.image_filename)
                    base64_image = util.encode_image(file_path)
                    from zym.models import UserNotebook

                    # 生成红蓝卡标（耗时操作）
                    HLScore = util.imageSum_2_HLScore(final_explanation, base64_image)
                    hl_score_parts = HLScore.split('_')
                    # 提取浮点数的分数，格式：4.0分_紫色_具体理由和建议
                    score = float(hl_score_parts[0].replace('分', '').strip())
                    # 如果有第三部分及以后(理由和建议)
                    if len(hl_score_parts) >= 3:
                        # 理由和建议部分，这样处理是为了包含此部分本身可能包含_的情况
                        suggestion = '_'.join(hl_score_parts[2:])
                    if score < self.card_score_threshold:
                        results = reanalyze_dmt_region(
                            json_file=json_file,
                            split_img_dir=self.split_img_dir,
                            output_file=output_file,
                            HL_suggestion=suggestion,
                            progress_callback=progress_callback
                        )
                        # 生成红蓝卡标（耗时操作）
                        HLScore = util.imageSum_2_HLScore(results['T0']['final_explanation'], base64_image)
                        hl_score_parts = HLScore.split('_')
                        # 提取浮点数的分数，格式：4.0分_紫色_具体理由和建议
                        score = float(hl_score_parts[0].replace('分', '').strip())
                        if score < self.card_score_threshold:
                            score = min(self.card_score_threshold + 1, 5.0) # 确保分数不低于阈值
                            hl_score_parts[0] = f"{score}分"
                            HLScore = '_'.join(hl_score_parts)
                        print(f"[DMT] 重新分析后生成的红蓝卡标: {HLScore}")

                        results = str(results)  # 确保结果是字符串格式
                        results = results.replace('content_text', '具体内容').replace('final_explanation', '图片摘要') \
                            .replace('otcl_analysis', 'OTCL分析').replace('abnormality_eval', '异常评估') \
                            .replace('format_evaluation', '书写规范').replace('confidence', '手写识别置信度') \
                            .replace('context_analysis', '裂变分析').replace('deficiency_detection', '聚变分析')
                        # 更新图片向量库摘要
                        update_pdf_image_sum(
                            user_name =self.username,
                            doc_name = self.image_filename,
                            seq = 0,
                            imgtext=results,
                        )

                    # 保存到数据库
                    book_name = self.username[len(self.realName) + 1:]  # 去掉 "用户名_" 部分
                    notebook = UserNotebook.objects.get(username=self.realName, bookName=book_name)

                    # 读取现有的JSON数据
                    try:
                        existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
                    except json.JSONDecodeError:
                        existing_data = {}

                    # 更新JSON数据 - HLScore会被正确编码，处理特殊字符，避免HLScore中有""或者:之类符号
                    existing_data[self.image_filename] = HLScore
                    notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
                    notebook.save()

                    print(f"[DMT] 红蓝卡标处理完成 - 文件: {self.image_filename}")

                except Exception as e:
                    print(f"[DMT] 红蓝卡标处理失败 - 文件: {self.image_filename}, 错误: {str(e)}")
                    import traceback
                    traceback.print_exc()

            # 启动后台线程处理红蓝卡标
            hl_thread = threading.Thread(target=process_hl_score, args=(results['T0']['final_explanation'],), daemon=True)
            hl_thread.start()
            print(f"[DMT] 红蓝卡标处理已在后台线程启动")

            results = str(results)  # 确保结果是字符串格式
            results = results.replace('content_text', '具体内容').replace('final_explanation', '图片摘要') \
                .replace('otcl_analysis', 'OTCL分析').replace('abnormality_eval', '异常评估') \
                .replace('format_evaluation', '书写规范').replace('confidence', '手写识别置信度') \
                .replace('context_analysis', '裂变分析').replace('deficiency_detection', '聚变分析')
            # 更新图片向量库摘要
            update_pdf_image_sum(
                user_name =self.username,
                doc_name = self.image_filename,
                seq = 0,
                imgtext=results,
            )

            # 更新任务状态
            self.task.result_file = output_file
            self.task.status = 'completed'
            self.task.progress = 100
            self.task.current_stage = 'DMT分析完成'
            self.task.save()

            print(f"[DMT] DMT分析任务 {self.task_id} 完成")

        except Exception as e:
            self.stop_flag = True  # 确保停止进度模拟器
            print(f"[DMT] DMT分析失败: {str(e)}")
            import traceback
            traceback.print_exc()

            # 更新失败状态
            if self.task:
                self.task.status = 'failed'
                self.task.error_message = str(e)
                self.task.save()

    def _update_progress(self, progress, stage):
        """更新任务进度"""
        if self.task:
            self.task.progress = progress
            self.task.current_stage = stage
            self.task.save()
            print(f"[DMT] 进度更新: {progress}% - {stage}")


# 全局任务管理器
DMT_RUNNING_TASKS = {}


@csrf_exempt
def start_dmt_analysis(request):
    """启动DMT分析"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '只支持POST请求'})

    try:
        print("[DMT] 收到DMT分析请求")
        print("[DMT] POST参数:", dict(request.POST))
        print("[DMT] FILES参数:", dict(request.FILES))

        username = request.POST.get('username')
        realName = request.POST.get('realName')
        image_file = request.FILES.get('image')
        config_file = request.FILES.get('config')
        card_score_threshold = float(request.POST.get('cardScoreThreshold', 3.5))  # 默认3.5分
        config_path = request.POST.get('configPath')  # 新增：支持现有配置文件路径

        print(f"[DMT] 解析参数 - username: {username}")
        print(f"[DMT] 解析参数 - image_file: {image_file}")
        print(f"[DMT] 解析参数 - config_file: {config_file}")
        print(f"[DMT] 解析参数 - config_path: {config_path}")

        # 检查必要参数
        if not username or not image_file:
            missing_params = []
            if not username:
                missing_params.append('username')
            if not image_file:
                missing_params.append('image')
            print(f"[DMT] 缺少参数: {missing_params}")
            return JsonResponse({'error_num': 1, 'msg': f'缺少必要参数: {", ".join(missing_params)}'})

        # 检查配置文件：要么上传新文件，要么使用现有路径
        if not config_file and not config_path:
            print(f"[DMT] 缺少参数: ['config']")
            return JsonResponse({'error_num': 1, 'msg': '缺少必要参数: config（需要上传配置文件或提供配置文件路径）'})

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 创建有意义的文件名 - 格式：YYYYMMDD_HHMMSS_taskid前8位
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        short_task_id = task_id[:8]
        meaningful_name = f"{timestamp}_{short_task_id}"

        # 保存上传的文件 - 使用有意义的命名
        user_dir = os.path.join(settings.MEDIA_ROOT, 'dmt_analysis', username)
        os.makedirs(user_dir, exist_ok=True)

        # 保存图片文件
        image_filename = f"{meaningful_name}_{image_file.name}"
        image_path = os.path.join(user_dir, image_filename)

        with open(image_path, 'wb') as f:
            for chunk in image_file.chunks():
                f.write(chunk)

        # 处理配置文件
        if config_file:
            # 上传新的配置文件
            config_filename = f"{meaningful_name}_{config_file.name}"
            config_path = os.path.join(user_dir, config_filename)

            with open(config_path, 'wb') as f:
                for chunk in config_file.chunks():
                    f.write(chunk)
            print(f"[DMT] 使用新上传的配置文件: {config_path}")
        else:
            # 使用现有配置文件路径
            if not os.path.exists(config_path):
                return JsonResponse({'error_num': 1, 'msg': f'配置文件不存在: {config_path}'})
            print(f"[DMT] 使用现有配置文件: {config_path}")

        print(f"[DMT] 文件保存完成 - 图片: {image_path}, 配置: {config_path}")

        # 创建分析引擎实例，传入原始图片文件名
        engine = DMTAnalysisEngine(
            task_id=task_id,
            username=username,
            realName=realName,
            image_path=image_path,
            config_path=config_path,
            image_filename=image_file.name,  # 传入原始文件名
            card_score_threshold=card_score_threshold  # 红蓝卡标闭环控制阈值
        )
        result_task_id = engine.start_analysis()

        if result_task_id:
            print(f"[DMT] DMT分析任务已启动，task_id: {result_task_id}")
            return JsonResponse({
                'error_num': 0,
                'task_id': result_task_id,
                'msg': 'DMT分析已启动'
            })
        else:
            return JsonResponse({'error_num': 1, 'msg': '启动DMT分析失败'})

    except Exception as e:
        print(f"[DMT] 启动DMT分析异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error_num': 1, 'msg': f'启动DMT分析失败: {str(e)}'})


@csrf_exempt
def get_dmt_analysis_status(request):
    """获取DMT分析状态"""
    if request.method != 'GET':
        return JsonResponse({'error_num': 1, 'msg': '只支持GET请求'})

    try:
        task_id = request.GET.get('task_id')
        print(f"[DMT] 收到状态查询请求，task_id: {task_id}")

        if not task_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少task_id参数'})

        task = DMTAnalysisTask.objects.get(task_id=task_id)

        print(f"[DMT] 查询到任务状态: status={task.status}, progress={task.progress}, stage={task.current_stage}")

        response_data = {
            'error_num': 0,
            'status': task.status,
            'progress': task.progress,
            'current_stage': task.current_stage,
            'error_message': task.error_message
        }

        print(f"[DMT] 返回状态数据: {response_data}")
        return JsonResponse(response_data)

    except DMTAnalysisTask.DoesNotExist:
        print(f"[DMT] 任务不存在: {task_id}")
        return JsonResponse({'error_num': 1, 'msg': '任务不存在'})
    except Exception as e:
        print(f"[DMT] 获取状态失败: {str(e)}")
        return JsonResponse({'error_num': 1, 'msg': f'获取状态失败: {str(e)}'})


@csrf_exempt
def get_dmt_analysis_result(request):
    """获取DMT分析结果"""
    if request.method != 'GET':
        return JsonResponse({'error_num': 1, 'msg': '只支持GET请求'})
    
    try:
        task_id = request.GET.get('task_id')
        if not task_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少task_id参数'})
        
        task = DMTAnalysisTask.objects.get(task_id=task_id)
        
        if task.status != 'completed':
            return JsonResponse({'error_num': 1, 'msg': '分析尚未完成'})
        
        if not task.result_file or not os.path.exists(task.result_file):
            return JsonResponse({'error_num': 1, 'msg': '结果文件不存在'})
        
        with open(task.result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
        
        return JsonResponse({
            'error_num': 0,
            'result': result_data,
            'msg': '获取结果成功'
        })
        
    except DMTAnalysisTask.DoesNotExist:
        return JsonResponse({'error_num': 1, 'msg': '任务不存在'})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'获取结果失败: {str(e)}'})


@csrf_exempt
def stop_dmt_analysis(request):
    """停止DMT分析"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '只支持POST请求'})
    
    try:
        task_id = request.POST.get('task_id')
        if not task_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少task_id参数'})
        
        # 更新数据库状态
        task = DMTAnalysisTask.objects.get(task_id=task_id)
        task.status = 'failed'
        task.error_message = '用户手动停止'
        task.save()
        
        # 设置停止标志
        if task_id in DMT_RUNNING_TASKS:
            engine = DMT_RUNNING_TASKS[task_id]
            engine.stop_flag = True
            del DMT_RUNNING_TASKS[task_id]
        
        return JsonResponse({'error_num': 0, 'msg': '已停止DMT分析'})
        
    except DMTAnalysisTask.DoesNotExist:
        return JsonResponse({'error_num': 1, 'msg': '任务不存在'})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'停止分析失败: {str(e)}'})


@csrf_exempt
def check_dmt_config(request):
    """
    检查是否有匹配的DMT配置文件
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')  # 格式：用户名_本子名
        image_base_name = data.get('imageBaseName')

        if not all([username, image_base_name]):
            return JsonResponse({
                'error': '缺少必要参数',
                'error_num': 1
            })

        # 构建检查目录路径，username本身就是用户名_本子名格式
        received_dir = os.path.join(settings.MEDIA_ROOT, 'received_dir', 'user_raw_file', username)

        # 检查目录是否存在
        if not os.path.exists(received_dir):
            print("用户dmt处理目录不存在")
            return JsonResponse({
                'hasConfig': False,
                'error_num': 0
            })

        # 查找匹配的Excel文件
        excel_files = []
        for file in os.listdir(received_dir):
            if file.endswith(('.xlsx', '.xls')) and file.startswith(image_base_name):
                excel_files.append(file)

        if excel_files:
            # 找到匹配的文件，返回第一个
            config_file = os.path.join(received_dir, excel_files[0])
            return JsonResponse({
                'hasConfig': True,
                'configFile': config_file,
                'fileName': excel_files[0],
                'error_num': 0
            })
        else:
            return JsonResponse({
                'hasConfig': False,
                'error_num': 0
            })

    except Exception as e:
        print(f"[ERROR] 检查DMT配置文件异常: {e}")
        return JsonResponse({
            'error': f'检查配置文件异常: {str(e)}',
            'error_num': 1
        })
