from django.contrib import admin
from .models import Patient, PatientResponse

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('pesel', 'first_name', 'last_name', 'date_of_birth', 'created_at')
    search_fields = ('pesel', 'first_name', 'last_name')

@admin.register(PatientResponse)
class PatientResponseAdmin(admin.ModelAdmin):
    list_display = ('get_pesel', 'score', 'context', 'timestamp', 'is_synced_with_his')
    list_filter = ('context', 'is_synced_with_his')
    search_fields = ('patient__pesel',)

    def get_pesel(self, obj):
        return obj.patient.pesel
    get_pesel.short_description = 'PESEL'
