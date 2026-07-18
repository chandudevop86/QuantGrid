from pathlib import Path
from urllib.request import urlretrieve

SECURITY_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

def download_security_master():
    Path("data").mkdir(exist_ok=True)

    destination = Path("data/dhan_security_master.csv")

    print("Downloading Dhan Security Master...")
    urlretrieve(SECURITY_MASTER_URL, destination)

    print(f"Saved to {destination}")

if __name__ == "__main__":
    download_security_master()