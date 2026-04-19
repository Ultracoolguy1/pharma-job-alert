import requests
import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup
from companies import EXACT_COMPANIES

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
SEEN_JOBS_FILE = "seen_jobs.json"
JOBS_FILE = "jobs.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen_jobs):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen_jobs), f)

def load_all_jobs():
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_all_jobs(jobs):
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

def is_target_company(company_name):
    for exact in EXACT_COMPANIES:
        if exact == company_name or exact in company_name:
            return True
    return False

def search_saramin(company):
    results = []
    try:
        url = f"https://www.saramin.co.kr/zf_user/search?searchword={requests.utils.quote(company)}&ind_key=70302%2C70306&recruitPage=1"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for item in soup.select(".item_recruit"):
                title_el = item.select_one(".job_tit a")
                company_el = item.select_one(".corp_name a")
                if not title_el or not company_el:
                    continue
                title = title_el.get_text(strip=True)
                company_name = company_el.get_text(strip=True)
                link = "https://www.saramin.co.kr" + title_el.get("href", "")
                if is_target_company(company_name):
                    results.append({
                        "id": f"saramin_{link}",
                        "title": title,
                        "company": company_name,
                        "link": link,
                        "platform": "사람인",
                        "date": datetime.now().strftime("%Y.%m.%d")
                    })
    except Exception as e:
        print(f"사람인 오류 ({company}): {e}")
    return results

def search_jobkorea(company):
    results = []
    try:
        url = f"https://www.jobkorea.co.kr/Search/?stext={requests.utils.quote(company)}&tabType=recruit&dkwrd=10003843052"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            href_map = {}
            for link_el in soup.select("a[href*='/Recruit/GI_Read/']"):
                href = link_el.get("href", "").split("?")[0]
                text = link_el.get_text(strip=True)
                if not text or len(text) < 2:
                    continue
                if href not in href_map:
                    href_map[href] = []
                href_map[href].append(text)
            for href, texts in href_map.items():
                if len(texts) < 2:
                    continue
                title, company_name = texts[0], texts[1]
                link = f"https://www.jobkorea.co.kr{href}"
                if is_target_company(company_name):
                    results.append({
                        "id": f"jobkorea_{href}",
                        "title": title,
                        "company": company_name,
                        "link": link,
                        "platform": "잡코리아",
                        "date": datetime.now().strftime("%Y.%m.%d")
                    })
    except Exception as e:
        print(f"잡코리아 오류 ({company}): {e}")
    return results

def send_slack(new_jobs):
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
    print(f"슬랙 전송: {response.status_code}")

def main():
    print(f"[{datetime.now()}] 수집 시작")
    seen_jobs = load_seen_jobs()
    all_jobs_data = load_all_jobs()
    all_jobs = []
    seen_ids = set()
    new_jobs = []

    for company in EXACT_COMPANIES:
        print(f"검색: {company}")
        saramin = search_saramin(company)
        jobkorea = search_jobkorea(company)
        print(f"  사람인: {len(saramin)}건, 잡코리아: {len(jobkorea)}건")
        all_jobs.extend(saramin + jobkorea)
        time.sleep(1)

    seen_titles = {}
    for job in all_jobs:
        job_id = job["id"]
        title_key = f"{job['company']}_{job['title']}"
        if job_id not in seen_jobs and title_key not in seen_titles:
            new_jobs.append(job)
            seen_ids.add(job_id)
            seen_titles[title_key] = True

    print(f"새 공고 {len(new_jobs)}건")

    # jobs.json 업데이트 (새 공고 앞에 추가, 최대 500개 유지)
    all_jobs_data = new_jobs + all_jobs_data
    all_jobs_data = all_jobs_data[:500]
    save_all_jobs(all_jobs_data)

    for i in range(0, len(new_jobs), 20):
        send_slack(new_jobs[i:i+20])

    seen_jobs.update(seen_ids)
    save_seen_jobs(seen_jobs)
    print("완료!")

if __name__ == "__main__":
    main()
