import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class NotificationService:
    """
    The Voice of the Agent.
    Sends real-time updates to humans based on Forensic State.
    """

    @staticmethod
    def send_notification(audit_task):
        """
        Dispatches message based on STATE_HALTED vs STATE_CLEARED.
        """
        if audit_task.status == 'CLEARED':
            NotificationService._send_cleared_notice(audit_task)
        elif audit_task.status == 'HALTED':
            NotificationService._send_halt_notice(audit_task)
            
        audit_task.notification_sent = True
        audit_task.save()

    @staticmethod
    def _send_halt_notice(task):
        """
        Template for HALTED state.
        "Refusal is a safety mechanism."
        """
        # Extract the specific violation for transparency
        violations = task.verdict_json.get('violations', [])
        
        # FIX: The Gate Layer returns 'validation_trace', not 'violation'
        if violations:
            primary_violation = violations[0].get('validation_trace', 'Unknown Violation')
            rule_code = violations[0].get('logic_source', 'Unknown')
        else:
            primary_violation = "Multiple Constraints Failed"
            rule_code = "N/A"

        message = (
            f"🚨 *MedGate Forensic Alert*\n"
            f"Case ID: {task.case_id}\n"
            f"Status: HALTED 🛑\n"
            f"Violation: {rule_code} — {primary_violation}\n"
            f"Action: Audit stopped. Manual review required."
        )
        
        # Integration Point: Twilio / WhatsApp API
        logger.info(f"[WHATSAPP_MOCK_SEND] To: Auditor | Body: \n{message}")
        task.notification_channel = "WhatsApp"

    @staticmethod
    def _send_cleared_notice(task):
        """
        Template for CLEARED state.
        "The PASS is the product." 
        """
        # Workflow serializes passed rules into "passed" key
        passed_rules = task.verdict_json.get('passed', [])
        
        message = (
            f"✅ *MedGate Certified Audit*\n"
            f"Case ID: {task.case_id}\n"
            f"Status: CLEARED\n"
            f"Protocols Passed: {len(passed_rules)}\n"
            f"Certification: Validated by MedGemma Forensic Engine."
        )
        
        logger.info(f"[WHATSAPP_MOCK_SEND] To: Auditor | Body: \n{message}")
        task.notification_channel = "WhatsApp"