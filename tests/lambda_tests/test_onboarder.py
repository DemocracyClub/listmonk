import json

import boto3
import pytest
import responses
from dateutil.tz import tzlocal
from freezegun import freeze_time
from freezegun.api import FakeDatetime
from moto import mock_scheduler
from responses import matchers

from onboard_scheduler.handler import get_subscribers, handle

SOME_UNONBOARDED_SUBSCRIBERS = {
    "data": {
        "results": [
            {
                "id": 1,
                "created_at": "2019-06-26T16:51:54.37065+05:30",
                "updated_at": "2019-07-03T11:53:53.839692+05:30",
                "uuid": "5e91dda1-1c16-467d-9bf9-2a21bf22ae21",
                "email": "test@test.com",
                "name": "Test Subscriber",
                "attribs": {
                    "city": "Bengaluru",
                    "projects": 3,
                    "stack": {
                        "frameworks": ["echo", "go"],
                        "languages": ["go", "python"],
                    },
                },
                "status": "enabled",
                "lists": [
                    {
                        "subscription_status": "unconfirmed",
                        "id": 1,
                        "uuid": "41badaf2-7905-4116-8eac-e8817c6613e4",
                        "name": "Default list",
                        "type": "public",
                        "tags": ["test"],
                        "created_at": "2019-06-26T16:51:54.367719+05:30",
                        "updated_at": "2019-06-26T16:51:54.367719+05:30",
                    }
                ],
            }
        ],
        "query": "subscribers.attribs->>'onboarded' IS NULL AND subscribers.created_at >= '2023-01-13 00:00:00'",
        "total": 1,
        "per_page": 20,
        "page": 1,
    }
}


@pytest.fixture(scope="module")
def mock_listmonk_subscribers():
    with responses.RequestsMock() as rsps:
        with freeze_time("2023-01-14"):
            # Register via 'Response' object
            params = {
                "key": "test-key",
                "query": "subscribers.attribs->>'onboarded' IS NULL AND subscribers.created_at >= '2023-01-13 00:00:00' subscribers.id IN (SELECT subscriber_id FROM subscriber_lists WHERE status='confirmed')",
            }
            query = responses.Response(
                method="GET",
                url="https://mailinglist.democracyclub.org.uk/api/subscribers",
                match=[matchers.query_param_matcher(params)],
                json=SOME_UNONBOARDED_SUBSCRIBERS,
            )
            rsps.add(query)
            # See https://github.com/getmoto/moto/issues/6417
            responses._real_send = rsps.unbound_on_send()

            yield rsps


@pytest.fixture()
def mock_aws_services(aws_credentials):
    with mock_scheduler():
        yield boto3.client("scheduler", region_name="eu-west-2")


def test_test_query_listmonk(mock_listmonk_subscribers):
    """
    Really a smoke test to make sure the query is as expected
    """
    subscribers = get_subscribers()
    assert len(subscribers["data"]["results"]) == 1


def test_handler(
    mock_aws_services,
    mock_listmonk_subscribers,
):
    expected_put_data = {
        "attribs": {
            "city": "Bengaluru",
            "onboarded": "1",
            "projects": 3,
            "stack": {"frameworks": ["echo", "go"], "languages": ["go", "python"]},
        },
        "email": "test@test.com",
        "lists": [1],
        "name": "Test Subscriber",
        "status": "enabled",
    }
    mock_listmonk_subscribers.add(
        "PUT",
        "https://mailinglist.democracyclub.org.uk/api/subscribers/1",
        # body="NOT A BODY",
        match=[
            matchers.json_params_matcher(expected_put_data, strict_match=False),
            matchers.query_param_matcher({"key": "test-key"}),
        ],
    )
    handle({}, {})
    assert mock_aws_services.list_schedules()["Schedules"] == [
        {
            "Arn": "arn:aws:scheduler:eu-west-2:123456789012:schedule/default/Onboard-subscriber-1",
            "CreationDate": FakeDatetime(2023, 1, 14, 0, 0, tzinfo=tzlocal()),
            "GroupName": "default",
            "LastModificationDate": FakeDatetime(2023, 1, 14, 0, 0, tzinfo=tzlocal()),
            "Name": "Onboard-subscriber-1",
            "State": "ENABLED",
            "Target": {
                "Arn": "arn:aws:events:eu-west-2:743524368797:event-bus/MailingListEvents-production"
            },
        }
    ]
