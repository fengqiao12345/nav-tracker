import json
import ssl
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter


# ==========================================
# 基础配置
# ==========================================

PRODUCT_LIST_PAGE = (
    "https://www.bankofbeijing.com.cn/"
    "personal/second/lccp"
    "?column=1555805279772381184"
)

PRODUCT_LIST_API = (
    "https://www.bankofbeijing.com.cn/"
    "api/wealth/callGenInfo"
)

SNAPSHOT_FILE = Path(
    "bank_products_snapshot.json"
)

OUTPUT_FILE = Path(
    "new_products.html"
)

MANAGER_NAME = "北银理财有限责任公司"

# 新品页面保留最近30天监测到的产品
DISPLAY_DAYS = 30

# 每页查询100条，程序自动翻页
PAGE_SIZE = 100


# ==========================================
# 兼容北京银行旧版SSL
# ==========================================

class LegacySSLAdapter(HTTPAdapter):
    """兼容北京银行网站的旧版SSL协商方式。"""

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
    "https://www.bankofbeijing.com.cn/",
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
# 页面访问与产品查询
# ==========================================

def prepare_session():
    """访问北京银行产品页面，建立普通会话。"""

    response = SESSION.get(
        PRODUCT_LIST_PAGE,
        timeout=30,
    )

    print(
        "北京银行产品页面预访问：",
        response.status_code,
    )


def build_payload(page_number):
    """生成产品列表查询参数。"""

    return {
        "bjyhHoldDays": "",
        "orderType": [],
        "prdAttr": "",
        "pminAmount": "",
        "riskLevel": "",
        "prdName": "",
        "prdCode": "",
        "currType": "",
        "isBuy": "",
        "pageNum": page_number,
        "pageSize": PAGE_SIZE,
        "channel": 1,
        "language": "CN",
    }


def fetch_product_page(page_number):
    """读取一页北京银行产品列表。"""

    headers = {
        "Accept": (
            "application/json, "
            "text/plain, */*"
        ),
        "Content-Type": "application/json",
        "Origin": (
            "https://www.bankofbeijing.com.cn"
        ),
        "Referer": PRODUCT_LIST_PAGE,
    }

    response = SESSION.post(
        PRODUCT_LIST_API,
        json=build_payload(page_number),
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    if result.get("code") != 0:
        raise RuntimeError(
            "北京银行产品列表接口返回异常："
            f"{result.get('message')}"
        )

    data = result.get("data", {})

    products = data.get("list", [])

    total = int(
        data.get("total", 0)
    )

    return products, total


def is_rmb_product(product):
    """
    排除明显的美元产品。

    当前公开接口没有稳定返回币种字段，
    因此结合产品名称和起购金额判断。
    """

    name = str(
        product.get("prdName", "")
    )

    first_amount = str(
        product.get("pfirstAmt", "")
    )

    dollar_words = (
        "美元",
        "现钞",
        "现汇",
        "USD",
    )

    combined_text = (
        name + " " + first_amount
    ).upper()

    return not any(
        word.upper() in combined_text
        for word in dollar_words
    )


def normalize_product(product):
    """提取新品页面需要的产品信息。"""

    return {
        "code": str(
            product.get("prdcode", "")
        ).strip(),
        "name": str(
            product.get("prdName", "")
        ).strip(),
        "manager": str(
            product.get(
                "prdManagerName",
                "",
            )
        ).strip(),
        "holding_period": str(
            product.get(
                "bjyhHoldDaysName",
                "",
            )
        ).strip(),
        "subscribe_type": str(
            product.get("ss", "")
        ).strip(),
        "first_amount": str(
            product.get(
                "pfirstAmt",
                "",
            )
        ).strip(),
        "risk_name": str(
            product.get(
                "riskName",
                "",
            )
        ).strip(),
        "product_type": str(
            product.get(
                "prdAttrName",
                "",
            )
        ).strip(),
        "income_rate": str(
            product.get(
                "incomeRate",
                "",
            )
        ).strip(),
    }


def fetch_all_bob_products():
    """
    读取北京银行全部产品，
    只保留北银理财人民币产品。
    """

    products, total = fetch_product_page(1)

    all_products = list(products)

    total_pages = max(
        1,
        (
            total + PAGE_SIZE - 1
        ) // PAGE_SIZE,
    )

    print(
        f"北京银行产品总数：{total}，"
        f"共{total_pages}页"
    )

    for page_number in range(
        2,
        total_pages + 1,
    ):
        page_products, _ = (
            fetch_product_page(
                page_number
            )
        )

        all_products.extend(
            page_products
        )

    selected = {}

    for product in all_products:
        manager = str(
            product.get(
                "prdManagerName",
                "",
            )
        ).strip()

        code = str(
            product.get(
                "prdcode",
                "",
            )
        ).strip()

        if manager != MANAGER_NAME:
            continue

        if not code:
            continue

        if not is_rmb_product(product):
            continue

        selected[code] = (
            normalize_product(product)
        )

    print(
        "北京银行渠道北银理财人民币产品数：",
        len(selected),
    )

    return selected


# ==========================================
# 快照管理
# ==========================================

def load_snapshot():
    """读取已有产品快照。"""

    if not SNAPSHOT_FILE.exists():
        return {}

    try:
        snapshot = json.loads(
            SNAPSHOT_FILE.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError:
        return {}

    if not isinstance(snapshot, dict):
        return {}

    return snapshot


def save_snapshot(snapshot):
    """保存最新产品快照。"""

    SNAPSHOT_FILE.write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def update_snapshot(current_products):
    """
    第一次运行只建立基准，不把存量产品列为新品。

    第二次及以后运行时，
    新出现的产品代码会被记录为新品。
    """

    snapshot = load_snapshot()

    today = date.today().isoformat()

    if not snapshot.get("initialized"):
        baseline_products = {}

        for code, product in (
            current_products.items()
        ):
            baseline_products[code] = {
                **product,
                "first_seen": today,
                "is_baseline": True,
                "last_seen": today,
            }

        new_snapshot = {
            "initialized": True,
            "baseline_date": today,
            "updated_at": (
                datetime.now()
                .astimezone()
                .isoformat(
                    timespec="seconds"
                )
            ),
            "products": baseline_products,
        }

        save_snapshot(new_snapshot)

        print(
            "首次运行：已建立产品基准，"
            "本次不生成存量新品。"
        )

        return new_snapshot, []

    saved_products = snapshot.get(
        "products",
        {},
    )

    new_products = []

    for code, product in (
        current_products.items()
    ):
        if code not in saved_products:
            saved_products[code] = {
                **product,
                "first_seen": today,
                "is_baseline": False,
                "last_seen": today,
            }

            new_products.append(
                saved_products[code]
            )

            print(
                f"发现新品："
                f"{product['name']} / {code}"
            )

        else:
            first_seen = saved_products[
                code
            ].get(
                "first_seen",
                today,
            )

            is_baseline = saved_products[
                code
            ].get(
                "is_baseline",
                True,
            )

            saved_products[code] = {
                **product,
                "first_seen": first_seen,
                "is_baseline": is_baseline,
                "last_seen": today,
            }

    snapshot["products"] = (
        saved_products
    )

    snapshot["updated_at"] = (
        datetime.now()
        .astimezone()
        .isoformat(
            timespec="seconds"
        )
    )

    save_snapshot(snapshot)

    return snapshot, new_products


# ==========================================
# 新品页面生成
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


def get_recent_new_products(snapshot):
    """读取最近30天发现的新品。"""

    cutoff_date = (
        date.today()
        - timedelta(
            days=DISPLAY_DAYS
        )
    )

    recent = []

    for product in snapshot.get(
        "products",
        {},
    ).values():
        if product.get(
            "is_baseline",
            True,
        ):
            continue

        first_seen_text = product.get(
            "first_seen",
            "",
        )

        try:
            first_seen_date = (
                date.fromisoformat(
                    first_seen_text
                )
            )
        except ValueError:
            continue

        if first_seen_date < cutoff_date:
            continue

        recent.append(product)

    recent.sort(
        key=lambda item: (
            item.get(
                "first_seen",
                "",
            ),
            item.get(
                "code",
                "",
            ),
        ),
        reverse=True,
    )

    return recent


def create_product_card(product):
    """生成新品卡片。"""

    income_rate = product.get(
        "income_rate",
        "",
    )

    income_html = ""

    if (
        income_rate
        and income_rate not in (
            "0",
            "0%",
            "-",
        )
    ):
        income_html = f"""
        <div class="info-item">
          <span>页面展示收益</span>
          <strong>
            {escape_html(income_rate)}
          </strong>
        </div>
        """

    return f"""
    <article class="card">
      <div class="new-tag">
        北京银行新上架
      </div>

      <h2>
        {escape_html(product.get("name", ""))}
      </h2>

      <div class="code">
        产品代码：
        {escape_html(product.get("code", ""))}
      </div>

      <div class="info-grid">
        <div class="info-item">
          <span>持有期限</span>
          <strong>
            {escape_html(
                product.get(
                    "holding_period",
                    "-",
                )
            )}
          </strong>
        </div>

        <div class="info-item">
          <span>风险等级</span>
          <strong>
            {escape_html(
                product.get(
                    "risk_name",
                    "-",
                )
            )}
          </strong>
        </div>

        <div class="info-item">
          <span>起购金额</span>
          <strong>
            {escape_html(
                product.get(
                    "first_amount",
                    "-",
                )
            )}
          </strong>
        </div>

        <div class="info-item">
          <span>申赎方式</span>
          <strong>
            {escape_html(
                product.get(
                    "subscribe_type",
                    "-",
                )
            )}
          </strong>
        </div>

        {income_html}
      </div>

      <div class="first-seen">
        首次监测到：
        {escape_html(
            product.get(
                "first_seen",
                "",
            )
        )}
      </div>
    </article>
    """


def render_new_products_page(snapshot):
    """生成北京银行新品监测页面。"""

    recent_products = (
        get_recent_new_products(
            snapshot
        )
    )

    if recent_products:
        cards_html = "".join(
            create_product_card(product)
            for product in recent_products
        )

        empty_html = ""
    else:
        cards_html = ""

        empty_html = """
        <div class="empty">
          <div class="empty-icon">✓</div>
          <div class="empty-title">
            暂无新上架产品
          </div>
          <div class="empty-text">
            已完成当前产品基准建立。<br>
            后续北京银行新出现的北银理财人民币产品，
            将自动显示在这里。
          </div>
        </div>
        """

    update_time = snapshot.get(
        "updated_at",
        "",
    )

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

  <title>哪吒攒钱｜北京银行新品</title>

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
      padding: 18px 14px 40px;
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
        rgba(23,54,93,0.18);
    }}

    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
    }}

    .sub {{
      font-size: 13px;
      line-height: 1.6;
      opacity: 0.9;
    }}

    .nav {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 14px;
    }}

    .nav a {{
      padding: 11px;
      border-radius: 11px;
      text-align: center;
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
    }}

    .nav .home {{
      background: white;
      color: #17365d;
      border: 1px solid #dce4ef;
    }}

    .nav .current {{
      background: #17365d;
      color: white;
    }}

    .list {{
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }}

    .card {{
      position: relative;
      padding: 17px;
      background: white;
      border: 1px solid #eef1f5;
      border-radius: 16px;
      box-shadow:
        0 3px 12px
        rgba(15,23,42,0.06);
    }}

    .new-tag {{
      display: inline-block;
      margin-bottom: 10px;
      padding: 5px 9px;
      border-radius: 999px;
      background: #fff1f1;
      color: #c62828;
      font-size: 12px;
      font-weight: 700;
    }}

    h2 {{
      margin: 0 0 5px;
      font-size: 18px;
    }}

    .code {{
      color: #6b7280;
      font-size: 12px;
    }}

    .info-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 9px;
      margin-top: 14px;
    }}

    .info-item {{
      padding: 10px;
      background: #f7f9fc;
      border-radius: 11px;
    }}

    .info-item span {{
      display: block;
      margin-bottom: 5px;
      color: #6b7280;
      font-size: 12px;
    }}

    .info-item strong {{
      font-size: 14px;
    }}

    .first-seen {{
      margin-top: 12px;
      color: #6b7280;
      font-size: 12px;
    }}

    .empty {{
      margin-top: 14px;
      padding: 42px 20px;
      background: white;
      border-radius: 16px;
      text-align: center;
      border: 1px solid #eef1f5;
    }}

    .empty-icon {{
      width: 44px;
      height: 44px;
      margin: 0 auto 12px;
      border-radius: 50%;
      background: #e8f7ec;
      color: #16803c;
      font-size: 25px;
      line-height: 44px;
      font-weight: 700;
    }}

    .empty-title {{
      font-size: 18px;
      font-weight: 700;
    }}

    .empty-text {{
      margin-top: 8px;
      color: #6b7280;
      font-size: 13px;
      line-height: 1.7;
    }}

    .notice {{
      margin-top: 15px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.7;
    }}
  </style>
</head>

<body>
  <main>
    <section class="header">
      <h1>北京银行新品</h1>

      <div class="sub">
        只监测北京银行公开产品列表中新出现的
        北银理财人民币产品。<br>
        最近更新：{escape_html(update_time)}
      </div>
    </section>

    <nav class="nav">
      <a
        class="home"
        href="index.html">
        净值追踪
      </a>

      <a
        class="current"
        href="new_products.html">
        新品监测
      </a>
    </nav>

    <section class="list">
      {cards_html}
      {empty_html}
    </section>

    <div class="notice">
      说明：本页面所称“新品”，是指程序首次监测到
      该产品出现在北京银行公开产品列表中，
      不代表该产品仅由北京银行独家销售，
      也不代表产品当日正式成立。
      实际销售信息以北京银行APP及正式销售文件为准。
    </div>
  </main>
</body>
</html>
"""

    OUTPUT_FILE.write_text(
        html,
        encoding="utf-8",
    )


# ==========================================
# 主程序
# ==========================================

def main():
    prepare_session()

    current_products = (
        fetch_all_bob_products()
    )

    if not current_products:
        raise RuntimeError(
            "未取得北京银行渠道"
            "北银理财人民币产品，"
            "本次不更新快照"
        )

    snapshot, new_products = (
        update_snapshot(
            current_products
        )
    )

    render_new_products_page(
        snapshot
    )

    print(
        "新品监测执行完成："
        f"本次发现{len(new_products)}只新品"
    )


if __name__ == "__main__":
    main()
