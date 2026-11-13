import requests
import json
from datetime import date
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
}
TODAY = date.today().strftime("%Y-%m-%d")

def fetch_nav(code):
    url = f"https://www.beijingbobwealth.com.cn/xxpl/cpgg/jzgg/index.html?PROD_CODE={code}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        trs = soup.select("table tr")
        if len(trs) < 2:
            return None, None
        tds = trs[1].select("td")
        if len(tds)>=4:
            unit = float(tds[2].get_text(strip=True))
            acc = float(tds[3].get_text(strip=True))
            return unit, acc
        return None, None
    except Exception as e:
        print("抓取异常：",e)
        return None, None

def load_products():
    with open("products.json","r",encoding="utf-8") as f:
        return json.load(f)

def build_html(prods):
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>哪吒攒钱</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:system-ui}
body{background:#f5f7fa;padding:20px}
.box{max-width:1100px;margin:0 auto}
.top{background:#1a4b97;color:#fff;padding:24px;border-radius:12px;margin-bottom:20px}
.btn{padding:12px 22px;border-radius:8px;border:none;font-size:16px}
.btn1{background:#1a4b97;color:#fff}
.btn2{background:#e8edf7;color:#1a4b97}
.card{background:#fff;padding:18px;border-radius:10px;margin:14px 0;box-shadow:0 2px 6px #00000012}
</style>
</head>
<body>
<div class="box">
<div class="top">
<h1>哪吒攒钱</h1>
<div>理财净值追踪页 | 数据日期:""" + TODAY + """</div>
</div>
<div style="margin-bottom:18px">
<button class="btn btn1">净值追踪</button>
<button class="btn btn2" onclick="location.href='new_products.html'">新品监测</button>
</div>
"""
    for p in prods:
        name = p.get("name","未命名产品")
        code = p.get("share_code","")
        enable = p.get("enabled",True)
        if not enable:
            continue
        if not code:
            html += f'<div class="card"><h3>{name}</h3><p style="color:red">❌ 缺少share_code</p></div>'
            continue
        unit,acc = fetch_nav(code)
        if unit is None:
            html += f'<div class="card"><h3>{name}</h3><p>份额代码：{code}</p><p style="color:red">❌ 抓取失败</p></div>'
        else:
            html += f'<div class="card"><h3>{name}</h3><p>份额代码：{code}</p><p>单位净值：{unit:.6f}</p><p>累计净值：{acc:.6f}</p></div>'
    html += "</div></body></html>"
    return html

def main():
    plist = load_products()
    html = build_html(plist)
    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✅ index.html生成完成")

if __name__ == "__main__":
    main()
