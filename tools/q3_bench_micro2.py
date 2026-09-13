from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'v550':{'route_scan_value_s':550},
 'v550_b600':{'route_scan_value_s':550,'bootstrap_radii':[600,800,1000]},
 'v550_b650':{'route_scan_value_s':550,'bootstrap_radii':[650,850,1050]},
 'direct_v550':{'service_waypoint':0,'service_aware_route':0,'route_scan_value_s':550},
 'v550_r1':{'route_scan_value_s':550,'risk_empty_probe_stop':1,'risk_empty_probe_limit':1,'risk_empty_probe_max_known':12},
}
b.main()
