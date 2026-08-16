from pathlib import Path

p = Path('avr_cover_single_demo.py')
s = p.read_text(encoding='utf-8')

s = s.replace('AVR 翻唱逐首自动化 音频严格确认版 v0.2.8', 'AVR 翻唱逐首自动化 音频20秒等待版 v0.2.9')

old = '''        self.upload_audio(task.audio_path)\n        self.click_primary_next("第3步", timeout=max(20, self.audio_wait))\n'''
new = '''        self.upload_audio(task.audio_path)\n        # v0.2.9：即使 AVR 已经检测到音频就绪，也固定再等待 20 秒。\n        # 这是硬等待，不会因为“下一步可用”或其他 DOM 信号提前结束。\n        self.log("第3步：本地音频已确认。现在固定等待 20 秒，让 AVR 完成内部音频处理。")\n        for remain in (20, 15, 10, 5):\n            self.log(f"第3步：距离继续还有 {remain} 秒。")\n            self.sleep(5)\n        self.log("第3步：固定 20 秒等待结束，现在才点击‘下一步’。")\n        self.click_primary_next("第3步", timeout=max(20, self.audio_wait))\n'''

if old not in s:
    raise SystemExit('hard 20s wait patch failed: submit_one marker not found')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('hard 20s wait patch applied')
