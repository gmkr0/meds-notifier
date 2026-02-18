import json
import logging
import os
from datetime import date, timedelta

from shared import dynamo, telegram

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CONFIRM_COMMANDS = {"/done", "/administered"}
OK_RESPONSE = {"statusCode": 200, "body": "ok"}
FORBIDDEN_RESPONSE = {"statusCode": 403, "body": "forbidden"}

_webhook_secret = os.environ.get("WEBHOOK_SECRET")


def _find_pending_schedule_key():
    """Find the most recent unconfirmed schedule key by checking DynamoDB.

    Checks in order: today evening, today morning, yesterday evening.
    Returns the first unconfirmed key found, or None.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    candidates = [
        dynamo.build_schedule_key("evening", today),
        dynamo.build_schedule_key("morning", today),
        dynamo.build_schedule_key("evening", yesterday),
    ]
    for key in candidates:
        item = dynamo.get_confirmation(key)
        if item is not None and not item["confirmed"]["BOOL"]:
            return key
    return None


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
    key = _find_pending_schedule_key()
    if key is None:
        telegram.send_message(chat_id, "No pending medication to confirm right now.")
        return

    dynamo.mark_confirmed(key, chat_id)

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]
    telegram.broadcast(chat_ids, f"{name} confirmed the medication! \u2705")


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
    elif command == "/subscribe":
        _handle_subscribe(chat_id, name)
    elif command == "/unsubscribe":
        _handle_unsubscribe(chat_id)
    elif command == "/start":
        _handle_start(chat_id, name)
    else:
        telegram.send_message(
            chat_id,
            "Unknown command. Try /done, /subscribe, or /unsubscribe.",
        )

    return OK_RESPONSE
