import numpy as np
from q4_targeted_rescue_v3 import _particles
from sim_engine import _nearest_neighbor_order,_two_opt_order


def plan_probes_with_stats(belief,current,hypothetical,budget):
    pos,radius,heading,directional=_particles(belief.get('no_signal_points',[]))
    if not len(pos):return [],[]
    def visibility(point):
        d=np.asarray(point)-pos
        return (np.sum(d*d,axis=1)<=radius*radius)&(~directional|(np.sum(d*heading,axis=1)>=0))
    weight=np.ones(len(pos))
    for point in hypothetical:weight[visibility(point)]*=0.15
    candidates=[]
    for rr in (700,1150,1550,1950,2100):
        a=np.deg2rad(np.arange(0,360,15));candidates.extend(rr*np.column_stack([np.cos(a),np.sin(a)]))
    route=list(hypothetical)
    selected=[]
    stats=[]
    for _ in range(budget):
        if not route:ordered=[]
        else:
            order=_nearest_neighbor_order(current,route);order=_two_opt_order(current,route,order,max_passes=10)
            ordered=[route[i] for i in order]
        best=None
        for p in candidates:
            if selected and min(np.linalg.norm(p-q) for q in selected)<250:continue
            chain=[np.asarray(current)]+ordered
            insertion=float(np.linalg.norm(p-chain[-1]))
            for a,b in zip(chain[:-1],chain[1:]):
                insertion=min(insertion,float(np.linalg.norm(p-a)+np.linalg.norm(p-b)-np.linalg.norm(a-b)))
            vis=visibility(p);coverage=float(weight[vis].sum())/max(float(weight.sum()),1e-9)
            score=coverage/(100+insertion/5)
            item=(score,coverage,-insertion,p,vis)
            if best is None or item[:3]>best[:3]:best=item
        if best is None:break
        selected.append(best[3]);route.append(best[3]);weight[best[4]]*=0.02
        stats.append({'score':float(best[0]),'coverage':float(best[1]),'insertion_m':float(-best[2])})
    return selected,stats


def plan_probes(belief,current,hypothetical,budget):
    return plan_probes_with_stats(belief,current,hypothetical,budget)[0]
