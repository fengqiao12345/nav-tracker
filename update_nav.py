import json
import re
import ssl
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter


# ==========================================
# 基础配置
# ==========================================

PAGE_URL = (
    "https://bankofbeijing.com.cn/"
    "personal/second/lcjz"
    "?column=1549644340891176960"
)

API_URL = (
    "https://bankofbeijing.com.cn/"
    "api/wealth/callJz"
)

TITLE_ID = "1549644340891176960"

PRODUCTS_FILE = Path("products.json")
SEED_FILE = Path("nav_data.json")
HISTORY_FILE = Path("nav_history.json")
INDEX_FILE = Path("index.html")


# ==========================================
# 兼容北京银行旧版SSL
# ==========================================

class LegacySSLAdapter(HTTPAdapter):
    """兼容部分银行网站使用的旧版SSL协商方式。"""

    def create_ssl_context(self):
        context = ssl.create_default_context()

        legacy_option = getattr(
            ssl,
            "OP_LEGACY_SERVER_CONNECT",
            0x4,
        )
        context.options |= legacy_option

        try:
            context.set_ciphers(
                "DEFAULT@SECLEVEL=1"
            )
        except ssl.SSLError:
            pass

        return context

    def init_poolmanager(
        self,
        connections,
        maxsize,
        block=False,
        **pool_kwargs,
    ):
        pool_kwargs["ssl_context"] = (
            self.create_ssl_context()
        )

        return super().init_poolmanager(
            connections,
            maxsize,
            block=block,
            **pool_kwargs,
        )

    def proxy_manager_for(
        self,
        proxy,
        **proxy_kwargs,
    ):
        proxy_kwargs["ssl_context"] = (
            self.create_ssl_context()
        )

        return super().proxy_manager_for(
            proxy,
            **proxy_kwargs,
        )


SESSION = requests.Session()

SESSION.mount(
    "https://bankofbeijing.com.cn/",
    LegacySSLAdapter(),
)

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept-Language": (
            "zh-CN,zh;q=0.9,en;q=0.8"
        ),
    }
)


# ==========================================
# 读取产品清单
# ==========================================

def load_products():
    """从products.json读取所有启用产品。"""

    if not PRODUCTS_FILE.exists():
        raise RuntimeError(
            "没有找到 products.json"
        )

    products = json.loads(
        PRODUCTS_FILE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(products, list):
        raise RuntimeError(
            "products.json最外层必须是数组"
        )

    enabled_products = []

    for product in products:
        if not isinstance(product, dict):
            continue

        if not product.get("enabled", True):
            continue

        name = str(
            product.get("name", "")
        ).strip()

        share_code = str(
            product.get("share_code", "")
        ).strip()

        registration_code = str(
            product.get(
                "registration_code",
                "",
            )
        ).strip()

        if not name or not share_code:
            print(
                "跳过信息不完整的产品：",
                product,
            )
            continue

        enabled_products.append(
            {
                "name": name,
                "share_code": share_code,
                "registration_code": (
                    registration_code
                ),
            }
        )

    if not enabled_products:
        raise RuntimeError(
            "products.json中没有启用产品"
        )

    return enabled_products


# ==========================================
# 读取已有历史数据
# ==========================================

def load_history():
    """
    优先读取nav_history.json。
    首次运行时，从nav_data.json建立初始记录。
    """

    if HISTORY_FILE.exists():
        history = json.loads(
            HISTORY_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(history, dict):
            return history

    history = {}

    if not SEED_FILE.exists():
        return history

    seed_data = json.loads(
        SEED_FILE.read_text(
            encoding="utf-8"
        )
    )

    for product in seed_data.get(
        "products",
        [],
    ):
        code = str(
            product.get(
                "share_code",
                "",
            )
        ).strip()

        nav_date = str(
            product.get(
                "nav_date",
                "",
            )
        ).strip()

        unit_nav = product.get(
            "unit_nav"
        )

        wan_return = product.get(
            "wan_return",
            0,
        )

        if (
            not code
            or not nav_date
            or unit_nav in (None, "")
        ):
            continue

        history[code] = [
            {
                "date": nav_date,
                "nav": float(unit_nav),
                "wan_return": float(
                    wan_return
                ),
            }
        ]

    return history


# ==========================================
# 北京银行公开净值接口
# ==========================================

def prepare_session():
    """访问公开净值页面，建立普通访问会话。"""

    try:
        response = SESSION.get(
            PAGE_URL,
            timeout=30,
        )

        print(
            "北京银行净值页面预访问：",
            response.status_code,
        )

    except Exception as error:
        print(
            "页面预访问提示：",
            type(error).__name__,
            error,
        )


def get_nav_records(share_code):
    """获取指定产品最近10个净值点。"""

    payload = {
        "pageNum": 1,
        "pageSize": 10,
        "titleId": TITLE_ID,
        "prodCode": share_code,
        "channel": 1,
        "language": "CN",
    }

    headers = {
        "Accept": (
            "application/json, "
            "text/plain, */*"
        ),
        "Content-Type": "application/json",
        "Origin": (
            "https://bankofbeijing.com.cn"
        ),
        "Referer": PAGE_URL,
    }

    response = SESSION.post(
        API_URL,
        json=payload,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    result = response.json()

    if result.get("code") != 0:
        print(
            f"{share_code}：接口返回异常，"
            f"code={result.get('code')}，"
            f"message={result.get('message')}"
        )
        return []

    records = (
        result.get("data", {})
        .get("records", [])
    )

    valid_records = []

    for record in records:
        product_code = str(
            record.get(
                "prdcode",
                "",
            )
        ).strip()

        nav_date = str(
            record.get(
                "navTime",
                "",
            )
        ).strip()

        nav_value = record.get("nav")

        if product_code != share_code:
            continue

        if nav_value in (None, ""):
            continue

        if not re.fullmatch(
            r"\d{8}",
            nav_date,
        ):
            continue

        try:
            nav_number = float(nav_value)
        except (TypeError, ValueError):
            continue

        if nav_number <= 0:
            continue

        valid_records.append(
            {
                "date": (
                    f"{nav_date[0:4]}-"
                    f"{nav_date[4:6]}-"
                    f"{nav_date[6:8]}"
                ),
                "nav": nav_number,
            }
        )

    unique_records = {}

    for record in valid_records:
        unique_records[
            record["date"]
        ] = record

    sorted_records = sorted(
        unique_records.values(),
        key=lambda item: item["date"],
    )

    if sorted_records:
        latest = sorted_records[-1]

        print(
            f"{share_code}：取得北京银行净值 "
            f"{latest['date']} "
            f"{latest['nav']}"
        )
    else:
        print(
            f"{share_code}："
            "北京银行接口未返回有效净值"
        )

    return sorted_records


# ==========================================
# 合并历史并计算万收
# ==========================================

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


def merge_product_history(
    history,
    share_code,
    api_records,
):
    """将接口数据合并到历史记录。"""

    current_records = history.setdefault(
        share_code,
        [],
    )

    record_map = {}

    for record in current_records:
        date_value = str(
            record.get("date", "")
        ).strip()

        nav_value = record.get("nav")

        if (
            not date_value
            or nav_value in (None, "")
        ):
            continue

        record_map[date_value] = {
            "date": date_value,
            "nav": float(nav_value),
            "wan_return": float(
                record.get(
                    "wan_return",
                    0,
                )
            ),
        }

    changed = False

    for record in api_records:
        date_value = record["date"]
        nav_value = float(
            record["nav"]
        )

        existing = record_map.get(
            date_value
        )

        if existing is None:
            record_map[date_value] = {
                "date": date_value,
                "nav": nav_value,
                "wan_return": 0.0,
            }
            changed = True

        elif existing["nav"] != nav_value:
            existing["nav"] = nav_value
            changed = True

    merged_records = sorted(
        record_map.values(),
        key=lambda item: item["date"],
    )

    for index, record in enumerate(
        merged_records
    ):
        if index == 0:
            record["wan_return"] = float(
                record.get(
                    "wan_return",
                    0,
                )
            )
            continue

        previous_nav = merged_records[
            index - 1
        ]["nav"]

        new_wan_return = (
            calculate_wan_return(
                record["nav"],
                previous_nav,
            )
        )

        if (
            record.get("wan_return")
            != new_wan_return
        ):
            record["wan_return"] = (
                new_wan_return
            )
            changed = True

    history[share_code] = (
        merged_records
    )

    return changed


# ==========================================
# 生成网页
# ==========================================

def escape_html(value):
    """处理网页特殊字符。"""

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def create_product_card(
    product,
    record,
):
    """生成一个产品卡片。"""

    wan_return = float(
        record.get(
            "wan_return",
            0,
        )
    )

    if wan_return > 0:
        return_class = "positive"
        return_text = (
            f"+{wan_return:.2f} 元"
        )

    elif wan_return < 0:
        return_class = "negative"
        return_text = (
            f"{wan_return:.2f} 元"
        )

    else:
        return_class = "neutral"
        return_text = "0.00 元"

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


def render_index(
    products,
    history,
):
    """根据产品清单自动生成网页。"""

    cards = []
    latest_dates = []

    for product in products:
        code = product["share_code"]

        records = history.get(
            code,
            [],
        )

        if not records:
            print(
                f"{product['name']}没有历史数据，"
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

  <title>哪吒攒钱买天官</title>

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

    .neutral {{
      color: #6b7280;
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

    @media (
      prefers-color-scheme: dark
    ) {{
      body {{
        background: #0f172a;
        color: #f3f4f6;
      }}

      .card {{
        background: #172033;
        border-color: #253047;
      }}

      .metric {{
        background: #202b40;
      }}

      .product-code,
      .label,
      .nav-date,
      .notice {{
        color: #a7b0c0;
      }}
    }}
  </style>
</head>

<body>
  <main>
    <section class="header">
      <h1>哪吒攒钱买天官</h1>

      <div class="update-time">
        哪吒攒钱 ｜ 数据日期：
        {overall_date}
      </div>
    </section>

    <section class="product-list">
      {''.join(cards)}
    </section>

    <div class="notice">
      数据来自北京银行公开披露渠道，
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


# ==========================================
# 主程序
# ==========================================

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
            api_records = get_nav_records(
                code
            )

        except Exception as error:
            print(
                f"{name}检查失败："
                f"{type(error).__name__}: "
                f"{error}"
            )
            continue

        if not api_records:
            print(
                f"{name}未取得有效净值"
            )
            continue

        success_count += 1

        changed = merge_product_history(
            history,
            code,
            api_records,
        )

        latest_record = api_records[-1]

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

    if success_count == 0:
        raise RuntimeError(
            "所有产品均未成功取得"
            "北京银行真实净值，"
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
