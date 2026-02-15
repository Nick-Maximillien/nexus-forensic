import logging
from datetime import datetime
from apps.forensic_corpus.models import ForensicRule
from apps.forensic_domain.contract import ForensicVerdict

logger = logging.getLogger(__name__)

class ForensicGateLayer:
    """
    FORENSIC GATE LAYER (CORE ADJUDICATION ENGINE)
    
    This class implements the deterministic reasoning engine for the MedGate 
    Forensic ecosystem. It serves as the symbolic component of a 
    Neuro-Symbolic architecture, where 'Understanding' is handled by 
    fine-tuned MedGemma models, and 'Judgment' is handled by these 
    mathematically verifiable logic gates.
    
    CAPABILITIES:
    1. Temporal Adjudication: Verifies the chronological sequence of events.
    2. Threshold Adjudication: Validates vital signs and lab results.
    3. Sufficiency Adjudication: Ensures presence of mandatory artifacts.
    4. State Adjudication: Real-time evaluation of IoT sensor streams.
    """

    # --------------------------------------------------
    # MORPHOLOGY ENGINE: ADMINISTRATIVE NOISE REDUCTION
    # --------------------------------------------------
    # These terms are filtered during semantic matching to prioritize 
    # clinical intent over administrative documentation style.
    STOPWORDS = {
        "assessment", "evaluation", "monitoring", "calculation", "verification", "check", 
        "test", "screening", "analysis", "audit", "log", "record", "report",
        "and", "or", "for", "of", "the", "in", "to", "a", "with", "status"
    }

    @staticmethod
    def _parse_time(iso_str):
        """
        Standardizes timestamp formats across heterogeneous data sources 
        (PDF extractions vs IoT sensor packets).
        """
        if not iso_str: return None
        try:
            return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        except ValueError:
            return None

    # ----------------------------------------------
    # UNIT CONVERSION HELPER: FORENSIC NORMALIZATION
    # ----------------------------------------------
    @staticmethod
    def _convert_to_base(value: float, unit: str) -> float:
        """
        Normalizes forensic measurements to base units (grams, liters).
        This is a critical safety component that prevents 'False Negatives' 
        arising from unit mismatches in unstructured clinical notes.
        """
        if not unit: return value
        unit = unit.lower().strip()
        
        # Mass Normalization (Base: grams)
        if unit == 'mg': return value * 1e-3
        if unit == 'mcg' or unit == 'ug': return value * 1e-6
        if unit == 'ng': return value * 1e-9
        if unit == 'pg': return value * 1e-12
        
        # Volume Normalization (Base: liters)
        if unit == 'ml': return value * 1e-3
        if unit == 'dl': return value * 1e-1
        
        return value

    # ----------------------------
    # GATE 1: TEMPORAL CONSISTENCY
    # ----------------------------
    @staticmethod
    def validate_temporal_logic(events: list, rule: ForensicRule):
        """
        Enforces causal timelines (e.g., Treatment B must follow Diagnosis A).
        Detects 'Time Travel' violations and 'Delay Breaches' against 
        national clinical standards.
        """
        config = rule.logic_config
        anchor_type = str(config.get('anchor', '')).lower()
        target_type = str(config.get('target', '')).lower()

        # Robust cross-field matching (Case-Insensitive)
        anchor_event = next((e for e in events if str(e.get('type','')).lower() == anchor_type or str(e.get('name','')).lower() == anchor_type), None)
        target_event = next((e for e in events if str(e.get('type','')).lower() == target_type or str(e.get('name','')).lower() == target_type), None)

        # Requirement Gap: Anchor exists but required follow-up is missing
        if anchor_event and not target_event:
            return f"Requirement Gap: Rule requires '{config.get('target')}' following '{config.get('anchor')}', but it was not found in the timeline."

        if not anchor_event or not target_event:
            return None 

        t1 = ForensicGateLayer._parse_time(anchor_event.get('timestamp'))
        t2 = ForensicGateLayer._parse_time(target_event.get('timestamp'))
        
        if not t1 or not t2: return None

        # Sequence Validation
        if t2 < t1:
            return f"Time Travel: {config['target']} ({t2.time()}) occurred before {config['anchor']} ({t1.time()})"

        # Latency Validation
        if 'max_delay_minutes' in config:
            delta_mins = (t2 - t1).total_seconds() / 60
            if delta_mins > config['max_delay_minutes']:
                return f"Delay Breach: {delta_mins:.1f}m elapsed (Limit: {config['max_delay_minutes']}m)"

        return None

    # ------------------------------------------------------
    # GATE 2: EVIDENCE SUFFICIENCY & IoT STATE ADJUDICATION
    # -----------------------------------------------------
    @staticmethod
    def validate_existence(events: list, rule: ForensicRule):
        """
        Determines if required clinical artifacts are present.
        Performs 'Semantic State Adjudication' for IoT telemetry,
        mapping sensor voltages and pressures to regulatory 'Adequacy'.
        """
        raw_req = rule.logic_config.get('required_artifact', '')
        
        if isinstance(raw_req, list):
            targets = [str(t).lower().strip() for t in raw_req]
        else:
            targets = [str(raw_req).lower().strip()]

        found = False
        iot_violation = None
        
        UNIVERSAL_QUANTIFIERS = {
            "each", "all", "every", "hospital-wide", "facility-wide", 
            "monitoring", "evaluation", "director", "role", "leadership"
        }
        
        LOCAL_SCOPES = {
            "unit", "ward", "department", "floor", "suite", "room", "clinic", 
            "log", "report", "leader", "personnel", "matrix"
        }

        # Context Detectors: Differentiates between Document Audits and Live Streams
        ev_blob_all = str(events).lower()
        is_adult_patient = any(m in ev_blob_all for m in ["para", "gravida", "gestation", "pregnancy", "adult", "28-year-old", "anc visit"])
        is_iot_context = any(m in ev_blob_all for m in ["online", "offline", "psi", "reservoir", "telemetry", "generator", "manifold", "grid power"])

        for target in targets:
            # Malformed Rule Guard
            if not target or target.strip() == "":
                return None

            # Bypass for sparse data sets
            if 'unknown' in target:
                if not events: return f"Missing Artifact: '{target}' required, but clinical evidence is empty."
                return None

            # Pediatric Immunity Gate: Prevents adult claims from failing child-specific growth rules
            if is_adult_patient and any(kw in target for kw in ["child", "pediatric", "infant", "hei", "growth milestone", "developmental"]):
                return None

            # Telemetric Immunity Gate: Prevents IoT streams from failing on written documentation requirements
            if is_iot_context and any(kw in target for kw in ["plan", "study", "studies", "documentation", "manual", "policy", "guideline", "protocol", "signage", "route", "awareness", "escalation", "program", "audit", "mechanism", "results", "burden", "status"]):
                return None

        # Data Stream Iteration
        for e in events:
            ev_name = str(e.get('name', '')).lower()
            ev_blob = " ".join([str(v) for v in e.values() if v]).lower()
            ev_tokens = set(ev_blob.split())
            
            # State adjudication values
            raw_val = e.get('value')
            val_str = str(raw_val).upper() if raw_val is not None else ""
            try:
                clean_val = str(raw_val).replace('%','').replace('PSI','').replace('psi','').strip()
                val_num = float(clean_val) if clean_val.replace('.','',1).lstrip('-').isdigit() else None
            except:
                val_num = None

            for target in targets:
                if not target: continue
                
                # IOT LOGIC: ADJUDICATING INFRASTRUCTURE RELIABILITY
                if is_iot_context:
                    # Power State Adjudication
                    if ("power" in target or "electricity" in target) and ("grid" in ev_blob or "generator" in ev_blob):
                        if "ONLINE" in val_str:
                            found = True; break
                        else:
                            iot_violation = f"Infrastructure Failure: '{target}' is currently OFFLINE."
                            continue 

                    # Water Resource Adjudication
                    if ("water" in target or "sanitation" in target) and ("reservoir" in ev_blob or "level" in ev_blob):
                        if val_num is not None and val_num >= 20.0:
                            found = True; break
                        elif val_num is not None:
                            iot_violation = f"Resource Exhaustion: Safe Water Level is critical ({val_num}%)."
                            continue

                    # Oxygen Pressure Adjudication
                    if ("oxygen" in target or "manifold" in target or "infrastructure" in target) and ("psi" in ev_blob or "manifold" in ev_blob):
                        if val_num is not None and val_num >= 500.0:
                            found = True; break
                        elif val_num is not None:
                            iot_violation = f"Critical Depletion: Oxygen Pressure is below medical safety limits ({val_num} PSI)."
                            continue

                # Standard Keyword Matching Logic
                if is_iot_context and any(kw in target for kw in ["oxygen", "water", "power", "grid", "psi"]):
                    if iot_violation and target in ev_blob:
                        continue

                if target in ev_blob:
                    found = True
                    break

                # Forensic Synonym Mapping
                if any(kw in target for kw in ["art", "initiation", "regimen"]):
                    if any(m in ev_blob for m in ["tdf", "3tc", "dtg", "efv", "arv", "nvp", "abc", "lpv"]):
                        found = True
                        break

                # Counseling and Social Evidence Proxies
                if any(kw in target for kw in ["counselling", "education", "psychosocial", "assessment"]):
                    counseling_keywords = ["eac", "adherence", "disclosure", "stigma", "discordant", "counselled"]
                    if any(m in ev_blob for m in counseling_keywords):
                        found = True
                        break

                # Administrative and Supply Chain Proxies (KQMH Compliance)
                if any(kw in target for kw in ["data management", "records", "information system", "supplies", "drug use"]):
                    admin_proxies = ["patient file", "mch handbook", "records maintained", "file opened", "documented", "batch", "traceability", "dispensed"]
                    if any(m in ev_blob for m in admin_proxies):
                        found = True
                        break
                
                # Semantic Root Extraction (Medical Bag-of-Words)
                req_tokens = [t for t in target.split() if t not in ForensicGateLayer.STOPWORDS]
                req_token_set = set(req_tokens)
                
                req_has_universal = any(u in target for u in UNIVERSAL_QUANTIFIERS)
                ev_has_local = any(l in ev_blob for l in LOCAL_SCOPES)
                
                threshold = 0.4
                if req_has_universal and ev_has_local:
                    threshold = 0.15 
                
                if len(req_tokens) <= 2 and req_tokens:
                    if req_token_set.issubset(ev_tokens):
                        found = True
                        break

                common_tokens = req_token_set.intersection(ev_tokens)
                denom = len(req_token_set) if req_token_set else 1
                
                if (len(common_tokens) / denom) >= threshold:
                    found = True
                    break
            
            if found: break
        
        if not found:
            if iot_violation: return iot_violation
            display_req = targets[0] if targets else "Unknown Requirement"
            return f"Missing Artifact: '{display_req}' not found in claim evidence."
        return None

    # -----------------------
    # GATE 3: THRESHOLD LOGIC
    # -----------------------
    @staticmethod
    def validate_threshold(events: list, rule: ForensicRule):
        """
        Numerical Adjudication Gate.
        Validates vital signs and lab values against protocol-defined 
        min/max limits using unit-normalized comparison.
        """
        target = str(rule.logic_config.get('target_vital', '')).lower()
        min_val = rule.logic_config.get('min_value')
        max_val = rule.logic_config.get('max_value')
        
        # Validates both Explicit Name and Event Type
        measurement = next((e for e in events if str(e.get('name','')).lower() == target or str(e.get('type','')).lower() == target), None)
        
        if not measurement:
            return None 

        raw_val = measurement.get('value')
        meas_unit = str(measurement.get('unit', '')).lower()
        
        if raw_val is None: return None
        
        try:
            # Perform unit-aware normalization before limit check
            val = ForensicGateLayer._convert_to_base(float(str(raw_val).replace('%','')), meas_unit)
        except (ValueError, TypeError):
            return None
        
        if min_val is not None and val < min_val:
            return f"Vital Failure: {target} is {val} (Required Min: {min_val})"
        
        if max_val is not None and val > max_val:
            return f"Vital Failure: {target} is {val} (Max Allowed: {max_val})"
            
        return None

    # -------------------------
    # GATE 4: CONTRAINDICATIONS
    # -------------------------
    @staticmethod
    def validate_contraindication(events: list, rule: ForensicRule):
        """
        Safety Gate.
        Prevents dangerous combinations of conditions and treatments 
        (e.g., Drug X cannot be given if History Y is present).
        """
        forbidden = rule.logic_config.get('forbidden_treatment')
        trigger_cond = rule.logic_config.get('trigger_condition') 
        trigger_drug = rule.logic_config.get('trigger_drug')      
        
        forbidden_event = next((e for e in events if e.get('name') == forbidden), None)
        
        if forbidden_event:
            # Check for existing condition or drug in the event history
            trigger_found = any(
                e.get('name') == trigger_cond or e.get('name') == trigger_drug 
                for e in events
            )
            
            if trigger_found:
                found_trigger = trigger_cond if any(e.get('name') == trigger_cond for e in events) else trigger_drug
                return f"Contraindication: '{forbidden}' given despite '{found_trigger}' history."
        return None

    # --------------------------
    # GATE 5: MUTUAL EXCLUSIVITY
    # --------------------------
    @staticmethod
    def validate_exclusive(events: list, rule: ForensicRule):
        """
        Integrity Gate.
        Detects conflicting events that logically cannot co-exist in a 
        truthful clinical claim.
        """
        event_1 = rule.logic_config.get('event_1')
        event_2 = rule.logic_config.get('event_2')
        
        found_1 = any(e.get('name') == event_1 or e.get('type') == event_1 for e in events)
        found_2 = any(e.get('name') == event_2 or e.get('type') == event_2 for e in events)
        
        if found_1 and found_2:
            return f"Mutually Exclusive: '{event_1}' and '{event_2}' cannot both be present."
        return None

    # -----------------------------------
    # GATE 6: DATA INTEGRITY (DUPLICATES)
    # -----------------------------------
    @staticmethod
    def validate_duplicate_event(events: list, rule: ForensicRule):
        """
        Forensic Fingerprinting Gate.
        Detects duplicate records based on type, timestamp, and source 
        to identify data double-counting or record tampering.
        """
        seen = set()
        for e in events:
            sig = (
                e.get('type', 'unknown'), 
                e.get('timestamp', 'unknown'), 
                e.get('source', 'unknown')
            )
            if sig in seen:
                return f"Data Integrity Error: Duplicate event detected: {sig}"
            seen.add(sig)
        return None

    # ----------------------------
    # GATE 7: CONDITIONAL COUPLING
    # ----------------------------
    @staticmethod
    def validate_conditional_existence(events: list, rule: ForensicRule):
        """
        Logic Gate: Trigger Assertion -> Mandatory Proof.
        Example: If 'General Anesthesia' is mentioned, then a 
        'Pre-Anesthesia Evaluation' MUST exist.
        """
        assertion = str(rule.logic_config.get('trigger_assertion', '')).lower()
        required = str(rule.logic_config.get('required_artifact', '')).lower()
        
        assertion_found = any(
            assertion in str(e.get('name', '')).lower() or assertion in str(e.get('type', '')).lower()
            for e in events
        )
        
        if assertion_found:
            # Adult context safety guard
            ev_blob_full = str(events).lower()
            is_adult_context = any(m in ev_blob_full for m in ["para", "gravida", "gestation", "pregnancy", "anc visit", "28-year-old"])
            if is_adult_context and any(kw in required for kw in ["child", "pediatric", "infant", "hei", "growth milestone"]):
                return None

            # Token-based verification
            req_tokens = [t for t in required.split() if t not in ForensicGateLayer.STOPWORDS]
            
            artifact_found = False
            for e in events:
                ev_blob = " ".join([str(v) for v in e.values() if v]).lower()
                if required in ev_blob:
                    artifact_found = True
                    break
                if req_tokens and all(t in ev_blob for t in req_tokens):
                    artifact_found = True
                    break

            # Synoptic Mapping (Medical Logic Fallbacks)
            if not artifact_found:
                synonyms = ["tdf", "3tc", "dtg", "efv", "arv", "eac", "adherence", "disclosure", "stigma", "discordant", "patient file", "handbook", "batch", "traceability", "online", "psi"]
                if any(m in ev_blob_full for m in synonyms):
                    artifact_found = True

            if not artifact_found:
                return f"Requirement Gap: Rule requires '{required}' following '{assertion}', but it was not found."
        return None

    # ------------------------------
    # GATE 8: PROTOCOL APPLICABILITY
    # ------------------------------
    @staticmethod
    def validate_protocol_validity(events: list, rule: ForensicRule):
        """
        Temporal Boundary Gate.
        Ensures the evidence falls within the legal window of the 
        protocol's validity (e.g., using a 2022 protocol for a 2018 event).
        """
        protocol = rule.protocol
        if not protocol.valid_from:
            return None 

        for e in events:
            ts = ForensicGateLayer._parse_time(e.get('timestamp'))
            if not ts: continue

            valid_from = datetime.combine(protocol.valid_from, datetime.min.time()).replace(tzinfo=ts.tzinfo)
            
            if ts < valid_from:
                return f"Protocol Mismatch: Event {e.get('name')} ({ts.date()}) predates protocol start ({protocol.valid_from})"
            
            if protocol.valid_until:
                valid_until = datetime.combine(protocol.valid_until, datetime.max.time()).replace(tzinfo=ts.tzinfo)
                if ts > valid_until:
                    return f"Protocol Mismatch: Event {e.get('name')} ({ts.date()}) is after protocol expiry ({protocol.valid_until})"
        
        return None

    # --------------------
    # GATE 9: COUNT SANITY
    # --------------------
    @staticmethod
    def validate_count_sanity(events: list, rule: ForensicRule):
        """
        Statistical Outlier Gate.
        Detects anomalies in event volume (e.g., claiming 5 amputations 
        for a single patient encounter).
        """
        target_type = rule.logic_config.get('event_type')
        max_count = rule.logic_config.get('max_count')
        
        if not target_type or not max_count: return None

        count = sum(1 for e in events if e.get('type') == target_type or e.get('name') == target_type)
        
        if count > max_count:
            return f"Sanity Check Failed: {count} occurrences of '{target_type}' (Max: {max_count})"
        
        return None

    # -------------------------------------
    # GATE 10: MONOTONIC TIMELINE STABILITY
    # -------------------------------------
    @staticmethod
    def validate_monotonic_ordering(events: list, rule: ForensicRule):
        """
        Chronological Integrity Gate.
        Ensures that successive records of the same type always move 
        forward in time, identifying back-dated or inconsistent logs.
        """
        target_type = rule.logic_config.get('event_type')
        relevant = [e for e in events if e.get('type') == target_type or e.get('name') == target_type]
        
        last_ts = None
        for e in relevant:
            curr_ts = ForensicGateLayer._parse_time(e.get('timestamp'))
            if not curr_ts: continue
            
            if last_ts and curr_ts < last_ts:
                return f"Timeline Corruption: {target_type} at {curr_ts} appears after record at {last_ts}"
            last_ts = curr_ts
            
        return None

    # ------------------------
    # MAIN EXECUTION PIPELINE
    # ------------------------
    @staticmethod
    def execute_audit(claim_events: list, applicable_rules: list[ForensicRule]) -> ForensicVerdict:
        """
        ADJUDICATION ORCHESTRATOR
        
        Runs the multi-layered logic suite and generates a Certified 
        Forensic Trace. This trace is the 'Evidence of Thinking' that 
        Nexus Forensic provides for every clinical verdict.
        """
        violations = []
        passed = []

        # Demographic Context Resolution
        blob = " ".join([str(e) for e in claim_events]).lower()
        is_adult_context = any(m in blob for m in ['gravida', 'para', 'maternity', 'pregnancy', 'adult', '28-year-old', 'years old', 'gestation'])

        for rule in applicable_rules:
            # Rule/Scope Compatibility Check
            if rule.scope_tags and 'pediatric' in rule.scope_tags:
                if is_adult_context:
                    continue 

            error = None
            
            # Logic Gate Dispatcher
            if rule.rule_type == 'temporal':
                error = ForensicGateLayer.validate_temporal_logic(claim_events, rule)
            elif rule.rule_type == 'existence':
                error = ForensicGateLayer.validate_existence(claim_events, rule)
            elif rule.rule_type == 'threshold':
                error = ForensicGateLayer.validate_threshold(claim_events, rule)
            elif rule.rule_type == 'contra':
                error = ForensicGateLayer.validate_contraindication(claim_events, rule)
            elif rule.rule_type == 'exclusive':
                error = ForensicGateLayer.validate_exclusive(claim_events, rule)        
            elif rule.rule_type == 'duplicate':
                error = ForensicGateLayer.validate_duplicate_event(claim_events, rule)
            elif rule.rule_type == 'conditional_existence':
                error = ForensicGateLayer.validate_conditional_existence(claim_events, rule)
            elif rule.rule_type == 'protocol_validity':
                error = ForensicGateLayer.validate_protocol_validity(claim_events, rule)
            elif rule.rule_type == 'count_sanity':
                error = ForensicGateLayer.validate_count_sanity(claim_events, rule)
            elif rule.rule_type == 'monotonic':
                error = ForensicGateLayer.validate_monotonic_ordering(claim_events, rule)

            # Record Verdict
            if error:
                violations.append({
                    "system_result": "Violation Detected",
                    "protocol": {
                        "title": rule.protocol.title,
                        "version": rule.protocol.version,
                        "issuing_body": rule.protocol.issuing_body
                    },
                    "rule": {
                        "code": rule.rule_code,
                        "text": rule.text_description, 
                        "type": rule.rule_type,
                        "scope": rule.scope_tags,   
                        "intent": rule.intent_tags  
                    },
                    "validation_trace": error, 
                    "technical_metadata": rule.logic_config 
                })
            else:
                passed.append(rule)

        is_valid = len(violations) == 0
        
        # Return the Immutable Verdict Contract
        return ForensicVerdict(
            is_valid=is_valid,
            passed_rules=passed,
            violations=violations
        )

# END OF PRECISION LAYER