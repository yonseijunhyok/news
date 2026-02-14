import re
import threading
import webbrowser
from dataclasses import dataclass
from typing import List

import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import messagebox

RANKING_URL = "https://news.naver.com/main/ranking/popularMemo.naver"

POLITICS_KEYWORDS = [
    "국회","정당","여당","야당","선거","총선","대선","지방선거",
    "대통령","대통령실","청와대","장관","국무","헌재","탄핵",
    "의원","법안","정책","외교","안보","북한","통일"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

@dataclass
class Article:
    title: str
    url: str

def is_politics(url: str, title: str) -> bool:
    if "sid1=100" in url or "sid=100" in url:
        return True
    return any(k in title for k in POLITICS_KEYWORDS)

def fetch_articles() -> List[Article]:
    r = requests.get(RANKING_URL, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(r.text, "lxml")
    result = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a.get("href","")
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        if href.startswith("/"):
            href = "https://news.naver.com" + href
        if "news.naver.com" not in href:
            continue
        if len(title) < 6:
            continue
        if (title, href) in seen:
            continue
        seen.add((title, href))
        if is_politics(href, title):
            continue
        result.append(Article(title, href))
    return result

class App:
    def __init__(self, root):
        self.root = root
        root.title("네이버 랭킹 - 정치 제외")
        root.geometry("900x600")

        self.status = tk.Label(root, text="새로고침을 누르세요")
        self.status.pack()

        self.btn = tk.Button(root, text="새로고침", command=self.refresh)
        self.btn.pack()

        self.listbox = tk.Listbox(root, font=("맑은 고딕",11))
        self.listbox.pack(fill="both", expand=True)

        self.listbox.bind("<Double-Button-1>", self.open_selected)
        self.articles = []

    def refresh(self):
        def worker():
            try:
                self.status.config(text="불러오는 중...")
                arts = fetch_articles()
                self.root.after(0, lambda:self.update_list(arts))
            except Exception as e:
                messagebox.showerror("오류", str(e))
        threading.Thread(target=worker, daemon=True).start()

    def update_list(self, arts):
        self.articles = arts
        self.listbox.delete(0, tk.END)
        for i,a in enumerate(arts,1):
            self.listbox.insert(tk.END, f"{i:02d}. {a.title}")
        self.status.config(text=f"{len(arts)}개 (정치 제외)")

    def open_selected(self, event):
        sel = self.listbox.curselection()
        if sel:
            webbrowser.open(self.articles[sel[0]].url)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()