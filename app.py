import re
import threading
import webbrowser
from dataclasses import dataclass
from typing import List, Set

import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import messagebox

RANKING_URL = "https://news.naver.com/main/ranking/popularMemo.naver"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ✅ 여기 한 파일(txt)만 바꾸면, 앞으로는 exe 다시 만들지 않고도 필터를 조절할 수 있게 해둠
# exe 옆에 "user_block_keywords.txt" 파일을 만들고, 한 줄에 하나씩 키워드를 추가하면 됨.
USER_BLOCKLIST_FILE = "user_block_keywords.txt"

# 정치 섹션 코드(확실한 경우)
POLITICS_SID = {"sid1=100", "sid=100"}

# ✅ 기본 정치 키워드(강화 버전)
# - 정당/기관/선거/인물/사건/재판/계엄/탄핵/국회/대통령실/내란 등
DEFAULT_BLOCK_KEYWORDS = {
    # 정당/정치권
    "국힘", "국민의힘", "더불어민주당", "민주당", "정의당", "개혁신당", "진보당",
    "여당", "야당", "당대표", "원내대표", "비대위", "공천", "경선",

    # 선거
    "선거", "총선", "대선", "지선", "지방선거", "재보궐", "보궐선거", "투표", "득표",

    # 기관/직책
    "국회", "의원", "국회의원", "상임위", "본회의", "법사위", "청문회",
    "대통령", "대통령실", "장관", "총리", "국무회의", "청와대",
    "헌재", "헌법재판소", "대법원", "검찰", "검찰총장", "법무부",

    # 외교/안보(정치성 강한 것들 위주)
    "외교", "안보", "국방", "합참", "NSC", "북한", "대북", "한미", "한일", "중국", "러시아",

    # 사건/프레임
    "탄핵", "내란", "계엄", "비상계엄", "특검", "수사", "기소", "재판", "공판", "구속", "영장",
    "국정감사", "감사원", "국정원", "경호처",

    # 대표 정치인/주요 인물(필요하면 계속 추가)
    "윤석열", "윤", "이재명", "한동훈", "조국", "홍준표", "이준석",
    "오세훈", "박원순", "문재인", "박근혜",

    # 표현
    "정치", "정국", "국정", "정권", "대선주자",
}

@dataclass
class Article:
    title: str
    url: str

def load_user_block_keywords() -> Set[str]:
    kws: Set[str] = set()
    try:
        with open(USER_BLOCKLIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w and not w.startswith("#"):
                    kws.add(w)
    except FileNotFoundError:
        pass
    except Exception:
        # 파일이 깨져도 프로그램은 돌아가게
        pass
    return kws

def is_politics_by_url(url: str) -> bool:
    return any(s in url for s in POLITICS_SID)

def is_politics_by_title(title: str, block_keywords: Set[str]) -> bool:
    t = title.strip()
    return any(k in t for k in block_keywords)

def fetch_articles() -> List[Article]:
    r = requests.get(RANKING_URL, headers=HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    # 정치 키워드(기본 + 사용자 추가)
    block_keywords = set(DEFAULT_BLOCK_KEYWORDS)
    block_keywords |= load_user_block_keywords()

    result: List[Article] = []
    seen = set()

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue

        if href.startswith("/"):
            href = "https://news.naver.com" + href

        if "news.naver.com" not in href:
            continue

        # 너무 짧은 텍스트는 메뉴/탭일 확률이 큼
        if len(title) < 6:
            continue

        key = (title, href)
        if key in seen:
            continue
        seen.add(key)

        # ✅ 정치 제외 (강화)
        if is_politics_by_url(href):
            continue
        if is_politics_by_title(title, block_keywords):
            continue

        result.append(Article(title=title, url=href))

    return result

class App:
    def __init__(self, root):
        self.root = root
        root.title("네이버 랭킹 - 정치 제외")
        root.geometry("900x650")

        # 상단: 상태 + 새로고침
        top = tk.Frame(root)
        top.pack(fill="x", padx=12, pady=10)

        self.status = tk.Label(top, text="새로고침을 누르세요.")
        self.status.pack(side="left")

        self.btn = tk.Button(top, text="새로고침", command=self.refresh)
        self.btn.pack(side="right")

        #
