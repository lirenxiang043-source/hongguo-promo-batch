# 批量串行脚本与 QC 配方（阶段 C）

## batch 脚本（batch_l13.py / batch_b1.py）

一条一条严格串行：**生视频 → 字幕 → 标黄 → 三段录屏渲染 → 成片**，一条完成再下一条。

```bash
python batch_b1.py --one B1雨巷橘猫       # 单条验证全链路
python batch_b1.py --gen-only             # 只生视频（便于集中监控额度/提交）
python batch_b1.py --render-only          # 只剪辑
HGP_ACCOUNTS=2,4 python batch_b1.py       # 指定账号池，每条按池轮询
python batch_b1.py                        # 全量：先生后剪
```

### JOBS 结构
```python
JOBS = [
    ('B1雨巷橘猫', '一只戴花环趴在雨巷木栏上的橘猫幼崽'),
    ...
]
```
tag 对应参考图 `rabbit_iter/16x9/<tag>.jpg`；subject 只描述主体，场景写在口播/参考图里。

### 关键设计
- **跳过已完成**：raw 存在且 >1MB 跳生视频；成片存在跳剪辑。中断后重跑不重复烧额度。
- **口播字节级一致**：`ORAL` 常量全局唯一，所有条用同一段（本次 101 字 / 15s ≈ 6.7 字/秒，正常）。
- **账号池轮询**：`HGP_ACCOUNTS` 指定的池内逐账号尝试；每条失败换下一个。
  配合 gen_one 的 `single=1`，每个账号每次只提交 1 次。
- **日志**：`batch_out/batch_b1.log`，带时间戳，便于追溯每条的提交/成功/失败。

### 生成耗时参考
一条 15s 图生视频：快则 30s-1min，慢则排队 8-12 分钟。10 条批量预留 30-60 分钟。
后台跑，用长 timeout 轮询，不要反复重启批次。

## 剪辑三步

```bash
python auto_subtitle.py <tag> "<完整口播>" 15.05
python rebuild_ass.py <tag>
HGP_RES_FILE=资源.mp4 python render_v2.py <tag> batch_out/raw/raw_<tag>.mp4
```

- `auto_subtitle.py`：按标点切句，按字数比例分配时间，标出品牌词句
- `rebuild_ass.py`：严格只高亮完整词 `红果短剧`（"红果短期"、裸"短剧"不高亮）+ 顶部 AI 声明行
- `render_v2.py`：录屏段由关键词触发匹配

## 录屏段关键词映射（render_v2.py）

| 文案里出现 | 录屏素材 |
|---|---|
| 自动续播 / 连播 / 接着播 | `自动续播全剧.mp4` |
| 电影 / 电视剧 | `电影.mp4` |
| 小说 | `小说.mp4` |
| 资源非常丰富 / 题材全 / 汇集 | `资源.mp4`（`HGP_RES_FILE` 指定） |

`BREAK_KEYS` 控制段的延伸边界：遇到下一个主题词就停止当前段延伸。
段规划可用 `render_v2.plan(tag)` 打印核对（哪句用哪个录屏、时间区间）。

## 小说段错显电影列表的排查（本次重点）

现象：成片"小说短视频更是不在话下"那句，手机里显示电影列表。

排查顺序：
1. 看 `subs_<tag>.json` 确认该句时间区间
2. 用 `render_v2.plan(tag)` 确认规划里该句指向 `小说.mp4`
3. **抽素材本身**：`ffmpeg -ss 7 -i 小说.mp4 -frames:v 1 ...` 看素材第7秒是不是小说 tab
4. 本次结论：素材本身第1秒就是小说书城，没问题 → 是第一次批量渲染时素材正被写入，
   取到了旧内容。**直接重渲染即修复**，不需改脚本。

若素材本身确实是电影内容，则需要换一份真正的小说录屏素材。

## QC 配方（每条成片必做）

```bash
# 参数
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=width,height -of default=nw=1 final_<tag>.mp4
# 期望 15.05-15.07s / 1280x720 / h264+aac

# 品牌句抽帧（找"红果短剧"那句的时间点）
ffmpeg -y -ss <t> -i final.mp4 -frames:v 1 -vf scale=640:-1 brand.png
# 确认：黄色"红果短剧" + 右上角 logo + 左侧手机录屏

# 小说段抽帧（约 11.5s）
ffmpeg -y -ss 11.5 -i final.mp4 -frames:v 1 \
  -vf "crop=270:600:30:60,scale=135:-1" novel.png
# 确认：小说书城/排行榜界面，不是电影列表

# 批量核验小说段：把多条抽帧拼网格一次看完
ffmpeg -i n%02d.png -vf "tile=4x2" grid.png
```

**录屏必须在动**：取同一记录段内两帧做像素对比，变化率应 >20%（通常 35-50%）。
静态说明 `setpts` 偏移坏了，需重渲染。

## 交付

成片复制到独立目录，命名 `红果推广_NN_主体.mp4`（NN 两位序号）。
主回复报进度（如"8/10 完成"）+ 未完成原因（额度耗尽 / 窗口需复位）+ 补跑命令。
未生成成功的条目：删掉错误的 raw/成片残留，避免下次跳过逻辑误判。
