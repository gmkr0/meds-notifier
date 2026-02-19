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
    dog_name = CONFIG["dog_name"]
    med = CONFIG["medication"]
    pending = dynamo.get_pending_confirmations()

    if not pending:
        logger.info("No pending confirmations — nothing to remind")
        return {"statusCode": 200, "body": "nothing pending"}

    subscribers = dynamo.get_all_subscribers()
    chat_ids = [int(s["chat_id"]["N"]) for s in subscribers]

    if not chat_ids:
        logger.warning("No subscribers for reminder")
        return {"statusCode": 200, "body": "no subscribers"}

    for key in pending:
        text = (
            f"\u26a0\ufe0f Reminder: {dog_name}'s {med['name']} ({med['dose']}) "
            f"still pending!"
        )

        # Remove buttons from the latest tracked messages
        sent_messages = dynamo.get_sent_messages(key)
        if sent_messages:
            latest = {cid: mids[-1] for cid, mids in sent_messages.items()}
            telegram.edit_broadcast_reply_markup(
                latest, reply_markup=telegram.NO_BUTTONS
            )

        # Send new reminder to ALL subscribers
        new_sent = telegram.broadcast(
            chat_ids, text, reply_markup=telegram.DONE_BUTTON
        )
        if new_sent:
            dynamo.save_sent_messages(key, new_sent)

        logger.info("Sent reminder to %d subscribers for %s", len(chat_ids), key)

    return {"statusCode": 200, "body": f"reminded for {len(pending)} pending dose(s)"}
