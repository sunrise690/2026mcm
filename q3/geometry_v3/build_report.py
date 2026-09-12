"""从已结束的评测目录生成可核验电子包；不手工录入实验数值。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parent


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def paired(rows, candidate='v3_flow', baseline='planned_legacy'):
    a = {r['seed']: r for r in rows if r['variant'] == candidate}
    b = {r['seed']: r for r in rows if r['variant'] == baseline}
    seeds = sorted(a.keys() & b.keys())
    common_ok = [s for s in seeds if a[s]['ok'] and b[s]['ok']]
    if not common_ok:
        return None
    delta = np.array([b[s]['avg_clear_time_s'] - a[s]['avg_clear_time_s'] for s in common_ok])
    rng = np.random.default_rng(44107)
    boot = delta[rng.integers(0, len(delta), size=(10000, len(delta)))].mean(axis=1)
    base_mean = statistics.mean(b[s]['avg_clear_time_s'] for s in common_ok)
    return {'candidate': candidate, 'baseline': baseline, 'paired_cases': len(seeds),
            'common_fullclear_cases': len(common_ok), 'both_all_clear': len(common_ok) == len(seeds),
            'mean_saved_s_per_source': float(delta.mean()), 'relative_mean_reduction': float(delta.mean() / base_mean),
            'saved_s_per_source_bootstrap95': np.percentile(boot, [2.5, 97.5]).tolist(),
            'wins': int(np.count_nonzero(delta > 1e-8)), 'ties': int(np.count_nonzero(np.abs(delta) <= 1e-8)),
            'losses': int(np.count_nonzero(delta < -1e-8)),
            'scope': 'paired simulated scenes; bootstrap describes scene variation, not formal simulator performance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True, help='label=finished_run_directory')
    args = parser.parse_args()
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    index = {'runs': []}
    tables = []
    comparisons = {}
    for item in args.run:
        label, location = item.split('=', 1)
        if not label.replace('_', '').isalnum():
            raise ValueError('非法证据标签')
        source = Path(location)
        target = evidence / label
        target.mkdir(exist_ok=True)
        results = json.loads((source / 'results.json').read_text(encoding='utf-8'))
        manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
        if not results['fingerprints_unchanged']:
            raise AssertionError('拒绝归档源码漂移的结果')
        for name, expected in manifest['hashes'].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise AssertionError(f'源码已改变，必须重跑: {name}')
        shutil.copyfile(source / 'manifest.json', target / 'manifest.json')
        shutil.copyfile(source / 'results.json', target / 'results.json')
        with zipfile.ZipFile(target / 'actions.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for row in results['rows']:
                path = source / row['variant'] / f"seed_{row['seed']}.actions.jsonl"
                archive.write(path, f"{row['variant']}/{path.name}")
        index['runs'].append({'label': label, 'variants': manifest['variants'], 'cases': len(results['rows']),
                              'manifest_sha256': hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest(),
                              'results_sha256': hashlib.sha256((target / 'results.json').read_bytes()).hexdigest(),
                              'actions_sha256': hashlib.sha256((target / 'actions.zip').read_bytes()).hexdigest()})
        for s in results['summary']:
            tables.append((label, s))
        comparisons[label] = paired(results['rows'])
    dump(evidence / 'index.json', index)
    dump(evidence / 'paired_comparisons.json', comparisons)
    lines = ['# 离线仿真结果', '', '数值由 build_report.py 从每局结果自动生成。秒/源均值仅覆盖成功局；有失败的版本不进入全清耗时排名。', '',
             '| 数据集 | 版本 | 全清且满足该版本完成条件 | 秒/源 |', '|---|---|---:|---:|']
    for label, s in tables:
        lines.append(f"| {label} | {s['variant']} | {s['fullclear']}/{s['runs']} | {s['mean_fullclear_s_per_source']:.4f} |")
    lines += ['', '## 同场景配对比较', '', '正值表示新方案更快。区间为固定种子的 10000 次场景配对自举 95% 区间。', '']
    for label, pair in comparisons.items():
        if pair is not None:
            lo, hi = pair['saved_s_per_source_bootstrap95']
            lines.append(f"- {label}: v3_flow 相对 planned_legacy 平均节省 {pair['mean_saved_s_per_source']:.4f} s/源（{100*pair['relative_mean_reduction']:.2f}%），区间 [{lo:.4f}, {hi:.4f}]；快/平/慢={pair['wins']}/{pair['ties']}/{pair['losses']}，共同全清 {pair['common_fullclear_cases']}/{pair['paired_cases']}。")
    lines += ['', 'latest 是冻结提交 4be1da2 的概率软停止版，通常更快，但不提供连续域完整性证书。',
              '本目录提供独立严格全清方案，不替换 q3/current，也不声称击败其成功子集的耗时。', '',
              '所有正式数值须结合 evidence/audit.json 的动作重放与独立覆盖检查结果使用。', '']
    (ROOT / 'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(comparisons, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
