from playwright.sync_api import sync_playwright
import json


def fetch_nse_option_chain(symbol: str):

    url = (
        "https://www.nseindia.com/api/"
        f"option-chain-indices?symbol={symbol}"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )

        page = context.new_page()

        page.goto(
            "https://www.nseindia.com",
            wait_until="domcontentloaded",
            timeout=15000,
        )

        page.wait_for_timeout(3000)

        data = page.evaluate(
            """
            async (url) => {
                const r = await fetch(url, {
                    credentials: "include"
                });

                if (!r.ok) {
                    throw new Error(
                        `HTTP ${r.status}: ${await r.text()}`
                    );
                }

                return await r.json();
            }
            """,
            url,
        )

        browser.close()

        return data
    
    