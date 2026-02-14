import re
import threading
import webbrowser
from dataclasses import dataclass
from typing import List, Set, Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import messagebox

RANKING_URL = "https://news.naver.com/main/ranking/popularMemo.naver"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# exe 옆에 만들 수 있는 사용자 차단 키워드 파일(한 줄 1개, 2글자 이상 권장)
USER_BLOCKLIST_FILE = "user_block_keywords.txt"

# URL에 정치 섹션 코드가 확실히 있으면 정치로 간주
POLITICS_SID_PATTERNS = (r"([?&])sid1=100([&#]|$)", r"([?&])sid=100([&#]|$)")

# ✅ 네이버 기능/메뉴 텍스트(기사 아님) — 이런 텍스트는 목록에서 제외
NON_ARTICLE_TITLES = {
    "많이 본 뉴스", "댓글 많은 뉴스", "공감 많은 뉴스", "랭킹뉴스", "랭킹",
    "정치", "경제", "사회", "생활/문화", "IT/과학", "세계", "연예", "스포츠",
    "뉴스", "홈"
}

# ✅ 정치 “확정” 키워드(강하게)
# - 정당/기관/선거/정치인 실명/정치권 표현
DEFAULT_POLITICS_KEYWORDS = {
    # 정당/정치권
    "국민의힘", "국힘", "더불어민주당", "민주당", "정의당", "진보당", "개혁신당",
    "여당", "야당", "여야", "여권", "야권", "정치권", "당대표", "원내대표", "비대위",
    "공천", "경선",

    # 선거
    "선거", "총선", "대선", "지방선거", "보궐선거", "재보궐",

    # 기관/직책
    "국회", "국회의원", "의원", "본회의", "상임위", "법사위", "청문회",
    "대통령", "대통령실", "총리", "장관", "국무", "청와대",
    "헌재", "헌법재판소", "대법원", "검찰", "법무부", "감사원", "국정원",

    # 외교/안보(정치성이 강하게 섞이는 키워드)
    "외교", "안보", "국방", "북한", "대북", "한미", "한일",

    # 정치 관련 사건/프레임
    "탄핵", "계엄", "내란", "특검", "정권", "정국",

    # 자주 등장하는 정치인/인물(요청 예시 포함)
    "윤석열", "한동훈", "배현진", "장동혁", "송영길", "이재명", "이준석", "조국", "홍준표",
    # ‘李’는 특정인 지칭에 많이 쓰지만 매우 짧아서 남용 위험이 있어 기본엔 넣지 않음.
}

# 너무 짧거나 흔해서 위험한 것들은 자동 무시(사용자 파일에도 적용)
ALWAYS_IGNORE = {"윤", "李", "野"}  # 필요한 경우엔 "윤석열", "野당"처럼 구체로

# 제목에 이런 문자만 있는 건 제외(메뉴/버튼류)
MIN_TITLE_LEN = 10


@dataclass
class Article:
    title: str
    url: str


def normalize(s: str) -> str:
    return " ".join((s or "").replace("\u3000", " ").split()).strip()


def load_user_block_keywords() -> Set[str]:
    kws: Set[str] = set()
    try:
        with open(USER_BLOCKLIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if not w or w.startswith("#"):
                    continue
                w = normalize(w)
                # 1글자/위험단어는 자동 무시
                if len(w) <= 1:
                    continue
                if w in ALWAYS_IGNORE:
                    continue
                kws.add(w)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return kws


def is_politics_by_url(url: str) -> bool:
    for pat in POLITICS_SID_PATTERNS:
        if re.search(pat, url):
            return True
    return False


def is_politics_by_title(title: str, block_keywords: Set[str]) -> bool:
    t = normalize(title)
    return any(k in t for k in block_keywords)


def looks_like_article_url(url: str) -> bool:
    """
    기사 링크만 최대한 안정적으로 골라내기 위한 휴리스틱.
    - oid/aid 파라미터가 있거나
    - /article/ 경로를 포함하는 등
    """
    if "news.naver.com" not in url:
        return False

    # 랭킹 메인/탭/기능 페이지 제외
    if "ranking" in url and "read" not in url and "/article/" not in url:
        # 예: popularMemo.naver, rankingList.naver 등
        return False

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # 네이버 기사 URL의 대표적 신호: oid & aid
    if "oid" in qs and "aid" in qs:
        return True

    # 신형 경로 패턴(있을 수 있음)
    if "/article/" in parsed.path:
        return True

    # read.naver.com 도 기사일 때가 있음
    if "read.naver.com" in url:
        return True

    return False


def is_non_article_title(title: str) -> bool:
    t = normalize(title)
    if not t:
        return True
    if t in NON_ARTICLE_TITLES:
        return True
    # “많이 본 뉴스”, “댓글 많은 뉴스” 같은 문구가 포함된 버튼/탭 제거
    for kw in ("많이 본", "댓글 많은", "공감 많은", "랭킹", "더보기"):
        if kw in t and len(t) <= 20:
            return True
    # 너무 짧은 건 메뉴일 확률이 큼
    if len(t) < MIN_TITLE_LEN:
        return True
    return False


def fetch_articles() -> List[Article]:
    r = requests.get(RANKING_URL, headers=HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    block_keywords = set(DEFAULT_POLITICS_KEYWORDS) | load_user_block_keywords()

    result: List[Article] = []
    seen_urls = set()

    for a in soup.select("a[href]"):
        href = normalize(a.get("href", ""))
        title = normalize(a.get_text(" ", strip=True))

        if not href or not title:
            continue

        # 상대경로 -> 절대경로
        if href.startswith("/"):
            href = "https://news.naver.com" + href

        # 기사 링크만 선별
        if not looks_like_article_url(href):
            continue

        # 기능/탭/메뉴 텍스트 제외
        if is_non_article_title(title):
            continue

        # URL 중복 제거
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # 정치 제외
        if is_politics_by_url(href):
            continue
        if is_politics_by_title(title, block_keywords):
            continue

        result.append(Article(title=title, url=href))

    return result


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("네이버 랭킹 - 정치 제외")
        root.geometry("900x650")

        top = tk.Frame(root)
        top.pack(fill="x", padx=12, pady=10)

        self.status = tk.Label(top, text="새로고침을 누르세요.")
        self.status.pack(side="left")

        self.btn = tk.Button(top, text="새로고침", command=self.refresh)
        self.btn.pack(side="right")

        hot = tk.LabelFrame(root, text="지금 제일 핫한 뉴스 (TOP 1)")
        hot.pack(fill="x", padx=12, pady=(0, 10))

        self.top_title = tk.Label(
            hot,
            text="(아직 없음)",
            font=("맑은 고딕", 14, "bold"),
            justify="left",
            anchor="w",
            wraplength=850,
        )
        self.top_title.pack(fill="x", padx=10, pady=(10, 6))

        self.top_open = tk.Button(hot, text="TOP 1 열기", state="disabled", command=self.open_top1)
        self.top_open.pack(anchor="w", padx=10, pady=(0, 10))

        mid = tk.LabelFrame(root, text="나머지 뉴스")
        mid.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.listbox = tk.Listbox(mid, font=("맑은 고딕", 11))
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(mid, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.listbox.bind("<Double-Button-1>", self.open_selected)

        bottom = tk.Frame(root)
        bottom.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(
            bottom,
            text="필터 추가: exe 옆에 user_block_keywords.txt 파일을 만들고, 한 줄에 하나씩(2글자 이상) 추가하면 적용됩니다.",
            fg="#555555",
        ).pack(anchor="w")

        self.articles: List[Article] = []
        self.top1: Optional[Article] = None

    def set_busy(self, busy: bool, msg: str):
        self.btn.config(state=("disabled" if busy else "normal"))
        self.status.config(text=msg)

    def refresh(self):
        def worker():
            try:
                self.root.after(0, lambda: self.set_busy(True, "불러오는 중..."))
                arts = fetch_articles()
                self.root.after(0, lambda: self.update_ui(arts))
            except Exception as e:
                self.root.after(0, lambda: self.set_busy(False, "실패"))
                self.root.after(0, lambda: messagebox.showerror("오류", f"불러오지 못했습니다.\n\n{e}"))

        threading.Thread(target=worker, daemon=True).start()

    def update_ui(self, arts: List[Article]):
        self.articles = arts
        self.listbox.delete(0, tk.END)

        if arts:
            self.top1 = arts[0]
            self.top_title.config(text=self.top1.title)
            self.top_open.config(state="normal")
        else:
            self.top1 = None
            self.top_title.config(text="(표시할 뉴스가 없어요. 필터가 너무 강할 수도 있어요.)")
            self.top_open.config(state="disabled")

        # TOP1 제외한 나머지
        for i, a in enumerate(arts[1:], start=2):
            self.listbox.insert(tk.END, f"{i:02d}. {a.title}")

        self.set_busy(False, f"완료: {len(arts)}개 (정치 제외)")

    def open_top1(self):
        if self.top1:
            webbrowser.open(self.top1.url)

    def open_selected(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        real_idx = sel[0] + 1
        if 0 <= real_idx < len(self.articles):
            webbrowser.open(self.articles[real_idx].url)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
