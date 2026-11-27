"""Coordinate GitHub and external scheduler ticks using the durable sync state."""
from datetime import datetime, timezone

SLOT_SECONDS = 300


def slot_for(value):
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("Scheduler timestamp must contain a timezone")
    return int(instant.timestamp()) // SLOT_SECONDS * SLOT_SECONDS


def claim_slot(store, created_at, observed_at):
    try:
        slot = slot_for(created_at or observed_at)
    except ValueError:
        slot = slot_for(observed_at)
    previous = store.data.get("lastAutomaticSlot")
    label = datetime.fromtimestamp(slot, timezone.utc).isoformat()
    if previous is not None and slot <= previous:
        return False, label

    # GitState.save is a fast-forward compare-and-swap. On conflict, the caller
    # fails before opening a source or sending a notification.
    store.data["lastAutomaticSlot"] = slot
    store.save()
    return True, label
