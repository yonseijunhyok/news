import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np
import pyautogui
import pytesseract
import tkinter as tk
from tkinter import filedialog, messagebox

pyautogui.FAILSAFE = True

CONFIG_PATH = Path("macro_config.json")


@dataclass
class TemplateItem:
    name: str
    path: Path


class MacroApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("로그라이크 선택지 매크로 (Windows)")
        self.root.geometry("930x680")

        self.templates: List[TemplateItem] = []
        self.template_cache: Dict[str, np.ndarray] = {}
        self.running = False
        self.mode = "image"
        self.worker_thread: Optional[threading.Thread] = None
        self.ui_queue: "queue.Queue[str]" = queue.Queue()

        self._build_ui()
        self.load_config()
        self.root.after(120, self.process_ui_queue)

    def _build_ui(self) -> None:
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=12, pady=10)

        tk.Label(top, text="Tesseract 경로:").pack(side="left")
        self.tesseract_path_var = tk.StringVar(value=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        tk.Entry(top, textvariable=self.tesseract_path_var, width=55).pack(side="left", padx=8)
        tk.Button(top, text="찾기", command=self.pick_tesseract).pack(side="left")

        templates_frame = tk.LabelFrame(self.root, text="1) 사전 등록 이미지 (선택지 캡처)")
        templates_frame.pack(fill="both", padx=12, pady=8, expand=True)

        self.template_list = tk.Listbox(templates_frame, height=11)
        self.template_list.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

        btns = tk.Frame(templates_frame)
        btns.pack(side="left", fill="y", padx=10, pady=10)
        tk.Button(btns, text="이미지 추가", width=14, command=self.add_template).pack(pady=4)
        tk.Button(btns, text="선택 제거", width=14, command=self.remove_template).pack(pady=4)
        tk.Button(btns, text="설정 저장", width=14, command=self.save_config).pack(pady=4)

        options = tk.LabelFrame(self.root, text="2) 동작 조건")
        options.pack(fill="x", padx=12, pady=8)

        row1 = tk.Frame(options)
        row1.pack(fill="x", padx=10, pady=6)
        tk.Label(row1, text="이미지 모드 목표 이름:").pack(side="left")
        self.target_name_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.target_name_var, width=22).pack(side="left", padx=8)
        tk.Label(row1, text="(비우면 최고 매칭 이미지 클릭)").pack(side="left")

        row2 = tk.Frame(options)
        row2.pack(fill="x", padx=10, pady=6)
        tk.Label(row2, text="텍스트 모드 키워드(콤마 구분):").pack(side="left")
        self.text_keywords_var = tk.StringVar(value="전투,회복,보상")
        tk.Entry(row2, textvariable=self.text_keywords_var, width=45).pack(side="left", padx=8)

        row3 = tk.Frame(options)
        row3.pack(fill="x", padx=10, pady=6)
        tk.Label(row3, text="탐지 주기(초):").pack(side="left")
        self.interval_var = tk.StringVar(value="0.8")
        tk.Entry(row3, textvariable=self.interval_var, width=10).pack(side="left", padx=8)
        tk.Label(row3, text="이미지 임계값(0~1):").pack(side="left")
        self.threshold_var = tk.StringVar(value="0.86")
        tk.Entry(row3, textvariable=self.threshold_var, width=10).pack(side="left", padx=8)

        controls = tk.Frame(self.root)
        controls.pack(fill="x", padx=12, pady=8)

        tk.Button(controls, text="이미지 모드 시작", command=self.start_image_mode).pack(side="left", padx=4)
        tk.Button(controls, text="텍스트 모드 시작", command=self.start_text_mode).pack(side="left", padx=4)
        tk.Button(controls, text="중지", command=self.stop).pack(side="left", padx=4)

        self.status_var = tk.StringVar(value="준비됨")
        tk.Label(self.root, textvariable=self.status_var, anchor="w", fg="#444").pack(fill="x", padx=14, pady=(0, 10))

        tips = (
            "팁: 앱플레이어를 화면에 띄운 뒤 실행하세요. 클릭은 실제 윈도우 커서로 진행됩니다.\n"
            "긴급 중지는 마우스를 좌상단(0,0)으로 이동하면 FAILSAFE로 정지됩니다."
        )
        tk.Label(self.root, text=tips, justify="left", fg="#666").pack(fill="x", padx=14, pady=(0, 12))

    def pick_tesseract(self) -> None:
        file_path = filedialog.askopenfilename(filetypes=[("tesseract", "tesseract.exe"), ("실행 파일", "*.exe")])
        if file_path:
            self.tesseract_path_var.set(file_path)

    def add_template(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="선택지 이미지 선택",
            filetypes=[("Image", "*.png;*.jpg;*.jpeg;*.bmp")],
        )
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                continue
            if any(t.path == path for t in self.templates):
                continue
            self.templates.append(TemplateItem(name=path.stem, path=path))
            self.template_list.insert(tk.END, f"{path.stem} | {path}")
            self.template_cache.pop(str(path), None)

    def remove_template(self) -> None:
        indices = list(self.template_list.curselection())
        if not indices:
            return
        for idx in reversed(indices):
            key = str(self.templates[idx].path)
            del self.templates[idx]
            self.template_list.delete(idx)
            self.template_cache.pop(key, None)

    def start_image_mode(self) -> None:
        if not self.templates:
            messagebox.showwarning("안내", "먼저 선택지 이미지를 1개 이상 등록하세요.")
            return
        self.mode = "image"
        self.start_worker()

    def start_text_mode(self) -> None:
        self.mode = "text"
        tesseract_path = Path(self.tesseract_path_var.get())
        if not tesseract_path.exists():
            messagebox.showwarning("안내", "Tesseract 경로가 올바르지 않습니다.")
            return
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)
        self.start_worker()

    def start_worker(self) -> None:
        if self.running:
            return

        try:
            interval = max(0.2, float(self.interval_var.get() or "0.8"))
            threshold = float(self.threshold_var.get() or "0.86")
            if threshold < 0 or threshold > 1:
                raise ValueError("임계값은 0~1 사이여야 합니다.")
            self.interval_var.set(str(interval))
        except ValueError as exc:
            messagebox.showwarning("입력 오류", str(exc))
            return

        self.running = True
        self.set_status(f"실행 중 ({self.mode} 모드)")
        self.worker_thread = threading.Thread(target=self.run_loop, daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        self.running = False
        self.set_status("중지됨")

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def process_ui_queue(self) -> None:
        while True:
            try:
                msg = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            self.set_status(msg)
        self.root.after(120, self.process_ui_queue)

    def run_loop(self) -> None:
        with mss.mss() as sct:
            while self.running:
                try:
                    hit = self.find_by_image(sct) if self.mode == "image" else self.find_by_text(sct)
                    if hit:
                        x, y, reason = hit
                        self.ui_queue.put(f"클릭: ({x}, {y}) | {reason}")
                        pyautogui.click(x=x, y=y)
                        time.sleep(0.45)
                except pyautogui.FailSafeException:
                    self.running = False
                    self.ui_queue.put("FAILSAFE 작동: 마우스가 좌상단으로 이동되어 자동 중지됨")
                    break
                except Exception as exc:
                    self.ui_queue.put(f"오류: {exc}")

                interval = max(0.2, float(self.interval_var.get() or "0.8"))
                time.sleep(interval)

    def _grab_screen(self, sct: mss.mss) -> np.ndarray:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = np.array(shot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _load_template(self, path: Path) -> Optional[np.ndarray]:
        cache_key = str(path)
        if cache_key in self.template_cache:
            return self.template_cache[cache_key]
        tpl = cv2.imread(cache_key, cv2.IMREAD_GRAYSCALE)
        if tpl is None:
            return None
        self.template_cache[cache_key] = tpl
        return tpl

    def find_by_image(self, sct: mss.mss) -> Optional[Tuple[int, int, str]]:
        screen = self._grab_screen(sct)
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        threshold = float(self.threshold_var.get() or "0.86")

        target = self.target_name_var.get().strip().lower()
        candidates = self.templates
        if target:
            candidates = [t for t in self.templates if t.name.lower() == target]
            if not candidates:
                return None

        best_score = 0.0
        best_click: Optional[Tuple[int, int, str]] = None

        for item in candidates:
            tpl = self._load_template(item.path)
            if tpl is None:
                continue

            th, tw = tpl.shape
            sh, sw = screen_gray.shape
            if th > sh or tw > sw:
                continue

            res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val > best_score:
                cx = max_loc[0] + tw // 2
                cy = max_loc[1] + th // 2
                best_score = max_val
                best_click = (cx, cy, f"이미지: {item.name} ({max_val:.2f})")

        if best_click and best_score >= threshold:
            return best_click
        return None

    def find_by_text(self, sct: mss.mss) -> Optional[Tuple[int, int, str]]:
        screen = self._grab_screen(sct)
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        data = pytesseract.image_to_data(
            th,
            lang="kor+eng",
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT,
        )
        keywords = [k.strip() for k in self.text_keywords_var.get().split(",") if k.strip()]

        if not keywords:
            return None

        for i, word in enumerate(data.get("text", [])):
            txt = (word or "").strip()
            if not txt:
                continue
            if any(k.lower() in txt.lower() for k in keywords):
                x = data["left"][i] + data["width"][i] // 2
                y = data["top"][i] + data["height"][i] // 2
                return x, y, f"텍스트: {txt}"
        return None

    def save_config(self) -> None:
        payload = {
            "tesseract_path": self.tesseract_path_var.get(),
            "target_name": self.target_name_var.get(),
            "text_keywords": self.text_keywords_var.get(),
            "interval": self.interval_var.get(),
            "threshold": self.threshold_var.get(),
            "templates": [str(t.path) for t in self.templates],
        }
        CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.set_status("설정을 저장했습니다.")

    def load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        self.tesseract_path_var.set(payload.get("tesseract_path", self.tesseract_path_var.get()))
        self.target_name_var.set(payload.get("target_name", ""))
        self.text_keywords_var.set(payload.get("text_keywords", self.text_keywords_var.get()))
        self.interval_var.set(str(payload.get("interval", self.interval_var.get())))
        self.threshold_var.set(str(payload.get("threshold", self.threshold_var.get())))

        template_paths = payload.get("templates", [])
        for fp in template_paths:
            path = Path(fp)
            if path.exists() and not any(t.path == path for t in self.templates):
                self.templates.append(TemplateItem(name=path.stem, path=path))
                self.template_list.insert(tk.END, f"{path.stem} | {path}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MacroApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop(), root.destroy()))
    root.mainloop()
