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
Q4 = ROOT / 'feedback_v2_q4'
TARGET = Q4 / 'workspace' / 'code' / 'q4_targeted_rescue_v3.py'


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


stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup = Q4 / f'round11_before_dynamic_speed_{stamp}'
backup.mkdir(parents=True, exist_ok=False)
shutil.copy2(TARGET, backup / TARGET.name)

text = TARGET.read_text(encoding='utf-8')
text2, n = re.subn(r'def _particles\(no_signal_points, count=\d+, directional_prior=0\.55\):',
                   'def _particles(no_signal_points, count=80000, directional_prior=0.55):',
                   text, count=1)
if n != 1:
    raise RuntimeError('could not patch _particles default count')
text2, n2 = re.subn(r'def _tail_particles\(no_signal_points, count=\d+\):',
                    'def _tail_particles(no_signal_points, count=24000):',
                    text2, count=1)
if n2 != 1:
    raise RuntimeError('could not patch _tail_particles default count')
TARGET.write_text(text2, encoding='utf-8')

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

log_path = Q4 / 'feedback_q4_v2.log'
with log_path.open('ab') as log:
    log.write(b'\n=== ROUND11: dynamic-route speed restart ===\n')
    proc = subprocess.Popen(
        ['/root/miniconda3/bin/python', 'feedback_tune_q4.py', '--generations', '1000',
         '--population', '40', '--workers', '12', '--screen-per-n', '2', '--validate-per-n', '10'],
        cwd=str(Q4), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
(Q4 / 'feedback_q4_v2.pid').write_text(str(proc.pid), encoding='utf-8')
print(json.dumps({
    'round': '11-speed',
    'old_pids': old,
    'pid': proc.pid,
    'backup': str(backup),
    'changes': [
        'posterior probe particles reduced from 200000 to 80000 for faster non-fixed-route search',
        'tail probe particles reduced to 24000',
        'restarted Q4 dynamic-route tuner cleanly by process group',
    ],
}, indent=2))
