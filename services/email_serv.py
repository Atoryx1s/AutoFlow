import datetime
import logging
import resend
from config import ADMIN_EMAIL, RESEND_API_KEY, TIMEZONE

logger = logging.getLogger(__name__)
resend.api_key = RESEND_API_KEY

def send_feedback_email(message):
    try:
        if not ADMIN_EMAIL:
            logger.error("ADMIN_EMAIL configuration not set")
            return False

        local_time = datetime.datetime.now(TIMEZONE)
        html_body = f"""
        <h3>📨 Nová spätná väzba:</h3>
        <p><b>📅 Čas odoslania:</b> {local_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <hr>
        <p><b>💬 Správa:</b></p>
        <p style="white-space: pre-wrap; background: #f4f4f4; padding: 10px; border-radius: 5px;">{message}</p>
        <br>
        <p><i>Táto správa bola odoslaná bezpečne a plne anonymne (bez ukladania metaúdajov).</i></p>
        """
        resend.Emails.send({
            "from": "Building Bot <onboarding@resend.dev>",
            "to": [ADMIN_EMAIL],
            "subject": "📝 Spätná väzba od používateľa Telegram bota",
            "html": html_body,
        })
        logger.info("Feedback email successfully sent via Resend API.")
        return True
    except Exception as e:
        logger.exception(f"Error sending feedback email via HTTP API: {e}")
        return False
