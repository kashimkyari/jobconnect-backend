from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import logging
from ..config import settings

logger = logging.getLogger(__name__)

client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

async def send_sms(to_number: str, message: str) -> bool:
    """
    Send SMS using Twilio
    """
    try:
        message = client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_number
        )
        logger.info(f"SMS sent successfully to {to_number}, SID: {message.sid}")
        return True
    except TwilioRestException as e:
        logger.error(f"Twilio error: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return False

# SMS Templates
def verification_code_sms(code: str) -> str:
    return f"Your JobConnect verification code is: {code}"

def job_offer_sms(employer_name: str, job_title: str) -> str:
    return f"You have received a job offer from {employer_name} for: {job_title}. Log in to JobConnect to respond."

def payment_received_sms(amount: float) -> str:
    return f"Payment of ${amount:.2f} has been received and is now in escrow. Log in to JobConnect for details."
