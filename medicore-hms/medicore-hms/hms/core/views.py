"""
MediCore HMS — Views
Covers: auth, doctor slots, patient booking (atomic + select_for_update),
        Google OAuth2 flow, dashboard routing.
"""
import datetime
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse

from .decorators import doctor_required, patient_required
from .models import Booking, GoogleToken, Slot, User
from .services import (
    create_booking_calendar_events,
    send_booking_confirmation,
    send_welcome_email,
)

logger = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        first_name  = request.POST.get("first_name", "").strip()
        last_name   = request.POST.get("last_name",  "").strip()
        email       = request.POST.get("email",      "").strip().lower()
        password    = request.POST.get("password",   "")
        confirm_pw  = request.POST.get("confirm_password", "")
        role        = request.POST.get("role", "patient")
        specialty   = request.POST.get("specialty",  "").strip()
        dob         = request.POST.get("dob",        "") or None
        blood_group = request.POST.get("blood_group","").strip()

        # Validation
        if password != confirm_pw:
            messages.error(request, "Passwords do not match.")
            return render(request, "core/signup.html", {"post": request.POST})
        if User.objects.filter(username=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, "core/signup.html", {"post": request.POST})

        user = User.objects.create_user(
            username   = email,
            email      = email,
            password   = password,
            first_name = first_name,
            last_name  = last_name,
            is_doctor  = (role == "doctor"),
            is_patient = (role == "patient"),
            specialty  = specialty if role == "doctor" else "",
            date_of_birth = dob,
            blood_group   = blood_group if role == "patient" else "",
        )
        # Trigger welcome email (non-blocking)
        send_welcome_email(user)

        login(request, user)
        messages.success(request, f"Welcome to MediCore, {user.first_name}!")
        return redirect("dashboard")

    return render(request, "core/signup.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        email    = request.POST.get("email",    "").strip().lower()
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid email or password.")

    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# ── Dashboard ─────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    user  = request.user
    today = timezone.now().date()

    if user.is_doctor:
        my_slots    = Slot.objects.filter(doctor=user)
        today_slots = my_slots.filter(date=today)
        upcoming    = Booking.objects.filter(
            slot__doctor=user, status="confirmed", slot__date__gte=today
        ).select_related("patient", "slot").order_by("slot__date", "slot__start_time")[:5]
        ctx = {
            "total_slots":     my_slots.count(),
            "booked_slots":    my_slots.filter(is_booked=True).count(),
            "available_slots": my_slots.filter(is_booked=False).count(),
            "today_slots":     today_slots,
            "upcoming":        upcoming,
        }
        return render(request, "core/doctor_dashboard.html", ctx)

    # Patient dashboard
    my_bookings = Booking.objects.filter(patient=user).select_related(
        "slot", "slot__doctor"
    ).order_by("-created_at")
    upcoming = my_bookings.filter(status="confirmed", slot__date__gte=today)
    ctx = {
        "total_bookings":     my_bookings.count(),
        "upcoming_count":     upcoming.count(),
        "cancelled_count":    my_bookings.filter(status="cancelled").count(),
        "upcoming_bookings":  upcoming[:5],
        "recent_bookings":    my_bookings[:5],
    }
    return render(request, "core/patient_dashboard.html", ctx)


# ── Doctor Slot Management ────────────────────────────────────────────

@doctor_required
def slot_list_view(request):
    slots = Slot.objects.filter(doctor=request.user).select_related("booking__patient")
    return render(request, "core/slot_list.html", {"slots": slots})


@doctor_required
def slot_create_view(request):
    if request.method == "POST":
        date_str   = request.POST.get("date")
        start_str  = request.POST.get("start_time")
        end_str    = request.POST.get("end_time")

        try:
            date  = datetime.date.fromisoformat(date_str)
            start = datetime.time.fromisoformat(start_str)
            end   = datetime.time.fromisoformat(end_str)
        except (ValueError, TypeError):
            messages.error(request, "Invalid date or time format.")
            return redirect("slot_list")

        if date < timezone.now().date():
            messages.error(request, "Cannot create a slot in the past.")
            return redirect("slot_list")
        if end <= start:
            messages.error(request, "End time must be after start time.")
            return redirect("slot_list")

        Slot.objects.create(
            doctor=request.user, date=date, start_time=start, end_time=end
        )
        messages.success(request, "Slot created successfully.")
        return redirect("slot_list")

    return render(request, "core/slot_form.html")


@doctor_required
def slot_delete_view(request, pk):
    slot = get_object_or_404(Slot, pk=pk, doctor=request.user)
    if slot.is_booked:
        messages.error(request, "Cannot delete a booked slot.")
    else:
        slot.delete()
        messages.success(request, "Slot deleted.")
    return redirect("slot_list")


# ── Patient Booking ───────────────────────────────────────────────────

@patient_required
def doctor_list_view(request):
    doctors = User.objects.filter(is_doctor=True)
    today   = timezone.now().date()
    # Annotate available slot count
    for doc in doctors:
        doc.available_count = Slot.objects.filter(
            doctor=doc, is_booked=False, date__gte=today
        ).count()
    return render(request, "core/doctor_list.html", {"doctors": doctors})


@patient_required
def doctor_slots_view(request, doctor_id):
    doctor = get_object_or_404(User, pk=doctor_id, is_doctor=True)
    today  = timezone.now().date()
    slots  = Slot.objects.filter(
        doctor=doctor, is_booked=False, date__gte=today
    ).order_by("date", "start_time")
    return render(request, "core/doctor_slots.html", {"doctor": doctor, "slots": slots})


@patient_required
def book_slot_view(request, slot_id):
    """
    CRITICAL: Uses select_for_update() inside transaction.atomic()
    to prevent race conditions — only one patient can book a slot.
    """
    if request.method != "POST":
        return redirect("doctor_list")

    notes = request.POST.get("notes", "").strip()

    try:
        with transaction.atomic():
            # Lock the row — any concurrent request blocks here until we commit
            slot = Slot.objects.select_for_update().get(pk=slot_id)

            if slot.is_booked:
                messages.error(request, "Sorry, this slot was just booked by someone else.")
                return redirect("doctor_slots", doctor_id=slot.doctor_id)

            if slot.date < timezone.now().date():
                messages.error(request, "This slot is in the past.")
                return redirect("doctor_slots", doctor_id=slot.doctor_id)

            # Mark booked atomically
            slot.is_booked = True
            slot.save(update_fields=["is_booked"])

            booking = Booking.objects.create(
                patient=request.user,
                slot=slot,
                notes=notes,
                status="confirmed",
            )

    except Slot.DoesNotExist:
        messages.error(request, "Slot not found.")
        return redirect("doctor_list")
    except IntegrityError:
        # OneToOne constraint on slot — concurrent booking attempt
        messages.error(request, "This slot was just taken. Please choose another.")
        return redirect("doctor_slots", doctor_id=slot.doctor_id)

    # Outside transaction — non-critical side effects
    create_booking_calendar_events(booking)   # Google Calendar
    send_booking_confirmation(booking)         # Serverless email

    messages.success(
        request,
        f"Appointment confirmed with Dr. {slot.doctor.get_full_name()} on {slot.date} at {slot.start_time}."
    )
    return redirect("my_bookings")


@patient_required
def my_bookings_view(request):
    bookings = Booking.objects.filter(patient=request.user).select_related(
        "slot", "slot__doctor"
    ).order_by("-created_at")
    return render(request, "core/my_bookings.html", {"bookings": bookings})


@patient_required
def cancel_booking_view(request, pk):
    booking = get_object_or_404(Booking, pk=pk, patient=request.user)
    if booking.status == "confirmed":
        with transaction.atomic():
            booking.status = "cancelled"
            booking.save(update_fields=["status"])
            booking.slot.is_booked = False
            booking.slot.save(update_fields=["is_booked"])
        messages.success(request, "Appointment cancelled.")
    return redirect("my_bookings")


# ── Doctor Appointments ───────────────────────────────────────────────

@doctor_required
def doctor_appointments_view(request):
    bookings = Booking.objects.filter(
        slot__doctor=request.user
    ).select_related("patient", "slot").order_by("-created_at")
    return render(request, "core/doctor_appointments.html", {"bookings": bookings})


# ── Google OAuth2 ─────────────────────────────────────────────────────

@login_required
def google_oauth_start(request):
    """Redirect user to Google consent screen."""
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id":     settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
                    "token_uri":     "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                }
            },
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        auth_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
        request.session["oauth_state"] = state
        return redirect(auth_url)
    except Exception as exc:
        logger.error("OAuth start error: %s", exc)
        messages.error(request, "Google OAuth not configured. Add GOOGLE_CLIENT_ID to .env")
        return redirect("dashboard")


@login_required
def google_oauth_callback(request):
    """Handle Google OAuth2 callback and store tokens."""
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id":     settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
                    "token_uri":     "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                }
            },
            scopes=["https://www.googleapis.com/auth/calendar.events"],
            state=request.session.get("oauth_state"),
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        flow.fetch_token(authorization_response=request.build_absolute_uri())

        creds = flow.credentials
        GoogleToken.objects.update_or_create(
            user=request.user,
            defaults={
                "access_token":  creds.token,
                "refresh_token": creds.refresh_token or "",
            },
        )
        messages.success(request, "Google Calendar connected successfully!")
    except Exception as exc:
        logger.error("OAuth callback error: %s", exc)
        messages.error(request, "Google Calendar connection failed.")

    return redirect("dashboard")
