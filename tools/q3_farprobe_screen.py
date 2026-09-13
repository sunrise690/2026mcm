from pathlib import Path
import sys, os, json, statistics, contextlib, io, importlib.util, hashlib, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'q3'/'bench'; SIM=BENCH/'jammers_offline_sim.py'; CTRL=ROOT/'q3'/'current'/'tunable_controller.py'; CFG=ROOT/'q3'/'current'/'alg_sparseboot3.json'
sys.path.insert(0,str(BENCH))
from sim_payload import write_sim
if not SIM.exists():write_sim(SIM)
CASES=[1003,1024,1007,1015,1013,1022]
C={
 'base':(1e9,1.1),
 'd1600_p35':(1600,.35),'d1400_p35':(1400,.35),'d1200_p35':(1200,.35),'d1000_p35':(1000,.35),
 'd1600_p45':(1600,.45),'d1400_p45':(1400,.45),'d1200_p45':(1200,.45),'d1000_p45':(1000,.45),
 'd1600_p55':(1600,.55),'d1400_p55':(1400,.55),'d1200_p55':(1200,.55),
}
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def sb(seed):return hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()
def work(arg):
 label,cap,pfloor,seed=arg;sim=load(f's_{label}_{seed}',SIM);base=json.loads(CFG.read_text())['tune'];base['route_scan_value_s']=550;os.environ['Q3_TUNE_JSON']=json.dumps(base)
 ctrl=load(f'c_{label}_{seed}',CTRL);C0=ctrl.Q3ParticleController;orig=C0.exploration_point
 def ep(self):
  q=orig(self)
  if q is None:return None
  k=self.known()
  if 10<=k<=12 and len(self.cleared)>=k:
   d=float(np.linalg.norm(np.asarray(q,float)-np.asarray(self.c.position,float)))
   ps=float(self.posterior_same_count())
   if d>=cap and ps>=pfloor:return None
  return q
 C0.exploration_point=ep
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
 c=Client(e);err=None
 try:
  with contextlib.redirect_stdout(io.StringIO()):ctrl.run_q3_particle(c)
 except Exception:err=traceback.format_exc(limit=2)
 n=len(sc.jammers)
 return {'variant':label,'seed':seed,'N':n,'ok':e.cleared_count==n,'cleared':e.cleared_count,'avg':e.virtual_time_s/n,'time':e.virtual_time_s,'error':err}
def main():
 args=[(l,*v,s) for l,v in C.items() for s in CASES];rows=[]
 with ProcessPoolExecutor(max_workers=7) as ex:
  fs=[ex.submit(work,a) for a in args]
  for f in as_completed(fs):
   r=f.result();rows.append(r);print('ROW',json.dumps(r),flush=True)
 out={}
 for l in C:
  rr=[r for r in rows if r['variant']==l];by={n:statistics.mean(r['avg'] for r in rr if r['N']==n) for n in (10,11,12)}
  out[l]={'fullclear':sum(r['ok'] for r in rr),'mean':statistics.mean(by.values()),'byN':by,'max':max(r['avg'] for r in rr),'miss':[(r['seed'],r['N'],r['cleared']) for r in rr if not r['ok']]}
 rank=sorted(out,key=lambda x:(out[x]['fullclear']<6,out[x]['mean']))
 print('RESULT_JSON='+json.dumps({'ranking':rank,'summary':out},sort_keys=True))
if __name__=='__main__':main()
