import numpy as np
import pandas as pd

def run_monte_carlo_simulation(trade_returns, n_simulations=1000, n_trades=40):
    if not trade_returns or len(trade_returns) < 5:
        return None, None

    returns_arr = np.array(trade_returns)
    simulated_curves = []
    max_drawdowns = []

    for _ in range(n_simulations):
        sampled_trades = np.random.choice(returns_arr, size=n_trades, replace=True)
        equity = [100.0]
        for ret in sampled_trades:
            delta = equity[-1] * (ret / 100.0) * 0.25
            equity.append(equity[-1] + delta)
        
        simulated_curves.append(equity)
        eq_series = pd.Series(equity)
        dd = (eq_series - eq_series.cummax()) / eq_series.cummax() * 100.0
        max_drawdowns.append(abs(dd.min()))

    curves_df = pd.DataFrame(simulated_curves).T
    mdd_series = pd.Series(max_drawdowns)
    
    stats = {
        "平均期望淨值": round(float(curves_df.iloc[-1].mean()), 2),
        "前 5% 最佳淨值": round(float(curves_df.iloc[-1].quantile(0.95)), 2),
        "後 5% 極端淨值": round(float(curves_df.iloc[-1].quantile(0.05)), 2),
        "95% VaR 最大回撤": round(float(mdd_series.quantile(0.95)), 2),
        "破產機率 (淨值腰斬)": f"{(curves_df.iloc[-1] < 50.0).mean() * 100:.2f}%"
    }
    return curves_df, stats
