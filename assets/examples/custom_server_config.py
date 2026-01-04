"""
Example: Configure Proxy Machine to use a custom bulk data server

This demonstrates how to modify the fetch logic to prioritize your
self-hosted server while falling back to Scryfall if needed.
"""

import os
from typing import Optional
from pathlib import Path


class CustomServerConfig:
    """Configuration for custom bulk data server."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url or os.environ.get("PM_BULK_DATA_URL")
        self.username = username or os.environ.get("PM_SERVER_USER")
        self.password = password or os.environ.get("PM_SERVER_PASS")
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        # Fallback to Scryfall
        self.scryfall_base = "https://api.scryfall.com"

    def get_bulk_url(self, filename: str) -> str:
        """Get URL for bulk data file."""
        if self.base_url:
            return f"{self.base_url.rstrip('/')}/bulk-data/{filename}"
        return f"{self.scryfall_base}/bulk-data/{filename}"

    def get_token_url(self, token_id: str) -> str:
        """Get URL for token image."""
        if self.base_url:
            return f"{self.base_url.rstrip('/')}/tokens/{token_id}.jpg"
        # Fallback to Scryfall
        return f"https://api.scryfall.com/cards/{token_id}?format=image"

    def get_auth(self) -> Optional[tuple[str, str]]:
        """Get authentication credentials if configured."""
        if self.username and self.password:
            return (self.username, self.password)
        return None


def download_with_fallback(
    filename: str,
    output_path: Path,
    config: CustomServerConfig,
) -> bool:
    """
    Download file from custom server with fallback to Scryfall.

    Returns True if successful, False otherwise.
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Try custom server first
    if config.base_url:
        try:
            url = config.get_bulk_url(filename)
            print(f"Attempting download from custom server: {url}")

            response = session.get(
                url,
                auth=config.get_auth(),
                timeout=config.timeout,
                verify=config.verify_ssl,
                stream=True,
            )
            response.raise_for_status()

            # Download to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print("Successfully downloaded from custom server")
            return True

        except Exception as e:
            print(f"Custom server failed: {e}")
            print("Falling back to Scryfall...")

    # Fallback to Scryfall
    try:
        # Get bulk data info from Scryfall API
        bulk_info_url = f"{config.scryfall_base}/bulk-data"
        response = session.get(bulk_info_url, timeout=config.timeout)
        response.raise_for_status()

        bulk_data = response.json()

        # Find matching file
        for item in bulk_data.get("data", []):
            if filename in item.get("download_uri", ""):
                download_url = item["download_uri"]
                print(f"Downloading from Scryfall: {download_url}")

                response = session.get(
                    download_url, stream=True, timeout=config.timeout
                )
                response.raise_for_status()

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                print("Successfully downloaded from Scryfall")
                return True

        print(f"File not found in Scryfall bulk data: {filename}")
        return False

    except Exception as e:
        print(f"Scryfall download failed: {e}")
        return False


# Example usage
if __name__ == "__main__":
    # Configure custom server
    config = CustomServerConfig(
        base_url="http://your-server.com",
        username="friend1",  # Optional
        password="password",  # Optional
    )

    # Download bulk data
    output_dir = Path("./bulk-data")

    files_to_download = [
        "all-cards.json.gz",
        "oracle-cards.json.gz",
        "unique-artwork.json.gz",
    ]

    for filename in files_to_download:
        output_path = output_dir / filename
        success = download_with_fallback(filename, output_path, config)

        if success:
            print(f"[OK] {filename}")
        else:
            print(f"[FAIL] {filename}")
