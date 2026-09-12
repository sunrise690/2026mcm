from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path('/root/autodl-tmp/b0_iteration_20260912')
Q3 = ROOT / 'feedback_v2_q3'
Q4 = ROOT / 'feedback_v2_q4'
Q4_LIVE = Q4 / 'workspace' / 'code' / 'live_q4.py'
Q4_CORE = Q4 / 'workspace' / 'code' / 'q4_core.py'

# Best reliable Q3 candidate: true-hybrid, fixed repeated validation, 100% clear.
Q3_RECORD = Q3 / 'results' / 'best_fullclear.json'

# Best Q4 candidate by the pre-Round11 GitHub/cloud feedback score. Round11 dynamic
# route candidates are explicitly not used because their validated clear rate is lower.
Q4_RECORD = Q4 / 'round6_before_probe_batch_score_20260913_022101' / 'feedback_results' / 'best.json'


def literal(v):
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, bool):
        return 'True' if v else 'False'
    return repr(v)


def q4_tuner_pids() -> list[int]:
    out = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / 'cmdline').read_bytes().replace(b'\0', b' ')
            cwd = os.readlink(proc / 'cwd')
        except Exception:
            continue
        if b'feedback_tune_q4.py' in cmd and cwd == str(Q4):
            out.append(int(proc.name))
    return sorted(out)


def stop_q4_tuner() -> list[int]:
    old = q4_tuner_pids()
    for pid in old:
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    time.sleep(2)
    for pid in q4_tuner_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    return old


def patch_constants(path: Path, cfg: dict) -> list[str]:
    text = path.read_text(encoding='utf-8')
    changed = []
    for key, value in cfg.items():
        pattern = rf'(?m)^{re.escape(key)}\s*=\s*.*$'
        repl = f'{key}={literal(value)}'
        text2, n = re.subn(pattern, repl, text, count=1)
        if n:
            text = text2
            changed.append(key)
    text = re.sub(r'(?m)^VERSION\s*=\s*.*$', 'VERSION="github-best-fc32832baead"', text, count=1)
    path.write_text(text, encoding='utf-8')
    return changed


stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup = ROOT / f'github_best_apply_backup_{stamp}'
backup.mkdir(parents=True, exist_ok=False)
for p in (Q4_LIVE, Q4_CORE):
    shutil.copy2(p, backup / p.name)
if (Q4 / 'feedback_results').exists():
    shutil.copytree(Q4 / 'feedback_results', backup / 'q4_feedback_results')

q3_obj = json.loads(Q3_RECORD.read_text(encoding='utf-8'))
q4_obj = json.loads(Q4_RECORD.read_text(encoding='utf-8'))
q4_cfg = q4_obj['config']

stopped = stop_q4_tuner()

# Export Q3 official runnable best package and also keep the tuning JSON in-place.
subprocess.run(
    ['/root/miniconda3/bin/python', '-m', 'optimizer.export_best', '--record', str(Q3_RECORD), '--name', 'q3_github_best_fullclear'],
    cwd=str(Q3), check=True,
)
q3_export = Q3 / 'exported' / 'q3_github_best_fullclear'
q3_tuning_src = q3_export / 'workspace' / 'code' / 'q3_tuning.json'
q3_tuning_dst = Q3 / 'workspace' / 'code' / 'q3_tuning.json'
shutil.copy2(q3_tuning_src, q3_tuning_dst)

live_changed = patch_constants(Q4_LIVE, q4_cfg)
core_changed = patch_constants(Q4_CORE, q4_cfg)
(Q4 / 'current_github_best_config.json').write_text(json.dumps(q4_obj, ensure_ascii=False, indent=2), encoding='utf-8')

summary = {
    'timestamp': stamp,
    'backup': str(backup),
    'q3': {
        'record': str(Q3_RECORD),
        'candidate_id': q3_obj.get('candidate_id'),
        'mean_s_per_source': q3_obj.get('metrics', {}).get('mean_of_group_means'),
        'clear_rate': q3_obj.get('metrics', {}).get('clear_rate'),
        'export': str(q3_export),
        'active_tuning_json': str(q3_tuning_dst),
    },
    'q4': {
        'record': str(Q4_RECORD),
        'candidate_id': q4_obj.get('id'),
        'mean_s_per_source': q4_obj.get('mean_s_per_source'),
        'full_rate': q4_obj.get('full_rate'),
        'source_clear_rate': q4_obj.get('source_clear_rate'),
        'patched_live_constants': sorted(live_changed),
        'patched_core_constants': sorted(core_changed),
        'stopped_q4_tuner_pids': stopped,
        'active_config': str(Q4 / 'current_github_best_config.json'),
    },
    'policy': 'Use GitHub/cloud recorded best strategy; do not use lower-clear Round11 dynamic-route candidate.',
}
(ROOT / 'github_best_strategy_applied.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
