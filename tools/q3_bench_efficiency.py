from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

# Generation 4: attack action overhead rather than adding exploration trips.
# Keep stop thresholds unchanged so any gain here is not bought with missed sources.
b.CANDIDATES={
 'baseline':{},
 'leaninfo':{'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 'leaninfo2':{'route_info_limit_low':1,'route_info_limit_high':1,'hard_done_info_limit':0},
 'unc100':{'service_uncertainty_trigger':100},
 'unc130':{'service_uncertainty_trigger':130},
 'unc160':{'service_uncertainty_trigger':160},
 'detour20':{'service_waypoint_detour_weight':2.0},
 'detour35':{'service_waypoint_detour_weight':3.5},
 'unc130_lean':{'service_uncertainty_trigger':130,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 'unc160_lean':{'service_uncertainty_trigger':160,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
 'detour20_lean':{'service_waypoint_detour_weight':2.0,'route_info_limit_low':0,'route_info_limit_high':1,'hard_done_info_limit':0},
}
b.main()
