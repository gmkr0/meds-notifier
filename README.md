# Dog Medication Reminder Bot

Serverless Telegram bot that sends medication reminders on a schedule, tracks confirmations, and sends follow-ups if doses are missed. Built on AWS with Terraform.

## Prerequisites

- Python 3.12+
- Terraform 1.0+
- [just](https://github.com/casey/just) command runner
- AWS account with access credentials
- Telegram bot token (from [@BotFather](https://t.me/BotFather))

## Setup

### 1. Install dev dependencies

```bash
just install
```

### 2. Configure medication

Edit `src/config.json` with your dog's name, medication, dose, notification hours, and timezone.

### 3. Run tests

```bash
just test
```

### 4. Deploy

Create a `.env` file with your credentials:

```
BOT_TOKEN=your-telegram-bot-token
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

Then deploy:

```bash
just deploy
```

### 5. Register Telegram webhook

```bash
just register-webhook
```

This registers the API Gateway URL and webhook secret with Telegram.

## Usage

Once deployed, interact with the bot on Telegram:

- `/start` — Subscribe and see available commands
- `/done` — Confirm medication was given
- `/subscribe` — Subscribe to notifications
- `/unsubscribe` — Stop receiving notifications

The bot sends reminders at the configured notification hours and follows up every 15 minutes until the dose is confirmed.
