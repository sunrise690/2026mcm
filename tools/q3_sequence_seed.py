from pathlib import Path
import sys, os, json, io, contextlib, importlib.util, hashlib, re
import numpy as np
ROOT=Path(__file__).resolve().parents[1];BENCH=ROOT/'q3'/'bench';SIM=BENCH/'jammers_offline_sim.py';CTRL=ROOT/'q3'/'current'/'tunable_controller.py';CFG=ROOT/'q3'/'current'/'alg_sparseboot3.json'
sys.path.insert(0,str(BENCH));from sim_payload import write_sim
if not SIM.exists():write_sim(SIM)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def sb(seed):return hashlib.sha256(f'cumcm-offline-generator-key:{seed}'.encode()).digest()
sim=load('sim',SIM);cfg=json.loads(CFG.read_text())['tune'];cfg['route_scan_value_s']=550;os.environ['Q3_TUNE_JSON']=json.dumps(cfg);ctrl=load('ctrl',CTRL)
sc=sim.generate_practice(3,sb(1024));e=sim.Engine(sc,record_trace=False)
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
buf=io.StringIO()
with contextlib.redirect_stdout(buf):ctrl.run_q3_particle(Client(e))
keep=[]
for line in buf.getvalue().splitlines():
 if any(k in line for k in ('[发现]','[启动]','[探索]','[清除]','[成功]','[普查','[结束判据]','[顺路普查]')):keep.append(line)
print('SEQUENCE_BEGIN')
print('\n'.join(keep))
print('SEQUENCE_END')
print('TRUE_SOURCES='+json.dumps([{'ch':j.channel,'x':j.x,'y':j.y,'r':j.radius} for j in sc.jammers]))
print('SUMMARY='+json.dumps({'N':len(sc.jammers),'time':e.virtual_time_s,'avg':e.virtual_time_s/len(sc.jammers),'cleared':e.cleared_count}))
