#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765/api/v1"


def request(path: str, *, method: str = "GET", payload: dict | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def main() -> int:
    run = request(
        "/controller/haptics/test",
        method="POST",
        payload={"left": 220, "right": 180, "duration_ms": 2200},
    )
    time.sleep(0.45)
    mid = request("/state")
    time.sleep(2.1)
    end = request("/state")
    print(
        json.dumps(
            {
                "run_status": run.get("status"),
                "mid_motors": mid.get("motors"),
                "mid_haptics_test": mid.get("haptics_test"),
                "mid_audio": mid.get("audio"),
                "end_motors": end.get("motors"),
                "end_haptics_test": end.get("haptics_test"),
                "end_audio": end.get("audio"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
