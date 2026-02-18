variable "morning_schedule_cron" {
  description = "Cron expression for morning medication notification"
  type        = string
  default     = "cron(0 11 * * ? *)"
}

variable "evening_schedule_cron" {
  description = "Cron expression for evening medication notification"
  type        = string
  default     = "cron(0 23 * * ? *)"
}

variable "morning_reminder_cron" {
  description = "Cron expression for morning reminder (typically 15 min after morning_schedule_cron)"
  type        = string
  default     = "cron(15 11 * * ? *)"
}

variable "evening_reminder_cron" {
  description = "Cron expression for evening reminder (typically 15 min after evening_schedule_cron)"
  type        = string
  default     = "cron(15 23 * * ? *)"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, staging)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "med-notifier"
}

variable "telegram_bot_token" {
  description = "Telegram bot token — stored in SSM SecureString"
  type        = string
  sensitive   = true
}

variable "aws_access_key" {
  description = "AWS access key"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS secret key"
  type        = string
  sensitive   = true
}