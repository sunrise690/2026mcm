from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

# Generation 2: spend essentially no extra motion on exploration. Instead, when
# choosing which already-detected source to clear next, reward source locations
# that are also likely to expose a still-hidden channel. Combine this with the
# endpoint-to-next-hotspot objective patched by bench_candidates.
b.CANDIDATES={
 'baseline':{},
 'bonus150':{'source_detect_bonus_s':150,'source_detect_min_known':4,'source_choice_pool':6},
 'bonus300':{'source_detect_bonus_s':300,'source_detect_min_known':4,'source_choice_pool':6},
 'bonus500':{'source_detect_bonus_s':500,'source_detect_min_known':4,'source_choice_pool':6},
 'bonus800':{'source_detect_bonus_s':800,'source_detect_min_known':4,'source_choice_pool':6},
 'tail075_bonus300':{'route_end_explore':1,'route_end_explore_weight':0.75,'source_detect_bonus_s':300,'source_detect_min_known':4,'source_choice_pool':6},
 'tail075_bonus500':{'route_end_explore':1,'route_end_explore_weight':0.75,'source_detect_bonus_s':500,'source_detect_min_known':4,'source_choice_pool':6},
 'tail075_scan1500':{'route_end_explore':1,'route_end_explore_weight':0.75,'route_scan_value_s':1500},
 'tail075_unc110':{'route_end_explore':1,'route_end_explore_weight':0.75,'service_uncertainty_trigger':110},
 'tail075_detour25':{'route_end_explore':1,'route_end_explore_weight':0.75,'service_waypoint_detour_weight':2.5},
 'plain_tail100':{'service_aware_route':0,'route_end_explore':1,'route_end_explore_weight':1.0},
}
b.main()
