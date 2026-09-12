import math
from pathlib import Path
import sys
import unittest

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coverage_geometry import covering_radius, DiskCertificate, ResidualPlanner, verify_cells


def ring(n=6):
    angle = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return 1500 * np.column_stack((np.cos(angle), np.sin(angle)))


class CoverageTests(unittest.TestCase):
    def test_boundary_arc_extremum_and_collinear_sites(self):
        self.assertAlmostEqual(covering_radius([[100, 0]])[0], 1900.0)
        self.assertAlmostEqual(covering_radius([[0, 0], [0, 0], [100, 0]])[0], 1800.0)

    def test_interior_hole_and_closed_boundary(self):
        self.assertAlmostEqual(covering_radius(ring())[0], 1500.0)
        covered = np.vstack(([0, 0], ring()))
        expected = math.sqrt(1800 ** 2 + 1500 ** 2 - 2 * 1800 * 1500 * math.cos(np.pi / 6))
        self.assertAlmostEqual(covering_radius(covered)[0], expected)
        self.assertTrue(verify_cells(covered)[0])
        self.assertFalse(verify_cells(ring(), max_depth=8)[0])

    def test_oracle_agrees_with_independent_dense_sampling(self):
        rng = np.random.default_rng(7314)
        angles = np.linspace(0, 2 * np.pi, 20000, endpoint=False)
        boundary = 1800 * np.column_stack((np.cos(angles), np.sin(angles)))
        axis = np.arange(-1800, 1801, 15)
        xx, yy = np.meshgrid(axis, axis)
        grid = np.column_stack((xx.ravel(), yy.ravel()))
        pts = np.vstack((grid[np.sum(grid * grid, axis=1) <= 1800 ** 2], boundary))
        for n in (2, 3, 7, 10, 14):
            for _ in range(4):
                sites = rng.uniform(-1500, 1500, (n, 2))
                exact, _ = covering_radius(sites)
                dense = np.sqrt(np.min(np.sum((pts[:, None] - sites[None]) ** 2, axis=2), axis=1)).max()
                self.assertGreaterEqual(exact + 1e-5, dense)
                self.assertLessEqual(exact, dense + 15)

    def test_channel_evidence_and_duplicates_are_isolated(self):
        cert = DiskCertificate()
        for point in np.vstack(([0, 0], ring())):
            cert.add_no_signal(point, 1)
            cert.add_no_signal(point, 1)
        self.assertTrue(cert.report([1])['complete'])
        self.assertFalse(cert.report([1, 2])['complete'])
        self.assertEqual(len(cert.stations[1]), 7)

    def test_cluster_projection_respects_all_constraints(self):
        planner = ResidualPlanner()
        points = np.array([[1400, -200], [1400, 200], [1700, 0]])
        q = planner.project_cluster(points, [0, 0])
        self.assertIsNotNone(q)
        self.assertLess(np.linalg.norm(q), np.linalg.norm(points.mean(axis=0)))
        self.assertLessEqual(np.max(np.linalg.norm(points - q, axis=1)), 999.98)

    def test_exchange_proposal_closes_removed_ring_station(self):
        sites = np.vstack(([0, 0], ring()[1:]))
        planner = ResidualPlanner()
        q = planner.one_station(sites, [0, 0])
        self.assertIsNotNone(q)
        self.assertLessEqual(covering_radius(np.vstack((sites, q)))[0], 999.98)
        self.assertTrue(verify_cells(np.vstack((sites, q)))[0])


if __name__ == '__main__':
    unittest.main()
