from django.db import models

class Card(models.Model):
    # 数据库自增id
    cid = models.AutoField(primary_key=True)
    # 产生日期时间
    datetime = models.DateTimeField(auto_now_add=True)
    # 用户名
    username = models.CharField(max_length=255)
    # 来自模型的id
    model_id = models.CharField(max_length=255)
    # 卡片状态
    status = models.CharField(max_length=50)
    # 卡片内容
    content = models.TextField()
    # 卡片标题
    title = models.CharField(max_length=255)
    # 卡片得分
    score = models.FloatField()
    # 卡片参数
    time_params = models.JSONField(null=True, blank=True)
    # 三轮对话
    history = models.JSONField(null=True, blank=True)
    # 卡片是否被处理过
    seed = models.IntegerField(default=0)
    # 卡片红蓝
    color = models.CharField(max_length=255, default="紫")
    # 卡片打分理由
    reason = models.TextField(default="")
    # 关键词
    keyWords = models.TextField(default="")
    # 卡片内容标题
    contentTitle = models.TextField(default="")
    # 微调红蓝评测模型卡片得分
    scoreSFT = models.FloatField(default=-1.0)
    # 微调红蓝评测模型卡片红蓝
    colorSFT = models.CharField(max_length=255, default="紫")
    # 微调红蓝评测模型卡片打分理由
    reasonSFT = models.TextField(default="")
    # 卡片类型闪念文献永久
    type = models.TextField(default="")
    # 前置索引
    preIndex = models.TextField(default="")
    # 后置索引
    postIndex = models.TextField(default="")
    # 上一版内容留存
    lastContent = models.TextField(default="")
    # 卡片作者（不同于所有者）
    writer = models.CharField(max_length=64, default="")
    # T->TA共生
    interGrowthT2TA = models.TextField(default="")
    # TA->GL共生
    interGrowthTA2GL = models.TextField(default="")
    # GL->GM共生
    interGrowthGL2GM = models.TextField(default="")
    # TA2GL问题的分区/ 每条问题回答的红蓝分和改进/ 5步建议
    subareaAndHLAndSugTA2GL = models.TextField(default="")
    # 问题评论
    question_comment = models.TextField(default="", blank=True, null=True)
    # 置信度评分（0-5分，null表示未评估）
    confidence_score = models.FloatField(null=True, blank=True, default=None)
    # 腐烂度评分（0-5分，越低越好，null表示未评估）
    rot_score = models.FloatField(null=True, blank=True, default=None)
    # 四色语境类型（R/B/P/G：红/蓝/紫/绿）
    four_color_type = models.CharField(max_length=1, default='', blank=True)
    # DMT层次（D/M/T：Down/Middle/Top）
    dmt_level = models.CharField(max_length=1, default='', blank=True)
    # 是否为神经元卡（每个场景最后一个子场景生成的卡片）
    is_neuron = models.BooleanField(default=False)
    # 是否为进化卡（通过卡片进化功能生成的卡片）
    is_evolved = models.BooleanField(default=False)
    # 被勾选次数（用于价值评估）
    selection_count = models.IntegerField(default=0)
    # 生成此卡片时勾选的文档列表（JSON格式）
    selected_docs = models.TextField(default='', blank=True)
    # 生成此卡片时的三窗口模型配置（JSON格式：{"main": modelId, "up": modelId, "down": modelId}）
    three_window_models = models.JSONField(null=True, blank=True)
    # 是否已经按照新要求做好四色/DMT分析和赋值
    is_analyzed_by_new_standard = models.BooleanField(default=False)

    def __str__(self):
        return self.titles


class BgCard(models.Model):
    cid = models.AutoField(primary_key=True)
    datetime = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    detail = models.CharField(max_length=255)
    content = models.TextField()
    def __str__(self):
        return self.name


class DeletedFile(models.Model):
    username = models.CharField(max_length=100)  # 用户名
    filename = models.CharField(max_length=255)  # 文件名
    delete_time = models.DateTimeField(auto_now_add=True)  # 删除时间
    scene_name = models.CharField(max_length=100)  # 场景名称

    class Meta:
        unique_together = ('username', 'filename', 'scene_name')  # 确保同一用户在同一场景下的文件记录唯一


class AutomationRecord(models.Model):
    """记录自动化操作流程"""
    notebook_id = models.CharField(max_length=255)  # username_bookName
    step_number = models.IntegerField()  # 步骤序号
    action_type = models.CharField(max_length=50)  # 操作类型
    action_data = models.JSONField()  # 操作详细数据
    timestamp = models.DateTimeField(auto_now_add=True)
    target_file = models.CharField(max_length=255, default='')  # 添加目标文件字段
    times = models.IntegerField(default=1)  # 新增：记录次数

    # class Meta:
    #     unique_together = ('notebook_id', 'times', 'step_number')


class AutomationTask(models.Model):
    """自动化任务状态"""
    notebook_id = models.CharField(max_length=255)
    target_file = models.CharField(max_length=255)  # 当前处理的文件
    status = models.CharField(max_length=20, default='pending')  # pending/running/success/failed
    current_step = models.IntegerField(default=0)
    total_steps = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    execution_state = models.JSONField(null=True, blank=True)  # 🔥 新增：保存执行状态以支持中断恢复


class AutomationStatus(models.Model):
    """保存每个文件的自动化执行状态"""
    notebook_id = models.CharField(max_length=255)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20)  # null/running/success/failed
    task_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('notebook_id', 'file_name')


class DMTAnalysisTask(models.Model):
    task_id = models.CharField(max_length=100, unique=True)
    username = models.CharField(max_length=100)
    image_name = models.CharField(max_length=255)
    config_file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default='pending')  # pending, processing, completed, failed
    progress = models.IntegerField(default=0)  # 0-100
    current_stage = models.CharField(max_length=50, default='')  # D分析, M分析, T分析
    result_file = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dmt_analysis_task'
