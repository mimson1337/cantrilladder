import json
import os
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django import forms
from django.conf import settings  # Potrzebne do ścieżki pliku
from .models import Patient, PatientResponse
from django.contrib import messages

# =====================
# Konfiguracja pliku JSON
# =====================
QUESTION_FILE_PATH = os.path.join(settings.BASE_DIR, 'ankieta_pytania.json')


def get_questions_from_json():
    """Funkcja pomocnicza: wczytuje pytania z pliku lub zwraca domyślne."""
    default_questions = [
        "Jak oceniasz swój nastrój?",
        "Jak oceniasz poziom energii?",
        "Jak oceniasz poziom stresu?"
    ]

    if os.path.exists(QUESTION_FILE_PATH):
        try:
            with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('questions', default_questions)
        except json.JSONDecodeError:
            return default_questions
    return default_questions


# =====================
# Formularz PESEL
# =====================
class PeselForm(forms.Form):
    pesel = forms.CharField(max_length=11, label='PESEL')


# =====================
# Widok: Generator dla LEKARZA
# =====================
def manage_questions(request):
    """To jest widok edytora ankiety dla lekarza"""

    # 1. ZAPIS (POST)
    if request.method == 'POST':
        questions_list = request.POST.getlist('questions')
        # Usuwamy puste pola i spacje
        clean_questions = [q for q in questions_list if q.strip()]

        data = {
            "title": request.POST.get('title', 'Ankieta Cantrila'),
            "questions": clean_questions
        }

        with open(QUESTION_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        # --- ZMIANY TUTAJ ---
        # Dodajemy komunikat o sukcesie
        messages.success(request, '✅ Ankieta została pomyślnie zapisana!')

        # Przekierowujemy na stronę główną
        return redirect('home')

    # 2. ODCZYT (GET)
    initial_data = {"questions": [""]}
    if os.path.exists(QUESTION_FILE_PATH):
        try:
            with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                initial_data = json.load(f)
        except json.JSONDecodeError:
            pass

    # Używamy 'cantrilapp/generator.html' (jeśli naprawiłeś foldery)
    # lub 'generator.html' (jeśli plik jest bezpośrednio w templates)
    # Zostawiam tak jak miałeś w ostatnim działającym screenie:
    return render(request, 'generator.html', {
        'data': initial_data
    })


# =====================
# Widok: Strona główna
# =====================
def home(request):
    return render(request, 'home.html')


# =====================
# Start ankiety (Logika Pacjenta)
# =====================
def ankieta_start(request):
    if request.method == 'POST':
        form = PeselForm(request.POST)
        if form.is_valid():
            pesel = form.cleaned_data['pesel']

            # Szukamy pacjenta lub tworzymy nowego
            try:
                patient = Patient.objects.get(pesel=pesel)
                # Sprawdzamy czy ma już jakieś odpowiedzi
                po_badaniu = PatientResponse.objects.filter(patient=patient).exists()
            except Patient.DoesNotExist:
                patient = Patient.objects.create(pesel=pesel)
                po_badaniu = False

            request.session['patient_id'] = patient.id
            request.session['po_badaniu'] = po_badaniu
            request.session['answers'] = {}

            return redirect('ankieta_question', question_number=1)
    else:
        form = PeselForm()
    return render(request, 'ankieta_start.html', {'form': form})


# =====================
# Pytania ankiety (Dynamiczne z JSON)
# =====================
def ankieta_question(request, question_number):
    question_number = int(question_number)
    patient_id = request.session.get('patient_id')

    # Pobieramy aktualną listę pytań z pliku JSON
    current_questions = get_questions_from_json()
    total_questions = len(current_questions)

    # Zabezpieczenie: jeśli nie ma ID pacjenta w sesji, wracamy do startu
    if not patient_id:
        return redirect('ankieta_start')

    patient = Patient.objects.get(id=patient_id)

    # --- KONIEC ANKIETY ---
    if question_number > total_questions:
        answers = request.session.get('answers', {})

        # Zapisujemy odpowiedzi do bazy
        for q_num_str, answer in answers.items():
            idx = int(q_num_str) - 1

            # Pobieramy TREŚĆ pytania, żeby wiedzieć czego dotyczyła ocena
            # (Ważne, bo lekarz może zmienić kolejność pytań w przyszłości)
            if 0 <= idx < len(current_questions):
                context_text = current_questions[idx]
            else:
                context_text = f"Pytanie {q_num_str}"

            PatientResponse.objects.create(
                patient=patient,
                score=int(answer),
                context=context_text,  # Zapisujemy treść pytania, a nie tylko numer
                notes='',
                is_synced_with_his=False
            )

        request.session.flush()
        return render(request, 'ankieta_done.html')

    # --- WYŚWIETLANIE PYTANIA ---
    # Pobieramy treść konkretnego pytania (indeks to numer - 1)
    question_text = current_questions[question_number - 1]

    if request.method == 'POST':
        answer = request.POST.get('answer')
        if not answer:
            return render(request, 'ankieta_question.html', {
                'question': question_text,
                'question_number': question_number,
                'total_questions': total_questions,
                'error': 'Proszę udzielić odpowiedzi'
            })

        request.session['answers'][str(question_number)] = answer
        request.session.modified = True

        return redirect('ankieta_question', question_number=question_number + 1)

    return render(request, 'ankieta_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': total_questions
    })


# =====================
# Zakończenie ankiety
# =====================
def ankieta_done(request):
    return render(request, 'ankieta_done.html')


# =====================
# Formularz /admin (Stary kod, opcjonalny)
# =====================
@csrf_exempt
def patient_form(request):
    if request.method == 'POST':
        # Tutaj musiałbyś dostosować logikę do modelu Patient, 
        # jeśli nadal używasz tego widoku ręcznego wprowadzania
        return render(request, 'form.html', {'message': 'Funkcja wyłączona w tym przykładzie'})
    return render(request, 'form.html')