from django.db import models

class PatientResponse(models.Model):
    CONTEXT_CHOICES = [
        ('admission', 'Przyjęcie'),
        ('discharge', 'Wypis'),
        ('followup', 'Follow-up'),
    ]

    pesel = models.CharField(max_length=11)
    score = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    context = models.CharField(max_length=20, choices=CONTEXT_CHOICES)
    notes = models.TextField(blank=True, null=True)
    is_synced_with_his = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.pesel} ({self.score}) {self.context}"
