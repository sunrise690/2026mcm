"""V4：小风险预算停止；风险上界与真值全清结果分别报告。"""
import numpy as np

import controller as certified
from coverage_geometry import covering_radius
from risk_geometry import RiskOracle, RiskPlanner


class Q3ParticleController(certified.Q3ParticleController):
    def __init__(self, client, tune=None):
        super().__init__(client, tune)
        self.epsilon = float(self.tune.get('risk_epsilon', 0.001))
        if not 0 < self.epsilon <= 0.05:
            raise ValueError('风险预算必须处于 (0, 0.05]')
        self.risk_oracle = RiskOracle()
        self.risk_planner = RiskPlanner()
        self.risk_report = {}

    def discovery_verified(self):
        self.risk_report = self.risk_oracle.bounds(self.used, self.known(), self.epsilon)
        return self.risk_report['accepted']

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
                accepted = self.discovery_verified()
                items = [(ch, b.estimate()[0]) for ch, b in self.B.items()
                         if b.status == 'detected' and ch not in self.cleared
                         and b.estimate()[0] is not None]
                if items:
                    kind, ch, p = self.joint_next(items, soft_done=accepted)
                    if kind == 'probe':
                        self.scan_unknown(p)
                        self.scan_info(p, limit=5)
                        continue
                    self.premeasure_selected(ch)
                    self.service(ch)
                    p = np.asarray(self.c.position, float)
                    if not self.discovery_verified():
                        pd = self.cover.conditional_detect(p)
                        hp = max(0.05, 1.0 - self.posterior_same_count())
                        threshold = (6 * len(self.unknown()) - 1) / (float(self.tune.get('risk_scan_value', 900)) * hp)
                        if pd >= threshold:
                            self.scan_unknown(p)
                    self.scan_info(p, limit=1 if self.known() >= 16 else (2 if self.known() < 13 else 4))
                    continue
                if any(b.status == 'detected' for b in self.B.values()):
                    raise RuntimeError('仍有已发现但无法定位的源')
                if accepted:
                    self.completion_verified = True
                    self.completion_reason = 'maximum_count' if self.known() >= 16 else 'bounded_model_risk'
                    break
                if self.known() < 10:
                    p = self.exploration_point()
                else:
                    p = self.risk_planner.propose(self.used, self.c.position, self.known(), self.epsilon,
                                                   scan_seconds=6 * len(self.unknown()),
                                                   project=bool(self.tune.get('risk_projection', 1)))
                if p is None or any(np.linalg.norm(p - old) < 2.0 for old in self.used):
                    p = self.planner.propose(self.used, self.c.position, scan_seconds=6 * len(self.unknown()))
                if p is None:
                    raise RuntimeError('风险门禁未通过，且无法构造新探测点')
                if any(np.linalg.norm(p - old) < 2.0 for old in self.used):
                    _, p = covering_radius(self.used)
                self.geometry_report['tail_probes'] += 1
                self.scan_unknown(p)
                self.scan_info(p, limit=5)
            else:
                self.completion_reason = 'step_limit'
            # completion_verified 表示策略完成，不等于零风险覆盖证书。
            self.completion_certificate = {'kind': 'model_risk_budget', 'risk': self.risk_report,
                                           'all_detected_cleared': all(b.status != 'detected' for b in self.B.values())}
            self.geometry_report.update({'risk_planning_calls': self.risk_planner.calls,
                                         'probability_projections': self.risk_planner.projected})
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

