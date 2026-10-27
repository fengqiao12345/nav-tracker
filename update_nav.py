import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


# 北银理财官网
BASE_URL = "https://www.beijingbobwealth.com.cn"

# 本地文件
PRODUCTS_FILE = Path("products.json")
SEED_FILE = Path("nav_data.json")
HISTORY_FILE = Path("nav_history.json")
INDEX_FILE = Path("index.html")

# 模拟普通浏览器访问
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
)


def get_url(url):
    """读取公开网页或PDF。"""
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    return response


def load_products():
    """从products.json读取所有启用的产品。"""
    if not PRODUCTS_FILE.exists():
        raise RuntimeError("没有找到 products.json")

    products = json.loads(
        PRODUCTS_FILE.read_text(encoding="utf-8")
    )

    enabled_products = []

    for product in products:
        if not product.get("enabled", True):
            continue

        share_code = product.get("share_code", "").strip()
        name = product.get("name", "").strip()

        if not share_code or not name:
            print("跳过信息不完整的产品：", product)
            continue

        enabled_products.append(
            {
                "name": name,
                "share_code": share_code,
                "registration_code": product.get(
                    "registration_code", ""
                ).strip(),
            }
        )

    if not enabled_products:
        raise RuntimeError("products.json中没有启用的产品")

    return enabled_products


def load_history():
    """读取历史净值；首次运行时从nav_data.json建立初始记录。"""
    if HISTORY_FILE.exists():
        return json.loads(
            HISTORY_FILE.read_text(encoding="utf-8")
        )

    history = {}

    if SEED_FILE.exists():
        seed_data = json.loads(
            SEED_FILE.read_text(encoding="utf-8")
        )

        for product in seed_data.get("products", []):
            code = product.get("share_code", "").strip()

            if not code:
                continue

            history[code] = [
                {
                    "date": product.get("nav_date"),
                    "nav": float(product.get("unit_nav")),
                    "wan_return": float(
                        product.get("wan_return", 0)
                    ),
                }
            ]

    return history


def extract_pdf_text(url):
    """读取PDF中的文字。"""
    response = get_url(url)
    reader = PdfReader(io.BytesIO(response.content))

    pages = []

    for page in reader.pages:
        pages.append(page.extract_text() or "")

    return "\n".join(pages)


def find_candidate_links(share_code):
    """在北银理财近期净值公告中寻找产品公告链接。"""
    links = []

    # 最新公告在前面。检查前30页，足够覆盖近期更新公告。
    for page_number in range(0, 30):

        if page_number == 0:
            page_url = (
                f"{BASE_URL}/xxpl/cpgg/jzgg/index.html"
            )
        else:
            page_url = (
                f"{BASE_URL}/xxpl/cpgg/jzgg/"
                f"index{page_number + 1}.html"
            )

        try:
            html = get_url(page_url).text
        except Exception as error:
            print("公告列表读取失败：", page_url, error)
            continue

        soup = BeautifulSoup(html, "html.parser")

        for link in soup.find_all("a", href=True):
            title = " ".join(
                link.get_text(" ", strip=True).split()
            )
            href = urljoin(page_url, link["href"])

            if share_code in title or share_code in href:
                links.append(href)

        # 避免请求过快
        time.sleep(0.2)

    # 去重并保留原顺序
    return list(dict.fromkeys(links))


def parse_nav_record(text, share_code):
    """从公告文字中提取净值日期和单位净值。"""
    clean_text = " ".join(
        text.replace("\u3000", " ").split()
    )

    code_position = clean_text.find(share_code)

    if code_position < 0:
        return None

    # 只分析产品代码附近的文字
    block = clean_text[
        max(0, code_position - 180):
        code_position + 300
    ]

    dates = re.findall(
        r"(20\d{2})\s*年\s*"
        r"(\d{1,2})\s*月\s*"
        r"(\d{1,2})\s*日",
        block,
    )

    nav_values = re.findall(
        r"(?<!\d)([01]\.\d{4,8})(?!\d)",
        block,
    )

    if not dates or not nav_values:
        return None

    year, month, day = dates[-1]

    return {
        "date": (
            f"{int(year):04d}-"
            f"{int(month):02d}-"
            f"{int(day):02d}"
        ),
        "nav": float(nav_values[0]),
    }


def get_latest_nav(share_code):
    """取得某产品最新公开净值。"""
    records = []
    links = find_candidate_links(share_code)

    print(
        f"{share_code}：找到{len(links)}个候选公告"
    )

    for link in links:
        try:
            if ".pdf" in link.lower():
                text = extract_pdf_text(link)
            else:
                text = get_url(link).text

            record = parse_nav_record(text, share_code)

            if record:
                records.append(record)

        except Exception as error:
            print("公告读取失败：", link, error)

    if not records:
        return None

    return max(records, key=lambda item: item["date"])


def calculate_wan_return(current_nav, previous_nav):
    """计算相邻净值点每万元变化。"""
    if previous_nav <= 0:
        return 0.0

    return (
        current_nav / previous_nav - 1
    ) * 10000


def update_product_history(
    history,
    share_code,
    latest_record,
):
    """将新净值写入历史记录，避免重复。"""
    records = history.setdefault(share_code, [])

    if not records:
        records.append(
            {
                "date": latest_record["date"],
                "nav": latest_record["nav"],
                "wan_return": 0.0,
            }
        )
        return True

    records.sort(key=lambda item: item["date"])
    previous = records[-1]

    # 发现更新日期
    if latest_record["date"] > previous["date"]:
        wan_return = calculate_wan_return(
            latest_record["nav"],
            previous["nav"],
        )

        records.append(
            {
                "date": latest_record["date"],
                "nav": latest_record["nav"],
                "wan_return": round(wan_return, 2),
            }
        )
        return True

    # 同一天管理人修改了净值
    if (
        latest_record["date"] == previous["date"]
        and latest_record["nav"] != previous["nav"]
    ):
        if len(records) >= 2:
            previous_nav = records[-2]["nav"]
            wan_return = calculate_wan_return(
                latest_record["nav"],
                previous_nav,
            )
        else:
            wan_return = previous.get(
                "wan_return", 0
            )

        previous["nav"] = latest_record["nav"]
        previous["wan_return"] = round(
            wan_return, 2
        )
        return True

    return False


def escape_html(value):
    """避免产品名称中的特殊字符影响网页。"""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def create_product_card(product, record):
    """生成一只产品的网页卡片。"""
    wan_return = float(
        record.get("wan_return", 0)
    )

    if wan_return >= 0:
        return_class = "positive"
        return_text = f"+{wan_return:.2f} 元"
    else:
        return_class = "negative"
        return_text = f"{wan_return:.2f} 元"

    return f"""
    <article class="card">
      <div class="product-name">
        {escape_html(product["name"])}
      </div>

      <div class="product-code">
        份额代码：
        {escape_html(product["share_code"])}
      </div>

      <div class="metrics">
        <div class="metric">
          <div class="label">单位净值</div>
          <div class="value">
            {float(record["nav"]):.6f}
          </div>
        </div>

        <div class="metric">
          <div class="label">
            相邻净值点万收
          </div>
          <div class="value {return_class}">
            {return_text}
          </div>
        </div>
      </div>

      <div class="nav-date">
        净值日期：{record["date"]}
      </div>
    </article>
    """


def render_index(products, history):
    """根据产品数量自动生成完整网页。"""
    cards = []
    latest_dates = []

    for product in products:
        code = product["share_code"]
        records = history.get(code, [])

        if not records:
            continue

        records.sort(key=lambda item: item["date"])
        latest_record = records[-1]

        cards.append(
            create_product_card(
                product,
                latest_record,
            )
        )
        latest_dates.append(latest_record["date"])

    if not cards:
        raise RuntimeError(
            "没有可用于生成网页的产品数据"
        )

    overall_date = max(latest_dates)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta
    name="viewport"
    content="width=device-width,initial-scale=1"
  >
  <meta name="theme-color" content="#17365d">
  <title>理财净值观测</title>

  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: #f5f7fb;
      color: #1f2937;
      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "PingFang SC",
        "Microsoft YaHei",
        sans-serif;
    }}

    main {{
      max-width: 680px;
      margin: 0 auto;
      padding: 18px 14px 36px;
    }}

    .header {{
      padding: 21px 18px;
      color: white;
      background:
        linear-gradient(135deg, #17365d, #2f75b5);
      border-radius: 18px;
      box-shadow:
        0 8px 22px rgba(23, 54, 93, 0.18);
    }}

    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
    }}

    .update-time {{
      font-size: 13px;
      opacity: 0.9;
    }}

    .product-list {{
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }}

    .card {{
      padding: 16px;
      background: white;
      border: 1px solid #eef1f5;
      border-radius: 16px;
      box-shadow:
        0 3px 12px rgba(15, 23, 42, 0.06);
    }}

    .product-name {{
      margin-bottom: 4px;
      font-size: 17px;
      font-weight: 700;
    }}

    .product-code {{
      color: #6b7280;
      font-size: 12px;
    }}

    .metrics {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 15px;
    }}

    .metric {{
      padding: 11px;
      background: #f7f9fc;
      border-radius: 12px;
    }}

    .label {{
      margin-bottom: 5px;
      color: #6b7280;
      font-size: 12px;
    }}

    .value {{
      font-size: 20px;
      font-weight: 750;
    }}

    .positive {{
      color: #c62828;
    }}

    .negative {{
      color: #16803c;
    }}

    .nav-date {{
      margin-top: 11px;
      color: #6b7280;
      font-size: 12px;
    }}

    .notice {{
      margin-top: 15px;
      padding: 0 3px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.65;
    }}
  </style>
</head>

<body>
  <main>
    <section class="header">
      <h1>理财净值观测</h1>
      <div class="update-time">
        数据日期：{overall_date}
      </div>
    </section>

    <section class="product-list">
      {''.join(cards)}
    </section>

    <div class="notice">
      数据来自公开披露渠道整理，仅用于个人查阅与对照，
      不构成投资建议。请以产品管理人正式披露为准。
      “万收”表示相邻净值点每万元变化，
      两个净值点之间可能跨越多个自然日。
    </div>
  </main>
</body>
</html>
"""

    INDEX_FILE.write_text(
        html,
        encoding="utf-8",
    )


def main():
    products = load_products()
    history = load_history()

    success_count = 0
    updated_count = 0

    for product in products:
        code = product["share_code"]

        print(
            f"开始检查：{product['name']} / {code}"
        )

        try:
            latest_record = get_latest_nav(code)
        except Exception as error:
            print(
                f"{product['name']}检查失败：{error}"
            )
            continue

        if not latest_record:
            print(
                f"{product['name']}未找到最新净值"
            )
            continue

        success_count += 1

        changed = update_product_history(
            history,
            code,
            latest_record,
        )

        if changed:
            updated_count += 1
            print(
                f"{product['name']}已更新："
                f"{latest_record['date']} "
                f"{latest_record['nav']}"
            )
        else:
            print(
                f"{product['name']}暂无新净值"
            )

    # 全部查询失败时，不覆盖现有网页
    if success_count == 0:
        raise RuntimeError(
            "所有产品均未成功获取，"
            "为保护现有网页，本次不更新文件"
        )

    HISTORY_FILE.write_text(
        json.dumps(
            history,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    render_index(products, history)

    print(
        f"执行完成：成功检查{success_count}只，"
        f"新增或修正{updated_count}只"
    )


if __name__ == "__main__":
    main()
