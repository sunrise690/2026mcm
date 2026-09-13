from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'q3'/'bench'))
import bench_candidates as b

# Scan unknown channels only at localization waypoints that the robot already
# visits. This spends measurement/switch time but adds no extra travel.
b.CANDIDATES={
 'baseline':{},
 'ws04_12':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.04,'service_waypoint_unknown_max_known':12},
 'ws08_12':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.08,'service_waypoint_unknown_max_known':12},
 'ws12_12':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.12,'service_waypoint_unknown_max_known':12},
 'ws16_12':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.16,'service_waypoint_unknown_max_known':12},
 'ws08_14':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.08,'service_waypoint_unknown_max_known':14},
 'ws12_14':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.12,'service_waypoint_unknown_max_known':14},
 'ws16_14':{'service_waypoint_unknown_scan':1,'service_waypoint_unknown_thr':0.16,'service_waypoint_unknown_max_known':14},
}
b.main()
