import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from pgvector.django import VectorField
from django.contrib.postgres.search import SearchVectorField

# Define the formal hierarchy of health facilities in Kenya
# Used to determine the applicability of specific clinical standards
FACILITY_LEVELS = [
    ('level_1', 'Community (CHVs)'),
    ('level_2', 'Dispensaries'),
    ('level_3', 'Health Centres'),
    ('level_4', 'Sub-County Hospitals'),
    ('level_5', 'County Referral Hospitals'),
    ('level_6', 'National Referral (KNH/MTRH)'),
]

# ClinicalProtocol serves as the primary container for medical law and guidelines
# It provides the high-level context for all downstream forensic rules
class ClinicalProtocol(models.Model):
    """
    Represents a standard of care (e.g., MoH MCH Handbook).
    """
    # Mapping of medical specializations to ensure scoped retrieval
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
    
    # Minimum facility level required to provide the services described in this protocol
    min_facility_level = models.CharField(
        max_length=20, 
        choices=FACILITY_LEVELS, 
        default='level_1'
    )

    # Date ranges to ensure audits use chronologically appropriate standards
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.version})"

# ForensicRule represents an atomic, executable unit of medical logic
# It bridges the gap between human-readable prose and deterministic machine execution
class ForensicRule(models.Model):
    """
    Turns human-readable prose to deterministic machine execution
    Refers to specific constraints defined in Nexus Forensic (Temporal/Evidence/Logical)
    """
    # Defines the specific logic gate that will process the claim evidence
    RULE_TYPES = [
        # A. Temporal Consistency
        ('temporal', 'Temporal Sequence'),       # Cause < Effect
        # B. Evidence Sufficiency
        ('existence', 'Evidence Requirement'),   # "Must have ECG"
        # C. Logical Consistency & Thresholds
        ('threshold', 'Vital/Lab Threshold'),    # "HR < 50"
        ('contra', 'Contraindication'),          # "No Nitrates if BP < 90"
        ('exclusive', 'Mutually Exclusive'),     # "Cannot do A and B simultaneously"
        # Forensic science extensions for timeline and data integrity
        ('duplicate', 'Duplicate Event Detection'),           # Data Integrity
        ('conditional_existence', 'Conditional Evidence Requirement'), # Assertion -> Proof
        ('protocol_validity', 'Protocol Time Applicability'), # Metadata Consistency
        ('count_sanity', 'Event Count Sanity'),               # Outlier Detection
        ('monotonic', 'Monotonic Event Ordering'),            # Timeline Stability
    ]

    # Categorizes the rule by operational area
    APPLICABILITY_SCOPES = [
        ('clinical', 'Clinical (Patient Care)'),
        ('facility', 'Facility (Operations/Admin)'),
        ('billing', 'Billing & Coding'),
        ('legal', 'Legal & Regulatory'),
    ]

    # Categorizes the rule by the underlying risk or purpose
    RULE_INTENTS = [
        ('safety', 'Patient Safety'),
        ('quality', 'Quality of Care'),
        ('compliance', 'Regulatory Compliance'),
        ('billing', 'Billing Integrity'),
        ('documentation', 'Documentation Sufficiency'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protocol = models.ForeignKey(ClinicalProtocol, on_delete=models.CASCADE, related_name='rules')
    
    # Unique identifier for the rule (e.g., KQMH-1.2.1)
    rule_code = models.CharField(max_length=50, db_index=True) 
    
    rule_type = models.CharField(max_length=50, choices=RULE_TYPES)
    
    # The human-readable standard as found in the source document
    text_description = models.TextField() 

    # The machine-readable JSON configuration used by the Forensic Gate logic
    logic_config = models.JSONField(default=dict)

    # Multi-select field for facility levels where this specific rule is applicable
    applicable_facility_levels = ArrayField(
        models.CharField(max_length=20, choices=FACILITY_LEVELS),
        default=list,
        help_text="Facility levels where this specific rule is enforceable."
    )

    # Tags for surgical scoping during retrieval phases
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

    # Native PostgreSQL search vector for keyword-based retrieval fallback
    search_vector = SearchVectorField(null=True) 

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rule_code}: {self.rule_type}"

# RuleEmbedding stores high-dimensional vectors for semantic RAG retrieval
# Designed to be compatible with pgvector for efficient similarity searches
class RuleEmbedding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.OneToOneField(ForensicRule, on_delete=models.CASCADE, related_name='embedding')
    # 768 dimensions matches the Vertex AI Text embeddings MedLM models
    vector = VectorField(dimensions=768)