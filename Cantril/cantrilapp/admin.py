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
        'get_survey_title',
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

    def get_survey_title(self, obj):
        return obj.survey.title if obj.survey else obj.json_survey_id

    get_survey_title.short_description = 'Survey'



@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('order', 'short')
    ordering = ('order',)

    def short(self, obj):
        return str(obj)
    short.short_description = 'Question'
