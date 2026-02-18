import json
import logging
import os

from shared import dynamo, telegram

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_config_dir = os.environ.get("CONFIG_PATH", os.path.dirname(__file__))
with open(os.path.join(_config_dir, "config.json")) as f:
    CONFIG = json.load(f)


def lambda_handler(event, context):
    schedule_key = event["schedule_key"]
    dog_name = CONFIG["dog_name"]
    full_key = dynamo.build_schedule_key(schedule_key)

    item = dynamo.get_confirmation(full_key)
    if item is None:
        logger.info("No confirmation record for %s — skipping", full_key)
        return {"statusCode": 200, "body": "no record"}

    if item["confirmed"]["BOOL"]:
        logger.info("Already confirmed for %s", full_key)
        return {"statusCode": 200, "body": "already confirmed"}

    meds = [m for m in CONFIG["medications"] if m["schedule_key"] == schedule_key]
    med_names = ", ".join(f"{m['name']} {m['dose']}" for m in meds) if meds else "medication"

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]

    if not chat_ids:
        logger.warning("No subscribers for reminder")
        return {"statusCode": 200, "body": "no subscribers"}

    text = (
        f"\u26a0\ufe0f Reminder: {dog_name}'s {med_names} "
        f"has not been confirmed yet!"
    )
    telegram.broadcast(chat_ids, text)

    logger.info("Sent reminder to %d subscribers for %s", len(chat_ids), full_key)
    return {"statusCode": 200, "body": f"reminded {len(chat_ids)} subscribers"}
