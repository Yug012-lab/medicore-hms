"""
MediCore HMS — Serverless Email Service
Handles: SIGNUP_WELCOME | BOOKING_CONFIRMATION
Local:   serverless offline  →  POST http://localhost:3000/dev/send-email
Deploy:  serverless deploy   →  POST https://<id>.execute-api.<region>.amazonaws.com/dev/send-email
"""
import json
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SMTP_HOST  = os.environ.get("SMTP_HOST",  "smtp.gmail.com")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER  = os.environ.get("SMTP_USER",  "")
SMTP_PASS  = os.environ.get("SMTP_PASS",  "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@medicore.hms")


# ── Email Templates ───────────────────────────────────────────────────

def _welcome_html(name: str) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:32px 24px">
      <div style="background:#03045e;border-radius:12px 12px 0 0;padding:24px;text-align:center">
        <div style="font-size:32px">🏥</div>
        <div style="font-family:sans-serif;font-size:22px;font-weight:700;color:#fff;margin-top:8px">MediCore HMS</div>
      </div>
      <div style="background:#fff;border:1px solid #dbeafe;border-top:none;border-radius:0 0 12px 12px;padding:32px">
        <h2 style="color:#03045e;margin-bottom:12px">Welcome, {name}! 👋</h2>
        <p style="color:#64748b;line-height:1.8;margin-bottom:16px">
          Your MediCore HMS account is ready. You can now log in and start using the system.
        </p>
        <div style="background:#f0f7ff;border-radius:8px;padding:16px;margin-bottom:20px">
          <div style="font-size:13px;color:#1e40af;font-weight:600;margin-bottom:6px">What you can do:</div>
          <ul style="color:#64748b;font-size:13px;line-height:2;margin:0;padding-left:18px">
            <li>Book appointments with available doctors</li>
            <li>View and manage your schedule</li>
            <li>Connect your Google Calendar</li>
          </ul>
        </div>
        <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:24px">
          MediCore HMS · Hospital Management System
        </p>
      </div>
    </div>
    """


def _booking_html(patient_name: str, doctor_name: str, date: str, start: str, end: str) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:32px 24px">
      <div style="background:#03045e;border-radius:12px 12px 0 0;padding:24px;text-align:center">
        <div style="font-size:32px">📅</div>
        <div style="font-family:sans-serif;font-size:22px;font-weight:700;color:#fff;margin-top:8px">Appointment Confirmed</div>
      </div>
      <div style="background:#fff;border:1px solid #dbeafe;border-top:none;border-radius:0 0 12px 12px;padding:32px">
        <h2 style="color:#03045e;margin-bottom:4px">Hi {patient_name},</h2>
        <p style="color:#64748b;margin-bottom:20px">Your appointment has been successfully booked.</p>
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:20px;margin-bottom:20px">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
            <span style="font-size:20px">👨‍⚕️</span>
            <div>
              <div style="font-size:14px;font-weight:700;color:#03045e">Dr. {doctor_name}</div>
              <div style="font-size:12px;color:#065f46">Confirmed</div>
            </div>
          </div>
          <div style="font-size:13px;color:#374151"><strong>📅 Date:</strong> {date}</div>
          <div style="font-size:13px;color:#374151;margin-top:4px"><strong>🕐 Time:</strong> {start} – {end}</div>
        </div>
        <div style="background:#eff6ff;border-radius:8px;padding:14px;font-size:12px;color:#1e40af">
          📅 A Google Calendar event has been created for this appointment. Check your calendar for the reminder.
        </div>
        <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:24px">
          MediCore HMS · Hospital Management System
        </p>
      </div>
    </div>
    """


# ── SMTP sender ───────────────────────────────────────────────────────

def _send_smtp(to: str, subject: str, html_body: str) -> dict:
    """Send email via SMTP. Returns status dict."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP credentials not configured — email logged only.")
        logger.info("EMAIL TO: %s | SUBJECT: %s", to, subject)
        return {"status": "logged", "message": "SMTP not configured, email logged locally."}

    msg = MIMEMultipart("alternative")
    msg["From"]    = FROM_EMAIL
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to, msg.as_string())
        logger.info("Email sent to %s", to)
        return {"status": "sent"}
    except smtplib.SMTPException as exc:
        logger.error("SMTP error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ── Lambda Handler ────────────────────────────────────────────────────

def send_email(event, context):
    """
    POST /dev/send-email
    Body: { "trigger": "SIGNUP_WELCOME"|"BOOKING_CONFIRMATION", ...payload }
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "headers": headers,
                "body": json.dumps({"error": "Invalid JSON"})}

    trigger = body.get("trigger", "")
    logger.info("Email trigger received: %s", trigger)

    if trigger == "SIGNUP_WELCOME":
        to   = body.get("to", "")
        name = body.get("name", "User")
        result = _send_smtp(
            to      = to,
            subject = "Welcome to MediCore HMS 🏥",
            html_body = _welcome_html(name),
        )

    elif trigger == "BOOKING_CONFIRMATION":
        to           = body.get("to", "")
        patient_name = body.get("patient_name", "Patient")
        doctor_name  = body.get("doctor_name", "Doctor")
        date         = body.get("date", "")
        start        = body.get("start_time", "")
        end          = body.get("end_time", "")
        result = _send_smtp(
            to      = to,
            subject = f"Appointment Confirmed – Dr. {doctor_name} 📅",
            html_body = _booking_html(patient_name, doctor_name, date, start, end),
        )

    else:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": f"Unknown trigger: {trigger}"}),
        }

    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps({"trigger": trigger, **result}),
    }
