locals {
  full_name = "${var.project_name}-${var.function_name}-${var.environment}"
}

# --- IAM Role ---

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.full_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "custom" {
  count      = length(var.policy_arns)
  role       = aws_iam_role.lambda.name
  policy_arn = var.policy_arns[count.index]
}

# --- CloudWatch Log Group ---

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.full_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "logging" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logging" {
  name   = "${local.full_name}-logging"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.logging.json
}

# --- Lambda Function ---

resource "aws_lambda_function" "this" {
  function_name = local.full_name
  role          = aws_iam_role.lambda.arn
  handler       = var.handler
  runtime       = var.runtime
  timeout       = var.timeout
  memory_size   = var.memory_size

  filename         = var.source_path
  source_code_hash = filebase64sha256(var.source_path)

  environment {
    variables = var.environment_variables
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.logging,
  ]
}
