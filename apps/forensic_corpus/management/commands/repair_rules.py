import time
from django.core.management.base import BaseCommand
from apps.forensic_corpus.models import ForensicRule
from apps.forensic_corpus.ingestion.llm_normalizer import extract_metadata_only

class Command(BaseCommand):
    help = "Repairs rules where AI logic extraction previously failed."

    def handle(self, *args, **options):
        # Find broken rules (logic_config has the fallback value)
        broken_rules = ForensicRule.objects.filter(
            logic_config__required_artifact='unknown_requirement'
        )
        
        count = broken_rules.count()
        self.stdout.write(f"Found {count} rules with corrupted logic. Starting repair...")

        for i, rule in enumerate(broken_rules):
            try:
                self.stdout.write(f"Repairing {rule.rule_code}...")
                
                # Re-run the AI extraction
                metadata = extract_metadata_only(rule.rule_code, rule.text_description)
                
                # Update the rule
                rule.rule_type = metadata.get('rule_type', 'existence')
                rule.logic_config = metadata.get('logic_config', {})
                rule.save()
                
                # Rate limit respect
                time.sleep(1.0) 
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to repair {rule.rule_code}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Repair Complete! Fixed {count} rules."))