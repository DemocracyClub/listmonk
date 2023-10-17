import json
import os
from dataclasses import dataclass

import requests


def format_api_url(endpoint):
    return f"https://{FQDN}/api/{endpoint}?key={API_KEY}"


@dataclass(match_args=False)
class EmailSubscriber:
    name: str
    email: str
    list_uuids: list
    source: str = None
    extra_context: dict = None
    status: str = "enabled"
    subscriber_id: int = None
    confirmed: bool = False

    def __post_init__(self):
        # Validate email
        if "@" not in self.email:
            raise ValueError("Invalid email address.")
        if "@" in self.name:
            raise ValueError("Name cannot contain an email address")
        if not isinstance(self.list_uuids, list):
            raise ValueError("'list_uuids' must be a list")
        self.list_uuids = [int(x) for x in self.list_uuids]

    @classmethod
    def from_event(cls, event: dict):
        detail = event["detail"]

        confirmed = False

        return cls(
            email=detail.get("email"),
            name=detail.get("name"),
            list_uuids=detail.get("lists"),
            source=event["source"],
            extra_context=detail.get("extra_context"),
            subscriber_id=detail.get("id"),
            confirmed=confirmed,
        )

    @classmethod
    def from_subscriber_id(cls, subscriber_id):
        url = format_api_url(f"subscribers/{subscriber_id}")
        data = requests.get(url).json()["data"]
        print(data)
        list_ids = [mailinglist["id"] for mailinglist in data["lists"]]
        confirmed = any(
            mailinglist["subscription_status"] == "confirmed"
            for mailinglist in data["lists"]
        )

        return cls(
            name=data["name"],
            email=data["email"],
            extra_context=data["attribs"],
            subscriber_id=subscriber_id,
            confirmed=confirmed,
            list_uuids=list_ids,
        )

    def as_listmonk_json(self):
        return {
            "email": self.email,
            "name": self.name,
            "status": self.status,
            "lists": self.list_uuids,
            "attribs": self.extra_context,
        }


API_KEY = os.environ.get("MAILINGLIST_API_KEY")
FQDN = os.environ.get("FQDN")


def new_subscription(event):
    subscriber = EmailSubscriber.from_event(event)

    url = format_api_url("subscribers")
    req = requests.post(
        url,
        json=subscriber.as_listmonk_json(),
    )
    if req.status_code == 200:
        print("added new person")
        subscriber.subscriber_id = req.json()["data"]["id"]
        return True
    if req.status_code == 409:
        print("person alrady exists")
        return True
    req.raise_for_status()


def first_welcome_email(event):
    if not event["detail"]["subscriber_id"]:
        print("subscriber ID not in event")
        return

    subscriber = EmailSubscriber.from_subscriber_id(event["detail"]["subscriber_id"])

    url = format_api_url("tx")
    data = {"template_id": 4, "subscriber_id": subscriber.subscriber_id}
    req = requests.post(url, json=data)
    req.raise_for_status()


def handler(event, context):
    print(event)
    detail_type = event["detail-type"]

    if detail_type == "new_subscription":
        return new_subscription(event)
    if detail_type == "first_welcome_email":
        return first_welcome_email(event)

    raise ValueError(f"Unknown detail-type '{detail_type}'")
