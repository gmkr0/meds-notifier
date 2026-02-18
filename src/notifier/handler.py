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

    meds = [m for m in CONFIG["medications"] if m["schedule_key"] == schedule_key]
    if not meds:
        logger.info("No medications for schedule_key=%s", schedule_key)
        return {"statusCode": 200, "body": "no medications for this window"}

    full_key = dynamo.build_schedule_key(schedule_key)
    dynamo.put_pending_confirmation(full_key)

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]

    if not chat_ids:
        logger.warning("No subscribers to notify")
        return {"statusCode": 200, "body": "no subscribers"}

    for med in meds:
        text = (
            f"\U0001f48a Time to give {dog_name} their "
            f"{med['name']} {med['dose']}! Reply /done to confirm."
        )
        telegram.broadcast(chat_ids, text)

    logger.info("Notified %d subscribers for %s", len(chat_ids), full_key)
    return {"statusCode": 200, "body": f"notified {len(chat_ids)} subscribers"}
