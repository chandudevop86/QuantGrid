from playwright.sync_api import sync_playwright
import json


def fetch_nse_option_chain(symbol: str):

    url = (
        "https://www.nseindia.com/api/"
        f"option-chain-indices?symbol={symbol}"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            )
        )

        page.goto(
            "https://www.nseindia.com",
            wait_until="networkidle",
            timeout=30000,
        )

        data = page.evaluate(
            """
            async (url) => {
                const res = await fetch(url);
                return await res.text();
            }
            """,
            url,
        )

        browser.close()

    return json.loads(data)