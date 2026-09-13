from pathlib import Path
import sys, numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

b.CANDIDATES={
 'baseline':{},
 'wb4':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.06,'service_waypoint_unknown_max_known':12,'waypoint_unknown_budget':4},
 'wb6':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.06,'service_waypoint_unknown_max_known':12,'waypoint_unknown_budget':6},
 'wb8':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.06,'service_waypoint_unknown_max_known':12,'waypoint_unknown_budget':8},
 'wb4h':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.10,'service_waypoint_unknown_max_known':12,'waypoint_unknown_budget':4},
 'wb6h':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.10,'service_waypoint_unknown_max_known':12,'waypoint_unknown_budget':6},
}

_base_patch=b.patch_service_aware_endpoint
def patch(ctrl):
    _base_patch(ctrl)
    C=ctrl.Q3ParticleController
    orig_service=C.service
    orig_scan=C.scan_unknown
    def service(self,ch):
        self._wp_budget_context=True
        try:return orig_service(self,ch)
        finally:self._wp_budget_context=False
    def scan_unknown(self,p):
        budget=int(self.tune.get('waypoint_unknown_budget',0))
        if not getattr(self,'_wp_budget_context',False) or budget<=0:
            return orig_scan(self,p)
        p=np.asarray(p,float)
        if not hasattr(self,'_wp_budget_used'):self._wp_budget_used=[]
        if any(float(np.linalg.norm(p-q))<2.0 for q in self._wp_budget_used):return 0
        chs=self.unknown()
        if not chs:return 0
        rc=getattr(self.c,'receiver_channel',None)
        # Rotate the subset so repeated waypoint opportunities cover different channels.
        rest=[x for x in chs if x!=rc]
        off=(getattr(self,'_scan_seq',0)*max(1,budget))%max(1,len(rest)) if rest else 0
        rest=rest[off:]+rest[:off]
        ordered=(([rc] if rc in chs else [])+rest)[:budget]
        before=self.known()
        for ch in ordered:
            if self.known()>=16:break
            self.measure(p,ch)
        self._wp_budget_used.append(p.copy())
        return self.known()-before
    C.service=service
    C.scan_unknown=scan_unknown
b.patch_service_aware_endpoint=patch
b.main()
