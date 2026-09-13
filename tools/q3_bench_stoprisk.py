from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

# Generation 5: bounded risk only on the low-count posterior stop thresholds.
# N>=13 thresholds remain the proven sparseboot3 values.
b.CANDIDATES={
 'baseline':{},
 's1':{'stop_thr_10':0.54,'stop_thr_11':0.64,'stop_thr_12':0.72},
 's2':{'stop_thr_10':0.50,'stop_thr_11':0.60,'stop_thr_12':0.68},
 's3':{'stop_thr_10':0.46,'stop_thr_11':0.58,'stop_thr_12':0.66},
 's4':{'stop_thr_10':0.42,'stop_thr_11':0.54,'stop_thr_12':0.62},
 's1_lean':{'stop_thr_10':0.54,'stop_thr_11':0.64,'stop_thr_12':0.72,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 's2_lean':{'stop_thr_10':0.50,'stop_thr_11':0.60,'stop_thr_12':0.68,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 's3_lean':{'stop_thr_10':0.46,'stop_thr_11':0.58,'stop_thr_12':0.66,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
}
b.main()
