import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timezone, timedelta

def get_today_str():
    # 台北時區 UTC+8
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d')

def get_candidate_models(api_key):
    """取得可用模型清單，最優先使用官方指定的 gemini-3.8-flash 並依版本由新到舊排序"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(url)
    candidates = []
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for m in data.get('models', []):
            name = m.get('name', '')
            methods = m.get('supportedGenerationMethods', [])
            if 'generateContent' in methods and 'gemini' in name.lower():
                if any(x in name.lower() for x in ['embedding', 'imagen', 'veo', 'vision', 'audio', 'tts', 'aqa', 'bisect']):
                    continue
                candidates.append(name)
    except Exception as e:
        print(f"查詢模型清單提醒: {e}")

    # 依版本號由新到舊排序
    candidates.sort(reverse=True)

    # 將 Google 官方指定給新用戶的最新模型排在最優先
    priority = [
        'models/gemini-3.8-flash',
        'models/gemini-flash-latest',
        'models/gemini-pro-latest',
    ]
    ordered = []
    for p in priority:
        if p not in ordered:
            ordered.append(p)
    for c in candidates:
        if c not in ordered:
            ordered.append(c)
    return ordered

def fetch_google_news_rss():
    """從 Google News 台灣版抓取最新『蔣萬安 沈伯洋』新聞作為輔助資料"""
    query = urllib.parse.quote("蔣萬安 沈伯洋 when:1d")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    news_items = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        for item in root.findall('.//item')[:15]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            pub_date = item.findtext('pubDate', '')
            news_items.append(f"- 標題：{title}\n  時間：{pub_date}\n  連結：{link}")
    except Exception as e:
        print(f"RSS 新聞抓取略過: {e}")
    return "\n".join(news_items)

def query_gemini(api_key, model_list, recent_context, news_feed, today_date):
    prompt = f"""你是一個客觀公正的政治新聞研究編輯。
請針對「2026年台北市長選舉」，根據過去24小時內（今天日期為 {today_date}）「蔣萬安陣營」與「沈伯洋陣營」的最新重點攻防新聞（包括市政交鋒、政策質疑、公開回應、辯論、造勢等）進行整理。

【現有時間軸最新已記錄的事件（請勿重複記錄相同事件）】：
{recent_context}

【最新抓取之新聞參考清單】：
{news_feed if news_feed else "（請透過搜尋工具檢索今日最新新聞）"}

【整理原則（嚴格遵守）】：
1. 對於同一個新聞事件，不需要天天寫，請一併整理在新聞事件的起始日即可，除非該新聞有出現重大變化或新進展。
2. 如果過去24小時內有全新的重大攻防事件，或是既有事件有重大進展，請依據以下 HTML 格式產出一個或多個 <div class="row">...</div> 節點。
3. 如果過去24小時內「沒有」任何新的重大攻防，請直接只輸出：NO_UPDATE

【HTML 節點標準格式】：
<div class="row">
  <div class="top"><div class="card chiang">
  <div class="label">蔣萬安／蔣陣營</div>
  <p>[蔣萬安或蔣陣營說法與具體論述摘要]</p>
  <a href="[真實新聞來源完整URL]" target="_blank" rel="noopener">新聞來源 ↗</a>
</div></div>
  <div class="mid"><div class="dot"></div><time>{today_date}</time><h3>[精簡具代表性的事件標題]</h3></div>
  <div class="bottom"><div class="card shen">
  <div class="label">沈伯洋／沈陣營</div>
  <p>[沈伯洋或沈陣營說法與具體論述摘要]</p>
  <a href="[真實新聞來源完整URL]" target="_blank" rel="noopener">新聞來源 ↗</a>
</div></div>
</div>

請只輸出 HTML 代碼或 NO_UPDATE，不要包含任何開頭或結尾的 markdown 標籤（如 ```html），也不要有任何多餘說明。"""

    for model_name in model_list:
        url = f"[https://generativelanguage.googleapis.com/v1beta/](https://generativelanguage.googleapis.com/v1beta/){model_name}:generateContent?key={api_key}"
        for use_search_tool in [True, False]:
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            if use_search_tool:
                payload["tools"] = [{"google_search": {}}]

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                candidates = data.get('candidates', [])
                if candidates:
                    content = candidates[0].get('content', {}).get('parts', [])
                    text = "".join([p.get('text', '') for p in content]).strip()
                    if text:
                        print(f"成功使用模型 {model_name} (search={use_search_tool}) 完成生成！")
                        return text
            except urllib.error.HTTPError as e:
                err_text = e.read().decode('utf-8')
                if e.code == 404 or "no longer available" in err_text:
                    print(f"模型 {model_name} 無法使用，自動切換下一個模型...")
                    break
                elif use_search_tool:
                    print(f"模型 {model_name} 不支援 search tool (HTTP {e.code})，改用標準模式...")
                    continue
                else:
                    print(f"模型 {model_name} 請求失敗 (HTTP {e.code}): {err_text}")
                    break

    print("所有候選模型皆無法完成請求。")
    sys.exit(1)

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)
        
    html_file = "index.html"
    if not os.path.exists(html_file):
        print(f"Error: {html_file} not found.")
        sys.exit(1)
        
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    events = re.findall(r'<time>(.*?)</time><h3>(.*?)
