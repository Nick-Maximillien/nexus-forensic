import os
import time
from django.core.management.base import BaseCommand, CommandError
from apps.forensic_corpus.models import ClinicalProtocol, ForensicRule
from apps.forensic_corpus.ingestion.parser import ClinicalProtocolParser, GuidelineParser
from apps.forensic_corpus.ingestion.llm_normalizer import extract_metadata_only

class Command(BaseCommand):
    help = """
    Ingests a Clinical Protocol PDF and extracts deterministic Forensic Rules.
    - [CREDIT SAFE]: Checks database before calling Vertex AI.
    - [RESUMABLE]: Markdown Caching and Individual Commits.
    """

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to PDF file')
        parser.add_argument('--title', type=str, required=True, help='e.g. "AHA ACLS Guidelines"')
        parser.add_argument('--doc_version', type=str, required=True, help='e.g. "v2025.1"')
        parser.add_argument('--issuing_body', type=str, required=True, help='e.g. "American Heart Association"')
        
        parser.add_argument(
            '--specialty', 
            type=str, 
            required=True, 
            choices=[s[0] for s in ClinicalProtocol.SPECIALTIES],
            help='Clinical specialty context'
        )
        
        parser.add_argument('--valid_from', type=str, required=True, help='YYYY-MM-DD')
        parser.add_argument('--parser_type', type=str, default='protocol', 
                            choices=['protocol', 'guideline'])

    def handle(self, *args, **options):
        file_path = options['file']
        start_time = time.time()
        
        print(f"\n[INFO] Starting Credit-Safe Ingestion Process...")
        
        # 1. Idempotent Protocol Creation
        protocol, created = ClinicalProtocol.objects.get_or_create(
            title=options['title'],
            version=options['doc_version'],
            defaults={
                "issuing_body": options['issuing_body'],
                "specialty": options['specialty'],
                "valid_from": options['valid_from'],
                "is_active": True
            }
        )

        parser_strategy = ClinicalProtocolParser() if options['parser_type'] == 'protocol' else GuidelineParser()

        # 2. Get Raw Candidates (No LLM consumed here)
        candidates = parser_strategy.process_file(file_path, protocol)
        
        saved_count = 0
        skipped_count = 0

        # 3. The Credit-Wall Loop
        for item in candidates:
            # DB check BEFORE spending money
            exists = ForensicRule.objects.filter(
                protocol=protocol, 
                rule_code=item['rule_code']
            ).exists()

            if exists:
                skipped_count += 1
                continue

            # PAYWALL: Only call LLM for new rules
            print(f" [LLM] Normalizing NEW rule: {item['rule_code']}")
            metadata = extract_metadata_only(item['rule_code'], item['grounded_text'])
            
            if metadata:
                ForensicRule.objects.create(
                    protocol=protocol,
                    rule_code=item['rule_code'],
                    rule_type=metadata.get('rule_type', 'existence'),
                    text_description=f"[{item['section_name']}] {item['clean_text']}",
                    logic_config=metadata.get('logic_config', {}),
                    scope_tags=metadata.get('scope_tags', ['clinical']),
                    intent_tags=metadata.get('intent_tags', ['compliance']),
                    applicable_facility_levels=['level_2', 'level_3', 'level_4', 'level_5', 'level_6']
                )
                saved_count += 1
                if saved_count % 5 == 0:
                    print(f"[PROGRESS] {saved_count} new rules added. {skipped_count} skipped.")

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(
            f"[COMPLETE] Added {saved_count} new entries. Skipped {skipped_count} existing in {elapsed:.2f}s"
        ))