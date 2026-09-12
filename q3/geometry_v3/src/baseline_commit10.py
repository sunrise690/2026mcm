from __future__ import annotations
import math
import numpy as np

REGION=1800.0
RMIN=1000.0; RMAX=1500.0
MAXN=16

def angle_diff(a,b):
    return np.abs((a-b+180.0)%360.0-180.0)

class ParticleBelief:
    def __init__(self,ch:int,n:int=24000):
        self.ch=ch; self.n=n; self.rng=np.random.default_rng(880301+ch*10007)
        self.hist=[]; self.X=None; self.status='unknown'; self.clear_fail=[]
    def add(self,p,res,bearing=None):
        p=np.asarray(p,float); self.hist.append((p,res,bearing))
        if res=='direction': self.status='detected'
        if self.X is None:
            if any(h[1]=='direction' for h in self.hist): self.rebuild(self.n)
        else:
            self._apply(self.hist[-1])
            if len(self.X)<250: self.rebuild(max(self.n,50000))
    def add_clear_fail(self,p):
        p=np.asarray(p,float); self.clear_fail.append(p)
        if self.X is not None and len(self.X):
            d=np.linalg.norm(self.X[:,:2]-p,axis=1); self.X=self.X[d>19.9]
            if len(self.X)<250:self.rebuild(max(self.n,50000))
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
            pred=np.degrees(np.arctan2(self.X[:,1]-p[1],self.X[:,0]-p[0]))%360;m=(d<=self.X[:,2])&(angle_diff(pred,th)<=1.02)
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
    def __init__(self,h=45.0):
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
            score=pd-dist/9000.0
            if best is None or score>best[0]:best=(score,np.asarray(p,float),pd,dist)
        return best[1],best[2]

class Q3ParticleController:
    def __init__(self,client):
        self.c=client;self.B={ch:ParticleBelief(ch) for ch in range(1,21)};self.cleared=set();self.cover=Coverage();self.used=[]
        self._scan_seq=0; self.committed_probe=None
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
        chs=self.unknown();rc=getattr(self.c,'receiver_channel',None)
        if rc in chs:chs.remove(rc);chs.insert(0,rc)
        before=self.known();self._scan_seq+=1
        print(f"[普查{self._scan_seq}] 到达 {self._pos(p)}，扫描未知频道 {len(chs)} 个...",flush=True)
        for ch in chs:
            if self.known()>=16:break
            self.measure(p,ch)
        if self.known()<16:self.cover.add(p);self.used.append(p.copy())
        gain=self.known()-before
        print(f"[普查{self._scan_seq}] 完成，新发现 {gain} 个 | {self._progress()}",flush=True)
        return gain
    def scan_info(self,p,limit=3):
        p=np.asarray(p,float);cand=[]
        for ch,b in self.B.items():
            if ch in self.cleared or b.status!='detected':continue
            if any(np.linalg.norm(h[0]-p)<1 for h in b.hist):continue
            est,r=b.estimate()
            if est is None or r<25:continue
            prob=b.signal_prob(p);cross=b.expected_cross(p)
            score=prob*(0.8*cross+min(1.5,r/250))
            if score>0.22:cand.append((score,ch))
        cand.sort(reverse=True);chosen=cand[:limit]
        if chosen:
            print(f"[补测] 位置{self._pos(p)}，补测 {len(chosen)} 个频道："+','.join(f"CH{ch:02d}" for _,ch in chosen),flush=True)
        for _,ch in chosen:self.measure(p,ch)
    def bootstrap_point(self):
        best=None;cur=np.asarray(self.c.position,float)
        for r,n in [(700,24),(900,24),(1100,24)]:
            for k in range(n):
                p=r*np.array([math.cos(2*math.pi*k/n),math.sin(2*math.pi*k/n)])
                gain=self.cover.gain(p);info=0
                for b in self.B.values():
                    if b.status=='detected':info+=b.signal_prob(p)*b.expected_cross(p)
                score=220*info+0.025*gain-0.08*np.linalg.norm(p-cur)
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
        if len(items)<=15:
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

    def joint_next(self,items,soft_done=False):
        if soft_done or self.known()>=16:
            self.committed_probe=None
            order=self.exact_order(items)
            return ('none',None,None) if not order else ('source',order[0][0],order[0][1])
        cur=np.asarray(self.c.position,float)

        # Keep a cheap future survey point committed across intermediate clears.
        # This fixes the old receding-horizon bug where a 200-300 m end-of-tour
        # survey could mutate into a 2 km cross-disk trip by the time the tour ended.
        if self.committed_probe is not None:
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
            order=self.exact_order(items)
            return ('none',None,None) if not order else ('source',order[0][0],order[0][1])
        hp=max(0.0,min(1.0,1.0-self.posterior_same_count()))
        order=self.exact_order(items)
        if not order:return ('none',None,None)
        probe=np.asarray(probe,float); pts=[np.asarray(p,float) for _,p in order]
        best=(float('inf'),0)
        for pos in range(len(pts)+1):
            a=cur if pos==0 else pts[pos-1]
            if pos<len(pts):
                b=pts[pos]; delta=float(np.linalg.norm(probe-a)+np.linalg.norm(b-probe)-np.linalg.norm(b-a))
            else:
                delta=float(np.linalg.norm(probe-a))
            if delta<best[0]: best=(delta,pos)
        allowance=(260.0+1900.0*hp*pd) if self.known()<12 else (160.0+1200.0*hp*pd)
        m=len(self.unknown()); scan_s=5.0*m+max(0,m-1)
        allowance=max(40.0,allowance-2.0*scan_s)
        # Commit whenever the whole-tour insertion is cheap enough, not only when
        # the optimal insertion happens to be the very next action.
        if self.known()>=10 and best[0] <= allowance and hp*pd>=0.16:
            self.committed_probe=probe.copy()
            aug=list(items)+[(-999,probe)]
            ao=self.exact_order(aug)
            if ao:
                ch,p=ao[0]
                if ch==-999:
                    self.committed_probe=None
                    return ('probe',None,np.asarray(p,float))
                return ('source',ch,np.asarray(p,float))
        return ('source',order[0][0],order[0][1])
    def service(self,ch):
        b=self.B[ch]
        p0,r0=b.estimate()
        if p0 is not None:
            print(f"[清除] CH{ch:02d} 目标≈{self._pos(p0)} 后验半径≈{float(r0):.0f}m",flush=True)
        for it in range(3):
            p,r=b.estimate()
            if p is None:
                print(f"  [清除] CH{ch:02d} 无可用位置估计，暂缓",flush=True);return False
            if r>28 and it==0:
                print(f"  [定位] CH{ch:02d} 不确定度 {float(r):.0f}m，先到估计点补测",flush=True)
                self.measure(p,ch)
                if ch in self.cleared:return True
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
    def exploration_point(self):
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
            maxpd=max(r[5] for r in finish)
            # Near the upper source-count bound, missing one source is much more
            # expensive than a modest detour. Tighten the admissible loss in
            # hidden-source detection probability as k approaches 16.
            gap=0.01 if k>=15 else (0.05 if k>=14 else 0.10)
            safe=[r for r in finish if r[5]>=maxpd-gap]
            return min(safe,key=lambda r:(r[2],-r[5],-r[4]))[0]
        # Otherwise maximize posterior progress per virtual second.
        def utility(r):
            gain=max(0.0,r[4]-ps0)
            return gain/max(1.0,r[2]) + 0.00012*gain
        best=max(rec,key=lambda r:(utility(r),r[4],r[5],-r[2]))
        return best[0]
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
        if k<=10:return 0.74
        if k==11:return 0.78
        if k==12:return 0.81
        if k==13:return 0.83
        return 0.85
    def coverage_done(self):return self.cover.expected_detect()>=0.997
    def run(self):
        entered=self.c.enter()
        print("="*62,flush=True)
        print("Q3 自动定位清除程序 v154（11源后终点感知版）",flush=True)
        remain=entered.get('remaining_real_duration_s') if isinstance(entered,dict) else None
        if isinstance(remain,(int,float)):print(f"[连接] 已进入问题3测试，真实时间剩余 {float(remain):.0f}s",flush=True)
        else:print("[连接] /enter 成功，开始执行 Q3",flush=True)
        print("="*62,flush=True)
        try:
            self.scan_unknown(np.zeros(2))
            p=self.bootstrap_point();print(f"[启动] 第二测站选择 {self._pos(p)}",flush=True);self.scan_unknown(p);self.scan_info(p,limit=8)
            for step in range(120):
                k=self.known();ps=self.posterior_same_count();thr=self.stop_threshold(k)
                soft_done=(k>=10 and len(self.cleared)>=9 and ps>=thr);hard_done=(k>=16);discovery_done=hard_done or soft_done
                detected=[(ch,b.estimate()[0]) for ch,b in self.B.items() if ch not in self.cleared and b.status=='detected' and b.estimate()[0] is not None]
                if detected:
                    kind,ch,p=self.joint_next(detected,soft_done=discovery_done)
                    if kind=='probe':
                        print(f"[探索] 插入后验探测点 {self._pos(p)}，继续寻找未发现源",flush=True)
                        self.scan_unknown(p);self.scan_info(p,limit=5);continue
                    self.service(ch);q=np.asarray(self.c.position,float)
                    if not hard_done and not soft_done:
                        pd=self.cover.conditional_detect(q);thscan=0.08 if self.known()>=14 else (0.11 if self.known()>=12 else 0.15)
                        if pd>=thscan:
                            print(f"[顺路普查] 当前清除点仍有发现隐藏源价值 P≈{pd:.2f}",flush=True)
                            self.scan_unknown(q)
                    self.scan_info(q,limit=2 if self.known()<13 else 4)
                    continue
                if discovery_done:
                    print(f"[结束判据] 当前无待清源，发现阶段判定完成 | {self._progress()}",flush=True);break
                ep=self.exploration_point()
                if ep is None:
                    print("[结束判据] 无可用后验探测点，结束搜索",flush=True);break
                print(f"[探索] 无待清源，前往后验热点 {self._pos(ep)}",flush=True)
                self.scan_unknown(ep);self.scan_info(ep,limit=5)
            print(f"[主程序完成] {self._progress()}",flush=True)
            return len(self.cleared)
        finally:
            body=self.c.exit()
            reason=body.get('exit_reason') if isinstance(body,dict) else None
            print(f"[退出] 已发送 /exit"+(f"，原因={reason}" if reason is not None else ""),flush=True)

def run_q3_particle(client):return Q3ParticleController(client).run()
