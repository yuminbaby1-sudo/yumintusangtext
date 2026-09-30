import numpy as np
import pandas as pd

def run_grid_search_optimization(stock_dfs, benchmark_df, backtest_days=35, score_func=None):
    atr_mults = [1.5, 1.8, 2.0, 2.5, 3.0]
    holding_windows = [5, 8, 10, 15, 20]
    results = []
    
    sample_df = list(stock_dfs.values())[0][1]
    dates = sample_df.index[-backtest_days-20:-20]

    for h_win in holding_windows:
        for a_mult in atr_mults:
            trade_pnls = []
            active_holdings = {}
            for d in dates:
                active_holdings = {k: v for k, v in active_holdings.items() if v > d}
                if len(active_holdings) >= 4: continue

                candidates = []
                for name, (clean_code, df_item) in stock_dfs.items():
                    if name in active_holdings or d not in df_item.index: continue
                    pos = df_item.index.get_loc(d)
                    if pos >= 60:
                        res = score_func(df_item.iloc[:pos+1], benchmark_df.loc[:d], clean_code)
                        if res and res.get('is_eligible'):
                            candidates.append((res['total_score'], name, df_item, res['close'], res['stop_loss']))

                if not candidates: continue
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, p_name, full_df, entry_p, stop_l = candidates[0]
                
                f_idx = full_df.index.get_loc(d)
                f_window = full_df.iloc[f_idx+1 : f_idx+1+h_win]
                if f_window.empty: continue

                risk = entry_p - stop_l
                tp_price = entry_p + a_mult * risk
                exit_p = f_window['Close'].iloc[-1]

                for _, row in f_window.iterrows():
                    if row['Low'] <= stop_l:
                        exit_p = stop_l
                        break
                    if row['High'] >= tp_price:
                        exit_p = tp_price
                        break

                net_ret = ((exit_p - entry_p) / entry_p * 100) - 0.45
                trade_pnls.append(net_ret)
                active_holdings[p_name] = f_window.index[-1]

            if trade_pnls:
                wins = [p for p in trade_pnls if p > 0]
                losses = [p for p in trade_pnls if p <= 0]
                w_rate = (len(wins) / len(trade_pnls)) * 100.0
                pf = (sum(wins) / (abs(sum(losses)) + 1e-9)) if losses else 9.9
                results.append({
                    "ATR停利倍數": f"{a_mult:.1f}R",
                    "持股天數上限": f"{h_win} 天",
                    "總交易筆數": len(trade_pnls),
                    "實戰勝率%": round(w_rate, 1),
                    "賺賠比(PF)": round(pf, 2),
                    "累計淨利%": round(sum(trade_pnls), 2)
                })

    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values(by=["賺賠比(PF)", "實戰勝率%"], ascending=False)
    return df_res
