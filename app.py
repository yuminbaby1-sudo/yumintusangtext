import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="專業台股技術分析系統", layout="wide", initial_sidebar_state="expanded")

# --- 指標運算函式 ---
def calculate_indicators(df):
    # 均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

    # KD (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    rsv = ((df['Close'] - low_min) / (high_max - low_min + 1e-9)) * 100
    rsv = rsv.fillna(50)

    k_list, d_list = [], []
    k, d = 50.0, 50.0
    for r in rsv:
        k = (2/3) * k + (1/3) * r
        d = (2/3) * d + (1/3) * k
        k_list.append(k)
        d_list.append(d)
    df['K'] = k_list
    df['D'] = d_list

    # MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    return df

# --- 側邊欄 ---
st.sidebar.title("📈 操盤分析控制台")
preset_stocks = {
    "台積電 (2330)": "2330.TW",
    "聯發科 (2454)": "2454.TW",
    "鴻海 (2317)": "2317.TW",
    "元大台灣50 (0050)": "0050.TW",
    "長榮 (2603)": "2603.TW",
    "自訂輸入": "CUSTOM"
}
selected_preset = st.sidebar.selectbox("常用標的", list(preset_stocks.keys()))
if preset_stocks[selected_preset] == "CUSTOM":
    stock_code = st.sidebar.text_input("輸入股票代號 (例: 2454.TW / 3293.TWO)", value="2330.TW")
else:
    stock_code = preset_stocks[selected_preset]

period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2)
show_ma = st.sidebar.multiselect("均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA20", "MA60"])
indicator_choice = st.sidebar.radio("副圖技術指標", ["KD 指標 (9,3,3)", "MACD (12,26,9)", "兩者皆顯示"])

# --- 抓取資料 ---
@st.cache_data(ttl=300)
def load_data(ticker, period):
    return yf.download(ticker, period=period)

with st.spinner("盤勢資料與指標運算中..."):
    df = load_data(stock_code, period_map[selected_period])

if df.empty:
    st.error("查無此股票資料，上市請加 .TW，上櫃請加 .TWO")
else:
    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
        df.columns = df.columns.get_level_values(0)

    df = calculate_indicators(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    price_change = latest['Close'] - prev['Close']
    pct_change = (price_change / prev['Close']) * 100

    # 頂部即時指標
    st.header(f"{stock_code} 專業技術分析看板")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("最新收盤價", f"{latest['Close']:.2f} 元", f"{price_change:+.2f} ({pct_change:+.2f}%)")
    col2.metric("單日最高 / 最低", f"{latest['High']:.2f} / {latest['Low']:.2f}")
    col3.metric("區間最高價", f"{df['High'].max():.2f} 元")
    col4.metric("區間最低價", f"{df['Low'].min():.2f} 元")
    col5.metric("今日成交量", f"{int(latest['Volume']):,} 股")

    st.markdown("---")

    # --- 大神技術面訊號診斷系統 ---
    st.subheader("💡 技術派訊號自動診斷")
    signals = []

    # 1. 趨勢模板：多頭排列判定 (Minervini / Weinstein)
    if latest['MA5'] > latest['MA20'] > latest['MA60'] and latest['MA20'] > df['MA20'].iloc[-5]:
        signals.append(("success", "🔥【均線多頭排列】5MA > 20MA > 60MA 且月線上彎，屬於強勢多方攻擊架構。"))
    elif latest['MA5'] < latest['MA20'] < latest['MA60']:
        signals.append(("error", "⚠️【均線空頭排列】短期均線全數下彎，空方主導，建議保守勿摸底。"))

    # 2. 量價關係：帶量突破
    if latest['Volume'] > latest['Vol_MA5'] * 1.5 and pct_change > 2.0:
        signals.append(("success", f"⚡【帶量攻擊訊號】今日成交量放大至 5 日均量的 {latest['Volume']/latest['Vol_MA5']:.1f} 倍且漲幅 > 2%，主力資金表態。"))
    elif latest['Volume'] < latest['Vol_MA5'] * 0.6 and pct_change < 0:
        signals.append(("info", "💤【量縮回檔整理】下跌過程中量能急縮，籌碼未見明顯渙散，留意支撐測試。"))

    # 3. KD 轉折 / 鈍化
    if prev['K'] < prev['D'] and latest['K'] >= latest['D'] and latest['K'] < 50:
        signals.append(("success", "📈【低檔黃金交叉】KD 指標在 50 以下出現黃金交叉，短線反彈動能醞釀。"))
    elif latest['K'] > 80 and latest['D'] > 80:
        signals.append(("warning", "🚀【KD 高檔鈍化】指標進入極強單邊走勢，強者恆強，若跌破 80 需防回檔。"))

    # 4. MACD 零軸轉強
    if latest['DIF'] > 0 and latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']:
        signals.append(("success", "🎯【MACD 零軸上多方增強】紅柱持續放大，中多動能延續。"))

    if signals:
        for level, msg in signals:
            if level == "success":
                st.success(msg)
            elif level == "warning":
                st.warning(msg)
            elif level == "error":
                st.error(msg)
            else:
                st.info(msg)
    else:
        st.write("目前盤勢處於區間震盪整理，未出現明顯關鍵突破或反轉訊號。")

    st.markdown("---")

    # --- 繪製多圖表 ---
    if indicator_choice == "兩者皆顯示":
        rows, row_heights = 4, [0.5, 0.16, 0.17, 0.17]
        subplot_titles = ("K線與均線走勢", "成交量 (Volume)", "KD 指標", "MACD 指標")
    else:
        rows, row_heights = 3, [0.55, 0.22, 0.23]
        subplot_titles = ("K線與均線走勢", "成交量 (Volume)", indicator_choice)

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights, subplot_titles=subplot_titles)

    # 主圖 K 線 (紅漲綠跌)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
    ), row=1, col=1)

    ma_colors = {'MA5': '#f39c12', 'MA10': '#9b59b6', 'MA20': '#2980b9', 'MA60': '#16a085'}
    for ma in show_ma:
        fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode='lines', name=ma, line=dict(color=ma_colors[ma], width=1.5)), row=1, col=1)

    # 成交量
    vol_colors = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Vol_MA5'], line=dict(color='orange', width=1.2), name="量5MA"), row=2, col=1)

    # 副圖指標
    curr_row = 3
    if indicator_choice in ["KD 指標 (9,3,3)", "兩者皆顯示"]:
        fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='#e74c3c', width=1.5), name="K"), row=curr_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='#3498db', width=1.5), name="D"), row=curr_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="gray", row=curr_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="gray", row=curr_row, col=1)
        curr_row += 1

    if indicator_choice in ["MACD (12,26,9)", "兩者皆顯示"]:
        fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='#2980b9', width=1.3), name="DIF"), row=curr_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#e67e22', width=1.3), name="MACD"), row=curr_row, col=1)
        hist_colors = ['#eb4034' if val >= 0 else '#0da651' for val in df['MACD_Hist']]
        fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=hist_colors, name="MACD柱"), row=curr_row, col=1)

    fig.update_layout(height=850, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📋 近期歷史數據明細"):
        st.dataframe(df[['Open', 'High', 'Low', 'Close', 'Volume', 'MA5', 'MA20', 'K', 'D', 'MACD_Hist']].tail(20).sort_index(ascending=False).style.format("{:.2f}"))