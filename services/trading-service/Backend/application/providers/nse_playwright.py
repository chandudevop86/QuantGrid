import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.nseindia.com"


def _session():
    s = requests.Session()

    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )

    s.mount("https://", HTTPAdapter(max_retries=retries))

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
    })

    return s


def fetch_nse_option_chain(symbol="NIFTY"):
    s = _session()

    # Get cookies
    r = s.get(BASE_URL, timeout=20)
    r.raise_for_status()

    # Fetch option chain
    api = (
        f"{BASE_URL}/api/option-chain-indices?symbol={symbol}"
    )

    r = s.get(api, timeout=20)
    r.raise_for_status()

    return r.json()