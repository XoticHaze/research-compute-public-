#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,statistics,tempfile,urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA='research_compute_public.p10_curve_state_forward.v1'

def fnum(x:Any):
    try:v=float(x)
    except (TypeError,ValueError):return None
    return v if math.isfinite(v) and v>0 else None

def inum(x:Any):
    try:v=int(float(x))
    except (TypeError,ValueError):return None
    return v if v>0 else None

def gpu_name(x:str,allowed:set[str]):
    u=(x or '').upper().replace('NVIDIA',' ')
    for g in sorted(allowed,key=len,reverse=True):
        if g in u:return g
    return None

def gpu_price(r):
    p=fnum(r.get('price_per_gpu_hour'))
    if p is not None:return p
    total=fnum(r.get('price_per_hour')); n=inum(r.get('gpu_count'))
    return total/n if total is not None and n else None

def download(spec,dst):
    h=hashlib.sha256(); size=0
    with urllib.request.urlopen(spec['url'],timeout=180) as src,dst.open('wb') as out:
        while True:
            b=src.read(1024*1024)
            if not b:break
            h.update(b); out.write(b); size+=len(b)
    got=h.hexdigest()
    if got!=spec['sha256']:raise RuntimeError(f'digest mismatch {got} != {spec["sha256"]}')
    return {'url':spec['url'],'sha256':got,'bytes':size}

def month_ord(m):
    y,mo=map(int,m.split('-')); return y*12+mo-1

def add_months(m,n):
    o=month_ord(m)+n; return f'{o//12:04d}-{o%12+1:02d}'

def lin_slope(vals):
    n=len(vals); xs=list(range(n)); xm=(n-1)/2; ym=statistics.fmean(vals); den=sum((x-xm)**2 for x in xs)
    return sum((x-xm)*(y-ym) for x,y in zip(xs,vals))/den if den else 0.0

def quad_acc(vals):
    # second derivative coefficient via centered quadratic least squares, solved analytically.
    n=len(vals); xs=[i-(n-1)/2 for i in range(n)]; x2=[x*x for x in xs]
    s0=n; s2=sum(x2); s4=sum(v*v for v in x2); sy=sum(vals); sy2=sum(y*q for y,q in zip(vals,x2)); den=s0*s4-s2*s2
    a=(s0*sy2-s2*sy)/den if den else 0.0
    return 2*a

def state_at(prices:list[float],pos:int,windows:list[int]):
    if pos < max(windows):return None
    logs=[math.log(p) for p in prices]
    feat=[]; slopes=[]; accs=[]; vols=[]; slope_d=[]; vol_d=[]
    for w in windows:
        seg=logs[pos-w:pos+1]; rets=[seg[i]-seg[i-1] for i in range(1,len(seg))]
        ret=seg[-1]-seg[0]; slope=lin_slope(seg); acc=quad_acc(seg); vol=(statistics.pstdev(rets) if len(rets)>1 else 0.0)
        travelled=sum(abs(x) for x in rets); eff=abs(sum(rets))/travelled if travelled else 0.0
        raw=prices[pos-w:pos+1]; dist=prices[pos]/max(raw)-1.0
        if pos-1>=w:
            prev=logs[pos-w-1:pos]; prev_rets=[prev[i]-prev[i-1] for i in range(1,len(prev))]
            ps=lin_slope(prev); pv=(statistics.pstdev(prev_rets) if len(prev_rets)>1 else 0.0)
        else: ps=slope; pv=vol
        sd=slope-ps; vd=vol-pv
        feat.extend([ret,slope,acc,vol,eff,dist,sd,vd]); slopes.append(slope); accs.append(acc); vols.append(vol); slope_d.append(sd); vol_d.append(vd)
    signs=[1 if s>0 else -1 if s<0 else 0 for s in slopes]; direction=statistics.fmean(signs); agreement=abs(direction)
    feat.extend([direction,agreement,slopes[0]-slopes[-1],accs[0]-accs[-1]])
    comps=[]
    for sd,vd,v in zip(slope_d,vol_d,vols):
        scale=max(abs(v),1e-6); comps.extend([sd/scale,vd/scale])
    feat.append(math.sqrt(statistics.fmean([x*x for x in comps])))
    if not all(math.isfinite(x) for x in feat):return None
    return feat

def median_mad(values):
    med=statistics.median(values); mad=statistics.median([abs(x-med) for x in values]); return med,mad

def knn_predict(origin_feat,candidates,k,origin_price):
    if len(candidates)<k:return None,None
    dims=len(origin_feat); centers=[]; scales=[]
    for j in range(dims):
        med,mad=median_mad([c['feat'][j] for c in candidates]); centers.append(med); scales.append(mad)
    scored=[]
    for c in candidates:
        parts=[]
        for j in range(dims):
            if scales[j]<=1e-12:continue
            parts.append(((origin_feat[j]-c['feat'][j])/scales[j])**2)
        d=math.sqrt(statistics.fmean(parts)) if parts else 0.0
        scored.append((d,c['forward_log_return']))
    scored.sort(key=lambda x:x[0]); chosen=scored[:k]
    pred=origin_price*math.exp(statistics.median([r for _,r in chosen]))
    return pred,statistics.median([d for d,_ in chosen])

def ols_log_slope(hist):
    if len(hist)<2:return None
    xs=[month_ord(r['month']) for r in hist]; ys=[math.log(r['price']) for r in hist]; xm=statistics.fmean(xs); ym=statistics.fmean(ys); den=sum((x-xm)**2 for x in xs)
    return sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den if den else None

def metric(rows,model):
    vals=[r for r in rows if r.get(model) is not None]
    if not vals:return {'n':0,'mape':None,'mae':None}
    errs=[abs(r[model]-r['realized']) for r in vals]; return {'n':len(vals),'mae':statistics.fmean(errs),'mape':statistics.fmean([e/r['realized'] for e,r in zip(errs,vals)])}

def rel(ch,b):
    return None if ch is None or b is None or b<=0 else (b-ch)/b

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('contract',type=Path); ap.add_argument('output',type=Path); ns=ap.parse_args(); c=json.loads(ns.contract.read_text())
    pool=list(c['state_pool_generations']); targets=list(c['target_generations']); allowed=set(pool); pricing=c['pricing_type']; windows=list(map(int,c['curve_windows_observations']))
    pdv=defaultdict(list); seen=set(); receipts=[]; source_rows=0
    with tempfile.TemporaryDirectory() as td:
        for i,spec in enumerate(c['archives']):
            p=Path(td)/f'a{i}.csv.gz'; receipts.append(download(spec,p))
            with gzip.open(p,'rt',encoding='utf-8',newline='') as fh:
                for r in csv.DictReader(fh):
                    if (r.get('pricing_type') or '').strip().lower()!=pricing:continue
                    g=gpu_name(r.get('gpu_name',''),allowed); provider=(r.get('provider') or r.get('source') or '').strip().lower(); date=(r.get('snapshot_date') or '').strip(); price=gpu_price(r)
                    if g is None or not provider or not date or price is None:continue
                    source_rows+=1; ident=(provider,date,g,round(price,10))
                    if ident in seen:continue
                    seen.add(ident); pdv[(provider,date,g)].append(price)
    gdv=defaultdict(list); pc=defaultdict(int)
    for (provider,date,g),vals in pdv.items():gdv[(date,g)].append(statistics.median(vals)); pc[(date,g)]+=1
    daily_by_gen={g:[] for g in pool}
    for (date,g),vals in gdv.items():daily_by_gen[g].append({'date':date,'month':date[:7],'price':statistics.median(vals),'provider_count':pc[(date,g)]})
    for g in pool:daily_by_gen[g].sort(key=lambda r:r['date'])
    monthly={g:{} for g in pool}; month_pos={g:{} for g in pool}; states={g:{} for g in pool}
    for g,rows in daily_by_gen.items():
        prices=[r['price'] for r in rows]
        for i,r in enumerate(rows):
            if r['month'] not in monthly[g] or r['date']>monthly[g][r['month']]['date']:
                monthly[g][r['month']]=r; month_pos[g][r['month']]=i
        for m,pos in month_pos[g].items():
            st=state_at(prices,pos,windows)
            if st is not None:states[g][m]=st
    # precompute causal candidate states and their realized forward log returns
    horizons=list(map(int,c['horizon_months'])); k=int(c['knn_k']); min_train=int(c['minimum_training_states']); min_prior=int(c['minimum_prior_months_for_depreciation'])
    forecasts=[]
    for target in targets:
        tmonths=sorted(monthly[target])
        for om in tmonths:
            if om not in states[target]:continue
            origin=monthly[target][om]; hist=[monthly[target][m] | {'month':m} for m in tmonths if month_ord(m)<=month_ord(om)]
            slope=ols_log_slope(hist) if len(hist)>=min_prior else None
            for h in horizons:
                rm=add_months(om,h); rr=monthly[target].get(rm)
                if rr is None:continue
                own=[]; transport=[]
                for cg in pool:
                    for cm,cf in states[cg].items():
                        crm=add_months(cm,h); cr=monthly[cg].get(crm)
                        if cr is None or cr['date']>origin['date']:continue
                        rec={'generation':cg,'feat':cf,'forward_log_return':math.log(cr['price']/monthly[cg][cm]['price'])}
                        if cg==target:own.append(rec)
                        else:transport.append(rec)
                own_pred,own_dist=(knn_predict(states[target][om],own,k,origin['price']) if len(own)>=min_train else (None,None))
                tr_pred,tr_dist=(knn_predict(states[target][om],transport,k,origin['price']) if len(transport)>=min_train else (None,None))
                dep=origin['price']*math.exp(min(0.0,slope)*h) if slope is not None else None
                forecasts.append({'generation':target,'horizon_months':h,'origin_month':om,'origin_date':origin['date'],'origin_price':origin['price'],'realized_month':rm,'realized_date':rr['date'],'realized':rr['price'],'changed_outcome':rr['price']!=origin['price'],'random_walk':origin['price'],'depreciation':dep,'own_curve_knn':own_pred,'transport_curve_knn':tr_pred,'own_training_states':len(own),'transport_training_states':len(transport),'own_neighbor_distance_median':own_dist,'transport_neighbor_distance_median':tr_dist})
    models=['random_walk','depreciation','own_curve_knn','transport_curve_knn']; min_changed=int(c['minimum_changed_origins_for_supported_result']); mat=float(c['material_improvement_fraction']); results=[]; wins={g:[] for g in targets}
    for g in targets:
        gate_model=c['gate_models'][g]
        for h in horizons:
            subset=[r for r in forecasts if r['generation']==g and r['horizon_months']==h]; changed=[r for r in subset if r['changed_outcome']]
            ms={m:metric(changed,m) for m in models}; ch=ms[gate_model]['mape']; rw=ms['random_walk']['mape']; dep=ms['depreciation']['mape']; irw=rel(ch,rw); idep=rel(ch,dep)
            supported=ms[gate_model]['n']>=min_changed and ms['random_walk']['n']>=min_changed and ms['depreciation']['n']>=min_changed
            passes=bool(supported and irw is not None and idep is not None and irw>=mat and idep>=mat)
            if passes:wins[g].append(h)
            results.append({'generation':g,'horizon_months':h,'gate_model':gate_model,'origin_count':len(subset),'changed_origin_count':len(changed),'changed_metrics':ms,'improve_rw':irw,'improve_dep':idep,'supported':supported,'passes':passes,'median_gate_neighbor_distance':statistics.median([r[f'{"own" if gate_model.startswith("own") else "transport"}_neighbor_distance_median'] for r in changed if r.get(f'{"own" if gate_model.startswith("own") else "transport"}_neighbor_distance_median') is not None]) if any(r.get(f'{"own" if gate_model.startswith("own") else "transport"}_neighbor_distance_median') is not None for r in changed) else None})
    need=int(c['advancement_gate']['required_supported_winning_horizons_per_generation']); gg={g:len(wins[g])>=need for g in targets}
    classification='MODELABLE_CANDIDATE_CURVE_STATE_FORWARD_PASS' if all(gg.values()) else 'CURVE_STATE_FORWARD_NARROW_GENERATION_ONLY' if any(gg.values()) else 'CURVE_STATE_FORWARD_FAILS_BASELINES' if any(r['supported'] for r in results) else 'INSUFFICIENT_CURVE_STATE_FORWARD_SUPPORT'
    result={'schema':SCHEMA,'research_only':True,'promotion_authority':False,'private_data_loaded':False,'classification':classification,'source':{'dataset':c['dataset'],'archive_receipts':receipts},'counts':{'source_target_rows_before_exact_dedup':source_rows,'exact_dedup_rows':len(seen),'provider_daily_series':len(pdv),'forecast_rows':len(forecasts)},'coverage':{g:{'daily_count':len(daily_by_gen[g]),'monthly_count':len(monthly[g]),'state_month_count':len(states[g]),'first_date':daily_by_gen[g][0]['date'] if daily_by_gen[g] else None,'last_date':daily_by_gen[g][-1]['date'] if daily_by_gen[g] else None} for g in pool},'results':results,'supported_winning_horizons':wins,'generation_gate':gg,'curve_state_contract':c['curve_state_policy'],'parent_gate_note':'This is a frozen direct forward discriminator for parent #128. MODELABLE still requires evidence across more than one generation/time segment and does not create trading authority.'}
    ns.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    compact={'classification':classification,'coverage':result['coverage'],'wins':wins,'gate':gg,'results':[{k:r[k] for k in ['generation','horizon_months','gate_model','origin_count','changed_origin_count','supported','passes','improve_rw','improve_dep','median_gate_neighbor_distance']} | {'gate_mape':r['changed_metrics'][r['gate_model']]['mape'],'rw_mape':r['changed_metrics']['random_walk']['mape'],'dep_mape':r['changed_metrics']['depreciation']['mape']} for r in results]}
    print('P10_CURVE_STATE_FORWARD_TERMINAL='+json.dumps(compact,sort_keys=True)); return 0

if __name__=='__main__':raise SystemExit(main())
