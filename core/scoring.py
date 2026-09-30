import numpy as np

def score_single_stock(df_slice, bm_slice, clean_code):
    if len(df_slice) < 60:
        return None
    latest = df_slice.iloc[-1]
    prev = df_slice.iloc[-2]

    try:
        p_num = int(clean_code)
        if (2800 <= p_num <= 2899) or (2600 <= p_num <= 2699) or (1100 <= p_num <= 1110):
            return None
    except Exception:
        pass

    entry_p = float(latest['Close'])
    turnover_ma5_twd = float(df_slice['Turnover_MA5'].iloc[-1])
    cur_vol_lots = float(latest['Volume']) / 1000.0
    amp20 = float(df_slice['Amplitude20'].iloc[-1])

    if entry_p <= 35.0 or turnover_ma5_twd < 150000000.0 or amp20 < 8.0:
        return None

    if not (latest['Close'] > latest['MA20'] and latest['Close'] > latest['MA60']):
        return None
    if latest['MA20'] < df_slice['MA20'].iloc[-5] * 0.995:
        return None

    bias5 = float(latest['Bias5'])
    bias20 = float(latest['Bias20'])
    if bias5 > 3.5 or bias20 > 10.0:
        return None

    bw_min = df_slice['BB_Width'].tail(30).min()
    vcp_tight = (latest['BB_Width'] <= bw_min * 1.35)
    amp_tight = (df_slice['High'].tail(5).max() - df_slice['Low'].tail(5).min()) / entry_p * 100 < 5.0
    vdu_dry = (latest['Volume'] < df_slice['Vol_MA20'].iloc[-1] * 0.6)
    
    s_vcp = 0
    if vcp_tight: s_vcp += 10
    if amp_tight: s_vcp += 5
    if vdu_dry or latest['Volume'] > df_slice['Vol_MA5'].iloc[-1] * 1.3: s_vcp += 10

    poc_p = float(latest['VP_POC'])
    s_vpvr = 0
    if entry_p >= poc_p: s_vpvr += 12
    if entry_p > latest['MA20']: s_vpvr += 8

    s_trend = 0
    if latest['Close'] > latest['MA20'] > latest['MA60']: s_trend += 10
    if latest['EMA10'] > latest['MA20']: s_trend += 5
    if (df_slice['High'].tail(60).max() - entry_p) / entry_p <= 0.08: s_trend += 5

    s_mom = 0
    if 50 <= latest['K'] <= 82: s_mom += 3
    if latest['MACD_Hist'] > 0: s_mom += 3
    if 52 <= latest['RSI'] <= 70: s_mom += 4

    tech_score_75 = s_vcp + s_vpvr + s_trend + s_mom

    chip_acc = float(latest['Chip_Accumulation'])
    score_major = 10 if chip_acc > 0.25 else (8 if chip_acc > 0.10 else (6 if chip_acc > 0 else 4))
    pts_major = (score_major / 10.0) * 13.0

    stock_ret20 = (latest['Close'] - df_slice['Close'].iloc[-20]) / df_slice['Close'].iloc[-20] * 100
    bm_ret20 = 0.0
    if len(bm_slice) >= 20:
        bm_ret20 = (bm_slice['Close'].iloc[-1] - bm_slice['Close'].iloc[-20]) / bm_slice['Close'].iloc[-20] * 100
    rs_alpha = stock_ret20 - bm_ret20

    score_foreign = 10 if rs_alpha > 7.0 else (8 if rs_alpha > 2.0 else 5)
    pts_foreign = (score_foreign / 10.0) * 5.0

    score_trust = 9 if (latest['Volume'] > df_slice['Vol_MA5'].iloc[-1] * 1.2 and latest['Close'] > latest['Open']) else 5
    score_whale = 9 if vcp_tight else 5
    pts_trust_whale = ((score_trust + score_whale) / 20.0) * 2.0

    chips_score_20 = pts_major + pts_foreign + pts_trust_whale
    fund_score_5 = 4.0 if latest['Close'] > latest['MA60'] else 2.0

    total_score = round(tech_score_75 + chips_score_20 + fund_score_5, 1)

    k_val = float(latest['K'])
    k_dir = "▲" if latest['K'] >= prev['K'] else "▼"

    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
    atr_pct = float(latest['ATR_Pct'])
    atr_multiplier = 2.0 if atr_pct > 3.2 else (1.5 if atr_pct < 1.8 else 1.8)

    atr_stop = entry_p - atr_multiplier * atr_v
    struct_stop = float(df_slice['Low'].tail(5).min()) * 0.99
    final_stop = max(struct_stop, atr_stop)
    risk_pct = (entry_p - final_stop) / entry_p * 100

    if risk_pct < 4.0: final_stop = entry_p * 0.95; risk_pct = 5.0
    elif risk_pct > 8.0: final_stop = entry_p * 0.92; risk_pct = 8.0

    return {
        "total_score": total_score,
        "tech_score_75": tech_score_75,
        "score_major": score_major,
        "score_foreign": score_foreign,
        "score_trust": score_trust,
        "score_whale": score_whale,
        "k_val": k_val,
        "k_dir": k_dir,
        "close": entry_p,
        "pct": (latest['Close'] - prev['Close']) / prev['Close'] * 100,
        "volume_lots": cur_vol_lots,
        "turnover_yi": turnover_ma5_twd / 100000000.0,
        "bias5": bias5,
        "bias20": bias20,
        "ma5": float(latest['MA5']),
        "ma10": float(latest['MA10']),
        "ma20": float(latest['MA20']),
        "ma60": float(latest['MA60']),
        "stop_loss": final_stop,
        "risk_pct": risk_pct,
        "amp20": amp20,
        "score_vcp": s_vcp,
        "is_eligible": True
    }
