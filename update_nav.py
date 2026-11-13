import json
from datetime import date
from playwright.sync_api import sync_playwright

TODAY = date.today().strftime("%Y-%m-%d")

def fetch_nav(code):
    url = f"https://www.beijingbobwealth.com.cn/xxpl/cpgg/jzgg/index.html?PROD_CODE={code}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")
            page.goto(url, timeout=30000)
            # 等待表格渲染
            page.wait_for_selector("table", timeout=15000)
            # 取第一行净值（最新）
            row = page.locator("table tr:nth-child(2)").inner_text()
            browser.close()
            parts = row.split()
            nav_date = parts[1]
            unit_nav = parts[2]
            acc_nav = parts[3]
            return unit_nav, acc_nav, nav_date
    except Exception as e:
        print(f"[{code}] 抓取失败：{e}")
        return None, None, None

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
.top h1{font-size:28px;margin-bottom:6px}
.top p{opacity:0.9}
.btn-group{margin-bottom:20px}
.btn{padding:10px 22px;border-radius:8px;border:none;font-size:16px;cursor:pointer}
.btn1{background:#1a4b97;color:#fff}
.btn2{background:#e8edf7;color:#1a4b97}
.card{background:#fff;padding:18px;border-radius:10px;margin:14px 0;box-shadow:0 2px 6px #00000012}
.err{color:red}
.info{color:#666;font-size:14px;margin:4px 0}
</style>
</head>
<body>
<div class="box">
<div class="top">
<h1>哪吒攒钱</h1>
<p>理财净值追踪页 | 数据日期:""" + TODAY + """</p>
</div>
<div class="btn-group">
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
            html += f'<div class="card"><h3>{name}</h3><p class="err">❌ 缺少share_code</p></div>'
            continue
        unit,acc,nav_dt = fetch_nav(code)
        if unit is None:
            html += f'<div class="card"><h3>{name}</h3><p>份额代码：{code}</p><p class="err">❌ 抓取失败</p></div>'
        else:
            html += f'''
<div class="card">
<h3>{name}</h3>
<p>份额代码：{code}</p>
<p class="info">净值日期：{nav_dt}</p>
<p>单位净值：{unit}</p>
<p>累计净值：{acc}</p>
</div>
'''
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
