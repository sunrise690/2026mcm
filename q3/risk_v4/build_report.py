"""从完整运行生成报告、逐局动作归档及明确的发布判定。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def compare(rows, candidate, reference):
    selected = {r['seed']: r for r in rows if r['variant'] == candidate}
    refs = {r['seed']: r for r in rows if r['variant'] == reference}
    seeds = sorted(selected.keys() & refs.keys())
    if not seeds:
        return None
    if any(selected[s].get('avg_clear_time_s') is None or refs[s].get('avg_clear_time_s') is None for s in seeds):
        return {'valid': False, 'reason': 'missing_time'}
    a = np.array([selected[s]['avg_clear_time_s'] for s in seeds])
    b = np.array([refs[s]['avg_clear_time_s'] for s in seeds])
    delta = b-a
    rng = np.random.default_rng(412907)
    boot = delta[rng.integers(0, len(seeds), size=(10000, len(seeds)))].mean(axis=1)
    return {'valid': True, 'candidate': candidate, 'reference': reference, 'cases': len(seeds),
            'candidate_all_case_mean': float(a.mean()), 'reference_all_case_mean': float(b.mean()),
            'saved_s_per_source': float(delta.mean()), 'relative_gain': float(delta.mean()/b.mean()),
            'saved_bootstrap95': np.percentile(boot, [2.5, 97.5]).tolist(),
            'wins': int(np.count_nonzero(delta>1e-8)), 'ties': int(np.count_nonzero(abs(delta)<=1e-8)),
            'losses': int(np.count_nonzero(delta<-1e-8)), 'failed_cases_included': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    index = {'candidate': args.candidate, 'runs': []}
    tables = []
    comparisons = {}
    decision = {'status': 'WAITING_FOR_CONFIRMATION', 'candidate': args.candidate, 'publish_allowed': False}
    for item in args.run:
        label, location = item.split('=', 1)
        if not label.replace('_','').isalnum():
            raise ValueError('非法标签')
        source = Path(location)
        target = evidence / label
        target.mkdir(exist_ok=True)
        manifest, result = read(source / 'manifest.json'), read(source / 'results.json')
        if not result['fingerprints_unchanged']:
            raise AssertionError('运行期间源码改变')
        for path, expected in manifest['hashes'].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise AssertionError(f'需要重跑已改变的源码: {path}')
        for filename in ('manifest.json', 'results.json'):
            shutil.copyfile(source / filename, target / filename)
        with zipfile.ZipFile(target / 'actions.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for row in result['rows']:
                path = source / row['variant'] / f"seed_{row['seed']}.actions.jsonl"
                archive.write(path, f"{row['variant']}/{path.name}")
        index['runs'].append({'label': label, 'cases': len(result['rows']),
                              **{field: hashlib.sha256((target / name).read_bytes()).hexdigest()
                                 for name, field in (('manifest.json', 'manifest_sha256'), ('results.json', 'results_sha256'), ('actions.zip', 'actions_sha256'))}})
        tables.extend((label, s) for s in result['summary'])
        comparisons[label] = compare(result['rows'], args.candidate, 'certified_reference')
        if label == 'confirmation':
            protocol = read(ROOT / 'configs/protocol.json')
            selection = read(evidence / 'selection.json')
            if selection['candidate'] != args.candidate or selection['hashes'] != manifest['hashes']:
                raise AssertionError('确认候选或源码不同于预先冻结的选择')
            expected_seeds = list(range(*protocol['fresh_confirmation_range_half_open']))
            chosen = next(s for s in result['summary'] if s['variant']==args.candidate)
            pair = comparisons[label]
            risk_gate = chosen['runs'] >= 600 and chosen['errors']==0 and chosen['failure_rate_upper95']<=0.01
            time_gate = pair is not None and pair.get('valid') and pair['relative_gain']>=0.10 and pair['saved_bootstrap95'][0]>0
            seeds_gate = manifest['seeds'] == expected_seeds
            decision = {'status': 'PASS' if risk_gate and time_gate and seeds_gate else 'FAIL',
                        'candidate': args.candidate, 'risk_gate': risk_gate, 'gain_gate': bool(time_gate),
                        'seed_gate': seeds_gate, 'publish_allowed': bool(risk_gate and time_gate and seeds_gate),
                        'summary': chosen, 'paired': pair,
                        'authorization': 'User permitted very small risk for substantial gain and previously authorized pushing successful work.'}
    write(evidence / 'index.json', index)
    write(evidence / 'comparisons.json', comparisons)
    write(evidence / 'release_gate.json', decision)
    lines = ['# 风险预算几何算法仿真结果', '',
             '时间列包含失败局，逐局分母是实际清除源数。风险上界为单侧精确 95% 二项置信上界，不是控制器内部模型预算。', '',
             '| 数据集 | 算法 | 全清 | 失败率 | 失败率上界 | 全部局均值（秒/源） |', '|---|---|---:|---:|---:|---:|']
    for label, s in tables:
        mean = s['all_case_mean_s_per_cleared_source']
        display = '--' if mean is None else f'{mean:.4f}'
        lines.append(f"| {label} | {s['variant']} | {s['fullclear']}/{s['runs']} | {100*s['failure_rate']:.3f}% | {100*s['failure_rate_upper95']:.3f}% | {display} |")
    lines += ['', '## 配对时间收益', '']
    for label, pair in comparisons.items():
        if pair and pair.get('valid'):
            lo, hi = pair['saved_bootstrap95']
            lines.append(f"- {label}: 平均节省 {pair['saved_s_per_source']:.4f} 秒/源（{100*pair['relative_gain']:.2f}%）；95% 配对自举区间 [{lo:.4f}, {hi:.4f}]；快/平/慢={pair['wins']}/{pair['ties']}/{pair['losses']}。")
    lines += ['', '## 发布门禁', '', f"判定：{decision['status']}。发布许可计算值：{decision['publish_allowed']}。",
              '风险与收益必须同时通过 configs/protocol.json 的预设条件。正式发布还须通过 evidence/audit.json 的动作重放核验。', '',
              '结果适用于本次离线练习分布，不等于官方成绩。零次失败也不能报告为零风险。', '']
    (ROOT / 'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
