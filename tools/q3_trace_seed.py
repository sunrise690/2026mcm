from pathlib import Path
import sys, os, json, contextlib, io, importlib.util, hashlib
from collections import defaultdict
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'q3'/'bench'; SIM=BENCH/'jammers_offline_sim.py'; CTRL=ROOT/'q3'/'current'/'tunable_controller.py'; CFG=ROOT/'q3'/'current'/'alg_sparseboot3.json'
sys.path.insert(0,str(BENCH))
from sim_payload import write_sim
if not SIM.exists(): write_sim(SIM)

def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def seedbytes(seed):return hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()

def one(label,override):
 sim=load('sim_'+label,SIM); base=json.loads(CFG.read_text())['tune'];base.update(override);os.environ['Q3_TUNE_JSON']=json.dumps(base)
 ctrl=load('ctrl_'+label,CTRL)
 C=ctrl.Q3ParticleController
 orig_scan=C.scan_unknown;orig_info=C.scan_info;orig_service=C.service
 def scan(self,p):
  old=getattr(self.c,'ctx','other');self.c.ctx='scan_unknown'
  try:return orig_scan(self,p)
  finally:self.c.ctx=old
 def info(self,p,*a,**kw):
  old=getattr(self.c,'ctx','other');self.c.ctx='scan_info'
  try:return orig_info(self,p,*a,**kw)
  finally:self.c.ctx=old
 def service(self,ch):
  old=getattr(self.c,'ctx','other');self.c.ctx='service'
  try:return orig_service(self,ch)
  finally:self.c.ctx=old
 C.scan_unknown=scan;C.scan_info=info;C.service=service
 sc=sim.generate_practice(3,seedbytes(1024));e=sim.Engine(sc,record_trace=False)
 class Client:
  def __init__(self,e):self.e=e;self.last_response={};self.ctx='other';self.ev=[]
  @property
  def position(self):return np.array([self.e.x,self.e.y],float)
  @property
  def receiver_channel(self):return self.e.receiver_channel
  def enter(self):self.last_response=self.e.enter();return self.last_response
  def _call(self,kind,x,y,ch):
   a=np.array([self.e.x,self.e.y],float);t0=self.e.virtual_time_s
   z=getattr(self.e,kind)(x,y,ch);b=np.array([self.e.x,self.e.y],float);t1=self.e.virtual_time_s
   self.ev.append({'ctx':self.ctx,'kind':kind,'ch':ch,'from':a.tolist(),'to':b.tolist(),'dist':float(np.linalg.norm(b-a)),'dt':t1-t0,'result':z.get(kind+'_result')})
   self.last_response=z;return z
  def measure(self,x,y,ch):return self._call('measure',x,y,ch)
  def clear(self,x,y,ch):return self._call('clear',x,y,ch)
  def exit(self):self.last_response=self.e.exit();return self.last_response
 c=Client(e)
 with contextlib.redirect_stdout(io.StringIO()):ctrl.run_q3_particle(c)
 agg=defaultdict(lambda:{'dist':0.0,'dt':0.0,'calls':0})
 for x in c.ev:
  q=agg[x['ctx']];q['dist']+=x['dist'];q['dt']+=x['dt'];q['calls']+=1
 top=sorted(c.ev,key=lambda x:x['dist'],reverse=True)[:20]
 print('TRACE_JSON='+json.dumps({'label':label,'N':len(sc.jammers),'cleared':e.cleared_count,'time':e.virtual_time_s,'avg':e.virtual_time_s/len(sc.jammers),'agg':agg,'top_moves':top},default=dict))

one('baseline',{})
one('v550',{'route_scan_value_s':550})
# trigger
