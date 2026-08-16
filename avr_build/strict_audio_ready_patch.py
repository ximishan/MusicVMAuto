from pathlib import Path
import re

p = Path('avr_cover_single_demo.py')
s = p.read_text(encoding='utf-8')

s = s.replace('AVR 翻唱逐首自动化 歌词等待检查版 v0.2.7', 'AVR 翻唱逐首自动化 音频严格确认版 v0.2.8')

pattern = re.compile(r'''        self\.log\(f"第3步：已选择本地音频 \{audio_path\.name\}"\)\n\n        # 等待 AVR 自己完成音频解析/匹配：主按钮可用 \+ 页面不处于明显处理中。\n.*?        raise RuntimeError\(f"等待 AVR 处理本地音频超时。页面状态：\{last_text\[:900\]\}"\)''', re.S)

replacement = r'''        self.log(f"第3步：文件选择动作已完成：{audio_path.name}")
        self.log("第3步：开始严格等待 AVR 明确确认本地 WAV 已加载；仅‘下一步可点’不再作为成功条件。")

        # v0.2.8：必须得到“音频真正进入 AVR”的明确证据，才允许进入第4步。
        # 允许的证据：
        #   1) DOM file input 中的 files[0].name 与当前文件一致；
        #   2) 页面明确显示当前文件名/文件名主干；
        #   3) 页面按钮/文案由“选择”变为“更换/重新选择/已选择/已加载/就绪”等明确完成态；
        #   4) 页面中出现可播放的 audio 元素且已拿到 metadata。
        # 绝不再使用“下一步按钮稳定可用 1.2 秒”这种兜底。
        basename = audio_path.name
        stem = audio_path.stem
        basename_json = json.dumps(basename, ensure_ascii=False)
        stem_json = json.dumps(stem, ensure_ascii=False)
        deadline = time.time() + max(int(self.audio_wait), 90)
        last_text = ""
        last_state = {}
        ready_since = None
        last_log_at = 0.0

        while time.time() < deadline:
            self.check_stop()
            state = self.eval(f"""
(() => {{
 const root=document.querySelector('.cover-panel')||document.body;
 const visible=el=>!!(el&&(el.offsetWidth||el.offsetHeight||el.getClientRects().length));
 const text=(root.innerText||'').replace(/\\s+/g,' ');
 const buttons=Array.from(root.querySelectorAll('button,[role="button"],label')).filter(visible)
   .map(x=>(x.textContent||'').replace(/\\s+/g,' ').trim()).filter(Boolean);
 const inputs=Array.from(document.querySelectorAll('input[type="file"]')).map(x=>({{
   id:x.id||'', name:x.name||'', files:Array.from(x.files||[]).map(f=>f.name||'')
 }}));
 const audios=Array.from(document.querySelectorAll('audio')).map(a=>({{
   src:a.currentSrc||a.src||'', readyState:Number(a.readyState||0), duration:Number.isFinite(a.duration)?a.duration:0,
   error:!!a.error
 }}));
 const base={basename_json};
 const stem={stem_json};
 const fileInputMatch=inputs.some(x=>x.files.some(n=>n===base || n.includes(stem)));
 const filenameShown=text.includes(base) || (stem.length>=6 && text.includes(stem));
 const doneWords=['已选择','已加载','加载完成','上传成功','音频已就绪','参考音频已就绪','参考音频已选择','使用本地参考音频'];
 const doneWord=doneWords.find(k=>text.includes(k))||'';
 const changedButton=buttons.find(t=>/更换.*音频|重新选择.*音频|移除.*音频|清除.*音频/.test(t))||'';
 const playableAudio=audios.some(a=>!a.error && a.readyState>=1 && (a.duration>0 || !!a.src));
 const next=Array.from(root.querySelectorAll('button')).filter(visible)
   .find(x=>/下一步|继续/.test((x.textContent||'').trim()));
 const busyWords=['正在上传','上传中','正在处理','解析中','匹配中','音频处理中','读取音频','正在读取','加载中'];
 const busy=busyWords.find(k=>text.includes(k))||'';
 return {{
   text:text.slice(0,6000), buttons:buttons.slice(0,60), inputs, audios,
   fileInputMatch, filenameShown, doneWord, changedButton, playableAudio,
   nextEnabled:!!(next&&!next.disabled), busy
 }};
}})()
""", timeout=10) or {{}}

            last_state = state
            last_text = str(state.get("text") or "")
            signals = []
            if state.get("fileInputMatch"):
                signals.append("file-input文件名匹配")
            if state.get("filenameShown"):
                signals.append("页面显示当前文件名")
            if state.get("changedButton"):
                signals.append(f"按钮状态={state.get('changedButton')}")
            if state.get("doneWord"):
                signals.append(f"完成文案={state.get('doneWord')}")
            if state.get("playableAudio"):
                signals.append("audio元素已加载metadata")

            # 必须有明确音频信号 + 下一步可用 + 当前不处于上传/解析忙碌状态。
            ready = bool(signals) and bool(state.get("nextEnabled")) and not state.get("busy")
            now = time.time()
            if ready:
                if ready_since is None:
                    ready_since = now
                    self.log("第3步：检测到音频就绪候选信号：" + "；".join(signals) + "。继续稳定校验 2 秒。")
                elif now - ready_since >= 2.0:
                    self.log("第3步：本地音频已严格确认加载完成：" + "；".join(signals))
                    self.log("第3步：现在才允许进入第4步。")
                    return
            else:
                ready_since = None

            if now - last_log_at >= 5.0:
                last_log_at = now
                detail = []
                if state.get("busy"):
                    detail.append(f"忙碌={state.get('busy')}")
                detail.append(f"下一步={'可用' if state.get('nextEnabled') else '不可用'}")
                detail.append(f"明确信号={signals if signals else '无'}")
                self.log("第3步等待音频加载：" + " | ".join(detail))
            time.sleep(0.5)

        self._log_step_three_state()
        raise RuntimeError(
            "第3步等待本地音频真正加载超时。为避免创建一个缺少正确参考音频的批次，程序已停止，"
            "不会点击下一步/不会进入第4步。\n"
            f"最后状态：nextEnabled={last_state.get('nextEnabled')} "
            f"busy={last_state.get('busy')!r} "
            f"fileInputMatch={last_state.get('fileInputMatch')} "
            f"filenameShown={last_state.get('filenameShown')} "
            f"doneWord={last_state.get('doneWord')!r} "
            f"changedButton={last_state.get('changedButton')!r} "
            f"playableAudio={last_state.get('playableAudio')}\n"
            f"页面状态：{last_text[:900]}"
        )'''

s, n = pattern.subn(lambda _m: replacement, s, count=1)
if n != 1:
    raise SystemExit(f'audio strict patch failed: {n}')

p.write_text(s, encoding='utf-8')
print('strict audio ready patch applied')
