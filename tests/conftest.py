import sys
sys.path.append("cdk/functions/")

import pytest


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    monkeypatch.setenv("MAILINGLIST_API_KEY", "test-key")


@pytest.fixture()
def aws_credentials(monkeypatch):
    """Mocked AWS Credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
