#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CUMCM 2026 B题（第3/4问）离线模拟器
===================================

目标：复刻官方练习模拟器的“算法可观测行为”，用于本地高频仿真和策略优化。

已按官方客户端静态逆向实现：
- practice-gen-v1 练习场景生成（给定 32-byte generator seed 可确定性重放）
- Q3 全向；Q4 D|N ~ Uniform{1,...,N}，再均匀抽 D 个频道为定向源
- 源中心均匀分布在半径 1770m 圆盘（1800m 目标区留 30m 外环）
- 接收半径在 [1000,1500]m 的整数微米上均匀抽取
- 定向源方向在 [0,360) 的整数微度上均匀抽取，180°闭半平面覆盖
- spatial-bearing-v1 空间相关示向误差场（150m 网格，BLAKE2b）
- 示向角 0.01° 量化及 ±1° 约束
- move / measure / clear 虚拟时间（整数微秒累计）
- /enter /measure /clear /exit 常用 HTTP JSON 接口与 request_id 幂等

默认行为：不传 seed 时每次启动使用 secrets.token_bytes(32)，因此每次案例不同，
与官方练习案例“本地 crypto/rand 生成 32-byte seed”的行为一致。

注意：
- 正式赛 sealed formal dataset 不在公开客户端中，不能由本模拟器预测。
- HTTP 层以“可跑选手算法”为优先，少数错误报文/连接关闭细节不追求逐字节一致。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import math
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

# -------------------- Official constants --------------------
TARGET_AREA_RADIUS_UM = 1_800_000_000
JAMMER_MAX_RADIUS_UM = 1_770_000_000
OUTER_EMPTY_RING_UM = 30_000_000
JAMMER_COUNT_MIN = 10
JAMMER_COUNT_MAX = 16
CHANNEL_MIN = 1
CHANNEL_MAX = 20
MAX_RECEIVE_MIN_UM = 1_000_000_000
MAX_RECEIVE_MAX_UM = 1_500_000_000

NEAR_DISTANCE_UM = 5_000_000
CLEAR_DISTANCE_UM = 20_000_000
MOVE_SPEED_UM_PER_S = 5_000_000
CHANNEL_SWITCH_DURATION_US = 1_000_000
MEASURE_DURATION_US = 5_000_000
CLEAR_SUCCESS_DURATION_US = 5_000_000
CLEAR_FAILURE_DURATION_US = 3_000_000
MAX_VIRTUAL_DURATION_US = 360_000_000_000
MAX_REAL_DURATION_S = 1200
DIRECTIONAL_BEAM_WIDTH_UDEG = 180_000_000
BEARING_NOISE_GRID_UM = 150_000_000
BEARING_ERROR_MAX_UDEG = 1_000_000
MAX_COORD_ABS_M = 2_000_000.0

PRACTICE_DOMAIN = b"practice-case-v1\x00"
MASK64 = (1 << 64) - 1


def go_round(x: float) -> int:
    """Go math.Round: nearest integer, ties away from zero."""
    if x >= 0:
        return math.floor(x + 0.5)
    return math.ceil(x - 0.5)


class CounterSource:
    """Official practice deterministic source: HMAC-SHA256 + label-local counters."""

    def __init__(self, key32: bytes):
        if len(key32) != 32:
            raise ValueError("generator seed must be exactly 32 bytes")
        self.key = key32
        self.counter: Dict[str, int] = {}

    def next(self, label: str) -> int:
        c = self.counter.get(label, 0)
        msg = PRACTICE_DOMAIN + label.encode("utf-8") + b"\x00" + c.to_bytes(8, "big")
        digest = hmac.new(self.key, msg, hashlib.sha256).digest()
        self.counter[label] = c + 1
        return int.from_bytes(digest[:8], "big")

    def uint_n(self, label: str, n: int) -> int:
        if n <= 0 or n > (1 << 63):
            raise ValueError("invalid uintN range")
        threshold = ((-n) & MASK64) % n
        while True:
            x = self.next(label)
            if x >= threshold:
                return x % n

    def float01_53(self, label: str) -> float:
        return (self.next(label) >> 11) * (2.0 ** -53)

    def shuffle(self, label: str, seq: list[int]) -> None:
        for i in range(len(seq) - 1, 0, -1):
            j = self.uint_n(label, i + 1)
            seq[i], seq[j] = seq[j], seq[i]


@dataclass
class Jammer:
    channel: int
    x_um: int
    y_um: int
    max_receive_um: int
    kind: str = "omni"  # omni | directional
    direction_udeg: Optional[int] = None
    cleared: bool = False

    def truth_dict(self, include_state: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "channel": self.channel,
            "x_um": self.x_um,
            "y_um": self.y_um,
            "x_m": self.x_um / 1e6,
            "y_m": self.y_um / 1e6,
            "max_receive_um": self.max_receive_um,
            "max_receive_m": self.max_receive_um / 1e6,
            "kind": self.kind,
        }
        if self.direction_udeg is not None:
            d["direction_udeg"] = self.direction_udeg
            d["direction_deg"] = self.direction_udeg / 1e6
        if include_state:
            d["cleared"] = self.cleared
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Jammer":
        return cls(
            channel=int(d["channel"]),
            x_um=int(d.get("x_um", go_round(float(d["x_m"]) * 1e6))),
            y_um=int(d.get("y_um", go_round(float(d["y_m"]) * 1e6))),
            max_receive_um=int(d.get("max_receive_um", go_round(float(d["max_receive_m"]) * 1e6))),
            kind=str(d.get("kind", "omni")),
            direction_udeg=(None if d.get("direction_udeg", d.get("direction_deg")) is None
                            else int(d.get("direction_udeg", go_round(float(d["direction_deg"]) * 1e6)))),
            cleared=bool(d.get("cleared", False)),
        )


@dataclass
class Scenario:
    problem_no: int
    generator_seed_hex: str
    noise_seed_hex: str
    jammers: list[Jammer]

    def to_dict(self, include_rules: bool = True, include_state: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": "scenario-v1",
            "ruleset_version": "rules-v1",
            "source": "practice_generated",
            "problem_no": self.problem_no,
            "generator_version": "practice-gen-v1",
            "generator_seed_hex": self.generator_seed_hex,
            "noise_seed_hex": self.noise_seed_hex,
            "jammers": [j.truth_dict(include_state=include_state) for j in self.jammers],
        }
        if include_rules:
            out["generation_rules"] = {
                "generator_rules_version": "practice-gen-rules-v1",
                "target_area_radius_um": TARGET_AREA_RADIUS_UM,
                "jammer_max_radius_um": JAMMER_MAX_RADIUS_UM,
                "outer_empty_ring_um": OUTER_EMPTY_RING_UM,
                "jammer_count_min": JAMMER_COUNT_MIN,
                "jammer_count_max": JAMMER_COUNT_MAX,
                "channel_min": CHANNEL_MIN,
                "channel_max": CHANNEL_MAX,
                "max_receive_min_um": MAX_RECEIVE_MIN_UM,
                "max_receive_max_um": MAX_RECEIVE_MAX_UM,
                "position_distribution": "uniform_disk_area",
                "max_receive_distribution": "uniform_integer_um",
                "problem4_directional_count_mode": "uniform_integer_one_to_count",
            }
            out["simulation_rules"] = {
                "simulation_rules_version": "simulation-rules-v1",
                "target_area_radius_um": TARGET_AREA_RADIUS_UM,
                "near_distance_um": NEAR_DISTANCE_UM,
                "clear_distance_um": CLEAR_DISTANCE_UM,
                "move_speed_um_per_s": MOVE_SPEED_UM_PER_S,
                "channel_switch_duration_us": CHANNEL_SWITCH_DURATION_US,
                "measure_duration_us": MEASURE_DURATION_US,
                "clear_success_duration_us": CLEAR_SUCCESS_DURATION_US,
                "clear_failure_duration_us": CLEAR_FAILURE_DURATION_US,
                "max_virtual_duration_us": MAX_VIRTUAL_DURATION_US,
                "directional_beam_width_udeg": DIRECTIONAL_BEAM_WIDTH_UDEG,
                "bearing_noise_model": "spatial-bearing-v1",
                "bearing_noise_grid_um": BEARING_NOISE_GRID_UM,
                "bearing_error_max_udeg": BEARING_ERROR_MAX_UDEG,
            }
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scenario":
        return cls(
            problem_no=int(d["problem_no"]),
            generator_seed_hex=str(d.get("generator_seed_hex", "00" * 32)),
            noise_seed_hex=str(d["noise_seed_hex"]),
            jammers=[Jammer.from_dict(x) for x in d["jammers"]],
        )


def inside_jammer_disk(x_um: int, y_um: int) -> bool:
    return x_um * x_um + y_um * y_um <= JAMMER_MAX_RADIUS_UM * JAMMER_MAX_RADIUS_UM


def generate_practice(problem_no: int, generator_seed: bytes) -> Scenario:
    if problem_no not in (3, 4):
        raise ValueError("problem_no must be 3 or 4")
    src = CounterSource(generator_seed)

    n = JAMMER_COUNT_MIN + src.uint_n("count", JAMMER_COUNT_MAX - JAMMER_COUNT_MIN + 1)
    channels = list(range(CHANNEL_MIN, CHANNEL_MAX + 1))
    src.shuffle("channels", channels)
    selected = sorted(channels[:n])

    directional: set[int] = set()
    if problem_no == 4:
        dcount = 1 + src.uint_n("directional-count", n)
        shuffled = selected.copy()
        src.shuffle("directional-channels", shuffled)
        directional = set(shuffled[:dcount])

    jammers: list[Jammer] = []
    for ch in selected:
        # Only retry when integer-micrometre rounding lands outside the 1770m disk.
        while True:
            u = src.float01_53(f"jammer/{ch}/radius")
            r_um = JAMMER_MAX_RADIUS_UM * math.sqrt(u)
            theta = 2.0 * math.pi * src.float01_53(f"jammer/{ch}/theta")
            x_um = go_round(r_um * math.cos(theta))
            y_um = go_round(r_um * math.sin(theta))
            if inside_jammer_disk(x_um, y_um):
                break

        receive_span = MAX_RECEIVE_MAX_UM - MAX_RECEIVE_MIN_UM + 1
        receive_um = MAX_RECEIVE_MIN_UM + src.uint_n(f"jammer/{ch}/receive", receive_span)

        if ch in directional:
            direction_udeg = src.uint_n(f"jammer/{ch}/direction", 360_000_000)
            kind = "directional"
        else:
            direction_udeg = None
            kind = "omni"

        jammers.append(Jammer(ch, x_um, y_um, receive_um, kind, direction_udeg))

    noise_seed = src.next("noise-seed")
    return Scenario(problem_no, generator_seed.hex(), f"{noise_seed:016x}", jammers)


# -------------------- spatial-bearing-v1 --------------------

def _noise_grid(seed_u64: int, channel: int, gx: int, gy: int) -> float:
    msg = f"{seed_u64}:{channel}:{gx}:{gy}".encode("utf-8")
    digest = hashlib.blake2b(msg, digest_size=8).digest()
    u64 = int.from_bytes(digest, "big")
    u = u64 / float(1 << 64)
    return 2.0 * u - 1.0


def _smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def bearing_error_degrees(noise_seed_hex: str, channel: int, x_m: float, y_m: float) -> float:
    seed_u64 = int(noise_seed_hex, 16)
    u = x_m / 150.0
    v = y_m / 150.0
    ix = math.floor(u)
    iy = math.floor(v)
    fx = min(1.0, max(0.0, u - ix))
    fy = min(1.0, max(0.0, v - iy))
    sx = _smoothstep(fx)
    sy = _smoothstep(fy)

    g00 = _noise_grid(seed_u64, channel, ix, iy)
    g10 = _noise_grid(seed_u64, channel, ix + 1, iy)
    g01 = _noise_grid(seed_u64, channel, ix, iy + 1)
    g11 = _noise_grid(seed_u64, channel, ix + 1, iy + 1)
    a = g00 + sx * (g10 - g00)
    b = g01 + sx * (g11 - g01)
    return a + sy * (b - a)


def normalize_deg(x: float) -> float:
    """Match Go normalizeDegrees: fmod -> add 360 if negative -> normalize -0.0."""
    x = math.fmod(x, 360.0)
    if x < 0.0:
        x += 360.0
    if x == 0.0:
        x = 0.0
    return x


def bearing_deg(x0: float, y0: float, x1: float, y1: float) -> float:
    return normalize_deg(math.degrees(math.atan2(y1 - y0, x1 - x0)))


def angle_delta_deg(a: float, b: float) -> float:
    """Shortest absolute angular separation, matching Go math.Remainder semantics."""
    return abs(math.remainder(a - b, 360.0))


def quantize_bearing_hundredths(true_deg: float, error_deg: float) -> int:
    noisy_h = go_round((true_deg + error_deg) * 100.0)
    lo_h = math.ceil((true_deg - 1.0) * 100.0)
    hi_h = math.floor((true_deg + 1.0) * 100.0)
    h = min(hi_h, max(lo_h, noisy_h))
    return h % 36000


# -------------------- Core simulation --------------------

@dataclass
class RunStats:
    measure_accepted_count: int = 0
    channel_switch_count: int = 0
    clear_failure_count: int = 0
    clear_success_count: int = 0
    action_count: int = 0


class Engine:
    def __init__(self, scenario: Scenario, record_trace: bool = True):
        # Copy state so reusing a Scenario object does not retain cleared flags.
        self.scenario = Scenario.from_dict(scenario.to_dict(include_rules=False, include_state=False))
        self.jammers: dict[int, Jammer] = {j.channel: j for j in self.scenario.jammers}
        self.x = 0.0
        self.y = 0.0
        self.receiver_channel = 1
        self.virtual_time_us = 0
        self.entered = False
        self.exited = False
        self.timed_out = False
        self.stats = RunStats()
        self.record_trace = record_trace
        self.trace: list[dict[str, Any]] = []
        self.real_enter_monotonic: Optional[float] = None

    @property
    def virtual_time_s(self) -> float:
        return self.virtual_time_us / 1_000_000.0

    @property
    def cleared_count(self) -> int:
        return sum(j.cleared for j in self.jammers.values())

    @property
    def jammer_count(self) -> int:
        return len(self.jammers)

    def summary(self) -> dict[str, Any]:
        directional = sum(j.kind == "directional" for j in self.jammers.values())
        return {
            "problem_no": self.scenario.problem_no,
            "jammer_count": self.jammer_count,
            "directional_count": directional,
            "omni_count": self.jammer_count - directional,
            "cleared_count": self.cleared_count,
            "measure_accepted_count": self.stats.measure_accepted_count,
            "channel_switch_count": self.stats.channel_switch_count,
            "clear_failure_count": self.stats.clear_failure_count,
            "clear_success_count": self.stats.clear_success_count,
            "virtual_time_us": self.virtual_time_us,
            "virtual_time_s": self.virtual_time_s,
            "position": {"x": self.x, "y": self.y},
            "receiver_channel": self.receiver_channel,
            "entered": self.entered,
            "exited": self.exited,
            "timed_out": self.timed_out,
        }

    def _can_act(self) -> bool:
        return self.entered and not self.exited and not self.timed_out

    def _finish_action(self) -> None:
        # Official rule: a request already fully accepted before cutoff may finish;
        # after its completion, no later action executes.
        if self.virtual_time_us >= MAX_VIRTUAL_DURATION_US:
            self.timed_out = True

    def _distance_to_jammer_m(self, j: Jammer, x: float, y: float) -> float:
        return math.hypot(j.x_um / 1e6 - x, j.y_um / 1e6 - y)

    def _move_to(self, x: float, y: float) -> tuple[float, int]:
        d_m = math.hypot(x - self.x, y - self.y)
        dt_us = go_round(d_m * 1_000_000_000_000.0 / MOVE_SPEED_UM_PER_S)
        self.virtual_time_us += dt_us
        self.x = 0.0 if x == 0.0 else x
        self.y = 0.0 if y == 0.0 else y
        return d_m, dt_us

    def _covered(self, j: Jammer, x: float, y: float) -> bool:
        dx_m = x - j.x_um / 1e6
        dy_m = y - j.y_um / 1e6
        d_m = math.hypot(dx_m, dy_m)
        if d_m * 1e6 > j.max_receive_um:
            return False
        if j.kind == "omni":
            return True
        if j.direction_udeg is None:
            return False
        # Recovered official zero-distance special case: source position is covered.
        if d_m == 0.0:
            return True
        source_to_robot = normalize_deg(math.degrees(math.atan2(dy_m, dx_m)))
        center = j.direction_udeg / 1e6
        return angle_delta_deg(source_to_robot, center) <= 90.000000001

    def _append_trace(self, entry: dict[str, Any]) -> None:
        if self.record_trace:
            self.trace.append(entry)

    def enter(self) -> dict[str, Any]:
        if self.entered or self.exited or self.timed_out:
            return {"accepted": False, "virtual_time_s": 0}
        self.entered = True
        self.real_enter_monotonic = time.monotonic()
        resp = {
            "accepted": True,
            "virtual_time_s": self.virtual_time_s,
            "max_virtual_duration_s": MAX_VIRTUAL_DURATION_US / 1e6,
            "max_real_duration_s": MAX_REAL_DURATION_S,
            "remaining_real_duration_s": MAX_REAL_DURATION_S,
        }
        self._append_trace({"action": "enter", "virtual_time_us_after": self.virtual_time_us, "response": resp.copy()})
        return resp

    def measure(self, x: float, y: float, channel: int) -> dict[str, Any]:
        if not self._can_act():
            return {"accepted": False, "virtual_time_s": 0}
        before_t = self.virtual_time_us
        before_pos = (self.x, self.y)
        before_ch = self.receiver_channel
        d_m, move_us = self._move_to(x, y)
        switched = channel != self.receiver_channel
        if switched:
            self.virtual_time_us += CHANNEL_SWITCH_DURATION_US
            self.stats.channel_switch_count += 1
        self.receiver_channel = channel
        self.virtual_time_us += MEASURE_DURATION_US
        self.stats.measure_accepted_count += 1
        self.stats.action_count += 1

        j = self.jammers.get(channel)
        if j is None or j.cleared or not self._covered(j, x, y):
            resp: dict[str, Any] = {
                "accepted": True,
                "virtual_time_s": self.virtual_time_s,
                "measure_result": "no_signal",
            }
            true = None
            err = None
        else:
            distance_m = self._distance_to_jammer_m(j, x, y)
            if distance_m * 1e6 <= NEAR_DISTANCE_UM:
                resp = {
                    "accepted": True,
                    "virtual_time_s": self.virtual_time_s,
                    "measure_result": "near",
                }
                true = None
                err = None
            else:
                true = bearing_deg(x, y, j.x_um / 1e6, j.y_um / 1e6)
                err = bearing_error_degrees(self.scenario.noise_seed_hex, channel, x, y)
                h = quantize_bearing_hundredths(true, err)
                resp = {
                    "accepted": True,
                    "virtual_time_s": self.virtual_time_s,
                    "measure_result": "direction",
                    "svd_deg": h / 100.0,
                }

        self._append_trace({
            "action": "measure",
            "channel": channel,
            "position": {"x": x, "y": y},
            "position_before": {"x": before_pos[0], "y": before_pos[1]},
            "receiver_channel_before": before_ch,
            "channel_switched": switched,
            "move_distance_m": d_m,
            "move_time_us": move_us,
            "action_time_us": MEASURE_DURATION_US + (CHANNEL_SWITCH_DURATION_US if switched else 0),
            "virtual_time_us_before": before_t,
            "virtual_time_us_after": self.virtual_time_us,
            "true_bearing_deg": true,
            "bearing_error_deg": err,
            "response": resp.copy(),
        })
        self._finish_action()
        return resp

    def clear(self, x: float, y: float, channel: int) -> dict[str, Any]:
        if not self._can_act():
            return {"accepted": False, "virtual_time_s": 0}
        before_t = self.virtual_time_us
        before_pos = (self.x, self.y)
        d_m, move_us = self._move_to(x, y)
        j = self.jammers.get(channel)
        distance_to_target_m: Optional[float] = None
        if j is not None:
            distance_to_target_m = self._distance_to_jammer_m(j, x, y)

        success = (
            j is not None
            and not j.cleared
            and distance_to_target_m is not None
            and distance_to_target_m * 1e6 <= CLEAR_DISTANCE_UM
        )
        if success:
            assert j is not None
            j.cleared = True
            action_us = CLEAR_SUCCESS_DURATION_US
            self.virtual_time_us += action_us
            self.stats.clear_success_count += 1
            result = "success"
        else:
            action_us = CLEAR_FAILURE_DURATION_US
            self.virtual_time_us += action_us
            self.stats.clear_failure_count += 1
            result = "no_target_in_range"
        self.stats.action_count += 1

        resp = {"accepted": True, "virtual_time_s": self.virtual_time_s, "clear_result": result}
        self._append_trace({
            "action": "clear",
            "channel": channel,
            "position": {"x": x, "y": y},
            "position_before": {"x": before_pos[0], "y": before_pos[1]},
            "move_distance_m": d_m,
            "move_time_us": move_us,
            "action_time_us": action_us,
            "virtual_time_us_before": before_t,
            "virtual_time_us_after": self.virtual_time_us,
            "distance_to_target_m": distance_to_target_m,
            "response": resp.copy(),
        })
        self._finish_action()
        return resp

    def exit(self) -> dict[str, Any]:
        if not self._can_act():
            return {"accepted": False, "virtual_time_s": 0}
        self.exited = True
        resp = {"accepted": True, "virtual_time_s": self.virtual_time_s, "exit_reason": "user_exit"}
        self._append_trace({"action": "exit", "virtual_time_us_after": self.virtual_time_us, "response": resp.copy()})
        return resp

    def save_trace(self, path: str | os.PathLike[str]) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for entry in self.trace:
                f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


# -------------------- HTTP compatibility layer --------------------

class DuplicateKeyError(ValueError):
    pass


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise DuplicateKeyError(k)
        out[k] = v
    return out


def _valid_id_string(v: Any) -> bool:
    if not isinstance(v, str) or not v or len(v) > 256:
        return False
    # Conservative approximation of official rejection of control/format chars.
    return all(ord(c) >= 0x20 and c not in "\x7f" for c in v)


class SimulatorHTTP:
    def __init__(self, engine: Engine, robot_id: Optional[str] = None, bind_first_robot: bool = True):
        self.engine = engine
        self.robot_id = robot_id
        self.bind_first_robot = bind_first_robot
        self.seen: dict[str, tuple[str, bytes, int, dict[str, Any]]] = {}

    def _identity_ok(self, body: dict[str, Any], path: str) -> bool:
        if body.get("arena_id") != "default":
            return False
        rid = body.get("robot_id")
        if not _valid_id_string(rid):
            return False
        if self.robot_id is None and self.bind_first_robot and path == "/enter":
            self.robot_id = rid
        if self.robot_id is not None and rid != self.robot_id:
            return False
        return True

    def execute(self, path: str, body_raw: bytes) -> tuple[int, dict[str, Any]]:
        try:
            body = json.loads(body_raw.decode("utf-8"), object_pairs_hook=_no_duplicate_object)
        except (Exception, DuplicateKeyError):
            return 400, {"accepted": False, "virtual_time_s": 0}
        if not isinstance(body, dict):
            return 400, {"accepted": False, "virtual_time_s": 0}

        request_id = body.get("request_id")
        robot_id = body.get("robot_id")
        if not _valid_id_string(request_id) or not _valid_id_string(robot_id):
            return 400, {"accepted": False, "virtual_time_s": 0}

        canon = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if request_id in self.seen:
            old_path, old_canon, status, old_resp = self.seen[request_id]
            if old_path != path or old_canon != canon:
                return 409, {"accepted": False, "virtual_time_s": 0}
            return status, dict(old_resp)

        if path in ("/enter", "/exit"):
            if set(body) != {"arena_id", "robot_id", "request_id"}:
                return 200, {"accepted": False, "virtual_time_s": 0}
        elif path in ("/measure", "/clear"):
            if set(body) != {"arena_id", "robot_id", "request_id", "position", "channel"}:
                return 200, {"accepted": False, "virtual_time_s": 0}
        else:
            return 404, {"accepted": False, "virtual_time_s": 0}

        if not self._identity_ok(body, path):
            return 200, {"accepted": False, "virtual_time_s": 0}

        if path == "/enter":
            resp = self.engine.enter()
        elif path == "/exit":
            resp = self.engine.exit()
        else:
            pos = body.get("position")
            if not isinstance(pos, dict) or set(pos) != {"x", "y"}:
                return 200 if isinstance(pos, dict) else 400, {"accepted": False, "virtual_time_s": 0}
            ch = body.get("channel")
            if isinstance(ch, bool) or not isinstance(ch, (int, float)):
                return 400, {"accepted": False, "virtual_time_s": 0}
            chf = float(ch)
            if not math.isfinite(chf) or int(chf) != chf or not (CHANNEL_MIN <= int(chf) <= CHANNEL_MAX):
                return 400, {"accepted": False, "virtual_time_s": 0}
            channel = int(chf)
            try:
                # bool is a JSON number in Python's type hierarchy but should not be accepted as coordinate.
                if isinstance(pos["x"], bool) or isinstance(pos["y"], bool):
                    raise ValueError
                x = float(pos["x"])
                y = float(pos["y"])
            except Exception:
                return 400, {"accepted": False, "virtual_time_s": 0}
            if not math.isfinite(x) or not math.isfinite(y) or abs(x) > MAX_COORD_ABS_M or abs(y) > MAX_COORD_ABS_M:
                return 400, {"accepted": False, "virtual_time_s": 0}
            resp = self.engine.measure(x, y, channel) if path == "/measure" else self.engine.clear(x, y, channel)

        status = 200
        if resp.get("accepted") is True:
            self.seen[request_id] = (path, canon, status, dict(resp))
        return status, resp


# -------------------- CLI helpers --------------------

def _seed_from_args(args: argparse.Namespace, run_index: int = 0) -> bytes:
    exact = getattr(args, "generator_seed_hex", None)
    local_seed = getattr(args, "seed", None)
    if exact:
        if run_index:
            raise ValueError("--generator-seed-hex represents one exact case only")
        s = exact.strip().lower()
        if len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
            raise ValueError("generator seed must be 64 hex chars")
        return bytes.fromhex(s)
    if local_seed is not None:
        # Deterministic local mapping only. Official itself uses crypto/rand bytes.
        return hashlib.sha256(f"cumcm-offline-generator-key:{int(local_seed) + run_index}".encode()).digest()
    return secrets.token_bytes(32)


def _load_or_generate(args: argparse.Namespace, run_index: int = 0) -> Scenario:
    scenario_path = getattr(args, "scenario", None)
    if scenario_path:
        if run_index:
            raise ValueError("--scenario can only represent one case")
        with open(scenario_path, "r", encoding="utf-8") as f:
            return Scenario.from_dict(json.load(f))
    return generate_practice(args.problem, _seed_from_args(args, run_index))


def _write_json(path: str | os.PathLike[str], obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def cmd_show(args: argparse.Namespace) -> None:
    sc = _load_or_generate(args)
    obj = sc.to_dict(include_rules=True)
    if args.out:
        _write_json(args.out, obj)
        print(args.out)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_sample(args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for i in range(args.runs):
        sc = _load_or_generate(args, i)
        nd = sum(j.kind == "directional" for j in sc.jammers)
        rows.append({
            "run": i,
            "generator_seed_hex": sc.generator_seed_hex,
            "noise_seed_hex": sc.noise_seed_hex,
            "jammer_count": len(sc.jammers),
            "omni_count": len(sc.jammers) - nd,
            "directional_count": nd,
            "channels": " ".join(str(j.channel) for j in sc.jammers),
        })
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(args.out)
    else:
        print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_noise(args: argparse.Namespace) -> None:
    e = bearing_error_degrees(args.noise_seed_hex, args.channel, args.x, args.y)
    print(f"error_deg={e:.15f}")
    if args.true_bearing is not None:
        h = quantize_bearing_hundredths(args.true_bearing, e)
        print(f"svd_deg={h / 100:.2f}")


def _print_case_summary(sc: Scenario) -> None:
    d = sum(j.kind == "directional" for j in sc.jammers)
    print(f"problem={sc.problem_no} N={len(sc.jammers)} omni={len(sc.jammers)-d} directional={d}")
    print(f"generator_seed_hex={sc.generator_seed_hex}")
    print(f"noise_seed_hex={sc.noise_seed_hex}")


def cmd_serve(args: argparse.Namespace) -> None:
    sc = _load_or_generate(args)
    engine = Engine(sc, record_trace=True)
    strict_robot_id = None if args.robot_id in (None, "", "*") else args.robot_id
    sim = SimulatorHTTP(engine, robot_id=strict_robot_id, bind_first_robot=True)

    if args.truth_out:
        _write_json(args.truth_out, sc.to_dict(include_rules=True))

    class Handler(BaseHTTPRequestHandler):
        server_version = "CUMCM-Offline-Sim/3.0"

        def log_message(self, fmt: str, *a: Any) -> None:
            if not args.quiet:
                super().log_message(fmt, *a)

        def do_POST(self) -> None:
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = 0
            if n < 0 or n > 65536:
                self.send_response(413)
                self.end_headers()
                return
            raw = self.rfile.read(n)
            status, resp = sim.execute(self.path, raw)
            resp = dict(resp)
            resp.setdefault("real_timestamp_ms", int(time.time() * 1000))
            out = json.dumps(resp, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

            if args.trace_out and engine.exited:
                engine.save_trace(args.trace_out)
            if args.summary_out and engine.exited:
                _write_json(args.summary_out, engine.summary())

    _print_case_summary(sc)
    print(f"HTTP: http://127.0.0.1:{args.port}")
    if strict_robot_id is None:
        print("robot_id: first successful /enter binds the supplied robot_id (drop-in mode)")
    else:
        print(f"robot_id: strict {strict_robot_id}")
    if args.show_truth:
        print(json.dumps([j.truth_dict() for j in sc.jammers], ensure_ascii=False, indent=2))
    print("Ctrl+C stops server.")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if args.trace_out:
            engine.save_trace(args.trace_out)
            print(f"trace -> {args.trace_out}")
        if args.summary_out:
            _write_json(args.summary_out, engine.summary())
            print(f"summary -> {args.summary_out}")
        print(json.dumps(engine.summary(), ensure_ascii=False, indent=2))


def _assert_close(a: float, b: float, eps: float = 1e-12) -> None:
    if abs(a - b) > eps:
        raise AssertionError(f"{a!r} != {b!r}")


def cmd_selftest(args: argparse.Namespace) -> None:
    checks: list[tuple[str, bool]] = []

    # 1) Official timing example: 0 -> 105 -> 111 -> 194 -> 199.
    sc = Scenario(4, "00" * 32, "0000000000000000", [])
    e = Engine(sc)
    checks.append(("enter time = 0", e.enter()["virtual_time_s"] == 0))
    checks.append(("measure (300,400), ch1 = 105", e.measure(300, 400, 1)["virtual_time_s"] == 105))
    checks.append(("same point ch2 = 111", e.measure(300, 400, 2)["virtual_time_s"] == 111))
    checks.append(("failed clear (300,0) = 194", e.clear(300, 0, 3)["virtual_time_s"] == 194))
    checks.append(("clear does not switch receiver; ch2 measure = 199", e.measure(300, 0, 2)["virtual_time_s"] == 199))

    # 2) Directional boundary is closed (±90 degrees accepted).
    j = Jammer(1, 0, 0, 1_500_000_000, "directional", 0)
    e2 = Engine(Scenario(4, "00" * 32, "0000000000000000", [j]))
    checks.append(("directional +90 boundary covered", e2._covered(e2.jammers[1], 0, 1000)))
    checks.append(("directional -90 boundary covered", e2._covered(e2.jammers[1], 0, -1000)))
    checks.append(("directional rear half-plane rejected", not e2._covered(e2.jammers[1], -1000, 0)))

    # 3) Zero-distance directional special case => near.
    e3 = Engine(Scenario(4, "00" * 32, "0000000000000000", [Jammer(1, 0, 0, 1_000_000_000, "directional", 180_000_000)]))
    e3.enter()
    checks.append(("directional source at same point returns near", e3.measure(0, 0, 1)["measure_result"] == "near"))

    # 4) Same point/channel noise is deterministic.
    n1 = bearing_error_degrees("0123456789abcdef", 7, 123.4, -567.8)
    n2 = bearing_error_degrees("0123456789abcdef", 7, 123.4, -567.8)
    checks.append(("spatial noise deterministic", n1 == n2 and -1.0 <= n1 <= 1.0))

    # 4b) Official bearingnoise.grid calls blake2b.New(8, nil), not BLAKE2b-512[:8].
    # This fixed vector catches that subtle but important distinction.
    gv = _noise_grid(123456789, 7, 1, -2)
    checks.append(("noise grid uses BLAKE2b digest_size=8", abs(gv - (-0.5732823192927411)) < 1e-15))

    # 5) Given generator seed, generation is deterministic.
    key = bytes.fromhex("11" * 32)
    a = generate_practice(4, key).to_dict(include_rules=False)
    b = generate_practice(4, key).to_dict(include_rules=False)
    checks.append(("practice generator deterministic", a == b))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), name)
    if failed:
        raise SystemExit(f"selftest failed: {failed}")
    print(f"ALL PASS ({len(checks)} checks)")


def _add_case_source_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--problem", type=int, choices=[3, 4], default=4)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--generator-seed-hex", default=None, help="exact 32-byte practice generator seed (64 hex chars)")
    g.add_argument("--seed", type=int, default=None, help="local deterministic seed; omit for crypto-random case")
    g.add_argument("--scenario", default=None, help="load an exported scenario JSON instead of generating")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CUMCM2026 B Q3/Q4 official-like offline simulator")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="generate/load one case and show/export truth")
    _add_case_source_args(s)
    s.add_argument("--out", default="")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("sample", help="sample many cases to inspect N/D/channel distribution")
    _add_case_source_args(s)
    s.add_argument("--runs", type=int, default=200)
    s.add_argument("--out", default="")
    s.set_defaults(func=cmd_sample)

    s = sub.add_parser("noise", help="evaluate spatial-bearing-v1 error at a point")
    s.add_argument("--noise-seed-hex", required=True)
    s.add_argument("--channel", type=int, required=True)
    s.add_argument("--x", type=float, required=True)
    s.add_argument("--y", type=float, required=True)
    s.add_argument("--true-bearing", type=float, default=None)
    s.set_defaults(func=cmd_noise)

    s = sub.add_parser("serve", help="run drop-in local HTTP simulator")
    _add_case_source_args(s)
    s.add_argument("--port", type=int, default=2026)
    s.add_argument("--robot-id", default="*", help="strict robot_id; '*' binds first /enter and accepts existing contestant code")
    s.add_argument("--show-truth", action="store_true")
    s.add_argument("--truth-out", default="truth.json")
    s.add_argument("--trace-out", default="trace.jsonl")
    s.add_argument("--summary-out", default="run_summary.json")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("selftest", help="run regression tests including the official timing example")
    s.set_defaults(func=cmd_selftest)
    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
