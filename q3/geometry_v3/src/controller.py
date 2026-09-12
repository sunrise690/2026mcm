"""V3：连续圆域证书、残余覆盖投影与提前插入测站。"""
import math
import numpy as np

import baseline_latest as base
from baseline_complete import _AcceptedClient
from coverage_geometry import DiskCertificate, ResidualPlanner, covering_radius, RECEIVE_RADIUS, MARGIN

LATEST_TUNE = {
    'particle_n': 32000, 'particle_rebuild_n': 64000,
    'adaptive_route_scan': 1, 'route_scan_value_s': 900, 'stop_thr_13': 0.9,
    'service_waypoint': 1, 'service_waypoint_min_prob': 0.4,
    'service_waypoint_cross_weight': 300, 'service_waypoint_prob_weight': 100,
    'adaptive_bootstrap_info': 1, 'scan_info_score_thr': 0.3,
    'service_uncertainty_trigger': 80, 'stop_thr_10': 0.58,
    'stop_thr_11': 0.68, 'stop_thr_12': 0.75, 'service_waypoint_detour_weight': 1.5,
    'service_aware_route': 1, 'service_aware_uncertainty_scale': 0.8,
    'hard_done_info_limit': 1,
}


class Q3ParticleController(base.Q3ParticleController):
    def __init__(self, client, tune=None):
        config = dict(LATEST_TUNE)
        config.update(tune or {})
        super().__init__(_AcceptedClient(client), config)
        self.certificate = DiskCertificate()
        self.planner = ResidualPlanner()
        self.completion_verified = False
        self.completion_reason = 'not_started'
        self.completion_certificate = None
        self.max_steps = 180
        self.geometric_probe = None
        self.probe_known = -1
        self.geometry_report = {'tail_probes': 0, 'inserted_probes': 0}

    def measure(self, p, ch):
        p = np.asarray(p, float)
        b = self.B[ch]
        response = self.c.measure(float(p[0]), float(p[1]), int(ch))
        result = response.get('measure_result')
        if result not in ('no_signal', 'direction', 'near'):
            raise RuntimeError('测量响应缺少合法结果')
        if result == 'direction' and not isinstance(response.get('svd_deg'), (float, int)):
            raise RuntimeError('示向缺失')
        was_unknown = b.status == 'unknown'
        b.add(p, result, response.get('svd_deg'))
        if was_unknown and result == 'no_signal':
            self.certificate.add_no_signal(p, ch)
        if result == 'near':
            b.status = 'detected'
            clear = self.c.clear(float(p[0]), float(p[1]), int(ch))
            if clear['clear_result'] != 'success':
                raise RuntimeError('同点 near 后清除失败，接口证据矛盾')
            b.status = 'cleared'
            self.cleared.add(ch)
        return result

    def discovery_verified(self):
        return self.known() >= 16 or self.certificate.report(self.unknown())['complete']

    def coverage_done(self):
        return self.certificate.report(self.unknown())['complete']

    def route_probe(self, items):
        if self.known() < int(self.tune.get('joint_min_known', 8)):
            return None
        if self.probe_known != self.known():
            self.geometric_probe = None
        order = self.source_order(items, False)
        if not order:
            return None
        if self.geometric_probe is None:
            # 未来清除点仅用于提出路线，不进入已接受观测构成的完成证书。
            future = np.asarray(self.used + [np.asarray(p, float) for _, p in items])
            q = self.planner.propose(future, self.c.position, scan_seconds=6 * len(self.unknown()))
            if q is None:
                return None
            _, index = self._route_insertion(order, q)
            a = np.asarray(self.c.position if index == 0 else order[index - 1][1], float)
            b = np.asarray(order[index][1], float) if index < len(order) else None
            refined = self.planner.propose(future, a, b, scan_seconds=6 * len(self.unknown()))
            if refined is not None:
                q = refined
            self.geometric_probe = np.asarray(q, float)
            self.probe_known = self.known()
        q = self.geometric_probe
        if any(np.linalg.norm(q - old) < 2.0 for old in self.used):
            self.geometric_probe = None
            return None
        delta, index = self._route_insertion(order, q)
        if index == 0 and delta <= float(self.tune.get('joint_detour_m', 800.0)):
            self.geometric_probe = None
            self.geometry_report['inserted_probes'] += 1
            return q
        return None

    def run(self):
        self.c.enter()
        self.completion_reason = 'running'
        try:
            self.scan_unknown(np.zeros(2))
            if not self.discovery_verified():
                p = self.bootstrap_point()
                self.scan_unknown(p)
                self.scan_info(p, limit=self.known())
            for _ in range(self.max_steps):
                verified = self.discovery_verified()
                items = [(ch, b.estimate()[0]) for ch, b in self.B.items()
                         if b.status == 'detected' and ch not in self.cleared
                         and b.estimate()[0] is not None]
                if items:
                    if not verified and self.tune.get('joint_geometry', 0):
                        p = self.route_probe(items)
                        if p is not None:
                            self.scan_unknown(p)
                            self.scan_info(p, limit=5)
                            continue
                    kind, ch, p = self.joint_next(items, soft_done=verified)
                    if kind == 'probe':
                        self.scan_unknown(p)
                        self.scan_info(p, limit=5)
                        continue
                    self.premeasure_selected(ch)
                    self.service(ch)
                    p = np.asarray(self.c.position, float)
                    if not self.discovery_verified():
                        # 继续使用信号先验选择顺路扫描；完成判定独立依赖几何证据。
                        pd = self.cover.conditional_detect(p)
                        hp = max(0.05, 1.0 - self.posterior_same_count())
                        threshold = (6 * len(self.unknown()) - 1) / (900 * hp)
                        geometric_gain = False
                        if self.tune.get('geometric_route_scan', 0):
                            sites = np.asarray(self.used, float).reshape(-1, 2)
                            unresolved = self.planner._remaining(sites, self.planner.grid)
                            gain = np.count_nonzero(np.sum((unresolved - p) ** 2, axis=1) <= (RECEIVE_RADIUS - MARGIN) ** 2)
                            fraction = float(self.tune.get('geometric_scan_fraction', 0.25))
                            geometric_gain = (gain >= max(12, fraction * len(unresolved))
                                              or covering_radius(np.vstack((sites, p)))[0] <= RECEIVE_RADIUS - MARGIN)
                        if pd >= threshold or geometric_gain:
                            self.scan_unknown(p)
                    limit = 1 if self.known() >= 16 else (2 if self.known() < 13 else 4)
                    self.scan_info(p, limit=limit)
                    continue
                if any(b.status == 'detected' for b in self.B.values()):
                    raise RuntimeError('存在无法定位的已发现源')
                if verified:
                    self.completion_verified = True
                    self.completion_reason = 'maximum_count' if self.known() >= 16 else 'continuous_coverage'
                    break
                # 单站半径验证提供证书；没有一个点能覆盖所有缺口时按簇推进。
                p = self.planner.propose(self.used, self.c.position, scan_seconds=6 * len(self.unknown()))
                if p is None:
                    raise RuntimeError('证书未完成但规划器没有缺口测站')
                if any(np.linalg.norm(p - old) < 2.0 for old in self.used):
                    _, p = covering_radius(self.used)
                    self.geometry_report['progress_fallbacks'] = self.geometry_report.get('progress_fallbacks', 0) + 1
                self.geometry_report['tail_probes'] += 1
                self.scan_unknown(p)
                self.scan_info(p, limit=5)
            else:
                self.completion_reason = 'step_limit'
            self.completion_certificate = self.certificate.report(self.unknown())
            self.geometry_report.update({'planning_calls': self.planner.calls,
                                         'exchange_steps': self.planner.exchange_steps})
            return len(self.cleared)
        except Exception:
            self.completion_verified = False
            self.completion_reason = 'exception'
            raise
        finally:
            try:
                self.c.exit()
            except Exception:
                self.completion_verified = False
                self.completion_reason = 'exit_failed'
                raise
