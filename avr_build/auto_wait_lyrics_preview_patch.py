from pathlib import Path

p = Path('avr_cover_single_demo.py')
s = p.read_text(encoding='utf-8')

s = s.replace('AVR 翻唱逐首自动化 歌词检查版 v0.2.5-preview', 'AVR 翻唱逐首自动化 歌词等待检查版 v0.2.7')
s = s.replace('ttk.Button(btns, text="开始逐首提交", command=self.start)', 'ttk.Button(btns, text="测试第一首到歌词", command=self.start)')

old = '''        # 4. 创建单曲批次
        self.wait_final_review()
        self.click_final_create()

        # 5. 创建后等待“确认匹配素材”，覆盖 Excel 歌词
        self.wait_review_lyrics()
        result = self.fill_review_lyrics(task.lyrics)
'''
new = '''        # 4. 创建单曲批次
        self.wait_final_review()
        self.log("第4步：准备点击‘确认并创建批次’。点击后只等待当前歌曲歌词弹窗，不会处理下一首。")
        self.click_final_create()
        self.log("第4步：批次已创建。当前歌曲已锁定，开始等待‘确认匹配素材/原曲歌词’弹窗。")

        # 5. 创建后等待“确认匹配素材”，覆盖 Excel 歌词
        # 测试版至少等待 180 秒；没出现就停在当前首，绝不进入下一首。
        old_review_wait = self.review_wait
        try:
            self.review_wait = max(int(self.review_wait), 180)
            self.log(f"歌词等待：最长 {self.review_wait} 秒；期间不会开始下一首。")
            self.wait_review_lyrics()
        finally:
            self.review_wait = old_review_wait
        self.log("歌词等待：已检测到‘确认匹配素材/原曲歌词’文本框，开始写入 Excel 歌词。")
        result = self.fill_review_lyrics(task.lyrics)
'''
if old not in s:
    raise SystemExit('submit flow marker not found')
s = s.replace(old, new, 1)

s = s.replace(
'''            "这是歌词检查版，只处理第一首待处理歌曲。\\n"
            "程序会走到确认匹配素材，写入 Excel 歌词后立即停住。\\n"
            "绝不会点击最终确认，也不会处理下一首。\\n\\n"
            "是否开始检查？"''',
'''            "这是歌词等待检查版，只处理第一首待处理歌曲。\\n"
            "程序会自动点击第4步‘确认并创建批次’，然后锁定当前歌曲。\\n"
            "接着等待歌词弹窗（最长180秒），把 Excel 歌词写进去并校验后停住。\\n"
            "绝不会点击‘确认正确，继续’，也绝不会处理第二首。\\n\\n"
            "是否开始测试？"''',
1)

p.write_text(s, encoding='utf-8')
print('auto wait lyrics preview patch applied')
