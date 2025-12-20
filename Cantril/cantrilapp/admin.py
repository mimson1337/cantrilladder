from django.contrib import admin
from .models import Patient, PatientResponse, Question


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('pesel', 'first_name', 'last_name', 'date_of_birth', 'created_at')
    search_fields = ('pesel', 'first_name', 'last_name')


@admin.register(PatientResponse)
class PatientResponseAdmin(admin.ModelAdmin):
    list_display = (
        'get_pesel',
        'survey_id',        # zamiast 'survey'
        'question_id',      # zamiast 'question'
        'response_type',
        'scale_value',
        'evaluated_score',
        'is_processed',
        'created_at',
    )
    list_filter = ('response_type', 'is_processed')
    search_fields = ('patient__pesel',)

    def get_pesel(self, obj):
        return obj.patient.pesel

    get_pesel.short_description = 'PESEL'



@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('order', 'short')
    ordering = ('order',)

    def short(self, obj):
        return str(obj)
    short.short_description = 'Question'
