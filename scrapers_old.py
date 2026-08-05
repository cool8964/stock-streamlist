import requests
import unicodedata
import random
import time
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Edge/122.0.0.0"
]

def get_robust_session():
    session = requests.Session()
    # 增加重試次數與 backoff_factor，應對短暫的網路波動
    retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return session

def get_twse_index_volume(date_str, session):
    url = f"https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date={date_str}"
    try:
        res = session.get(url, timeout=8)
        if res.status_code != 200:
            return None, None, None
        text = res.text.strip()
        if not text or text.startswith("<"):
            return None, None, None
        
        res_json = res.json()
        if res_json.get("stat") != "OK":
            return None, None, None
            
        data = res_json.get("data", [])
        tw_date = f"{int(date_str[:4]) - 1911}/{date_str[4:6]}/{date_str[6:8]}"
        for row in data:
            if row[0].strip() == tw_date:
                index = float(row[4].replace(",", "").strip())
                volume = round(int(row[1].replace(",", "").strip()) / 1000, 2)
                volume_m = round(int(row[2].replace(",", "").strip()) / 100000000, 2)
                return index, volume, volume_m
    except Exception as e:
        pass
    return None, None, None

def get_taifex_future(date_str, session):
    formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}" 
    url = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
    payload = {
        "queryType": "2",  
        "marketCode": "0",
        "queryDate": formatted_date,  
        "commodity_id": "TX"
    }
    taifex_future_headers = {
        "Origin": "https://www.taifex.com.tw",
        "Referer": "https://www.taifex.com.tw/cht/3/futDailyMarketReport",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": session.headers.get("User-Agent")
    }
    try:
        res = session.post(url, data=payload, headers=taifex_future_headers, timeout=8)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table", class_="table_f")
        if table:
            rows = table.find_all("tr")
            for row in rows:
                tds = [td.get_text().strip() for td in row.find_all("td")]
                if len(tds) > 6:
                    commodity_name = tds[0].replace(" ", "")
                    if "TX" in commodity_name:
                        close_val = tds[5].replace(",", "").strip()
                        if close_val and close_val not in ["-", ""]:
                            return float(close_val)
    except Exception as e:
        pass
    return None

def get_twse_dealers(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate={date_str}"
    try:
        res = session.get(url, timeout=8)
        if res.status_code != 200:
            return None, None, None
        text = res.text.strip()
        if not text or text.startswith("<"):
            return None, None, None
            
        res_json = res.json()
        if res_json.get("stat") != "OK":
            return None, None, None
            
        raw_data = res_json.get("data", [])
        if not raw_data or len(raw_data) < 5:
            return None, None, None

        def get_diff_float(row):
            return float(row[3].replace(",", "").strip())

        val_dealers_self  = get_diff_float(raw_data[0])
        val_dealers_hedge = get_diff_float(raw_data[1])
        val_sitc          = get_diff_float(raw_data[2])
        val_foreign_main  = get_diff_float(raw_data[3])
        val_foreign_corp  = get_diff_float(raw_data[4])

        foreign = round((val_foreign_main + val_foreign_corp) / 100000000, 2)
        sitc = round(val_sitc / 100000000, 2)
        dealers = round((val_dealers_self + val_dealers_hedge) / 100000000, 2)
            
        return foreign, sitc, dealers
    except Exception as e:
        pass
    return None, None, None

def get_twse_margin_trading(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&date={date_str}&selectType=ALL"
    try:
        res = session.get(url, timeout=8)
        if res.status_code != 200:
            return None, None, None, None, None
        text = res.text.strip()
        if not text or text.startswith("<"):
            return None, None, None, None, None
            
        json_data = res.json()
        if json_data.get("stat") != "OK":
            return None, None, None, None, None
            
        tables = json_data.get("tables", [])
        if not tables: return None, None, None, None, None
        
        raw_data = None
        for table in tables:
            d = table.get("data", [])
            if d:
                raw_data = d
                break
        if not raw_data: return None, None, None, None, None
        
        margin_shares_curr = 0       
        short_shares_prev = 0        
        short_shares_curr = 0        
        margin_money_prev = 0        
        margin_money_curr = 0        

        for row in raw_data:
            item_name = str(row[0]).strip().replace(" ", "")
            if "融資(交易單位)" in item_name or ("融資" in item_name and "張" in item_name):
                margin_shares_curr = float(str(row[5]).replace(",", "").strip() or 0)
            elif "融券(交易單位)" in item_name or ("融券" in item_name and "張" in item_name):
                short_shares_prev = float(str(row[4]).replace(",", "").strip() or 0)
                short_shares_curr = float(str(row[5]).replace(",", "").strip() or 0)
            elif "融資金額" in item_name and "仟元" in item_name:
                margin_money_prev = float(str(row[4]).replace(",", "").strip() or 0)
                margin_money_curr = float(str(row[5]).replace(",", "").strip() or 0)

        margin_diff = round((margin_money_curr - margin_money_prev) / 100000, 2)
        margin_balance = round(margin_money_curr / 100000, 2)
        short_diff = round(short_shares_curr - short_shares_prev)
        short_balance = round(short_shares_curr)
        margin_ratio = round((short_shares_curr / margin_shares_curr) * 100, 2) if margin_shares_curr > 0 else 0.0

        return f"{margin_diff:.2f}", f"{margin_balance:.2f}", f"{short_diff:.2f}", f"{short_balance:.2f}", f"{margin_ratio:.2f}"
    except Exception as e:
        pass
    return None, None, None, None, None

def get_twse_sbl_data(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?response=json&date={date_str}&selectType=ALL"
    try:
        res = session.get(url, timeout=8)
        if res.status_code != 200:
            return None, None, None
        text = res.text.strip()
        if not text or text.startswith("<"):
            return None, None, None
            
        json_data = res.json()
        if json_data.get("stat") == "OK":
            raw_data = json_data.get("data", [])
            for row in raw_data:
                if len(row) > 12 and "合計" in str(row[1]):
                    sbl_sell = round(float(str(row[9]).replace(",", "").strip() or 0) / 1000)     
                    sbl_return = round(float(str(row[10]).replace(",", "").strip() or 0) / 1000)  
                    sbl_bal = round(float(str(row[12]).replace(",", "").strip() or 0) / 1000)     
                    return f"{sbl_sell:,.2f}", f"{sbl_return:,.2f}", f"{sbl_bal:,.2f}"
    except Exception as e:
        pass
    return None, None, None

def get_twse_default_money(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/announcement/BFIGTU?response=json&startDate={date_str}&endDate={date_str}"
    try:
        res = session.get(url, timeout=8)
        if res.status_code != 200:
            return "0.00", "0.00"
        text = res.text.strip()
        if not text or text.startswith("<"):
            return "0.00", "0.00"
            
        json_data = res.json()
        stat = json_data.get("stat", "")
        if "沒有符合條件的資料" in stat or stat != "OK": 
            return "0.00", "0.00"
            
        tables = json_data.get("tables", [])
        if not tables: return "0.00", "0.00"
        raw_data = tables[0].get("data", [])
        if raw_data:
            row = raw_data[0]
            total_val = float(row[1].strip().replace(",", "")) / 1000000
            offset_val = float(row[2].strip().replace(",", "")) / 1000000
            return f"{total_val:.2f}", f"{offset_val:.2f}"
        return "0.00", "0.00"
    except Exception as e:
        pass
    return "0.00", "0.00"

def get_taifex_open_interest(date_str, session):
    oi_data = {"自營商": None, "投信": None, "外資": None}
    try:
        formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}"
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        payload = {
            "queryType": "1", "goDay": "", "doQuery": "1", "dateType": "0",
            "queryDate": formatted_date, "commodityId": "TXF"
        }
        user_agent = session.headers.get("User-Agent", "Mozilla/5.0")
        taifex_headers = {
            "Origin": "https://www.taifex.com.tw",
            "Referer": "https://www.taifex.com.tw/cht/3/futContractsDate",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": user_agent
        }
        res = session.post(url, data=payload, headers=taifex_headers, timeout=8)
        if res.status_code != 200 or not res.text.strip():
            return None, None, None

        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table", class_="table_f")
        if table:
            rows = table.find_all("tr")
            is_target_product = False
            for row in rows:
                td_elements = row.find_all("td")
                tds = ["".join(td.get_text().split()) for td in td_elements]
                if not tds: continue
                if any("臺股期貨" in x or "台股期貨" in x for x in tds):
                    is_target_product = True
                elif is_target_product and any(any(p in x for p in ["電子期", "金融期", "小型臺指", "小型台指", "臺灣半導體", "台灣半導體"]) for x in tds):
                    is_target_product = False
                if is_target_product:
                    for identity in oi_data.keys():
                        if any(identity in x for x in tds):
                            if len(tds) >= 5:
                                val = tds[-2]
                                cleaned_val = "".join([c for c in val if c.isdigit() or c == '-'])
                                if cleaned_val:
                                    oi_data[identity] = cleaned_val
            return oi_data["自營商"], oi_data["投信"], oi_data["外資"]
    except Exception as e:
        pass
    return None, None, None

def fetch_all_stock_data(date_str, external_session=None):
    session = external_session if external_session is not None else get_robust_session()
    
    # 輕量隨機延遲，兼顧速度與防封鎖
    time.sleep(random.uniform(0.3, 0.8))
    
    idx, vol, vol_m = get_twse_index_volume(date_str, session)
    future = get_taifex_future(date_str, session)
    foreign, sitc, dealers = get_twse_dealers(date_str, session)
    
    if foreign is not None and sitc is not None and dealers is not None:
        total_institutional_day = round((foreign or 0) + (sitc or 0) + (dealers or 0), 2)
        total_institutional_day_str = f"{total_institutional_day:.2f}"
    else:
        total_institutional_day_str = None

    margin_diff, margin_balance, short_diff, short_balance, margin_ratio = get_twse_margin_trading(date_str, session)
    sbl_sell, sbl_return, sbl_bal = get_twse_sbl_data(date_str, session)
    default_total, default_offset = get_twse_default_money(date_str, session)
    oi_dealers, oi_sitc, oi_foreign = get_taifex_open_interest(date_str, session)
    
    idx_str = f"{idx:.2f}" if idx is not None else None
    future_str = f"{future:.2f}" if future is not None else None
    vol_str = f"{vol:.2f}" if vol is not None else None
    vol_m_str = f"{vol_m:.2f}" if vol_m is not None else None
    foreign_str = f"{foreign:.2f}" if foreign is not None else None
    sitc_str = f"{sitc:.2f}" if sitc is not None else None
    dealers_str = f"{dealers:.2f}" if dealers is not None else None

    return {
        "大盤指數": idx_str,
        "台指期近一": future_str,
        "成交量(千股)": vol_str,
        "成交量金額(億)": vol_m_str,
        "外資進出(億)": foreign_str,
        "投信進出(億)": sitc_str,
        "自營商進出(億)": dealers_str,
        "三大法人(億)": total_institutional_day_str,
        "融資增減": margin_diff,
        "融資餘額": margin_balance,
        "融券增減": short_diff,
        "融券餘額": short_balance,
        "券資比(%)": margin_ratio,
        "券賣出量(千股)": sbl_sell,
        "券賣還券(千股)": sbl_return,
        "券賣餘額(千股)": sbl_bal,
        "自營商未平倉(口)": oi_dealers,
        "投信未平倉(口)": oi_sitc,
        "外資未平倉(口)": oi_foreign,
        "違約合計(百萬)": default_total,
        "違約相抵後(百萬)": default_offset
    }

def fetch_stock_name(stock_code):
    stock_code = str(stock_code).upper().strip()
    if stock_code == "INDEX":
        return "大盤"
    try:
        url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                if item.get("公司代號") == stock_code:
                    return item.get("公司名稱", stock_code)
    except Exception:
        pass
    return stock_code