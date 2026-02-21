from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from shared import dynamo


class TestNotifierHandler:
    def test_happy_path(self, aws):
        """Notifier sends messages to all subscribers and saves message IDs."""
        dynamo.add_subscriber(111, "Alice")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = 42
            from src.notifier.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "1" in result["body"]
        mock_send.assert_called()

        # Verify pending confirmation was created with hour-based key
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        key = dynamo.build_schedule_key(now.hour, now.date())
        item = dynamo.get_confirmation(key)
        assert item is not None
        assert item["confirmed"]["BOOL"] is False
        assert item["scheduled_at"]["N"] is not None

        # Verify sent_messages were saved
        sent = dynamo.get_sent_messages(key)
        assert sent == {111: [42]}

    def test_no_subscribers(self, aws):
        """Notifier creates confirmation but reports no subscribers."""
        with patch("shared.telegram.send_message") as mock_send:
            from src.notifier.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "no subscribers" in result["body"]
        mock_send.assert_not_called()

        # Confirmation should still be created
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        key = dynamo.build_schedule_key(now.hour, now.date())
        item = dynamo.get_confirmation(key)
        assert item is not None

    def test_multiple_subscribers(self, aws):
        """Notifier saves message IDs for all subscribers."""
        dynamo.add_subscriber(111, "Alice")
        dynamo.add_subscriber(222, "Bob")

        call_count = 0

        def mock_send_side_effect(chat_id, text, reply_markup=None):
            nonlocal call_count
            call_count += 1
            return 100 + call_count

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.side_effect = mock_send_side_effect
            from src.notifier.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200

        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        key = dynamo.build_schedule_key(now.hour, now.date())
        sent = dynamo.get_sent_messages(key)
        assert len(sent) == 2
        assert 111 in sent
        assert 222 in sent
