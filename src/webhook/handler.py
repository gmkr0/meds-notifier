import json
import logging
from datetime import date, timedelta

from shared import dynamo, telegram

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CONFIRM_COMMANDS = {"/done", "/administered"}
OK_RESPONSE = {"statusCode": 200, "body": "ok"}


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


def _parse_message(event):
    """Extract chat_id, text, and sender name from an API Gateway v2 event."""
    body = json.loads(event.get("body", "{}"))
    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    first = message.get("from", {}).get("first_name", "")
    last = message.get("from", {}).get("last_name", "")
    name = f"{first} {last}".strip() or "Unknown"
    return chat_id, text, name


def _handle_done(chat_id, name):
    key = _find_pending_schedule_key()
    if key is None:
        telegram.send_message(chat_id, "No pending medication to confirm right now.")
        return

    dynamo.mark_confirmed(key, chat_id)

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]
    telegram.broadcast(chat_ids, f"{name} confirmed {key} \u2705")


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


def lambda_handler(event, context):
    chat_id, text, name = _parse_message(event)
    if chat_id is None:
        logger.warning("No chat_id in event: %s", json.dumps(event))
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
