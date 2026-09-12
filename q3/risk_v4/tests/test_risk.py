"""模型公式、保守积分及概率完成与真值全清的区别。"""
import math
import contextlib
import io
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'geometry_v3'
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(BASE / 'src'), str(BASE / 'simulator')]
import benchmark
from coverage_geometry import covering_radius
from risk_geometry import RiskOracle, RiskPlanner, missing_risk, allowed_miss, DENSITY_FACTOR
from risk_controller import Q3ParticleController


class RiskTests(unittest.TestCase):
    def test_count_posterior_matches_label_assignment_likelihood(self):
        for known in range(10, 16):
            for w in (0.0001, 0.001, 0.01):
                likelihood = [math.comb(20-known, n-known) / math.comb(20, n) * w ** (n-known)
                              for n in range(known, 17)]
                expected = sum(likelihood[1:]) / sum(likelihood)
                self.assertAlmostEqual(missing_risk(known, w), expected, places=13)
        self.assertEqual(missing_risk(9, 0), 1.0)
        self.assertEqual(missing_risk(16, 1), 0.0)

    def test_risk_inverse(self):
        for k in (10, 13, 15):
            for epsilon in (0.001, 0.003, 0.01):
                w = allowed_miss(k, epsilon)
                self.assertAlmostEqual(missing_risk(k, w), epsilon, places=12)
                self.assertGreater(missing_risk(k, w * 1.01), epsilon)

    def test_integral_bounds_enclose_analytic_single_station(self):
        a, b, radius = 1000.0, 1500.0, 1800.0
        integral = (2 / (500 * radius**2) * ((b**3-a**3)/3 - a*(b*b-a*a)/2)
                    + (radius**2-b*b)/radius**2) * DENSITY_FACTOR
        result = RiskOracle().bounds([[0, 0]], 13, 0.001, tolerance=0.01)
        self.assertLessEqual(result['mass_lower'], integral)
        self.assertGreaterEqual(result['mass_upper'], integral)
        self.assertFalse(result['accepted'])

    def test_tiny_holes_are_risk_completion_not_coverage(self):
        angles = np.linspace(0, 2 * np.pi, 6, endpoint=False)
        sites = np.vstack(([0, 0], 1100 * np.column_stack((np.cos(angles), np.sin(angles)))))
        self.assertGreater(covering_radius(sites)[0], 1000)
        oracle = RiskOracle()
        result = oracle.bounds(sites, 13, 0.003)
        self.assertTrue(result['accepted'], result)
        self.assertLessEqual(result['risk_upper'], 0.003)
        self.assertFalse(oracle.bounds(sites, 13, 1e-8)['accepted'])

    def test_duplicate_station_cannot_reduce_risk(self):
        oracle = RiskOracle()
        a = oracle.bounds([[0, 0], [100, 200]], 12, 0.001)
        b = oracle.bounds([[0, 0], [100, 200], [0, 0]], 12, 0.001)
        self.assertEqual(a, b)

    def test_no_signal_prior_shrinks_after_new_station(self):
        planner = RiskPlanner(radial=12, angular=48)
        _, a = planner.residual([[0, 0]])
        _, b = planner.residual([[0, 0], [1200, 0]])
        self.assertLess(float(np.sum(b - 1000)), float(np.sum(a - 1000)))

    def test_all_case_timing_includes_failures(self):
        rows = [dict(variant='a', ok=True, missing=0, avg_clear_time_s=100, wall_s=1, error=None),
                dict(variant='a', ok=False, missing=1, avg_clear_time_s=200, wall_s=1, error=None)]
        summary = benchmark.aggregate(rows)[0]
        self.assertEqual(summary['all_case_mean_s_per_cleared_source'], 150)
        self.assertEqual(summary['failure_rate'], 0.5)

    def test_zero_failures_do_not_imply_zero_risk(self):
        rows = [dict(variant='a', ok=True, missing=0, avg_clear_time_s=100, wall_s=1, error=None)] * 600
        summary = benchmark.aggregate(rows)[0]
        self.assertAlmostEqual(summary['failure_rate_upper95'], 1-0.05**(1/600), places=12)
        self.assertGreater(summary['failure_rate_upper95'], 0)
        self.assertLess(summary['failure_rate_upper95'], 0.01)

    def test_near_count_completion_and_rejected_exit(self):
        for reject_exit in (False, True):
            def dispatch(action, *args):
                return {'accepted': not (reject_exit and action=='exit'), 'virtual_time_s': 0.0,
                        'measure_result': 'near', 'clear_result': 'success'}
            ctl = Q3ParticleController(benchmark.ObservationsOnlyClient(dispatch))
            with contextlib.redirect_stdout(io.StringIO()):
                if reject_exit:
                    with self.assertRaises(RuntimeError):
                        ctl.run()
                    self.assertFalse(ctl.completion_verified)
                else:
                    self.assertEqual(ctl.run(), 16)
                    self.assertTrue(ctl.completion_verified)
                    self.assertEqual(ctl.completion_reason, 'maximum_count')

    def test_invalid_risk_budget_rejected(self):
        client = benchmark.ObservationsOnlyClient(lambda *args: {'accepted': True})
        for value in (0, -0.1, float('nan'), 0.5):
            with self.assertRaises(ValueError):
                Q3ParticleController(client, {'risk_epsilon': value})

    def test_risk_acceptance_cannot_complete_pending_source(self):
        client = benchmark.ObservationsOnlyClient(lambda *args: {'accepted': True, 'virtual_time_s': 0})
        ctl = Q3ParticleController(client)
        for ch in range(1, 13):
            ctl.B[ch].status = 'cleared'
            ctl.cleared.add(ch)
        ctl.B[1].status = 'detected'
        ctl.cleared.remove(1)
        ctl.B[1].estimate = lambda: (np.array([0.0, 0.0]), 1.0)
        ctl.scan_unknown = lambda *args: 0
        ctl.scan_info = lambda *args, **kwargs: None
        ctl.discovery_verified = lambda: True
        ctl.service = lambda *args: False
        ctl.max_steps = 1
        with contextlib.redirect_stdout(io.StringIO()):
            ctl.run()
        self.assertFalse(ctl.completion_verified)
        self.assertEqual(ctl.completion_reason, 'step_limit')


if __name__ == '__main__':
    unittest.main()
