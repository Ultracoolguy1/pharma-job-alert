import requests
import json
import os
import time
import re
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

def is_relevant_job(title):
    return True  # 임시 전체 허용

def clean_jobkorea_title(title_el):
    try:
        strings = list(title_el.strings)
        if strings:
            return strings[0].strip()
    except:
        pass
    return title_el.get_text(strip=True)

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

def calc_dday(deadline_str):
    if not deadline_str or deadline_str in ["상시채용", "채용시마감", "-"]:
        return deadline_str or "-"
    try:
        now = datetime.now()
        if re.match(r"\d{2}/\d{2}", deadline_str):
            month, day = deadline_str.split("/")
            deadline = datetime(now.year, int(month), int(day))
            if deadline < now:
                deadline = datetime(now.year + 1, int(month), int(day))
        elif re.match(r"\d{4}\.\d{2}\.\d{2}", deadline_str):
            deadline = datetime.strptime(deadline_str, "%Y.%m.%d")
        elif re.match(r"\d{4}-\d{2}-\d{2}", deadline_str):
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
        else:
            return deadline_str
        diff = (deadline.date() - now.date()).days
        if diff == 0:
            return "D-day"
        elif diff > 0:
            return f"D-{diff}"
        else:
            return "마감"
    except:
        return deadline_str

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
                if company not in company_name and company_name not in company:
                    continue
                if not is_relevant_job(title):
                    continue
                link = "https://www.saramin.co.kr" + title_el.get("href", "")
                deadline_raw = ""
                date_el = item.select_one(".job_date .date")
                if date_el:
                    deadline_raw = date_el.get_text(strip=True)
                print(f"    [사람인] {title} | 마감일: {deadline_raw}")
                dday = calc_dday(deadline_raw)
                results.append({
                    "id": f"saramin_{link}",
                    "title": title,
                    "company": company_name,
                    "link": link,
                    "platform": "사람인",
                    "deadline": deadline_raw,
                    "dday": dday,
                    "date": datetime.now().strftime("%Y.%m.%d")
                })
    except Exception as e:
        print(f"사람인 오류 ({company}): {e}")
    return results

def search_jobkorea(company):
    results = []
    try:
        # 업종 필터 제거 - 회사명 검색만으로 충분
        url = f"https://www.jobkorea.co.kr/Search/?stext={requests.utils.quote(company)}&tabType=recruit"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            href_map = {}
            for link_el in soup.select("a[href*='/Recruit/GI_Read/']"):
                href = link_el.get("href", "").split("?")[0]
                text = clean_jobkorea_title(link_el)
                if not text or len(text) < 2:
                    continue
                if href not in href_map:
                    href_map[href] = []
                href_map[href].append(text)
            for href, texts in href_map.items():
                if len(texts) < 2:
                    continue
                title, company_name = texts[0], texts[1]
                if company not in company_name and company_name not in company:
                    continue
                if not is_relevant_job(title):
                    continue
                link = f"https://www.jobkorea.co.kr{href}"

                deadline_raw = ""
                dday = "-"
                try:
                    link_el = soup.find("a", href=lambda h: h and href in h)
                    if link_el:
                        parent = link_el.find_parent()
                        if parent:
                            text_content = parent.get_text()
                            date_match = re.search(r"\d{4}-\d{2}-\d{2}|\d{4}\.\d{2}\.\d{2}|\d{2}/\d{2}", text_content)
                            if date_match:
                                deadline_raw = date_match.group()
                                dday = calc_dday(deadline_raw)
                            elif "상시" in text_content:
                                deadline_raw = "상시채용"
                                dday = "상시채용"
                except:
                    pass

                print(f"    [잡코리아] {title} | 마감일: {deadline_raw}")
                results.append({
                    "id": f"jobkorea_{href}",
                    "title": title,
                    "company": company_name,
                    "link": link,
                    "platform": "잡코리아",
                    "deadline": deadline_raw,
                    "dday": dday,
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
        dday_text = f" | {job.get('dday', '')}" if job.get('dday') and job.get('dday') != '-' else ""
        text += f"*{i}. [{job['company']}] {job['title']}*\n"
        text += f"   📌 {job['platform']}{dday_text}\n"
        text += f"   🔗 {job['link']}\n\n"
    payload = {"text": text}
    response = requests.post(SLACK_WEBHOOK_URL, json=payload)
    print(f"슬랙 전송: {response.status_code}")

def main():
    print(f"[{datetime.now()}] 수집 시작")
    seen_jobs = load_seen_jobs()
    all_jobs = []

    for company in EXACT_COMPANIES:
        print(f"검색: {company}")
        saramin = search_saramin(company)
        jobkorea = search_jobkorea(company)
        print(f"  사람인: {len(saramin)}건, 잡코리아: {len(jobkorea)}건")
        all_jobs.extend(saramin + jobkorea)
        time.sleep(1)

    seen_ids_dedup = set()
    unique_jobs = []
    for job in all_jobs:
        if job["id"] not in seen_ids_dedup:
            unique_jobs.append(job)
            seen_ids_dedup.add(job["id"])

    new_jobs = []
    seen_ids = set()
    for job in unique_jobs:
        if job["id"] not in seen_jobs:
            new_jobs.append(job)
            seen_ids.add(job["id"])

    print(f"새 공고 {len(new_jobs)}건")

    existing_jobs = load_all_jobs()
    existing_ids = {j["id"] for j in existing_jobs}
    for job in unique_jobs:
        if job["id"] not in existing_ids:
            existing_jobs.insert(0, job)
    existing_jobs = existing_jobs[:500]
    save_all_jobs(existing_jobs)

    for i in range(0, len(new_jobs), 20):
        send_slack(new_jobs[i:i+20])

    seen_jobs.update(seen_ids)
    save_seen_jobs(seen_jobs)
    print("완료!")

if __name__ == "__main__":
    main()
