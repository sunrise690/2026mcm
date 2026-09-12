from __future__ import annotations
import argparse,json,random
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import cloud_autotune_q4 as core
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'feedback_results'; VERS=OUT/'versions'; STATE=OUT/'state.json'
SPACE={
 'STOP_RISK':[0.35,0.50,0.65,0.75,0.85,0.92,0.97],
 'TAIL_BUDGET':[0,1,2,3,4],
 'MIN_SCAN_SEPARATION':[120.0,180.0,240.0,300.0,400.0,500.0],
 'RESCAN_LIMIT':[0,1,2,3,4],
 'BOOTSTRAP_POINTS':[3,4,5,6,7,8],
}
BASE={'STOP_RISK':0.85,'TAIL_BUDGET':0,'MIN_SCAN_SEPARATION':300.0,'RESCAN_LIMIT':2,'BOOTSTRAP_POINTS':5}
def score(r):
 rows=r['rows']; by={n:[x for x in rows if x['N']==n] for n in range(10,17)}
 means={n:sum(x['per_true_n'] for x in a)/len(a) for n,a in by.items() if a}
 clears={n:sum(x['success'] for x in a)/len(a) for n,a in by.items() if a}
 mean=sum(means.values())/len(means); n10=means.get(10,mean); n16=means.get(16,mean)
 full=r['full_rate']; src=r['source_clear_rate']
 val=mean+9000*(1-full)+4500*(1-src)+15*max(0,mean-350)+7*max(0,n10-390)+2*max(0,n16-300)
 r.update(feedback_score=val,per_n_means=means,per_n_clear=clears)
 return r
def line(tag,r):
 m=r['per_n_means']; c=r['per_n_clear']
 return f"{tag} {r['id']} score={r['feedback_score']:.1f} mean={r['mean_s_per_source']:.1f} full={r['full_rate']:.1%} src={r['source_clear_rate']:.2%} N10={m.get(10,float('nan')):.1f}/{c.get(10,0):.0%} N16={m.get(16,float('nan')):.1f}/{c.get(16,0):.0%}"
def mutate(c,rng,rate=.45):
 d=dict(c); changed=False
 for k,v in SPACE.items():
  if rng.random()<rate:
   cur=d.get(k,BASE[k]); i=v.index(cur) if cur in v else len(v)//2
   opts=list(dict.fromkeys([v[max(0,i-1)],v[min(len(v)-1,i+1)],rng.choice(v)])); opts=[x for x in opts if x!=cur]
   if opts:d[k]=rng.choice(opts);changed=True
 if not changed:
  k=rng.choice(list(SPACE));d[k]=rng.choice(SPACE[k])
 return d
def evaluate(pop,seeds,workers,stage):
 out=[]
 with ProcessPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(core._worker_eval,(c,seeds,stage)) for c in pop]
  for f in as_completed(fs):out.append(score(f.result()))
 return sorted(out,key=lambda r:r['feedback_score'])
def slim(r):return {k:v for k,v in r.items() if k!='rows'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--generations',type=int,default=1000);ap.add_argument('--population',type=int,default=24);ap.add_argument('--workers',type=int,default=10);ap.add_argument('--screen-per-n',type=int,default=2);ap.add_argument('--validate-per-n',type=int,default=10);ap.add_argument('--resume',action='store_true');a=ap.parse_args()
 OUT.mkdir(exist_ok=True);VERS.mkdir(exist_ok=True)
 train=core.make_seed_bank(9710000,a.screen_per_n); valid=core.make_seed_bank(9810000,a.validate_per_n)
 rng=random.Random(20260913)
 anchors=[BASE,dict(BASE,BOOTSTRAP_POINTS=3,STOP_RISK=.65,TAIL_BUDGET=1),dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.75,TAIL_BUDGET=1,MIN_SCAN_SEPARATION=240.0),dict(BASE,BOOTSTRAP_POINTS=6,STOP_RISK=.92,TAIL_BUDGET=0)]
 start=0;pop=[];best=None
 if a.resume and STATE.exists():
  st=json.loads(STATE.read_text());start=st['generation'];pop=st['population'];best=st.get('best')
 else:
  pop=anchors[:]
  while len(pop)<a.population:pop.append({k:rng.choice(v) for k,v in SPACE.items()})
 for gen in range(start,a.generations):
  print(f'=== FEEDBACK Q4 gen {gen}/{a.generations-1} ===',flush=True)
  rows=evaluate(pop,train,a.workers,'feedback-screen')
  for r in rows[:4]:print(line('SCREEN',r),flush=True)
  finalists=[r['config'] for r in rows[:4]]
  if gen%5==0:
   vr=evaluate(finalists,valid,a.workers,'feedback-valid')
   for r in vr:print(line('VALID',r),flush=True)
   winner=vr[0]
   if best is None or winner['feedback_score']<best['feedback_score']:
    best=slim(winner); p=VERS/f"gen_{gen:04d}_{winner['id']}.json";p.write_text(json.dumps(best,indent=2));(OUT/'best.json').write_text(json.dumps(best,indent=2));print('NEW_BEST',p,flush=True)
  elites=[r['config'] for r in rows[:max(4,a.population//4)]]
  pop=list(elites)
  while len(pop)<a.population:
   if rng.random()<.12:pop.append({k:rng.choice(v) for k,v in SPACE.items()})
   else:pop.append(mutate(rng.choice(elites),rng,.35+.25*rng.random()))
  STATE.write_text(json.dumps({'generation':gen+1,'population':pop,'best':best},indent=2))
if __name__=='__main__':main()
