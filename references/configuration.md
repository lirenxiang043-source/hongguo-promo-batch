# 机器配置与路径适配

脚本顶部含机器特定绝对路径，换机/换工作区时按本文适配后再跑。

## 目录布局（默认值，脚本已用相对路径推导大部分）

```
<WORK>/                          # 工作区根目录，通常是 C:/Users/<u>/WorkBuddy/<session>
├── promo/                       # 剪辑/渲染脚本 + batch_out/
│   ├── batch_l13.py, batch_b1.py
│   ├── render_v2.py, auto_subtitle.py, rebuild_ass.py, publish_range.py, gen_image.py
│   └── batch_out/{raw,final_v2}/
├── promo_platform/
│   └── gen_one.py               # 生视频提交脚本
├── rabbit_iter/{raw,16x9,thumbs}/
├── 画面迭代库*.json / .html
├── 文案库*.json / .html
└── douyin_awemes*.json / filtered_*.json / links_*.json
```

多数脚本用 `BASE = Path(__file__).resolve().parent` 推导，只要保持上述相对结构即可。

## 必须按本机改的绝对路径

| 脚本 | 常量 | 默认/说明 |
|---|---|---|
| `gen_one.py` | `TASKS` | `C:\Users\Administrator\AppData\Roaming\doubao-video-workspace\canvas-bridge-tasks.json` → 改成当前用户 AppData 路径 |
| `gen_one.py` | `GATEWAY` / `CONFIRM_URL` / `BRIDGE_ACCOUNTS` | `127.0.0.1:8788` / `:3219`，一般不变 |
| `render_v2.py` | `RECDIR` | `D:\l\素材\录屏\多功能` → 本机录屏素材目录 |
| `render_v2.py` | `_LOGO_ORIG` | `D:\l\素材\微信图片_....png`，不存在时回退到工作区 `hongguo_logo.png` |
| `publish_range.py` | `BASE` | 发布助手 `http://127.0.0.1:5199` |

## 环境变量覆盖（无需改代码）

- `HGP_WORK`：工作区根目录（render/gen_image/publish 用）
- `HGP_GATEWAY`：网关地址，默认 `http://127.0.0.1:8788`
- `HGP_IMG_MODEL`：生图模型，默认 `Seedream 5.5`
- `HGP_RES_FILE`：资源段录屏文件名，默认 `资源.mp4`
- `HGP_TASK_ID` / `HGP_TITLE` / `HGP_TOPICS`：发布参数
- `HGP_ACCOUNTS`：批量脚本指定账号池，如 `2,4`；不设则 `0`=自动 1→7
- `HGP_VIDEO_DIR`：发布脚本取片目录

## 素材清单（render_v2 的录屏映射）

`RECDIR` 下需有这些竖屏录屏 mp4（文件名即关键词匹配目标）：
- `自动续播全剧.mp4` — 连播/续播句
- `电影.mp4` / `电视剧.mp4` — 影视句
- `小说.mp4` — 小说句（**注意核对素材内容是否真是小说 tab，本项目曾出现文件名对但开头停在电影 tab 的情况**）
- `资源.mp4` — "资源非常丰富"句

另有 `hongguo_logo.png`、`music_bed.m4a`、手机框/圆角遮罩 PNG（现成 pipeline skill 的 assets/ 可复用）。

## 前置服务

- 豆包多开客户端（内含网关 8788 + 桥接 3219），已打账号池/固定会话/额度和 panelfix 补丁
- 发布助手 Node 应用 5199
- Python 3 + requests；ffmpeg/ffprobe 在 PATH
- 宿主提供 `AudioTranscribe` 工具（字幕与文案库口播都靠它）
- 抓取用 `patchright`（反检测），`headless=False`，登录态 `douyin_state.json`
