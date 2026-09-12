from __future__ import annotations
import math
import json
import os
from pathlib import Path
import numpy as np

DEFAULT_TUNE = {
    "geometry_mode": 0,
    "particle_n": 24000,
    "particle_rebuild_n": 50000,
    "particle_min_keep": 250,
    "bearing_tol_deg": 1.02,
    "coverage_grid_h": 45.0,
    "best_probe_dist_div": 9000.0,
    "scan_info_score_thr": 0.22,
    "bootstrap_info_w": 220.0,
    "bootstrap_gain_w": 0.025,
    "bootstrap_move_w": 0.08,
    "bootstrap_info_limit": 8,
    "probe_info_limit": 5,
    "route_info_limit_low": 2,
    "route_info_limit_high": 4,
    "hard_done_info_limit": -1,
    "route_scan_thr_low": 0.15,
    "route_scan_thr_mid": 0.11,
    "route_scan_thr_high": 0.08,
    "service_uncertainty_trigger": 28.0,
    "service_iters": 3,
    "exact_tsp_limit": 15,
    "stop_thr_10": 0.74,
    "stop_thr_11": 0.78,
    "stop_thr_12": 0.81,
    "stop_thr_13": 0.83,
    "stop_thr_14": 0.85,
    "stop_thr_15": 0.85,
    "finish_gap_13": 0.10,
    "finish_gap_14": 0.05,
    "finish_gap_15": 0.01,
    "finish_choose_cheapest": 0,
    "explore_progress_bonus": 0.00012,
    "probe_allow_base_low": 260.0,
    "probe_allow_gain_low": 1900.0,
    "probe_allow_base_high": 160.0,
    "probe_allow_gain_high": 1200.0,
    "probe_low_known_cut": 12,
    "probe_scan_cost_scale": 2.0,
    "probe_allow_floor": 40.0,
    "commit_probe_enabled": 1,
    "commit_min_known": 10,
    "commit_min_hppd": 0.16,
    "commit_reset_on_discovery": 0,
    "coverage_preclear_min_known": 9,
    "coverage_eff_q_weight": 0.65,
    "joint_candidate_pool": 70,
    "joint_pd_min": 0.04,
    "joint_fragment_s_low": 720.0,
    "joint_fragment_s_mid": 560.0,
    "joint_net_min": 18.0,
    "joint_posterior_gain_s": 45.0,
    "sweep_sector_deg": 70.0,
    "sweep_dist_div": 8500.0,
    "sweep_sector_penalty": 0.28,
    "sweep_endpoint_weight": 1.10,
    "adaptive_joint_max_known": 12,
    "soft_stop_probe_limit": 0,
    "source_detect_bonus_s": 0.0,
    "source_detect_min_known": 10,
    "source_choice_pool": 5,
    "adaptive_route_scan": 0,
    "route_scan_value_s": 900.0,
    "adaptive_route_scan_min_known": 0,
    "adaptive_route_scan_max_known": 16,
    "route_premeasure": 0,
    "route_premeasure_min_radius": 45.0,
    "route_premeasure_min_prob": 0.45,
    "route_premeasure_min_cross": 0.35,
    "service_waypoint": 0,
    "service_waypoint_min_prob": 0.55,
    "service_waypoint_cross_weight": 700.0,
    "service_waypoint_prob_weight": 180.0,
    "service_waypoint_detour_weight": 1.0,
    "adaptive_bootstrap_info": 0,
    "service_shared_scan": 0,
    "service_waypoint_unknown_scan": 0,
    "service_waypoint_unknown_thr": 0.12,
    "service_waypoint_unknown_max_known": 12,
    "service_shared_limit": 4,
    "service_shared_score_thr": 0.38,
    "batch_discovery": 0,
    "batch_discovery_max_known": 12,
    "risk_empty_probe_stop": 0,
    "risk_empty_probe_limit": 1,
    "risk_empty_probe_max_known": 12,
    "bootstrap_radii": [700,900,1100],
    "bootstrap_sparse_radii": [700,900,1100],
    "bootstrap_sparse_max_known": -1,
    "bootstrap_unknown_scan": 1,
    "bootstrap_first_source_w": 0.0,
    "route_end_explore": 0,
    "route_end_explore_weight": 1.0,
    "service_aware_route": 0,
    "service_aware_uncertainty_scale": 1.0,
    "service_aware_max_known": 16,
    "preclear_probe_once": 0,
    "preclear_probe_max_known": 9,
    "preclear_probe_info_limit": 0,
}

def load_tuning(override=None):
    cfg=dict(DEFAULT_TUNE)
    p=Path(__file__).with_name("q3_tuning.json")
    if p.exists():
        try:
            obj=json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj,dict): cfg.update(obj)
        except Exception:
            pass
    env=os.environ.get("Q3_TUNE_JSON")
    if env:
        try:
            obj=json.loads(env)
            if isinstance(obj,dict): cfg.update(obj)
        except Exception:
            pass
    if override: cfg.update(dict(override))
    return cfg

REGION=1800.0
RMIN=1000.0; RMAX=1500.0
MAXN=16
GEOMETRY_NAMES={0:"commit10",1:"coverage_first",2:"joint_info_tsp",3:"sector_sweep",4:"adaptive_hybrid"}

def angle_diff(a,b):
    return np.abs((a-b+180.0)%360.0-180.0)

class ParticleBelief:
    def __init__(self,ch:int,n=None,tune=None):
        self.tune=tune or DEFAULT_TUNE
        if n is None:n=int(self.tune["particle_n"])
        self.ch=ch; self.n=int(n); self.rng=np.random.default_rng(880301+ch*10007)
        self.hist=[]; self.X=None; self.status='unknown'; self.clear_fail=[]
    def add(self,p,res,bearing=None):
        p=np.asarray(p,float); self.hist.append((p,res,bearing))
        if res=='direction': self.status='detected'
        if self.X is None:
            if any(h[1]=='direction' for h in self.hist): self.rebuild(self.n)
        else:
            self._apply(self.hist[-1])
            if len(self.X)<int(self.tune["particle_min_keep"]): self.rebuild(max(self.n,int(self.tune["particle_rebuild_n"])))
    def add_clear_fail(self,p):
        p=np.asarray(p,float); self.clear_fail.append(p)
        if self.X is not None and len(self.X):
            d=np.linalg.norm(self.X[:,:2]-p,axis=1); self.X=self.X[d>19.9]
            if len(self.X)<int(self.tune["particle_min_keep"]):self.rebuild(max(self.n,int(self.tune["particle_rebuild_n"])))
    def rebuild(self,n=None):
        n=self.n if n is None else n
        first=next((h for h in self.hist if h[1]=='direction'),None)
        if first is None:return
        s,_,th=first; chunks=[]; total=0; tries=0
        while total<n and tries<30:
            tries+=1; m=max(20000,n-total)
            t=RMAX*np.sqrt(self.rng.random(m)); loR=np.maximum(RMIN,t)
            acc=self.rng.random(m) <= np.maximum(0.0,(RMAX-loR)/(RMAX-RMIN))
            ang=np.radians(th+self.rng.uniform(-1.0,1.0,m))
            x=s[0]+t*np.cos(ang); y=s[1]+t*np.sin(ang)
            acc &= x*x+y*y <= REGION**2
            ii=np.where(acc)[0]
            if len(ii):
                lr=loR[ii];rr=lr+self.rng.random(len(ii))*(RMAX-lr)
                z=np.c_[x[ii],y[ii],rr];chunks.append(z);total+=len(z)
        if not chunks:
            self.X=np.empty((0,3));return
        self.X=np.vstack(chunks)[:n]
        skipped=False
        for h in self.hist:
            if not skipped and h is first:
                skipped=True;continue
            self._apply(h,rebuild=False)
            if self.X is None or len(self.X)==0:break
        for q in self.clear_fail:
            if self.X is not None and len(self.X):
                d=np.linalg.norm(self.X[:,:2]-q,axis=1);self.X=self.X[d>19.9]
    def _apply(self,h,rebuild=False):
        if self.X is None or len(self.X)==0:return
        p,res,th=h;d=np.linalg.norm(self.X[:,:2]-p,axis=1)
        if res=='no_signal': m=d>self.X[:,2]
        elif res=='near': m=d<=20
        elif res=='direction':
            pred=np.degrees(np.arctan2(self.X[:,1]-p[1],self.X[:,0]-p[0]))%360;m=(d<=self.X[:,2])&(angle_diff(pred,th)<=float(self.tune["bearing_tol_deg"]))
        else:return
        self.X=self.X[m]
    def estimate(self):
        if self.X is None or len(self.X)==0:
            dirs=[h for h in self.hist if h[1]=='direction']
            if not dirs:return None,9999.0
            if len(dirs)>=2:
                A=[];y=[]
                for p,_,th in dirs:
                    a=math.radians(float(th));e=np.array([math.cos(a),math.sin(a)]);n=np.array([-e[1],e[0]])
                    A.append(n);y.append(float(np.dot(n,p)))
                A=np.asarray(A,float);y=np.asarray(y,float)
                try:
                    est=np.linalg.lstsq(A,y,rcond=None)[0]
                    nr=float(np.linalg.norm(est))
                    if nr>REGION:est*=REGION/nr
                    cross=0.0
                    for i in range(len(dirs)):
                        ai=math.radians(float(dirs[i][2]));ei=np.array([math.cos(ai),math.sin(ai)])
                        for j in range(i):
                            aj=math.radians(float(dirs[j][2]));ej=np.array([math.cos(aj),math.sin(aj)])
                            cross=max(cross,abs(float(ei[0]*ej[1]-ei[1]*ej[0])))
                    return np.asarray(est,float), max(35.0,120.0*(0.35/max(0.12,cross)))
                except Exception:
                    pass
            p,_,th=dirs[0];a=math.radians(float(th));return p+850*np.array([math.cos(a),math.sin(a)]),600.0
        xy=self.X[:,:2];c=np.median(xy,axis=0);r=np.percentile(np.linalg.norm(xy-c,axis=1),90);return c,float(r)
    def signal_prob(self,p):
        if self.X is None or len(self.X)==0:return 0.4
        p=np.asarray(p,float);d=np.linalg.norm(self.X[:,:2]-p,axis=1);return float(np.mean(d<=self.X[:,2]))
    def expected_cross(self,p):
        if not self.hist:return 0.0
        dirs=[h for h in self.hist if h[1]=='direction']
        if not dirs:return 0.0
        est,_=self.estimate();p=np.asarray(p,float);v=est-p;nv=np.linalg.norm(v)
        if nv<1:return 1.0
        u=v/nv;best=0
        for s,_,th in dirs:
            a=math.radians(float(th));e=np.array([math.cos(a),math.sin(a)])
            best=max(best,abs(float(e[0]*u[1]-e[1]*u[0])))
        return best

class Coverage:
    def __init__(self,h=None,tune=None):
        self.tune=tune or DEFAULT_TUNE
        if h is None:h=float(self.tune["coverage_grid_h"])
        xs=np.arange(-REGION,REGION+h,h);xx,yy=np.meshgrid(xs,xs,indexing='xy');p=np.c_[xx.ravel(),yy.ravel()]
        self.p=p[np.linalg.norm(p,axis=1)<=REGION];self.c=np.zeros(len(self.p),bool);self.points=[];self.d2=np.full(len(self.p),np.inf)
    def add(self,p):
        p=np.asarray(p,float);self.points.append(p.copy());dd=np.sum((self.p-p)**2,axis=1);self.d2=np.minimum(self.d2,dd);self.c|=(dd<=1000.0**2)
    def gain(self,p):
        p=np.asarray(p,float);h=np.sum((self.p-p)**2,axis=1)<=1000.0**2;return int(np.count_nonzero(h&~self.c))
    def frac(self):return float(np.mean(self.c))
    def expected_detect(self):
        d=np.sqrt(self.d2);q=np.zeros(len(d));q[d<=1000]=1.0;m=(d>1000)&(d<1500);q[m]=(1500-d[m])/500.0;return float(np.mean(q))
    def miss_weight(self):
        d=np.sqrt(self.d2);w=np.ones(len(d));w[d<=1000]=0.0;m=(d>1000)&(d<1500);w[m]=(d[m]-1000.0)/500.0;return w
    def conditional_detect(self,p):
        p=np.asarray(p,float);dprev=np.sqrt(self.d2);w=self.miss_weight();den=float(np.sum(w))
        if den<=1e-9:return 0.0
        dn=np.linalg.norm(self.p-p,axis=1)
        hi=np.minimum(dprev,1500.0);lo=np.maximum(dn,1000.0)
        joint=np.maximum(0.0,hi-lo)/500.0
        return float(np.sum(joint)/den)
    def best_posterior_probe(self,current,max_candidates=420):
        w=self.miss_weight();idx=np.where(w>1e-5)[0]
        if not len(idx):return None,0.0
        if len(idx)>max_candidates:
            order=idx[np.argsort(w[idx])[::-1]]
            step=max(1,len(order)//max_candidates);idx=order[::step][:max_candidates]
        cand=[self.p[i] for i in idx]
        cen=np.average(self.p,axis=0,weights=w);cand.append(cen)
        cur=np.asarray(current,float);best=None
        for p in cand:
            pd=self.conditional_detect(p);dist=float(np.linalg.norm(np.asarray(p)-cur))
            score=pd-dist/float(self.tune["best_probe_dist_div"])
            if best is None or score>best[0]:best=(score,np.asarray(p,float),pd,dist)
        return best[1],best[2]

class Q3ParticleController:
    def __init__(self,client,tune=None):
        self.tune=load_tuning(tune)
        self.c=client;self.B={ch:ParticleBelief(ch,tune=self.tune) for ch in range(1,21)};self.cleared=set();self.cover=Coverage(tune=self.tune);self.used=[]
        self._scan_seq=0;self.committed_probe=None;self.sweep_angle_deg=None;self.soft_stop_probes=0;self.empty_probe_streak=0
    def g(self,key):return self.tune[key]
    def geometry_mode(self):return int(self.tune.get("geometry_mode",0))
    def geometry_name(self):return GEOMETRY_NAMES.get(self.geometry_mode(),f"mode_{self.geometry_mode()}")
    def _update_sweep(self,p):
        p=np.asarray(p,float)
        if np.linalg.norm(p)>50:
            self.sweep_angle_deg=float(math.degrees(math.atan2(float(p[1]),float(p[0])))%360.0)
    def _vt(self):
        body=getattr(self.c,'last_response',None) or {}
        v=body.get('virtual_time_s')
        return f"{float(v):.1f}s" if isinstance(v,(int,float)) else "--"
    def _pos(self,p):
        p=np.asarray(p,float);return f"({p[0]:.0f},{p[1]:.0f})"
    def _progress(self):
        det=sum(1 for b in self.B.values() if b.status=='detected')
        return f"已发现={self.known()}  待清={det}  已清={len(self.cleared)}  t={self._vt()}"
    def known(self):return sum(b.status in ('detected','cleared') for b in self.B.values())
    def unknown(self):return [ch for ch,b in self.B.items() if b.status=='unknown']
    def measure(self,p,ch):
        p=np.asarray(p,float);was_unknown=(self.B[ch].status=='unknown')
        z=self.c.measure(float(p[0]),float(p[1]),int(ch));r=z.get('measure_result')
        self.B[ch].add(p,r,z.get('svd_deg'))
        if r=='direction':
            self.B[ch].status='detected'
            if was_unknown:
                deg=z.get('svd_deg')
                dtext=f"{float(deg):.2f}°" if isinstance(deg,(int,float)) else "--"
                print(f"  [发现] CH{ch:02d} 位置{self._pos(p)} 示向={dtext} | {self._progress()}",flush=True)
        elif r=='near':
            q=self.c.clear(float(p[0]),float(p[1]),int(ch))
            if q.get('clear_result')=='success':
                self.B[ch].status='cleared';self.cleared.add(ch)
                print(f"  [近场直清] CH{ch:02d} 位置{self._pos(p)} 成功 | {self._progress()}",flush=True)
        return r
    def scan_unknown(self,p):
        p=np.asarray(p,float)
        if any(float(np.linalg.norm(p-q))<2.0 for q in self.used): return 0
        if self.geometry_mode()==3:self._update_sweep(p)
        chs=self.unknown();rc=getattr(self.c,'receiver_channel',None)
        if rc in chs:chs.remove(rc);chs.insert(0,rc)
        before=self.known();self._scan_seq+=1
        print(f"[普查{self._scan_seq}] 到达 {self._pos(p)}，扫描未知频道 {len(chs)} 个...",flush=True)
        for ch in chs:
            if self.known()>=16:break
            self.measure(p,ch)
        if self.known()<16:self.cover.add(p);self.used.append(p.copy())
        gain=self.known()-before
        if gain>0 and int(self.g("commit_reset_on_discovery")):self.committed_probe=None
        print(f"[普查{self._scan_seq}] 完成，新发现 {gain} 个 | {self._progress()}",flush=True)
        return gain
    def scan_info(self,p,limit=3,min_score=None):
        p=np.asarray(p,float);cand=[]
        for ch,b in self.B.items():
            if ch in self.cleared or b.status!='detected':continue
            if any(np.linalg.norm(h[0]-p)<1 for h in b.hist):continue
            est,r=b.estimate()
            if est is None or r<25:continue
            prob=b.signal_prob(p);cross=b.expected_cross(p)
            score=prob*(0.8*cross+min(1.5,r/250))
            threshold=float(self.g("scan_info_score_thr")) if min_score is None else float(min_score)
            if score>threshold:cand.append((score,ch))
        cand.sort(reverse=True);chosen=cand[:limit]
        if chosen:
            print(f"[补测] 位置{self._pos(p)}，补测 {len(chosen)} 个频道："+','.join(f"CH{ch:02d}" for _,ch in chosen),flush=True)
        for _,ch in chosen:self.measure(p,ch)
    def bootstrap_point(self):
        best=None;cur=np.asarray(self.c.position,float)
        source_est=[b.estimate()[0] for b in self.B.values() if b.status=='detected' and b.estimate()[0] is not None]
        radii=self.g("bootstrap_sparse_radii") if self.known()<=int(self.g("bootstrap_sparse_max_known")) else self.g("bootstrap_radii")
        for r in radii:
            n=24
            for k in range(n):
                p=r*np.array([math.cos(2*math.pi*k/n),math.sin(2*math.pi*k/n)])
                gain=self.cover.gain(p);info=0
                for b in self.B.values():
                    if b.status=='detected':info+=b.signal_prob(p)*b.expected_cross(p)
                first_move=min((float(np.linalg.norm(p-q)) for q in source_est),default=0.0)
                score=float(self.g("bootstrap_info_w"))*info+float(self.g("bootstrap_gain_w"))*gain-float(self.g("bootstrap_move_w"))*np.linalg.norm(p-cur)-float(self.g("bootstrap_first_source_w"))*first_move
                if best is None or score>best[0]:best=(score,p)
        return best[1]
    def route_first(self,items,route_target=None,endpoint_weight=0.85):
        if not items:return None
        chs=[ch for ch,p in items];pts=np.asarray([p for ch,p in items],float);n=len(chs)
        size=1<<n;D=np.linalg.norm(pts[:,None,:]-pts[None,:,:],axis=2);d0=np.linalg.norm(pts-np.asarray(self.c.position,float),axis=1)
        dp=np.full((size,n),np.inf);par=np.full((size,n),-1,np.int16)
        for i in range(n):dp[1<<i,i]=d0[i]
        for mask in range(1,size):
            for i in range(n):
                if not (mask>>i)&1:continue
                prev=mask^(1<<i)
                if prev==0:continue
                js=[j for j in range(n) if (prev>>j)&1]
                vals=[dp[prev,j]+D[j,i] for j in js]
                k=int(np.argmin(vals));v=vals[k]
                if v<dp[mask,i]:dp[mask,i]=v;par[mask,i]=js[k]
        full=size-1
        if route_target is None:
            last=int(np.argmin(dp[full]))
        else:
            rt=np.asarray(route_target,float);tail=np.linalg.norm(pts-rt,axis=1);last=int(np.argmin(dp[full]+endpoint_weight*tail))
        order=[];mask=full
        while mask:
            order.append(last);q=int(par[mask,last]);mask^=1<<last;last=q
        first=list(reversed(order))[0]
        return chs[first],pts[first]
    def exact_order(self,items,route_target=None,endpoint_weight=0.0):
        if not items:return []
        if len(items)<=int(self.g("exact_tsp_limit")):
            chs=[ch for ch,p in items];pts=np.asarray([p for ch,p in items],float);n=len(chs)
            size=1<<n;D=np.linalg.norm(pts[:,None,:]-pts[None,:,:],axis=2);d0=np.linalg.norm(pts-np.asarray(self.c.position,float),axis=1)
            dp=np.full((size,n),np.inf);par=np.full((size,n),-1,np.int16)
            for i in range(n):dp[1<<i,i]=d0[i]
            for mask in range(1,size):
                for i in range(n):
                    if not (mask>>i)&1:continue
                    prev=mask^(1<<i)
                    if prev==0:continue
                    js=[j for j in range(n) if (prev>>j)&1]
                    vals=[dp[prev,j]+D[j,i] for j in js];k=int(np.argmin(vals));dp[mask,i]=vals[k];par[mask,i]=js[k]
            mask=size-1
            if route_target is None or endpoint_weight<=0:
                last=int(np.argmin(dp[mask]))
            else:
                rt=np.asarray(route_target,float);tail=np.linalg.norm(pts-rt,axis=1)
                last=int(np.argmin(dp[mask]+float(endpoint_weight)*tail))
            o=[]
            while mask:
                o.append(last);q=int(par[mask,last]);mask^=1<<last;last=q
            return [(chs[i],pts[i]) for i in reversed(o)]
        # 16-source real-time fallback: nearest-neighbour + 2-opt, avoids exponential stall.
        chs=[ch for ch,p in items];pts=np.asarray([p for ch,p in items],float);cur=np.asarray(self.c.position,float);n=len(chs)
        starts=np.argsort(np.linalg.norm(pts-cur,axis=1))[:6];best=None
        def plen(o):
            z=float(np.linalg.norm(pts[o[0]]-cur))
            for a,b in zip(o,o[1:]):z+=float(np.linalg.norm(pts[b]-pts[a]))
            return z
        for st in starts:
            unused=set(range(n));unused.remove(int(st));o=[int(st)]
            while unused:
                j=min(unused,key=lambda x:float(np.linalg.norm(pts[x]-pts[o[-1]])));o.append(j);unused.remove(j)
            base=plen(o)
            for _ in range(3):
                changed=False
                for a in range(n-2):
                    for b in range(a+2,n):
                        q=o[:a+1]+list(reversed(o[a+1:b+1]))+o[b+1:];v=plen(q)
                        if v+1e-9<base:o,base,changed=q,v,True
                if not changed:break
            obj=base
            if route_target is not None and endpoint_weight>0:
                obj+=float(endpoint_weight)*float(np.linalg.norm(pts[o[-1]]-np.asarray(route_target,float)))
            if best is None or obj<best[0]:best=(obj,o)
        return [(chs[i],pts[i]) for i in best[1]]

    def service_aware_order(self,items):
        if not items:return []
        if len(items)>int(self.g("exact_tsp_limit")):return self.exact_order(items)
        chs=[ch for ch,_ in items];pts=np.asarray([p for _,p in items],float);n=len(items)
        starts=[np.asarray(self.c.position,float)]+[pts[j] for j in range(n)]
        edge=np.zeros((n+1,n),float)
        scale=float(self.g("service_aware_uncertainty_scale"))
        for a,cur in enumerate(starts):
            for i,(ch,target) in enumerate(items):
                b=self.B[ch];_,rad=b.estimate();target=np.asarray(target,float)
                if rad*scale>float(self.g("service_uncertainty_trigger")):
                    q=self.service_measure_point(b,target,current=cur)
                    edge[a,i]=float(np.linalg.norm(q-cur)+np.linalg.norm(target-q))
                else:edge[a,i]=float(np.linalg.norm(target-cur))
        size=1<<n;dp=np.full((size,n),np.inf);par=np.full((size,n),-1,np.int16)
        for i in range(n):dp[1<<i,i]=edge[0,i]
        for mask in range(1,size):
            for i in range(n):
                if not (mask>>i)&1:continue
                prev=mask^(1<<i)
                if prev==0:continue
                js=[j for j in range(n) if (prev>>j)&1]
                vals=[dp[prev,j]+edge[j+1,i] for j in js];k=int(np.argmin(vals));dp[mask,i]=vals[k];par[mask,i]=js[k]
        mask=size-1;last=int(np.argmin(dp[mask]));order=[]
        while mask:
            order.append(last);q=int(par[mask,last]);mask^=1<<last;last=q
        return [(chs[i],pts[i]) for i in reversed(order)]

    def source_order(self,items,discovery_done=False):
        if int(self.g("service_aware_route")) and self.known()<=int(self.g("service_aware_max_known")):
            return self.service_aware_order(items)
        if int(self.g("route_end_explore")) and not discovery_done and self.known()<16:
            target=self.exploration_point()
            if target is not None:
                return self.exact_order(items,route_target=target,endpoint_weight=float(self.g("route_end_explore_weight")))
        return self.exact_order(items)

    def _joint_next_base(self,items,soft_done=False):
        if soft_done or self.known()>=16:
            self.committed_probe=None
            order=self.source_order(items,soft_done)
            return ('none',None,None) if not order else ('source',order[0][0],order[0][1])
        cur=np.asarray(self.c.position,float)
        if int(self.g("commit_probe_enabled")) and self.committed_probe is not None:
            cp=np.asarray(self.committed_probe,float)
            aug=list(items)+[(-999,cp)]
            ao=self.exact_order(aug)
            if ao:
                ch,p=ao[0]
                if ch==-999:
                    self.committed_probe=None
                    return ('probe',None,np.asarray(p,float))
                return ('source',ch,np.asarray(p,float))
            self.committed_probe=None
        probe,pd=self.cover.best_posterior_probe(cur)
        if probe is None:
            order=self.source_order(items,soft_done)
            return ('none',None,None) if not order else ('source',order[0][0],order[0][1])
        hp=max(0.0,min(1.0,1.0-self.posterior_same_count()))
        order=self.source_order(items,soft_done)
        if not order:return ('none',None,None)
        probe=np.asarray(probe,float);pts=[np.asarray(p,float) for _,p in order]
        best=(float('inf'),0)
        for pos in range(len(pts)+1):
            a=cur if pos==0 else pts[pos-1]
            if pos<len(pts):
                b=pts[pos];delta=float(np.linalg.norm(probe-a)+np.linalg.norm(b-probe)-np.linalg.norm(b-a))
            else:delta=float(np.linalg.norm(probe-a))
            if delta<best[0]:best=(delta,pos)
        if self.known()<int(self.g("probe_low_known_cut")):
            allowance=float(self.g("probe_allow_base_low"))+float(self.g("probe_allow_gain_low"))*hp*pd
        else:
            allowance=float(self.g("probe_allow_base_high"))+float(self.g("probe_allow_gain_high"))*hp*pd
        m=len(self.unknown());scan_s=5.0*m+max(0,m-1)
        allowance=max(float(self.g("probe_allow_floor")),allowance-float(self.g("probe_scan_cost_scale"))*scan_s)
        can_commit=(int(self.g("commit_probe_enabled")) and self.known()>=int(self.g("commit_min_known")) and best[0]<=allowance and hp*pd>=float(self.g("commit_min_hppd")))
        if can_commit:
            self.committed_probe=probe.copy()
            aug=list(items)+[(-999,probe)]
            ao=self.exact_order(aug)
            if ao:
                ch,p=ao[0]
                if ch==-999:
                    self.committed_probe=None
                    return ('probe',None,np.asarray(p,float))
                return ('source',ch,np.asarray(p,float))
        if best[1]==0 and best[0]<=allowance:return ('probe',None,probe)
        bonus_s=float(self.g("source_detect_bonus_s"))
        if bonus_s>0 and self.known()>=int(self.g("source_detect_min_known")):
            pool=order[:max(1,int(self.g("source_choice_pool")))]
            def source_score(item):
                ch,p=item;p=np.asarray(p,float)
                travel_s=float(np.linalg.norm(p-cur))/5.0
                pd=self.cover.conditional_detect(p)
                return travel_s-bonus_s*hp*pd
            chosen=min(pool,key=source_score)
            return ('source',chosen[0],np.asarray(chosen[1],float))
        return ('source',order[0][0],order[0][1])
    def _route_insertion(self,order,q):
        cur=np.asarray(self.c.position,float);pts=[np.asarray(p,float) for _,p in order];q=np.asarray(q,float)
        best=(float('inf'),0)
        for pos in range(len(pts)+1):
            a=cur if pos==0 else pts[pos-1]
            if pos<len(pts):
                b=pts[pos];delta=float(np.linalg.norm(q-a)+np.linalg.norm(b-q)-np.linalg.norm(b-a))
            else:delta=float(np.linalg.norm(q-a))
            if delta<best[0]:best=(delta,pos)
        return best

    def _joint_next_information(self,items,soft_done=False):
        if soft_done or self.known()>=16:
            return self._joint_next_base(items,soft_done=True)
        cur=np.asarray(self.c.position,float)
        # Honor a previously committed information node.
        if int(self.g("commit_probe_enabled")) and self.committed_probe is not None:
            cp=np.asarray(self.committed_probe,float);ao=self.exact_order(list(items)+[(-999,cp)])
            if ao:
                ch,p=ao[0]
                if ch==-999:
                    self.committed_probe=None;return ('probe',None,np.asarray(p,float))
                return ('source',ch,np.asarray(p,float))
            self.committed_probe=None
        order=self.exact_order(items)
        if not order:return ('none',None,None)
        hp=max(0.0,min(1.0,1.0-self.posterior_same_count()))
        ps0=self.posterior_same_count();m=len(self.unknown());scan_s=5.0*m+max(0,m-1)
        frag=float(self.g("joint_fragment_s_low")) if self.known()<11 else float(self.g("joint_fragment_s_mid"))
        best=None
        for q in self._explore_candidates(cur,max_pool=int(self.g("joint_candidate_pool"))):
            q=np.asarray(q,float);pd=self.cover.conditional_detect(q)
            if pd<float(self.g("joint_pd_min")):continue
            detour,pos=self._route_insertion(order,q);extra_s=detour/5.0+scan_s
            q1=self._q_after_probe(q);ps1=self._posterior_same_at_q(self.known(),q1)
            benefit=hp*pd*frag+float(self.g("joint_posterior_gain_s"))*max(0.0,ps1-ps0)
            net=benefit-extra_s
            rec=(net,pd,-extra_s,q,pos,detour)
            if best is None or rec[:3]>best[:3]:best=rec
        if best is not None and best[0]>=float(self.g("joint_net_min")):
            q=best[3]
            if int(self.g("commit_probe_enabled")):self.committed_probe=q.copy()
            ao=self.exact_order(list(items)+[(-999,q)])
            if ao:
                ch,p=ao[0]
                if ch==-999:
                    self.committed_probe=None;return ('probe',None,np.asarray(p,float))
                return ('source',ch,np.asarray(p,float))
        return ('source',order[0][0],order[0][1])

    def _coverage_eff_point(self,current):
        cur=np.asarray(current,float);cand=self._explore_candidates(cur,max_pool=120)
        if not cand:return None
        m=len(self.unknown());scan_s=5.0*m+max(0,m-1);q0=self.cover.expected_detect();best=None
        for p in cand:
            p=np.asarray(p,float);dist=float(np.linalg.norm(p-cur));cost=max(25.0,dist/5.0+scan_s)
            pd=self.cover.conditional_detect(p);q1=self._q_after_probe(p)
            utility=(pd+float(self.g("coverage_eff_q_weight"))*max(0.0,q1-q0))/cost
            rec=(utility,pd,q1,-cost,p)
            if best is None or rec[:4]>best[:4]:best=rec
        return best[4]

    def _sweep_point(self,current):
        cur=np.asarray(current,float);cand=self._explore_candidates(cur,max_pool=120)
        if not cand:return None
        if self.sweep_angle_deg is None:
            self._update_sweep(cur)
            if self.sweep_angle_deg is None:self.sweep_angle_deg=0.0
        step=float(self.g("sweep_sector_deg"));target=(self.sweep_angle_deg+step)%360.0;best=None
        for p in cand:
            p=np.asarray(p,float);ang=float(math.degrees(math.atan2(float(p[1]),float(p[0])))%360.0)
            ad=abs((ang-target+180.0)%360.0-180.0)/180.0
            pd=self.cover.conditional_detect(p);dist=float(np.linalg.norm(p-cur))
            score=pd-dist/float(self.g("sweep_dist_div"))-float(self.g("sweep_sector_penalty"))*ad
            rec=(score,pd,-dist,p)
            if best is None or rec[:3]>best[:3]:best=rec
        return best[3]

    def _joint_next_sweep(self,items,soft_done=False):
        if soft_done or self.known()>=16:
            return self._joint_next_base(items,soft_done=True)
        target=self._sweep_point(np.asarray(self.c.position,float))
        order=self.exact_order(items,route_target=target,endpoint_weight=float(self.g("sweep_endpoint_weight")) if target is not None else 0.0)
        return ('none',None,None) if not order else ('source',order[0][0],order[0][1])

    def joint_next(self,items,soft_done=False):
        mode=self.geometry_mode();k=self.known()
        if mode==2:return self._joint_next_information(items,soft_done)
        if mode==3:return self._joint_next_sweep(items,soft_done)
        if mode==4 and 10<=k<=int(self.g("adaptive_joint_max_known")):
            return self._joint_next_information(items,soft_done)
        return self._joint_next_base(items,soft_done)

    def premeasure_selected(self,ch):
        if not int(self.g("route_premeasure")):return False
        b=self.B[ch];cur=np.asarray(self.c.position,float)
        if any(np.linalg.norm(h[0]-cur)<2.0 for h in b.hist):return False
        est,r=b.estimate()
        if est is None or r<float(self.g("route_premeasure_min_radius")):return False
        prob=b.signal_prob(cur);cross=b.expected_cross(cur)
        if prob<float(self.g("route_premeasure_min_prob")) or cross<float(self.g("route_premeasure_min_cross")):return False
        print(f"[路线预定位] CH{ch:02d} 当前点补测，P≈{prob:.2f} 交会≈{cross:.2f}",flush=True)
        self.measure(cur,ch)
        return True

    def service_measure_point(self,b,target,current=None):
        target=np.asarray(target,float);cur=np.asarray(self.c.position if current is None else current,float)
        if not int(self.g("service_waypoint")):return target
        v=target-cur;dist=float(np.linalg.norm(v))
        if dist<250:return target
        u=v/dist;n=np.array([-u[1],u[0]]);lat=min(360.0,0.28*dist)
        candidates=[]
        for f in (0.35,0.50,0.65,0.80):
            for side in (0.0,-0.55,0.55,-1.0,1.0):
                q=cur+f*v+side*lat*n
                nq=float(np.linalg.norm(q))
                if nq>REGION:q=q*(REGION/nq)
                prob=b.signal_prob(q);cross=b.expected_cross(q)
                if prob<float(self.g("service_waypoint_min_prob")):continue
                detour=float(np.linalg.norm(q-cur)+np.linalg.norm(target-q)-dist)
                score=float(self.g("service_waypoint_cross_weight"))*prob*cross+float(self.g("service_waypoint_prob_weight"))*prob-float(self.g("service_waypoint_detour_weight"))*detour
                candidates.append((score,prob,cross,-detour,q))
        if not candidates:return target
        best=max(candidates,key=lambda x:x[:4])
        return np.asarray(best[4],float) if best[0]>0 else target

    def service(self,ch):
        b=self.B[ch]
        p0,r0=b.estimate()
        if p0 is not None:
            print(f"[清除] CH{ch:02d} 目标≈{self._pos(p0)} 后验半径≈{float(r0):.0f}m",flush=True)
        for it in range(int(self.g("service_iters"))):
            p,r=b.estimate()
            if p is None:
                print(f"  [清除] CH{ch:02d} 无可用位置估计，暂缓",flush=True);return False
            if r>float(self.g("service_uncertainty_trigger")) and it==0:
                mp=self.service_measure_point(b,p)
                print(f"  [定位] CH{ch:02d} 不确定度 {float(r):.0f}m，前往交会站 {self._pos(mp)}",flush=True)
                self.measure(mp,ch)
                if ch in self.cleared:return True
                if (int(self.g("service_waypoint_unknown_scan")) and self.known()<=int(self.g("service_waypoint_unknown_max_known"))
                    and self.cover.conditional_detect(mp)>=float(self.g("service_waypoint_unknown_thr"))):
                    print(f"  [定位兼普查] 交会站兼作未知频道普查",flush=True)
                    self.scan_unknown(mp)
                if int(self.g("service_shared_scan")):
                    self.scan_info(mp,limit=int(self.g("service_shared_limit")),min_score=float(self.g("service_shared_score_thr")))
                continue
            z=self.c.clear(float(p[0]),float(p[1]),int(ch))
            if z.get('clear_result')=='success':
                b.status='cleared';self.cleared.add(ch)
                print(f"  [成功] CH{ch:02d} @ {self._pos(p)} | {self._progress()}",flush=True);return True
            print(f"  [失败] CH{ch:02d} @ {self._pos(p)}，利用失败点继续定位",flush=True)
            b.add_clear_fail(p)
            self.measure(p,ch)
            if ch in self.cleared:return True
        p,r=b.estimate()
        if p is not None:
            z=self.c.clear(float(p[0]),float(p[1]),int(ch))
            if z.get('clear_result')=='success':
                b.status='cleared';self.cleared.add(ch)
                print(f"  [成功] CH{ch:02d} @ {self._pos(p)} | {self._progress()}",flush=True);return True
        print(f"  [暂未清除] CH{ch:02d}，后续滚动重规划",flush=True)
        return False
    def _posterior_same_at_q(self,k,q):
        if k<10:return 0.0
        q=max(1e-8,min(1-1e-10,float(q)));ws=[]
        for n in range(k,17):ws.append(math.comb(n,k)*(q**k)*((1-q)**(n-k)))
        z=sum(ws);return 0.0 if z<=0 else ws[0]/z
    def _explore_candidates(self,current,max_pool=180):
        w=self.cover.miss_weight();idx=np.where(w>1e-6)[0]
        if not len(idx):return []
        pts=self.cover.p;cur=np.asarray(current,float);cand=[]
        # Always retain the original v142 greedy point: this prevents lookahead
        # from throwing away a strong one-step finishing action.
        g,_=self.cover.best_posterior_probe(cur)
        if g is not None:cand.append(np.asarray(g,float))
        # Posterior-hot candidates, spread through the ordered support.
        order=idx[np.argsort(w[idx])[::-1]]
        if len(order)>max_pool:
            step=max(1,len(order)//max_pool);order=order[::step][:max_pool]
        cand.extend(pts[i].copy() for i in order)
        # Nearby high-posterior actions matter because a survey has a fixed scan cost.
        near=idx[np.argsort(np.sum((pts[idx]-cur)**2,axis=1))[:24]]
        cand.extend(pts[i].copy() for i in near)
        den=float(np.sum(w))
        if den>1e-9:
            cen=np.average(pts,axis=0,weights=w)
            if np.linalg.norm(cen)<=REGION:cand.append(np.asarray(cen,float))
        out=[];seen=set()
        for q in cand:
            key=(int(round(float(q[0])/15)),int(round(float(q[1])/15)))
            if key not in seen:seen.add(key);out.append(np.asarray(q,float))
        return out
    def _q_after_probe(self,p):
        d2=np.minimum(self.cover.d2,np.sum((self.cover.p-np.asarray(p,float))**2,axis=1))
        d=np.sqrt(d2);q=np.zeros(len(d));q[d<=1000.0]=1.0;m=(d>1000.0)&(d<1500.0);q[m]=(1500.0-d[m])/500.0
        return float(np.mean(q))
    def _exploration_point_base(self):
        cur=np.asarray(self.c.position,float);k=self.known()
        # Before ten discoveries the count posterior is intentionally inactive;
        # keep the original strong maximum-detection geometry.
        if k<10:
            p,_=self.cover.best_posterior_probe(cur);return p
        cand=self._explore_candidates(cur)
        if not cand:return None
        thr=self.stop_threshold(k);ps0=self.posterior_same_count();m=len(self.unknown())
        scan_s=5.0*m+max(0,m-1)
        rec=[]
        for p in cand:
            dist=float(np.linalg.norm(p-cur));cost=dist/5.0+scan_s
            q1=self._q_after_probe(p);ps1=self._posterior_same_at_q(k,q1)
            pd=self.cover.conditional_detect(p)
            rec.append((p,dist,cost,q1,ps1,pd))
        # If one survey can finish, do not choose a cheap but low-detection point:
        # retain candidates close to the best hidden-source hit probability, then
        # take the cheapest of that statistically safe set.
        finish=[r for r in rec if r[4]>=thr]
        if finish:
            if int(self.g("finish_choose_cheapest")) or k>=13:
                return min(finish,key=lambda r:(r[2],-r[4],-r[5]))[0]
            maxpd=max(r[5] for r in finish)
            gap=float(self.g("finish_gap_15")) if k>=15 else (float(self.g("finish_gap_14")) if k>=14 else float(self.g("finish_gap_13")))
            safe=[r for r in finish if r[5]>=maxpd-gap]
            return min(safe,key=lambda r:(r[2],-r[5],-r[4]))[0]
        # Otherwise maximize posterior progress per virtual second.
        def utility(r):
            gain=max(0.0,r[4]-ps0)
            return gain/max(1.0,r[2]) + float(self.g("explore_progress_bonus"))*gain
        best=max(rec,key=lambda r:(utility(r),r[4],r[5],-r[2]))
        return best[0]
    def exploration_point(self):
        mode=self.geometry_mode();cur=np.asarray(self.c.position,float);k=self.known()
        if mode==1 and k<10:return self._coverage_eff_point(cur)
        if mode==3 and k<13:return self._sweep_point(cur)
        if mode==4 and k<10:return self._coverage_eff_point(cur)
        return self._exploration_point_base()
    def posterior_same_count(self):
        k=self.known()
        if k<10:return 0.0
        q=max(1e-6,min(1-1e-9,self.cover.expected_detect()))
        ws=[]
        for n in range(k,17):
            w=math.comb(n,k)*(q**k)*((1-q)**(n-k));ws.append((n,w))
        z=sum(w for _,w in ws)
        return 0.0 if z<=0 else ws[0][1]/z
    def stop_threshold(self,k=None):
        k=self.known() if k is None else int(k)
        if k<=10:return float(self.g("stop_thr_10"))
        if k==11:return float(self.g("stop_thr_11"))
        if k==12:return float(self.g("stop_thr_12"))
        if k==13:return float(self.g("stop_thr_13"))
        if k==14:return float(self.g("stop_thr_14"))
        return float(self.g("stop_thr_15"))
    def coverage_done(self):return self.cover.expected_detect()>=0.997
    def run(self):
        entered=self.c.enter()
        print("="*62,flush=True)
        print(f"Q3 多算法共同进化控制器 | geometry={self.geometry_mode()}:{self.geometry_name()}",flush=True)
        remain=entered.get('remaining_real_duration_s') if isinstance(entered,dict) else None
        if isinstance(remain,(int,float)):print(f"[连接] 已进入问题3测试，真实时间剩余 {float(remain):.0f}s",flush=True)
        else:print("[连接] /enter 成功，开始执行 Q3",flush=True)
        print("="*62,flush=True)
        try:
            self.scan_unknown(np.zeros(2))
            p=self.bootstrap_point();print(f"[启动] 第二测站选择 {self._pos(p)}",flush=True)
            if int(self.g("bootstrap_unknown_scan")):self.scan_unknown(p)
            else:print("[启动] 第二测站仅执行已发现源定位，未知频道留给清除路径",flush=True)
            boot_limit=self.known() if int(self.g("adaptive_bootstrap_info")) else int(self.g("bootstrap_info_limit"))
            self.scan_info(p,limit=boot_limit)
            if (int(self.g("preclear_probe_once")) and self.known()<10
                and self.known()<=int(self.g("preclear_probe_max_known"))):
                ep=self.exploration_point()
                if ep is not None:
                    print(f"[预清除补探] 已发现{self.known()}，仅补探一次 {self._pos(ep)}",flush=True)
                    self.scan_unknown(ep)
                    lim=int(self.g("preclear_probe_info_limit"))
                    if lim>0:self.scan_info(ep,limit=lim)
            if self.geometry_mode()==3:self._update_sweep(p)
            for step in range(120):
                k=self.known();ps=self.posterior_same_count();thr=self.stop_threshold(k)
                soft_done=(k>=10 and len(self.cleared)>=9 and ps>=thr);hard_done=(k>=16);discovery_done=hard_done or soft_done
                detected=[(ch,b.estimate()[0]) for ch,b in self.B.items() if ch not in self.cleared and b.status=='detected' and b.estimate()[0] is not None]
                if detected and int(self.g("batch_discovery")) and not discovery_done and k<=int(self.g("batch_discovery_max_known")):
                    ep=self.exploration_point()
                    if ep is not None:
                        print(f"[批量发现] 已发现{k}，先完成发现判据，再统一规划清除路线 {self._pos(ep)}",flush=True)
                        self.scan_unknown(ep);self.scan_info(ep,limit=int(self.g("probe_info_limit")));continue
                # Structural gene: coverage-first modes may delay early clears until a
                # minimum discovery count, exploiting the hard Q3 prior N>=10.
                if detected and self.geometry_mode() in (1,4) and k<int(self.g("coverage_preclear_min_known")):
                    ep=self._coverage_eff_point(np.asarray(self.c.position,float))
                    if ep is not None:
                        print(f"[结构策略] coverage-first: 已发现{k}，先覆盖 {self._pos(ep)}",flush=True)
                        self.scan_unknown(ep);self.scan_info(ep,limit=int(self.g("probe_info_limit")));continue
                if detected:
                    kind,ch,p=self.joint_next(detected,soft_done=discovery_done)
                    if kind=='probe':
                        print(f"[探索] 插入后验探测点 {self._pos(p)}，继续寻找未发现源",flush=True)
                        self.scan_unknown(p);self.scan_info(p,limit=int(self.g("probe_info_limit")));continue
                    self.premeasure_selected(ch)
                    self.service(ch);q=np.asarray(self.c.position,float)
                    if self.geometry_mode()==3:self._update_sweep(q)
                    if not hard_done and not soft_done:
                        pd=self.cover.conditional_detect(q)
                        use_adaptive=(int(self.g("adaptive_route_scan")) and int(self.g("adaptive_route_scan_min_known"))<=self.known()<=int(self.g("adaptive_route_scan_max_known")))
                        if use_adaptive:
                            m=len(self.unknown());scan_s=5.0*m+max(0,m-1)
                            hp=max(0.05,1.0-self.posterior_same_count())
                            thscan=scan_s/max(1.0,float(self.g("route_scan_value_s"))*hp)
                        else:
                            thscan=float(self.g("route_scan_thr_high")) if self.known()>=14 else (float(self.g("route_scan_thr_mid")) if self.known()>=12 else float(self.g("route_scan_thr_low")))
                        if pd>=thscan:
                            print(f"[顺路普查] 当前清除点仍有发现隐藏源价值 P≈{pd:.2f}",flush=True)
                            self.scan_unknown(q)
                    info_limit=(int(self.g("route_info_limit_low")) if self.known()<13 else int(self.g("route_info_limit_high")))
                    if hard_done and int(self.g("hard_done_info_limit"))>=0:
                        info_limit=int(self.g("hard_done_info_limit"))
                    if info_limit>0:self.scan_info(q,limit=info_limit)
                    continue
                if int(self.g("risk_empty_probe_stop")) and k>=10 and k<=int(self.g("risk_empty_probe_max_known")) and len(self.cleared)>=k and self.empty_probe_streak>=int(self.g("risk_empty_probe_limit")):
                    print(f"[风险收益判据] 连续{self.empty_probe_streak}次独立热点扫描为空，提前结束",flush=True);break
                if discovery_done:
                    if soft_done and self.soft_stop_probes < int(self.g("soft_stop_probe_limit")):
                        ep=self.exploration_point()
                        self.soft_stop_probes += 1
                        if ep is not None:
                            print(f"[结束前复查] 第{self.soft_stop_probes}次独立后验测量 {self._pos(ep)}",flush=True)
                            self.scan_unknown(ep);self.scan_info(ep,limit=int(self.g("probe_info_limit")))
                            continue
                    print(f"[结束判据] 当前无待清源，发现阶段判定完成 | {self._progress()}",flush=True);break
                ep=self.exploration_point()
                if ep is None:
                    print("[结束判据] 无可用后验探测点，结束搜索",flush=True);break
                print(f"[探索] 无待清源，前往后验热点 {self._pos(ep)}",flush=True)
                gain=self.scan_unknown(ep)
                if gain==0 and len(self.cleared)>=self.known():self.empty_probe_streak+=1
                else:self.empty_probe_streak=0
                self.scan_info(ep,limit=int(self.g("probe_info_limit")))
            print(f"[主程序完成] {self._progress()}",flush=True)
            return len(self.cleared)
        finally:
            body=self.c.exit()
            reason=body.get('exit_reason') if isinstance(body,dict) else None
            print(f"[退出] 已发送 /exit"+(f"，原因={reason}" if reason is not None else ""),flush=True)

def run_q3_particle(client):return Q3ParticleController(client).run()

