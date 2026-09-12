"""第四问自适应级联探索：仅基于公开反馈，复用保守定位清除。"""
from __future__ import annotations
import json, math, time
from pathlib import Path
import numpy as np
import q4_core as core
from q4_targeted_rescue_v3 import select_probe
from channel_count_risk import remaining_active_risk

VERSION='v456-low10-center6-boot4'
OPPORTUNITY_UNKNOWN_LIMIT=4
TAIL_BUDGET=1
MIN_SCAN_SEPARATION=300.0
RESCAN_LIMIT=2
HIGH_DENSITY_RESCAN_LIMIT=6
HIGH_DENSITY_FOUND_MIN=14
HIGH_DENSITY_ONE_BEARING_MIN=4
RESCAN_SKIP_MEC_RADIUS_M=20.0
BOOTSTRAP_POINTS=4
DYNAMIC_ROUTE_CENTER_FOUND_MIN=6
DYNAMIC_LATE_RESCUE_MAX_FOUND=12
OPPORTUNITY_REMAINING_RISK_FLOOR=0.14
TAIL_REMAINING_RISK_FLOOR=0.24

def configure_profile(name):
    core.configure_profile(name)


def _rescan_still_useful(belief):
    """只跳过已收缩到清除半径量级的多示向可行域。"""
    if len(belief.get('directions',[]))<2:
        return True
    poly=core.belief_polygon(belief,sides=96)
    if len(poly)<3:
        return True
    _,radius=core.minimum_enclosing_circle(poly)
    return float(radius)>RESCAN_SKIP_MEC_RADIUS_M


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
        preserve_dense_opportunity=(not force and dense_dynamic_route
                                    and len(found)<=DYNAMIC_LATE_RESCUE_MAX_FOUND)
        if not force and unknown and len(found)>=10:
            if remaining_active_risk(beliefs,len(found))<=OPPORTUNITY_REMAINING_RISK_FLOOR and not preserve_dense_opportunity:
                unknown=[]
        if not force and visited and min(np.linalg.norm(point-np.asarray(v)) for v in visited)<MIN_SCAN_SEPARATION:return
        if (not force and len(found)>=14 and len(unknown)>OPPORTUNITY_UNKNOWN_LIMIT
                and not preserve_dense_opportunity):
            unknown.sort(key=lambda c:(len(beliefs[c].get('no_signal_points',[])),(c-opportunity_cursor)%21))
            unknown=unknown[:OPPORTUNITY_UNKNOWN_LIMIT]
            opportunity_cursor=unknown[-1]
        one_bearing_count=sum(b['status']=='detected' and len(b.get('directions',[]))==1 for b in beliefs.values())
        rescan_limit=(HIGH_DENSITY_RESCAN_LIMIT if len(found)>=HIGH_DENSITY_FOUND_MIN
                      and one_bearing_count>=HIGH_DENSITY_ONE_BEARING_MIN else RESCAN_LIMIT)
        rescans=core.q4_select_rescan_channels(beliefs,point,limit=rescan_limit) if scan_detected_again else []
        rescans=[c for c in rescans if _rescan_still_useful(beliefs[c])]
        channels=unknown+ [c for c in rescans if c not in unknown]
        if not channels:return
        visited.append(point.tolist())
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
    # 中心点已经显示高密度时，固定环不再提供足够的边际收益；
    # 后续探点直接与待清目标统一进入动态路线。低密度状态保留覆盖兜底。
    dense_dynamic_route=len(found)>=DYNAMIC_ROUTE_CENTER_FOUND_MIN
    if BOOTSTRAP_POINTS>1 and not dense_dynamic_route:
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
        if (len(found)>=14 and one_bearing_count<10 and len(probe_stats)>=3
                and probe_stats[2]['coverage']<0.24):
            probe_budget=2
        if len(probe_stats)>=4:
            fourth=probe_stats[3]
            regular_guard=10<=len(found)<=12 and (fourth['coverage']>=0.18 or fourth['insertion_m']<=100.0)
            sparse_guard=(len(found)<=8 or (len(found)==9 and fourth['coverage']>=0.16) or (len(found)==10 and one_bearing_count<=5) or (len(found)==11 and one_bearing_count<=6))
            if regular_guard or sparse_guard:
                probe_budget=4
        pending_probes.extend(planned[:probe_budget])
    clear_detected()
    tails=[]
    for k in range(TAIL_BUDGET):
        if len(found)>=16 or time.monotonic()-start>=deadline:break
        unknown=[c for c,b in beliefs.items() if b['status']=='unknown']
        if not unknown:break
        remaining_risk=remaining_active_risk(beliefs,len(found)) if len(found)>=10 else 1.0
        force_dense_rescue=dense_dynamic_route and len(found)<=DYNAMIC_LATE_RESCUE_MAX_FOUND
        if len(found)>=10 and remaining_risk<=TAIL_REMAINING_RISK_FLOOR and not force_dense_rescue:
            print('剩余活动源后验风险低，跳过尾探')
            break
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





