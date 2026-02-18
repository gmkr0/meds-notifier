import os
import pytest
import boto3
from moto import mock_aws

# Set env vars before any shared module imports
os.environ.setdefault("TABLE_CONFIRMATIONS", "test-confirmations")
os.environ.setdefault("TABLE_SUBSCRIBERS", "test-subscribers")
os.environ.setdefault("SSM_BOT_TOKEN_PARAM", "/test/bot-token")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("CONFIG_PATH", "src")


@pytest.fixture(autouse=True)
def _reset_shared_caches():
    """Reset module-level caches between tests."""
    import shared.telegram as tg
    import shared.dynamo as db

    tg._bot_token = None
    tg._ssm_client = None
    db._client = None
    yield


@pytest.fixture()
def aws(request):
    """Provide mocked AWS services with DynamoDB tables and SSM parameter."""
    with mock_aws():
        region = os.environ["AWS_DEFAULT_REGION"]

        # DynamoDB tables
        ddb = boto3.client("dynamodb", region_name=region)
        ddb.create_table(
            TableName=os.environ["TABLE_CONFIRMATIONS"],
            KeySchema=[{"AttributeName": "schedule_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "schedule_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName=os.environ["TABLE_SUBSCRIBERS"],
            KeySchema=[{"AttributeName": "chat_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "chat_id", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # SSM parameter
        ssm = boto3.client("ssm", region_name=region)
        ssm.put_parameter(
            Name=os.environ["SSM_BOT_TOKEN_PARAM"],
            Value="fake-bot-token-123",
            Type="SecureString",
        )

        yield ddb
