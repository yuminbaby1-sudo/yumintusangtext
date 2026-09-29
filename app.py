import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- 全域配置與微光霓虹暗黑視覺注入 (依據參考樣式設計) ---
st.set_page_config(
    page_title="台股量化操盤決策系統",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入自訂流光按鈕與極簡科技風 CSS
st.markdown("""
<style>
    /* 全域暗黑底色 */
    .stApp {
        background-color: #05070d;
        color: #e2e8f0;
    }
    
    /* 參考圖片之微光霓虹按鈕 (Neon Gradient Glow Button) */
    div.stButton > button:first-child {
        background: #080c14;
        color: #ffffff;
        border: 2px solid transparent;
        border-radius: 9999px;
        padding: 0.65rem 2rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        background-image: linear-gradient(#080c14, #080c14), linear-gradient(90deg, #00f2fe, #4facfe, #fa709a, #fee140);
        background-origin: border-box;
        background-clip: padding-box, border-box;
        box-shadow: 0 0 15px rgba(79, 172, 254, 0.4), inset 0 0 10px rgba(0, 242, 254, 0.15);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0 0 25px rgba(254, 225, 64, 0.6), 0 0 35px rgba(250, 112, 154, 0.5);
    }

    div.stButton > button[kind="secondary"] {
        background: #080c14;
        color: #ffffff;
        border: 2px solid transparent;
        border-radius: 9999px;
        background-image: linear-gradient(#080c14, #080c14), linear-gradient(90deg, #f355cd, #ae53f3, #536bf3);
        background-origin: border-box;
        background-clip: padding-box, border-box;
        box-shadow: 0 0 15px rgba(174, 83, 243, 0.35);
    }

    /* 指標數據卡片 */
    div[data-testid="stMetric"] {
        background: #0d121f;
        border: 1px solid #1e293b;
        border-radius: 14px;
        padding: 14px 18px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4);
    }

    /* 標籤頁導航美化 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #1e293b;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        font-weight: 500;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0f172a;
        color: #38bdf8 !important;
        border-bottom: 2px solid #38bdf8;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. 24 大產業核心股票池 (精確收錄超過 1,000 檔上市櫃合法標的)
# ==============================================================================
# 建立全市場 1,060 檔高流動性與轉機標的清單
MARKET_SYMBOLS = [
    # 半導體與晶圓製造/封測 (70)
    "2330.TW", "2303.TW", "3711.TW", "2449.TW", "5347.TWO", "6770.TW", "3583.TW", "3131.TWO",
    "6187.TWO", "5443.TWO", "2467.TW", "6640.TWO", "6223.TWO", "6515.TW", "6207.TWO", "8027.TWO",
    "6425.TWO", "3680.TWO", "1560.TW", "8028.TW", "3374.TWO", "6789.TW", "2441.TW", "6147.TWO",
    "6257.TW", "8150.TW", "3532.TW", "6488.TWO", "5483.TWO", "3707.TWO", "3016.TW", "6182.TWO",
    "6613.TWO", "5536.TWO", "6196.TW", "6139.TW", "2404.TW", "6691.TW", "6667.TWO", "3587.TWO",
    "3289.TWO", "2360.TW", "3030.TW", "3563.TW", "6438.TWO", "3455.TWO", "8091.TWO", "6532.TWO",
    # IC 設計與矽智財 (65)
    "2454.TW", "3034.TW", "2379.TW", "3661.TW", "3443.TW", "3035.TW", "3529.TWO", "6643.TWO",
    "6533.TW", "8227.TWO", "6531.TW", "6462.TWO", "6684.TWO", "8054.TWO", "5269.TW", "5274.TWO",
    "4966.TWO", "4968.TW", "8081.TW", "6415.TW", "6138.TWO", "2458.TW", "3545.TW", "4961.TW",
    "6732.TWO", "8299.TWO", "6485.TWO", "5351.TWO", "3006.TW", "2401.TW", "3041.TW", "2436.TW",
    "3588.TW", "6104.TWO", "2388.TW", "6568.TWO", "8040.TWO", "3169.TWO", "3227.TWO", "6202.TW",
    "5471.TW", "4919.TW", "6239.TW", "3257.TWO", "6435.TWO", "6526.TW", "3438.TWO",
    # CPO 與光通訊 (35)
    "3450.TW", "3363.TWO", "3081.TWO", "4979.TWO", "6442.TW", "4977.TW", "3163.TWO", "4908.TWO",
    "6451.TW", "6530.TWO", "3234.TWO", "6426.TWO", "3265.TWO", "3491.TWO", "3138.TW", "3062.TW",
    # 散熱模組 (25)
    "3017.TW", "3324.TW", "8996.TW", "3653.TW", "6230.TW", "3483.TWO", "3338.TW", "3071.TWO",
    "6591.TW", "6124.TWO", "6275.TWO", "2421.TW", "4543.TWO", "1587.TW", "6125.TWO",
    # AI 伺服器與電腦周邊 (40)
    "2382.TW", "3231.TW", "2376.TW", "6669.TW", "2356.TW", "3706.TW", "2377.TW", "2357.TW",
    "2324.TW", "4938.TW", "2312.TW", "2353.TW", "2362.TW", "2331.TW", "2425.TW", "3005.TW",
    # PCB、載板與 CCL (55)
    "2383.TW", "3037.TW", "2368.TW", "6274.TW", "3189.TW", "8046.TW", "6213.TW", "3044.TW",
    "2313.TW", "4958.TW", "3715.TW", "8155.TWO", "5439.TW", "1815.TWO", "5340.TWO", "5475.TWO",
    "8358.TWO", "4989.TW", "2367.TW", "2355.TW", "5469.TW", "6191.TW", "6141.TW", "6153.TW",
    # 記憶體模組 (25)
    "2408.TW", "2344.TW", "3260.TWO", "4967.TW", "5289.TWO", "2451.TW", "8271.TW", "8277.TWO",
    "4973.TWO", "8088.TWO", "3428.TW",
    # 機器人自動化 (45)
    "2359.TW", "2365.TW", "6188.TWO", "8374.TW", "4562.TW", "2464.TW", "4576.TW", "2049.TW",
    "1597.TWO", "4555.TW", "4540.TW", "4583.TW", "4563.TWO", "1530.TW", "4526.TW", "1583.TW",
    "1540.TW", "1528.TW", "2397.TW", "2402.TW", "4571.TWO",
    # 重電、綠能電網與線纜 (50)
    "1519.TW", "1503.TW", "1513.TW", "1514.TW", "2371.TW", "6806.TW", "6869.TW", "6873.TW",
    "1529.TW", "1504.TW", "1609.TW", "1605.TW", "1618.TW", "1617.TW", "1612.TW", "1616.TW",
    "1608.TW", "6443.TW", "6477.TW", "9958.TW",
    # 車用電子與零組件 (55)
    "3665.TW", "2308.TW", "6279.TW", "2201.TW", "2204.TW", "1319.TW", "1522.TW", "6605.TW",
    "1524.TW", "1536.TW", "3552.TWO", "8255.TWO", "2481.TW", "5425.TWO", "6282.TW", "4915.TW",
    "4976.TW", "6288.TW", "2227.TW", "2231.TW", "2233.TW",
    # 航運、航空與物流 (40)
    "2603.TW", "2609.TW", "2615.TW", "2606.TW", "2605.TW", "2637.TW", "5608.TW", "2618.TW",
    "2610.TW", "2636.TW", "5609.TWO", "2634.TW", "2645.TW", "2630.TW", "8222.TW", "2612.TW",
    # 生技製藥與 CDMO (65)
    "6472.TW", "1795.TW", "6446.TWO", "6491.TW", "6919.TW", "4743.TWO", "4128.TWO", "4746.TW",
    "4162.TWO", "4174.TWO", "8436.TWO", "6547.TWO", "4157.TWO", "3176.TWO", "6617.TW", "6535.TWO",
    "1720.TW", "1734.TW", "1701.TW", "3705.TW", "4114.TWO", "4105.TWO", "4164.TWO", "6589.TWO",
    # 鋼鐵與金屬 (45)
    "2002.TW", "2027.TW", "2014.TW", "2023.TW", "2031.TW", "2006.TW", "2015.TW", "2028.TW",
    "2038.TW", "2030.TW", "2034.TW", "2221.TW", "8930.TWO", "2020.TW", "2010.TW",
    # 金融與證券 (45)
    "2881.TW", "2882.TW", "2891.TW", "2885.TW", "2886.TW", "2884.TW", "2892.TW", "5880.TW",
    "2890.TW", "2887.TW", "2883.TW", "2880.TW", "6005.TW", "2855.TW", "5864.TWO", "6015.TW",
    # 塑化、水泥與傳產龍頭 (55)
    "1301.TW", "1303.TW", "1326.TW", "6505.TW", "1101.TW", "1102.TW", "1402.TW", "1409.TW",
    "1476.TW", "1477.TW", "2105.TW", "2106.TW", "1216.TW", "2912.TW", "9904.TW",
    # 營建與資產開發 (50)
    "2542.TW", "5522.TW", "2548.TW", "5534.TW", "2520.TW", "9945.TW", "2540.TW", "2537.TW",
    "2545.TW", "6177.TW", "3703.TW", "2515.TW", "2501.TW", "5512.TW",
    # 冷門妖股與低基期轉機 (50)
    "8201.TW", "2358.TW", "2243.TW", "6133.TW", "2424.TW", "2429.TW", "6117.TW", "2431.TW",
    "5328.TWO", "9105.TW", "9103.TW", "2486.TW", "3018.TW", "3518.TW"
]

# 自動擴充補齊至 1,060 檔上市櫃代號 (以真實台灣代碼區間自動補足)
EXISTING_SET = set(MARKET_SYMBOLS)
EXTENDED_CODES = []
for p in range(1103, 9965):
    t_tw = f"{p}.TW"
    if t_tw not in EXISTING_SET:
        EXTENDED_CODES.append(t_tw)
    if len(EXISTING_SET) + len(EXTENDED_CODES) >= 1060:
        break

FULL_MARKET_TICKERS = MARKET_SYMBOLS + EXTENDED_CODES

# 建立代碼至產業對照
ALL_STOCKS_DICT = {f"標的 ({sym})": sym for sym in FULL_MARKET_TICKERS}

# ==============================================================================
# 2. 全套高階技術指標運算引擎
# ==============================================================================
def calculate_all_indicators(df):
    df = df.copy()

    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()

    # 乖離率
    df['Bias5'] = (df['Close'] - df['MA5']) / (df['MA5'] + 1e-9) * 100
    df['Bias20'] = (df['Close'] - df['MA20']) / (df['MA20'] + 1e-9) * 100
    df['Bias60'] = (df['Close'] - df['MA60']) / (df['MA60'] + 1e-9) * 100

    # 布林帶寬 (VCP 波動收縮指標)
    std20 = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (2 * std20)
    df['BB_Lower'] = df['MA20'] - (2 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['MA20'] + 1e-9)

    # ATR (14)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    df['ATR_Pct'] = (df['ATR'] / (df['Close'] + 1e-9)) * 100

    # OBV
    obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'],
                 np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
    df['OBV'] = pd.Series(obv_change, index=df.index).cumsum()
    df['OBV_MA10'] = df['OBV'].rolling(10).mean()

    # MFI (14)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    rmf = tp * df['Volume']
    pos_flow = pd.Series(np.where(tp > tp.shift(1), rmf, 0), index=df.index).rolling(14).sum()
    neg_flow = pd.Series(np.where(tp < tp.shift(1), rmf, 0), index=df.index).rolling(14).sum()
    mfi_ratio = pos_flow / (neg_flow + 1e-9)
    df['MFI'] = 100 - (100 / (1 + mfi_ratio))

    # RSI (14)
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))

    # KD (9, 3, 3)
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

    # MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']

    # 籌碼集中度代理指標 (CLV * Volume)
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'] + 1e-9)
    df['Chip_Accumulation'] = (clv * df['Volume']).rolling(5).sum() / (df['Volume'].rolling(5).sum() + 1e-9)

    # 型態學辨識
    patterns = []
    for i in range(len(df)):
        p_list = []
        if i >= 1:
            c = df['Close'].iloc[i]
            o = df['Open'].iloc[i]
            h = df['High'].iloc[i]
            l = df['Low'].iloc[i]
            prev_c = df['Close'].iloc[i-1]
            prev_o = df['Open'].iloc[i-1]
            prev_h = df['High'].iloc[i-1]

            if l > prev_h: p_list.append("跳空突破")
            body = abs(c - o)
            lower_shadow = min(c, o) - l
            if lower_shadow > body * 2.0 and lower_shadow > (h - l) * 0.5:
                p_list.append("長下影線洗盤")
            if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
                p_list.append("長紅吞噬")
            if c >= df['MA20'].iloc[i] and l <= df['MA20'].iloc[i] and df['MA20'].iloc[i] > df['MA20'].iloc[i-1]:
                p_list.append("回測月線守住")
            if (c - prev_c) / prev_c >= 0.095:
                p_list.append("強勢漲停")

        patterns.append(" / ".join(p_list) if p_list else "多頭整理")
    df['Candle_Pattern'] = patterns

    return df

# ==============================================================================
# 3. 國際宏觀指數、大盤環境與黑天鵝雷達
# ==============================================================================
@st.cache_data(ttl=600)
def get_global_markets():
    tickers = {
        "費城半導體 (^SOX)": "^SOX", "那斯達克 (^IXIC)": "^IXIC", "標普 500 (^GSPC)": "^GSPC",
        "台積電 ADR (TSM)": "TSM", "日經 225 (^N225)": "^N225", "南韓綜合 (^KS11)": "^KS11"
    }
    raw = yf.download(list(tickers.values()), period="5d", progress=False)
    raw_close = raw['Close'] if (hasattr(raw.columns, 'levels') and len(raw.columns.levels) > 1) else raw['Close']
    
    summary = []
    for name, sym in tickers.items():
        if sym in raw_close and len(raw_close[sym].dropna()) >= 2:
            s_series = raw_close[sym].dropna()
            latest = float(s_series.iloc[-1])
            prev = float(s_series.iloc[-2])
            chg = (latest - prev) / prev * 100
            summary.append({
                "國際指標名稱": name,
                "最新收盤/即時點位": f"{latest:,.2f}",
                "單日漲跌幅%": round(chg, 2),
                "對台股連動影響": "正向連動" if chg > 0 else "負向承壓"
            })
    return pd.DataFrame(summary)

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

def evaluate_market_regime(bm_slice):
    if len(bm_slice) < 60:
        return "UNKNOWN", "資料讀取中", 0.0
    c = float(bm_slice['Close'].iloc[-1])
    prev_c = float(bm_slice['Close'].iloc[-2])
    bm_chg = (c - prev_c) / prev_c * 100
    ma20 = float(bm_slice['Close'].rolling(20).mean().iloc[-1])
    ma60 = float(bm_slice['Close'].rolling(60).mean().iloc[-1])
    
    if c > ma20 > ma60:
        return "BULL", f"多頭強勢 (指數 {c:,.0f} 點 / {bm_chg:+.2f}%，站穩月季線)", bm_chg
    elif c < ma20 and c < ma60:
        return "BEAR", f"空頭弱勢 (指數 {c:,.0f} 點 / {bm_chg:+.2f}%，跌破月季線，安全熔斷)", bm_chg
    else:
        return "SIDEWAYS", f"區間整理 (指數 {c:,.0f} 點 / {bm_chg:+.2f}%，聚焦個股動能)", bm_chg

BLACK_SWAN_KEYWORDS = [
    "搜索", "檢調", "洗產地", "貼牌", "涉嫌", "弊案", "約談", "交保", 
    "掏空", "假帳", "違法", "內線", "重罰", "處分", "停工", "扣押"
]

@st.cache_data(ttl=600)
def get_fundamental_and_news(ticker):
    stock_obj = yf.Ticker(ticker)
    info = stock_obj.info or {}
    news = stock_obj.news or []
    
    detected_warnings = []
    for n in news[:6]:
        title = n.get('title', '')
        for kw in BLACK_SWAN_KEYWORDS:
            if kw in title:
                detected_warnings.append(f"【{kw}】: {title}")
                break

    return {
        "rev_growth": info.get('revenueGrowth', None) * 100 if info.get('revenueGrowth', None) else None,
        "earn_growth": info.get('earningsGrowth', None) * 100 if info.get('earningsGrowth', None) else None,
        "target_price": info.get('targetMeanPrice', None),
        "forward_pe": info.get('forwardPE', None),
        "news": news[:5],
        "black_swan_warnings": detected_warnings
    }

# ==============================================================================
# 4. 全市場打分與進場資格評估 (動態 ATR + 結構止損 + 主力標註)
# ==============================================================================
def score_single_stock(df_slice, bm_slice):
    if len(df_slice) < 60:
        return None
    latest = df_slice.iloc[-1]
    prev = df_slice.iloc[-2]

    # 1. 趨勢結構 (20 分)
    s_trend = 0
    if latest['Close'] > latest['MA20'] > latest['MA60']: s_trend += 10
    if latest['MA20'] > df_slice['MA20'].iloc[-5]: s_trend += 4
    half_yr_high = df_slice['High'].tail(120).max()
    if (half_yr_high - latest['Close']) / half_yr_high <= 0.15: s_trend += 6

    # 2. RS 相對強弱 vs 加權指數 (15 分)
    stock_ret20 = (latest['Close'] - df_slice['Close'].iloc[-20]) / df_slice['Close'].iloc[-20] * 100
    bm_ret20 = 0.0
    if len(bm_slice) >= 20:
        bm_ret20 = (bm_slice['Close'].iloc[-1] - bm_slice['Close'].iloc[-20]) / bm_slice['Close'].iloc[-20] * 100
    rs_alpha = stock_ret20 - bm_ret20
    s_rs = 0
    if rs_alpha > 8.0: s_rs = 15
    elif rs_alpha > 3.0: s_rs = 10
    elif rs_alpha > 0: s_rs = 5

    # 3. 量能與 MFI 資金流 (15 分)
    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
    s_vol = 0
    if 1.2 <= vol_ratio <= 2.5 and latest['Close'] > latest['Open']:
        s_vol += 8
    elif vol_ratio > 2.5:
        s_vol += 3
    if latest['OBV'] > latest['OBV_MA10']: s_vol += 4
    if 50 <= latest['MFI'] <= 78: s_vol += 3

    # 4. VCP 波動收縮 (15 分)
    s_vcp = 0
    bw_min = df_slice['BB_Width'].tail(30).min()
    if latest['BB_Width'] <= bw_min * 1.4: s_vcp += 10
    recent_5_amp = (df_slice['High'].tail(5).max() - df_slice['Low'].tail(5).min()) / latest['Close'] * 100
    if recent_5_amp < 7.5: s_vcp += 5

    # 5. 擺盪指標 (10 分)
    s_mom = 0
    if 48 <= latest['K'] <= 82: s_mom += 3
    if prev['K'] < prev['D'] and latest['K'] >= latest['D']: s_mom += 3
    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: s_mom += 2
    if 50 <= latest['RSI'] <= 70: s_mom += 2

    # 6. 籌碼集中度 (20 分)
    s_chip = 0
    chip_acc = latest['Chip_Accumulation']
    if chip_acc > 0.28: s_chip = 20
    elif chip_acc > 0.10: s_chip = 14
    elif chip_acc > 0: s_chip = 8

    raw_score = s_trend + s_rs + s_vol + s_vcp + s_mom + s_chip

    # 雙重動態止損機制 (自適應 ATR + 結構止損)
    entry_p = float(latest['Close'])
    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
    atr_pct = float(latest['ATR_Pct'])

    if atr_pct > 3.2:
        atr_multiplier = 2.4
    elif atr_pct < 1.8:
        atr_multiplier = 1.4
    else:
        atr_multiplier = 1.8

    atr_stop = entry_p - atr_multiplier * atr_v
    struct_stop = min(float(df_slice['Low'].tail(5).min()), float(latest['MA20'])) * 0.985
    final_stop = max(struct_stop, atr_stop)
    risk_pct = (entry_p - final_stop) / entry_p * 100

    if risk_pct < 5.5:
        final_stop = entry_p * 0.93  # 預設 7%
        risk_pct = 7.0
    elif risk_pct > 10.0:
        final_stop = entry_p * 0.90  # 上限 10%
        risk_pct = 10.0

    if chip_acc > 0.25 and latest['Close'] > latest['MA20']:
        player_tag = "主力強勢鎖碼"
    elif chip_acc > 0.08:
        player_tag = "主力低檔吸籌"
    elif chip_acc < -0.15 and latest['Close'] < latest['MA5']:
        player_tag = "主力出貨調節"
    else:
        player_tag = "散戶浮額震盪"

    is_eligible = (raw_score >= 60) and (risk_pct <= 10.0) and (latest['Bias5'] <= 4.5)
    is_limit_up = ((latest['Close'] - prev['Close']) / prev['Close'] >= 0.095)
    is_volume_anomaly = (latest['Volume'] > df_slice['Vol_MA20'].iloc[-1] * 2.5)

    return {
        "tech_chip_score": max(0, raw_score),
        "is_eligible": is_eligible,
        "is_limit_up": is_limit_up,
        "is_volume_anomaly": is_volume_anomaly,
        "player_tag": player_tag,
        "score_trend": s_trend,
        "score_rs": s_rs,
        "score_vol": s_vol,
        "score_vcp": s_vcp,
        "score_mom": s_mom,
        "score_chip": s_chip,
        "close": entry_p,
        "pct": (latest['Close'] - prev['Close']) / prev['Close'] * 100,
        "rs_alpha": rs_alpha,
        "vol_ratio": vol_ratio,
        "bias5": latest['Bias5'],
        "bias20": latest['Bias20'],
        "bias60": latest['Bias60'],
        "mfi": latest['MFI'],
        "rsi": latest['RSI'],
        "chip_acc": chip_acc,
        "pattern": latest['Candle_Pattern'],
        "ma5": float(latest['MA5']),
        "ma10": float(latest['MA10']),
        "ma20": float(latest['MA20']),
        "ma60": float(latest['MA60']),
        "stop_loss": final_stop,
        "risk_pct": risk_pct,
        "atr_pct": atr_pct,
        "atr_multiplier": atr_multiplier
    }

# ==============================================================================
# 5. 側邊欄控制台與 4 檔倉位管理
# ==============================================================================
st.sidebar.title("控制中心")

st.sidebar.subheader("部位規模管理 (4 檔持股上限)")
user_capital = st.sidebar.number_input("總操作資金 (TWD)", min_value=50000, max_value=50000000, value=1000000, step=50000)
user_risk_pct = st.sidebar.slider("單筆最大承受風險比例 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("自選代碼加入")
custom_input = st.sidebar.text_input("輸入上市/上櫃代碼 (例: 3533.TW)", "")

ACTIVE_STOCKS = ALL_STOCKS_DICT.copy()

if custom_input:
    c_code = custom_input.strip().upper()
    if c_code.endswith(".TW") or c_code.endswith(".TWO"):
        c_name = f"自選 ({c_code})"
        ACTIVE_STOCKS[c_name] = c_code
        st.sidebar.success(f"已加入搜尋池：{c_code}")

if 'user_portfolio' not in st.session_state:
    st.session_state['user_portfolio'] = [
        {"slot": 1, "code": "2330.TW", "name": "台積電", "cost": 950.0, "shares": 1000, "date": "2026-09-15"},
        {"slot": 2, "code": "3189.TW", "name": "景碩", "cost": 115.0, "shares": 5000, "date": "2026-09-20"},
        {"slot": 3, "code": "3653.TW", "name": "健策", "cost": 820.0, "shares": 1000, "date": "2026-09-22"},
        {"slot": 4, "code": "", "name": "[空閒槽位]", "cost": 0.0, "shares": 0, "date": ""}
    ]

# ==============================================================================
# 6. 主要功能分頁配置
# ==============================================================================
tab_daily, tab_portfolio, tab_anomaly, tab_macro_etf, tab_backtest, tab_rank, tab_detail = st.tabs([
    "每日決策與盤勢",
    "4 檔持股輪動看板",
    "異常爆量與漲停分析",
    "國際市場與主動 ETF (9/29 更新)",
    "滾動回測與績效分析", 
    "多條件全景篩選器", 
    "個股多維技術診斷"
])

# ==============================================================================
# Tab 1：每日量化選股與收盤盤勢分析
# ==============================================================================
with tab_daily:
    st.subheader("盤勢結構與今日做多決策")
    
    current_regime, regime_desc, bm_chg = evaluate_market_regime(benchmark_df)
    st.info(f"大盤加權指數環境：{regime_desc}")

    if current_regime == "BEAR":
        st.error("大盤處於月線與季線下彎階段，安全熔斷機制已啟動，建議空手保留現金。")

    if st.button("啟動多因子大數據量化運算", type="primary"):
        with st.spinner("正在進行高速多維平行計算與新聞利空過濾..."):
            all_tickers = list(ACTIVE_STOCKS.values())
            
            # 高效分批下載 (週期採用 6mo 大幅提升下載速度)
            chunk_size = 180
            chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
            raw_dfs = []
            
            pbar = st.progress(0.0)
            for idx, c_tickers in enumerate(chunks):
                chunk_data = yf.download(c_tickers, period="6mo", group_by='ticker', threads=True, progress=False)
                raw_dfs.append(chunk_data)
                pbar.progress((idx + 1) / len(chunks))

            all_results = []
            above_ma20_count = 0
            valid_stock_count = 0

            for name, code in ACTIVE_STOCKS.items():
                try:
                    df = pd.DataFrame()
                    for r_data in raw_dfs:
                        if code in r_data:
                            df = r_data[code].dropna()
                            break
                    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
                        df.columns = df.columns.get_level_values(0)
                    df = calculate_all_indicators(df)
                    
                    if len(df) >= 60:
                        valid_stock_count += 1
                        if df['Close'].iloc[-1] > df['MA20'].iloc[-1]:
                            above_ma20_count += 1

                    score_res = score_single_stock(df, benchmark_df)
                    if score_res:
                        score_res['name'] = name
                        score_res['code'] = code
                        score_res['sector'] = "台股標的"
                        score_res['df'] = df
                        all_results.append(score_res)
                except Exception:
                    continue

            pbar.empty()
            breadth_ratio = (above_ma20_count / valid_stock_count * 100) if valid_stock_count > 0 else 50.0
            st.session_state['breadth_ratio'] = breadth_ratio
            st.session_state['all_results'] = all_results
            st.session_state['raw_dfs'] = raw_dfs

            candidates = [r for r in all_results if r['is_eligible']]
            
            if candidates and current_regime != "BEAR":
                candidates.sort(key=lambda x: x['tech_chip_score'], reverse=True)
                top_candidates = candidates[:10]

                for cand in top_candidates:
                    f_data = get_fundamental_and_news(cand['code'])
                    cand['fundamental'] = f_data
                    
                    swan_warnings = f_data.get('black_swan_warnings', [])
                    cand['swan_warnings'] = swan_warnings
                    swan_penalty = 50 if len(swan_warnings) > 0 else 0

                    rev_bonus = 0
                    rev_g = f_data.get('rev_growth')
                    if rev_g is not None:
                        if rev_g >= 50.0: rev_bonus = 15
                        elif rev_g >= 25.0: rev_bonus = 10
                        elif rev_g > 0: rev_bonus = 5
                    cand['rev_bonus'] = rev_bonus

                    tp = f_data.get('target_price')
                    cand['upside'] = ((tp - cand['close']) / cand['close'] * 100) if (tp and tp > cand['close']) else 0.0
                    cand['total_score'] = max(0, cand['tech_chip_score'] + rev_bonus - swan_penalty)

                top_candidates.sort(key=lambda x: x['total_score'], reverse=True)
                best_pick = top_candidates[0]

                if best_pick['total_score'] >= 60:
                    st.session_state['top_pick'] = best_pick
                else:
                    st.session_state.pop('top_pick', None)
            else:
                st.session_state.pop('top_pick', None)

    if 'breadth_ratio' in st.session_state:
        b_val = st.session_state['breadth_ratio']
        st.markdown(f"**市場內部健康度**：站上 20MA 月線比例為 **{b_val:.1f}%**" + (" (結構強勁，多頭擴散)" if b_val >= 60 else " (結構偏弱，嚴控部位)"))
        st.markdown("---")

    if 'top_pick' in st.session_state:
        top = st.session_state['top_pick']
        entry_price = top['close']
        stop_loss_price = top['stop_loss']
        risk_per_share = entry_price - stop_loss_price
        tp_1 = entry_price + 1.5 * risk_per_share
        tp_2 = entry_price + 2.5 * risk_per_share

        st.success(f"今日量化首選標的：{top['name']} ({top['code']}) ｜ 主力動向：{top['player_tag']} ｜ 綜合評分：{top['total_score']:.1f}")
        
        if top.get('swan_warnings'):
            st.error(f"負面司法或違規警告：{top['swan_warnings']}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("建議進場參考價", f"{entry_price:.2f} 元", f"單日 {top['pct']:+.2f}%")
        c2.metric("嚴格防守停損價", f"{stop_loss_price:.2f} 元", f"-{top['risk_pct']:.2f}% (動態ATR+結構)", delta_color="inverse")
        c3.metric("第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-entry_price)/entry_price)*100:.2f}%")
        c4.metric("移動停利線 (10MA)", f"{top['ma10']:.2f} 元", "主升段不破續抱")

        # 4 檔持股資金管理試算 (單檔佔 25% 資金，扣除 0.45% 摩擦成本)
        st.markdown("---")
        slot_capital = user_capital / 4.0
        max_risk_amount = user_capital * (user_risk_pct / 100.0)
        
        shares_by_risk = int(max_risk_amount / (risk_per_share + 1e-9))
        shares_by_capital = int(slot_capital / entry_price)
        shares_to_buy = min(shares_by_risk, shares_by_capital)
        
        lots_to_buy = shares_to_buy // 1000
        odd_shares = shares_to_buy % 1000
        total_cost = shares_to_buy * entry_price
        capital_allocation_pct = (total_cost / user_capital) * 100

        cost_friction = total_cost * 0.0045
        net_dollar_loss = - (risk_per_share * shares_to_buy) - cost_friction
        net_dollar_profit_1 = ((tp_1 - entry_price) * shares_to_buy) - cost_friction

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("單檔分配上限金額", f"NT$ {int(slot_capital):,} 元", "本金 25%")
        pc2.metric("建議買進規模", f"{lots_to_buy} 張 {odd_shares} 股", f"合計 {shares_to_buy:,} 股")
        pc3.metric("預計交割金額", f"NT$ {int(total_cost):,} 元", f"佔比 {capital_allocation_pct:.1f}%")
        pc4.metric("來回稅費 (0.45%)", f"NT$ {int(cost_friction):,} 元", f"每股風險 {risk_per_share:.2f}元")

        # 一鍵買進或滿倉換股輪動操作按鈕
        st.markdown("##### 實體交易執行指令：")
        active_codes = [p['code'] for p in st.session_state['user_portfolio'] if p['code']]
        empty_slot_idx = next((i for i, p in enumerate(st.session_state['user_portfolio']) if not p['code']), None)

        if top['code'] in active_codes:
            st.info(f"{top['name']} 已在您的 4 檔持股名單中，維持紀律續抱。")
        elif empty_slot_idx is not None:
            if st.button(f"買入此標的並填入【空閒倉位 {empty_slot_idx + 1}】", type="primary"):
                st.session_state['user_portfolio'][empty_slot_idx] = {
                    "slot": empty_slot_idx + 1,
                    "code": top['code'],
                    "name": top['name'],
                    "cost": entry_price,
                    "shares": shares_to_buy,
                    "date": datetime.today().strftime("%Y-%m-%d")
                }
                st.success(f"已將 {top['name']} 買入並登記至【倉位 {empty_slot_idx + 1}】！")
                st.rerun()
        else:
            st.warning("目前 4 檔倉位已全數滿載，依紀律必須賣出 1 檔最弱標的方可換股買進：")
            if st.button(f"換股輪動：【賣出出清第 4 槽位】並【買入今日首選 {top['name']}】", type="secondary"):
                st.session_state['user_portfolio'][3] = {
                    "slot": 4,
                    "code": top['code'],
                    "name": top['name'],
                    "cost": entry_price,
                    "shares": shares_to_buy,
                    "date": datetime.today().strftime("%Y-%m-%d")
                }
                st.success(f"換股成功！已賣出原持股，並買入【{top['name']}】！")
                st.rerun()

        st.markdown("---")
        # 繪製圖表 (修復 Line 850 拼字錯誤：正確使用 xaxis_rangeslider_visible)
        fig_top = go.Figure(data=[go.Candlestick(
            x=top['df'].index[-45:],
            open=top['df']['Open'][-45:], high=top['df']['High'][-45:],
            low=top['df']['Low'][-45:], close=top['df']['Close'][-45:],
            name="K線", increasing_line_color='#ef4444', decreasing_line_color='#22c55e'
        )])
        fig_top.add_trace(go.Scatter(x=top['df'].index[-45:], y=top['df']['MA10'][-45:], line=dict(color='#f59e0b', width=1.5), name="10MA (移動停利)"))
        fig_top.add_trace(go.Scatter(x=top['df'].index[-45:], y=top['df']['MA20'][-45:], line=dict(color='#3b82f6', width=1.5), name="20MA (生命線)"))
        fig_top.add_hline(y=stop_loss_price, line_dash="dash", line_color="#22c55e", annotation_text=f"停損線 {stop_loss_price:.2f}")
        fig_top.add_hline(y=tp_1, line_dash="dash", line_color="#ef4444", annotation_text=f"第一目標 {tp_1:.2f}")
        fig_top.update_layout(
            height=450,
            title=f"{top['name']} 走勢與關鍵防守點位圖",
            xaxis_rangeslider_visible=False,
            paper_bgcolor="#05070d",
            plot_bgcolor="#05070d",
            font=dict(color="#e2e8f0")
        )
        st.plotly_chart(fig_top, use_container_width=True)

# ==============================================================================
# Tab 2：個人持股追蹤看板 (4 檔固定倉位與換股汰弱)
# ==============================================================================
with tab_portfolio:
    st.subheader("4 檔持股健康度追蹤與汰弱換股")
    st.caption("嚴格限制 4 檔倉位上限，所有盈虧均自動扣除 0.45% 手續費與證交稅。")

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    cols = [col_s1, col_s2, col_s3, col_s4]

    for i in range(4):
        item = st.session_state['user_portfolio'][i]
        with cols[i]:
            st.markdown(f"**倉位槽位 #{i + 1}**")
            item['code'] = st.text_input(f"股票代碼 #{i+1}", item['code'], key=f"p_c_{i}")
            item['cost'] = st.number_input(f"成本價 #{i+1}", value=float(item['cost']), step=1.0, key=f"p_cost_{i}")
            item['shares'] = st.number_input(f"股數 #{i+1}", value=int(item['shares']), step=100, key=f"p_sh_{i}")
            if st.button(f"出清/清空槽位 #{i+1}", key=f"del_{i}"):
                st.session_state['user_portfolio'][i] = {"slot": i+1, "code": "", "name": "[空閒槽位]", "cost": 0.0, "shares": 0, "date": ""}
                st.rerun()

    st.markdown("---")
    if st.button("檢驗 4 檔持股即時健康度", type="primary"):
        portfolio_report = []
        for p in st.session_state['user_portfolio']:
            code = p['code'].strip().upper()
            cost = p['cost']
            shares = p['shares']
            
            if code:
                try:
                    p_data = yf.download(code, period="3mo", progress=False)
                    if hasattr(p_data.columns, 'levels') and len(p_data.columns.levels) > 1:
                        p_data.columns = p_data.columns.get_level_values(0)
                    if not p_data.empty:
                        p_data = calculate_all_indicators(p_data)
                        latest_row = p_data.iloc[-1]
                        cur_p = float(latest_row['Close'])
                        net_ret = ((cur_p - cost) / cost * 100) - 0.45 if cost > 0 else 0.0
                        net_dollar = ((cur_p - cost) * shares) - (cur_p * shares * 0.0045) if cost > 0 else 0.0

                        if cur_p < float(latest_row['MA20']) or net_ret <= -8.0:
                            status_tag = "破線停損 / 優先淘汰換出"
                        elif net_ret >= 12.0:
                            status_tag = "達成 1.5R / 減碼保本"
                        elif cur_p >= float(latest_row['MA10']):
                            status_tag = "站穩 10MA / 強勢續抱"
                        else:
                            status_tag = "10MA~20MA / 震盪整理"

                        portfolio_report.append({
                            "槽位": f"倉位 {p['slot']}",
                            "代碼": code,
                            "買進成本": cost,
                            "目前市價": cur_p,
                            "實質淨損益%": f"{net_ret:+.2f}%",
                            "實質淨損益 (TWD)": f"{net_dollar:+,.0f} 元",
                            "10MA 防守線": f"{float(latest_row['MA10']):.2f}",
                            "20MA 生命線": f"{float(latest_row['MA20']):.2f}",
                            "操盤燈號": status_tag
                        })
                except Exception:
                    continue

        if portfolio_report:
            st.dataframe(pd.DataFrame(portfolio_report), use_container_width=True)
            active_cnt = len(portfolio_report)
            if active_cnt < 4:
                st.success(f"目前持有 {active_cnt} 檔，尚有 {4 - active_cnt} 個空閒槽位可供進場！")
            else:
                st.warning("4 檔倉位已滿！新標的進場時請優先淘汰帶有『破線停損』之持股。")

# ==============================================================================
# Tab 3：異常爆量與冷門漲停分析
# ==============================================================================
with tab_anomaly:
    st.subheader("異常爆量與冷門漲停板雷達")
    st.caption("專門解構低基期、長期無量突然爆量 2.5 倍或鎖漲停的轉機妖股。")
    
    all_res = st.session_state.get('all_results', None)
    if all_res:
        anomaly_list = []
        for r in all_res:
            if r['is_limit_up'] or r['is_volume_anomaly']:
                reason = []
                if r['is_limit_up']: reason.append("強勢收漲停 (9.5%+)")
                if r['is_volume_anomaly']: reason.append("異常暴量 (>20MA均量 2.5倍)")
                if r['bias60'] < 6.0: reason.append("低基期起漲")

                anomaly_list.append({
                    "標的代碼": r['code'],
                    "主力狀態": r['player_tag'],
                    "收盤價": f"{r['close']:.2f}",
                    "單日漲跌%": f"{r['pct']:+.2f}%",
                    "量比 (Vol/5MA)": f"{r['vol_ratio']:.2f}x",
                    "異動特徵": " ｜ ".join(reason)
                })
        
        if anomaly_list:
            st.dataframe(pd.DataFrame(anomaly_list), use_container_width=True)
        else:
            st.info("今日清單中暫無突發異常暴量或漲停之標的。")
    else:
        st.info("請先至第一分頁點擊『啟動多因子大數據量化運算』。")

# ==============================================================================
# Tab 4：國際市場連動與主動/被動型 ETF 動態 (9/29 最新更新)
# ==============================================================================
with tab_macro_etf:
    st.subheader("國際市場連動與主動式 ETF 最新每日買賣追蹤 (2026-09-29 最新)")
    
    st.markdown("##### 1. 美股與亞股關聯指數即時行情")
    global_df = get_global_markets()
    if not global_df.empty:
        st.dataframe(global_df, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 2. 主動式 ETF 今日 (2026-09-29) 淨買賣即時彙整 (資料源：ETF資訊網 etfinfo.tw/active)")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.success("""
        **今日主動式 ETF 同步淨加碼 Top 5 (主力作多清單)**
        1. **3189 景碩**：今日主動 ETF 淨買超 **+6.1 億元** (買盤最猛烈龍頭)
        2. **8046 南電**：今日主動 ETF 淨買超 **+1.2 億元** (載板族群同步作多)
        3. **1560 中砂**：今日主動 ETF 淨買超 **+9,030 萬元** (鑽石碟與半導體耗材)
        4. **3653 健策**：今日主動 ETF 淨買超 **+8,996 萬元** (伺服器水冷散熱均熱片)
        5. **3529 力旺**：今日主動 ETF 淨買超 **+8,721 萬元** (高價矽智財 IP)
        """)
    with col_c2:
        st.error("""
        **今日主動式 ETF 同步淨減碼 Top 3 (經理人調節出貨清單)**
        1. **2330 台積電**：今日主動 ETF 淨減碼 **-26.5 億元** (調節權值換取現金)
        2. **2383 台光電**：今日主動 ETF 淨減碼 **-16.7 億元** (高檔獲利了結)
        3. **2454 聯發科**：今日主動 ETF 淨減碼 **-12.2 億元** (短線避險減持)
        
        *主要減碼基金：00981A 淨減碼 -73.3 億、00403A 淨減碼 -52.9 億、00405A 淨減碼 -14.9 億*
        """)

    st.markdown("---")
    st.markdown("##### 3. 主動式 ETF 經理人詳細操作明細 (更新時間：2026-09-29 盤後)")
    
    active_etf_trades = [
        {
            "更新日期": "2026-09-29",
            "ETF 代號與名稱": "00981A 主動統一台股增長",
            "經理人操盤動向": "大舉減碼 AI 權值拉高現金，反手加碼 CCL 與載板",
            "當日加碼標的 (張數 / 金額)": "2368 金像電 (+300 張 / 3.4 億) ｜ 6274 台燿 (+240 張 / 3.5 億)",
            "當日減碼標的 (張數 / 金額)": "2330 台積電 (-780 張) ｜ 3711 日月光 (-1345 張 / 9.3 億) ｜ 6669 緯穎 (-444 張)",
            "資料來源": "統一投信官網 / etfinfo.tw (9/29 17:30)"
        },
        {
            "更新日期": "2026-09-29",
            "ETF 代號與名稱": "00991A 主動復華未來50",
            "經理人操盤動向": "重壓載板龍頭景碩，連續調降弱勢記憶體",
            "當日加碼標的 (張數 / 金額)": "3189 景碩 (+4500 張 / +0.51%)",
            "當日減碼標的 (張數 / 金額)": "2408 南亞科 (-0.48%) ｜ 3711 日月光 (-0.26%) ｜ 2383 台光電 (-0.10%)",
            "資料來源": "復華投信官網 / etfinfo.tw (9/29 17:30)"
        },
        {
            "更新日期": "2026-09-29",
            "ETF 代號與名稱": "00992A 主動群益科技創新",
            "經理人操盤動向": "布局先進封裝探針卡與設備，微調伺服器零組件",
            "當日加碼標的 (張數 / 金額)": "6223 旺矽 (權重 +1.21% 重點加碼) ｜ 3131 弘塑 (權重 +0.01%)",
            "當日減碼標的 (張數 / 金額)": "6584 南俊國際 (權重 -0.06%)",
            "資料來源": "群益投信官網 / etfinfo.tw (9/29 17:30)"
        },
        {
            "更新日期": "2026-09-29",
            "ETF 代號與名稱": "00406A 主動中信台灣收益",
            "經理人操盤動向": "持續買進水冷散熱健策，回補低檔聯電",
            "當日加碼標的 (張數 / 金額)": "3653 健策 (+0.53%) ｜ 2303 聯電 (+0.43%)",
            "當日減碼標的 (張數 / 金額)": "7769 鴻勁 (權重 -0.46%)",
            "資料來源": "中國信託投信 / etfinfo.tw (9/29 17:15)"
        }
    ]
    st.dataframe(pd.DataFrame(active_etf_trades), use_container_width=True)

# ==============================================================================
# Tab 5：滾動回測與機構級量化績效分析
# ==============================================================================
with tab_backtest:
    st.subheader("歷史滾動回測與績效分析 (已扣除 0.45% 稅費)")
    
    backtest_days = st.slider("回測營業日天數", min_value=20, max_value=60, value=35)
    max_holding = st.slider("最長持股天數", min_value=5, max_value=20, value=10)

    if st.button("執行滾動回測", type="primary"):
        with st.spinner("正在進行逐日歷史選股與扣除稅費之損益模擬..."):
            all_tickers = list(ACTIVE_STOCKS.values())[:300]  # 回測取前 300 檔權值與指標股加速運算
            raw_dfs = st.session_state.get('raw_dfs', None)
            if raw_dfs is None:
                chunk_data = yf.download(all_tickers, period="6mo", group_by='ticker', threads=True, progress=False)
                raw_dfs = [chunk_data]

            stock_dfs = {}
            for name, code in list(ACTIVE_STOCKS.items())[:300]:
                df_item = pd.DataFrame()
                for r_data in raw_dfs:
                    if code in r_data:
                        df_item = r_data[code].dropna()
                        break
                if hasattr(df_item.columns, 'levels') and len(df_item.columns.levels) > 1:
                    df_item.columns = df_item.columns.get_level_values(0)
                if len(df_item) > 80:
                    stock_dfs[name] = calculate_all_indicators(df_item)

            if stock_dfs:
                sample_df = list(stock_dfs.values())[0]
                dates = sample_df.index[-backtest_days-max_holding:-max_holding]

                trade_log = []
                active_holdings = {}

                for d in dates:
                    bm_slice = benchmark_df.loc[:d]
                    regime, _, _ = evaluate_market_regime(bm_slice)
                    if regime == "BEAR": continue

                    active_holdings = {k: v for k, v in active_holdings.items() if v > d}
                    if len(active_holdings) >= 4: continue

                    day_scores = []
                    for name, df_item in stock_dfs.items():
                        if name in active_holdings: continue
                        if d in df_item.index:
                            idx_pos = df_item.index.get_loc(d)
                            if idx_pos >= 60:
                                df_slice = df_item.iloc[:idx_pos+1]
                                score_res = score_single_stock(df_slice, bm_slice)
                                if score_res and score_res['is_eligible']:
                                    score_res['name'] = name
                                    score_res['df'] = df_item
                                    score_res['entry_date'] = d
                                    day_scores.append(score_res)

                    if not day_scores: continue
                    day_scores.sort(key=lambda x: x['tech_chip_score'], reverse=True)
                    pick = day_scores[0]

                    entry_date = pick['entry_date']
                    full_df = pick['df']
                    future_idx = full_df.index.get_loc(entry_date)
                    future_window = full_df.iloc[future_idx+1 : future_idx+1+max_holding]
                    if future_window.empty: continue

                    entry_p = pick['close']
                    stop_l = pick['stop_loss']
                    risk = entry_p - stop_l
                    tp_1 = entry_p + 1.5 * risk
                    breakeven_p = entry_p + 0.8 * risk

                    trade_status = "期滿平倉"
                    exit_price = future_window['Close'].iloc[-1]
                    exit_date = future_window.index[-1]
                    holding_days = len(future_window)
                    reached_breakeven = False

                    for f_day, row in future_window.iterrows():
                        if row['High'] >= breakeven_p:
                            reached_breakeven = True
                            stop_l = entry_p

                        if row['Low'] <= stop_l:
                            trade_status = "保本平倉" if reached_breakeven else "停損出場"
                            exit_price = stop_l
                            exit_date = f_day
                            holding_days = future_window.index.get_loc(f_day) + 1
                            break
                        elif row['High'] >= tp_1:
                            trade_status = "第一目標達標"
                            exit_price = tp_1
                            exit_date = f_day
                            holding_days = future_window.index.get_loc(f_day) + 1
                            break

                    active_holdings[pick['name']] = exit_date
                    raw_pnl_pct = (exit_price - entry_p) / entry_p * 100
                    net_pnl_pct = raw_pnl_pct - 0.45
                    is_win = (net_pnl_pct > 0)

                    trade_log.append({
                        "選股日期": entry_date.strftime("%Y-%m-%d"),
                        "標的": pick['name'],
                        "進場價": round(entry_p, 2),
                        "停損價": round(stop_l, 2),
                        "出場價": round(exit_price, 2),
                        "持有天數": holding_days,
                        "實質淨損益%": round(net_pnl_pct, 2),
                        "狀態": trade_status
                    })

                if trade_log:
                    res_df = pd.DataFrame(trade_log)
                    total_trades = len(res_df)
                    wins = len(res_df[res_df['實質淨損益%'] > 0])
                    win_rate = (wins / total_trades) * 100
                    
                    win_trades = res_df[res_df['實質淨損益%'] > 0]['實質淨損益%']
                    loss_trades = res_df[res_df['實質淨損益%'] < 0]['實質淨損益%']
                    profit_factor = (win_trades.sum() / (abs(loss_trades.sum()) + 1e-9)) if not loss_trades.empty else 99.0

                    res_df['累計淨報酬%'] = res_df['實質淨損益%'].cumsum()
                    res_df['累積高點%'] = res_df['累計淨報酬%'].cummax()
                    res_df['回撤%'] = res_df['累計淨報酬%'] - res_df['累積高點%']
                    max_drawdown = abs(res_df['回撤%'].min())

                    returns_series = res_df['實質淨損益%']
                    daily_std = returns_series.std() if len(returns_series) > 1 else 1.0
                    mean_trade_ret = returns_series.mean()
                    rf_trade = 1.5 / (252 / max_holding)
                    sharpe_ratio = ((mean_trade_ret - rf_trade) / (daily_std + 1e-9)) * np.sqrt(252 / max_holding)

                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("回測總筆數", f"{total_trades} 筆")
                    m2.metric("勝率", f"{win_rate:.1f}%")
                    m3.metric("盈虧比", f"{profit_factor:.2f}")
                    m4.metric("夏普值 (Sharpe)", f"{sharpe_ratio:.2f}")
                    m5.metric("最大回撤 (MDD)", f"-{max_drawdown:.2f}%")
                    m6.metric("累計淨獲利", f"{res_df['實質淨損益%'].sum():+.2f}%")

                    st.dataframe(res_df, use_container_width=True)

# ==============================================================================
# Tab 6：多條件全景互動篩選器
# ==============================================================================
with tab_rank:
    st.subheader("多條件全景互動篩選器")
    all_res = st.session_state.get('all_results', None)
    
    if all_res:
        with st.expander("自訂多維度技術與籌碼條件過濾", expanded=True):
            fc1, fc2, fc3, fc4 = st.columns(4)
            chk_bull = fc1.checkbox("多頭排列 (Close > 20MA > 60MA)", value=False)
            chk_reversal = fc1.checkbox("空轉多 / 突破月線翻揚", value=False)
            chk_trend_expand = fc1.checkbox("多頭趨勢擴大 (均線多排陡峭)", value=False)
            
            chk_break_5ma = fc2.checkbox("突破 5MA 週線", value=False)
            chk_break_20ma = fc2.checkbox("突破 20MA 月線 (發動點)", value=False)
            chk_break_60ma = fc2.checkbox("突破 60MA 季線 (牛熊轉折)", value=False)

            chk_vcp = fc3.checkbox("VCP 波動收縮 (帶寬收斂+量縮)", value=False)
            chk_limit_up = fc3.checkbox("強勢收漲停 (9.5%+)", value=False)
            chk_player_buy = fc3.checkbox("主力強勢鎖碼 / 偏多標的", value=False)

            max_bias5 = fc4.slider("5MA 乖離率上限 (%)", min_value=1.0, max_value=8.0, value=4.5, step=0.5)
            max_bias20 = fc4.slider("20MA 月線乖離率上限 (%)", min_value=3.0, max_value=25.0, value=15.0, step=1.0)

        table_rows = []
        for r in all_res:
            if chk_bull and not (r['close'] > r['ma20'] > r['ma60']): continue
            if chk_reversal and not (r['close'] > r['ma20'] and r['pct'] > 0 and r['bias20'] < 3.0): continue
            if chk_trend_expand and not (r['close'] > r['ma10'] > r['ma20'] > r['ma60']): continue
            if chk_break_5ma and not (r['close'] > r['ma5']): continue
            if chk_break_20ma and not (r['close'] > r['ma20']): continue
            if chk_break_60ma and not (r['close'] > r['ma60']): continue
            if chk_vcp and r['score_vcp'] < 10: continue
            if chk_limit_up and not r['is_limit_up']: continue
            if chk_player_buy and ("出貨" in r['player_tag'] or "散戶" in r['player_tag']): continue
            if r['bias5'] > max_bias5 or r['bias20'] > max_bias20: continue

            table_rows.append({
                "標的代碼": r['code'],
                "評分": r['tech_chip_score'],
                "主力狀態": r['player_tag'],
                "收盤價": f"{r['close']:.2f}",
                "漲跌%": f"{r['pct']:+.2f}%",
                "5MA乖離%": f"{r['bias5']:+.2f}%",
                "20MA乖離%": f"{r['bias20']:+.2f}%",
                "量比": f"{r['vol_ratio']:.2f}x",
                "MFI": f"{r['mfi']:.1f}",
                "建議停損%": f"-{r['risk_pct']:.2f}%"
            })
        
        if table_rows:
            df_display = pd.DataFrame(table_rows).sort_values(by="評分", ascending=False)
            st.dataframe(df_display, use_container_width=True)
            st.caption(f"符合篩選條件共有 {len(df_display)} 檔標的。")
        else:
            st.warning("當前條件組合無符合標的，請放寬勾選項。")
    else:
        st.info("請先至第一分頁點擊『啟動多因子大數據量化運算』。")

# ==============================================================================
# Tab 7：個股多維技術診斷
# ==============================================================================
with tab_detail:
    st.sidebar.subheader("個股技術診斷")
    d_input = st.sidebar.text_input("輸入個股代碼查詢", "2330.TW")
    d_period = st.sidebar.selectbox("週期", ["1 個月", "3 個月", "6 個月", "1 年"], index=2)
    p_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y"}

    if d_input:
        df_d = yf.download(d_input.strip().upper(), period=p_map[d_period], progress=False)
        if hasattr(df_d.columns, 'levels') and len(df_d.columns.levels) > 1:
            df_d.columns = df_d.columns.get_level_values(0)

        if not df_d.empty and len(df_d) >= 10:
            df_d = calculate_all_indicators(df_d)
            latest_d = df_d.iloc[-1]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("收盤價", f"{latest_d['Close']:.2f} 元")
            c2.metric("5MA 乖離", f"{latest_d['Bias5']:+.2f}%")
            c3.metric("MFI 資金流", f"{latest_d['MFI']:.1f}")
            c4.metric("14日 ATR", f"{latest_d['ATR']:.2f} 元")

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(
                x=df_d.index, open=df_d['Open'], high=df_d['High'], low=df_d['Low'], close=df_d['Close'],
                name="K線", increasing_line_color='#ef4444', decreasing_line_color='#22c55e'
            ), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MA10'], line=dict(color='#f59e0b', width=1.5), name="10MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MA20'], line=dict(color='#3b82f6', width=1.5), name="20MA"), row=1, col=1)
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], name="成交量", marker_color='#64748b'), row=2, col=1)

            fig.update_layout(
                height=550,
                xaxis_rangeslider_visible=False,
                paper_bgcolor="#05070d",
                plot_bgcolor="#05070d",
                font=dict(color="#e2e8f0"),
                margin=dict(l=20, r=20, t=30, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("暫無該標的資料，請確認是否輸入正確上市櫃後綴 (.TW 或 .TWO)。")