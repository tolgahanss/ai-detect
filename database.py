import httpx

class SupabaseClient:
    def __init__(self, url: str, key: str):
        # ── SİBER ZIRH: Tüm pislikleri temizliyoruz ──
        cleaned_url = url.strip().strip('"').strip("'").rstrip("/")
        cleaned_key = key.strip().strip('"').strip("'")

        self.base_url = cleaned_url
        if self.base_url.endswith("/rest/v1"):
            self.rest_url = self.base_url
        else:
            self.rest_url = f"{self.base_url}/rest/v1"

        self.headers = {
            "apikey": cleaned_key,
            "Authorization": f"Bearer {cleaned_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(headers=self.headers, timeout=10.0)
        
        # ── SİBER AJAN: Render gercekte nereye gidiyor? (Loglara yazacak) ──
        print(f"--- SIBER LOG: BAGLANILAN URL = {self.rest_url} ---", flush=True)

    def select(self, table: str, columns: str = "*", filters: dict = None) -> list:
        params = {"select": columns}
        if filters:
            for k, v in filters.items():
                params[k] = f"eq.{v}"
        try:
            response = self._client.get(f"{self.rest_url}/{table}", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"--- SIBER LOG HATA: GET {self.rest_url}/{table} BASARISIZ. Detay: {str(e)}", flush=True)
            raise e

    def insert(self, table: str, data: dict) -> list:
        response = self._client.post(f"{self.rest_url}/{table}", json=data)
        response.raise_for_status()
        return response.json()

    def update(self, table: str, data: dict, filters: dict) -> list:
        params = {}
        for k, v in filters.items():
            params[k] = f"eq.{v}"
        response = self._client.patch(f"{self.rest_url}/{table}", json=data, params=params)
        response.raise_for_status()
        return response.json()

    def count(self, table: str, filters: dict = None) -> int:
        headers = {**self.headers, "Prefer": "count=exact"}
        params = {"select": "*"}
        if filters:
            for k, v in filters.items():
                if isinstance(v, tuple):
                    op, val = v
                    params[k] = f"{op}.{val}"
                else:
                    params[k] = f"eq.{v}"
        response = self._client.get(f"{self.rest_url}/{table}", params=params, headers=headers)
        response.raise_for_status()
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            total = content_range.split("/")[-1]
            return int(total) if total != "*" else 0
        return len(response.json())

    def select_with_filters(self, table: str, columns: str = "*", raw_filters: dict = None) -> list:
        params = {"select": columns}
        if raw_filters:
            params.update(raw_filters)
        response = self._client.get(f"{self.rest_url}/{table}", params=params)
        response.raise_for_status()
        return response.json()


_client: SupabaseClient | None = None

def get_supabase() -> SupabaseClient:
    global _client
    if _client is None:
        # ── HİÇBİR ENV (ÇEVRE) DEĞİŞKENİNE GÜVENMİYORUZ, ADRES VE ŞİFREYİ ÇİVİ GİBİ ÇAKIYORUZ ──
        _client = SupabaseClient(
            url="https://uvkocqokxeueajpssaew.supabase.co",
            key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV2a29jcW9reGV1ZWFqcHNzYWV3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkxNDA3NDIsImV4cCI6MjA5NDcxNjc0Mn0.P14jCGhTRuUPbGXGCly-BzVyT5GCArx1TwqgvmFH8XQ"
        )
    return _client
