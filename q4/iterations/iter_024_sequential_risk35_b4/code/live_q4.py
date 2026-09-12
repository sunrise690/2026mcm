"""第四问自适应级联探索：仅基于公开反馈，复用保守定位清除。"""
from __future__ import annotations
import json, math, time
from pathlib import Path
import numpy as np
import q4_core as core
from q4_targeted_rescue_v3 import select_probe
from channel_risk import remaining_risk

VERSION='v408-sequential-risk35-b4'
STOP_RISK=0.35
TAIL_BUDGET=4
MIN_SCAN_SEPARATION=300.0
RESCAN_LIMIT=2
BOOTSTRAP_POINTS=4

def configure_profile(name):
    core.configure_profile(name)


def run_q4(client, *, case_code, real_margin_s=45.0, scan_detected_again=True, fast=False, full_census=False):
    start=time.monotonic()
    client.current_position_m=np.zeros(2)
    client.current_virtual_time_s=0.0
    client.current_channel=1
    entered=client.enter()
    deadline=float(entered.get('remaining_real_duration_s',1200))-real_margin_s
    beliefs=core.new_beliefs(); found=set(); cleared=set(); visited=[]; attempted={}

    def scan(point, force=False):
        point=np.asarray(point,float)
        unknown=[c for c,b in beliefs.items() if b['status']=='unknown']
        if not unknown and len(found)>=16:return
        if not force and visited and min(np.linalg.norm(point-np.asarray(v)) for v in visited)<MIN_SCAN_SEPARATION:return
        visited.append(point.tolist())
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
            if not options:break
            _,c,target=min(options,key=lambda x:x[0])
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
    # 先利用清除终点扫描；每次只增加一个探点，随后重算频道连续性风险。
    from joint_probe import plan_probes
    clear_detected()
    tails=[]
    for k in range(TAIL_BUDGET):
        if len(found)>=16 or time.monotonic()-start>=deadline:break
        unknown=[c for c,b in beliefs.items() if b['status']=='unknown']
        if not unknown:break
        risk,target_channel=remaining_risk(beliefs,found)
        if risk<STOP_RISK:
            print(f'尾部频道后验剩余风险{risk:.3f}低于阈值，停止补探')
            break
        target_channel=target_channel if target_channel in unknown else unknown[0]
        planned=plan_probes(beliefs[target_channel],client.current_position_m,[],1)
        if not planned:break
        q=np.asarray(planned[0],float)
        print(f'顺序后验探索{k+1}，剩余风险{risk:.3f}')
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
