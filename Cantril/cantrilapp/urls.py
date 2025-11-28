from django.urls import path
from . import views

urlpatterns = [
    # Strona startowa
    path('', views.home, name='home'),

    # Ścieżki dla pacjenta (Ankieta)
    path('ankieta/start/', views.ankieta_start, name='ankieta_start'),
    path('ankieta/question/<int:question_number>/', views.ankieta_question, name='ankieta_question'),
    path('ankieta/done/', views.ankieta_done, name='ankieta_done'),

    # Stary formularz (opcjonalny)
    path('form/', views.patient_form, name='patient_form'),

    # --- NOWOŚĆ: Generator ankiety dla lekarza ---
    # To połączy adres /generator/ z widokiem manage_questions w views.py
    path('generator/', views.manage_questions, name='manage_questions'),

    # panel pielęgniarki (zakomentowane - na przyszłość)
    # path('panel/', views.panel_home, name='panel_home'),
    # path('panel/results/', views.panel_results, name='panel_results'),
]