import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from dualsense_companion.api.origins import DEFAULT_ALLOWED_ORIGINS, validate_allowed_origins, validate_origin
from dualsense_companion.api.server import validate_loopback_host
from dualsense_companion.core.config import ConfigRepository
from dualsense_companion.core.facade import CoreFacade
from dualsense_companion.core.product import ProductService
from dualsense_companion.core.remote import RemoteAccessManager


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

    def test_frontend_origin_policy_is_explicit_and_local_only(self):
        self.assertEqual(validate_origin("http://localhost:5173"), "http://localhost:5173")
        self.assertEqual(validate_origin("http://tauri.localhost"), "http://tauri.localhost")
        self.assertEqual(validate_allowed_origins(DEFAULT_ALLOWED_ORIGINS), DEFAULT_ALLOWED_ORIGINS)
        for origin in (
            "*",
            "https://example.invalid",
            "http://localhost:3000",
            "http://localhost:5173/app",
            "http://localhost:5173?remote=true",
        ):
            with self.assertRaises(ValueError, msg=origin):
                validate_origin(origin)

    async def test_http_origin_policy_allows_approved_origin_and_blocks_remote_origin(self):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            approved = await client.get(
                "/api/v1/health",
                headers={"Origin": "http://localhost:5173"},
            )
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.headers.get("access-control-allow-origin"), "http://localhost:5173")

            preflight = await client.options(
                "/api/v1/config",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(preflight.headers.get("access-control-allow-origin"), "http://localhost:5173")

            rejected = await client.get(
                "/api/v1/health",
                headers={"Origin": "https://example.invalid"},
            )
            self.assertEqual(rejected.status_code, 403)
            self.assertEqual(rejected.json()["error"]["code"], "api.origin_rejected")
            self.assertNotIn("access-control-allow-origin", rejected.headers)

            # CORS alone would not prevent a malicious browser from sending a
            # simple cross-origin POST. The origin guard must reject it before
            # a state-changing endpoint reaches the facade.
            blocked_command = await client.post(
                "/api/v1/profiles/Heavy%20Impacts/load",
                headers={"Origin": "https://example.invalid", "Content-Type": "text/plain"},
            )
            self.assertEqual(blocked_command.status_code, 403)
            self.assertEqual(self.facade.snapshot().active_profile, "Default")

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
            self.assertEqual(invalid.json()["error"]["code"], "api.validation")
            self.assertIn("rumble.gate", invalid.json()["error"]["fields"])
            below_range = await client.patch("/api/v1/config", json={"rumble": {"gamma": 0.005}})
            self.assertEqual(below_range.status_code, 422)
            self.assertEqual(below_range.json()["error"]["code"], "api.validation")
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

    async def test_p5_exclusive_candidates_and_duplicate_contracts(self):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            capabilities = await client.get("/api/v1/exclusive/capabilities")
            self.assertEqual(capabilities.status_code, 200)
            self.assertFalse(capabilities.json()["provider_available"])
            self.assertFalse(capabilities.json()["physical_suppression_verified"])

            status = await client.get("/api/v1/exclusive/status")
            self.assertEqual(status.status_code, 200)
            self.assertFalse(status.json()["enabled"])
            self.assertTrue(status.json()["double_input_risk"])

            diagnostic = await client.get("/api/v1/diagnostics/duplicate-input")
            self.assertEqual(diagnostic.status_code, 200)
            self.assertFalse(diagnostic.json()["risk"])
            self.assertTrue(diagnostic.json()["physical_visible"])
            self.assertFalse(diagnostic.json()["virtual_active"])

            candidates = await client.get("/api/v1/games/candidates")
            self.assertEqual(candidates.status_code, 200)
            self.assertEqual(candidates.json(), {"candidates": []})

            state = await client.get("/api/v1/state")
            self.assertEqual(state.status_code, 200)
            self.assertIn("exclusive", state.json())
            self.assertIn("player_leds", state.json())

    async def test_p4_remote_http_requires_origin_and_session_cookie(self):
        import httpx

        manager = RemoteAccessManager()
        product = ProductService(self.facade, remote=manager)
        app = create_app(self.facade, product=product)
        transport = httpx.ASGITransport(app=app)
        local_origin = "http://localhost:5173"
        remote_origin = "https://remote.example"
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            challenge_response = await client.post(
                "/api/v1/remote/pairing/start",
                headers={"Origin": local_origin},
                json={"origin_hint": remote_origin},
            )
            self.assertEqual(challenge_response.status_code, 200)
            challenge = challenge_response.json()

            complete = await client.post(
                "/api/v1/remote/pairing/complete",
                headers={"Origin": remote_origin},
                json={
                    "pairing_id": challenge["pairing_id"],
                    "code": challenge["code"],
                    "origin": remote_origin,
                },
            )
            self.assertEqual(complete.status_code, 200)
            cookie = complete.headers["set-cookie"].split(";", 1)[0]
            self.assertIn("HttpOnly", complete.headers["set-cookie"])
            self.assertIn("Secure", complete.headers["set-cookie"])

            unauthorized = await client.get(
                "/api/v1/health",
                headers={"Origin": remote_origin},
            )
            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(unauthorized.headers["access-control-allow-origin"], remote_origin)

            authorized = await client.get(
                "/api/v1/health",
                headers={"Origin": remote_origin, "Cookie": cookie},
            )
            self.assertEqual(authorized.status_code, 200)
            self.assertEqual(authorized.headers["access-control-allow-origin"], remote_origin)

            # A tunnel can forward a non-browser client without an Origin
            # header. The registered Host still identifies the remote origin
            # and must require the same cookie session.
            host_unauthorized = await client.get(
                "/api/v1/health",
                headers={"Host": "remote.example"},
            )
            self.assertEqual(host_unauthorized.status_code, 401)
            host_authorized = await client.get(
                "/api/v1/health",
                headers={"Host": "remote.example", "Cookie": cookie},
            )
            self.assertEqual(host_authorized.status_code, 200)

            # With remote access enabled, an origin-less request whose Host is
            # neither loopback nor a registered origin must not fall through to
            # trusted local access.
            unknown_host = await client.get(
                "/api/v1/health",
                headers={"Host": "evil.example"},
            )
            self.assertEqual(unknown_host.status_code, 401)

            # A genuine loopback origin-less client keeps local trust.
            local_loopback = await client.get(
                "/api/v1/health",
                headers={"Host": "127.0.0.1:8765"},
            )
            self.assertEqual(local_loopback.status_code, 200)

            oversized = await client.post(
                "/api/v1/remote/disable",
                headers={"Origin": remote_origin, "Cookie": cookie, "Content-Length": str(300_000)},
                content=b"{}",
            )
            self.assertEqual(oversized.status_code, 413)

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

    async def test_controller_lab_endpoints_are_strict_and_capability_gated(self):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            telemetry = await client.get("/api/v1/controller/telemetry")
            self.assertEqual(telemetry.status_code, 200)
            self.assertIn("sticks", telemetry.json()["input"])
            self.assertIn("touch0", telemetry.json()["input"])

            disconnected_lightbar_read = await client.get("/api/v1/controller/lightbar")
            self.assertEqual(disconnected_lightbar_read.status_code, 422)
            self.assertEqual(disconnected_lightbar_read.json()["error"]["code"], "controller.unavailable")

            extra = await client.put(
                "/api/v1/controller/lightbar",
                json={"r": 1, "g": 2, "b": 3, "unexpected": True},
            )
            self.assertEqual(extra.status_code, 422)
            self.assertEqual(extra.json()["error"]["code"], "api.validation")

            disconnected_lightbar = await client.put(
                "/api/v1/controller/lightbar",
                json={"r": 1, "g": 2, "b": 3},
            )
            self.assertEqual(disconnected_lightbar.status_code, 422)
            self.assertEqual(disconnected_lightbar.json()["error"]["code"], "controller.unavailable")

            trigger_preview = await client.post(
                "/api/v1/controller/triggers/preview",
                json={"left": {}, "right": {}, "duration_ms": 20},
            )
            self.assertEqual(trigger_preview.status_code, 422)
            self.assertEqual(trigger_preview.json()["error"]["code"], "controller.unavailable")

            coerced_calibration = await client.put(
                "/api/v1/controller/sticks/calibration",
                json={
                    "left_deadzone": "0.1",
                    "right_deadzone": 0.1,
                    "left_center_x": 0,
                    "left_center_y": 0,
                    "right_center_x": 0,
                    "right_center_y": 0,
                },
            )
            self.assertEqual(coerced_calibration.status_code, 422)

            drift_estimate = await client.post(
                "/api/v1/controller/sticks/calibration/estimate",
                json={
                    "samples": [{"left_x": 0.04, "left_y": -0.03, "right_x": -0.02, "right_y": 0.01} for _ in range(60)]
                },
            )
            self.assertEqual(drift_estimate.status_code, 200)
            estimate = drift_estimate.json()
            self.assertEqual(estimate["samples"], 60)
            self.assertAlmostEqual(estimate["left"]["drift_radius"], 0.05)
            self.assertEqual(estimate["left"]["recommended_deadzone"], 0.02)
            self.assertAlmostEqual(estimate["recommended_calibration"]["left_center_x"], 0.04)

    async def test_full_profile_export_import_and_rejected_import(self):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            exported = await client.get("/api/v1/profiles/Default/export")
            self.assertEqual(exported.status_code, 200)
            profile = exported.json()
            self.assertEqual(profile["schema_version"], 2)

            saved = await client.put("/api/v1/profiles/API Lab", json=profile)
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["full_profile"]["schema_version"], 2)

            overwrite_required = await client.put("/api/v1/profiles/API Lab", json=profile)
            self.assertEqual(overwrite_required.status_code, 422)
            self.assertEqual(overwrite_required.json()["error"]["code"], "profile.overwrite_required")

            imported = await client.post(
                "/api/v1/profiles/import",
                json={"content": json.dumps({**profile, "name": "Imported Lab"})},
            )
            self.assertEqual(imported.status_code, 200)
            self.assertEqual(imported.json()["name"], "Imported Lab")

            malformed = await client.post("/api/v1/profiles/import", json={"content": "{broken"})
            self.assertEqual(malformed.status_code, 422)
            self.assertEqual(malformed.json()["error"]["code"], "profile.invalid")

            await client.delete("/api/v1/profiles/API%20Lab")
            await client.delete("/api/v1/profiles/Imported%20Lab")

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

    async def test_websocket_accepts_approved_browser_origin(self):
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": "/api/v1/ws",
            "raw_path": b"/api/v1/ws",
            "query_string": b"",
            "headers": [(b"origin", b"http://127.0.0.1:5173")],
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
        await asyncio.sleep(0.02)
        await incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, timeout=1)
        self.assertTrue(any(item["type"] == "websocket.accept" for item in sent))


if __name__ == "__main__":
    unittest.main()
