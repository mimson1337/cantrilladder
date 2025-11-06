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

        # Ensure patient exists and create response linked to patient
        patient, _ = Patient.objects.get_or_create(pesel=pesel)
        PatientResponse.objects.create(
            patient=patient,
            score=int(score) if score is not None and score != '' else 0,
            context=context or '',
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
from .models import Patient, PatientResponse, Question
from django.contrib.auth.decorators import login_required

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

    # Load questions from DB if present, otherwise fall back to QUESTIONS constant
    def get_questions_list():
        qs = list(Question.objects.all())
        if qs:
            return [q.text for q in qs]
        return QUESTIONS

    questions_list = get_questions_list()

    patient_id = request.session.get('patient_id')
    patient = Patient.objects.get(id=patient_id)

    if question_number > len(questions_list):
        answers = request.session.get('answers', {})
        po_badaniu = request.session.get('po_badaniu', False)

        for q_num, answer in answers.items():
            # Try to attach a Question object if available
            question_obj = Question.objects.filter(order=int(q_num)).first()
            PatientResponse.objects.create(
                patient=patient,
                score=int(answer),
                question=question_obj,
                context=(question_obj.text if question_obj else f"Pytanie {q_num}"),
                notes='',
                is_synced_with_his=False
            )

        request.session.flush()
        return render(request, 'ankieta_done.html')

    question_text = questions_list[question_number - 1]

    if request.method == 'POST':
        answer = request.POST.get('answer')
        if not answer:
            return render(request, 'ankieta_question.html', {
                'question': question_text,
                'question_number': question_number,
                'total_questions': len(questions_list),
                'error': 'Proszę udzielić odpowiedzi'
            })

        request.session['answers'][str(question_number)] = answer
        request.session.modified = True

        return redirect('ankieta_question', question_number=question_number + 1)

    return render(request, 'ankieta_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': len(questions_list)
    })


# =====================
# Zakończenie ankiety
# =====================
def ankieta_done(request):
    return render(request, 'ankieta_done.html')


@login_required
def manage_questions(request):
    """Simple management view: list existing questions and allow adding/deleting.
    Not protected by auth in this prototype — consider restricting in production.
    """
    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            qid = request.POST.get('question_id')
            Question.objects.filter(id=qid).delete()
        else:
            text = request.POST.get('text')
            order = request.POST.get('order') or 0
            if text:
                Question.objects.create(text=text, order=int(order))
        return redirect('manage_questions')

    questions = Question.objects.all()
    return render(request, 'manage_questions.html', {'questions': questions})


@login_required
def panel_results(request):
    """Show completed surveys grouped by patient."""
    patients = Patient.objects.prefetch_related('responses').all()
    return render(request, 'panel_results.html', {'patients': patients})


@login_required
def panel_home(request):
    """Panel home with tabs linking to management pages."""
    return render(request, 'panel_home.html')


@login_required
def manage_patients(request):
    """List existing patients and allow adding or deleting (prototype).
    """
    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            pid = request.POST.get('patient_id')
            Patient.objects.filter(id=pid).delete()
        else:
            pesel = request.POST.get('pesel')
            first = request.POST.get('first_name')
            last = request.POST.get('last_name')
            dob = request.POST.get('date_of_birth')
            if pesel:
                Patient.objects.get_or_create(pesel=pesel, defaults={'first_name': first or '', 'last_name': last or '', 'date_of_birth': dob or None})
        return redirect('manage_patients')

    patients = Patient.objects.all()
    return render(request, 'manage_patients.html', {'patients': patients})

# =====================
# API (opcjonalne)
# =====================
@csrf_exempt
def submit_response(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            pesel = data.get('pesel')
            if not pesel:
                return JsonResponse({'status': 'error', 'message': 'Missing pesel'}, status=400)
            patient, _ = Patient.objects.get_or_create(pesel=pesel)
            PatientResponse.objects.create(
                patient=patient,
                score=int(data.get('score', 0)),
                context=data.get('context', ''),
                notes=data.get('notes', '')
            )
            return JsonResponse({'status': 'success'}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
