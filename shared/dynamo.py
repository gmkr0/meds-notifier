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
    resp = _get_client().scan(TableName=_subscribers_table())
    return resp.get("Items", [])


def add_subscriber(chat_id, name):
    """Add a subscriber to the subscribers table."""
    _get_client().put_item(
        TableName=_subscribers_table(),
        Item={
            "chat_id": {"N": str(chat_id)},
            "name": {"S": name},
            "subscribed_at": {"N": str(int(time.time()))},
        },
    )


def remove_subscriber(chat_id):
    """Remove a subscriber from the subscribers table."""
    _get_client().delete_item(
        TableName=_subscribers_table(),
        Key={"chat_id": {"N": str(chat_id)}},
    )
