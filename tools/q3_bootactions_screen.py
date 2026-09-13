from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'base':{},
 'v550':{'route_scan_value_s':550},
 'info3':{'route_scan_value_s':550,'adaptive_bootstrap_info':0,'bootstrap_info_limit':3},
 'info4':{'route_scan_value_s':550,'adaptive_bootstrap_info':0,'bootstrap_info_limit':4},
 'info5':{'route_scan_value_s':550,'adaptive_bootstrap_info':0,'bootstrap_info_limit':5},
 'info6':{'route_scan_value_s':550,'adaptive_bootstrap_info':0,'bootstrap_info_limit':6},
 'no2scan':{'route_scan_value_s':550,'bootstrap_unknown_scan':0},
 'no2scan_i4':{'route_scan_value_s':550,'bootstrap_unknown_scan':0,'adaptive_bootstrap_info':0,'bootstrap_info_limit':4},
 'no2scan_i6':{'route_scan_value_s':550,'bootstrap_unknown_scan':0,'adaptive_bootstrap_info':0,'bootstrap_info_limit':6},
}
b.main()
