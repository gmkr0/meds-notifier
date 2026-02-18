import json
import logging
import urllib.request
import urllib.error
import os

import boto3

logger = logging.getLogger(__name__)

_bot_token = None
_ssm_client = None


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


def send_message(chat_id, text):
    """Send a message to a single Telegram chat. Returns True on success."""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("Failed to send message to %s: %s", chat_id, exc)
        return False


def broadcast(chat_ids, text):
    """Send a message to multiple subscribers. Logs failures individually."""
    for chat_id in chat_ids:
        ok = send_message(chat_id, text)
        if not ok:
            logger.warning("Broadcast failed for chat_id=%s", chat_id)
