from django.urls import path
from . import views

urlpatterns = [
    # Strona startowa
    path('', views.home, name='home'),

    # Ścieżki dla pacjenta (Ankieta) - nowy wybór trybu i rozdzielone flow
    path('ankieta/start/', views.ankieta_choice, name='ankieta_choice'),
    path('ankieta/cantril/question/<int:question_number>/', views.ankieta_cantril_question, name='ankieta_cantril_question'),
    path('ankieta/voice/question/<int:question_number>/', views.ankieta_voice_question, name='ankieta_voice_question'),
    path('ankieta/done/', views.ankieta_done, name='ankieta_done'),

    # Stary formularz (opcjonalny)
    path('form/', views.patient_form, name='patient_form'),

    # --- NOWOŚĆ: Generator ankiety dla lekarza ---
    # To połączy adres /generator/ z widokiem manage_questions w views.py
    path('generator/', views.manage_questions, name='manage_questions'),
    # Panel lekarza
    path('panel/', views.panel_home, name='panel_home'),
    path('panel/results/', views.panel_results, name='panel_results'),
    path('panel/history/', views.panel_history, name='panel_history'),
    path('panel/patient/<int:patient_id>/history/', views.panel_patient_history, name='panel_patient_history'),

    # Webhook endpoint for n8n results
    path('webhook/n8n/results/', views.n8n_results_webhook, name='n8n_results_webhook'),
]