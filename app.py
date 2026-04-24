"""
================================================================================
 MEDICATION REMINDER WEB APP — UBUNTU SERVER INSTALLATION GUIDE
================================================================================

 WHAT IT DOES
 ----------------------------------------------------------------------------
 Sends medication reminders via Email and Telegram at scheduled times.
 Supports confirmation and snooze through Telegram buttons or email replies.
 Track doses in a web dashboard and view full history.

 SCHEDULE TYPES
 ----------------------------------------------------------------------------
   daily    : Every day at HH:MM
   weekdays : Monday through Friday
   weekly   : Specific days (e.g., Mon, Wed, Fri)
   monthly  : Specific days of month (e.g., 1, 15)
   yearly   : Once per year on MM-DD

 NOTIFICATION FLOW
 ----------------------------------------------------------------------------
 1. Cron job fires at the scheduled time.
 2. Email sent to ALERT_EMAIL with med details.
 3. Telegram sent with [✅ Confirm Taken] [😴 Snooze 10m] buttons.
 4. If still pending after 15 minutes, a second nag fires.
 5. Reply "TAKEN" or "SNOOZE 15" via email or Telegram to interact.

 FILES YOU NEED
 ----------------------------------------------------------------------------
 app.py            : Main Flask application (this file)
 requirements.txt  : Python dependencies
 .env              : Secrets and config — NEVER COMMIT THIS
 meds.db           : Auto-created SQLite database

================================================================================
 UBUNTU SERVER INSTALLATION
================================================================================

 1. SYSTEM DEPENDENCIES
 ----------------------------------------------------------------------------
    sudo apt update
    sudo apt install python3 python3-pip python3-venv sqlite3 -y

 2. CREATE APP DIRECTORY
 ----------------------------------------------------------------------------
    sudo mkdir -p /opt/medreminder
    sudo chown -R $USER:$USER /opt/medreminder
    cd /opt/medreminder

 3. PYTHON VIRTUAL ENVIRONMENT
 ----------------------------------------------------------------------------
    python3 -m venv venv
    source venv/bin/activate

 4. INSTALL PYTHON PACKAGES
 ----------------------------------------------------------------------------
    pip install flask flask-sqlalchemy apscheduler python-dotenv werkzeug

    # Or create requirements.txt with:
    # flask>=2.0
    # flask-sqlalchemy>=3.0
    # apscheduler>=3.10
    # python-dotenv>=1.0
    # werkzeug>=2.0

 5. CONFIGURE ENVIRONMENT VARIABLES (.env)
 ----------------------------------------------------------------------------
    nano /opt/medreminder/.env

    # ---- paste this and edit values ----
    EMAIL_ADDRESS=your.email@gmail.com
    EMAIL_PASSWORD=your_gmail_app_password
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    ALERT_EMAIL=your.email@gmail.com

    TELEGRAM_BOT_TOKEN=1234567890:YOUR_TOKEN_HERE
    TELEGRAM_CHAT_ID=12345678

    IMAP_SERVER=imap.gmail.com

    SECRET_KEY=replace_with_random_letters_and_numbers
    DEFAULT_PASSWORD=your_dashboard_password
    # -------------------------------------

 6. GMAIL SETUP (Email + IMAP)
 ----------------------------------------------------------------------------
    - Enable 2-Factor Authentication on your Google Account
    - Go to Google Account → Security → App Passwords
    - Generate an App Password for "Mail" on "Other device"
    - Paste that 16-character password into EMAIL_PASSWORD above
    - Go to Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP

 7. TELEGRAM BOT SETUP
 ----------------------------------------------------------------------------
    - Open Telegram, search for @BotFather, start chat
    - Send /newbot, name it, get your HTTP API Token
    - Start your bot and send /start
    - Get your Chat ID by visiting:
      https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
    - Look for "chat":{"id":12345678

 8. CREATE SYSTEMD SERVICE (runs 24/7)
 ----------------------------------------------------------------------------
    sudo nano /etc/systemd/system/medreminder.service

    # ---- paste exactly ----
    [Unit]
    Description=Medication Reminder Web App
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=ubuntu
    Group=ubuntu
    WorkingDirectory=/opt/medreminder
    ExecStart=/opt/medreminder/venv/bin/python /opt/medreminder/app.py
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    # ------------------------

    # If running as root instead of 'ubuntu', change User/Group to 'root'

    sudo systemctl daemon-reload
    sudo systemctl enable medreminder
    sudo systemctl start medreminder

 9. CHECK STATUS & LOGS
 ----------------------------------------------------------------------------
    sudo systemctl status medreminder
    sudo journalctl -u medreminder -f

 10. FIREWALL (optional)
 ----------------------------------------------------------------------------
    # If accessing directly on port 5000:
    sudo ufw allow 5000/tcp

    # Or use Nginx reverse proxy (recommended):
    sudo apt install nginx
    sudo nano /etc/nginx/sites-available/medreminder

    server {
        listen 80;
        server_name _;
        location / {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }

    sudo ln -s /etc/nginx/sites-available/medreminder /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t
    sudo systemctl restart nginx
    sudo ufw allow 'Nginx Full'
    sudo ufw delete allow 5000/tcp

================================================================================
 IMPORTANT NOTES
================================================================================

 - ALWAYS restart the service after editing app.py or .env:
     sudo systemctl restart medreminder

 - If a medication time is already passed today, APScheduler waits until tomorrow.
   Set a test med 2 minutes in the future to verify it's working.

 - Manual trigger (for immediate testing without waiting):
     cd /opt/medreminder && source venv/bin/activate
     python -c "from app import app, send_notifications; app.app_context().__enter__(); send_notifications(1)"

 - The SQLite database (meds.db) and telegram_offset.json live in WorkingDirectory.
   Back them up if you migrate servers.

================================================================================
"""

import imaplib
import email
from email.header import decode_header
import os
import re
import smtplib
import json
import urllib.request
from datetime import datetime, date, timedelta
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, request, redirect, url_for, session, flash, render_template_string
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# =============================================================================
# CONFIG
# =============================================================================
load_dotenv()

class Config:
    EMAIL        = os.getenv("EMAIL_ADDRESS")
    EMAIL_PW     = os.getenv("EMAIL_PASSWORD")
    SMTP_SERVER  = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
    ALERT_EMAIL  = os.getenv("ALERT_EMAIL", os.getenv("EMAIL_ADDRESS"))
    SMS_GATEWAY  = os.getenv("SMS_GATEWAY")
    SECRET_KEY   = os.getenv("SECRET_KEY", "dev-key")
    DEFAULT_PW   = os.getenv("DEFAULT_PASSWORD", "password")
    IMAP_SERVER  = os.getenv("IMAP_SERVER")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =============================================================================
# APP SETUP
# =============================================================================
app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///meds.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
scheduler = BackgroundScheduler()

# =============================================================================
# HTML TEMPLATES
# =============================================================================
LOGIN_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Med Reminder — Login</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f2f5;margin:0;display:flex;justify-content:center;align-items:center;height:100vh}
.card{background:#fff;padding:2rem;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.1);width:100%;max-width:360px}
h1{margin:0 0 1rem;font-size:1.5rem}
input{width:100%;padding:.75rem;margin-bottom:1rem;border:1px solid #ddd;border-radius:8px;font-size:1rem}
button{width:100%;padding:.75rem;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:1rem;cursor:pointer}
.error{color:#dc2626;margin-bottom:1rem}
</style>
</head>
<body>
<div class="card">
<h1>💊 Med Reminder</h1>
{% with messages = get_flashed_messages() %}
{% if messages %}{% for msg in messages %}<div class="error">{{ msg }}</div>{% endfor %}{% endif %}
{% endwith %}
<form method="post">
<input type="text" name="username" value="admin" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Log In</button>
</form>
</div>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Med Reminder</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f3f4f6;margin:0;color:#111}
.header{background:#2563eb;color:#fff;padding:1rem;display:flex;justify-content:space-between;align-items:center}
.header h1{margin:0;font-size:1.25rem} .header a{color:#fff;text-decoration:none;font-size:.9rem}
.container{max-width:800px;margin:0 auto;padding:1rem}
.time{text-align:center;color:#6b7280;margin-bottom:1rem;font-size:.9rem}
.grid{display:grid;grid-template-columns:1fr;gap:1rem}
@media(min-width:600px){.grid{grid-template-columns:1fr 1fr}}
.card{background:#fff;border-radius:12px;padding:1.25rem;box-shadow:0 1px 3px rgba(0,0,0,.1);border-left:6px solid #cbd5e1}
.card.green{border-left-color:#22c55e;background:#f0fdf4}
.card.yellow{border-left-color:#eab308;background:#fefce8}
.card.red{border-left-color:#ef4444;background:#fef2f2}
.card.blue{border-left-color:#3b82f6;background:#eff6ff}
.card.orange{border-left-color:#f97316;background:#fff7ed}
.badge{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-size:.75rem;font-weight:600;text-transform:uppercase}
.badge-confirmed{background:#22c55e;color:#fff} .badge-due{background:#eab308;color:#000}
.badge-missed{background:#ef4444;color:#fff} .badge-upcoming{background:#3b82f6;color:#fff}
.badge-snoozed{background:#f97316;color:#fff}
h2{margin:0 0 .25rem;font-size:1.1rem}
.meta{color:#6b7280;font-size:.875rem;margin-bottom:.5rem}
.actions{display:flex;gap:.5rem;margin-top:.75rem}
button{border:none;padding:.5rem 1rem;border-radius:8px;font-size:.875rem;cursor:pointer}
.btn-confirm{background:#22c55e;color:#fff} .btn-snooze{background:#f59e0b;color:#fff}
form{display:inline} .flash{padding:.75rem;border-radius:8px;background:#fee2e2;color:#991b1b;margin-bottom:1rem}
.empty{text-align:center;color:#6b7280;padding:2rem}
.nav{margin-bottom:1rem} .nav a{color:#2563eb;text-decoration:none;font-weight:600;margin-right:1rem}
</style>
</head>
<body>
<div class="header"><h1>💊 Med Reminder</h1><a href="/logout">Log Out</a></div>
<div class="container">
<div class="time">{{ now.strftime('%A, %B %d — %I:%M %p') }}</div>
<div class="nav">
<a href="/medications">⚙️ Manage Medications</a>
<a href="/history">📋 History</a>
</div>

{% with messages = get_flashed_messages() %}
{% if messages %}{% for msg in messages %}<div class="flash">{{ msg }}</div>{% endfor %}{% endif %}
{% endwith %}

{% if not doses %}
<div class="empty">No medications scheduled for today.</div>
{% else %}
<div class="grid">
{% for d in doses %}
<div class="card {{ d.css }}">
<div style="display:flex;justify-content:space-between;align-items:start">
<h2>{{ d.obj.medication.name }}</h2>
<span class="badge badge-{{ d.css }}">{{ d.label }}</span>
</div>
<div class="meta">{{ d.obj.medication.dosage }} • {{ d.schedule_label }} • {{ d.time }}</div>
{% if d.obj.medication.instructions %}
<div class="meta">{{ d.obj.medication.instructions }}</div>
{% endif %}
{% if d.state == 'snoozed' %}
<div class="meta">⏰ Until {{ d.obj.snooze_until.strftime('%I:%M %p') }}</div>
{% endif %}
{% if d.state == 'confirmed' %}
<div class="meta">✅ Taken at {{ d.obj.confirmed_at.strftime('%I:%M %p') }}</div>
{% endif %}
{% if d.state in ('upcoming','due','missed','snoozed') %}
<div class="actions">
<form method="post" action="/confirm/{{ d.obj.id }}"><button class="btn-confirm" type="submit">✅ Confirm Taken</button></form>
<form method="post" action="/snooze/{{ d.obj.id }}"><input type="hidden" name="minutes" value="10"><button class="btn-snooze" type="submit">😴 Snooze 10m</button></form>
</div>
{% endif %}
</div>
{% endfor %}
</div>
{% endif %}
</div>

<script>
const audioCtx = new (window.AudioContext||window.webkitAudioContext)();
function beep(){
  const osc=audioCtx.createOscillator(), g=audioCtx.createGain();
  osc.connect(g); g.connect(audioCtx.destination); osc.type='sine'; osc.frequency.value=880;
  osc.start(); g.gain.exponentialRampToValueAtTime(0.00001,audioCtx.currentTime+0.5);
  osc.stop(audioCtx.currentTime+0.5);
}
{% if any_due %}
if('Notification' in window && Notification.permission==='granted'){
  new Notification('Medication Reminder',{body:'You have medications to take now.'});
}
beep();
{% endif %}
if('Notification' in window && Notification.permission==='default'){Notification.requestPermission();}
setTimeout(()=>location.reload(),60000);
</script>
</body>
</html>"""

MEDS_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manage Medications</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f3f4f6;margin:0}
.header{background:#2563eb;color:#fff;padding:1rem;display:flex;justify-content:space-between;align-items:center}
.header h1{margin:0;font-size:1.25rem} .header a{color:#fff;text-decoration:none;font-size:.9rem}
.container{max-width:900px;margin:0 auto;padding:1rem}
table{width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);border-collapse:collapse}
th,td{padding:.6rem 1rem;text-align:left;font-size:.875rem} th{background:#e5e7eb;font-weight:600}
tr{border-bottom:1px solid #e5e7eb} form{display:inline}
.btn-del{background:#ef4444;color:#fff;border:none;padding:.35rem .75rem;border-radius:6px;cursor:pointer;font-size:.8rem}
.card{background:#fff;padding:1.25rem;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.1);margin-top:1.5rem}
input,textarea,select{width:100%;padding:.6rem;border:1px solid #d1d5db;border-radius:8px;margin-bottom:.75rem;font-family:inherit;font-size:1rem}
button[type=submit]{background:#2563eb;color:#fff;border:none;padding:.6rem 1.25rem;border-radius:8px;cursor:pointer}
.back{color:#2563eb;text-decoration:none;display:inline-block;margin-bottom:1rem}
#weekly_fields label{margin-right:.6rem;font-size:.9rem}
</style>
</head>
<body>
<div class="header"><h1>Manage Medications</h1><a href="/logout">Log Out</a></div>
<div class="container">
<a href="/" class="back">← Back to Dashboard</a>

<table>
<thead><tr><th>Name</th><th>Dosage</th><th>Time</th><th>Schedule</th><th>Instructions</th><th></th></tr></thead>
<tbody>
{% for m in medications %}
<tr>
<td>{{ m.name }}</td>
<td>{{ m.dosage or '-' }}</td>
<td>{{ m.time }}</td>
<td>
{% if m.schedule_type == 'daily' %}Daily
{% elif m.schedule_type == 'weekdays' %}Mon-Fri
{% elif m.schedule_type == 'weekly' %}
    {% set dmap = {'0':'Mon','1':'Tue','2':'Wed','3':'Thu','4':'Fri','5':'Sat','6':'Sun'} %}
    {% for n in m.schedule_days.split(',') %}{{ dmap[n.strip()] }}{% if not loop.last %}, {% endif %}{% endfor %}
{% elif m.schedule_type == 'monthly' %}{{ m.schedule_days }} of month
{% elif m.schedule_type == 'yearly' %}
    {% set mmdd = m.schedule_days.split('-') %}
    {% set mnames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'] %}
    {{ mnames[mmdd[0]|int - 1] }} {{ mmdd[1]|int }}
{% else %}-{% endif %}
</td>
<td>{{ m.instructions or '-' }}</td>
<td><form method="post" action="/medications/delete/{{ m.id }}" onsubmit="return confirm('Delete {{ m.name }}?')">
<button class="btn-del" type="submit">Delete</button></form></td>
</tr>
{% endfor %}
</tbody>
</table>

<div class="card">
<h3>Add New Medication</h3>
<form method="post" action="/medications/add">
<input name="name" placeholder="Name (e.g. Vitamin D)" required>
<input name="dosage" placeholder="Dosage (e.g. 2000 IU)">
<input name="time" type="time" required>

<label for="schedule_type">Schedule</label>
<select name="schedule_type" id="schedule_type" onchange="toggleSchedule()">
    <option value="daily">Every Day</option>
    <option value="weekdays">Mon-Fri (Weekdays)</option>
    <option value="weekly">Specific Days of Week</option>
    <option value="monthly">Specific Days of Month</option>
    <option value="yearly">Once a Year (MM-DD)</option>
</select>

<div id="weekly_fields" style="display:none;margin:.5rem 0">
    <label><input type="checkbox" name="weekdays" value="0"> Mon</label>
    <label><input type="checkbox" name="weekdays" value="1"> Tue</label>
    <label><input type="checkbox" name="weekdays" value="2"> Wed</label>
    <label><input type="checkbox" name="weekdays" value="3"> Thu</label>
    <label><input type="checkbox" name="weekdays" value="4"> Fri</label>
    <label><input type="checkbox" name="weekdays" value="5"> Sat</label>
    <label><input type="checkbox" name="weekdays" value="6"> Sun</label>
</div>

<div id="monthly_fields" style="display:none;margin:.5rem 0">
    <input name="month_days" placeholder="e.g. 1, 15">
</div>

<div id="yearly_fields" style="display:none;margin:.5rem 0">
    <input name="yearly_date" placeholder="MM-DD, e.g. 01-15">
</div>

<textarea name="instructions" rows="2" placeholder="Instructions (e.g. With food)"></textarea>
<button type="submit">Add Medication</button>
</form>
</div>

<script>
function toggleSchedule() {
    var type = document.getElementById('schedule_type').value;
    document.getElementById('weekly_fields').style.display = (type == 'weekly') ? 'block' : 'none';
    document.getElementById('monthly_fields').style.display = (type == 'monthly') ? 'block' : 'none';
    document.getElementById('yearly_fields').style.display = (type == 'yearly') ? 'block' : 'none';
}
toggleSchedule();
</script>
</div>
</body>
</html>"""

HISTORY_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dose History</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f3f4f6;margin:0}
.header{background:#2563eb;color:#fff;padding:1rem;display:flex;justify-content:space-between;align-items:center}
.header h1{margin:0;font-size:1.25rem} .header a{color:#fff;text-decoration:none;font-size:.9rem}
.container{max-width:900px;margin:0 auto;padding:1rem}
table{width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);border-collapse:collapse}
th,td{padding:.6rem 1rem;text-align:left;font-size:.875rem} th{background:#e5e7eb;font-weight:600}
tr{border-bottom:1px solid #e5e7eb}
.status-pending{color:#2563eb;font-weight:600}
.status-confirmed{color:#16a34a}
.status-snoozed{color:#d97706}
.status-missed{color:#dc2626}
.back{color:#2563eb;text-decoration:none;display:inline-block;margin-bottom:1rem}
.empty{text-align:center;color:#6b7280;padding:2rem}
.summary{background:#fff;padding:1rem;border-radius:12px;margin-bottom:1rem;display:flex;gap:1.5rem;flex-wrap:wrap}
.stat{text-align:center}
.stat .num{font-size:1.5rem;font-weight:700;color:#2563eb}
.stat .lbl{font-size:.8rem;color:#6b7280}
</style>
</head>
<body>
<div class="header"><h1>Dose History</h1><a href="/logout">Log Out</a></div>
<div class="container">
<a href="/" class="back">← Dashboard</a>

{% if not doses %}
<div class="empty">No history found yet.</div>
{% else %}
<div class="summary">
<div class="stat"><div class="num">{{ confirmed_count }}</div><div class="lbl">Confirmed</div></div>
<div class="stat"><div class="num">{{ missed_count }}</div><div class="lbl">Missed / Overdue</div></div>
<div class="stat"><div class="num">{{ snoozed_count }}</div><div class="lbl">Snoozed</div></div>
<div class="stat"><div class="num">{{ doses|length }}</div><div class="lbl">Total Tracked</div></div>
</div>

<table>
<thead>
<tr><th>Date</th><th>Medication</th><th>Dosage</th><th>Scheduled</th><th>Status</th><th>Confirmed At</th></tr>
</thead>
<tbody>
{% for d in doses %}
<tr>
<td>{{ d.date.strftime('%Y-%m-%d') }}</td>
<td>{{ d.medication.name }}</td>
<td>{{ d.medication.dosage or '-' }}</td>
<td>{{ d.time }}</td>
<td class="status-{{ d.status }}">{{ d.status.title() }}</td>
<td>{{ d.confirmed_at.strftime('%I:%M %p') if d.confirmed_at else '-' }}</td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
</div>
</body>
</html>"""

# =============================================================================
# MODELS
# =============================================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(100))
    time = db.Column(db.String(5), nullable=False)
    instructions = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    schedule_type = db.Column(db.String(20), default='daily')
    schedule_days = db.Column(db.String(50))
    doses = db.relationship("Dose", backref="medication", lazy=True, cascade="all, delete-orphan")

class Dose(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medication_id = db.Column(db.Integer, db.ForeignKey("medication.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(5), nullable=False)
    status = db.Column(db.String(20), default="pending")
    confirmed_at = db.Column(db.DateTime)
    snooze_until = db.Column(db.DateTime)
    notified_at = db.Column(db.DateTime)
    nag_sent = db.Column(db.Boolean, default=False)

# =============================================================================
# AUTH
# =============================================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# =============================================================================
# HELPERS
# =============================================================================
def _send_smtp(to_addr, subject, body):
    print(f"[DEBUG SMTP] to={to_addr}, subject={subject[:30]}")
    if not Config.EMAIL or not Config.EMAIL_PW:
        print("[DEBUG SMTP] MISSING CREDENTIALS")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = Config.EMAIL
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        print("[DEBUG SMTP] Connecting...")
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.starttls()
        print("[DEBUG SMTP] TLS OK, logging in...")
        server.login(Config.EMAIL, Config.EMAIL_PW)
        print("[DEBUG SMTP] Login OK, sending...")
        server.sendmail(Config.EMAIL, to_addr, msg.as_string())
        server.quit()
        print("[DEBUG SMTP] SENT SUCCESSFULLY")
        return True
    except Exception as e:
        print(f"[DEBUG SMTP] EXCEPTION: {e}")
        return False

def send_email(subject, body):
    if _send_smtp(Config.ALERT_EMAIL, subject, body):
        app.logger.info(f"Email sent: {subject}")

def format_schedule_label(med):
    if not med.schedule_type or med.schedule_type == 'daily':
        return 'Daily'
    if med.schedule_type == 'weekdays':
        return 'Mon-Fri'
    if med.schedule_type == 'weekly':
        days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        nums = [int(x) for x in med.schedule_days.split(',') if x.strip()]
        return ', '.join(days[n] for n in nums)
    if med.schedule_type == 'monthly':
        return f"{med.schedule_days} of month"
    if med.schedule_type == 'yearly':
        mm, dd = med.schedule_days.split('-')
        month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        return f"{month_names[int(mm)-1]} {int(dd)} yearly"
    return ''

def med_is_scheduled_for_date(med, target_date):
    if med.schedule_type == 'daily':
        return True
    if med.schedule_type in ('weekdays', 'weekly'):
        if not med.schedule_days:
            return True
        allowed = [int(x) for x in med.schedule_days.split(',') if x.strip()]
        return target_date.weekday() in allowed
    if med.schedule_type == 'monthly':
        if not med.schedule_days:
            return True
        allowed = [int(x) for x in med.schedule_days.split(',') if x.strip()]
        return target_date.day in allowed
    if med.schedule_type == 'yearly':
        return target_date.strftime('%m-%d') == med.schedule_days
    return True

def ensure_today_doses():
    today = date.today()
    meds = Medication.query.filter_by(active=True).all()
    created = False
    for med in meds:
        if not med_is_scheduled_for_date(med, today):
            continue
        if not Dose.query.filter_by(medication_id=med.id, date=today).first():
            db.session.add(Dose(medication_id=med.id, date=today, time=med.time))
            created = True
    if created:
        db.session.commit()

# =============================================================================
# TELEGRAM NOTIFICATIONS
# =============================================================================
OFFSET_FILE = "telegram_offset.json"

def _read_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0

def _write_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)

def send_telegram(text, dose_id=None):
    print(f"[DEBUG TG] called, dose_id={dose_id}")
    if not Config.TELEGRAM_TOKEN or not Config.TELEGRAM_CHAT_ID:
        print("[DEBUG TG] MISSING TOKEN OR CHAT_ID")
        return False
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": Config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        if dose_id:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "✅ Confirm Taken", "callback_data": f"confirm_{dose_id}"},
                    {"text": "😴 Snooze 10m", "callback_data": f"snooze_{dose_id}"}
                ]]
            }
        data = json.dumps(payload).encode()
        print(f"[DEBUG TG] JSON size: {len(data)} bytes")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[DEBUG TG] HTTP {resp.status}")
            return resp.status == 200
    except Exception as e:
        print(f"[DEBUG TG] EXCEPTION: {e}")
        return False

def _ack_telegram_callback(callback_id, text):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"
        payload = {"callback_query_id": callback_id, "text": text}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        if e.code != 400:
            app.logger.error(f"Telegram ack HTTP {e.code}")
    except Exception as e:
        app.logger.error(f"Telegram ack error: {e}")

def extract_med_from_text(text):
    if not text:
        return None
    text_lower = text.lower()
    clean = re.sub(r"^(re:|fwd:|\s)+", "", text_lower)
    meds = Medication.query.all()
    for med in meds:
        if med.name.lower() in clean:
            return med.name
    return None

def check_telegram_replies():
    if not Config.TELEGRAM_TOKEN or not Config.TELEGRAM_CHAT_ID:
        return
    try:
        offset = _read_offset()
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/getUpdates"
        payload = {"offset": offset + 1, "limit": 10}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if not result.get("ok") or not result.get("result"):
                return

            for update in result["result"]:
                _write_offset(update["update_id"])

                cb = update.get("callback_query")
                msg = update.get("message")

                if cb:
                    data = cb.get("data", "")
                    from_id = str(cb["from"]["id"])
                    if from_id != Config.TELEGRAM_CHAT_ID:
                        continue

                    if data.startswith("confirm_"):
                        dose_id = int(data.split("_")[1])
                        with app.app_context():
                            dose = Dose.query.get(dose_id)
                            if dose and dose.status != "confirmed":
                                dose.status = "confirmed"
                                dose.confirmed_at = datetime.now()
                                db.session.commit()
                                try:
                                    scheduler.remove_job(f"nag_{dose.id}")
                                except Exception:
                                    pass
                                _ack_telegram_callback(cb["id"], f"✅ {dose.medication.name} confirmed")

                    elif data.startswith("snooze_"):
                        dose_id = int(data.split("_")[1])
                        with app.app_context():
                            dose = db.session.get(Dose, dose_id)
                            if dose:
                                dose.status = "snoozed"
                                dose.snooze_until = datetime.now() + timedelta(minutes=10)
                                db.session.commit()
                                scheduler.add_job(
                                    send_notifications,
                                    "date",
                                    run_date=dose.snooze_until,
                                    args=[dose.medication_id],
                                    id=f"snooze_{dose.id}",
                                    replace_existing=True,
                                )
                                _ack_telegram_callback(cb["id"], f"😴 {dose.medication.name} snoozed 10m")

                elif msg:
                    text = msg.get("text", "").lower()
                    from_id = str(msg["from"]["id"])
                    if from_id != Config.TELEGRAM_CHAT_ID:
                        continue

                    is_confirm = any(w in text for w in ["taken", "took", "yes", "done"])
                    is_snooze = "snooze" in text
                    if not is_confirm and not is_snooze:
                        continue

                    with app.app_context():
                        today = date.today()
                        med_name = extract_med_from_text(text)
                        dose = None

                        if med_name:
                            med = Medication.query.filter(Medication.name.ilike(f"%{med_name}%")).first()
                            if med:
                                dose = Dose.query.filter_by(medication_id=med.id, date=today)\
                                                 .filter(Dose.status.in_(["pending", "snoozed"])).first()

                        if not dose and is_confirm:
                            pending = Dose.query.filter_by(date=today)\
                                                .filter(Dose.status.in_(["pending", "snoozed"])).all()
                            if len(pending) == 1:
                                dose = pending[0]

                        if dose:
                            if is_confirm and dose.status != "confirmed":
                                dose.status = "confirmed"
                                dose.confirmed_at = datetime.now()
                                db.session.commit()
                                try:
                                    scheduler.remove_job(f"nag_{dose.id}")
                                except Exception:
                                    pass
                            elif is_snooze:
                                dose.status = "snoozed"
                                dose.snooze_until = datetime.now() + timedelta(minutes=10)
                                db.session.commit()
                                scheduler.add_job(
                                    send_notifications,
                                    "date",
                                    run_date=dose.snooze_until,
                                    args=[dose.medication_id],
                                    id=f"snooze_{dose.id}",
                                    replace_existing=True,
                                )
    except Exception as e:
        app.logger.error(f"Telegram poll error: {e}")

# =============================================================================
# SCHEDULER JOBS
# =============================================================================
def send_notifications(med_id):
    with app.app_context():
        print(f"[DEBUG] === TRIGGER med_id={med_id} ===")
        med = db.session.get(Medication, med_id)
        print(f"[DEBUG] med={med}, active={med.active if med else 'N/A'}")
        if not med or not med.active:
            print("[DEBUG] med missing/inactive, returning")
            return

        today = date.today()
        dose = Dose.query.filter_by(medication_id=med.id, date=today).first()
        print(f"[DEBUG] dose={dose}")
        if not dose:
            dose = Dose(medication_id=med.id, date=today, time=med.time)
            db.session.add(dose)
            db.session.commit()
            print("[DEBUG] created new dose")

        print(f"[DEBUG] dose.status={dose.status}")
        if dose.status == "confirmed":
            print("[DEBUG] already confirmed, returning")
            return
        if dose.status == "snoozed" and dose.snooze_until and dose.snooze_until > datetime.now():
            print("[DEBUG] snoozed, returning")
            return

        dose.notified_at = datetime.now()
        db.session.commit()

        subject = f"💊 {med.name}"
        body = (f"Time to take {med.name} ({med.dosage}).\n"
                f"{med.instructions or ''}\n\n"
                f"Reply: TAKEN or SNOOZE 10")

        print("[DEBUG] about to call send_email...")
        send_email(subject, body)
        print("[DEBUG] send_email returned")

        if Config.TELEGRAM_TOKEN:
            print("[DEBUG] about to call send_telegram...")
            send_telegram(
                f"⏰ <b>{med.name}</b>\n📏 {med.dosage}\n📝 {med.instructions or ''}",
                dose_id=dose.id
            )
            print("[DEBUG] send_telegram returned")
        else:
            print("[DEBUG] no telegram token, skipping")

        print("[DEBUG] scheduling nag...")
        nag_time = datetime.now() + timedelta(minutes=15)
        scheduler.add_job(
            send_nag,
            "date",
            run_date=nag_time,
            args=[dose.id],
            id=f"nag_{dose.id}",
            replace_existing=True,
        )
        print("[DEBUG] === DONE ===")

def send_nag(dose_id):
    with app.app_context():
        dose = Dose.query.get(dose_id)
        if not dose or dose.status != "pending" or dose.nag_sent:
            return
        dose.nag_sent = True
        db.session.commit()
        med = dose.medication
        msg = (f"⚠️ You missed {med.name} ({med.dosage}). Please take it now.\n"
               f"Reply: TAKEN or SNOOZE 10")
        send_email(f"Missed: {med.name}", msg)

        if Config.TELEGRAM_TOKEN:
            send_telegram(
                f"⚠️ You missed <b>{med.name}</b> ({med.dosage}). Please take it now.",
                dose_id=dose.id
            )

# =============================================================================
# ROUTES
# =============================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        flash("Invalid username or password")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    ensure_today_doses()
    today = date.today()
    doses = Dose.query.filter_by(date=today).join(Medication).order_by(Dose.time).all()
    now = datetime.now()

    dose_data = []
    any_due = False
    for d in doses:
        dt = datetime.combine(today, datetime.strptime(d.time, "%H:%M").time())
        if d.status == "confirmed":
            state, css, label = ("confirmed", "green", "✅ Confirmed")
        elif d.status == "snoozed":
            state, css, label = ("snoozed", "orange", "😴 Snoozed")
        elif dt > now:
            state, css, label = ("upcoming", "blue", "⏳ Upcoming")
        elif (now - dt).total_seconds() < 1800:
            state, css, label = ("due", "yellow", "🔔 Take Now")
            any_due = True
        else:
            state, css, label = ("missed", "red", "❌ Overdue")

        dose_data.append({
            "obj": d,
            "time": d.time,
            "state": state,
            "css": css,
            "label": label,
            "schedule_label": format_schedule_label(d.medication),
        })

    return render_template_string(DASHBOARD_HTML, doses=dose_data, now=now, any_due=any_due)

@app.route("/confirm/<int:dose_id>", methods=["POST"])
@login_required
def confirm(dose_id):
    dose = Dose.query.get_or_404(dose_id)
    if dose.status != "confirmed":
        dose.status = "confirmed"
        dose.confirmed_at = datetime.now()
        db.session.commit()
        try:
            scheduler.remove_job(f"nag_{dose.id}")
        except Exception:
            pass
        flash(f"Confirmed: {dose.medication.name}", "success")
    return redirect(url_for("dashboard"))

@app.route("/snooze/<int:dose_id>", methods=["POST"])
@login_required
def snooze(dose_id):
    minutes = int(request.form.get("minutes", 10))
    dose = Dose.query.get_or_404(dose_id)

    dose.status = "snoozed"
    dose.snooze_until = datetime.now() + timedelta(minutes=minutes)
    db.session.commit()

    scheduler.add_job(
        send_notifications,
        "date",
        run_date=dose.snooze_until,
        args=[dose.medication_id],
        id=f"snooze_{dose.id}",
        replace_existing=True,
    )
    flash(f"Snoozed {dose.medication.name} for {minutes} minutes", "info")
    return redirect(url_for("dashboard"))

@app.route("/medications")
@login_required
def medications():
    meds = Medication.query.all()
    return render_template_string(MEDS_HTML, medications=meds)

@app.route("/medications/add", methods=["POST"])
@login_required
def add_medication():
    schedule_type = request.form.get("schedule_type", "daily")
    schedule_days = ""

    if schedule_type == "weekdays":
        schedule_days = "0,1,2,3,4"
    elif schedule_type == "weekly":
        days = request.form.getlist("weekdays")
        schedule_days = ",".join(str(n) for n in sorted(int(d) for d in days))
    elif schedule_type == "monthly":
        schedule_days = request.form.get("month_days", "").replace(" ", "")
    elif schedule_type == "yearly":
        schedule_days = request.form.get("yearly_date", "").strip()

    med = Medication(
        name=request.form["name"],
        dosage=request.form.get("dosage", ""),
        time=request.form["time"],
        instructions=request.form.get("instructions", ""),
        schedule_type=schedule_type,
        schedule_days=schedule_days,
    )
    db.session.add(med)
    db.session.commit()

    h, m = map(int, med.time.split(":"))

    if med.schedule_type == "daily":
        trigger_args = {'hour': h, 'minute': m}
    elif med.schedule_type in ("weekdays", "weekly"):
        trigger_args = {'day_of_week': med.schedule_days, 'hour': h, 'minute': m}
    elif med.schedule_type == "monthly":
        trigger_args = {'day': med.schedule_days, 'hour': h, 'minute': m}
    elif med.schedule_type == "yearly":
        mm, dd = med.schedule_days.split("-")
        trigger_args = {'month': int(mm), 'day': int(dd), 'hour': h, 'minute': m}
    else:
        trigger_args = {'hour': h, 'minute': m}

    scheduler.add_job(
        send_notifications,
        "cron",
        args=[med.id],
        id=f"med_{med.id}",
        replace_existing=True,
        **trigger_args
    )
    flash(f"Added {med.name}", "success")
    return redirect(url_for("medications"))

@app.route("/medications/delete/<int:med_id>", methods=["POST"])
@login_required
def delete_medication(med_id):
    med = Medication.query.get_or_404(med_id)
    try:
        scheduler.remove_job(f"med_{med.id}")
    except Exception:
        pass
    db.session.delete(med)
    db.session.commit()
    flash(f"Deleted {med.name}", "danger")
    return redirect(url_for("medications"))

@app.route("/history")
@login_required
def history():
    cutoff = date.today() - timedelta(days=60)
    doses = Dose.query.filter(Dose.date >= cutoff)\
                      .order_by(Dose.date.desc(), Dose.time.asc())\
                      .all()

    confirmed_count = sum(1 for d in doses if d.status == "confirmed")
    missed_count = sum(1 for d in doses if d.status == "pending")
    snoozed_count = sum(1 for d in doses if d.status == "snoozed")

    return render_template_string(
        HISTORY_HTML,
        doses=doses,
        confirmed_count=confirmed_count,
        missed_count=missed_count,
        snoozed_count=snoozed_count
    )

# =============================================================================
# INIT
# =============================================================================
def decode_header_value(value):
    if not value:
        return ""
    decoded = decode_header(value)[0]
    if isinstance(decoded[0], bytes):
        return decoded[0].decode(decoded[1] or "utf-8", errors="ignore")
    return str(decoded[0])

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="ignore") if payload else ""

def check_email_replies():
    if not Config.IMAP_SERVER or not Config.EMAIL or not Config.EMAIL_PW:
        return
    try:
        mail = imaplib.IMAP4_SSL(Config.IMAP_SERVER)
        mail.login(Config.EMAIL, Config.EMAIL_PW)
        mail.select("inbox")

        # Only check last 2 days
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        dt = datetime.now() - timedelta(days=2)
        since_date = f"{dt.day:02d}-{months[dt.month-1]}-{dt.year}"
        status, messages = mail.search(None, f'(UNSEEN SINCE "{since_date}")')

        if status != "OK" or not messages[0]:
            mail.logout()
            return

        for msg_id in messages[0].split():
            status, data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw = data[0][1]
            msg = email.message_from_bytes(raw)
            sender = msg.get("From", "").lower()

            # ONLY accept replies from your own address
            if not Config.ALERT_EMAIL or Config.ALERT_EMAIL.lower() not in sender:
                continue

            subject = decode_header_value(msg.get("Subject", "")).lower()
            body = get_email_body(msg).lower()
            full_text = f"{subject} {body}"

            # Strict commands only
            is_confirm = any(w in full_text for w in ["taken", "took", "yes", "done"])
            is_snooze = "snooze" in full_text

            if not is_confirm and not is_snooze:
                mail.store(msg_id, "+FLAGS", "\\Seen")
                continue

            with app.app_context():
                today = date.today()
                med_name = extract_med_from_text(subject) or extract_med_from_text(full_text)

                minutes = 10
                if is_snooze:
                    m = re.search(r"snooze\s+(\d+)", full_text)
                    if m:
                        minutes = int(m.group(1))

                dose = None
                if med_name:
                    med = Medication.query.filter(Medication.name.ilike(f"%{med_name}%")).first()
                    if med:
                        dose = Dose.query.filter_by(medication_id=med.id, date=today)\
                                         .filter(Dose.status.in_(["pending", "snoozed"])).first()

                if not dose and is_confirm:
                    pending = Dose.query.filter_by(date=today)\
                                        .filter(Dose.status.in_(["pending", "snoozed"])).all()
                    if len(pending) == 1:
                        dose = pending[0]
                    elif len(pending) > 1:
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        continue
                    else:
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        continue

                if dose:
                    if is_confirm and dose.status != "confirmed":
                        dose.status = "confirmed"
                        dose.confirmed_at = datetime.now()
                        db.session.commit()
                        try:
                            scheduler.remove_job(f"nag_{dose.id}")
                        except Exception:
                            pass
                    elif is_snooze:
                        dose.status = "snoozed"
                        dose.snooze_until = datetime.now() + timedelta(minutes=minutes)
                        db.session.commit()
                        scheduler.add_job(
                            send_notifications,
                            "date",
                            run_date=dose.snooze_until,
                            args=[dose.medication_id],
                            id=f"snooze_{dose.id}",
                            replace_existing=True,
                        )

                mail.store(msg_id, "+FLAGS", "\\Seen")

        mail.logout()
    except Exception as e:
        app.logger.error(f"IMAP error: {e}")

def init_db_and_scheduler():
    with app.app_context():
        db.create_all()
        if not User.query.first():
            db.session.add(User(
                username="admin",
                password_hash=generate_password_hash(Config.DEFAULT_PW)
            ))
        if not Medication.query.first():
            defaults = [
                Medication(name="Vitamin D", dosage="2000 IU", time="08:00", instructions="With breakfast"),
                Medication(name="Lisinopril", dosage="10mg", time="09:00", instructions="With water"),
                Medication(name="Metformin", dosage="500mg", time="13:00", instructions="With lunch"),
                Medication(name="Atorvastatin", dosage="20mg", time="21:30", instructions="Before bed"),
            ]
            db.session.add_all(defaults)
        db.session.commit()

        for med in Medication.query.filter_by(active=True).all():
            h, m = map(int, med.time.split(":"))

            if med.schedule_type == "daily":
                trigger_args = {'hour': h, 'minute': m}
            elif med.schedule_type in ("weekdays", "weekly"):
                trigger_args = {'day_of_week': med.schedule_days, 'hour': h, 'minute': m}
            elif med.schedule_type == "monthly":
                trigger_args = {'day': med.schedule_days, 'hour': h, 'minute': m}
            elif med.schedule_type == "yearly":
                mm, dd = med.schedule_days.split("-")
                trigger_args = {'month': int(mm), 'day': int(dd), 'hour': h, 'minute': m}
            else:
                trigger_args = {'hour': h, 'minute': m}

            scheduler.add_job(
                send_notifications,
                "cron",
                args=[med.id],
                id=f"med_{med.id}",
                replace_existing=True,
                **trigger_args
            )

    if Config.TELEGRAM_TOKEN:
        scheduler.add_job(
            check_telegram_replies,
            "interval",
            seconds=30,
            id="telegram_poll",
            replace_existing=True,
        )

    if Config.IMAP_SERVER:
        scheduler.add_job(
            check_email_replies,
            "interval",
            minutes=1,
            id="imap_poll",
            replace_existing=True,
        )

    scheduler.start()

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    init_db_and_scheduler()
    app.run(host="0.0.0.0", port=5000, use_reloader=False)