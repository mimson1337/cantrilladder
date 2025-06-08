from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('ankieta/start/', views.ankieta_start, name='ankieta_start'),
    path('ankieta/question/<int:question_number>/', views.ankieta_question, name='ankieta_question'),
    path('ankieta/done/', views.ankieta_done, name='ankieta_done'),  # widok podsumowania
]
