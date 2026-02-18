variable "notifier_schedule_cron" {
  description = "Cron expression for medication notifications (e.g. morning + evening)"
  type        = string
  default     = "cron(0 11,23 * * ? *)"
}

variable "schedule_timezone" {
  description = "IANA timezone for all schedules"
  type        = string
  default     = "America/New_York"
}

variable "reminder_interval_minutes" {
  description = "How often (in minutes) to check for unconfirmed medications and send reminders"
  type        = number
  default     = 15
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