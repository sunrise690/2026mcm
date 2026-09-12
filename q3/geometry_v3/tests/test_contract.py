"""检查观测边界、拒绝动作和真实完成状态，不依赖生成器真值选动作。"""
import contextlib
import hashlib
import io
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'simulator')]
import benchmark
import jammers_offline_sim as sim
from controller import Q3ParticleController


class ContractTests(unittest.TestCase):
    def client(self, *, near=False, reject=None):
        def dispatch(action, *args):
            if action == reject:
                return {'accepted': False}
            response = {'accepted': True, 'virtual_time_s': 0.0}
            if action == 'measure':
                response['measure_result'] = 'near' if near else 'no_signal'
            if action == 'clear':
                response['clear_result'] = 'success'
            return response
        return benchmark.ObservationsOnlyClient(dispatch)

    def test_adapter_exposes_no_public_truth_and_preserves_clear_channel(self):
        client = self.client()
        for name in ('engine', 'scenario', 'jammers', 'seed', '__dict__'):
            self.assertFalse(hasattr(client, name))
        client.measure(1, 2, 7)
        client.clear(5, 6, 9)
        self.assertEqual(client.position, (5.0, 6.0))
        self.assertEqual(client.receiver_channel, 7)

    def test_invalid_actions_are_not_dispatched(self):
        dispatch = mock.Mock()
        client = benchmark.ObservationsOnlyClient(dispatch)
        for args in ((float('nan'), 0, 1), (0, 0, 1.5), (True, 0, 1), (0, 0, 21)):
            with self.assertRaises(ValueError):
                client.measure(*args)
        dispatch.assert_not_called()

    def test_rejected_measure_cannot_add_exclusion_evidence(self):
        ctl = Q3ParticleController(self.client(reject='measure'))
        with self.assertRaises(RuntimeError):
            ctl.measure([0, 0], 1)
        self.assertEqual(ctl.certificate.stations[1], [])

    def test_sixteen_near_sources_complete_by_count(self):
        ctl = Q3ParticleController(self.client(near=True))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ctl.run(), 16)
        self.assertTrue(ctl.completion_verified)
        self.assertEqual(ctl.completion_reason, 'maximum_count')

    def test_rejected_exit_revokes_completion(self):
        ctl = Q3ParticleController(self.client(near=True, reject='exit'))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            ctl.run()
        self.assertFalse(ctl.completion_verified)
        self.assertEqual(ctl.completion_reason, 'exit_failed')

    def test_step_limit_does_not_approve_completion(self):
        ctl = Q3ParticleController(self.client())
        ctl.max_steps = 0
        with contextlib.redirect_stdout(io.StringIO()):
            ctl.run()
        self.assertFalse(ctl.completion_verified)
        self.assertEqual(ctl.completion_reason, 'step_limit')

    def test_failed_cases_do_not_win_timing(self):
        rows = [dict(variant='x', ok=True, missing=0, avg_clear_time_s=100.0, wall_s=1, error=None),
                dict(variant='x', ok=False, missing=1, avg_clear_time_s=1.0, wall_s=1, error=None)]
        result = benchmark.aggregate(rows)[0]
        self.assertEqual(result['fullclear'], 1)
        self.assertEqual(result['mean_fullclear_s_per_source'], 100.0)

    def test_timeout_is_failure(self):
        with mock.patch.object(benchmark.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['stub'], 0.1)), \
             mock.patch.object(Path, 'mkdir'), mock.patch.object(Path, 'open', mock.mock_open()), \
             mock.patch.object(benchmark, 'dump'):
            row = benchmark.execute('latest', 0, Path('ignored'), 0.1)
        self.assertFalse(row['ok'])
        self.assertEqual(row['error'], 'timeout_0.1')

    def test_guard_blocks_network_entrypoints_without_network(self):
        functions = ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr')
        methods = ('connect', 'connect_ex', 'sendto')
        with mock.patch.multiple(socket, **{name: mock.Mock() for name in functions}), \
             mock.patch.multiple(socket.socket, **{name: mock.Mock() for name in methods}):
            benchmark.offline_guard()
            for name in functions:
                with self.assertRaises(RuntimeError):
                    getattr(socket, name)()
            for name in methods:
                with self.assertRaises(RuntimeError):
                    getattr(socket.socket, name)()

    def test_simulator_hash_and_builtin_contract(self):
        path = ROOT / 'simulator/jammers_offline_sim.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), benchmark.SIM_HASH)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            sim.cmd_selftest(None)
        self.assertIn('ALL PASS (12 checks)', output.getvalue())


if __name__ == '__main__':
    unittest.main()
