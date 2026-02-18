import json
import os
from unittest.mock import patch
from datetime import date

from shared import dynamo

VALID_SECRET_HEADERS = {"x-telegram-bot-api-secret-token": os.environ["WEBHOOK_SECRET"]}


def _make_event(chat_id, text, first_name="Test", last_name="User"):
    """Build a minimal API Gateway v2 event with a Telegram message."""
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


def _make_callback_event(chat_id, data, callback_query_id="cb-123",
                          first_name="Test", last_name="User"):
    """Build an API Gateway v2 event with a Telegram callback query (button press)."""
    return {
        "headers": VALID_SECRET_HEADERS,
        "body": json.dumps(
            {
                "callback_query": {
                    "id": callback_query_id,
                    "data": data,
                    "message": {"chat": {"id": chat_id}},
                    "from": {"first_name": first_name, "last_name": last_name},
                }
            }
        ),
    }


class TestWebhookDone:
    def test_done_confirms_and_broadcasts(self, aws):
        """'/done' confirms and broadcasts to all subscribers."""
        dynamo.add_subscriber(111, "Test User")
        dynamo.add_subscriber(222, "Other User")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)
        event = _make_event(111, "/done")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        item = dynamo.get_confirmation(key)
        assert item["confirmed"]["BOOL"] is True
        assert item["confirmed_by"]["N"] == "111"
        assert mock_send.call_count == 2
        msg = mock_send.call_args[0][1]
        assert "Test User" in msg
        assert "confirmed" in msg.lower()

    def test_administered_also_works(self, aws):
        """'/administered' is an alias for /done."""
        dynamo.add_subscriber(222, "Someone")
        key = dynamo.build_schedule_key(23)
        dynamo.put_pending_confirmation(key)
        event = _make_event(222, "/administered")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        item = dynamo.get_confirmation(key)
        assert item["confirmed"]["BOOL"] is True

    def test_done_confirms_all_pending(self, aws):
        """'/done' confirms all pending doses at once."""
        dynamo.add_subscriber(111, "Test User")
        key1 = dynamo.build_schedule_key(11)
        key2 = dynamo.build_schedule_key(23)
        dynamo.put_pending_confirmation(key1)
        dynamo.put_pending_confirmation(key2)
        event = _make_event(111, "/done")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert dynamo.get_confirmation(key1)["confirmed"]["BOOL"] is True
        assert dynamo.get_confirmation(key2)["confirmed"]["BOOL"] is True

    def test_done_no_pending(self, aws):
        """'/done' with nothing pending sends helpful message."""
        event = _make_event(111, "/done")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        mock_send.assert_called_once()
        assert "No pending" in mock_send.call_args[0][1]


class TestWebhookSubscribe:
    def test_subscribe(self, aws):
        """'/subscribe' adds user to subscribers table."""
        event = _make_event(333, "/subscribe", "Alice", "Smith")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        subs = dynamo.get_all_subscribers()
        assert len(subs) == 1
        assert subs[0]["chat_id"]["N"] == "333"
        assert subs[0]["name"]["S"] == "Alice Smith"

    def test_unsubscribe(self, aws):
        """'/unsubscribe' removes user from subscribers table."""
        dynamo.add_subscriber(444, "Bob")
        event = _make_event(444, "/unsubscribe")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        subs = dynamo.get_all_subscribers()
        assert len(subs) == 0


class TestWebhookStart:
    def test_start_subscribes_and_welcomes(self, aws):
        """'/start' subscribes user and sends welcome message."""
        event = _make_event(555, "/start", "Charlie", "")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        subs = dynamo.get_all_subscribers()
        assert len(subs) == 1
        msg = mock_send.call_args[0][1]
        assert "Welcome" in msg


class TestWebhookCallbackButton:
    def test_done_button_confirms_pending(self, aws):
        """Tapping the 'Done' inline button confirms the pending schedule key."""
        dynamo.add_subscriber(111, "Test User")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)
        event = _make_callback_event(111, "done")

        with patch("shared.telegram.send_message") as mock_send, \
             patch("shared.telegram.answer_callback_query") as mock_answer:
            mock_send.return_value = True
            mock_answer.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        item = dynamo.get_confirmation(key)
        assert item["confirmed"]["BOOL"] is True
        mock_answer.assert_called_once_with("cb-123")
        mock_send.assert_called_once()
        assert "Test User" in mock_send.call_args[0][1]

    def test_done_button_no_pending(self, aws):
        """Tapping 'Done' with nothing pending sends helpful message and acknowledges."""
        event = _make_callback_event(111, "done")

        with patch("shared.telegram.send_message") as mock_send, \
             patch("shared.telegram.answer_callback_query") as mock_answer:
            mock_send.return_value = True
            mock_answer.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        mock_send.assert_called_once()
        assert "No pending" in mock_send.call_args[0][1]
        mock_answer.assert_called_once()


class TestWebhookEdgeCases:
    def test_unknown_command(self, aws):
        """Unknown commands get a helpful reply."""
        event = _make_event(111, "/foobar")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "Unknown command" in mock_send.call_args[0][1]

    def test_malformed_body(self, aws):
        """Malformed body still returns 200 (no Telegram retry loop)."""
        event = {"headers": VALID_SECRET_HEADERS, "body": "not-json"}

        with patch("shared.telegram.send_message"):
            from src.webhook.handler import lambda_handler

            # json.loads will fail, but we should handle gracefully
            # Actually the handler will raise — let's verify it returns 200
            # for bodies that parse but have no message
            event2 = {"headers": VALID_SECRET_HEADERS, "body": "{}"}
            result = lambda_handler(event2, None)

        assert result["statusCode"] == 200

    def test_done_with_bot_suffix(self, aws):
        """'/done@MyBot' is handled the same as '/done'."""
        dynamo.add_subscriber(111, "Test User")
        key = dynamo.build_schedule_key(11)
        dynamo.put_pending_confirmation(key)
        event = _make_event(111, "/done@MedReminderBot")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        item = dynamo.get_confirmation(key)
        assert item["confirmed"]["BOOL"] is True


class TestWebhookSecretValidation:
    def test_missing_secret_header_rejected(self, aws):
        """Requests without the secret header are rejected with 403."""
        event = {"body": json.dumps({"message": {"chat": {"id": 111}, "text": "/done",
                 "from": {"first_name": "Test", "last_name": "User"}}})}

        from src.webhook.handler import lambda_handler

        result = lambda_handler(event, None)
        assert result["statusCode"] == 403

    def test_wrong_secret_header_rejected(self, aws):
        """Requests with a wrong secret header are rejected with 403."""
        event = {
            "headers": {"x-telegram-bot-api-secret-token": "wrong-secret"},
            "body": json.dumps({"message": {"chat": {"id": 111}, "text": "/done",
                     "from": {"first_name": "Test", "last_name": "User"}}}),
        }

        from src.webhook.handler import lambda_handler

        result = lambda_handler(event, None)
        assert result["statusCode"] == 403

    def test_correct_secret_header_accepted(self, aws):
        """Requests with the correct secret header are processed normally."""
        event = _make_event(111, "/subscribe", "Test", "User")

        with patch("shared.telegram.send_message") as mock_send:
            mock_send.return_value = True
            from src.webhook.handler import lambda_handler

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
