from __future__ import annotations

import json
import logging
from playwright.sync_api import sync_playwright

logger = logging.getLogger("quantgrid.option_chain")


BASE_URL = "https://www.nseindia.com"

API_URL = (
    "https://www.nseindia.com/api/"
    "option-chain-indices?symbol={symbol}"
)


def fetch_nse_option_chain(symbol="NIFTY"):

    symbol = symbol.upper()

    result = None

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-http2",
                "--disable-features=NetworkService",
            ],
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/126 Safari/537.36"
            ),
            locale="en-US",
        )

        page = context.new_page()
        page.set_extra_http_headers(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.nseindia.com/option-chain",
                }
            )

        try:

            # First visit NSE homepage
            page.goto(
                BASE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)


            # Get API response inside browser
            response = page.evaluate(
                """
                async (url) => {

                    const res = await fetch(
                        url,
                        {
                            headers:{
                                "accept":
                                "application/json"
                            }
                        }
                    );

                    return await res.text();
                }
                """,
                API_URL.format(symbol=symbol),
            )


            result = json.loads(response)


        except Exception:

            logger.exception(
                "NSE playwright fetch failed"
            )

            raise


        finally:
            browser.close()


    return result