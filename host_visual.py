from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw

VK_F8, VK_ESCAPE = 0x77, 0x1B
SCALES = (0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15)


def app_dir():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def key_down(vk):
    return os.name == "nt" and bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def setup_windows():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try: ctypes.windll.user32.SetProcessDPIAware()
            except Exception: pass
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.06


setup_windows()
ROOT = app_dir()
CONFIG = ROOT / "host_visual_config.json"
TEMPLATES = ROOT / "templates"
FAILURES = ROOT / "failures"

SPECS = {
    "line_settings": ("线路设置", 170, 58, 0.88),
    "verify_all_ip": ("验证所有IP", 180, 62, 0.88),
    "ip_checkmark": ("验证成功 √", 90, 56, 0.86),
    "qq_ready": ("QQ音乐加载完成标志", 220, 80, 0.84),
    "playlist_1": ("第1个歌单", 260, 70, 0.84),
    "playlist_2": ("第2个歌单", 260, 70, 0.84),
    "play_button": ("歌单播放按钮", 150, 62, 0.84),
    "playing_state": ("正在播放状态（可选）", 150, 70, 0.84),
    "popup_close": ("QQ普通弹窗关闭按钮（可选）", 150, 70, 0.86),
}

DEFAULT = {
    "vmware_title_keyword": "VMware",
    "base_date": "2026-08-12",
    "qqmusic_exe": r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
    "last_hits": {},
    "hints": {},
}


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT))
    if CONFIG.exists():
        try:
            data = json.loads(CONFIG.read_text(encoding="utf-8"))
            cfg.update({k: data[k] for k in DEFAULT if k in data})
        except Exception:
            pass
    return cfg


def save_cfg(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def tpl(key): return TEMPLATES / (key + ".png")


def playlist_today(base):
    return ((date.today() - date.fromisoformat(base)).days % 2) + 1


def vmware(keyword, activate=True):
    wins = [w for w in gw.getAllWindows() if keyword.lower() in (w.title or "").lower()]
    if not wins and keyword.lower() != "vmware":
        wins = [w for w in gw.getAllWindows() if "vmware" in (w.title or "").lower()]
    if not wins: raise RuntimeError("找不到 VMware 窗口。")
    w = max(wins, key=lambda x: max(1, x.width) * max(1, x.height))
    if w.isMinimized: w.restore(); time.sleep(.4)
    if activate:
        try: w.activate()
        except Exception: pass
        time.sleep(.35)
    return w


def screenshot(w):
    p = pyautogui.screenshot(region=(int(w.left), int(w.top), int(w.width), int(w.height)))
    return cv2.cvtColor(np.array(p), cv2.COLOR_RGB2BGR)


def read_img(path):
    if not path.exists(): return None
    raw = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


def write_img(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, data = cv2.imencode(".png", image)
    if not ok: raise RuntimeError("图片保存失败。")
    data.tofile(str(path))


class Vision:
    def __init__(self, cfg, log): self.cfg, self.log = cfg, log

    def _match(self, screen, template):
        s = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        best = None
        for scale in SCALES:
            tw, th = int(t.shape[1] * scale), int(t.shape[0] * scale)
            if tw < 8 or th < 8 or tw >= s.shape[1] or th >= s.shape[0]: continue
            r = cv2.resize(t, (tw, th), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
            _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(s, r, cv2.TM_CCOEFF_NORMED))
            item = {"score": float(score), "x": loc[0], "y": loc[1], "w": tw, "h": th, "scale": scale}
            if best is None or item["score"] > best["score"]: best = item
        return best

    def locate(self, w, key, full=True):
        template = read_img(tpl(key))
        if template is None: raise RuntimeError("模板未录制：" + SPECS[key][0])
        screen = screenshot(w)
        threshold = SPECS[key][3]
        h, sw = screen.shape[:2]
        hint = self.cfg.get("last_hits", {}).get(key) or self.cfg.get("hints", {}).get(key)
        if hint:
            cx, cy = int(hint["rx"] * sw), int(hint["ry"] * h)
            px, py = max(180, template.shape[1] * 2), max(120, template.shape[0] * 2)
            x1, y1, x2, y2 = max(0, cx-px), max(0, cy-py), min(sw, cx+px), min(h, cy+py)
            best = self._match(screen[y1:y2, x1:x2], template)
            if best and best["score"] >= threshold:
                best["x"], best["y"] = best["x"] + x1, best["y"] + y1
                return self._finish(w, screen, key, best)
        if not full: return None
        best = self._match(screen, template)
        if not best or best["score"] < threshold:
            self.log(f"未识别 {SPECS[key][0]}，最高相似度={0 if not best else best['score']:.3f}")
            return None
        return self._finish(w, screen, key, best)

    def _finish(self, w, screen, key, best):
        cx, cy = best["x"] + best["w"]//2, best["y"] + best["h"]//2
        h, sw = screen.shape[:2]
        self.cfg.setdefault("last_hits", {})[key] = {"rx": round(cx/sw, 6), "ry": round(cy/h, 6)}
        save_cfg(self.cfg)
        best["sx"], best["sy"] = int(w.left + cx), int(w.top + cy)
        return best

    def click(self, w, key):
        m = self.locate(w, key, True)
        if not m: raise RuntimeError("没有可靠识别到“" + SPECS[key][0] + "”，已停止，绝不坐标兜底。")
        self.log(f"识别 {SPECS[key][0]}：{m['score']:.3f}，scale={m['scale']:.2f}")
        pyautogui.click(m["sx"], m["sy"])
        return m


class App(tk.Tk):
    def __init__(self):
        super().__init__(); TEMPLATES.mkdir(exist_ok=True); FAILURES.mkdir(exist_ok=True)
        self.cfg, self.capturing = load_cfg(), False
        self.title("MusicVMAuto v0.4 - IP + QQ音乐（视觉版）"); self.geometry("930x850")
        self.build(); self.vision = Vision(self.cfg, self.log); self.after(300, self.notice)

    def build(self):
        r = ttk.Frame(self, padding=12); r.pack(fill="both", expand=True)
        ttk.Label(r, text="MusicVMAuto v0.4 - IP验证 + QQ音乐", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(r, text="宿主机运行。每次先识别当前画面再点击，不依赖窗口固定位置；模板通常只录一次，失败才重录。", wraplength=890).pack(anchor="w", pady=(3,10))
        c = ttk.LabelFrame(r, text="配置", padding=10); c.pack(fill="x")
        self.vm = tk.StringVar(value=self.cfg["vmware_title_keyword"]); self.base = tk.StringVar(value=self.cfg["base_date"]); self.qq = tk.StringVar(value=self.cfg["qqmusic_exe"])
        ttk.Label(c, text="VMware关键字").grid(row=0,column=0,sticky="w"); ttk.Entry(c,textvariable=self.vm,width=20).grid(row=0,column=1,sticky="ew",padx=6)
        ttk.Label(c, text="基准日期（歌单1）").grid(row=1,column=0,sticky="w"); ttk.Entry(c,textvariable=self.base,width=16).grid(row=1,column=1,sticky="w",padx=6)
        ttk.Label(c, text="QQ路径").grid(row=2,column=0,sticky="w"); ttk.Entry(c,textvariable=self.qq,width=65).grid(row=2,column=1,columnspan=2,sticky="ew",padx=6)
        ttk.Button(c,text="保存",command=self.save_ui).grid(row=0,column=3,rowspan=3,padx=6,sticky="ns"); c.columnconfigure(1,weight=1)
        f = ttk.LabelFrame(r, text="录制视觉模板：点记录 → 鼠标移到目标中央 → F8保存 / Esc取消", padding=10); f.pack(fill="x",pady=10)
        self.status={}
        for i,key in enumerate(SPECS):
            ttk.Label(f,text=SPECS[key][0],width=30).grid(row=i,column=0,sticky="w",pady=2); v=tk.StringVar(); self.status[key]=v
            ttk.Label(f,textvariable=v,width=10).grid(row=i,column=1); ttk.Button(f,text="记录",command=lambda k=key:self.record(k)).grid(row=i,column=2,padx=4)
            ttk.Button(f,text="测试识别",command=lambda k=key:self.run_bg(lambda:self.test(k))).grid(row=i,column=3,padx=4)
        self.refresh_status()
        a=ttk.LabelFrame(r,text="测试当前虚拟机",padding=10); a.pack(fill="x",pady=(0,10))
        ttk.Button(a,text="1. IP验证",command=lambda:self.run_bg(self.ip_flow)).grid(row=0,column=0,padx=5,sticky="ew")
        ttk.Button(a,text="2. QQ音乐",command=lambda:self.run_bg(self.qq_flow)).grid(row=0,column=1,padx=5,sticky="ew")
        ttk.Button(a,text="完整：IP → QQ",command=lambda:self.run_bg(self.full_flow)).grid(row=0,column=2,padx=5,sticky="ew")
        for i in range(3): a.columnconfigure(i,weight=1)
        ttk.Label(a,text="IP只点击“验证所有IP”，每次等√，最多3次；失败截图。QQ用 Win+R 启动你给的 QQMusic.exe 路径。",wraplength=870).grid(row=1,column=0,columnspan=3,sticky="w",pady=(7,0))
        l=ttk.LabelFrame(r,text="日志",padding=8); l.pack(fill="both",expand=True); self.box=tk.Text(l,height=14); self.box.pack(fill="both",expand=True)

    def notice(self):
        self.log("配置："+str(CONFIG)); self.log("模板："+str(TEMPLATES)); self.log("v0.4 不再使用固定坐标正式点击。")

    def log(self,msg):
        text=f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        try:self.after(0,lambda t=text:(self.box.insert("end",t+"\n"),self.box.see("end")))
        except Exception:pass

    def save_ui(self):
        if threading.current_thread() is not threading.main_thread(): return
        self.cfg["vmware_title_keyword"]=self.vm.get().strip() or "VMware"; self.cfg["base_date"]=self.base.get().strip() or "2026-08-12"; self.cfg["qqmusic_exe"]=self.qq.get().strip() or DEFAULT["qqmusic_exe"]; save_cfg(self.cfg)

    def refresh_status(self):
        for k,v in self.status.items():v.set("已录制" if tpl(k).exists() else "未录制")

    def record(self,key):
        if self.capturing:return
        self.save_ui(); w=vmware(self.cfg["vmware_title_keyword"],True); label,width,height,_=SPECS[key]
        messagebox.showinfo("记录模板",f"程序最小化后，把鼠标移动到“{label}”中央，按 F8 保存。Esc取消。没有倒计时。")
        self.capturing=True; self.iconify(); threading.Thread(target=self.record_worker,args=(key,width,height,w),daemon=True).start()

    def record_worker(self,key,width,height,w):
        try:
            while key_down(VK_F8) or key_down(VK_ESCAPE):time.sleep(.05)
            while self.capturing:
                if key_down(VK_ESCAPE):self.capturing=False;self.after(0,self.deiconify);return
                if key_down(VK_F8):
                    x,y=pyautogui.position(); w=vmware(self.cfg["vmware_title_keyword"],False)
                    if not(w.left<=x<w.left+w.width and w.top<=y<w.top+w.height):raise RuntimeError("鼠标不在 VMware 窗口内。")
                    left=max(int(w.left),int(x-width//2));top=max(int(w.top),int(y-height//2));right=min(int(w.left+w.width),left+width);bottom=min(int(w.top+w.height),top+height)
                    p=pyautogui.screenshot(region=(left,top,right-left,bottom-top));write_img(tpl(key),cv2.cvtColor(np.array(p),cv2.COLOR_RGB2BGR))
                    self.cfg.setdefault("hints",{})[key]={"rx":round((x-w.left)/w.width,6),"ry":round((y-w.top)/w.height,6)};self.cfg.get("last_hits",{}).pop(key,None);save_cfg(self.cfg)
                    self.capturing=False;self.after(0,self.deiconify);self.after(100,self.refresh_status);self.log("模板已保存："+SPECS[key][0]);return
                time.sleep(.05)
        except Exception as e:self.capturing=False;self.after(0,self.deiconify);self.after(100,lambda err=str(e):messagebox.showerror("记录失败",err))

    def test(self,key):
        w=vmware(self.cfg["vmware_title_keyword"],True);m=self.vision.locate(w,key,True)
        if not m:raise RuntimeError("识别失败："+SPECS[key][0])
        pyautogui.moveTo(m["sx"],m["sy"],duration=.25);self.log(f"测试成功 {SPECS[key][0]} 相似度={m['score']:.3f}，只移动鼠标不点击。")

    def need(self,*keys):
        miss=[SPECS[k][0] for k in keys if not tpl(k).exists()]
        if miss:raise RuntimeError("请先录制："+"、".join(miss))

    def failshot(self,w,name):
        try:path=FAILURES/(datetime.now().strftime("%Y%m%d-%H%M%S")+"_"+name+".png");write_img(path,screenshot(w));self.log("失败截图："+str(path))
        except Exception:pass

    def ip_flow(self):
        self.need("line_settings","verify_all_ip","ip_checkmark");w=vmware(self.cfg["vmware_title_keyword"],True)
        try:
            self.vision.click(w,"line_settings");time.sleep(.6)
            if self.vision.locate(w,"ip_checkmark",True):self.log("已有√，IP成功，无需点击验证。 ");return True
            for attempt in range(1,4):
                self.log(f"验证IP {attempt}/3");self.vision.click(w,"verify_all_ip");deadline=time.time()+8;poll=0
                while time.time()<deadline:
                    poll+=1
                    if self.vision.locate(w,"ip_checkmark",poll%4==0):self.log(f"检测到√，IP成功，点击次数={attempt}");return True
                    time.sleep(.7)
            raise RuntimeError("验证所有IP已点击3次，仍没有√。不会点击其他按钮。")
        except Exception:self.failshot(w,"ip_failed");raise

    def close_popup(self,w):
        if tpl("popup_close").exists():
            m=self.vision.locate(w,"popup_close",True)
            if m:pyautogui.click(m["sx"],m["sy"]);self.log("关闭了已录制的QQ普通弹窗。");time.sleep(.5)

    def launch_qq(self,w):
        self.vision.click(w,"line_settings");time.sleep(.2);path=self.cfg["qqmusic_exe"]
        pyautogui.hotkey("win","r");time.sleep(.5);pyautogui.write('"'+path+'"',interval=.004);pyautogui.press("enter");self.log("已通过 Win+R 启动 QQ音乐："+path)

    def qq_flow(self):
        self.need("line_settings","playlist_1","playlist_2","play_button");w=vmware(self.cfg["vmware_title_keyword"],True)
        try:
            self.launch_qq(w);deadline=time.time()+25;stable=0
            if tpl("qq_ready").exists():
                while time.time()<deadline:
                    self.close_popup(w);m=self.vision.locate(w,"qq_ready",True);stable=stable+1 if m else 0
                    if stable>=2:break
                    time.sleep(.8)
                if stable<2:raise RuntimeError("QQ音乐25秒内未识别到加载完成。")
            else:time.sleep(10)
            self.close_popup(w);idx=playlist_today(self.cfg["base_date"]);self.log("今天播放第"+str(idx)+"个歌单");self.vision.click(w,"playlist_"+str(idx));time.sleep(.8);self.close_popup(w);self.vision.click(w,"play_button")
            if tpl("playing_state").exists():
                end=time.time()+8
                while time.time()<end:
                    if self.vision.locate(w,"playing_state",True):self.log("已确认正在播放。");return True
                    time.sleep(.8)
                raise RuntimeError("已点播放，但未识别到正在播放状态。")
            self.log("已完成播放点击；未录制播放状态模板，因此暂不做最终确认。");return True
        except Exception:self.failshot(w,"qq_failed");raise

    def full_flow(self):
        if self.ip_flow():self.qq_flow();self.log("完整流程成功：IP → QQ音乐。")

    def run_bg(self,fn):
        self.save_ui()
        def worker():
            try:fn()
            except Exception as e:self.log("执行失败："+str(e));self.after(0,lambda err=str(e):messagebox.showerror("执行失败",err))
        threading.Thread(target=worker,daemon=True).start()


if __name__ == "__main__":App().mainloop()
