import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from pgvector.django import L2Distance

from apps.forensic_corpus.models import ForensicRule, ClinicalProtocol, RuleEmbedding

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Stitches 2009 'Spirit' intent with 2018 'Letter' logic configs."

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Actually apply the changes to the database.',
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.15,
            help='Distance threshold for semantic matching (lower is stricter). Default 0.15.',
        )

    def handle(self, *args, **options):
        commit = options['commit']
        dist_threshold = options['threshold']
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write(" KQMH FORENSIC STITCHING ENGINE")
        self.stdout.write("="*50 + "\n")

        if not commit:
            self.stdout.write(self.style.WARNING(" [SAFE MODE] DRY RUN: No data will be modified.\n"))

        try:
            with transaction.atomic():
                # 1. Fetch the 2018 "Letter" Protocol
                letter_proto = ClinicalProtocol.objects.filter(version="2018").first()
                if not letter_proto:
                    self.stdout.write(self.style.ERROR(" [CRITICAL] 2018 Checklist protocol not found. Ingest it first."))
                    return

                # 2. Iterate through all 2009 "Spirit" Rules
                spirit_rules = ForensicRule.objects.filter(
                    protocol__version="2009"
                ).select_related('protocol')

                stitched_count = 0
                noise_count = 0

                self.stdout.write(f" [INFO] Analyzing {spirit_rules.count()} Spirit Rules...")

                for spirit_rule in spirit_rules:
                    # Clean the ID for matching
                    clean_id = spirit_rule.rule_code.strip()

                    # FILTER: Skip obvious noise captured during ingestion
                    if clean_id.replace("ID ", "").count('.') > 3:
                        noise_count += 1
                        continue

                    letter_match = None

                    # TIER 1: Direct ID Anchor Match
                    letter_match = ForensicRule.objects.filter(
                        protocol=letter_proto,
                        rule_code=clean_id
                    ).first()

                    # TIER 2: Semantic Bridge (Similarity Search)
                    if not letter_match:
                        spirit_emb = RuleEmbedding.objects.filter(rule=spirit_rule).first()
                        if spirit_emb:
                            letter_match = ForensicRule.objects.filter(
                                protocol=letter_proto
                            ).annotate(
                                distance=L2Distance('embedding__vector', spirit_emb.vector)
                            ).filter(distance__lt=dist_threshold).order_by('distance').first()

                    # TIER 3: Logic Synthesis
                    if letter_match:
                        # Extract the 2018 logic
                        new_logic = letter_match.logic_config.copy()
                        
                        # Traceability metadata
                        new_logic['_stitched_from'] = letter_match.rule_code
                        new_logic['_verification_source'] = "2018_KQMH_HOSPITAL"
                        
                        # PRESERVATION GUARANTEE:
                        # We overwrite ONLY logic_config.
                        # Text description, intent tags, and facility levels remain 2009.
                        if commit:
                            spirit_rule.logic_config.update(new_logic)
                            spirit_rule.save()
                        
                        stitched_count += 1
                        self.stdout.write(f"  [MATCH] {spirit_rule.rule_code} (2009) <- {letter_match.rule_code} (2018)")
                    else:
                        # self.stdout.write(self.style.NOTICE(f"  [RETAIN] {spirit_rule.rule_code}: Standard 2009 logic kept."))
                        pass

                if commit:
                    self.stdout.write(self.style.SUCCESS(
                        f"\n SUCCESS: Stitched {stitched_count} rules. Filtered {noise_count} noise artifacts."
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"\n DRY RUN COMPLETE: Would have updated {stitched_count} rules."
                    ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f" [ERROR] Stitching failed: {str(e)}"))
            logger.error(f"Stitching error: {e}", exc_info=True)