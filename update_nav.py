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
    """
    从products.json读取所有启用产品。

    后续新增北银理财产品时，
    只需要修改products.json。
    """

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
            
