#!/usr/bin/env python3
"""P160 Oct-2026 frozen prospective cohort funded NAV, source-only consumer.

No network, broker, source fetching, retuning, portfolio allocation or model promotion.
Input: original Oct-01 frozen P160 observer JSON, 13-name adjusted OHLC CSV,
independently supplied exact common completed-session calendar JSON.
The caller/owner must authenticate issuer/source provenance separately.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pandas as pd

PROGRAM = 'P160_FIXED_P46_P47_COMBINATION'
SOURCE_REF = 'c575e02aba939b283c0aa409d9bc21f000c0762c'
SOURCE_BLOB = '89d8e4c004536310e588623203e8e23e8aac15d9'
FROZEN_OBSERVER_BLOB = '6e6f77a41efdeae2c0928e9c4f1cc0f98ea35737'
SYMBOLS = ('SPY','QQQ','TLT','GLD','DBC','SMH','XBI','ITB','KRE','ITA','IGV','IWM','XRT')
TARGET = {'QQQ':0.25,'SPY':0.25,'IGV':1/6,'IWM':1/6,'XBI':1/6}
MATCHED = {**{s:0.1 for s in ('SPY','QQQ','TLT','GLD','DBC')},
           **{s:0.0625 for s in ('SMH','XBI','ITB','KRE','ITA','IGV','IWM','XRT')}}
COST_BPS = 50.0
# Original frozen P160 source uses ta/tb = 0.5 * L1 weight turnover,
# deducts 50bps * ta/tb from each sleeve monthly return, blends 50/50,
# and leaves its matched/SPY/QQQ comparator returns uncharged.
ENTRY_HALF_L1_TURNOVER_P46 = 0.5
ENTRY_HALF_L1_TURNOVER_P47 = 0.5
ENTRY_COST_FRACTION = (0.5*ENTRY_HALF_L1_TURNOVER_P46 + 0.5*ENTRY_HALF_L1_TURNOVER_P47)*COST_BPS/10000.0
ENTRY_DATE = '2026-10-01'
SIGNAL_DATE = '2026-09-30'
LAST_HOLD_DATE = '2026-10-30'


def git_blob(data:bytes)->str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def require_frozen(frozen:dict, entry_open_utc:str)->None:
    if frozen.get('program_id')!=PROGRAM or frozen.get('signal_month_end')!=SIGNAL_DATE:
        raise ValueError('FROZEN_P160_PROGRAM_OR_SIGNAL_IDENTITY_MISMATCH')
    fi=frozen.get('frozen_identity') or {}
    if fi.get('source_ref')!=SOURCE_REF or fi.get('source_blob_sha')!=SOURCE_BLOB or float(fi.get('primary_cost_bps',-1))!=COST_BPS:
        raise ValueError('FROZEN_P160_SOURCE_OR_COST_MISMATCH')
    if frozen.get('state')!='PROSPECTIVE_ELIGIBLE':
        raise ValueError('FROZEN_P160_PROSPECTIVE_STATE_MISSING')
    a=frozen.get('paper_action') or {}
    for expected, actual, label in [(TARGET,a.get('target_weights'),'target'),(MATCHED,a.get('matched_control_weights'),'matched')]:
        if not isinstance(actual,dict) or set(actual)!=set(expected) or any(abs(float(actual[k])-v)>1e-12 for k,v in expected.items()):
            raise ValueError('FROZEN_P160_'+label.upper()+'_WEIGHTS_MISMATCH')
    created=datetime.fromisoformat(str(frozen['generated_at']).replace('Z','+00:00'))
    opened=datetime.fromisoformat(entry_open_utc.replace('Z','+00:00'))
    if created.tzinfo is None or opened.tzinfo is None or not created < opened:
        raise ValueError('P160_PREENTRY_FIRSTSEEN_NOT_PROVEN_BY_TIMESTAMPS')


def score(frozen:dict, bars:pd.DataFrame, expected_sessions:list[str], *, entry_open_utc:str, adjustment_basis:str, asof_date:str)->dict:
    require_frozen(frozen,entry_open_utc)
    if adjustment_basis!='yahoo_auto_adjust_ohlc':
        raise ValueError('P160_FROZEN_ADJUSTED_PRICE_BASIS_REQUIRED')
    if not expected_sessions or expected_sessions[0]!=ENTRY_DATE or expected_sessions[-1]!=asof_date or len(set(expected_sessions))!=len(expected_sessions):
        raise ValueError('P160_EXACT_COMPLETED_SESSION_CALENDAR_REQUIRED')
    if any(not (ENTRY_DATE<=d<=LAST_HOLD_DATE) for d in expected_sessions) or expected_sessions!=sorted(expected_sessions):
        raise ValueError('P160_UNAUTHORIZED_NEXT_MONTH_OR_NONCHRONOLOGICAL_SESSION')
    if not {'date','symbol','open','close'}.issubset(bars.columns):
        raise ValueError('P160_SOURCE_OHLC_SCHEMA_MISSING')
    q=bars.copy()
    q['date']=pd.to_datetime(q['date'],errors='raise').dt.strftime('%Y-%m-%d')
    q['symbol']=q['symbol'].astype(str)
    if (q['date']>asof_date).any():
        raise ValueError('P160_POST_ASOF_SOURCE_MEMBER_FORBIDDEN')
    q=q.loc[q['date'].isin(expected_sessions)]
    if q.duplicated(['date','symbol']).any():
        raise ValueError('P160_DUPLICATE_DATE_SYMBOL_MEMBER')
    if len(q)!=len(expected_sessions)*len(SYMBOLS):
        raise ValueError('P160_INCOMPLETE_COMMON_SESSION_MEMBER_COUNT')
    for d in expected_sessions:
        if set(q.loc[q.date==d,'symbol'])!=set(SYMBOLS):
            raise ValueError('P160_INCOMPLETE_COMMON_SESSION_SYMBOL_SET')
    for field in ('open','close'):
        q[field]=pd.to_numeric(q[field],errors='raise')
        if q[field].isna().any() or (q[field]<=0).any() or not q[field].map(lambda x:float('-inf')<x<float('inf')).all():
            raise ValueError('P160_NONFINITE_OR_NONPOSITIVE_'+field.upper())
    opens=q.loc[q.date==ENTRY_DATE].set_index('symbol')['open']
    closes=q.pivot(index='date',columns='symbol',values='close').reindex(index=expected_sessions,columns=list(SYMBOLS))
    paths={}
    for name,weights in [('candidate',TARGET),('matched',MATCHED),('SPY',{'SPY':1.0}),('QQQ',{'QQQ':1.0})]:
        # Frozen P160 monthly source computes simple weighted gross return, not
        # self-financing share purchase with proportional fee reduction.
        shares=pd.Series({s:w/float(opens[s]) for s,w in weights.items()})
        gross=(closes.loc[:,list(weights)]*shares).sum(axis=1)
        paths[name]=gross-ENTRY_COST_FRACTION if name=='candidate' else gross
    result={
        'schema':'research.p160_frozen_oct2026_funded_forward_nav_consumer.r1',
        'stage':'PROVISIONAL_FORWARD_ECONOMICS_ONLY__INDEPENDENT_SOURCE_ISSUER_PENDING',
        'program_id':PROGRAM,'signal_month_end':SIGNAL_DATE,'entry_date':ENTRY_DATE,
        'asof_completed_session':asof_date,'observed_sessions':len(expected_sessions),
        'frozen_cost_bps_per_half_l1_turnover':COST_BPS,'initial_candidate_cost_bps':ENTRY_COST_FRACTION*10000,
        'matched_and_opportunity_costs_in_original':False,
        'cost_policy':'PINNED_ORIGINAL_P160_HALF_L1_SLEEVE_RETURN_DEDUCTION',
        'initial_cost_charged':True,'terminal_exit_cost_charged':False,
        'daily_rebalance':False,'next_month_rebalance_executed':False,
        'adjustment_basis':adjustment_basis,
        'frozen_target_weights':TARGET,'frozen_matched_weights':MATCHED,
        'terminal_nav':{k:float(v.iloc[-1]) for k,v in paths.items()},
        'absolute_net_cumulative_bps':{k:float((v.iloc[-1]-1.0)*10000) for k,v in paths.items()},
        'candidate_minus_matched_terminal_nav_bps':float((paths['candidate'].iloc[-1]-paths['matched'].iloc[-1])*10000),
        'candidate_minus_QQQ_terminal_nav_bps':float((paths['candidate'].iloc[-1]-paths['QQQ'].iloc[-1])*10000),
        'candidate_minus_SPY_terminal_nav_bps':float((paths['candidate'].iloc[-1]-paths['SPY'].iloc[-1])*10000),
        'daily_nav':[{ 'session':d,**{k:float(v.loc[d]) for k,v in paths.items()} } for d in expected_sessions],
        'independent_issuer_admitted':False,'alpha_replacement_credit':False,'live_or_allocation_authority':False,
        'no_P47_standalone_reactivation':True,'protected_holdout_read':False
    }
    return result


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--frozen-json',type=Path,required=True)
    ap.add_argument('--adjusted-ohlc-csv',type=Path,required=True)
    ap.add_argument('--sessions-json',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    raw=args.frozen_json.read_bytes()
    if git_blob(raw)!=FROZEN_OBSERVER_BLOB:
        raise SystemExit('P160_ORIGINAL_OCT01_OBSERVER_GIT_BLOB_MISMATCH')
    frozen=json.loads(raw)
    source=args.adjusted_ohlc_csv.read_bytes()
    sessions=json.loads(args.sessions_json.read_text())
    if sessions.get('schema')!='research.p160_independently_admitted_sessions.v1':
        raise SystemExit('P160_SESSION_ISSUER_SCHEMA_NOT_ADMITTED')
    if sessions.get('source_sha256')!=hashlib.sha256(source).hexdigest():
        raise SystemExit('P160_SOURCE_BYTES_SHA_MISMATCH')
    result=score(frozen,pd.read_csv(args.adjusted_ohlc_csv),sessions['sessions'],
                 entry_open_utc=sessions['entry_open_utc'],
                 adjustment_basis=sessions['adjustment_basis'],
                 asof_date=sessions['sessions'][-1])
    result['source_sha256']=hashlib.sha256(source).hexdigest()
    result['frozen_observer_git_blob']=FROZEN_OBSERVER_BLOB
    result['source_issuer_receipt_ref']=sessions.get('issuer_receipt_ref')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'stage':result['stage'],'sessions':result['observed_sessions'],
                      'matched_excess_bps':result['candidate_minus_matched_terminal_nav_bps']}))


if __name__=='__main__':main()
