# 🏥 MediCore HMS — Hospital Management System

A full-stack Django hospital management system with race-condition-proof booking, Google Calendar OAuth2 integration, and a Serverless email notification service.

---

## 📁 Project Structure

```
medicore-hms/
├── README.md
├── requirements.txt          # Python dependencies
├── vercel.json               # Vercel deployment config
├── build_files.sh            # Vercel build script
├── .env.example              # Environment variable template
├── .gitignore
├── hms/                      # Django project
│   ├── manage.py
│   ├── hms/                  # Project config
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   └── core/                 # Main app
│       ├── models.py         # User, Slot, Booking, GoogleToken
│       ├── views.py          # All views with RBAC
│       ├── urls.py
│       ├── decorators.py     # doctor_required / patient_required
│       ├── services.py       # Email + Google Calendar
│       ├── admin.py
│       └── templates/core/
│           ├── base.html
│           ├── login.html
│           ├── signup.html
│           ├── doctor_dashboard.html
│           ├── patient_dashboard.html
│           ├── slot_list.html
│           ├── slot_form.html
│           ├── doctor_list.html
│           ├── doctor_slots.html
│           ├── my_bookings.html
│           └── doctor_appointments.html
└── email-service/            # Serverless email service
    ├── handler.py
    ├── serverless.yml
    └── package.json
```

---

## ⚙️ Local Setup (Step by Step)

### Prerequisites
- Python 3.11+
- PostgreSQL (or skip — SQLite works out of the box)
- Node.js 18+ (for email service)
- npm

---

### Step 1 — Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/medicore-hms.git
cd medicore-hms
```

### Step 2 — Python virtual environment

```bash
python -m venv venv
# Mac/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

### Step 3 — Environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=your-random-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL (leave blank to use SQLite)
DATABASE_URL=postgres://postgres:password@localhost:5432/medicore_hms

# Google Calendar (optional — app works without it)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/callback/

# Email service
EMAIL_SERVICE_URL=http://localhost:3000/dev/send-email
```

> **SQLite shortcut**: Leave `DATABASE_URL` blank — the app auto-uses SQLite. No Postgres setup needed locally.

### Step 4 — Database setup

```bash
cd hms
python manage.py migrate
python manage.py createsuperuser   # optional admin access
```

### Step 5 — Run Django

```bash
python manage.py runserver
```

✅ App live at: **http://localhost:8000**

---

### Step 6 — Run Email Service (separate terminal)

```bash
cd email-service
npm install
npx serverless offline
```

✅ Email endpoint at: **http://localhost:3000/dev/send-email**

---

## 🚀 Deploy to Vercel (Free Live Link)

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/medicore-hms.git
git push -u origin main
```

### Step 2 — Create free database (Supabase)

1. Go to [supabase.com](https://supabase.com) → New project
2. Go to **Settings → Database** → copy the **Connection string (URI)**
3. It looks like: `postgres://postgres:[password]@db.xxx.supabase.co:5432/postgres`

### Step 3 — Deploy on Vercel

1. Go to [vercel.com](https://vercel.com) → **Sign up with GitHub**
2. Click **Add New Project** → Import `medicore-hms`
3. Set **Root Directory** to: `.` (root)
4. Add these **Environment Variables**:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | any long random string |
| `DEBUG` | `False` |
| `DATABASE_URL` | your Supabase connection string |
| `ALLOWED_HOSTS` | `medicore-hms.vercel.app` |

5. Set **Build Command** to: `chmod +x build_files.sh && ./build_files.sh`
6. Set **Output Directory** to: `hms/staticfiles`
7. Click **Deploy**

✅ Live at: **https://medicore-hms.vercel.app**

---

## 🔐 Design Decisions

### Race Condition Handling
The most critical design decision was how to handle concurrent booking attempts.

**Problem**: Two patients could simultaneously request the same slot. Without locking, both could pass the `is_booked=False` check and create a double-booking.

**Solution**: `select_for_update()` inside `transaction.atomic()`:

```python
with transaction.atomic():
    slot = Slot.objects.select_for_update().get(pk=slot_id)
    if slot.is_booked:
        raise AlreadyBookedError()
    slot.is_booked = True
    slot.save()
    Booking.objects.create(patient=request.user, slot=slot)
```

**Why**: `select_for_update()` issues a `SELECT ... FOR UPDATE` SQL statement, placing a row-level lock on the slot. Any concurrent transaction trying to lock the same row blocks until the first transaction commits. This guarantees only one booking succeeds — the database enforces it, not application logic.

**Alternative considered**: Optimistic locking with a `version` field. Rejected because it requires retry logic on the client side, adding complexity without benefit for a low-concurrency HMS.

---

## 📋 API / URL Reference

| Method | URL | Role | Description |
|--------|-----|------|-------------|
| GET/POST | `/signup/` | Any | Create account |
| GET/POST | `/login/` | Any | Sign in |
| GET | `/logout/` | Auth | Sign out |
| GET | `/dashboard/` | Auth | Role-based dashboard |
| GET | `/slots/` | Doctor | List my slots |
| GET/POST | `/slots/create/` | Doctor | Create slot |
| POST | `/slots/<id>/delete/` | Doctor | Delete slot |
| GET | `/appointments/` | Doctor | My appointments |
| GET | `/doctors/` | Patient | Browse doctors |
| GET | `/doctors/<id>/slots/` | Patient | Doctor's slots |
| POST | `/book/<slot_id>/` | Patient | Book slot (atomic) |
| GET | `/my-bookings/` | Patient | My bookings |
| POST | `/bookings/<id>/cancel/` | Patient | Cancel booking |
| GET | `/oauth/start/` | Auth | Google OAuth2 start |
| GET | `/oauth/callback/` | Auth | Google OAuth2 callback |

---

## ⚠️ Limitations

1. **Email service** requires Node.js and `serverless-offline` running separately locally. On Vercel, deploy `email-service/` separately as a Vercel Serverless Function or AWS Lambda.
2. **Google Calendar** requires a Google Cloud project with the Calendar API enabled and OAuth2 credentials configured.
3. **Vercel** has a read-only filesystem — file uploads aren't supported (not needed for this app).
4. SQLite is used as fallback when `DATABASE_URL` is not set — fine for local dev, not recommended for production.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.0 |
| Database | PostgreSQL (SQLite fallback) |
| ORM | Django ORM |
| Auth | Session-based, custom User model |
| Static Files | WhiteNoise |
| Email Service | Serverless Framework (Python) |
| Calendar | Google Calendar API v3 (OAuth2) |
| Deployment | Vercel + Supabase |
