from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

ROOT = Path('/root/autodl-tmp/b0_iteration_20260912')
Q4 = ROOT / 'feedback_v2_q4'
LIVE = Q4 / 'workspace' / 'code' / 'live_q4.py'
TUNE = Q4 / 'feedback_tune_q4.py'


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f'missing block: {old[:80]!r}')
    return text.replace(old, new, 1)


def replace_re_once(text: str, pattern: str, new: str) -> str:
    text2, n = re.subn(pattern, new, text, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError(f'missing regex block: {pattern[:80]!r}')
    return text2


def kill_tree(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        pass


stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup = Q4 / f'round11_before_risk_targeted_{stamp}'
backup.mkdir(parents=True, exist_ok=False)
for p in (LIVE, TUNE):
    shutil.copy2(p, backup / p.name)
if (Q4 / 'feedback_results').exists():
    shutil.copytree(Q4 / 'feedback_results', backup / 'feedback_results')

live = LIVE.read_text(encoding='utf-8')

live = replace_once(
    live,
    "MID_RISK_MAX_FOUND=15\n",
    "MID_RISK_MAX_FOUND=15\n"
    "FIRST_PROBE_MIN_FOUND=10\n"
    "FIRST_PROBE_RISK=0.18\n"
    "POST_CLEAR_SCAN_MIN_UNKNOWN=2\n"
    "POST_CLEAR_SCAN_MIN_FOUND=10\n"
    "POST_CLEAR_SCAN_INTERVAL=1\n"
    "BOOTSTRAP_RADIUS_M=800.0\n"
    "BOOTSTRAP_MODE='adaptive'\n"
    "BOOTSTRAP_TRAVEL_PENALTY=0.00045\n",
)

live = replace_re_once(
    live,
    r"            if core\._clear_corridor_live\(client,beliefs,c\):\n"
    r"                cleared\.add\(c\)\n"
    r"                print\(f'.*?'\)\n"
    r"            scan\(client\.current_position_m\)\n",
    "            if core._clear_corridor_live(client,beliefs,c):\n"
    "                cleared.add(c)\n"
    "                print(f'cleared {c}; cleared={len(cleared)} found={len(found)}')\n"
    "            unknown_now=[ch for ch,b in beliefs.items() if b['status']=='unknown']\n"
    "            do_post_scan=(len(found)>=int(POST_CLEAR_SCAN_MIN_FOUND)\n"
    "                          and len(unknown_now)>=int(POST_CLEAR_SCAN_MIN_UNKNOWN)\n"
    "                          and int(POST_CLEAR_SCAN_INTERVAL)>0\n"
    "                          and attempted[c] % int(POST_CLEAR_SCAN_INTERVAL)==0)\n"
    "            if do_post_scan:\n"
    "                scan(client.current_position_m)\n",
)

live = replace_re_once(
    live,
    r"    # .*?\n"
    r"    if BOOTSTRAP_POINTS>1:\n"
    r"        for a in np\.arange\(BOOTSTRAP_POINTS-1\)\*360/max\(1,BOOTSTRAP_POINTS-1\):\n"
    r"            q=800\*np\.asarray\(\[math\.cos\(math\.radians\(a\)\),math\.sin\(math\.radians\(a\)\)\]\)\n"
    r"            scan\(q,force=True\)\n"
    r"            risk_now,_=remaining_risk\(beliefs,found\)\n"
    r"            if len\(found\)>=RISK_STOP_MIN_FOUND and risk_now<STOP_RISK:\n"
    r"                print\(f'.*?'\)\n"
    r"                break\n",
    "    # Adaptive bootstrap: choose the next census point from the current posterior\n"
    "    # instead of walking a fixed ring. Ring points remain available only as an\n"
    "    # explicit searched fallback mode.\n"
    "    if BOOTSTRAP_POINTS>1 and str(BOOTSTRAP_MODE)!='none':\n"
    "        for step in range(int(BOOTSTRAP_POINTS)-1):\n"
    "            if str(BOOTSTRAP_MODE)=='ring':\n"
    "                a=step*360/max(1,int(BOOTSTRAP_POINTS)-1)\n"
    "                q=float(BOOTSTRAP_RADIUS_M)*np.asarray([math.cos(math.radians(a)),math.sin(math.radians(a))])\n"
    "            else:\n"
    "                risk_now,target_channel=remaining_risk(beliefs,found)\n"
    "                unknown=[c for c,b in beliefs.items() if b['status']=='unknown']\n"
    "                if not unknown: break\n"
    "                target_channel=target_channel if target_channel in unknown else unknown[0]\n"
    "                q,prob=select_probe(beliefs[target_channel],client.current_position_m,\n"
    "                                    [np.asarray(x,float) for x in visited],\n"
    "                                    travel_penalty=float(BOOTSTRAP_TRAVEL_PENALTY))\n"
    "                if q is None: break\n"
    "                print(f'adaptive bootstrap {step+1}: risk={risk_now:.3f}; target={target_channel}; p={prob:.3f}')\n"
    "            scan(q,force=True)\n"
    "            risk_now,_=remaining_risk(beliefs,found)\n"
    "            if len(found)>=RISK_STOP_MIN_FOUND and risk_now<STOP_RISK:\n"
    "                print(f'bootstrap early stop found={len(found)} risk={risk_now:.3f}')\n"
    "                break\n",
)

live = replace_once(
    live,
    "    unknown=[c for c,b in beliefs.items() if b['status']=='unknown']\n"
    "    if unknown:\n"
    "        pending_probes.extend(plan_probes(beliefs[unknown[0]],client.current_position_m,[x for x in hypothetical if x is not None],PROBE_BATCH_SIZE))\n",
    "    risk,target_channel=remaining_risk(beliefs,found)\n"
    "    unknown=[c for c,b in beliefs.items() if b['status']=='unknown']\n"
    "    first_probe=(unknown and int(PROBE_BATCH_SIZE)>0\n"
    "                 and (len(found)<int(FIRST_PROBE_MIN_FOUND) or risk>=float(FIRST_PROBE_RISK)))\n"
    "    if first_probe:\n"
    "        target_channel=target_channel if target_channel in unknown else unknown[0]\n"
    "        pending_probes.extend(plan_probes(beliefs[target_channel],client.current_position_m,[x for x in hypothetical if x is not None],PROBE_BATCH_SIZE))\n"
    "        print(f'first joint probe risk={risk:.3f}; target={target_channel}; budget={PROBE_BATCH_SIZE}')\n"
    "    else:\n"
    "        print(f'first joint probe skipped risk={risk:.3f}; found={len(found)}')\n",
)

live = replace_once(
    live,
    "        q,p=select_probe(beliefs[unknown[0]],client.current_position_m,[np.asarray(x) for x in visited],travel_penalty=0.00045)\n",
    "        _,target_channel=remaining_risk(beliefs,found)\n"
    "        target_channel=target_channel if target_channel in unknown else unknown[0]\n"
    "        q,p=select_probe(beliefs[target_channel],client.current_position_m,[np.asarray(x) for x in visited],travel_penalty=0.00045)\n",
)

LIVE.write_text(live, encoding='utf-8')

tune = TUNE.read_text(encoding='utf-8')
tune = replace_once(
    tune,
    " 'ONE_BEARING_HOMING_STEP_M':[300.0,400.0,500.0],\n}",
    " 'ONE_BEARING_HOMING_STEP_M':[300.0,400.0,500.0],\n"
    " 'FIRST_PROBE_MIN_FOUND':[9,10,11,12],\n"
    " 'FIRST_PROBE_RISK':[0.08,0.12,0.18,0.25,0.35],\n"
    " 'POST_CLEAR_SCAN_MIN_UNKNOWN':[1,2,3,4],\n"
    " 'POST_CLEAR_SCAN_MIN_FOUND':[9,10,11,12,13],\n"
    " 'POST_CLEAR_SCAN_INTERVAL':[1,2,3],\n"
    " 'BOOTSTRAP_RADIUS_M':[650.0,800.0,950.0,1100.0],\n"
    " 'BOOTSTRAP_MODE':['adaptive','ring','none'],\n"
    " 'BOOTSTRAP_TRAVEL_PENALTY':[0.00025,0.00035,0.00045,0.00065,0.0009],\n"
    "}",
)
tune = replace_once(
    tune,
    "'ONE_BEARING_HOMING':False,'ONE_BEARING_HOMING_STEP_M':400.0}",
    "'ONE_BEARING_HOMING':False,'ONE_BEARING_HOMING_STEP_M':400.0,"
    "'FIRST_PROBE_MIN_FOUND':10,'FIRST_PROBE_RISK':0.18,"
    "'POST_CLEAR_SCAN_MIN_UNKNOWN':2,'POST_CLEAR_SCAN_MIN_FOUND':10,"
    "'POST_CLEAR_SCAN_INTERVAL':1,'BOOTSTRAP_RADIUS_M':800.0,"
    "'BOOTSTRAP_MODE':'adaptive','BOOTSTRAP_TRAVEL_PENALTY':0.00045}",
)
tune = replace_once(
    tune,
    "dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.85,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1)]",
    "dict(BASE,BOOTSTRAP_POINTS=4,STOP_RISK=.85,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1),\n"
    "   dict(BASE,BOOTSTRAP_POINTS=3,BOOTSTRAP_MODE='adaptive',BOOTSTRAP_TRAVEL_PENALTY=.00065,STOP_RISK=.65,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1,FIRST_PROBE_RISK=.25,POST_CLEAR_SCAN_MIN_FOUND=11,POST_CLEAR_SCAN_MIN_UNKNOWN=3),\n"
    "   dict(BASE,BOOTSTRAP_POINTS=2,BOOTSTRAP_MODE='adaptive',BOOTSTRAP_TRAVEL_PENALTY=.00035,STOP_RISK=.75,TAIL_BUDGET=2,PROBE_BATCH_SIZE=2,FIRST_PROBE_MIN_FOUND=11,POST_CLEAR_SCAN_INTERVAL=2),\n"
    "   dict(BASE,BOOTSTRAP_POINTS=4,BOOTSTRAP_MODE='none',STOP_RISK=.50,TAIL_BUDGET=1,PROBE_BATCH_SIZE=1,MID_RISK_EXTRA_PROBES=0,POST_CLEAR_SCAN_MIN_FOUND=12)]",
)
TUNE.write_text(tune, encoding='utf-8')

pid_file = Q4 / 'feedback_q4_v2.pid'
if pid_file.exists():
    try:
        kill_tree(int(pid_file.read_text().strip()))
    except Exception as exc:
        print('pid stop warning', repr(exc))

log = open(Q4 / 'feedback_q4_v2.log', 'ab')
proc = subprocess.Popen(
    ['/root/miniconda3/bin/python', 'feedback_tune_q4.py', '--generations', '1000',
     '--population', '40', '--workers', '12', '--screen-per-n', '2', '--validate-per-n', '10'],
    cwd=str(Q4), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    start_new_session=True,
)
pid_file.write_text(str(proc.pid), encoding='utf-8')
print(json.dumps({
    'round': 11,
    'pid': proc.pid,
    'backup': str(backup),
    'changes': [
        'adaptive bootstrap replaces fixed initial ring as the default discovery route',
        'risk-targeted first/joint/tail probes use highest posterior survival channel',
        'searchable first-probe gate by found count and posterior risk',
        'searchable post-clear scan gate to reduce repeated all-channel scans',
        'searchable bootstrap radius anchors for discovery cost/coverage balance',
    ],
}, indent=2))
