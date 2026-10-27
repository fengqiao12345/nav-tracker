import json
import re
import time
from pathlib import Path

import requests


# ==============================
# 基础设置
# ==============================

BASE_URL = "https://www.beijingbobwealth.com.cn"

API_URL = (
    "https://www.beijingbobwealth.com.cn/"
    "bylc-api/product/navindex"
)

PRODUCTS_FILE = Path("products.json")
SEED_FILE = Path("nav_data.json")
HISTORY_FILE = Path("nav_history.json")
INDEX_FILE = Path("index.html")


# 创建网络会话
SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
)


# ==============================
# 读取产品清单
# ==============================

def load_products():
    """从products.json读取启用的北银理财产品。"""

    if not PRODUCTS_FILE.exists():
        raise RuntimeError("没有找到 products.json")

    products = json.loads(
        PRODUCTS_FILE.read_text(encoding="utf-8")
    )

    enabled_products = []

    for product in products:

        if not product.get("enabled", True):
            continue

        name = str(
            product.get("name", "")
        ).strip()

        share_code = str(
            product.get("share_code", "")
        ).strip()

        registration_code = str(
            product.get("registration_code", "")
        ).strip()

        if not name or not share_code:
            print("跳过信息不完整的产品：", product)
            continue

        enabled_products.append(
            {
                "name": name,
                "share_code": share_code,
                "registration_code": registration_code,
            }
        )

    if not enabled_products:
        raise RuntimeError(
            "products.json中没有启用的产品"
        )

    return enabled_products


# ==============================
# 读取历史数据
# ==============================

def load_history():
    """
    优先读取nav_history.json。
    首次运行时，从nav_data.json建立初始历史记录。
    """

    if HISTORY_FILE.exists():
        return json.loads(
            HISTORY_FILE.read_text(encoding="utf-8")
        )

    history = {}

    if not SEED_FILE.exists():
        return history

    seed_data = json.loads(
        SEED_FILE.read_text(encoding="utf-8")
    )

    for product in seed_data.get("products", []):

        code = str(
            product.get("share_code", "")
        ).strip()

        nav_date = str(
            product.get("nav_date", "")
        ).strip()

        unit_nav = product.get("unit_nav")

        wan_return = product.get(
            "wan_return", 0
        )

        if not code or not nav_date:
            continue

        if unit_nav is None:
            continue

        history[code] = [
            {
                "date": nav_date,
                "nav": float(unit_nav),
                "wan_return": float(wan_return),
            }
        ]

    return history


# ==============================
# 调用北银理财真实净值接口
# ==============================

def prepare_session():
    """
    先访问官网首页，让服务器建立普通公开访问会话。
    不使用银行账户，不使用个人Cookie。
    """

    try:
        SESSION.get(
            BASE_URL,
            timeout=30,
        )
    except Exception as error:
        print("官网预访问未完成：", error)


def get_latest_nav(share_code):
    """
    从北银理财公开接口获取某份额代码的最新净值。
    """

    params = {
        "noCache": int(time.time() * 1000),
        "pageSize": 10,
        "pageNumber": 1,
        "KEY": share_code,
    }

    headers = {
        "Accept": (
            "application/json, "
            "text/javascript, */*; q=0.01"
        ),
        "Referer": (
            f"{BASE_URL}/xxpl/cpgg/"
            "jzgg/index.html"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }

    response = SESSION.get(
        API_URL,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    if result.get("state") != "ok":
        print(
            f"{share_code}：接口返回状态异常，"
            f"state={result.get('state')}"
        )
        return None

    data = result.get("data", {})
    records = data.get("list", [])

    if not records:
        print(
            f"{share_code}：接口未返回净值记录"
        )
        return None

    valid_records = []

    for record in records:

        product_code = str(
            record.get("PROD_CODE", "")
        ).strip()

        nav_date = str(
            record.get("NAV_DATE", "")
        ).strip()

        nav_value = record.get("NAV")

        # 必须精确匹配份额代码
        if product_code != share_code:
            continue

        if nav_value is None:
            continue

        # 日期必须是8位数字，例如20261026
        if not re.fullmatch(
            r"\d{8}",
            nav_date,
        ):
            continue

        formatted_date = (
            f"{nav_date[0:4]}-"
            f"{nav_date[4:6]}-"
            f"{nav_date[6:8]}"
        )

        valid_records.append(
            {
                "date": formatted_date,
                "nav": float(nav_value),
            }
        )

    if not valid_records:
        print(
            f"{share_code}："
            "没有找到代码匹配的有效净值"
        )
        return None

    latest_record = max(
        valid_records,
        key=lambda item: item["date"],
    )

    print(
        f"{share_code}：取得净值 "
        f"{latest_record['date']} "
        f"{latest_record['nav']}"
    )

    return latest_record


# ==============================
# 计算万收并保存历史
# ==============================

def calculate_wan_return(
    current_nav,
    previous_nav,
):
    """计算相邻净值点每万元变化。"""

    if previous_nav <= 0:
        return 0.0

    value = (
        current_nav / previous_nav - 1
    ) * 10000

    return round(value, 2)


def update_product_history(
    history,
    share_code,
    latest_record,
):
    """将最新净值写入历史记录，避免重复。"""

    records = history.setdefault(
        share_code,
        [],
    )

    records.sort(
        key=lambda item: item["date"]
    )

    # 第一次加入的新产品
    if not records:
        records.append(
            {
                "date": latest_record["date"],
                "nav": latest_record["nav"],
                "wan_return": 0.0,
            }
        )

        return True

    previous_record = records[-1]

    # 出现新的净值日期
    if (
        latest_record["date"]
        > previous_record["date"]
    ):
        wan_return = calculate_wan_return(
            latest_record["nav"],
            previous_record["nav"],
        )

        records.append(
            {
                "date": latest_record["date"],
                "nav": latest_record["nav"],
                "wan_return": wan_return,
            }
        )

        return True

    # 管理人修正了同一天的净值
    if (
        latest_record["date"]
        == previous_record["date"]
        and latest_record["nav"]
        != previous_record["nav"]
    ):

        if len(records) >= 2:
            earlier_nav = records[-2]["nav"]

            wan_return = calculate_wan_return(
                latest_record["nav"],
                earlier_nav,
            )
        else:
            wan_return = previous_record.get(
                "wan_return",
                0.0,
            )

        previous_record["nav"] = (
            latest_record["nav"]
        )

        previous_record["wan_return"] = (
            wan_return
        )

        return True

    return False


# ==============================
# 自动生成手机网页
# ==============================

def escape_html(value):
    """处理产品名称中的特殊字符。"""

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def create_product_card(
    product,
    record,
):
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
          <div class="label">
            单位净值
          </div>

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


def render_index(
    products,
    history,
):
    """根据产品清单自动生成完整网页。"""

    cards = []
    latest_dates = []

    for product in products:

        code = product["share_code"]
        records = history.get(code, [])

        if not records:
            print(
                f"{product['name']}没有历史记录，"
                "本次不显示"
            )
            continue

        records.sort(
            key=lambda item: item["date"]
        )

        latest_record = records[-1]

        cards.append(
            create_product_card(
                product,
                latest_record,
            )
        )

        latest_dates.append(
            latest_record["date"]
        )

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

  <meta
    name="theme-color"
    content="#17365d"
  >

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
        linear-gradient(
          135deg,
          #17365d,
          #2f75b5
        );
      border-radius: 18px;
      box-shadow:
        0 8px 22px
        rgba(23, 54, 93, 0.18);
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
        0 3px 12px
        rgba(15, 23, 42, 0.06);
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
      数据来自公开披露渠道整理，
      仅用于个人查阅与对照，
      不构成投资建议。
      请以产品管理人正式披露为准。
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


# ==============================
# 主程序
# ==============================

def main():
    products = load_products()
    history = load_history()

    prepare_session()

    success_count = 0
    updated_count = 0

    for product in products:

        name = product["name"]
        code = product["share_code"]

        print(
            f"开始检查：{name} / {code}"
        )

        try:
            latest_record = get_latest_nav(code)

        except Exception as error:
            print(
                f"{name}检查失败："
                f"{type(error).__name__}: {error}"
            )
            continue

        if not latest_record:
            print(
                f"{name}未取得有效净值"
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
                f"{name}已新增或修正："
                f"{latest_record['date']} "
                f"{latest_record['nav']}"
            )
        else:
            print(
                f"{name}暂无新净值"
            )

    # 三只产品全部失败时明确报错，
    # 不生成网页，也不覆盖现有正确数据。
    if success_count == 0:
        raise RuntimeError(
            "所有产品均未成功取得真实净值，"
            "本次不更新网页"
        )

    HISTORY_FILE.write_text(
        json.dumps(
            history,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    render_index(
        products,
        history,
    )

    print(
        f"执行完成：成功检查"
        f"{success_count}只，"
        f"新增或修正"
        f"{updated_count}只"
    )


if __name__ == "__main__":
    main()
