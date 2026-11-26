#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""画面迭代生图工具 · 豆包 Seedream 5.5

用法:
  # 单张迭代（默认 16:9，自动裁成 1280x720 并入库）
  python gen_image.py --tag A11_狐狸 --subject "一只红狐狸幼崽，嘴巴张开正在说话"

  # 指定完整提示词 / 场景预设
  python gen_image.py --tag A12_水獭 --prompt "一只水獭幼崽，..." --scene rabbit_h2

  # 其它比例、只出原图不裁切
  python gen_image.py --tag S1 --prompt "..." --ratio 1:1 --no-crop

  # 批量
  python gen_image.py --tag A12_水獭 --subject "..." --tag A13_浣熊 --subject "..."

完成后会自动写入 画面迭代库_生成记录.json 并重建 画面迭代库.html。

环境变量:
  HGP_IMG_MODEL   生图模型，默认 Seedream 5.5
  HGP_GATEWAY     网关地址，默认 http://127.0.0.1:8788
  HGP_KEY         网关密钥；不填则读 promo/.doubao_key.tmp
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('HGP_WORK') or BASE.parent)
GATEWAY = os.environ.get('HGP_GATEWAY', 'http://127.0.0.1:8788').rstrip('/')
DEFAULT_MODEL = os.environ.get('HGP_IMG_MODEL', 'Seedream 5.5')
KEY_FILE = BASE / '.doubao_key.tmp'

RAWDIR = ROOT / 'rabbit_iter' / 'raw'
OUTDIR = ROOT / 'rabbit_iter' / '16x9'
THUMB = ROOT / 'rabbit_iter' / 'thumbs'
RECORD = ROOT / '画面迭代库_生成记录.json'

SCENES = {
    'rabbit_h2': ('3D动画电影质感，夜晚室内深蓝色调，虚化的窗户与窗外冷色光斑，'
                  '左侧一本打开的乐谱架，前景一把木质原声吉他，主体站在吉他的音孔旁、'
                  '一只前肢举着发光的金色心形音符，冷暖对比电影级侧逆光，中景平视机位，'
                  '主体占画面高度约55%，头顶留白给字幕。16:9构图，不要文字不要水印。'),
    'night_balcony': ('夜色阳台场景，城市夜色虚化背景，暖色窗光与冷色天光对比，'
                      '主体站在阳台栏杆旁，电影级浅景深，35mm 视角，主体占画面高度约55%，'
                      '头顶留白给字幕。16:9构图，不要文字不要水印。'),
}


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def read_key(explicit=None):
    if explicit:
        return explicit.strip()
    env = os.environ.get('HGP_KEY')
    if env:
        return env.strip()
    for candidate in (KEY_FILE, ROOT / 'promo' / '.doubao_key.tmp', ROOT / '.doubao_key.tmp'):
        if candidate.exists():
            return candidate.read_text(encoding='utf-8').strip()
    raise SystemExit('缺少网关密钥：请设置 HGP_KEY 或创建 %s' % KEY_FILE)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', **kw)


def post_json(url, payload, key, timeout=240):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', 'ignore'))


def download(url, dest, timeout=180):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open('wb') as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest.stat().st_size


def probe_size(path):
    p = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(path)])
    try:
        w, h = [int(x) for x in p.stdout.strip().split(',')[:2]]
        return w, h
    except Exception:
        return 0, 0


def crop_to(src, dest, ratio_w, ratio_h, width=1280):
    w, h = probe_size(src)
    if not w or not h:
        raise RuntimeError('无法读取图片尺寸: %s' % src)
    target_w = int(round(h * ratio_w / ratio_h))
    if target_w <= w:
        x = (w - target_w) // 2
        vf = 'crop=%d:%d:%d:0' % (target_w, h, x)
    else:
        target_h = int(round(w * ratio_h / ratio_w))
        y = (h - target_h) // 2
        vf = 'crop=%d:%d:0:%d' % (w, target_h, y)
    out_h = int(round(width * ratio_h / ratio_w))
    vf += ',scale=%d:%d' % (width, out_h)
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf', vf, str(dest)])
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError('裁切失败: %s' % src)


def remove_watermark(path, x_ratio=0.895, y_ratio=0.925, w_ratio=0.10, h_ratio=0.068):
    """抹掉右下角“豆包 AI 生成”水印；深色背景上 delogo 基本无痕。"""
    w, h = probe_size(path)
    if not w or not h:
        return False
    x = int(w * x_ratio)
    y = int(h * y_ratio)
    ww = min(int(w * w_ratio), w - x - 2)
    hh = min(int(h * h_ratio), h - y - 2)
    if ww <= 2 or hh <= 2:
        return False
    tmp = path.with_name(path.stem + '.nowm' + path.suffix)
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(path),
         '-vf', 'delogo=x=%d:y=%d:w=%d:h=%d' % (x, y, ww, hh), str(tmp)])
    if tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(path)
        return True
    tmp.unlink(missing_ok=True)
    return False


def write_thumb(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf', 'scale=400:-1', str(dest)])


def load_records():
    if not RECORD.exists():
        return []
    try:
        data = json.loads(RECORD.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_record(entry):
    rows = load_records()
    rows = [r for r in rows if r.get('path') != entry.get('path')]
    rows.append(entry)
    RECORD.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')


def build_prompt(subject=None, prompt=None, scene=None):
    if prompt:
        text = prompt.strip()
        if scene and scene in SCENES:
            text = text + '，' + SCENES[scene]
        return text
    if not subject:
        raise SystemExit('需要 --prompt 或 --subject')
    text = subject.strip()
    if scene and scene in SCENES:
        text = text + '，' + SCENES[scene]
    elif scene:
        text = text + '，' + scene
    return text


def generate_one(tag, prompt, ratio='16:9', model=DEFAULT_MODEL, key=None, outdir=None,
                 rawdir=None, thumbdir=None, crop=True, retries=3, dewatermark=True):
    key = key or read_key()
    outdir = Path(outdir) if outdir else OUTDIR
    rawdir = Path(rawdir) if rawdir else RAWDIR
    thumbdir = Path(thumbdir) if thumbdir else THUMB
    for d in (rawdir, outdir, thumbdir):
        d.mkdir(parents=True, exist_ok=True)

    last = None
    for attempt in range(1, retries + 1):
        try:
            log('%s 提交生图（%s, %s）第 %d 次' % (tag, model, ratio, attempt))
            resp = post_json(GATEWAY + '/v1/images/generations',
                             {'model': model, 'size': ratio, 'prompt': prompt}, key)
            items = resp.get('data') or []
            if not items:
                raise RuntimeError('网关未返回图片: %s' % json.dumps(resp, ensure_ascii=False)[:300])
            item = items[0]
            url = item.get('url')
            if not url:
                raise RuntimeError('返回缺少 url')
            # 豆包开了无水印档位时，网关直接给 image_ori_raw，这里就不必再擦除。
            source_watermarked = item.get('watermarked')
            raw = rawdir / (tag + '.jpg')
            size = download(url, raw)
            w, h = probe_size(raw)
            log('%s 下载完成 %.0f KB，%dx%d' % (tag, size / 1024.0, w, h))

            if crop and ':' in ratio:
                rw, rh = [int(x) for x in ratio.split(':')[:2]]
                final = outdir / (tag + '.jpg')
                crop_to(raw, final, rw, rh)
                need_wm = source_watermarked is not False
                wm_removed = remove_watermark(final) if (dewatermark and need_wm) else False
            else:
                final = raw
                wm_removed = False
            write_thumb(final, thumbdir / (tag + '.jpg'))
            fw, fh = probe_size(final)

            record = {
                'tag': tag,
                'path': final.relative_to(ROOT).as_posix() if final.is_relative_to(ROOT) else str(final),
                'raw': raw.relative_to(ROOT).as_posix() if raw.is_relative_to(ROOT) else str(raw),
                'model': resp.get('model') or model,
                'requested_model': model,
                'ratio': ratio,
                'prompt': prompt,
                'width': fw,
                'height': fh,
                'watermark_removed': wm_removed,
                'source_watermarked': source_watermarked,
                'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
            }
            save_record(record)
            log('%s 已入库 %s（%dx%d）' % (tag, final, fw, fh))
            return record
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, OSError) as e:
            detail = ''
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = e.read().decode('utf-8', 'ignore')[:300]
                except Exception:
                    pass
            last = '%s %s' % (e, detail)
            log('%s 第 %d 次失败: %s' % (tag, attempt, last))
            if attempt < retries:
                time.sleep(4)
    raise RuntimeError('%s 生图失败: %s' % (tag, last))


def rebuild_library():
    script = ROOT / 'build_visual_library.py'
    if not script.exists():
        return
    p = run([sys.executable, str(script)])
    print((p.stdout or '').strip(), flush=True)
    if p.returncode != 0:
        log('画面库重建失败: %s' % (p.stderr or '').strip()[:300])


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='豆包 Seedream 5.5 画面迭代生图')
    ap.add_argument('--tag', action='append', default=[], help='文件名/编号，可重复')
    ap.add_argument('--subject', action='append', default=[], help='主体描述，可重复，与 --tag 一一对应')
    ap.add_argument('--prompt', default='', help='完整提示词（单张时使用）')
    ap.add_argument('--scene', default='rabbit_h2', help='场景预设 rabbit_h2 / night_balcony / none / 自定义文本')
    ap.add_argument('--ratio', default='16:9', help='出图比例，默认 16:9')
    ap.add_argument('--model', default=DEFAULT_MODEL, help='模型，默认 Seedream 5.5')
    ap.add_argument('--outdir', default='', help='成图目录，默认 rabbit_iter/16x9')
    ap.add_argument('--no-crop', action='store_true', help='不裁切，保留原始出图')
    ap.add_argument('--keep-watermark', action='store_true', help='保留右下角“豆包 AI 生成”水印（默认自动抹除）')
    ap.add_argument('--no-rebuild', action='store_true', help='不重建画面迭代库')
    ap.add_argument('--key', default='', help='网关密钥')
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    scene = None if args.scene in ('', 'none', 'None') else args.scene
    key = read_key(args.key)

    jobs = []
    if args.prompt:
        if not args.tag:
            raise SystemExit('使用 --prompt 时必须给 --tag')
        jobs = [(t, build_prompt(prompt=args.prompt, scene=scene)) for t in args.tag]
    else:
        if not args.tag:
            raise SystemExit('请给 --tag 和 --subject')
        if len(args.tag) != len(args.subject):
            raise SystemExit('--tag 与 --subject 数量需一致（%d vs %d）' % (len(args.tag), len(args.subject)))
        jobs = [(t, build_prompt(subject=s, scene=scene)) for t, s in zip(args.tag, args.subject)]

    ok = 0
    for tag, prompt in jobs:
        try:
            generate_one(tag, prompt, ratio=args.ratio, model=args.model, key=key,
                         outdir=args.outdir or None, crop=not args.no_crop,
                         dewatermark=not args.keep_watermark)
            ok += 1
        except Exception as e:
            log('%s 失败: %s' % (tag, e))

    if ok and not args.no_rebuild:
        rebuild_library()
    log('完成 %d/%d，模型 %s' % (ok, len(jobs), args.model))
    return 0 if ok == len(jobs) else 1


if __name__ == '__main__':
    raise SystemExit(main())
