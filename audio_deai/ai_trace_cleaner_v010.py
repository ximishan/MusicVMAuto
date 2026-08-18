import os
import sys
import math
import time
import queue
import shutil
import signal
import tempfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    import imageio_ffmpeg
except Exception as e:
    imageio_ffmpeg = None

APP_NAME = "AI音频消痕工具"
APP_VERSION = "v0.1.0"
SUPPORTED = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus", ".aiff", ".aif"}

def qpath(p: Path) -> str:
    return str(p)

def ffmpeg_exe() -> str:
    if imageio_ffmpeg is None:
        raise RuntimeError("未找到内置 FFmpeg 组件。")
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not exe or not os.path.exists(exe):
        raise RuntimeError("内置 FFmpeg 不存在。")
    return exe

def lin(db: float) -> float:
    return 10.0 ** (db / 20.0)

PITCH1 = 2.0 ** (-22.0 / 1200.0)
PITCH2 = 0.975

def pitch_chain(sr: int, ratio: float) -> str:
    tempo = 1.0 / ratio
    return f"asetrate={sr}*{ratio:.9f},aresample={sr},atempo={tempo:.9f}"

def stage1_filter() -> str:
    return ",".join([
        "highpass=f=28",
        pitch_chain(44100, PITCH1),
        "treble=g=-0.20:f=8500",
        "treble=g=0:f=7000",
        "treble=g=-1.5:f=10000",
        "treble=g=-2.5:f=12000",
        "lowpass=f=15000",
        "aecho=0.80:0.60:35|55:0.08|0.05",
        "volume=0.82",
        "aresample=44100:dither_method=triangular",
    ])

def stage3_filter() -> str:
    th = lin(-18)
    makeup = lin(1.5)
    plus2 = lin(2.0)
    return ",".join([
        pitch_chain(48000, PITCH2),
        "equalizer=f=80:t=q:w=1:g=4.0",
        "equalizer=f=150:t=q:w=1:g=3.0",
        "equalizer=f=300:t=q:w=1:g=-1.5",
        "equalizer=f=1500:t=q:w=1:g=-1.0",
        "equalizer=f=4000:t=q:w=1:g=3.5",
        "equalizer=f=8000:t=q:w=1:g=1.8",
        "aecho=0.55:0.40:35|45:0.12|0.08",
        "volume=2.0",
        "highpass=f=45",
        f"acompressor=threshold={th:.8f}:ratio=2.0:attack=10:release=120:makeup={makeup:.8f}",
        f"volume={plus2:.8f}",
        "alimiter=limit=0.97",
    ])

def stage4_filter() -> str:
    th = lin(-19)
    return ",".join([
        "highpass=f=28",
        "equalizer=f=120:t=q:w=1:g=0.25",
        "equalizer=f=1800:t=q:w=1:g=0.20",
        "equalizer=f=7200:t=q:w=1:g=-0.18",
        f"acompressor=threshold={th:.8f}:ratio=1.18:attack=24:release=210",
        "alimiter=limit=0.96",
    ])

class Runner:
    def __init__(self, log_cb, progress_cb, stop_event):
        self.log_cb = log_cb
        self.progress_cb = progress_cb
        self.stop_event = stop_event
        self.proc = None

    def log(self, s):
        self.log_cb(s)

    def run_cmd(self, cmd, step_name):
        if self.stop_event.is_set():
            raise RuntimeError("用户已停止。")
        self.log(f"{step_name}：开始")
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        while self.proc.poll() is None:
            if self.stop_event.is_set():
                try:
                    self.proc.terminate()
                except Exception:
                    pass
                raise RuntimeError("用户已停止。")
            time.sleep(0.15)
        out, err = self.proc.communicate()
        code = self.proc.returncode
        self.proc = None
        if code != 0:
            tail = (err or out or "")[-3000:]
            raise RuntimeError(f"{step_name}失败（FFmpeg exit={code}）\n{tail}")
        self.log(f"{step_name}：完成")

    def process_one(self, src: Path, dst: Path):
        exe = ffmpeg_exe()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ai_trace_clean_") as td:
            td = Path(td)
            s1 = td / "01.wav"
            s2 = td / "02.wav"
            s3 = td / "03.wav"

            self.run_cmd([
                exe, "-y", "-hide_banner", "-loglevel", "error",
                "-i", qpath(src),
                "-vn", "-ac", "2", "-ar", "44100",
                "-af", stage1_filter(),
                "-c:a", "pcm_s16le", qpath(s1)
            ], "节点1 频谱/音高/空间处理")

            self.run_cmd([
                exe, "-y", "-hide_banner", "-loglevel", "error",
                "-i", qpath(s1),
                "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
                "-ac", "2", "-ar", "44100",
                "-c:a", "pcm_s16le", qpath(s2)
            ], "节点2 响度归一")

            self.run_cmd([
                exe, "-y", "-hide_banner", "-loglevel", "error",
                "-i", qpath(s2),
                "-af", stage3_filter(),
                "-ac", "2", "-ar", "48000",
                "-c:a", "pcm_s24le", qpath(s3)
            ], "节点3 N19 主处理")

            self.run_cmd([
                exe, "-y", "-hide_banner", "-loglevel", "error",
                "-i", qpath(s3),
                "-map_metadata", "-1",
                "-af", stage4_filter(),
                "-ac", "2", "-ar", "48000",
                "-c:a", "pcm_s16le", qpath(dst)
            ], "节点4 后处理/去元数据")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("820x640")
        self.minsize(760, 560)
        self.stop_event = threading.Event()
        self.worker = None
        self.msgq = queue.Queue()

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.mode = tk.StringVar(value="folder")
        self.suffix = tk.StringVar(value="_消痕")
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.DoubleVar(value=0)

        self.build_ui()
        self.after(100, self.drain_queue)

    def build_ui(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text=f"{APP_NAME}  {APP_VERSION}", font=("Microsoft YaHei UI", 16, "bold"))
        title.pack(anchor="w")
        ttk.Label(root, text="FFmpeg 兼容复刻版：批量处理 WAV / MP3 / FLAC / M4A 等，统一输出 48kHz 16-bit WAV。").pack(anchor="w", pady=(4, 10))

        m = ttk.LabelFrame(root, text="处理范围", padding=10)
        m.pack(fill="x")
        ttk.Radiobutton(m, text="整个目录", value="folder", variable=self.mode, command=self.on_mode_change).pack(side="left")
        ttk.Radiobutton(m, text="单个音频", value="file", variable=self.mode, command=self.on_mode_change).pack(side="left", padx=(18,0))

        f1 = ttk.Frame(root)
        f1.pack(fill="x", pady=(10, 6))
        ttk.Label(f1, text="输入：", width=8).pack(side="left")
        ttk.Entry(f1, textvariable=self.input_path).pack(side="left", fill="x", expand=True)
        ttk.Button(f1, text="选择", command=self.choose_input).pack(side="left", padx=(6,0))

        f2 = ttk.Frame(root)
        f2.pack(fill="x", pady=6)
        ttk.Label(f2, text="输出目录：", width=8).pack(side="left")
        ttk.Entry(f2, textvariable=self.output_path).pack(side="left", fill="x", expand=True)
        ttk.Button(f2, text="选择", command=self.choose_output).pack(side="left", padx=(6,0))

        opts = ttk.LabelFrame(root, text="输出设置", padding=10)
        opts.pack(fill="x", pady=(8, 8))
        ttk.Label(opts, text="文件名后缀：").pack(side="left")
        ttk.Entry(opts, textvariable=self.suffix, width=14).pack(side="left")
        ttk.Label(opts, text="    输出格式固定：WAV / 48kHz / Stereo / PCM 16-bit").pack(side="left")

        note = ttk.LabelFrame(root, text="说明", padding=10)
        note.pack(fill="x", pady=(0,8))
        ttk.Label(
            note,
            text="本版复刻 AVR N19 的主要参数与处理顺序，但用 FFmpeg 标准滤镜替代 SoX reverb/pitch 与 Rubber Band，因此不会与 AVR 输出做到逐字节一致。适合先试听和对比效果。",
            wraplength=760,
            justify="left"
        ).pack(anchor="w")

        barf = ttk.Frame(root)
        barf.pack(fill="x", pady=(4,6))
        self.start_btn = ttk.Button(barf, text="开始处理", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(barf, text="停止", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8,0))
        ttk.Label(barf, textvariable=self.status_var).pack(side="right")

        ttk.Progressbar(root, maximum=100, variable=self.progress_var).pack(fill="x")

        logf = ttk.LabelFrame(root, text="运行日志", padding=6)
        logf.pack(fill="both", expand=True, pady=(8,0))
        self.logbox = tk.Text(logf, height=18, wrap="word")
        self.logbox.pack(fill="both", expand=True)
        self.logbox.configure(state="disabled")

    def on_mode_change(self):
        self.input_path.set("")

    def choose_input(self):
        if self.mode.get() == "file":
            p = filedialog.askopenfilename(
                title="选择音频",
                filetypes=[("音频文件", "*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.wma *.opus *.aiff *.aif"), ("全部文件", "*.*")]
            )
        else:
            p = filedialog.askdirectory(title="选择音频目录")
        if p:
            self.input_path.set(p)
            if not self.output_path.get():
                base = Path(p).parent if self.mode.get() == "file" else Path(p)
                self.output_path.set(str(base / "AI消痕输出"))

    def choose_output(self):
        p = filedialog.askdirectory(title="选择输出目录")
        if p:
            self.output_path.set(p)

    def post(self, kind, payload):
        self.msgq.put((kind, payload))

    def log(self, msg):
        self.post("log", msg)

    def drain_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {payload}\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "progress":
                    self.progress_var.set(payload)
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.worker = None
                    ok, msg = payload
                    if ok:
                        messagebox.showinfo("完成", msg)
                    else:
                        messagebox.showerror("处理停止", msg)
        except queue.Empty:
            pass
        self.after(100, self.drain_queue)

    def collect_files(self):
        raw = self.input_path.get().strip()
        if not raw:
            raise RuntimeError("请选择输入音频或目录。")
        p = Path(raw)
        if self.mode.get() == "file":
            if not p.is_file():
                raise RuntimeError("输入文件不存在。")
            if p.suffix.lower() not in SUPPORTED:
                raise RuntimeError(f"暂不支持该格式：{p.suffix}")
            return [p]
        if not p.is_dir():
            raise RuntimeError("输入目录不存在。")
        files = [x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in SUPPORTED]
        files.sort(key=lambda x: str(x).lower())
        if not files:
            raise RuntimeError("目录里没有找到支持的音频文件。")
        return files

    def start(self):
        if self.worker:
            return
        try:
            _ = ffmpeg_exe()
            files = self.collect_files()
            outdir = Path(self.output_path.get().strip())
            if not str(outdir):
                raise RuntimeError("请选择输出目录。")
        except Exception as e:
            messagebox.showerror("无法开始", str(e))
            return

        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress_var.set(0)
        self.worker = threading.Thread(target=self.worker_main, args=(files, outdir), daemon=True)
        self.worker.start()

    def worker_main(self, files, outdir):
        runner = Runner(self.log, lambda x: self.post("progress", x), self.stop_event)
        ok_count = 0
        try:
            self.log(f"检测到 {len(files)} 个音频。")
            self.log(f"内置 FFmpeg：{ffmpeg_exe()}")
            for i, src in enumerate(files, 1):
                if self.stop_event.is_set():
                    raise RuntimeError("用户已停止。")
                self.post("status", f"处理中 {i}/{len(files)}：{src.name}")
                self.log("=" * 60)
                self.log(f"开始：{src}")
                suffix = self.suffix.get().strip() or "_消痕"
                dst = outdir / f"{src.stem}{suffix}.wav"
                if dst.exists():
                    n = 2
                    while True:
                        cand = outdir / f"{src.stem}{suffix}_{n}.wav"
                        if not cand.exists():
                            dst = cand
                            break
                        n += 1
                runner.process_one(src, dst)
                ok_count += 1
                self.log(f"完成输出：{dst}")
                self.post("progress", i * 100.0 / len(files))
            self.post("status", f"完成：{ok_count}/{len(files)}")
            self.post("done", (True, f"处理完成，共 {ok_count} 个音频。\n输出目录：{outdir}"))
        except Exception as e:
            self.log(f"停止：{e}")
            self.post("status", "已停止")
            self.post("done", (False, str(e)))

    def stop(self):
        if self.worker:
            self.stop_event.set()
            self.status_var.set("正在停止…")

if __name__ == "__main__":
    app = App()
    app.mainloop()
