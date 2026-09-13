from pathlib import Path
import sys, os, json, statistics, contextlib, io, importlib.util, hashlib, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'q3'/'bench'; SIM=BENCH/'jammers_offline_sim.py'; CTRL=ROOT/'q3'/'current'/'tunable_controller.py'; CFG=ROOT/'q3'/'current'/'alg_sparseboot3.json'
sys.path.insert(0,str(BENCH))
from sim_payload import write_sim
if not SIM.exists():write_sim(SIM)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def sb(seed):return hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()
# deterministically collect 5 cases for each N=10,11,12
_sim0=load('sim_collect',SIM);cases={10:[],11:[],12:[]};seed=1000
while any(len(v)<5 for v in cases.values()):
 sc=_sim0.generate_practice(3,sb(seed));n=len(sc.jammers)
 if n in cases and len(cases[n])<5:cases[n].append(seed)
 seed+=1
CASES=sum((cases[n] for n in (10,11,12)),[])
V={
 'base':(1e9,1.1),
 'd1200_p35':(1200,.35),'d1000_p35':(1000,.35),'d800_p35':(800,.35),'d600_p35':(600,.35),
 'd1200_p30':(1200,.30),'d1000_p30':(1000,.30),'d800_p30':(800,.30),
 'd1000_p25':(1000,.25),'d800_p25':(800,.25),
}
def work(arg):
 label,cap,pfloor,seed=arg;sim=load(f's_{label}_{seed}',SIM);base=json.loads(CFG.read_text())['tune'];base['route_scan_value_s']=550;os.environ['Q3_TUNE_JSON']=json.dumps(base)
 ctrl=load(f'c_{label}_{seed}',CTRL);C=ctrl.Q3ParticleController;orig=C.exploration_point
 def ep(self):
  q=orig(self)
  if q is None:return None
  k=self.known()
  if 10<=k<=12 and len(self.cleared)>=k:
   d=float(np.linalg.norm(np.asarray(q,float)-np.asarray(self.c.position,float)));ps=float(self.posterior_same_count())
   if d>=cap and ps>=pfloor:return None
  return q
 C.exploration_point=ep
 sc=sim.generate_practice(3,sb(seed));e=sim.Engine(sc,record_trace=False)
 class Client:
  def __init__(self,e):self.e=e;self.last_response={}
  @property
  def position(self):return np.array([self.e.x,self.e.y],float)
  @property
  def receiver_channel(self):return self.e.receiver_channel
  def enter(self):self.last_response=self.e.enter();return self.last_response
  def measure(self,x,y,ch):self.last_response=self.e.measure(x,y,ch);return self.last_response
  def clear(self,x,y,ch):self.last_response=self.e.clear(x,y,ch);return self.last_response
  def exit(self):self.last_response=self.e.exit();return self.last_response
 try:
  with contextlib.redirect_stdout(io.StringIO()):ctrl.run_q3_particle(Client(e))
  err=None
 except Exception:err=traceback.format_exc(limit=2)
 n=len(sc.jammers);return {'variant':label,'seed':seed,'N':n,'ok':e.cleared_count==n,'cleared':e.cleared_count,'avg':e.virtual_time_s/n,'error':err}
def main():
 print('CASES='+json.dumps(cases),flush=True);args=[(l,*v,s) for l,v in V.items() for s in CASES];rows=[]
 with ProcessPoolExecutor(max_workers=7) as ex:
  fs=[ex.submit(work,a) for a in args]
  for f in as_completed(fs):rows.append(f.result())
 out={}
 for l in V:
  rr=[r for r in rows if r['variant']==l];by={n:statistics.mean(r['avg'] for r in rr if r['N']==n) for n in (10,11,12)}
  out[l]={'fullclear':sum(r['ok'] for r in rr),'runs':len(rr),'mean':statistics.mean(by.values()),'byN':by,'miss':[(r['seed'],r['N'],r['cleared']) for r in rr if not r['ok']]}
 rank=sorted(out,key=lambda x:(out[x]['fullclear']<len(CASES),out[x]['mean']))
 print('RESULT_JSON='+json.dumps({'ranking':rank,'summary':out},sort_keys=True))
if __name__=='__main__':main()
