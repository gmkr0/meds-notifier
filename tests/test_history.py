import json
import os
from unittest.mock import patch

from shared import dynamo

VALID_SECRET_HEADERS = {"x-telegram-bot-api-secret-token": os.environ["WEBHOOK_SECRET"]}
MEDS = [
    {"name": "Phenobarbital", "dose": "145.8 mg"},
    {"name": "Levetiracetam", "dose": "2250 mg"},
]


def _make_event(chat_id, text, first_name="Test", last_name="User"):
    return {
        "headers": VALID_SECRET_HEADERS,
        "body": json.dumps(
            {
                "message": {
                    "chat": {"id": chat_id},
                    "text": text,
                    "from": {"first_name": first_name, "last_name": last_name},
                }
            }
        ),
    }


class TestHistoryDynamo:
    def test_scheduled_then_given(self, aws):
        """Notifier record is created pending, confirmation flips it to given."""
        dynamo.record_scheduled_dose("Shelsi", "2026-10-30_11", MEDS, scheduled_at=1000)
        [entry] = dynamo.get_history("Shelsi")
        assert entry["status"] == dynamo.HISTORY_PENDING
        assert entry["medications"] == MEDS
        assert entry["scheduled_at"] == 1000

        dynamo.record_administration("Shelsi", "2026-10-30_11", 111, "Test User", past_due=True)
        [entry] = dynamo.get_history("Shelsi")
        assert entry["status"] == dynamo.HISTORY_GIVEN
        assert entry["confirmed_by"] == 111
        assert entry["confirmed_by_name"] == "Test User"
        assert entry["past_due"] is True
        assert entry["confirmed_at"] is not None
        # Snapshot from the notifier is preserved
        assert entry["medications"] == MEDS
        assert entry["scheduled_at"] == 1000

    def test_given_without_prior_record(self, aws):
        """Confirming a dose with no notifier record still writes history."""
        dynamo.record_administration(
            "Shelsi", "2026-10-30_23", 222, "Other", past_due=False,
            medications=MEDS, scheduled_at=500,
        )
        [entry] = dynamo.get_history("Shelsi")
        assert entry["status"] == dynamo.HISTORY_GIVEN
        assert entry["medications"] == MEDS
        assert entry["scheduled_at"] == 500

    def test_newest_first_and_limit(self, aws):
        for key in ["2026-10-28_11", "2026-10-28_23", "2026-10-29_11", "2026-10-29_23"]:
            dynamo.record_scheduled_dose("Shelsi", key, MEDS)
        entries = dynamo.get_history("Shelsi", limit=3)
        assert [e["schedule_key"] for e in entries] == [
            "2026-10-29_23", "2026-10-29_11", "2026-10-28_23",
        ]

    def test_range_filter(self, aws):
        for key in ["2026-09-30_23", "2026-10-01_11", "2026-10-31_23", "2026-11-01_11"]:
            dynamo.record_scheduled_dose("Shelsi", key, MEDS)
        entries = dynamo.get_history("Shelsi", limit=50, start="2026-10", end="2026-10")
        assert [e["schedule_key"] for e in entries] == ["2026-10-31_23", "2026-10-01_11"]

    def test_other_dog_not_returned(self, aws):
        dynamo.record_scheduled_dose("Shelsi", "2026-10-30_11", MEDS)
        dynamo.record_scheduled_dose("Rex", "2026-10-30_11", MEDS)
        assert len(dynamo.get_history("Shelsi")) == 1


class TestHistoryViaWebhook:
    def test_done_writes_history(self, aws):
        """'/done' records the administration in the history table."""
        dynamo.add_subscriber(111, "Test User")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)

        with patch("shared.telegram.send_message") as mock_send, \
             patch("shared.telegram.delete_message"):
            mock_send.return_value = 99
            from src.webhook.handler import lambda_handler, CONFIG

            lambda_handler(_make_event(111, "/done"), None)

        [entry] = dynamo.get_history(CONFIG["dog_name"])
        assert entry["schedule_key"] == key
        assert entry["status"] == dynamo.HISTORY_GIVEN
        assert entry["confirmed_by"] == 111
        assert entry["confirmed_by_name"] == "Test User"
        assert entry["past_due"] is False
        assert entry["medications"] == CONFIG["medications"]

    def test_history_command_lists_doses(self, aws):
        from src.webhook.handler import CONFIG
        dog = CONFIG["dog_name"]
        dynamo.record_scheduled_dose(dog, "2026-10-29_11", MEDS, scheduled_at=1000)
        dynamo.record_administration(dog, "2026-10-29_11", 111, "Alice", past_due=False)
        dynamo.record_scheduled_dose(dog, "2026-10-29_23", MEDS, scheduled_at=1000)
        dynamo.record_administration(dog, "2026-10-29_23", 222, "Bob", past_due=True)
        # Old pending record -> missed
        dynamo.record_scheduled_dose(dog, "2026-10-28_11", MEDS, scheduled_at=1000)
        # Fresh pending record -> pending
        dynamo.record_scheduled_dose(dog, "2026-10-30_11", MEDS)

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = 99
            from src.webhook.handler import lambda_handler

            result = lambda_handler(_make_event(111, "/history"), None)

        assert result["statusCode"] == 200
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        lines = msg.splitlines()
        assert "Last 4 dose(s)" in lines[0]
        body = lines[2:]
        # Newest first
        assert "Oct 30 11:00" in body[0] and "pending" in body[0]
        assert "Oct 29 23:00" in body[1] and "by Bob" in body[1] and "⚠️" in body[1]
        assert "Oct 29 11:00" in body[2] and "by Alice" in body[2] and "✅" in body[2]
        assert "Oct 28 11:00" in body[3] and "missed" in body[3]

    def test_history_command_with_limit(self, aws):
        from src.webhook.handler import CONFIG
        dog = CONFIG["dog_name"]
        for key in ["2026-10-28_11", "2026-10-28_23", "2026-10-29_11"]:
            dynamo.record_scheduled_dose(dog, key, MEDS)

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = 99
            from src.webhook.handler import lambda_handler

            lambda_handler(_make_event(111, "/history 2"), None)

        msg = mock_send.call_args[0][1]
        assert "Last 2 dose(s)" in msg
        assert "Oct 28 11:00" not in msg

    def test_history_command_empty(self, aws):
        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = 99
            from src.webhook.handler import lambda_handler

            lambda_handler(_make_event(111, "/history"), None)

        assert "No medication history" in mock_send.call_args[0][1]


class TestHistoryViaNotifier:
    def test_notifier_records_scheduled_dose(self, aws):
        dynamo.add_subscriber(111, "Test User")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = 99
            from src.notifier.handler import lambda_handler, CONFIG

            lambda_handler({}, None)

        [entry] = dynamo.get_history(CONFIG["dog_name"])
        assert entry["status"] == dynamo.HISTORY_PENDING
        assert entry["medications"] == CONFIG["medications"]
        assert dynamo.get_confirmation(entry["schedule_key"]) is not None
