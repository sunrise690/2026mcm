"""第四问自适应级联探索：仅基于公开反馈，复用保守定位清除。"""
from __future__ import annotations
import json, math, time
from pathlib import Path
import numpy as np
import q4_core as core
from q4_targeted_rescue_v3 import select_probe

VERSION='v435-adaptive-probe4-guard'
OPPORTUNITY_UNKNOWN_LIMIT=4
TAIL_BUDGET=1
MIN_SCAN_SEPARATION=300.0
RESCAN_LIMIT=2
BOOTSTRAP_POINTS=5

def configure_profile(name):
    core.configure_profile(name)


def run_q4(client, *, case_code, real_margin_s=45.0, scan_detected_again=True, fast=False, full_census=False):
    start=time.monotonic()
    client.current_position_m=np.zeros(2)
    client.current_virtual_time_s=0.0
    client.current_channel=1
    entered=client.enter()
    deadline=float(entered.get('remaining_real_duration_s',1200))-real_margin_s
    beliefs=core.new_beliefs(); found=set(); cleared=set(); visited=[]; attempted={}; pending_probes=[]
    opportunity_cursor=0

    def scan(point, force=False):
        nonlocal opportunity_cursor
        point=np.asarray(point,float)
        unknown=[c for c,b in beliefs.items() if b['status']=='unknown']
        if not unknown and len(found)>=16:return
        if not force and visited and min(np.linalg.norm(point-np.asarray(v)) for v in visited)<MIN_SCAN_SEPARATION:return
        visited.append(point.tolist())
        if not force and len(found)>=14 and len(unknown)>OPPORTUNITY_UNKNOWN_LIMIT:
            unknown.sort(key=lambda c:(len(beliefs[c].get('no_signal_points',[])),(c-opportunity_cursor)%21))
            unknown=unknown[:OPPORTUNITY_UNKNOWN_LIMIT]
            opportunity_cursor=unknown[-1]
        rescans=core.q4_select_rescan_channels(beliefs,point,limit=RESCAN_LIMIT) if scan_detected_again else []
        channels=unknown+ [c for c in rescans if c not in unknown]
        if client.current_channel in channels:
            channels.remove(client.current_channel);channels.insert(0,client.current_channel)
        for c in channels:
            body=core._measure_live(client,beliefs,point,c)
            if body.get('measure_result') in ('direction','near'):
                found.add(c)
                if body.get('measure_result')=='near':
                    cb=core._clear_live(client,beliefs,point,c,'cascade_near')
                    if cb.get('clear_result')=='success':cleared.add(c)
            if len(found)>=16:break

    def clear_detected():
        while time.monotonic()-start<deadline:
            options=[]
            for c in sorted(found):
                b=beliefs[c]
                if b['status']!='detected' or attempted.get(c,0)>=2:continue
                target=core._belief_target_point(b)
                if target is not None:
                    dist=float(np.linalg.norm(np.asarray(target)-client.current_position_m))
                    options.append((dist,c,target))
            all_points=[x[2] for x in options]+pending_probes
            if not all_points:break
            order=core._nearest_neighbor_order(client.current_position_m,all_points)
            order=core._two_opt_order(client.current_position_m,all_points,order,max_passes=20)
            index=order[0]
            if index>=len(options):
                point=pending_probes.pop(index-len(options))
                if len(found)<16:scan(point,force=True)
                continue
            _,c,target=options[index]
            attempted[c]=attempted.get(c,0)+1
            if core._clear_corridor_live(client,beliefs,c):
                cleared.add(c)
                print(f'级联清除{c}，累计{len(cleared)}；已发现{len(found)}')
            scan(client.current_position_m)
    scan(np.zeros(2),force=True)
    # 初始测点只用于没有可用测向/支撑交会的启动；不强制完成全环。
    if BOOTSTRAP_POINTS>1:
        for a in np.arange(BOOTSTRAP_POINTS-1)*360/max(1,BOOTSTRAP_POINTS-1):
            q=800*np.asarray([math.cos(math.radians(a)),math.sin(math.radians(a))])
            scan(q,force=True)
    # 预计清除终点也可扫描：补查点提前插入联合路线，避免完成清除后重新跨场。
    from q4_targeted_rescue_v3 import _particles
    from joint_probe import plan_probes_with_stats
    hypothetical=[core._belief_target_point(beliefs[c]) for c in sorted(found) if beliefs[c]['status']=='detected']
    unknown=[c for c,b in beliefs.items() if b['status']=='unknown']
    if unknown:
        planned,probe_stats=plan_probes_with_stats(beliefs[unknown[0]],client.current_position_m,[x for x in hypothetical if x is not None],4)
        probe_budget=3
        one_bearing_count=sum(b['status']=='detected' and len(b.get('directions',[]))==1 for b in beliefs.values())
        if len(probe_stats)>=4:
            fourth=probe_stats[3]
            regular_guard=10<=len(found)<=12 and (fourth['coverage']>=0.18 or fourth['insertion_m']<=100.0)
            sparse_guard=(len(found)<=8 or (len(found)==9 and fourth['coverage']>=0.16) or (len(found)==10 and one_bearing_count<=5))
            if regular_guard or sparse_guard:
                probe_budget=4
        pending_probes.extend(planned[:probe_budget])
    clear_detected()
    tails=[]
    for k in range(TAIL_BUDGET):
        if len(found)>=16 or time.monotonic()-start>=deadline:break
        unknown=[c for c,b in beliefs.items() if b['status']=='unknown']
        if not unknown:break
        q,p=select_probe(beliefs[unknown[0]],client.current_position_m,[np.asarray(x) for x in visited],travel_penalty=0.00045)
        if q is None:break
        print(f'后验探索{k+1} 概率{p:.3f}')
        scan(q,force=True);tails.append(q.tolist())
        clear_detected()
    client.exit()
    result={'version':VERSION,'profile':'cascade','problem':4,'case_code':case_code,
       'cleared_channels':sorted(cleared),'cleared_count_observed_by_program':len(cleared),
       'positive_channels':sorted(found),'unknown_channels_at_exit':[c for c,b in beliefs.items() if b['status']=='unknown'],
       'visited_census_points_m':visited,'visited_census_count':len(visited),'tail_points_m':tails,
       'virtual_time_s':client.current_virtual_time_s,
       'average_clear_time_s_observed_by_program':client.current_virtual_time_s/len(cleared) if cleared else None,
       'program_runtime_s':time.monotonic()-start,'log_path':str(client.log_path)}
    client.log_path.with_suffix('.summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    import argparse
    from live_runner import SimulatorClient
    ap=argparse.ArgumentParser();ap.add_argument('--robot-id',required=True);ap.add_argument('--base-url',default='http://127.0.0.1:2026');ap.add_argument('--log',default='figures/cascade.jsonl');args=ap.parse_args()
    run_q4(SimulatorClient(args.robot_id,args.base_url,log_path=args.log),case_code='cascade')


