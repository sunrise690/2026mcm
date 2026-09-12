"""重放归档动作并独立复核指标、源码哈希与逐频道完成证书。"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'simulator')]
import jammers_offline_sim as sim
from coverage_geometry import verify_cells


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def replay(actions, row, certified):
    seed = row['seed']
    seed_key = hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()
    engine = sim.Engine(sim.generate_practice(3, seed_key), record_trace=False)
    stations = defaultdict(set)
    cleared = set()
    count = 0
    for line in actions.splitlines():
        item = json.loads(line)
        action, args = item['action'], item['args']
        expected = getattr(engine, action)(*args)
        recorded = item['response']
        for key in ('accepted', 'virtual_time_s', 'measure_result', 'svd_deg', 'clear_result', 'exit_reason'):
            if recorded.get(key) != expected.get(key):
                raise AssertionError(f"{row['variant']}/{seed} 动作{count}字段{key}重放不一致")
        if recorded.get('accepted'):
            if action == 'measure' and recorded.get('measure_result') == 'no_signal':
                stations[int(args[2])].add(tuple(args[:2]))
            if action == 'clear' and recorded.get('clear_result') == 'success':
                cleared.add(int(args[2]))
        count += 1
    summary = engine.summary()
    if summary != row['engine_summary']:
        raise AssertionError(f"{row['variant']}/{seed} 引擎摘要不一致")
    for key, expected in (('N', summary['jammer_count']), ('cleared', summary['cleared_count']),
                          ('virtual_time_s', summary['virtual_time_s'])):
        if row[key] != expected:
            raise AssertionError(f'{seed} 指标 {key} 不一致')
    avg = summary['virtual_time_s'] / summary['cleared_count'] if summary['cleared_count'] else None
    if row['avg_clear_time_s'] != avg:
        raise AssertionError(f'{seed} 秒/源分母不一致')
    proof_ok = True
    if certified and row['ok'] and len(cleared) < 16:
        keys = {tuple(sorted(stations[ch])) for ch in range(1, 21) if ch not in cleared}
        proof_ok = all(verify_cells(key)[0] for key in keys)
        if not proof_ok:
            raise AssertionError(f'{seed} 日志未提供覆盖证据')
    actual_ok = (len(cleared) == summary['jammer_count'] and row['error'] is None
                 and summary['exited'] and not summary['timed_out']
                 and (not certified or row['controller_end'].get('completion_verified') is True))
    if row['ok'] != actual_ok:
        raise AssertionError(f'{seed} 全清门禁不一致')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', default=str(ROOT / 'evidence'))
    args = parser.parse_args()
    directory = Path(args.evidence)
    index = load(directory / 'index.json')
    checked_cases = 0
    checked_actions = 0
    details = []
    for entry in index['runs']:
        folder = directory / entry['label']
        for filename, key in (('manifest.json', 'manifest_sha256'), ('results.json', 'results_sha256'),
                              ('actions.zip', 'actions_sha256')):
            if hashlib.sha256((folder / filename).read_bytes()).hexdigest() != entry[key]:
                raise AssertionError(f'{entry["label"]} 归档哈希错误: {filename}')
        manifest = load(folder / 'manifest.json')
        results = load(folder / 'results.json')
        if not results['fingerprints_unchanged']:
            raise AssertionError('原评测期间源码发生变更')
        for name, expected in manifest['hashes'].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise AssertionError(f'{entry["label"]} 当前源码与归档不同: {name}')
        expected_jobs = {(v, s) for v in manifest['variants'] for s in manifest['seeds']}
        actual_jobs = {(r['variant'], r['seed']) for r in results['rows']}
        if expected_jobs != actual_jobs or len(actual_jobs) != len(results['rows']):
            raise AssertionError('存在缺失或重复评测任务')
        if entry['label'] == 'confirmation':
            protocol = load(ROOT / 'configs/evaluation_protocol.json')
            expected_seeds = list(range(*protocol['fresh_confirmation_range_half_open']))
            if manifest['seeds'] != expected_seeds:
                raise AssertionError('确认集不符合预设协议')
            candidate = [r for r in results['rows'] if r['variant'] == protocol['candidate']]
            if len(candidate) != len(expected_seeds) or not all(r['ok'] for r in candidate):
                raise AssertionError('确认集未通过全清发布门禁')
        with zipfile.ZipFile(folder / 'actions.zip') as archive:
            for row in results['rows']:
                actions = archive.read(f"{row['variant']}/seed_{row['seed']}.actions.jsonl").decode('utf-8')
                checked_actions += replay(actions, row, row['variant'] != 'latest')
                checked_cases += 1
        for summary in results['summary']:
            rows = [r for r in results['rows'] if r['variant'] == summary['variant']]
            successful = [r for r in rows if r['ok']]
            if len(successful) != summary['fullclear']:
                raise AssertionError('汇总全清数量错误')
            if successful and statistics.mean(r['avg_clear_time_s'] for r in successful) != summary['mean_fullclear_s_per_source']:
                raise AssertionError('汇总平均时间错误')
        details.append({'label': entry['label'], 'cases': len(results['rows']), 'passed': True})
        print(f"核验 {entry['label']}: {len(results['rows'])} 局通过", flush=True)
    report = {'status': 'PASS', 'checked_cases': checked_cases, 'checked_actions': checked_actions,
              'generated_at': datetime.now(timezone.utc).isoformat(), 'runs': details,
              'evidence_index_sha256': hashlib.sha256((directory / 'index.json').read_bytes()).hexdigest(),
              'checks': ['source_hashes', 'simulator_replay', 'action_responses', 'virtual_time',
                         'full_clear_metrics', 'accepted_exit', 'independent_closed_cell_coverage']}
    (directory / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
