#!/bin/bash
# Vercel build script — runs before deployment
pip install -r requirements.txt
cd hms
python manage.py collectstatic --noinput
python manage.py migrate --noinput
