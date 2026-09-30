"""
台股量化操盤決策系統 v3.1（零執行緒安全防禦 ＆ 完整功能旗艦版）
執行：pip install streamlit yfinance pandas numpy plotly requests lxml html5lib beautifulsoup4 tzdata
     streamlit run tw_quant_app.py
     （背景推播模式）python tw_quant_app.py --daemon
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass
from functools import lru_cache
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================================
# A. 資料來源層（純同步零執行緒安全連線）
# ============================================================================
TZ = ZoneInfo("Asia/Taipei")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

try:
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
except Exception:
    pass


def now_tw() -> dt.datetime:
    return dt.datetime.now(TZ)


def _get(url: str, params: dict | None = None, timeout: int = 15) -> requests.Response:
    last = None
    for verify in (True, False):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout, verify=verify)
            r.raise_for_status()
            return r
        except requests.exceptions.SSLError as e:
            last = e
            continue
        except Exception as e:
            last = e
            break
    raise last  # type: ignore[misc]


def _num(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return np.nan


def load_universe():
    rows, msgs = [], []
    for mode, sfx in ((2, "TW"), (4, "TWO")):
        try:
            r = _get("https://isin.twse.com.tw/isin/C_public.jsp", params={"strMode": mode})
            tbl = pd.read_html(io.StringIO(r.content.decode("big5", errors="ignore")))[0]
            if not any("有價證券" in str(c) for c in tbl.columns):
                tbl.columns = tbl.iloc[0]
                tbl = tbl.iloc[1:]
            cols = [str(c) for c in tbl.columns]
            tbl.columns = cols
            c0 = next((c for c in cols if "有價證券代號" in c), cols[0])
            c_ind = next((c for c in cols if "產業別" in c), None)
            c_cfi = next((c for c in cols if "CFI" in c.upper()), None)
            for _, row in tbl.iterrows():
                cell = str(row[c0])
                if "\u3000" not in cell:
                    continue
                code, name = cell.split("\u3000", 1)
                code = code.strip()
                if not re.fullmatch(r"\d{4}", code):
                    continue
                if c_cfi:
                    cfi = str(row[c_cfi])
                    if cfi not in ("nan", "") and not cfi.startswith("ES"):
                        continue
                rows.append(dict(code=code, name=name.strip(), market=sfx,
                                 industry=str(row[c_ind]).strip() if c_ind else ""))
        except Exception as e:
            msgs.append(f"股票清單（{'上市' if mode == 2 else '上櫃'}）抓取失敗：{e}")
    df = pd.DataFrame(rows).drop_duplicates("code") if rows else pd.DataFrame(columns=["code", "name", "market", "industry"])
    if not df.empty:
        msgs.append(f"股票清單：上市 {int((df.market == 'TW').sum())} 檔、上櫃 {int((df.market == 'TWO').sum())} 檔")
    return df, msgs


def load_daily_turnover():
    out, msgs = {}, []
    try:
        js = _get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL").json()
        for r in js:
            out[str(r.get("Code", "")).strip()] = _num(r.get("TradeValue"))
        msgs.append(f"上市成交值：{len(js)} 檔")
    except Exception as e:
        msgs.append(f"上市成交值抓取失敗：{e}")
    try:
        js = _get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes").json()
        n = 0
        for r in js:
            ck = next((k for k in r if "Code" in k), None)
            ak = next((k for k in r if "Amount" in k), None)
            if ck and ak:
                out[str(r[ck]).strip()] = _num(r[ak])
                n += 1
        msgs.append(f"上櫃成交值：{n} 檔")
    except Exception as e:
        msgs.append(f"上櫃成交值抓取失敗：{e}")
    return pd.Series(out, dtype=float).dropna(), msgs


def load_institutional(n_days: int = 5):
    """三大法人近 n 日累計（主力核心：投信連續買盤與外資動向）"""
    msgs, frames, used = [], [], []
    day = now_tw().date()
    attempts = 0
    while len(used) < n_days and attempts < 12:
        attempts += 1
        if day.weekday() < 5:
            try:
                js = _get("https://www.twse.com.tw/rwd/zh/fund/T86",
                          params={"date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"}).json()
                if js.get("stat") == "OK" and js.get("data"):
                    f = js["fields"]
                    i_code = next(i for i, x in enumerate(f) if "證券代號" in x)
                    i_for = next(i for i, x in enumerate(f) if x.startswith("外陸資買賣超") or ("外資" in x and "買賣超" in x))
                    i_trust = next(i for i, x in enumerate(f) if x.startswith("投信買賣超"))
                    i_tot = next(i for i, x in enumerate(f) if x.startswith("三大法人買賣超"))
                    df = pd.DataFrame([[r[i_code].strip(), _num(r[i_for]), _num(r[i_trust]), _num(r[i_tot])]
                                       for r in js["data"]], columns=["code", "foreign", "trust", "total"])
                    frames.append(df)
                    used.append(day)
                time.sleep(0.2)
            except Exception:
                pass
        day -= dt.timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["foreign", "trust", "total"]), [], ["三大法人資料抓取中斷"]
    out = pd.concat(frames).groupby("code")[["foreign", "trust", "total"]].sum()
    msgs.append(f"法人主力籌碼：累計近 {len(used)} 個交易日")
    return out, used, msgs


def load_revenue_yoy():
    out, msgs = {}, []
    urls = ["https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"]
    for u in urls:
        try:
            js = _get(u).json()
            n = 0
            for r in js:
                ck = next((k for k in r if "公司代號" in k or k.lower().endswith("code")), None)
                yk = next((k for k in r if "去年同月增減" in k), None)
                if ck and yk:
                    out[str(r[ck]).strip()] = _num(r[yk])
                    n += 1
            msgs.append(f"營收 YoY：{n} 檔")
        except Exception:
            pass
    return pd.Series(out, dtype=float), msgs


def load_flags():
    punish, notice, msgs = set(), set(), []
    for name, url, bucket in (("處置股", "https://openapi.twse.com.tw/v1/announcement/punish", punish),
                              ("注意股", "https://openapi.twse.com.tw/v1/announcement/notice", notice)):
        try:
            for r in _get(url).json():
                ck = next((k for k in r if k.lower().endswith("code") or "代號" in k), None)
                if ck:
                    bucket.add(str(r[ck]).strip())
            msgs.append(f"{name}：{len(bucket)} 檔")
        except Exception:
            pass
    return punish, notice, msgs


# ----------------------------------------------------------------------------
# 核心升級：零執行緒 原生 Yahoo Finance HTTP 下載器（徹底杜絕 thread limit 崩潰）
# ----------------------------------------------------------------------------
def _fetch_yahoo_chart_single(ticker: str, session: requests.Session, range_str: str = "2y") -> pd.DataFrame | None:
    enc_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc_ticker}"
    params = {"range": range_str, "interval": "1d"}
    try:
        r = session.get(url, params=params, headers=UA, timeout=10)
        if r.status_code != 200:
            return None
        js = r.json()
        res = js.get("chart", {}).get("result")
        if not res:
            return None
        res0 = res[0]
        timestamps = res0.get("timestamp", [])
        indicators = res0.get("indicators", {})
        quotes = indicators.get("quote", [{}])[0]
        adjclose = indicators.get("adjclose", [{}])[0].get("adjclose", [])

        opens = quotes.get("open", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        closes = adjclose if adjclose else quotes.get("close", [])
        volumes = quotes.get("volume", [])

        if not timestamps or not closes:
            return None

        df = pd.DataFrame({
            "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes
        }, index=pd.to_datetime(timestamps, unit="s"))
        df.index = df.index.tz_localize(None).normalize()
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df if len(df) >= 30 else None
    except Exception:
        return None


def download_prices(tickers: list[str], period: str = "2y", chunk: int = 20, min_len: int = 60) -> dict:
    """純單執行緒同步下載，零多執行緒池，記憶體消耗極低且不會崩潰"""
    out = {}
    range_map = {"3y": "2y", "2y": "2y", "1y": "1y", "7d": "7d", "5d": "5d"}
    q_range = range_map.get(period, "2y")

    with requests.Session() as s:
        for t in tickers:
            df = _fetch_yahoo_chart_single(t, s, range_str=q_range)
            if df is not None and len(df) >= min_len:
                out[t] = df
    return out


def links(code: str, market: str = "TW") -> dict:
    tv = "TPEX" if market == "TWO" else "TWSE"
    return {
        "Yahoo 股市": f"https://tw.stock.yahoo.com/quote/{code}",
        "Goodinfo": f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={code}",
        "玩股網": f"https://www.wantgoo.com/stock/{code}",
        "TradingView": f"https://tw.tradingview.com/chart/?symbol={tv}%3A{code}",
        "公開資訊觀測站": f"https://mops.twse.com.tw/mops/web/t05st01?co_id={code}",
    }


def get_secret(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as _st
        v = _st.secrets.get(name, None)
        return str(v) if v else default
    except Exception:
        return default


def load_names():
    names, markets, msgs = {}, {}, []
    src = [("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "TW", ("公司簡稱",)),
           ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "TWO", ("公司簡稱", "CompanyAbbreviation")),
           ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "TW", ("Name",)),
           ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "TWO", ("CompanyName",))]
    for url, mk, keys in src:
        try:
            js = _get(url).json()
            n = 0
            for r in js:
                ck = next((k for k in r if "公司代號" in k or k.lower().endswith("code")), None)
                nk = next((k for k in keys if k in r), None) or next((k for k in r if "簡稱" in k), None)
                if ck and nk:
                    code, nm = str(r[ck]).strip(), str(r[nk]).strip()
                    if re.fullmatch(r"\d{4}", code) and nm:
                        names.setdefault(code, nm)
                        markets.setdefault(code, mk)
                        n += 1
            msgs.append(f"簡稱來源：{n} 檔")
        except Exception:
            pass
    return names, markets, msgs


TDCC_FILE = Path("tdcc_history.csv")


def load_tdcc():
    msgs = []
    empty = pd.DataFrame(columns=["big400", "big1000", "d_big400", "date"])
    try:
        r = _get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", timeout=20)
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8-sig", errors="ignore")))
        df.columns = [str(c).strip() for c in df.columns]
        c_date, c_code, c_lvl, _, _, c_pct = df.columns[:6]
        df[c_code] = df[c_code].astype(str).str.strip()
        df = df[df[c_code].str.fullmatch(r"\d{4}")]
        lvl = pd.to_numeric(df[c_lvl], errors="coerce")
        pct = pd.to_numeric(df[c_pct], errors="coerce")
        m400, m1000 = lvl.between(12, 15), lvl == 15
        cur = pd.DataFrame({"big400": pct[m400].groupby(df.loc[m400, c_code]).sum(),
                            "big1000": pct[m1000].groupby(df.loc[m1000, c_code]).sum()})
        cur.index.name = "code"
        date = str(df[c_date].iloc[0]).strip()
        if TDCC_FILE.exists():
            hist = pd.read_csv(TDCC_FILE, dtype={"code": str, "date": str})
        else:
            hist = pd.DataFrame(columns=["date", "code", "big400", "big1000"])
        if date not in set(hist["date"]):
            add = cur.reset_index()
            add.insert(0, "date", date)
            hist = pd.concat([hist, add], ignore_index=True)
            try:
                hist.to_csv(TDCC_FILE, index=False)
            except Exception:
                pass
        prev_dates = sorted(d for d in set(hist["date"]) if d < date)
        if prev_dates:
            prev = hist[hist["date"] == prev_dates[-1]].set_index("code")["big400"]
            cur["d_big400"] = cur["big400"] - prev.reindex(cur.index)
        else:
            cur["d_big400"] = np.nan
        cur["date"] = date
        msgs.append(f"集保大戶資料：更新至週 {date}")
        return cur, msgs
    except Exception as e:
        msgs.append(f"集保大戶載入略過：{e}")
        return empty, msgs


def merge_recent(hist: dict, recent: dict) -> dict:
    out = dict(hist)
    for t, r in recent.items():
        if t in out:
            m = pd.concat([out[t], r])
            out[t] = m[~m.index.duplicated(keep="last")].sort_index()
        else:
            out[t] = r
    return out


# ----------------------------------------------------------------------------
# 推播系統與訊號去重
# ----------------------------------------------------------------------------
def send_telegram(token: str, chat_id: str, text: str):
    try:
        for i in range(0, len(text), 3800):
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=12,
                              json={"chat_id": chat_id, "text": text[i:i + 3800], "disable_web_page_preview": True})
            if not r.ok:
                return False, f"Telegram 失敗: {r.text[:100]}"
        return True, "Telegram ✔"
    except Exception as e:
        return False, f"Telegram 例外: {e}"


def send_line(token: str, user_id: str, text: str):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 4500):
            msg = [{"type": "text", "text": text[i:i + 4500]}]
            url = "https://api.line.me/v2/bot/message/push" if user_id else "https://api.line.me/v2/bot/message/broadcast"
            body = {"to": user_id, "messages": msg} if user_id else {"messages": msg}
            r = requests.post(url, headers=headers, json=body, timeout=12)
            if not r.ok:
                return False, f"LINE 失敗: {r.text[:100]}"
        return True, "LINE ✔"
    except Exception as e:
        return False, f"LINE 例外: {e}"


def notify_cfg() -> dict:
    return dict(tg_token=get_secret("TELEGRAM_BOT_TOKEN"), tg_chat=get_secret("TELEGRAM_CHAT_ID"),
                line_token=get_secret("LINE_CHANNEL_TOKEN"), line_user=get_secret("LINE_USER_ID"))


def notify_all(text: str, cfg: dict) -> list:
    res = []
    if cfg.get("tg_token") and cfg.get("tg_chat"):
        res.append(send_telegram(cfg["tg_token"], cfg["tg_chat"], text))
    if cfg.get("line_token"):
        res.append(send_line(cfg["line_token"], cfg.get("line_user", ""), text))
    return res


ALERT_FILE = Path("alert_state.json")
_ALERT_LOCK = threading.Lock()


def _alert_read() -> dict:
    try:
        return json.loads(ALERT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _alert_write(state: dict):
    try:
        ALERT_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def alert_claim(keys: list) -> list:
    with _ALERT_LOCK:
        state = _alert_read()
        seen, now = state.setdefault("seen", {}), time.time()
        fresh = [k for k in dict.fromkeys(keys) if k not in seen]
        for k in fresh:
            seen[k] = now
        for k in [k for k, v in seen.items() if now - v > 4 * 86400]:
            del seen[k]
        _alert_write(state)
        return fresh


def alert_release(keys: list):
    with _ALERT_LOCK:
        state = _alert_read()
        for k in keys:
            state.get("seen", {}).pop(k, None)
        _alert_write(state)


def alert_state_get(name: str, default=None):
    return _alert_read().get("state", {}).get(name, default)


def alert_state_set(name: str, value):
    with _ALERT_LOCK:
        state = _alert_read()
        state.setdefault("state", {})[name] = value
        _alert_write(state)


# ============================================================================
# B. 量化引擎：主力籌碼 ＆ 高勝率縮量回測策略
# ============================================================================
TRADING_DAYS = 252


def tick_size(p: float) -> float:
    if p < 10: return 0.01
    if p < 50: return 0.05
    if p < 100: return 0.1
    if p < 500: return 0.5
    if p < 1000: return 1.0
    return 5.0


def tick_round(p: float, mode: str = "nearest") -> float:
    t = tick_size(p)
    n = p / t
    if mode == "down": n = np.floor(n + 1e-9)
    elif mode == "up": n = np.ceil(n - 1e-9)
    else: n = np.round(n)
    return round(float(n * t), 2)


@dataclass(frozen=True)
class Costs:
    fee_rate: float = 0.001425
    fee_disc: float = 0.6
    tax: float = 0.003
    slip: float = 0.001

    @property
    def fee(self) -> float:
        return self.fee_rate * self.fee_disc

    @property
    def round_trip(self) -> float:
        return 2 * self.fee + self.tax + 2 * self.slip


@dataclass(frozen=True)
class Filters:
    min_price: float = 30.0
    min_turnover: float = 1.0e8
    min_amp: float = 8.0
    bias5_max: float = 4.0
    bias20_max: float = 11.0


@dataclass(frozen=True)
class Params:
    preset: str = "主力波段型"
    min_score: float = 65.0
    stop_atr: float = 1.8
    tp_r: float = 2.5
    hold: int = 15
    trail_atr: float = 2.5

    def label(self) -> str:
        tp = f"停利{self.tp_r}R" if self.tp_r > 0 else "移動停利"
        return f"{self.preset}｜門檻{self.min_score:.0f}｜停損{self.stop_atr}ATR｜{tp}｜追蹤{self.trail_atr}ATR｜持股≤{self.hold}日"


# 全面廢除大戶權重，100% 聚焦主力資金（flow）與相對強度（rs）
PRESETS = {
    "主力波段型": {"trend": 0.25, "compress": 0.10, "mom": 0.10, "rs": 0.25, "flow": 0.30},
    "強勢領頭羊": {"trend": 0.20, "compress": 0.05, "mom": 0.20, "rs": 0.35, "flow": 0.20},
    "支撐回測型": {"trend": 0.30, "compress": 0.20, "mom": 0.10, "rs": 0.20, "flow": 0.20},
}
DEFAULT_GRID = dict(
    preset=list(PRESETS),
    min_score=[62, 68],
    stop_atr=[1.5, 2.0],
    tp_r=[2.0, 3.0, 0.0],
    trail_atr=[2.0, 2.8],
    hold=[12, 18],
)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    d["Volume"] = d["Volume"].fillna(0.0)
    o, c, h, l, v = d["Open"], d["Close"], d["High"], d["Low"], d["Volume"]

    for n in (5, 10, 20, 60):
        d[f"MA{n}"] = c.rolling(n).mean()
    d["MA20_slope5"] = d["MA20"] / d["MA20"].shift(5) - 1
    d["EMA10"] = c.ewm(span=10, adjust=False).mean()
    d["Vol_MA5"] = v.rolling(5).mean()
    d["Vol_MA20"] = v.rolling(20).mean()
    d["Turnover_MA5"] = (c * v).rolling(5).mean()
    d["Amp20"] = (h.rolling(20).max() / l.rolling(20).min() - 1) * 100
    for n in (5, 10, 20, 60):
        d[f"Bias{n}"] = (c / d[f"MA{n}"] - 1) * 100

    std20 = c.rolling(20).std()
    d["BB_Width"] = 4 * std20 / d["MA20"]
    d["BB_Pct"] = d["BB_Width"].rolling(60).rank(pct=True)

    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    d["RSI"] = 100 - 100 / (1 + ag / (al + 1e-12))

    rng9 = h.rolling(9).max() - l.rolling(9).min()
    rsv = ((c - l.rolling(9).min()) / (rng9 + 1e-9) * 100).fillna(50)
    d["K"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d["D"] = d["K"].ewm(alpha=1 / 3, adjust=False).mean()

    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["MACD_Hist"] = dif - dif.ewm(span=9, adjust=False).mean()

    # 主力資金作手特徵（CLV + CMF 資金流）
    clv = ((c - l) - (h - c)) / (h - l + 1e-9)
    d["CLV5"] = (clv * v).rolling(5).sum() / (v.rolling(5).sum() + 1e-9)
    d["CMF20"] = (clv * v).rolling(20).sum() / (v.rolling(20).sum() + 1e-9)
    big = v > 1.3 * d["Vol_MA20"].shift(1)
    acc = (big & (c > o) & (clv > 0.3)).astype(float)
    dist = (big & (c < o) & (clv < -0.3)).astype(float)
    d["AD_net20"] = acc.rolling(20).sum() - dist.rolling(20).sum()
    upv = v.where(c > pc, 0.0).rolling(20).sum()
    dnv = v.where(c < pc, 0.0).rolling(20).sum()
    d["UDVR"] = upv / (dnv + 1.0)

    # 縮量窒息洗盤特徵（避開追高，專抓主力洗盤點）
    d["Vol_Shrink"] = (v < d["Vol_MA5"] * 0.75).astype(float)
    d["Close_loc"] = (c - l) / (h - l + 1e-9)
    d["Range5"] = (h.rolling(5).max() - l.rolling(5).min()) / c * 100
    d["Low5"] = l.rolling(5).min()
    d["High20_prev"] = h.rolling(20).max().shift(1)
    d["pct"] = c.pct_change() * 100
    return d


PANEL_FIELDS = [
    "Open", "High", "Low", "Close", "Volume", "MA5", "MA10", "MA20", "MA60", "MA20_slope5", "EMA10",
    "Vol_MA5", "Vol_MA20", "Turnover_MA5", "Amp20", "Bias5", "Bias10", "Bias20", "BB_Pct", "ATR", "RSI",
    "K", "D", "MACD_Hist", "CLV5", "CMF20", "AD_net20", "UDVR", "Vol_Shrink", "Close_loc", "Range5",
    "Low5", "High20_prev", "pct"
]


def build_panel(stock_dfs: dict) -> dict:
    P = {}
    for f in PANEL_FIELDS:
        P[f] = pd.concat({code: df[f] for code, df in stock_dfs.items()}, axis=1).sort_index()
    return P


def compute_features(P: dict, bench_close: pd.Series) -> dict:
    C = P["Close"]
    Cf = C.ffill()
    b = bench_close.reindex(C.index).ffill()
    rs20 = (Cf / Cf.shift(20) - 1).sub(b / b.shift(20) - 1, axis=0)
    rs60 = (Cf / Cf.shift(60) - 1).sub(b / b.shift(60) - 1, axis=0)

    f = {}
    f["trend"] = 0.25 * ((C > P["MA20"]).astype(float) + (P["MA20"] > P["MA60"]).astype(float)
                         + (P["MA20_slope5"] > 0).astype(float) + (P["EMA10"] > P["MA20"]).astype(float))
    f["compress"] = 0.6 * (1 - P["BB_Pct"]) + 0.4 * (P["Range5"] < 6).astype(float)
    f["mom"] = (0.35 * ((P["RSI"] >= 50) & (P["RSI"] <= 68)).astype(float)
                + 0.35 * (P["MACD_Hist"] > 0).astype(float)
                + 0.30 * ((P["K"] > P["D"]) & (P["K"] <= 78)).astype(float))
    rs = 0.6 * rs20 + 0.4 * rs60
    f["rs"] = (rs / 0.18).clip(-1, 1) * 0.5 + 0.5

    # 主力資金作手權重
    f["flow"] = (0.40 * ((P["CMF20"] + 0.08) / 0.28).clip(0, 1)
                 + 0.35 * ((P["AD_net20"] + 1) / 4).clip(0, 1)
                 + 0.25 * ((P["UDVR"] - 0.8) / 1.2).clip(0, 1))

    # 型態升級：專注「均線多頭＋縮量壓回 10EMA/20MA 止跌」
    pullback = ((P["MA20_slope5"] > 0) & (P["Bias20"].abs() <= 2.8) & (P["Bias5"].abs() <= 2.0)
                & (P["Vol_Shrink"] > 0) & (C > P["MA20"])).astype(float)
    breakout = ((C > P["High20_prev"]) & (P["Volume"] > 1.3 * P["Vol_MA20"]) & (P["Close_loc"] > 0.6)).astype(float)

    f["setup"] = np.maximum(pullback, 0.6 * breakout)
    return f


def composite_score(feats: dict, preset: str) -> pd.DataFrame:
    w = PRESETS[preset]
    tot = sum(w.values())
    return sum(feats[k] * v for k, v in w.items()) / tot * 100


def universe_masks(P: dict, flt: Filters):
    C = P["Close"]
    liquid = ((C > flt.min_price) & (P["Turnover_MA5"] >= flt.min_turnover) & (P["Amp20"] >= flt.min_amp)
              & (P["Volume"] > 0) & P["MA60"].notna() & P["ATR"].notna())
    trend_ok = (C > P["MA20"]) & (C > P["MA60"]) & (P["MA20_slope5"] > -0.003)
    heat_ok = (P["Bias5"] <= flt.bias5_max) & (P["Bias20"] <= flt.bias20_max)
    return liquid, liquid & trend_ok & heat_ok


def regime_levels(bench_close: pd.Series, idx, P: dict):
    b = bench_close.reindex(idx).ffill()
    ma20, ma60 = b.rolling(20).mean(), b.rolling(60).mean()
    strong = (b > ma20) & (ma20 > ma60)
    weak = (b < ma20) & (b < ma60)
    lvl = pd.Series(1, index=idx)
    lvl[strong] = 2
    lvl[weak] = 0
    lvl[ma60.isna()] = 0
    C = P["Close"]
    breadth = ((C > P["MA20"]).sum(axis=1) / C.notna().sum(axis=1).replace(0, np.nan)).fillna(0.5)
    lvl = lvl.where(breadth >= 0.30, (lvl - 1).clip(lower=0))
    return lvl.to_numpy().astype(int), breadth


def plan_trade(fill: float, atr: float, low5: float, stop_atr: float, tp_r: float):
    stop_raw = fill - stop_atr * atr
    struct = low5 * 0.99
    stop = max(stop_raw, struct)
    risk = float(np.clip((fill - stop) / fill, 0.035, 0.08))
    stop = tick_round(fill * (1 - risk))
    R = fill - stop
    tp = tick_round(fill + tp_r * R) if tp_r > 0 else float("inf")
    return stop, tp, R


def size_position(capital: float, risk_pct: float, entry: float, stop: float, max_alloc: float = 0.25) -> dict:
    per_share = max(entry - stop, 1e-9)
    by_risk = int(capital * risk_pct / 100.0 / per_share)
    by_alloc = int(capital * max_alloc / entry)
    shares = max(0, min(by_risk, by_alloc))
    return dict(shares=shares, lots=shares // 1000, odd=shares % 1000, amount=shares * entry,
                pct_capital=shares * entry / capital * 100 if capital else 0.0,
                risk_amt=shares * per_share, binding="風險上限" if by_risk <= by_alloc else "單檔25%資金上限")


class Engine:
    def __init__(self, P: dict, bench_close: pd.Series, flt: Filters, costs: Costs,
                 capital: float = 1_000_000.0, risk_frac: float = 0.015):
        self.P, self.flt, self.costs, self.capital, self.risk_frac = P, flt, costs, capital, risk_frac
        self.idx = P["Close"].index
        self.codes = list(P["Close"].columns)
        self.feats = compute_features(P, bench_close)
        self.scores = {k: composite_score(self.feats, k) for k in PRESETS}
        self.liquid, self.elig = universe_masks(P, flt)
        self.regime_lvl, self.breadth = regime_levels(bench_close, self.idx, P)
        self.regime = self.regime_lvl > 0
        self.bench_close = bench_close
        C = P["Close"]
        self.arr = dict(O=P["Open"].to_numpy(), H=P["High"].to_numpy(), L=P["Low"].to_numpy(),
                        C=C.to_numpy(), Cf=C.ffill().to_numpy(), ATR=P["ATR"].to_numpy(),
                        LOW5=P["Low5"].to_numpy())
        self._rank_cache = {}

    def ranks(self, preset: str, min_score: float, topk: int = 6):
        key = (preset, float(min_score), topk)
        if key not in self._rank_cache:
            S = self.scores[preset].where(self.elig & (self.scores[preset] >= min_score)).to_numpy()
            filled = np.where(np.isnan(S), -np.inf, S)
            order = np.argsort(-filled, axis=1)[:, :topk]
            vals = np.take_along_axis(S, order, axis=1)
            self._rank_cache[key] = (order, vals)
        return self._rank_cache[key]


MAX_BY_LEVEL = {0: 0, 1: 2, 2: 4}


def simulate(eng: Engine, params: Params, start: int, end: int, max_pos: int = 4):
    A = eng.arr
    O, H, L, C, Cf, ATR, LOW5 = A["O"], A["H"], A["L"], A["C"], A["Cf"], A["ATR"], A["LOW5"]
    order, valid = eng.ranks(params.preset, params.min_score)
    lvl, costs = eng.regime_lvl, eng.costs
    fee, slip, tax = costs.fee, costs.slip, costs.tax
    init = eng.capital
    cash, pos, trades, eq_vals, eq_idx = init, [], [], [], []
    start = max(start, 1)
    end = min(end, len(eng.idx))

    def close_pos(p, d, px, reason):
        nonlocal cash
        cash += p["sh"] * px * (1 - slip - fee - tax)
        net = (px * (1 - slip - fee - tax) / (p["fill"] * (1 + fee)) - 1) * 100
        trades.append(dict(code=eng.codes[p["j"]], entry_date=eng.idx[p["d0"]], exit_date=eng.idx[d],
                           fill=p["fill"], exit=px, reason=reason, days=d - p["d0"] + 1,
                           net_pct=net, r_mult=(px - p["fill"]) / p["R"]))

    for d in range(start, end):
        allowed = min(max_pos, MAX_BY_LEVEL[int(lvl[d - 1])])
        if len(pos) < allowed:
            held = {p["j"] for p in pos}
            for k in range(order.shape[1]):
                if np.isnan(valid[d - 1, k]):
                    break
                j = int(order[d - 1, k])
                if j in held:
                    continue
                o, pc, atr, low5 = O[d, j], C[d - 1, j], ATR[d - 1, j], LOW5[d - 1, j]
                if np.isnan(o) or np.isnan(pc) or np.isnan(atr) or np.isnan(low5):
                    continue
                if o / pc - 1 >= 0.085:
                    continue
                fill = o * (1 + slip)
                stop, tp, R = plan_trade(fill, atr, low5, params.stop_atr, params.tp_r)
                equity = cash + sum(p["sh"] * Cf[d - 1, p["j"]] for p in pos)
                alloc = min(equity / max_pos, cash, equity * eng.risk_frac / max(R / fill, 1e-9))
                sh = int(alloc / (fill * (1 + fee)))
                if sh <= 0:
                    continue
                cash -= sh * fill * (1 + fee)
                pos.append(dict(j=j, d0=d, fill=fill, stop=stop, tp=tp, R=R, sh=sh, atr=atr, hh=fill))
                break

        for p in list(pos):
            j = p["j"]
            o, h, l, c = O[d, j], H[d, j], L[d, j], C[d, j]
            if np.isnan(c):
                continue
            px = reason = None
            if o <= p["stop"]:
                px, reason = o, "跳空停損"
            elif l <= p["stop"]:
                px, reason = p["stop"]
                reason = "停損" if p["stop"] < p["fill"] else "移動停利"
            elif o >= p["tp"]:
                px, reason = o, "跳空達標"
            elif h >= p["tp"]:
                px, reason = p["tp"], "達標停利"
            elif d - p["d0"] + 1 >= params.hold:
                px, reason = c, "期滿出場"

            if px is not None:
                close_pos(p, d, px, reason)
                pos.remove(p)
            else:
                p["hh"] = max(p["hh"], h)
                if p["hh"] >= p["fill"] + 1.0 * p["R"]:
                    p["stop"] = max(p["stop"], tick_round(p["fill"] * 1.008))
                if p["hh"] >= p["fill"] + 1.8 * p["R"]:
                    p["stop"] = max(p["stop"], tick_round(p["hh"] - params.trail_atr * p["atr"]))

        eq_vals.append(cash + sum(p["sh"] * Cf[d, p["j"]] for p in pos))
        eq_idx.append(eng.idx[d])

    for p in list(pos):
        close_pos(p, end - 1, Cf[end - 1, p["j"]], "視窗結束")
    if eq_vals:
        eq_vals[-1] = cash
    equity = pd.Series(eq_vals, index=eq_idx, dtype=float) / init
    return pd.DataFrame(trades), equity


def summarize(trades: pd.DataFrame, equity: pd.Series | None = None) -> dict:
    s = dict(n=len(trades), win_rate=np.nan, avg_win=np.nan, avg_loss=np.nan, payoff=np.nan, expectancy=np.nan,
             profit_factor=np.nan, tstat=np.nan, max_consec_loss=0, avg_hold=np.nan,
             total_ret=np.nan, cagr=np.nan, mdd=np.nan, sharpe=np.nan)
    if len(trades):
        r = trades["net_pct"].to_numpy()
        n = len(r)
        wins, losses = r[r > 0], r[r <= 0]
        s["win_rate"] = len(wins) / n * 100
        s["avg_win"] = wins.mean() if len(wins) else 0.0
        s["avg_loss"] = losses.mean() if len(losses) else 0.0
        s["payoff"] = abs(s["avg_win"] / s["avg_loss"]) if s["avg_loss"] < 0 else np.nan
        s["expectancy"] = r.mean()
        s["profit_factor"] = wins.sum() / abs(losses.sum()) if losses.sum() < 0 else np.nan
        sd = r.std(ddof=1) if n > 1 else np.nan
        s["tstat"] = r.mean() / (sd / np.sqrt(n)) if (n > 1 and sd and sd > 0) else np.nan
        run = best = 0
        for x in r:
            run = run + 1 if x <= 0 else 0
            best = max(best, run)
        s["max_consec_loss"] = best
        s["avg_hold"] = trades["days"].mean()
    if equity is not None and len(equity) > 1:
        s["total_ret"] = (equity.iloc[-1] - 1) * 100
        s["mdd"] = abs((equity / equity.cummax() - 1).min()) * 100
        if len(equity) >= 120:
            s["cagr"] = (equity.iloc[-1] ** (TRADING_DAYS / len(equity)) - 1) * 100
        dr = equity.pct_change().dropna()
        if dr.std() > 0:
            s["sharpe"] = dr.mean() / dr.std() * np.sqrt(TRADING_DAYS)
    return s


def bench_return(bench_close: pd.Series, index) -> tuple[pd.Series, float]:
    b = bench_close.reindex(index).ffill().dropna()
    if len(b) < 2:
        return pd.Series(dtype=float), np.nan
    curve = b / b.iloc[0]
    return curve, (curve.iloc[-1] - 1) * 100


def mc_ruin(trade_rets_pct, n_sims=1500, n_trades=50, frac=0.25, block=3, ruin=0.5, seed=42) -> dict:
    r = np.asarray(trade_rets_pct, dtype=float) / 100.0
    n = len(r)
    if n < 5:
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n_trades / block))
    starts = rng.integers(0, n, size=(n_sims, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    seq = r[idx].reshape(n_sims, -1)[:, :n_trades]
    eq = np.concatenate([np.ones((n_sims, 1)), np.cumprod(1 + frac * seq, axis=1)], axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    mdd = -(eq / peak - 1).min(axis=1) * 100
    return dict(curves=eq, end_mean=eq[:, -1].mean(), end_p5=np.percentile(eq[:, -1], 5),
                mdd95=np.percentile(mdd, 95), p_ruin=(eq.min(axis=1) <= ruin).mean() * 100)


def walk_forward(eng: Engine, grid: dict | None = None, train_days: int = 240, test_days: int = 60,
                 min_trades: int = 10, progress=None, warm: int = 60):
    grid = grid or DEFAULT_GRID
    combos = [Params(preset=a, min_score=b, stop_atr=c, tp_r=d, trail_atr=e, hold=f)
              for a, b, c, d, e, f in product(grid["preset"], grid["min_score"], grid["stop_atr"],
                                              grid["tp_r"], grid["trail_atr"], grid["hold"])]
    T = len(eng.idx)
    folds, a = [], warm
    while a + train_days + test_days <= T:
        folds.append((a, a + train_days, a + train_days + test_days))
        a += test_days
    if not folds:
        return None

    step = 0
    total = len(folds) * len(combos)
    rows, oos_trades, chained = [], [], []
    level = 1.0

    for fi, (tr_s, tr_e, te_e) in enumerate(folds):
        best_obj, best_c = -1e9, combos[0]
        for c in combos:
            t, q = simulate(eng, c, tr_s, tr_e)
            st_ = summarize(t, q)
            obj = (st_["expectancy"] if st_["n"] >= min_trades else -1e9)
            if obj > best_obj:
                best_obj, best_c = obj, c
            step += 1
            if progress and step % 10 == 0:
                progress(min(step / total, 0.95))

        t_oos, q_oos = simulate(eng, best_c, tr_e, te_e)
        st_oos = summarize(t_oos, q_oos)
        rows.append(dict(fold=fi + 1, train=f"{eng.idx[tr_s].date()}~{eng.idx[tr_e-1].date()}",
                         test=f"{eng.idx[tr_e].date()}~{eng.idx[te_e-1].date()}", params=best_c.label(),
                         test_n=st_oos["n"], test_exp=st_oos["expectancy"], test_ret=st_oos["total_ret"],
                         test_mdd=st_oos["mdd"]))
        if len(t_oos):
            oos_trades.append(t_oos)
        chained.append(q_oos * level)
        level = chained[-1].iloc[-1]

    oos_tr = pd.concat(oos_trades, ignore_index=True) if oos_trades else pd.DataFrame()
    oos_eq = pd.concat(chained) if chained else pd.Series(dtype=float)
    oos_stats = summarize(oos_tr, oos_eq if len(oos_eq) else None)
    return dict(folds=pd.DataFrame(rows), oos_trades=oos_tr, oos_equity=oos_eq, oos_stats=oos_stats,
                final_params=best_c, train_days=train_days, test_days=test_days)


# ============================================================================
# 主力籌碼加減分：100% 聚焦投信與外資
# ============================================================================
def make_main_force_chip_fn(chips, tdcc, weight: float = 1.0):
    def fn(code: str, close: float, turnover5: float):
        b, det = 0.0, {}
        if chips is not None and len(chips) and code in chips.index and turnover5 > 0:
            r = chips.loc[code]
            denom = turnover5 * 5
            f_ratio = float(r["foreign"]) * close / denom
            t_ratio = float(r["trust"]) * close / denom
            # 投信主導波段佔 6 分，外資佔 4 分
            b += float(np.clip(t_ratio / 0.03, -1, 1)) * 6.0 + float(np.clip(f_ratio / 0.05, -1, 1)) * 4.0
            det.update(foreign=float(r["foreign"]), trust=float(r["trust"]), total=float(r["total"]))
        if tdcc is not None and len(tdcc) and code in tdcc.index:
            r = tdcc.loc[code]
            det.update(big400=float(r["big400"]) if pd.notna(r["big400"]) else np.nan,
                       d_big400=float(r["d_big400"]) if pd.notna(r["d_big400"]) else np.nan)
        return float(b * weight), det
    return fn


def latest_candidates(eng: Engine, params: Params, top: int = 10, exclude: set | None = None, chip_fn=None) -> list:
    S = eng.scores[params.preset].iloc[-1]
    E = eng.elig.iloc[-1]
    m = E & (S >= params.min_score)
    if exclude:
        m &= ~S.index.isin(list(exclude))
    P = eng.P
    pool = S[m].sort_values(ascending=False).index[:max(top * 3, 25)]
    out = []
    for code in pool:
        close = float(P["Close"][code].iloc[-1])
        fill = close * (1 + eng.costs.slip)
        stop, tp, R = plan_trade(fill, float(P["ATR"][code].iloc[-1]), float(P["Low5"][code].iloc[-1]),
                                 params.stop_atr, params.tp_r)
        turn5 = float(P["Turnover_MA5"][code].iloc[-1])
        bonus, det = chip_fn(code, close, turn5) if chip_fn else (0.0, {})
        tech = float(S[code])
        out.append(dict(code=code, score=tech, bonus=bonus, final=tech + bonus, chip=det, close=close,
                        pct=float(P["pct"][code].iloc[-1]), stop=stop, tp=tp, risk_pct=(fill - stop) / fill * 100,
                        turnover_yi=turn5 / 1e8, volume_lots=float(P["Volume"][code].iloc[-1]) / 1000,
                        bias5=float(P["Bias5"][code].iloc[-1]), bias20=float(P["Bias20"][code].iloc[-1]),
                        k=float(P["K"][code].iloc[-1]), rsi=float(P["RSI"][code].iloc[-1]),
                        sub={k: float(eng.feats[k][code].iloc[-1]) * 100
                             for k in ("trend", "compress", "mom", "rs", "flow", "setup")}))
    out.sort(key=lambda r: r["final"], reverse=True)
    return out[:top]


def detect_events(d: pd.DataFrame) -> list:
    x, p = d.iloc[-1], d.iloc[-2]
    c = float(x["Close"])
    vr = float(x["Volume"] / (x["Vol_MA20"] + 1e-9))
    body = abs(c - x["Open"]) / (x["High"] - x["Low"] + 1e-9)
    ev = []
    if c > x["High20_prev"] and vr > 1.3: ev.append(("breakout20", "🚀 突破20日新高且放量"))
    if c > x["MA20"] and p["Close"] <= p["MA20"]: ev.append(("up_ma20", "⬆ 站上月線"))
    if c < x["MA20"] and p["Close"] >= p["MA20"]: ev.append(("dn_ma20", "⬇ 跌破月線"))
    if x["K"] > x["D"] and p["K"] <= p["D"] and x["K"] < 80: ev.append(("kd_gold", "KD 黃金交叉"))
    if x["K"] < x["D"] and p["K"] >= p["D"] and p["K"] > 70: ev.append(("kd_dead", "KD 高檔死亡交叉"))
    if x["MACD_Hist"] > 0 and p["MACD_Hist"] <= 0: ev.append(("macd_up", "MACD 翻紅"))
    if x["MACD_Hist"] < 0 and p["MACD_Hist"] >= 0: ev.append(("macd_dn", "MACD 翻綠"))
    if vr > 2 and c > x["Open"] and body > 0.6: ev.append(("big_red", "🔥 主力放量長紅"))
    if vr > 2 and c < x["Open"] and body > 0.6: ev.append(("big_black", "⚠ 爆量長黑出貨"))
    return ev


SCREEN_FLAGS = [
    "多頭排列 (收盤>20MA>60MA)", "空轉多 (3日內站上月線)", "多頭擴大 (5>10>20>60MA)", "今日強勢漲停 (≥9.5%)",
    "突破週線 (3日內站上5MA)", "突破月線 (3日內站上20MA)", "突破季線 (3日內站上60MA)", "創20日新高",
    "量縮整理 (帶寬低檔+5日振幅<6%)", "窒息量縮 (量<20日均量60%)", "主力出擊 (量>5日均量1.5倍)",
    "主力量價鎖碼 (CLV推力>0.15)", "MACD 紅柱", "RSI 50–68 健康動能", "KD 黃金交叉 (K>D 且 K<80)",
]


def snapshot(eng: Engine, preset: str) -> pd.DataFrame:
    P = eng.P
    C = P["Close"]

    def cross(a, b, k=3):
        x = ((a > b) & (a.shift(1) <= b.shift(1))).astype(float)
        return x.rolling(k).max().iloc[-1] > 0

    last = lambda df: df.iloc[-1]
    flags = {
        SCREEN_FLAGS[0]: last((C > P["MA20"]) & (P["MA20"] > P["MA60"])),
        SCREEN_FLAGS[1]: cross(C, P["MA20"]),
        SCREEN_FLAGS[2]: last((P["MA5"] > P["MA10"]) & (P["MA10"] > P["MA20"]) & (P["MA20"] > P["MA60"])),
        SCREEN_FLAGS[3]: last(P["pct"]) >= 9.5,
        SCREEN_FLAGS[4]: cross(C, P["MA5"]),
        SCREEN_FLAGS[5]: cross(C, P["MA20"]),
        SCREEN_FLAGS[6]: cross(C, P["MA60"]),
        SCREEN_FLAGS[7]: last(C > P["High20_prev"]),
        SCREEN_FLAGS[8]: last((P["BB_Pct"] <= 0.25) & (P["Range5"] < 6)),
        SCREEN_FLAGS[9]: last(P["Volume"] < P["Vol_MA20"] * 0.6),
        SCREEN_FLAGS[10]: last(P["Volume"] > P["Vol_MA5"] * 1.5),
        SCREEN_FLAGS[11]: last(P["CLV5"] > 0.15),
        SCREEN_FLAGS[12]: last(P["MACD_Hist"] > 0),
        SCREEN_FLAGS[13]: last((P["RSI"] >= 50) & (P["RSI"] <= 68)),
        SCREEN_FLAGS[14]: last((P["K"] > P["D"]) & (P["K"] < 80)),
    }
    out = pd.DataFrame({
        "close": last(C), "pct": last(P["pct"]), "volume_lots": last(P["Volume"]) / 1000,
        "turnover_yi": last(P["Turnover_MA5"]) / 1e8, "bias5": last(P["Bias5"]), "bias20": last(P["Bias20"]),
        "K": last(P["K"]), "RSI": last(P["RSI"]), "score": last(eng.scores[preset]),
        "liquid": last(eng.liquid), "eligible": last(eng.elig),
    })
    for k, v in flags.items():
        out[k] = v.astype(bool)
    return out


def bull_bear_checks(d: pd.DataFrame, chip: dict | None = None, rev_yoy: float | None = None) -> dict:
    bull, bear = [], []
    x, p = d.iloc[-1], d.iloc[-2]
    c = x["Close"]
    if c > x["MA5"]: bull.append("站上週線 5MA")
    if c > x["MA20"]: bull.append("站上月線 20MA")
    if c > x["MA60"]: bull.append("站上季線 60MA")
    if x["MA5"] > x["MA10"] > x["MA20"]: bull.append("短天期均線多頭排列")
    if 50 <= x["K"] <= 80 and x["K"] > x["D"]: bull.append("KD 強勢黃金交叉")
    if x["MACD_Hist"] > 0: bull.append("MACD 柱狀體翻紅")
    if 50 <= x["RSI"] <= 68: bull.append("RSI 處於健康動能波")
    if x["Volume"] > x["Vol_MA5"] * 1.25 and c > p["Close"]: bull.append("主力價漲量增攻擊")
    if c < x["MA20"]: bear.append("跌破月線")
    if c < x["MA60"]: bear.append("跌破季線")
    if x["Bias20"] > 11: bear.append("乖離率偏高，慎防洗盤")
    if x["MACD_Hist"] < 0: bear.append("MACD 綠柱走弱")
    if chip:
        if chip.get("trust", 0) > 300_000: bull.append("投信近5日鎖碼買超")
        elif chip.get("trust", 0) < -300_000: bear.append("投信持續提款賣超")
        if chip.get("foreign", 0) > 1_000_000: bull.append("外資連續買超支援")
    if rev_yoy is not None and not np.isnan(rev_yoy):
        if rev_yoy >= 20: bull.append(f"月營收年增達 {rev_yoy:.0f}%")
        elif rev_yoy < 0: bear.append(f"月營收年減 {rev_yoy:.0f}%")
    return dict(bull=bull, bear=bear)


def holding_health(d: pd.DataFrame, params: Params) -> dict:
    x = d.iloc[-1]
    close = float(x["Close"])
    stop, tp, _ = plan_trade(close, float(x["ATR"]), float(x["Low5"]), params.stop_atr, params.tp_r)
    flags, weak = [], 0
    if close < x["MA20"]: flags.append("跌破月線"); weak += 2
    if x["MA20_slope5"] < 0: flags.append("月線下彎走空"); weak += 1
    if close < x["MA60"]: flags.append("跌破季線"); weak += 2
    if x["RSI"] < 45: flags.append("RSI<45 動能衰退"); weak += 1
    if close <= stop: flags.append("跌破量化防守價"); weak += 3
    return dict(close=close, stop=stop, tp=tp, weak=weak, flags=flags)


# ============================================================================
# C. 題材庫與持股儲存
# ============================================================================
SECTORS = {
    "CPO 矽光子與光通訊": [("3450", "聯鈞", ["光收發", "CPO"]), ("3363", "上詮", ["光纖陣列", "CPO"]),
                          ("3081", "聯亞", ["磊晶", "InP"]), ("4979", "華星光", ["AOC", "光模組"]),
                          ("6442", "光聖", ["光被動"]), ("4977", "眾達-KY", ["CPO", "光模組"])],
    "散熱模組與水冷系統": [("3017", "奇鋐", ["水冷板", "散熱模組"]), ("3324", "雙鴻", ["液冷", "CDU"]),
                          ("3653", "健策", ["均熱片"]), ("8996", "高力", ["熱交換器"]),
                          ("6230", "超眾", ["熱導管"]), ("3483", "力致", ["散熱模組"])],
    "重電綠能與強韌電網": [("1513", "中興電", ["儲能", "GIS"]), ("1519", "華城", ["外銷變壓器"]),
                          ("1503", "士電", ["重電配電盤"]), ("1514", "亞力", ["半導體廠務電網"]),
                          ("1609", "大亞", ["綠能電纜", "儲能"])],
    "AI 伺服器與硬體代工": [("2382", "廣達", ["AI伺服器代工"]), ("3231", "緯創", ["GPU模組基板"]),
                           ("2376", "技嘉", ["伺服器代工"]), ("6669", "緯穎", ["雲端ASIC ODM"]),
                           ("2059", "川湖", ["伺服器滑軌"]), ("8210", "勤誠", ["伺服器機殼"])],
    "PCB、載板與 CCL": [("2383", "台光電", ["CCL無鹵基板"]), ("3037", "欣興", ["ABF載板"]),
                       ("2368", "金像電", ["伺服器高層板"]), ("6274", "台燿", ["高速CCL"]),
                       ("3189", "景碩", ["BT/ABF載板"])],
    "半導體製造與設備": [("2330", "台積電", ["晶圓代工"]), ("3583", "辛耘", ["CoWoS濕製程"]),
                        ("3131", "弘塑", ["先進封裝設備"]), ("6223", "旺矽", ["垂直探針卡"]),
                        ("1560", "中砂", ["鑽石碟", "再生晶圓"])],
    "機器人自動化與工具機": [("2359", "所羅門", ["AI機器視覺"]), ("2365", "昆盈", ["影像感測元件"]),
                            ("6188", "廣明", ["協作型機器手臂"]), ("8374", "羅昇", ["智動化傳動控制"]),
                            ("4583", "台灣精銳", ["高精密減速機"])],
}
NAME_MAP = {c: n for v in SECTORS.values() for c, n, _ in v}
TAG_MAP = {c: t for v in SECTORS.values() for c, _, t in v}

PORTFOLIO_FILE = Path("portfolio.json")
DEFAULT_PORTFOLIO = [
    {"code": "2330", "cost": 960.0, "shares": 1000, "date": "2026-09-10"},
    {"code": "3017", "cost": 650.0, "shares": 1000, "date": "2026-09-15"},
    {"code": "1513", "cost": 168.0, "shares": 5000, "date": "2026-09-20"},
]


def load_portfolio() -> list:
    try:
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [dict(x) for x in DEFAULT_PORTFOLIO]


def save_portfolio(rows: list):
    PORTFOLIO_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


WATCHLIST_FILE = Path("watchlist.json")


def load_watchlist() -> list:
    try:
        return [str(x).strip() for x in json.loads(WATCHLIST_FILE.read_text(encoding="utf-8")) if str(x).strip()]
    except Exception:
        return ["3450", "2383", "3653"]


def save_watchlist(codes: list):
    WATCHLIST_FILE.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")


def load_meta_core(hour_key: str) -> dict:
    uni, m1 = load_universe()
    turn, m2 = load_daily_turnover()
    names, markets, m6 = load_names()
    chips, chip_days, m3 = load_institutional(5)
    tdcc, m7 = load_tdcc()
    rev, m4 = load_revenue_yoy()
    punish, notice, m5 = load_flags()
    if uni.empty and markets:
        uni = pd.DataFrame([dict(code=c, name=names.get(c, c), market=m, industry="") for c, m in markets.items()])
    return dict(uni=uni, turn=turn, names=names, markets=markets, chips=chips, chip_days=chip_days, tdcc=tdcc,
                rev=rev, punish=punish, notice=notice, msgs=m1 + m6 + m2 + m3 + m7 + m4 + m5)


def build_name_market(meta: dict):
    uni = meta["uni"]
    names = dict(NAME_MAP)
    names.update(dict(zip(uni["code"], uni["name"])))
    names.update(meta["names"])
    market = {**meta["markets"], **dict(zip(uni["code"], uni["market"]))}
    return names, market


def build_engine_core(meta, n, excl, min_price, min_turn_yi, fee_disc, slip_pct, risk_frac, get_prices_fn):
    uni = meta["uni"].copy()
    if not uni.empty:
        if excl:
            uni = uni[~uni["industry"].isin(list(excl))]
        if len(meta["turn"]):
            uni["turn"] = uni["code"].map(meta["turn"])
            uni = uni.dropna(subset=["turn"]).sort_values("turn", ascending=False).head(n)
        else:
            uni = uni[uni["code"].isin(NAME_MAP)]
    else:
        uni = pd.DataFrame([dict(code=c, name=NAME_MAP[c], market="TW", industry="") for c in NAME_MAP])

    tickers = [f"{r.code}.{r.market}" for r in uni.itertuples()]
    prices = get_prices_fn(tuple(tickers + ["^TWII"]))
    bench = prices.pop("^TWII", None)
    if bench is None or not prices:
        raise RuntimeError("加權指數或價格資料連線逾時，請點擊重試。")

    dfs = {}
    for t, df in prices.items():
        try:
            dfs[t.split(".")[0]] = add_indicators(df)
        except Exception:
            continue
    P = build_panel(dfs)
    flt = Filters(min_price, min_turn_yi * 1e8, 8.0, 4.0, 11.0)
    eng = Engine(P, bench["Close"], flt, Costs(fee_disc=fee_disc, slip=slip_pct / 100.0), risk_frac=risk_frac)
    return eng, bench


def get_ind_map(codes: list, market: dict, get_prices_fn) -> dict:
    codes = [c for c in dict.fromkeys(str(c).strip() for c in codes) if c]
    if not codes:
        return {}
    out, miss = {}, []
    first = {c: f"{c}.{market.get(c, 'TW')}" for c in codes}
    px = get_prices_fn(tuple(first.values()))
    for c, t in first.items():
        if t in px:
            out[c] = add_indicators(px[t])
        else:
            miss.append(c)
    if miss:
        alt = {c: f"{c}.{'TWO' if market.get(c, 'TW') == 'TW' else 'TW'}" for c in miss}
        px2 = get_prices_fn(tuple(alt.values()))
        for c, t in alt.items():
            if t in px2:
                out[c] = add_indicators(px2[t])
    return out


@dataclass
class Alert:
    key: str
    cat: str
    text: str


ALERT_CATS = {"regime": "大盤環境轉折", "cand": "主力首選推薦", "hold": "持股部位警示", "watch": "自選股事件雷達"}
LVL_TXT = {2: "🟢 多頭排列（滿球做多）", 1: "🟡 中性震盪（精選波段）", 0: "🔴 空頭走勢（防守觀望）"}


def build_alerts(eng: Engine, params: Params, ctx: dict) -> list:
    names = ctx["names"]
    lab = lambda c: f"{names.get(c, '')}({c})" if names.get(c) else str(c)
    out = []
    date_s = eng.idx[-1].strftime("%Y-%m-%d")
    today_s = now_tw().strftime("%Y-%m-%d")
    lvl = int(eng.regime_lvl[-1])

    prev = alert_state_get("regime_lvl")
    if prev is not None and int(prev) != lvl:
        out.append(Alert(f"regime|{today_s}|{lvl}", "regime",
                         f"🧭 大盤環境狀態轉變：{LVL_TXT[int(prev)]} → {LVL_TXT[lvl]}（加權指數 {float(eng.bench_close.iloc[-1]):,.0f}）"))
    alert_state_set("regime_lvl", lvl)

    if lvl > 0:
        for i, c in enumerate(latest_candidates(eng, params, top=4, exclude=ctx["punish"], chip_fn=ctx["chip_fn"]), 1):
            size = size_position(ctx["capital"], ctx["risk_pct"], c["close"], c["stop"])
            tp_txt = "移動停利" if np.isinf(c["tp"]) else f"{c['tp']:.2f}"
            det = c["chip"]
            chip_txt = ""
            if "trust" in det:
                chip_txt += f"投信5日{det['trust']/1000:+,.0f}張 外資5日{det['foreign']/1000:+,.0f}張"
            out.append(Alert(f"cand|{date_s}|{c['code']}", "cand",
                             f"🔥 主力精選#{i} {lab(c['code'])}\n"
                             f"收 {c['close']:.2f}｜防守價 {c['stop']:.2f}｜目標 {tp_txt}｜風控 {c['risk_pct']:.1f}%\n"
                             f"建議規模 {size['lots']}張 ({size['shares']}股) ≈ {size['amount']:,.0f}元\n"
                             f"{chip_txt}\nhttps://tw.stock.yahoo.com/quote/{c['code']}"))

    for r in ctx["portfolio"]:
        code = str(r.get("code", "")).strip()
        d = ctx["ind_map"].get(code)
        if not code or d is None or len(d) < 60:
            continue
        ddate = d.index[-1].strftime("%Y-%m-%d")
        h = holding_health(d, params)
        close = h["close"]
        cost = float(r.get("cost") or 0)
        if cost > 0:
            st_c, tp_c, _ = plan_trade(cost, float(d["ATR"].iloc[-1]), float(d["Low5"].iloc[-1]),
                                       params.stop_atr, params.tp_r if params.tp_r > 0 else 2.5)
            pnl = (close / cost - 1) * 100
            if close <= st_c:
                out.append(Alert(f"hold_stop|{ddate}|{code}", "hold",
                                 f"🚨 持股 {lab(code)} 跌破持倉成本防守價 {st_c:.2f}（成本 {cost:.2f}，{pnl:+.1f}%）！"))
        if h["weak"] >= 2:
            out.append(Alert(f"hold_weak|{ddate}|{code}|{h['weak']}", "hold",
                             f"⚠ 持股 {lab(code)} 轉弱警訊：{'、'.join(h['flags'])}｜現價 {close:.2f}"))

    for code in ctx["watch"]:
        d = ctx["ind_map"].get(code)
        if d is None or len(d) < 60:
            continue
        ddate = d.index[-1].strftime("%Y-%m-%d")
        close, pct = float(d["Close"].iloc[-1]), float(d["pct"].iloc[-1])
        for k, txt in detect_events(d):
            out.append(Alert(f"watch|{ddate}|{code}|{k}", "watch", f"👀 自選股動態 {lab(code)} {txt}（收 {close:.2f}，{pct:+.2f}%）"))
    return out


def dispatch_alerts(alerts: list, cfg: dict, enabled=None):
    enabled = set(enabled or ALERT_CATS)
    sel = [a for a in alerts if a.cat in enabled]
    if not sel:
        return "本次無符合條件的推播訊號。", []
    if not ((cfg.get("tg_token") and cfg.get("tg_chat")) or cfg.get("line_token")):
        return "未設定 Telegram 或 LINE Token，跳過推播發送。", sel
    fresh_keys = set(alert_claim([a.key for a in sel]))
    fresh = [a for a in sel if a.key in fresh_keys]
    if not fresh:
        return "訊號皆已推播過，無重複推播。", []
    text = f"⚡ 台股量化決策發報 {now_tw():%m/%d %H:%M}\n\n" + "\n\n".join(a.text for a in fresh)
    res = notify_all(text, cfg)
    if not any(ok for ok, _ in res):
        alert_release(list(fresh_keys))
    return "；".join(m for _, m in res) or "推播完成", fresh


def daemon_main():
    cfg = notify_cfg()
    cap = float(os.environ.get("CAPITAL", "1000000"))
    rp = float(os.environ.get("RISK_PCT", "1.5"))
    n = int(os.environ.get("N_UNIVERSE", "80"))
    chip_w = float(os.environ.get("CHIP_WEIGHT", "1"))

    hist = lru_cache(maxsize=3)(lambda tk, day: download_prices(list(tk), "2y"))
    rec = lru_cache(maxsize=2)(lambda tk, bk: download_prices(list(tk), "5d", min_len=2))
    meta_fn = lru_cache(maxsize=2)(load_meta_core)
    print("🚀 台股量化主力 Daemon 已啟動；盤中每 20 分鐘掃描一次...", flush=True)

    while True:
        now = now_tw()
        if now.weekday() < 5 and dt.time(8, 55) <= now.time() <= dt.time(14, 0):
            bk = now.strftime("%Y-%m-%d-%H-") + str(now.minute // 20)
            try:
                gp = lambda tk, bk=bk: merge_recent(hist(tuple(tk), bk[:10]), rec(tuple(tk), bk))
                meta = meta_fn(bk.rsplit("-", 1)[0])
                names, market = build_name_market(meta)
                params = Params()
                eng, _ = build_engine_core(meta, n, ["金融保險業", "航運業"], 30.0, 1.0,
                                           0.6, 0.10, rp / 100.0, gp)
                ind_map = get_ind_map([r.get("code") for r in load_portfolio()] + load_watchlist(), market, gp)
                ctx = dict(names=names, capital=cap, risk_pct=rp, portfolio=load_portfolio(),
                           watch=load_watchlist(), ind_map=ind_map,
                           chip_fn=make_main_force_chip_fn(meta["chips"], meta["tdcc"], chip_w),
                           punish=meta["punish"])
                msg, fresh = dispatch_alerts(build_alerts(eng, params, ctx), cfg)
                print(f"[{now:%H:%M:%S}] 掃描完成：新訊號 {len(fresh)} 則 ｜ {msg}", flush=True)
            except Exception as e:
                print(f"[{now:%H:%M:%S}] 掃描失敗：{e}", flush=True)
        time.sleep(300)


if __name__ == "__main__" and "--daemon" in sys.argv:
    daemon_main()
    sys.exit(0)


# ============================================================================
# D. 前端頁面佈局
# ============================================================================
st.set_page_config(page_title="台股量化操盤決策系統", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .stApp {background:#080c14 !important; color:#fff !important;}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {background:#0b0f19 !important; border-right:1px solid rgba(79,172,254,.25) !important;}
p, span, label, h1, h2, h3, h4, h5, h6, li {color:#fff !important;}
a {color:#38bdf8 !important;}
div.stButton > button {background:#080c14 !important; color:#fff !important; border:2px solid #38bdf8 !important; border-radius:9999px !important;
  padding:.5rem 2rem !important; font-weight:700 !important; box-shadow:0 0 12px rgba(56,189,248,.35) !important;}
div[data-testid="stMetric"] {background:#0f172a !important; border:1px solid #1e293b !important; border-radius:12px !important; padding:12px 16px !important;}
.stock-card {background:#0b1120; border:1px solid #1e293b; border-radius:14px; padding:16px; margin-bottom:12px;}
.stock-card-top1 {background:#0f172a; border:2px solid #38bdf8; border-radius:18px; padding:20px; margin-bottom:16px; box-shadow:0 0 25px rgba(56,189,248,.25);}
.tag-badge {display:inline-block; background:#082f49; color:#38bdf8 !important; border:1px solid #0284c7; padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; margin:0 4px 4px 0;}
.rating-box {display:flex; justify-content:space-around; background:#060a12; border:1px solid #1e293b; border-radius:10px; padding:8px 4px; margin-top:10px; text-align:center;}
.rl {font-size:12px; color:#94a3b8 !important;} .rv {font-size:16px; font-weight:700;}
.bb-bg {width:100%; height:8px; background:#22c55e; border-radius:9999px; overflow:hidden; margin:8px 0;}
.bb-fill {height:100%; background:#ef4444;}
.chk-bull {background:#450a0a; border:1px solid #b91c1c; color:#fca5a5 !important; padding:2px 6px; border-radius:6px; font-size:12px; display:inline-block; margin:2px 4px 2px 0;}
.chk-bear {background:#052e16; border:1px solid #15803d; color:#86efac !important; padding:2px 6px; border-radius:6px; font-size:12px; display:inline-block; margin:2px 4px 2px 0;}
.lnk {font-size:12px; margin-right:10px;}
</style>
""", unsafe_allow_html=True)

# 側邊欄控制
sb = st.sidebar
sb.markdown("### 資金與風控設定")
capital = sb.number_input("操作資金規模 (TWD)", 100_000, 50_000_000, 1_000_000, 50_000)
risk_pct = sb.slider("單筆最大承受風險 (%)", 0.5, 3.0, 1.5, 0.1)

sb.markdown("### 股票池規模（零執行緒安全防禦）")
n_universe = sb.select_slider("分析股票池（當日成交值前 N 檔）", [50, 70, 90, 120], value=70)
excl = sb.multiselect("排除產業", ["金融保險業", "航運業", "水泥工業", "食品工業", "貿易百貨業"], default=["金融保險業", "航運業"])
min_price = sb.number_input("最低股價", 5.0, 300.0, 30.0, 5.0)
min_turn_yi = sb.number_input("5日均成交值下限（億）", 0.5, 10.0, 1.0, 0.1)

sb.markdown("### 交易成本與籌碼")
fee_disc = sb.slider("手續費折扣（0.6 = 6折）", 0.2, 1.0, 0.6, 0.05)
slip_pct = sb.slider("單邊預估滑價 (%)", 0.0, 0.5, 0.10, 0.05)
chip_weight = sb.slider("主力籌碼加減分權重 (投信+外資)", 0.0, 2.0, 1.0, 0.1)

if sb.button("🔄 強制刷新並重新分析"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()


def bucket_key() -> str:
    n = now_tw()
    return n.strftime("%Y-%m-%d-%H-") + str(n.minute // 20)


@st.cache_data(ttl=3600, show_spinner=False)
def load_meta(hour_key: str):
    return load_meta_core(hour_key)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def prices_hist(tickers: tuple, day_key: str):
    return download_prices(list(tickers), period="2y")


@st.cache_data(ttl=1200, show_spinner=False)
def prices_recent(tickers: tuple, bucket: str):
    return download_prices(list(tickers), period="5d", min_len=2)


def get_prices(tickers, bucket: str) -> dict:
    tk = tuple(tickers)
    return merge_recent(prices_hist(tk, bucket[:10]), prices_recent(tk, bucket))


@st.cache_resource(ttl=1200, show_spinner=False)
def build_engine(bucket, n, excl_t, min_price, min_turn_yi, fee_disc, slip_pct, risk_pct):
    meta_ = load_meta(bucket.rsplit("-", 1)[0])
    return build_engine_core(meta_, n, list(excl_t), min_price, min_turn_yi,
                             fee_disc, slip_pct, risk_pct / 100.0, lambda tk: get_prices(tk, bucket))


b_key = bucket_key()
try:
    with st.spinner("🚀 量化引擎計算中（純同步安全連線）..."):
        eng, bench_df = build_engine(b_key, n_universe, tuple(excl), min_price, min_turn_yi, fee_disc, slip_pct, risk_pct)
        meta = load_meta(b_key.rsplit("-", 1)[0])
except Exception as e:
    st.error(f"系統啟動中發生錯誤：{e}")
    st.info("💡 提示：若剛剛曾在 Streamlit Cloud 發生 thread 崩潰，請務必至右下角選單點擊『Reboot App』釋放舊殘留執行緒。")
    st.stop()

NAMES, ALL_MARKET = build_name_market(meta)
get_px = lambda tk: get_prices(tk, b_key)
data_date = eng.idx[-1].strftime("%Y-%m-%d")
regime_lvl = int(eng.regime_lvl[-1])
regime_ok = regime_lvl > 0
chip_fn = make_main_force_chip_fn(meta["chips"], meta["tdcc"], chip_weight)
params = Params()

portfolio_rows = st.session_state.setdefault("portfolio", load_portfolio())
watch_codes = st.session_state.setdefault("watchlist", load_watchlist())

ind_map_hold = get_ind_map([r.get("code") for r in portfolio_rows] + watch_codes, ALL_MARKET, get_px)
ctx = dict(names=NAMES, capital=capital, risk_pct=risk_pct, portfolio=portfolio_rows,
           watch=watch_codes, ind_map=ind_map_hold, chip_fn=chip_fn, punish=meta["punish"])
alerts = build_alerts(eng, params, ctx)


def label(code: str) -> str:
    n = NAMES.get(code)
    return f"{n} ({code})" if n else f"{code}"


def link_html(code: str) -> str:
    return "".join(f'<a class="lnk" href="{u}" target="_blank">{n}</a>'
                   for n, u in links(code, ALL_MARKET.get(code, "TW")).items())


def candle_fig(df: pd.DataFrame, n: int = 50, stop=None, tp=None, height=340, title=""):
    d = df.tail(n)
    cats = d.index.strftime("%m/%d").tolist()
    fig = go.Figure(go.Candlestick(x=cats, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                   increasing_line_color="#ef4444", decreasing_line_color="#22c55e", name="K"))
    fig.add_trace(go.Scatter(x=cats, y=d["MA20"], line=dict(color="#38bdf8", width=1.5), name="20MA"))
    fig.add_trace(go.Scatter(x=cats, y=d["MA60"], line=dict(color="#f59e0b", width=1.5), name="60MA"))
    if stop:
        fig.add_hline(y=stop, line_dash="dash", line_color="#22c55e", annotation_text=f"停損 {stop:.2f}")
    if tp and not np.isinf(tp):
        fig.add_hline(y=tp, line_dash="dash", line_color="#ef4444", annotation_text=f"目標 {tp:.2f}")
    fig.update_layout(height=height, title=title, xaxis=dict(type="category", rangeslider=dict(visible=False)),
                      margin=dict(l=10, r=10, t=35 if title else 10, b=10), paper_bgcolor="#080c14",
                      plot_bgcolor="#080c14", font=dict(color="#fff"), showlegend=False)
    return fig


# ============================================================================
# 完整 6 大頁籤
# ============================================================================
tab_daily, tab_port, tab_sec, tab_val, tab_scr, tab_alert = st.tabs([
    "🎯 每日主力決策推薦", "💼 持股健檢與換股", "🌐 族群多空儀表板",
    "🧪 Walk-Forward 樣本外驗證", "🛠️ 15 項全景篩選器", "🔔 推播通知與自選股"
])

# ----------------------------------------------------------------------------
# Tab 1：每日主力決策推薦
# ----------------------------------------------------------------------------
with tab_daily:
    st.markdown(f"### 盤勢格局與主力做多決策 ｜ 資料基準：`{data_date}`")
    breadth = float(eng.breadth.iloc[-1]) * 100
    (st.info if regime_ok else st.warning)(
        f"大盤指標狀態：{LVL_TXT[regime_lvl]} ｜ 加權指數：{float(eng.bench_close.iloc[-1]):,.0f} ｜ 股票池站上月線比例：{breadth:.0f}%"
    )

    cands = latest_candidates(eng, params, top=10, exclude=meta["punish"], chip_fn=chip_fn)
    if not cands:
        st.warning("目前市場暫無同時符合「多頭排列 + 縮量止跌回測 + 主力鎖碼」之標的，空手觀望亦為策略一環。")
    else:
        t1 = cands[0]
        code = t1["code"]
        tags = "".join(f'<span class="tag-badge">{html.escape(t)}</span>' for t in TAG_MAP.get(code, []))
        subs = t1["sub"]
        st.markdown("#### 👑 今日主力第一首選")
        st.markdown(f"""
        <div class="stock-card-top1">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <div>
              <span style="font-size:30px;font-weight:900;color:#f59e0b !important;">{html.escape(label(code))}</span>
              <div style="margin-top:6px;">{tags}</div>
              <div style="margin-top:6px;">{link_html(code)}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:34px;font-weight:900;">{t1['close']:.2f}</div>
              <div style="font-size:18px;font-weight:700;color:{'#ef4444' if t1['pct']>=0 else '#22c55e'} !important;">
                {'▲' if t1['pct']>=0 else '▼'} {t1['pct']:+.2f}%
              </div>
              <div style="font-size:14px;color:#38bdf8 !important;font-weight:700;">
                主力綜合分 {t1['final']:.1f}（技術基礎 {t1['score']:.1f} ＋ 主力鎖碼加分 {t1['bonus']:+.1f}）
              </div>
            </div>
          </div>
          <div class="rating-box">
            <div><div class="rl">趨勢結構</div><div class="rv">{subs['trend']:.0f}</div></div>
            <div><div class="rl">籌碼沉澱</div><div class="rv">{subs['compress']:.0f}</div></div>
            <div><div class="rl">動能強度</div><div class="rv">{subs['mom']:.0f}</div></div>
            <div><div class="rl">相對大盤 RS</div><div class="rv">{subs['rs']:.0f}</div></div>
            <div><div class="rl">主力資金流</div><div class="rv">{subs['flow']:.0f}</div></div>
            <div><div class="rl">回測型態分</div><div class="rv">{subs['setup']:.0f}</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        size = size_position(capital, risk_pct, t1["close"], t1["stop"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("參考進場點（次日開盤）", f"{t1['close']:.2f} 元", f"5日均額 {t1['turnover_yi']:.1f} 億")
        c2.metric("關鍵防守價（跌破停損）", f"{t1['stop']:.2f} 元", f"-{t1['risk_pct']:.2f}%", delta_color="inverse")
        c3.metric("目標獲利點 (2.5R)", f"{t1['tp']:.2f} 元", f"+{(t1['tp']/t1['close']-1)*100:.2f}%")
        c4.metric("部位規模配置", f"{size['lots']} 張 ({size['shares']} 股)", f"承擔風險 ≈ {size['risk_amt']:,.0f} 元")

        det = t1["chip"]
        chip_line = []
        if "trust" in det:
            chip_line.append(f"主力籌碼近5日：投信 {det['trust']/1000:+,.0f} 張、外資 {det['foreign']/1000:+,.0f} 張")
        if pd.notna(det.get("big400")):
            chip_line.append(f"大戶持股參考：{det['big400']:.1f}%")
        st.caption(" ｜ ".join(chip_line))

        ind_df = pd.DataFrame({f: eng.P[f][code] for f in ("Open", "High", "Low", "Close", "MA20", "MA60")}).dropna()
        st.plotly_chart(candle_fig(ind_df, 50, t1["stop"], t1["tp"], title=f"{label(code)} 日K線與防守目標位"), use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🎯 主力評分候選清單（第 2～10 名）")
        rows = []
        for i, c in enumerate(cands[1:], start=2):
            cdet = c["chip"]
            rows.append({
                "排名": f"#{i}", "標的": label(c["code"]), "主力總分": round(c["final"], 1), "技術分": round(c["score"], 1),
                "主力加分": round(c["bonus"], 1), "收盤": c["close"], "漲跌%": round(c["pct"], 2),
                "防守停損": c["stop"], "波段目標": c["tp"],
                "投信5日(張)": round(cdet.get("trust", 0) / 1000) if "trust" in cdet else "—",
                "外資5日(張)": round(cdet.get("foreign", 0) / 1000) if "foreign" in cdet else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Tab 2：持股健檢與換股
# ----------------------------------------------------------------------------
with tab_port:
    st.markdown("### 💼 持股健檢與換股建議（存於 `portfolio.json`）")
    base = pd.DataFrame(portfolio_rows)
    for col in ("code", "cost", "shares", "date"):
        if col not in base: base[col] = None
    base["code"] = base["code"].astype(str).str.strip()
    base.insert(1, "name", base["code"].map(lambda c: NAMES.get(c, "—")))

    edited = st.data_editor(base[["code", "name", "cost", "shares", "date"]], num_rows="dynamic", use_container_width=True,
                            column_config={"code": "代碼", "name": st.column_config.TextColumn("名稱", disabled=True),
                                           "cost": st.column_config.NumberColumn("買進成本", format="%.2f"),
                                           "shares": st.column_config.NumberColumn("持股股數", step=1000),
                                           "date": "買進日期 (YYYY-MM-DD)"})
    if st.button("💾 儲存最新持股"):
        rows_new = edited[["code", "cost", "shares", "date"]].dropna(subset=["code"]).replace({np.nan: None}).to_dict("records")
        st.session_state["portfolio"] = rows_new
        save_portfolio(rows_new)
        st.success("持股資料已成功寫入 portfolio.json！")
        st.rerun()

    hold_health_list = []
    for r in portfolio_rows:
        c = str(r.get("code") or "").strip()
        if not c or c not in ind_map_hold: continue
        d = ind_map_hold[c]
        h = holding_health(d, params)
        cost = float(r.get("cost") or 0)
        pnl = (h["close"] / cost - 1) * 100 if cost else 0
        hold_health_list.append({
            "標的": label(c), "現價": round(h["close"], 2), "成本": cost, "未實現%": round(pnl, 2),
            "弱勢評分": h["weak"], "警訊描述": "、".join(h["flags"]) or "格局健康", "量化防守價": h["stop"]
        })
    if hold_health_list:
        st.dataframe(pd.DataFrame(hold_health_list), use_container_width=True, hide_index=True)

    if hold_health_list and cands:
        weakest = max(hold_health_list, key=lambda x: x["弱勢評分"])
        if weakest["弱勢評分"] >= 2 and regime_ok:
            st.error(f"🚨 換股警報：持股 【{weakest['標的']}】 弱勢評分達 {weakest['弱勢評分']}（{weakest['警訊描述']}），"
                     f"建議換入今日主力首選 【{label(cands[0]['code'])}】！")

# ----------------------------------------------------------------------------
# Tab 3：族群多空儀表板
# ----------------------------------------------------------------------------
with tab_sec:
    st.markdown("### 🌐 核心概念族群動能儀表板")
    sec_pick = st.selectbox("選擇產業族群", list(SECTORS))
    items = SECTORS[sec_pick]
    sec_inds = get_ind_map([c for c, _, _ in items], ALL_MARKET, get_px)

    cols = st.columns(2)
    for idx, (c, n0, tg) in enumerate(items):
        with cols[idx % 2]:
            d = sec_inds.get(c)
            if d is None or len(d) < 30: continue
            last, prev = float(d["Close"].iloc[-1]), float(d["Close"].iloc[-2])
            diff = last - prev
            checks = bull_bear_checks(d, chip_fn(c, last, float(d['Turnover_MA5'].iloc[-1]))[1] if chip_fn else None)
            pct_bull = int(len(checks["bull"]) / max(1, len(checks["bull"]) + len(checks["bear"])) * 100)

            st.markdown(f"""
            <div class="stock-card">
              <div style="display:flex;justify-content:space-between;">
                <div><b>{c} {NAMES.get(c, n0)}</b></div>
                <div style="color:{'#ef4444' if diff>=0 else '#22c55e'}; font-weight:700;">
                  {last:.2f} ({diff/prev*100:+.2f}%)
                </div>
              </div>
              <div class="bb-bg"><div class="bb-fill" style="width:{pct_bull}%;"></div></div>
              <div style="font-size:12px;">多方：{''.join(f'<span class="chk-bull">{x}</span>' for x in checks['bull'][:4])}</div>
            </div>
            """, unsafe_allow_html=True)
            st.plotly_chart(candle_fig(d, 30, height=200), use_container_width=True)

# ----------------------------------------------------------------------------
# Tab 4：Walk-Forward 驗證與蒙地卡羅回測
# ----------------------------------------------------------------------------
with tab_val:
    st.markdown("### 🧪 Walk-Forward 樣本外滾動驗證與蒙地卡羅風控")
    st.caption("模擬滾動視窗：以過去交易日挑選最佳主力參數，在隨後完全未見過的測試視窗實測；所有數值扣除交易滑價與手續費。")

    if st.button("▶ 啟動 Walk-Forward 樣本外回測驗證"):
        bar = st.progress(0.0, text="滾動驗證計算中...")
        res = walk_forward(eng, progress=lambda x: bar.progress(x))
        bar.empty()
        if res:
            st.session_state["wf_res"] = res
            st.success("驗證完成！")

    wf = st.session_state.get("wf_res")
    if wf:
        o = wf["oos_stats"]
        bench_curve, bench_ret = bench_return(eng.bench_close, wf["oos_equity"].index)
        m = st.columns(4)
        m[0].metric("樣本外勝率", f"{o['win_rate']:.1f}%", f"總交易 {o['n']} 筆")
        m[1].metric("賺賠比 (Payoff)", f"{o['payoff']:.2f}")
        m[2].metric("策略累計總報酬", f"{o['total_ret']:+.1f}%")
        m[3].metric("同期加權指數報酬", f"{bench_ret:+.1f}%", f"Alpha: {o['total_ret'] - bench_ret:+.1f}%")

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=wf["oos_equity"].index, y=wf["oos_equity"].values, name="主力策略樣本外淨值", line=dict(color="#f59e0b", width=2)))
        fig_eq.add_trace(go.Scatter(x=bench_curve.index, y=bench_curve.values, name="大盤買進持有基準", line=dict(color="#38bdf8", width=1.5, dash="dot")))
        fig_eq.update_layout(height=340, title="策略累積淨值 vs 大盤基準 (起點 = 1.0)", paper_bgcolor="#080c14", plot_bgcolor="#080c14", font=dict(color="#fff"))
        st.plotly_chart(fig_eq, use_container_width=True)

        st.markdown("##### 🎲 蒙地卡羅模擬（區塊自助抽樣 1500 次）")
        mc = mc_ruin(wf["oos_trades"]["net_pct"].tolist() if len(wf["oos_trades"]) else [])
        if mc:
            c1, c2, c3 = st.columns(3)
            c1.metric("50筆交易後平均淨值", f"{mc['end_mean']:.2f}")
            c2.metric("95% 信賴最大回撤", f"-{mc['mdd95']:.1f}%")
            c3.metric("本金腰斬風險機率", f"{mc['p_ruin']:.2f}%")

# ----------------------------------------------------------------------------
# Tab 5：15 項全景篩選器
# ----------------------------------------------------------------------------
with tab_scr:
    st.markdown("### 🛠️ 15 項全景條件式雷達篩選")
    snap = snapshot(eng, params.preset)
    snap = snap[snap["liquid"]]
    chosen = []

    with st.expander("條件過濾清單（交集篩選）", expanded=True):
        cols = st.columns(3)
        for i, name in enumerate(SCREEN_FLAGS):
            if cols[i % 3].checkbox(name, key=f"scr_{i}"):
                chosen.append(name)
        s1, s2 = st.columns(2)
        mb5 = s1.slider("5MA 乖離上限 (%)", 1.0, 10.0, 4.0, 0.5)
        mb20 = s2.slider("20MA 乖離上限 (%)", 3.0, 25.0, 12.0, 1.0)

    res = snap.copy()
    for name in chosen:
        res = res[res[name]]
    res = res[(res["bias5"] <= mb5) & (res["bias20"] <= mb20)].sort_values("score", ascending=False)

    if not res.empty:
        st.dataframe(pd.DataFrame({
            "標的": [label(c) for c in res.index], "收盤": res["close"].round(2),
            "漲跌%": res["pct"].round(2), "主力評分": res["score"].round(1),
            "5日均額(億)": res["turnover_yi"].round(2), "5MA乖離%": res["bias5"].round(2)
        }), use_container_width=True, hide_index=True)
    else:
        st.warning("查無符合全部交集條件之標的，請適度放寬勾選限制。")

# ----------------------------------------------------------------------------
# Tab 6：推播通知與自選股監控
# ----------------------------------------------------------------------------
with tab_alert:
    st.markdown("### 🔔 Telegram / LINE 推播發報與自選股監控")
    cfg_curr = notify_cfg()
    configured = bool((cfg_curr["tg_token"] and cfg_curr["tg_chat"]) or cfg_curr["line_token"])

    with st.expander("通訊推播金鑰設定", expanded=not configured):
        st.info("支援 Telegram Bot 與 LINE Official Messaging API。建議存於環境變數或 Streamlit Secrets。")
        tg_tok = st.text_input("Telegram Token", value=cfg_curr["tg_token"], type="password")
        tg_cht = st.text_input("Telegram Chat ID", value=cfg_curr["tg_chat"])

    if st.button("📨 發送連線測試推播"):
        res = notify_all("✅ 台股量化決策系統推播連線成功！", cfg_curr)
        for ok, msg in res:
            (st.success if ok else st.error)(msg)

    st.markdown("#### 自選股監控清單")
    wl_input = st.text_area("自選股代碼（逗號或空格分隔）", value=", ".join(watch_codes))
    if st.button("💾 儲存自選股"):
        parsed = [c for c in re.split(r"[\s,，]+", wl_input) if re.fullmatch(r"\d{4}", c)]
        st.session_state["watchlist"] = parsed
        save_watchlist(parsed)
        st.success("自選股清單已更新！")
        st.rerun()

    st.markdown("#### 📡 目前偵測即時訊號總覽")
    if alerts:
        st.dataframe(pd.DataFrame([{"類型": ALERT_CATS[a.cat], "訊號內容": a.text.replace("\n", " ｜ ")} for a in alerts]),
                     use_container_width=True, hide_index=True)
    else:
        st.info("目前無新觸發事件訊號。")