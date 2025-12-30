import json
import os
import requests
import uuid
from datetime import datetime
from django.utils import timezone
from django.db.models import Count, Max, Min, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import default_storage
from .models import Patient, PatientResponse, Survey, Question

# =====================
# Konfiguracja pliku JSON i n8n
# =====================
QUESTION_FILE_PATH = os.path.join(settings.BASE_DIR, 'ankieta_pytania.json')
N8N_WEBHOOK_URL = "http://localhost:5678/webhook/198c3dbf-28a7-4fbd-a770-483b2ce47bdc"

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


def get_survey_metadata_from_json():
    """Wczytuje metadane ankiety (design, title) z pliku JSON."""
    metadata = {
        "title": "Ankieta",
        "ladder_design": "classic"
    }
    if os.path.exists(QUESTION_FILE_PATH):
        try:
            with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                metadata["title"] = data.get("title", "Ankieta")
                metadata["ladder_design"] = data.get("ladder_design", "classic")
        except json.JSONDecodeError:
            pass
    return metadata


def format_survey_label(survey_id, fallback_dt=None):
    """Return human-friendly label for a survey id, e.g. 'Ankieta - 2025-12-29 15:14:51'.
    If survey_id contains a timestamp suffix like _YYYYmmddTHHMMSS we parse it.
    Otherwise use fallback_dt (a datetime) when available, else return the raw id.
    """
    if not survey_id:
        return survey_id
    try:
        parts = str(survey_id).rsplit('_', 1)
        if len(parts) == 2:
            prefix = parts[0]
            ts = parts[1]
            # try to resolve prefix as UUID hex and find Survey title
            try:
                import uuid as _uuid
                survey_uuid = _uuid.UUID(hex=prefix)
                try:
                    s = Survey.objects.get(id=survey_uuid)
                    # parse timestamp
                    if len(ts) == 15 and ts[8] == 'T':
                        dt = datetime.strptime(ts, '%Y%m%dT%H%M%S')
                        return f"{s.title} - {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                except Survey.DoesNotExist:
                    pass
            except Exception:
                # not a uuid hex, fall back
                pass

            # expect format like 20251229T151451, fallback to previous behavior
            if len(ts) == 15 and ts[8] == 'T':
                dt = datetime.strptime(ts, '%Y%m%dT%H%M%S')
                return f"Ankieta - {dt.strftime('%Y-%m-%d %H:%M:%S')}"
    except Exception:
        pass

    if fallback_dt:
        try:
            if isinstance(fallback_dt, str):
                fallback_dt = datetime.fromisoformat(fallback_dt)
            return f"Ankieta - {fallback_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            pass

    return survey_id


def get_question_text_by_id(question_id):
    """Map a question id (e.g. 'q1') to its text using the current JSON config."""
    if not question_id:
        return question_id
    try:
        questions = get_questions_from_json()
        for q in questions:
            if isinstance(q, dict) and q.get('id') == str(question_id):
                return q.get('text') or question_id
    except Exception:
        pass
    return question_id

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
    """Manage survey questions - create new or edit existing"""
    
    if request.method == "POST":
        title = (request.POST.get('title') or '').strip()
        survey_uuid = request.POST.get('survey_uuid', '').strip()  # For editing existing
        
        if not title:
            messages.error(request, 'Tytuł ankiety jest wymagany.')
            return redirect('manage_questions')

        # If editing existing survey, check if title changed to duplicate
        if survey_uuid:
            try:
                survey = Survey.objects.get(id=survey_uuid)
                # Only check for duplicates if title actually changed
                if survey.title.lower() != title.lower() and Survey.objects.filter(title__iexact=title).exclude(id=survey_uuid).exists():
                    messages.error(request, 'Ankieta o takiej nazwie już istnieje. Podaj unikalny tytuł.')
                    return redirect('manage_questions')
            except Survey.DoesNotExist:
                messages.error(request, 'Ankieta nie znaleziona.')
                return redirect('manage_questions')
        else:
            # For new surveys, check for duplicate titles
            if Survey.objects.filter(title__iexact=title).exists():
                messages.error(request, 'Ankieta o takiej nazwie już istnieje. Podaj unikalny tytuł.')
                return redirect('manage_questions')

        # Get ladder design
        ladder_design = request.POST.get('ladder_design', 'classic').strip()
        
        questions_list = request.POST.getlist('questions')
        scale_labels_min = request.POST.getlist('scale_labels_min[]')
        scale_labels_max = request.POST.getlist('scale_labels_max[]')
        
        clean_questions = [q.strip() for q in questions_list if q.strip()]

        if not clean_questions:
            messages.error(request, 'Proszę dodać co najmniej jedno pytanie.')
            return redirect('manage_questions')

        questions_with_data = [
            {
                "text": q,
                "scale_labels": {
                    "min": scale_labels_min[i].strip() if i < len(scale_labels_min) else "",
                    "max": scale_labels_max[i].strip() if i < len(scale_labels_max) else ""
                }
            } 
            for i, q in enumerate(clean_questions)
        ]

        # Create or update survey
        if survey_uuid:
            # Update existing survey
            survey = Survey.objects.get(id=survey_uuid)
            survey.title = title
            survey.ladder_design = ladder_design
            survey.save()
            
            # Delete and recreate questions
            Question.objects.filter(survey=survey).delete()
            action_text = "została zaktualizowana"
        else:
            # Create new survey
            survey = Survey.objects.create(title=title, ladder_design=ladder_design)
            action_text = "została utworzona"

        # Create Question records with scale_labels
        for order, q_data in enumerate(questions_with_data, start=1):
            Question.objects.create(
                survey=survey,
                text=q_data['text'],
                order=order,
                scale_labels=q_data.get('scale_labels', {})
            )

        # Update the active JSON file for patient flow (backward compatibility)
        data = {
            "title": title,
            "ladder_design": ladder_design,
            "questions": [
                {
                    "id": f"q{i+1}",
                    "text": q_data['text'],
                    "scale_labels": q_data.get('scale_labels', {})
                }
                for i, q_data in enumerate(questions_with_data)
            ]
        }
        
        with open(QUESTION_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        # Also save survey-specific JSON
        surveys_dir = os.path.join(settings.BASE_DIR, 'surveys')
        os.makedirs(surveys_dir, exist_ok=True)
        survey_path = os.path.join(surveys_dir, f"{survey.id}.json")
        with open(survey_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        messages.success(request, f"✅ Ankieta '{title}' {action_text}!")
        return redirect('manage_questions')

    # GET request - show form
    mode = request.GET.get('mode', 'list')  # 'list', 'new', or survey_uuid for edit
    
    surveys = Survey.objects.all().order_by('-id')
    initial_data = None
    edit_survey_uuid = None

    # If specific survey UUID provided, load it for editing
    if mode != 'new' and mode != 'list':
        try:
            edit_survey = Survey.objects.get(id=mode)
            questions = Question.objects.filter(survey=edit_survey).order_by('order')
            
            # If no questions in DB, try to load from JSON (backward compatibility for old surveys)
            if not questions.exists():
                try:
                    with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        # Use JSON questions, but link to this survey
                        initial_data = {
                            "survey_uuid": str(edit_survey.id),
                            "title": edit_survey.title or json_data.get("title", ""),
                            "ladder_design": edit_survey.ladder_design or json_data.get("ladder_design", "classic"),
                            "questions": json_data.get("questions", [])
                        }
                except:
                    pass
            
            # If questions in DB, use them (preferred)
            if initial_data is None and questions.exists():
                initial_data = {
                    "survey_uuid": str(edit_survey.id),
                    "title": edit_survey.title,
                    "ladder_design": edit_survey.ladder_design,
                    "questions": [
                        {
                            "id": f"q{q.order}",
                            "text": q.text,
                            "scale_labels": q.scale_labels or {"min": "", "max": ""}
                        }
                        for q in questions
                    ]
                }
                edit_survey_uuid = str(edit_survey.id)
            elif initial_data is not None:
                # Loaded from JSON fallback
                edit_survey_uuid = str(edit_survey.id)
        except Survey.DoesNotExist:
            pass

    # If mode is 'new' or no survey UUID found, show new survey form
    if initial_data is None:
        initial_data = {
            "survey_uuid": "",
            "title": "",
            "ladder_design": "classic",
            "questions": [{"id": "q1", "text": "", "scale_labels": {"min": "", "max": ""}}]
        }

    # Debug: print structure
    print(f"DEBUG manage_questions - initial_data: {initial_data}")
    
    context = {
        'data': initial_data,
        'surveys': surveys,
        'edit_survey_uuid': edit_survey_uuid,
        'mode': 'edit' if edit_survey_uuid else 'new'
    }
    
    return render(request, 'generator.html', context)

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
            # Redirect to survey selection instead of directly to questions
            return redirect('ankieta_select_survey')
    else:
        form = PeselForm()
    return render(request, 'ankieta_choice.html', {'form': form})

def ankieta_select_survey(request):
    """Show available surveys and last completion date for each."""
    patient_id = request.session.get('patient_id')
    if not patient_id:
        return redirect('ankieta_choice')

    patient = Patient.objects.get(id=patient_id)
    surveys = Survey.objects.all()
    
    # Get last completion date for each survey
    surveys_with_history = []
    for survey in surveys:
        last_response = PatientResponse.objects.filter(
            patient=patient,
            survey=survey
        ).order_by('-created_at').first()
        
        surveys_with_history.append({
            'survey': survey,
            'last_completed': last_response.created_at if last_response else None
        })
    
    if request.method == "POST":
        survey_uuid = request.POST.get('survey_uuid')
        mode = request.POST.get('mode', 'cantril')
        try:
            survey = Survey.objects.get(id=survey_uuid)
            request.session['survey_uuid'] = str(survey.id)
            request.session['survey_run_id'] = f"{uuid.uuid4().hex}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
            request.session['survey_started_at'] = datetime.utcnow().isoformat()
            request.session['survey_mode'] = mode
            request.session['answers'] = {}
            
            if mode == 'voice':
                return redirect('ankieta_voice_question', question_number=1)
            else:
                return redirect('ankieta_cantril_question', question_number=1)
        except Survey.DoesNotExist:
            messages.error(request, 'Ankieta nie znaleziona.')
    
    return render(request, 'ankieta_select_survey.html', {
        'patient': patient,
        'surveys_with_history': surveys_with_history
    })

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
    survey_metadata = get_survey_metadata_from_json()
    total_questions = len(questions)

    # --- KONIEC ANKIETY ---
    if question_number > total_questions:
        answers = request.session.get('answers', {})
        survey_id = request.session.get('survey_run_id', 'cantril_v1')
        survey_uuid = request.session.get('survey_uuid')
        survey = None
        if survey_uuid:
            try:
                survey = Survey.objects.get(id=survey_uuid)
            except Survey.DoesNotExist:
                pass

        # Zapisz odpowiedzi do bazy i przygotuj JSON outbox
        out = []
        for q_num_str, answer_data in answers.items():
            idx = int(q_num_str) - 1
            q_data = questions[idx] if 0 <= idx < len(questions) else {}
            question_id = q_data.get('id', f'q{q_num_str}')
            response_type = answer_data["type"]

            response = PatientResponse.objects.create(
                patient=patient,
                survey=survey,
                json_survey_id=survey_id,
                question_id=question_id,
                response_type=response_type,
                scale_value=answer_data.get("value") if response_type=="scale" else None,
                text_answer=answer_data.get("value") if response_type=="text" else "",
                question_text=q_data.get('text', '') if isinstance(q_data, dict) else (q_data or ''),
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
                q_idx = question_number - 1
                q_data = questions[q_idx] if isinstance(questions[q_idx], dict) else {'text': questions[q_idx]}
                return render(request, 'ankieta_question.html', {
                    'question': question_text,
                    'question_number': question_number,
                    'total_questions': total_questions,
                    'scale_range': list(range(1, 11)),
                    'ladder_design': survey_metadata['ladder_design'],
                    'scale_labels': q_data.get('scale_labels', {}),
                    'error': 'Proszę udzielić odpowiedzi',
                })
            request.session['answers'][str(question_number)] = {"type": "scale", "value": int(answer)}

        elif response_type == "text":
            answer = request.POST.get("text_answer")
            if not answer:
                q_idx = question_number - 1
                q_data = questions[q_idx] if isinstance(questions[q_idx], dict) else {'text': questions[q_idx]}
                return render(request, 'ankieta_question.html', {
                    'question': question_text,
                    'question_number': question_number,
                    'total_questions': total_questions,
                    'scale_range': list(range(1, 11)),
                    'ladder_design': survey_metadata['ladder_design'],
                    'scale_labels': q_data.get('scale_labels', {}),
                    'error': 'Proszę wpisać odpowiedź',
                })
            request.session['answers'][str(question_number)] = {"type": "text", "value": answer}

        request.session.modified = True
        return redirect('ankieta_cantril_question', question_number=question_number + 1)

    return render(request, 'ankieta_question.html', {
        'question': question_text,
        'question_number': question_number,
        'total_questions': total_questions,
        'scale_range': list(range(1, 11)),
        'ladder_design': survey_metadata['ladder_design'],
        'scale_labels': q_data.get('scale_labels', {}) if isinstance(q_data, dict) else {}
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
    survey_uuid = request.session.get('survey_uuid')
    survey = None
    if survey_uuid:
        try:
            survey = Survey.objects.get(id=survey_uuid)
        except Survey.DoesNotExist:
            pass

    # --- KONIEC ANKIETY ---
    if question_number > total_questions:
        # we already created PatientResponse for each question in this flow
        # create outbox file listing responses for later n8n processing
        responses = PatientResponse.objects.filter(patient=patient, json_survey_id=survey_id)
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
            pr = PatientResponse.objects.create(
                patient=patient,
                survey=survey,
                json_survey_id=survey_id,
                question_id=question_id,
                response_type='text',
                text_answer=text,
                question_text=question_text,
                is_processed=False
            )

            # Send webhook to n8n for text response and mark processed on success
            try:
                data = {
                    'question': question_text,
                    'patientID': str(patient.id),
                    'surveyID': survey_id,
                    'questionID': question_id,
                    'text': text
                }
                resp = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
                print('➡️ n8n text webhook status:', getattr(resp, 'status_code', None))
                if getattr(resp, 'status_code', 0) >= 200 and getattr(resp, 'status_code', 0) < 300:
                    pr.is_processed = True
                    pr.save()
                else:
                    print('⚠️ n8n returned non-2xx for text webhook:', getattr(resp, 'status_code', None), getattr(resp, 'text', None))
            except Exception as e:
                print('⚠️ Błąd przy wysyłce tekstu do n8n:', e)

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
            pr = PatientResponse.objects.create(
                patient=patient,
                survey=survey,
                json_survey_id=survey_id,
                question_id=question_id,
                response_type='audio',
                audio_file=saved_name,
                question_text=question_text,
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

                # send to n8n (non-blocking: errors are caught) and mark processed on success
                resp = requests.post(N8N_WEBHOOK_URL, data=data, files=files, timeout=10)
                print('➡️ n8n audio webhook status:', getattr(resp, 'status_code', None))
                if getattr(resp, 'status_code', 0) >= 200 and getattr(resp, 'status_code', 0) < 300:
                    pr.is_processed = True
                    pr.save()
                else:
                    print('⚠️ n8n returned non-2xx for audio webhook:', getattr(resp, 'status_code', None), getattr(resp, 'text', None))
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


def ladder_designs(request):
    """View to select and change ladder design globally."""
    ladder_design_choices = [
        ('classic', 'Klasyczny - Niebieski gradient', '🔵'),
        ('gradient', 'Gradient - Dynamiczny', '🌈'),
        ('minimal', 'Minimalistyczny - Prosty', '⚫'),
        ('circular', 'Okrągły - Nowoczesny', '⭕'),
        ('modern', 'Nowoczesny - Śmiały', '✨'),
    ]
    
    current_metadata = get_survey_metadata_from_json()
    current_design = current_metadata.get('ladder_design', 'classic')
    
    if request.method == 'POST':
        new_design = request.POST.get('ladder_design', 'classic').strip()
        
        # Validate design choice
        valid_designs = [d[0] for d in ladder_design_choices]
        if new_design not in valid_designs:
            messages.error(request, 'Wybrany design nie jest dostępny.')
            return redirect('ladder_designs')
        
        # Load current JSON data
        if os.path.exists(QUESTION_FILE_PATH):
            try:
                with open(QUESTION_FILE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                data = {"title": "Ankieta", "questions": []}
        else:
            data = {"title": "Ankieta", "questions": []}
        
        # Update design
        data['ladder_design'] = new_design
        
        # Save back to JSON
        with open(QUESTION_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        messages.success(request, f"✅ Design drabiny zmieniony na: {new_design}!")
        return redirect('ladder_designs')
    
    return render(request, 'ladder_designs.html', {
        'ladder_design_choices': ladder_design_choices,
        'current_design': current_design
    })


def panel_results(request):
    """Show processed results. Filterable by pesel or survey_id."""
    pesel = request.GET.get('pesel', '').strip()
    survey_id = request.GET.get('survey_id', '').strip()

    qs = PatientResponse.objects.select_related('patient').order_by('-created_at')
    if pesel:
        qs = qs.filter(patient__pesel=pesel)
    # Only filter by survey_id if it's a valid non-None value
    if survey_id and survey_id != 'None':
        qs = qs.filter(json_survey_id=survey_id)

    # prepare simple rows
    rows = []
    for r in qs:
        # format created_at into local timezone defined in settings (e.g. Europe/Warsaw)
        created_cet = None
        try:
            if r.created_at is not None:
                local_dt = timezone.localtime(r.created_at)
                created_cet = local_dt.strftime('%Y-%m-%d %H:%M:%S')
                # shorter label (no seconds) for compact display
                created_label = local_dt.strftime('%Y-%m-%d %H:%M')
            else:
                created_label = ''
        except Exception:
            created_cet = str(r.created_at)
            created_label = created_cet

        # map response type to Polish label
        type_map = {
            'scale': 'Skala',
            'text': 'Tekst',
            'audio': 'Audio'
        }

        eval_label = 'Brak' if r.evaluated_score is None else str(r.evaluated_score)

        # prefer stored question_text if available (preserves historical wording)
        qtext = getattr(r, 'question_text', None) or None
        if not qtext:
            qtext = get_question_text_by_id(r.question_id)

        rows.append({
            'patient_pesel': r.patient.pesel,
            'json_survey_id': r.json_survey_id,
            'survey_label': format_survey_label(r.json_survey_id, r.created_at),
            'question_id': r.question_id,
            'question_text': qtext,
            'response_type': r.response_type,
            'response_type_label': type_map.get(r.response_type, r.response_type),
            'scale_value': r.scale_value,
            'text_answer': r.text_answer,
            'audio_file': r.audio_file.url if r.audio_file else None,
            'evaluated_score': r.evaluated_score,
            'evaluated_label': eval_label,
            'is_processed': r.is_processed,
            'created_at': r.created_at,
            'created_cet': created_cet,
            'created_label': created_label,
        })

    return render(request, 'panel_results.html', {'rows': rows, 'pesel': pesel, 'survey_id': survey_id})


def panel_history(request):
    """History of filled surveys grouped by patient and survey_id.

    Search supports: pesel, first/last name, survey_id.
    """
    q = request.GET.get('q', '').strip()
    
    # Ignore if q is the string "None"
    if q == 'None':
        q = ''

    base_qs = PatientResponse.objects.select_related('patient')
    if q:
        base_qs = base_qs.filter(
            Q(patient__pesel__icontains=q)
            | Q(patient__first_name__icontains=q)
            | Q(patient__last_name__icontains=q)
            | Q(json_survey_id__icontains=q)
        )

    aggregated = (
        base_qs.values(
            'patient_id',
            'patient__pesel',
            'patient__first_name',
            'patient__last_name',
            'json_survey_id',
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

        # compute a human-friendly label for the survey (use first_response_at as fallback)
        fallback_dt = row.get('first_response_at') or row.get('last_response_at')
        # format first/last response to local time strings
        try:
            first_local = timezone.localtime(row['first_response_at']).strftime('%Y-%m-%d %H:%M:%S') if row.get('first_response_at') else None
        except Exception:
            first_local = row.get('first_response_at')
        try:
            last_local = timezone.localtime(row['last_response_at']).strftime('%Y-%m-%d %H:%M:%S') if row.get('last_response_at') else None
        except Exception:
            last_local = row.get('last_response_at')

        patients_map[pid]['surveys'].append(
            {
                'survey_id': row['json_survey_id'],
                'survey_label': format_survey_label(row['json_survey_id'], fallback_dt),
                'responses_count': row['responses_count'],
                'processed_count': row['processed_count'],
                'first_response_at': first_local,
                'last_response_at': last_local,
            }
        )

    patients = list(patients_map.values())
    patients.sort(key=lambda p: (p['pesel'] or ''))

    # If a query was provided, further filter surveys by the human-friendly survey_label
    if q:
        ql = q.lower()
        filtered = []
        for p in patients:
            orig = p['surveys']
            p['surveys'] = [s for s in orig if ql in (s.get('survey_label') or '').lower() or ql in (s.get('survey_id') or '').lower()]
            if p['surveys']:
                filtered.append(p)
        patients = filtered

    return render(request, 'panel_history.html', {'patients': patients, 'q': q})


def panel_patient_history(request, patient_id: int):
    """Patient card: list survey runs (survey_id) for a single patient."""
    patient = get_object_or_404(Patient, id=patient_id)

    # Get all surveys with responses from this patient
    survey_responses = PatientResponse.objects.filter(
        patient=patient,
        survey__isnull=False  # Only show Survey model based responses
    ).values('survey').annotate(
        responses_count=Count('id'),
        processed_count=Count('id', filter=Q(is_processed=True)),
        first_response_at=Min('created_at'),
        last_response_at=Max('created_at'),
    ).order_by('-last_response_at')

    surveys_list = []
    for item in survey_responses:
        survey = Survey.objects.get(id=item['survey'])
        try:
            first_local = timezone.localtime(item['first_response_at']).strftime('%Y-%m-%d %H:%M:%S') if item.get('first_response_at') else None
        except Exception:
            first_local = item.get('first_response_at')
        try:
            last_local = timezone.localtime(item['last_response_at']).strftime('%Y-%m-%d %H:%M:%S') if item.get('last_response_at') else None
            last_date_only = timezone.localtime(item['last_response_at']).strftime('%Y-%m-%d') if item.get('last_response_at') else None
        except Exception:
            last_local = item.get('last_response_at')
            last_date_only = None

        # Format title as "<SURVEY NAME> - <DATE>"
        survey_display_title = f"{survey.title} - {last_date_only}" if last_date_only else survey.title

        surveys_list.append({
            'survey': survey,
            'survey_display_title': survey_display_title,
            'responses_count': item['responses_count'],
            'processed_count': item['processed_count'],
            'first_response_at': first_local,
            'last_response_at': last_local,
        })

    return render(
        request,
        'panel_patient_history.html',
        {
            'patient': patient,
            'surveys': surveys_list,
        },
    )


def panel_survey_completions(request, survey_id: int, patient_id: int):
    """View all completions of a specific survey by a specific patient."""
    survey = get_object_or_404(Survey, id=survey_id)
    patient = get_object_or_404(Patient, id=patient_id)
    
    # First, get all responses for this patient and survey (with survey FK set)
    responses_with_survey = PatientResponse.objects.filter(
        patient=patient,
        survey=survey
    ).order_by('-created_at')
    
    # Collect json_survey_id values from these responses
    survey_session_ids = set(r.json_survey_id for r in responses_with_survey if r.json_survey_id)
    
    # Now also include any older responses with the same json_survey_id but no survey FK
    # (for backwards compatibility)
    if survey_session_ids:
        all_responses = PatientResponse.objects.filter(
            Q(patient=patient, survey=survey) |
            Q(patient=patient, json_survey_id__in=survey_session_ids)
        ).order_by('-created_at')
    else:
        all_responses = responses_with_survey
    
    # Group by completion session (json_survey_id)
    completions = {}
    for response in all_responses:
        session_id = response.json_survey_id
        if session_id not in completions:
            completions[session_id] = {
                'session_id': session_id,
                'completed_at': response.created_at,
                'responses': []
            }
        completions[session_id]['responses'].append(response)
    
    # Sort completions by date
    completions_list = sorted(
        completions.values(),
        key=lambda x: x['completed_at'],
        reverse=True
    )
    
    # Format dates
    for completion in completions_list:
        try:
            completion['completed_at_local'] = timezone.localtime(
                completion['completed_at']
            ).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            completion['completed_at_local'] = str(completion['completed_at'])
    
    return render(
        request,
        'panel_survey_completions.html',
        {
            'survey': survey,
            'patient': patient,
            'completions': completions_list,
        }
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

        # Find PatientResponse by json_survey_id (renamed from survey_id) and questionID
        try:
            pr = PatientResponse.objects.get(question_id=str(qid), json_survey_id=str(survey))
            pr.evaluated_score = float(score) if score is not None else None
            pr.is_processed = True
            pr.save()
            updated += 1
            print(f"✏️ Updated PatientResponse {pr.id}")
        except PatientResponse.DoesNotExist:
            print(f"❌ PatientResponse not found for json_survey_id={survey}, qid={qid}")

    return JsonResponse({'status': 'ok', 'updated': updated, 'created': created})

# =====================
# Stary formularz pacjenta (opcjonalny)
# =====================
@csrf_exempt
def patient_form(request):
    if request.method == "POST":
        return render(request, 'form.html', {'message': 'Funkcja wyłączona w tym przykładzie'})
    return render(request, 'form.html')
