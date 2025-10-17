# menu/models.py
from django.db import models

class ExternalUser(models.Model):
    moodle_uid = models.CharField(max_length=255)
    isTeacher = models.BooleanField()

    class Meta:
        managed = False  # Django no crea ni migra esta tabla
        db_table = 'users'  # nombre real de la tabla en la DB externa
