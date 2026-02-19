import json
import logging
import urllib.request
import urllib.error
import os

import boto3

logger = logging.getLogger(__name__)

_bot_token = None
_ssm_client = None

DONE_BUTTON = {
    "inline_keyboard": [[{"text": "Done \u2705", "callback_data": "done"}]]
}

NO_BUTTONS = {"inline_keyboard": []}


def _get_ssm_client():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def get_bot_token():
    """Return Telegram bot token. Uses BOT_TOKEN env var if set, otherwise fetches from SSM."""
    global _bot_token
    if _bot_token is None:
        token = os.environ.get("BOT_TOKEN")
        if token:
            _bot_token = token
        else:
            param_name = os.environ["SSM_BOT_TOKEN_PARAM"]
            resp = _get_ssm_client().get_parameter(
                Name=param_name, WithDecryption=True
            )
            _bot_token = resp["Parameter"]["Value"]
    return _bot_token


def send_message(chat_id, text, reply_markup=None):
    """Send a message to a single Telegram chat. Returns message_id (int) on success, None on failure."""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("result", {}).get("message_id")
            return None
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("Failed to send message to %s: %s", chat_id, exc)
        return None


def answer_callback_query(callback_query_id, text=None):
    """Acknowledge a callback query (inline button press)."""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    body = {"callback_query_id": callback_query_id}
    if text:
        body["text"] = text
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("Failed to answer callback query: %s", exc)
        return False


def edit_message_text(chat_id, message_id, text, reply_markup=None):
    """Edit an existing message. Returns True on success."""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    body = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("Failed to edit message %s for %s: %s", message_id, chat_id, exc)
        return False


def edit_broadcast(sent_messages, text, reply_markup=None):
    """Edit messages for multiple subscribers given a {chat_id: message_id} map."""
    for chat_id, message_id in sent_messages.items():
        ok = edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
        if not ok:
            logger.warning("Edit broadcast failed for chat_id=%s", chat_id)


def edit_message_reply_markup(chat_id, message_id, reply_markup=None):
    """Edit only the reply markup of an existing message (leaves text unchanged)."""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/editMessageReplyMarkup"
    body = {"chat_id": chat_id, "message_id": message_id}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("Failed to edit reply markup %s for %s: %s", message_id, chat_id, exc)
        return False


def edit_broadcast_reply_markup(sent_messages, reply_markup=None):
    """Edit reply markup for multiple subscribers given a {chat_id: message_id} map."""
    for chat_id, message_id in sent_messages.items():
        ok = edit_message_reply_markup(chat_id, message_id, reply_markup=reply_markup)
        if not ok:
            logger.warning("Edit reply markup failed for chat_id=%s", chat_id)


def delete_message(chat_id, message_id):
    """Delete a message. Returns True on success."""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    body = {"chat_id": chat_id, "message_id": message_id}
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("Failed to delete message %s for %s: %s", message_id, chat_id, exc)
        return False


def delete_broadcast(sent_messages):
    """Delete messages for multiple subscribers given a {chat_id: [message_id, ...]} map."""
    for chat_id, message_ids in sent_messages.items():
        for message_id in message_ids:
            ok = delete_message(chat_id, message_id)
            if not ok:
                logger.warning("Delete broadcast failed for chat_id=%s msg=%s", chat_id, message_id)


def broadcast(chat_ids, text, reply_markup=None):
    """Send a message to multiple subscribers. Returns {chat_id: message_id} for successes."""
    sent = {}
    for chat_id in chat_ids:
        message_id = send_message(chat_id, text, reply_markup=reply_markup)
        if message_id is not None:
            sent[chat_id] = message_id
        else:
            logger.warning("Broadcast failed for chat_id=%s", chat_id)
    return sent
