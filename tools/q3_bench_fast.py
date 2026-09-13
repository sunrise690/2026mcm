from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b
b.CANDIDATES={
 'baseline':{},
 'tail050':{'route_end_explore':1,'route_end_explore_weight':0.50},
 'tail075':{'route_end_explore':1,'route_end_explore_weight':0.75},
 'tail100':{'route_end_explore':1,'route_end_explore_weight':1.00},
 'tail125':{'route_end_explore':1,'route_end_explore_weight':1.25},
 'tail100_bonus300':{'route_end_explore':1,'route_end_explore_weight':1.00,'source_detect_bonus_s':300,'source_detect_min_known':4,'source_choice_pool':6},
 'tail100_noprobe':{'route_end_explore':1,'route_end_explore_weight':1.00,'probe_allow_base_low':-1000,'probe_allow_gain_low':0,'probe_allow_base_high':-1000,'probe_allow_gain_high':0},
 'tail100_leaninfo':{'route_end_explore':1,'route_end_explore_weight':1.00,'route_info_limit_low':1,'route_info_limit_high':2,'hard_done_info_limit':0},
}
b.main()
