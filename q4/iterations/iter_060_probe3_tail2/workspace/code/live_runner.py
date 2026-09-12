"""与官方环境模拟器通信的最小安全运行器。

用法（必须在 workspace 目录执行）：
    python code/live_runner.py --robot-id 202613001114 --mode demo

demo 模式只发送题面给出的四个接口示例，适合确认连接和程序格式；
不会冒充官方结果，也不会把离线随机场景当成真实测试结果。
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any

import requests


class SimulatorError(RuntimeError):
    pass


class SimulatorClient:
    def __init__(self, robot_id: str, base_url: str = "http://127.0.0.1:2026", timeout: float = 8.0,
                 log_path: str | Path = "figures/live_api_log.jsonl"):
        self.robot_id = str(robot_id)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.log_path = Path(log_path)
        self.counter = 0
        self.position = (0.0, 0.0)
        self.last_response: dict[str, Any] | None = None

    def _request_id(self, label: str) -> str:
        self.counter += 1
        return f"{label}-{self.counter}-{uuid.uuid4().hex[:8]}"

    def _base(self, label: str) -> dict[str, Any]:
        return {"arena_id": "default", "robot_id": self.robot_id,
                "request_id": self._request_id(label)}

    def _append_log(self, path: str, payload: dict[str, Any], body: dict[str, Any] | None,
                    error: str | None = None) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"path": path, "request": payload}
        if body is not None:
            record["response"] = body
        if error is not None:
            record["error"] = error
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def post(self, path: str, payload: dict[str, Any], *, retry_network_once: bool = True) -> dict[str, Any]:
        """发送一次请求；仅网络异常时用完全相同的 request_id/payload 重试。"""
        url = self.base_url + path
        # 模拟器点击“开始测试”后通常有几秒准备/倒计时；网络层关闭
        # 连接属于可重试的传输失败，使用同一 request_id 重发是幂等安全的。
        attempts = 8 if retry_network_once else 1
        for attempt in range(attempts):
            try:
                response = requests.post(url, json=payload,
                                         headers={"Content-Type": "application/json"},
                                         timeout=self.timeout)
                try:
                    body = response.json()
                except ValueError as exc:
                    raise SimulatorError(f"{path} 返回非 JSON，HTTP {response.status_code}") from exc
                if response.status_code != 200:
                    self._append_log(path, payload, body, f"HTTP {response.status_code}")
                    raise SimulatorError(f"{path} HTTP {response.status_code}: {body}")
                if body.get("accepted") is not True:
                    self._append_log(path, payload, body, "accepted=false")
                    raise SimulatorError(f"{path} 未执行: {body}")
                self.last_response = body
                self._append_log(path, payload, body)
                return body
            except requests.RequestException:
                if attempt + 1 >= attempts:
                    self._append_log(path, payload, None, "network request failed")
                    raise
                time.sleep(1.0)
        raise AssertionError("unreachable")

    def enter(self) -> dict[str, Any]:
        return self.post("/enter", self._base("enter"))

    def measure(self, x: float, y: float, channel: int) -> dict[str, Any]:
        if not 1 <= int(channel) <= 20:
            raise ValueError("channel 必须为 1..20")
        p = self._base("measure")
        p.update({"position": {"x": float(x), "y": float(y)}, "channel": int(channel)})
        body = self.post("/measure", p)
        self.position = (float(x), float(y))
        return body

    def clear(self, x: float, y: float, channel: int) -> dict[str, Any]:
        if not 1 <= int(channel) <= 20:
            raise ValueError("channel 必须为 1..20")
        p = self._base("clear")
        p.update({"position": {"x": float(x), "y": float(y)}, "channel": int(channel)})
        body = self.post("/clear", p)
        self.position = (float(x), float(y))
        return body

    def exit(self) -> dict[str, Any]:
        return self.post("/exit", self._base("exit"))


def demo(client: SimulatorClient) -> None:
    """题面示例动作：用于验证接口，不代表 Q3/Q4 求解策略。"""
    entered = client.enter()
    print("已进入，剩余真实时间：", entered.get("remaining_real_duration_s"), "秒")
    actions = [
        ("measure", (300, 400, 1)),
        ("measure", (300, 400, 2)),
        ("clear", (300, 0, 3)),
        ("measure", (300, 0, 2)),
    ]
    for kind, (x, y, channel) in actions:
        body = getattr(client, kind)(x, y, channel)
        print(kind, channel, body.get("measure_result", body.get("clear_result", body)))
    print("退出：", client.exit().get("exit_reason"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot-id", required=True, help="当前模拟器右上角显示的队号")
    ap.add_argument("--base-url", default="http://127.0.0.1:2026")
    ap.add_argument("--mode", choices=["demo"], default="demo")
    ap.add_argument("--log", default="figures/live_api_log.jsonl")
    args = ap.parse_args()
    client = SimulatorClient(args.robot_id, args.base_url, log_path=args.log)
    try:
        demo(client)
    except Exception as exc:
        print(f"运行失败：{exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
