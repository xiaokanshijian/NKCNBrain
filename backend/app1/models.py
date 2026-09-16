# from __future__ import unicode_literals
from django.db import models


# Create your models here.

class User(models.Model):
    username = models.CharField(max_length=64)
    password = models.CharField(max_length=64)
    allowed = models.IntegerField(default=0)
    coacher = models.CharField(max_length=64, default='admin')
    level = models.CharField(max_length=64, default='GM')
    controlled = models.IntegerField(default=0)
    choose = models.IntegerField(default=0)  # 登录时选择：内心独白、听说对话、简构简用、深构深用
    system_mode = models.IntegerField(default=0)  # System选择：0=System2慢思考，1=System1快思考

    def __str__(self):
        return self.username


class UserSceneParams(models.Model):
    # 数据库自增id
    uspid = models.AutoField(primary_key=True)
    username = models.CharField(max_length=64)
    sid = models.CharField(max_length=64)
    usparams = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.username