from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import PatientResponse
from datetime import datetime
from django.shortcuts import render, redirect

@csrf_exempt
def submit_response(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            PatientResponse.objects.create(
                pesel=data['pesel'],
                score=data['score'],
                context=data['context'],
                notes=data.get('notes', '')
            )
            return JsonResponse({'status': 'success'}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)


from django.shortcuts import render
from .models import PatientResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def patient_form(request):
    if request.method == 'POST':
        pesel = request.POST.get('pesel')
        score = request.POST.get('score')
        context = request.POST.get('context')
        notes = request.POST.get('notes')

        PatientResponse.objects.create(
            pesel=pesel,
            score=score,
            context=context,
            notes=notes
        )

        return render(request, 'cantrilapp/form.html', {'message': 'Odpowiedź zapisana!'})

    return render(request, 'cantrilapp/form.html')

def home(request):
    return render(request, 'home.html')


from django import forms

class PeselForm(forms.Form):
    pesel = forms.CharField(max_length=11, label='PESEL')
    # opcjonalnie:
    # before_after = forms.ChoiceField(choices=[('before', 'Przed badaniem'), ('after', 'Po badaniu')], widget=forms.RadioSelect)

from django.shortcuts import render, redirect
from .models import PatientResponse  # zakładam, że tu masz model z pesel

def ankieta_start(request):
    if request.method == 'POST':
        form = PeselForm(request.POST)
        if form.is_valid():
            pesel = form.cleaned_data['pesel']
            # Sprawdź czy istnieje w bazie - patrzymy po peselu
            istnieje = PatientResponse.objects.filter(pesel=pesel).exists()
            request.session['pesel'] = pesel
            request.session['po_badaniu'] = istnieje  # True jeśli jest już w bazie
            request.session['answers'] = {}  # wyczyść stare odpowiedzi, jeśli były
            
            return redirect('ankieta_question', question_number=1)
    else:
        form = PeselForm()
    return render(request, 'ankieta_start.html', {'form': form})

QUESTIONS = [
    "Jak oceniasz swój nastrój?",
    "Jak oceniasz poziom energii?",
    # ... do 10 pytań
]

from django.shortcuts import render, redirect

def ankieta_question(request, question_number):
    question_number = int(question_number)
    if question_number > len(QUESTIONS):
        # koniec ankiety - zapisz do bazy
        pesel = request.session.get('pesel')
        po_badaniu = request.session.get('po_badaniu', False)
        answers = request.session.get('answers', {})

        # Przykład zapisu: zapisujesz każdą odpowiedź osobno lub w jednej instancji
        # Można zapisać każdą odpowiedź jako osobny rekord lub jako JSON w jednym polu
        for q_num, answer in answers.items():
            PatientResponse.objects.create(
                pesel=pesel,
                score=int(answer),
                context=f"Pytanie {q_num}",
                notes='',
                po_badaniu=po_badaniu
            )
        # Wyczyszczenie sesji
        request.session.pop('answers', None)
        request.session.pop('pesel', None)
        request.session.pop('po_badaniu', None)

        return render(request, 'ankieta_done.html')  # strona podsumowania

    question_text = QUESTIONS[question_number - 1]

    if request.method == 'POST':
        answer = request.POST.get('answer')
        if not answer:
            return render(request, 'ankieta_question.html', {
                'question': question_text,
                'question_number': question_number,
                'total_questions': len(QUESTIONS),
                'error': 'Proszę udzielić odpowiedzi'
            })

        if 'answers' not in request.session:
            request.session['answers'] = {}
        request.session['answers'][str(question_number)] = answer
        request.session.modified = True

        return redirect('ankieta_question', question_number=question_number + 1)

    return render(request, 'ankieta_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': len(QUESTIONS)
    })


def ankieta_done(request):
    return render(request, 'ankieta_done.html')
