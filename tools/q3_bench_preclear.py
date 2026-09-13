from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'pre6':{'preclear_probe_once':1,'preclear_probe_max_known':6,'preclear_probe_info_limit':0},
 'pre7':{'preclear_probe_once':1,'preclear_probe_max_known':7,'preclear_probe_info_limit':0},
 'pre8':{'preclear_probe_once':1,'preclear_probe_max_known':8,'preclear_probe_info_limit':0},
 'pre9':{'preclear_probe_once':1,'preclear_probe_max_known':9,'preclear_probe_info_limit':0},
 'pre8_tail100':{'preclear_probe_once':1,'preclear_probe_max_known':8,'preclear_probe_info_limit':0,'route_end_explore':1,'route_end_explore_weight':1.0},
 'pre8_info2':{'preclear_probe_once':1,'preclear_probe_max_known':8,'preclear_probe_info_limit':2},
 'pre8_scan1500':{'preclear_probe_once':1,'preclear_probe_max_known':8,'preclear_probe_info_limit':0,'route_scan_value_s':1500},
}
b.main()
