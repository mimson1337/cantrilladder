import json
import os
import requests
import uuid
from django.db.models import Count, Max, Min, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import default_storage
from .models import Patient, PatientResponse

# =====================
# Konfiguracja pliku JSON i n8n
# =====================
QUESTION_FILE_PATH = os.path.join(settings.BASE_DIR, 'ankieta_pytania.json')
N8N_WEBHOOK_URL = "http://localhost:5678/webhook-test/198c3dbf-28a7-4fbd-a770-483b2ce47bdc"

def get_questions_from_json():
    """Wczytuje pytania z pliku JSON lub domyślne."""
    default_questions = [
        {"id": "q1", "text": "Jak oceniasz swój nastrój?"},
        {"id": "q2", "text": "Jak oceniasz poziom energii?"},
        {"id": "q3", "text": "Jak oceniasz poziom stresu?"}
    ]
    if os.path.exists(QUESTION_FILE_PATH):
        try:
            with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("questions", default_questions)
        except json.JSONDecodeError:
            return default_questions
    return default_questions

# =====================
# Formularz PESEL
# =====================
class PeselForm(forms.Form):
    pesel = forms.CharField(
        label='PESEL',
        min_length=11,
        max_length=11,
        widget=forms.TextInput(
            attrs={
                'inputmode': 'numeric',
                'pattern': r'\d{11}',
                'maxlength': '11',
                'minlength': '11',
                'autocomplete': 'off',
            }
        ),
    )

    def clean_pesel(self):
        pesel = (self.cleaned_data.get('pesel') or '').strip()
        if len(pesel) != 11:
            raise forms.ValidationError('PESEL musi mieć dokładnie 11 cyfr.')
        if not pesel.isdigit():
            raise forms.ValidationError('PESEL musi składać się wyłącznie z cyfr.')
        return pesel

# =====================
# Generator ankiety dla lekarza
# =====================
def manage_questions(request):
    if request.method == "POST":
        questions_list = request.POST.getlist('questions')
        clean_questions = [q.strip() for q in questions_list if q.strip()]

        questions_with_id = [{"id": f"q{i+1}", "text": q} for i, q in enumerate(clean_questions)]
        data = {
            "title": request.POST.get('title', 'Ankieta Cantrila'),
            "questions": questions_with_id
        }

        with open(QUESTION_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        messages.success(request, "✅ Ankieta została pomyślnie zapisana!")
        return redirect('home')

    initial_data = {"questions": [{"id": "q1", "text": ""}]}
    if os.path.exists(QUESTION_FILE_PATH):
        try:
            with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                initial_data = json.load(f)
        except json.JSONDecodeError:
            pass

    return render(request, 'generator.html', {'data': initial_data})

# =====================
# Strona główna
# =====================
def home(request):
    return render(request, 'home.html')

# =====================
# Start ankiety pacjenta
# =====================
def ankieta_choice(request):
    """Start survey: enter PESEL and choose mode (cantril or voice/text)."""
    if request.method == "POST":
        form = PeselForm(request.POST)
        mode = request.POST.get('mode', 'cantril')
        if form.is_valid():
            pesel = form.cleaned_data['pesel']
            patient, created = Patient.objects.get_or_create(pesel=pesel)
            request.session['patient_id'] = patient.id
            request.session['survey_run_id'] = str(uuid.uuid4())
            request.session['survey_mode'] = mode
            # for cantril we keep session answers; for voice we will save per-question
            request.session['answers'] = {}
            if mode == 'voice':
                return redirect('ankieta_voice_question', question_number=1)
            else:
                return redirect('ankieta_cantril_question', question_number=1)
    else:
        form = PeselForm()
    return render(request, 'ankieta_choice.html', {'form': form})

# =====================
# Pojedyncze pytanie ankiety (scale/text/audio)
# =====================
def ankieta_cantril_question(request, question_number):
    """Cantril ladder flow (scale answers)."""
    question_number = int(question_number)
    patient_id = request.session.get('patient_id')
    if not patient_id:
        return redirect('ankieta_choice')

    patient = Patient.objects.get(id=patient_id)
    questions = get_questions_from_json()
    total_questions = len(questions)

    # --- KONIEC ANKIETY ---
    if question_number > total_questions:
        answers = request.session.get('answers', {})
        survey_id = request.session.get('survey_run_id', 'cantril_v1')

        # Zapisz odpowiedzi do bazy i przygotuj JSON outbox
        out = []
        for q_num_str, answer_data in answers.items():
            idx = int(q_num_str) - 1
            q_data = questions[idx] if 0 <= idx < len(questions) else {}
            question_id = q_data.get('id', f'q{q_num_str}')
            response_type = answer_data["type"]

            response = PatientResponse.objects.create(
                patient=patient,
                survey_id=survey_id,
                question_id=question_id,
                response_type=response_type,
                scale_value=answer_data.get("value") if response_type=="scale" else None,
                text_answer=answer_data.get("value") if response_type=="text" else "",
                is_processed=False
            )

            out.append({
                "patientID": str(patient.id),
                "surveyID": survey_id,
                "questionID": question_id,
                "question": q_data.get('text', ''),
                "responseType": response_type,
                "scaleValue": answer_data.get('value') if response_type=='scale' else None,
                "textAnswer": answer_data.get('value') if response_type=='text' else None,
            })

        # write outbox JSON for later n8n processing (simulate webhook payload)
        out_dir = os.path.join(settings.BASE_DIR, 'outbox')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{survey_id}_{patient.id}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        request.session.flush()
        return render(request, 'ankieta_done.html')

    # --- WYŚWIETLANIE PYTANIA ---
    q_raw = questions[question_number - 1]
    if isinstance(q_raw, dict):
        q_data = q_raw
        question_text = q_data.get('text', '')
        question_id_default = q_data.get('id', f'q{question_number}')
    else:
        q_data = None
        question_text = q_raw
        question_id_default = f'q{question_number}'

    if request.method == "POST":
        response_type = request.POST.get("response_type", "scale")

        if response_type == "scale":
            answer = request.POST.get("answer")
            if not answer:
                return render(request, 'ankieta_question.html', {
                    'question': question_text,
                    'question_number': question_number,
                    'total_questions': total_questions,
                    'scale_range': list(range(1, 11)),
                    'error': 'Proszę udzielić odpowiedzi',
                })
            request.session['answers'][str(question_number)] = {"type": "scale", "value": int(answer)}

        elif response_type == "text":
            answer = request.POST.get("text_answer")
            if not answer:
                return render(request, 'ankieta_question.html', {
                    'question': question_text,
                    'question_number': question_number,
                    'total_questions': total_questions,
                    'scale_range': list(range(1, 11)),
                    'error': 'Proszę wpisać odpowiedź',
                })
            request.session['answers'][str(question_number)] = {"type": "text", "value": answer}

        request.session.modified = True
        return redirect('ankieta_cantril_question', question_number=question_number + 1)

    return render(request, 'ankieta_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': total_questions,
        'scale_range': list(range(1, 11))
    })


def ankieta_voice_question(request, question_number):
    """Voice/text flow. Audio files are saved immediately and a PatientResponse is created per question.
    Recording should start client-side on load and stop when user clicks Next (form submission).
    """
    question_number = int(question_number)
    patient_id = request.session.get('patient_id')
    if not patient_id:
        return redirect('ankieta_choice')

    patient = Patient.objects.get(id=patient_id)
    questions = get_questions_from_json()
    total_questions = len(questions)

    survey_id = request.session.get('survey_run_id', str(uuid.uuid4()))

    # --- KONIEC ANKIETY ---
    if question_number > total_questions:
        # we already created PatientResponse for each question in this flow
        # create outbox file listing responses for later n8n processing
        responses = PatientResponse.objects.filter(patient=patient, survey_id=survey_id)
        out = []
        for r in responses:
            out.append({
                "patientID": str(patient.id),
                "surveyID": survey_id,
                "questionID": r.question_id,
                "question": "",
                "responseType": r.response_type,
                "textAnswer": r.text_answer,
                "audioFile": r.audio_file.url if r.audio_file else None,
            })

        out_dir = os.path.join(settings.BASE_DIR, 'outbox')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{survey_id}_{patient.id}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        request.session.flush()
        return render(request, 'ankieta_done.html')

    # --- WYŚWIETLANIE PYTANIA ---
    q_raw = questions[question_number - 1]
    if isinstance(q_raw, dict):
        q_data = q_raw
        question_text = q_data.get('text', '')
        question_id_default = q_data.get('id', f'q{question_number}')
    else:
        q_data = None
        question_text = q_raw
        question_id_default = f'q{question_number}'

    if request.method == 'POST':
        response_type = request.POST.get('response_type', 'audio')

        if response_type == 'text':
            text = request.POST.get('text_answer', '').strip()
            if not text:
                return render(request, 'ankieta_voice_question.html', {
                    'question': question_text,
                    'question_number': question_number,
                    'total_questions': total_questions,
                    'error': 'Proszę wpisać odpowiedź',
                })
            # save response immediately
            question_id = question_id_default
            PatientResponse.objects.create(
                patient=patient,
                survey_id=survey_id,
                question_id=question_id,
                response_type='text',
                text_answer=text,
                is_processed=False
            )

        elif response_type == 'audio':
            audio_file = request.FILES.get('audio_file')
            if not audio_file:
                return render(request, 'ankieta_voice_question.html', {
                    'question': question_text,
                    'question_number': question_number,
                    'total_questions': total_questions,
                    'error': 'Proszę nagrać odpowiedź',
                })

            # save audio to storage
            filename = f"{uuid.uuid4().hex}_{audio_file.name}"
            save_path = os.path.join('audio_answers', filename)
            saved_name = default_storage.save(save_path, audio_file)

            question_id = question_id_default
            PatientResponse.objects.create(
                patient=patient,
                survey_id=survey_id,
                question_id=question_id,
                response_type='audio',
                audio_file=saved_name,
                is_processed=False
            )

            # Prepare webhook payload and send multipart to n8n
            try:
                # open saved file for sending
                f = default_storage.open(saved_name, 'rb')
                # determine mime by extension
                lower = saved_name.lower()
                if lower.endswith('.mp3'):
                    mime = 'audio/mpeg'
                elif lower.endswith('.wav'):
                    mime = 'audio/wav'
                elif lower.endswith('.webm'):
                    mime = 'audio/webm'
                else:
                    mime = 'application/octet-stream'

                files = {'audio': (os.path.basename(saved_name), f, mime)}

                # Simple payload for n8n
                data = {
                    'question': question_text,
                    'patientID': str(patient.id),
                    'surveyID': survey_id,
                    'questionID': question_id
                }

                # send to n8n (non-blocking: errors are caught)
                requests.post(N8N_WEBHOOK_URL, data=data, files=files, timeout=10)
                f.close()
            except Exception as e:
                # don't break the flow if webhook fails
                print('⚠️ Błąd przy wysyłce do n8n:', e)

        return redirect('ankieta_voice_question', question_number=question_number + 1)

    return render(request, 'ankieta_voice_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': total_questions,
    })

# =====================
# Zakończenie ankiety
# =====================
def ankieta_done(request):
    return render(request, 'ankieta_done.html')


# =====================
# Panel lekarza + n8n webhook
# =====================
def panel_home(request):
    """Simple panel with links to generator or results view."""
    return render(request, 'panel_home.html')


def panel_results(request):
    """Show processed results. Filterable by pesel or survey_id."""
    pesel = request.GET.get('pesel', '').strip()
    survey_id = request.GET.get('survey_id', '').strip()

    qs = PatientResponse.objects.select_related('patient').order_by('-created_at')
    if pesel:
        qs = qs.filter(patient__pesel=pesel)
    if survey_id:
        qs = qs.filter(survey_id=survey_id)

    # prepare simple rows
    rows = []
    for r in qs:
        rows.append({
            'patient_pesel': r.patient.pesel,
            'survey_id': r.survey_id,
            'question_id': r.question_id,
            'response_type': r.response_type,
            'scale_value': r.scale_value,
            'text_answer': r.text_answer,
            'audio_file': r.audio_file.url if r.audio_file else None,
            'evaluated_score': r.evaluated_score,
            'is_processed': r.is_processed,
            'created_at': r.created_at,
        })

    return render(request, 'panel_results.html', {'rows': rows, 'pesel': pesel, 'survey_id': survey_id})


def panel_history(request):
    """History of filled surveys grouped by patient and survey_id.

    Search supports: pesel, first/last name, survey_id.
    """
    q = request.GET.get('q', '').strip()

    base_qs = PatientResponse.objects.select_related('patient')
    if q:
        base_qs = base_qs.filter(
            Q(patient__pesel__icontains=q)
            | Q(patient__first_name__icontains=q)
            | Q(patient__last_name__icontains=q)
            | Q(survey_id__icontains=q)
        )

    aggregated = (
        base_qs.values(
            'patient_id',
            'patient__pesel',
            'patient__first_name',
            'patient__last_name',
            'survey_id',
        )
        .annotate(
            responses_count=Count('id'),
            processed_count=Count('id', filter=Q(is_processed=True)),
            first_response_at=Min('created_at'),
            last_response_at=Max('created_at'),
        )
        .order_by('patient__pesel', '-last_response_at')
    )

    patients_map = {}
    for row in aggregated:
        pid = row['patient_id']
        if pid not in patients_map:
            patients_map[pid] = {
                'id': pid,
                'pesel': row['patient__pesel'],
                'first_name': row['patient__first_name'],
                'last_name': row['patient__last_name'],
                'surveys': [],
            }

        patients_map[pid]['surveys'].append(
            {
                'survey_id': row['survey_id'],
                'responses_count': row['responses_count'],
                'processed_count': row['processed_count'],
                'first_response_at': row['first_response_at'],
                'last_response_at': row['last_response_at'],
            }
        )

    patients = list(patients_map.values())
    patients.sort(key=lambda p: (p['pesel'] or ''))

    return render(request, 'panel_history.html', {'patients': patients, 'q': q})


def panel_patient_history(request, patient_id: int):
    """Patient card: list survey runs (survey_id) for a single patient."""
    patient = get_object_or_404(Patient, id=patient_id)
    survey_q = request.GET.get('survey', '').strip()

    base_qs = PatientResponse.objects.filter(patient=patient)
    if survey_q:
        base_qs = base_qs.filter(survey_id__icontains=survey_q)

    surveys = (
        base_qs.values('survey_id')
        .annotate(
            responses_count=Count('id'),
            processed_count=Count('id', filter=Q(is_processed=True)),
            first_response_at=Min('created_at'),
            last_response_at=Max('created_at'),
        )
        .order_by('-last_response_at')
    )

    return render(
        request,
        'panel_patient_history.html',
        {
            'patient': patient,
            'surveys': list(surveys),
            'survey': survey_q,
        },
    )


@csrf_exempt
def n8n_results_webhook(request):
    """Endpoint to receive processed results from n8n.

    Expected: form-data or JSON with keys like 'questionID', 'patientID', 'surveyID', 'score'
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST expected'})

    # Try to parse as JSON first, then fall back to form data
    payload = None
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        # Try form data
        payload = request.POST.dict()
        if not payload:
            return JsonResponse({'status': 'error', 'message': 'No data received'})

    # Ensure payload is a list
    if isinstance(payload, dict):
        payload = [payload]

    print(f"🔍 DEBUG n8n webhook: {json.dumps(payload, indent=2)}")

    updated = 0
    created = 0
    for item in payload:
        # Get required fields
        qid = item.get('question ID') or item.get('questionID') or item.get('question_id') or item.get('questionId')
        survey = item.get('survey ID') or item.get('surveyID') or item.get('survey_id')
        score = item.get('score') or item.get('evaluated_score') or item.get('rating')

        if not qid or not survey:
            print(f"⚠️ Missing qid or survey: qid={qid}, survey={survey}")
            continue

        print(f"📝 Processing: qid={qid}, survey={survey}, score={score}")

        # Find PatientResponse directly by surveyID and questionID
        try:
            pr = PatientResponse.objects.get(question_id=str(qid), survey_id=str(survey))
            pr.evaluated_score = float(score) if score is not None else None
            pr.is_processed = True
            pr.save()
            updated += 1
            print(f"✏️ Updated PatientResponse {pr.id}")
        except PatientResponse.DoesNotExist:
            print(f"❌ PatientResponse not found for survey={survey}, qid={qid}")

    return JsonResponse({'status': 'ok', 'updated': updated, 'created': created})

# =====================
# Stary formularz pacjenta (opcjonalny)
# =====================
@csrf_exempt
def patient_form(request):
    if request.method == "POST":
        return render(request, 'form.html', {'message': 'Funkcja wyłączona w tym przykładzie'})
    return render(request, 'form.html')
