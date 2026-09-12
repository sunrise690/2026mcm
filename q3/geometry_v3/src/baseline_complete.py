"""第三问完整清除候选：复用快照策略，以连续域证书替代概率软结束。

控制器仅调用公开的 enter/measure/clear/exit 以及位置、当前频道和响应。
证明条件按题面最保守的 1800 米目标圆域、1000 米最小接收半径处理，
不使用离线模拟器的源位置、实际源数、接收半径、种子或生成分布。
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

_BASELINE_PATH = Path(__file__).resolve().with_name("baseline_commit10.py")
_spec = importlib.util.spec_from_file_location("_q3_complete_original", _BASELINE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"不能加载第三问基线: {_BASELINE_PATH}")
_base = importlib.util.module_from_spec(_spec)
exec(compile(_BASELINE_PATH.read_bytes(), str(_BASELINE_PATH), "exec"), _base.__dict__)

REGION = 1800.0
RMIN = 1000.0
MAXN = 16


class ContinuousCoverageCertificate:
    """记录每个频道的无信号证据，并提供整个闭圆盘的充分覆盖证书。

    取覆盖 [-R,R]^2 的闭方格，保留与目标闭圆盘相交的所有单元，
    包括中心落在圆外的边界单元。若某次无信号测量位置 p 与单元
    中心 c 满足 ||p-c|| + h*sqrt(2)/2 <= r_min - margin，则由
    三角不等式，单元内的每个点均在该测量的保证接收范围内。
    每个未知频道的所有单元都有这种无信号证据，才排除未发现源。
    不要求所有单元使用同一个测量位置，允许不同单元由不同测站覆盖。
    """

    def __init__(self, radius=REGION, receive_radius=RMIN, spacing=45.0,
                 channel_count=20, margin=1e-6):
        if radius <= 0 or receive_radius <= 0 or spacing <= 0 or margin < 0:
            raise ValueError("覆盖参数必须为正，安全裕量不得为负")
        self.radius = float(radius)
        self.receive_radius = float(receive_radius)
        self.margin = float(margin)
        n = int(math.ceil(2.0 * self.radius / spacing))
        self.spacing = 2.0 * self.radius / n
        half = self.spacing / 2.0
        self.half_diagonal = math.sqrt(2.0) * half
        self.safe_radius = self.receive_radius - self.half_diagonal - self.margin
        if self.safe_radius <= 0:
            raise ValueError("网格过粗，无法构成保守覆盖证书")
        axis = -self.radius + (np.arange(n, dtype=float) + 0.5) * self.spacing
        xx, yy = np.meshgrid(axis, axis, indexing="xy")
        centers = np.column_stack((xx.ravel(), yy.ravel()))
        nearest_to_origin = np.maximum(np.abs(centers) - half, 0.0)
        intersects = np.sum(nearest_to_origin ** 2, axis=1) <= self.radius ** 2 + 1e-8
        self.centers = centers[intersects]
        self.covered = np.zeros((channel_count, len(self.centers)), dtype=bool)
        self.no_signal_counts = np.zeros(channel_count, dtype=np.int64)
        self._safe_r2 = self.safe_radius ** 2

    def add_no_signal(self, point, channel):
        """只能在公开接口接受并明确返回 no_signal 后调用。"""
        point = np.asarray(point, dtype=float)
        if point.shape != (2,) or not np.all(np.isfinite(point)):
            raise ValueError("测站坐标必须是两个有限数值")
        row = int(channel) - 1
        if not 0 <= row < len(self.covered):
            raise ValueError("频道超出证书范围")
        self.covered[row] |= np.sum((self.centers - point) ** 2, axis=1) <= self._safe_r2
        self.no_signal_counts[row] += 1

    def unresolved(self, channels):
        rows = np.asarray(list(channels), dtype=int) - 1
        if len(rows) == 0:
            return np.zeros(len(self.centers), dtype=bool)
        return ~np.all(self.covered[rows], axis=0)

    def is_complete(self, channels):
        return not bool(np.any(self.unresolved(channels)))

    def gain(self, point, channels):
        unresolved = self.unresolved(channels)
        if not np.any(unresolved):
            return 0
        delta = self.centers[unresolved] - np.asarray(point, dtype=float)
        return int(np.count_nonzero(np.sum(delta ** 2, axis=1) <= self._safe_r2))

    def best_probe(self, current, channels, max_candidates=240):
        """以真实尚未获得证据的单元选择补扫点，优先一次扫完的近点。"""
        channels = list(channels)
        remaining = self.centers[self.unresolved(channels)]
        if len(remaining) == 0:
            return None
        current = np.asarray(current, dtype=float)
        if len(remaining) > max_candidates:
            indices = np.linspace(0, len(remaining) - 1, max_candidates, dtype=int)
            pool = remaining[indices]
        else:
            pool = remaining.copy()
        # 加入剩余单元质心、邻近单元，以及目标域内环上的均匀测站。
        # 外圆网格中心可以在目标圆外；所有候选操作点投影回圆内。
        nearest = remaining[np.argsort(np.sum((remaining - current) ** 2, axis=1))[:16]]
        angles = np.linspace(0.0, 2.0 * math.pi, 48, endpoint=False)
        rings = np.concatenate([
            np.column_stack((np.cos(angles), np.sin(angles))) * r
            for r in (1050.0, 1350.0, 1600.0)
        ])
        candidates = np.vstack((current[None, :], np.mean(remaining, axis=0)[None, :],
                                pool, nearest, rings))
        norms = np.linalg.norm(candidates, axis=1)
        outside = norms > self.radius - 1e-6
        candidates[outside] *= ((self.radius - 1e-6) / norms[outside])[:, None]
        candidates = np.unique(np.round(candidates, decimals=7), axis=0)
        scan_seconds = 6.0 * len(list(channels))
        best = None
        finish = None
        for point in candidates:
            gain = int(np.count_nonzero(np.sum((remaining - point) ** 2, axis=1) <= self._safe_r2))
            if gain == 0:
                continue
            travel = float(np.linalg.norm(point - current))
            cost = travel / 5.0 + scan_seconds
            if gain == len(remaining):
                if finish is None or travel < finish[0]:
                    finish = (travel, point.copy())
            # 固定扫描费用已包含，避免为极小局部缺口反复驻点切换频道。
            utility = gain / max(1.0, cost)
            candidate = (utility, gain, -travel, point.copy())
            if best is None or candidate[:3] > best[:3]:
                best = candidate
        if finish is not None:
            return finish[1]
        # 至少一个剩余单元的投影中心可覆盖该单元，所以这里应有进展。
        if best is None:
            raise RuntimeError("连续域证书仍有缺口，但没有能推进覆盖的测站")
        return best[3]

    def summary(self, channels):
        channels = list(channels)
        remaining = int(np.count_nonzero(self.unresolved(channels)))
        return {
            "method": "intersecting_closed_square_cells_with_half_diagonal_margin",
            "domain_radius_m": self.radius,
            "minimum_receive_radius_m": self.receive_radius,
            "cell_spacing_m": self.spacing,
            "half_diagonal_m": self.half_diagonal,
            "numeric_margin_m": self.margin,
            "cell_count": len(self.centers),
            "unresolved_cell_count": remaining,
            "unknown_channels": channels,
            "all_unknown_channels_certified": remaining == 0,
            "accepted_no_signal_counts": {
                str(ch): int(self.no_signal_counts[ch - 1]) for ch in channels
            },
        }


class _NearAwareBelief(_base.ParticleBelief):
    def __init__(self, channel):
        super().__init__(channel)
        self.near_position = None

    def add(self, point, result, bearing=None):
        super().add(point, result, bearing)
        if result == "near":
            # near 自身已经证明存在源，不能因为随后清除异常而变回 unknown。
            self.status = "detected"
            self.near_position = np.asarray(point, dtype=float).copy()

    def estimate(self):
        if self.near_position is not None:
            # 基线对 near 没有 direction 历史时不能估计，保留已知近场位置。
            return self.near_position.copy(), 5.0
        return super().estimate()


class _AcceptedClient:
    """统一校验所有动作，包含继承的 service 清除路径。"""
    def __init__(self, client):
        self.__client = client
    @property
    def position(self): return self.__client.position
    @property
    def receiver_channel(self): return self.__client.receiver_channel
    @property
    def last_response(self): return self.__client.last_response
    @property
    def current_virtual_time_s(self): return self.__client.current_virtual_time_s
    def _call(self, action, *args):
        response = getattr(self.__client, action)(*args)
        if not isinstance(response, dict) or response.get("accepted") is not True:
            raise RuntimeError(f"{action} 未明确接受，不能用于状态或证书更新")
        if action == "clear" and response.get("clear_result") not in ("success", "no_target_in_range"):
            raise RuntimeError("清除响应缺少合法结果")
        return response
    def enter(self): return self._call("enter")
    def measure(self, x, y, channel): return self._call("measure", x, y, channel)
    def clear(self, x, y, channel): return self._call("clear", x, y, channel)
    def exit(self): return self._call("exit")


class Q3ParticleController(_base.Q3ParticleController):
    """兼容原 Q3ParticleController(client) 的离线可评测候选。"""

    def __init__(self, client):
        super().__init__(_AcceptedClient(client))
        self.B = {ch: _NearAwareBelief(ch) for ch in range(1, 21)}
        self.certificate = ContinuousCoverageCertificate()
        self.completion_verified = False
        self.completion_reason = "not_started"
        self.completion_certificate = None
        self.coverage_probe_count = 0
        self.max_steps = 180

    @staticmethod
    def _require_accepted(response, action):
        if not isinstance(response, dict) or response.get("accepted") is not True:
            raise RuntimeError(f"{action} 未被接受，不能将该操作计为有效证据")

    def measure(self, point, channel):
        point = np.asarray(point, dtype=float)
        belief = self.B[channel]
        was_unknown = belief.status == "unknown"
        response = self.c.measure(float(point[0]), float(point[1]), int(channel))
        self._require_accepted(response, "measure")
        result = response.get("measure_result")
        if result not in ("no_signal", "direction", "near"):
            raise RuntimeError(f"未知测量结果: {result!r}")
        belief.add(point, result, response.get("svd_deg"))
        if result == "no_signal" and was_unknown:
            self.certificate.add_no_signal(point, channel)
        elif result == "direction":
            belief.status = "detected"
            if was_unknown:
                print(f"  [发现] CH{channel:02d} 位置{self._pos(point)} | {self._progress()}", flush=True)
        elif result == "near":
            response = self.c.clear(float(point[0]), float(point[1]), int(channel))
            self._require_accepted(response, "near 后清除")
            if response.get("clear_result") == "success":
                belief.status = "cleared"
                self.cleared.add(channel)
                print(f"  [近场直清] CH{channel:02d} 成功 | {self._progress()}", flush=True)
            else:
                raise RuntimeError(f"协议矛盾：CH{channel:02d} 同点near后清除失败")
        return result

    def scan_unknown(self, point):
        point = np.asarray(point, dtype=float)
        # 只跳过坐标相同的重复完整普查；补扫点若能补证书缺口不会被跳过。
        if any(float(np.linalg.norm(point - old)) < 1e-6 for old in self.used):
            return 0
        channels = self.unknown()
        if not channels or self.known() >= MAXN:
            return 0
        receiver = getattr(self.c, "receiver_channel", None)
        if receiver in channels:
            channels.remove(receiver)
            channels.insert(0, receiver)
        before = self.known()
        self._scan_seq += 1
        print(f"[普查{self._scan_seq}] {self._pos(point)}，扫描未知频道 {len(channels)} 个", flush=True)
        for channel in channels:
            if self.known() >= MAXN:
                break
            self.measure(point, channel)
        if self.known() < MAXN:
            # 这里仅保留基线路由使用的统计覆盖图，结束证据来自逐频道证书。
            self.cover.add(point)
            self.used.append(point.copy())
        gain = self.known() - before
        print(f"[普查{self._scan_seq}] 新发现 {gain} 个 | {self._progress()}", flush=True)
        return gain

    def coverage_done(self):
        return self.certificate.is_complete(self.unknown())

    def discovery_verified(self):
        return self.known() >= MAXN or self.coverage_done()

    def _coverage_probe(self):
        point = self.certificate.best_probe(self.c.position, self.unknown())
        if point is not None:
            self.coverage_probe_count += 1
            remaining = int(np.count_nonzero(self.certificate.unresolved(self.unknown())))
            print(f"[证书补扫] 尚有 {remaining} 个单元缺少排除证据，前往 {self._pos(point)}", flush=True)
        return point

    def run(self):
        entered = self.c.enter()
        self._require_accepted(entered, "enter")
        self.completion_reason = "running"
        print("Q3 完整清除候选：连续域覆盖证书 + 原粒子定位与滚动路由", flush=True)
        try:
            self.scan_unknown(np.zeros(2))
            if not self.discovery_verified():
                point = self.bootstrap_point()
                self.scan_unknown(point)
                self.scan_info(point, limit=8)
            for step in range(self.max_steps):
                known = self.known()
                discovery_done = self.discovery_verified()
                detected = []
                for channel, belief in self.B.items():
                    if channel not in self.cleared and belief.status == "detected":
                        estimate, _ = belief.estimate()
                        if estimate is not None:
                            detected.append((channel, estimate))
                if detected:
                    kind, channel, point = self.joint_next(detected, soft_done=discovery_done)
                    if kind == "probe":
                        self.scan_unknown(point)
                        self.scan_info(point, limit=5)
                        continue
                    self.service(channel)
                    current = np.asarray(self.c.position, dtype=float)
                    if not self.discovery_verified():
                        pd = self.cover.conditional_detect(current)
                        threshold = 0.08 if self.known() >= 14 else (0.11 if self.known() >= 12 else 0.15)
                        unresolved = int(np.count_nonzero(self.certificate.unresolved(self.unknown())))
                        cert_gain = self.certificate.gain(current, self.unknown())
                        cheap_progress = (
                            cert_gain == unresolved
                            or (cert_gain >= 0.45 * unresolved
                                and cert_gain >= 0.015 * len(self.certificate.centers))
                        )
                        if pd >= threshold or cheap_progress:
                            self.scan_unknown(current)
                    self.scan_info(current, limit=2 if self.known() < 13 else 4)
                    continue
                if discovery_done:
                    # 除了不存在可路由目标，还要明确没有任何待清状态。
                    pending = [ch for ch, b in self.B.items() if b.status == "detected"]
                    if pending:
                        raise RuntimeError(f"仍有无法定位的待清频道: {pending}")
                    self.completion_verified = True
                    self.completion_reason = (
                        "maximum_16_sources_cleared" if len(self.cleared) >= MAXN
                        else "continuous_domain_certified_and_all_detected_cleared"
                    )
                    break
                probable_done = (
                    known >= 10 and len(self.cleared) >= 9
                    and self.posterior_same_count() >= self.stop_threshold(known)
                )
                point = self._coverage_probe() if probable_done else self.exploration_point()
                if point is None:
                    point = self._coverage_probe()
                if point is None:
                    raise RuntimeError("搜索尚未完成，且不能构造下一测站")
                self.scan_unknown(point)
                self.scan_info(point, limit=5)
            else:
                self.completion_reason = "step_limit_without_completion_certificate"
            self.completion_certificate = self.certificate.summary(self.unknown())
            self.completion_certificate.update({
                "completion_verified": self.completion_verified,
                "completion_reason": self.completion_reason,
                "cleared_count": len(self.cleared),
                "known_count": self.known(),
                "supplemental_coverage_probes": self.coverage_probe_count,
            })
            print(f"[完成复核] verified={self.completion_verified} reason={self.completion_reason} | {self._progress()}", flush=True)
            return len(self.cleared)
        except Exception:
            self.completion_reason = "exception_without_completion_certificate"
            raise
        finally:
            try:
                response = self.c.exit()
                reason = response.get("exit_reason")
                if self.completion_certificate is not None:
                    self.completion_certificate["exit_accepted"] = True
                print(f"[退出] {reason}", flush=True)
            except Exception:
                self.completion_verified = False
                self.completion_reason = "exit_failed"
                if self.completion_certificate is not None:
                    self.completion_certificate.update({"exit_accepted": False,
                        "completion_verified": False, "completion_reason": "exit_failed"})
                raise


def run_q3_particle(client):
    return Q3ParticleController(client).run()

