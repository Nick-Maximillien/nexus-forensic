import os
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.forensic_corpus.models import ClinicalProtocol, ForensicRule
from apps.forensic_corpus.ingestion.parser import ClinicalProtocolParser, GuidelineParser

class Command(BaseCommand):
    help = """
    Ingests a Clinical Protocol PDF and extracts deterministic Forensic Rules.
    - Creates a ClinicalProtocol parent object.
    - Parses the PDF into atomic rules (ForensicRule).
    - Uses LLM Normalizer (via parser) to extract logic_config.
    """

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to PDF file')
        parser.add_argument('--title', type=str, required=True, help='e.g. "AHA ACLS Guidelines"')
        parser.add_argument('--doc_version', type=str, required=True, help='e.g. "v2025.1"')
        parser.add_argument('--issuing_body', type=str, required=True, help='e.g. "American Heart Association"')
        parser.add_argument('--specialty', type=str, required=True, 
                            choices=['cardiology', 'oncology', 'emergency', 'general', 'neurology'])
        parser.add_argument('--valid_from', type=str, required=True, help='YYYY-MM-DD')
        # Parser selection: 'protocol' (generic hierarchical) or 'guideline' (explicit recommendations)
        parser.add_argument('--parser_type', type=str, default='protocol', 
                            choices=['protocol', 'guideline'])

    def handle(self, *args, **options):
        file_path = options['file']
        start_time = time.time()
        
        print(f"\n[INFO] Starting Ingestion Process...")
        print(f"[INFO] Target File: {file_path}")
        print(f"[INFO] Protocol Metadata: {options['title']} ({options['doc_version']})")

        # 1. Select the correct strategy based on document structure
        if options['parser_type'] == 'protocol':
            parser_strategy = ClinicalProtocolParser()
        else:
            parser_strategy = GuidelineParser()

        self.stdout.write(f"[LOG] Selected Strategy: {parser_strategy.__class__.__name__}")

        try:
            with transaction.atomic():
                # 2. Create the Constitution (ClinicalProtocol) 
                print(f"[LOG] Database Transaction Started. Creating/Fetching Protocol object...")
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
                
                if not created:
                    self.stdout.write(self.style.WARNING(f"[WARN] Protocol '{protocol}' already exists. Appending rules..."))
                else:
                    self.stdout.write(f"[SUCCESS] Created New Protocol: {protocol}")

                # 3. Parse and Extract Rules
                # The process_file method in your parser returns a list of unsaved ForensicRule objects
                self.stdout.write("[LOG] Parsing PDF and extracting logic (this relies on Vertex AI)...")
                
                # Capture rules from parser
                new_rules = parser_strategy.process_file(file_path, protocol)
                
                # LOGGING: Detailed Inspection of Extracted Logic
                print(f"\n[DEBUG] --- Extraction Inspection ({len(new_rules)} Rules Found) ---")
                for i, r in enumerate(new_rules[:5]): # Show first 5 for sanity check
                    print(f"  [{i+1}] Code: {r.rule_code} | Type: {r.rule_type}")
                    print(f"      Logic: {r.logic_config}")
                if len(new_rules) > 5:
                    print(f"      ... and {len(new_rules) - 5} more rules.")
                print(f"[DEBUG] -----------------------------------------------------\n")

                if not new_rules:
                    self.stdout.write(self.style.WARNING("[WARN] No rules were extracted. Check parser Regex or PDF content."))
                    return 

                # 4. Bulk Save to DB
                # Note: We use bulk_create for efficiency
                print(f"[LOG] Committing {len(new_rules)} rules to database...")
                ForensicRule.objects.bulk_create(new_rules)

                elapsed = time.time() - start_time
                self.stdout.write(self.style.SUCCESS(
                    f"[COMPLETE] Successfully ingested {len(new_rules)} forensic rules for {protocol.title} in {elapsed:.2f}s"
                ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[CRITICAL FAILURE] Ingestion failed: {e}"))
            import traceback
            traceback.print_exc()
            # Transaction atomic ensures no partial data is saved