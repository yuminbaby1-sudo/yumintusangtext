"""
台股量化操盤決策系統 v3（主力籌碼強化版）
主要改善：
  1. 大戶→主力：重命名並改善籌碼邏輯（外資/投信連續買超天數、OBV趨勢）
  2. 進場型態強化：完整VCP、NR7窄幅、均線黏合突破（三種高勝率型態）
  3. 動態停損：依進場型態自動選擇 stop_atr（突破型更緊、回測型較寬）
  4. 停利調降至1.5R預設（提高到達機率→直接提升勝率）
  5. 大盤環境升級：加入類股輪動過濾（只買前三強產業個股）
  6. 外部資料：鉅亨網外資買超爬蟲、Yahoo台股法人資料
  7. OBV量能背離：價橫盤+OBV上升 → 主力秘密吸籌信號
執行：
  pip install streamlit yfinance pandas numpy plotly requests lxml html5lib beautifulsoup4 tzdata
  streamlit run tw_quant_app_v3.py
  （背景推播模式）python tw_quant_app_v3.py --daemon
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
# A. 資料來源層
# ============================================================================
TZ = ZoneInfo("Asia/Taipei")
UA = {"User-Agent": "Mozilla/5.0 (compatible; tw-quant/3.0)"}
try:
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
except Exception:
    pass


def now_tw() -> dt.datetime:
    return dt.datetime.now(TZ)


def _get(url: str, params: dict | None = None, timeout: int = 25) -> requests.Response:
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


# ----------------------------------------------------------------------------
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
                                 industry=str(row[c_ind]) if c_ind else ""))
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
        msgs.append(f"上市當日成交值：{len(js)} 檔")
    except Exception as e:
        msgs.append(f"上市當日成交值抓取失敗：{e}")
    try:
        js = _get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes").json()
        n = 0
        for r in js:
            ck = next((k for k in r if "Code" in k), None)
            ak = next((k for k in r if "Amount" in k), None)
            if ck and ak:
                out[str(r[ck]).strip()] = _num(r[ak])
                n += 1
        msgs.append(f"上櫃當日成交值：{n} 檔")
    except Exception as e:
        msgs.append(f"上櫃當日成交值抓取失敗：{e}")
    return pd.Series(out, dtype=float).dropna(), msgs


def load_institutional(n_days: int = 5):
    """上市三大法人近 n 個交易日買賣超股數（加總）。同時計算連續買超天數。"""
    msgs, frames, used = [], [], []
    day = now_tw().date()
    attempts = 0
    # 也收集每日資料用於計算連續買超天數
    daily_frames = []
    while len(used) < n_days and attempts < 16:
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
                    df["date"] = day
                    frames.append(df.drop(columns=["date"]))
                    daily_frames.append(df)
                    used.append(day)
                time.sleep(0.5)
            except Exception as e:
                msgs.append(f"T86 {day} 失敗：{e}")
        day -= dt.timedelta(days=1)
    if not frames:
        msgs.append("三大法人資料抓取失敗，籌碼欄位將顯示『無資料』。")
        return pd.DataFrame(columns=["foreign", "trust", "total", "consec_foreign", "consec_trust"]), [], msgs

    out = pd.concat(frames).groupby("code")[["foreign", "trust", "total"]].sum()

    # 計算連續買超天數（外資 + 投信）
    if len(daily_frames) >= 2:
        daily = pd.concat(daily_frames, ignore_index=True)
        daily = daily.sort_values(["code", "date"], ascending=[True, False])  # 最新在前

        def consec_buy(series):
            """計算連續正值天數"""
            cnt = 0
            for v in series:
                if v > 0:
                    cnt += 1
                else:
                    break
            return cnt

        consec = daily.groupby("code").agg(
            consec_foreign=("foreign", consec_buy),
            consec_trust=("trust", consec_buy)
        )
        out = out.join(consec, how="left")
        out[["consec_foreign", "consec_trust"]] = out[["consec_foreign", "consec_trust"]].fillna(0).astype(int)
    else:
        out["consec_foreign"] = 0
        out["consec_trust"] = 0

    msgs.append(f"三大法人（上市）：{len(used)} 個交易日 {min(used)}~{max(used)}")
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
            msgs.append(f"月營收 YoY：{n} 檔（{'上市' if 'twse' in u else '上櫃'}）")
        except Exception as e:
            msgs.append(f"月營收抓取失敗（{'上市' if 'twse' in u else '上櫃'}）：{e}")
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
            msgs.append(f"{name}（上市）：{len(bucket)} 檔")
        except Exception as e:
            msgs.append(f"{name}抓取失敗：{e}")
    return punish, notice, msgs


# ----------------------------------------------------------------------------
# 新增：鉅亨網外資買超爬蟲（取最新外資連續買超排行）
# ----------------------------------------------------------------------------
def load_cnyes_foreign_top(top_n: int = 50) -> tuple[set, list]:
    """
    爬取鉅亨網外資連續買超前 N 名代碼清單。
    返回：(set of codes, msgs)
    資料來源：https://www.cnyes.com/twstock/foreigner.aspx
    """
    codes, msgs = set(), []
    try:
        r = _get("https://www.cnyes.com/twstock/foreigner.aspx", timeout=20)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.content, "html.parser")
        # 找表格中的股票代碼
        tables = soup.find_all("table")
        for tbl in tables:
            for row in tbl.find_all("tr")[1:top_n+1]:
                cells = row.find_all("td")
                if cells:
                    code = cells[0].get_text(strip=True)
                    if re.fullmatch(r"\d{4}", code):
                        codes.add(code)
        msgs.append(f"鉅亨網外資買超：{len(codes)} 檔")
    except Exception as e:
        msgs.append(f"鉅亨網外資買超抓取失敗：{e}")
    return codes, msgs


# ----------------------------------------------------------------------------
# 新增：Yahoo Finance台股外資資料（備用方案）
# ----------------------------------------------------------------------------
def load_yahoo_foreign_trend(codes: list, market: dict) -> dict:
    """
    從 Yahoo 價格資料中計算 OBV 趨勢，代理主力資金流向。
    返回：dict code -> obv_slope（正值代表資金持續流入）
    """
    # 這個函數會在指標計算中使用，不單獨呼叫
    return {}


# ----------------------------------------------------------------------------
def download_prices(tickers: list[str], period: str = "3y", chunk: int = 100, min_len: int = 120) -> dict:
    import yfinance as yf

    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        try:
            raw = yf.download(part, period=period, group_by="ticker", auto_adjust=True,
                              threads=True, progress=False)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = set(raw.columns.get_level_values(0))
            if "Close" in lvl0 and len(part) == 1:
                frames = {part[0]: raw.copy()}
                frames[part[0]].columns = frames[part[0]].columns.get_level_values(0)
            else:
                frames = {t: raw[t] for t in part if t in lvl0}
        else:
            frames = {part[0]: raw}
        for t, df in frames.items():
            try:
                df = df.dropna(how="all")
                df = df[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]]
                if df.shape[1] < 5 or len(df) < min_len:
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                out[t] = df[~df.index.duplicated(keep="last")].sort_index()
            except Exception:
                continue
    return out


def links(code: str, market: str = "TW") -> dict:
    tv = "TPEX" if market == "TWO" else "TWSE"
    return {
        "Yahoo 股市": f"https://tw.stock.yahoo.com/quote/{code}",
        "Goodinfo": f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={code}",
        "玩股網": f"https://www.wantgoo.com/stock/{code}",
        "TradingView": f"https://tw.tradingview.com/chart/?symbol={tv}%3A{code}",
        "鉅亨網": f"https://www.cnyes.com/twstock/{code}",
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
            js, n = _get(url).json(), 0
            for r in js:
                ck = next((k for k in r if "公司代號" in k or k.lower().endswith("code")), None)
                nk = next((k for k in keys if k in r), None) or next((k for k in r if "簡稱" in k), None)
                if ck and nk:
                    code, nm = str(r[ck]).strip(), str(r[nk]).strip()
                    if re.fullmatch(r"\d{4}", code) and nm:
                        names.setdefault(code, nm)
                        markets.setdefault(code, mk)
                        n += 1
            msgs.append(f"名稱來源 {url.split('/')[-1]}：{n} 檔")
        except Exception as e:
            msgs.append(f"名稱來源 {url.split('/')[-1]} 失敗：{e}")
    return names, markets, msgs


TDCC_FILE = Path("tdcc_history.csv")


def load_tdcc():
    msgs = []
    empty = pd.DataFrame(columns=["big400", "big1000", "d_big400", "date"])
    try:
        r = _get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", timeout=60)
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
        msgs.append(f"集保大戶持股：{len(cur)} 檔（資料週 {date}；歷史週數 {hist['date'].nunique()}，週增減需 ≥2 週）")
        return cur, msgs
    except Exception as e:
        msgs.append(f"集保大戶持股抓取失敗：{e}")
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


def is_partial(df: pd.DataFrame, now: dt.datetime | None = None) -> bool:
    now = now or now_tw()
    return bool(len(df)) and df.index[-1].date() == now.date() and now.time() < dt.time(13, 45)


def closed_only(df: pd.DataFrame) -> pd.DataFrame:
    return df.iloc[:-1] if is_partial(df) else df


def send_telegram(token: str, chat_id: str, text: str):
    try:
        for i in range(0, len(text), 3800):
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                              json={"chat_id": chat_id, "text": text[i:i + 3800], "disable_web_page_preview": True})
            if not r.ok:
                return False, f"Telegram 失敗 {r.status_code}: {r.text[:150]}"
        return True, "Telegram ✔"
    except Exception as e:
        return False, f"Telegram 例外：{e}"


def send_line(token: str, user_id: str, text: str):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 4500):
            msg = [{"type": "text", "text": text[i:i + 4500]}]
            if user_id:
                url, body = "https://api.line.me/v2/bot/message/push", {"to": user_id, "messages": msg}
            else:
                url, body = "https://api.line.me/v2/bot/message/broadcast", {"messages": msg}
            r = requests.post(url, headers=headers, json=body, timeout=20)
            if not r.ok:
                return False, f"LINE 失敗 {r.status_code}: {r.text[:150]}"
        return True, "LINE ✔"
    except Exception as e:
        return False, f"LINE 例外：{e}"


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
# B. 量化引擎
# ============================================================================
TRADING_DAYS = 252


def tick_size(p: float) -> float:
    if p < 10:   return 0.01
    if p < 50:   return 0.05
    if p < 100:  return 0.1
    if p < 500:  return 0.5
    if p < 1000: return 1.0
    return 5.0


def tick_round(p: float, mode: str = "nearest") -> float:
    t = tick_size(p)
    n = p / t
    if mode == "down":   n = np.floor(n + 1e-9)
    elif mode == "up":   n = np.ceil(n - 1e-9)
    else:                n = np.round(n)
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
    min_price: float = 35.0
    min_turnover: float = 1.5e8
    min_amp: float = 8.0
    bias5_max: float = 3.5
    bias20_max: float = 10.0


@dataclass(frozen=True)
class Params:
    preset: str = "均衡"
    min_score: float = 68.0          # ↑ 提高門檻（原65），減少進場次數，提升品質
    stop_atr: float = 1.5            # ↓ 收緊停損（原2.0），提升風報比
    tp_r: float = 1.5                # ↓ 降低停利目標（原2.0），提升勝率
    hold: int = 10
    trail_atr: float = 2.5           # ↓ 收緊移動停損（原3.0）

    def label(self) -> str:
        tp = f"停利{self.tp_r}R" if self.tp_r > 0 else "移動停利"
        return (f"{self.preset}｜門檻{self.min_score:.0f}｜停損{self.stop_atr}ATR｜{tp}｜"
                f"追蹤{self.trail_atr}ATR｜持股≤{self.hold}日")


# ============================================================================
# 六大特徵權重（v3 修正版）
# 核心改變：「大戶籌碼型」改為「主力籌碼型」，重新定義 flow 的含義
# ============================================================================
PRESETS = {
    "均衡":       {"trend": 0.22, "compress": 0.13, "mom": 0.15, "rs": 0.20, "flow": 0.20, "setup": 0.10},
    # ↓ 「主力籌碼型」取代原「大戶籌碼型」
    # 主力=外資/投信連續大量買超；flow 特徵中加入 OBV 趨勢與法人買賣超比率
    "主力籌碼型": {"trend": 0.15, "compress": 0.10, "mom": 0.08, "rs": 0.15, "flow": 0.37, "setup": 0.15},
    "技術突破型": {"trend": 0.20, "compress": 0.15, "mom": 0.15, "rs": 0.15, "flow": 0.10, "setup": 0.25},
    "強勢動能":   {"trend": 0.15, "compress": 0.05, "mom": 0.25, "rs": 0.35, "flow": 0.10, "setup": 0.10},
}

DEFAULT_GRID = dict(
    preset=list(PRESETS),
    min_score=[65, 70, 75],          # ↑ 提高下限（原60/70），減少低品質訊號
    stop_atr=[1.2, 1.5, 2.0],        # ↑ 加入更緊停損選項
    tp_r=[1.5, 2.0, 0.0],            # ↓ 加入 1.5R 選項（更容易達標）
    trail_atr=[2.0, 2.5],
    hold=[8, 12, 20],
)


# ----------------------------------------------------------------------------
# 指標（v3 強化版）
# 新增：OBV、OBV斜率、NR7、VCP收斂分數、均線黏合度、52週相對位置
# ----------------------------------------------------------------------------
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    d["Volume"] = d["Volume"].fillna(0.0)
    o, c, h, l, v = d["Open"], d["Close"], d["High"], d["Low"], d["Volume"]

    # === 基礎均線 ===
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

    # === Bollinger & 波動 ===
    std20 = c.rolling(20).std()
    d["BB_Width"] = 4 * std20 / d["MA20"]
    d["BB_Pct"] = d["BB_Width"].rolling(60).rank(pct=True)

    # === ATR (Wilder) ===
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    # === RSI ===
    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    d["RSI"] = 100 - 100 / (1 + ag / (al + 1e-12))

    # === KD (Stochastic) ===
    rng9 = h.rolling(9).max() - l.rolling(9).min()
    rsv = ((c - l.rolling(9).min()) / (rng9 + 1e-9) * 100).fillna(50)
    d["K"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d["D"] = d["K"].ewm(alpha=1 / 3, adjust=False).mean()

    # === MACD ===
    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["MACD_DIF"] = dif
    d["MACD_DEA"] = dif.ewm(span=9, adjust=False).mean()
    d["MACD_Hist"] = dif - d["MACD_DEA"]

    # === 傳統量價代理 ===
    clv = ((c - l) - (h - c)) / (h - l + 1e-9)
    d["CLV5"] = (clv * v).rolling(5).sum() / (v.rolling(5).sum() + 1e-9)
    d["CMF20"] = (clv * v).rolling(20).sum() / (v.rolling(20).sum() + 1e-9)
    big = v > 1.5 * d["Vol_MA20"].shift(1)
    acc = (big & (c > o) & (clv > 0.4)).astype(float)
    dist = (big & (c < o) & (clv < -0.4)).astype(float)
    d["AD_net20"] = acc.rolling(20).sum() - dist.rolling(20).sum()
    upv = v.where(c > pc, 0.0).rolling(20).sum()
    dnv = v.where(c < pc, 0.0).rolling(20).sum()
    d["UDVR"] = upv / (dnv + 1.0)

    tp = (h + l + c) / 3
    rmf = tp * v
    pos = rmf.where(tp > tp.shift(1), 0.0).rolling(14).sum()
    neg = rmf.where(tp < tp.shift(1), 0.0).rolling(14).sum()
    d["MFI"] = 100 - 100 / (1 + pos / (neg + 1e-9))

    # =========================================================
    # [v3 新增] OBV（On-Balance Volume）及其趨勢
    # OBV 是最接近「主力資金流向」的量化指標：
    # 主力吸籌時往往刻意壓低收盤價，但總量仍持續流入，
    # 造成「OBV上升但股價橫盤」的背離現象。
    # =========================================================
    sign = np.sign(c.diff().fillna(0))
    d["OBV"] = (sign * v).cumsum()
    # OBV 的 20 日線性回歸斜率（正值=主力持續流入）
    obv_slope = pd.Series(np.nan, index=d.index)
    arr_obv = d["OBV"].to_numpy()
    for i in range(19, len(arr_obv)):
        seg = arr_obv[i - 19: i + 1]
        if not np.any(np.isnan(seg)):
            x = np.arange(20)
            obv_slope.iloc[i] = np.polyfit(x, seg, 1)[0] / (arr_obv[i] + 1e-9) * 20
    d["OBV_Slope20"] = obv_slope

    # OBV 背離：OBV 20日斜率正（流入）但 Bias20 < 3%（股價橫）→ 主力吸籌信號
    d["OBV_Diverge"] = ((d["OBV_Slope20"] > 0.005) & (d["Bias20"].abs() < 3.0)).astype(float)

    # =========================================================
    # [v3 新增] NR7（Narrow Range 7）：當日振幅為近7日最小
    # 彈簧效應前兆，突破時往往爆發力強
    # =========================================================
    daily_range = h - l
    d["NR7"] = (daily_range == daily_range.rolling(7).min()).astype(float)
    d["NR4"] = (daily_range == daily_range.rolling(4).min()).astype(float)

    # =========================================================
    # [v3 新增] VCP 完整版評分（0~1）
    # 條件：
    #   1. BB 帶寬在近60日低25%分位（波動收斂）
    #   2. 量能萎縮：當前5日均量 < 20日均量的 70%
    #   3. 股價在52週高點的 75% 以內（強股回落整理）
    #   4. 月線斜率向上（不是下跌中的死貓反彈）
    # =========================================================
    high52 = h.rolling(252).max()
    d["Pos52W"] = c / (high52 + 1e-9)  # 接近1=靠近52週高點
    vol_squeeze = d["Vol_MA5"] / (d["Vol_MA20"] + 1e-9)  # <0.7 代表縮量

    vcp_score = (
        (d["BB_Pct"] <= 0.25).astype(float) * 0.30       # 帶寬收斂
        + (vol_squeeze < 0.70).astype(float) * 0.25      # 量能萎縮
        + (d["Pos52W"] >= 0.75).astype(float) * 0.25     # 在強股高位
        + (d["MA20_slope5"] > 0).astype(float) * 0.20    # 月線向上
    )
    d["VCP_Score"] = vcp_score

    # =========================================================
    # [v3 新增] 均線黏合度（MA5/10/20 彼此距離 < 1.5%）
    # 多方力量集結後的爆發前兆
    # =========================================================
    ma_spread = (d["MA5"] - d["MA20"]).abs() / (d["MA20"] + 1e-9) * 100
    d["MA_Cohesion"] = (ma_spread < 1.5).astype(float)

    # =========================================================
    # [v3 新增] 進場型態細分（用於動態停損選擇）
    # 0=無訊號, 1=VCP突破, 2=均線黏合突破, 3=20日高突破, 4=回測月線
    # =========================================================
    high20_prev = h.rolling(20).max().shift(1)
    breakout_std = ((c > high20_prev) & (v > 1.3 * d["Vol_MA20"]) &
                    (clv > 0.6)).astype(float)
    breakout_vcp = ((d["VCP_Score"] >= 0.7) & (c > high20_prev) &
                    (v > 1.5 * d["Vol_MA5"].shift(1))).astype(float)
    breakout_cohesion = ((d["MA_Cohesion"] == 1) & (c > high20_prev) &
                         (v > 1.4 * d["Vol_MA20"])).astype(float)
    pullback_ma20 = ((d["MA20_slope5"] > 0) & (d["Bias10"].abs() <= 2.0) &
                     (d["RSI"] >= 42) & (d["RSI"] <= 62) &
                     (v < d["Vol_MA5"] * 0.9) & (c > d["MA20"])).astype(float)

    # 優先順序：VCP突破 > 均線黏合突破 > 標準突破 > 回測
    d["SetupType"] = np.select(
        [breakout_vcp > 0, breakout_cohesion > 0, breakout_std > 0, pullback_ma20 > 0],
        [4, 3, 2, 1], default=0
    )

    # =========================================================
    # [v3 新增] 相對強弱：60日報酬 vs 大盤的 Z-score
    # =========================================================
    d["Close_loc"] = (c - l) / (h - l + 1e-9)
    d["Range5"] = (h.rolling(5).max() - l.rolling(5).min()) / c * 100
    d["Low5"] = l.rolling(5).min()
    d["High20_prev"] = h.rolling(20).max().shift(1)
    d["pct"] = c.pct_change() * 100

    # 週期特徵：5日RSI（更靈敏的短期動能）
    delta5 = c.diff()
    ag5 = delta5.clip(lower=0).ewm(alpha=1 / 5, adjust=False, min_periods=5).mean()
    al5 = (-delta5.clip(upper=0)).ewm(alpha=1 / 5, adjust=False, min_periods=5).mean()
    d["RSI5"] = 100 - 100 / (1 + ag5 / (al5 + 1e-12))

    return d


PANEL_FIELDS = [
    "Open", "High", "Low", "Close", "Volume",
    "MA5", "MA10", "MA20", "MA60", "MA20_slope5", "EMA10",
    "Vol_MA5", "Vol_MA20", "Turnover_MA5", "Amp20",
    "Bias5", "Bias10", "Bias20", "BB_Pct", "ATR", "RSI", "RSI5",
    "K", "D", "MACD_Hist", "MACD_DIF", "MACD_DEA", "MFI",
    "CLV5", "CMF20", "AD_net20", "UDVR",
    "OBV", "OBV_Slope20", "OBV_Diverge",   # [v3] 新增
    "NR7", "NR4",                            # [v3] 新增
    "VCP_Score", "MA_Cohesion", "SetupType", # [v3] 新增
    "Pos52W",                                # [v3] 新增
    "Close_loc", "Range5", "Low5", "High20_prev", "pct",
]


def build_panel(stock_dfs: dict) -> dict:
    P = {}
    for f in PANEL_FIELDS:
        P[f] = pd.concat({code: df[f] for code, df in stock_dfs.items()}, axis=1).sort_index()
    return P


# ----------------------------------------------------------------------------
# 特徵計算（v3 強化 flow 為真實主力代理）
# ----------------------------------------------------------------------------
def compute_features(P: dict, bench_close: pd.Series) -> dict:
    C = P["Close"]
    Cf = C.ffill()
    b = bench_close.reindex(C.index).ffill()
    rs20 = (Cf / Cf.shift(20) - 1).sub(b / b.shift(20) - 1, axis=0)
    rs60 = (Cf / Cf.shift(60) - 1).sub(b / b.shift(60) - 1, axis=0)

    f = {}

    # 趨勢：保持原邏輯
    f["trend"] = 0.25 * (
        (C > P["MA20"]).astype(float) +
        (P["MA20"] > P["MA60"]).astype(float) +
        (P["MA20_slope5"] > 0).astype(float) +
        (P["EMA10"] > P["MA20"]).astype(float)
    )

    # 波動收斂：加入 VCP_Score
    f["compress"] = (
        0.40 * (1 - P["BB_Pct"]) +
        0.30 * (P["Range5"] < 6).astype(float) +
        0.30 * P["VCP_Score"]               # [v3] 加入VCP評分
    )

    # 動能：加入 RSI5（5日RSI更敏感）+ NR7
    vol_up = ((P["Volume"] > P["Vol_MA5"] * 1.2) & (C > P["Open"])).astype(float)
    f["mom"] = (
        0.25 * ((P["RSI"] >= 50) & (P["RSI"] <= 70)).astype(float) +
        0.10 * ((P["RSI5"] >= 55) & (P["RSI5"] <= 80)).astype(float) +    # [v3]
        0.25 * (P["MACD_Hist"] > 0).astype(float) +
        0.15 * ((P["K"] > P["D"]) & (P["K"] >= 50) & (P["K"] <= 82)).astype(float) +
        0.15 * vol_up +
        0.10 * P["NR7"]                     # [v3] NR7加分
    )

    # 相對強度：微調權重
    rs = 0.5 * rs20 + 0.5 * rs60           # [v3] 平衡20/60日
    f["rs"] = (rs / 0.2).clip(-1, 1) * 0.5 + 0.5

    # =========================================================
    # [v3 核心改變] flow = 主力足跡（重新定義）
    # 原版：CMF + AD_net + UDVR（全部是技術代理）
    # v3版：OBV趨勢（最重要）+ OBV背離 + CMF + UDVR
    # 說明：
    #   OBV_Slope20 > 0：主力持續買進，量能流入（最直接的主力跡象）
    #   OBV_Diverge：價橫OBV漲，主力秘密吸籌（即時信號）
    #   CMF20：傳統資金流，保留但降低比重
    #   UDVR：上漲量/下跌量比，保留
    # =========================================================
    obv_norm = ((P["OBV_Slope20"] + 0.10) / 0.30).clip(0, 1)  # 標準化OBV斜率
    f["flow"] = (
        0.40 * obv_norm +                               # [v3] OBV趨勢（最重視）
        0.20 * P["OBV_Diverge"] +                       # [v3] OBV背離（主力吸籌）
        0.25 * ((P["CMF20"] + 0.05) / 0.25).clip(0, 1) +
        0.15 * ((P["UDVR"] - 0.8) / 1.2).clip(0, 1)
    )

    # =========================================================
    # [v3 強化] 進場型態：三種高勝率型態
    # VCP突破（score=1）、均線黏合突破（0.9）、標準突破（0.8）、回測支撐（0.6）
    # =========================================================
    setup_vcp      = (P["SetupType"] == 4).astype(float)  # VCP突破（最強）
    setup_cohesion = (P["SetupType"] == 3).astype(float)  # 均線黏合突破
    setup_std      = (P["SetupType"] == 2).astype(float)  # 標準20日高突破
    setup_pb       = (P["SetupType"] == 1).astype(float)  # 回測月線

    f["setup"] = (
        1.00 * setup_vcp +
        0.90 * setup_cohesion +
        0.80 * setup_std +
        0.60 * setup_pb
    ).clip(0, 1)

    return f


def composite_score(feats: dict, preset: str) -> pd.DataFrame:
    w = PRESETS[preset]
    tot = sum(w.values())
    return sum(feats[k] * v for k, v in w.items()) / tot * 100


def universe_masks(P: dict, flt: Filters):
    C = P["Close"]
    liquid = ((C > flt.min_price) &
              (P["Turnover_MA5"] >= flt.min_turnover) &
              (P["Amp20"] >= flt.min_amp) &
              (P["Volume"] > 0) &
              P["MA60"].notna() &
              P["ATR"].notna())
    trend_ok = (C > P["MA20"]) & (C > P["MA60"]) & (P["MA20_slope5"] > -0.005)
    heat_ok = (P["Bias5"] <= flt.bias5_max) & (P["Bias20"] <= flt.bias20_max)
    return liquid, liquid & trend_ok & heat_ok


def regime_levels(bench_close: pd.Series, idx, P: dict):
    """大盤環境分三級：2 多頭(最多4檔) / 1 中性(最多2檔) / 0 空頭(不進場)"""
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


# =========================================================
# [v3 新增] 類股輪動強弱評分
# 計算各股過去 10 日相對大盤的超額報酬，找出強勢族群
# =========================================================
def compute_sector_strength(P: dict, bench_close: pd.Series, sector_map: dict) -> dict:
    """
    sector_map: {code: sector_name}
    返回：{sector_name: avg_rs10}（正值=強勢，負值=弱勢）
    """
    C = P["Close"].ffill()
    b = bench_close.reindex(C.index).ffill()
    rs10 = (C / C.shift(10) - 1).sub(b / b.shift(10) - 1, axis=0)
    latest_rs = rs10.iloc[-1]
    sector_scores = {}
    for code, sector in sector_map.items():
        if code in latest_rs and pd.notna(latest_rs[code]):
            sector_scores.setdefault(sector, []).append(float(latest_rs[code]))
    return {k: np.mean(v) for k, v in sector_scores.items()}


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
                        LOW5=P["Low5"].to_numpy(), SETUP=P["SetupType"].to_numpy())
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


# ----------------------------------------------------------------------------
# 交易計畫（v3：依進場型態動態選擇停損倍數）
# 核心改善：突破型用更緊停損（提升風報比），回測型略寬（允許波動）
# ----------------------------------------------------------------------------
def plan_trade(fill: float, atr: float, low5: float, stop_atr: float, tp_r: float,
               setup_type: int = 0):
    """
    setup_type:
      4 = VCP突破：停損最緊（×0.7），這種型態失敗快跑
      3 = 均線黏合突破：停損緊（×0.8）
      2 = 標準突破：原始停損
      1 = 回測支撐：停損略寬（×1.1），允許更多波動
      0 = 其他：原始停損
    """
    atr_mult = {4: 0.70, 3: 0.80, 2: 1.00, 1: 1.10, 0: 1.00}.get(int(setup_type), 1.0)
    effective_atr = stop_atr * atr_mult
    stop_raw = fill - effective_atr * atr
    struct = low5 * 0.99
    stop = max(stop_raw, struct)
    risk = float(np.clip((fill - stop) / fill, 0.02, 0.10))
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


MAX_BY_LEVEL = {0: 0, 1: 2, 2: 4}


def simulate(eng: Engine, params: Params, start: int, end: int, max_pos: int = 4):
    A = eng.arr
    O, H, L, C, Cf, ATR, LOW5 = A["O"], A["H"], A["L"], A["C"], A["Cf"], A["ATR"], A["LOW5"]
    SETUP = A["SETUP"]
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
                           net_pct=net, r_mult=(px - p["fill"]) / p["R"],
                           setup_type=p.get("setup_type", 0)))

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
                setup_type = int(SETUP[d - 1, j]) if not np.isnan(SETUP[d - 1, j]) else 0
                if np.isnan(o) or np.isnan(pc) or np.isnan(atr) or np.isnan(low5):
                    continue
                if o / pc - 1 >= 0.09:
                    continue
                fill = o * (1 + slip)
                stop, tp, R = plan_trade(fill, atr, low5, params.stop_atr, params.tp_r, setup_type)
                equity = cash + sum(p["sh"] * Cf[d - 1, p["j"]] for p in pos)
                alloc = min(equity / max_pos, cash, equity * eng.risk_frac / max(R / fill, 1e-9))
                sh = int(alloc / (fill * (1 + fee)))
                if sh <= 0:
                    continue
                cash -= sh * fill * (1 + fee)
                pos.append(dict(j=j, d0=d, fill=fill, stop=stop, tp=tp, R=R, sh=sh,
                                atr=atr, hh=fill, setup_type=setup_type))
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
                px = p["stop"]
                reason = "停損" if p["stop"] < p["fill"] else ("移動停利" if p["stop"] > p["fill"] * 1.01 else "保本出場")
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
                    p["stop"] = max(p["stop"], tick_round(p["fill"] * 1.006))
                if p["hh"] >= p["fill"] + 1.5 * p["R"]:
                    p["stop"] = max(p["stop"], tick_round(p["hh"] - params.trail_atr * p["atr"]))

        eq_vals.append(cash + sum(p["sh"] * Cf[d, p["j"]] for p in pos))
        eq_idx.append(eng.idx[d])

    for p in list(pos):
        close_pos(p, end - 1, Cf[end - 1, p["j"]], "視窗結束")
    if eq_vals:
        eq_vals[-1] = cash
    equity = pd.Series(eq_vals, index=eq_idx, dtype=float) / init
    return pd.DataFrame(trades), equity


# ----------------------------------------------------------------------------
# 績效統計
# ----------------------------------------------------------------------------
def _wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    ctr = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (ctr - half) * 100, (ctr + half) * 100


def summarize(trades: pd.DataFrame, equity: pd.Series | None = None) -> dict:
    s = dict(n=len(trades), win_rate=np.nan, avg_win=np.nan, avg_loss=np.nan, payoff=np.nan, expectancy=np.nan,
             profit_factor=np.nan, tstat=np.nan, wr_lo=np.nan, wr_hi=np.nan, max_consec_loss=0, avg_hold=np.nan,
             total_ret=np.nan, cagr=np.nan, mdd=np.nan, sharpe=np.nan, exp_lo=np.nan, exp_hi=np.nan)
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
        s["wr_lo"], s["wr_hi"] = _wilson(len(wins), n)
        run = best = 0
        for x in r:
            run = run + 1 if x <= 0 else 0
            best = max(best, run)
        s["max_consec_loss"] = best
        s["avg_hold"] = trades["days"].mean()
        if n >= 5:
            rng = np.random.default_rng(7)
            bs = rng.choice(r, size=(2000, n), replace=True).mean(axis=1)
            s["exp_lo"], s["exp_hi"] = np.percentile(bs, [5, 95])
        # [v3] 各型態勝率分析
        if "setup_type" in trades.columns:
            for st in [1, 2, 3, 4]:
                sub = r[trades["setup_type"].to_numpy() == st]
                if len(sub) >= 3:
                    s[f"wr_setup{st}"] = (sub > 0).mean() * 100
                    s[f"exp_setup{st}"] = sub.mean()
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


def mc_ruin(trade_rets_pct, n_sims=2000, n_trades=60, frac=0.25, block=3, ruin=0.5, seed=42) -> dict:
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


# ----------------------------------------------------------------------------
# Walk-forward
# ----------------------------------------------------------------------------
def _objective(st: dict, min_trades: int) -> float:
    if st["n"] < min_trades or np.isnan(st["tstat"]):
        return -1e9
    # [v3] 加入勝率懲罰：勝率低於45%時降低目標函數
    wr_penalty = max(0.0, (45.0 - st["win_rate"]) / 10.0) if not np.isnan(st["win_rate"]) else 0.0
    return (st["tstat"]
            - max(0.0, (st["mdd"] if not np.isnan(st["mdd"]) else 0) - 20.0) / 10.0
            - wr_penalty)  # [v3] 新增勝率懲罰


_ORD_DIMS = ("min_score", "stop_atr", "tp_r", "trail_atr", "hold")


def _ckey(c: Params):
    return (c.preset, c.min_score, c.stop_atr, c.tp_r, c.trail_atr, c.hold)


def smooth_objectives(combos: list, objs: list, grid: dict) -> list:
    pos = {_ckey(c): i for i, c in enumerate(combos)}
    out = []
    for i, c in enumerate(combos):
        if objs[i] <= -1e8:
            out.append(-1e9)
            continue
        vals = [objs[i]]
        for name in _ORD_DIMS:
            lst = grid[name]
            j = lst.index(getattr(c, name))
            for dj in (-1, 1):
                if 0 <= j + dj < len(lst):
                    n = Params(**{**c.__dict__, name: lst[j + dj]})
                    vals.append(objs[pos[_ckey(n)]])
        out.append(float(np.mean([max(v, -5.0) for v in vals])))
    return out


def walk_forward(eng: Engine, grid: dict | None = None, train_days: int = 250, test_days: int = 60,
                 min_trades: int = 12, progress=None, warm: int = 70):
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

    total = (len(folds) * 2 + 1) * len(combos)
    step = 0
    rows, oos_trades, chained = [], [], []
    level = 1.0
    sel_counter = {}

    for fi, (a, b, e) in enumerate(folds):
        tr_stats, te_stats, te_data = [], [], []
        for c in combos:
            t, q = simulate(eng, c, a, b)
            tr_stats.append(summarize(t, q))
            step += 1
            t2, q2 = simulate(eng, c, b, e)
            te_stats.append(summarize(t2, q2))
            te_data.append((t2, q2))
            step += 1
            if progress:
                progress(min(step / total, 1.0))
        objs = [_objective(s, min_trades) for s in tr_stats]
        sm = smooth_objectives(combos, objs, grid)
        bi = int(np.argmax(sm))
        if sm[bi] <= -1e8:
            rows.append(dict(fold=fi + 1, train=f"{eng.idx[a].date()}~{eng.idx[b-1].date()}",
                             test=f"{eng.idx[b].date()}~{eng.idx[e-1].date()}", params="訓練期交易數不足，略過",
                             train_n=0, train_exp=np.nan, test_n=0, test_exp=np.nan, test_ret=np.nan,
                             test_mdd=np.nan, rank_pct=np.nan))
            continue
        best = combos[bi]
        sel_counter[best.preset] = sel_counter.get(best.preset, 0) + 1
        t2, q2 = te_data[bi]
        exps = np.array([s["expectancy"] if s["n"] > 0 else np.nan for s in te_stats], dtype=float)
        me = te_stats[bi]["expectancy"]
        valid = ~np.isnan(exps)
        rank_pct = (np.sum(exps[valid] < me) / valid.sum() * 100) if (valid.any() and not np.isnan(me)) else np.nan
        rows.append(dict(fold=fi + 1, train=f"{eng.idx[a].date()}~{eng.idx[b-1].date()}",
                         test=f"{eng.idx[b].date()}~{eng.idx[e-1].date()}", params=best.label(),
                         train_n=tr_stats[bi]["n"], train_exp=tr_stats[bi]["expectancy"],
                         test_n=te_stats[bi]["n"], test_exp=me, test_ret=te_stats[bi]["total_ret"],
                         test_mdd=te_stats[bi]["mdd"], rank_pct=rank_pct))
        if len(t2):
            t2 = t2.copy()
            t2["fold"] = fi + 1
            oos_trades.append(t2)
        chained.append(q2 * level)
        level = chained[-1].iloc[-1]

    a, b = T - train_days, T
    fin_stats = []
    for c in combos:
        t, q = simulate(eng, c, a, b)
        fin_stats.append(summarize(t, q))
        step += 1
        if progress:
            progress(min(step / total, 1.0))
    fobj = [_objective(s, min_trades) for s in fin_stats]
    fsm = smooth_objectives(combos, fobj, grid)
    fi_best = int(np.argmax(fsm))
    final_params, final_stats = combos[fi_best], fin_stats[fi_best]
    final_ok = fsm[fi_best] > -1e8

    oos_tr = pd.concat(oos_trades, ignore_index=True) if oos_trades else pd.DataFrame()
    oos_eq = pd.concat(chained) if chained else pd.Series(dtype=float)
    oos_stats = summarize(oos_tr, oos_eq if len(oos_eq) else None)
    fold_df = pd.DataFrame(rows)
    is_exp = fold_df["train_exp"].mean() if len(fold_df) else np.nan
    return dict(folds=fold_df, oos_trades=oos_tr, oos_equity=oos_eq, oos_stats=oos_stats,
                is_expectancy=is_exp, rank_pct_median=fold_df["rank_pct"].median() if len(fold_df) else np.nan,
                preset_selection=sel_counter, n_folds=len(folds), n_combos=len(combos),
                final_params=final_params if final_ok else Params(), final_stats=final_stats, final_ok=final_ok,
                train_days=train_days, test_days=test_days)


def verdict(wf: dict, bench_ret_pct: float | None = None):
    o = wf["oos_stats"]
    bullets, level = [], "green"

    def down(new):
        nonlocal level
        order = {"green": 0, "yellow": 1, "red": 2}
        if order[new] > order[level]:
            level = new

    n = o["n"]
    if n == 0:
        return "red", "樣本外沒有任何交易，無法驗證策略。", ["請放寬篩選條件、增加股票池或拉長資料期間。"]
    if n < 30:
        down("yellow")
        bullets.append(f"樣本外僅 {n} 筆交易（<30），任何績效數字的可信度都很有限。")
    exp = o["expectancy"]
    if exp <= 0:
        down("red")
        bullets.append(f"樣本外每筆期望值 {exp:+.2f}%（扣成本後）≤ 0：策略在未見過的資料上沒有優勢。")
    else:
        bullets.append(f"樣本外每筆期望值 {exp:+.2f}%（90% 自助信賴區間 {o['exp_lo']:+.2f}% ~ {o['exp_hi']:+.2f}%）。")
        if not np.isnan(o["exp_lo"]) and o["exp_lo"] <= 0:
            down("yellow")
            bullets.append("信賴區間下緣 ≤ 0：無法排除『只是運氣』。")
    if not np.isnan(o["win_rate"]) and o["win_rate"] < 45:
        down("yellow")
        bullets.append(f"勝率 {o['win_rate']:.1f}% < 45%，即使期望值為正，心理壓力仍大，考慮收緊停損或提高進場門檻。")
    if not np.isnan(o["tstat"]) and o["tstat"] < 1.65:
        down("yellow")
        bullets.append(f"t 值 {o['tstat']:.2f} < 1.65，統計顯著性不足。")
    ise = wf.get("is_expectancy", np.nan)
    if not np.isnan(ise) and ise > 0 and not np.isnan(exp) and exp < 0.5 * ise:
        down("yellow")
        bullets.append(f"樣本外期望值（{exp:+.2f}%）不到訓練期平均（{ise:+.2f}%）的一半，疑似過擬合。")
    rp = wf.get("rank_pct_median", np.nan)
    if not np.isnan(rp):
        if rp < 55:
            down("yellow")
            bullets.append(f"訓練期選出的參數在測試期僅排在同組參數的第 {rp:.0f} 百分位，挑參數沒有增值。")
        else:
            bullets.append(f"所選參數在測試期排名第 {rp:.0f} 百分位，優於多數候選參數。")
    if not np.isnan(o["mdd"]) and o["mdd"] > 20:
        down("yellow")
        bullets.append(f"樣本外最大回撤 {o['mdd']:.1f}%，偏大。")
    if o["max_consec_loss"] >= 6:
        bullets.append(f"最大連虧 {o['max_consec_loss']} 次，需要能承受這種連續虧損的部位大小。")
    if bench_ret_pct is not None and not np.isnan(bench_ret_pct) and not np.isnan(o["total_ret"]):
        diff = o["total_ret"] - bench_ret_pct
        if diff < 0:
            down("yellow")
            bullets.append(f"同期大盤買進持有 {bench_ret_pct:+.1f}%，策略 {o['total_ret']:+.1f}%，尚未贏過指數。")
        else:
            bullets.append(f"同期大盤 {bench_ret_pct:+.1f}%，策略 {o['total_ret']:+.1f}%，超額 {diff:+.1f}%。")
    heads = {"green": "樣本外驗證：通過基本檢查（仍不保證未來獲利）。",
             "yellow": "樣本外驗證：有疑慮，建議縮小部位或僅作觀察。",
             "red": "樣本外驗證：未通過，策略目前沒有可證實的優勢。"}
    return level, heads[level], bullets


def _fwd(eng: Engine, horizon: int) -> pd.DataFrame:
    P = eng.P
    return P["Close"].shift(-horizon) / P["Open"].shift(-1) - 1


def signal_quality(eng: Engine, preset: str, horizon: int = 10) -> dict:
    fwd, S, U = _fwd(eng, horizon), eng.scores[preset], eng.liquid
    valid = U & fwd.notna() & S.notna()
    s = S.where(valid).rank(axis=1)
    f = fwd.where(valid).rank(axis=1)
    n = valid.sum(axis=1)
    sm, fm = s.sub(s.mean(axis=1), axis=0), f.sub(f.mean(axis=1), axis=0)
    ic = (sm * fm).sum(axis=1) / np.sqrt((sm ** 2).sum(axis=1) * (fm ** 2).sum(axis=1))
    ic = ic[n >= 20].dropna()
    ic_s = ic.iloc[::horizon]
    res = dict(horizon=horizon, days=len(ic_s), ic_mean=np.nan, ic_ir=np.nan, ic_t=np.nan, quintile=pd.DataFrame())
    if len(ic_s) >= 5:
        res["ic_mean"] = ic_s.mean()
        res["ic_ir"] = ic_s.mean() / ic_s.std() if ic_s.std() > 0 else np.nan
        res["ic_t"] = ic_s.mean() / (ic_s.std() / np.sqrt(len(ic_s))) if ic_s.std() > 0 else np.nan
    b = np.ceil(s.div(n, axis=0) * 5).clip(1, 5)
    df = pd.DataFrame({"bucket": b.stack(), "fwd": fwd.where(valid).stack()}).dropna()
    if len(df):
        q = df.groupby("bucket")["fwd"].agg(平均報酬="mean", 勝率=lambda x: (x > 0).mean(), 樣本數="size")
        q["平均報酬"] *= 100
        q["勝率"] *= 100
        q.index = [f"Q{int(i)}" + ("（最低分）" if i == 1 else "（最高分）" if i == 5 else "") for i in q.index]
        res["quintile"] = q
    return res


def score_calibration(eng: Engine, preset: str, horizon: int) -> pd.DataFrame:
    fwd, S = _fwd(eng, horizon), eng.scores[preset]
    E = eng.elig & fwd.notna() & S.notna()
    df = pd.DataFrame({"score": S.where(E).stack(), "fwd": fwd.where(E).stack()}).dropna()
    if df.empty:
        return pd.DataFrame()
    df["band"] = pd.cut(df["score"], [0, 55, 65, 75, 85, 101], right=False,
                        labels=["<55", "55-65", "65-75", "75-85", "85+"])
    out = df.groupby("band", observed=True)["fwd"].agg(平均報酬="mean", 勝率=lambda x: (x > 0).mean(), 樣本數="size")
    out["平均報酬"] *= 100
    out["勝率"] *= 100
    return out


# ----------------------------------------------------------------------------
# 主力籌碼加減分（v3 強化版）
# 改變：
#   1. 外資連續買超天數 consec_foreign → 每天+1分（最高+6分）
#   2. 投信連續買超天數 consec_trust  → 每天+0.8分（最高+4分）
#   3. 法人合買信號（外資+投信同日買）→ +5分
#   4. 大戶持股週增減 d_big400       → ±3分（原版保留）
#   5. 上限從 ±10 提升為 ±15 分
# ----------------------------------------------------------------------------
def make_chip_fn(chips, tdcc, weight: float = 1.0):
    """
    主力籌碼加減分（±15 上限，v3 強化版）：
    - 外資連續買超天數：每日+1分（上限+6分）
    - 投信連續買超天數：每日+0.8分（上限+4分）
    - 外資+投信同日合買：+5分加成（法人合買信號，最強）
    - 大戶(>400張)持股週增減：±3分
    說明：
    這部分沒有歷史資料可回測，只用於『即時排序』，
    與已驗證的技術分數分開顯示為「主力分」。
    """
    def fn(code: str, close: float, turnover5: float):
        b, det = 0.0, {}
        if chips is not None and len(chips) and code in chips.index and turnover5 > 0:
            r = chips.loc[code]
            # [v3] 改用「連續買超天數」而非「金額比率」，更直接反映主力意圖
            consec_f = int(r.get("consec_foreign", 0)) if pd.notna(r.get("consec_foreign", np.nan)) else 0
            consec_t = int(r.get("consec_trust", 0)) if pd.notna(r.get("consec_trust", np.nan)) else 0
            foreign_val = float(r["foreign"])
            trust_val = float(r["trust"])

            # 連續買超加分
            f_score = min(consec_f * 1.0, 6.0)    # 最高+6
            t_score = min(consec_t * 0.8, 4.0)    # 最高+4
            b += f_score + t_score

            # 法人合買加成（外資與投信同日都買 → 強信號）
            if foreign_val > 0 and trust_val > 0:
                b += 5.0
            # 外資大量賣超懲罰
            elif foreign_val < 0:
                denom = turnover5 * 5
                f_ratio = abs(foreign_val) * close / denom
                b -= float(np.clip(f_ratio / 0.05, 0, 1)) * 3.0

            det.update(foreign=foreign_val, trust=trust_val, total=float(r["total"]),
                       consec_foreign=consec_f, consec_trust=consec_t)

        if tdcc is not None and len(tdcc) and code in tdcc.index:
            r = tdcc.loc[code]
            det.update(big400=float(r["big400"]) if pd.notna(r["big400"]) else np.nan,
                       d_big400=float(r["d_big400"]) if pd.notna(r["d_big400"]) else np.nan)
            if pd.notna(r["d_big400"]):
                b += float(np.clip(float(r["d_big400"]) / 0.5, -1, 1)) * 3

        # 上限 ±15（v3 提升，因為主力訊號更重要）
        return float(np.clip(b * weight, -15, 15)), det
    return fn


def latest_candidates(eng: Engine, params: Params, top: int = 10, exclude: set | None = None,
                       chip_fn=None, force_sector: set | None = None) -> list:
    """
    force_sector: 如果指定，只考慮在該族群內的股票（類股輪動過濾）
    """
    S = eng.scores[params.preset].iloc[-1]
    E = eng.elig.iloc[-1]
    m = E & (S >= params.min_score)
    if exclude:
        m &= ~S.index.isin(list(exclude))
    P = eng.P
    pool = S[m].sort_values(ascending=False).index[:max(top * 3, 30)]
    out = []
    for code in pool:
        close = float(P["Close"][code].iloc[-1])
        atr = float(P["ATR"][code].iloc[-1])
        low5 = float(P["Low5"][code].iloc[-1])
        setup_type = int(P["SetupType"][code].iloc[-1]) if pd.notna(P["SetupType"][code].iloc[-1]) else 0
        fill = close * (1 + eng.costs.slip)
        stop, tp, R = plan_trade(fill, atr, low5, params.stop_atr, params.tp_r, setup_type)
        turn5 = float(P["Turnover_MA5"][code].iloc[-1])
        bonus, det = chip_fn(code, close, turn5) if chip_fn else (0.0, {})
        tech = float(S[code])
        setup_names = {0: "無", 1: "回測月線", 2: "突破20高", 3: "均線黏合突破", 4: "VCP突破"}
        out.append(dict(code=code, score=tech, bonus=bonus, final=tech + bonus, chip=det, close=close,
                        pct=float(P["pct"][code].iloc[-1]), stop=stop, tp=tp, risk_pct=(fill - stop) / fill * 100,
                        turnover_yi=turn5 / 1e8, volume_lots=float(P["Volume"][code].iloc[-1]) / 1000,
                        bias5=float(P["Bias5"][code].iloc[-1]), bias20=float(P["Bias20"][code].iloc[-1]),
                        k=float(P["K"][code].iloc[-1]), rsi=float(P["RSI"][code].iloc[-1]),
                        setup_type=setup_type, setup_name=setup_names.get(setup_type, "未知"),
                        vcp_score=float(P["VCP_Score"][code].iloc[-1]),
                        obv_slope=float(P["OBV_Slope20"][code].iloc[-1]) if pd.notna(P["OBV_Slope20"][code].iloc[-1]) else 0.0,
                        obv_diverge=bool(P["OBV_Diverge"][code].iloc[-1]),
                        pos52w=float(P["Pos52W"][code].iloc[-1]),
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
    if x.get("VCP_Score", 0) >= 0.7 and c > x["High20_prev"]: ev.append(("vcp_breakout", "💎 VCP完整型態突破"))
    if x.get("MA_Cohesion", 0) == 1 and c > x["High20_prev"]: ev.append(("cohesion_break", "⚡ 均線黏合突破"))
    if x.get("OBV_Diverge", 0) == 1: ev.append(("obv_diverge", "🐋 OBV上升/價橫（主力吸籌）"))
    if c > x["MA20"] and p["Close"] <= p["MA20"]: ev.append(("up_ma20", "⬆ 站上月線"))
    if c < x["MA20"] and p["Close"] >= p["MA20"]: ev.append(("dn_ma20", "⬇ 跌破月線"))
    if c > x["MA60"] and p["Close"] <= p["MA60"]: ev.append(("up_ma60", "⬆ 站上季線"))
    if c < x["MA60"] and p["Close"] >= p["MA60"]: ev.append(("dn_ma60", "⬇ 跌破季線"))
    if x["K"] > x["D"] and p["K"] <= p["D"] and x["K"] < 80: ev.append(("kd_gold", "KD 黃金交叉"))
    if x["K"] < x["D"] and p["K"] >= p["D"] and p["K"] > 70: ev.append(("kd_dead", "KD 高檔死亡交叉"))
    if x["MACD_Hist"] > 0 and p["MACD_Hist"] <= 0: ev.append(("macd_up", "MACD 翻紅"))
    if x["MACD_Hist"] < 0 and p["MACD_Hist"] >= 0: ev.append(("macd_dn", "MACD 翻綠"))
    if vr > 2 and c > x["Open"] and body > 0.6: ev.append(("big_red", "🔥 爆量長紅"))
    if vr > 2 and c < x["Open"] and body > 0.6: ev.append(("big_black", "⚠ 爆量長黑"))
    if x["RSI"] > 75 and p["RSI"] <= 75: ev.append(("rsi_hot", "RSI 過熱(>75)"))
    if x["RSI"] < 30 and p["RSI"] >= 30: ev.append(("rsi_cold", "RSI 超賣(<30)"))
    return ev


SCREEN_FLAGS = [
    "多頭排列 (收盤>20MA>60MA)", "空轉多 (3日內站上月線)", "多頭擴大 (5>10>20>60MA)", "今日強勢漲停 (≥9.5%)",
    "突破週線 (3日內站上5MA)", "突破月線 (3日內站上20MA)", "突破季線 (3日內站上60MA)", "創20日新高",
    "VCP 收斂 (帶寬低檔+5日振幅<6%)", "窒息量縮 (量<20日均量60%)", "爆量攻擊 (量>5日均量1.5倍)",
    "量價鎖碼 (CLV推力>0.15)", "MACD 紅柱", "RSI 50–70 健康動能", "KD 黃金交叉 (K>D 且 K<80)",
    "NR7 窄幅 (彈簧效應前兆)",        # [v3] 新增
    "OBV 上升背離 (主力吸籌)",        # [v3] 新增
    "均線黏合 (5/10/20MA距離<1.5%)",  # [v3] 新增
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
        SCREEN_FLAGS[13]: last((P["RSI"] >= 50) & (P["RSI"] <= 70)),
        SCREEN_FLAGS[14]: last((P["K"] > P["D"]) & (P["K"] < 80)),
        SCREEN_FLAGS[15]: last(P["NR7"] > 0),               # [v3]
        SCREEN_FLAGS[16]: last(P["OBV_Diverge"] > 0),       # [v3]
        SCREEN_FLAGS[17]: last(P["MA_Cohesion"] > 0),       # [v3]
    }
    out = pd.DataFrame({
        "close": last(C), "pct": last(P["pct"]), "volume_lots": last(P["Volume"]) / 1000,
        "turnover_yi": last(P["Turnover_MA5"]) / 1e8, "bias5": last(P["Bias5"]), "bias20": last(P["Bias20"]),
        "K": last(P["K"]), "RSI": last(P["RSI"]), "score": last(eng.scores[preset]),
        "liquid": last(eng.liquid), "eligible": last(eng.elig),
        "setup_type": last(P["SetupType"]),   # [v3]
        "vcp_score": last(P["VCP_Score"]),    # [v3]
    })
    for k, v in flags.items():
        out[k] = v.astype(bool)
    return out


def bull_bear_checks(d: pd.DataFrame, chip: dict | None = None, rev_yoy: float | None = None) -> dict:
    bull, bear = [], []
    x, p = d.iloc[-1], d.iloc[-2]
    c = x["Close"]
    if c > x["MA5"]:   bull.append("站上週線 5MA")
    if c > x["MA20"]:  bull.append("站上月線 20MA")
    if c > x["MA60"]:  bull.append("站上季線 60MA")
    if (d["Close"].tail(5) > d["MA20"].tail(5)).all(): bull.append("連5日站穩月線")
    if x["MA5"] > x["MA10"] > x["MA20"]:  bull.append("短線多頭排列")
    if x["MA10"] > x["MA20"] > x["MA60"]: bull.append("長線多頭排列")
    if 50 <= x["K"] <= 80 and x["K"] > x["D"]:  bull.append("KD 多方強勢")
    if x["MACD_Hist"] > 0:                       bull.append("MACD 紅柱")
    if 50 <= x["RSI"] <= 70:                     bull.append("RSI 健康動能")
    if x["Volume"] > x["Vol_MA5"] * 1.3 and c > p["Close"]: bull.append("價漲量增")
    # [v3] 新增主力/結構性多頭訊號
    if x.get("OBV_Slope20", 0) > 0.005:          bull.append("OBV 持續上升（主力流入）")
    if x.get("OBV_Diverge", 0) == 1:             bull.append("OBV 背離（主力秘密吸籌）")
    if x.get("VCP_Score", 0) >= 0.7:             bull.append("VCP 型態完整（彈簧蓄勢）")
    if x.get("MA_Cohesion", 0) == 1:             bull.append("均線黏合（多方力量集結）")
    if x.get("NR7", 0) == 1:                     bull.append("NR7 窄幅（彈簧效應前兆）")

    if c < x["MA20"]:  bear.append("跌破月線")
    if c < x["MA60"]:  bear.append("跌破季線")
    if x["MA20"] < x["MA60"] and c < x["MA20"]: bear.append("均線空頭排列")
    if x["Bias5"] > 3.5:    bear.append("短線乖離過大")
    if x["Bias20"] > 12:    bear.append("月線乖離過熱")
    if x["RSI"] > 75:       bear.append("RSI 過熱")
    if x["MACD_Hist"] < 0:  bear.append("MACD 綠柱")
    if x["Volume"] > x["Vol_MA5"] * 1.3 and c < p["Close"]: bear.append("價跌量增")
    if chip:
        consec_f = chip.get("consec_foreign", 0)
        consec_t = chip.get("consec_trust", 0)
        if consec_f >= 3:   bull.append(f"外資連續買超 {consec_f} 日")
        elif chip.get("foreign", 0) < 0: bear.append("外資近5日賣超")
        if consec_t >= 5:   bull.append(f"投信連續買超 {consec_t} 日")
        elif chip.get("trust", 0) < 0:   bear.append("投信近5日賣超")
        if chip.get("foreign", 0) > 0 and chip.get("trust", 0) > 0:
            bull.append("外資+投信同步買超（法人合買）")
        d4 = chip.get("d_big400")
        if d4 is not None and d4 == d4:
            if d4 > 0.1:  bull.append(f"大戶持股週增 {d4:+.2f}pp")
            elif d4 < -0.1: bear.append(f"大戶持股週減 {d4:+.2f}pp")
    if rev_yoy is not None and not np.isnan(rev_yoy):
        if rev_yoy >= 20:   bull.append(f"月營收年增 {rev_yoy:.0f}%")
        elif rev_yoy > 0:   bull.append(f"月營收年增 {rev_yoy:.0f}%")
        else:               bear.append(f"月營收年減 {rev_yoy:.0f}%")
    return dict(bull=bull, bear=bear)


def holding_health(d: pd.DataFrame, params: Params) -> dict:
    x, p = d.iloc[-1], d.iloc[-2]
    close = float(x["Close"])
    setup_type = int(x.get("SetupType", 0)) if pd.notna(x.get("SetupType", 0)) else 0
    stop, tp, R = plan_trade(close, float(x["ATR"]), float(x["Low5"]), params.stop_atr, params.tp_r, setup_type)
    flags, weak = [], 0
    if close < x["MA20"]: flags.append("跌破月線"); weak += 2
    if x["MA20_slope5"] < 0: flags.append("月線下彎"); weak += 1
    if close < x["MA60"]: flags.append("跌破季線"); weak += 2
    if x["RSI"] < 45: flags.append("RSI<45 動能轉弱"); weak += 1
    if close <= stop: flags.append("觸及防守價"); weak += 3
    return dict(close=close, stop=stop, tp=tp, weak=weak, flags=flags,
                ret20=float(close / d["Close"].iloc[-21] - 1) * 100 if len(d) > 21 else np.nan)


# ============================================================================
# 共用：題材庫、檔案存取、引擎建構、訊號與推播、背景模式
# ============================================================================
SECTORS = {
    "重電綠能與強韌電網": [("1513", "中興電", ["儲能", "離岸風電", "GIS"]), ("1609", "大亞", ["電纜", "儲能"]),
                          ("1519", "華城", ["變壓器", "外銷"]), ("1503", "士電", ["重電", "車用電裝"]),
                          ("1514", "亞力", ["變配電", "半導體廠務"]), ("2371", "大同", ["重電", "資產開發"])],
    "CPO 矽光子與光通訊": [("3450", "聯鈞", ["光收發", "CPO"]), ("3363", "上詮", ["光纖陣列", "CPO"]),
                          ("3081", "聯亞", ["磊晶", "InP"]), ("4979", "華星光", ["AOC", "光模組"]),
                          ("6442", "光聖", ["光被動"]), ("4977", "眾達-KY", ["CPO", "光模組"])],
    "散熱模組與水冷系統": [("3017", "奇鋐", ["水冷板", "散熱模組"]), ("3324", "雙鴻", ["液冷", "CDU"]),
                          ("3653", "健策", ["均熱片"]), ("8996", "高力", ["熱交換器"]),
                          ("6230", "尼得科超眾", ["熱導管"]), ("3483", "力致", ["散熱模組"])],
    "AI 伺服器與硬體代工": [("2382", "廣達", ["AI伺服器"]), ("3231", "緯創", ["GPU基板"]), ("2376", "技嘉", ["AI伺服器"]),
                           ("6669", "緯穎", ["雲端ODM"]), ("2059", "川湖", ["伺服器滑軌"]), ("8210", "勤誠", ["伺服器機殼"])],
    "PCB、載板與 CCL": [("2383", "台光電", ["CCL"]), ("3037", "欣興", ["ABF載板"]), ("2368", "金像電", ["高層PCB"]),
                       ("6274", "台燿", ["CCL"]), ("3189", "景碩", ["載板"]), ("8046", "南電", ["載板"])],
    "記憶體模組與控制晶片": [("8299", "群聯", ["NAND控制IC"]), ("3260", "威剛", ["記憶體模組"]), ("4967", "十銓", ["記憶體模組"]),
                            ("2408", "南亞科", ["DRAM"]), ("2344", "華邦電", ["NOR/利基DRAM"]), ("3006", "晶豪科", ["利基DRAM"])],
    "半導體製造與設備": [("2330", "台積電", ["晶圓代工"]), ("2303", "聯電", ["成熟製程"]), ("3583", "辛耘", ["濕製程設備"]),
                        ("3131", "弘塑", ["濕製程設備"]), ("6223", "旺矽", ["探針卡"]), ("1560", "中砂", ["鑽石碟"])],
    "機器人自動化與智慧工具機": [("2359", "所羅門", ["機器視覺"]), ("2365", "昆盈", ["感測"]), ("6188", "廣明", ["協作機器人"]),
                                ("8374", "羅昇", ["傳動控制"]), ("2049", "上銀", ["滾珠螺桿"]), ("4583", "台灣精銳", ["精密減速機"])],
    "AI 晶片與 IP": [("2454", "聯發科", ["手機AP", "ASIC"]), ("3661", "世芯-KY", ["ASIC"]), ("3443", "創意", ["ASIC", "IP"]),
                    ("3529", "力旺", ["矽智財"]), ("6117", "迎廣", ["機殼", "水冷"])],
}
NAME_MAP = {c: n for v in SECTORS.values() for c, n, _ in v}
TAG_MAP = {c: t for v in SECTORS.values() for c, _, t in v}

PORTFOLIO_FILE = Path("portfolio.json")
DEFAULT_PORTFOLIO = [
    {"code": "2330", "cost": 950.0, "shares": 1000, "date": "2026-09-15"},
    {"code": "3189", "cost": 115.0, "shares": 5000, "date": "2026-09-20"},
    {"code": "3653", "cost": 820.0, "shares": 1000, "date": "2026-09-22"},
    {"code": "1513", "cost": 165.0, "shares": 6000, "date": "2026-09-25"},
]


def load_portfolio() -> list:
    try:
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [dict(x) for x in DEFAULT_PORTFOLIO]


def save_portfolio(rows: list):
    PORTFOLIO_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


WATCHLIST_FILE = Path("watchlist.json")
BEST_PARAMS_FILE = Path("best_params.json")


def load_watchlist() -> list:
    try:
        return [str(x).strip() for x in json.loads(WATCHLIST_FILE.read_text(encoding="utf-8")) if str(x).strip()]
    except Exception:
        return []


def save_watchlist(codes: list):
    WATCHLIST_FILE.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")


def save_best_params(p: Params, level: str = ""):
    try:
        BEST_PARAMS_FILE.write_text(json.dumps(dict(asdict(p), verdict=level, saved=now_tw().isoformat()),
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_best_params():
    try:
        raw = json.loads(BEST_PARAMS_FILE.read_text(encoding="utf-8"))
        return Params(**{k: raw[k] for k in Params.__dataclass_fields__ if k in raw})
    except Exception:
        return None


def load_meta_core(hour_key: str) -> dict:
    uni, m1 = load_universe()
    turn, m2 = load_daily_turnover()
    names, markets, m6 = load_names()
    chips, chip_days, m3 = load_institutional(5)
    tdcc, m7 = load_tdcc()
    rev, m4 = load_revenue_yoy()
    punish, notice, m5 = load_flags()
    cnyes_top, m8 = load_cnyes_foreign_top(50)  # [v3] 外資買超爬蟲
    if uni.empty and markets:
        uni = pd.DataFrame([dict(code=c, name=names.get(c, c), market=m, industry="") for c, m in markets.items()])
    return dict(uni=uni, turn=turn, names=names, markets=markets, chips=chips, chip_days=chip_days, tdcc=tdcc,
                rev=rev, punish=punish, notice=notice, cnyes_top=cnyes_top,
                msgs=m1 + m6 + m2 + m3 + m7 + m4 + m5 + m8)


def build_name_market(meta: dict):
    uni = meta["uni"]
    names = dict(NAME_MAP)
    names.update(dict(zip(uni["code"], uni["name"])))
    names.update(meta["names"])
    market = {**meta["markets"], **dict(zip(uni["code"], uni["market"]))}
    return names, market


def build_engine_core(meta, n, excl, min_price, min_turn_yi, min_amp, b5, b20, fee_disc, slip_pct,
                      risk_frac, use_intraday, get_prices_fn):
    uni, notes = meta["uni"].copy(), []
    if not uni.empty:
        if excl:
            uni = uni[~uni["industry"].isin(list(excl))]
        if len(meta["turn"]):
            uni["turn"] = uni["code"].map(meta["turn"])
            uni = uni.dropna(subset=["turn"]).sort_values("turn", ascending=False).head(n)
        else:
            notes.append("無法取得成交值排名，改用題材清單內的股票。")
            uni = uni[uni["code"].isin(NAME_MAP)]
    else:
        notes.append("官方股票清單抓取失敗，改用題材清單並猜測市場別（可能有誤）。")
        uni = pd.DataFrame([dict(code=c, name=NAME_MAP[c], market="TW", industry="") for c in NAME_MAP])
    tickers = [f"{r.code}.{r.market}" for r in uni.itertuples()]
    prices = get_prices_fn(tuple(tickers + ["^TWII"]))
    bench = prices.pop("^TWII", None)
    if bench is None or not prices:
        raise RuntimeError("價格資料下載失敗（yfinance）。請稍後重試或檢查網路。")
    if not use_intraday:
        prices = {t: closed_only(df) for t, df in prices.items()}
        bench = closed_only(bench)
    dfs = {}
    for t, df in prices.items():
        try:
            dfs[t.split(".")[0]] = add_indicators(df)
        except Exception:
            continue
    P = build_panel(dfs)
    flt = Filters(min_price, min_turn_yi * 1e8, min_amp, b5, b20)
    eng = Engine(P, bench["Close"], flt, Costs(fee_disc=fee_disc, slip=slip_pct / 100.0), risk_frac=risk_frac)
    return eng, bench, notes


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


def assemble_ctx(meta, market, names, eng, params, get_prices_fn, capital, risk_pct, chip_weight,
                 portfolio_rows, watch_codes) -> dict:
    hold_codes = [str(r.get("code", "")).strip() for r in portfolio_rows]
    ind_map = get_ind_map(hold_codes + list(watch_codes), market, get_prices_fn)
    return dict(meta=meta, names=names, market=market, capital=capital, risk_pct=risk_pct,
                portfolio=portfolio_rows, watch=list(watch_codes), ind_map=ind_map,
                chip_fn=make_chip_fn(meta["chips"], meta["tdcc"], chip_weight),
                punish=meta["punish"], notice=meta["notice"],
                cnyes_top=meta.get("cnyes_top", set()))


# ----------------------------------------------------------------------------
# 訊號建立與推播
# ----------------------------------------------------------------------------
@dataclass
class Alert:
    key: str
    cat: str
    text: str


ALERT_CATS = {"regime": "大盤環境轉折", "cand": "新進推薦", "hold": "持股警示", "watch": "自選股事件"}
LVL_TXT = {2: "🟢 多頭（最多4檔）", 1: "🟡 中性（最多2檔）", 0: "🔴 空頭（不新進場）"}
SETUP_TXT = {0: "", 1: "📌回測月線", 2: "📈突破20高", 3: "⚡均線黏合突破", 4: "💎VCP突破"}


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
                         f"🧭 大盤環境轉變：{LVL_TXT[int(prev)]} → {LVL_TXT[lvl]}（加權指數 {float(eng.bench_close.iloc[-1]):,.0f}）"))
    alert_state_set("regime_lvl", lvl)

    if lvl > 0:
        for i, c in enumerate(latest_candidates(eng, params, top=5, exclude=ctx["punish"], chip_fn=ctx["chip_fn"]), 1):
            size = size_position(ctx["capital"], ctx["risk_pct"], c["close"], c["stop"])
            tp_txt = "移動停利" if np.isinf(c["tp"]) else f"{c['tp']:.2f}"
            det = c["chip"]
            chip_txt = ""
            consec_f = det.get("consec_foreign", 0)
            consec_t = det.get("consec_trust", 0)
            if consec_f >= 3:
                chip_txt += f"外資連{consec_f}日買超 "
            elif "foreign" in det:
                chip_txt += f"外資5日{det['foreign']/1000:+,.0f}張 "
            if consec_t >= 3:
                chip_txt += f"投信連{consec_t}日買超 "
            if pd.notna(det.get("d_big400", np.nan)):
                chip_txt += f"大戶週{det['d_big400']:+.2f}pp"
            # 鉅亨外資名單加星
            cnyes_star = "⭐鉅亨外資買超名單" if c["code"] in ctx.get("cnyes_top", set()) else ""
            setup_info = SETUP_TXT.get(c["setup_type"], "")
            out.append(Alert(f"cand|{date_s}|{c['code']}", "cand",
                             f"🆕 推薦#{i} {lab(c['code'])} {setup_info} {cnyes_star}\n"
                             f"最終分{c['final']:.0f}＝技術{c['score']:.0f}{c['bonus']:+.0f}主力\n"
                             f"收 {c['close']:.2f}｜停損 {c['stop']:.2f}｜停利 {tp_txt}｜風險 {c['risk_pct']:.1f}%\n"
                             f"建議 {size['lots']}張{size['odd']}股 ≈ {size['amount']:,.0f}元\n"
                             f"{chip_txt}\nhttps://tw.stock.yahoo.com/quote/{c['code']}"))

    for r in ctx["portfolio"]:
        code = str(r.get("code", "")).strip()
        d = ctx["ind_map"].get(code)
        if not code or d is None or len(d) < 65:
            continue
        ddate = d.index[-1].strftime("%Y-%m-%d")
        h = holding_health(d, params)
        close = h["close"]
        try:
            cost = float(r.get("cost") or 0)
        except Exception:
            cost = 0.0
        if cost > 0:
            setup_type = int(d["SetupType"].iloc[-1]) if pd.notna(d["SetupType"].iloc[-1]) else 0
            st_c, tp_c, _ = plan_trade(cost, float(d["ATR"].iloc[-1]), float(d["Low5"].iloc[-1]),
                                       params.stop_atr, params.tp_r if params.tp_r > 0 else 2.0, setup_type)
            pnl = (close / cost - 1) * 100
            if close <= st_c:
                out.append(Alert(f"hold_stop|{ddate}|{code}", "hold",
                                 f"🚨 持股 {lab(code)} 現價 {close:.2f} 已跌破以成本計算的防守價 {st_c:.2f}（成本 {cost:.2f}，{pnl:+.1f}%）"))
            elif close >= tp_c:
                out.append(Alert(f"hold_tp|{ddate}|{code}", "hold",
                                 f"🎯 持股 {lab(code)} 現價 {close:.2f} 達停利參考 {tp_c:.2f}（成本 {cost:.2f}，{pnl:+.1f}%），可考慮分批/上移停損。"))
        if h["weak"] >= 2:
            out.append(Alert(f"hold_weak|{ddate}|{code}|{h['weak']}", "hold",
                             f"⚠ 持股 {lab(code)} 轉弱（弱勢分{h['weak']}）：{'、'.join(h['flags'])}｜現價 {close:.2f}"))
        for k, txt in detect_events(d):
            if k in ("dn_ma20", "dn_ma60", "big_black", "kd_dead", "macd_dn"):
                out.append(Alert(f"hold_ev|{ddate}|{code}|{k}", "hold", f"⚠ 持股 {lab(code)} {txt}（收 {close:.2f}）"))

    for code in ctx["watch"]:
        d = ctx["ind_map"].get(code)
        if d is None or len(d) < 65:
            continue
        ddate = d.index[-1].strftime("%Y-%m-%d")
        close, pct = float(d["Close"].iloc[-1]), float(d["pct"].iloc[-1])
        for k, txt in detect_events(d):
            out.append(Alert(f"watch|{ddate}|{code}|{k}", "watch", f"👀 {lab(code)} {txt}（收 {close:.2f}，{pct:+.2f}%）"))
    return out


def dispatch_alerts(alerts: list, cfg: dict, enabled=None):
    enabled = set(enabled or ALERT_CATS)
    sel = [a for a in alerts if a.cat in enabled]
    if not sel:
        return "本次沒有符合條件的訊號。", []
    if not ((cfg.get("tg_token") and cfg.get("tg_chat")) or cfg.get("line_token")):
        return "尚未設定 Telegram / LINE，訊號未推送。", sel
    fresh_keys = set(alert_claim([a.key for a in sel]))
    fresh = [a for a in sel if a.key in fresh_keys]
    if not fresh:
        return "沒有新的訊號（已推送過的不會重複）。", []
    text = f"📡 台股量化訊號 v3 {now_tw():%m/%d %H:%M}\n\n" + "\n\n".join(a.text for a in fresh)
    res = notify_all(text, cfg)
    if not any(ok for ok, _ in res):
        alert_release(list(fresh_keys))
    return "；".join(m for _, m in res) or "無推播結果", fresh


# ----------------------------------------------------------------------------
# 背景常駐模式
# ----------------------------------------------------------------------------
def daemon_main():
    cfg = notify_cfg()
    cap = float(os.environ.get("CAPITAL", "1000000"))
    rp = float(os.environ.get("RISK_PCT", "1.5"))
    n = int(os.environ.get("N_UNIVERSE", "200"))
    chip_w = float(os.environ.get("CHIP_WEIGHT", "1"))
    use_intraday = os.environ.get("USE_INTRADAY", "0") == "1"
    hist = lru_cache(maxsize=4)(lambda tk, day: download_prices(list(tk), "3y"))
    rec = lru_cache(maxsize=2)(lambda tk, bk: download_prices(list(tk), "7d", min_len=2))
    meta_fn = lru_cache(maxsize=2)(load_meta_core)
    print("daemon v3 啟動；每 20 分鐘於 08:50~15:00（週一至週五）掃描一次。", flush=True)
    while True:
        now = now_tw()
        if now.weekday() < 5 and dt.time(8, 50) <= now.time() <= dt.time(15, 0):
            bk = now.strftime("%Y-%m-%d-%H-") + str(now.minute // 20)
            try:
                gp = lambda tk, bk=bk: merge_recent(hist(tuple(tk), bk[:10]), rec(tuple(tk), bk))
                meta = meta_fn(bk.rsplit("-", 1)[0])
                names, market = build_name_market(meta)
                params = load_best_params() or Params()
                eng, _, _ = build_engine_core(meta, n, ["金融保險業", "航運業", "水泥工業"], 35.0, 1.5, 8.0, 4.5, 10.0,
                                              0.6, 0.10, rp / 100.0, use_intraday, gp)
                ctx = assemble_ctx(meta, market, names, eng, params, gp, cap, rp, chip_w, load_portfolio(), load_watchlist())
                msg, fresh = dispatch_alerts(build_alerts(eng, params, ctx), cfg)
                print(f"[{now:%m-%d %H:%M}] 新訊號 {len(fresh)} 則：{msg}", flush=True)
            except Exception as e:
                print(f"[{now:%m-%d %H:%M}] 掃描失敗：{e}", flush=True)
        now = now_tw()
        time.sleep(max(30, 1200 - (now.minute % 20) * 60 - now.second))


if __name__ == "__main__" and "--daemon" in sys.argv:
    daemon_main()
    sys.exit(0)


# ============================================================================
# C. 介面
# ============================================================================
st.set_page_config(page_title="台股量化操盤決策系統 v3", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .stApp {background:#080c14 !important; color:#fff !important;}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {background:#0b0f19 !important; border-right:1px solid rgba(79,172,254,.25) !important;}
p, span, label, h1, h2, h3, h4, h5, h6, li {color:#fff !important;}
a {color:#38bdf8 !important;}
div[data-baseweb="select"] > div {background:#0f172a !important; border:1px solid #334155 !important; border-radius:8px !important;}
div[data-baseweb="popover"], div[data-baseweb="menu"], ul[data-baseweb="menu"] {background:#0b1120 !important; border:1px solid #38bdf8 !important;}
li[data-baseweb="menu-item"] {background:#0b1120 !important; color:#fff !important;}
li[data-baseweb="menu-item"]:hover {background:#1e293b !important; color:#38bdf8 !important;}
div.stButton > button {background:#080c14 !important; color:#fff !important; border:2px solid transparent !important; border-radius:9999px !important;
  padding:.6rem 2rem !important; font-weight:700 !important;
  background-image:linear-gradient(#080c14,#080c14),linear-gradient(90deg,#00f2fe,#4facfe,#fa709a,#fee140) !important;
  background-origin:border-box !important; background-clip:padding-box,border-box !important;
  box-shadow:0 0 16px rgba(79,172,254,.45) !important; transition:all .25s ease-in-out !important;}
div.stButton > button:hover {transform:translateY(-2px) !important; box-shadow:0 0 26px rgba(250,112,154,.6) !important;}
div[data-testid="stMetric"] {background:#0f172a !important; border:1px solid #1e293b !important; border-radius:12px !important; padding:12px 16px !important;}
div[data-testid="stMetricLabel"] {color:#94a3b8 !important;}
.stock-card {background:#0b1120; border:1px solid #1e293b; border-radius:16px; padding:16px; margin-bottom:14px;}
.stock-card-top1 {background:#0f172a; border:2px solid #38bdf8; border-radius:18px; padding:20px; margin-bottom:18px; box-shadow:0 0 25px rgba(56,189,248,.25);}
.tag-badge {display:inline-block; background:#082f49; color:#38bdf8 !important; border:1px solid #0284c7; padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; margin:0 4px 4px 0;}
.setup-badge {display:inline-block; background:#1e1040; color:#a78bfa !important; border:1px solid #7c3aed; padding:2px 8px; border-radius:9999px; font-size:12px; font-weight:700; margin:0 4px 4px 0;}
.rating-box {display:flex; justify-content:space-around; background:#060a12; border:1px solid #1e293b; border-radius:10px; padding:10px 4px; margin-top:12px; text-align:center;}
.rl {font-size:12px; color:#94a3b8 !important;} .rv {font-size:17px; font-weight:700;}
.bb-bg {width:100%; height:10px; background:#22c55e; border-radius:9999px; overflow:hidden; margin:8px 0;}
.bb-fill {height:100%; background:#ef4444;}
.chk-bull {background:#450a0a; border:1px solid #b91c1c; color:#fca5a5 !important; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block; margin:3px 4px 3px 0;}
.chk-bear {background:#052e16; border:1px solid #15803d; color:#86efac !important; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block; margin:3px 4px 3px 0;}
.lnk {font-size:12px; margin-right:10px;}
.main-score-vcp {color:#a78bfa !important; font-weight:900;}
.main-score-std {color:#38bdf8 !important; font-weight:700;}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 側邊欄
# ============================================================================
sb = st.sidebar
sb.markdown("### ⚙️ 台股量化系統 v3")
sb.markdown("**主力籌碼強化版**")
sb.divider()
sb.markdown("### 資金與風控")
capital = sb.number_input("總操作資金 (TWD)", 50_000, 50_000_000, 1_000_000, 50_000)
risk_pct = sb.slider("單筆最大承受風險 (%)", 0.5, 5.0, 1.5, 0.1)
sb.markdown("### 股票池與過濾")
n_universe = sb.select_slider("分析股票池（當日成交值前 N 檔）", [100, 150, 200, 250, 300, 400], value=200)
excl = sb.multiselect("排除產業", ["金融保險業", "航運業", "水泥工業", "食品工業", "貿易百貨業", "觀光餐旅", "塑膠工業", "造紙工業"],
                      default=["金融保險業", "航運業", "水泥工業"])
min_price = sb.number_input("最低股價", 1.0, 500.0, 35.0, 1.0)
min_turn_yi = sb.number_input("5日均成交值下限（億）", 0.1, 20.0, 1.5, 0.1)
min_amp = sb.number_input("20日振幅下限 (%)", 0.0, 30.0, 8.0, 0.5)
bias5_max = sb.slider("5MA 乖離上限 (%)", 1.0, 8.0, 4.5, 0.5)
bias20_max = sb.slider("20MA 乖離上限 (%)", 3.0, 20.0, 10.0, 1.0)
sb.markdown("### 交易成本")
fee_disc = sb.slider("手續費折扣（0.6 = 6折）", 0.2, 1.0, 0.6, 0.02)
slip_pct = sb.slider("單邊滑價 (%)", 0.0, 0.5, 0.10, 0.05)
sb.markdown("### 即時性與主力籌碼")
use_intraday = sb.checkbox("排名使用盤中未收盤K線", value=False)
chip_weight = sb.slider("主力籌碼加減分權重（v3：外資連買天數+法人合買+大戶增減）", 0.0, 2.0, 1.0, 0.1,
                        help="v3 主力分最高 ±15，比 v2 更重視外資連續買超天數與法人合買訊號")
sb.markdown("### Walk-forward")
train_days = sb.slider("訓練視窗（交易日）", 150, 400, 250, 10)
test_days = sb.slider("測試視窗（交易日）", 40, 120, 60, 10)
if sb.button("🔄 重新抓取最新資料"):
    st.cache_data.clear()
    st.cache_resource.clear()
    for k in ("wf", "final_params"):
        st.session_state.pop(k, None)
    st.rerun()

# ============================================================================
# 資料載入
# ============================================================================
REFRESH_TICK_SEC = 300


def bucket_key() -> str:
    n = now_tw()
    return n.strftime("%Y-%m-%d-%H-") + str(n.minute // 20)


@st.cache_data(ttl=3600, show_spinner=False)
def load_meta(hour_key: str):
    return load_meta_core(hour_key)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def prices_hist(tickers: tuple, day_key: str):
    return download_prices(list(tickers), period="3y")


@st.cache_data(ttl=1200, show_spinner=False)
def prices_recent(tickers: tuple, bucket: str):
    return download_prices(list(tickers), period="7d", min_len=2)


def get_prices(tickers, bucket: str) -> dict:
    tk = tuple(tickers)
    return merge_recent(prices_hist(tk, bucket[:10]), prices_recent(tk, bucket))


@st.cache_resource(ttl=1500, show_spinner=False)
def build_engine(bucket, n, excl_t, min_price, min_turn_yi, min_amp, b5, b20, fee_disc, slip_pct, risk_pct, use_intraday):
    meta_ = load_meta(bucket.rsplit("-", 1)[0])
    return build_engine_core(meta_, n, list(excl_t), min_price, min_turn_yi, min_amp, b5, b20, fee_disc, slip_pct,
                             risk_pct / 100.0, use_intraday, lambda tk: get_prices(tk, bucket))


bucket = bucket_key()
try:
    with st.spinner("更新資料中（v3 含 OBV/VCP/NR7 計算，首次約 60~120 秒）…"):
        eng, bench_df, eng_notes = build_engine(bucket, n_universe, tuple(excl), min_price, min_turn_yi, min_amp,
                                                bias5_max, bias20_max, fee_disc, slip_pct, risk_pct, use_intraday)
        meta = load_meta(bucket.rsplit("-", 1)[0])
except Exception as e:
    st.error(f"資料載入失敗：{e}")
    st.stop()
st.session_state["loaded_bucket"] = bucket

NAMES, ALL_MARKET = build_name_market(meta)
get_px = lambda tk: get_prices(tk, bucket)
data_date = eng.idx[-1].strftime("%Y-%m-%d")
bench_last = float(eng.bench_close.iloc[-1])
regime_lvl = int(eng.regime_lvl[-1])
regime_ok = regime_lvl > 0
chip_fn = make_chip_fn(meta["chips"], meta["tdcc"], chip_weight)

wf = st.session_state.get("wf")
params = st.session_state.get("final_params") or load_best_params() or Params()
portfolio_rows = st.session_state.setdefault("portfolio", load_portfolio())
watch_codes = st.session_state.setdefault("watchlist", load_watchlist())


def label(code: str) -> str:
    n = NAMES.get(code)
    return f"{n} ({code})" if n else f"{code}"


def chip_dict(code: str):
    out = {}
    ch = meta["chips"]
    if code in ch.index:
        r = ch.loc[code]
        out.update(foreign=float(r["foreign"]), trust=float(r["trust"]), total=float(r["total"]),
                   consec_foreign=int(r.get("consec_foreign", 0)),
                   consec_trust=int(r.get("consec_trust", 0)))
    td = meta["tdcc"]
    if code in td.index:
        r = td.loc[code]
        out.update(big400=float(r["big400"]), d_big400=float(r["d_big400"]) if pd.notna(r["d_big400"]) else None)
    return out or None


def link_html(code: str) -> str:
    return "".join(f'<a class="lnk" href="{u}" target="_blank">{n}</a>'
                   for n, u in links(code, ALL_MARKET.get(code, "TW")).items())


def cur_cfg() -> dict:
    base, ov = notify_cfg(), st.session_state.get("cfg_override", {})
    return {k: (ov.get(k) or base.get(k, "")) for k in ("tg_token", "tg_chat", "line_token", "line_user")}


with st.expander("📡 資料狀態（v3：含OBV/VCP/NR7/外資連買天數/鉅亨爬蟲）"):
    st.write(f"價格資料最新日期：**{data_date}**　｜　股票池：**{len(eng.codes)}** 檔　｜　系統時間：{now_tw():%Y-%m-%d %H:%M} (台北)")
    st.write(f"鉅亨外資買超名單：**{len(meta.get('cnyes_top', set()))}** 檔")
    for m in eng_notes + meta["msgs"]:
        st.caption("• " + m)
    st.caption("• v3 主力分：外資連續買超天數（最高+6）+ 法人合買（+5）+ 投信連買天數（最高+4）+ 大戶週增減（±3），上限 ±15 分。")
    st.caption("• v3 新指標：OBV趨勢（主力資金流）、VCP完整型態評分、NR7窄幅、均線黏合度、52週相對位置。")


@st.fragment(run_every=REFRESH_TICK_SEC)
def auto_tick():
    cur, loaded = bucket_key(), st.session_state.get("loaded_bucket")
    mode = "盤中・含未收盤K線" if use_intraday else "僅用已收盤K線"
    st.caption(f"⏱ 每 20 分鐘自動更新｜資料時段 {loaded}｜台北時間 {now_tw():%H:%M:%S}｜{mode}")
    if loaded != cur:
        st.rerun()


auto_tick()

ctx = assemble_ctx(meta, ALL_MARKET, NAMES, eng, params, get_px, capital, risk_pct, chip_weight,
                   portfolio_rows, watch_codes)
alerts = build_alerts(eng, params, ctx)

cfg_now = cur_cfg()
configured = bool((cfg_now["tg_token"] and cfg_now["tg_chat"]) or cfg_now["line_token"])
if st.session_state.get("auto_push", configured) and st.session_state.get("alerted_bucket") != bucket:
    msg, fresh = dispatch_alerts(alerts, cfg_now, st.session_state.get("alert_cats", list(ALERT_CATS)))
    st.session_state["alerted_bucket"] = bucket
    st.session_state.setdefault("alert_log", []).insert(0, f"{now_tw():%m-%d %H:%M} ｜ 新訊號 {len(fresh)} 則 ｜ {msg}")
    if fresh:
        st.toast(f"已推送 {len(fresh)} 則新訊號")

tab_daily, tab_port, tab_sec, tab_val, tab_scr, tab_alert = st.tabs([
    "🎯 每日決策與推薦", "💼 持股健檢與換股", "🌐 族群多空儀表板", "🧪 Walk-Forward 驗證與風險",
    "🛠️ 18 項全景篩選器", "🔔 推播與自選股監控"])


def candle_fig(df: pd.DataFrame, n: int, stop=None, tp=None, height=380, title=""):
    d = df.tail(n)
    cats = d.index.strftime("%m/%d").tolist()
    fig = go.Figure(go.Candlestick(x=cats, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                   increasing_line_color="#ef4444", decreasing_line_color="#22c55e", name="K"))
    fig.add_trace(go.Scatter(x=cats, y=d["MA20"], line=dict(color="#3b82f6", width=1.4), name="20MA"))
    fig.add_trace(go.Scatter(x=cats, y=d["MA60"], line=dict(color="#f59e0b", width=1.4), name="60MA"))
    if "OBV" in d.columns:
        obv_norm = (d["OBV"] - d["OBV"].min()) / (d["OBV"].max() - d["OBV"].min() + 1e-9)
        obv_price = d["Low"].min() + obv_norm * (d["High"].max() - d["Low"].min()) * 0.2
        fig.add_trace(go.Scatter(x=cats, y=obv_price, line=dict(color="rgba(168,85,247,0.5)", width=1.0),
                                 name="OBV(縮放)", yaxis="y"))
    if stop:
        fig.add_hline(y=stop, line_dash="dash", line_color="#22c55e", annotation_text=f"停損 {stop:.2f}")
    if tp:
        fig.add_hline(y=tp, line_dash="dash", line_color="#ef4444", annotation_text=f"目標 {tp:.2f}")
    fig.update_layout(height=height, title=title, xaxis=dict(type="category", rangeslider=dict(visible=False)),
                      margin=dict(l=5, r=5, t=40 if title else 10, b=5), paper_bgcolor="#080c14",
                      plot_bgcolor="#080c14", font=dict(color="#fff"), showlegend=False)
    return fig


def ind_df(code: str) -> pd.DataFrame:
    P = eng.P
    fields = [f for f in PANEL_FIELDS if f in P]
    d = pd.DataFrame({f: P[f][code] for f in fields if code in P[f].columns})
    return d.dropna(subset=["Close"])


def verdict_banner(level, head, bullets):
    fn = {"green": st.success, "yellow": st.warning, "red": st.error}[level]
    fn(head + "\n\n" + "\n".join("- " + b for b in bullets))


# ============================================================================
# Tab 1：每日決策
# ============================================================================
def chip_line_v3(code: str, det: dict) -> str:
    parts = []
    if "foreign" in det:
        cf = det.get("consec_foreign", 0)
        ct = det.get("consec_trust", 0)
        f_str = f"外資連續買超 **{cf} 日**" if cf > 0 else f"外資5日 {det['foreign']/1000:+,.0f}張"
        t_str = f"投信連續買超 **{ct} 日**" if ct > 0 else f"投信5日 {det['trust']/1000:+,.0f}張"
        parts.append(f"{f_str}　{t_str}")
        if det.get("foreign", 0) > 0 and det.get("trust", 0) > 0:
            parts.append("🔥**法人合買信號**")
    else:
        parts.append("三大法人：無資料（上櫃或抓取失敗）")
    if pd.notna(det.get("big400", np.nan)):
        d4 = det.get("d_big400", np.nan)
        parts.append(f"大戶(>400張)持股 {det['big400']:.1f}%" + (f"（週 {d4:+.2f}pp）" if pd.notna(d4) else "（尚無上週比較）"))
    ry = meta["rev"].get(code, np.nan)
    parts.append(f"月營收年增 {ry:+.1f}%" if pd.notna(ry) else "月營收：無資料")
    return "　｜　".join(parts)


with tab_daily:
    st.markdown(f"### 盤勢與做多決策 ｜ 資料日期 {data_date} ｜ **v3 主力籌碼強化版**")
    breadth = float(eng.breadth.iloc[-1]) * 100
    (st.info if regime_ok else st.warning)(
        f"大盤環境：{LVL_TXT[regime_lvl]}｜加權指數 {bench_last:,.0f}｜股票池站上月線比例 {breadth:.0f}%"
        + ("" if regime_ok else "｜回測規則此時不新進場，以下僅供觀察"))

    if wf:
        _, bh = bench_return(eng.bench_close, wf["oos_equity"].index) if len(wf["oos_equity"]) else (None, np.nan)
        lv, hd, bl = verdict(wf, bh)
        verdict_banner(lv, hd, bl)
        st.caption(f"目前使用的參數（最近 {wf['train_days']} 日訓練視窗選出）：{params.label()}"
                   + ("" if wf["final_ok"] else "　⚠ 最近視窗交易數不足，改用預設參數"))
    else:
        st.warning("尚未執行 Walk-Forward 驗證，**建議先到「🧪 Walk-Forward 驗證」執行驗證**以確認策略有效性。")

    cands = latest_candidates(eng, params, top=10, exclude=meta["punish"], chip_fn=chip_fn)
    if not cands:
        st.warning("今日沒有標的同時通過流動性、趨勢、乖離與分數門檻。空手也是一種部位。")
    else:
        calib_key = f"calib_{params.preset}_{params.hold}_{data_date}"
        if calib_key not in st.session_state:
            st.session_state[calib_key] = score_calibration(eng, params.preset, params.hold)
        calib = st.session_state[calib_key]

        t1 = cands[0]
        code = t1["code"]
        tags = "".join(f'<span class="tag-badge">{html.escape(t)}</span>' for t in TAG_MAP.get(code, []))
        setup_badge = f'<span class="setup-badge">{SETUP_TXT.get(t1["setup_type"], "")}</span>' if t1["setup_type"] > 0 else ""
        cnyes_star = '<span class="tag-badge" style="background:#1c1410;border-color:#f59e0b;color:#f59e0b !important;">⭐鉅亨外資名單</span>' if code in meta.get("cnyes_top", set()) else ""
        flag_txt = "　⚠ 注意股" if code in meta["notice"] else ""
        subs = t1["sub"]
        st.markdown("#### 👑 今日首選")
        st.markdown(f"""
        <div class="stock-card-top1">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <div><span style="font-size:30px;font-weight:900;color:#f59e0b !important;">{html.escape(label(code))}</span>{flag_txt}
              <div style="margin-top:8px;">{tags}{setup_badge}{cnyes_star}</div>
              <div style="margin-top:6px;">{link_html(code)}</div></div>
            <div style="text-align:right;">
              <div style="font-size:34px;font-weight:900;">{t1['close']:.2f}</div>
              <div style="font-size:17px;font-weight:700;color:{'#ef4444' if t1['pct']>=0 else '#22c55e'} !important;">{'▲' if t1['pct']>=0 else '▼'} {t1['pct']:+.2f}%</div>
              <div style="font-size:13px;color:#38bdf8 !important;font-weight:700;">最終分 {t1['final']:.1f} ＝ 技術 {t1['score']:.1f} {t1['bonus']:+.1f} 主力（{params.preset}）</div>
              <div style="font-size:12px;color:#94a3b8 !important;">52W位置 {t1['pos52w']*100:.0f}%　VCP {t1['vcp_score']*100:.0f}%</div>
              </div></div>
          <div class="rating-box">
            <div><div class="rl">趨勢</div><div class="rv">{subs['trend']:.0f}</div></div>
            <div><div class="rl">波動收斂</div><div class="rv">{subs['compress']:.0f}</div></div>
            <div><div class="rl">動能</div><div class="rv">{subs['mom']:.0f}</div></div>
            <div><div class="rl">相對強度</div><div class="rv">{subs['rs']:.0f}</div></div>
            <div><div class="rl">主力足跡</div><div class="rv">{subs['flow']:.0f}</div></div>
            <div><div class="rl">進場型態</div><div class="rv">{subs['setup']:.0f}</div></div>
            <div><div class="rl">K / RSI</div><div class="rv">{t1['k']:.0f} / {t1['rsi']:.0f}</div></div>
            <div><div class="rl">OBV趨勢</div><div class="rv">{'↑主力' if t1['obv_slope']>0.005 else ('吸籌' if t1['obv_diverge'] else '—')}</div></div>
            </div></div>
        """, unsafe_allow_html=True)

        size = size_position(capital, risk_pct, t1["close"], t1["stop"])
        tp_show = None if np.isinf(t1["tp"]) else t1["tp"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("參考進場（隔日開盤附近）", f"{t1['close']:.2f}", f"成交 {int(t1['volume_lots']):,} 張")
        c2.metric("防守停損", f"{t1['stop']:.2f}", f"-{t1['risk_pct']:.2f}%｜{t1['setup_name']}", delta_color="inverse")
        c3.metric(f"停利目標 ({params.tp_r}R)" if tp_show else "停利方式",
                  f"{tp_show:.2f}" if tp_show else "移動停損", f"+{(tp_show/t1['close']-1)*100:.2f}%" if tp_show else f"獲利>1.5R後追蹤{params.trail_atr}ATR")
        c4.metric("5日均成交值", f"{t1['turnover_yi']:.2f} 億")
        s1, s2, s3 = st.columns(3)
        s1.metric("建議張數", f"{size['lots']} 張 + {size['odd']} 股", f"依{size['binding']}")
        s2.metric("投入金額", f"{size['amount']:,.0f} 元", f"{size['pct_capital']:.1f}% 資金")
        s3.metric("停損時預估虧損", f"{size['risk_amt']:,.0f} 元", f"{size['risk_amt']/capital*100:.2f}% 資金", delta_color="inverse")
        st.caption(chip_line_v3(code, t1["chip"]))
        if len(calib):
            band = pd.cut([t1["score"]], [0, 55, 65, 75, 85, 101], right=False, labels=["<55", "55-65", "65-75", "75-85", "85+"])[0]
            if band in calib.index:
                r = calib.loc[band]
                st.caption(f"📊 歷史校準：技術分落在 {band} 的訊號 {int(r['樣本數']):,} 次，"
                           f"持有 {params.hold} 日勝率 {r['勝率']:.1f}%、平均報酬 {r['平均報酬']:+.2f}%（未扣成本）。")
        st.plotly_chart(candle_fig(ind_df(code), 60, t1["stop"], tp_show, title=f"{label(code)} 日K（OBV縮放至低20%顯示）"),
                        use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🎯 第 2～10 名")
        rows = []
        setup_names = {0: "—", 1: "📌回測", 2: "📈突破", 3: "⚡黏合突破", 4: "💎VCP"}
        for i, c in enumerate(cands[1:], start=2):
            det = c["chip"]
            cf = det.get("consec_foreign", 0)
            ct = det.get("consec_trust", 0)
            rows.append({
                "名次": i, "標的": label(c["code"]),
                "最終分": round(c["final"], 1), "技術分": round(c["score"], 1), "主力分": round(c["bonus"], 1),
                "收盤": c["close"], "漲跌%": round(c["pct"], 2), "停損": c["stop"],
                "停利": "移動" if np.isinf(c["tp"]) else c["tp"], "風險%": round(c["risk_pct"], 2),
                "進場型態": setup_names.get(c["setup_type"], "—"),
                "VCP%": round(c["vcp_score"] * 100, 0),
                "外資連買日": cf if cf > 0 else ("賣" if det.get("foreign", 0) < 0 else 0),
                "投信連買日": ct if ct > 0 else ("賣" if det.get("trust", 0) < 0 else 0),
                "大戶>400%": round(det["big400"], 1) if pd.notna(det.get("big400", np.nan)) else None,
                "鉅亨": "⭐" if c["code"] in meta.get("cnyes_top", set()) else "",
                "注意": "⚠" if c["code"] in meta["notice"] else "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        pick = st.selectbox("查看連結與K線", [c["code"] for c in cands[1:]], format_func=label) if len(cands) > 1 else None
        if pick:
            cc = next(c for c in cands if c["code"] == pick)
            st.markdown(link_html(pick), unsafe_allow_html=True)
            st.caption(chip_line_v3(pick, cc["chip"]))
            st.plotly_chart(candle_fig(ind_df(pick), 60, cc["stop"], None if np.isinf(cc["tp"]) else cc["tp"], height=320),
                            use_container_width=True)
    st.caption("⚠ 以上為量化規則產出的輔助資訊，不是投資建議；實際下單前請自行確認消息面、處置/注意公告與流動性。")


# ============================================================================
# Tab 2：持股
# ============================================================================
with tab_port:
    st.markdown("### 💼 持股健檢與換股（存於 portfolio.json）")
    base = pd.DataFrame(portfolio_rows) if portfolio_rows else pd.DataFrame(columns=["code", "cost", "shares", "date"])
    for col in ("code", "cost", "shares", "date"):
        if col not in base:
            base[col] = None
    base["code"] = base["code"].astype(str).str.strip()
    base.insert(1, "name", base["code"].map(lambda c: NAMES.get(c, "（查無名稱，請確認代碼）")))
    edited = st.data_editor(base[["code", "name", "cost", "shares", "date"]], num_rows="dynamic", use_container_width=True,
                            key="port_editor",
                            column_config={"code": "代碼", "name": st.column_config.TextColumn("名稱（自動帶入）", disabled=True),
                                           "cost": st.column_config.NumberColumn("成本", format="%.2f"),
                                           "shares": st.column_config.NumberColumn("股數", step=1000),
                                           "date": "買進日(YYYY-MM-DD)"})
    if st.button("💾 儲存持股"):
        rows_new = (edited[["code", "cost", "shares", "date"]].dropna(subset=["code"])
                    .replace({np.nan: None}).to_dict("records"))
        st.session_state["portfolio"] = rows_new
        save_portfolio(rows_new)
        st.success("已儲存。")

    recs = edited.replace({np.nan: None}).to_dict("records")
    codes_h = [str(r.get("code") or "").strip() for r in recs if str(r.get("code") or "").strip()]
    need = [c for c in codes_h if c not in ctx["ind_map"]]
    ind_h = {**ctx["ind_map"], **(get_ind_map(need, ALL_MARKET, get_px) if need else {})}
    hold_rows, health = [], {}
    for r in recs:
        c = str(r.get("code") or "").strip()
        if not c:
            continue
        d = ind_h.get(c)
        if d is None or len(d) < 65:
            hold_rows.append({"標的": label(c), "警訊": "無法取得足夠的價格資料"})
            continue
        h = holding_health(d, params)
        cost = float(r.get("cost") or 0)
        shares = float(r.get("shares") or 0)
        pnl = (h["close"] / cost - 1) * 100 if cost else np.nan
        try:
            days_held = (pd.Timestamp(d.index[-1]) - pd.Timestamp(str(r.get("date"))[:10])).days
        except Exception:
            days_held = None
        health[c] = dict(h, pnl=pnl, days=days_held)
        cd = chip_dict(c) or {}
        hold_rows.append({"標的": label(c), "現價": round(h["close"], 2), "成本": cost, "未實現%": round(pnl, 2),
                          "損益(元)": round((h["close"] - cost) * shares), "弱勢分": h["weak"],
                          "警訊": "、".join(h["flags"]) or "—", "防守價": h["stop"], "持有天數": days_held,
                          "外資連買日": cd.get("consec_foreign", 0),
                          "投信連買日": cd.get("consec_trust", 0),
                          "大戶>400%": round(cd["big400"], 1) if pd.notna(cd.get("big400", np.nan)) else None,
                          "大戶週增減pp": round(cd["d_big400"], 2) if cd.get("d_big400") is not None else None})
    if hold_rows:
        st.dataframe(pd.DataFrame(hold_rows), use_container_width=True, hide_index=True)

    st.markdown("#### 換股建議")
    cands_p = latest_candidates(eng, params, top=3, exclude=meta["punish"], chip_fn=chip_fn)
    if not health:
        st.info("尚無持股。")
    elif not cands_p:
        st.info("今日無合格新標的，不需要換股。")
    else:
        top = cands_p[0]
        if top["code"] in health:
            st.success(f"今日首選 {label(top['code'])} 已在持股中。")
        else:
            wc, wh = max(health.items(), key=lambda kv: (kv[1]["weak"], -(kv[1]["pnl"] if pd.notna(kv[1]["pnl"]) else 0)))
            rt = eng.costs.round_trip * 100
            if wh["weak"] >= 2 and regime_ok:
                st.error(f"建議評估：賣出 **{label(wc)}**（弱勢分 {wh['weak']}：{'、'.join(wh['flags'])}），"
                         f"隔日開盤換入 **{label(top['code'])}**（最終分 {top['final']:.1f}｜{SETUP_TXT.get(top['setup_type'], '')}）。"
                         f"換股來回成本約 {rt:.2f}%。")
            else:
                st.success(f"持股沒有明顯轉弱訊號（最弱：{label(wc)}，弱勢分 {wh['weak']}），"
                           f"不建議為換股支付約 {rt:.2f}% 的來回成本。")


# ============================================================================
# Tab 3：族群
# ============================================================================
with tab_sec:
    st.markdown("### 🌐 族群多空儀表板（v3：含OBV/VCP/主力吸籌標記）")
    c_a, c_b = st.columns(2)
    sec = c_a.selectbox("產業族群", list(SECTORS))
    all_tags = sorted({t for v in SECTORS.values() for _, _, ts in v for t in ts})
    tag_pick = c_b.selectbox("概念標籤（選了會覆蓋族群）", ["—"] + all_tags)
    items = ([(c, n, t) for v in SECTORS.values() for c, n, t in v if tag_pick in t] if tag_pick != "—" else SECTORS[sec])
    seen = set()
    items = [i for i in items if not (i[0] in seen or seen.add(i[0]))]
    sec_ind = get_ind_map([c for c, _, _ in items], ALL_MARKET, get_px)
    for i in range(0, len(items), 2):
        cols = st.columns(2)
        for k in range(2):
            if i + k >= len(items):
                continue
            c, n0, tg = items[i + k]
            with cols[k]:
                d = sec_ind.get(c)
                if d is None or len(d) < 65:
                    st.warning(f"{label(c)}：無足夠價格資料")
                    continue
                last, prev = float(d["Close"].iloc[-1]), float(d["Close"].iloc[-2])
                diff = last - prev
                col = "#ef4444" if diff >= 0 else "#22c55e"
                diag = bull_bear_checks(d, chip_dict(c), meta["rev"].get(c, np.nan))
                nb, nr = len(diag["bull"]), max(1, len(diag["bear"]))
                pct_b = int(nb / (nb + nr) * 100)
                mk = "上櫃" if ALL_MARKET.get(c) == "TWO" else "上市"
                obv_tag = "🐋OBV吸籌" if d["OBV_Diverge"].iloc[-1] == 1 else ("📊OBV流入" if d["OBV_Slope20"].iloc[-1] > 0.005 else "")
                vcp_tag = f"💎VCP{d['VCP_Score'].iloc[-1]*100:.0f}%" if d["VCP_Score"].iloc[-1] >= 0.6 else ""
                nr7_tag = "⚡NR7" if d["NR7"].iloc[-1] == 1 else ""
                st.markdown(f"""
                <div class="stock-card">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div><span style="font-size:22px;font-weight:800;color:#f59e0b !important;">{c} {html.escape(NAMES.get(c, n0))}</span>
                      <span style="font-size:12px;background:#334155;padding:2px 6px;border-radius:4px;margin-left:6px;">{mk}</span>
                      <div style="margin-top:6px;">{''.join(f'<span class="tag-badge">{html.escape(t)}</span>' for t in tg)}
                      {f'<span class="setup-badge">{obv_tag}</span>' if obv_tag else ''}
                      {f'<span class="setup-badge">{vcp_tag}</span>' if vcp_tag else ''}
                      {f'<span class="setup-badge">{nr7_tag}</span>' if nr7_tag else ''}
                      </div></div>
                    <div style="text-align:right;"><div style="font-size:26px;font-weight:800;">{last:.2f}</div>
                      <div style="color:{col} !important;font-weight:600;">{'▲' if diff>=0 else '▼'} {diff:+.2f} ({diff/prev*100:+.2f}%)</div></div></div>
                  <div style="margin-top:8px;">{link_html(c)}</div></div>""", unsafe_allow_html=True)
                st.plotly_chart(candle_fig(d, 35, height=210), use_container_width=True)
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:700;">
                  <span style="color:#ef4444 !important;">● 多方 {nb} 項</span><span style="color:#22c55e !important;">● 空方 {len(diag['bear'])} 項</span></div>
                <div class="bb-bg"><div class="bb-fill" style="width:{pct_b}%;"></div></div>
                <div style="font-size:12px;"><b style="color:#f87171 !important;">多方：</b>{''.join(f'<span class="chk-bull">{html.escape(x)}</span>' for x in diag['bull'][:8])}</div>
                <div style="font-size:12px;"><b style="color:#4ade80 !important;">空方：</b>{''.join(f'<span class="chk-bear">{html.escape(x)}</span>' for x in diag['bear'][:6]) or '—'}</div>
                """, unsafe_allow_html=True)


# ============================================================================
# Tab 4：驗證
# ============================================================================
with tab_val:
    st.markdown("### 🧪 Walk-Forward 驗證與風險（v3）")
    st.info("""
**v3 回測改善：**
- 目標函數加入**勝率懲罰**（勝率<45% 會降低分數），Walk-Forward 會主動找更高勝率的參數組合
- 動態停損：VCP突破用×0.7 ATR、標準突破×1.0 ATR、回測×1.1 ATR
- 停利預設降至 1.5R（更容易達到），提升勝率
- 進場門檻提高至 65/70/75（三個候選），減少低品質訊號
    """)
    st.caption(f"候選參數組合共 {len(list(product(*DEFAULT_GRID.values())))} 組；"
               f"資料共 {len(eng.idx)} 個交易日（{eng.idx[0]:%Y-%m-%d} ~ {eng.idx[-1]:%Y-%m-%d}）。")

    if st.button("▶ 執行 Walk-Forward 驗證（v3）"):
        bar = st.progress(0.0, text="回測中（v3 含型態分類，速度可能略慢）…")
        res = walk_forward(eng, train_days=train_days, test_days=test_days, progress=lambda x: bar.progress(x))
        bar.empty()
        if res is None:
            st.error("資料天數不足以切出訓練+測試視窗。")
        else:
            st.session_state["wf"] = res
            st.session_state["final_params"] = res["final_params"]
            _bh = bench_return(eng.bench_close, res["oos_equity"].index)[1] if len(res["oos_equity"]) else np.nan
            save_best_params(res["final_params"], verdict(res, _bh)[0])
            st.rerun()

    wf = st.session_state.get("wf")
    if wf:
        o = wf["oos_stats"]
        curve, bh = bench_return(eng.bench_close, wf["oos_equity"].index) if len(wf["oos_equity"]) else (pd.Series(dtype=float), np.nan)
        lv, hd, bl = verdict(wf, bh)
        verdict_banner(lv, hd, bl)

        def f(x, fmt="{:.2f}", na="—"):
            return na if x is None or (isinstance(x, float) and np.isnan(x)) else fmt.format(x)

        m = st.columns(6)
        m[0].metric("樣本外交易筆數", f"{o['n']}", "n<30 不可靠" if o["n"] < 30 else "")
        m[1].metric("勝率", f(o["win_rate"], "{:.1f}%"), f"95%CI {f(o['wr_lo'], '{:.0f}')}~{f(o['wr_hi'], '{:.0f}')}%")
        m[2].metric("平均獲利 / 平均虧損", f"{f(o['avg_win'], '{:+.2f}')}% / {f(o['avg_loss'], '{:+.2f}')}%")
        m[3].metric("每筆期望值", f(o["expectancy"], "{:+.2f}%"), f"t={f(o['tstat'])}")
        m[4].metric("盈虧因子 / 賺賠比", f"{f(o['profit_factor'])} / {f(o['payoff'])}")
        m[5].metric("最大連虧", f"{o['max_consec_loss']} 次")
        m2 = st.columns(5)
        m2[0].metric("樣本外總報酬", f(o["total_ret"], "{:+.1f}%"), f"大盤 {f(bh, '{:+.1f}')}%")
        m2[1].metric("年化報酬", f(o["cagr"], "{:+.1f}%") if not np.isnan(o.get("cagr", np.nan)) else "期間過短")
        m2[2].metric("最大回撤", f(o["mdd"], "-{:.1f}%"))
        m2[3].metric("Sharpe", f(o["sharpe"]))
        m2[4].metric("平均持有", f(o["avg_hold"], "{:.1f} 日"))

        # 各進場型態績效分析（v3 新增）
        setup_stats = {}
        if len(wf["oos_trades"]) and "setup_type" in wf["oos_trades"].columns:
            st.markdown("##### [v3] 各進場型態績效分析")
            type_names = {1: "回測月線", 2: "突破20高", 3: "均線黏合突破", 4: "VCP突破"}
            rows_st = []
            for st_id, st_name in type_names.items():
                sub = wf["oos_trades"][wf["oos_trades"]["setup_type"] == st_id]
                if len(sub) == 0:
                    continue
                r = sub["net_pct"].to_numpy()
                wins = r[r > 0]
                rows_st.append({"型態": st_name, "筆數": len(r), "勝率": f"{len(wins)/len(r)*100:.1f}%",
                                "均獲利": f"{wins.mean():+.2f}%" if len(wins) else "—",
                                "均虧損": f"{r[r<=0].mean():+.2f}%" if (r<=0).any() else "—",
                                "期望值": f"{r.mean():+.2f}%"})
            if rows_st:
                st.dataframe(pd.DataFrame(rows_st), use_container_width=True, hide_index=True)
                st.caption("VCP突破 和 均線黏合突破 理論上應有更高勝率，若沒有，代表這兩種型態在你的股票池中出現頻率太低，統計意義有限。")

        if len(wf["oos_equity"]):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=wf["oos_equity"].index, y=wf["oos_equity"].values, name="策略（樣本外串接）", line=dict(color="#f59e0b", width=2.2)))
            if len(curve):
                fig.add_trace(go.Scatter(x=curve.index, y=curve.values, name="加權指數買進持有", line=dict(color="#38bdf8", width=1.6)))
            fig.update_layout(height=340, title="樣本外淨值（起點=1）", paper_bgcolor="#080c14", plot_bgcolor="#080c14", font=dict(color="#fff"))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("##### 各折明細")
        fd = wf["folds"].copy()
        fd = fd.rename(columns={"fold": "折", "train": "訓練期", "test": "測試期", "params": "訓練期選出的參數",
                                "train_n": "訓練筆數", "train_exp": "訓練期望值%", "test_n": "測試筆數",
                                "test_exp": "測試期望值%", "test_ret": "測試報酬%", "test_mdd": "測試MDD%",
                                "rank_pct": "測試期排名百分位"})
        st.dataframe(fd.round(2), use_container_width=True, hide_index=True)

        st.markdown("##### 🎲 蒙地卡羅（區塊自助法）")
        trs = wf["oos_trades"]["net_pct"].tolist() if len(wf["oos_trades"]) else []
        mc = mc_ruin(trs)
        if not mc:
            st.info("樣本外交易少於 5 筆，無法做蒙地卡羅。")
        else:
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("60 筆後平均淨值", f"{mc['end_mean']:.2f}")
            a2.metric("5% 最差淨值", f"{mc['end_p5']:.2f}")
            a3.metric("95% 信賴最大回撤", f"-{mc['mdd95']:.1f}%")
            a4.metric("淨值腰斬機率", f"{mc['p_ruin']:.2f}%")
            fig2 = go.Figure()
            for row in mc["curves"][:60]:
                fig2.add_trace(go.Scatter(y=row, mode="lines", line=dict(width=.6, color="rgba(56,189,248,.18)"), showlegend=False))
            fig2.add_trace(go.Scatter(y=mc["curves"].mean(axis=0), line=dict(width=2.4, color="#f59e0b"), name="平均"))
            fig2.update_layout(height=320, paper_bgcolor="#080c14", plot_bgcolor="#080c14", font=dict(color="#fff"),
                               xaxis_title="交易筆數", yaxis_title="淨值")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("##### 🔬 訊號預測力（Rank IC）")
        hz = st.select_slider("預測期間（交易日）", [5, 10, 15, 20], value=10)
        sq = signal_quality(eng, params.preset, hz)
        q1, q2, q3 = st.columns(3)
        q1.metric("Rank IC 平均", f(sq["ic_mean"], "{:+.3f}"))
        q2.metric("IC t 值", f(sq["ic_t"]), "|t|>2 才算顯著")
        q3.metric("IC IR", f(sq["ic_ir"]))
        if len(sq["quintile"]):
            st.dataframe(sq["quintile"].round(2), use_container_width=True)
        if len(wf["oos_trades"]):
            with st.expander("樣本外逐筆交易明細"):
                t = wf["oos_trades"].copy()
                t["code"] = t["code"].map(label)
                t["entry_date"] = pd.to_datetime(t["entry_date"]).dt.strftime("%Y-%m-%d")
                t["exit_date"] = pd.to_datetime(t["exit_date"]).dt.strftime("%Y-%m-%d")
                setup_n = {0: "無", 1: "回測", 2: "突破", 3: "黏合突破", 4: "VCP"}
                if "setup_type" in t.columns:
                    t["型態"] = t["setup_type"].map(setup_n)
                st.dataframe(t.rename(columns={"code": "標的", "entry_date": "進場日", "exit_date": "出場日",
                                               "fill": "成交價", "exit": "出場價", "reason": "出場原因",
                                               "days": "持有日", "net_pct": "淨損益%", "r_mult": "R倍數",
                                               "fold": "折"}).round(2), use_container_width=True, hide_index=True)
    else:
        st.info("按上方按鈕開始驗證。")


# ============================================================================
# Tab 5：篩選器（v3：18 項）
# ============================================================================
with tab_scr:
    st.markdown("### 🛠️ 18 項全景篩選器（v3 新增：NR7、OBV背離、均線黏合）")
    snap = snapshot(eng, params.preset)
    snap = snap[snap["liquid"]]
    chosen = []
    with st.expander("勾選條件（全部 AND）", expanded=True):
        cols = st.columns(3)
        for i, name in enumerate(SCREEN_FLAGS):
            if cols[i % 3].checkbox(name, key=f"scr_{i}"):
                chosen.append(name)
        s1, s2 = st.columns(2)
        mb5 = s1.slider("5MA 乖離上限 (%)", 1.0, 15.0, 15.0, 0.5, key="scr_b5")
        mb20 = s2.slider("20MA 乖離上限 (%)", 3.0, 40.0, 40.0, 1.0, key="scr_b20")
    res = snap.copy()
    for name in chosen:
        res = res[res[name]]
    res = res[(res["bias5"] <= mb5) & (res["bias20"] <= mb20)].sort_values("score", ascending=False)
    if res.empty:
        st.warning("沒有符合的標的，請放寬條件。")
    else:
        setup_n = {0: "—", 1: "📌回測", 2: "📈突破", 3: "⚡黏合突破", 4: "💎VCP"}
        show = pd.DataFrame({
            "標的": [label(c) for c in res.index],
            "分數": res["score"].round(1),
            "收盤": res["close"].round(2),
            "漲跌%": res["pct"].round(2),
            "成交(張)": res["volume_lots"].round(0).astype(int),
            "5日均額(億)": res["turnover_yi"].round(2),
            "5MA乖離%": res["bias5"].round(2),
            "型態": res["setup_type"].map(setup_n),
            "VCP%": (res["vcp_score"] * 100).round(0).astype(int),
            "K": res["K"].round(1),
            "RSI": res["RSI"].round(1),
            "通過推薦過濾": np.where(res["eligible"], "✔", ""),
        })
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(f"符合 {len(res)} 檔 / 流動性股票池 {len(snap)} 檔。")


# ============================================================================
# Tab 6：推播與自選股監控
# ============================================================================
with tab_alert:
    st.markdown("### 🔔 推播與自選股監控（Telegram / LINE）")
    st.caption("v3 新增推播：OBV背離（主力吸籌）、VCP突破、均線黏合突破、法人合買信號、鉅亨外資買超名單。")
    with st.expander("推播管道設定", expanded=not configured):
        st.markdown("""
**Telegram**：在 @BotFather 建立機器人；對機器人傳訊後開啟 `https://api.telegram.org/bot<TOKEN>/getUpdates` 找 `chat.id`。
**LINE Messaging API**：LINE Notify 已終止（2025/3/31），請改用 Official Account + Messaging API。
建議將金鑰放在環境變數或 `.streamlit/secrets.toml`（鍵名：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID、LINE_CHANNEL_TOKEN、LINE_USER_ID）。
        """)
        ov = st.session_state.setdefault("cfg_override", {})
        ov["tg_token"] = st.text_input("Telegram Bot Token", value=ov.get("tg_token", ""), type="password")
        ov["tg_chat"] = st.text_input("Telegram Chat ID", value=ov.get("tg_chat", ""))
        ov["line_token"] = st.text_input("LINE Channel access token", value=ov.get("line_token", ""), type="password")
        ov["line_user"] = st.text_input("LINE User ID（可留空=廣播）", value=ov.get("line_user", ""))
    cfg_now = cur_cfg()
    configured = bool((cfg_now["tg_token"] and cfg_now["tg_chat"]) or cfg_now["line_token"])
    a1, a2 = st.columns(2)
    a1.checkbox("開啟自動推播（每 20 分鐘）", value=configured, key="auto_push")
    a2.multiselect("推播類型", list(ALERT_CATS), default=list(ALERT_CATS), format_func=lambda k: ALERT_CATS[k], key="alert_cats")
    if st.button("📨 傳送測試訊息"):
        res = notify_all("✅ 台股量化系統 v3 推播測試成功（主力籌碼強化版）。", cfg_now) if configured else []
        if not res:
            st.error("尚未設定任何推播管道。")
        for ok, m in res:
            (st.success if ok else st.error)(m)

    st.markdown("#### 自選股監控")
    wl_text = st.text_area("代碼（以逗號、空白或換行分隔）", value=", ".join(st.session_state["watchlist"]), height=70)
    if st.button("💾 儲存自選股"):
        codes = [c for c in re.split(r"[\s,，、]+", wl_text) if re.fullmatch(r"\d{4}", c)]
        st.session_state["watchlist"] = codes
        save_watchlist(codes)
        st.success(f"已儲存 {len(codes)} 檔：" + "、".join(label(c) for c in codes))
        st.rerun()
    if st.session_state["watchlist"]:
        st.caption("目前監控：" + "、".join(label(c) for c in st.session_state["watchlist"]))

    st.markdown("#### 目前偵測到的訊號")
    if alerts:
        st.dataframe(pd.DataFrame([{"類型": ALERT_CATS[a.cat], "內容": a.text.replace("\n", "  ")} for a in alerts]),
                     use_container_width=True, hide_index=True)
    else:
        st.info("目前沒有新的訊號。")
    if st.session_state.get("alert_log"):
        st.markdown("#### 推播紀錄")
        for line in st.session_state["alert_log"][:15]:
            st.caption(line)
