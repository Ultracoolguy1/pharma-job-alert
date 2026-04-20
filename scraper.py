import requests
import json
import os
import time
import re
from datetime import datetime, timedelta
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

def calc_dday(deadline_str):
    """마감일 문자열로 D-day 계산. 예: '05/15' → 'D-26'"""
    if not deadline_str or deadline_str in ["상시채용", "채용시마감", "-"]:
        return deadline_str or "-"
    try:
        now = datetime.now()
        # MM/DD 형식
        if re.match(r"\d{2}/\d{2}", deadline_str):
            month, day = deadline_str.split("/")
            deadline = datetime(now.year, int(month), int(day))
            if deadline < now:
                deadline = datetime(now.year + 1, int(month), int(day))
        # YYYY.MM.DD 형식
        elif re.match(r"\d{4}\.\d{2}\.\d{2}", deadline_str):
            deadline = datetime.strptime(deadline_str, "%Y.%m.%d")
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
                link = "https://www.saramin.co.kr" + title_el.get("href", "")

                # 마감일 추출
                deadline_raw = ""
                date_el = item.select_one(".job_date .date")
                if date_el:
                    deadline_raw = date_el.get_text(strip=True)
                else:
                    limit_el = item.select_one(".job_condition span:last-child")
                    if limit_el:
                        deadline_raw = limit_el.get_text(strip=True)

                dday = calc_dday(deadline_raw)

                if is_target_company(company_name):
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

                # 잡코리아 마감일: 해당 링크 주변 텍스트에서 날짜 패턴 찾기
                deadline_raw = ""
                dday = "-"
                try:
                    link_el = soup.find("a", href=lambda h: h and href in h)
                    if link_el:
                        parent = link_el.find_parent()
                        if parent:
                            text_content = parent.get_text()
                            date_match = re.search(r"(\d{2}/\d{2})|(\d{4}\.\d{2}\.\d{2})", text_content)
                            if date_match:
                                deadline_raw = date_match.group()
                                dday = calc_dday(deadline_raw)
                            elif "상시" in text_content:
                                deadline_raw = "상시채용"
                                dday = "상시채용"
                except:
                    pass

                if is_target_company(company_name):
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
        dday_text = f" | {job.get('dday', '')}" if job.get('dday') else ""
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

    # 플랫폼 간 중복 제거
    seen_titles = {}
    unique_jobs = []
    for job in all_jobs:
        title_key = f"{job['company']}_{job['title']}"
        if title_key not in seen_titles:
            unique_jobs.append(job)
            seen_titles[title_key] = True

    # 새 공고 찾기
    new_jobs = []
    seen_ids = set()
    for job in unique_jobs:
        if job["id"] not in seen_jobs:
            new_jobs.append(job)
            seen_ids.add(job["id"])

    print(f"새 공고 {len(new_jobs)}건")

    # jobs.json 업데이트
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
