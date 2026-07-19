"""
Backend/tools/update_dhan_security_master.py

Dhan Security Master Downloader & Utility Script
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import requests

# Production endpoints for Dhan Scrip Master files
SECURITY_MASTER_URL = os.getenv(
    "DHAN_SECURITY_MASTER_URL", 
    "https://dhan.co"
)
DEFAULT_DESTINATION = Path("data/dhan_security_master.csv")


class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def success(msg: str) -> None:
    print(f"{Color.GREEN}✔ {msg}{Color.END}")


def info(msg: str) -> None:
    print(f"{Color.CYAN}➜ {msg}{Color.END}")


def warn(msg: str) -> None:
    print(f"{Color.YELLOW}⚠ {msg}{Color.END}")


def error(msg: str) -> None:
    print(f"{Color.RED}✖ {msg}{Color.END}")


def download_security_master(url: str, destination: Path) -> None:
    """
    Downloads the Dhan Security Master CSV using secure streaming chunks.
    Fixes B310: Replaces vulnerable urlretrieve with explicit requests protocol validation.
    """
    print()
    print(Color.BOLD + "=" * 70)
    print("QuantGrid Dhan Security Master Synchronizer")
    print("=" * 70 + Color.END)
    
    info(f"Target URL  : {url}")
    info(f"Destination : {destination}")

    # Ensure parent folder data/ hierarchy exists atomically
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Fixed B310: requests verifies network protocols directly (avoids file:// vulnerabilities)
        # Using stream=True prevents storing multi-megabyte files entirely in system RAM
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            
            info("Downloading file payload in chunks...")
            with open(destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        
        success("Security master synced and updated successfully.")

    except requests.exceptions.RequestException as e:
        error(f"Network error occurred while fetching security master: {e}")
        sys.exit(1)
    except IOError as e:
        error(f"File system operational block error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"An unexpected utility error occurred: {e}")
        sys.exit(1)


def main() -> None:
    download_security_master(SECURITY_MASTER_URL, DEFAULT_DESTINATION)


if __name__ == "__main__":
    main()
