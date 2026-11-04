import os
import sys

sys.path.append("cdk/functions/")

# Handlers create boto3 clients at import, which read credentials straight away.
# Set fake ones here so that tests can never use real AWS credentials.
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ.pop("AWS_PROFILE", None)

import pytest


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    monkeypatch.setenv("MAILINGLIST_API_USER", "api-user")
    monkeypatch.setenv("MAILINGLIST_API_KEY", "test-token")
    monkeypatch.setenv("FQDN", "mailinglist.example.com")
    monkeypatch.setenv(
        "EVENT_BUS_ARN",
        "arn:aws:events:eu-west-2:123456789012:event-bus/MailingListEvents-test",
    )
    monkeypatch.setenv(
        "EVENT_BUS_ROLE_ARN", "arn:aws:iam::123456789012:role/event-runner"
    )


@pytest.fixture()
def aws_credentials(monkeypatch):
    """Mocked AWS region for moto. See above for credentials."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
