"""Posterior risk using the public consecutive-channel rule: active channels are 1..N."""
from __future__ import annotations
from functools import lru_cache
import numpy as np

@lru_cache(maxsize=256)
def _survival_probability(key: bytes) -> float:
    points=np.frombuffer(key,dtype=np.float64).reshape(-1,2)
    rng=np.random.default_rng(731991)
    count=80000
    r=1770.0*np.sqrt(rng.random(count));a=rng.random(count)*2*np.pi
    pos=np.column_stack([r*np.cos(a),r*np.sin(a)])
    radius=rng.uniform(1000.0,1500.0,count);h=rng.random(count)*2*np.pi
    heading=np.column_stack([np.cos(h),np.sin(h)]);directional=rng.random(count)<0.55
    keep=np.ones(count,bool)
    for point in points:
        delta=point-pos
        visible=(np.sum(delta*delta,axis=1)<=radius*radius)&(~directional|(np.sum(delta*heading,axis=1)>=0.0))
        keep&=~visible
    return float((np.sum(keep)+1)/(count+2))

def _channel_survival(belief: dict) -> float:
    points=np.round(np.asarray(belief.get("no_signal_points",[]),dtype=np.float64),3)
    return _survival_probability(points.tobytes())

def remaining_risk(beliefs: dict, found: set[int]) -> tuple[float,int|None]:
    lower=max(10,max(found,default=0))
    required=[c for c in range(1,lower+1) if beliefs[c].get("status")=="unknown"]
    if required:
        return 1.0,required[0]
    weights=[1.0];likelihood=1.0
    for channel in range(lower+1,17):
        likelihood*=_channel_survival(beliefs[channel])
        weights.append(likelihood)
    total=float(sum(weights))
    risk=0.0 if total<=0.0 else 1.0-weights[0]/total
    return risk,(lower+1 if lower<16 else None)
