"""
MediCore HMS — Core Models
- User  : custom AbstractUser with is_doctor / is_patient flags
- Slot  : doctor availability slot
- Booking: patient → slot booking
- GoogleToken: OAuth2 tokens per user
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model supporting Doctor and Patient roles."""
    is_doctor  = models.BooleanField(default=False)
    is_patient = models.BooleanField(default=False)

    # Doctor-only fields
    specialty  = models.CharField(max_length=100, blank=True)
    phone      = models.CharField(max_length=20,  blank=True)

    # Patient-only fields
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group   = models.CharField(max_length=5, blank=True)

    def __str__(self):
        role = "Doctor" if self.is_doctor else "Patient" if self.is_patient else "User"
        return f"{self.get_full_name() or self.username} ({role})"


class Slot(models.Model):
    """A doctor's available time slot."""
    doctor     = models.ForeignKey(User, on_delete=models.CASCADE, related_name="slots",
                                   limit_choices_to={"is_doctor": True})
    date       = models.DateField()
    start_time = models.TimeField()
    end_time   = models.TimeField()
    is_booked  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]

    def __str__(self):
        status = "BOOKED" if self.is_booked else "available"
        return f"Dr.{self.doctor.last_name} — {self.date} {self.start_time}–{self.end_time} [{status}]"


class Booking(models.Model):
    """A patient's confirmed booking of a doctor slot."""
    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
    ]
    patient    = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings",
                                   limit_choices_to={"is_patient": True})
    slot       = models.OneToOneField(Slot, on_delete=models.CASCADE, related_name="booking")
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="confirmed")
    notes      = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Google Calendar event IDs (set after creation)
    doctor_event_id  = models.CharField(max_length=200, blank=True)
    patient_event_id = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Booking #{self.pk} — {self.patient} @ {self.slot}"


class GoogleToken(models.Model):
    """Stores OAuth2 access + refresh tokens per user."""
    user          = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_token")
    access_token  = models.TextField()
    refresh_token = models.TextField(blank=True)
    token_expiry  = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"GoogleToken for {self.user}"
