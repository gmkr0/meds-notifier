terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  prefix = "${var.project_name}-${var.environment}"

  lambda_env_common = {
    TABLE_CONFIRMATIONS  = aws_dynamodb_table.confirmations.name
    TABLE_SUBSCRIBERS    = aws_dynamodb_table.subscribers.name
    SSM_BOT_TOKEN_PARAM  = aws_ssm_parameter.bot_token.name
    ENVIRONMENT          = var.environment
  }
}

# =============================================================================
# Webhook Secret — auto-generated for Telegram secret_token validation
# =============================================================================

resource "random_password" "webhook_secret" {
  length  = 64
  special = false
}

# =============================================================================
# SSM — Telegram Bot Token
# =============================================================================

resource "aws_ssm_parameter" "bot_token" {
  name  = "/${var.project_name}/${var.environment}/telegram-bot-token"
  type  = "SecureString"
  value = var.telegram_bot_token
}

# =============================================================================
# DynamoDB
# =============================================================================

resource "aws_dynamodb_table" "confirmations" {
  name         = "${var.project_name}-confirmations-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "schedule_key"

  attribute {
    name = "schedule_key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "subscribers" {
  name         = "${var.project_name}-subscribers-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "chat_id"

  attribute {
    name = "chat_id"
    type = "N"
  }
}

# =============================================================================
# IAM Policy — shared DynamoDB + SSM access for all Lambdas
# =============================================================================

data "aws_iam_policy_document" "lambda_shared" {
  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.confirmations.arn,
      aws_dynamodb_table.subscribers.arn,
    ]
  }

  statement {
    sid    = "SSMReadToken"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
    ]
    resources = [
      aws_ssm_parameter.bot_token.arn,
    ]
  }
}

resource "aws_iam_policy" "lambda_shared" {
  name   = "${local.prefix}-lambda-shared"
  policy = data.aws_iam_policy_document.lambda_shared.json
}

# =============================================================================
# Lambda — Notifier
# =============================================================================

module "lambda_notifier" {
  source        = "./modules/lambda"
  project_name  = var.project_name
  environment   = var.environment
  function_name = "notifier"
  source_path   = "${path.module}/../dist/notifier.zip"
  timeout       = 30

  environment_variables = local.lambda_env_common

  policy_arns = [aws_iam_policy.lambda_shared.arn]
}

# =============================================================================
# Lambda — Reminder
# =============================================================================

module "lambda_reminder" {
  source        = "./modules/lambda"
  project_name  = var.project_name
  environment   = var.environment
  function_name = "reminder"
  source_path   = "${path.module}/../dist/reminder.zip"
  timeout       = 30

  environment_variables = local.lambda_env_common

  policy_arns = [aws_iam_policy.lambda_shared.arn]
}

# =============================================================================
# Lambda — Webhook
# =============================================================================

module "lambda_webhook" {
  source        = "./modules/lambda"
  project_name  = var.project_name
  environment   = var.environment
  function_name = "webhook"
  source_path   = "${path.module}/../dist/webhook.zip"
  timeout       = 10

  environment_variables = merge(local.lambda_env_common, {
    WEBHOOK_SECRET = random_password.webhook_secret.result
  })

  policy_arns = [aws_iam_policy.lambda_shared.arn]
}

# =============================================================================
# API Gateway v2 (HTTP) — Telegram Webhook
# =============================================================================

resource "aws_apigatewayv2_api" "webhook" {
  name          = "${local.prefix}-webhook-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambda_webhook.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

resource "aws_apigatewayv2_stage" "webhook" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = var.environment
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
}

resource "aws_lambda_permission" "apigw_webhook" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*/*/webhook"
}

# =============================================================================
# EventBridge Scheduler — IAM Role
# =============================================================================

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.prefix}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_invoke" {
  statement {
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      module.lambda_notifier.function_arn,
      module.lambda_reminder.function_arn,
    ]
  }
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name   = "${local.prefix}-scheduler-invoke"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_invoke.json
}

# =============================================================================
# EventBridge Schedules
# =============================================================================

resource "aws_scheduler_schedule" "notifier" {
  name       = "${local.prefix}-notifier"
  group_name = "default"

  schedule_expression          = var.notifier_schedule_cron
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = module.lambda_notifier.function_arn
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({})
  }
}

resource "aws_scheduler_schedule" "reminder" {
  name       = "${local.prefix}-reminder"
  group_name = "default"

  schedule_expression          = "cron(10/${var.reminder_interval_minutes} * * * ? *)"
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = module.lambda_reminder.function_arn
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({})
  }
}

