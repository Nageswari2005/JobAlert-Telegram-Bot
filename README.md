# JobAlert Telegram Bot

A beginner-friendly Python bot that checks public remote-job feeds, filters relevant roles,
stores sent job IDs in SQLite, and sends new matches to Telegram twice a day.

## Included in this first version

- Roles: Java, Python, Frontend, Software Developer, Internships, Data Analyst, Web Developer
- Geography: India-specific listings and remote listings marked India/worldwide/anywhere.
- Schedule: 9:00 AM and 6:00 PM Asia/Kolkata (IST).
- Duplicate protection: SQLite.
- Commands: `/start`, `/jobs`, `/help`.

## Important coverage note

This starter version uses Remotive and Remote OK public feeds. They are primarily remote-job
sources, not comprehensive Indian job boards. It will not find every India-based vacancy.
Remote jobs with country restrictions are filtered where the feed makes those restrictions
clear. If a listing only says "Remote", verify that applicants in India are eligible before
applying. A later version can add India-focused providers such as Adzuna (which requires
an API ID and key) and other sources that permit API/feed use.

Remotive asks API users to credit Remotive and link to each original Remotive listing.
Its public API data may be delayed by 24 hours and should not be polled excessively.
Remote OK asks aggregators to credit Remote OK and link to the original listing.
Please respect each provider's current terms.

## 1. Install Python

Install Python 3.11 or newer from https://www.python.org/downloads/
On Windows, tick **Add Python to PATH** during installation.

Check in PowerShell:

```powershell
py --version
```

## 2. Create your Telegram bot

1. Open Telegram and search for `@BotFather` (verify the official account).
2. Send `/newbot`.
3. Enter a display name, for example `Nag JobAlert`.
4. Enter a unique username ending in `bot`, for example `nag_daily_jobalert_bot`.
5. BotFather gives you a token. Treat it like a password. Do not share it or upload it to GitHub.
6. Open your new bot using its username and press **Start**. The bot cannot message you first.

## 3. Set up the project in VS Code

1. Extract this ZIP file.
2. Open the `JobAlert_Telegram_Bot` folder in VS Code.
3. Open Terminal > New Terminal.
4. Create a virtual environment:

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

5. Install packages:

```powershell
py -m pip install -r requirements.txt
```

## 4. Add your bot token

1. In VS Code, make a copy of `.env.example` and name the copy `.env`.
2. Open `.env`.
3. Replace the placeholder with the token from BotFather:

```env
TELEGRAM_BOT_TOKEN=123456789:replace_this_with_your_real_token
```

Do not include extra quotation marks. Do not share the token in screenshots or chat.

## 5. Run the bot

In the activated terminal:

```powershell
py -m main
```

Open your Telegram bot and send:

```text
/start
```

Then send:

```text
/jobs
```

The `/jobs` command runs an immediate search. If there are matching new listings, the bot sends them. If not, it reports that no new matching jobs were found.

## 6. Keep it running

The 9 AM and 6 PM schedule works only while the Python program is running and the computer has internet access. Keep the terminal open.

If you close the terminal, shut down the computer, or put it to sleep, scheduled messages stop. For 24/7 alerts, deploy the project to an always-on host or VPS in a later step. A free hosting service may sleep or have usage limits.

## 7. Troubleshooting

- `Missing TELEGRAM_BOT_TOKEN`: check that `.env` exists and the token is correct.
- Bot does not reply: open the bot and press Start, then check the terminal.
- `InvalidToken`: create/copy a fresh token from BotFather. If exposed, revoke it with BotFather.
- `No new matching jobs`: the feeds may not currently have new listings matching your roles and location.
- `ModuleNotFoundError`: activate `.venv` and run `py -m pip install -r requirements.txt`.
- Windows says `py` is not recognized: reinstall Python and enable PATH, or try `python` instead of `py`.

## Files

- `main.py` — bot, job feeds, filters, scheduler, and database logic.
- `requirements.txt` — Python packages.
- `.env.example` — token template.
- `.gitignore` — prevents committing secrets and local database.
