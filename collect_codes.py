import requests
import json
import time
from bs4 import BeautifulSoup
from companies import EXACT_COMPANIES

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def get_saramin_code(company):
    """사람인에서 기업 코드 찾기"""
    try:
        url = f"https://www.saramin.co.kr/zf_user/search?searchword={requests.utils.quote(company)}&searchType=search&recruitPage=1&recruitSort=relation&recruitPageCount=5"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for item in soup.select(".item_recruit"):
                company_el = item.select_one(".corp_name a")
                if not company_el:
                    continue
                company_name = company_el.get_text(strip=True)
                if company in company_name or company_name in company:
                    href = company_el.get("href", "")
                    # href 예시: /zf_user/company-info/view?csn=1234567890
                    if "csn=" in href:
                        code = href.split("csn=")[1].split("&")[0]
                        return code
    except Exception as e:
        print(f"사람인 코드 오류 ({company}): {e}")
    return None

def get_jobkorea_code(company):
    """잡코리아에서 기업 코드 찾기"""
    try:
        url = f"https://www.jobkorea.co.kr/Search/?stext={requests.utils.quote(company)}&tabType=recruit&dkwrd=10003843052"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.select("a[href*='/Recruit/GI_Read/']")
            href_map = {}
            for link_el in links:
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
                company_name = texts[1]
                if company in company_name or company_name in company:
                    # 기업 페이지 링크 찾기
                    co_links = soup.select(f"a[href*='/Co_Read/']")
                    for co_link in co_links:
                        co_href = co_link.get("href", "")
                        co_name = co_link.get_text(strip=True)
                        if company in co_name or co_name in company:
                            # href 예시: /Co_Read/C/GI_Read/48893072
                            parts = co_href.split("/")
                            if len(parts) >= 3:
                                return parts[2]
    except Exception as e:
        print(f"잡코리아 코드 오류 ({company}): {e}")
    return None

def main():
    codes = {}
    total = len(EXACT_COMPANIES)

    for i, company in enumerate(EXACT_COMPANIES):
        print(f"[{i+1}/{total}] {company} 코드 수집 중...")
        saramin_code = get_saramin_code(company)
        jobkorea_code = get_jobkorea_code(company)
        codes[company] = {
            "saramin": saramin_code,
            "jobkorea": jobkorea_code
        }
        print(f"  사람인: {saramin_code}, 잡코리아: {jobkorea_code}")
        time.sleep(1)

    with open("company_codes.json", "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)

    print(f"\n완료! company_codes.json 저장됨")
    found_saramin = sum(1 for v in codes.values() if v["saramin"])
    found_jobkorea = sum(1 for v in codes.values() if v["jobkorea"])
    print(f"사람인 코드 수집: {found_saramin}/{total}")
    print(f"잡코리아 코드 수집: {found_jobkorea}/{total}")

if __name__ == "__main__":
    main()
