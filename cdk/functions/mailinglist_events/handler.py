import os
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

import requests

REQUEST_TIMEOUT_SECONDS = 10


class ListmonkList(TypedDict):
    id: int
    uuid: str
    subscription_status: str


class ListmonkSubscriber(TypedDict):
    email: str
    name: str
    attribs: dict[str, Any]
    lists: list[ListmonkList]


def format_api_url(endpoint: str) -> str:
    return f"https://{os.environ.get('FQDN')}/api/{endpoint}"


def auth_headers() -> dict[str, str]:
    user = os.environ.get("MAILINGLIST_API_USER")
    token = os.environ.get("MAILINGLIST_API_KEY")
    return {"Authorization": f"token {user}:{token}"}


@dataclass(match_args=False)
class EmailSubscriber:
    name: str
    email: str
    # Listmonk's numeric list IDs, as used when writing to the API
    list_ids: list[int]
    # The UUIDs of the lists this person hasn't unsubscribed from
    active_list_uuids: list[str] = field(default_factory=list)
    source: Optional[str] = None
    extra_context: Optional[dict[str, Any]] = None
    status: str = "enabled"
    subscriber_id: Optional[int] = None
    confirmed: bool = False

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "EmailSubscriber":
        detail = event["detail"]
        email = detail.get("email") or ""
        name = detail.get("name") or ""
        list_ids = detail.get("lists")

        if "@" not in email:
            raise ValueError("Invalid email address.")
        if "@" in name:
            raise ValueError("Name cannot contain an email address")
        if not isinstance(list_ids, list):
            raise ValueError("'lists' must be a list")

        return cls(
            email=email,
            name=name,
            list_ids=[int(x) for x in list_ids],
            source=event["source"],
            extra_context=detail.get("extra_context"),
            subscriber_id=detail.get("id"),
        )

    @classmethod
    def from_subscriber_id(cls, subscriber_id: int) -> "EmailSubscriber":
        req = requests.get(
            format_api_url(f"subscribers/{subscriber_id}"),
            headers=auth_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        req.raise_for_status()
        data: ListmonkSubscriber = req.json()["data"]
        print(data)
        lists = data["lists"]

        return cls(
            name=data["name"],
            email=data["email"],
            extra_context=data["attribs"],
            subscriber_id=subscriber_id,
            confirmed=any(
                mailing_list["subscription_status"] == "confirmed"
                for mailing_list in lists
            ),
            list_ids=[mailing_list["id"] for mailing_list in lists],
            active_list_uuids=[
                mailing_list["uuid"]
                for mailing_list in lists
                if mailing_list["subscription_status"] != "unsubscribed"
            ],
        )

    def as_listmonk_json(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "name": self.name,
            "status": self.status,
            "lists": self.list_ids,
            "attribs": self.extra_context,
        }


def new_subscription(event: dict[str, Any]) -> Optional[bool]:
    subscriber = EmailSubscriber.from_event(event)

    req = requests.post(
        format_api_url("subscribers"),
        json=subscriber.as_listmonk_json(),
        headers=auth_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if req.status_code == 200:
        print("added new person")
        subscriber.subscriber_id = req.json()["data"]["id"]
        return True
    if req.status_code == 409:
        print("person alrady exists")
        return True
    req.raise_for_status()
    return None


def first_welcome_email(event: dict[str, Any]) -> None:
    subscriber_id: Optional[int] = event["detail"].get("subscriber_id")
    if not subscriber_id:
        print("subscriber ID not in event")
        return

    subscriber = EmailSubscriber.from_subscriber_id(subscriber_id)

    if os.environ["MAIN_LIST_UUID"] not in subscriber.active_list_uuids:
        print("Subscriber not in mail email list")
        return

    data = {
        "template_id": int(os.environ["WELCOME_TEMPLATE_ID"]),
        "subscriber_id": subscriber.subscriber_id,
    }
    req = requests.post(
        format_api_url("tx"),
        json=data,
        headers=auth_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    req.raise_for_status()


def handler(event: dict[str, Any], context: Any) -> Optional[bool]:
    print(event)
    detail_type = event["detail-type"]

    if detail_type == "new_subscription":
        return new_subscription(event)
    if detail_type == "first_welcome_email":
        first_welcome_email(event)
        return None

    raise ValueError(f"Unknown detail-type '{detail_type}'")
