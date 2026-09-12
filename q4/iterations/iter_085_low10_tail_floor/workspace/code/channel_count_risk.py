"""基于公开离线生成规则的剩余活动频道后验风险。"""
from __future__ import annotations
from functools import lru_cache
from math import comb
import numpy as np

_SAMPLE_COUNT=50000
_rng=np.random.default_rng(731991)
_r=1770.0*np.sqrt(_rng.random(_SAMPLE_COUNT)); _a=2.0*np.pi*_rng.random(_SAMPLE_COUNT)
_POS=np.column_stack([_r*np.cos(_a),_r*np.sin(_a)])
_RADIUS=_rng.uniform(1000.0,1500.0,_SAMPLE_COUNT)
_h=2.0*np.pi*_rng.random(_SAMPLE_COUNT)
_HEADING=np.column_stack([np.cos(_h),np.sin(_h)])
# 公开规则为定向源数在1..N均匀；N=10..16时边际定向比例约0.53--0.55。
_DIRECTIONAL=_rng.random(_SAMPLE_COUNT)<0.54

@lru_cache(maxsize=4096)
def _active_survival(key: bytes) -> float:
    points=np.frombuffer(key,dtype=np.float64).reshape(-1,2)
    keep=np.ones(_SAMPLE_COUNT,dtype=bool)
    for point in points:
        delta=point-_POS
        visible=(np.sum(delta*delta,axis=1)<=_RADIUS*_RADIUS)&(
            (~_DIRECTIONAL)|(np.sum(delta*_HEADING,axis=1)>=0.0))
        keep &= ~visible
    return float((int(np.sum(keep))+1)/(_SAMPLE_COUNT+2))

def channel_survival(belief: dict) -> float:
    points=np.round(np.asarray(belief.get('no_signal_points',[]),dtype=np.float64),3)
    return _active_survival(points.tobytes())

def remaining_active_risk(beliefs: dict, found_count: int) -> float:
    """返回未知频道中至少还有一个活动源的后验概率。"""
    unknown=[b for b in beliefs.values() if b.get('status')=='unknown']
    if not unknown:
        return 0.0
    survivals=[channel_survival(b) for b in unknown]
    # e[m]为从未知频道选m个活动源时未被当前观测发现的似然和。
    e=np.zeros(len(survivals)+1,dtype=np.float64); e[0]=1.0
    used=0
    for s in survivals:
        used+=1
        for m in range(used,0,-1):
            e[m]+=e[m-1]*s
    lo=max(0,10-found_count); hi=min(16-found_count,len(survivals))
    if hi<lo:
        return 0.0
    weights=[]
    for m in range(lo,hi+1):
        n=found_count+m
        weights.append((m,float(e[m])/comb(20,n)))
    total=sum(w for _,w in weights)
    if total<=0.0:
        return 1.0
    p0=next((w/total for m,w in weights if m==0),0.0)
    return float(1.0-p0)
