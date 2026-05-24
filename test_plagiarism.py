import httpx

text = (
    "Yapay zeka bilgisayar biliminin onemli bir alt dalidir. "
    "Makine ogrenmesi ve derin ogrenme teknikleri kullanilarak gelistirilen modeller gunumuzde yaygin kullanim alani bulmaktadir. "
    "Bu teknolojiler dogal dil isleme ve goruntu tanima gibi alanlarda cigir acan gelismelere yol acmistir. "
    "Sonuc olarak yapay zeka modern dunyanin vazgecilmez bir parcasi haline gelmistir. "
    "Bilimsel arastirmalar gostermektedir ki yapay zeka uygulamalari onumuzdeki yillarda daha da gelisecektir."
)

res = httpx.post("http://127.0.0.1:8000/analyze-text", json={"text": text}, timeout=60)
data = res.json()

print("=== AI ANALIZ ===")
ai = data["analysis"]["ai"]
human = data["analysis"]["human"]
words = data["analysis"]["words"]
sentences = data["analysis"]["sentences"]
ai_blurred = data["analysis"]["is_blurred"]
print(f"  AI skoru: {ai}%")
print(f"  Insan skoru: {human}%")
print(f"  Kelime: {words}, Cumle: {sentences}")
print(f"  AI Paywall blur: {ai_blurred}")

print()
print("=== INTIHAL TARAMASI ===")
p = data["plagiarism"]
print(f"  Genel benzerlik: {p['overall_similarity']}%")
print(f"  Uyari (>20%): {p['is_flagged']}")
print(f"  Kaynak sayisi: {len(p['sources'])}")
print(f"  Cumle raporu sayisi: {len(p['sentence_reports'])}")
print(f"  Plag Paywall blur: {p['is_blurred']}")

print()
for i, sr in enumerate(p["sentence_reports"]):
    masked = sr["is_masked"]
    sim = sr["similarity"]
    src = sr.get("matched_source", "Yok")
    print(f"  Cumle {i+1}: benzerlik={sim}%, maskeli={masked}, kaynak={src}")
