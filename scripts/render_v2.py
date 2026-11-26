#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""动态录屏渲染 v3:
- 录屏真正「动态播放」：用 setpts 把录屏流平移到其显示起点，随主视频时间轴逐帧播放。
  (旧版录屏流从 0 播放但 enable 到 5.x 秒才显示, 到那时已播完 -> 停在最后一帧=静帧)
- 「自动续播全剧」那句 -> 「播放流畅」那句 的整个区间, 统一用 自动续播全剧.mp4 动态覆盖。
- logo 只在字幕明确出现完整「红果短剧」的句子出现。
用法: python render_v2.py <tag> <raw_video> [--dry]
"""
import json
import os
import subprocess
import sys
import pathlib

BASE = pathlib.Path(os.environ.get('HGP_WORK') or pathlib.Path.cwd())
# 素材目录/logo 可用环境变量覆盖（默认仍是红果短剧多功能目录，兼容历史批次）
RECDIR = pathlib.Path(os.environ.get('HGP_RECDIR') or r'D:\l\素材\录屏\多功能')
_LOGO_ORIG = os.environ.get('HGP_LOGO') or r'D:\l\素材\微信图片_20251210113937_73_2.png'
LOGO = _LOGO_ORIG if os.path.exists(_LOGO_ORIG) else str(BASE / 'hongguo_logo.png')
MUSIC = 'music_bed.m4a'
FINAL = BASE / 'batch_out' / 'final_v2'
FINAL.mkdir(parents=True, exist_ok=True)

# 自动续播大段
AUTO_FILE = os.environ.get('HGP_AUTO_FILE') or '自动续播全剧.mp4'
AUTO_KEYS = ('自动续播全剧', '续播全剧', '自动续播', '连播功能', '连播', '接着播')
FLUENT_KEYS = ('流畅',)                                  # 播放流畅/照流畅/放出流畅/画质播放流畅
BREAK_KEYS = ('除了', '小说', '电影', '电视剧', '资源')  # 遇到下一个主题就停止延伸

# 资源大段：从「海量热门短剧汇集」那句一直覆盖到片尾
RES_KEYS = ('海量', '热门短剧汇集', '汇集', '题材全', '资源')
# 资源段录屏文件可用环境变量覆盖（如这批用 漫剧.mp4），默认仍是 资源.mp4
RES_FILE = os.environ.get('HGP_RES_FILE') or '资源.mp4'

# 优质漫剧大段：从「优质漫剧」那句一直覆盖到「…都有」那句末（题材介绍整段）
QUALITY_KEYS = ('优质漫剧',)
QUALITY_FILE = os.environ.get('HGP_QUALITY_FILE') or '优质漫剧.mp4'

# 其余关键词 -> 录屏（长词在前）
KEYWORDS = [
    ('连续播放', '全集.mp4'),
    ('连续播', '全集.mp4'),
    ('连播', '全集.mp4'),
    ('优质漫剧', '优质漫剧.mp4'),   # 漫剧筛选列表页，配"优质漫剧多"
    ('电视剧', '电影.mp4'),
    ('电影', '电影.mp4'),
    ('小说', '小说.mp4'),
    ('资源', RES_FILE),
]
MAX_LEN = 2.6
MIN_LEN = 1.3

# 叠加手机的位置/尺寸可覆盖：参考图本身带手机时，放大叠加层把原手机完全盖住
PHONE_SCALE = os.environ.get('HGP_PHONE_SCALE', '224:498')
FRAME_SCALE = os.environ.get('HGP_FRAME_SCALE', '256:530')
REC_POS = os.environ.get('HGP_REC_POS', '60:95')
FRAME_POS = os.environ.get('HGP_FRAME_POS', '44:79')


def duration(video):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=nw=1:nk=1', str(video)],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')
    return float(p.stdout.strip())


def _fit_span(st, en):
    d = en - st
    if d < MIN_LEN:
        pad = (MIN_LEN - d) / 2
        st = max(0.0, st - pad)
        en = en + pad
    if en - st > MAX_LEN:
        en = st + MAX_LEN
    return (st, en)


def auto_span(segs):
    """返回 (start, end, matched_text)：从「自动续播全剧」句到「播放流畅」句。"""
    ai = None
    for i, s in enumerate(segs):
        if any(k in s['text'] for k in AUTO_KEYS):
            ai = i
            break
    if ai is None:
        return None
    st = segs[ai]['start']
    en = segs[ai]['end']
    for j in range(ai + 1, len(segs)):
        t = segs[j]['text']
        prev_en = en
        en = segs[j]['end']
        if any(f in t for f in FLUENT_KEYS):   # 到「播放流畅」结束
            break
        if any(b in t for b in BREAK_KEYS):    # 没流畅句, 遇到新主题就回退停住
            en = prev_en
            break
    return (st, en, segs[ai]['text'])


def resource_span(segs):
    """返回 (start, end, matched_text)：从「海量/汇集」句到片尾, 用资源.mp4 覆盖。"""
    ri = None
    for i, s in enumerate(segs):
        if any(k in s['text'] for k in RES_KEYS):
            ri = i
            break
    if ri is None:
        return None
    return (segs[ri]['start'], segs[-1]['end'], segs[ri]['text'])


def quality_span(segs):
    """返回 (start, end, matched_text)：从「优质漫剧多」句延伸到含「都有」的句末。
    让筛选列表录屏覆盖整个「优质漫剧多，修仙逆袭穿越都有」题材介绍段。"""
    qi = None
    for i, s in enumerate(segs):
        if any(k in s['text'] for k in QUALITY_KEYS):
            qi = i
            break
    if qi is None:
        return None
    st = segs[qi]['start']
    en = segs[qi]['end']
    # 向后延伸：遇到含「都有」的句子就吃到它的末尾；遇到资源主题/片尾就停住
    for j in range(qi + 1, len(segs)):
        t = segs[j]['text']
        if '都有' in t:
            en = segs[j]['end']
            break
        if any(k in t for k in RES_KEYS):
            en = segs[j - 1]['end']
            break
        en = segs[j]['end']
    return (st, en, segs[qi]['text'])


def plan(tag):
    segs = json.loads((BASE / ('subs_%s.json' % tag)).read_text(encoding='utf-8'))
    brand = None
    for s in segs:
        if '红果短剧' in s['text'] or '红果漫剧' in s['text']:
            brand = (s['start'], s['end'], s['text'])
            break

    au = auto_span(segs)
    qu = quality_span(segs)
    rs = resource_span(segs)
    clips = []
    if au:
        clips.append((AUTO_FILE, au[0], au[1], '自动续播', au[2]))
    if qu:
        clips.append((QUALITY_FILE, qu[0], qu[1], '优质漫剧', qu[2]))
    if rs:
        clips.append((RES_FILE, rs[0], rs[1], '资源', rs[2]))

    for s in segs:
        st, en, text = s['start'], s['end'], s['text']
        # 品牌句仍让 logo 显示, 但不再因此丢掉录屏(只要句子本身带录屏关键词)
        if au and st >= au[0] - 0.01 and en <= au[1] + 0.01:   # 已被自动续播大段覆盖
            continue
        if qu and st >= qu[0] - 0.01 and en <= qu[1] + 0.01:   # 已被优质漫剧大段覆盖
            continue
        if rs and st >= rs[0] - 0.01 and en <= rs[1] + 0.01:   # 已被资源大段覆盖
            continue
        hit = None
        for kw, fn in KEYWORDS:
            if kw in text:
                hit = (kw, fn)
                break
        if not hit:
            continue
        kw, fn = hit
        span = _fit_span(st, en)
        clips.append((fn, span[0], span[1], kw, text))

    clips.sort(key=lambda c: c[1])
    # 合并相邻同文件
    merged = []
    for c in clips:
        if merged and merged[-1][0] == c[0] and c[1] <= merged[-1][2] + 0.15:
            p = merged[-1]
            merged[-1] = (p[0], p[1], max(p[2], c[2]), p[3] + '/' + c[3], p[4] + ' | ' + c[4])
        else:
            merged.append(c)
    # 去相邻重叠
    for i in range(1, len(merged)):
        p, c = merged[i - 1], merged[i]
        if c[1] < p[2]:
            merged[i] = (c[0], p[2], c[2], c[3], c[4])
    merged = [c for c in merged if c[2] > c[1] + 0.05]
    return brand, merged, segs


def render(tag, raw, dry_run=False):
    brand, clips, segs = plan(tag)
    total = duration(raw)
    print('--- PLAN %s (total=%.2f) ---' % (tag, total))
    if brand:
        print('  logo/brand  %.2f-%.2f : %s' % (brand[0], brand[1], brand[2]))
    else:
        print('  logo/brand  NONE')
    for fn, s, e, kw, txt in clips:
        print('  REC %-18s %.2f-%.2f (%.2fs) [%s] %s' % (fn, s, e, e - s, kw, txt))
    if dry_run:
        return

    clips2 = []
    for fn, s, e, kw, txt in clips:
        e = min(e, total - 0.05)
        if e > s:
            clips2.append((fn, s, e, kw, txt))
    clips = clips2

    # logo 时段：围绕品牌句前后 0.25s，避让所有录屏
    b_brand = None
    if brand:
        bs = max(0.0, brand[0] - 0.25)
        be = min(total, brand[1] + 0.25)
        for _, s, e, _, _ in clips:
            if not (be <= s or bs >= e):
                if brand[0] < s:
                    be = min(be, s)
                else:
                    bs = max(bs, e)
        if be - bs >= 0.5:
            b_brand = (bs, be)
        else:
            # 品牌句整段被录屏覆盖时保留 logo：logo 在右下(500:440)与左侧录屏(60:95)不冲突
            b_brand = (max(0.0, brand[0] - 0.25), min(total, brand[1] + 0.25))

    uniq_files = []
    for fn, *_ in clips:
        if fn not in uniq_files:
            uniq_files.append(fn)
    cmd = ['ffmpeg', '-y', '-i', str(raw)]
    for fn in uniq_files:
        cmd += ['-i', str(RECDIR / fn)]
    n_clips = len(clips)
    n_rec = len(uniq_files)
    logo_idx = 1 + n_rec
    cmd += ['-i', LOGO, '-i', MUSIC, '-i', 'whoosh.wav', '-i', 'click.wav',
            '-i', 'pop.wav', '-i', 'phone_frame.png', '-i', 'screen_mask.png']
    music_i, whoosh_i, click_i, pop_i, frame_i, mask_i = (
        logo_idx + 1, logo_idx + 2, logo_idx + 3, logo_idx + 4, logo_idx + 5, logo_idx + 6)

    fc = []
    # 没有录屏片段时不要生成 split——否则 [fr0]/[mk0] 未连接会让 filtergraph 报错
    if n_clips > 0:
        fc.append('[%d:v]format=rgba,scale=%s,split=%d%s' % (frame_i, FRAME_SCALE, n_clips, ''.join('[fr%d]' % i for i in range(n_clips))))
        fc.append('[%d:v]format=gray,scale=%s,split=%d%s' % (mask_i, PHONE_SCALE, n_clips, ''.join('[mk%d]' % i for i in range(n_clips))))

    # 关键修复: setpts=PTS-STARTPTS+s/TB —— 让录屏从显示起点 s 开始逐帧播放(动态)
    clip_streams = []
    for i, (fn, s, e, kw, txt) in enumerate(clips):
        src = 1 + uniq_files.index(fn)
        d = e - s
        fc.append('[%d:v]trim=start=0:end=%.3f,setpts=PTS-STARTPTS+%.3f/TB,fps=24,'
                  'scale=%s:flags=lanczos,format=rgba[ra%d]' % (src, d, s, PHONE_SCALE, i))
        fc.append('[ra%d][mk%d]alphamerge[rec%d]' % (i, i, i))
        clip_streams.append((i, s, e))

    cur = '[0:v]'
    for i, s, e in clip_streams:
        fc.append("%s[rec%d]overlay=%s:enable='between(t,%.3f,%.3f)'[va%d]" % (cur, i, REC_POS, s, e, i))
        fc.append("[va%d][fr%d]overlay=%s:enable='between(t,%.3f,%.3f)'[vb%d]" % (i, i, FRAME_POS, s, e, i))
        cur = '[vb%d]' % i

    if b_brand:
        fc.append('[%d:v]scale=150:150:flags=lanczos[logo]' % logo_idx)
        fc.append("%s[logo]overlay=500:440:enable='between(t,%.3f,%.3f)'[vlogo]" % (cur, b_brand[0], b_brand[1]))
        cur = '[vlogo]'

    fc.append('%sass=subs_%s.ass[vout]' % (cur, tag))

    fc.append('[0:a]asetpts=PTS-STARTPTS[voice]')
    fc.append('[%d:a]asetpts=PTS-STARTPTS[music]' % music_i)
    mix_labels = ['[voice]', '[music]']
    for i, s, e in clip_streams:
        fc.append('[%d:a]adelay=%d:all=1,volume=0.55[w%d]' % (whoosh_i, int(s * 1000), i))
        mix_labels.append('[w%d]' % i)
    fc.append('[%d:a]adelay=100:all=1,volume=0.9[clk]' % click_i)
    mix_labels.append('[clk]')
    if b_brand:
        fc.append('[%d:a]adelay=%d:all=1,volume=0.8[pop]' % (pop_i, int(b_brand[0] * 1000)))
        mix_labels.append('[pop]')
    fc.append('%samix=inputs=%d:duration=first:normalize=0,aformat=sample_fmts=fltp[aout]' % (
        ''.join(mix_labels), len(mix_labels)))

    cmd += ['-filter_complex', ';'.join(fc),
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k', '-t', '%.2f' % total,
            str(FINAL / ('final_%s.mp4' % tag))]
    p = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True,
                       encoding='utf-8', errors='ignore')
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2000:])
    dst = FINAL / ('final_%s.mp4' % tag)
    print('RENDERED', dst.name, dst.stat().st_size)
    print('  logo', [round(x, 2) for x in b_brand] if b_brand else None)


if __name__ == '__main__':
    render(sys.argv[1], pathlib.Path(sys.argv[2]), dry_run=(len(sys.argv) > 3 and sys.argv[3] == '--dry'))
