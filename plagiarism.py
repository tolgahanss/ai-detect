import re
import asyncio
from difflib import SequenceMatcher
import httpx

def _split_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 15]

def _similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100, 1)

async def check_plagiarism(text: str, can_see_full: bool = False) -> dict:
    sentences = _split_sentences(text)
    if not sentences:
        return {"overall_similarity": 0, "sources": [], "is_flagged": False, "is_blurred": False}
    
    words = text.split()
    if len(words) < 5:
        return {"overall_similarity": 0, "sources": [], "is_flagged": False, "is_blurred": False}

    # En uzun 3 cümleyi seç
    target_sentences = sorted(sentences, key=len, reverse=True)[:3]
    
    total_similarity = 0
    detected_sources = {}
    
    # Wikipedia API için düzgün bir User-Agent
    headers = {
        "User-Agent": "AIDetectSaaS/2.0 (tolgahanss@example.com)"
    }

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for sentence in target_sentences:
            # Cümledeki ilk 5 kelimeyi arama terimi yap
            search_query = " ".join(sentence.split()[:5])
            
            try:
                # 1. Adım: Wikipedia'da asenkron arama yap
                search_url = "https://tr.wikipedia.org/w/api.php"
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": search_query,
                    "format": "json"
                }
                
                resp = await client.get(search_url, params=search_params, headers=headers)
                search_data = resp.json()
                
                search_results = search_data.get("query", {}).get("search", [])
                
                if search_results:
                    # En yakın ilk sonucu incele
                    top_result = search_results[0]
                    page_title = top_result["title"]
                    
                    # 2. Adım: Bulunan sayfanın içeriğini (metnini) asenkron olarak çek
                    content_params = {
                        "action": "query",
                        "prop": "extracts",
                        "exintro": True,
                        "explaintext": True,
                        "titles": page_title,
                        "format": "json"
                    }
                    
                    content_resp = await client.get(search_url, params=content_params, headers=headers)
                    content_data = content_resp.json()
                    
                    pages = content_data.get("query", {}).get("pages", {})
                    for page_id, page_info in pages.items():
                        snippet = page_info.get("extract", "")
                        if snippet:
                            sim_score = _similarity(sentence, snippet)
                            
                            # Cümle birebir içeride geçiyorsa veya benzerlik yüksekse intihal say
                            if sentence.lower()[:25] in snippet.lower() or sim_score > 35:
                                sim_score = max(sim_score, 90)  # Kesin eşleşme ödülü
                            
                            page_slug = page_title.replace(" ", "_")
                            url = f"https://tr.wikipedia.org/wiki/{page_slug}"
                            
                            if url not in detected_sources:
                                detected_sources[url] = {
                                    "title": f"Wikipedia: {page_title}",
                                    "url": url,
                                    "match_score": int(sim_score)
                                }
                            total_similarity += sim_score
                            break
            except Exception as e:
                print(f"[Plagiarism] Wiki asenkron arama hatası: {e}")
    
    avg_similarity = min(100, int(total_similarity / len(target_sentences))) if target_sentences else 0
    sources_list = list(detected_sources.values())

    is_blurred = False
    if not can_see_full and len(sources_list) > 1:
        is_blurred = True
        for i in range(1, len(sources_list)):
            sources_list[i]["url"] = "https://ai-detect-pearl.vercel.app/upgrade-to-see-source"
            sources_list[i]["title"] = "🔒 Premium Kaynak [Görmek İçin Yükselt]"

    return {
        "overall_similarity": avg_similarity,
        "sources": sources_list,
        "is_flagged": True if avg_similarity > 15 else False,
        "is_blurred": is_blurred
    }
