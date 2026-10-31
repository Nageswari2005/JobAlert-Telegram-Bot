import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

# -------------------- SETTINGS --------------------
IST = ZoneInfo("Asia/Kolkata")
DB_PATH = "jobalert.db"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# The first version uses public job feeds. These are not a complete list
# of every Indian vacancy; see README for adding India-focused sources.
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_URL = "https://remoteok.com/api"

ROLE_TERMS = [
    "java", "python", "frontend", "front-end", "front end",
    "software developer", "software engineer", "intern",
    "data analyst", "web developer", "web development",
]
MAX_AGE_DAYS = 30
MAX_JOBS_PER_DIGEST = 12

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("jobalert")


# -------------------- DATABASE --------------------
def db_connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sent_jobs (
                job_key TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                source TEXT,
                sent_at TEXT NOT NULL
            )
        """)
        conn.commit()


def add_subscriber(chat_id: int):
    with db_connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO subscribers(chat_id, created_at) VALUES (?, ?)",
            (chat_id, datetime.now(IST).isoformat()),
        )
        conn.commit()


def get_subscribers():
    with db_connect() as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    return [row[0] for row in rows]


def was_sent(job_key: str) -> bool:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM sent_jobs WHERE job_key = ?", (job_key,)
        ).fetchone()
    return row is not None


def mark_sent(job: dict):
    with db_connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sent_jobs
               (job_key, title, company, source, sent_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                job["key"], job["title"], job["company"], job["source"],
                datetime.now(IST).isoformat(),
            ),
        )
        conn.commit()


# -------------------- FILTERS --------------------
def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def matches_role(job: dict) -> bool:
    searchable = " ".join([
        job.get("title", ""),
        job.get("company", ""),
        job.get("category", ""),
        " ".join(job.get("tags", [])),
    ]).lower()
    return any(term in searchable for term in ROLE_TERMS)


def location_is_relevant(location: str) -> bool:
    """
    Include India-specific roles and remote roles explicitly open worldwide.
    A plain 'Remote' label is included but the notification tells the user
    to verify country eligibility on the original listing.
    """
    loc = clean(location).lower()
    if not loc:
        return False

    allowed = [
        "india", "worldwide", "anywhere", "global", "all countries",
        "remote", "work from anywhere",
    ]
    excluded = [
        "usa only", "us only", "united states", "north america",
        "europe only", "uk only", "canada only", "australia only",
        "germany only", "france only", "remote - us", "remote (us)",
        "remote us",
    ]
    if any(term in loc for term in excluded):
        return False
    return any(term in loc for term in allowed)


def is_recent(date_text: str) -> bool:
    if not date_text:
        return True  # Some feeds omit dates; keep but verify manually.
    try:
        parsed = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed >= datetime.now(IST) - timedelta(days=MAX_AGE_DAYS)
    except (ValueError, TypeError):
        return True


# -------------------- JOB SOURCES --------------------
def fetch_remotive() -> list[dict]:
    response = requests.get(
        REMOTIVE_URL,
        params={"limit": 200},
        headers={"User-Agent": "JobAlertStudentBot/1.0"},
        timeout=25,
    )
    response.raise_for_status()
    raw_jobs = response.json().get("jobs", [])
    jobs = []

    for item in raw_jobs:
        job = {
            "key": f"remotive:{item.get('id')}",
            "title": clean(item.get("title")),
            "company": clean(item.get("company_name")) or "Not specified",
            "location": clean(item.get("candidate_required_location")),
            "url": clean(item.get("url")),
            "date": clean(item.get("publication_date")),
            "salary": clean(item.get("salary")),
            "job_type": clean(item.get("job_type")),
            "category": clean(item.get("category")),
            "tags": item.get("tags", []) if isinstance(item.get("tags"), list) else [],
            "source": "Remotive",
        }
        if (job["title"] and job["url"]
                and matches_role(job)
                and location_is_relevant(job["location"])
                and is_recent(job["date"])):
            jobs.append(job)
    return jobs


def fetch_remoteok() -> list[dict]:
    response = requests.get(
        REMOTEOK_URL,
        headers={"User-Agent": "JobAlertStudentBot/1.0 (job alerts)"},
        timeout=25,
    )
    response.raise_for_status()
    raw_jobs = response.json()
    jobs = []

    for item in raw_jobs:
        if not isinstance(item, dict) or not item.get("id"):
            continue  # The feed starts with a legal notice object.

        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        job = {
            "key": f"remoteok:{item.get('id')}",
            "title": clean(item.get("position")),
            "company": clean(item.get("company")) or "Not specified",
            "location": clean(item.get("location")) or "Remote",
            "url": clean(item.get("url")),
            "date": clean(item.get("date")),
            "salary": clean(item.get("salary")),
            "job_type": "",
            "category": "",
            "tags": tags,
            "source": "Remote OK",
        }
        if (job["title"] and job["url"]
                and matches_role(job)
                and location_is_relevant(job["location"])
                and is_recent(job["date"])):
            jobs.append(job)
    return jobs


def collect_jobs() -> list[dict]:
    all_jobs = []
    for source_name, fetcher in [
        ("Remotive", fetch_remotive),
        ("Remote OK", fetch_remoteok),
    ]:
        try:
            found = fetcher()
            logger.info("%s returned %s matching jobs", source_name, len(found))
            all_jobs.extend(found)
        except requests.RequestException as exc:
            logger.exception("Could not fetch %s: %s", source_name, exc)
        except (ValueError, KeyError, TypeError) as exc:
            logger.exception("Unexpected %s response: %s", source_name, exc)

    # Deduplicate within this scan by source-specific key.
    unique = {}
    for job in all_jobs:
        unique[job["key"]] = job
    return list(unique.values())


# -------------------- TELEGRAM MESSAGES --------------------
def format_job(job: dict) -> str:
    location = job["location"]
    eligibility_note = ""
    if location.lower() == "remote":
        eligibility_note = "\n⚠️ Check whether applicants from India are eligible."

    lines = [
        "💼 " + job["title"],
        "🏢 Company: " + job["company"],
        "📍 Location: " + (location or "Not specified"),
    ]
    if job["job_type"]:
        lines.append("🧩 Type: " + job["job_type"].replace("_", " ").title())
    if job["salary"]:
        lines.append("💰 Salary/Stipend: " + job["salary"])
    lines.extend([
        "🔎 Source: " + job["source"],
        "🔗 Apply: " + job["url"],
    ])
    if job["source"] == "Remotive":
        lines.append("Source credit: Remotive")
    elif job["source"] == "Remote OK":
        lines.append("Source credit: Remote OK")
    if eligibility_note:
        lines.append(eligibility_note.strip())
    return "\n".join(lines)


async def send_digest(application: Application, chat_id: int | None = None):
    subscribers = [chat_id] if chat_id is not None else get_subscribers()
    if not subscribers:
        logger.info("No subscribers yet. Open the bot and send /start.")
        return

    jobs = collect_jobs()
    new_jobs = [job for job in jobs if not was_sent(job["key"])]
    new_jobs = new_jobs[:MAX_JOBS_PER_DIGEST]

    if not new_jobs:
        for target in subscribers:
            await application.bot.send_message(
                chat_id=target,
                text="🔎 JobAlert checked the sources. No new matching jobs were found in this scan.\n\nUse /jobs to run another check.",
            )
        return

    for target in subscribers:
        await application.bot.send_message(
            chat_id=target,
            text=f"🚀 JobAlert found {len(new_jobs)} new matching opportunities!",
        )
        for job in new_jobs:
            await application.bot.send_message(
                chat_id=target,
                text=format_job(job),
                disable_web_page_preview=True,
            )

    # Mark only after successful delivery to all target chats.
    for job in new_jobs:
        mark_sent(job)


# -------------------- COMMANDS --------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    add_subscriber(chat_id)
    await update.message.reply_text(
        "🎉 Welcome to JobAlert!\n\n"
        "I'll send matching job and internship updates at 9:00 AM and 6:00 PM IST.\n\n"
        "Commands:\n"
        "/jobs - Check for new jobs now\n"
        "/help - Show help\n\n"
        "Your chat is registered. Try /jobs for your first scan."
    )


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    add_subscriber(chat_id)
    await update.message.reply_text("🔍 Searching job feeds. This may take a few seconds...")
    await send_digest(context.application, chat_id=chat_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "JobAlert commands:\n"
        "/start - Register this Telegram chat\n"
        "/jobs - Search and send new matching jobs now\n"
        "/help - Show this message\n\n"
        "The automatic schedule is 9:00 AM and 6:00 PM IST."
    )


async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Starting scheduled job scan")
    await send_digest(context.application)


async def post_init(application: Application):
    # Two daily runs in India Standard Time.
    application.job_queue.run_daily(
        scheduled_job,
        time=datetime.strptime("09:00", "%H:%M").time().replace(tzinfo=IST),
        name="morning_job_alert",
    )
    application.job_queue.run_daily(
        scheduled_job,
        time=datetime.strptime("18:00", "%H:%M").time().replace(tzinfo=IST),
        name="evening_job_alert",
    )
    logger.info("Daily schedules registered: 09:00 and 18:00 IST")


def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit(
            "Missing TELEGRAM_BOT_TOKEN. Create a .env file using .env.example."
        )

    init_db()
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("jobs", jobs_command))
    application.add_handler(CommandHandler("help", help_command))

    logger.info("JobAlert bot is running. Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()
