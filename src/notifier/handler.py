import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from shared import dynamo, telegram

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_config_dir = os.environ.get("CONFIG_PATH", os.path.dirname(__file__))
with open(os.path.join(_config_dir, "config.json")) as f:
    CONFIG = json.load(f)


def lambda_handler(event, context):
    dog_name = CONFIG["dog_name"]
    med = CONFIG["medication"]

    tz = ZoneInfo(CONFIG["timezone"])
    now = datetime.now(tz)
    key = dynamo.build_schedule_key(now.hour, now.date())
    dynamo.put_pending_confirmation(key)

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]

    if not chat_ids:
        logger.warning("No subscribers to notify")
        return {"statusCode": 200, "body": "no subscribers"}

    text = f"\U0001f48a Time to give {dog_name} his {med['name']} ({med['dose']})!"
    sent = telegram.broadcast(chat_ids, text, reply_markup=telegram.DONE_BUTTON)
    if sent:
        dynamo.save_sent_messages(key, sent)

    logger.info("Notified %d subscribers for %s", len(chat_ids), key)
    return {"statusCode": 200, "body": f"notified {len(chat_ids)} subscribers"}
