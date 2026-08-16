from pathlib import Path
import re

p = Path('avr_cover_single_demo.py')
s = p.read_text(encoding='utf-8')

s = s.replace('AVR 翻唱逐首自动化 歌词检查版 v0.2.5-preview', 'AVR 翻唱逐首自动化 安全歌词检查版 v0.2.6')
s = s.replace('歌词检查版不保存“已提交”进度，避免误认为歌曲已真正提交。', '安全检查版第一阶段不会点击“确认并创建批次”；第二阶段必须由用户手动确认才会创建批次进入歌词页。')

new_submit = '''    def submit_one(self, task: SongTask) -> str:\n        \"\"\"安全检查第一阶段：只运行到第4步，绝不创建批次。\"\"\"\n        self.status(f"第 {task.row} 行：{task.display_name}")\n        self.log("=" * 66)\n        self.log(f"开始单曲：{task.display_name}")\n        self.log(f"音频：{task.audio_path}")\n\n        self.ensure_cover_step_one()\n        self.fill_step_one_song(task.avr_input_name)\n        self.click_primary_next("第1步")\n\n        self.select_use_original_lyrics()\n        self.click_primary_next("第2步")\n\n        self.upload_audio(task.audio_path)\n        self.click_primary_next("第3步", timeout=max(20, self.audio_wait))\n\n        self.wait_final_review()\n        self.status(f"已停在第4步，尚未创建批次：{task.display_name}")\n        self.log("【安全暂停】已到第4步，但没有点击‘确认并创建批次’。")\n        return "PREVIEW_STEP4_READY"\n\n    def continue_to_lyrics_preview(self, task: SongTask) -> dict:\n        \"\"\"用户明确确认后才创建批次；只填歌词，不点最终确认。\"\"\"\n        self.wait_final_review()\n        self.click_final_create()\n        self.wait_review_lyrics()\n        result = self.fill_review_lyrics(task.lyrics)\n        self.status(f"歌词已写入，等待人工检查：{task.display_name}")\n        self.log(\n            f"【歌词检查已暂停】{task.display_name} | "\n            f"{result['len']}字符/{result['hash']}。未点击‘确认正确，继续’。"\n        )\n        return result\n'''

s, n = re.subn(
    r'    def submit_one\(self, task: SongTask\) -> str:\n.*?\n\n# =========================================================\n# GUI',
    new_submit + '\n\n# =========================================================\n# GUI',
    s,
    flags=re.S,
)
if n != 1:
    raise SystemExit(f'submit_one patch failed: {n}')

s = s.replace(
    '        self.controller: Optional[AvrCoverController] = None\n        cfg = read_ini()',
    '        self.controller: Optional[AvrCoverController] = None\n        self.preview_task: Optional[SongTask] = None\n        cfg = read_ini()',
)

old_buttons = '''        self.btn_start = ttk.Button(btns, text="开始逐首提交", command=self.start)\n        self.btn_start.pack(side="left")\n        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop, state="disabled")\n        self.btn_stop.pack(side="left", padx=8)\n'''
new_buttons = '''        self.btn_start = ttk.Button(btns, text="运行到第4步（不创建批次）", command=self.start)\n        self.btn_start.pack(side="left")\n        self.btn_lyrics = ttk.Button(btns, text="继续到歌词检查", command=self.continue_to_lyrics, state="disabled")\n        self.btn_lyrics.pack(side="left", padx=8)\n        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop, state="disabled")\n        self.btn_stop.pack(side="left", padx=8)\n'''
if old_buttons not in s:
    raise SystemExit('buttons patch failed')
s = s.replace(old_buttons, new_buttons, 1)

start_idx = s.index('    def start(self):')
msg_start = s.index('        msg = (\n', start_idx)
msg_end = s.index('        if not messagebox.askyesno("确认逐首提交", msg):', msg_start)
new_msg = '''        msg = (\n            f"总歌曲：{len(tasks)}\\n"\n            f"本次只检查第一首：{pending[0].display_name}\\n\\n"\n            "第一阶段只运行到 AVR 第4步。\\n"\n            "不会点击‘确认并创建批次’，因此不会由工具创建/提交批次。\\n\\n"\n            "到第4步后，如确实要检查 AVR 歌词框，\\n"\n            "再手动点击工具里的‘继续到歌词检查’。\\n"\n            "注意：只有点击那个按钮后，AVR 才会创建批次并进入歌词确认页。\\n\\n"\n            "是否运行到第4步？"\n        )\n'''
s = s[:msg_start] + new_msg + s[msg_end:]

old_branch = '''                    source = ctl.submit_one(task)\n                    if source == "PREVIEW_LYRICS_READY":\n                        self.log("歌词检查版：未保存已提交进度；AVR 保持停在歌词确认页面。")\n                        self.after(0, lambda: messagebox.showinfo(\n                            "歌词已写入",\n                            "Excel 歌词已写入并通过两次回读校验。\\n\\n"\n                            "程序已停在 AVR 的“确认匹配素材”页面，\\n"\n                            "不会点击“确认正确，继续”。\\n\\n"\n                            "请你现在直接检查 AVR 里的歌词。"\n                        ))\n                        break\n'''
new_branch = '''                    source = ctl.submit_one(task)\n                    if source == "PREVIEW_STEP4_READY":\n                        self.preview_task = task\n                        self.after(0, lambda: self.btn_lyrics.config(state="normal"))\n                        self.log("安全检查版：已停在第4步；没有点击‘确认并创建批次’，没有保存已提交进度。")\n                        self.after(0, lambda: messagebox.showinfo(\n                            "已安全停在第4步",\n                            "目前没有点击‘确认并创建批次’。\\n\\n"\n                            "所以工具尚未创建/提交 AVR 批次。\\n\\n"\n                            "如果要继续检查歌词框，请手动点击\\n"\n                            "‘继续到歌词检查’。\\n\\n"\n                            "注意：那一步会创建 AVR 批次，但仍不会点击‘确认正确，继续’。"\n                        ))\n                        break\n'''
if old_branch not in s:
    raise SystemExit('worker branch patch failed')
s = s.replace(old_branch, new_branch, 1)

s = s.replace(
'''            elif source == "PREVIEW_LYRICS_READY":\n                self.status("歌词检查版已暂停，等待人工核对")\n                self.log("=" * 66)\n                self.log("歌词检查版已暂停：未点击最终确认，未处理下一首。")\n''',
'''            elif source == "PREVIEW_STEP4_READY":\n                self.status("已安全停在第4步，尚未创建批次")\n                self.log("=" * 66)\n                self.log("安全检查版已暂停：没有点击‘确认并创建批次’，未处理下一首。")\n''',
1)

marker = '    def _run_worker(self, tasks: List[SongTask], excel_path: Path, min_d: int, max_d: int):\n'
method = '''    def continue_to_lyrics(self):\n        if self.worker and self.worker.is_alive():\n            return\n        task = self.preview_task\n        if task is None:\n            messagebox.showwarning("还不能继续", "请先运行到第4步。")\n            return\n\n        msg = (\n            f"当前歌曲：{task.display_name}\\n\\n"\n            "为了进入 AVR 的‘确认匹配素材/歌词’页面，下一步必须点击\\n"\n            "‘确认并创建批次’。这会在 AVR 中创建批次。\\n\\n"\n            "随后只会把 Excel 歌词写入歌词框并停住，\\n"\n            "绝不会点击‘确认正确，继续’。\\n\\n"\n            "确定继续吗？"\n        )\n        if not messagebox.askyesno("确认创建批次并检查歌词", msg):\n            return\n\n        self.stop_event.clear()\n        self.btn_start.config(state="disabled")\n        self.btn_lyrics.config(state="disabled")\n        self.btn_stop.config(state="normal")\n\n        def work():\n            ctl = None\n            try:\n                ctl = self._make_controller()\n                self.controller = ctl\n                ctl.connect()\n                result = ctl.continue_to_lyrics_preview(task)\n                self.status("歌词检查版已暂停，等待人工核对")\n                self.log("=" * 66)\n                self.log("歌词已写入并稳定校验；未点击‘确认正确，继续’，未处理下一首。")\n                self.after(0, lambda: messagebox.showinfo(\n                    "歌词已写入",\n                    f"Excel 歌词已经写入 AVR。\\n\\n字符数：{result['len']}\\n指纹：{result['hash']}\\n\\n"\n                    "现在请直接查看 AVR 页面。\\n工具不会点击‘确认正确，继续’。"\n                ))\n            except Exception as e:\n                self.status("歌词检查失败")\n                self.log("歌词检查失败：" + str(e))\n                self.log(traceback.format_exc())\n                try:\n                    if ctl:\n                        ctl.save_debug(task.display_name + "_lyrics")\n                except Exception:\n                    pass\n                self.after(0, lambda: messagebox.showerror("歌词检查失败", str(e)))\n            finally:\n                if ctl:\n                    ctl.disconnect()\n                self.controller = None\n                self.messages.put(("finished", ""))\n\n        self.worker = threading.Thread(target=work, daemon=True)\n        self.worker.start()\n\n'''
if marker not in s:
    raise SystemExit('run worker marker missing')
s = s.replace(marker, method + marker, 1)

p.write_text(s, encoding='utf-8')
print('safe preview patch applied')
