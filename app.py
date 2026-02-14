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

# exe 옆에 이 파일을 만들면, 한 줄에 하나씩 "강한 차단 단어(구체 표현)"를 추가할 수 있음
USER_BLOCKLIST_FILE = "user_block_keywords.txt"

# URL에 이 섹션 코드가 있으면 정치로 확정
POLITICS_SID = {"sid1=100", "sid=100"}


# ✅ 1) 정치 "확정" 단어들: 이 중 하나라도 제목에 있으면 바로 차단
#    (정당/정치인 실명/기관/선거 등)
DEFAULT_STRONG = {
    # 정당/정치권
    "국민의힘", "더불어민주당", "정의당", "진보당", "개혁신당",
    "국힘", "민주당", "여당", "야당", "당대표", "원내대표", "비대위", "공천", "경선",

    # 선거
    "총선", "대선", "지방선거", "보궐선거", "재보궐", "투표", "득표",

    # 기관/직책
    "국회", "국회의원", "의원", "본회의", "상임위", "법사위", "청문회",
    "대통령실", "대통령", "총리", "장관", "국무회의", "청와대",
    "헌법재판소", "헌재", "국정원", "감사원",

    # 대표 정치인(✅ 한 글자 금지: "윤" 같은 건 절대 넣지 않음)
    "윤석열", "이재명", "한동훈", "이준석", "조국", "홍준표", "오세훈", "문재인", "박근혜",
}

# ✅ 2) 정치 "맥락" 단어들: 이것만으로는 차단하지 않음 (문맥용)
CONTEXT = {
    "정권", "정국", "국정", "정치권", "정치권의", "여의도",
    "대통령실", "국회", "정당", "선거", "공천", "경선",
    "외교", "안보", "대북", "북한", "한미", "한일",
    "검찰", "법무부", "특검", "국정감사",
}

# ✅ 3) 애매한 단어들: 단독으로는 차단하지 않음 (맥락 단어랑 같이 있을 때만 차단)
WEAK = {
    "재판", "수사", "기소", "구속", "영장", "공판",
    "발언", "논란", "비판", "반박", "공방", "공격",
    "파장", "격돌", "폭로", "혐의",
    "탄핵", "계엄", "내란",  # 이건 정치성이 강하지만, 기사 맥락상 완충을 위해 "맥락+약어"로 처리
}

# ✅ 4) 아주 흔한 단어는 사용자 파일에 있어도 무시(실수 방지)
#    (원하면 추가 가능)
ALWAYS_IGNORE = {"윤", "재판", "수사"}  # <- 너무 넓게 잡히는 것들


@dataclass
class Article:
    title: str
    url: str


def normalize(s: str) -> str:
    # 공백/특수기호를 대충 정리해서 매칭 안정화
    return " ".join(s.replace("\u3000", " ").split()).strip()


def load_user_block_keywords() -> Set[str]:
    kws: Set[str] = set()
    try:
        with open(USER_BLOCKLIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if not w or w.startswith("#"):
                    continue
                w = normalize(w)
                # ✅ 한 글자는 무시 (윤 같은 실수 방지)
                if len(w) <= 1:
                    continue
                # ✅ 너무 흔한 단어는 무시
                if w in ALWAYS_IGNORE:
                    continue
                kws.add(w)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return kws


def is_politics_by_url(url: str) -> bool:
    return any(s in url for s in POLITICS_SID)


def contains_any(text: str, words: Set[str]) -> bool:
    return any(w in text for w in words)


def is_politics_smart(title: str, strong: Set[str], context: Set[str], weak: Set[str]) -> bool:
    t = normalize(title)

    # 1) 확정 단어는 바로 차단
    if contains_any(t, strong):
        return True

    # 2) 애매한 단어는 "정치 맥락"이 같이 있을 때만 차단
    has_context = contains_any(t, context)
    has_weak = contains_any(t, weak)
    if has_context and has_weak:
        return True

    # 3) 아주 정치성이 강한 조합(특정 표현)
    #    (여기서도 짧은 단어 단독은 쓰지 않음)
    special_phrases = {
        "내란 재판", "계엄 논란", "탄핵 정국", "특검 추진", "공천 논란",
        "대통령실 브리핑", "국회 통과", "법안 발의", "국정감사",
    }
    if contains_any(t, special_phrases):
        return True

    return False


def fetch_articles() -> List[Article]:
    r = requests.get(RANKING_URL, headers=HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    user_strong = load_user_block_keywords()

    strong = set(DEFAULT_STRONG) | user_strong
    context = set(CONTEXT)
    weak = set(WEAK)

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

        if len(title) < 6:
            continue

        key = (title, href)
        if key in seen:
            continue
        seen.add(key)

        # 정치 제외
        if is_politics_by_url(href):
            continue
        if is_politics_smart(title, strong, context, weak):
            continue

        result.append(Article(title=normalize(title), url=href))

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
        self.top1: Article | None = None

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
