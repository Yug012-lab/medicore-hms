"""
MediCore HMS — External Services
1. email_service   : calls the Serverless email endpoint via requests
2. calendar_service: creates Google Calendar events via OAuth2
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# ── Email Service ─────────────────────────────────────────────────────

def trigger_email(trigger_type: str, payload: dict) -> bool:
    """
    POST to the Serverless email-service endpoint.
    trigger_type: "SIGNUP_WELCOME" | "BOOKING_CONFIRMATION"
    Returns True on success, False on failure (non-blocking).
    """
    url = settings.EMAIL_SERVICE_URL
    body = {"trigger": trigger_type, **payload}
    try:
        resp = requests.post(url, json=body, timeout=5)
        resp.raise_for_status()
        logger.info("Email triggered: %s → %s", trigger_type, payload.get("to"))
        return True
    except requests.RequestException as exc:
        # Non-blocking — log and continue
        logger.warning("Email service unavailable: %s", exc)
        return False


def send_welcome_email(user) -> bool:
    return trigger_email("SIGNUP_WELCOME", {
        "to":   user.email,
        "name": user.get_full_name() or user.username,
    })


def send_booking_confirmation(booking) -> bool:
    slot   = booking.slot
    doctor = slot.doctor
    patient = booking.patient
    return trigger_email("BOOKING_CONFIRMATION", {
        "to":           patient.email,
        "patient_name": patient.get_full_name(),
        "doctor_name":  doctor.get_full_name(),
        "date":         str(slot.date),
        "start_time":   str(slot.start_time),
        "end_time":     str(slot.end_time),
    })


# ── Google Calendar Service ───────────────────────────────────────────

def _build_calendar_service(token_obj):
    """Build an authorized Google Calendar API service from stored tokens."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request

        creds = Credentials(
            token=token_obj.access_token,
            refresh_token=token_obj.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        # Auto-refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_obj.access_token = creds.token
            token_obj.save(update_fields=["access_token", "updated_at"])

        return build("calendar", "v3", credentials=creds)
    except Exception as exc:
        logger.warning("Could not build Calendar service: %s", exc)
        return None


def create_calendar_event(user, booking) -> str:
    """
    Creates a Google Calendar event for `user` (doctor or patient).
    Returns the event ID or empty string on failure.
    """
    try:
        token_obj = user.google_token
    except Exception:
        logger.info("No Google token for user %s — skipping calendar.", user.username)
        return ""

    service = _build_calendar_service(token_obj)
    if not service:
        return ""

    slot = booking.slot
    is_patient = user.is_patient
    other = slot.doctor if is_patient else booking.patient

    title = (
        f"Appointment with Dr. {other.get_full_name()}"
        if is_patient
        else f"Appointment with {other.get_full_name()}"
    )

    event_body = {
        "summary": title,
        "description": booking.notes or "MediCore HMS appointment",
        "start": {
            "dateTime": f"{slot.date}T{slot.start_time}:00",
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": f"{slot.date}T{slot.end_time}:00",
            "timeZone": "UTC",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 60},
                {"method": "popup",  "minutes": 15},
            ],
        },
    }

    try:
        event = service.events().insert(calendarId="primary", body=event_body).execute()
        logger.info("Calendar event created for %s: %s", user.username, event.get("id"))
        return event.get("id", "")
    except Exception as exc:
        logger.warning("Calendar event creation failed: %s", exc)
        return ""


def create_booking_calendar_events(booking):
    """Create calendar events for both doctor and patient."""
    patient_event_id = create_calendar_event(booking.patient, booking)
    doctor_event_id  = create_calendar_event(booking.slot.doctor, booking)

    if patient_event_id or doctor_event_id:
        booking.patient_event_id = patient_event_id
        booking.doctor_event_id  = doctor_event_id
        booking.save(update_fields=["patient_event_id", "doctor_event_id"])
