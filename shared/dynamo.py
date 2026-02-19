import os
import time
import logging
from datetime import date

import boto3

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("dynamodb")
    return _client


def _confirmations_table():
    return os.environ["TABLE_CONFIRMATIONS"]


def _subscribers_table():
    return os.environ["TABLE_SUBSCRIBERS"]


def build_schedule_key(hour, d=None):
    """Build a date-scoped key like '2024-01-15_11'."""
    if d is None:
        d = date.today()
    return f"{d.isoformat()}_{hour}"


def put_pending_confirmation(schedule_key):
    """Write an unconfirmed record with 24h TTL."""
    ttl = int(time.time()) + 86400
    _get_client().put_item(
        TableName=_confirmations_table(),
        Item={
            "schedule_key": {"S": schedule_key},
            "confirmed": {"BOOL": False},
            "ttl": {"N": str(ttl)},
        },
    )


def get_confirmation(schedule_key):
    """Fetch confirmation record. Returns item dict or None."""
    resp = _get_client().get_item(
        TableName=_confirmations_table(),
        Key={"schedule_key": {"S": schedule_key}},
    )
    return resp.get("Item")


def mark_confirmed(schedule_key, chat_id):
    """Update a confirmation record to confirmed."""
    _get_client().update_item(
        TableName=_confirmations_table(),
        Key={"schedule_key": {"S": schedule_key}},
        UpdateExpression="SET confirmed = :c, confirmed_by = :cb, confirmed_at = :ca",
        ExpressionAttributeValues={
            ":c": {"BOOL": True},
            ":cb": {"N": str(chat_id)},
            ":ca": {"N": str(int(time.time()))},
        },
    )


def get_pending_confirmations():
    """Scan for all unconfirmed records. Returns list of schedule_key strings."""
    resp = _get_client().scan(
        TableName=_confirmations_table(),
        FilterExpression="confirmed = :f",
        ExpressionAttributeValues={":f": {"BOOL": False}},
    )
    return [item["schedule_key"]["S"] for item in resp.get("Items", [])]


def get_all_subscribers():
    """Scan the subscribers table. Returns list of items."""
    resp = _get_client().scan(
        TableName=_subscribers_table(),
        FilterExpression="is_active = :f",
        ExpressionAttributeValues={":f": {"BOOL": True}},
        )
    return resp.get("Items", [])


def add_subscriber(chat_id, name):
    """Add a subscriber to the subscribers table."""
    _get_client().put_item(
        TableName=_subscribers_table(),
        Item={
            "chat_id": {"N": str(chat_id)},
            "name": {"S": name},
            "subscribed_at": {"N": str(int(time.time()))},
            "is_active": {"BOOL": True},
        },
    )


def remove_subscriber(chat_id):
    """Remove a subscriber from the subscribers table."""
    _get_client().delete_item(
        TableName=_subscribers_table(),
        Key={"chat_id": {"N": str(chat_id)}},
    )


def save_sent_messages(schedule_key, sent_messages):
    """Append sent message IDs to per-chat_id lists on a confirmation record.

    Each chat_id maps to a list of message IDs so that all notifications
    and reminders can be cleaned up on confirmation.
    """
    if not sent_messages:
        return
    _get_client().update_item(
        TableName=_confirmations_table(),
        Key={"schedule_key": {"S": schedule_key}},
        UpdateExpression="SET sent_messages = if_not_exists(sent_messages, :empty)",
        ExpressionAttributeValues={":empty": {"M": {}}},
    )
    for chat_id, msg_id in sent_messages.items():
        cid_str = str(chat_id)
        _get_client().update_item(
            TableName=_confirmations_table(),
            Key={"schedule_key": {"S": schedule_key}},
            UpdateExpression=(
                "SET sent_messages.#cid = "
                "list_append(if_not_exists(sent_messages.#cid, :empty_list), :new_id)"
            ),
            ExpressionAttributeNames={"#cid": cid_str},
            ExpressionAttributeValues={
                ":empty_list": {"L": []},
                ":new_id": {"L": [{"N": str(msg_id)}]},
            },
        )


def get_sent_messages(schedule_key):
    """Return {chat_id (int): [message_id (int), ...]} from the confirmation record."""
    item = get_confirmation(schedule_key)
    if not item or "sent_messages" not in item:
        return {}
    raw = item["sent_messages"]["M"]
    return {
        int(cid): [int(mid["N"]) for mid in msg_list["L"]]
        for cid, msg_list in raw.items()
    }
