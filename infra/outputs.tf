output "webhook_url" {
  description = "Full URL for the Telegram webhook endpoint"
  value       = "${aws_apigatewayv2_stage.webhook.invoke_url}/webhook"
}

output "api_gateway_id" {
  description = "API Gateway ID"
  value       = aws_apigatewayv2_api.webhook.id
}

output "notifier_function_name" {
  description = "Notifier Lambda function name"
  value       = module.lambda_notifier.function_name
}

output "reminder_function_name" {
  description = "Reminder Lambda function name"
  value       = module.lambda_reminder.function_name
}

output "webhook_function_name" {
  description = "Webhook Lambda function name"
  value       = module.lambda_webhook.function_name
}

output "confirmations_table_name" {
  description = "DynamoDB confirmations table name"
  value       = aws_dynamodb_table.confirmations.name
}

output "subscribers_table_name" {
  description = "DynamoDB subscribers table name"
  value       = aws_dynamodb_table.subscribers.name
}

output "ssm_bot_token_param" {
  description = "SSM parameter name for the Telegram bot token"
  value       = aws_ssm_parameter.bot_token.name
}
