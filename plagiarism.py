import re
import asyncio
from difflib import SequenceMatcher
import wikipediaapi

# Wikipedia API'sini Türkçe olarak ve düzgün bir User-Agent ile tanımla
wiki_wiki = wikipediaapi.Wikipedia(
    user_agent="AIDetectSaaS/2.0 (tolgahanss@example.com)",
    language="tr"
)

def _split_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 15]

def _similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100, 1)

async def check_plagiarism(text: str, can_see_full: bool = False) -> dict:
    sentences = _split_sentences(text)
    if not sentences:
        return {"overall_similarity": 0, "sources": [], "is_flagged": False, "is_blurred": False}
    
    # En uzun ve kritik 3 cümleyi seç
    target_sentences = sorted(sentences, key=len, reverse=True)[:3]
    
    total_similarity = 0
    detected_sources = {}
    
    for sentence in target_sentences:
        # Cümledeki ilk 4-5 kelimeyi alıp anahtar kelime araması yapıyoruz
        search_query = " ".join(sentence.split()[:5])
        
        try:
            # Wikipedia'da o başlığı ara
            page = wiki_wiki.page(search_query)
            
            if page.exists():
                # Sayfanın ilk 500 karakterlik özetini al
                snippet = page.summary[:500]
                sim_score = _similarity(sentence, snippet)
                
                # Eğer %35'ten fazla benzerlik yakalarsak intihal bas
                if sim_score > 35:
                    url = page.fullurl
                    if url not in detected_sources:
                        detected_sources[url] = {
                            "title": f"Wikipedia: {page.title}",
                            "url": url,
                            "match_score": sim_score
                        }
                    total_similarity += sim_score
        except Exception as e:
            print(f"[Plagiarism] Wiki tarama hatası: {e}")
            
    avg_similarity = min(100, int(total_similarity / len(target_sentences))) if target_sentences else 0
    sources_list = list(detected_sources.values())
    
    # Paywall maskeleme mantığı (Premium kontrolü)
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
