import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


# ==========================================
# 基础配置
# ==========================================

BASE_URL = "https://www.beijingbobwealth.com.cn"

ANNOUNCEMENT_PATH = "/xxpl/cpgg/fxgg/"

ANNOUNCEMENT_PAGE = (
    BASE_URL
    + ANNOUNCEMENT_PATH
    + "index.html"
)

SNAPSHOT_FILE = Path(
    "bob_issuance_snapshot.json"
)

OUTPUT_FILE = Path(
    "new_products.html"
)

MANAGER_NAME = "北银理财有限责任公司"

# 页面显示最近7天发布或发现的新品
DISPLAY_DAYS = 7

# 每次检查最近3页发行公告
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
# 网页及公告解析
# ==========================================

def normalize_text(value):
    """清理文字中的多余空格和换行。"""

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
    """预访问北银理财发行公告首页。"""

    response = SESSION.get(
        ANNOUNCEMENT_PAGE,
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
    """从标题、周边文字和链接中提取日期。"""

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
            return date.fromisoformat(
                normalized_value
            ).isoformat()

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

    return name.strip(
        " _-—"
    )


def extract_product_code(
    title,
    href,
):
    """
    从标题或链接中提取产品代码。

    没有公开销售代码时，
    根据公告链接生成稳定标识。
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


def extract_fundraising_scale(
    pdf_url,
):
    """
    从PDF正文中提取产品募集规模。

    发行公告未披露募集规模时，
    页面显示“未披露”。
    """

    if not pdf_url:
        return "未披露"

    try:
        response = SESSION.get(
            pdf_url,
            headers={
                "Referer": (
                    BASE_URL + "/"
                ),
            },
            timeout=45,
        )

        response.raise_for_status()

        reader = PdfReader(
            io.BytesIO(
                response.content
            )
        )

        text_parts = []

        # 通常关键信息在前几页
        for page in reader.pages[:6]:
            text_parts.append(
                page.extract_text()
                or ""
            )

        full_text = normalize_text(
            " ".join(text_parts)
        )

        patterns = (
            (
                r"产品募集规模"
                r"[\s：:]*"
                r"([0-9,，.]+)"
                r"\s*(亿元|万元|元)"
            ),
            (
                r"份额募集规模"
                r"[\s：:]*"
                r"([0-9,，.]+)"
                r"\s*(亿元|万元|元)"
            ),
            (
                r"募集规模"
                r"[\s：:]*"
                r"([0-9,，.]+)"
                r"\s*(亿元|万元|元)"
            ),
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                full_text,
            )

            if not match:
                continue

            number = (
                match.group(1)
                .replace("，", ",")
            )

            unit = match.group(2)

            return f"{number}{unit}"

    except Exception as error:
        print(
            "募集规模提取失败："
            f"{type(error).__name__}: "
            f"{error}"
        )

    return "未披露"


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

        # 只处理PDF公告
        if (
            ".pdf"
            not in decoded_href.lower()
        ):
            continue

        link_text = normalize_text(
            link.get_text(
                " ",
                strip=True,
            )
        )

        parent_text = ""

        if link.parent:
            parent_text = normalize_text(
                link.parent.get_text(
                    " ",
                    strip=True,
                )
            )

        grandparent_text = ""

        if (
            link.parent
            and link.parent.parent
        ):
            grandparent_text = (
                normalize_text(
                    link.parent.parent.get_text(
                        " ",
                        strip=True,
                    )
                )
            )

        combined_text = normalize_text(
            f"{link_text} "
            f"{parent_text} "
            f"{grandparent_text} "
            f"{decoded_href}"
        )

        if "发行公告" not in combined_text:
            continue

        if (
            "理财产品"
            not in combined_text
            and "理财管理计划"
            not in combined_text
        ):
            continue

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

        file_title = (
            decoded_href
            .split("/")[-1]
            .replace(".pdf", "")
        )

        title = max(
            (
                link_text,
                parent_text,
                file_title,
            ),
            key=len,
        )

        if (
            "发行公告" not in title
            and "发行公告"
            in file_title
        ):
            title = file_title

        product_name = (
            clean_product_name(
                title
            )
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
            "product_type": (
                "人民币理财产品"
            ),
            "announcement_date": (
                announcement_date
            ),
            "announcement_url": href,
            "fundraising_scale": (
                extract_fundraising_scale(
                    href
                )
            ),
        }

    print(
        f"北银理财发行公告第"
        f"{page_number}页："
        f"取得{len(products)}条"
        f"人民币产品公告"
    )

    return products


def fetch_all_bob_products():
    """读取最近几页人民币产品发行公告。"""

    selected = {}

    successful_pages = 0

    for page_number in range(
        1,
        FETCH_PAGES + 1,
    ):
        try:
            selected.update(
                fetch_announcement_page(
                    page_number
                )
            )

            successful_pages += 1

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


def update_snapshot(
    current_products,
):
    """更新发行公告历史快照。"""

    snapshot = load_snapshot()

    today = date.today()

    today_text = (
        today.isoformat()
    )

    cutoff_date = (
        today
        - timedelta(
            days=DISPLAY_DAYS
        )
    )

    if not snapshot.get(
        "initialized"
    ):
        saved_products = {}

        initial_new_products = []

        for code, product in (
            current_products.items()
        ):
            try:
                announcement_date = (
                    date.fromisoformat(
                        product.get(
                            "announcement_date",
                            "",
                        )
                    )
                )

            except ValueError:
                announcement_date = None

            show_product = (
                announcement_date
                is not None
                and announcement_date
                >= cutoff_date
            )

            saved_product = {
                **product,
                "first_seen": today_text,
                "is_baseline": (
                    not show_product
                ),
                "last_seen": today_text,
            }

            saved_products[
                code
            ] = saved_product

            if show_product:
                initial_new_products.append(
                    saved_product
                )

        snapshot = {
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
            "products": saved_products,
        }

        save_snapshot(snapshot)

        print(
            f"首次运行：最近"
            f"{DISPLAY_DAYS}天识别到"
            f"{len(initial_new_products)}只新品"
        )

        return (
            snapshot,
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
                f"发现新品："
                f"{product['name']} "
                f"/ {code}"
            )

        else:
            old_product = (
                saved_products[code]
            )

            saved_products[code] = {
                **product,
                "first_seen": (
                    old_product.get(
                        "first_seen",
                        today_text,
                    )
                ),
                "is_baseline": (
                    old_product.get(
                        "is_baseline",
                        True,
                    )
                ),
                "last_seen": today_text,
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
# 页面生成
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

        possible_dates = []

        for field_name in (
            "announcement_date",
            "first_seen",
        ):
            try:
                possible_dates.append(
                    date.fromisoformat(
                        product.get(
                            field_name,
                            "",
                        )
                    )
                )

            except ValueError:
                continue

        if not possible_dates:
            continue

        if max(
            possible_dates
        ) < cutoff_date:
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

    link_html = ""

    if announcement_url:
        link_html = (
            '<a class="announcement-link" '
            f'href="{announcement_url}" '
            'target="_blank" '
            'rel="noopener noreferrer">'
            '查看发行公告'
            '</a>'
        )

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
                product.get(
                    "announcement_date",
                    "-",
                )
                or "-"
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
        <div class="fundraising">
          产品募集规模：
          <strong>
            {escape_html(
                product.get(
                    "fundraising_scale",
                    "未披露",
                )
            )}
          </strong>
        </div>

        {link_html}
      </div>
    </article>
    """


def render_new_products_page(
    snapshot,
):
    """生成北银理财新品监测页面。"""

    products = (
        get_recent_new_products(
            snapshot
        )
    )

    if products:
        cards_html = "".join(
            create_product_card(
                product
            )
            for product in products
        )

    else:
        cards_html = """
        <div class="empty">
          <div class="empty-icon">✓</div>

          <div class="empty-title">
            最近7天暂无新发行公告
          </div>

          <div class="empty-text">
            后续出现新的人民币理财产品发行公告，
            将自动显示在这里。
          </div>
        </div>
        """

    update_time = escape_html(
        snapshot.get(
            "updated_at",
            "",
        )
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

    .fundraising {{
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

    .image-actions {{
      margin-top: 15px;
    }}

    .image-actions button {{
      width: 100%;
      padding: 13px;
      border: 0;
      border-radius: 12px;
      background: #17365d;
      color: white;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
    }}

    .image-actions button:disabled {{
      opacity: 0.65;
      cursor: wait;
    }}

    .image-result {{
      display: none;
      margin-top: 14px;
    }}

    .image-result.show {{
      display: block;
    }}

    .image-result img {{
      display: block;
      width: 100%;
      height: auto;
      border-radius: 12px;
      -webkit-touch-callout: default;
      user-select: auto;
    }}

    .save-tip {{
      margin-bottom: 10px;
      padding: 12px;
      border-radius: 10px;
      background: #fff7df;
      color: #7a4b00;
      text-align: center;
      font-size: 14px;
      line-height: 1.6;
    }}

    @media (
      max-width: 480px
    ) {{
      .card-footer {{
        align-items: flex-start;
        flex-direction: column;
      }}
    }}
  </style>

  <script
    src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js">
  </script>
</head>

<body>
  <main>
    <div id="capture-area">
      <section class="header">
        <h1>北银理财新品</h1>

        <div class="sub">
          监测北银理财官网发行公告中新出现的
          人民币理财产品。<br>
          最近更新：{update_time}
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
      </section>

      <div class="notice">
        说明：本页面所称“新品”，是指程序首次监测到
        该产品出现在北银理财官网发行公告中。
        公告发布不等于产品当日正式成立，
        也不代表已在全部销售渠道上架。
        具体信息以北银理财正式公告及销售文件为准。
      </div>
    </div>

    <div class="image-actions">
      <button
        type="button"
        id="make-image">
        生成新品长图
      </button>
    </div>

    <div
      id="image-result"
      class="image-result">
    </div>
  </main>

  <script>
    document
      .getElementById("make-image")
      .addEventListener(
        "click",
        makeLongImage
      );

    async function makeLongImage() {{
      const button =
        document.getElementById(
          "make-image"
        );

      const result =
        document.getElementById(
          "image-result"
        );

      if (
        typeof html2canvas
        !== "function"
      ) {{
        result.classList.add(
          "show"
        );

        result.innerHTML =
          '<div class="save-tip">'
          + '长图组件加载失败，请刷新页面后重试。'
          + '</div>';

        return;
      }}

      button.disabled = true;

      button.textContent =
        "正在生成长图…";

      result.classList.remove(
        "show"
      );

      result.innerHTML = "";

      try {{
        const target =
          document.getElementById(
            "capture-area"
          );

        const canvas =
          await html2canvas(
            target,
            {{
              backgroundColor:
                "#f5f7fb",
              scale: 2,
              useCORS: true,
              logging: false
            }}
          );

        const image =
          document.createElement(
            "img"
          );

        image.src =
          canvas.toDataURL(
            "image/png"
          );

        image.alt =
          "北银理财新品监测长图";

        const tip =
          document.createElement(
            "div"
          );

        tip.className =
          "save-tip";

        tip.textContent =
          "长按下方图片，选择保存图片或保存到照片";

        result.appendChild(
          tip
        );

        result.appendChild(
          image
        );

        result.classList.add(
          "show"
        );

        result.scrollIntoView(
          {{
            behavior: "smooth",
            block: "start"
          }}
        );

        button.textContent =
          "重新生成新品长图";

      }} catch (error) {{
        result.classList.add(
          "show"
        );

        result.innerHTML =
          '<div class="save-tip">'
          + '长图生成失败，请刷新页面后重试。'
          + '</div>';

        button.textContent =
          "重新生成新品长图";

      }} finally {{
        button.disabled = false;
      }}
    }}
  </script>
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
