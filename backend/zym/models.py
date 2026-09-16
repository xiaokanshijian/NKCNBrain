from django.db import models
from django.db.models import UniqueConstraint
# Create your models here.
class UserNotebook(models.Model):
    username=models.CharField(max_length=64)    # 属于哪个用户名
    bookId=models.CharField(max_length=64)      # 其实是类似"1718611892973"这样的时间戳
    bookName=models.CharField(max_length=64)    # 本子名
    bookdescription=models.CharField(max_length=64)
    sid = models.IntegerField(default=1)        # 来自哪个场景sid
    isShared = models.IntegerField(default=0)   # 是否别人分享复制来的本子
    comments = models.TextField(default="")
    context_data = models.TextField(default="")  # 用于存储复杂的上下文数据
    writer = models.CharField(max_length=64, default="")    # 本子的作者是谁
    syncUsers = models.TextField(default="")    # 若非空则是群组共享本子，此字段是拥有群组本子查看权限的用户
    syncTodo = models.TextField(default="")     # 同上，此字段是需要完成问题打点的用户
    MayImgDocHLScore = models.TextField(default="")
    # 🔥 文档四色DMT属性信息（JSON格式：{"filename": {"main_four_color": "R", "secondary_four_color": "B", "dmt_level": "T"}}）
    documentFourColorDMT = models.TextField(default="")
    # 🔥 关键词四色DMT属性信息（JSON格式：{"关键词": {"four_color_type": "R", "dmt_level": "T"}}）
    keywordFourColorDMT = models.TextField(default="")
    # 🔥 文档预处理章节摘要状态（JSON格式：{"filename": true/false}，true表示已完成，false表示未处理）
    documentPreSummaryStatus = models.TextField(default="")
    # 🔥 问题链智能排序状态（Boolean，true表示已完成排序，false表示未排序）
    questionChainSorted = models.BooleanField(default=False)
    # 🔥 问题链排序后的CID顺序（JSON格式：["cid1", "cid2", ...]）
    questionChainSortedOrder = models.TextField(default="")
    # 🔥 问题链分类信息（JSON格式：{"分类名1": ["cid1", "cid2", ...], "分类名2": ["cid3", ...]}）
    questionChainCategories = models.TextField(default="")
    # 🔥 关键词融合关系（JSON格式：{"融合关键词": {"source_keywords": ["关键词1", "关键词2"], "created_at": "时间戳"}}）
    keywordFusionRelations = models.TextField(default="")

    class Meta:
        db_table = 'zym_usernotebook'  # 指定数据库中的表名
        constraints = [
            UniqueConstraint(fields=['username', 'bookName', 'sid'], name='zyr_unique_together_constraint')
        ]



# 记录用户和笔记本的对应关系

class scene(models.Model):
    sid = models.AutoField(primary_key=True)
    username = models.CharField(max_length=64)  # 0或1，表示此场景是否已发布
    sceneDescription = models.CharField(max_length=64)
    uploader = models.CharField(max_length=64, default='admin')