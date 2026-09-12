from pathlib import Path
import csv
import datetime
import json
import re

ROOT = Path('/root/autodl-tmp/b0_iteration_20260912')


def ts(path):
    return datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else '-'


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def q3_from_best(path):
    obj = read_json(path)
    if not obj:
        return None
    metrics = obj.get('metrics', obj)
    groups = {int(g.get('N')): g for g in metrics.get('groups', []) if g.get('N') in (10, 16)}
    return {
        'kind': 'q3_best',
        'id': metrics.get('candidate_id') or obj.get('candidate_id'),
        'gen': obj.get('generation'),
        'mean': metrics.get('mean_of_group_means') or metrics.get('sample_mean'),
        'clear': metrics.get('clear_rate'),
        'src_clear': metrics.get('source_clear_rate'),
        'N10': groups.get(10),
        'N16': groups.get(16),
        'mtime': ts(path),
    }


def q4_from_hof(path):
    obj = read_json(path)
    if not obj:
        return None
    top = obj[0] if isinstance(obj, list) and obj else obj
    out = {
        'kind': 'q4_hof',
        'id': top.get('id'),
        'stage': top.get('stage'),
        'mean': top.get('mean_s_per_source'),
        'clear': top.get('full_rate'),
        'src_clear': top.get('source_clear_rate'),
        'mtime': ts(path),
        'N10': None,
        'N16': None,
    }
    for key in ('groups', 'by_n', 'n_stats', 'per_n'):
        val = top.get(key)
        if isinstance(val, list):
            for g in val:
                n = g.get('N') or g.get('n') or g.get('sources')
                if n in (10, 16):
                    out[f'N{n}'] = g
        elif isinstance(val, dict):
            for n in (10, 16):
                g = val.get(str(n)) or val.get(n)
                if g:
                    out[f'N{n}'] = g
    return out


def q4_from_csv(summary_path, cases_path):
    summary = read_json(summary_path)
    if not summary or not cases_path.exists():
        return None
    rows = list(csv.DictReader(cases_path.open(newline='', encoding='utf-8')))
    by = {10: [], 16: []}
    for row in rows:
        n = int(float(row.get('n_sources') or row.get('N') or row.get('n') or -1))
        if n in by:
            by[n].append(row)
    def stat(rows):
        if not rows:
            return None
        value_keys = ['s_per_source', 'seconds_per_source', 'time_per_source', 'mean_s_per_source', 'seconds_per_src', 'avg_s_per_source']
        vals = []
        for r in rows:
            raw = next((r.get(k) for k in value_keys if r.get(k) not in (None, '')), None)
            if raw is not None:
                vals.append(float(raw))
        clears = []
        for r in rows:
            raw = r.get('full_clear') or r.get('fullclear') or r.get('is_fullclear') or r.get('cleared') or r.get('clear')
            clears.append(str(raw).lower() in ('1', 'true', 'yes'))
        if not vals:
            return {'runs': len(rows), 'clear_rate': sum(clears)/len(clears) if clears else None, 'columns': list(rows[0].keys())}
        return {'mean': sum(vals)/len(vals), 'runs': len(vals), 'clear_rate': sum(clears)/len(clears) if clears else None}
    return {
        'kind': 'q4_validation',
        'id': summary.get('id') or summary.get('candidate_id') or summary.get('best_id'),
        'mean': summary.get('mean_s_per_source') or summary.get('mean'),
        'clear': summary.get('full_rate') or summary.get('clear_rate'),
        'src_clear': summary.get('source_clear_rate'),
        'mtime': ts(summary_path),
        'N10': stat(by[10]),
        'N16': stat(by[16]),
    }


def q4_from_log(path):
    if not path.exists():
        return None
    text = path.read_text(encoding='utf-8', errors='replace')[-200000:]
    rows = []
    pat = re.compile(r'^(SCREEN|VALID)\s+(\w+)\s+score=([0-9.]+)\s+mean=([0-9.]+)\s+full=([0-9.]+)%\s+src=([0-9.]+)%\s+N10=([0-9.]+)/([0-9.]+)%\s+N16=([0-9.]+)/([0-9.]+)%', re.M)
    for m in pat.finditer(text):
        rows.append({
            'stage': m.group(1),
            'id': m.group(2),
            'mean': float(m.group(4)),
            'clear': float(m.group(5))/100,
            'src_clear': float(m.group(6))/100,
            'N10': {'mean': float(m.group(7)), 'clear_rate': float(m.group(8))/100},
            'N16': {'mean': float(m.group(9)), 'clear_rate': float(m.group(10))/100},
        })
    valids = [r for r in rows if r['stage'] == 'VALID']
    screens = [r for r in rows if r['stage'] == 'SCREEN']
    chosen = (valids or screens)
    if not chosen:
        return None
    best = sorted(chosen, key=lambda r: ((1-r['clear'])*10000, r['mean']))[0]
    best.update({'kind': 'q4_log', 'mtime': ts(path), 'seen_rows': len(rows), 'valid_rows': len(valids)})
    return best


def fmt_group(g):
    if not g:
        return '未输出'
    mean = g.get('mean') or g.get('mean_s_per_source') or g.get('s_per_source') or g.get('seconds_per_source')
    clear = g.get('clear_rate') or g.get('full_rate') or g.get('fullclear_rate')
    runs = g.get('runs') or g.get('n') or g.get('samples') or g.get('count')
    full = g.get('fullclear') or g.get('fullclear_runs')
    if runs is None and full is not None:
        runs = '?'
    if clear is None and runs and full not in (None, '?'):
        clear = full / runs
    parts = []
    parts.append(f"{float(mean):.1f}s/源" if mean is not None else '秒/源未输出')
    parts.append(f"全清率{float(clear)*100:.1f}%" if clear is not None else '全清率未输出')
    parts.append(f"样本量{runs}" if runs is not None else '样本量未输出')
    return ', '.join(parts)


items = [
    ('主Q3历史', q3_from_best(ROOT/'q3_cloud_autotune_5090_multialgo/results/best_fullclear.json')),
    ('主Q4历史', q4_from_csv(ROOT/'q4_v371_cloud_multi_5090/autotune_results/best_validation_summary.json', ROOT/'q4_v371_cloud_multi_5090/autotune_results/best_validation_cases.csv') or q4_from_hof(ROOT/'q4_v371_cloud_multi_5090/coevo_results/hall_of_fame.json')),
    ('真正混合Q3', q3_from_best(ROOT/'feedback_v2_q3/results/best_fullclear.json')),
    ('真正混合Q4', q4_from_log(ROOT/'feedback_v2_q4/feedback_q4_v2.log') or q4_from_hof(ROOT/'feedback_v2_q4/coevo_results/hall_of_fame.json')),
]

for name, item in items:
    print('ITEM', name)
    if not item:
        print('  未输出')
        continue
    print('  kind', item.get('kind'), 'id', item.get('id'), 'mtime', item.get('mtime'), 'mean', item.get('mean'), 'clear', item.get('clear'), 'src_clear', item.get('src_clear'))
    if item.get('gen') is not None:
        print('  generation', item.get('gen'))
    if item.get('stage'):
        print('  stage', item.get('stage'), 'seen_rows', item.get('seen_rows'), 'valid_rows', item.get('valid_rows'))
    print('  N10', fmt_group(item.get('N10')))
    print('  N16', fmt_group(item.get('N16')))
