from unittest.mock import patch
from datetime import date, timedelta

from shared import dynamo


class TestReminderHandler:
    def test_pending_confirmation_sends_reminder(self, aws):
        """Reminder sends alert when a confirmation is pending."""
        dynamo.add_subscriber(222, "Bob")
        key = dynamo.build_schedule_key("morning")
        dynamo.put_pending_confirmation(key)

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "1 pending" in result["body"]
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert "not been confirmed" in msg

    def test_already_confirmed_no_reminder(self, aws):
        """Reminder is a no-op when already confirmed."""
        key = dynamo.build_schedule_key("evening")
        dynamo.put_pending_confirmation(key)
        dynamo.mark_confirmed(key, 222)

        with patch("shared.telegram.send_message") as mock_send:
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "nothing pending" in result["body"]
        mock_send.assert_not_called()

    def test_no_record_skips(self, aws):
        """Reminder skips when there's no confirmation record at all."""
        with patch("shared.telegram.send_message") as mock_send:
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "nothing pending" in result["body"]
        mock_send.assert_not_called()

    def test_multiple_pending_windows(self, aws):
        """Reminder sends for each pending window."""
        dynamo.add_subscriber(333, "Carol")
        morning_key = dynamo.build_schedule_key("morning")
        evening_key = dynamo.build_schedule_key("evening")
        dynamo.put_pending_confirmation(morning_key)
        dynamo.put_pending_confirmation(evening_key)

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "2 pending" in result["body"]
        assert mock_send.call_count == 2

    def test_yesterday_pending_still_reminds(self, aws):
        """Reminder catches unconfirmed records from yesterday."""
        dynamo.add_subscriber(444, "Dave")
        yesterday = date.today() - timedelta(days=1)
        key = dynamo.build_schedule_key("evening", yesterday)
        dynamo.put_pending_confirmation(key)

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "1 pending" in result["body"]
        mock_send.assert_called_once()
