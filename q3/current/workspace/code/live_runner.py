from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import requests


class SimulatorError(RuntimeError):
    pass


class SimulatorClient:
    """Minimal client for the official CUMCM B jammer simulator HTTP API."""

    def __init__(self, robot_id: str, base_url: str = "http://127.0.0.1:2026", *, log_path: str | Path | None = None):
        self.robot_id = str(robot_id)
        self.base_url = base_url.rstrip("/")
        self.position = (0.0, 0.0)
        self.current_position_m = self.position
        self.receiver_channel = None
        self.current_channel = None
        self.last_response: dict = {}
        self.current_virtual_time_s = 0.0
        self.log_path = Path(log_path) if log_path is not None else None
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _base(self) -> dict:
        return {
            "arena_id": "default",
            "robot_id": self.robot_id,
            "request_id": uuid.uuid4().hex,
        }

    def _write_log(self, path: str, payload: dict, response: dict) -> None:
        if self.log_path is None:
            return
        rec = {
            "ts": time.time(),
            "path": path,
            "request": payload,
            "response": response,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")

    def post(self, path: str, payload: dict) -> dict:
        try:
            r = requests.post(self.base_url + path, json=payload, timeout=15)
            r.raise_for_status()
            body = r.json()
        except Exception as exc:
            raise SimulatorError(f"{path} 请求失败: {exc}") from exc
        if not isinstance(body, dict):
            raise SimulatorError(f"{path} 返回不是 JSON 对象: {body!r}")
        self.last_response = body
        if isinstance(body.get("virtual_time_s"), (int, float)):
            self.current_virtual_time_s = float(body["virtual_time_s"])
        self._write_log(path, payload, body)
        if body.get("accepted") is not True:
            raise SimulatorError(f"{path} 未执行: {body}")
        return body

    def enter(self) -> dict:
        return self.post("/enter", self._base())

    def measure(self, x: float, y: float, channel: int) -> dict:
        payload = self._base()
        payload.update({"position": {"x": float(x), "y": float(y)}, "channel": int(channel)})
        body = self.post("/measure", payload)
        self.position = (float(x), float(y))
        self.current_position_m = self.position
        self.receiver_channel = int(channel)
        self.current_channel = int(channel)
        return body

    def clear(self, x: float, y: float, channel: int) -> dict:
        payload = self._base()
        payload.update({"position": {"x": float(x), "y": float(y)}, "channel": int(channel)})
        body = self.post("/clear", payload)
        self.position = (float(x), float(y))
        self.current_position_m = self.position
        return body

    def exit(self) -> dict:
        return self.post("/exit", self._base())
