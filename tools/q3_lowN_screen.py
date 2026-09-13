from pathlib import Path
import sys, json, statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

CASES=[1003,1024,1007,1015,1013,1022]  # N10,N10,N11,N11,N12,N12
C={
 'baseline':{},
 'v500':{'route_scan_value_s':500},
 'v550':{'route_scan_value_s':550},
 'v600':{'route_scan_value_s':600},
 'v500_m12':{'route_scan_value_s':500,'adaptive_route_scan_max_known':12},
 'v550_m12':{'route_scan_value_s':550,'adaptive_route_scan_max_known':12},
 'v600_m12':{'route_scan_value_s':600,'adaptive_route_scan_max_known':12},
 'v550_b600':{'route_scan_value_s':550,'bootstrap_radii':[600,800,1000]},
 'v550_b650':{'route_scan_value_s':550,'bootstrap_radii':[650,850,1050]},
 'v550_b750':{'route_scan_value_s':550,'bootstrap_radii':[750,950,1150]},
 'direct_v550':{'service_waypoint':0,'service_aware_route':0,'route_scan_value_s':550},
 'unc180_v550':{'service_uncertainty_trigger':180,'route_scan_value_s':550},
 'r1_v550':{'route_scan_value_s':550,'risk_empty_probe_stop':1,'risk_empty_probe_limit':1,'risk_empty_probe_max_known':12},
}

def main():
    args=[(name,ov,s) for name,ov in C.items() for s in CASES]
    rows=[]
    with ProcessPoolExecutor(max_workers=7) as ex:
        fs=[ex.submit(b.work,a) for a in args]
        for f in as_completed(fs):
            r=f.result();rows.append(r);print('ROW',json.dumps(r),flush=True)
    out={}
    for name in C:
        rr=[r for r in rows if r['variant']==name]
        by={}
        for n in (10,11,12):
            q=[r for r in rr if r['N']==n]
            by[n]=statistics.mean(r['avg'] for r in q)
        out[name]={'fullclear':sum(r['ok'] for r in rr),'mean_lowN':statistics.mean(by.values()),'byN':by,'max':max(r['avg'] for r in rr)}
    rank=sorted(out,key=lambda x:(out[x]['fullclear']<6,out[x]['mean_lowN']))
    print('RESULT_JSON='+json.dumps({'ranking':rank,'summary':out},sort_keys=True))
if __name__=='__main__':main()
