# VideoNotes

把 B 站视频/合集或本地视频，转成结构化的中文技术教程笔记（Markdown + 整页课件截图）。

详细设计见 [docs/DESIGN.md](docs/DESIGN.md)。

## 开发环境

- Windows 10/11 x64
- Python 3.12（D:\software\python）
- 依赖由 uv 管理：`uv sync --extra gui --extra dev`
- ffmpeg 放在 `runtime/ffmpeg.exe`

## 生成笔记（命令行）

```bat
vnote build "https://space.bilibili.com/317080675/lists/4878258?type=season" --index 0 --out "D:/notes_ai_generate"
vnote build "D:/videos/lecture.mp4" --out "D:/notes_ai_generate" --keep
```

## 启动界面

双击 `run_app.cmd`（无控制台），或 `run_app_debug.cmd`（保留控制台便于看报错）。

首次启动：进入"设置"填写 DeepSeek 与 DashScope 的 API Key。

## 命令行

```bat
vnote app                                   # 启动界面
vnote config list                           # 查看配置
vnote config set deepseek_api_key sk-xxx    # 保存密钥（DPAPI 加密）
vnote bili parse <url>                      # 解析链接类型
vnote bili list <url> --out collection.json # 枚举合集视频
```

## 当前进度

- [x] 项目骨架、配置存储（SQLite + Windows DPAPI）
- [x] B 站链接解析与合集枚举（单视频/合集/收藏夹/分 P）
- [x] 桌面壳：课程库、任务中心、设置页
- [x] ffmpeg / yt-dlp 运行环境，720P 下载 + 音轨提取验证
- [ ] M0：ASR 时间戳、Qwen-VL 判页准确率（需要 API Key）
- [x] M1：转写 → 分节 → 笔记生成（已用合集视频跑通）
- [x] M2：抽帧 → dHash 聚类 → Qwen-VL 判页 → 原分辨率截图 → 插入笔记
- [x] M3：课程库 / 课程详情 / 后台生成队列 / 笔记预览
- [x] M4：课程目录 + index.md、PyInstaller 打包（release/VideoNotes-win64.zip）

## 打包

```bat
pyinstaller --noconfirm --clean --windowed --name VideoNotes --paths src ^
  --add-binary "runtimefmpeg.exe;runtime" ^
  --add-binary "runtimeyt-dlp.exe;runtime" ^
  --exclude-module tkinter --exclude-module matplotlib ^
  --exclude-module pandas --exclude-module numpy app.py
```

产物：`dist/VideoNotes/VideoNotes.exe`（便携版，运行时在 `_internal/runtime/`）。
打包 zip：`release/VideoNotes-win64.zip`。

## 输出结构

```
输出根目录/
  <课程名>/
    index.md
    01-<视频标题>/
      notes.md
      assets/slide-*.png
      transcript.json / sections.json / slides.json / meta.json
```
