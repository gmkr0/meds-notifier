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
│       └── lambda/
│           ├── main.tf
│           ├── variables.tf
│           └── outputs.tf
├── src/
│   ├── config.json
│   ├── notifier/
│   │   └── handler.py
│   ├── reminder/
│   │   └── handler.py
│   └── webhook/
│       └── handler.py
├── shared/
│   ├── dynamo.py          # DynamoDB helper functions
│   └── telegram.py        # Telegram API helper (sendMessage, broadcast, callback)
├── tests/
│   ├── conftest.py        # Pytest fixtures (moto mocks, env setup)
│   ├── test_notifier.py
│   ├── test_reminder.py
│   └── test_webhook.py
├── justfile
├── pytest.ini
└── requirements-dev.txt
```

## Architecture

### Lambda Functions

1. **lambda_notifier** — triggered by EventBridge cron schedule
   - Reads medication config from `src/config.json` (path via `CONFIG_PATH` env var)
   - Determines current hour (in configured timezone) to build confirmation key
   - Writes a pending confirmation record to DynamoDB with 24h TTL
   - Sends message with inline "Done" button to all subscribers

2. **lambda_reminder** — triggered by EventBridge cron (1 minute offset, every N minutes)
   - If any pending → broadcasts reminder to all subscribers
   - If all confirmed → no-op

3. **lambda_webhook** — API Gateway v2 POST endpoint (Telegram webhook)
   - Validates `X-Telegram-Bot-Api-Secret-Token` header against `WEBHOOK_SECRET` env var
   - `/start` → subscribes user and sends welcome message with command list
   - `/done` or `/administered` → scans DynamoDB for all pending confirmations, marks all as done, broadcasts to all
   - `/subscribe` → adds chat_id to `med_tracker_subscribers`
   - `/unsubscribe` → removes chat_id from subscribers
   - Inline button callback (`data="done"`) → same as `/done`, with callback acknowledgement

### DynamoDB Tables

**med_tracker_confirmations**
| PK (schedule_key) | confirmed | confirmed_by | confirmed_at | ttl |
|--------------------------|-----------|-------------|-------------|-------|
| `2024-01-15_11` | true | chat_id | timestamp | +24h |

**med_tracker_subscribers**
| PK (chat_id) | name | subscribed_at |
|---------------|------|---------------|
| 123456789 | John | timestamp |

### Schedule Key Format

`YYYY-MM-DD_HH` — date + hour scoped so confirmations reset per dose.

## Config File (src/config.json)

```json
{
  "dog_name": "Shelsi",
  "medication": {
    "name": "Phenobarbital",
    "dose": "64.8 mg"
  },
  "timezone": "America/New_York"
}
```

## Terraform Resources

- `aws_lambda_function` × 3 (notifier, reminder, webhook) via `infra/modules/lambda/`
- `random_password` for webhook secret (auto-generated, passed to webhook Lambda)
- `aws_iam_role` + shared policy for Lambda (DynamoDB read/write, SSM read, CloudWatch Logs)
- `aws_dynamodb_table` × 2 (confirmations with TTL, subscribers)
- `aws_scheduler_schedule` × 2 (notifier cron, reminder cron with 1-min offset)
- `aws_apigatewayv2_api` + integration + route (`POST /webhook`) with auto-deploy stage + throttling
- `aws_ssm_parameter` for Telegram bot token (SecureString)
- `aws_cloudwatch_log_group` × 3 (14-day retention)

### Terraform Variables

| Variable                    | Description                     | Default                 |
| --------------------------- | ------------------------------- | ----------------------- |
| `notifier_schedule_cron`    | Notifier cron schedule          | `cron(0 11,23 * * ? *)` |
| `schedule_timezone`         | IANA timezone for all schedules | `America/New_York`      |
| `reminder_interval_minutes` | Reminder rate interval          | `15`                    |
| `aws_region`                | AWS region                      | `us-east-1`             |
| `environment`               | Deployment environment          | `prod`                  |
| `project_name`              | Project name prefix             | `med-notifier`          |
| `telegram_bot_token`        | Telegram bot token (sensitive)  | —                       |
| `aws_access_key`            | AWS access key (sensitive)      | —                       |
| `aws_secret_key`            | AWS secret key (sensitive)      | —                       |

## Implementation Rules

- Each Lambda ZIP includes its `handler.py` + the `shared/` directory; notifier and reminder also include `config.json`
- Use `boto3` for DynamoDB and SSM (available in Lambda runtime, no layer needed)
- Use `urllib.request` for Telegram API calls — no external dependencies
- Bot token resolved at runtime: checks `BOT_TOKEN` env var first, falls back to SSM
- Webhook secret validated via Telegram's `X-Telegram-Bot-Api-Secret-Token` header
- All sensitive Terraform variables marked `sensitive = true`

## Commands

```bash
just install            # Install dev dependencies (pytest, moto, boto3)
just test               # Run unit tests
just package            # ZIP Lambda functions for deployment
just deploy             # Package + terraform init + apply
just destroy            # Terraform destroy
just register-webhook   # Register Telegram webhook URL + secret with bot API
```

## Testing

- Tests use `pytest` with `moto` for mocking AWS services and `unittest.mock` for Telegram API calls
- Shared fixtures in `tests/conftest.py`: mocked DynamoDB tables, SSM parameter, env vars
- Module-level caches in `shared/` are reset between tests via fixture
- Run with `just test`

## Conventions

- Python code follows standard Python style (PEP 8)
- Terraform uses module-based organization under `infra/modules/`
- Environment variables passed to Lambdas: `TABLE_CONFIRMATIONS`, `TABLE_SUBSCRIBERS`, `SSM_BOT_TOKEN_PARAM`, `CONFIG_PATH`, `ENVIRONMENT`, `WEBHOOK_SECRET` (webhook only)
- Lambda handler entry points: `handler.lambda_handler(event, context)`
- DynamoDB client and SSM client are lazy-initialized and cached at module level
