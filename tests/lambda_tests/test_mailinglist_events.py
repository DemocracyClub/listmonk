import json

import pytest
import requests
import responses
from mailinglist_events.handler import MAIN_LIST_UUID, handler
from responses import matchers

API_URL = "https://mailinglist.example.com/api"
AUTH_HEADER = {"Authorization": "token api-user:test-token"}
OTHER_LIST_UUID = "41badaf2-7905-4116-8eac-e8817c6613e4"


@pytest.fixture()
def rsps():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def new_subscription_event(**detail):
    return {
        "detail-type": "new_subscription",
        "source": "test",
        "detail": {
            "email": "test@example.com",
            "name": "Test Subscriber",
            "lists": ["1", 2],
            **detail,
        },
    }


def welcome_event(subscriber_id=1):
    return {
        "detail-type": "first_welcome_email",
        "source": "new_subscriber_event",
        "detail": {"subscriber_id": subscriber_id},
    }


def add_subscriber(rsps, uuid=MAIN_LIST_UUID, status="confirmed", name="Test"):
    rsps.get(
        f"{API_URL}/subscribers/1",
        json={
            "data": {
                "email": "test@example.com",
                "name": name,
                "attribs": {},
                "lists": [
                    {"id": 1, "uuid": uuid, "subscription_status": status}
                ],
            }
        },
        match=[matchers.header_matcher(AUTH_HEADER)],
    )


def tx_calls(rsps):
    return [c for c in rsps.calls if c.request.url == f"{API_URL}/tx"]


@pytest.mark.parametrize("status_code", [200, 409])
def test_new_subscription(rsps, status_code):
    rsps.post(
        f"{API_URL}/subscribers",
        status=status_code,
        json={"data": {"id": 1}},
        match=[matchers.header_matcher(AUTH_HEADER)],
    )

    assert handler(new_subscription_event(), {}) is True

    request = rsps.calls[0].request
    assert "key=" not in request.url
    assert json.loads(request.body)["lists"] == [1, 2]


def test_new_subscription_without_name(rsps):
    rsps.post(f"{API_URL}/subscribers", json={"data": {"id": 1}})
    event = new_subscription_event()
    del event["detail"]["name"]

    assert handler(event, {}) is True


def test_new_subscription_error_raises(rsps):
    rsps.post(f"{API_URL}/subscribers", status=500)

    with pytest.raises(requests.HTTPError):
        handler(new_subscription_event(), {})


@pytest.mark.parametrize(
    "detail",
    [
        {"email": "not-an-email"},
        {"email": None},
        {"name": "someone@example.com"},
        {"lists": "1"},
    ],
)
def test_invalid_new_subscription(detail):
    with pytest.raises(ValueError):
        handler(new_subscription_event(**detail), {})


def test_welcome_email_sent_to_main_list_subscriber(rsps):
    add_subscriber(rsps)
    rsps.post(
        f"{API_URL}/tx",
        json={"data": True},
        match=[matchers.header_matcher(AUTH_HEADER)],
    )

    handler(welcome_event(), {})

    assert json.loads(tx_calls(rsps)[0].request.body) == {
        "template_id": 4,
        "subscriber_id": 1,
    }


def test_welcome_email_allows_existing_name_containing_at(rsps):
    add_subscriber(rsps, name="someone@example.com")
    rsps.post(f"{API_URL}/tx", json={"data": True})

    handler(welcome_event(), {})

    assert len(tx_calls(rsps)) == 1


@pytest.mark.parametrize(
    "list_kwargs",
    [
        pytest.param({"uuid": OTHER_LIST_UUID}, id="other-list"),
        pytest.param({"status": "unsubscribed"}, id="unsubscribed"),
    ],
)
def test_welcome_email_not_sent(rsps, list_kwargs):
    add_subscriber(rsps, **list_kwargs)

    handler(welcome_event(), {})

    assert tx_calls(rsps) == []


def test_welcome_email_lookup_failure_raises(rsps):
    rsps.get(f"{API_URL}/subscribers/1", status=403)

    with pytest.raises(requests.HTTPError):
        handler(welcome_event(), {})


def test_unknown_detail_type():
    with pytest.raises(ValueError):
        handler({"detail-type": "nope"}, {})
