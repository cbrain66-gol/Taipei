import os
import sys
import json
import urllib.request
import re
from datetime import datetime, timezone, timedelta

def get_today_str():
    # 台北時區 UTC+8
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d')

def query_gemini_with_search(api_key, recent_context, today_date):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    prompt = f"""你是一個客觀公正的政治新聞研究編輯。
請針對「2026年台北市長選舉」，搜尋過去24小時內（今天日期為 {today_date}）「蔣萬安陣營」與「沈伯洋陣營」的最新重點攻防新聞（包括市政交鋒、政策質疑、公開回應、辯論、造勢等）。

【現有時間軸最新已記錄的事件】：
{recent_context}

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

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}]
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        
    candidates = data.get('candidates', [])
    if not candidates:
        return None
    content = candidates[0].get('content', {}).get('parts', [])
    return "".join([p.get('text', '') for p in content]).strip()

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
        
    events = re.findall(r'<time>(.*?)</time><h3>(.*?)</h3>', html_content)
    recent_events = events[-5:] if len(events) >= 5 else events
    recent_context = "\n".join([f"- {date}: {title}" for date, title in recent_events])
    
    today_date = get_today_str()
    print(f"Checking updates for {today_date}...")
    
    result = query_gemini_with_search(api_key, recent_context, today_date)
    if not result or "NO_UPDATE" in result:
        print("No new major campaign events today. index.html remains unchanged.")
        return
        
    cleaned_result = re.sub(r'^```html\s*', '', result, flags=re.IGNORECASE)
    cleaned_result = re.sub(r'^```\s*', '', cleaned_result)
    cleaned_result = re.sub(r'```$', '', cleaned_result).strip()
    
    if '<div class="row">' not in cleaned_result:
        print("Generated output did not contain valid row format.")
        return
        
    target = '</div></div>\n <div class="note">'
    replacement = f'    </div>{cleaned_result}\n    </div></div>\n <div class="note">'
    
    if target in html_content:
        new_html = html_content.replace(target, replacement)
    else:
        target_alt = '</div></div>\n  <div class="note">'
        if target_alt in html_content:
            new_html = html_content.replace(target_alt, replacement)
        else:
            print("Could not locate insertion anchor in index.html.")
            return

    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(new_html)
        
    print(f"Successfully updated {html_file} with new events for {today_date}!")

if __name__ == "__main__":
    main()
