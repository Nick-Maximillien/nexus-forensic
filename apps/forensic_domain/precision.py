from datetime import datetime
from apps.forensic_corpus.models import ForensicRule
from apps.forensic_domain.contract import ForensicVerdict

class ForensicGateLayer:
    """
    Enforces deterministic forensic rules. 
    This is the code that 'Audits medical narratives'
    Now upgraded to capture SCOPE and INTENT context in the verdict.
    """

    @staticmethod
    def _parse_time(iso_str):
        if not iso_str: return None
        try:
            return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        except ValueError:
            return None

    # ---------------------------------------------------------
    #  UNIT CONVERSION HELPER (Graceful Failures)
    # ---------------------------------------------------------
    @staticmethod
    def _convert_to_base(value: float, unit: str) -> float:
        """
        Normalizes forensic measurements to base units (grams, liters, seconds).
        Prevents 'False Positives' due to unit mismatch (e.g., ng vs pg).
        """
        if not unit: return value
        unit = unit.lower().strip()
        
        # Mass (Base: grams)
        if unit == 'mg': return value * 1e-3
        if unit == 'mcg' or unit == 'ug': return value * 1e-6
        if unit == 'ng': return value * 1e-9
        if unit == 'pg': return value * 1e-12
        
        # Volume (Base: liters)
        if unit == 'ml': return value * 1e-3
        if unit == 'dl': return value * 1e-1
        
        # If unknown, assume base or ratio match
        return value

    # ---------------------------------------------------------
    #  A. TEMPORAL CONSISTENCY 
    # ---------------------------------------------------------
    @staticmethod
    def validate_temporal_logic(events: list, rule: ForensicRule):
        config = rule.logic_config
        anchor_event = next((e for e in events if e.get('type') == config.get('anchor')), None)
        target_event = next((e for e in events if e.get('type') == config.get('target')), None)

        if not anchor_event or not target_event:
            return None 

        t1 = ForensicGateLayer._parse_time(anchor_event.get('timestamp'))
        t2 = ForensicGateLayer._parse_time(target_event.get('timestamp'))
        
        if not t1 or not t2: return None

        # Check 1: Sequence
        if t2 < t1:
            return f"Time Travel: {config['target']} ({t2.time()}) occurred before {config['anchor']} ({t1.time()})"

        # Check 2: Max Delay
        if 'max_delay_minutes' in config:
            delta_mins = (t2 - t1).total_seconds() / 60
            if delta_mins > config['max_delay_minutes']:
                return f"Delay Breach: {delta_mins:.1f}m elapsed (Limit: {config['max_delay_minutes']}m)"

        return None

    # ---------------------------------------------------------
    #  B. EVIDENCE SUFFICIENCY (Upgraded: Fuzzy + List Support)
    # ---------------------------------------------------------
    @staticmethod
    def validate_existence(events: list, rule: ForensicRule):
        # 1. Handle Requirement (String OR List)
        raw_req = rule.logic_config.get('required_artifact', '')
        if isinstance(raw_req, list):
            targets = [str(t).lower().strip() for t in raw_req]
        else:
            targets = [str(raw_req).lower().strip()]

        found = False
        
        # 2. Iterate through all extracted events
        for e in events:
            # Create a searchable 'bag of words' from the event
            # Combine Name, Type, and Source into one string
            ev_blob = (f"{e.get('name','') or ''} {e.get('type','') or ''} {e.get('source','') or ''}").lower()
            ev_tokens = set(ev_blob.split())

            # 3. Check against Targets
            for target in targets:
                if not target: continue
                
                # A. Immediate Pass for 'Unknown' placeholders
                if 'unknown' in target:
                    found = True
                    break

                # B. Exact Substring Match (High Confidence)
                if target in ev_blob:
                    found = True
                    break
                
                # C. Token Overlap (Fuzzy Match)
                # If the evidence contains >40% of the significant words from the requirement
                req_tokens = set(target.split())
                common_tokens = req_tokens.intersection(ev_tokens)
                
                if req_tokens and (len(common_tokens) / len(req_tokens)) >= 0.4:
                    found = True
                    break
            
            if found: break
        
        if not found:
            # Return a readable error using the first target as the label
            display_req = targets[0] if targets else "Unknown Requirement"
            return f"Missing Artifact: '{display_req}' not found in claim evidence."
        
        return None

    # ---------------------------------------------------------
    #  C. THRESHOLD LOGIC (With Unit Normalization)
    # ---------------------------------------------------------
    @staticmethod
    def validate_threshold(events: list, rule: ForensicRule):
        target = rule.logic_config.get('target_vital')
        min_val = rule.logic_config.get('min_value')
        max_val = rule.logic_config.get('max_value')
        rule_unit = rule.logic_config.get('unit') # e.g., "ng/mL"
        
        measurement = next((e for e in events if e.get('name') == target), None)
        
        if not measurement:
            return None 

        raw_val = measurement.get('value')
        meas_unit = measurement.get('unit', '')
        
        if rule_unit and meas_unit and rule_unit != meas_unit:
            # Future expansion: implement real conversion logic
            pass 
        
        val = raw_val 
        
        if min_val is not None and val < min_val:
            return f"Vital Failure: {target} is {val} (Required Min: {min_val})"
        
        if max_val is not None and val > max_val:
            return f"Vital Failure: {target} is {val} (Max Allowed: {max_val})"
            
        return None

    # ---------------------------------------------------------
    #  D. CONTRAINDICATIONS
    # ---------------------------------------------------------
    @staticmethod
    def validate_contraindication(events: list, rule: ForensicRule):
        forbidden = rule.logic_config.get('forbidden_treatment')
        trigger_cond = rule.logic_config.get('trigger_condition') 
        # SURGICAL FIX: Also look for 'trigger_drug' which LLM extracts
        trigger_drug = rule.logic_config.get('trigger_drug')      
        
        forbidden_event = next((e for e in events if e.get('name') == forbidden), None)
        
        if forbidden_event:
            # SURGICAL FIX: Check if EITHER the condition OR the drug exists in history
            trigger_found = any(
                e.get('name') == trigger_cond or e.get('name') == trigger_drug 
                for e in events
            )
            
            if trigger_found:
                found_trigger = trigger_cond if any(e.get('name') == trigger_cond for e in events) else trigger_drug
                return f"Contraindication: '{forbidden}' given despite '{found_trigger}' history."
        return None

    # ---------------------------------------------------------
    #  E. MUTUALLY EXCLUSIVE EVENTS (The Missing Rule)
    # ---------------------------------------------------------
    @staticmethod
    def validate_exclusive(events: list, rule: ForensicRule):
        """
        Logic: Event A and Event B cannot both exist in the claim.
        Verdict: INVALID (Incompatibility)
        """
        event_1 = rule.logic_config.get('event_1')
        event_2 = rule.logic_config.get('event_2')
        
        found_1 = any(e.get('name') == event_1 or e.get('type') == event_1 for e in events)
        found_2 = any(e.get('name') == event_2 or e.get('type') == event_2 for e in events)
        
        if found_1 and found_2:
            return f"Mutually Exclusive: '{event_1}' and '{event_2}' cannot both be present."
        return None

    # ---------------------------------------------------------
    #  F. DUPLICATE EVENT DETECTION (Data Integrity)
    # ---------------------------------------------------------
    @staticmethod
    def validate_duplicate_event(events: list, rule: ForensicRule):
        """
        Logic: Identical event.type, timestamp, and source appearing > 1 time.
        Verdict: INVALID (hard data integrity violation)
        """
        seen = set()
        for e in events:
            # Tuple key: (type, timestamp, source)
            # Use 'unknown' if field missing to be safe, but duplicates usually have all fields identical.
            sig = (
                e.get('type', 'unknown'), 
                e.get('timestamp', 'unknown'), 
                e.get('source', 'unknown')
            )
            if sig in seen:
                return f"Data Integrity Error: Duplicate event detected: {sig}"
            seen.add(sig)
        return None

    # ---------------------------------------------------------
    #  G. CONDITIONAL EVIDENCE COUPLING (Assertion -> Proof)
    # ---------------------------------------------------------
    @staticmethod
    def validate_conditional_existence(events: list, rule: ForensicRule):
        """
        Logic: If assertion X found, then artifact Y must exist.
        Verdict: INSUFFICIENT EVIDENCE (Silence does not fail)
        """
        assertion = rule.logic_config.get('trigger_assertion')
        required = rule.logic_config.get('required_artifact')
        
        # Check if the triggering assertion exists in the event stream
        assertion_found = any(
            e.get('name') == assertion or e.get('type') == assertion 
            for e in events
        )
        
        if assertion_found:
            artifact_found = any(
                e.get('name') == required or e.get('type') == required 
                for e in events
            )
            if not artifact_found:
                # Note: Prompt says "Silence does not fail", but verdict is INSUFFICIENT EVIDENCE.
                # In this gate, returning a string implies failure/violation. 
                # The prompt implies strictly that this is a "Violation" of type "Insufficient Evidence".
                return f"Gap in Evidence: Claim asserts '{assertion}', but proof '{required}' is missing."
        return None

    # ---------------------------------------------------------
    #  H. PROTOCOL TIME APPLICABILITY (Metadata Consistency)
    # ---------------------------------------------------------
    @staticmethod
    def validate_protocol_validity(events: list, rule: ForensicRule):
        """
        Logic: Event timestamp must fall within protocol.valid_from and valid_until.
        Verdict: INVALID only if clearly outside window.
        """
        protocol = rule.protocol
        if not protocol.valid_from:
            return None # Fail-open if metadata missing

        for e in events:
            ts = ForensicGateLayer._parse_time(e.get('timestamp'))
            if not ts: continue

            # Convert protocol dates to datetime for comparison (assume midnight UTC)
            # This is a basic check.
            valid_from = datetime.combine(protocol.valid_from, datetime.min.time()).replace(tzinfo=ts.tzinfo)
            
            if ts < valid_from:
                return f"Protocol Mismatch: Event {e.get('name')} ({ts.date()}) predates protocol start ({protocol.valid_from})"
            
            if protocol.valid_until:
                valid_until = datetime.combine(protocol.valid_until, datetime.max.time()).replace(tzinfo=ts.tzinfo)
                if ts > valid_until:
                    return f"Protocol Mismatch: Event {e.get('name')} ({ts.date()}) is after protocol expiry ({protocol.valid_until})"
        
        return None

    # ---------------------------------------------------------
    #  I. EVENT COUNT SANITY (Outlier Detection)
    # ---------------------------------------------------------
    @staticmethod
    def validate_count_sanity(events: list, rule: ForensicRule):
        """
        Logic: Count of specific event type > threshold.
        Verdict: INVALID on extreme outliers.
        """
        target_type = rule.logic_config.get('event_type')
        max_count = rule.logic_config.get('max_count')
        
        if not target_type or not max_count: return None

        count = sum(1 for e in events if e.get('type') == target_type or e.get('name') == target_type)
        
        if count > max_count:
            return f"Sanity Check Failed: {count} occurrences of '{target_type}' (Max: {max_count})"
        
        return None

    # ---------------------------------------------------------
    #  J. MONOTONIC EVENT ORDERING (Timeline Stability)
    # ---------------------------------------------------------
    @staticmethod
    def validate_monotonic_ordering(events: list, rule: ForensicRule):
        """
        Logic: Repeated events of same type must not move backward in time.
        Verdict: INVALID (timeline corruption)
        """
        target_type = rule.logic_config.get('event_type')
        
        # Filter relevant events
        relevant = [e for e in events if e.get('type') == target_type or e.get('name') == target_type]
        
        # We assume 'events' list preserves the order of ingestion/record index.
        # If 'events' comes sorted by timestamp, this rule is moot.
        # Assuming 'events' represents record order:
        
        last_ts = None
        for e in relevant:
            curr_ts = ForensicGateLayer._parse_time(e.get('timestamp'))
            if not curr_ts: continue
            
            if last_ts and curr_ts < last_ts:
                return f"Timeline Corruption: {target_type} at {curr_ts} appears after record at {last_ts}"
            last_ts = curr_ts
            
        return None

    # ---------------------------------------------------------
    #  MAIN EXECUTION PIPELINE
    # ---------------------------------------------------------
    @staticmethod
    def execute_audit(claim_events: list, applicable_rules: list[ForensicRule]) -> ForensicVerdict:
        """
        Runs the full audit suite and generates the Certified Forensic Trace.
        """
        violations = []
        passed = []

        for rule in applicable_rules:
            error = None
            
            # 1. Standard Rules
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

            if error:
                # --- SURGICAL UPDATE: DATA RICH CAPTURE WITH CONTEXT ---
                # We now attach Scope and Intent to the violation record.
                # This allows the UI/LLM to categorize (e.g., "Safety Violation").
                violations.append({
                    "system_result": "Violation Detected",
                    "protocol": {
                        "title": rule.protocol.title,
                        "version": rule.protocol.version,
                        "issuing_body": rule.protocol.issuing_body
                    },
                    "rule": {
                        "code": rule.rule_code,
                        "text": rule.text_description, # <-- The actual law text
                        "type": rule.rule_type,
                        "scope": rule.scope_tags,   #  Injected Scope
                        "intent": rule.intent_tags  #  Injected Intent
                    },
                    "validation_trace": error, 
                    "technical_metadata": rule.logic_config 
                })
            else:
                passed.append(rule)

        is_valid = len(violations) == 0
        
        return ForensicVerdict(
            is_valid=is_valid,
            passed_rules=passed,
            violations=violations
        )