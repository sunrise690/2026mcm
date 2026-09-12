from pathlib import Path
import datetime
import json
import os
import signal
import shutil
import subprocess
import time

ROOT = Path('/root/autodl-tmp/b0_iteration_20260912')
Q3 = ROOT / 'feedback_v2_q3'
Q4 = ROOT / 'feedback_v2_q4'
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


def proc_matches(proc, cwd_root, marker):
    try:
        raw = (proc / 'cmdline').read_bytes()
        cwd = os.readlink(proc / 'cwd')
    except OSError:
        return False
    return marker in raw and str(cwd).startswith(str(cwd_root))


def stop_group(cwd_root, marker):
    victims = []
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit() and proc_matches(proc, cwd_root, marker):
            victims.append(int(proc.name))
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(1.0)
    return victims


def archive_one(root, name, paths):
    archive = root / f'{name}_{stamp}'
    archive.mkdir(parents=True, exist_ok=False)
    for p in paths:
        if p.exists():
            dst = archive / p.name
            if p.is_dir():
                shutil.copytree(p, dst)
            else:
                dst.write_bytes(p.read_bytes())
    return archive


q3_archive = archive_one(Q3, 'round8_before_sparse_bootstrap', [
    Q3 / 'workspace' / 'code' / 'q3_controller.py',
    Q3 / 'optimizer' / 'evaluate.py',
    Q3 / 'optimizer' / 'search_space.py',
    Q3 / 'configs' / 'default.json',
    Q3 / 'feedback_q3_v2.log',
    Q3 / 'results' / 'state.json',
])
q4_archive = archive_one(Q4, 'round8_before_speed_rebalance', [
    Q4 / 'workspace' / 'code' / 'live_q4.py',
    Q4 / 'feedback_tune_q4.py',
    Q4 / 'feedback_q4_v2.log',
    Q4 / 'feedback_results' / 'state.json',
])

q3_victims = stop_group(Q3, b'optimizer.autotune')
q4_victims = stop_group(Q4, b'feedback_tune_q4.py')

q3_ctrl = Q3 / 'workspace' / 'code' / 'q3_controller.py'
text = q3_ctrl.read_text(encoding='utf-8')
old = """    def bootstrap_point(self):
        best=None;cur=np.asarray(self.c.position,float)
        for r,n in [(700,24),(900,24),(1100,24)]:
"""
new = """    def bootstrap_point(self):
        best=None;cur=np.asarray(self.c.position,float)
        radii=[(650,24),(800,24),(950,24)] if self.known()<=3 else [(700,24),(900,24),(1100,24)]
        for r,n in radii:
"""
if old not in text:
    raise SystemExit('Q3 bootstrap_point pattern not found')
q3_ctrl.write_text(text.replace(old, new, 1), encoding='utf-8')
subprocess.run(['/root/miniconda3/bin/python', '-m', 'py_compile', str(q3_ctrl)], check=True)

state = Q3 / 'results' / 'state.json'
if state.exists():
    state.rename(state.with_name(state.name + f'.round8_{stamp}'))

q4_tune = Q4 / 'feedback_tune_q4.py'
text = q4_tune.read_text(encoding='utf-8')
repls = {
    "'STOP_RISK':[0.25,0.35,0.50,0.65,0.75,0.85,0.92],": "'STOP_RISK':[0.35,0.50,0.65,0.75,0.85,0.92,0.96,0.98,0.995],",
    "'TAIL_BUDGET':[0,1,2,3,4],": "'TAIL_BUDGET':[0,1,2,3,4,5],",
    "'BOOTSTRAP_POINTS':[2,3,4,5],": "'BOOTSTRAP_POINTS':[1,2,3,4,5],",
    "BASE={'STOP_RISK':0.75,'TAIL_BUDGET':1,'MIN_SCAN_SEPARATION':240.0,'RESCAN_LIMIT':1,'BOOTSTRAP_POINTS':4,'PROBE_BATCH_SIZE':1}": "BASE={'STOP_RISK':0.92,'TAIL_BUDGET':2,'MIN_SCAN_SEPARATION':240.0,'RESCAN_LIMIT':1,'BOOTSTRAP_POINTS':2,'PROBE_BATCH_SIZE':1}",
    "val=(mean+22000*(1-full)+10000*(1-src)+20*max(0,mean-350)+16*max(0,n10-390)+2*max(0,n16-300)+4500*max(0,1-clears.get(10,0))+2500*max(0,1-clears.get(16,0)))": "val=(mean+42000*(1-full)+18000*(1-src)+26*max(0,mean-350)+34*max(0,n10-350)+4*max(0,n16-300)+9000*max(0,1-clears.get(10,0))+4500*max(0,1-clears.get(16,0)))",
    "  dict(BASE,BOOTSTRAP_POINTS=2,STOP_RISK=.75,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1),\n  dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.85,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1),\n  dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.65,TAIL_BUDGET=2,MIN_SCAN_SEPARATION=240.0,PROBE_BATCH_SIZE=1),\n  dict(BASE,BOOTSTRAP_POINTS=5,STOP_RISK=.92,TAIL_BUDGET=0,PROBE_BATCH_SIZE=2)]": "  dict(BASE,BOOTSTRAP_POINTS=1,STOP_RISK=.98,TAIL_BUDGET=4,PROBE_BATCH_SIZE=2),\n  dict(BASE,BOOTSTRAP_POINTS=2,STOP_RISK=.995,TAIL_BUDGET=5,PROBE_BATCH_SIZE=2),\n  dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.92,TAIL_BUDGET=2,MIN_SCAN_SEPARATION=180.0,PROBE_BATCH_SIZE=1),\n  dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.85,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1)]",
}
for old, new in repls.items():
    if old not in text:
        raise SystemExit(f'Q4 tune pattern not found: {old[:80]}')
    text = text.replace(old, new)
q4_tune.write_text(text, encoding='utf-8')
subprocess.run(['/root/miniconda3/bin/python', '-m', 'py_compile', str(q4_tune)], check=True)

state = Q4 / 'feedback_results' / 'state.json'
if state.exists():
    state.rename(state.with_name(state.name + f'.round8_{stamp}'))

env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', PYTHONUNBUFFERED='1')

(Q3 / 'feedback_q3_v2.log').open('a', encoding='utf-8').write('\n=== ROUND8: sparse bootstrap radii, restart search ===\n')
q3_log = (Q3 / 'feedback_q3_v2.log').open('ab', buffering=0)
q3_proc = subprocess.Popen([
    '/root/miniconda3/bin/python', '-m', 'optimizer.autotune',
    '--generations', '1000', '--population', '24', '--workers', '10',
    '--fast-per-n', '1', '--medium-per-n', '2', '--final-per-n', '5',
    '--keep-fast', '8', '--keep-medium', '3', '--device', 'cpu',
    '--timeout', '120', '--min-safe-clear', '0.999999',
], cwd=Q3, stdin=subprocess.DEVNULL, stdout=q3_log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
(Q3 / 'feedback_q3_v2.pid').write_text(str(q3_proc.pid), encoding='utf-8')

(Q4 / 'feedback_q4_v2.log').open('a', encoding='utf-8').write('\n=== ROUND8: speed/full-clear rebalance, restart search ===\n')
q4_log = (Q4 / 'feedback_q4_v2.log').open('ab', buffering=0)
q4_proc = subprocess.Popen([
    '/root/miniconda3/bin/python', 'feedback_tune_q4.py',
    '--generations', '1000', '--population', '30', '--workers', '12',
    '--screen-per-n', '2', '--validate-per-n', '10',
], cwd=Q4, stdin=subprocess.DEVNULL, stdout=q4_log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
(Q4 / 'feedback_q4_v2.pid').write_text(str(q4_proc.pid), encoding='utf-8')

print(json.dumps({
    'q3_archive': str(q3_archive),
    'q4_archive': str(q4_archive),
    'q3_killed': q3_victims,
    'q4_killed': q4_victims,
    'q3_pid': q3_proc.pid,
    'q4_pid': q4_proc.pid,
}, indent=2))
