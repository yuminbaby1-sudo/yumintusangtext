import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="AI 時代尖端操盤系統 (技術+基本面+利多催化劑)", layout="wide", initial_sidebar_state="expanded")

# --- 20 大尖端主流族群輪動觀察池 (涵蓋 85 檔指標飆股) ---
SECTOR_MAP = {
    "CPO 矽光子 / 光通訊": {
        "聯鈞 (3450)": "3450.TW", "上詮 (3363)": "3363.TWO", "聯亞 (3081)": "3081.TWO",
        "華星光 (4979)": "4979.TWO", "光聖 (6442)": "6442.TW", "眾達-KY (4977)": "4977.TW"
    },
    "CoWoS 先進封裝 / 設備": {
        "辛耘 (3583)": "3583.TW", "弘塑 (3131)": "3131.TWO", "萬潤 (6187)": "6187.TWO",
        "均豪 (5443)": "5443.TWO", "志聖 (2467)": "2467.TW"
    },
    "散熱模組 (水冷/液冷)": {
        "奇鋐 (3017)": "3017.TW", "雙鴻 (3324)": "3324.TW", "高力 (8996)": "8996.TW",
        "健策 (3653)": "3653.TW", "尼得科超眾 (6230)": "6230.TW"
    },
    "AI 伺服器 & 組裝": {
        "廣達 (2382)": "2382.TW", "緯創 (3231)": "3231.TW", "技嘉 (2376)": "2376.TW",
        "緯穎 (6669)": "6669.TW", "英業達 (2356)": "2356.TW", "神達 (3706)": "3706.TW"
    },
    "PCB / 載板 / CCL": {
        "台光電 (2383)": "2383.TW", "欣興 (3037)": "3037.TW", "金像電 (2368)": "2368.TW",
        "台燿 (6274)": "6274.TW", "景碩 (3189)": "3189.TW", "南電 (8046)": "8046.TW"
    },
    "記憶體 / 模組 / 顆粒": {
        "南亞科 (2408)": "2408.TW", "華邦電 (2344)": "2344.TW", "群聯 (8299)": "8299.TWO",
        "威剛 (3260)": "3260.TWO", "十銓 (4967)": "4967.TW", "晶豪科 (3006)": "3006.TW"
    },
    "機器人 / 自動化": {
        "所羅門 (2359)": "2359.TW", "昆盈 (2365)": "2365.TW", "廣明 (6188)": "6188.TWO",
        "和碩 (4938)": "4938.TW", "羅昇 (8374)": "8374.TW", "穎漢 (4562)": "4562.TW"
    },
    "ASIC / 矽智財 (IP)": {
        "世芯-KY (3661)": "3661.TW", "創意 (3443)": "3443.TW", "智原 (3035)": "3035.TW",
        "力旺 (3529)": "3529.TWO", "M31 (6643)": "6643.TWO"
    },
    "IC 設計 / 主流晶片": {
        "聯發科 (2454)": "2454.TW", "聯詠 (3034)": "3034.TW", "瑞昱 (2379)": "2379.TW",
        "祥碩 (5269)": "5269.TW", "信驊 (5274)": "5274.TWO"
    },
    "半導體代工與封測": {
        "台積電 (2330)": "2330.TW", "聯電 (2303)": "2303.TW", "日月光投控 (3711)": "3711.TW",
        "京元電子 (2449)": "2449.TW"
    },
    "重電 / 綠能電網": {
        "華城 (1519)": "1519.TW", "士電 (1503)": "1503.TW", "中興電 (1513)": "1513.TW",
        "亞力 (1514)": "1514.TW", "大同 (2371)": "2371.TW"
    },
    "軍工防衛 / 無人機": {
        "雷虎 (8033)": "8033.TW", "漢翔 (2634)": "2634.TW", "駐龍 (4572)": "4572.TW",
        "亞航 (2630)": "2630.TW", "寶一 (8222)": "8222.TW"
    },
    "車用電子 / 電動車": {
        "貿聯-KY (3665)": "3665.TW", "台達電 (2308)": "2308.TW", "定穎投控 (3715)": "3715.TW",
        "胡連 (6279)": "6279.TW"
    },
    "光學鏡頭 / 機器視覺": {
        "大立光 (3008)": "3008.TW", "玉晶光 (3406)": "3406.TW", "先進光 (3362)": "3362.TWO",
        "佳凌 (4976)": "4976.TW"
    },
    "半導體特用化學品": {
        "中華化 (1727)": "1727.TW", "三晃 (1721)": "1721.TW", "勝一 (1773)": "1773.TW",
        "長興 (1717)": "1717.TW"
    },
    "航運 / 貨櫃與散裝": {
        "長榮 (2603)": "2603.TW", "陽明 (2609)": "2609.TW", "萬海 (2615)": "2615.TW",
        "裕民 (2606)": "2606.TW", "新興 (2605)": "2605.TW"
    },
    "生技醫療 / CDMO": {
        "保瑞 (6472)": "6472.TW", "美時 (1795)": "1795.TW", "藥華藥 (6446)": "6446.TWO",
        "晶碩 (6491)": "6491.TW"
    },
    "鋼鐵與原物料": {
        "中鋼 (2002)": "2002.TW", "大成鋼 (2027)": "2027.TW", "中鴻 (2014)": "2014.TW"
    },
    "金融內資主力": {
        "富邦金 (2881)": "2881.TW", "國泰金 (2882)": "2882.TW", "中信金 (2891)": "2891.TW",
        "元大金 (2885)": "2885.TW"
    },
    "核心權值指標": {
        "鴻海 (2317)": "2317.TW", "元大台灣50 (0050)": "0050.TW"
    }
}

ALL_STOCKS = {}
STOCK_TO_SECTOR = {}
for sec, stk_dict in SECTOR_MAP.items():
    for name, code in stk_dict.items():
        ALL_STOCKS[name] = code
        STOCK_TO_SECTOR[name] = sec

# --- 高階技術指標計算 ---
def calculate_indicators(df):
    df = df.copy()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

    # VCP 波動收斂
    std20 = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (2 * std20)
    df['BB_Lower'] = df['MA20'] - (2 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['MA20'] + 1e-9)

    # ATR
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()

    # OBV
    obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'],
                 np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
    df['OBV'] = pd.Series(obv_change, index=df.index).cumsum()
    df['OBV_MA10'] = df['OBV'].rolling(10).mean()

    # KD
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
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

    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    return df

# --- 大盤基準 ---
@st.cache_data(ttl=600)
def get_benchmark_data():
    bm = yf.download("^TWII", period="6mo", progress=False)
    if hasattr(bm.columns, 'levels') and len(bm.columns.levels) > 1:
        bm.columns = bm.columns.get_level_values(0)
    if bm.empty:
        bm = yf.download("0050.TW", period="6mo", progress=False)
        if hasattr(bm.columns, 'levels') and len(bm.columns.levels) > 1:
            bm.columns = bm.columns.get_level_values(0)
    return bm

benchmark_df = get_benchmark_data()
bm_trend = "中性整理"
if not benchmark_df.empty:
    bm_c = benchmark_df['Close'].iloc[-1]
    bm_ma20 = benchmark_df['Close'].rolling(20).mean().iloc[-1]
    bm_ma60 = benchmark_df['Close'].rolling(60).mean().iloc[-1]
    if bm_c > bm_ma20 > bm_ma60:
        bm_trend = "🟢 多頭主升環境 (族群輪動強勁，做多順勢推升勝率最高)"
    elif bm_c < bm_ma20 and bm_c < bm_ma60:
        bm_trend = "🔴 空頭防守環境 (大盤下彎，嚴格控制持倉部位)"
    else:
        bm_trend = "🟡 區間震盪環境 (指數空間有限，資金極度聚焦熱門題材股)"

# --- 基本面與即時利多新聞抓取函式 ---
@st.cache_data(ttl=600)
def get_fundamental_and_news(ticker):
    stock_obj = yf.Ticker(ticker)
    info = stock_obj.info or {}
    news = stock_obj.news or []

    # 擷取關鍵基本面
    rev_growth = info.get('revenueGrowth', None) # 營收年增率
    earn_growth = info.get('earningsGrowth', None) # 獲利年增率
    target_price = info.get('targetMeanPrice', None) # 法人平均目標價
    forward_pe = info.get('forwardPE', None) # 前瞻本益比
    gross_margin = info.get('grossMargins', None) # 毛利率

    return {
        "rev_growth": rev_growth * 100 if rev_growth is not None else None,
        "earn_growth": earn_growth * 100 if earn_growth is not None else None,
        "target_price": target_price,
        "forward_pe": forward_pe,
        "gross_margin": gross_margin * 100 if gross_margin is not None else None,
        "news": news[:5] # 取最近 5 則最新消息
    }

# --- 頁籤系統 ---
tab_daily, tab_rank, tab_detail = st.tabs([
    "🎯 今日 AI 推薦做多標的 (技術+基本面+利多)", 
    "🔥 20 大尖端族群動能總榜", 
    "🔍 個股多維深入技術與基本面診斷"
])

# =========================================================
# 分頁 1：今日推薦 (大數據精選 + 基本面體檢 + 利多新聞)
# =========================================================
with tab_daily:
    st.header("🎯 世紀飆股雷達：今日最佳現貨做多標的")
    st.info(f"當前大盤總體環境架構：**{bm_trend}**")

    if st.button("🚀 啟動 20 大族群大數據＋基本面成長性深度掃描", type="primary"):
        with st.spinner("正在進行平行計算：技術趨勢(25%) + RS相對強弱(20%) + 量價OBV(20%) + VCP型態(10%) + 基本面/法人空間(25%)..."):
            all_tickers = list(ALL_STOCKS.values())
            raw_data = yf.download(all_tickers, period="6mo", group_by='ticker', threads=True, progress=False)

            bm_ret_20d = 0.0
            if len(benchmark_df) >= 20:
                bm_ret_20d = (benchmark_df['Close'].iloc[-1] - benchmark_df['Close'].iloc[-20]) / benchmark_df['Close'].iloc[-20] * 100

            results = []
            sector_scores = {sec: [] for sec in SECTOR_MAP.keys()}
            sector_pcts = {sec: [] for sec in SECTOR_MAP.keys()}

            for name, code in ALL_STOCKS.items():
                try:
                    df = raw_data[code].dropna() if code in raw_data else pd.DataFrame()
                    if len(df) < 60:
                        continue
                    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
                        df.columns = df.columns.get_level_values(0)

                    df = calculate_indicators(df)
                    latest = df.iloc[-1]
                    prev = df.iloc[-2]
                    sec_name = STOCK_TO_SECTOR[name]
                    pct_change = (latest['Close'] - prev['Close']) / prev['Close'] * 100

                    # 1. 趨勢與架構 (25%)
                    score_trend = 0
                    if latest['Close'] > latest['MA20'] > latest['MA60']: score_trend += 12
                    if latest['MA20'] > df['MA20'].iloc[-5]: score_trend += 5
                    half_yr_high = df['High'].tail(120).max()
                    if (half_yr_high - latest['Close']) / half_yr_high <= 0.15: score_trend += 8

                    # 2. 相對強弱 RS vs 大盤 (20%)
                    stock_ret_20d = (latest['Close'] - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100
                    rs_alpha = stock_ret_20d - bm_ret_20d
                    score_rs = 0
                    if rs_alpha > 8.0: score_rs = 20
                    elif rs_alpha > 3.0: score_rs = 14
                    elif rs_alpha > 0: score_rs = 8

                    # 3. 威科夫量價與吸籌 (20%)
                    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
                    score_vol = 0
                    if vol_ratio >= 1.4 and latest['Close'] > latest['Open']: score_vol += 12
                    elif vol_ratio >= 1.1 and latest['Close'] > latest['Open']: score_vol += 7
                    if latest['OBV'] > latest['OBV_MA10']: score_vol += 8

                    # 4. VCP 波動收斂 (10%)
                    score_vcp = 0
                    bw_min_recent = df['BB_Width'].tail(30).min()
                    if latest['BB_Width'] <= bw_min_recent * 1.3: score_vcp += 6
                    recent_5_amp = (df['High'].tail(5).max() - df['Low'].tail(5).min()) / latest['Close'] * 100
                    if recent_5_amp < 6.0: score_vcp += 4

                    # 5. 時機動能 (5%)
                    score_mom = 0
                    if 50 <= latest['K'] <= 80: score_mom += 3
                    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: score_mom += 2

                    tech_total = score_trend + score_rs + score_vol + score_vcp + score_mom

                    # 風控檢驗
                    entry_p = float(latest['Close'])
                    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
                    low_5d = float(df['Low'].tail(5).min())
                    stop_l = max(low_5d, entry_p - 1.3 * atr_v)
                    risk_pct = (entry_p - stop_l) / entry_p * 100

                    if risk_pct > 7.0:
                        tech_total -= 30

                    results.append({
                        "name": name,
                        "code": code,
                        "sector": sec_name,
                        "tech_score": max(0, tech_total),
                        "score_trend": score_trend,
                        "score_rs": score_rs,
                        "score_vol": score_vol,
                        "score_vcp": score_vcp,
                        "score_mom": score_mom,
                        "close": entry_p,
                        "pct": pct_change,
                        "rs_alpha": rs_alpha,
                        "vol_ratio": vol_ratio,
                        "stop_loss": stop_l,
                        "risk_pct": risk_pct,
                        "df": df
                    })
                except Exception:
                    continue

            if results:
                # 先對技術前 8 名做基本面加權深化
                results.sort(key=lambda x: x['tech_score'], reverse=True)
                top_candidates = results[:8]

                for cand in top_candidates:
                    f_data = get_fundamental_and_news(cand['code'])
                    cand['fundamental'] = f_data

                    # 基本面評分 (20分)
                    score_fund = 0
                    rev_g = f_data['rev_growth']
                    tp = f_data['target_price']
                    
                    # 營收爆發性
                    if rev_g is not None:
                        if rev_g >= 30.0: score_fund += 10 # 營收年增 30% 以上爆發
                        elif rev_g >= 15.0: score_fund += 6
                        elif rev_g > 0: score_fund += 3

                    # 法人目標價空間
                    if tp is not None and tp > cand['close']:
                        upside = (tp - cand['close']) / cand['close'] * 100
                        cand['upside'] = upside
                        if upside >= 25.0: score_fund += 10 # 距離目標價還有 25%+ 空間
                        elif upside >= 12.0: score_fund += 6
                        elif upside > 0: score_fund += 3
                    else:
                        cand['upside'] = 0.0

                    cand['score_fund'] = score_fund
                    cand['total_score'] = cand['tech_score'] + score_fund

                # 選出融合技術與基本面的總冠軍
                top_candidates.sort(key=lambda x: x['total_score'], reverse=True)
                top = top_candidates[0]

                # 計算 1.5R 與 2.5R 盈虧比目標
                risk_amt = top['close'] - top['stop_loss']
                tp_1 = top['close'] + 1.5 * risk_amt
                tp_2 = top['close'] + 2.5 * risk_amt

                st.success(f"🏆 【今日雙維度（技術＋基本面）綜合冠軍】：**{top['name']}** ｜ 所屬族群：**【{top['sector']}】**")
                
                # 數值指標卡
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("🎯 建議現價進場點", f"{top['close']:.2f} 元", f"今日漲跌 {top['pct']:+.2f}%")
                col2.metric("🛡️ 嚴格防守停損點", f"{top['stop_loss']:.2f} 元", f"-{top['risk_pct']:.2f}%", delta_color="inverse")
                col3.metric("📈 第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-top['close'])/top['close'])*100:.2f}%")
                col4.metric("🚀 波段主力目標 (2.5R)", f"{tp_2:.2f} 元", f"+{((tp_2-top['close'])/top['close'])*100:.2f}%")

                st.markdown("---")

                # 基本面體檢與法人共識
                st.subheader("📊 核心基本面爆發力與法人預期")
                f = top['fundamental']
                fb1, fb2, fb3, fb4 = st.columns(4)
                
                rev_display = f"{f['rev_growth']:+.1f}%" if f['rev_growth'] is not None else "資料更新中"
                earn_display = f"{f['earn_growth']:+.1f}%" if f['earn_growth'] is not None else "資料更新中"
                tp_display = f"{f['target_price']:.1f} 元" if f['target_price'] is not None else "尚無法人目標"
                upside_display = f"{top.get('upside', 0):+.1f}%" if f['target_price'] is not None else "--"
                pe_display = f"{f['forward_pe']:.1f} 倍" if f['forward_pe'] is not None else "N/A"

                fb1.metric("最新營收年增率 (YoY)", rev_display)
                fb2.metric("最新獲利年增率 (YoY)", earn_display)
                fb3.metric("法人平均目標價", tp_display, f"潛在空間 {upside_display}")
                fb4.metric("前瞻本益比 (Forward PE)", pe_display)

                st.markdown("---")

                # 十倍催化劑：即時新聞與合作題材
                st.subheader("📰 十倍行情催化劑：即時利多新聞與題材動向")
                if f['news']:
                    for n in f['news']:
                        title = n.get('title', '即時訊息')
                        publisher = n.get('publisher', '財經媒體')
                        link = n.get('link', '#')
                        st.markdown(f"* 🔗 **[{title}]({link})** — *{publisher}*")
                else:
                    st.write("目前尚無最新重大公開公告，主力處於低調沿均線吃貨期。")

                st.markdown("---")

                # 視覺化圖表
                fig_top = go.Figure(data=[go.Candlestick(
                    x=top['df'].index[-45:],
                    open=top['df']['Open'][-45:],
                    high=top['df']['High'][-45:],
                    low=top['df']['Low'][-45:],
                    close=top['df']['Close'][-45:],
                    name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
                )])
                fig_top.add_hline(y=top['stop_loss'], line_dash="dash", line_color="#0da651", annotation_text=f"停損線 {top['stop_loss']:.2f}")
                fig_top.add_hline(y=tp_1, line_dash="dash", line_color="#eb4034", annotation_text=f"第一目標 {tp_1:.2f}")
                fig_top.add_hline(y=tp_2, line_dash="dash", line_color="#f39c12", annotation_text=f"波段目標 {tp_2:.2f}")
                if f['target_price']:
                    fig_top.add_hline(y=f['target_price'], line_dash="dot", line_color="#9b59b6", annotation_text=f"法人目標價 {f['target_price']:.1f}")

                fig_top.update_layout(height=460, title=f"{top['name']} ({top['sector']}) 關鍵防守與目標走勢圖", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig_top, use_container_width=True)

                st.session_state['results'] = results
            else:
                st.warning("市場正處於劇烈下修期，無符合標準之標的，請嚴格空手觀望。")
    else:
        st.write("👉 點擊上方按鈕，系統將自動啟動技術面、營收成長性與利多消息之綜合演算。")

# =========================================================
# 分頁 2：族群熱度與全體評分榜
# =========================================================
with tab_rank:
    st.header("🔥 20 大尖端族群動能熱度與多因子全景榜")
    if 'results' in st.session_state and st.session_state['results']:
        st.subheader("📋 85 檔個股多維度技術評分明細")
        filter_sec = st.selectbox("依族群篩選查看", ["全部族群"] + list(SECTOR_MAP.keys()))
        
        table_rows = []
        for r in st.session_state['results']:
            if filter_sec != "全部族群" and r['sector'] != filter_sec:
                continue
            table_rows.append({
                "標的": r['name'],
                "所屬族群": r['sector'],
                "技術分": r['tech_score'],
                "現價": f"{r['close']:.2f}",
                "今日漲跌%": f"{r['pct']:+.2f}%",
                "相對大盤RS%": f"{r['rs_alpha']:+.2f}%",
                "量比 (Vol/5MA)": f"{r['vol_ratio']:.2f}x",
                "趨勢(25)": r['score_trend'],
                "RS(20)": r['score_rs'],
                "量能(20)": r['score_vol'],
                "VCP(10)": r['score_vcp'],
                "時機(5)": r['score_mom'],
                "建議停損%": f"-{r['risk_pct']:.2f}%"
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
    else:
        st.info("請先至第一分頁點擊『啟動大數據掃描』，數據將自動在此生成。")

# =========================================================
# 分頁 3：個股多維深入技術與基本面診斷
# =========================================================
with tab_detail:
    st.sidebar.title("📈 個股深度分析控制台")
    selected_sec = st.sidebar.selectbox("快速按族群挑選", list(SECTOR_MAP.keys()))
    selected_stock = st.sidebar.selectbox("選擇要分析的標的", list(SECTOR_MAP[selected_sec].keys()))
    stock_code = SECTOR_MAP[selected_sec][selected_stock]

    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
    selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2)
    show_ma = st.sidebar.multiselect("顯示均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA20", "MA60"])
    indicator_choice = st.sidebar.radio("副圖技術指標", ["KD 指標 (9,3,3)", "MACD (12,26,9)", "布林帶寬 (VCP壓縮)", "全指標展示"])

    df_d = yf.download(stock_code, period=period_map[selected_period], progress=False)
    if hasattr(df_d.columns, 'levels') and len(df_d.columns.levels) > 1:
        df_d.columns = df_d.columns.get_level_values(0)

    if not df_d.empty:
        df_d = calculate_indicators(df_d)
        latest_d = df_d.iloc[-1]
        prev_d = df_d.iloc[-2] if len(df_d) > 1 else latest_d
        p_diff = latest_d['Close'] - prev_d['Close']
        pct_diff = (p_diff / prev_d['Close']) * 100

        st.subheader(f"{selected_stock} 綜合深度技術看板 ｜ 族群：{selected_sec}")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("最新收盤價", f"{latest_d['Close']:.2f} 元", f"{p_diff:+.2f} ({pct_diff:+.2f}%)")
        c2.metric("單日最高 / 最低", f"{latest_d['High']:.2f} / {latest_d['Low']:.2f}")
        c3.metric("5日均量 (Vol 5MA)", f"{int(latest_d['Vol_MA5']):,} 股")
        c4.metric("14日真實波幅 (ATR)", f"{latest_d['ATR']:.2f} 元")
        c5.metric("布林帶寬 (BandWidth)", f"{latest_d['BB_Width']:.3f}")

        # 子圖架構
        if indicator_choice == "全指標展示":
            rows, r_heights = 5, [0.44, 0.14, 0.14, 0.14, 0.14]
            sub_titles = ("K線與均線走勢", "成交量 (Volume)", "KD 指標", "MACD 指標", "布林帶寬 (波動擠壓)")
        elif indicator_choice == "布林帶寬 (VCP壓縮)":
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線走勢", "成交量", "布林帶寬 (BandWidth)")
        else:
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線走勢", "成交量", indicator_choice)

        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=r_heights, subplot_titles=sub_titles)

        # 1. K 線圖 (台股紅漲綠跌)
        fig.add_trace(go.Candlestick(
            x=df_d.index, open=df_d['Open'], high=df_d['High'], low=df_d['Low'], close=df_d['Close'],
            name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
        ), row=1, col=1)

        ma_colors = {'MA5': '#f39c12', 'MA10': '#9b59b6', 'MA20': '#2980b9', 'MA60': '#16a085'}
        for ma in show_ma:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d[ma], mode='lines', name=ma, line=dict(color=ma_colors[ma], width=1.5)), row=1, col=1)

        # 2. 成交量
        vol_c = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_d['Close'], df_d['Open'])]
        fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], marker_color=vol_c, name="成交量"), row=2, col=1)

        # 3. 副圖
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

        fig.update_layout(height=850, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # 深入基本面與新聞折疊區
        with st.expander("🏢 該標的深入基本面體檢與最新即時新聞"):
            f_detail = get_fundamental_and_news(stock_code)
            dc1, dc2, dc3 = st.columns(3)
            dc1.write(f"**營收年增率 (YoY)**：{f_detail['rev_growth']:+.1f}%" if f_detail['rev_growth'] else "**營收年增率**：N/A")
            dc2.write(f"**法人目標價**：{f_detail['target_price']:.1f} 元" if f_detail['target_price'] else "**法人目標價**：尚無公開報告")
            dc3.write(f"**前瞻本益比**：{f_detail['forward_pe']:.1f} 倍" if f_detail['forward_pe'] else "**前瞻本益比**：N/A")
            
            st.markdown("#### 最新新聞與公告")
            if f_detail['news']:
                for nw in f_detail['news']:
                    st.markdown(f"* 🔗 [{nw.get('title', '新聞')}]({nw.get('link', '#')}) — *{nw.get('publisher', '')}*")
            else:
                st.write("查無近期相關新聞。")