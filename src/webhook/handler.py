import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from shared import dynamo, telegram

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CONFIRM_COMMANDS = {"/done", "/administered"}
HISTORY_DEFAULT_LIMIT = 10
HISTORY_MAX_LIMIT = 50
OK_RESPONSE = {"statusCode": 200, "body": "ok"}
FORBIDDEN_RESPONSE = {"statusCode": 403, "body": "forbidden"}

_webhook_secret = os.environ.get("WEBHOOK_SECRET")

_config_dir = os.environ.get("CONFIG_PATH", os.path.dirname(__file__))
with open(os.path.join(_config_dir, "config.json")) as f:
    CONFIG = json.load(f)

def _parse_update(event):
    """Parse an API Gateway v2 event into chat_id, text, name, and callback_query_id.

    Handles both regular messages and inline button callback queries.
    """
    body = json.loads(event.get("body", "{}"))

    callback = body.get("callback_query")
    if callback:
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        data = callback.get("data", "")
        first = callback.get("from", {}).get("first_name", "")
        last = callback.get("from", {}).get("last_name", "")
        name = f"{first} {last}".strip() or "Unknown"
        return chat_id, data, name, callback.get("id")

    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    first = message.get("from", {}).get("first_name", "")
    last = message.get("from", {}).get("last_name", "")
    name = f"{first} {last}".strip() or "Unknown"
    return chat_id, text, name, None


def _handle_done(chat_id, name):
    dog_name = CONFIG["dog_name"]
    meds = ", ".join(f"{m['name']} ({m['dose']})" for m in CONFIG["medications"])

    pending = dynamo.get_pending_confirmations()
    if not pending:
        telegram.send_message(chat_id, "No pending medication to confirm right now.")
        return

    for pending_confirmation in pending:
        key = pending_confirmation.schedule_key
        dynamo.mark_confirmed(key, chat_id)
        dynamo.record_administration(
            dog_name,
            key,
            chat_id,
            name,
            past_due=_is_past_due(pending_confirmation),
            medications=CONFIG["medications"],
            scheduled_at=pending_confirmation.scheduled_at,
        )
        # Delete old notification/reminder messages
        sent_messages = dynamo.get_sent_messages(key)
        if sent_messages:
            telegram.delete_broadcast(sent_messages)

    # Broadcast confirmation to all subscribers
    subscribers = dynamo.get_all_subscribers()
    all_chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]

    is_past_due = any(_is_past_due(confirmation) for confirmation in pending)
    icon = "⚠️" if is_past_due else "✅"
    confirmation_text = "confirmed *past due*" if is_past_due else "confirmed"

    confirmed_text = (
        f"{icon} {dog_name}'s {meds} "
        f"\u2014 {confirmation_text} by {name}!"
    )
    if all_chat_ids:
        telegram.broadcast(all_chat_ids, confirmed_text)

def _is_past_due(confirmation: dynamo.PendingConfirmation):
    due_period_minutes = CONFIG["due_period_minutes"]
    now = time.time()
    scheduled_at = confirmation.scheduled_at
    difference_minuntes = (now - scheduled_at) / 60
    return difference_minuntes > due_period_minutes

def _parse_history_limit(text):
    parts = text.split()
    if len(parts) > 1 and parts[1].isdigit():
        return max(1, min(int(parts[1]), HISTORY_MAX_LIMIT))
    return HISTORY_DEFAULT_LIMIT


def _format_history_entry(entry, tz):
    """One line per dose: scheduled slot, status, who confirmed and when."""
    scheduled = datetime.strptime(entry["schedule_key"], "%Y-%m-%d_%H").replace(tzinfo=tz)
    slot = scheduled.strftime("%a %b %d %H:%M")

    if entry["status"] == dynamo.HISTORY_GIVEN and entry["confirmed_at"]:
        given_at = datetime.fromtimestamp(entry["confirmed_at"], tz).strftime("%H:%M")
        icon = "⚠️" if entry["past_due"] else "✅"
        who = entry["confirmed_by_name"] or "someone"
        return f"{icon} {slot} — given {given_at} by {who}"

    scheduled_at = entry["scheduled_at"] or scheduled.timestamp()
    if time.time() - scheduled_at < 86400:
        return f"⏳ {slot} — pending"
    return f"❌ {slot} — missed"


def _handle_history(chat_id, text):
    dog_name = CONFIG["dog_name"]
    tz = ZoneInfo(CONFIG["timezone"])
    limit = _parse_history_limit(text)

    entries = dynamo.get_history(dog_name, limit=limit)
    if not entries:
        telegram.send_message(chat_id, f"No medication history recorded for {dog_name} yet.")
        return

    lines = [f"📋 Last {len(entries)} dose(s) for {dog_name}:", ""]
    lines.extend(_format_history_entry(e, tz) for e in entries)
    telegram.send_message(chat_id, "\n".join(lines))


def _handle_subscribe(chat_id, name):
    dynamo.add_subscriber(chat_id, name)
    telegram.send_message(chat_id, "You're now subscribed to medication reminders!")


def _handle_unsubscribe(chat_id):
    dynamo.remove_subscriber(chat_id)
    telegram.send_message(chat_id, "You've been unsubscribed from medication reminders.")


def _handle_start(chat_id, name):
    dynamo.add_subscriber(chat_id, name)
    telegram.send_message(
        chat_id,
        "Welcome! You're subscribed to medication reminders.\n\n"
        "Commands:\n"
        "/done - Confirm medication given\n"
        "/history [n] - Show the last n doses (default 10)\n"
        "/subscribe - Subscribe to reminders\n"
        "/unsubscribe - Unsubscribe from reminders",
    )


def _verify_secret(event):
    """Validate the X-Telegram-Bot-Api-Secret-Token header if WEBHOOK_SECRET is configured."""
    if not _webhook_secret:
        return True
    headers = event.get("headers") or {}
    token = headers.get("x-telegram-bot-api-secret-token", "")
    return token == _webhook_secret


def lambda_handler(event, context):
    if not _verify_secret(event):
        logger.warning("Rejected request: invalid webhook secret")
        return FORBIDDEN_RESPONSE

    chat_id, text, name, callback_query_id = _parse_update(event)
    if chat_id is None:
        logger.warning("No chat_id in event: %s", json.dumps(event))
        return OK_RESPONSE

    # Handle inline button callback
    if callback_query_id:
        if text == "done":
            _handle_done(chat_id, name)
        telegram.answer_callback_query(callback_query_id)
        return OK_RESPONSE

    command = text.split()[0].lower() if text else ""
    # Strip @botname suffix (e.g. /done@MyBot)
    command = command.split("@")[0]

    if command in CONFIRM_COMMANDS:
        _handle_done(chat_id, name)
    elif command == "/history":
        _handle_history(chat_id, text)
    elif command == "/subscribe":
        _handle_subscribe(chat_id, name)
    elif command == "/unsubscribe":
        _handle_unsubscribe(chat_id)
    elif command == "/start":
        _handle_start(chat_id, name)
    else:
        telegram.send_message(
            chat_id,
            "Unknown command. Try /done, /history, /subscribe, or /unsubscribe.",
        )

    return OK_RESPONSE
