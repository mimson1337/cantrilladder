from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django import forms
from .models import PatientResponse
import json

# =====================
# Formularz PESEL
# =====================
class PeselForm(forms.Form):
    pesel = forms.CharField(max_length=11, label='PESEL')

# =====================
# Pytania do ankiety
# =====================
QUESTIONS = [
    "Jak oceniasz swój nastrój?",
    "Jak oceniasz poziom energii?",
    "Jak oceniasz poziom stresu?",
    "Jak oceniasz swoje relacje z innymi?",
    "Jak oceniasz swoją jakość snu?",
    "Jak oceniasz swój stan fizyczny?",
    "Jak oceniasz swoją motywację do działania?",
    "Jak oceniasz swoje samopoczucie ogólne?",
    "Jak oceniasz swoją zdolność radzenia sobie z trudnościami?",
    "Jak oceniasz swoje zadowolenie z życia?"
]

# =====================
# Widok: Strona główna
# =====================
def home(request):
    return render(request, 'home.html')

# =====================
# Formularz /admin
# =====================
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

        return render(request, 'form.html', {'message': 'Odpowiedź zapisana!'})

    return render(request, 'form.html')

# =====================
# Start ankiety
# =====================
# def ankieta_start(request):
#     if request.method == 'POST':
#         form = PeselForm(request.POST)
#         if form.is_valid():
#             pesel = form.cleaned_data['pesel']
#             istnieje = PatientResponse.objects.filter(pesel=pesel).exists()

#             request.session['pesel'] = pesel
#             request.session['po_badaniu'] = istnieje
#             request.session['answers'] = {}

#             return redirect('ankieta_question', question_number=1)
#     else:
#         form = PeselForm()
#     return render(request, 'ankieta_start.html', {'form': form})
from .models import Patient, PatientResponse

def ankieta_start(request):
    if request.method == 'POST':
        form = PeselForm(request.POST)
        if form.is_valid():
            pesel = form.cleaned_data['pesel']

            # Szukamy pacjenta
            try:
                patient = Patient.objects.get(pesel=pesel)
                po_badaniu = PatientResponse.objects.filter(patient=patient).exists()
            except Patient.DoesNotExist:
                # Tworzymy nowego pacjenta jeśli nie ma w bazie
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
# Pytania ankiety
# =====================
# def ankieta_question(request, question_number):
#     question_number = int(question_number)

#     # Zakończenie ankiety
#     if question_number > len(QUESTIONS):
#         pesel = request.session.get('pesel')
#         po_badaniu = request.session.get('po_badaniu', False)
#         answers = request.session.get('answers', {})

#         for q_num, answer in answers.items():
#             PatientResponse.objects.create(
#                 pesel=pesel,
#                 score=int(answer),
#                 context=f"Pytanie {q_num}",
#                 notes='',
#                 po_badaniu=po_badaniu
#             )

#         # Wyczyść sesję
#         request.session.flush()
#         return render(request, 'ankieta_done.html')

#     question_text = QUESTIONS[question_number - 1]

#     if request.method == 'POST':
#         answer = request.POST.get('answer')
#         if not answer:
#             return render(request, 'ankieta_question.html', {
#                 'question': question_text,
#                 'question_number': question_number,
#                 'total_questions': len(QUESTIONS),
#                 'error': 'Proszę udzielić odpowiedzi'
#             })

#         request.session['answers'][str(question_number)] = answer
#         request.session.modified = True

#         return redirect('ankieta_question', question_number=question_number + 1)

#     return render(request, 'ankieta_question.html', {
#         'question': question_text,
#         'question_number': question_number,
#         'total_questions': len(QUESTIONS)
#     })
def ankieta_question(request, question_number):
    question_number = int(question_number)

    patient_id = request.session.get('patient_id')
    patient = Patient.objects.get(id=patient_id)

    if question_number > len(QUESTIONS):
        answers = request.session.get('answers', {})
        po_badaniu = request.session.get('po_badaniu', False)

        for q_num, answer in answers.items():
            PatientResponse.objects.create(
                patient=patient,
                score=int(answer),
                context=f"Pytanie {q_num}",
                notes='',
                is_synced_with_his=False
            )

        request.session.flush()
        return render(request, 'ankieta_done.html')

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

        request.session['answers'][str(question_number)] = answer
        request.session.modified = True

        return redirect('ankieta_question', question_number=question_number + 1)

    return render(request, 'ankieta_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': len(QUESTIONS)
    })


# =====================
# Zakończenie ankiety
# =====================
def ankieta_done(request):
    return render(request, 'ankieta_done.html')

# =====================
# API (opcjonalne)
# =====================
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
