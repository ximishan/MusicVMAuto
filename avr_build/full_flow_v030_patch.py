from pathlib import Path
import re

p = Path('avr_cover_single_demo.py')
s = p.read_text(encoding='utf-8')

# 正式版名称
for old_name in [
    'AVR 翻唱逐首自动化 音频20秒等待版 v0.2.9',
    'AVR 翻唱逐首自动化 音频严格确认版 v0.2.8',
    'AVR 翻唱逐首自动化 歌词等待检查版 v0.2.7',
    'AVR 翻唱逐首自动化 歌词检查版 v0.2.5-preview',
]:
    s = s.replace(old_name, 'AVR 翻唱逐首自动化 完整版 v0.3.0')

# 第2步：使用原词后固定等待15秒，再进入第3步。
old_step2 = '''        # 2. 只改“使用原词”\n        self.select_use_original_lyrics()\n        self.click_primary_next("第2步")\n'''
new_step2 = '''        # 2. 只改“使用原词”；固定等待15秒后再进入第3步。\n        self.select_use_original_lyrics()\n        self.log("第2步：已选择‘使用原词’，固定等待 15 秒后再继续。")\n        for remain in (15, 10, 5):\n            self.log(f"第2步：距离继续还有 {remain} 秒。")\n            self.sleep(5)\n        self.log("第2步：15 秒等待结束，现在点击‘下一步’。")\n        self.click_primary_next("第2步")\n'''
if old_step2 not in s:
    raise SystemExit('v0.3.0 patch failed: step2 marker not found')
s = s.replace(old_step2, new_step2, 1)

# 歌词检查版原本写入并停住；正式版改为写入校验成功后点击确认，
# 并等待 AVR 明确接受当前歌曲。兼容多个测试版的日志文案差异。
preview_tail = re.compile(
    r'''        self\.status\(f"歌词已写入，等待人工检查：\{task\.display_name\}"\)\n'''
    r'''        self\.log\(.*?\n'''
    r'''        return "PREVIEW_LYRICS_READY"''',
    re.S,
)
full_tail = '''        # 6. Excel 歌词已经通过两次稳定回读，才允许提交当前任务。\n        self.log(\n            f"歌词确认：Excel 歌词已稳定写入 AVR：{result['len']}字符/{result['hash']}。"\n        )\n        before_confirm_jobs = self.snapshot_job_lists()\n        source = self.confirm_material_and_wait_submit(task.title, before_confirm_jobs)\n        self.log(f"当前歌曲提交成功：{source}")\n        return source'''
s, n = preview_tail.subn(full_tail, s, count=1)
if n != 1:
    raise SystemExit(f'v0.3.0 patch failed: lyrics preview tail marker count={n}')

# 恢复正式按钮名称。
s = s.replace('text="测试第一首到歌词"', 'text="开始逐首提交"')

# 恢复开始前确认文案：不再声称只处理第一首。
new_msg = '''            "执行方式：严格一首一首。\\n"\n            "第2步选择‘使用原词’后固定等待15秒；本地音频确认后固定等待20秒。\\n"\n            "第4步创建批次后，会锁定当前歌曲等待歌词弹窗。\\n"\n            "Excel 歌词写入并通过两次校验后，自动点击‘确认正确，继续’。\\n"\n            "当前歌曲确认进入后续流程后固定等待5秒，再开始下一首。\\n\\n"\n            "任一步失败都会立即停止，不会跳到下一首。\\n\\n"\n            "是否开始？"'''

old_msgs = [
'''            "这是歌词等待检查版，只处理第一首待处理歌曲。\\n"\n            "程序会自动点击第4步‘确认并创建批次’，然后锁定当前歌曲。\\n"\n            "接着等待歌词弹窗（最长180秒），把 Excel 歌词写进去并校验后停住。\\n"\n            "绝不会点击‘确认正确，继续’，也绝不会处理第二首。\\n\\n"\n            "是否开始测试？"''',
'''            "这是歌词检查版，只处理第一首待处理歌曲。\\n"\n            "程序会走到“确认匹配素材”，写入 Excel 歌词后立即停住。\\n"\n            "绝不会点击“确认正确，继续”，也不会处理下一首。\\n\\n"\n            "是否开始检查？"''',
]
msg_replaced = False
for old_msg in old_msgs:
    if old_msg in s:
        s = s.replace(old_msg, new_msg, 1)
        msg_replaced = True
        break
if not msg_replaced:
    raise SystemExit('v0.3.0 patch failed: start message marker not found')

# 两首之间改为固定5秒，不再使用随机 min/max。
old_delay = '''                # 当前首确认成功以后，才允许下一首\n                if idx < len(pending) - 1:\n                    delay = random.randint(min_d, max_d) if max_d >= min_d else min_d\n                    if delay > 0:\n                        self.status(f"{task.display_name} 已提交；{delay} 秒后下一首")\n                        self.log(f"当前首已确认提交，等待 {delay} 秒后处理下一首。")\n                        ctl.sleep(delay)\n'''
new_delay = '''                # 当前首确认成功以后，固定等待5秒，才允许下一首。\n                if idx < len(pending) - 1:\n                    self.status(f"{task.display_name} 已提交；5 秒后下一首")\n                    self.log("当前首歌词已确认、任务已提交；固定等待 5 秒后处理下一首。")\n                    ctl.sleep(5)\n'''
if old_delay not in s:
    raise SystemExit('v0.3.0 patch failed: inter-song delay marker not found')
s = s.replace(old_delay, new_delay, 1)

# UI 上明确说明正式流程固定5秒，避免旧 min/max 输入框造成误解。
s = s.replace('ttk.Label(delay_frame, text="两首之间等待").pack(side="left")',
              'ttk.Label(delay_frame, text="两首之间等待（正式流程固定5秒）").pack(side="left")', 1)

# 清理 preview worker 分支，避免未来误判。
preview_worker = re.compile(
    r'''                    if source == "PREVIEW_LYRICS_READY":\n.*?                        break\n''',
    re.S,
)
s, _ = preview_worker.subn('', s, count=1)

preview_finish = re.compile(
    r'''            elif source == "PREVIEW_LYRICS_READY":\n.*?            else:\n''',
    re.S,
)
s, _ = preview_finish.subn('            else:\n', s, count=1)

# 顶部说明同步成正式逻辑。
s = s.replace(
    '严格一首一首：当前歌曲确认提交成功后，才开始下一首；不修改 AVR 原有业务逻辑。',
    '严格一首一首：歌词校验并提交成功后固定等待5秒，才开始下一首；不修改 AVR 原有业务逻辑。',
    1,
)

# 最终自检：正式版绝不能再含有 preview 返回。
if 'return "PREVIEW_LYRICS_READY"' in s:
    raise SystemExit('v0.3.0 patch failed: preview return still exists')
if 'AVR 翻唱逐首自动化 完整版 v0.3.0' not in s:
    raise SystemExit('v0.3.0 patch failed: app name not updated')

p.write_text(s, encoding='utf-8')
print('full flow v0.3.0 patch applied')
