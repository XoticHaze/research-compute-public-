from __future__ import annotations

"""Born-public Homebuilder rate-context duration consumer.

This adapter does not copy or import private Foundry source or data. It consumes only:
1) the exact public Stage-A adapter/contract already published in TextConverterToolbox,
2) public market prices, and
3) the born-public causal rate-context semantics established by public-compute PR #24.

Scientific question: conditional on the accepted generic Homebuilder admission rule, does
one-session-lagged Homebuilder/rate context improve a LOSO choice between 5- and 60-session
holding horizons versus the same duration learner using generic features only?

External Homebuilder holdouts CCS/MHO/HOV/BZH are never loaded.
"""

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

CAMPAIGN = Path('.campaign')
BASE_PATH = CAMPAIGN / 'stagea.py'
CONTRACT_PATH = CAMPAIGN / 'stagea_contract.json'
OUT = Path('homebuilder_rate_context_duration_public_20260905.json')

HOME = ('DHI', 'LEN', 'PHM', 'NVR', 'TOL', 'MTH', 'KBH', 'LGIH')
EXTERNAL = {'CCS', 'MHO', 'HOV', 'BZH'}
BENCHMARK = 'ITB'
RATE_SYMBOLS = ('XHB', 'TLT', 'IEF', 'SHY')
HORIZONS = (5, 60)
RATE_FEATURES = [
    'itb_ret20_lag1', 'itb_ret60_lag1',
    'xhb_ret20_lag1', 'xhb_ret60_lag1',
    'builder_peer_spread_itb_minus_xhb_20_lag1',
    'tlt_ret20_lag1', 'tlt_ret60_lag1',
    'ief_ret20_lag1', 'ief_ret60_lag1',
    'shy_ret20_lag1', 'shy_ret60_lag1',
    'duration_pressure_20_lag1', 'long_duration_pressure_20_lag1',
    'curve_proxy_ief_minus_shy_20_lag1',
    'curve_proxy_tlt_minus_ief_20_lag1',
]
MIN_LOSO_ROWS = 1000


def load_base():
    spec = importlib.util.spec_from_file_location('public_stagea', BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot load public Stage-A adapter')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model() -> Pipeline:
    return Pipeline([
        ('scale', StandardScaler()),
        ('ridge', Ridge(alpha=10.0)),
    ])


def check_stagea_parity(base, contract: dict) -> dict:
    """Use the established Public Foundry replay-drift classification.

    Exact historical aggregate identity is recorded but not required when live-source
    replay preserves the accepted family pass-count decisions. A pass-count change is a
    scientific parity break and blocks the downstream duration consumer.
    """
    parity = contract['parity_control']
    result = base._evaluate_matrix(parity['families'], parity['common_cutoff'])
    expected = parity['accepted_family_summary']
    families = {}
    exact = True
    decisions_match = True
    for family, exp in expected.items():
        got = result['family_summary'][family]
        state_delta = int(got['aggregate_primary_states']) - int(exp['aggregate_primary_states'])
        net_delta = float(got['aggregate_stock_net25_mean_bps']) - float(exp['aggregate_stock_net25_mean_bps'])
        rel_delta = float(got['aggregate_stock_after25_minus_sector_etf_mean_bps']) - float(exp['aggregate_stock_after25_minus_sector_etf_mean_bps'])
        sub_delta = float(got['aggregate_sector_substitution50_mean_bps']) - float(exp['aggregate_sector_substitution50_mean_bps'])
        pass_count_match = int(got['passing_symbols']) == int(exp['passing_symbols'])
        family_exact = bool(
            pass_count_match
            and state_delta == 0
            and abs(net_delta) <= 1e-8
            and abs(rel_delta) <= 1e-8
            and abs(sub_delta) <= 1e-8
        )
        exact = exact and family_exact
        decisions_match = decisions_match and pass_count_match
        families[family] = {
            'passing_symbols_actual': int(got['passing_symbols']),
            'passing_symbols_expected': int(exp['passing_symbols']),
            'passing_symbols_match': pass_count_match,
            'state_count_delta': state_delta,
            'absolute_bps_delta': net_delta,
            'matched_etf_excess_bps_delta': rel_delta,
            'substitution50_bps_delta': sub_delta,
            'exact_parity': family_exact,
        }
    classification = 'EXACT_PARITY' if exact else (
        'LIVE_SOURCE_REPLAY_DRIFT_WITH_DECISION_PARITY' if decisions_match else 'SCIENTIFIC_PARITY_BREAK'
    )
    if not decisions_match:
        raise RuntimeError(f'Stage-A scientific parity break: {families}')
    return {
        'passed': True,
        'classification': classification,
        'accepted_family_decisions_match': decisions_match,
        'exact_historical_parity': exact,
        'family_deltas': families,
        'result': result,
    }


def rate_context(prices: dict[str, pd.Series], calendar: pd.DatetimeIndex) -> pd.DataFrame:
    out = pd.DataFrame(index=calendar)
    for symbol in (BENCHMARK, *RATE_SYMBOLS):
        key = symbol.lower()
        out[f'{key}_ret20_lag1'] = prices[symbol].pct_change(20).shift(1)
        out[f'{key}_ret60_lag1'] = prices[symbol].pct_change(60).shift(1)
    out['duration_pressure_20_lag1'] = (-prices['IEF'].pct_change(20)).shift(1)
    out['long_duration_pressure_20_lag1'] = (-prices['TLT'].pct_change(20)).shift(1)
    out['curve_proxy_ief_minus_shy_20_lag1'] = (
        prices['IEF'].pct_change(20) - prices['SHY'].pct_change(20)
    ).shift(1)
    out['curve_proxy_tlt_minus_ief_20_lag1'] = (
        prices['TLT'].pct_change(20) - prices['IEF'].pct_change(20)
    ).shift(1)
    out['builder_peer_spread_itb_minus_xhb_20_lag1'] = (
        prices[BENCHMARK].pct_change(20) - prices['XHB'].pct_change(20)
    ).shift(1)
    return out


def duration_frame(base, data: dict[str, pd.DataFrame], context: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows = []
    target_name = f'target_{horizon}_per_session'
    for symbol in HOME:
        df = data[symbol]
        target = (
            (df.price.shift(-(base.DELAY + horizon)) / df.price.shift(-base.DELAY) - 1.0) * 10000.0
            - base.COST_BPS
        ) / float(horizon)
        part = df[base.FEATURES].copy()
        part[RATE_FEATURES] = context[RATE_FEATURES].to_numpy()
        part['symbol'] = symbol
        part['signal_i'] = np.arange(len(df), dtype=int)
        part[target_name] = target
        rows.append(part)
    return pd.concat(rows, ignore_index=True).replace([np.inf, -np.inf], np.nan)


def fit_loso(base, frame: pd.DataFrame, held_symbol: str, horizon: int, start: int, columns: list[str]):
    purge = max(int(base.PURGE), int(base.DELAY + horizon))
    target = f'target_{horizon}_per_session'
    train = frame[(frame.symbol != held_symbol) & (frame.signal_i < start - purge)].dropna(
        subset=[*columns, target]
    )
    if len(train) < MIN_LOSO_ROWS:
        raise RuntimeError(f'{held_symbol} h{horizon}: insufficient LOSO rows={len(train)}')
    m = model()
    m.fit(train[columns].to_numpy(float), train[target].to_numpy(float))
    return m, int(len(train))


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {'trades': 0, 'mean_net25_bps': None, 'mean_matched_itb_excess_bps': None, 'mean_hold_sessions': None, 'h5_share': None}
    return {
        'trades': len(rows),
        'mean_net25_bps': float(np.mean([r['stock_net25_bps'] for r in rows])),
        'mean_matched_itb_excess_bps': float(np.mean([r['matched_itb_excess_bps'] for r in rows])),
        'mean_hold_sessions': float(np.mean([r['horizon'] for r in rows])),
        'h5_share': float(np.mean([r['horizon'] == 5 for r in rows])),
    }


def grouped_mean(rows: list[dict], key: str) -> dict:
    groups: dict[object, list[float]] = {}
    for row in rows:
        groups.setdefault(row[key], []).append(float(row['matched_itb_excess_bps']))
    return {str(k): float(np.mean(v)) for k, v in groups.items()}


def concentration(challenger: list[dict], control: list[dict]) -> dict:
    cs, bs = grouped_mean(challenger, 'symbol'), grouped_mean(control, 'symbol')
    symbol_delta = {s: cs.get(s, 0.0) - bs.get(s, 0.0) for s in HOME}
    pos = [v for v in symbol_delta.values() if v > 0]
    symbol_share = None if not pos else float(max(pos) / sum(pos))

    cy, by = grouped_mean(challenger, 'year'), grouped_mean(control, 'year')
    years = sorted(set(cy) | set(by))
    year_delta = {y: cy.get(y, 0.0) - by.get(y, 0.0) for y in years}
    ypos = [v for v in year_delta.values() if v > 0]
    year_share = None if not ypos else float(max(ypos) / sum(ypos))
    return {
        'max_positive_symbol_share': symbol_share,
        'max_positive_year_share': year_share,
        'symbol_mean_excess_delta_bps': symbol_delta,
        'year_mean_excess_delta_bps': year_delta,
    }


def main() -> None:
    if set(HOME) & EXTERNAL:
        raise RuntimeError('external Homebuilder holdouts entered development universe')
    base = load_base()
    contract = json.loads(CONTRACT_PATH.read_text())
    parity = check_stagea_parity(base, contract)

    selection = tuple(dict.fromkeys((*base.TRAIN, *HOME, 'QQQ', BENCHMARK, *RATE_SYMBOLS)))
    raw = {symbol: base._load(symbol) for symbol in selection}
    cutoff = min(frame.iloc[-1].timestamp for frame in raw.values())
    sets = [set(frame.loc[frame.timestamp <= cutoff, 'timestamp']) for frame in raw.values()]
    calendar = pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(calendar) < 3000:
        raise RuntimeError(f'insufficient common model calendar={len(calendar)}')
    prices = {symbol: raw[symbol].set_index('timestamp').price.reindex(calendar) for symbol in raw}
    if any(series.isna().any() for series in prices.values()):
        raise RuntimeError('missing common-calendar price')

    modeled = (*base.TRAIN, *HOME)
    data = base._engineer(prices, calendar, modeled)
    context = rate_context(prices, calendar)
    folds = base._global_folds(len(calendar))
    train_states = base._state_frame(base.TRAIN, data, folds)
    frames = {h: duration_frame(base, data, context, h) for h in HORIZONS}

    generic = list(base.FEATURES)
    full = [*generic, *RATE_FEATURES]
    all_rows = {'control': [], 'rate_context': []}
    errors = {'control': [], 'rate_context': []}
    fold_results = []
    loso_support = []

    for fold in range(base.EVAL_FIRST_FOLD, base.FOLDS + 1):
        start, stop = folds[fold - 1]
        train = train_states[train_states.signal_i < start - base.PURGE]
        if len(train) < 1000:
            raise RuntimeError(f'fold {fold}: insufficient admission training rows={len(train)}')
        admission_model = base._fit(train)
        fold_rows = {'control': [], 'rate_context': []}
        fold_errors = {'control': [], 'rate_context': []}

        for symbol in HOME:
            threshold_support = data[symbol].iloc[: start - base.PURGE].mom20.dropna()
            if len(threshold_support) < 250:
                raise RuntimeError(f'{symbol} fold {fold}: insufficient momentum support')
            threshold = float(threshold_support.quantile(1.0 - base.TAIL))

            models = {'control': {}, 'rate_context': {}}
            for h in HORIZONS:
                models['control'][h], n0 = fit_loso(base, frames[h], symbol, h, start, generic)
                models['rate_context'][h], n1 = fit_loso(base, frames[h], symbol, h, start, full)
                loso_support.append({'fold': fold, 'symbol': symbol, 'horizon': h, 'control_rows': n0, 'rate_context_rows': n1})

            safe_stop = max(start, stop - (base.DELAY + max(HORIZONS)))
            next_exec = {'control': -1, 'rate_context': -1}
            for signal_i in range(start, safe_stop):
                generic_values = data[symbol].loc[signal_i, generic].to_numpy(float)
                rate_values = context.iloc[signal_i][RATE_FEATURES].to_numpy(float)
                if not np.isfinite(generic_values).all() or not np.isfinite(rate_values).all():
                    continue
                admission = float(admission_model.predict(np.asarray([generic_values], float))[0])
                if admission <= 0.0 or float(data[symbol].at[signal_i, 'mom20']) >= threshold:
                    continue

                feature_values = {
                    'control': generic_values,
                    'rate_context': np.concatenate([generic_values, rate_values]),
                }
                for arm in ('control', 'rate_context'):
                    predictions = {}
                    for h in HORIZONS:
                        pred = float(models[arm][h].predict(np.asarray([feature_values[arm]], float))[0])
                        predictions[h] = pred
                        target_col = f'target_{h}_per_session'
                        hit = frames[h][(frames[h].symbol == symbol) & (frames[h].signal_i == signal_i)][target_col]
                        if not hit.empty:
                            actual = float(hit.iloc[0])
                            if np.isfinite(actual):
                                fold_errors[arm].append(abs(pred - actual))
                                errors[arm].append(abs(pred - actual))
                    chosen_h = max(HORIZONS, key=lambda h: predictions[h])
                    exec_i = signal_i + base.DELAY
                    exit_i = exec_i + chosen_h
                    if exec_i < next_exec[arm]:
                        continue
                    stock_gross = float(prices[symbol].iloc[exit_i] / prices[symbol].iloc[exec_i] - 1.0) * 10000.0
                    itb_gross = float(prices[BENCHMARK].iloc[exit_i] / prices[BENCHMARK].iloc[exec_i] - 1.0) * 10000.0
                    record = {
                        'fold': fold,
                        'symbol': symbol,
                        'signal_date': calendar[signal_i].isoformat(),
                        'entry_date': calendar[exec_i].isoformat(),
                        'year': int(calendar[exec_i].year),
                        'horizon': int(chosen_h),
                        'predicted_per_session_bps': predictions[chosen_h],
                        'stock_net25_bps': stock_gross - base.COST_BPS,
                        'matched_itb_excess_bps': stock_gross - base.COST_BPS - itb_gross,
                    }
                    fold_rows[arm].append(record)
                    all_rows[arm].append(record)
                    next_exec[arm] = exit_i

        c = summarize(fold_rows['control'])
        r = summarize(fold_rows['rate_context'])
        c_mae = None if not fold_errors['control'] else float(np.mean(fold_errors['control']))
        r_mae = None if not fold_errors['rate_context'] else float(np.mean(fold_errors['rate_context']))
        economic_improved = bool(
            c['mean_net25_bps'] is not None and r['mean_net25_bps'] is not None
            and r['mean_net25_bps'] > c['mean_net25_bps']
            and r['mean_matched_itb_excess_bps'] > c['mean_matched_itb_excess_bps']
        )
        mae_improved = bool(c_mae is not None and r_mae is not None and r_mae < c_mae)
        fold_results.append({
            'fold': fold,
            'control': c,
            'rate_context': r,
            'control_duration_mae_bps_per_session': c_mae,
            'rate_context_duration_mae_bps_per_session': r_mae,
            'economic_improved': economic_improved,
            'mae_improved': mae_improved,
        })

    control = summarize(all_rows['control'])
    challenger = summarize(all_rows['rate_context'])
    control_mae = float(np.mean(errors['control']))
    challenger_mae = float(np.mean(errors['rate_context']))
    econ_folds = sum(int(row['economic_improved']) for row in fold_results)
    mae_folds = sum(int(row['mae_improved']) for row in fold_results)
    conc = concentration(all_rows['rate_context'], all_rows['control'])
    concentration_pass = bool(
        conc['max_positive_symbol_share'] is not None
        and conc['max_positive_year_share'] is not None
        and conc['max_positive_symbol_share'] <= 0.50
        and conc['max_positive_year_share'] <= 0.50
    )
    gate = bool(
        challenger_mae < control_mae
        and challenger['mean_net25_bps'] > control['mean_net25_bps']
        and challenger['mean_matched_itb_excess_bps'] > control['mean_matched_itb_excess_bps']
        and econ_folds >= 3
        and mae_folds >= 3
        and concentration_pass
    )

    output = {
        'schema': 'public_compute.homebuilder_rate_context_duration.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS',
        'decision': 'PASS_RATE_CONTEXT_DURATION_DEVELOPMENT' if gate else 'REJECT_RATE_CONTEXT_DURATION_DEVELOPMENT',
        'scientific_authority': {'repo': 'XoticHaze/research-foundry', 'pr': 278},
        'public_foundry_method': {
            'private_source_or_data_transferred': False,
            'public_stagea_blob_sha': '9f7f802469dc6a33abd3431295d5232ebc4289c5',
            'public_stagea_commit': '2d8995ba66502a4de25c64c1c32a67e132b05522',
            'rate_context_source': 'born-public PR24 semantics',
        },
        'parity': parity,
        'selection_calendar': {'rows': len(calendar), 'first': calendar[0].isoformat(), 'last': calendar[-1].isoformat(), 'common_cutoff': cutoff.isoformat()},
        'development_universe': list(HOME),
        'external_holdouts_loaded': False,
        'admission': 'exact public Stage-A generic Ridge>0 plus frozen prior-history top30 momentum exclusion',
        'duration': {'horizons': list(HORIZONS), 'learner': 'StandardScaler + Ridge(alpha=10)', 'loso_target_symbol_excluded': True},
        'control_features': generic,
        'challenger_added_features': RATE_FEATURES,
        'control': control,
        'rate_context': challenger,
        'control_duration_mae_bps_per_session': control_mae,
        'rate_context_duration_mae_bps_per_session': challenger_mae,
        'economic_improvement_folds': econ_folds,
        'mae_improvement_folds': mae_folds,
        'concentration': conc,
        'concentration_pass': concentration_pass,
        'folds': fold_results,
        'loso_support': loso_support,
        'gate': {
            'lower_duration_mae': challenger_mae < control_mae,
            'higher_net_economics': challenger['mean_net25_bps'] > control['mean_net25_bps'],
            'higher_matched_itb_economics': challenger['mean_matched_itb_excess_bps'] > control['mean_matched_itb_excess_bps'],
            'economic_improvement_folds_at_least_3_of_5': econ_folds >= 3,
            'mae_improvement_folds_at_least_3_of_5': mae_folds >= 3,
            'positive_increment_not_overconcentrated': concentration_pass,
        },
        'next_boundary': 'a development PASS may justify a separately frozen prospective duration observer; admission remains unchanged',
        'research_only': True,
        'promotion_authority': False,
        'runtime_mutation': False,
        'broker_action': False,
        'live_trading_change': False,
    }
    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print('HOMEBUILDER_RATE_CONTEXT_DURATION=' + json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    main()
