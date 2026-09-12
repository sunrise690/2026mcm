"""原模拟器动作重放、公开观测风险复算和失败率/时间汇总核验。"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'geometry_v3'
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(BASE / 'src'), str(BASE / 'simulator')]
import benchmark
import jammers_offline_sim as sim
from coverage_geometry import verify_cells
from risk_geometry import RiskOracle


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def replay(text, row, config):
    seed_key = hashlib.sha256(f"cumcm-offline-generator-key:{row['seed']}".encode()).digest()
    engine = sim.Engine(sim.generate_practice(3, seed_key), record_trace=False)
    negatives = defaultdict(set)
    detected = set()
    cleared = set()
    count = 0
    for line in text.splitlines():
        action = json.loads(line)
        name, args = action['action'], action['args']
        expected = getattr(engine, name)(*args)
        recorded = action['response']
        for key in ('accepted', 'virtual_time_s', 'measure_result', 'svd_deg', 'clear_result', 'exit_reason'):
            if expected.get(key) != recorded.get(key):
                raise AssertionError(f"{row['variant']}/{row['seed']} 动作{count} {key} 重放不一致")
        if recorded.get('accepted'):
            if name == 'measure':
                channel = int(args[2])
                if recorded.get('measure_result') == 'no_signal':
                    negatives[channel].add(tuple(args[:2]))
                else:
                    detected.add(channel)
            elif name == 'clear' and recorded.get('clear_result') == 'success':
                cleared.add(int(args[2]))
        count += 1
    summary = engine.summary()
    if summary != row['engine_summary']:
        raise AssertionError('引擎汇总与原记录不一致')
    if row['N'] != summary['jammer_count'] or row['cleared'] != len(cleared):
        raise AssertionError('真值评测数目错误')
    if row['virtual_time_s'] != summary['virtual_time_s']:
        raise AssertionError('虚拟时间不一致')
    if row['avg_clear_time_s'] != summary['virtual_time_s'] / len(cleared):
        raise AssertionError('秒/源口径错误')
    policy_ok = row['controller_end'].get('completion_verified', True)
    actual_ok = (row['error'] is None and len(cleared) == summary['jammer_count']
                 and summary['exited'] and not summary['timed_out'] and policy_ok)
    if actual_ok != row['ok']:
        raise AssertionError('风险完成状态与真值全清状态混淆')
    if policy_ok and config['module'] != 'baseline_latest':
        if detected - cleared:
            raise AssertionError('风险预算不能批准未清除的已发现源')
        if len(cleared) < 16:
            unknown = [ch for ch in range(1, 21) if ch not in cleared]
            if config['module'] == 'risk_controller':
                common = set.intersection(*(negatives[ch] for ch in unknown))
                epsilon = config['tune']['risk_epsilon']
                risk = RiskOracle().bounds(sorted(common), len(cleared), epsilon)
                if not risk['accepted']:
                    raise AssertionError('公开观测无法复算通过风险门禁')
                logged = row['controller_end']['risk_report']['risk_upper']
                if abs(risk['risk_upper'] - logged) > 1e-12:
                    raise AssertionError('记录的风险上界错误')
            else:
                keys = {tuple(sorted(negatives[ch])) for ch in unknown}
                if not all(verify_cells(key)[0] for key in keys):
                    raise AssertionError('严格参考版本的覆盖证据不完整')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', default=str(ROOT / 'evidence'))
    args = parser.parse_args()
    folder = Path(args.evidence)
    index = read(folder / 'index.json')
    configs = read(ROOT / 'configs/variants.json')
    cases = actions = 0
    reports = []
    for entry in index['runs']:
        directory = folder / entry['label']
        for filename, field in (('manifest.json', 'manifest_sha256'), ('results.json', 'results_sha256'), ('actions.zip', 'actions_sha256')):
            if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != entry[field]:
                raise AssertionError(f'归档哈希错误: {filename}')
        manifest, results = read(directory / 'manifest.json'), read(directory / 'results.json')
        if entry['label'] == 'confirmation':
            selected = read(folder / 'selection.json')
            if selected['hashes'] != manifest['hashes'] or selected['candidate'] not in manifest['variants']:
                raise AssertionError('确认集违反预先冻结的候选选择')
            if manifest['seeds'] != list(range(*selected['confirmation_seeds_half_open'])):
                raise AssertionError('确认种子区间不符合预设')
        if not results['fingerprints_unchanged']:
            raise AssertionError('评测期间存在源码漂移')
        for path, expected in manifest['hashes'].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise AssertionError(f'源码已改变: {path}')
        jobs = {(v, s) for v in manifest['variants'] for s in manifest['seeds']}
        observed = {(r['variant'], r['seed']) for r in results['rows']}
        if jobs != observed or len(observed) != len(results['rows']):
            raise AssertionError('缺失或重复样本')
        with zipfile.ZipFile(directory / 'actions.zip') as archive:
            for row in results['rows']:
                raw = archive.read(f"{row['variant']}/seed_{row['seed']}.actions.jsonl").decode('utf-8')
                actions += replay(raw, row, configs[row['variant']])
                cases += 1
        recalculated = benchmark.aggregate(results['rows'])
        if recalculated != results['summary']:
            raise AssertionError('失败率、置信上界或时间统计不一致')
        reports.append({'label': entry['label'], 'cases': len(results['rows']), 'status': 'PASS'})
        print(f"{entry['label']}: {len(results['rows'])} replayed", flush=True)
    report = {'status': 'PASS', 'cases': cases, 'actions': actions, 'runs': reports,
              'timestamp': datetime.now(timezone.utc).isoformat(),
              'evidence_index_sha256': hashlib.sha256((folder / 'index.json').read_bytes()).hexdigest(),
              'checks': ['source_hashes', 'archive_integrity', 'simulator_responses', 'virtual_time',
                         'no_failed_case_filtering', 'confidence_limit', 'risk_from_public_observations',
                         'strict_reference_coverage']}
    (folder / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
