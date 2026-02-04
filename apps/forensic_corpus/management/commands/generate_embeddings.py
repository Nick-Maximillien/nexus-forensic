import time
from django.core.management.base import BaseCommand
from apps.forensic_corpus.models import ForensicRule, RuleEmbedding
from apps.forensic_rag.utils import get_embedding

class Command(BaseCommand):
    help = "Generates pgvector embeddings for new Forensic Rules."

    def handle(self, *args, **options):
        print(f"\n[INFO] Starting Vectorization Process...")

        # 1. Fetch rules that lack embeddings
        # We query for rules where the 'embedding' relation is null 
        pending_rules = ForensicRule.objects.filter(
            embedding__isnull=True,
            protocol__is_active=True # Only embed active standards 
        ).select_related('protocol')

        total = pending_rules.count()
        self.stdout.write(f"[LOG] Found {total} forensic rules pending vectorization.")

        if total == 0:
            print("[INFO] No pending rules found. Exiting.")
            return

        success_count = 0
        
        for i, rule in enumerate(pending_rules):
            try:
                # 2. Construct Semantic Payload
                # We combine the Protocol Context + Rule Code + Text Description
                semantic_text = (
                    f"{rule.protocol.title} - {rule.rule_code} ({rule.get_rule_type_display()})\n"
                    f"{rule.text_description}"
                )
                
                # LOGGING: Peek at what we are embedding
                # print(f"[DEBUG] Embedding Payload ({rule.rule_code}): {semantic_text[:50]}...")

                # 3. Call Vertex AI (text-embedding-004) 
                vector = get_embedding(semantic_text)
                
                # 4. Validation (Prevent Zero-Vector Poisoning)
                if not vector or (len(vector) > 0 and vector[0] == 0):
                    self.stdout.write(self.style.WARNING(f"[WARN] Skipping {rule.rule_code}: Empty vector returned (Quota or Auth issue)."))
                    time.sleep(5) # Cool down
                    continue

                # 5. Save RuleEmbedding
                RuleEmbedding.objects.create(
                    rule=rule,
                    vector=vector
                )
                
                success_count += 1
                
                # Progress Logging
                if success_count % 5 == 0 or success_count == total:
                    self.stdout.write(f"[PROGRESS] Indexed {success_count}/{total} rules... (Last: {rule.rule_code})")

                # 6. Rate Limiting (Vertex AI Quota Protection)
                time.sleep(1.0) 

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[ERROR] Failed to index {rule.rule_code}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"[COMPLETE] Successfully vectorized {success_count} rules."))