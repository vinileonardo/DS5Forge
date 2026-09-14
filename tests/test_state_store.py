import unittest

from dualsense_companion.core.state_store import StateStore
from dualsense_companion.domain.models import RuntimeSnapshot


class StateStoreTests(unittest.TestCase):
    def test_snapshots_are_versioned_and_events_are_bounded(self):
        store = StateStore(RuntimeSnapshot.initial())
        subscription = store.subscribe(maxsize=1)
        store.update(rumble_enabled=False)
        store.update(touchpad_enabled=False)
        event = subscription.get(timeout=0.2)
        self.assertEqual(event.type, "state.updated")
        self.assertFalse(event.payload["state"]["touchpad_enabled"])
        self.assertEqual(event.payload["state"]["sequence"], 2)
        self.assertEqual(store.get().sequence, 2)
        store.unsubscribe(subscription)


if __name__ == "__main__":
    unittest.main()
