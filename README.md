# 💊 MedReminder — Personal Medication Reminder Web App

A self-hosted Flask web application that sends medication reminders via **Email** and **Telegram**, tracks daily doses, and supports reply-based confirmation and snoozing from any device.

---

## ✨ Features

- **Web Dashboard** — Manage medications and confirm doses from any browser
- **Flexible Scheduling** — Daily, weekdays, weekly, monthly, or yearly recurring reminders
- **Dual Notifications** — Email + Telegram push alerts with inline action buttons
- **Two-Way Replies** — Confirm or snooze via Telegram buttons **or** email replies (`TAKEN`, `SNOOZE 15`)
- **Missed Dose Nag** — Automatic follow-up alert after 15 minutes if unconfirmed
- **Dose History** — View confirmation history for the last 60 days
- **Mobile Friendly** — Responsive UI works seamlessly on phones and tablets

---

## 🏗️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask + SQLAlchemy |
| Scheduler | APScheduler (background cron) |
| Database | SQLite |
| Notifications | SMTP (Email) + Telegram Bot API |
| Reply Handling | IMAP (Email) + Telegram Long Polling |
| Deployment | Systemd + Optional Nginx |

---

## 📋 Requirements

- Ubuntu 22.04/24.04 LTS (or any Linux server)
- Python 3.10+
- Gmail account (for SMTP + IMAP)
- Telegram account (for bot notifications)

---

## 🚀 Installation

### 1. System Dependencies

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv sqlite3 -y
```

### 2. Create Application Directory

```bash
sudo mkdir -p /opt/medreminder
sudo chown -R $USER:$USER /opt/medreminder
cd /opt/medreminder
```

### 3. Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python Packages

```bash
pip install flask flask-sqlalchemy apscheduler python-dotenv werkzeug
```

Or use `requirements.txt`:

```text
flask>=2.0
flask-sqlalchemy>=3.0
apscheduler>=3.10
python-dotenv>=1.0
werkzeug>=2.0
```

### 5. Configure Environment Variables

```bash
nano /opt/medreminder/.env
```

```env
# Email (Gmail SMTP)
EMAIL_ADDRESS=your.email@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
ALERT_EMAIL=your.email@gmail.com

# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:YOUR_TOKEN_HERE
TELEGRAM_CHAT_ID=12345678

# Email Replies (IMAP)
IMAP_SERVER=imap.gmail.com

# Web App Security
SECRET_KEY=replace_with_random_letters_and_numbers
DEFAULT_PASSWORD=your_dashboard_password
```

> ⚠️ **Never commit `.env` to Git.** It contains your passwords and tokens.

---

## 🔧 External Service Setup

### Gmail Configuration (Email + IMAP)

1. Enable **2-Factor Authentication** on your Google Account
2. Go to **Google Account → Security → App Passwords**
3. Generate an App Password for **"Mail"** on **"Other device"**
4. Copy the 16-character password into `EMAIL_PASSWORD` in your `.env`
5. In Gmail, go to **Settings → Forwarding and POP/IMAP → Enable IMAP**

### Telegram Bot Setup

1. Open Telegram and search for **`@BotFather`**
2. Send `/newbot` and follow the prompts
3. Copy the **HTTP API Token** into `TELEGRAM_BOT_TOKEN`
4. Start a chat with your new bot and send **`/start`**
5. Get your Chat ID by visiting:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
6. Look for `"chat":{"id":12345678` — that number is your `TELEGRAM_CHAT_ID`

---

## 🖥️ Production Deployment

### Systemd Service (24/7)

Create the service file:

```bash
sudo nano /etc/systemd/system/medreminder.service
```

Paste the following (adjust `User`/`Group` if running as root):

```ini
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
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable medreminder
sudo systemctl start medreminder
```

Check status and logs:

```bash
sudo systemctl status medreminder
sudo journalctl -u medreminder -f
```

---

## 🌐 Nginx Reverse Proxy (Optional)

Access the app on standard port 80 instead of 5000:

```bash
sudo apt install nginx
sudo nano /etc/nginx/sites-available/medreminder
```

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/medreminder /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo ufw allow 'Nginx Full'
sudo ufw delete allow 5000/tcp
```

Now visit `http://your-server-ip/` without specifying a port.

---

## 📱 Usage

### Managing Medications

1. Open `http://your-server-ip/` in your browser
2. Log in with username `admin` and your `DEFAULT_PASSWORD`
3. Go to **⚙️ Manage Medications** to add, edit, or delete medications
4. Set schedule type: Daily, Weekdays, Weekly, Monthly, or Yearly

### Confirming / Snoozing Doses

**Via Telegram:**
- Tap **✅ Confirm Taken** or **😴 Snooze 10m** inline buttons
- Or send a text message: `TAKEN Depakote` or `SNOOZE 15`

**Via Email:**
- Reply to any reminder email with `TAKEN` or `SNOOZE 15`
- Only replies from your `ALERT_EMAIL` address are processed

---

## 🩺 Dose States

| State | Meaning |
|-------|---------|
| **Pending** | Waiting for you to take the medication |
| **Confirmed** | You confirmed the dose; nag cancelled |
| **Snoozed** | Re-alert scheduled for N minutes later |
| **Missed** | Overdue by >30 minutes with no confirmation |

---

## 🛠️ Troubleshooting

### Medication time passed but no alert fired?

APScheduler cron only fires at the **exact** scheduled time. If you set 08:00 and start the app at 08:05, it waits until **tomorrow** at 08:00.

**Fix:** Set a test medication 2 minutes in the future and wait.

### "No jobs scheduled" in logs?

The service wasn't restarted after editing `app.py` or `.env`:

```bash
sudo systemctl restart medreminder
```

### Email not sending?

- Verify you're using a **Gmail App Password**, not your normal Gmail password
- Ensure `EMAIL_ADDRESS` and `ALERT_EMAIL` are filled in `.env`
- Check `journalctl -u medreminder -n 50` for SMTP errors

### Telegram not responding?

- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct
- Ensure you sent `/start` to your bot in Telegram

---

## 💾 Backup & Migration

Important files to back up:

```bash
/opt/medreminder/meds.db              # SQLite database (all medications & history)
/opt/medreminder/telegram_offset.json # Telegram polling offset
/opt/medreminder/.env                 # Credentials and config
```

Restore by copying these files to a new server and restarting the service.

---

## 📝 .gitignore

If you push this to a repository, create `.gitignore`:

```gitignore
.env
meds.db
telegram_offset.json
__pycache__/
venv/
```

---

## 📄 License

MIT License — Free for personal and commercial use.

---

**Disclaimer:** This is a personal health tracking tool, not medical advice. Always follow your doctor's instructions.
```
