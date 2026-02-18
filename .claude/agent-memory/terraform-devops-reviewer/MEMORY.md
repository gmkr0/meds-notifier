# Terraform DevOps Reviewer — Project Memory

## Project Identity
- **Project**: med-notifier — serverless Telegram bot for dog medication reminders
- **Stack**: 3 Lambda (Python 3.12) + 2 DynamoDB + 4 EventBridge schedules + API Gateway v2 HTTP + SSM
- **Infra root**: `C:\work\meds-notifier\infra\`
- **Modules**: `infra/modules/lambda/` and `infra/modules/dynamodb/`

## Confirmed Good Patterns
- API Gateway v2 HTTP (not REST) — correct and cheaper choice
- DynamoDB PAY_PER_REQUEST on both tables — correct for sporadic workload
- TTL enabled on confirmations table — correct
- Least-privilege IAM: logging policy scoped to specific log group ARN
- SSM SecureString for bot token, never hardcoded
- CloudWatch log groups with 14-day retention (not infinite)
- Lambda at 128 MB — correct floor for this workload
- `sensitive = true` on `telegram_bot_token` variable

## Known Issues Found (First Review — 2026-02-18)
See `review-findings.md` for full detail. Summary:

1. **CRITICAL bug**: reminder schedule cron string manipulation via `replace()` is fragile and breaks
   when `reminder_delay_minutes` >= 10 (produces `cron(150 8 ...)` instead of `cron(15 0 8 ...)`)
   — the `replace("cron(0", ...)` pattern assumes the minute field is always `0`.
2. **Duplicate tags**: SSM param and API Gateway resources define inline tags that duplicate
   the provider-level `default_tags` block — results in tag conflicts on plan.
3. **Simplicity**: dynamodb module wraps exactly 2 resources with 2 variables — candidates for inlining.
4. **Simplicity**: `role_arn` and `role_name` outputs from lambda module are unused in root module.
5. **Correctness**: `ssm:GetParameter` without `WithDecryption` — reading a SecureString requires
   `ssm:GetParametersByPath` or at minimum the `kms:Decrypt` permission on the CMK (if using
   customer-managed key). For AWS-managed key the GetParameter call works but confirm at runtime.
6. **Outputs**: `api_gateway_id` output exists but appears unused externally — minor noise.

## Naming Convention
- Resources: `${project_name}-${function_name}-${environment}` (e.g., `med-notifier-notifier-prod`)
- Local prefix: `${var.project_name}-${var.environment}`
- SSM path: `/${project_name}/${environment}/telegram-bot-token`

## Module Notes
- Lambda module creates: IAM role, inline logging policy, policy attachments (count), CW log group, Lambda function
- All 3 Lambdas share one IAM policy (`lambda_shared`) covering both DynamoDB tables + SSM param
- Lambda module variables `handler`, `runtime`, `memory_size` have sensible defaults; only `source_path` and `function_name` are required without defaults
