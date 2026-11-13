import requests
import json
from datetime import date
from bs4 import BeautifulSoup

# -------------------------- 配置区 --------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9"
}
TODAY = date.today().strftime("%Y-%m-%d")
# -----------------------------------------------------------

def get_total_asset(prod_code):
    url = f"https://www.beijingbobwealth.com.cn/xxpl/cpgg/jzgg/index.html?PROD_CODE={prod_code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tr")
        if len(rows) < 2:
            return "-"
        latest_row = rows[1]
        tds = latest_row.select("td")
        if len(tds) >= 8:
            asset_yuan = float(tds[7].get_text(strip=True))
            asset_yi = round(asset_yuan / 100000000, 2)
            return f"{asset_yi}亿"
        return "-"
    except Exception as e:
        print(f"【资产净值抓取失败 {prod_code}】{e}")
        return "-"

def fetch_product_info(prod_code):
    url = f"https://www.beijingbobwealth.com.cn/xxpl/cpgg/jzgg/index.html?PROD_CODE={prod_code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tr")
        if len(rows) < 2:
            print(f"【{prod_code}】页面表格为空")
            return None, None
        latest_row = rows[1]
        tds = latest_row.select("td")
        if len(tds) >= 4:
            unit_nav = float(tds[2].get_text(strip=True))
            acc_nav = float(tds[3].get_text(strip=True))
            return unit_nav, acc_nav
        print(f"【{prod_code}】表格列数不足")
        return None, None
    except Exception as e:
        print(f"【净值抓取失败 {prod_code}】{e}")
        return None, None

def load_products():
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_history():
    try:
        with open("nav_history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_history(history):
    with open("nav_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def build_html(product_list, history):
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>哪吒攒钱</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,sans-serif}
body{background:#f5f7fa;padding:20px}
.container{max-width:1200px;margin:0 auto}
.header{background:#1a4b97;color:#fff;padding:24px;border-radius:12px;margin-bottom:20px}
.header h1{font-size:28px;margin-bottom:8px}
.tab-bar{display:flex;gap:8px;margin-bottom:20px}
.tab{padding:12px 24px;border-radius:8px;border:none;font-size:16px;cursor:pointer}
.tab.active{background:#1a4b97;color:#fff}
.tab.inactive{background:#e8edf7;color:#1a4b97}
.card{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 2px 8px #00000010}
.card-title{font-size:18px;font-weight:bold;margin-bottom:6px}
.card-sub{color:#666;margin-bottom:16px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.item{padding:12px;background:#f5f7fa;border-radius:8px;text-align:center}
.item .val{font-size:22px;font-weight:bold;margin:4px 0}
.up{color:#d63031}
.down{color:#00b894}
.desc{font-size:14px;color:#555}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>哪吒攒钱</h1>
<div>理财净值追踪页 | 数据日期: """ + TODAY + """</div>
</div>
<div class="tab-bar">
<button class="tab active" onclick="location.href='index.html'">净值追踪</button>
<button class="tab inactive" onclick="location.href='new_products.html'">新品监测</button>
</div>
"""
    for p in product_list:
        if "code" not in p or "name" not in p:
            continue
        name = p["name"]
        code = p["code"]
        unit_nav, acc_nav = fetch_product_info(code)
        asset_str = get_total_asset(code)
        if unit_nav is None:
            html += f'<div class="card"><div class="card-title">{name}</div><div class="card-sub">份额代码：{code}</div><div>抓取失败</div></div>'
            continue

        prod_key = f"{code}"
        if prod_key not in history:
            history[prod_key] = {}
        history[prod_key][TODAY] = unit_nav
        sorted_dates = sorted(history[prod_key].keys())
        prev_nav = None
        if len(sorted_dates)>=2:
            prev_day = sorted_dates[-2]
            prev_nav = history[prod_key][prev_day]
        diff = 0
        if prev_nav is not None:
            diff = round((unit_nav - prev_nav)*10000,2)
        diff_class = "up" if diff>0 else "down" if diff<0 else ""

        recent7 = sorted_dates[-7:] if len(sorted_dates)>=7 else sorted_dates
        recent14 = sorted_dates[-14:] if len(sorted_dates)>=14 else sorted_dates
        def avg_tenk(arr):
            if len(arr)<2:return 0
            s=0
            for i in range(1,len(arr)):
                s += (history[prod_key][arr[i]] - history[prod_key][arr[i-1]])*10000
            return round(s/(len(arr)-1),2)
        avg7 = avg_tenk(recent7)
        avg14 = avg_tenk(recent14)
        avg7_cls = "up" if avg7>0 else "down" if avg7<0 else ""
        avg14_cls = "up" if avg14>0 else "down" if avg14<0 else ""

        html += f"""
<div class="card">
<div class="card-title">{name}</div>
<div class="card-sub">份额代码：{code}</div>
<div class="grid">
    <div class="item"><div class="desc">单位净值</div><div class="val">{unit_nav:.6f}</div></div>
    <div class="item"><div class="desc">当日万收</div><div class="val {diff_class}">{diff:.2f}元</div></div>
    <div class="item"><div class="desc">7日日均万收</div><div class="val {avg7_cls}">{avg7:.2f}元</div></div>
    <div class="item"><div class="desc">14日日均万收</div><div class="val {avg14_cls}">{avg14:.2f}元</div></div>
    <div class="item"><div class="desc">产品总资产</div><div class="val">{asset_str}</div></div>
</div>
<div style="margin-top:12px;color:#777;font-size:14px">净值日期: {TODAY}</div>
</div>
"""
    html += """
</div>
</body>
</html>
"""
    return html

def main():
    products = load_products()
    history = load_history()
    html_text = build_html(products, history)
    save_history(history)
    with open("index.html","w",encoding="utf-8") as f:
        f.write(html_text)
    print("✅ index.html 生成完成，nav_history.json已更新")

if __name__ == "__main__":
    main()
