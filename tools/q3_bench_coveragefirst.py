from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'cov1_8':{'geometry_mode':1,'coverage_preclear_min_known':8},
 'cov1_9':{'geometry_mode':1,'coverage_preclear_min_known':9},
 'cov1_10':{'geometry_mode':1,'coverage_preclear_min_known':10},
 'cov4_8':{'geometry_mode':4,'coverage_preclear_min_known':8},
 'cov4_9':{'geometry_mode':4,'coverage_preclear_min_known':9},
 'cov4_10':{'geometry_mode':4,'coverage_preclear_min_known':10},
 'cov1_9_lean':{'geometry_mode':1,'coverage_preclear_min_known':9,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 'cov4_9_lean':{'geometry_mode':4,'coverage_preclear_min_known':9,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
}
b.main()
