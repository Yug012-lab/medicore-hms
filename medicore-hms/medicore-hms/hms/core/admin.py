from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Slot, Booking, GoogleToken


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display  = ("username", "email", "first_name", "last_name", "is_doctor", "is_patient")
    list_filter   = ("is_doctor", "is_patient", "is_staff")
    fieldsets     = UserAdmin.fieldsets + (
        ("HMS Role", {"fields": ("is_doctor", "is_patient", "specialty", "phone", "date_of_birth", "blood_group")}),
    )


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display  = ("doctor", "date", "start_time", "end_time", "is_booked")
    list_filter   = ("is_booked", "date")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display  = ("patient", "slot", "status", "created_at")
    list_filter   = ("status",)


@admin.register(GoogleToken)
class GoogleTokenAdmin(admin.ModelAdmin):
    list_display  = ("user", "updated_at")
