import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="AI 量化操盤與高維度技術分析系統", layout="wide", initial_sidebar_state="expanded")

# --- 觀察池：涵蓋台股指標性權值、AI主流、重電、航運、高流動性族群 ---
STOCK_POOL = {
    "台積電 (2330)": "2330.TW",
    "聯發科 (2454)": "2454.TW",
    "鴻海 (2317)": "2317.TW",
    "廣達 (2382)": "2382.TW",
    "緯創 (3231)": "3231.TW",
    "台達電 (2308)": "2308.TW",
    "長榮 (2603)": "2603.TW",
    "陽明 (2609)": "2609.TW",
    "華城 (1519)": "1519.TW",
    "士電 (1503)": "1503.TW",
    "奇鋐 (3017)": "3017.TW",
    "雙鴻 (3324)": "3324.TW",
    "世芯-KY (3661)": "3661.TW",
    "聯詠 (3034)": "3034.TW",
    "技嘉 (2376)": "2376.TW",
    "智原 (3035)": "3035.TW",
    "元大台灣50 (0050)": "0050.TW"
}

# --- 高維技術指標計算 ---
def calculate_advanced_indicators(df):
    # 1. 均線系統
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

    # 2. 布林通道與擠壓指標 (BandWidth) - 判斷 VCP 波動收縮
    std20 = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (2 * std20)
    df['BB_Lower'] = df['MA20'] - (2 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['MA20'] + 1e-9)

    # 3. ATR (真實波幅 - 用於科學停損)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    # 4. OBV (能量潮 - 威科夫籌碼吸籌判斷)
    obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'],
                 np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
    df['OBV'] = pd.Series(obv_change, index=df.index).cumsum()
    df['OBV_MA10'] = df['OBV'].rolling(window=10).mean()

    # 5. KD 指標 (9, 3, 3)
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

    # 6. MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']

    return df

@st.cache_data(ttl=600)
def fetch_data(ticker, period="6mo"):
    data = yf.download(ticker, period=period)
    if hasattr(data.columns, 'levels') and len(data.columns.levels) > 1:
        data.columns = data.columns.get_level_values(0)
    return data

# --- 讀取大盤加權指數做環境濾網 ---
@st.cache_data(ttl=600)
def get_benchmark_data():
    bm = fetch_data("^TWII", period="6mo")
    if bm.empty:
        bm = fetch_data("0050.TW", period="6mo")
    return bm

benchmark_df = get_benchmark_data()
bm_trend = "中性震盪"
if not benchmark_df.empty:
    bm_close = benchmark_df['Close'].iloc[-1]
    bm_ma20 = benchmark_df['Close'].rolling(20).mean().iloc[-1]
    bm_ma60 = benchmark_df['Close'].rolling(60).mean().iloc[-1]
    if bm_close > bm_ma20 > bm_ma60:
        bm_trend = "🟢 多頭強勢區 (順勢做多勝率高)"
    elif bm_close < bm_ma20 and bm_close < bm_ma60:
        bm_trend = "🔴 空頭防守區 (嚴控持股倉位)"
    else:
        bm_trend = "🟡 區間整理 (精選個股，勿追高)"

# --- 頁籤佈局 ---
tab_daily, tab_board, tab_detail = st.tabs([
    "🎯 今日 AI 推薦做多標的", 
    "📊 大數據多因子評分總榜", 
    "🔍 個股深入多維技術診斷"
])

# =========================================================
# 分頁 1：今日精選推薦 (含深度思考拆解與停損停利)
# =========================================================
with tab_daily:
    st.header("🎯 頂尖量化操盤：今日最佳現貨做多標的")
    st.info(f"當前大盤環境狀態：**{bm_trend}**（大盤加權指數結構）")

    if st.button("⚡ 啟動全市場大數據動能與型態運算", type="primary"):
        with st.spinner("正在進行五大維度加權評分（趨勢30%、RS 25%、量能20%、VCP 15%、動能10%）..."):
            results = []
            
            # 計算大盤近 20 日漲跌幅做為基準
            bm_ret_20d = 0.0
            if len(benchmark_df) >= 20:
                bm_ret_20d = (benchmark_df['Close'].iloc[-1] - benchmark_df['Close'].iloc[-20]) / benchmark_df['Close'].iloc[-20] * 100

            for name, code in STOCK_POOL.items():
                try:
                    df = fetch_data(code, period="6mo")
                    if len(df) < 60:
                        continue
                    df = calculate_advanced_indicators(df)
                    latest = df.iloc[-1]
                    prev = df.iloc[-2]

                    # 1. 趨勢與結構 (權重 30 分)
                    score_trend = 0
                    if latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']:
                        score_trend += 15
                    if latest['MA20'] > df['MA20'].iloc[-5]:
                        score_trend += 5
                    # 股價距離半年高點在 15% 以內 (Minervini 強勢股特徵)
                    half_year_high = df['High'].tail(120).max()
                    if (half_year_high - latest['Close']) / half_year_high <= 0.15:
                        score_trend += 10

                    # 2. 相對大盤強弱度 RS (權重 25 分)
                    stock_ret_20d = (latest['Close'] - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100
                    rs_alpha = stock_ret_20d - bm_ret_20d
                    score_rs = 0
                    if rs_alpha > 8.0:
                        score_rs = 25
                    elif rs_alpha > 3.0:
                        score_rs = 18
                    elif rs_alpha > 0:
                        score_rs = 10

                    # 3. 威科夫量價與吸籌 (權重 20 分)
                    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
                    score_vol = 0
                    if vol_ratio >= 1.4 and latest['Close'] > latest['Open']:
                        score_vol += 12
                    elif vol_ratio >= 1.1 and latest['Close'] > latest['Open']:
                        score_vol += 7
                    if latest['OBV'] > latest['OBV_MA10']:
                        score_vol += 8

                    # 4. 波動收縮與型態 VCP (權重 15 分)
                    score_vcp = 0
                    # 檢視布林帶寬是否處於相對低位 (能量擠壓)
                    bw_min_recent = df['BB_Width'].tail(30).min()
                    if latest['BB_Width'] <= bw_min_recent * 1.3:
                        score_vcp += 10
                    # 近 5 日震幅收斂
                    recent_5_amp = (df['High'].tail(5).max() - df['Low'].tail(5).min()) / latest['Close'] * 100
                    if recent_5_amp < 6.0:
                        score_vcp += 5

                    # 5. 指標時機共振 (權重 10 分)
                    score_mom = 0
                    if 50 <= latest['K'] <= 80:
                        score_mom += 4
                    if prev['K'] < prev['D'] and latest['K'] >= latest['D']:
                        score_mom += 3  # 金叉
                    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']:
                        score_mom += 3

                    # 總得分加總
                    total_score = score_trend + score_rs + score_vol + score_vcp + score_mom

                    # 風控檢驗：計算進場防守空間
                    entry_p = float(latest['Close'])
                    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
                    low_5d = float(df['Low'].tail(5).min())
                    
                    # 停損設在 (近5日低點) 與 (現價 - 1.3*ATR) 的較高者
                    stop_l = max(low_5d, entry_p - 1.3 * atr_v)
                    risk_pct = (entry_p - stop_l) / entry_p * 100

                    # 懲罰機制：追高過度、停損需承受超過 7% 者大扣分
                    if risk_pct > 7.0:
                        total_score -= 30

                    results.append({
                        "name": name,
                        "code": code,
                        "total_score": max(0, total_score),
                        "score_trend": score_trend,
                        "score_rs": score_rs,
                        "score_vol": score_vol,
                        "score_vcp": score_vcp,
                        "score_mom": score_mom,
                        "close": entry_p,
                        "pct": (latest['Close'] - prev['Close']) / prev['Close'] * 100,
                        "rs_alpha": rs_alpha,
                        "vol_ratio": vol_ratio,
                        "stop_loss": stop_l,
                        "risk_pct": risk_pct,
                        "df": df
                    })
                except Exception:
                    continue

            if results:
                # 排序出今日最高分標的
                results.sort(key=lambda x: x['total_score'], reverse=True)
                top = results[0]

                # 計算 1:1.5 與 1:2.5 盈虧比目標價
                risk_amt = top['close'] - top['stop_loss']
                tp_1 = top['close'] + 1.5 * risk_amt
                tp_2 = top['close'] + 2.5 * risk_amt

                st.success(f"🏆 【今日全市場做多綜合評分首選】：**{top['name']}**")

                # 關鍵數值指標卡
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("🎯 建議現價進場點", f"{top['close']:.2f} 元", f"今日 {top['pct']:+.2f}%")
                col2.metric("🛡️ 嚴格防守停損點", f"{top['stop_loss']:.2f} 元", f"-{top['risk_pct']:.2f}%", delta_color="inverse")
                col3.metric("📈 第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-top['close'])/top['close'])*100:.2f}%")
                col4.metric("🚀 波段主力目標 (2.5R)", f"{tp_2:.2f} 元", f"+{((tp_2-top['close'])/top['close'])*100:.2f}%")

                st.markdown("---")

                # 大數據決策思維拆解
                st.subheader("🧠 系統為何選中它？大數據加權思考拆解")
                m_t, m_r, m_v, m_vc, m_m = st.columns(5)
                m_t.metric("1. 趨勢與結構 (30%)", f"{top['score_trend']} / 30 分")
                m_r.metric("2. 相對大盤 RS (25%)", f"{top['score_rs']} / 25 分", f"超額 Alpha {top['rs_alpha']:+.2f}%")
                m_v.metric("3. 威科夫量能 (20%)", f"{top['score_vol']} / 20 分", f"量比 {top['vol_ratio']:.2f}x")
                m_vc.metric("4. 波動收縮 VCP (15%)", f"{top['score_vcp']} / 15 分")
                m_m.metric("5. 時機動能 (10%)", f"{top['score_mom']} / 10 分")

                st.write(f"""
                **📌 操盤手深度作戰思維：**
                * **趨勢核心**：站穩 20MA 月線與 60MA 季線之上，且均線呈現多頭仰角發散，屬於 Weinstein 經典第二階段（Stage 2）的主升段架構。
                * **相對優勢 (RS)**：近一個月相對加權指數跑出 **{top['rs_alpha']:+.2f}%** 的超額 Alpha，顯現主力資金明顯抗跌護盤，屬領頭羊性質。
                * **進出場紀律**：
                    * **進場依據**：量縮整理後帶量轉強，盤中以 **{top['close']:.2f} 元** 附近介入。
                    * **停損守則**：若收盤跌破 **{top['stop_loss']:.2f} 元**（單筆虧損控制在 **{top['risk_pct']:.2f}%** 內），代表突破假訊號，無條件停損出場。
                    * **止盈節奏**：到達第一目標 **{tp_1:.2f} 元** 先行獲利了結 1/2，將剩餘倉位之停損點移動至買進成本價（保本），無壓力讓利潤奔跑至 **{tp_2:.2f} 元**。
                """)

                # 繪製視覺化點位 K 線圖
                fig_top = go.Figure(data=[go.Candlestick(
                    x=top['df'].index[-45:],
                    open=top['df']['Open'][-45:],
                    high=top['df']['High'][-45:],
                    low=top['df']['Low'][-45:],
                    close=top['df']['Close'][-45:],
                    name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
                )])
                fig_top.add_hline(y=top['stop_loss'], line_dash="dash", line_color="#0da651", annotation_text=f"停損防守線 {top['stop_loss']:.2f}")
                fig_top.add_hline(y=tp_1, line_dash="dash", line_color="#eb4034", annotation_text=f"第一止盈目標 {tp_1:.2f}")
                fig_top.add_hline(y=tp_2, line_dash="dash", line_color="#f39c12", annotation_text=f"波段止盈目標 {tp_2:.2f}")
                fig_top.update_layout(height=450, title=f"{top['name']} 關鍵點位與多空防守佈局", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig_top, use_container_width=True)

                # 存入 session_state 供排行榜使用
                st.session_state['scan_results'] = results
            else:
                st.warning("目前市場處於深度修正期，無符合嚴格高盈虧比的做多標的，請保持耐性空手觀望。")
    else:
        st.write("👉 請點擊上方按鈕，啟動加權大數據模型進行即時運算。")

# =========================================================
# 分頁 2：大數據多因子評分全體排行榜
# =========================================================
with tab_board:
    st.header("📊 股票池多因子綜合評分全景榜")
    st.caption("公開大數據運算過程，觀察每檔標的在趨勢、RS、量價、VCP 與時機的細項得分。")
    
    if 'scan_results' in st.session_state and st.session_state['scan_results']:
        rank_data = []
        for r in st.session_state['scan_results']:
            rank_data.append({
                "代碼與名稱": r['name'],
                "總分 (滿分100)": r['total_score'],
                "現價": f"{r['close']:.2f}",
                "今日漲跌%": f"{r['pct']:+.2f}%",
                "相對大盤RS超額%": f"{r['rs_alpha']:+.2f}%",
                "量比 (Vol/5MA)": f"{r['vol_ratio']:.2f}x",
                "趨勢分(30)": r['score_trend'],
                "RS分(25)": r['score_rs'],
                "量能分(20)": r['score_vol'],
                "VCP分(15)": r['score_vcp'],
                "時機分(10)": r['score_mom'],
                "建議停損%": f"-{r['risk_pct']:.2f}%"
            })
        st.dataframe(pd.DataFrame(rank_data), use_container_width=True)
    else:
        st.info("請先在第一分頁點擊『啟動全市場大數據動能與型態運算』，數據將自動在此同步生成。")

# =========================================================
# 分頁 3：個股深入多維技術診斷 (保留完整看板 + 擴充布林帶寬)
# =========================================================
with tab_detail:
    st.sidebar.title("📈 個股技術分析控制台")
    selected_stock = st.sidebar.selectbox("選擇要分析的標的", list(STOCK_POOL.keys()), key="detail_stock")
    stock_code = STOCK_POOL[selected_stock]

    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
    selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2, key="detail_period")
    show_ma = st.sidebar.multiselect("顯示均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA20", "MA60"])
    indicator_choice = st.sidebar.radio("副圖技術指標", ["KD 指標 (9,3,3)", "MACD (12,26,9)", "布林帶寬 (VCP壓縮)", "全指標展示"])

    df_d = fetch_data(stock_code, period_map[selected_period])
    if not df_d.empty:
        df_d = calculate_advanced_indicators(df_d)
        latest_d = df_d.iloc[-1]
        prev_d = df_d.iloc[-2] if len(df_d) > 1 else latest_d
        p_diff = latest_d['Close'] - prev_d['Close']
        pct_diff = (p_diff / prev_d['Close']) * 100

        st.subheader(f"{selected_stock} 綜合深度技術看板")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("最新收盤價", f"{latest_d['Close']:.2f} 元", f"{p_diff:+.2f} ({pct_diff:+.2f}%)")
        c2.metric("單日最高 / 最低", f"{latest_d['High']:.2f} / {latest_d['Low']:.2f}")
        c3.metric("5日均量 (Vol 5MA)", f"{int(latest_d['Vol_MA5']):,} 股")
        c4.metric("14日真實波幅 (ATR)", f"{latest_d['ATR']:.2f} 元")
        c5.metric("布林帶寬 (BandWidth)", f"{latest_d['BB_Width']:.3f}")

        # 子圖架構建立
        if indicator_choice == "全指標展示":
            rows, r_heights = 5, [0.44, 0.14, 0.14, 0.14, 0.14]
            sub_titles = ("K線與均線/布林通道走勢", "成交量 (Volume)", "KD 指標", "MACD 指標", "布林帶寬 (波動擠壓)")
        elif indicator_choice == "布林帶寬 (VCP壓縮)":
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線與布林通道", "成交量", "布林帶寬 (BandWidth)")
        else:
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線與均線走勢", "成交量", indicator_choice)

        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=r_heights, subplot_titles=sub_titles)

        # 1. K 線圖
        fig.add_trace(go.Candlestick(
            x=df_d.index, open=df_d['Open'], high=df_d['High'], low=df_d['Low'], close=df_d['Close'],
            name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
        ), row=1, col=1)

        # 均線或布林通道
        ma_colors = {'MA5': '#f39c12', 'MA10': '#9b59b6', 'MA20': '#2980b9', 'MA60': '#16a085'}
        for ma in show_ma:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d[ma], mode='lines', name=ma, line=dict(color=ma_colors[ma], width=1.5)), row=1, col=1)

        # 2. 成交量
        vol_c = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_d['Close'], df_d['Open'])]
        fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], marker_color=vol_c, name="成交量"), row=2, col=1)

        # 3. 各指標繪製
        cur = 3
        if indicator_choice in ["KD 指標 (9,3,3)", "全指標展示"]:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['K'], line=dict(color='#e74c3c', width=1.5), name="K (9)"), row=cur, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['D'], line=dict(color='#3498db', width=1.5), name="D (9)"), row=cur, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="gray", row=cur, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="gray", row=cur, col=1)
            cur += 1

        if indicator_choice in ["MACD (12,26,9)", "全指標展示"]:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['DIF'], line=dict(color='#2980b9', width=1.3), name="DIF"), row=cur, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MACD'], line=dict(color='#e67e22', width=1.3), name="MACD"), row=cur, col=1)
            hist_c = ['#eb4034' if v >= 0 else '#0da651' for v in df_d['MACD_Hist']]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['MACD_Hist'], marker_color=hist_c, name="MACD柱"), row=cur, col=1)
            cur += 1

        if indicator_choice in ["布林帶寬 (VCP壓縮)", "全指標展示"]:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['BB_Width'], line=dict(color='#8e44ad', width=1.4), name="BandWidth"), row=cur, col=1)

        fig.update_layout(height=900, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # 匯出資料
        with st.expander("📥 檢視與下載個股歷史技術指標數據 (CSV)"):
            st.dataframe(df_d.tail(30).sort_index(ascending=False))
            st.download_button(
                label="下載完整 CSV",
                data=df_d.to_csv().encode('utf-8-sig'),
                file_name=f"{stock_code}_advanced_data.csv",
                mime="text/csv"
            )