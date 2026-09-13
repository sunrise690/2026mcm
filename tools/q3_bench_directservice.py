from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

b.CANDIDATES={
 'baseline':{},
 'direct':{'service_waypoint':0,'service_aware_route':0},
 'direct_aw':{'service_waypoint':0,'service_aware_route':1},
 'unc180':{'service_uncertainty_trigger':180},
 'unc240':{'service_uncertainty_trigger':240},
 'unc320':{'service_uncertainty_trigger':320},
 'unc180_v550':{'service_uncertainty_trigger':180,'route_scan_value_s':550},
 'direct_v550':{'service_waypoint':0,'service_aware_route':0,'route_scan_value_s':550},
}
b.main()
