import json
from unittest.mock import patch, MagicMock
from datetime import date

from shared import dynamo


class TestNotifierHandler:
    def test_happy_path(self, aws):
        """Notifier sends messages to all subscribers for matching meds."""
        # Add a subscriber
        dynamo.add_subscriber(111, "Alice")

        event = {"schedule_key": "morning"}

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.notifier.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "1" in result["body"]
        mock_send.assert_called()

        # Verify pending confirmation was created
        key = dynamo.build_schedule_key("morning")
        item = dynamo.get_confirmation(key)
        assert item is not None
        assert item["confirmed"]["BOOL"] is False

    def test_no_meds_for_window(self, aws):
        """Notifier returns early when no medications match the schedule key."""
        event = {"schedule_key": "noon"}

        with patch("shared.telegram.send_message") as mock_send:
            from src.notifier.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "no medications" in result["body"]
        mock_send.assert_not_called()

    def test_no_subscribers(self, aws):
        """Notifier creates confirmation but reports no subscribers."""
        event = {"schedule_key": "morning"}

        with patch("shared.telegram.send_message") as mock_send:
            from src.notifier.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "no subscribers" in result["body"]
        mock_send.assert_not_called()

        # Confirmation should still be created
        key = dynamo.build_schedule_key("morning")
        item = dynamo.get_confirmation(key)
        assert item is not None
