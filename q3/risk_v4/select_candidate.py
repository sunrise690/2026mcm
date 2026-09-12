"""在查看新确认集之前，从完整开发对照中冻结一个候选。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import benchmark
from build_report import compare

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development', required=True)
    args = parser.parse_args()
    folder = Path(args.development)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    data = json.loads((folder / 'results.json').read_text(encoding='utf-8'))
    if not data['fingerprints_unchanged'] or manifest['hashes'] != benchmark.fingerprints():
        raise AssertionError('开发结果不是当前冻结源码')
    reference = json.loads((ROOT.parent / 'geometry_v3/evidence/development/results.json').read_text(encoding='utf-8'))
    refs = [dict(row, variant='certified_reference') for row in reference['rows'] if row['variant']=='v3_flow']
    choices = []
    selected = None
    for name, epsilon in [('risk005', 0.005), ('risk010', 0.01)]:
        summary = next(s for s in data['summary'] if s['variant']==name)
        paired = compare(data['rows'] + refs, name, 'certified_reference')
        eligible = (summary['errors']==0 and summary['failure_rate']<=0.005
                    and paired['cases']==300 and paired['relative_gain']>=0.10
                    and paired['saved_bootstrap95'][0]>0)
        choices.append({'variant': name, 'epsilon': epsilon, 'summary': summary, 'paired': paired, 'eligible': eligible})
        if selected is None and eligible:
            selected = name
    record = {'candidate': selected, 'frozen_at': datetime.now(timezone.utc).isoformat(),
              'rule': 'Among the two finalists, prefer the smaller model budget that meets development gain and risk screening. Final risk certification uses the untouched confirmation set.',
              'hashes': benchmark.fingerprints(), 'choices': choices,
              'confirmation_seeds_half_open': [70000, 70600]}
    (ROOT / 'evidence/selection.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if selected is None:
        raise RuntimeError('没有满足开发门禁的候选，不能使用确认集')


if __name__ == '__main__':
    main()
