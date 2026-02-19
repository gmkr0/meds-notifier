from unittest.mock import patch, call
from datetime import date, timedelta

from shared import dynamo, telegram


class TestReminderHandler:
    def test_pending_edits_old_and_sends_new(self, aws):
        """Reminder removes buttons from old messages and sends new reminder to all."""
        dynamo.add_subscriber(222, "Bob")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)
        dynamo.save_sent_messages(key, {222: 50})

        with patch("shared.telegram.edit_message_reply_markup") as mock_edit, \
             patch("shared.telegram.send_message") as mock_send:
            mock_edit.return_value = True
            mock_send.return_value = 70
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "1 pending" in result["body"]
        # Old message had button removed
        mock_edit.assert_called_once_with(222, 50, reply_markup=telegram.NO_BUTTONS)
        # New reminder sent to subscriber
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 222
        assert "still pending" in mock_send.call_args[0][1]
        # New message ID accumulated alongside old one
        sent = dynamo.get_sent_messages(key)
        assert sent[222] == [50, 70]

    def test_multiple_subscribers_all_get_new_message(self, aws):
        """Both old and new subscribers get new reminder messages."""
        dynamo.add_subscriber(222, "Bob")
        dynamo.add_subscriber(333, "Carol")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)
        # Only Bob has an existing tracked message
        dynamo.save_sent_messages(key, {222: 50})

        with patch("shared.telegram.edit_message_reply_markup") as mock_edit, \
             patch("shared.telegram.send_message") as mock_send:
            mock_edit.return_value = True
            mock_send.side_effect = [60, 61]
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        # Only Bob's old message had button removed
        mock_edit.assert_called_once_with(222, 50, reply_markup=telegram.NO_BUTTONS)
        # Both subscribers got new messages
        assert mock_send.call_count == 2
        sent = dynamo.get_sent_messages(key)
        assert sent[222] == [50, 60]
        assert sent[333] == [61]

    def test_no_sent_messages_sends_to_all(self, aws):
        """Reminder sends to all when no previous messages exist (no edit needed)."""
        dynamo.add_subscriber(222, "Bob")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)

        with patch("shared.telegram.edit_message_reply_markup") as mock_edit, \
             patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = 70
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        mock_edit.assert_not_called()
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 222

    def test_already_confirmed_no_reminder(self, aws):
        """Reminder is a no-op when already confirmed."""
        key = dynamo.build_schedule_key(23)
        dynamo.put_pending_confirmation(key)
        dynamo.mark_confirmed(key, 222)

        with patch("shared.telegram.send_message") as mock_send, \
             patch("shared.telegram.edit_message_reply_markup") as mock_edit:
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "nothing pending" in result["body"]
        mock_send.assert_not_called()
        mock_edit.assert_not_called()

    def test_no_record_skips(self, aws):
        """Reminder skips when there's no confirmation record at all."""
        with patch("shared.telegram.send_message") as mock_send:
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "nothing pending" in result["body"]
        mock_send.assert_not_called()

    def test_multiple_pending_doses(self, aws):
        """Reminder handles each pending dose separately."""
        dynamo.add_subscriber(333, "Carol")
        key1 = dynamo.build_schedule_key(11)
        key2 = dynamo.build_schedule_key(23)
        dynamo.put_pending_confirmation(key1)
        dynamo.put_pending_confirmation(key2)
        dynamo.save_sent_messages(key1, {333: 50})
        dynamo.save_sent_messages(key2, {333: 51})

        with patch("shared.telegram.edit_message_reply_markup") as mock_edit, \
             patch("shared.telegram.send_message") as mock_send:
            mock_edit.return_value = True
            mock_send.return_value = 70
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "2 pending" in result["body"]
        # Two old messages had buttons removed
        assert mock_edit.call_count == 2
        # Two new reminder messages sent (one per pending key)
        assert mock_send.call_count == 2

    def test_yesterday_pending_still_reminds(self, aws):
        """Reminder catches unconfirmed records from yesterday."""
        dynamo.add_subscriber(444, "Dave")
        yesterday = date.today() - timedelta(days=1)
        key = dynamo.build_schedule_key(23, yesterday)
        dynamo.put_pending_confirmation(key)
        dynamo.save_sent_messages(key, {444: 80})

        with patch("shared.telegram.edit_message_reply_markup") as mock_edit, \
             patch("shared.telegram.send_message") as mock_send:
            mock_edit.return_value = True
            mock_send.return_value = 90
            from src.reminder.handler import lambda_handler

            result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "1 pending" in result["body"]
        # Old message button removed
        mock_edit.assert_called_once()
        # New reminder sent
        mock_send.assert_called_once()
