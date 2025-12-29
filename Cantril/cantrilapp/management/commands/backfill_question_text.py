from django.core.management.base import BaseCommand
from django.conf import settings
from cantrilapp.models import PatientResponse
import os
import json

class Command(BaseCommand):
    help = 'Backfill PatientResponse.question_text from outbox JSON files when available'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without writing')

    def handle(self, *args, **options):
        dry = options.get('dry_run')
        base = settings.BASE_DIR
        outdir = os.path.join(base, 'outbox')
        qs = PatientResponse.objects.filter(question_text__isnull=True)
        total = qs.count()
        updated = 0
        self.stdout.write(f'Found {total} responses with null question_text')

        for r in qs:
            out_path = os.path.join(outdir, f"{r.survey_id}_{r.patient.id}.json")
            if not os.path.exists(out_path):
                continue
            try:
                with open(out_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Failed to load {out_path}: {e}'))
                continue

            # data expected to be a list of entries with questionID / question keys
            found_text = None
            if isinstance(data, dict):
                data = [data]
            for item in data:
                qid = item.get('questionID') or item.get('questionId') or item.get('question_id') or item.get('question')
                # some outbox entries store question text under 'question' and id under 'questionID'
                if item.get('questionID') and item.get('questionID') == r.question_id:
                    found_text = item.get('question') or item.get('text') or ''
                    break
                # if data structure had question id under 'question' key
                if (item.get('question') or '').strip() and (item.get('questionID') is None) and r.question_id in (item.get('question') or ''):
                    # not reliable
                    continue

            if not found_text:
                # try to match by questionID key variants
                for item in data:
                    for key in ('questionID','questionId','question_id'):
                        if item.get(key) and str(item.get(key)) == str(r.question_id):
                            found_text = item.get('question') or item.get('text') or ''
                            break
                    if found_text:
                        break

            if not found_text:
                continue

            if dry:
                self.stdout.write(f'[DRY] Would set response {r.id} question_text="{found_text}"')
            else:
                r.question_text = found_text
                r.save(update_fields=['question_text'])
                updated += 1
                self.stdout.write(self.style.SUCCESS(f'Updated response {r.id}'))

        self.stdout.write(self.style.SUCCESS(f'Done. Updated {updated} responses (out of {total})'))
