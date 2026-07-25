import requests
import unicodedata
import random
import time
from datetime import datetime
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# -------------------------------------------------------------------------
# 防反爬蟲設定：隨機 User-Agent 庫
# -------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Edge/122.0.0.0"
]

def get_robust_session():
    """建立帶有自動重試機制、且模擬正常瀏覽器的 Session"""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return session

# ==========================================================
# 1. 抓取大盤指數、大盤成交量（來源：證交所）
# ==========================================================
def get_twse_index_volume(date_str, session):
    url = f"https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date={date_str}"
    try:
        res = session.get(url, timeout=5)
        data = res.json().get("data", [])
        tw_date = f"{int(date_str[:4]) - 1911}/{date_str[4:6]}/{date_str[6:8]}"
        for row in data:
            if row[0].strip() == tw_date:
                index = float(row[4].replace(",", "").strip())
                volume = round(int(row[2].replace(",", "").strip()) / 100000000, 2)
                return index, volume
    except Exception as e:
        print(f"【1. 大盤/成交量 異常】: {e}")
    return None, None

# ==========================================================
# 2. 抓取台指期近一最後成交價（來源：期交所）
# ==========================================================
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
        res = session.post(url, data=payload, headers=taifex_future_headers, timeout=5)
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
                        if close_val and close_val != "-" and close_val != "":
                            return float(close_val)
                            
        print(f"【2. 台指期近一 提示】期交所當日 ({date_str}) 無行情或該日未開盤")
    except Exception as e:
        print(f"【2. 台指期近一 異常】: {e}")
    return None

# ==========================================================
# 3. 三大法人買賣差額（來源：證交所）
# ==========================================================
def get_twse_dealers(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate={date_str}"
    try:
        res = session.get(url, timeout=5)
        res_json = res.json()
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
        print(f"【3. 三大法人 異常】: {e}")
    return None, None, None

# ==========================================================
# 4. 融資融券餘額/信用交易統計（來源：證交所）
# ==========================================================
def get_twse_margin_trading(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&date={date_str}&selectType=ALL"
    try:
        res = session.get(url, timeout=5)
        json_data = res.json()
        tables = json_data.get("tables", [])
        if not tables: return None, None, None, None, None
        raw_data = tables[0].get("data", [])
        if not raw_data: return None, None, None, None, None
        
        margin_shares_curr = 0       
        short_shares_prev = 0        
        short_shares_curr = 0        
        margin_money_prev = 0        
        margin_money_curr = 0        

        for row in raw_data:
            item_name = row[0].strip().replace(" ", "")
            if "融資(交易單位)" in item_name:
                margin_shares_curr = float(row[5].replace(",", "").strip())
            elif "融券(交易單位)" in item_name:
                short_shares_prev = float(row[4].replace(",", "").strip())
                short_shares_curr = float(row[5].replace(",", "").strip())
            elif "融資金額(仟元)" in item_name:
                margin_money_prev = float(row[4].replace(",", "").strip())
                margin_money_curr = float(row[5].replace(",", "").strip())

        margin_diff = round((margin_money_curr - margin_money_prev) / 100000, 2)
        margin_balance = round(margin_money_curr / 100000, 2)
        short_diff = round(short_shares_curr - short_shares_prev, 2)
        short_balance = round(short_shares_curr, 2)
        margin_ratio = round((short_shares_curr / margin_shares_curr) * 100, 2) if margin_shares_curr > 0 else 0.0

        return f"{margin_diff:.2f}", f"{margin_balance:.2f}", f"{short_diff:.2f}", f"{short_balance:.2f}", f"{margin_ratio:.2f}"
    except Exception as e:
        print(f"【4. 信用交易 異常】: {e}")
    return None, None, None, None, None

# ==========================================================
# 5. 證券商申報投資人違約金額（來源：證交所）
# ==========================================================
def get_twse_default_money(date_str, session):
    url = f"https://www.twse.com.tw/rwd/zh/announcement/BFIGTU?response=json&startDate={date_str}&endDate={date_str}"
    try:
        res = session.get(url, timeout=5)
        json_data = res.json()
        if "沒有符合條件的資料" in json_data.get("stat", ""): return "0.00", "0.00"
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
        print(f"【5. 違約金額 異常】: {e}")
    return None, None

# ==========================================================
# 6. 三大法人未平倉口數
# ==========================================================
def get_taifex_open_interest(date_str, session):
    oi_data = {"自營商": None, "投信": None, "外資": None}
    
    try:
        try:
            import time
            import random
            time.sleep(random.uniform(0.1, 0.5))
        except Exception:
            pass
            
        formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}"
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        
        payload = {
            "queryType": "1",
            "goDay": "",
            "doQuery": "1",
            "dateType": "0",
            "queryDate": formatted_date,
            "commodityId": "TXF"
        }
        
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        if session and hasattr(session, "headers") and session.headers:
            user_agent = session.headers.get("User-Agent", user_agent)
            
        taifex_headers = {
            "Origin": "https://www.taifex.com.tw",
            "Referer": "https://www.taifex.com.tw/cht/3/futContractsDate",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": user_agent
        }
        
        if session is None:
            import requests
            res = requests.post(url, data=payload, headers=taifex_headers, timeout=10)
        else:
            res = session.post(url, data=payload, headers=taifex_headers, timeout=10)
        
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
                if not tds:
                    continue
                
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
                                oi_data[identity] = cleaned_val
                                
            return oi_data["自營商"], oi_data["投信"], oi_data["外資"]
            
    except Exception as e:
        print(f"❌【未平倉爬蟲出錯，已被安全攔截】詳細原因: {e}")
        
    return None, None, None

# ==========================================================
# 主整合程式
# ==========================================================
def fetch_all_stock_data(date_str, external_session=None):
    session = external_session if external_session is not None else get_robust_session()
    
    time.sleep(random.uniform(0.05, 0.25))
    
    idx, vol = get_twse_index_volume(date_str, session)
    future = get_taifex_future(date_str, session)
    foreign, sitc, dealers = get_twse_dealers(date_str, session)
    margin_diff, margin_balance, short_diff, short_balance, margin_ratio = get_twse_margin_trading(date_str, session)
    default_total, default_offset = get_twse_default_money(date_str, session)
    oi_dealers, oi_sitc, oi_foreign = get_taifex_open_interest(date_str, session)
    
    idx_str = f"{idx:.2f}" if idx is not None else None
    future_str = f"{future:.2f}" if future is not None else None
    vol_str = f"{vol:.2f}" if vol is not None else None
    foreign_str = f"{foreign:.2f}" if foreign is not None else None
    sitc_str = f"{sitc:.2f}" if sitc is not None else None
    dealers_str = f"{dealers:.2f}" if dealers is not None else None

    return {
        "大盤指數": idx_str,
        "台指期近一": future_str,
        "大盤成交量": f"{vol_str} 億" if vol_str else None,
        "外資進出": f"{foreign_str} 億" if foreign_str else None,
        "法人進出(投信)": f"{sitc_str} 億" if sitc_str else None,
        "自營商進出": f"{dealers_str} 億" if dealers_str else None,
        "融資增減": f"{margin_diff} 億" if margin_diff else None,
        "融資餘額": f"{margin_balance} 億" if margin_balance else None,
        "借券增減": f"{short_diff} 張" if short_diff else None,
        "借券餘額": f"{short_balance} 張" if short_balance else None,
        "券資比": f"{margin_ratio}%" if margin_ratio else None,
        "自營商未平倉": f"{oi_dealers} 口" if oi_dealers else None,
        "投信未平倉": f"{oi_sitc} 口" if oi_sitc else None,
        "外資未平倉": f"{oi_foreign} 口" if oi_foreign else None,
        "違約合計總金額": f"{default_total} 百萬" if default_total else None,
        "違約相抵後金額": f"{default_offset} 百萬" if default_offset else None
    }

if __name__ == "__main__":
    test_date = "20260605"
    data = fetch_all_stock_data(test_date)
    
    print(f"\n====== 全籌碼資料綜合抓取結果 ({test_date}) ======")
    if data and any(data.values()):
        for k, v in data.items():
            print(f"{k}: {v}")