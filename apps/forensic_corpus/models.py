import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from pgvector.django import VectorField
from django.contrib.postgres.search import SearchVectorField

# 1. The "Constitution" of Medicine: Clinical Protocols
class ClinicalProtocol(models.Model):
    """
    Represents a standard of care (e.g., AHA ACLS).
    """
    SPECIALTIES = [
        ('cardiology', 'Cardiology'),
        ('oncology', 'Oncology'),
        ('emergency', 'Emergency Medicine'),
        ('general', 'General Practice'),
        ('neurology', 'Neurology'),
        ('internal_medicine', 'Internal Medicine'),
        ('family_medicine', 'Family Medicine'),
        ('pediatrics', 'Pediatrics'),
        ('obstetrics_gynecology', 'Obstetrics & Gynecology'),
        ('surgery_general', 'General Surgery'),
        ('orthopedics', 'Orthopedics'),
        ('anesthesiology', 'Anesthesiology'),
        ('critical_care', 'Critical Care'),
        ('infectious_disease', 'Infectious Disease'),
        ('pulmonology', 'Pulmonology'),
        ('nephrology', 'Nephrology'),
        ('gastroenterology', 'Gastroenterology'),
        ('endocrinology', 'Endocrinology'),
        ('hematology', 'Hematology'),
        ('radiology', 'Radiology'),
        ('pathology', 'Pathology'),
        ('psychiatry', 'Psychiatry'),
        ('dermatology', 'Dermatology'),
        ('urology', 'Urology'),
        ('ophthalmology', 'Ophthalmology'),
        ('otolaryngology', 'Otolaryngology (ENT)'),
        ('rehabilitation', 'Physical Medicine & Rehabilitation'),
        ('palliative_care', 'Palliative Care'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)  # e.g., "AHA ACS Management Guidelines"
    version = models.CharField(max_length=50) # e.g., "v2025.1"
    issuing_body = models.CharField(max_length=255) # e.g., "American Heart Association"
    specialty = models.CharField(max_length=50, choices=SPECIALTIES)
    
    # Validity Window
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.version})"

# 2. Atomic Logic Units: The Forensic Rules
class ForensicRule(models.Model):
    """
    Equivalent to LegalUnit, but executable.
    Refers to specific constraints defined in MedGate (Temporal/Evidence/Logical)
    """
    RULE_TYPES = [
        # A. Temporal Consistency
        ('temporal', 'Temporal Sequence'),       # Cause < Effect

        # B. Evidence Sufficiency
        ('existence', 'Evidence Requirement'),   # "Must have ECG"
        
        # C. Logical Consistency & Thresholds
        ('threshold', 'Vital/Lab Threshold'),    # "HR < 50"
        ('contra', 'Contraindication'),          # "No Nitrates if BP < 90"
        ('exclusive', 'Mutually Exclusive'),     # "Cannot do A and B simultaneously"

        # --- FORENSIC SCIENCE EXTENSIONS  ---
        ('duplicate', 'Duplicate Event Detection'),           # Data Integrity
        ('conditional_existence', 'Conditional Evidence Requirement'), # Assertion -> Proof
        ('protocol_validity', 'Protocol Time Applicability'), # Metadata Consistency
        ('count_sanity', 'Event Count Sanity'),               # Outlier Detection
        ('monotonic', 'Monotonic Event Ordering'),            # Timeline Stability
    ]

    # SCOPE DEFINITIONS (Where does this apply?)
    APPLICABILITY_SCOPES = [
        ('clinical', 'Clinical (Patient Care)'),
        ('facility', 'Facility (Operations/Admin)'),
        ('billing', 'Billing & Coding'),
        ('legal', 'Legal & Regulatory'),
    ]

    # INTENT DEFINITIONS (Why does this exist?)
    RULE_INTENTS = [
        ('safety', 'Patient Safety'),
        ('quality', 'Quality of Care'),
        ('compliance', 'Regulatory Compliance'),
        ('billing', 'Billing Integrity'),
        ('documentation', 'Documentation Sufficiency'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protocol = models.ForeignKey(ClinicalProtocol, on_delete=models.CASCADE, related_name='rules')
    
    # UPGRADE: Index for exact "Tag A-0045" lookups
    rule_code = models.CharField(max_length=50, db_index=True) 
    
    rule_type = models.CharField(max_length=50, choices=RULE_TYPES)
    
    # The human-readable standard (for the LLM to cite)
    text_description = models.TextField() 

    # The machine-readable logic (for the Django Gate to execute)
    logic_config = models.JSONField(default=dict)

    # Deterministic Scope & Intent Tags
    # This enables "Surgical Scoping" without keyword hacking
    scope_tags = ArrayField(
        models.CharField(max_length=50, choices=APPLICABILITY_SCOPES),
        default=list,
        help_text="Deterministic enforcement contexts (e.g., ['clinical'])"
    )

    intent_tags = ArrayField(
        models.CharField(max_length=50, choices=RULE_INTENTS),
        default=list,
        help_text="Why this rule exists (e.g., ['safety', 'compliance'])"
    )

    # UPGRADE: Full-Text Search Vector for Hybrid Search
    search_vector = SearchVectorField(null=True) 

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rule_code}: {self.rule_type}"

# 3. Semantic Search Vector
class RuleEmbedding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.OneToOneField(ForensicRule, on_delete=models.CASCADE, related_name='embedding')
    vector = VectorField(dimensions=768) # Compatible with Vertex AI