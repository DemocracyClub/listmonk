import json

import boto3
import pytest
import requests
import responses
from freezegun import freeze_time
from moto import mock_scheduler
from onboard_scheduler.handler import (
    MAIN_LIST_UUID,
    get_subscribers,
    handler,
    schedule_onboarding,
)
from responses import matchers

API_URL = "https://mailinglist.example.com/api"
AUTH_HEADER = {"Authorization": "token api-user:test-token"}
OTHER_LIST_UUID = "41badaf2-7905-4116-8eac-e8817c6613e4"


def make_list(uuid=MAIN_LIST_UUID, status="confirmed", list_id=1):
    return {
        "subscription_status": status,
        "id": list_id,
        "uuid": uuid,
        "name": "A list",
    }


def make_subscriber(subscriber_id=1, lists=None):
    return {
        "id": subscriber_id,
        "email": f"test{subscriber_id}@example.com",
        "name": "Test Subscriber",
        "attribs": {"city": "Bengaluru"},
        "status": "enabled",
        "lists": [make_list()] if lists is None else lists,
    }


@pytest.fixture()
def rsps():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture()
def scheduler_client(aws_credentials):
    with mock_scheduler():
        yield boto3.client("scheduler", region_name="eu-west-2")


def add_subscribers(rsps, *subscribers):
    rsps.get(
        f"{API_URL}/subscribers",
        json={"data": {"results": list(subscribers)}},
        match=[matchers.header_matcher(AUTH_HEADER)],
    )


def schedule_names(client):
    return [s["Name"] for s in client.list_schedules()["Schedules"]]


def put_bodies(rsps):
    return {
        call.request.url: json.loads(call.request.body)
        for call in rsps.calls
        if call.request.method == "PUT"
    }


@freeze_time("2023-01-14")
def test_get_subscribers_query(rsps):
    add_subscribers(rsps, make_subscriber())

    assert len(get_subscribers()["data"]["results"]) == 1

    url = rsps.calls[0].request.url
    assert "key=" not in url
    assert "2023-01-13+00%3A00%3A00%2B00%3A00" in url
    assert "IS+NULL" in url


def test_main_list_subscriber_is_scheduled(scheduler_client, rsps):
    add_subscribers(rsps, make_subscriber())
    rsps.put(
        f"{API_URL}/subscribers/1",
        match=[matchers.header_matcher(AUTH_HEADER)],
    )

    handler({}, {})

    assert schedule_names(scheduler_client) == ["Onboard-subscriber-1"]
    assert put_bodies(rsps)[f"{API_URL}/subscribers/1"] == {
        "attribs": {"city": "Bengaluru", "onboarded": "1"},
        "email": "test1@example.com",
        "lists": [1],
        "name": "Test Subscriber",
        "status": "enabled",
    }


@pytest.mark.parametrize(
    "lists",
    [
        pytest.param([make_list(uuid=OTHER_LIST_UUID)], id="other-list"),
        pytest.param(
            [
                make_list(status="unsubscribed"),
                make_list(uuid=OTHER_LIST_UUID, list_id=2),
            ],
            id="unsubscribed-from-main-list",
        ),
    ],
)
def test_other_subscribers_are_skipped(scheduler_client, rsps, lists):
    add_subscribers(rsps, make_subscriber(lists=lists))
    rsps.put(f"{API_URL}/subscribers/1")

    handler({}, {})

    assert schedule_names(scheduler_client) == []
    attribs = put_bodies(rsps)[f"{API_URL}/subscribers/1"]["attribs"]
    assert attribs["onboarding_skipped"] == "1"
    assert attribs["onboarded"] == "1"


@freeze_time("2023-07-01 12:00:30")
def test_schedule_is_a_full_day_ahead_in_utc(scheduler_client):
    schedule_onboarding(make_subscriber())

    schedule = scheduler_client.get_schedule(Name="Onboard-subscriber-1")
    assert schedule["ScheduleExpression"] == "at(2023-07-02T12:00:00)"
    assert schedule["ScheduleExpressionTimezone"] == "UTC"
    assert json.loads(schedule["Target"]["Input"]) == {"subscriber_id": 1}


def test_already_scheduled_subscriber_is_still_marked(scheduler_client, rsps):
    schedule_onboarding(make_subscriber())
    add_subscribers(rsps, make_subscriber())
    rsps.put(f"{API_URL}/subscribers/1")

    handler({}, {})

    assert f"{API_URL}/subscribers/1" in put_bodies(rsps)


def test_failure_does_not_block_other_subscribers(scheduler_client, rsps):
    add_subscribers(rsps, make_subscriber(1), make_subscriber(2))
    rsps.put(f"{API_URL}/subscribers/1", status=500)
    rsps.put(f"{API_URL}/subscribers/2")

    with pytest.raises(RuntimeError, match=r"\[1\]"):
        handler({}, {})

    assert sorted(schedule_names(scheduler_client)) == [
        "Onboard-subscriber-1",
        "Onboard-subscriber-2",
    ]


def test_query_failure_raises(rsps):
    rsps.get(f"{API_URL}/subscribers", status=403)

    with pytest.raises(requests.HTTPError):
        handler({}, {})
