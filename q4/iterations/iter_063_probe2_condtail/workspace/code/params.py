"""题面参数唯一入口；数值均从 PROBLEM_FACTS.json 读取。"""
from pathlib import Path
import json

_ROOT = Path(__file__).resolve().parents[1]
_FACTS = json.loads((_ROOT / "PROBLEM_FACTS.json").read_text(encoding="utf-8"))
SPATIAL = _FACTS["domain"]["spatial"]
TEMPORAL = _FACTS["domain"]["temporal"]
JAMMER = next(x for x in _FACTS["entities"] if x["id"] == "jammer")
ROBOT = next(x for x in _FACTS["entities"] if x["id"] == "robot_dog")
COST = {x["action"]: x["cost"] for x in _FACTS["action_costs_s"]}
REGION_RADIUS_M = float(SPATIAL["region_radius_m"])
COORD_ABS_LIMIT_M = float(SPATIAL["coord_abs_limit_m"])
BEARING_ERROR_BOUND_DEG = float(max(abs(x) for x in _FACTS["measurement"]["svd_error_deg"]))
R_EFF_LO_M, R_EFF_HI_M = map(float, JAMMER["effective_radius_range_m"])
NEAR_RADIUS_M = float(_FACTS["measurement"]["near_threshold_m"])
CLEAR_RADIUS_M = float(_FACTS["measurement"]["clear_radius_m"])
ROBOT_SPEED_MPS = float(ROBOT["speed_mps"])
MEASURE_ACTION_TIME_S = float(COST["measure"])
CHANNEL_SWITCH_TIME_S = float(COST["channel_switch"])
CLEAR_FAILED_TIME_S = float(COST["clear_no_target"])
CLEAR_SUCCESS_TIME_S = float(COST["clear_success"])
OPTICAL_LOCATE_TIME_S = float(COST["optical_locate"])
LASER_CLEAR_TIME_S = float(COST["laser_clear"])
VIRTUAL_TIME_LIMIT_S = float(TEMPORAL["max_virtual_duration_s"])
MAX_REAL_DURATION_S = float(TEMPORAL["max_real_duration_s"])
SOURCE_COUNT_MIN, SOURCE_COUNT_MAX = map(int, JAMMER["count_range"])
CHANNEL_MIN, CHANNEL_MAX = map(int, JAMMER["channel_range"])
DIRECTIONAL_HALF_ANGLE_DEG = float(JAMMER["directional_half_angle_deg"])
GEOM_TOL_M = 1e-7
ANGLE_TOL_DEG = 1e-9
DIAMETER_TOL_M = 0.01
CANDIDATE_BOUNDARY_TOL_M = 0.5
Q4_POSITION_BOX_TOL_M = 1.0
Q4_HEADING_BOX_TOL_DEG = 0.1
BOOTSTRAP_REPLICATES = 2000
BASE_SEED = 20260911
SCENARIOS_PER_N = 5

assert CLEAR_SUCCESS_TIME_S == OPTICAL_LOCATE_TIME_S + LASER_CLEAR_TIME_S
assert R_EFF_LO_M <= R_EFF_HI_M <= REGION_RADIUS_M
assert SOURCE_COUNT_MIN <= SOURCE_COUNT_MAX <= CHANNEL_MAX
print("[params] 题面参数与时间口径一致性 PASS")
