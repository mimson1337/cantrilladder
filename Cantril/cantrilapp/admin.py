from django.contrib import admin
from .models import PatientResponse

@admin.register(PatientResponse)
class PatientResponseAdmin(admin.ModelAdmin):
    list_display = ('pesel', 'score', 'context', 'timestamp', 'is_synced_with_his')
    list_filter = ('context', 'is_synced_with_his')
    search_fields = ('pesel',)
