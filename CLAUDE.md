# Dog Medication Telegram Bot

Serverless Telegram bot on AWS that reminds subscribers to give a dog its medication on a schedule, waits for confirmation, and sends follow-up reminders.

## Tech Stack

- **Infrastructure**: Terraform (AWS provider)
- **Runtime**: Python 3.12 (AWS Lambda)
- **Messaging**: Telegram Bot API (via `urllib.request` — no external deps)
- **State**: DynamoDB (confirmation tracking + subscriber list)
- **Scheduler**: Amazon EventBridge Scheduler
- **Secrets**: AWS SSM Parameter Store (Telegram bot token, SecureString)

## Project Structure

```
.
├── infra/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/
│       ├── lambda/
│       └── dynamodb/
├── src/
│   ├── notifier/
│   │   ├── handler.py
│   │   └── config.json
│   ├── reminder/
│   │   └── handler.py
│   └── webhook/
│       └── handler.py
├── shared/
│   ├── telegram.py      # Telegram API helper (sendMessage, etc.)
│   └── dynamo.py        # DynamoDB helper functions
├── tests/
│   ├── test_notifier.py
│   ├── test_reminder.py
│   └── test_webhook.py
├── Makefile
└── README.md
```

## Architecture

### Lambda Functions

1. **lambda_notifier** — triggered by EventBridge on schedule (morning + evening)
   - Reads medication config from bundled `config.json`
   - Writes a pending confirmation record to DynamoDB (`med_tracker_confirmations`) with 24h TTL
   - Sends message to all subscribers: "💊 Time to give [dog_name] their [medication] [dose]! Reply /done to confirm."

2. **lambda_reminder** — triggered by EventBridge 15 minutes after each notifier
   - Checks DynamoDB for the current schedule window's confirmation status
   - If not confirmed → sends reminder: "⚠️ Reminder: [dog_name]'s [medication] has not been confirmed yet!"
   - If confirmed → no-op

3. **lambda_webhook** — API Gateway POST endpoint (Telegram webhook)
   - `/done` or `/administered` → writes confirmation to DynamoDB for current schedule window
   - `/subscribe` → adds chat_id to `med_tracker_subscribers`
   - `/unsubscribe` → removes chat_id from subscribers

### DynamoDB Tables

**med_tracker_confirmations**
| PK (schedule_key)       | confirmed | confirmed_by | confirmed_at | TTL   |
|--------------------------|-----------|-------------|-------------|-------|
| `2024-01-15_morning`     | true      | chat_id     | timestamp   | +24h  |

**med_tracker_subscribers**
| PK (chat_id) | name | subscribed_at |
|---------------|------|---------------|
| 123456789     | John | timestamp     |

### Schedule Window Key Format

`YYYY-MM-DD_morning` or `YYYY-MM-DD_evening` — date-scoped so confirmations reset daily.

## Config File (src/notifier/config.json)

```json
{
  "dog_name": "Max",
  "medications": [
    {
      "name": "Vetmedin",
      "dose": "5mg",
      "schedule_key": "morning"
    },
    {
      "name": "Vetmedin",
      "dose": "5mg",
      "schedule_key": "evening"
    }
  ],
  "reminder_window_minutes": 15
}
```

## Terraform Resources

- `aws_lambda_function` × 3 (notifier, reminder, webhook)
- `aws_iam_role` + policies for Lambda (DynamoDB read/write, SSM read, CloudWatch Logs)
- `aws_dynamodb_table` × 2 (confirmations, subscribers)
- `aws_scheduler_schedule` × 4 (morning notifier, morning reminder +15min, evening notifier, evening reminder +15min)
- `aws_apigatewayv2_api` + `aws_apigatewayv2_integration` + route for webhook
- `aws_ssm_parameter` for Telegram bot token (SecureString)
- `aws_cloudwatch_log_group` × 3

### Terraform Variables

| Variable                | Description                        | Default              |
|-------------------------|------------------------------------|----------------------|
| `morning_schedule_cron` | Morning schedule                   | `cron(0 8 * * ? *)`  |
| `evening_schedule_cron` | Evening schedule                   | `cron(0 20 * * ? *)` |
| `aws_region`            | AWS region                         | `us-east-1`          |
| `environment`           | Deployment environment             | `prod`               |

## Implementation Rules

- Each Lambda ZIP includes its `handler.py` + the `shared/` directory
- Use `boto3` for DynamoDB and SSM (available in Lambda runtime, no layer needed)
- Use `urllib.request` for Telegram API calls — no external dependencies
- All sensitive values (bot token) come from SSM at runtime, never hardcoded
- Telegram webhook URL registered after API Gateway deploy via `make register-webhook`

## Commands

```bash
make install            # Install dev dependencies (pytest, moto, etc.)
make test               # Run unit tests
make package            # ZIP Lambda functions for deployment
make deploy             # terraform init + apply
make destroy            # terraform destroy
make register-webhook   # Register Telegram webhook URL with bot API
```

## Testing

- Tests use `pytest` with `moto` for mocking AWS services and `unittest.mock` for Telegram API calls
- Test files: `tests/test_notifier.py`, `tests/test_reminder.py`, `tests/test_webhook.py`
- Run with `make test` or `python -m pytest tests/`

## Conventions

- Python code follows standard Python style (PEP 8)
- Terraform uses module-based organization under `infra/modules/`
- Environment variables used to pass config to Lambdas: `TABLE_CONFIRMATIONS`, `TABLE_SUBSCRIBERS`, `SSM_BOT_TOKEN_PARAM`, `SCHEDULE_KEY` (morning/evening)
- Lambda handler entry points: `handler.lambda_handler(event, context)`
