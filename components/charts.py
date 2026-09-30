import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def plot_candlestick_with_vpvr(df, stock_title, stop_loss_price=None, tp_price=None):
    sub_df = df.tail(45).copy()
    date_cats = sub_df.index.strftime('%m/%d').tolist()

    fig = make_subplots(
        rows=1, cols=2, shared_yaxes=True,
        column_widths=[0.82, 0.18], horizontal_spacing=0.02,
        subplot_titles=[f"{stock_title} 連續日K與關鍵點位", "VPVR 籌碼分佈"]
    )

    fig.add_trace(go.Candlestick(
        x=date_cats, open=sub_df['Open'], high=sub_df['High'],
        low=sub_df['Low'], close=sub_df['Close'],
        name="K線", increasing_line_color='#ef4444', decreasing_line_color='#22c55e'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=date_cats, y=sub_df['MA10'], line=dict(color='#f59e0b', width=1.5), name="10MA"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=date_cats, y=sub_df['MA20'], line=dict(color='#3b82f6', width=1.5), name="20MA"
    ), row=1, col=1)

    if stop_loss_price:
        fig.add_hline(y=stop_loss_price, line_dash="dash", line_color="#22c55e",
                      annotation_text=f"停損 {stop_loss_price:.2f}", row=1, col=1)
    if tp_price:
        fig.add_hline(y=tp_price, line_dash="dash", line_color="#ef4444",
                      annotation_text=f"目標 {tp_price:.2f}", row=1, col=1)

    p_min, p_max = sub_df['Low'].min(), sub_df['High'].max()
    bins = np.linspace(p_min, p_max, 15)
    bin_idx = np.digitize(sub_df['Close'], bins)
    vol_bins = np.zeros(len(bins))
    for b, v in zip(bin_idx, sub_df['Volume']):
        if 0 <= b < len(vol_bins): vol_bins[b] += v

    poc_idx = np.argmax(vol_bins)
    bar_colors = ['#38bdf8' if idx != poc_idx else '#f59e0b' for idx in range(len(bins))]

    fig.add_trace(go.Bar(
        x=vol_bins, y=bins, orientation='h',
        marker=dict(color=bar_colors), name="籌碼峰"
    ), row=1, col=2)

    fig.update_layout(
        height=480,
        xaxis=dict(type='category'),
        xaxis2=dict(showticklabels=False),
        paper_bgcolor="#080c14",
        plot_bgcolor="#080c14",
        font=dict(color="#ffffff"),
        showlegend=False,
        margin=dict(l=20, r=20, t=30, b=20)
    )
    return fig
