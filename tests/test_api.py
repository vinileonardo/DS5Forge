import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from dualsense_companion.api.server import validate_loopback_host
from dualsense_companion.core.config import ConfigRepository
from dualsense_companion.core.facade import CoreFacade


class FakeControllerFactory:
    def connect(self):
        raise AssertionError("controller connection is not expected in API tests")


class FakeMouse:
    def move(self, dx, dy):
        return None

    def button(self, left, down):
        return None

    def wheel(self, amount, horizontal=False):
        return None

    def release_all(self):
        return None


HAS_API_TEST_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "pydantic"))
if HAS_API_TEST_DEPS:
    from dualsense_companion.api.http import create_app
else:
    create_app = None


@unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI and httpx are optional local test dependencies")
class ApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        repo = ConfigRepository(
            config_path=root / "config.json",
            bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
            bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
            user_profiles_dir=root / "profiles",
        )
        self.facade = CoreFacade(
            config_repository=repo,
            controller_factory=FakeControllerFactory(),
            mouse_output=FakeMouse(),
        )
        assert create_app is not None
        self.app = create_app(self.facade)

    def tearDown(self):
        self.facade.stop()
        self.temp.cleanup()

    def test_loopback_bind_guard_rejects_external_addresses(self):
        self.assertEqual(validate_loopback_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(validate_loopback_host("localhost"), "localhost")
        with self.assertRaises(ValueError):
            validate_loopback_host("0.0.0.0")
        from dualsense_companion.api.server import validate_port

        self.assertEqual(validate_port(8765), 8765)
        with self.assertRaises(ValueError):
            validate_port(0)
        with self.assertRaises(ValueError):
            validate_port(65536)

    def test_openapi_exposes_typed_request_contracts(self):
        schema = self.app.openapi()
        config_patch = schema["paths"]["/api/v1/config"]["patch"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        rumble_command = schema["paths"]["/api/v1/commands/rumble"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        self.assertIn("$ref", config_patch)
        self.assertIn("$ref", rumble_command)
        self.assertNotEqual(config_patch.get("additionalProperties"), True)
        self.assertNotEqual(rumble_command.get("additionalProperties"), True)

    async def test_health_state_and_validation(self):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            self.assertEqual((await client.get("/api/v1/health")).status_code, 200)
            state = await client.get("/api/v1/state")
            self.assertEqual(state.status_code, 200)
            self.assertIn("connection", state.json())
            invalid = await client.patch("/api/v1/config", json={"rumble": {"gate": "bad"}})
            self.assertEqual(invalid.status_code, 422)
            numeric_string = await client.patch("/api/v1/config", json={"rumble": {"gate": "0.1"}})
            self.assertEqual(numeric_string.status_code, 422)
            unknown = await client.patch("/api/v1/config", json={"unexpected": True})
            self.assertEqual(unknown.status_code, 422)
            coerced_bool = await client.post("/api/v1/commands/rumble", json={"enabled": 1})
            self.assertEqual(coerced_bool.status_code, 422)
            coerced_trackpad_bool = await client.patch(
                "/api/v1/config",
                json={"trackpad": {"tap_to_click": 1}},
            )
            self.assertEqual(coerced_trackpad_bool.status_code, 422)
            explicit_null = await client.patch("/api/v1/config", json={"theme": None})
            self.assertEqual(explicit_null.status_code, 422)
            nested_null = await client.patch("/api/v1/config", json={"rumble": {"gate": None}})
            self.assertEqual(nested_null.status_code, 422)

    async def test_commands_and_profiles_happy_path_and_error(self):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            patched = await client.patch("/api/v1/config", json={"theme": "Dark"})
            self.assertEqual(patched.status_code, 200)
            self.assertEqual(patched.json()["theme"], "Dark")

            profiles = await client.get("/api/v1/profiles")
            self.assertEqual(profiles.status_code, 200)
            self.assertTrue(any(item["name"] == "Default" for item in profiles.json()["profiles"]))

            loaded = await client.post("/api/v1/profiles/Default/load")
            self.assertEqual(loaded.status_code, 200)
            saved = await client.put("/api/v1/profiles/API Test", json={"gate": 0.08})
            self.assertEqual(saved.status_code, 200)
            deleted = await client.delete("/api/v1/profiles/API Test")
            self.assertEqual(deleted.status_code, 200)
            missing = await client.post("/api/v1/profiles/API Test/load")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["error"]["code"], "profile.not_found")

            touchpad = await client.post("/api/v1/commands/touchpad", json={"enabled": False})
            self.assertEqual(touchpad.status_code, 200)
            rumble_test = await client.post("/api/v1/commands/rumble/test", json={"duration_ms": 10})
            self.assertEqual(rumble_test.status_code, 200)
            self.assertFalse(rumble_test.json()["accepted"])

    async def test_websocket_starts_with_snapshot(self):
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": "/api/v1/ws",
            "raw_path": b"/api/v1/ws",
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
            "subprotocols": [],
        }

        async def start_socket():
            sent = []
            incoming = asyncio.Queue()

            async def receive():
                return await incoming.get()

            async def send(message):
                sent.append(message)

            task = asyncio.create_task(self.app(scope, receive, send))
            await incoming.put({"type": "websocket.connect"})
            await asyncio.sleep(0.02)
            return task, incoming, sent

        task, incoming, sent = await start_socket()
        self.facade.set_touchpad_enabled(False)
        await asyncio.sleep(0.15)
        await incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, timeout=1)
        payloads = [json.loads(item["text"]) for item in sent if item["type"] == "websocket.send"]
        self.assertTrue(payloads)
        self.assertEqual(payloads[0]["type"], "state.snapshot")
        self.assertEqual(payloads[0]["version"], 1)
        self.assertTrue(any(payload["type"] == "state.updated" for payload in payloads[1:]))

        reconnect_task, reconnect_incoming, reconnect_sent = await start_socket()
        await reconnect_incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(reconnect_task, timeout=1)
        reconnect_payloads = [json.loads(item["text"]) for item in reconnect_sent if item["type"] == "websocket.send"]
        self.assertEqual(reconnect_payloads[0]["type"], "state.snapshot")

    async def test_websocket_rejects_unapproved_browser_origin(self):
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": "/api/v1/ws",
            "raw_path": b"/api/v1/ws",
            "query_string": b"",
            "headers": [(b"origin", b"https://example.invalid")],
            "client": ("test", 1),
            "server": ("test", 80),
            "subprotocols": [],
        }
        incoming = asyncio.Queue()
        sent = []

        async def receive():
            return await incoming.get()

        async def send(message):
            sent.append(message)

        task = asyncio.create_task(self.app(scope, receive, send))
        await incoming.put({"type": "websocket.connect"})
        await asyncio.wait_for(task, timeout=1)
        self.assertTrue(any(item["type"] == "websocket.close" and item["code"] == 1008 for item in sent))


if __name__ == "__main__":
    unittest.main()
