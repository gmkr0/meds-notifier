import json
import logging
import os
from datetime import date, timedelta

from shared import dynamo, telegram

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_config_dir = os.environ.get("CONFIG_PATH", os.path.dirname(__file__))
with open(os.path.join(_config_dir, "config.json")) as f:
    CONFIG = json.load(f)

SCHEDULE_WINDOWS = ["morning", "evening"]


def _find_pending_keys():
    """Find all unconfirmed schedule keys, checking today and yesterday."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    pending = []
    for window in SCHEDULE_WINDOWS:
        for d in (today, yesterday):
            key = dynamo.build_schedule_key(window, d)
            item = dynamo.get_confirmation(key)
            if item is not None and not item["confirmed"]["BOOL"]:
                pending.append((key, window))
    return pending


def lambda_handler(event, context):
    dog_name = CONFIG["dog_name"]
    pending = _find_pending_keys()

    if not pending:
        logger.info("No pending confirmations — nothing to remind")
        return {"statusCode": 200, "body": "nothing pending"}

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]

    if not chat_ids:
        logger.warning("No subscribers for reminder")
        return {"statusCode": 200, "body": "no subscribers"}

    for key, window in pending:
        meds = [m for m in CONFIG["medications"] if m["schedule_key"] == window]
        med_names = ", ".join(f"{m['name']} {m['dose']}" for m in meds) if meds else "medication"
        text = (
            f"\u26a0\ufe0f Reminder: {dog_name}'s {med_names} "
            f"has not been confirmed yet!"
        )
        telegram.broadcast(chat_ids, text)
        logger.info("Sent reminder to %d subscribers for %s", len(chat_ids), key)

    return {"statusCode": 200, "body": f"reminded for {len(pending)} pending window(s)"}
