from unittest.mock import patch

from shared import dynamo


class TestReminderHandler:
    def test_pending_confirmation_sends_reminder(self, aws):
        """Reminder sends alert when confirmation is pending."""
        dynamo.add_subscriber(222, "Bob")
        key = dynamo.build_schedule_key("morning")
        dynamo.put_pending_confirmation(key)

        event = {"schedule_key": "morning"}

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.reminder.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "1" in result["body"]
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert "not been confirmed" in msg

    def test_already_confirmed_no_reminder(self, aws):
        """Reminder is a no-op when already confirmed."""
        key = dynamo.build_schedule_key("evening")
        dynamo.put_pending_confirmation(key)
        dynamo.mark_confirmed(key, 222)

        event = {"schedule_key": "evening"}

        with patch("shared.telegram.send_message") as mock_send:
            from src.reminder.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "already confirmed" in result["body"]
        mock_send.assert_not_called()

    def test_no_record_skips(self, aws):
        """Reminder skips when there's no confirmation record at all."""
        event = {"schedule_key": "morning"}

        with patch("shared.telegram.send_message") as mock_send:
            from src.reminder.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "no record" in result["body"]
        mock_send.assert_not_called()
