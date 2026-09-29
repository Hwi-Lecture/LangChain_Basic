"""
삼성전자 반도체 뉴스룸 '반도체 8대 공정' 시리즈 크롤러

각 URL에 접속해 본문 텍스트만 추출하고, 개별 텍스트 파일로 저장한다.
RAG 실습용 코퍼스 구축의 첫 단계(문서 수집)로 사용한다.

실행방법:
cd "4. RAG"
python "0. crawl_semiconductor_8process.py"
"""

import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URLS = [
    ("01_wafer", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-1%ED%83%84-%EC%9B%A8%EC%9D%B4%ED%8D%BC%EB%9E%80-%EB%AC%B4%EC%97%87%EC%9D%BC%EA%B9%8C%EC%9A%94/"),
    ("02_oxidation", "https://news.samsungsemiconductor.com/kr/%eb%b0%98%eb%8f%84%ec%b2%b4-8%eb%8c%80-%ea%b3%b5%ec%a0%95-2%ed%83%84-%ec%9b%a8%ec%9d%b4%ed%8d%bc-%ed%91%9c%eb%a9%b4%ec%9d%84-%eb%b3%b4%ed%98%b8%ed%95%98%eb%8a%94-%ec%82%b0%ed%99%94%ea%b3%b5/"),
    ("03_ic", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-3%ED%83%84-%EC%A0%84%EC%9E%90%EC%82%B0%EC%97%85%EC%9D%98-%ED%98%81%EB%AA%85-%EC%A7%91%EC%A0%81%ED%9A%8C%EB%A1%9C/"),
    ("04_photo", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-4%ED%83%84-%EC%9B%A8%EC%9D%B4%ED%8D%BC%EC%97%90-%ED%9A%8C%EB%A1%9C%EB%A5%BC-%EA%B7%B8%EB%A0%A4-%EB%84%A3%EB%8A%94-%ED%8F%AC%ED%86%A0/"),
    ("05_etching", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-5%ED%83%84-%EB%B0%98%EB%8F%84%EC%B2%B4-%ED%9A%8C%EB%A1%9C%ED%8C%A8%ED%84%B4%EC%9D%98-%EC%99%84%EC%84%B1-%EC%8B%9D%EA%B0%81-%EA%B3%B5/"),
    ("06_deposition_ion_implant", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-6%ED%83%84-%EB%B0%98%EB%8F%84%EC%B2%B4%EA%B0%80-%EC%9B%90%ED%95%98%EB%8A%94-%EC%A0%84%EA%B8%B0%EC%A0%81-%ED%8A%B9%EC%84%B1%EC%9D%84-%EA%B0%96/"),
    ("07_metal_wiring", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-7%ED%83%84-%EC%A0%84%EA%B8%B0%EB%A5%BC-%ED%86%B5%ED%95%98%EA%B2%8C-%ED%95%98%EB%8A%94-%EB%A7%88%EC%A7%80%EB%A7%89-%EC%9E%91%EC%97%85/"),
    ("08_eds", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-8%ED%83%84-%ED%95%A9%EA%B2%A9%EC%9C%BC%EB%A1%9C-%EA%B0%80%EB%8A%94-%EC%B2%AB-%EB%B2%88%EC%A7%B8-%EA%B4%80%EB%AC%B8-edselectrical-die-sorting/"),
    ("09_packaging", "https://news.samsungsemiconductor.com/kr/%EB%B0%98%EB%8F%84%EC%B2%B4-8%EB%8C%80-%EA%B3%B5%EC%A0%95-9%ED%83%84-%EC%99%B8%EB%B6%80%ED%99%98%EA%B2%BD%EC%9C%BC%EB%A1%9C%EB%B6%80%ED%84%B0-%EB%B0%98%EB%8F%84%EC%B2%B4%EB%A5%BC-%EB%B3%B4%ED%98%B8-2/"),
]

OUTPUT_DIR = Path("data/semiconductor_8process_corpus")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
REQUEST_INTERVAL_SEC = 2


def extract_article_text(html: str) -> str:
    """뉴스룸 페이지 HTML에서 제목과 본문만 뽑아낸다."""
    soup = BeautifulSoup(html, "html.parser")

    # 스크립트, 스타일, 네비게이션 등 잡음 제거
    for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # 본문 컨테이너 후보를 순서대로 시도한다.
    # 사이트 구조가 바뀌면 이 셀렉터 목록만 수정하면 된다.
    body_selectors = [
        "article",
        "div.entry-content",
        "div.post-content",
        "div.content",
        "main",
    ]
    body = None
    for selector in body_selectors:
        body = soup.select_one(selector)
        if body:
            break
    if body is None:
        body = soup

    paragraphs = [p.get_text(" ", strip=True) for p in body.find_all(["p", "h2", "h3", "li"])]
    paragraphs = [p for p in paragraphs if p]

    # "관련 콘텐츠 보러가기", "삼성전자 반도체 소식 더 알아보기" 이후의
    # 다른 글 목록은 본문이 아니므로 잘라낸다.
    cut_markers = ["관련 콘텐츠 보러가기", "삼성전자 반도체 소식 더 알아보기"]
    cut_index = len(paragraphs)
    for i, p in enumerate(paragraphs):
        if any(marker in p for marker in cut_markers):
            cut_index = i
            break
    paragraphs = paragraphs[:cut_index]

    body_text = "\n\n".join(paragraphs)
    return f"{title}\n\n{body_text}".strip()


def crawl():
    OUTPUT_DIR.mkdir(exist_ok=True)

    for name, url in URLS:
        out_path = OUTPUT_DIR / f"{name}.txt"
        if out_path.exists():
            print(f"[스킵] {name}: 이미 존재함")
            continue

        print(f"[요청] {name}: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[실패] {name}: {e}")
            continue

        text = extract_article_text(resp.text)
        if len(text) < 50:
            print(f"[경고] {name}: 추출된 본문이 너무 짧음 ({len(text)}자). 셀렉터 확인 필요.")

        out_path.write_text(text, encoding="utf-8")
        print(f"[완료] {name}: {len(text)}자 저장")

        time.sleep(REQUEST_INTERVAL_SEC)


if __name__ == "__main__":
    crawl()
