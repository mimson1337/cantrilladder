import uuid
from django.db import models


class Patient(models.Model):
    pesel = models.CharField(max_length=11, unique=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pesel} {self.first_name} {self.last_name}"


class Survey(models.Model):
    LADDER_DESIGNS = [
        ('classic', 'Klasyczny - Niebieski gradient'),
        ('gradient', 'Gradient - Dynamiczny'),
        ('minimal', 'Minimalistyczny - Prosty'),
        ('circular', 'Okrągły - Nowoczesny'),
        ('modern', 'Nowoczesny - Śmiały'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    ladder_design = models.CharField(max_length=20, choices=LADDER_DESIGNS, default='classic')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title



class Question(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    order = models.PositiveIntegerField()
    # scale_labels: JSON in format {"min": "Bardzo słaby", "max": "Bardzo dobry"}
    scale_labels = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.order}. {self.text[:50]}"


# cantrilapp/models.py

class PatientResponse(models.Model):
    RESPONSE_TYPE = (
        ('scale', 'Scale 1-10'),
        ('text', 'Text'),
        ('audio', 'Audio'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='responses')
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses', null=True, blank=True)
    json_survey_id = models.CharField(max_length=100, null=True, blank=True)  # JSON survey ID (legacy)
    question_id = models.CharField(max_length=100) # ID pytania z JSON

    response_type = models.CharField(max_length=10, choices=RESPONSE_TYPE)
    scale_value = models.FloatField(null=True, blank=True)
    text_answer = models.TextField(null=True, blank=True)
    # store the question text at the time of response to keep history stable
    question_text = models.TextField(null=True, blank=True)
    audio_file = models.FileField(upload_to='audio_answers/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # dane z n8n
    transcript = models.TextField(blank=True)
    evaluated_score = models.FloatField(null=True, blank=True)
    is_processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.patient.pesel} | {self.json_survey_id or self.survey.title if self.survey else 'N/A'} | {self.question_id}"
