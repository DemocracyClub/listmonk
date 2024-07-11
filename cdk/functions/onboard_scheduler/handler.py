import datetime
import json
import os

import boto3
import requests


scheduler = boto3.client("scheduler", region_name="eu-west-2")


def format_api_url(endpoint):
    API_KEY = os.environ.get("MAILINGLIST_API_KEY")
    FQDN = os.environ.get("FQDN")
    return f"https://{FQDN}/api/{endpoint}?key={API_KEY}"


def get_past_slice_time():
    """
    The formatted date to look backwards in time
    for querying ListMonk's database for new subscribers
    """
    return str(datetime.datetime.now() - datetime.timedelta(days=1))


def schedule_onboarding(subscriber: dict):
    one_day_from_now = datetime.datetime.now() + datetime.timedelta(days=1)
    print("Scheduling onboarding")
    schedule = scheduler.create_schedule(
        ScheduleExpression=f"at({datetime.datetime.strftime(one_day_from_now, '%Y-%m-%dT%H:%M:00')})",
        ScheduleExpressionTimezone="Europe/London",
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
    print(schedule)


def get_subscribers():
    # Check for un-onboarded signups in the last day (day, in case we've missed anyone for some reason)
    past_time_slice = get_past_slice_time()
    url = format_api_url("subscribers")
    query = f"""
        subscribers.attribs->>'onboarded' IS NULL 
        AND subscribers.created_at >= '{past_time_slice}'
        AND subscribers.id IN (SELECT subscriber_id FROM subscriber_lists WHERE status='confirmed')
        """
    req = requests.get(
        url,
        params={"query": query},
    )
    req.raise_for_status()
    return req.json()


def handler(event, context):
    subscribers = get_subscribers()
    for subscriber in subscribers["data"]["results"]:
        # update the subscriber
        # The PUT request update the entire record, so we need to
        # send everything, not just the changed content
        attribs = subscriber["attribs"]
        attribs["onboarded"] = "1"
        if "b97e389a-c986-4725-8796-2a1cf2734e43" in subscriber.list_uuids:
            attribs["onboarding_skipped"] = "1"
        put_data = {
            "email": subscriber["email"],
            "name": subscriber["name"],
            "status": subscriber["status"],
            "lists": [mailing_list["id"] for mailing_list in subscriber["lists"]],
            "attribs": attribs,
        }
        url = format_api_url(f"subscribers/{subscriber['id']}")
        requests.put(url, json=put_data)
        if "b97e389a-c986-4725-8796-2a1cf2734e43" in subscriber.list_uuids:
            schedule_onboarding(subscriber)
