import requests
import json
import os
from datetime import datetime
from companies import COMPANIES, KEYWORDS

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
SEEN_JOBS_FILE = "seen_jobs.json"

def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen_jobs):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen_jobs), f)

def search_saramin(company, keyword):
    """사람인 RSS로 공고 검색"""
    results = []
    try:
        query = f"{company} {keyword}"
        url = f"https://www.saramin.co.kr/zf_user/rss/job?searchword={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "").strip()
                company_name = item.findtext("company", title).strip()
                
                # 기업명 + 키워드 둘 다 포함 확인
                if any(c in title or c in company_name for c in [company]):
                    job_id = f"saramin_{link}"
                    results.append({
                        "id": job_id,
                        "title": title,
                        "company": company_name,
                        "link": link,
                        "date": pub_date,
                        "platform": "사람인"
                    })
    except Exception as e:
        print(f"사람인 검색 오류 ({company} / {keyword}): {e}")
    return results

def search_jobkorea(company, keyword):
    """잡코리아 스크래핑으로 공고 검색"""
    results = []
    try:
        query = f"{company} {keyword}"
        url = f"https://www.jobkorea.co.kr/Search/?stext={requests.utils.quote(query)}&tabType=recruit"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            job_items = soup.select(".recruit-info")
            
            for item in job_items:
                title_el = item.select_one(".title")
                link_el = item.select_one("a")
                company_el = item.select_one(".corp-name")
                
                if title_el and link_el:
                    title = title_el.get_text(strip=True)
                    link = "https://www.jobkorea.co.kr" + link_el.get("href", "")
                    company_name = company_el.get_text(strip=True) if company_el else company
                    job_id = f"jobkorea_{link}"
                    
                    results.append({
                        "id": job_id,
                        "title": title,
                        "company": company_name,
                        "link": link,
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "platform": "잡코리아"
                    })
    except Exception as e:
        print(f"잡코리아 검색 오류 ({company} / {keyword}): {e}")
    return results

def send_slack(new_jobs):
    """슬랙으로 새 공고 전송"""
    if not new_jobs:
        print("새 공고 없음")
        return
    
    today = datetime.now().strftime("%Y.%m.%d")
    text = f"🆕 *새 채용공고 {len(new_jobs)}건* ({today})\n\n"
    
    for i, job in enumerate(new_jobs, 1):
        text += f"*{i}. [{job['company']}] {job['title']}*\n"
        text += f"   📌 {job['platform']}\n"
        text += f"   🔗 {job['link']}\n\n"
    
    payload = {"text": text}
    response = requests.post(SLACK_WEBHOOK_URL, json=payload)
    print(f"슬랙 전송 완료: {response.status_code}")

def main():
    print(f"[{datetime.now()}] 채용공고 수집 시작")
    seen_jobs = load_seen_jobs()
    new_jobs = []
    all_jobs = []

    for company in COMPANIES:
        for keyword in KEYWORDS:
            saramin_jobs = search_saramin(company, keyword)
            jobkorea_jobs = search_jobkorea(company, keyword)
            all_jobs.extend(saramin_jobs + jobkorea_jobs)

    # 중복 제거 및 새 공고 필터링
    seen_ids = set()
    for job in all_jobs:
        job_id = job["id"]
        if job_id not in seen_jobs and job_id not in seen_ids:
            new_jobs.append(job)
            seen_ids.add(job_id)

    print(f"새 공고 {len(new_jobs)}건 발견")
    
    # 슬랙 전송 (20개씩 나눠서)
    chunk_size = 20
    for i in range(0, len(new_jobs), chunk_size):
        send_slack(new_jobs[i:i+chunk_size])

    # seen_jobs 업데이트
    seen_jobs.update(seen_ids)
    save_seen_jobs(seen_jobs)
    print("완료!")

if __name__ == "__main__":
    main()
