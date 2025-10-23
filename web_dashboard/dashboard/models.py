# menu/models.py
from django.db import models

class ExternalUser(models.Model):
    id = models.AutoField(primary_key=True)
    matrix_id = models.TextField(unique=True)
    moodle_id = models.IntegerField()
    is_teacher = models.BooleanField(default=False)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False  # Django no crea ni migra esta tabla
        db_table = 'users'  # nombre real de la tabla en la DB externa

    def __dict__(self):
        return {
            'id': self.id,
            'matrix_id': self.matrix_id,
            'moodle_id': self.moodle_id,
            'is_teacher': self.is_teacher,
            'registered_at': self.registered_at.isoformat(),
            'username': self.matrix_id.split(":")[0][1:]  # extrae el nombre de usuario del matrix_id
        }

    def __str__(self):
        return self.matrix_id

class Room(models.Model):
    id = models.AutoField(primary_key=True)
    room_id = models.TextField(unique=True)
    moodle_course_id = models.IntegerField()
    teacher_id = models.IntegerField()  # references your external users table
    shortcode = models.TextField()
    moodle_group = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False  # Django no crea ni migra esta tabla
        db_table = 'rooms'
        constraints = [
            models.UniqueConstraint(fields=['teacher_id', 'shortcode'], name='unique_teacher_shortcode')
        ]

    def __str__(self):
        return f"{self.shortcode} (course {self.moodle_course_id})"
    
class Reaction(models.Model):
    id = models.AutoField(primary_key=True)
    teacher_id = models.IntegerField()
    student_id = models.IntegerField()
    room_id = models.IntegerField()
    emoji = models.TextField()
    count = models.IntegerField(default=1)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'reactions'
        constraints = [
            models.UniqueConstraint(fields=['teacher_id', 'student_id', 'emoji'], name='unique_reaction')
        ]

    def __str__(self):
        return f"{self.emoji} x{self.count} (teacher={self.teacher_id}, student={self.student_id})"

