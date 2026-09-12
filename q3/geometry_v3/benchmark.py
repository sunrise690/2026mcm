"""独立进程离线评测，固定源代码、随机场景与三类证据。"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'simulator')]
SIM_HASH = 'a677095911df518d8442cc7d35b2a623f527e4f2b4462326375a9056f3f1c3ec'


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def fingerprints():
    files = [Path(__file__), *sorted((ROOT / 'src').glob('*.py')),
             *sorted((ROOT / 'simulator').glob('*.py')), *sorted((ROOT / 'configs').glob('*.json'))]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def offline_guard():
    def deny(*args, **kwargs):
        raise RuntimeError('离线评测禁止网络连接')
    for name in ('connect', 'connect_ex', 'sendto'):
        setattr(socket.socket, name, deny)
    for name in ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr'):
        setattr(socket, name, deny)


class ObservationsOnlyClient:
    __slots__ = ('__dispatch', '__position', '__channel', 'last_response')

    def __init__(self, dispatch):
        self.__dispatch = dispatch
        self.__position = (0.0, 0.0)
        self.__channel = 1
        self.last_response = {}

    @property
    def position(self):
        return self.__position

    @property
    def receiver_channel(self):
        return self.__channel

    @property
    def current_virtual_time_s(self):
        return self.last_response.get('virtual_time_s', 0.0)

    def _call(self, action, *args):
        import math
        if args:
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in args):
                raise ValueError('动作参数必须有限')
            x, y, ch = args
            if ch != int(ch) or not 1 <= ch <= 20 or max(abs(x), abs(y)) > 2e6:
                raise ValueError('动作范围非法')
        response = self.__dispatch(action, *args)
        self.last_response = dict(response)
        if response.get('accepted') is not True:
            raise RuntimeError(f'{action} 未接受')
        if args:
            self.__position = (float(args[0]), float(args[1]))
            if action == 'measure':
                self.__channel = int(args[2])
        return dict(response)

    def enter(self):
        return self._call('enter')

    def measure(self, x, y, ch):
        return self._call('measure', x, y, ch)

    def clear(self, x, y, ch):
        return self._call('clear', x, y, ch)

    def exit(self):
        return self._call('exit')


def child(variant, seed, output):
    offline_guard()
    import jammers_offline_sim as sim
    from controller import LATEST_TUNE
    cfg = json.loads((ROOT / 'configs/variants.json').read_text(encoding='utf-8'))[variant]
    seed_key = hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()
    engine = sim.Engine(sim.generate_practice(3, seed_key), record_trace=False)
    module = importlib.import_module(cfg['module'])
    output = Path(output)
    started = time.perf_counter()
    error = None
    controller = None
    with output.with_suffix('.actions.jsonl').open('w', encoding='utf-8') as log:
        def dispatch(action, *args):
            response = getattr(engine, action)(*args)
            log.write(json.dumps({'action': action, 'args': args, 'response': response}, ensure_ascii=False) + '\n')
            log.flush()
            return response
        try:
            tuning = LATEST_TUNE if cfg.get('latest_tune') else cfg.get('tune', {})
            kwargs = {} if cfg['module'] in ('baseline_complete', 'baseline_planned') else {'tune': tuning}
            controller = module.Q3ParticleController(ObservationsOnlyClient(dispatch), **kwargs)
            controller.run()
        except Exception as ex:
            error = f'{type(ex).__name__}: {ex}'
            traceback.print_exc()
    summary = engine.summary()
    n, cleared = summary['jammer_count'], summary['cleared_count']
    report = {}
    if controller is not None:
        for key in ('completion_verified', 'completion_reason', 'completion_certificate', 'geometry_report'):
            if hasattr(controller, key):
                report[key] = getattr(controller, key)
    row = {'variant': variant, 'seed': seed, 'N': n, 'cleared': cleared, 'missing': n - cleared,
           'ok': n == cleared and error is None and summary['exited'] and not summary['timed_out']
                 and getattr(controller, 'completion_verified', True),
           'virtual_time_s': summary['virtual_time_s'],
           'avg_clear_time_s': summary['virtual_time_s'] / cleared if cleared else None,
           'wall_s': time.perf_counter() - started, 'error': error,
           'engine_summary': summary, 'controller_end': report}
    dump(output, row)
    return row


def execute(variant, seed, directory, timeout):
    output = directory / variant / f'seed_{seed}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop('Q3_TUNE_JSON', None)
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONHASHSEED='0')
    command = [sys.executable, '-B', str(Path(__file__)), '--child', '--variants', variant,
               '--seeds', str(seed), '--output', str(output)]
    with output.with_suffix('.log').open('w', encoding='utf-8') as log:
        try:
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            error = None if process.returncode == 0 else f'exit_{process.returncode}'
        except subprocess.TimeoutExpired:
            error = f'timeout_{timeout}'
    if error is None and output.exists():
        return json.loads(output.read_text(encoding='utf-8'))
    row = {'variant': variant, 'seed': seed, 'N': None, 'cleared': 0, 'ok': False, 'error': error or 'missing_output'}
    dump(output, row)
    return row


def aggregate(rows):
    out = []
    for name in sorted({r['variant'] for r in rows}):
        data = [r for r in rows if r['variant'] == name]
        ok = [r for r in data if r['ok']]
        out.append({'variant': name, 'runs': len(data), 'fullclear': len(ok),
                    'missing': sum(r['missing'] for r in data) if all('missing' in r for r in data) else None,
                    'mean_fullclear_s_per_source': statistics.mean(r['avg_clear_time_s'] for r in ok) if ok else None,
                    'max_fullclear_s_per_source': max((r['avg_clear_time_s'] for r in ok), default=None),
                    'errors': sum(r.get('error') is not None for r in data),
                    'mean_wall_s': statistics.mean(r.get('wall_s', 0) for r in data)})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variants', default='latest,v3_tail')
    parser.add_argument('--seeds', default='0,7,13,17,27,10040')
    parser.add_argument('--seed-file')
    parser.add_argument('--seed-range', nargs=2, type=int)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--label', default='benchmark')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    variants = args.variants.split(',')
    seeds = [int(x) for x in args.seeds.split(',')]
    if args.seed_file:
        seeds = json.loads(Path(args.seed_file).read_text(encoding='utf-8'))['seeds']
    if args.seed_range:
        seeds = list(range(*args.seed_range))
    if args.child:
        child(variants[0], seeds[0], args.output)
        return
    if len(set(seeds)) != len(seeds) or not seeds:
        raise ValueError('种子必须唯一且非空')
    hashes = fingerprints()
    if hashes['simulator/jammers_offline_sim.py'] != SIM_HASH:
        raise RuntimeError('模拟器哈希不匹配')
    directory = ROOT / 'runs' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + args.label)
    directory.mkdir(parents=True)
    import scipy
    import numpy
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'seeds': seeds,
                'variants': variants, 'hashes': hashes, 'timeout_s': args.timeout, 'workers': args.workers,
                'python': sys.version, 'numpy': numpy.__version__, 'scipy': scipy.__version__,
                'metric': 'virtual_time_s / cleared_count; failed cases cannot win time rankings',
                'seed_mapping': 'sha256(cumcm-offline-generator-key:{integer_seed})',
                'network_allowed': False}
    dump(directory / 'manifest.json', manifest)
    print(f'RUN_DIR={directory}', flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, v, s, directory, args.timeout) for s in seeds for v in variants]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            if not row['ok'] or len(rows) % 10 == 0 or len(rows) == len(futures):
                print(f"[{len(rows)}/{len(futures)}] {row['variant']} seed={row['seed']} {row['cleared']}/{row['N']} {'OK' if row['ok'] else 'FAIL'}", flush=True)
            with (directory / 'progress.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(row, ensure_ascii=False) + '\n')
    result = {'summary': aggregate(rows), 'rows': sorted(rows, key=lambda r: (r['variant'], r['seed'])),
              'fingerprints_unchanged': fingerprints() == hashes}
    dump(directory / 'results.json', result)
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2), flush=True)
    if not result['fingerprints_unchanged']:
        raise RuntimeError('评测期间源码改变，本批结果不可用于晋级')


if __name__ == '__main__':
    main()
