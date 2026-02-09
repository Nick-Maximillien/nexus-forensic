from dataclasses import dataclass, field
from typing import List, Optional, Dict
from apps.forensic_corpus.models import ForensicRule

@dataclass
class ForensicAuditPlan:
    """
    Wire 1: The Blueprint. 
    Defines the scope of the audit based on the claim metadata.
    """
    # 1. Mandatory Fields
    specialty_context: str  # e.g., "cardiology"
    event_timestamp: str    # ISO format

    # 2. Optional Fields
    patient_age: Optional[int] = None
    active_protocols_only: bool = True
    
    # SCOPE CONTROL: 'clinical' (Patient) vs 'facility' (Ops)
    audit_scope: str = "clinical" 

    #  Facility level awareness for the Kenyan Pilot
    facility_level: Optional[str] = "level_2" 

@dataclass
class ForensicVerdict:
    """
    Wire 3: The Gatekeeper. 
    If this is False, MedGemma is NEVER called.
    """
    is_valid: bool
    passed_rules: List[ForensicRule] = field(default_factory=list)
    violations: List[Dict[str, str]] = field(default_factory=list)
    audit_trail: str = ""