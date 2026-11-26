"""Conservatively reserve room for automated LINE pushes before sending."""
from datetime import datetime
from urllib.parse import quote

import requests

import notify_line as line

API = "https://api.line.me/v2/bot"
FREE_MONTHLY_CAP = 200
MANUAL_RESERVE = 10


class LineQuota:
    def __init__(self, store):
        self.store = store
        self.snapshot = None
        self.unavailable_month = None
        self.unavailable_reason = None

    def read(self, endpoint):
        if not line.LINE_TOKEN:
            raise ValueError("LINE credentials are unavailable")
        response = requests.get(
            API + endpoint, headers={"Authorization": f"Bearer {line.LINE_TOKEN}"}, timeout=8,
        )
        response.raise_for_status()
        return response.json()

    def limits(self):
        quota = self.read("/message/quota")
        consumption = self.read("/message/quota/consumption")["totalUsage"]
        if quota.get("type") == "limited":
            maximum = min(FREE_MONTHLY_CAP, quota["value"])
        elif quota.get("type") == "none":
            maximum = FREE_MONTHLY_CAP
        else:
            raise ValueError("Unexpected LINE quota response")
        target = line.LINE_TO
        if target.startswith("U"):
            recipients = 1
        elif target.startswith(("C", "R")):
            kind = "group" if target.startswith("C") else "room"
            recipients = self.read(f"/{kind}/{quote(target, safe='')}/members/count")["count"]
        else:
            raise ValueError("Unknown LINE recipient type")
        if not all(type(number) is int and number >= 0 for number in (maximum, consumption, recipients)):
            raise ValueError("Invalid LINE quota response")
        if not recipients:
            raise ValueError("LINE recipient count is zero")
        return maximum, consumption, recipients

    def reserve(self, batch):
        month = datetime.now(line.JST).strftime("%Y-%m")
        if self.unavailable_month == month:
            return False, self.unavailable_reason
        if self.snapshot is None or self.snapshot[0] != month:
            try:
                self.snapshot = (month, *self.limits())
            except (requests.RequestException, KeyError, TypeError, ValueError) as error:
                self.unavailable_month = month
                self.unavailable_reason = type(error).__name__
                return False, self.unavailable_reason
        _, maximum, consumption, recipients = self.snapshot
        budget = self.store.data.get("lineQuota", {})
        projected = budget["projectedUsage"] if budget.get("month") == month else 0
        projected = max(consumption, projected)
        if consumption >= maximum:
            return False, "monthly_budget"
        if batch.get("quotaMonth") == month:
            return True, None  # An idempotent retry uses the same durable reservation.
        if projected + recipients > max(0, maximum - MANUAL_RESERVE):
            return False, "monthly_budget"
        self.store.data["lineQuota"] = {"month": month, "projectedUsage": projected + recipients}
        batch["quotaMonth"] = month
        return True, None
