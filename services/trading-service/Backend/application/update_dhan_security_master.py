from pathlib import Path
import requests

SECURITY_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

def download_security_master():
    Path("data").mkdir(exist_ok=True)

    destination = Path("data/dhan_security_master.csv")

    print("Downloading Dhan Security Master...")
    
    # Fixed B310: Swapped urlretrieve with requests streaming to enforce secure remote protocol paths
    with requests.get(SECURITY_MASTER_URL, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    print(f"Saved to {destination}")

if __name__ == "__main__":
    download_security_master()
