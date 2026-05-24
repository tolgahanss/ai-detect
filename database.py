"""
Supabase veritabanı bağlantısı — PostgREST API üzerinden.

Supabase'in arka planında PostgREST kullanır. Tüm sorgular
otomatik olarak parametrize edilir → SQL Injection imkansız.

NOT: Ağır 'supabase' paketi yerine doğrudan httpx ile PostgREST API
kullanıyoruz. Bu, aynı güvenlik seviyesini çok daha hafif bağımlılıklarla sağlar.
"""

import httpx
from config import settings


class SupabaseClient:
    """
    Hafif Supabase REST API client'ı.

    PostgREST API üzerinden çalışır — tüm sorgular otomatik
    parametrize edilir, SQL Injection riski yoktur.
    """

    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip("/")
        if self.base_url.endswith("/rest/v1"):
            self.rest_url = self.base_url
        else:
            self.rest_url = f"{self.base_url}/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(headers=self.headers, timeout=10.0)

    def select(self, table: str, columns: str = "*", filters: dict = None) -> list:
        """
        Tablodan veri çeker (SELECT).

        PostgREST filtreleri kullanır — değerler otomatik escape edilir.
        → SQL Injection imkansız.

        Args:
            table: Tablo adı
            columns: Seçilecek sütunlar (varsayılan: *)
            filters: {"sütun": "değer"} formatında filtreler

        Returns:
            Eşleşen satırların listesi
        """
        params = {"select": columns}
        if filters:
            for key, value in filters.items():
                params[key] = f"eq.{value}"

        response = self._client.get(f"{self.rest_url}/{table}", params=params)
        response.raise_for_status()
        return response.json()

    def insert(self, table: str, data: dict) -> list:
        """
        Tabloya yeni kayıt ekler (INSERT).

        JSON body olarak gönderilir — PostgREST tarafında
        parametrize edilir → SQL Injection imkansız.

        Args:
            table: Tablo adı
            data: Eklenecek veri dict'i

        Returns:
            Eklenen satır(lar) listesi
        """
        response = self._client.post(f"{self.rest_url}/{table}", json=data)
        response.raise_for_status()
        return response.json()

    def update(self, table: str, data: dict, filters: dict) -> list:
        """
        Tablodaki kayıtları günceller (UPDATE).

        PostgREST filtreleri kullanır → SQL Injection imkansız.

        Args:
            table: Tablo adı
            data: Güncellenecek alanlar
            filters: Hangi kayıtların güncelleneceği

        Returns:
            Güncellenen satır(lar) listesi
        """
        params = {}
        for key, value in filters.items():
            params[key] = f"eq.{value}"

        response = self._client.patch(
            f"{self.rest_url}/{table}", json=data, params=params
        )
        response.raise_for_status()
        return response.json()

    def count(self, table: str, filters: dict = None) -> int:
        """
        Tablodaki kayıt sayısını döndürür (COUNT).

        PostgREST'in HEAD + Prefer: count=exact yöntemini kullanır.
        → SQL Injection imkansız.
        """
        headers = {**self.headers, "Prefer": "count=exact"}
        params = {"select": "*"}
        if filters:
            for key, value in filters.items():
                if isinstance(value, tuple):
                    # Özel operatör desteği: ("gte", "2024-01-01")
                    op, val = value
                    params[key] = f"{op}.{val}"
                else:
                    params[key] = f"eq.{value}"

        response = self._client.get(
            f"{self.rest_url}/{table}",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        # PostgREST Content-Range header'ından toplam sayı
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            total = content_range.split("/")[-1]
            return int(total) if total != "*" else 0
        return len(response.json())

    def select_with_filters(
        self, table: str, columns: str = "*", raw_filters: dict = None
    ) -> list:
        """
        Gelişmiş filtrelerle SELECT sorgusu.

        raw_filters, PostgREST operatörlerini doğrudan destekler:
          {"credits": "lte.0"}  → credits <= 0
          {"created_at": "gte.2024-01-01"}  → created_at >= 2024-01-01

        → SQL Injection imkansız — değerler PostgREST tarafında parametrize edilir.
        """
        params = {"select": columns}
        if raw_filters:
            params.update(raw_filters)

        response = self._client.get(f"{self.rest_url}/{table}", params=params)
        response.raise_for_status()
        return response.json()


# ─────────────────────── Singleton Client ──────────────────────────

_client: SupabaseClient | None = None


def get_supabase() -> SupabaseClient:
    """Supabase client singleton'ını döndürür."""
    global _client
    if _client is None:
        _client = SupabaseClient(
            url=settings.SUPABASE_URL,
            key=settings.SUPABASE_KEY,
        )
    return _client
