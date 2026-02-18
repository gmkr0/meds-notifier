from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from shared import dynamo


class TestNotifierHandler:
    def test_happy_path(self, aws):
        """Notifier sends messages to all subscribers."""
        dynamo.add_subscriber(111, "Alice")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
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
