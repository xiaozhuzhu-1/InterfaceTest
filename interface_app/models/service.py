from django.db import models

class Service(models.Model):
    project_id = models.IntegerField('project_id', db_index=True)
    name = models.CharField('name',max_length=255,null=False)
    description = models.TextField('描述')