from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('ankieta/start/', views.ankieta_start, name='ankieta_start'),
    path('ankieta/question/<int:question_number>/', views.ankieta_question, name='ankieta_question'),
    path('ankieta/done/', views.ankieta_done, name='ankieta_done'),
    path('form/', views.patient_form, name='patient_form'),
    # panel pielęgniarki
    # path('panel/', views.panel_home, name='panel_home'),
    # path('panel/results/', views.panel_results, name='panel_results'),
]