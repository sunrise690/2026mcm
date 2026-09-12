import numpy as np
import math
from functools import lru_cache

@lru_cache(maxsize=1)
def particles():
    rng=np.random.default_rng(731991)
    count=200000
    r=1800*np.sqrt(rng.random(count));a=rng.random(count)*2*np.pi
    pos=np.column_stack([r*np.cos(a),r*np.sin(a)])
    radius=rng.uniform(1000,1500,count);h=rng.random(count)*2*np.pi
    heading=np.column_stack([np.cos(h),np.sin(h)]);directional=rng.random(count)<0.55
    return pos,radius,heading,directional

def choose_probe(belief,current,used,found_count,unknown_count):
    pos,radius,heading,directional=particles();keep=np.ones(len(pos),bool)
    for p in belief.get('no_signal_points',[]):
        delta=np.asarray(p)-pos
        keep&=~((np.sum(delta*delta,axis=1)<=radius*radius)&(~directional|(np.sum(delta*heading,axis=1)>=0)))
    q=(np.sum(keep)+1)/(len(keep)+2)
    weights=np.array([math.comb(n,found_count)*q**(n-found_count)*(1-q)**found_count for n in range(max(10,found_count),17)])
    if found_count<10:risk=1.0
    else:risk=1.0-float(weights[0]/max(float(weights.sum()),1e-300))
    pos=pos[keep];radius=radius[keep];heading=heading[keep];directional=directional[keep]
    if not len(pos):return None,0.0,risk
    cur=np.asarray(current);best=None
    candidates=[]
    for ring in (0,650,1000,1400,1750,1950,2150):
        a=np.deg2rad(np.arange(0,360,15)) if ring else np.array([0])
        candidates.extend(ring*np.column_stack([np.cos(a),np.sin(a)]))
    for ring in (350,650,900):
        a=np.deg2rad(np.arange(0,360,30));candidates.extend(cur+ring*np.column_stack([np.cos(a),np.sin(a)]))
    for point in candidates:
        if np.linalg.norm(point)>2200:continue
        if used and min(np.linalg.norm(point-np.asarray(p)) for p in used)<200:continue
        d=point-pos
        vis=(np.sum(d*d,axis=1)<=radius*radius)&(~directional|(np.sum(d*heading,axis=1)>=0))
        probability=float(np.mean(vis));travel=float(np.linalg.norm(point-cur))/5
        score=probability/(travel+6*unknown_count+100)
        item=(score,probability,-travel,point)
        if best is None or item[:3]>best[:3]:best=item
    if best is None:return None,0.0,risk
    return best[-1],best[1],risk
