# MusicVMAuto

用于 VMware Workstation 多虚拟机中的音乐客户端自动化。当前先做 **IP 验证 + QQ 音乐**，后续再接酷我音乐和 A-1 ~ A-50 批量切换。

## 当前架构

程序只运行在 VMware 外面的宿主机。虚拟机里不安装 Python、不复制源码、不额外驻留程序。

v0.5 已经废弃固定坐标和人工模板录制，改成 **本地中文 OCR 识别**：每一步先截图读取当前虚拟机画面中的文字，再决定是否点击。

## v0.5.1：无模板 IP + QQ 音乐

入口：

```bat
python host_controller.py
```

或运行 GitHub Actions / `build_host.bat` 生成的：

```text
MusicVMAutoNoTemplate.exe
```

### 不再需要录制

下面这些操作已经全部删除：

- 记录模板
- F8 取点
- Esc 取消录制
- 保存按钮坐标
- `templates\` 目录

正常使用只需要保证 VMware 当前虚拟机画面可见。

OCR 使用 RapidOCR + ONNX Runtime，本地运行，不需要把截图上传到云端。

## IP 验证逻辑

```text
OCR 找“线路设置”
→ 点击
→ OCR 找“验证所有IP”
→ 点击
→ 等待并 OCR 检测 √ / ✓ / ✔ / ☑
→ 没检测到则只重试“验证所有IP”
→ 最多 3 次
→ 仍失败则保存截图并停止当前步骤
```

安全约束：只有 OCR 明确识别到 `线路设置` 和 `验证所有IP` 才允许点击。找不到时不会用固定坐标兜底，也不会点击重新加载线路、删除IP、验证勾选IP等其他按钮。

## QQ 音乐逻辑

v0.5.1 已经 **彻底删除** 下面这条启动方式：

```text
Ctrl + G
→ Win + R
→ 输入 QQMusic.exe 路径
```

原因是 VMware 环境中系统级组合键可能被虚拟机或宿主机解释成其他操作。

现在 QQ 音乐只使用：

```text
OCR 读取当前虚拟机画面
→ 找到桌面“QQ音乐”文字
→ 双击桌面图标文字位置
→ 等待 QQ音乐主界面出现
```

如果 OCR 找不到桌面 `QQ音乐`，程序会保存截图并停止当前 QQ 步骤，**不会发送任何快捷键，也不会猜坐标点击**。

QQ 打开后继续：

```text
OCR 等待 QQ 音乐界面加载
→ 遇到验证码 / 重新登录 / 安全验证等界面则停止，不乱点
→ 可安全识别的“稍后再说 / 暂不升级 / 我知道了”等提示可自动关闭
→ OCR 找“创建的歌单 / 自建歌单 / 我的歌单”
→ 根据日期选择第1或第2个歌单
→ OCR 找“播放全部”
→ 点击播放
```

当前默认轮换基准：

```text
2026-08-11 = 歌单1
2026-08-12 = 歌单2
之后每天 1 / 2 交替
```

## 失败处理

任何关键文字识别失败，都不会猜坐标继续点击。当前 VMware 画面会保存到：

```text
failures\
```

第一次测试建议先选中 A-1，然后依次测试：

```text
检测 VMware + OCR
1. IP验证
2. QQ音乐
完整：IP → QQ
```

## 打包 EXE

本地：

```bat
build_host.bat
```

输出：

```text
dist\MusicVMAutoNoTemplate.exe
```

GitHub Actions 同时会：

- 生成 Artifact：`MusicVMAutoNoTemplate-Windows`
- 在 GitHub Releases 发布可直接下载的 `MusicVMAutoNoTemplate.exe`

## 下一阶段

先把 A-1 的 `IP → QQ音乐` OCR 流程跑稳定，再继续：

- 加强 IP `√` 的视觉确认兜底
- 加强 QQ 播放状态确认
- VMware A-1 ~ A-50 自动切换
- 单台失败不阻塞下一台
- Agent 只处理 OCR 无法理解的未知异常界面
- 每天 00:00 自动执行
- 酷我音乐工作流
