class LegacySSLAdapter(HTTPAdapter):
    """兼容部分银行官网使用的旧版SSL协商方式。"""

    def init_poolmanager(
        self,
        connections,
        maxsize,
        block=False,
        **pool_kwargs,
    ):
        ssl_context = ssl.create_default_context()

        legacy_option = getattr(
            ssl,
            "OP_LEGACY_SERVER_CONNECT",
            0x4,
        )

        ssl_context.options |= legacy_option

        pool_kwargs["ssl_context"] = ssl_context

        return super().init_poolmanager(
            connections,
            maxsize,
            block=block,
            **pool_kwargs,
        )


SESSION = requests.Session()

SESSION.mount(
    "https://bankofbeijing.com.cn",
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
