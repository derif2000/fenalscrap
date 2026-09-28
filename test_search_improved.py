from src.webapp.data import FenalcoData
from src.webapp.assistant import Assistant

data = FenalcoData()
data.reload()
assistant = Assistant(data)

q = "mira cada documento y post, incluyendo imagenes, graficas, tablas y demas y dime en cuales existe un 26% como dato"
res = assistant.search(q, top_n=10)
print(f"Total results returned: {len(res)}")
print("Top 5 results AFTER optimization:")
for i, r in enumerate(res[:5], 1):
    txt = r.get("content_text", "")
    has_26 = "26%" in txt or "26 %" in txt or "26," in txt or "26." in txt
    print(f"{i}. {r.get('title', '')[:55]} | has 26%: {has_26}")
