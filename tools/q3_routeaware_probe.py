from pathlib import Path
import sys, numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

b.CANDIDATES={
 'base':{},
 'v550':{'route_scan_value_s':550},
 'ra90':{'route_scan_value_s':550,'ra_pd_ratio':0.90},
 'ra80':{'route_scan_value_s':550,'ra_pd_ratio':0.80},
 'ra70':{'route_scan_value_s':550,'ra_pd_ratio':0.70},
 'ra60':{'route_scan_value_s':550,'ra_pd_ratio':0.60},
 'ra80p90':{'route_scan_value_s':550,'ra_pd_ratio':0.80,'ra_ps_ratio':0.90},
 'ra70p90':{'route_scan_value_s':550,'ra_pd_ratio':0.70,'ra_ps_ratio':0.90},
}

_base_patch=b.patch_service_aware_endpoint
def patch(ctrl):
    _base_patch(ctrl)
    C=ctrl.Q3ParticleController
    orig=C.joint_next
    def joint(self,items,soft_done=False):
        ans=orig(self,items,soft_done)
        if ans[0] != 'probe' or soft_done or not items:
            return ans
        k=self.known()
        if not (8 <= k <= 12):
            return ans
        ratio=float(self.tune.get('ra_pd_ratio',1.01))
        if ratio>1.0:
            return ans
        cur=np.asarray(self.c.position,float)
        order=self.source_order(items,False)
        if not order:
            return ans
        cand=self._explore_candidates(cur,max_pool=180)
        if not cand:
            return ans
        rec=[]
        ps0=self.posterior_same_count()
        for q in cand:
            q=np.asarray(q,float)
            pd=float(self.cover.conditional_detect(q))
            det,pos=self._route_insertion(order,q)
            ps1=self._posterior_same_at_q(k,self._q_after_probe(q)) if k>=10 else 0.0
            rec.append((pd,ps1,float(det),int(pos),q))
        maxpd=max(x[0] for x in rec)
        maxps=max(x[1] for x in rec) if k>=10 else 0.0
        psratio=float(self.tune.get('ra_ps_ratio',0.0))
        safe=[x for x in rec if x[0] >= ratio*maxpd and (k<10 or maxps<=1e-12 or x[1] >= psratio*maxps)]
        if not safe:
            return ans
        # Minimize true insertion detour; tie-break toward stronger detection/posterior.
        best=min(safe,key=lambda x:(x[2],-x[0],-x[1]))
        q=best[4]
        self.committed_probe=q.copy()
        ao=self.exact_order(list(items)+[(-999,q)])
        if not ao:
            return ans
        ch,p=ao[0]
        if ch==-999:
            self.committed_probe=None
            return ('probe',None,np.asarray(p,float))
        return ('source',ch,np.asarray(p,float))
    C.joint_next=joint
b.patch_service_aware_endpoint=patch
b.main()
