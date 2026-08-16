from pathlib import Path
import re

p = Path('avr_cover_single_demo.py')
s = p.read_text(encoding='utf-8')
s = s.replace('AVR 翻唱逐首自动化 Demo v0.2.4', 'AVR 翻唱逐首自动化 歌词检查版 v0.2.5-preview')
s = s.replace('- 创建批次后，在“确认匹配素材”页用 Excel 歌词覆盖原曲歌词并确认。', '- 创建批次后，在“确认匹配素材”页用 Excel 歌词覆盖原曲歌词，然后停住供人工检查；绝不点击最终确认。')
s = s.replace('- 保存断点进度，避免重复提交。', '- 歌词检查版不保存“已提交”进度，避免误认为歌曲已真正提交。')

new_fill = r'''    def fill_review_lyrics(self, lyrics: str):
        """歌词检查版：真实输入 Excel 歌词，两次回读一致后停住。"""
        if not lyrics:
            raise RuntimeError("Excel 歌词为空，禁止继续。")
        expected = lyrics
        expected_hash = hashlib.sha256(expected.encode("utf-8")).hexdigest()[:12]
        locate_js = r"""
(() => {
 const visible=el=>!!(el&&(el.offsetWidth||el.offsetHeight||el.getClientRects().length));
 let el=document.querySelector('#review-lyrics');
 if(el&&visible(el)) { el.focus(); el.select(); return {ok:true,value:String(el.value||'')}; }
 const areas=Array.from(document.querySelectorAll('textarea')).filter(visible);
 const candidates=areas.filter(x=>{
   const p=x.closest('section,div,form')||x.parentElement;
   const t=(p&&p.innerText)||'';
   return /原曲歌词/.test(t) || /确认匹配素材/.test(t);
 });
 if(candidates.length!==1) return {ok:false,count:candidates.length};
 el=candidates[0]; el.focus(); el.select(); return {ok:true,value:String(el.value||'')};
})()
"""
        before = self.eval(locate_js, timeout=15)
        if not before or not before.get("ok"):
            raise RuntimeError(f"找不到唯一的原曲歌词文本框：{before}")
        before_value = str(before.get("value") or "")
        before_hash = hashlib.sha256(before_value.encode("utf-8")).hexdigest()[:12]
        self.log(f"歌词检查：Excel={len(expected)}字符/{expected_hash}；AVR当前={len(before_value)}字符/{before_hash}")
        if not self.cdp:
            raise RuntimeError("CDP 未连接，无法使用真实输入事件写歌词。")
        self.cdp.call("Input.insertText", {"text": expected}, timeout=30)
        self.eval(r"""
(() => {
 const el=document.querySelector('#review-lyrics') || document.activeElement;
 if(!el || el.tagName!=='TEXTAREA') return false;
 el.dispatchEvent(new Event('change',{bubbles:true})); el.blur(); return true;
})()
""", timeout=10)
        def read_current():
            return str(self.eval(r"""
(() => {
 const visible=el=>!!(el&&(el.offsetWidth||el.offsetHeight||el.getClientRects().length));
 let el=document.querySelector('#review-lyrics');
 if(el&&visible(el)) return String(el.value||'');
 const areas=Array.from(document.querySelectorAll('textarea')).filter(visible);
 const candidates=areas.filter(x=>{
   const p=x.closest('section,div,form')||x.parentElement;
   const t=(p&&p.innerText)||'';
   return /原曲歌词/.test(t) || /确认匹配素材/.test(t);
 });
 return candidates.length===1 ? String(candidates[0].value||'') : '';
})()
""", timeout=10) or "")
        self.sleep(1.2)
        check1 = read_current(); h1 = hashlib.sha256(check1.encode("utf-8")).hexdigest()[:12]
        self.log(f"歌词检查：第一次回读={len(check1)}字符/{h1} {'✓' if check1 == expected else '✗'}")
        if check1 != expected:
            raise RuntimeError(f"第一次回读不一致，已停止。Excel={len(expected)}/{expected_hash} AVR={len(check1)}/{h1}")
        self.sleep(2.0)
        check2 = read_current(); h2 = hashlib.sha256(check2.encode("utf-8")).hexdigest()[:12]
        self.log(f"歌词检查：第二次稳定回读={len(check2)}字符/{h2} {'✓' if check2 == expected else '✗'}")
        if check2 != expected:
            raise RuntimeError(f"AVR 又覆盖了歌词，已停止。Excel={len(expected)}/{expected_hash} AVR={len(check2)}/{h2}")
        self.log("歌词检查：Excel 歌词已稳定写入 AVR。现在停在确认匹配素材页面，请人工核对。")
        return {"len": len(check2), "hash": h2}
'''
s, n = re.subn(r'    def fill_review_lyrics\(self, lyrics: str\):.*?(?=\n    def snapshot_job_lists)', new_fill, s, flags=re.S)
assert n == 1, n

old_submit = '''        # 5. 创建后等待“确认匹配素材”，覆盖 Excel 歌词
        self.wait_review_lyrics()
        self.fill_review_lyrics(task.lyrics)
        # 批次在第4步后可能已经出现在任务列表；这里重新取一次快照，
        # 之后只认“确认歌词以后”的状态变化，避免过早进入下一首。
        before_confirm_jobs = self.snapshot_job_lists()
        source = self.confirm_material_and_wait_submit(task.title, before_confirm_jobs)
        self.log(f"提交确认：{source}")
        return source
'''
new_submit = '''        # 5. 创建后等待“确认匹配素材”，覆盖 Excel 歌词
        self.wait_review_lyrics()
        result = self.fill_review_lyrics(task.lyrics)
        self.status(f"歌词已写入，等待人工检查：{task.display_name}")
        self.log(f"【歌词检查版已暂停】{task.display_name} | {result['len']}字符/{result['hash']}。不会继续提交。")
        return "PREVIEW_LYRICS_READY"
'''
assert old_submit in s
s = s.replace(old_submit, new_submit)

old_worker = '''                    source = ctl.submit_one(task)
                    progress[key] = {
                        "row": task.row,
                        "title": task.title,
                        "author": task.author,
                        "audio": str(task.audio_path),
                        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "confirm_source": source,
                    }
                    save_progress(progress)
                    self.log(f"✓ 已保存进度：{task.display_name}")
'''
new_worker = '''                    source = ctl.submit_one(task)
                    if source == "PREVIEW_LYRICS_READY":
                        self.log("歌词检查版：未保存已提交进度；AVR 保持停在歌词确认页面。")
                        self.after(0, lambda: messagebox.showinfo("歌词已写入", "Excel 歌词已写入并通过两次回读校验。\\n\\n程序已停在 AVR 的确认匹配素材页面，不会点击最终确认。\\n请直接检查 AVR 里的歌词。"))
                        break
                    progress[key] = {
                        "row": task.row,
                        "title": task.title,
                        "author": task.author,
                        "audio": str(task.audio_path),
                        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "confirm_source": source,
                    }
                    save_progress(progress)
                    self.log(f"✓ 已保存进度：{task.display_name}")
'''
assert old_worker in s
s = s.replace(old_worker, new_worker)

s = s.replace('''            "执行方式：严格一首一首。\\n"
            "每首都会真实点击 AVR 的创建/确认按钮，可能消耗 Suno 生成次数。\\n\\n"
            "是否开始？"''', '''            "这是歌词检查版，只处理第一首待处理歌曲。\\n"
            "程序会走到确认匹配素材，写入 Excel 歌词后立即停住。\\n"
            "绝不会点击最终确认，也不会处理下一首。\\n\\n"
            "是否开始检查？"''')

s = s.replace('''            if self.stop_event.is_set():
                self.status("已停止")
                self.log("用户已停止。")
            else:
                self.status("全部待处理歌曲已逐首提交完成")
                self.log("=" * 66)
                self.log("全部待处理歌曲已逐首提交完成。")
''', '''            if self.stop_event.is_set():
                self.status("已停止")
                self.log("用户已停止。")
            elif source == "PREVIEW_LYRICS_READY":
                self.status("歌词检查版已暂停，等待人工核对")
                self.log("=" * 66)
                self.log("歌词检查版已暂停：未点击最终确认，未处理下一首。")
            else:
                self.status("全部待处理歌曲已逐首提交完成")
                self.log("=" * 66)
                self.log("全部待处理歌曲已逐首提交完成。")
''')
p.write_text(s, encoding='utf-8')
print('patched', len(s))
