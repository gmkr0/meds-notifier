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


def _history_table():
    return os.environ["TABLE_HISTORY"]


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
            "scheduled_at": {"N": str(int(time.time()))},
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

class PendingConfirmation:
    def __init__(self, schedule_key, scheduled_at):
        self.schedule_key = schedule_key
        self.scheduled_at = scheduled_at

def get_pending_confirmations() -> list[PendingConfirmation]:
    """Scan for all unconfirmed records. Returns list of schedule_key strings."""
    resp = _get_client().scan(
        TableName=_confirmations_table(),
        FilterExpression="confirmed = :f",
        ExpressionAttributeValues={":f": {"BOOL": False}},
    )
    return [PendingConfirmation(item["schedule_key"]["S"], int(item["scheduled_at"]["N"])) for item in resp.get("Items", [])]


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


# =============================================================================
# Administration history (permanent, no TTL)
# =============================================================================
#
# PK: dog_name (S), SK: schedule_key (S, "YYYY-MM-DD_HH" — sorts chronologically).
# One item per scheduled dose. Written as "pending" by the notifier and updated
# to "given" when a subscriber confirms.

HISTORY_PENDING = "pending"
HISTORY_GIVEN = "given"


def record_scheduled_dose(dog_name, schedule_key, medications, scheduled_at=None):
    """Create a history record for a dose that was just scheduled/announced.

    `medications` is a list of {"name", "dose"} dicts, snapshotted so later
    config changes do not rewrite past history.
    """
    if scheduled_at is None:
        scheduled_at = int(time.time())
    _get_client().put_item(
        TableName=_history_table(),
        Item={
            "dog_name": {"S": dog_name},
            "schedule_key": {"S": schedule_key},
            "status": {"S": HISTORY_PENDING},
            "scheduled_at": {"N": str(int(scheduled_at))},
            "medications": {
                "L": [
                    {"M": {"name": {"S": m["name"]}, "dose": {"S": m["dose"]}}}
                    for m in medications
                ]
            },
        },
    )


def record_administration(dog_name, schedule_key, chat_id, name, past_due,
                          medications=None, scheduled_at=None):
    """Mark a dose as given in the history table.

    Uses update_item so it also works when the notifier record is missing
    (e.g. a dose created before the history table existed).
    """
    now = int(time.time())
    expr = (
        "SET #st = :st, confirmed_by = :cb, confirmed_by_name = :cbn, "
        "confirmed_at = :ca, past_due = :pd"
    )
    names = {"#st": "status"}
    values = {
        ":st": {"S": HISTORY_GIVEN},
        ":cb": {"N": str(chat_id)},
        ":cbn": {"S": name},
        ":ca": {"N": str(now)},
        ":pd": {"BOOL": bool(past_due)},
    }
    if scheduled_at is not None:
        expr += ", scheduled_at = if_not_exists(scheduled_at, :sa)"
        values[":sa"] = {"N": str(int(scheduled_at))}
    if medications:
        expr += ", medications = if_not_exists(medications, :meds)"
        values[":meds"] = {
            "L": [
                {"M": {"name": {"S": m["name"]}, "dose": {"S": m["dose"]}}}
                for m in medications
            ]
        }
    _get_client().update_item(
        TableName=_history_table(),
        Key={"dog_name": {"S": dog_name}, "schedule_key": {"S": schedule_key}},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def _parse_history_item(item):
    meds = [
        {"name": m["M"]["name"]["S"], "dose": m["M"]["dose"]["S"]}
        for m in item.get("medications", {}).get("L", [])
    ]
    return {
        "dog_name": item["dog_name"]["S"],
        "schedule_key": item["schedule_key"]["S"],
        "status": item.get("status", {}).get("S", HISTORY_PENDING),
        "scheduled_at": int(item["scheduled_at"]["N"]) if "scheduled_at" in item else None,
        "confirmed_at": int(item["confirmed_at"]["N"]) if "confirmed_at" in item else None,
        "confirmed_by": int(item["confirmed_by"]["N"]) if "confirmed_by" in item else None,
        "confirmed_by_name": item.get("confirmed_by_name", {}).get("S"),
        "past_due": item.get("past_due", {}).get("BOOL", False),
        "medications": meds,
    }


def get_history(dog_name, limit=10, start=None, end=None):
    """Return the most recent dose records for a dog, newest first.

    `start` / `end` are optional schedule_key prefixes (e.g. "2026-10" or
    "2026-10-15") used as an inclusive range on the sort key.
    """
    kwargs = {
        "TableName": _history_table(),
        "ScanIndexForward": False,
        "Limit": limit,
        "ExpressionAttributeValues": {":dog": {"S": dog_name}},
    }
    cond = "dog_name = :dog"
    if start and end:
        cond += " AND schedule_key BETWEEN :start AND :end"
        kwargs["ExpressionAttributeValues"][":start"] = {"S": start}
        kwargs["ExpressionAttributeValues"][":end"] = {"S": end + "~"}
    elif start:
        cond += " AND schedule_key >= :start"
        kwargs["ExpressionAttributeValues"][":start"] = {"S": start}
    elif end:
        cond += " AND schedule_key <= :end"
        kwargs["ExpressionAttributeValues"][":end"] = {"S": end + "~"}
    kwargs["KeyConditionExpression"] = cond

    resp = _get_client().query(**kwargs)
    return [_parse_history_item(i) for i in resp.get("Items", [])]
