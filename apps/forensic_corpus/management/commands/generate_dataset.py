import json
import random
from django.core.management.base import BaseCommand
from apps.forensic_corpus.models import ForensicRule

class Command(BaseCommand):
    help = "Generates a class-balanced, validated dataset for training the logic parsing model."

    def handle(self, *args, **options):
        # Ensure reproducibility for dataset generation
        random.seed(42)
        
        # ======================================================
        # Validation Logic: Schema Conformance
        # Ensures that database records meet the minimum structural 
        # requirements for the deterministic reasoning engine.
        # ======================================================
        def is_valid_for_training(r):
            c = r.logic_config
            if not isinstance(c, dict): 
                return False
            
            # Logic Type: Temporal (Causal sequences)
            if r.rule_type == 'temporal':
                return 'anchor' in c and 'target' in c
            
            # Logic Type: Threshold (Numerical limits)
            if r.rule_type == 'threshold':
                return 'target_vital' in c and ('min_value' in c or 'max_value' in c)
            
            # Logic Type: Contraindication (Mutual exclusion)
            if r.rule_type == 'contra':
                return 'forbidden_treatment' in c and ('trigger_condition' in c or 'trigger_drug' in c)
            
            # Logic Type: Conditional Existence (Assertion-based requirements)
            if r.rule_type == 'conditional_existence':
                return 'trigger_assertion' in c and 'required_artifact' in c
            
            # Logic Type: Exclusive (Non-coexistence)
            if r.rule_type == 'exclusive':
                return 'event_1' in c and 'event_2' in c

            # Logic Type: Count Sanity (Frequency limits)
            if r.rule_type == 'count_sanity':
                return 'event_type' in c and 'max_count' in c

            # Logic Type: Monotonic (Chronological integrity)
            if r.rule_type == 'monotonic':
                return 'event_type' in c

            # Logic Type: Existence (Artifact verification)
            if r.rule_type == 'existence':
                return 'required_artifact' in c

            # Metadata-based rules (Require no specific JSON configuration)
            if r.rule_type in ['duplicate', 'protocol_validity']:
                return True

            return False 

        # ===================================
        # Real Data Extraction and Balancing
        # ===================================
        self.stdout.write("Initializing dataset balancing and extraction...")
        dataset = []

        # Define distribution targets to prevent model overfitting on common classes
        DISTRIBUTION_PLAN = {
            'conditional_existence': 150,
            'existence': 150,
            'temporal': 'all',
            'contra': 'all',
            'protocol_validity': 'all',
            'threshold': 'all'
        }

        self.stdout.write("\nProcessing source records...")
        for r_type, limit in DISTRIBUTION_PLAN.items():
            qs = ForensicRule.objects.filter(rule_type=r_type)
            all_rules = list(qs)
            
            # Filter records against strict schema validation
            valid_rules = [r for r in all_rules if is_valid_for_training(r)]
            
            if limit == 'all':
                selected = valid_rules
            else:
                selected = random.sample(valid_rules, min(len(valid_rules), limit))
                
            self.stdout.write(f" - {r_type.ljust(25)}: {len(all_rules)} source -> {len(selected)} validated")
            
            for r in selected:
                # Standardize output format for fine-tuning
                structured_output = {
                    "rule_type": r.rule_type,
                    "logic_config": r.logic_config,
                    "scope_tags": r.scope_tags,
                    "intent_tags": r.intent_tags
                }

                dataset.append({
                    "instruction": "You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.",
                    "input": r.text_description,
                    "output": json.dumps(structured_output, sort_keys=True)
                })

        # ======================================================
        # Synthetic Data Injection
        # Augments rare classes and negative samples (Unsupported).
        # ======================================================
        self.stdout.write("\nGenerating synthetic augmentation samples...")

        def add_synthetic(text, r_type, config, scope=['clinical'], intent=['safety']):
            structured_output = {
                "rule_type": r_type, 
                "logic_config": config,
                "scope_tags": scope,
                "intent_tags": intent
            }
            if r_type == 'unsupported':
                structured_output['scope_tags'] = []
                structured_output['intent_tags'] = []
                structured_output['summary'] = "Non-executable narrative text"

            dataset.append({
                "instruction": "You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.",
                "input": text,
                "output": json.dumps(structured_output, sort_keys=True)
            })

        # Class Augmentation: Monotonic ordering
        logs = ["Nursing notes", "Vital signs", "Anesthesia record", "Medication administration record", "Shift handovers", "Patient intake"]
        for _ in range(50):
            log = random.choice(logs)
            add_synthetic(
                text=f"{log} must be recorded in chronological sequence.", 
                r_type="monotonic", 
                config={"event_type": log.lower().replace(" ", "_")},
                scope=['clinical'], 
                intent=['integrity']
            )

        # Class Augmentation: Mutually Exclusive billing/clinical events
        pairs = [
            ("General Anesthesia", "Conscious Sedation"),
            ("MRI with Contrast", "MRI without Contrast"),
            ("Initial Hospital Care", "Subsequent Hospital Care"),
            ("Warfarin", "New Oral Anticoagulant"),
            ("IV Infusion", "IV Push"),
        ]
        for _ in range(50):
            a, b = random.choice(pairs)
            add_synthetic(
                text=f"Cannot bill {a} and {b} on the same service date.", 
                r_type="exclusive", 
                config={"event_1": a, "event_2": b},
                scope=['billing'], 
                intent=['compliance'] 
            )

        # Class Augmentation: Frequency limits
        services = ["nebulizer treatment", "physical therapy unit", "consultation", "massage therapy", "EKG interpretation"]
        for i in range(50):
            limit = random.randint(1, 8)
            svc = random.choice(services)
            add_synthetic(
                text=f"Limit {svc} to {limit} units per session.", 
                r_type="count_sanity", 
                config={"event_type": svc.split(" ")[0].lower(), "max_count": limit},
                scope=['clinical'],
                intent=['safety']
            )

        # Class Augmentation: Vital signs thresholds
        vitals = [("Systolic BP", 80, 180), ("Heart Rate", 40, 120), ("O2 Saturation", 88, 100)]
        for i in range(35):
            name, min_r, max_r = random.choice(vitals)
            val = random.randint(min_r, max_r)
            add_synthetic(
                text=f"{name} must be above {val}.", 
                r_type="threshold", 
                config={"target_vital": name, "min_value": val},
                scope=['clinical'],
                intent=['safety']
            )

        # Negative Sample Injection: Narrative Abstention
        # Trains the model to identify text that does not contain executable logic.
        narratives = [
            "The committee met in 2024 to review the guidelines.",
            "Cardiovascular disease is the leading cause of death globally.",
            "Clinicians should use their best judgment when applying these rules.",
            "This document replaces the 2019 standards of care.",
            "Patient preferences should be considered in all decisions.",
            "See Appendix A for a list of contributing authors.",
            "The level of evidence for this section is based on expert consensus.",
            "Implementation of these guidelines varies by facility.",
            "Future research is needed to establish optimal thresholds.",
            "Conflict of interest disclosures are available online."
        ]
        for _ in range(50):
            txt = random.choice(narratives)
            variation = f"{txt} [Ref: {random.randint(100,999)}]" 
            add_synthetic(
                text=variation,
                r_type="unsupported",
                config={},
                scope=[],
                intent=[]
            )

        # Finalize and export dataset
        random.shuffle(dataset) 
        filename = "medgate_finetune_FINAL.jsonl"
        with open(filename, "w") as f:
            for entry in dataset:
                f.write(json.dumps(entry) + "\n")

        self.stdout.write(self.style.SUCCESS(f"\nExecution complete: Generated {filename} with {len(dataset)} validated pairs."))