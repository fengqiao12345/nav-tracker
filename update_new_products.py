import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup


# ==========================================
# 基础配置
# ==========================================

BASE_URL = (
    "https://www.beijingbobwealth.com.cn"
)

ANNOUNCEMENT_PATH = (
    "/xxpl/cpgg/fxgg/"
)

ANNOUNCEMENT_PAGE = (
    BASE_URL
    + ANNOUNCEMENT_PATH
    + "index.html"
)

# 使用新的快照文件，避免与旧的北京银行产品快照混淆
SNAPSHOT_FILE = Path(
    "bob_issuance_snapshot.json"
)

OUTPUT_FILE = Path(
    "new_products.html"
)

MANAGER_NAME = "北银理财有限责任公司"

# 页面展示最近7天发布或发现的新品
DISPLAY_DAYS = 7

# 每次读取发行公告最近3页
FETCH_PAGES = 3


SESSION = requests.Session()

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
# 网页读取与公告解析
# ==========================================

def normalize_text(value):
    """清理网页文字中的空格和换行。"""

    return " ".join(
        str(value or "").split()
    )


def build_page_url(page_number):
    """生成发行公告分页网址。"""

    if page_number == 1:
        file_name = "index.html"
    else:
        file_name = (
            f"index{page_number}.html"
        )

    return (
        BASE_URL
        + ANNOUNCEMENT_PATH
        + file_name
    )


def prepare_session():
    """访问北银理财发行公告首页。"""

    response = SESSION.get(
        ANNOUNCEMENT_PAGE,
        headers={
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Referer": BASE_URL + "/",
        },
        timeout=30,
    )

    response.raise_for_status()

    print(
        "北银理财发行公告页面预访问：",
        response.status_code,
    )


def extract_announcement_date(
    title,
    nearby_text,
    href,
):
    """从标题、周边文字或链接中提取公告日期。"""

    combined_text = (
        f"{title} "
        f"{nearby_text} "
        f"{href}"
    )

    matches = re.findall(
        r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}",
        combined_text,
    )

    for value in reversed(matches):
        value = value.replace(
            "/",
            "-",
        )

        parts = value.split("-")

        if len(parts) != 3:
            continue

        normalized_value = (
            f"{parts[0]}-"
            f"{int(parts[1]):02d}-"
            f"{int(parts[2]):02d}"
        )

        try:
            parsed_date = (
                date.fromisoformat(
                    normalized_value
                )
            )

            return (
                parsed_date.isoformat()
            )

        except ValueError:
            continue

    return ""


def clean_product_name(title):
    """清理发行公告标题。"""

    name = normalize_text(title)

    name = re.sub(
        r"[_\-—]?\s*"
        r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}"
        r"\s*$",
        "",
        name,
    )

    name = re.sub(
        r"理财产品发行公告$",
        "",
        name,
    )

    name = re.sub(
        r"发行公告$",
        "",
        name,
    )

    name = name.strip(
        " _-—"
    )

    return name


def extract_product_code(
    title,
    href,
):
    """
    尝试提取产品代码。

    如果公告标题和链接中没有销售代码，
    使用公告链接生成稳定编号。
    """

    combined_text = (
        f"{title} {href}"
    ).upper()

    patterns = (
        r"\b[A-Z]{1,5}\d{6,}[A-Z]?\b",
        r"\b\d{6,}[A-Z]\b",
    )

    for pattern in patterns:
        matches = re.findall(
            pattern,
            combined_text,
        )

        if matches:
            return matches[-1]

    digest = hashlib.sha256(
        href.encode("utf-8")
    ).hexdigest()[:12].upper()

    return f"GG{digest}"


def extract_holding_period(name):
    """从产品名称中识别持有期限。"""

    match = re.search(
        r"(\d+\s*天持有期)",
        name,
    )

    if match:
        return (
            match.group(1)
            .replace(" ", "")
        )

    if "封闭式" in name:
        return "封闭式"

    if "每日开放" in name:
        return "每日开放"

    return "-"


def is_rmb_issuance(title):
    """识别人民币理财产品发行公告。"""

    text = normalize_text(
        title
    ).upper()

    if "发行公告" not in text:
        return False

    if "理财产品" not in text:
        return False

    dollar_words = (
        "美元",
        "USD",
        "现钞",
        "现汇",
    )

    if any(
        word.upper() in text
        for word in dollar_words
    ):
        return False

    return True


def fetch_announcement_page(
    page_number,
):
    """读取并解析一页北银理财发行公告。"""

    page_url = build_page_url(
        page_number
    )

    response = SESSION.get(
        page_url,
        headers={
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Referer": (
                BASE_URL + "/"
            ),
            "Cache-Control": "no-cache",
        },
        timeout=30,
    )

    response.raise_for_status()

    # 北银理财网页使用UTF-8编码
    response.encoding = "utf-8"

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    products = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):
        raw_href = str(
            link.get(
                "href",
                "",
            )
        ).strip()

        if not raw_href:
            continue

        href = urljoin(
            page_url,
            raw_href,
        )

        decoded_href = unquote(
            href
        )

        # 只处理PDF发行公告
        if ".pdf" not in decoded_href.lower():
            continue

        link_text = normalize_text(
            link.get_text(
                " ",
                strip=True,
            )
        )

        # 标题可能放在父级元素中
        parent_text = ""

        if link.parent:
            parent_text = normalize_text(
                link.parent.get_text(
                    " ",
                    strip=True,
                )
            )

        # 如果父级文字仍不完整，再读取上一级
        grandparent_text = ""

        if (
            link.parent
            and link.parent.parent
        ):
            grandparent_text = normalize_text(
                link.parent.parent.get_text(
                    " ",
                    strip=True,
                )
            )

        combined_text = normalize_text(
            f"{link_text} "
            f"{parent_text} "
            f"{grandparent_text} "
            f"{decoded_href}"
        )

        # 必须是发行公告
        if "发行公告" not in combined_text:
            continue

        # 必须与理财产品有关
        if (
            "理财产品" not in combined_text
            and "理财管理计划" not in combined_text
        ):
            continue

        # 排除美元产品
        upper_text = combined_text.upper()

        if any(
            word in upper_text
            for word in (
                "美元",
                "USD",
                "现钞",
                "现汇",
            )
        ):
            continue

        # 优先使用网页中的可见标题
        title = link_text

        if (
            len(parent_text)
            > len(title)
        ):
            title = parent_text

        # 可见标题为空时，从PDF文件名获取
        if not title:
            title = (
                decoded_href
                .split("/")[-1]
                .replace(".pdf", "")
            )

        # 如果标题中不包含发行公告，
        # 使用解码后的PDF文件名
        if "发行公告" not in title:
            file_title = (
                decoded_href
                .split("/")[-1]
                .replace(".pdf", "")
            )

            if "发行公告" in file_title:
                title = file_title

        product_name = clean_product_name(
            title
        )

        announcement_date = (
            extract_announcement_date(
                title,
                combined_text,
                decoded_href,
            )
        )

        product_code = (
            extract_product_code(
                title,
                decoded_href,
            )
        )

        products[product_code] = {
            "code": product_code,
            "name": product_name,
            "manager": MANAGER_NAME,
            "holding_period": (
                extract_holding_period(
                    product_name
                )
            ),
            "subscribe_type": (
                "发行公告"
            ),
            "first_amount": "-",
            "risk_name": "-",
            "product_type": (
                "人民币理财产品"
            ),
            "income_rate": "",
            "announcement_date": (
                announcement_date
            ),
            "announcement_url": href,
        }

    print(
        f"北银理财发行公告第"
        f"{page_number}页："
        f"取得{len(products)}条"
        f"人民币产品公告"
    )

    return products

def fetch_all_bob_products():
    """
    读取北银理财发行公告最近几页。

    只保留人民币理财产品发行公告。
    """

    selected = {}

    successful_pages = 0

    for page_number in range(
        1,
        FETCH_PAGES + 1,
    ):
        try:
            page_products = (
                fetch_announcement_page(
                    page_number
                )
            )

            successful_pages += 1

            selected.update(
                page_products
            )

        except Exception as error:
            print(
                f"北银理财发行公告"
                f"第{page_number}页读取失败："
                f"{type(error).__name__}: "
                f"{error}"
            )

    if successful_pages == 0:
        raise RuntimeError(
            "北银理财发行公告页面"
            "全部读取失败"
        )

    print(
        "北银理财近期人民币"
        "发行公告数：",
        len(selected),
    )

    return selected


# ==========================================
# 快照管理
# ==========================================

def load_snapshot():
    """读取发行公告历史快照。"""

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

    if not isinstance(
        snapshot,
        dict,
    ):
        return {}

    return snapshot


def save_snapshot(snapshot):
    """保存发行公告历史快照。"""

    SNAPSHOT_FILE.write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def should_show_on_first_run(
    product,
    today,
):
    """
    第一次运行时显示最近7天的发行公告。

    更早公告只作为基准保存，
    不在新品页面大量展示。
    """

    announcement_text = (
        product.get(
            "announcement_date",
            "",
        )
    )

    try:
        announcement_date = (
            date.fromisoformat(
                announcement_text
            )
        )

    except ValueError:
        return False

    cutoff_date = (
        today
        - timedelta(
            days=DISPLAY_DAYS
        )
    )

    return (
        announcement_date
        >= cutoff_date
    )


def update_snapshot(current_products):
    """
    更新发行公告快照。

    第一次运行时：
    最近7天公告显示为新品，
    更早公告作为历史基准。
    """

    snapshot = load_snapshot()

    today = date.today()

    today_text = (
        today.isoformat()
    )

    if not snapshot.get(
        "initialized"
    ):
        baseline_products = {}

        initial_new_products = []

        for code, product in (
            current_products.items()
        ):
            show_product = (
                should_show_on_first_run(
                    product,
                    today,
                )
            )

            saved_product = {
                **product,
                "first_seen": today_text,
                "is_baseline": (
                    not show_product
                ),
                "last_seen": today_text,
            }

            baseline_products[
                code
            ] = saved_product

            if show_product:
                initial_new_products.append(
                    saved_product
                )

        new_snapshot = {
            "initialized": True,
            "source": (
                "北银理财发行公告"
            ),
            "baseline_date": (
                today_text
            ),
            "updated_at": (
                datetime.now()
                .astimezone()
                .isoformat(
                    timespec="seconds"
                )
            ),
            "products": (
                baseline_products
            ),
        }

        save_snapshot(
            new_snapshot
        )

        print(
            "首次运行：已建立发行公告基准，"
            f"最近{DISPLAY_DAYS}天识别到"
            f"{len(initial_new_products)}只新品。"
        )

        return (
            new_snapshot,
            initial_new_products,
        )

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
                "first_seen": today_text,
                "is_baseline": False,
                "last_seen": today_text,
            }

            new_products.append(
                saved_products[code]
            )

            print(
                "发现新品："
                f"{product['name']} "
                f"/ {code}"
            )

        else:
            old_product = (
                saved_products[code]
            )

            first_seen = (
                old_product.get(
                    "first_seen",
                    today_text,
                )
            )

            is_baseline = (
                old_product.get(
                    "is_baseline",
                    True,
                )
            )

            saved_products[code] = {
                **product,
                "first_seen": (
                    first_seen
                ),
                "is_baseline": (
                    is_baseline
                ),
                "last_seen": (
                    today_text
                ),
            }

    snapshot["source"] = (
        "北银理财发行公告"
    )

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


def get_recent_new_products(
    snapshot,
):
    """读取最近7天发布或发现的新品。"""

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

        announcement_text = (
            product.get(
                "announcement_date",
                "",
            )
        )

        first_seen_text = (
            product.get(
                "first_seen",
                "",
            )
        )

        relevant_date = None

        for text_value in (
            announcement_text,
            first_seen_text,
        ):
            try:
                value_date = (
                    date.fromisoformat(
                        text_value
                    )
                )

            except ValueError:
                continue

            if (
                relevant_date is None
                or value_date
                > relevant_date
            ):
                relevant_date = (
                    value_date
                )

        if relevant_date is None:
            continue

        if relevant_date < cutoff_date:
            continue

        recent.append(product)

    recent.sort(
        key=lambda item: (
            item.get(
                "announcement_date",
                "",
            ),
            item.get(
                "first_seen",
                "",
            ),
            item.get(
                "name",
                "",
            ),
        ),
        reverse=True,
    )

    return recent


def create_product_card(product):
    """生成新品卡片。"""

    announcement_url = (
        escape_html(
            product.get(
                "announcement_url",
                "",
            )
        )
    )

    announcement_date = (
        product.get(
            "announcement_date",
            "",
        )
        or "-"
    )

    link_html = ""

    if announcement_url:
        link_html = f"""
        {announcement_url}
          查看发行公告
        </a>
        """

    return f"""
    <article class="card">
      <div class="new-tag">
        北银理财新发行
      </div>

      <h2>
        {escape_html(
            product.get(
                "name",
                "",
            )
        )}
      </h2>

      <div class="code">
        公告标识：
        {escape_html(
            product.get(
                "code",
                "",
            )
        )}
      </div>

      <div class="info-grid">
        <div class="info-item">
          <span>公告日期</span>
          <strong>
            {escape_html(
                announcement_date
            )}
          </strong>
        </div>

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
          <span>产品类型</span>
          <strong>
            人民币理财产品
          </strong>
        </div>

        <div class="info-item">
          <span>公告类型</span>
          <strong>
            发行公告
          </strong>
        </div>
      </div>

      <div class="card-footer">
        <div class="first-seen">
          首次监测到：
          {escape_html(
              product.get(
                  "first_seen",
                  "",
              )
          )}
        </div>

        {link_html}
      </div>
    </article>
    """


def render_new_products_page(
    snapshot,
):
    """生成北银理财新品监测页面。"""

    recent_products = (
        get_recent_new_products(
            snapshot
        )
    )

    if recent_products:
        cards_html = "".join(
            create_product_card(
                product
            )
            for product
            in recent_products
        )

        empty_html = ""

    else:
        cards_html = ""

        empty_html = """
        <div class="empty">
          <div class="empty-icon">✓</div>

          <div class="empty-title">
            最近7天暂无新发行公告
          </div>

          <div class="empty-text">
            已完成北银理财发行公告基准建立。<br>
            后续出现新的人民币理财产品发行公告，
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

  <title>哪吒攒钱｜北银理财新品</title>

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
      line-height: 1.5;
    }}

    .code {{
      color: #6b7280;
      font-size: 12px;
      word-break: break-all;
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

    .card-footer {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-top: 12px;
    }}

    .first-seen {{
      color: #6b7280;
      font-size: 12px;
    }}

    .announcement-link {{
      color: #17365d;
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
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

    @media (
      max-width: 480px
    ) {{
      .info-grid {{
        grid-template-columns:
          1fr 1fr;
      }}

      .card-footer {{
        align-items: flex-start;
        flex-direction: column;
      }}
    }}
  </style>
</head>

<body>
  <main>
    <section class="header">
      <h1>北银理财新品</h1>

      <div class="sub">
        监测北银理财官网发行公告中新出现的
        人民币理财产品。<br>
        最近更新：
        {escape_html(update_time)}
      </div>
    </section>

    <nav class="nav">
      <a
        class="home"
        href="index.html">
        净值追踪
      </a>

      new_products.html
        新品监测
      </a>
    </nav>

    <section class="list">
      {cards_html}
      {empty_html}
    </section>

    <div class="notice">
      说明：本页面所称“新品”，是指程序首次监测到
      该产品出现在北银理财官网发行公告中。
      公告发布不等于产品当日正式成立，
      也不代表已在全部销售渠道上架。
      具体发行、成立和销售信息，
      以北银理财正式公告及销售文件为准。
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
            "未取得北银理财"
            "人民币产品发行公告，"
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
        f"本次发现"
        f"{len(new_products)}只新品"
    )


if __name__ == "__main__":
    main()
