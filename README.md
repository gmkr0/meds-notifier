# Dog Medication Reminder Bot

Serverless Telegram bot that sends medication reminders on a schedule, tracks confirmations, and sends follow-ups if doses are missed. Built on AWS with Terraform.

## Prerequisites

- Python 3.12+
- Terraform 1.0+
- AWS account with access credentials
- Telegram bot token (from [@BotFather](https://t.me/BotFather))

## Setup

### 1. Install dev dependencies

```bash
pip install -r requirements-dev.txt
```

### 2. Configure medication

Edit `src/config.json` with your dog's name, medication, and dose.

### 3. Run tests

```bash
python -m pytest tests/
```

### 4. Package Lambda functions

Each Lambda ZIP must include its `handler.py` plus the `shared/` directory. Place the ZIPs at:

```
dist/notifier.zip
dist/reminder.zip
dist/webhook.zip
```

### 5. Deploy infrastructure

```bash
cd infra
terraform init
terraform apply \
  -var="telegram_bot_token=YOUR_BOT_TOKEN" \
  -var="aws_access_key=YOUR_ACCESS_KEY" \
  -var="aws_secret_key=YOUR_SECRET_KEY"
```

### 6. Register Telegram webhook

After deploy, grab the webhook URL from Terraform output and register it:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<WEBHOOK_URL>"
```

## Usage

Once deployed, interact with the bot on Telegram:

- `/start` — Subscribe and see available commands
- `/done` — Confirm medication was given
- `/subscribe` — Subscribe to notifications
- `/unsubscribe` — Stop receiving notifications

The bot sends reminders at the configured morning and evening times, and follows up every 15 minutes until the dose is confirmed.
