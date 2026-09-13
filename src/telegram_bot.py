import os
import time
import requests

from logger import get_logger
from database import (
    get_pending_telegram_jobs,
    mark_job_telegram_sent, get_job_counts_by_decision, get_total_job_count,
)

logger = get_logger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(text, reply_markup=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    response = requests.post(
        f"{BASE_URL}/sendMessage",
        json=payload,
        timeout=10,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result}"
        )

    return result


def show_menu():
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Show APPLY jobs",
                    "callback_data": "apply_jobs",
                }
            ],
            [
                {
                    "text": "🤔 Show MAYBE jobs",
                    "callback_data": "maybe_jobs",
                }
            ],
            [
                {
                    "text": "📊 Show job counts",
                    "callback_data": "job_counts",
                }
            ],
            [
                {
                    "text": "🗂 Show total jobs",
                    "callback_data": "total_jobs",
                }
            ],
        ]
    }

    send_message(
        "🤖 Job Pipeline\n\nChoose an option:",
        reply_markup=keyboard,
    )



def show_job_counts():
    counts = get_job_counts_by_decision()

    message = (
        "📊 Job Statistics\n\n"
        f"✅ APPLY\n"
        f"Total: {counts['APPLY']['total']}\n"
        f"New: {counts['APPLY']['pending']}\n\n"

        f"🤔 MAYBE\n"
        f"Total: {counts['MAYBE']['total']}\n"
        f"New: {counts['MAYBE']['pending']}\n\n"

        f"⛔ SKIP\n"
        f"Total: {counts['SKIP']['total']}"
    )

    send_message(message)


def show_total_jobs():
    total = get_total_job_count()

    send_message(
        f"🗂 Database\n\n"
        f"Total jobs stored: {total}"
    )

def format_job_message(job):
    emoji = "🟢" if job["ai_decision"] == "APPLY" else "🟡"

    return (
        f"{emoji} {job['ai_decision']} — {job['ai_score']}/100\n\n"
        f"{job['job_title']}\n"
        f"{job['company']}\n"
        f"{job['location']}\n\n"
        f"{job['ai_reason']}\n\n"
        f"{job['job_url']}"
    )


def send_jobs(decision):
    jobs = get_pending_telegram_jobs(
        decision=decision,
        limit=20,
    )

    if not jobs:
        send_message(
            f"No pending {decision} jobs."
        )
        return

    send_message(
        f"Found {len(jobs)} pending {decision} jobs."
    )

    for job in jobs:
        try:
            send_message(
                format_job_message(job)
            )

            mark_job_telegram_sent(
                job["id"]
            )

        except Exception:
            logger.exception(
                "Failed to send job %s",
                job["id"],
            )


def answer_callback(callback_query_id):
    requests.post(
        f"{BASE_URL}/answerCallbackQuery",
        json={
            "callback_query_id": callback_query_id
        },
        timeout=10,
    )


def get_updates(offset=None):
    params = {
        "timeout": 30,
    }

    if offset is not None:
        params["offset"] = offset

    response = requests.get(
        f"{BASE_URL}/getUpdates",
        params=params,
        timeout=35,
    )

    response.raise_for_status()

    return response.json()["result"]


def run_bot():
    logger.info("Telegram bot started")

    offset = None

    while True:
        try:
            updates = get_updates(offset)

            for update in updates:
                offset = update["update_id"] + 1

                # /start command
                if "message" in update:
                    text = update["message"].get(
                        "text",
                        "",
                    )
                    message = update["message"]
                    chat_id = str(message["chat"]["id"])
                    if chat_id != str(TELEGRAM_CHAT_ID):
                        logger.warning(
                            "Ignoring message from unknown chat %s",
                            chat_id,
                        )
                        continue

                    if text == "/start":
                        show_menu()

                # button click
                if "callback_query" in update:
                    callback = update[
                        "callback_query"
                    ]

                    data = callback["data"]

                    answer_callback(
                        callback["id"]
                    )

                    if data == "apply_jobs":
                        send_jobs("APPLY")

                    elif data == "maybe_jobs":
                        send_jobs("MAYBE")

                    elif data == "job_counts":
                        show_job_counts()

                    elif data == "total_jobs":
                        show_total_jobs()

        except Exception:
            logger.exception(
                "Telegram bot polling failed"
            )

            time.sleep(5)



if __name__ == "__main__":
    run_bot()
