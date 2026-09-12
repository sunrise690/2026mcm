from pathlib import Path
import os, signal, time, json, shutil, subprocess
R=Path('/root/autodl-tmp/b0_iteration_20260912')
stamp=time.strftime('%Y%m%d_%H%M%S')
# Stop only feedback-v2 optimizer processes whose cwd is inside the two target directories.
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        cwd=(p/'cwd').resolve()
        cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='ignore')
    except Exception:
        continue
    if (str(cwd).startswith(str(R/'feedback_v2_q3')) or str(cwd).startswith(str(R/'feedback_v2_q4'))) and ('optimizer.autotune' in cmd or 'feedback_tune_q4.py' in cmd):
        try:
            os.kill(int(p.name), signal.SIGTERM)
            print('STOP',p.name,cmd[:120])
        except ProcessLookupError:
            pass
time.sleep(3)

# Q4: replace the invalid consecutive-channel posterior with a count posterior.
q4=R/'feedback_v2_q4'
riskf=q4/'workspace/code/channel_risk.py'
s=riskf.read_text(encoding='utf-8')
start=s.index('def remaining_risk(')
new_func='''def remaining_risk(beliefs: dict, found: set[int]) -> tuple[float,int|None]:\n    """Return P(total source count exceeds detections) under N~Uniform{10..16}.\n\n    Active channel IDs are an unknown subset of 1..20, so channel order carries no\n    count information.  Detection probability is estimated from the actual no-signal\n    survey geometry and the Q4 omni/directional mixture.\n    """\n    import math\n    k=len(found)\n    unknown=[c for c,b in beliefs.items() if b.get("status")=="unknown"]\n    if k<10:\n        return 1.0,(unknown[0] if unknown else None)\n    if k>=16 or not unknown:\n        return 0.0,None\n    survivals=[_channel_survival(beliefs[c]) for c in unknown]\n    survival=float(np.mean(survivals)) if survivals else 0.0\n    q=max(1e-6,min(1.0-1e-9,1.0-survival))\n    weights=[]\n    for n in range(k,17):\n        weights.append(math.comb(n,k)*(q**k)*((1.0-q)**(n-k)))\n    z=float(sum(weights))\n    p_same=0.0 if z<=0.0 else float(weights[0]/z)\n    return 1.0-p_same,(unknown[0] if unknown else None)\n'''
s=s[:start]+new_func
riskf.write_text(s,encoding='utf-8')

# Expand the stopping threshold search and include an aggressive 2-point anchor.
tuner=q4/'feedback_tune_q4.py'
s=tuner.read_text(encoding='utf-8')
s=s.replace("'STOP_RISK':[0.35,0.50,0.65,0.75,0.85,0.92,0.97]", "'STOP_RISK':[0.08,0.15,0.25,0.35,0.50,0.65,0.80]")
s=s.replace("'BOOTSTRAP_POINTS':[3,4,5,6,7,8]", "'BOOTSTRAP_POINTS':[2,3,4,5,6,7]")
s=s.replace("BASE={'STOP_RISK':0.85", "BASE={'STOP_RISK':0.35")
s=s.replace("anchors=[BASE,\n  dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.65,TAIL_BUDGET=1),", "anchors=[BASE,\n  dict(BASE,BOOTSTRAP_POINTS=2,STOP_RISK=.25,TAIL_BUDGET=1),\n  dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.15,TAIL_BUDGET=1),")
tuner.write_text(s,encoding='utf-8')

# Q3: delay all source-clearing travel until at least ten sources are discovered.
q3=R/'feedback_v2_q3'
ctrl=q3/'workspace/code/q3_controller.py'
s=ctrl.read_text(encoding='utf-8')
needle='''                # Structural gene: coverage-first modes may delay early clears until a\n                # minimum discovery count, exploiting the hard Q3 prior N>=10.\n                if detected and self.geometry_mode() in (1,4) and k<int(self.g("coverage_preclear_min_known")):\n'''
insert='''                # Round 3: build a batch before route service. Early clear trips fragment\n                # the route most severely for N=10; all geometry families may defer them.\n                batch_min=int(self.g("batch_preclear_min_known"))\n                if detected and k<batch_min:\n                    ep=self.exploration_point()\n                    if ep is not None:\n                        print(f"[结构策略] batch-preclear: 已发现{k}，先集中普查到{batch_min}源",flush=True)\n                        self.scan_unknown(ep);self.scan_info(ep,limit=int(self.g("probe_info_limit")));continue\n                # Coverage-first modes may continue deferring beyond the common batch floor.\n                if detected and self.geometry_mode() in (1,4) and k<int(self.g("coverage_preclear_min_known")):\n'''
if needle not in s:
    raise RuntimeError('Q3 insertion point not found')
s=s.replace(needle,insert)
ctrl.write_text(s,encoding='utf-8')
sp=q3/'optimizer/search_space.py'
s=sp.read_text(encoding='utf-8')
needle2="    Param('coverage_preclear_min_known', 6, 10, 'int', 1),"
if "Param('batch_preclear_min_known'" not in s:
    s=s.replace(needle2,"    Param('batch_preclear_min_known', 8, 10, 'int', 1),\n"+needle2)
sp.write_text(s,encoding='utf-8')
cfgp=q3/'configs/default.json'
cfg=json.loads(cfgp.read_text(encoding='utf-8'))
cfg['batch_preclear_min_known']=10
cfg['coverage_preclear_min_known']=10
cfg['probe_info_limit']=8
cfgp.write_text(json.dumps(cfg,indent=2),encoding='utf-8')

# Archive search outputs but retain the deterministic Q3 seed bank.
q3res=q3/'results'
if q3res.exists():
    archive=q3/f'round2_results_{stamp}'
    q3res.rename(archive)
    (q3/'results').mkdir()
    seed=archive/'seed_bank.json'
    if seed.exists(): shutil.copy2(seed,q3/'results/seed_bank.json')
q4res=q4/'feedback_results'
if q4res.exists(): q4res.rename(q4/f'round2_feedback_results_{stamp}')
for logname in ('feedback_q3_v2.log','feedback_q4_v2.log'):
    with (R/logname).open('a',encoding='utf-8') as f:
        f.write(f'\n=== ROUND3 {stamp}: Q3 batch-preclear; Q4 count-posterior early stop ===\n')

files=[ctrl,sp,riskf,q4/'workspace/code/live_q4.py',tuner]
for x in files:
    subprocess.run(['/root/miniconda3/bin/python','-m','py_compile',str(x)],check=True)
print('ROUND3_PATCH_OK',stamp)
