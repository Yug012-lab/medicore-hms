from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("",         views.login_view,   name="home"),
    path("signup/",  views.signup_view,  name="signup"),
    path("login/",   views.login_view,   name="login"),
    path("logout/",  views.logout_view,  name="logout"),

    # Dashboard
    path("dashboard/", views.dashboard_view, name="dashboard"),

    # Doctor — slots
    path("slots/",              views.slot_list_view,   name="slot_list"),
    path("slots/create/",       views.slot_create_view, name="slot_create"),
    path("slots/<int:pk>/delete/", views.slot_delete_view, name="slot_delete"),

    # Doctor — appointments
    path("appointments/", views.doctor_appointments_view, name="doctor_appointments"),

    # Patient — booking
    path("doctors/",                        views.doctor_list_view,  name="doctor_list"),
    path("doctors/<int:doctor_id>/slots/",  views.doctor_slots_view, name="doctor_slots"),
    path("book/<int:slot_id>/",             views.book_slot_view,    name="book_slot"),
    path("my-bookings/",                    views.my_bookings_view,  name="my_bookings"),
    path("bookings/<int:pk>/cancel/",       views.cancel_booking_view, name="cancel_booking"),

    # Google OAuth2
    path("oauth/start/",    views.google_oauth_start,    name="google_oauth_start"),
    path("oauth/callback/", views.google_oauth_callback, name="google_oauth_callback"),
]
