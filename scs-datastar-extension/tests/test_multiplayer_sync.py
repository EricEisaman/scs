import unittest

from fastapi import HTTPException

from app.main import MultiplayerRegistry
from app.multiplayer.protocol import CharacterState, JoinRequest


def character_payload(client_id, position=(1.0, 2.0), timestamp=1):
    return {
        "clientId": client_id,
        "characterModelId": "platformer-default",
        "position": list(position),
        "velocity": [0.0, 0.0],
        "animationState": "idle",
        "animationFrame": 0.0,
        "isJumping": False,
        "facing": 1,
        "score": 0,
        "onGround": True,
        "timestamp": timestamp,
    }


class CharacterProtocolTests(unittest.TestCase):
    def test_character_state_rejects_unknown_fields_and_non_2d_vectors(self):
        payload = character_payload("peer")
        self.assertEqual(CharacterState.from_payload(payload).to_dict(), payload)

        with self.assertRaises(ValueError):
            CharacterState.from_payload(dict(payload, rotation=[0, 0, 0]))
        with self.assertRaises(ValueError):
            CharacterState.from_payload(dict(payload, position=[1, 2, 3]))
        with self.assertRaises(ValueError):
            CharacterState.from_payload(dict(payload, facing=True))


class MultiplayerRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_character_updates_reject_extra_fields_before_broadcast(self):
        registry = MultiplayerRegistry()
        joined = await registry.join(JoinRequest("level-a", "Player"))
        queue, _ = await registry.subscribe_sse(joined.client_id)

        with self.assertRaises(HTTPException) as raised:
            await registry.handle_character_state(
                joined.client_id,
                [dict(character_payload(joined.client_id), rotation=[0, 0, 0])],
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertNotIn(joined.client_id, registry.character_cache)
        self.assertTrue(queue.empty())

    async def test_live_fanout_is_limited_to_matching_environment(self):
        registry = MultiplayerRegistry()
        same_room = await registry.join(JoinRequest("level-a", "A"))
        other_room = await registry.join(JoinRequest("level-b", "B"))
        same_queue, _ = await registry.subscribe_sse(same_room.client_id)
        other_queue, _ = await registry.subscribe_sse(other_room.client_id)

        await registry._broadcast_signal(
            "character-state-update",
            {"updates": [], "timestamp": 2},
            environment="level-a",
        )

        self.assertEqual((await same_queue.get())[0], "character-state-update")
        self.assertTrue(other_queue.empty())

    async def test_bootstrap_snapshot_and_live_queue_have_no_gap(self):
        registry = MultiplayerRegistry()
        first = await registry.join(JoinRequest("level-a", "First"))
        await registry.handle_character_state(
            first.client_id, [character_payload(first.client_id, timestamp=1)]
        )
        second = await registry.join(JoinRequest("level-a", "Second"))

        queue, bootstrap = await registry.subscribe_sse(second.client_id)
        initial = next(payload for name, payload in bootstrap if name == "character-state-update")
        self.assertEqual(initial["updates"][0]["clientId"], first.client_id)

        await registry.handle_character_state(
            first.client_id, [character_payload(first.client_id, position=(3.0, 4.0), timestamp=2)]
        )
        name, update = await queue.get()
        self.assertEqual(name, "character-state-update")
        self.assertEqual(update["updates"][0]["position"], [3.0, 4.0])


if __name__ == "__main__":
    unittest.main()