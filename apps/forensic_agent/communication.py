import logging
from django.conf import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)

class NotificationService:
    """
    The Voice of the Agent (Twilio Edition).
    Sends real-time updates via Twilio WhatsApp API.
    """

    @staticmethod
    def send_notification(audit_task):
        """
        Dispatches message based on STATE_HALTED vs STATE_CLEARED.
        """
        # 1. Determine Message Content
        if audit_task.status == 'CLEARED':
            message_body = NotificationService._build_cleared_message(audit_task)
        elif audit_task.status == 'HALTED':
            message_body = NotificationService._build_halt_message(audit_task)
        else:
            return 

        # 2. Send via Twilio
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            # Handle Sender Format
            from_number = settings.TWILIO_WHATSAPP_NUMBER 
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            # Handle Recipient Format (Sanitize & Prefix)
            raw_to = str(settings.AUDITOR_WHATSAPP_NUMBER).replace(" ", "").replace("-", "")
            if not raw_to.startswith("+"):
                # Assume Kenya if missing, or user must provide full E.164 in env
                raw_to = f"+{raw_to}" 
            
            if not raw_to.startswith("whatsapp:"):
                to_number = f"whatsapp:{raw_to}"
            else:
                to_number = raw_to

            logger.info(f" [TWILIO] Dispatching to {to_number}...")

            message = client.messages.create(
                body=message_body,
                from_=from_number,
                to=to_number
            )

            # 3. Update Audit Trace
            audit_task.notification_sent = True
            # Store Twilio SID (It fits easily in your 255-char column)
            audit_task.notification_channel = f"Twilio API ({message.sid})"
            audit_task.save(update_fields=['notification_sent', 'notification_channel'])
            
            logger.info(f"✅ Twilio Message Sent: {message.sid}")

        except TwilioRestException as e:
            logger.error(f"❌ Twilio API Failed: {e}")
        except Exception as e:
            logger.error(f"❌ Notification Error: {e}")

    @staticmethod
    def _build_halt_message(task):
        """Constructs a 'Forensic Alert' for invalid claims."""
        violations = task.verdict_json.get('violations', [])
        
        if violations:
            v = violations[0]
            rule_code = v.get('rule', {}).get('code', 'UNKNOWN')
            trace = v.get('validation_trace', 'Constraint Mismatch')
            if ":" in trace:
                trace = trace.split(":")[-1].strip()
            violation_text = f"[{rule_code}] {trace}"
            if len(violations) > 1:
                violation_text += f" (+{len(violations)-1} others)"
        else:
            violation_text = "Multiple Constraints Failed"

        return (
            f"🚨 *MEDGATE FORENSIC ALERT*\n"
            f"--------------------------------\n"
            f"❌ Status: *HALTED (INVALID)*\n"
            f"🆔 Case ID: {task.case_id}\n\n"
            f"🛑 *Critical Violation:*\n"
            f"{violation_text}\n\n"
            f"💡 Action: Audit stopped. Manual review required."
        )

    @staticmethod
    def _build_cleared_message(task):
        """Constructs a 'Digital Certificate' for valid claims."""
        passed_rules = task.verdict_json.get('passed_rules', [])
        protocol_count = len(passed_rules)
        top_protocols = list(set([r.get('protocol', 'Standard') for r in passed_rules[:3]]))
        protocol_summary = ", ".join(top_protocols)

        return (
            f"✅ *MEDGATE CERTIFIED AUDIT*\n"
            f"--------------------------------\n"
            f"🛡️ Status: *CLEARED (VALID)*\n"
            f"🆔 Case ID: {task.case_id}\n\n"
            f"📊 *Forensic Summary:*\n"
            f"• Protocols Verified: {protocol_count}\n"
            f"• Logic Gate: MedGemma Forensic Engine\n"
            f"• Scope: {protocol_summary}\n\n"
            f"🔗 Certificate Issued: {task.id}"
        )