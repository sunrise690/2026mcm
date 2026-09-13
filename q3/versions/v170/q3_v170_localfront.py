from q3_v163_local import Q3ParticleController as Base
import numpy as np, math

class Q3ParticleController(Base):
    def __init__(self,client):
        super().__init__(client)
        self._early_used=False; self._boundary_used=False
        self._mid_micro_used=False; self._high_micro_used=False

    def stop_threshold(self,k=None):
        k=self.known() if k is None else int(k)
        if k<=10:return 0.58
        if k==11:return 0.66
        if k==12:return 0.81
        if k==13:return 0.80
        return 0.85

    def _local_candidates(self,cur,distances=(200.,250.,300.),nang=24):
        out=[]
        for d in distances:
            for j in range(nang):
                a=2*math.pi*j/nang
                q=cur+d*np.array([math.cos(a),math.sin(a)])
                if np.linalg.norm(q)<=1800.0:
                    out.append((q,d,self.cover.gain(q),self.cover.conditional_detect(q)))
        return out

    def scan_unknown(self,p):
        gain=super().scan_unknown(p)
        k=self.known(); cur=np.asarray(self.c.position,float)
        if gain>0 and 10<=k<=11 and not self._mid_micro_used:
            cand=self._local_candidates(cur,(200.,250.,300.),24)
            if cand:
                q,d,hg,pd=max(cand,key=lambda z:(z[2],z[3],-z[1]))
                if hg>=190 and pd>=0.14:
                    self._mid_micro_used=True
                    super().scan_unknown(q)
        if 14<=k<=15 and not self._high_micro_used:
            cand=self._local_candidates(cur,(150.,200.,250.,300.),24)
            if cand:
                q,d,hg,pd=max(cand,key=lambda z:(z[3],z[2],-z[1]))
                if pd>=0.20 and hg>=30:
                    self._high_micro_used=True
                    super().scan_unknown(q)
        return gain

    def service(self,ch):
        ok=super().service(ch)
        q=np.asarray(self.c.position,float)
        if self.known()<10 and not any(float(np.linalg.norm(q-u))<2.0 for u in self.used):
            pd=self.cover.conditional_detect(q); gain=self.cover.gain(q); rad=float(np.linalg.norm(q))
            take=False
            if self.known()<=6 and not self._early_used and 0.04<=pd<=0.09 and gain>=120:
                self._early_used=True; take=True
            if (not take and not self._boundary_used and rad>=1500.0 and pd>=0.04 and gain>=100):
                self._boundary_used=True; take=True
            if take:self.scan_unknown(q)
        return ok

def run_q3_particle(client): return Q3ParticleController(client).run()
