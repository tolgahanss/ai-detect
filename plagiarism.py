"""
İntihal / Benzerlik Tarama Motoru
==================================
Metni cümlelere böler, her cümleyi DuckDuckGo üzerinden aratır,
bulunan sonuçlardan snippet'leri çeker ve difflib ile benzerlik
oranını hesaplar. Sonuç olarak cümle bazlı benzerlik raporu ve
genel benzerlik yüzdesi döner.
"""

import re
import asyncio
from difflib import SequenceMatcher
from typing import Optional

import httpx


# ─────────────── Yardımcı Fonksiyonlar ───────────────

def _split_sentences(text: str) -> list[str]:
    """Metni nokta / ünlem / soru işaretinden cümlelere böler."""
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 15]


def _similarity(a: str, b: str) -> float:
    """İki metin arasındaki benzerlik oranını 0-100 olarak döndürür."""
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100, 1)


# ─────────────── DuckDuckGo Arama ───────────────

async def _search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """
    DuckDuckGo'nun HTML arama sayfasını kullanarak sonuç çeker.
    Her sonuç: {"title", "url", "snippet"}
    """
    results = []
    try:
        # DuckDuckGo HTML versiyonu — API key gerektirmez
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        params = {"q": query, "kl": "tr-tr"}
        
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            resp = await client.get("https://html.duckduckgo.com/html/", params=params, headers=headers)
            html = resp.text
            
            # Basit regex ile sonuçları çek (lxml bağımlılığı gerektirmesin diye)
            # DuckDuckGo HTML result blokları: <a class="result__a" href="...">title</a>
            # snippet: <a class="result__snippet" ...>snippet text</a>
            
            links = re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>',
                html, re.DOTALL
            )
            snippets = re.findall(
                r'<a class="result__snippet"[^>]*>(.+?)</a>',
                html, re.DOTALL
            )
            
            for i in range(min(len(links), len(snippets), max_results)):
                url = links[i][0]
                title = re.sub(r'<[^>]+>', '', links[i][1]).strip()
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                
                # DuckDuckGo redirect URL'lerini temizle
                if "uddg=" in url:
                    match = re.search(r'uddg=([^&]+)', url)
                    if match:
                        from urllib.parse import unquote
                        url = unquote(match.group(1))
                
                if snippet and title:
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet
                    })
    except Exception as e:
        print(f"[Plagiarism] DuckDuckGo arama hatası: {e}")
    
    return results


# ─────────────── Ana Tarama Fonksiyonu ───────────────

async def check_plagiarism(text: str, can_see_full: bool = False) -> dict:
    sentences = _split_sentences(text)
    if not sentences:
        return {"overall_similarity": 0, "sources": [], "is_flagged": False, "is_blurred": False}
    
    # Hız için sadece en uzun/kritik 5 cümleyi seçip internette taratalım (DuckDuckGo ban yememek için)
    target_sentences = sorted(sentences, key=len, reverse=True)[:5]
    
    total_similarity = 0
    detected_sources = {}
    
    for sentence in target_sentences:
        # Cümleyi DuckDuckGo'da ücretsiz arat
        search_results = await _search_ddg(sentence, max_results=3)
        await asyncio.sleep(0.5) # Arama motorunu yormamak için kısa bir siber mola
        
        for res in search_results:
            sim_score = _similarity(sentence, res["snippet"])
            # Eğer %40'tan fazla benzerlik varsa intihal sayalım
            if sim_score > 40:
                url = res["url"]
                if url not in detected_sources:
                    detected_sources[url] = {
                        "title": res["title"],
                        "url": url,
                        "match_score": sim_score
                    }
                total_similarity += sim_score
                break # Bu cümle için bu kaynak yetti
                
    avg_similarity = min(100, int(total_similarity / len(target_sentences))) if target_sentences else 0
    sources_list = list(detected_sources.values())
    
    # Paywall maskeleme mantığı (Premium kontrolü)
    is_blurred = False
    if not can_see_full and len(sources_list) > 1:
        is_blurred = True
        # Premium değilse kaynak linklerini gizle
        for i in range(1, len(sources_list)):
            sources_list[i]["url"] = "https://ai-detect-pearl.vercel.app/upgrade-to-see-source"
            sources_list[i]["title"] = "🔒 Premium Kaynak [Görmek İçin Yükselt]"

    return {
        "overall_similarity": avg_similarity,
        "sources": sources_list,
        "is_flagged": True if avg_similarity > 20 else False,
        "is_blurred": is_blurred
    }

