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


def stop_group(cwd_root, marker):
    victims = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            raw = (proc / 'cmdline').read_bytes()
            cwd = os.readlink(proc / 'cwd')
        except OSError:
            continue
        if marker in raw and str(cwd).startswith(str(cwd_root)):
            victims.append(int(proc.name))
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(1.0)
    return victims


def archive(root, name, paths):
    dst = root / f'{name}_{stamp}'
    dst.mkdir(parents=True, exist_ok=False)
    for p in paths:
        if not p.exists():
            continue
        if p.is_dir():
            shutil.copytree(p, dst / p.name)
        else:
            (dst / p.name).write_bytes(p.read_bytes())
    return dst


q3_archive = archive(Q3, 'round9_before_reliable_seed', [Q3/'optimizer'/'autotune.py', Q3/'results'/'state.json', Q3/'feedback_q3_v2.log'])
q4_archive = archive(Q4, 'round9_before_reliable_seed', [Q4/'feedback_tune_q4.py', Q4/'feedback_results'/'state.json', Q4/'feedback_q4_v2.log'])
q3_victims = stop_group(Q3, b'optimizer.autotune')
q4_victims = stop_group(Q4, b'feedback_tune_q4.py')

q3_auto = Q3 / 'optimizer' / 'autotune.py'
text = q3_auto.read_text(encoding='utf-8')
old = """    else:
        generation=0; default=load_default(); population=[]
        # Gen0 contains the same baseline parameters under all structural algorithms.
        # This makes the first comparison attributable to geometry, not random tuning noise.
        for mode in sorted(ALGORITHM_NAMES):
            if len(population)>=args.population:break
            c=dict(default);c['geometry_mode']=mode;population.append(repair(c))
        while len(population)<args.population:
            # Roughly half local around commit10 parameters, half broad exploration.
            population.append(random_config(rng,default,sigma=0.18) if len(population)<args.population*0.6 else random_config(rng))
"""
new = """    else:
        generation=0; default=load_default(); population=[]
        seeded=[]
        for name in ('best_fullclear.json','best_safe.json','best_score.json'):
            rec=load_json(RESULTS_DIR/name)
            if rec and isinstance(rec.get('config'),dict):
                seeded.append(repair(rec['config']))
        for c in seeded:
            if len(population)<args.population:population.append(c)
        # Gen0 contains the same baseline parameters under all structural algorithms.
        # This makes the first comparison attributable to geometry, not random tuning noise.
        for mode in sorted(ALGORITHM_NAMES):
            if len(population)>=args.population:break
            c=dict(default);c['geometry_mode']=mode;population.append(repair(c))
        seed_base=seeded[0] if seeded else default
        while len(population)<args.population:
            # Search locally around the best reliable mixed candidate, then broaden.
            population.append(random_config(rng,seed_base,sigma=0.12) if len(population)<args.population*0.7 else random_config(rng))
"""
if old not in text:
    raise SystemExit('Q3 autotune init block not found')
q3_auto.write_text(text.replace(old, new, 1), encoding='utf-8')
subprocess.run(['/root/miniconda3/bin/python','-m','py_compile',str(q3_auto)], check=True)
state = Q3 / 'results' / 'state.json'
if state.exists():
    state.rename(state.with_name(state.name + f'.round9_{stamp}'))

q4_tune = Q4 / 'feedback_tune_q4.py'
text = q4_tune.read_text(encoding='utf-8')
old = """ anchors=[BASE,
  dict(BASE,BOOTSTRAP_POINTS=1,STOP_RISK=.98,TAIL_BUDGET=4,PROBE_BATCH_SIZE=2),
  dict(BASE,BOOTSTRAP_POINTS=2,STOP_RISK=.995,TAIL_BUDGET=5,PROBE_BATCH_SIZE=2),
  dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.92,TAIL_BUDGET=2,MIN_SCAN_SEPARATION=180.0,PROBE_BATCH_SIZE=1),
  dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.85,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1)]
"""
new = """ anchors=[BASE,
  dict(BASE,BOOTSTRAP_POINTS=1,STOP_RISK=.98,TAIL_BUDGET=4,PROBE_BATCH_SIZE=2),
  dict(BASE,BOOTSTRAP_POINTS=2,STOP_RISK=.995,TAIL_BUDGET=5,PROBE_BATCH_SIZE=2),
  dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.92,TAIL_BUDGET=2,MIN_SCAN_SEPARATION=180.0,PROBE_BATCH_SIZE=1),
  dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.85,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1)]
 hof_path=ROOT/'coevo_results'/'hall_of_fame.json'
 if hof_path.exists():
  for rec in json.loads(hof_path.read_text()):
   if rec.get('full_rate',0)>=0.999 and isinstance(rec.get('config'),dict):
    anchors.append(dict(rec['config']))
    if len(anchors)>=12:break
 best_path=OUT/'best.json'
 if best_path.exists():
  rec=json.loads(best_path.read_text())
  if isinstance(rec.get('config'),dict):anchors.append(dict(rec['config']))
"""
if old not in text:
    raise SystemExit('Q4 anchors block not found')
q4_tune.write_text(text.replace(old, new, 1), encoding='utf-8')
subprocess.run(['/root/miniconda3/bin/python','-m','py_compile',str(q4_tune)], check=True)
state = Q4 / 'feedback_results' / 'state.json'
if state.exists():
    state.rename(state.with_name(state.name + f'.round9_{stamp}'))

env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', PYTHONUNBUFFERED='1')
(Q3/'feedback_q3_v2.log').open('a', encoding='utf-8').write('\n=== ROUND9: seed reliable mixed candidates ===\n')
q3_log=(Q3/'feedback_q3_v2.log').open('ab', buffering=0)
q3 = subprocess.Popen(['/root/miniconda3/bin/python','-m','optimizer.autotune','--generations','1000','--population','24','--workers','10','--fast-per-n','1','--medium-per-n','2','--final-per-n','5','--keep-fast','8','--keep-medium','3','--device','cpu','--timeout','120','--min-safe-clear','0.999999'], cwd=Q3, stdin=subprocess.DEVNULL, stdout=q3_log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
(Q3/'feedback_q3_v2.pid').write_text(str(q3.pid), encoding='utf-8')

(Q4/'feedback_q4_v2.log').open('a', encoding='utf-8').write('\n=== ROUND9: seed HOF full-clear candidates ===\n')
q4_log=(Q4/'feedback_q4_v2.log').open('ab', buffering=0)
q4 = subprocess.Popen(['/root/miniconda3/bin/python','feedback_tune_q4.py','--generations','1000','--population','30','--workers','12','--screen-per-n','2','--validate-per-n','10'], cwd=Q4, stdin=subprocess.DEVNULL, stdout=q4_log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
(Q4/'feedback_q4_v2.pid').write_text(str(q4.pid), encoding='utf-8')

print(json.dumps({'q3_archive':str(q3_archive),'q4_archive':str(q4_archive),'q3_killed':q3_victims,'q4_killed':q4_victims,'q3_pid':q3.pid,'q4_pid':q4.pid}, indent=2))
