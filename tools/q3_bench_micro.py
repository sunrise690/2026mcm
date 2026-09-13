from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'lean':{'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 's2lean':{'stop_thr_10':0.50,'stop_thr_11':0.60,'stop_thr_12':0.68,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 'cov4_9lean':{'geometry_mode':4,'coverage_preclear_min_known':9,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
}
b.main()
