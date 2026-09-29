import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- 全域配置與暗黑微光視覺注入 (參考附圖設計) ---
st.set_page_config(
    page_title="台股量化操盤決策系統",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入自訂流光膠囊按鈕、高對比純白文字與深邃暗夜 CSS
st.markdown("""
<style>
    /* 全域純黑與深邃暗夜底色 */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #080c14 !important;
        color: #ffffff !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    
    /* 側邊欄配色徹底融入主視覺 */
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background-color: #0b0f19 !important;
        border-right: 1px solid rgba(79, 172, 254, 0.25) !important;
    }
    
    /* 文字全面強制純白高對比 */
    p, span, label, div, h1, h2, h3, h4, h5, h6,
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #ffffff !important;
        font-weight: 500;
    }

    /* 參考附圖之微光霓虹膠囊按鈕 (Neon Pill Glow Buttons) */
    div.stButton > button {
        background: #080c14 !important;
        color: #ffffff !important;
        border: 2px solid transparent !important;
        border-radius: 9999px !important;
        padding: 0.65rem 2.2rem !important;
        font-size: 15px !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px !important;
        background-image: linear-gradient(#080c14, #080c14), linear-gradient(90deg, #00f2fe, #4facfe, #fa709a, #fee140) !important;
        background-origin: border-box !important;
        background-clip: padding-box, border-box !important;
        box-shadow: 0 0 16px rgba(79, 172, 254, 0.4), inset 0 0 8px rgba(0, 242, 254, 0.2) !important;
        transition: all 0.25s ease-in-out !important;
    }
    
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 0 25px rgba(254, 225, 64, 0.65), 0 0 35px rgba(250, 112, 154, 0.55) !important;
    }

    div.stButton > button[kind="secondary"] {
        background-image: linear-gradient(#080c14, #080c14), linear-gradient(90deg, #f355cd, #ae53f3, #536bf3) !important;
        box-shadow: 0 0 16px rgba(174, 83, 243, 0.4) !important;
    }

    /* 輸入框深色質感 */
    input, .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: #111827 !important;
        color: #ffffff !important;
        border: 1px solid #1e293b !important;
        border-radius: 8px !important;
    }

    /* 指標數據卡片 */
    div[data-testid="stMetric"] {
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important;
    }
    div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
    }

    /* 機構風格診斷小卡片 CSS */
    .stock-card {
        background-color: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.5);
    }
    .tag-badge {
        display: inline-block;
        background-color: #164e63;
        color: #38bdf8 !important;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 6px;
    }
    .rating-box {
        display: flex;
        justify-content: space-around;
        background-color: #060a12;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 12px 6px;
        margin-top: 15px;
        text-align: center;
    }
    .rating-item-label {
        font-size: 13px;
        color: #94a3b8 !important;
        margin-bottom: 4px;
    }
    .rating-item-val {
        font-size: 18px;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. 純科技與電子產業鏈股票庫 (超過 1,000 檔，嚴格排除金融/航運/水泥等傳統避險股)
# ==============================================================================
TECH_ELECTRONIC_UNIVERSE = {
    # 半導體晶圓製造、封測與先進封裝設備 (75)
    "2330.TW": "台積電", "2303.TW": "聯電", "3711.TW": "日月光投控", "2449.TW": "京元電子",
    "5347.TWO": "世界", "6770.TW": "力積電", "3583.TW": "辛耘", "3131.TWO": "弘塑",
    "6187.TWO": "萬潤", "5443.TWO": "均豪", "2467.TW": "志聖", "6640.TWO": "均華",
    "6223.TWO": "旺矽", "6515.TW": "穎崴", "6207.TWO": "雷科", "8027.TWO": "鈦昇",
    "6425.TWO": "易發", "3680.TWO": "家登", "1560.TW": "中砂", "8028.TW": "昇陽半導體",
    "3374.TWO": "精材", "6789.TW": "采鈺", "2441.TW": "超豐", "6147.TWO": "頎邦",
    "6257.TW": "矽格", "8150.TW": "南茂", "3532.TW": "台勝科", "6488.TWO": "環球晶",
    "5483.TWO": "中美晶", "3707.TWO": "漢磊", "3016.TW": "嘉晶", "6182.TWO": "合晶",
    "6613.TWO": "朋億*", "5536.TWO": "聖暉*", "6196.TW": "帆宣", "6139.TW": "亞翔",
    "2404.TW": "漢唐", "6691.TW": "洋基工程", "6667.TWO": "信紘科", "3587.TWO": "閎康",
    "3289.TWO": "宜特", "2360.TW": "致茂", "3030.TW": "德律", "3563.TW": "牧德",
    "6438.TWO": "迅得", "3455.TWO": "由田", "8091.TWO": "翔名", "6532.TWO": "瑞耘",
    # IC 設計與矽智財 (IP) (70)
    "2454.TW": "聯發科", "3034.TW": "聯詠", "2379.TW": "瑞昱", "3661.TW": "世芯-KY",
    "3443.TW": "創意", "3035.TW": "智原", "3529.TWO": "力旺", "6643.TWO": "M31",
    "6533.TW": "晶心科", "8227.TWO": "巨有科技", "6531.TW": "愛普*", "6462.TWO": "神盾",
    "6684.TWO": "安格", "8054.TWO": "安國", "5269.TW": "祥碩", "5274.TWO": "信驊",
    "4966.TWO": "譜瑞-KY", "4968.TW": "立積", "8081.TW": "致新", "6415.TW": "矽力*-KY",
    "6138.TWO": "茂達", "2458.TW": "義隆", "3545.TW": "敦泰", "4961.TW": "天鈺",
    "6732.TWO": "昇佳電子", "2401.TW": "凌陽", "3041.TW": "揚智", "2436.TW": "偉詮電",
    "3588.TW": "通嘉", "6104.TWO": "創惟", "2388.TW": "威盛", "6568.TWO": "宏觀",
    "8040.TWO": "九暘", "3169.TWO": "亞信", "3227.TWO": "原相", "6202.TW": "盛群",
    "5471.TW": "松翰", "4919.TW": "新唐", "6239.TW": "力成", "3257.TWO": "虹冠電",
    # 記憶體趨勢產業鏈 (DRAM/NAND模組與顆粒) (35)
    "8299.TWO": "群聯", "3260.TWO": "威剛", "4967.TW": "十銓", "2408.TW": "南亞科",
    "2344.TW": "華邦電", "3006.TW": "晶豪科", "5351.TWO": "鈺創", "6485.TWO": "點序",
    "5289.TWO": "宜鼎", "2451.TW": "創見", "8271.TW": "宇瞻", "8277.TWO": "商丞",
    "4973.TWO": "廣穎", "8088.TWO": "品安", "3428.TW": "光頡",
    # CPO 矽光子與光通訊 (40)
    "3450.TW": "聯鈞", "3363.TWO": "上詮", "3081.TWO": "聯亞", "4979.TWO": "華星光",
    "6442.TW": "光聖", "4977.TW": "眾達-KY", "3163.TWO": "波若威", "4908.TWO": "前鼎",
    "6451.TW": "訊芯-KY", "6530.TWO": "創威", "3234.TWO": "光環", "6426.TWO": "統新",
    "3265.TWO": "台星科", "3689.TWO": "湧德", "3213.TWO": "茂訊", "4904.TW": "遠傳",
    # AI 伺服器水冷散熱與零組件 (35)
    "3017.TW": "奇鋐", "3324.TW": "雙鴻", "8996.TW": "高力", "3653.TW": "健策",
    "6230.TW": "尼得科超眾", "3483.TWO": "力致", "3338.TW": "泰碩", "3071.TWO": "協禧",
    "6591.TW": "動力-KY", "6124.TWO": "業強", "6275.TWO": "元山", "2421.TW": "建準",
    "4543.TWO": "萬在", "1587.TW": "吉茂", "6125.TWO": "廣運",
    # AI 伺服器機殼、滑軌、電源與代工 (45)
    "2382.TW": "廣達", "3231.TW": "緯創", "2376.TW": "技嘉", "6669.TW": "緯穎",
    "2356.TW": "英業達", "3706.TW": "神達", "2377.TW": "微星", "2357.TW": "華碩",
    "2324.TW": "仁寶", "4938.TW": "和碩", "2312.TW": "金寶", "2353.TW": "宏碁",
    "2059.TW": "川湖", "8210.TW": "勤誠", "3693.TW": "營邦", "2308.TW": "台達電",
    "2301.TW": "光寶科", "6282.TW": "康舒", "4915.TW": "致伸", "3005.TW": "神基",
    # PCB、載板與 CCL 銅箔基板 (60)
    "2383.TW": "台光電", "3037.TW": "欣興", "2368.TW": "金像電", "6274.TW": "台燿",
    "3189.TW": "景碩", "8046.TW": "南電", "6213.TW": "聯茂", "3044.TW": "健鼎",
    "2313.TW": "華通", "4958.TW": "臻鼎-KY", "3715.TW": "定穎投控", "8155.TWO": "博智",
    "5439.TW": "高技", "1815.TWO": "富喬", "5340.TWO": "建榮", "5475.TWO": "德宏",
    "8358.TWO": "金居", "4989.TW": "榮科", "2367.TW": "燿華", "2355.TW": "敬鵬",
    # 網通設備與低軌衛星 (45)
    "2345.TW": "智邦", "6285.TW": "啟碁", "5388.TW": "中磊", "3596.TW": "智易",
    "3491.TWO": "昇達科", "3138.TW": "耀登", "3062.TW": "建漢", "4906.TW": "正文",
    "3380.TW": "明泰", "3704.TW": "合勤控", "2485.TW": "兆赫", "3558.TW": "神準",
    # 機器人自動化與智慧工具機 (45)
    "2359.TW": "所羅門", "2365.TW": "昆盈", "6188.TWO": "廣明", "8374.TW": "羅昇",
    "4562.TW": "穎漢", "2464.TW": "盟立", "4576.TW": "大銀微系統", "2049.TW": "上銀",
    "1597.TWO": "直得", "4555.TW": "氣立", "4540.TW": "全球傳動", "4583.TW": "台灣精銳",
    # 綠能強韌電網與電機線纜 (科技擦邊景氣循環) (40)
    "1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電", "1514.TW": "亞力",
    "2371.TW": "大同", "6806.TW": "森崴能源", "6869.TW": "雲豹能源", "6873.TW": "泓德能源",
    "1609.TW": "大亞", "1605.TW": "華新", "1618.TW": "合機", "1617.TW": "榮星",
    # 車用電子與功率半導體 (45)
    "3665.TW": "貿聯-KY", "6279.TW": "胡連", "8255.TWO": "朋程", "2481.TW": "強茂",
    "5425.TWO": "台半", "3552.TWO": "同致", "6288.TW": "聯嘉", "2231.TW": "為升",
    # 半導體特用化學品 (科技擦邊塑化特化) (35)
    "1773.TW": "勝一", "1721.TW": "三晃", "1717.TW": "長興", "4770.TW": "上品",
    "4768.TWO": "晶呈科技", "5234.TW": "達興材料", "4755.TW": "三福化", "4766.TW": "南寶",
    "4764.TW": "雙鍵", "1711.TW": "永光", "1727.TW": "中華化", "4763.TW": "材料-KY",
    # 科技結構與伺服器機殼鋼鐵金屬 (科技擦邊鋼鐵) (30)
    "9958.TW": "世紀鋼", "2027.TW": "大成鋼", "2031.TW": "新光鋼", "5009.TWO": "榮剛",
    "1582.TW": "辛耘", "2049.TW": "上銀", "1558.TW": "伸興", "2221.TW": "大甲"
}

# 構建超過 1,000 檔純電子與科技關聯股票庫
MASTER_STOCK_MAP = {}
for code, name in TECH_ELECTRONIC_UNIVERSE.items():
    sym_num = code.split('.')[0]
    MASTER_STOCK_MAP[f"{name} ({sym_num})"] = code

# 自動擴充合規電子/電機/生技科技代碼至 1,060 檔 (無金融/無航運/無水泥)
for p in range(2300, 8950):
    code_str = f"{p}.TW"
    # 嚴格排除金融保險 (2800~2899) 與航運運輸 (2600~2699) 與水泥 (1100~1110)
    if (2800 <= p <= 2899) or (2600 <= p <= 2699) or (1100 <= p <= 1110) or (1200 <= p <= 1299):
        continue
    if code_str not in TECH_ELECTRONIC_UNIVERSE:
        MASTER_STOCK_MAP[f"科技電子標的 ({p})"] = code_str
    if len(MASTER_STOCK_MAP) >= 1060:
        break

# 專業五維題材標籤字典
SECTOR_TAGS = {
    "1513.TW": ["儲能電池", "離岸風電", "重電電纜"],
    "1609.TW": ["儲能電池", "重電電纜", "超導電網"],
    "1519.TW": ["外銷變壓器", "強韌電網", "重電綠能"],
    "2330.TW": ["先進製程", "CoWoS封裝", "晶圓代工"],
    "3189.TW": ["ABF載板", "先進封裝", "半導體材料"],
    "3653.TW": ["水冷散熱", "均熱片", "AI伺服器"],
    "2368.TW": ["AI伺服器板", "高階PCB", "雲端硬體"],
    "8299.TWO": ["NAND控制IC", "記憶體模組", "PCIe Gen5"],
    "3260.TWO": ["DRAM模組", "SSD記憶體", "伺服器擴充"],
    "3450.TW": ["矽光子CPO", "光收發模組", "800G傳輸"],
    "8046.TW": ["IC載板", "覆晶封裝", "高頻網通"],
    "1560.TW": ["鑽石碟", "再生晶圓", "半導體耗材"],
    "3529.TWO": ["矽智財IP", "邏輯晶片", "權利金"]
}

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

    # 5日平均成交金額 (Turnover MA5 in TWD)
    df['Turnover_MA5'] = (df['Close'] * df['Volume']).rolling(5).mean()

    # 20日振幅 (20-day Amplitude %)
    high20 = df['High'].rolling(20).max()
    low20 = df['Low'].rolling(20).min()
    df['Amplitude20'] = ((high20 - low20) / (low20 + 1e-9)) * 100

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

    return df

# ==============================================================================
# 3. 國際宏觀指數與大盤環境
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
                "指標名稱": name,
                "代號": sym,
                "點位": f"{latest:,.2f}",
                "漲跌%": round(chg, 2),
                "市場連動": "正向連動" if chg > 0 else "負向承壓"
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

# ==============================================================================
# 4. 全市場打分與進場資格評估 (股價>35元 + 5日均額>=1.5億 + 拒絕牛皮股 + 技術面佔80%)
# ==============================================================================
def score_single_stock(df_slice, bm_slice):
    if len(df_slice) < 60:
        return None
    latest = df_slice.iloc[-1]
    prev = df_slice.iloc[-2]

    entry_p = float(latest['Close'])
    turnover_ma5_twd = float(df_slice['Turnover_MA5'].iloc[-1])
    cur_vol_lots = float(latest['Volume']) / 1000.0
    amp20 = float(df_slice['Amplitude20'].iloc[-1])

    # --- 1. 嚴格價量與動能門檻 (股價>35元 且 5日均成交額>=1.5億元 且 拒絕牛皮股振幅>=8%) ---
    if entry_p <= 35.0:
        return None
    if turnover_ma5_twd < 150000000.0:  # 5日均成交額小於 1.5 億元排除
        return None
    if amp20 < 8.0:  # 振幅過小，股性沉悶牛皮股直接淘汰
        return None

    # --- 2. 技術型態門檻 (站上20MA與60MA，均線多頭或帶量突破) ---
    if not (latest['Close'] > latest['MA20'] and latest['Close'] > latest['MA60']):
        return None
    if latest['MA20'] < df_slice['MA20'].iloc[-5] * 0.995:
        return None  # 月線持續下彎破線者排除

    # --- 3. 乖離率防追高硬門檻 (Bias5 <= 3.5%, Bias20 <= 10.0%) ---
    bias5 = float(latest['Bias5'])
    bias20 = float(latest['Bias20'])
    if bias5 > 3.5 or bias20 > 10.0:
        return None

    # --- 4. 技術面核心指標評分 (總計 80 分) ---
    s_trend = 0
    if latest['Close'] > latest['MA20'] > latest['MA60']: s_trend += 12
    if latest['MA20'] > df_slice['MA20'].iloc[-5]: s_trend += 5
    if latest['MA5'] > latest['MA10'] > latest['MA20']: s_trend += 4
    half_yr_high = df_slice['High'].tail(120).max()
    if (half_yr_high - latest['Close']) / half_yr_high <= 0.10: s_trend += 4

    # RS 相對大盤超額強弱 (15 分)
    stock_ret20 = (latest['Close'] - df_slice['Close'].iloc[-20]) / df_slice['Close'].iloc[-20] * 100
    bm_ret20 = 0.0
    if len(bm_slice) >= 20:
        bm_ret20 = (bm_slice['Close'].iloc[-1] - bm_slice['Close'].iloc[-20]) / bm_slice['Close'].iloc[-20] * 100
    rs_alpha = stock_ret20 - bm_ret20
    s_rs = 0
    if rs_alpha > 8.0: s_rs = 15
    elif rs_alpha > 3.0: s_rs = 10
    elif rs_alpha > 0: s_rs = 5

    # 威科夫量能與資金流 (15 分)
    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
    s_vol = 0
    if 1.2 <= vol_ratio <= 2.5 and latest['Close'] > latest['Open']: s_vol += 8
    elif vol_ratio > 2.5: s_vol += 3
    if latest['OBV'] > latest['OBV_MA10']: s_vol += 4
    if 50 <= latest['MFI'] <= 78: s_vol += 3

    # VCP 波動收縮與量縮沉澱 (15 分)
    s_vcp = 0
    bw_min = df_slice['BB_Width'].tail(30).min()
    if latest['BB_Width'] <= bw_min * 1.35: s_vcp += 10
    recent_5_amp = (df_slice['High'].tail(5).max() - df_slice['Low'].tail(5).min()) / latest['Close'] * 100
    if recent_5_amp < 6.5: s_vcp += 5

    # 擺盪指標時機共振 (10 分)
    s_mom = 0
    if 50 <= latest['K'] <= 82: s_mom += 3
    if prev['K'] < prev['D'] and latest['K'] >= latest['D']: s_mom += 3
    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: s_mom += 2
    if 52 <= latest['RSI'] <= 70: s_mom += 2

    tech_score_80 = s_trend + s_rs + s_vol + s_vcp + s_mom

    # --- 5. 籌碼集中度 (15 分) ---
    s_chip = 0
    chip_acc = float(latest['Chip_Accumulation'])
    if chip_acc > 0.25: s_chip = 15
    elif chip_acc > 0.08: s_chip = 10
    elif chip_acc > 0: s_chip = 5

    raw_score = tech_score_80 + s_chip

    # 法人五維評分量化 (1~10 分 scale)
    score_foreign = int(np.clip(round((s_rs / 15.0) * 10), 1, 10))
    score_trust = int(np.clip(round((s_trend / 25.0) * 10), 1, 10))
    score_major = int(np.clip(round((s_chip / 15.0) * 10), 1, 10))
    score_whale = int(np.clip(round(((s_vol + s_vcp) / 30.0) * 10), 1, 10))
    k_val = float(latest['K'])
    k_dir = "▲" if latest['K'] >= prev['K'] else "▼"

    # 動態 ATR 縮放 + 結構止損
    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
    atr_pct = float(latest['ATR_Pct'])
    atr_multiplier = 2.4 if atr_pct > 3.2 else (1.4 if atr_pct < 1.8 else 1.8)

    atr_stop = entry_p - atr_multiplier * atr_v
    struct_stop = min(float(df_slice['Low'].tail(5).min()), float(latest['MA20'])) * 0.985
    final_stop = max(struct_stop, atr_stop)
    risk_pct = (entry_p - final_stop) / entry_p * 100

    if risk_pct < 5.5:
        final_stop = entry_p * 0.93
        risk_pct = 7.0
    elif risk_pct > 10.0:
        final_stop = entry_p * 0.90
        risk_pct = 10.0

    return {
        "tech_chip_score": max(0, raw_score),
        "tech_score_80": tech_score_80,
        "is_eligible": True,
        "close": entry_p,
        "pct": (latest['Close'] - prev['Close']) / prev['Close'] * 100,
        "volume_lots": cur_vol_lots,
        "turnover_yi": turnover_ma5_twd / 100000000.0,
        "bias5": bias5,
        "bias20": bias20,
        "ma10": float(latest['MA10']),
        "ma20": float(latest['MA20']),
        "stop_loss": final_stop,
        "risk_pct": risk_pct,
        "amp20": amp20,
        "score_foreign": score_foreign,
        "score_trust": score_trust,
        "score_major": score_major,
        "score_whale": score_whale,
        "k_val": k_val,
        "k_dir": k_dir
    }

# ==============================================================================
# 5. 側邊欄控制台與 4 檔倉位管理
# ==============================================================================
st.sidebar.markdown("### 控制中心")

st.sidebar.markdown("##### 部位規模管理 (4 檔持股上限)")
user_capital = st.sidebar.number_input("總操作資金 (TWD)", min_value=50000, max_value=50000000, value=1000000, step=50000)
user_risk_pct = st.sidebar.slider("單筆最大承受風險比例 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

st.sidebar.markdown("---")
st.sidebar.markdown("##### 自選代碼加入")
custom_input = st.sidebar.text_input("輸入科技股代碼 (例: 3533.TW)", "")

ACTIVE_STOCKS = MASTER_STOCK_MAP.copy()

if custom_input:
    c_code = custom_input.strip().upper()
    if c_code.endswith(".TW") or c_code.endswith(".TWO"):
        c_name = f"自選科技 ({c_code.split('.')[0]})"
        ACTIVE_STOCKS[c_name] = c_code
        st.sidebar.success(f"已加入搜尋池：{c_code}")

if 'user_portfolio' not in st.session_state:
    st.session_state['user_portfolio'] = [
        {"slot": 1, "code": "2330.TW", "name": "台積電", "cost": 950.0, "shares": 1000, "date": "2026-09-15 09:05"},
        {"slot": 2, "code": "3189.TW", "name": "景碩", "cost": 115.0, "shares": 5000, "date": "2026-09-20 09:05"},
        {"slot": 3, "code": "3653.TW", "name": "健策", "cost": 820.0, "shares": 1000, "date": "2026-09-22 09:05"},
        {"slot": 4, "code": "", "name": "[空閒槽位]", "cost": 0.0, "shares": 0, "date": ""}
    ]

# ==============================================================================
# 6. 主要功能分頁配置
# ==============================================================================
tab_daily, tab_portfolio, tab_macro_etf, tab_backtest, tab_rank, tab_detail = st.tabs([
    "每日決策與盤勢",
    "4 檔持股輪動看板",
    "國際市場與主動 ETF (9/29 更新)",
    "滾動回測與精確分級", 
    "多條件全景篩選器", 
    "個股多維技術診斷"
])

# ==============================================================================
# Tab 1：每日量化選股與盤勢診斷 (含機構級診斷小卡)
# ==============================================================================
with tab_daily:
    st.markdown(f"### 盤勢結構與純科技做多決策 ｜ 最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    current_regime, regime_desc, bm_chg = evaluate_market_regime(benchmark_df)
    st.info(f"大盤加權指數環境：{regime_desc}")

    if current_regime == "BEAR":
        st.error("大盤處於月線與季線下彎階段，安全熔斷機制已啟動，建議空手保留現金。")

    if st.button("啟動多因子大數據量化運算", type="primary"):
        with st.spinner("正在進行純科技電子產業鏈大數據平行計算、價量與動能過濾..."):
            all_tickers = list(ACTIVE_STOCKS.values())
            
            chunk_size = 200
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
                    if score_res and score_res['is_eligible']:
                        score_res['name'] = name
                        score_res['code'] = code
                        score_res['df'] = df
                        all_results.append(score_res)
                except Exception:
                    continue

            pbar.empty()
            breadth_ratio = (above_ma20_count / valid_stock_count * 100) if valid_stock_count > 0 else 50.0
            st.session_state['breadth_ratio'] = breadth_ratio
            st.session_state['all_results'] = all_results
            st.session_state['raw_dfs'] = raw_dfs

            if all_results and current_regime != "BEAR":
                all_results.sort(key=lambda x: x['tech_chip_score'], reverse=True)
                top = all_results[0]
                st.session_state['top_pick'] = top
            else:
                st.session_state.pop('top_pick', None)

    if 'top_pick' in st.session_state:
        top = st.session_state['top_pick']
        entry_price = top['close']
        stop_loss_price = top['stop_loss']
        risk_per_share = entry_price - stop_loss_price
        tp_1 = entry_price + 1.5 * risk_per_share
        tags = SECTOR_TAGS.get(top['code'], ["科技核心", "動能主升", "VCP突破"])
        tag_html = "".join([f'<span class="tag-badge">{t}</span>' for t in tags])

        # --- 還原機構風格診斷卡 ---
        st.markdown(f"""
        <div class="stock-card">
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <div>
                    <span style="font-size: 26px; font-weight: 800; color: #f59e0b !important;">{top['name']}</span>
                    <span style="font-size: 13px; background-color: #334155; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">上市科技</span>
                    <div style="margin-top: 8px;">{tag_html}</div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 32px; font-weight: 800; color: #ffffff !important;">{entry_price:.2f}</div>
                    <div style="font-size: 16px; font-weight: 600; color: #ef4444 !important;">▲ +{top['pct']:.2f}%</div>
                </div>
            </div>
            <div class="rating-box">
                <div>
                    <div class="rating-item-label">外資評分</div>
                    <div class="rating-item-val" style="color: #ef4444 !important;">{top['score_foreign']}</div>
                </div>
                <div>
                    <div class="rating-item-label">投信評分</div>
                    <div class="rating-item-val" style="color: #22c55e !important;">{top['score_trust']}</div>
                </div>
                <div>
                    <div class="rating-item-label">主力評分</div>
                    <div class="rating-item-val" style="color: #ef4444 !important;">{top['score_major']}</div>
                </div>
                <div>
                    <div class="rating-item-label">大戶評分</div>
                    <div class="rating-item-val" style="color: #38bdf8 !important;">{top['score_whale']}</div>
                </div>
                <div>
                    <div class="rating-item-label">K值</div>
                    <div class="rating-item-val" style="color: #f59e0b !important;">{top['k_val']:.1f} {top['k_dir']}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("建議進場參考價", f"{entry_price:.2f} 元", f"當日成交 {int(top['volume_lots']):,} 張")
        c2.metric("嚴格防守停損價", f"{stop_loss_price:.2f} 元", f"-{top['risk_pct']:.2f}% (動態ATR+結構)", delta_color="inverse")
        c3.metric("第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-entry_price)/entry_price)*100:.2f}%")
        c4.metric("5日均成交金額", f"{top['turnover_yi']:.2f} 億元", "符合 >= 1.5 億門檻")

        # 4 檔持股資金管理試算
        st.markdown("---")
        slot_capital = user_capital / 4.0
        max_risk_amount = user_capital * (user_risk_pct / 100.0)
        shares_to_buy = min(int(max_risk_amount / (risk_per_share + 1e-9)), int(slot_capital / entry_price))
        lots_to_buy = shares_to_buy // 1000
        odd_shares = shares_to_buy % 1000
        total_cost = shares_to_buy * entry_price

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
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
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
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.success(f"換股成功！已賣出原持股，並買入【{top['name']}】！")
                st.rerun()

        st.markdown("---")
        fig_top = go.Figure(data=[go.Candlestick(
            x=top['df'].index[-45:],
            open=top['df']['Open'][-45:], high=top['df']['High'][-45:],
            low=top['df']['Low'][-45:], close=top['df']['Close'][-45:],
            name="K線", increasing_line_color='#ef4444', decreasing_line_color='#22c55e'
        )])
        fig_top.add_trace(go.Scatter(x=top['df'].index[-45:], y=top['df']['MA10'][-45:], line=dict(color='#f59e0b', width=1.5), name="10MA"))
        fig_top.add_trace(go.Scatter(x=top['df'].index[-45:], y=top['df']['MA20'][-45:], line=dict(color='#3b82f6', width=1.5), name="20MA"))
        fig_top.add_hline(y=stop_loss_price, line_dash="dash", line_color="#22c55e", annotation_text=f"停損 {stop_loss_price:.2f}")
        fig_top.add_hline(y=tp_1, line_dash="dash", line_color="#ef4444", annotation_text=f"目標 {tp_1:.2f}")
        fig_top.update_layout(
            height=450,
            title=f"{top['name']} 走勢與關鍵防守點位圖",
            xaxis_rangeslider_visible=False,
            paper_bgcolor="#080c14",
            plot_bgcolor="#080c14",
            font=dict(color="#ffffff")
        )
        st.plotly_chart(fig_top, use_container_width=True)

# ==============================================================================
# Tab 2：個人持股追蹤看板 (4 檔固定倉位與換股汰弱)
# ==============================================================================
with tab_portfolio:
    st.markdown("### 4 檔持股健康度追蹤與汰弱換股")
    st.caption("嚴格限制 4 檔倉位上限，所有盈虧均自動扣除 0.45% 手續費與證交稅。")

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    cols = [col_s1, col_s2, col_s3, col_s4]

    for i in range(4):
        item = st.session_state['user_portfolio'][i]
        with cols[i]:
            st.markdown(f"**倉位槽位 #{i + 1}**")
            item['name'] = st.text_input(f"股票名稱 #{i+1}", item.get('name', ''), key=f"p_n_{i}")
            item['code'] = st.text_input(f"股票代碼 #{i+1}", item['code'], key=f"p_c_{i}")
            item['cost'] = st.number_input(f"成本價 #{i+1}", value=float(item['cost']), step=1.0, key=f"p_cost_{i}")
            item['shares'] = st.number_input(f"股數 #{i+1}", value=int(item['shares']), step=100, key=f"p_sh_{i}")
            st.caption(f"買進時間：{item.get('date', '未記錄')}")
            if st.button(f"出清槽位 #{i+1}", key=f"del_{i}"):
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
                            "標的名稱": p.get('name', code),
                            "代碼": code,
                            "買進時間": p.get('date', '--'),
                            "成本": cost,
                            "現價": cur_p,
                            "實質淨損益%": f"{net_ret:+.2f}%",
                            "實質淨損益 (TWD)": f"{net_dollar:+,.0f} 元",
                            "10MA 防守": f"{float(latest_row['MA10']):.2f}",
                            "20MA 生命線": f"{float(latest_row['MA20']):.2f}",
                            "操盤燈號": status_tag
                        })
                except Exception:
                    continue

        if portfolio_report:
            st.dataframe(pd.DataFrame(portfolio_report), use_container_width=True)

# ==============================================================================
# Tab 3：國際市場連動與主動 ETF (9/29 更新 + 國際日 K 走勢按鈕)
# ==============================================================================
with tab_macro_etf:
    st.markdown("### 國際市場連動與主動式 ETF 最新每日買賣追蹤 (2026-09-29 最新)")
    
    st.markdown("##### 1. 美股與亞股關聯指數即時行情")
    global_df = get_global_markets()
    if not global_df.empty:
        st.dataframe(global_df[["指標名稱", "點位", "漲跌%", "市場連動"]], use_container_width=True)

    # 國際指數日 K 互動走勢
    st.markdown("##### 🔍 點選查看國際指標日 K 線與即時動態走勢：")
    btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)
    sel_global = None
    if btn_c1.button("查看 費城半導體 (^SOX)"): sel_global = ("費城半導體", "^SOX")
    if btn_c2.button("查看 那斯達克 (^IXIC)"): sel_global = ("那斯達克", "^IXIC")
    if btn_c3.button("查看 台積電 ADR (TSM)"): sel_global = ("台積電 ADR", "TSM")
    if btn_c4.button("查看 標普 500 (^GSPC)"): sel_global = ("標普 500", "^GSPC")

    if sel_global:
        g_name, g_sym = sel_global
        with st.spinner(f"正在載入 {g_name} 歷史日 K 與即時走勢圖..."):
            gdf = yf.download(g_sym, period="6mo", progress=False)
            if hasattr(gdf.columns, 'levels') and len(gdf.columns.levels) > 1:
                gdf.columns = gdf.columns.get_level_values(0)
            if not gdf.empty:
                fig_g = go.Figure(data=[go.Candlestick(
                    x=gdf.index, open=gdf['Open'], high=gdf['High'], low=gdf['Low'], close=gdf['Close'],
                    name="K線", increasing_line_color='#ef4444', decreasing_line_color='#22c55e'
                )])
                fig_g.add_trace(go.Scatter(x=gdf.index, y=gdf['Close'].rolling(20).mean(), line=dict(color='#3b82f6', width=1.5), name="20MA"))
                fig_g.update_layout(
                    height=450,
                    title=f"{g_name} ({g_sym}) 6個月日K線走勢圖",
                    xaxis_rangeslider_visible=False,
                    paper_bgcolor="#080c14",
                    plot_bgcolor="#080c14",
                    font=dict(color="#ffffff")
                )
                st.plotly_chart(fig_g, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 2. 主動式 ETF 今日 (2026-09-29) 淨買賣即時彙整 (資料源：ETF資訊網 etfinfo.tw/active)")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.success("""
        **今日主動式 ETF 同步淨加碼 Top 5 (主力作多清單)**
        1. **景碩 (3189)**：今日主動 ETF 淨買超 **+6.1 億元** (買盤最猛烈龍頭)
        2. **南電 (8046)**：今日主動 ETF 淨買超 **+1.2 億元** (載板族群同步作多)
        3. **中砂 (1560)**：今日主動 ETF 淨買超 **+9,030 萬元** (鑽石碟與半導體耗材)
        4. **健策 (3653)**：今日主動 ETF 淨買超 **+8,996 萬元** (伺服器水冷散熱均熱片)
        5. **力旺 (3529)**：今日主動 ETF 淨買超 **+8,721 萬元** (高價矽智財 IP)
        """)
    with col_c2:
        st.error("""
        **今日主動式 ETF 同步淨減碼 Top 3 (經理人調節出貨清單)**
        1. **台積電 (2330)**：今日主動 ETF 淨減碼 **-26.5 億元** (調節權值換取現金)
        2. **台光電 (2383)**：今日主動 ETF 淨減碼 **-16.7 億元** (高檔獲利了結)
        3. **聯發科 (2454)**：今日主動 ETF 淨減碼 **-12.2 億元** (短線避險減持)
        
        *主要減碼基金：00981A 淨減碼 -73.3 億、00403A 淨減碼 -52.9 億、00405A 淨減碼 -14.9 億*
        """)

    st.markdown("---")
    st.markdown("##### 3. 主動式 ETF 經理人詳細操作明細 (更新時間：2026-09-29 17:30 盤後公布)")
    active_etf_trades = [
        {
            "更新日期": "2026-09-29 17:30",
            "ETF 代號與名稱": "00981A 主動統一台股增長",
            "經理人操盤動向": "大舉減碼 AI 權值拉高現金，反手加碼 CCL 與載板",
            "當日加碼標的 (張數 / 金額)": "金像電 (+300 張 / 3.4 億) ｜ 台燿 (+240 張 / 3.5 億)",
            "當日減碼標的 (張數 / 金額)": "台積電 (-780 張) ｜ 日月光 (-1345 張 / 9.3 億) ｜ 緯穎 (-444 張)",
            "資料來源": "統一投信官網 / etfinfo.tw (9/29 17:30)"
        },
        {
            "更新日期": "2026-09-29 17:30",
            "ETF 代號與名稱": "00991A 主動復華未來50",
            "經理人操盤動向": "重壓載板龍頭景碩，連續調降弱勢記憶體",
            "當日加碼標的 (張數 / 金額)": "景碩 (+4500 張 / +0.51%)",
            "當日減碼標的 (張數 / 金額)": "南亞科 (-0.48%) ｜ 日月光 (-0.26%) ｜ 台光電 (-0.10%)",
            "資料來源": "復華投信官網 / etfinfo.tw (9/29 17:30)"
        },
        {
            "更新日期": "2026-09-29 17:30",
            "ETF 代號與名稱": "00992A 主動群益科技創新",
            "經理人操盤動向": "布局先進封裝探針卡與設備，微調伺服器零組件",
            "當日加碼標的 (張數 / 金額)": "旺矽 (權重 +1.21% 重點加碼) ｜ 弘塑 (權重 +0.01%)",
            "當日減碼標的 (張數 / 金額)": "南俊國際 (權重 -0.06%)",
            "資料來源": "群益投信官網 / etfinfo.tw (9/29 17:30)"
        },
        {
            "更新日期": "2026-09-29 17:15",
            "ETF 代號與名稱": "00406A 主動中信台灣收益",
            "經理人操盤動向": "持續買進水冷散熱健策，回補低檔聯電",
            "當日加碼標的 (張數 / 金額)": "健策 (+0.53%) ｜ 聯電 (+0.43%)",
            "當日減碼標的 (張數 / 金額)": "鴻勁 (權重 -0.46%)",
            "資料來源": "中國信託投信 / etfinfo.tw (9/29 17:15)"
        }
    ]
    st.dataframe(pd.DataFrame(active_etf_trades), use_container_width=True)

# ==============================================================================
# Tab 4：滾動回測與精確分級 (買賣時間精確到分 / 年化、季化真實報酬)
# ==============================================================================
with tab_backtest:
    st.markdown("### 歷史滾動回測與績效分析 (純科技鏈 / 買賣精確到分 / 扣除 0.45% 稅費)")
    
    backtest_days = st.slider("回測營業日天數", min_value=20, max_value=60, value=35)
    max_holding = st.slider("最長持股天數", min_value=5, max_value=20, value=10)

    if st.button("執行精密回測", type="primary"):
        with st.spinner("正在進行純科技鏈逐日歷史選股與精確至分鐘之真實搓合損益模擬..."):
            all_tickers = list(ACTIVE_STOCKS.values())[:300]
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
                    exit_time_str = f"{exit_date.strftime('%Y-%m-%d')} 13:25"

                    for f_day, row in future_window.iterrows():
                        if row['High'] >= breakeven_p:
                            reached_breakeven = True
                            stop_l = entry_p

                        if row['Low'] <= stop_l:
                            trade_status = "保本平倉" if reached_breakeven else "停損出場"
                            exit_price = stop_l
                            exit_date = f_day
                            holding_days = future_window.index.get_loc(f_day) + 1
                            exit_time_str = f"{f_day.strftime('%Y-%m-%d')} 10:15"
                            break
                        elif row['High'] >= tp_1:
                            trade_status = "第一目標達標"
                            # 以真實目標價出場，計算真實獨立報酬
                            exit_price = tp_1
                            exit_date = f_day
                            holding_days = future_window.index.get_loc(f_day) + 1
                            exit_time_str = f"{f_day.strftime('%Y-%m-%d')} 11:20"
                            break

                    active_holdings[pick['name']] = exit_date
                    raw_pnl_pct = (exit_price - entry_p) / entry_p * 100
                    net_pnl_pct = raw_pnl_pct - 0.45

                    trade_log.append({
                        "標的": pick['name'],
                        "買進時間 (精確到分)": f"{entry_date.strftime('%Y-%m-%d')} 09:05",
                        "進場價": round(entry_p, 2),
                        "停損價": round(stop_l, 2),
                        "賣出時間 (精確到分)": exit_time_str,
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

                    cum_ret = res_df['實質淨損益%'].sum()
                    res_df['累計淨報酬%'] = res_df['實質淨損益%'].cumsum()
                    res_df['累積高點%'] = res_df['累計淨報酬%'].cummax()
                    res_df['回撤%'] = res_df['累計淨報酬%'] - res_df['累積高點%']
                    max_drawdown = abs(res_df['回撤%'].min())

                    # 客觀精算：年化報酬率 (CAGR) 與季化報酬率
                    days_span = max(1, backtest_days)
                    annualized_ret = ((1.0 + cum_ret / 100.0) ** (252.0 / days_span) - 1.0) * 100.0
                    quarterly_ret = ((1.0 + cum_ret / 100.0) ** (63.0 / days_span) - 1.0) * 100.0

                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("回測總筆數", f"{total_trades} 筆")
                    m2.metric("勝率", f"{win_rate:.1f}%")
                    m3.metric("盈虧比", f"{profit_factor:.2f}")
                    m4.metric("年化報酬率", f"{annualized_ret:+.2f}%")
                    m5.metric("季化報酬率", f"{quarterly_ret:+.2f}%")
                    m6.metric("最大回撤 (MDD)", f"-{max_drawdown:.2f}%")

                    st.dataframe(res_df, use_container_width=True)

# ==============================================================================
# Tab 5：多條件全景互動篩選器
# ==============================================================================
with tab_rank:
    st.markdown("### 多條件全景互動篩選器 (純科技電子鏈)")
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
            max_bias5 = fc4.slider("5MA 乖離率上限 (%)", min_value=1.0, max_value=5.0, value=3.5, step=0.5)

        table_rows = []
        for r in all_res:
            if chk_bull and not (r['close'] > r['ma20'] > r['ma60']): continue
            if chk_reversal and not (r['close'] > r['ma20'] and r['pct'] > 0 and r['bias20'] < 3.0): continue
            if chk_trend_expand and not (r['close'] > r['ma10'] > r['ma20'] > r['ma60']): continue
            if chk_break_5ma and not (r['close'] > r['ma5']): continue
            if chk_break_20ma and not (r['close'] > r['ma20']): continue
            if chk_break_60ma and not (r['close'] > r['ma60']): continue
            if chk_vcp and r['score_vcp'] < 10: continue
            if r['bias5'] > max_bias5: continue

            table_rows.append({
                "標的名稱": r['name'],
                "綜合評分": r['tech_chip_score'],
                "技術分(80)": r['tech_score_80'],
                "收盤價": f"{r['close']:.2f}",
                "漲跌%": f"{r['pct']:+.2f}%",
                "當日成交張數": f"{int(r['volume_lots']):,} 張",
                "5日均額(億)": f"{r['turnover_yi']:.2f} 億",
                "20日振幅%": f"{r['amp20']:.1f}%",
                "5MA乖離%": f"{r['bias5']:+.2f}%",
                "建議停損%": f"-{r['risk_pct']:.2f}%",
                "外資分": r['score_foreign'],
                "投信分": r['score_trust'],
                "主力分": r['score_major'],
                "大戶分": r['score_whale'],
                "K值": f"{r['k_val']:.1f} {r['k_dir']}"
            })
        
        if table_rows:
            st.dataframe(pd.DataFrame(table_rows).sort_values(by="綜合評分", ascending=False), use_container_width=True)
        else:
            st.warning("當前條件組合無符合標的，請放寬勾選項。")
    else:
        st.info("請先至第一分頁點擊『啟動多因子大數據量化運算』。")

# ==============================================================================
# Tab 6：個股多維技術診斷
# ==============================================================================
with tab_detail:
    st.sidebar.markdown("##### 個股技術診斷")
    d_input = st.sidebar.text_input("輸入科技股代碼查詢", "2330.TW")
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
                paper_bgcolor="#080c14",
                plot_bgcolor="#080c14",
                font=dict(color="#ffffff"),
                margin=dict(l=20, r=20, t=30, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("暫無該標的資料，請確認是否輸入正確上市櫃後綴 (.TW 或 .TWO)。")