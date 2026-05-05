import requests
from typing import List, Optional

ZOTERO_PORT = 23119
BASE = f"http://localhost:{ZOTERO_PORT}"


class ZoteroClient:
    def __init__(self):
        self.available = False

    def check_connection(self) -> bool:
        try:
            r = requests.get(f"{BASE}/better-bibtex/cayw?probe=true", timeout=1.5)
            self.available = r.status_code == 200
        except Exception:
            self.available = False
        return self.available

    def cite_as_you_write(self, fmt: str = "pandoc") -> Optional[str]:
        """Open Zotero CAYW dialog; returns formatted citation string."""
        try:
            r = requests.get(
                f"{BASE}/better-bibtex/cayw",
                params={"format": fmt, "minimize": "true"},
                timeout=60,
            )
            if r.status_code == 200 and r.text.strip():
                return r.text.strip()
        except Exception as e:
            print(f"Zotero CAYW: {e}")
        return None

    def search_items(self, query: str) -> List[dict]:
        try:
            r = requests.get(
                f"{BASE}/better-bibtex/search",
                params={"q": query, "limit": 50},
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def get_all_items(self) -> List[dict]:
        try:
            r = requests.get(f"{BASE}/api/items", params={"limit": 200}, timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def export_bibliography(self, keys: List[str], style: str = "apa") -> str:
        try:
            r = requests.post(
                f"{BASE}/better-bibtex/export/bibliography",
                json={"keys": keys, "style": style},
                timeout=10,
            )
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print(f"Bibliography export: {e}")
        return ""
