from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'off':{'adaptive_route_scan':0},
 'v400':{'adaptive_route_scan':1,'route_scan_value_s':400},
 'v550':{'adaptive_route_scan':1,'route_scan_value_s':550},
 'v700':{'adaptive_route_scan':1,'route_scan_value_s':700},
 'v1100':{'adaptive_route_scan':1,'route_scan_value_s':1100},
 'v1300':{'adaptive_route_scan':1,'route_scan_value_s':1300},
}
b.main()
