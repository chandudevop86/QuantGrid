from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=[
            "--disable-http2",
            "--disable-quic",
            "--no-sandbox",
        ],
    )

    page = browser.new_page()

    page.goto(
        "https://www.google.com",
        wait_until="domcontentloaded",
    )

    print("Google OK")

    page.goto(
        "https://www.nseindia.com",
        wait_until="domcontentloaded",
        timeout=30000,
    )

    print("NSE OK")

    input("Press Enter...")
    browser.close()