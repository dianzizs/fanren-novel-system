import json
import urllib.request

url = "http://localhost:8000/api/books/fanren-1-500/ask"
data = {"user_query": "韩立第一次见到墨大夫是什么情况", "debug": True}

req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=120)
d = json.loads(resp.read().decode())

# 写入文件
with open("trace_output.json", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print("Done")
