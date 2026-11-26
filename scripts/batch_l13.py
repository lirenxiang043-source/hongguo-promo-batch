#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L13 雨伞系列 10 条：图生视频(15s) -> 字幕 -> 标黄 -> 三段录屏渲染。严格串行，一条完成再下一条。

用法:
  python batch_l13.py --gen-only          # 只生视频（10条，串行）
  python batch_l13.py --render-only       # 只剪辑（10条，串行）
  python batch_l13.py --one L13_雨伞橘猫   # 单条：生视频+剪辑（验证用）
  python batch_l13.py                     # 全部：先生后剪
"""
import json, os, pathlib, subprocess, sys, time

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent
GEN_ONE = ROOT / 'promo_platform' / 'gen_one.py'   # 生视频脚本在 promo_platform 目录
PY = sys.executable
IMAGES = ROOT / 'rabbit_iter' / '16x9'
RAW = BASE / 'batch_out' / 'raw'
FINAL = BASE / 'batch_out' / 'final_v2'
LOG = BASE / 'batch_out' / 'batch_l13.log'
DURATION = 15.05
ORAL = ('点一下屏幕，整部剧就能连续播下去。这是红果短剧的连播功能，点开自动接着播，'
        '不用手动反复点。画质高清，播放流畅，除了短剧，它还能看电影、电视剧等等，'
        '小说短视频更是不在话下，资源非常丰富，各种高清资源随便看')

# 10 个动物；subject 用于图生视频的口播主体描述
JOBS = [
    ('L13_雨伞橘猫', '一只撑着白伞的橘猫幼崽'),
    ('L13_雨伞柴犬', '一只撑着白伞的柴犬幼崽'),
    ('L13_雨伞兔子', '一只撑着白伞的兔子幼崽'),
    ('L13_雨伞熊猫', '一只撑着白伞的熊猫幼崽'),
    ('L13_雨伞水獭', '一只撑着白伞的水獭幼崽'),
    ('L13_雨伞小熊', '一只撑着白伞的小熊幼崽'),
    ('L13_雨伞柯基', '一只撑着白伞的柯基幼崽'),
    ('L13_雨伞狐狸', '一只撑着白伞的狐狸幼崽'),
    ('L13_雨伞小鸭', '一只撑着白伞的小鸭幼崽'),
    ('L13_雨伞猫头鹰', '一只撑着白伞的猫头鹰幼崽'),
]

ENV = dict(os.environ)
ENV['HGP_RES_FILE'] = '资源.mp4'   # 新文案含"资源非常丰富"，用资源段录屏


def log(msg):
    line = time.strftime('[%H:%M:%S] ') + str(msg)
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def run(script, args, timeout=None):
    cmd = [PY, script] + [str(a) for a in args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='ignore', cwd=str(BASE), env=ENV, timeout=timeout)
    return p


def gen(tag, subject):
    raw = RAW / ('raw_%s.mp4' % tag)
    if raw.exists() and raw.stat().st_size > 1000000:
        log('  GEN SKIP %s 已存在 (%.1fMB)' % (tag, raw.stat().st_size / 1048576))
        return True
    ref = IMAGES / (tag + '.jpg')
    if not ref.exists():
        log('  GEN FAIL %s 参考图缺失 %s' % (tag, ref))
        return False
    log('  GEN START %s ref=%s' % (tag, ref.name))
    p = run(str(GEN_ONE), [tag, subject, ref, 0, ORAL], timeout=2700)
    out = p.stdout or ''
    if p.returncode == 0 and raw.exists() and raw.stat().st_size > 1000000:
        dur = ''
        for ln in out.splitlines():
            if 'FFPROBE duration' in ln:
                dur = ln.strip()
        log('  GEN OK %s (%.1fMB) %s' % (tag, raw.stat().st_size / 1048576, dur))
        return True
    log('  GEN FAIL %s rc=%s tail=%s' % (tag, p.returncode, out[-400:].replace('\n', ' | ')))
    return False


def render(tag):
    raw = RAW / ('raw_%s.mp4' % tag)
    final = FINAL / ('final_%s.mp4' % tag)
    if not raw.exists():
        log('  RENDER SKIP %s 无原片' % tag); return False
    if final.exists() and final.stat().st_size > 1000000:
        log('  RENDER SKIP %s 成片已存在 (%.1fMB)' % (tag, final.stat().st_size / 1048576))
        return True
    log('  RENDER START %s' % tag)
    p1 = run('auto_subtitle.py', [tag, ORAL, str(DURATION)])
    if p1.returncode != 0:
        log('  SUBTITLE FAIL %s: %s' % (tag, (p1.stdout or '')[-200:])); return False
    p2 = run('rebuild_ass.py', [tag])
    if p2.returncode != 0:
        log('  REBUILD FAIL %s: %s' % (tag, (p2.stdout or '')[-200:])); return False
    p3 = run('render_v2.py', [tag, raw], timeout=900)
    ok = p3.returncode == 0 and final.exists() and final.stat().st_size > 1000000
    log('  RENDER %s %s (%s bytes)' % (tag, 'OK' if ok else 'FAIL',
                                       final.stat().st_size if final.exists() else 0))
    if not ok:
        log('    tail: ' + (p3.stdout or '')[-500:].replace('\n', ' | '))
    return ok


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    only = None
    if mode == '--one':
        only = sys.argv[2]
        mode = ''
    jobs = [j for j in JOBS if only is None or j[0] == only]
    LOG.write_text('', encoding='utf-8')
    log('=== L13 batch start mode=%s oral=%d字 ===' % (mode or 'all', len(ORAL)))

    ok_gen = ok_render = 0
    for tag, subject in jobs:
        log('--- %s ---' % tag)
        if mode not in ('--render-only',):
            if not gen(tag, subject):
                continue
            ok_gen += 1
        if mode not in ('--gen-only',):
            if not render(tag):
                continue
            ok_render += 1
        time.sleep(1)
    log('=== DONE gen=%d render=%d ===' % (ok_gen, ok_render))


if __name__ == '__main__':
    main()
