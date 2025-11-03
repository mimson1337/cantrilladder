from django.db import models

class Patient(models.Model):
    pesel = models.CharField(max_length=11, unique=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pesel} {self.first_name} {self.last_name}"

class PatientResponse(models.Model):
    CONTEXT_CHOICES = [
        ('admission', 'Przyjęcie'),
        ('discharge', 'Wypis'),
        ('followup', 'Follow-up'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='responses')
    score = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    context = models.CharField(max_length=20, choices=CONTEXT_CHOICES)
    notes = models.TextField(blank=True, null=True)
    is_synced_with_his = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.patient.pesel} ({self.score}) {self.context}"
