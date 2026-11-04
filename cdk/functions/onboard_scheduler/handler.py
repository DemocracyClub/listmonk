import datetime
import json
import os
from typing import Any, TypedDict

import boto3
import requests

MAIN_LIST_UUID = "b97e389a-c986-4725-8796-2a1cf2734e43"
REQUEST_TIMEOUT_SECONDS = 10

scheduler = boto3.client("scheduler", region_name="eu-west-2")


class ListmonkList(TypedDict):
    id: int
    uuid: str
    subscription_status: str


class ListmonkSubscriber(TypedDict):
    id: int
    email: str
    name: str
    status: str
    attribs: dict[str, Any]
    lists: list[ListmonkList]


class SubscriberResults(TypedDict):
    results: list[ListmonkSubscriber]


class SubscriberQueryResponse(TypedDict):
    data: SubscriberResults


def format_api_url(endpoint: str) -> str:
    return f"https://{os.environ.get('FQDN')}/api/{endpoint}"


def auth_headers() -> dict[str, str]:
    user = os.environ.get("MAILINGLIST_API_USER")
    token = os.environ.get("MAILINGLIST_API_KEY")
    return {"Authorization": f"token {user}:{token}"}


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def get_past_slice_time() -> str:
    """
    The formatted date to look backwards in time
    for querying ListMonk's database for new subscribers
    """
    return str(utc_now() - datetime.timedelta(days=1))


def is_on_main_list(subscriber: ListmonkSubscriber) -> bool:
    return any(
        mailing_list["uuid"] == MAIN_LIST_UUID
        and mailing_list["subscription_status"] != "unsubscribed"
        for mailing_list in subscriber["lists"]
    )


def schedule_onboarding(subscriber: ListmonkSubscriber) -> None:
    one_day_from_now = utc_now() + datetime.timedelta(days=1)
    print("Scheduling onboarding")
    try:
        schedule = scheduler.create_schedule(
            ScheduleExpression=f"at({one_day_from_now.strftime('%Y-%m-%dT%H:%M:00')})",
            ScheduleExpressionTimezone="UTC",
            Name=f"Onboard-subscriber-{subscriber['id']}",
            ActionAfterCompletion="DELETE",
            Target={
                "Arn": os.environ.get("EVENT_BUS_ARN"),
                "RoleArn": os.environ.get("EVENT_BUS_ROLE_ARN"),
                "EventBridgeParameters": {
                    "DetailType": "first_welcome_email",
                    "Source": "new_subscriber_event",
                },
                "Input": json.dumps({"subscriber_id": subscriber["id"]}),
            },
            FlexibleTimeWindow={"Mode": "OFF"},
        )
    except scheduler.exceptions.ConflictException:
        # An earlier run scheduled this but failed to mark them as onboarded
        print("Onboarding already scheduled")
        return
    print(schedule)


def get_subscribers() -> SubscriberQueryResponse:
    # Check for un-onboarded signups in the last day (day, in case we've missed anyone for some reason)
    past_time_slice = get_past_slice_time()
    query = f"""
        subscribers.attribs->>'onboarded' IS NULL 
        AND subscribers.created_at >= '{past_time_slice}'
        AND subscribers.id IN (SELECT subscriber_id FROM subscriber_lists WHERE status='confirmed')
        """
    req = requests.get(
        format_api_url("subscribers"),
        params={"query": query},
        headers=auth_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    req.raise_for_status()
    response: SubscriberQueryResponse = req.json()
    return response


def onboard_subscriber(subscriber: ListmonkSubscriber) -> None:
    # Schedule before marking as onboarded. If either step fails the next run
    # retries, whereas marking first could lose the welcome email for good.
    on_main_list = is_on_main_list(subscriber)
    if on_main_list:
        schedule_onboarding(subscriber)

    # The PUT request update the entire record, so we need to
    # send everything, not just the changed content
    attribs = {**subscriber["attribs"], "onboarded": "1"}
    if not on_main_list:
        attribs["onboarding_skipped"] = "1"
    put_data = {
        "email": subscriber["email"],
        "name": subscriber["name"],
        "status": subscriber["status"],
        "lists": [mailing_list["id"] for mailing_list in subscriber["lists"]],
        "attribs": attribs,
    }
    req = requests.put(
        format_api_url(f"subscribers/{subscriber['id']}"),
        json=put_data,
        headers=auth_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    req.raise_for_status()


def handler(event: dict[str, Any], context: Any) -> None:
    failed_ids: list[int] = []
    for subscriber in get_subscribers()["data"]["results"]:
        # Don't let one bad record hold up everyone after it
        try:
            onboard_subscriber(subscriber)
        except Exception as error:
            print(f"Failed to onboard {subscriber['id']}: {error}")
            failed_ids.append(subscriber["id"])

    if failed_ids:
        raise RuntimeError(f"Failed to onboard subscribers: {failed_ids}")
