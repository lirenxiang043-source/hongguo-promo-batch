#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""扫描所有画面迭代目录，生成可搜索/预览/复制的画面迭代库。

用法:
  python build_visual_library.py
  python build_visual_library.py --watch   # 每 20 秒检测一次，有新图自动重建

新增图片:
  - 直接放进 画面迭代库_收件箱/（可按场景建子目录）
  - 或把图放进 rabbit_iter/16x9、visual_iter/16x9 等已有目录
  - 重建后会生成 画面迭代库.html / 画面迭代库.json / 画面迭代库_缩略图/
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INBOX = ROOT / '画面迭代库_收件箱'
THUMB_DIR = ROOT / '画面迭代库_缩略图'
HTML_PATH = ROOT / '画面迭代库.html'
JSON_PATH = ROOT / '画面迭代库.json'
GEN_LOG = ROOT / '画面迭代库_生成记录.json'
OVERRIDE_PATH = ROOT / '画面迭代库_手工.json'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
# 页面增删改只改这些元数据字段；path/thumb/size/mtime 等由文件扫描决定，不允许手改
EDITABLE_FIELDS = ('title', 'tag', 'subject', 'line', 'scene', 'variant', 'note', 'model', 'prompt')

# 优先级从高到低；同图去重时保留靠前的成图，原始出图只作为来源记录。
SOURCES = [
    ('inbox', INBOX, '最新收件箱', '收件箱', 0, True),
    ('rabbit_final', ROOT / 'rabbit_iter' / '16x9', '兔子先生 H2 · 夜晚吉他', '16:9 成图', 1, False),
    ('visual_final', ROOT / 'visual_iter' / '16x9', '夜色阳台 / 雨巷', '16:9 成图', 1, False),
    ('rabbit_raw', ROOT / 'rabbit_iter' / 'raw', '兔子先生 H2 · 夜晚吉他', '原始出图', 2, False),
    ('visual_raw_top', ROOT / 'visual_iter', '夜色阳台 / 雨巷', '原始出图', 2, False),
    ('visual_raw', ROOT / 'visual_iter' / 'raw', '夜色阳台 / 雨巷', '原始出图', 3, False),
]

SUBJECTS = {
    'A0': '原图', 'A1': '鹦鹉', 'A2': '橘猫', 'A3': '狐狸', 'A4': '熊猫',
    'A5': '兔子', 'A6': '恐龙', 'A7': '柴犬', 'A8': '企鹅', 'A9': '考拉',
    'A10': '树懒', 'A11': '红狐', 'A12': '水獭', 'A13': '浣熊',
    'B0': '原图', 'B1': '柴犬',
}
SCENE_NOTE = {
    '兔子先生 H2 · 夜晚吉他': '固定场景：夜晚室内深蓝调 / 左侧乐谱架 / 木质吉他 / 发光音符；只换主体，不换构图和光位。',
    '夜色阳台 / 雨巷': '固定场景：原视频抽帧，夜色阳台或雨巷；只换主体，保留机位、道具、光位和画风。',
    '最新收件箱': '手动放入的新迭代图；建议按场景建子目录，子目录名会自动成为场景名。',
}

TAG_RE = re.compile(r'^([AB])\s*(\d{1,2})[_\-\s]+(.+?)(?:\.[^.]+)?$', re.I)
IMG_RE = re.compile(r'\.(?:jpe?g|png|webp|bmp)$', re.I)


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', **kwargs)


def sha1(path):
    h = hashlib.sha1()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def probe_size(path):
    p = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(path)])
    try:
        w, h = [int(x) for x in p.stdout.strip().split(',')[:2]]
        return w, h
    except Exception:
        return 0, 0


def rel(path):
    return path.relative_to(ROOT).as_posix()


def load_gen_meta():
    """读取 gen_image.py 写下的生成记录，按相对路径 / 文件名索引。"""
    out = {}
    if not GEN_LOG.exists():
        return out
    try:
        rows = json.loads(GEN_LOG.read_text(encoding='utf-8'))
    except Exception:
        return out
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get('path') or ''
        if path:
            out[path] = row
        stem = Path(path).stem if path else (row.get('tag') or '')
        if stem and stem not in out:
            out[stem] = row
    return out


def pick_tag(path, source_key, ordinal):
    m = TAG_RE.match(path.stem)
    if m:
        tag = (m.group(1) + str(int(m.group(2)))).upper()
        label = SUBJECTS.get(tag) or m.group(3).strip()
        return tag, label
    if source_key == 'rabbit_raw':
        # 这一批 7 张无编号原图按出图顺序对应 A1~A7
        if ordinal <= 7:
            tag = 'A%d' % ordinal
            return tag, SUBJECTS[tag]
    if 'parrot' in path.stem.lower() or '鹦鹉' in path.stem:
        return 'A1', SUBJECTS['A1']
    return '', path.stem.replace('_', ' ')[:30]


def make_thumb(src, digest):
    dest = THUMB_DIR / ('%s.jpg' % digest[:14])
    try:
        if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
            return dest
        run(['ffmpeg', '-y', '-v', 'error', '-i', str(src),
             '-vf', 'scale=480:-1:flags=lanczos', '-q:v', '3', str(dest)])
    except Exception:
        pass
    return dest if dest.exists() else None


def iter_source_files(source_key, directory, recursive):
    if not directory.exists():
        return []
    if recursive:
        files = [p for p in directory.rglob('*') if p.is_file()]
    else:
        files = [p for p in directory.iterdir() if p.is_file()]
    files = [p for p in files if p.suffix.lower() in IMAGE_EXTS]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return files


def collect():
    entries = []
    by_hash = {}
    gen_meta = load_gen_meta()
    for source_key, directory, scene, variant, priority, recursive in SOURCES:
        files = iter_source_files(source_key, directory, recursive)
        ordinal = 0
        for src in files:
            if not IMG_RE.search(src.name):
                continue
            # 排除缩略图目录、隐藏文件
            if any(part.lower() in ('thumbs', 'thumb', '.git') for part in src.parts):
                continue
            ordinal += 1
            digest = sha1(src)
            meta = gen_meta.get(rel(src)) or gen_meta.get(src.stem) or {}
            tag, subject = pick_tag(src, source_key, ordinal)
            if tag in ('A0', 'B0'):
                variant_here = '参考原图'
            else:
                variant_here = variant
            scene_here = scene
            if source_key == 'inbox':
                parent = src.parent.relative_to(directory)
                if str(parent) not in ('', '.'):
                    scene_here = parent.parts[-1]
            if digest in by_hash:
                existing = by_hash[digest]
                if rel(src) not in existing['sources']:
                    existing['sources'].append(rel(src))
                # 收件箱里的同名图可能没编号；后面遇到带编号的成图时补齐元数据
                if tag and not existing['tag']:
                    existing.update(tag=tag, subject=subject, title=(tag + ' · ' + subject if tag else subject),
                                    line=tag[0] if tag and tag[0] in 'AB' else '', variant=variant_here)
                if meta and not existing.get('model'):
                    existing['model'] = meta.get('model', '')
                    existing['prompt'] = meta.get('prompt', '')
                continue
            w, h = probe_size(src)
            thumb = make_thumb(src, digest)
            entry = {
                'id': digest[:14],
                'tag': tag,
                'subject': subject,
                'title': (tag + ' · ' + subject) if tag else subject,
                'line': tag[0] if tag and tag[0] in 'AB' else '',
                'scene': scene_here,
                'variant': variant_here,
                'path': rel(src),
                'thumb': rel(thumb) if thumb else rel(src),
                'sources': [rel(src)],
                'width': w,
                'height': h,
                'size': src.stat().st_size,
                'mtime': datetime.datetime.fromtimestamp(src.stat().st_mtime).isoformat(timespec='seconds'),
                'model': meta.get('model', ''),
                'prompt': meta.get('prompt', ''),
                'note': SCENE_NOTE.get(scene_here, ''),
                'priority': priority,
            }
            by_hash[digest] = entry
            entries.append(entry)
    entries.sort(key=lambda e: (e['mtime'], e['title']), reverse=True)
    for e in entries:
        e.pop('priority', None)
    return entries


def apply_override(entries):
    """套用页面增删改的覆盖层，保证重建后手工改动不丢。
    deleted: 按 id 移除；overrides: 按 id 覆盖允许的手工字段；added: 手工新增条目。
    """
    if not OVERRIDE_PATH.exists():
        return entries
    try:
        ov = json.loads(OVERRIDE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return entries
    deleted = set(ov.get('deleted') or [])
    overrides = ov.get('overrides') or {}
    added = ov.get('added') or []
    added_map = {a.get('id'): a for a in added if a.get('id')}

    out = []
    for e in entries:
        if e.get('id') in deleted:
            continue
        # 扫描到的条目：优先套用编辑覆盖，其次套用新增时填的元数据
        src = overrides.get(e.get('id')) or added_map.get(e.get('id'))
        if src:
            for k in EDITABLE_FIELDS:
                if k in src:
                    e[k] = src[k]
        out.append(e)
    have = {e.get('id') for e in out}
    for a in added:
        if a.get('id') and a['id'] not in have and a['id'] not in deleted:
            row = dict(a)
            src = overrides.get(a['id'])
            if src:
                for k in EDITABLE_FIELDS:
                    if k in src:
                        row[k] = src[k]
            out.append(row)
            have.add(a['id'])
    return out


def build_data(entries):
    now = datetime.datetime.now()
    scenes = sorted({e['scene'] for e in entries})
    subjects = sorted({e['subject'] for e in entries if e['subject']})
    today = now.strftime('%Y-%m-%d')
    today_count = sum(1 for e in entries if e['mtime'].startswith(today))
    return {
        'generated_at': now.isoformat(timespec='seconds'),
        'total': len(entries),
        'subjects': subjects,
        'scenes': scenes,
        'models': sorted({e['model'] for e in entries if e.get('model')}),
        'today_count': today_count,
        'items': entries,
    }


def render_html(data):
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace('</', '<\\/')
    template = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>画面迭代库</title>
<style>
:root{--red:#ff4d2e;--red2:#ff7a5c;--ink:#F7F7F8;--muted:#8A8D95;--line:#23262C;--line2:#33373F;--bg:#06070A;--card:rgba(18,20,26,.9);--raised:#1C1F24}
*{box-sizing:border-box}
html{background:#030405}
body{margin:0;background:transparent;color:var(--ink);font-family:"Inter","Noto Sans SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
/* ===== Eye-opening cinematic background ===== */
.bg-stage{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none;background:#030405}
.eye-layer{position:absolute;inset:-4%;z-index:0;will-change:transform;transition:transform .6s cubic-bezier(.22,1,.36,1)}
.eye-img{position:absolute;inset:0;background-image:__EYE_URL__;background-size:cover;background-position:center 40%;transform:scale(1.06);animation:eyeBreath 8s 2.2s ease-in-out infinite}
@keyframes eyeBreath{0%,100%{transform:scale(1.06)}50%{transform:scale(1.1)}}
#stars{position:absolute;inset:0;width:100%;height:100%;z-index:1}
.eye-scrim{position:absolute;inset:0;z-index:2;background:linear-gradient(180deg,rgba(3,4,5,.62),rgba(3,4,5,.12) 26%,rgba(3,4,5,.3) 62%,rgba(3,4,5,.72)),linear-gradient(90deg,rgba(3,4,5,.86),rgba(3,4,5,.18) 55%,transparent 80%)}
.vignette{position:absolute;inset:0;z-index:2;background:radial-gradient(ellipse 92% 78% at 50% 42%,transparent 22%,rgba(3,4,5,.82) 100%)}
.eye-flash{position:absolute;inset:0;z-index:3;background:radial-gradient(ellipse 60% 40% at 50% 44%,rgba(255,30,30,.55),transparent 65%);opacity:0;animation:eyeFlash 1s .95s ease-out}
@keyframes eyeFlash{0%{opacity:0}22%{opacity:1}100%{opacity:0}}
.eye-curtain{position:fixed;inset:0;z-index:500;pointer-events:none;overflow:hidden}
.lid{position:absolute;left:0;right:0;height:50.5%;background:#030405}
.lid.top{top:0;box-shadow:0 4px 0 rgba(255,32,32,.92),0 10px 34px rgba(255,0,0,.55);animation:lidTop 1.5s .3s cubic-bezier(.76,0,.24,1) forwards}
.lid.bot{bottom:0;box-shadow:0 -4px 0 rgba(255,32,32,.92),0 -10px 34px rgba(255,0,0,.55);animation:lidBot 1.5s .3s cubic-bezier(.76,0,.24,1) forwards}
@keyframes lidTop{to{transform:translateY(-101%)}}
@keyframes lidBot{to{transform:translateY(101%)}}
.eye-replay{position:fixed;top:22px;right:30px;z-index:501;background:rgba(255,77,46,.08);border:1px solid rgba(255,77,46,.35);color:var(--red2);font-size:11px;font-weight:600;letter-spacing:.05em;padding:7px 13px;border-radius:99px;cursor:pointer;transition:all .2s}
.eye-replay:hover{background:rgba(255,77,46,.18);border-color:var(--red);color:#fff}
/* hide replay button whenever a floating overlay is open (avoid clashing with close button) */
body:has(.lightbox.on) .eye-replay,body:has(#cmd.on) .eye-replay,body:has(#mask[style*="flex"]) .eye-replay,body:has(#cmask[style*="flex"]) .eye-replay{opacity:0;pointer-events:none}
.lidClosing .lid.top{animation:lidTopClose .5s cubic-bezier(.76,0,.24,1) forwards}
.lidClosing .lid.bot{animation:lidBotClose .5s cubic-bezier(.76,0,.24,1) forwards}
@keyframes lidTopClose{from{transform:translateY(-101%)}to{transform:translateY(0)}}
@keyframes lidBotClose{from{transform:translateY(101%)}to{transform:translateY(0)}}
.hero{background:linear-gradient(180deg,rgba(3,4,5,.32),rgba(3,4,5,.04));color:#fff;padding:40px 26px 30px;border-bottom:1px solid var(--line)}
.wrap{max-width:1280px;margin:0 auto}
.eyebrow{font-size:10px;font-weight:700;letter-spacing:.18em;color:var(--red);text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:10px}
.eyebrow::before{content:"";width:26px;height:1px;background:var(--red)}
.hero h1{margin:0;font-size:clamp(30px,4.5vw,46px);font-weight:800;letter-spacing:-.045em;line-height:1.05}
.hero h1 em{font-style:normal;color:var(--red)}
.hero p{margin:12px 0 0;color:#8A8D95;font-size:13px;line-height:1.7;max-width:620px}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:28px}
.stat{position:relative;background:rgba(255,255,255,.035);border:1px solid var(--line);border-radius:12px;padding:14px 16px;backdrop-filter:blur(6px);overflow:hidden;transition:border-color .2s,transform .2s}
.stat::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:2px;border-radius:2px;background:var(--red);opacity:.7}
.stat:nth-child(2)::before{background:#F472B6}.stat:nth-child(3)::before{background:#22D3EE}.stat:nth-child(4)::before{background:#4ADE80}
.stat:hover{border-color:var(--line2);transform:translateY(-2px)}
.stat b{display:block;font-size:28px;font-weight:800;letter-spacing:-.04em;line-height:1;font-variant-numeric:tabular-nums}
.stat:nth-child(2) b{color:#F472B6}.stat:nth-child(3) b{color:#22D3EE}.stat:nth-child(4) b{color:#4ADE80}
.stat span{font-size:11px;color:#8A8D95;letter-spacing:.04em;margin-top:7px;display:block}
.main{max-width:1280px;margin:0 auto;padding:20px 26px 46px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin-bottom:16px;box-shadow:0 6px 22px rgba(0,0,0,.25);backdrop-filter:blur(8px)}
.hint{display:flex;gap:10px;align-items:flex-start;background:rgba(255,77,46,.07);border:1px solid rgba(255,77,46,.22);color:#e8a99f;border-radius:12px;padding:11px 14px;font-size:13px;line-height:1.7;margin-bottom:16px}
.hint b{color:var(--red2)}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.search{flex:1 1 260px;min-width:220px;position:relative}
.search input{width:100%;border:1px solid var(--line2);border-radius:10px;padding:11px 14px 11px 40px;font-size:14px;outline:none;background:rgba(3,4,5,.5);color:var(--ink);transition:border-color .18s,box-shadow .18s,background .18s}
.search input:focus{border-color:var(--red);box-shadow:0 0 0 3px rgba(255,77,46,.14);background:rgba(3,4,5,.72)}
.search input::placeholder{color:#5C5F67}
.search svg{position:absolute;left:14px;top:12px;width:16px;height:16px;color:#5C5F67;transition:color .18s}
.search:focus-within svg{color:var(--red)}
select{border:1px solid var(--line2);border-radius:10px;padding:11px 32px 11px 13px;background:rgba(3,4,5,.5);font-size:13px;color:var(--ink);outline:none;color-scheme:dark;cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238A8D95' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 11px center;transition:border-color .18s}
select:focus{border-color:var(--red)}
.daterow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:12px;padding-top:12px;border-top:1px dashed var(--line);font-size:12px;color:var(--muted)}
.daterow b{color:var(--ink)}
.daterow span{color:#5C5F67}
.daterow input[type=date]{border:1px solid var(--line2);border-radius:9px;padding:7px 9px;background:rgba(3,4,5,.5);font-size:12px;color:var(--ink);outline:none;color-scheme:dark}
.daterow input[type=date]:focus{border-color:var(--red)}
.daterow button{border:1px solid var(--line2);background:var(--raised);color:#c3c6cd;border-radius:7px;padding:6px 11px;font-size:11px;font-weight:500;cursor:pointer;transition:all .18s}
.daterow button:hover{border-color:var(--red);color:#fff;background:rgba(255,77,46,.12)}
.act-btn{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line2);background:var(--raised);color:#c3c6cd;border-radius:10px;padding:10px 15px;font-size:13px;font-weight:500;cursor:pointer;white-space:nowrap;transition:all .18s cubic-bezier(.22,1,.36,1)}
.act-btn svg{width:15px;height:15px;flex:none}
.act-btn:hover{border-color:var(--red);color:#fff;background:rgba(255,77,46,.1);transform:translateY(-1px)}
.act-btn.primary{background:linear-gradient(135deg,var(--red),var(--red2));border-color:transparent;color:#fff;font-weight:700;box-shadow:0 4px 16px rgba(255,77,46,.28)}
.act-btn.primary:hover{box-shadow:0 6px 24px rgba(255,77,46,.45);transform:translateY(-2px)}
.act-btn:active{transform:translateY(0)}
.mode-badge{font-size:11px;border-radius:99px;padding:6px 10px;background:rgba(255,255,255,.06);color:#8A8D95}
.mode-badge::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:#8A8D95;margin-right:6px;vertical-align:1px}
.mode-badge.api{background:rgba(74,222,128,.1);color:#4ADE80}
.mode-badge.api::before{background:#4ADE80}
.mode-badge.local{background:rgba(251,191,36,.1);color:#FBBF24}
.mode-badge.local::before{background:#FBBF24}
.card-ops{position:absolute;right:10px;top:10px;display:flex;gap:5px;z-index:2}
.card-ops button{border:1px solid rgba(255,255,255,.14);background:rgba(3,4,5,.78);color:#d6d7db;border-radius:7px;padding:5px 9px;font-size:11px;font-weight:600;cursor:pointer;backdrop-filter:blur(4px);transition:all .18s;opacity:.5}
.card:hover .card-ops button{opacity:1}
.card-ops button:hover{border-color:var(--red);color:#fff;background:var(--red)}
.card-ops button.del:hover{border-color:#FF4D4D;background:#FF4D4D;color:#fff}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;z-index:60;padding:20px;backdrop-filter:blur(6px)}
.modal{background:#121418;border:1px solid var(--line2);border-top:2px solid var(--red);border-radius:14px;width:min(620px,100%);max-height:90vh;overflow:auto;padding:24px 26px;box-shadow:0 24px 70px rgba(0,0,0,.7)}
.modal h3{font-size:19px;font-weight:800;letter-spacing:-.02em;margin:0 0 4px}
.modal .sub{color:var(--red);font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin-bottom:18px}
.modal label{display:block;font-size:12px;color:var(--muted);margin-bottom:11px}
.modal label span{display:block;margin-bottom:5px;font-weight:600;color:#d6d7db}
.modal input,.modal textarea,.modal select{width:100%;border:1px solid var(--line2);border-radius:8px;padding:9px 10px;font-size:13px;font-family:inherit;outline:none;background:rgba(3,4,5,.5);color:var(--ink);color-scheme:dark}
.modal input:focus,.modal textarea:focus{border-color:var(--red)}
.modal textarea{min-height:70px;resize:vertical;line-height:1.5}
.modal .row{display:flex;gap:10px}.modal .row>label{flex:1;min-width:0}
.modal .acts{display:flex;justify-content:flex-end;gap:9px;margin-top:8px}
.toast2{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);background:#F7F7F8;color:#08090B;font-size:12px;padding:9px 14px;border-radius:8px;opacity:0;pointer-events:none;transition:.2s;z-index:80}
.toast2.on{opacity:1}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.chip{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line2);background:rgba(255,255,255,.02);color:#9aa0a8;border-radius:999px;padding:7px 13px;font-size:12px;font-weight:500;cursor:pointer;transition:all .18s cubic-bezier(.22,1,.36,1)}
.chip::before{content:"";width:6px;height:6px;border-radius:50%;background:#5C5F67;flex:none;transition:background .18s}
.chip small{font-variant-numeric:tabular-nums;font-size:10px;opacity:.65;background:rgba(255,255,255,.07);border-radius:99px;padding:1px 6px;margin-left:1px}
.chip:hover{border-color:var(--red);color:var(--red2);background:rgba(255,77,46,.06)}
.chip.on{background:var(--red);border-color:var(--red);color:#fff;box-shadow:0 4px 14px rgba(255,77,46,.3)}
.chip.on::before{background:#fff}
.chip.on small{background:rgba(255,255,255,.2);opacity:.9}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.3);transition:box-shadow .2s,border-color .2s;cursor:zoom-in;position:relative}
.card:hover{box-shadow:0 16px 38px rgba(0,0,0,.55);border-color:rgba(255,77,46,.6)}
.thumb{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#111;transition:transform .4s cubic-bezier(.22,1,.36,1)}
.card:hover .thumb{transform:scale(1.04)}
.badge{position:absolute;top:10px;left:10px;background:rgba(3,4,5,.82);color:#fff;font-size:10px;font-weight:700;letter-spacing:.03em;padding:5px 9px;border-radius:7px;backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.08)}
.badge.v16{background:rgba(255,77,46,.94);border-color:rgba(255,255,255,.18)}
.badge.raw{background:rgba(42,90,158,.9)}
.badge.inbox{background:rgba(32,145,105,.92)}
.meta{padding:13px 14px 14px}
.title{font-size:14px;font-weight:700;letter-spacing:-.01em;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.title small{font-weight:500;color:#5C5F67;font-size:10px;white-space:nowrap;font-variant-numeric:tabular-nums}
.scene{color:#8A8D95;font-size:11px;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sub{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}
.tag{font-size:10px;font-weight:500;background:rgba(255,255,255,.05);color:#9aa0a8;border:1px solid rgba(255,255,255,.05);border-radius:5px;padding:3px 7px}
.tag.model{background:rgba(255,77,46,.13);color:var(--red2);border-color:rgba(255,77,46,.3);font-weight:700}
.actions{display:flex;gap:7px;margin-top:12px;padding-top:11px;border-top:1px solid var(--line)}
.actions button,.actions a{flex:1;text-align:center;border:1px solid var(--line2);background:rgba(255,255,255,.025);color:#9aa0a8;border-radius:7px;padding:7px 8px;font-size:11px;font-weight:500;cursor:pointer;text-decoration:none;transition:all .18s}
.actions button:hover,.actions a:hover{background:rgba(255,77,46,.13);color:var(--red2);border-color:rgba(255,77,46,.4)}
.empty{padding:60px 20px;text-align:center;color:#5C5F67;font-size:14px}
.footer{color:#5C5F67;font-size:12px;line-height:1.8;padding-top:14px}
.lightbox{position:fixed;inset:0;background:rgba(10,12,18,.82);display:none;align-items:center;justify-content:center;padding:26px;z-index:50;backdrop-filter:blur(5px)}
.lightbox.on{display:flex}
.lb-body{max-width:min(1180px,94vw);max-height:92vh;display:flex;flex-direction:column;gap:10px}
.lb-body img{max-width:100%;max-height:calc(92vh - 92px);object-fit:contain;border-radius:10px;background:#000;box-shadow:0 24px 80px rgba(0,0,0,.5)}
.lb-bar{display:flex;justify-content:space-between;align-items:center;gap:12px;color:#fff;font-size:13px}
.lb-bar .lb-title{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lb-bar .lb-btns{display:flex;gap:8px;flex-shrink:0}
.lb-bar button,.lb-bar a{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22);color:#fff;border-radius:8px;padding:7px 10px;font-size:12px;cursor:pointer;text-decoration:none}
.lb-bar button:hover,.lb-bar a:hover{background:rgba(255,255,255,.24)}
.lb-close{position:fixed;top:18px;right:22px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);color:#fff;border-radius:50%;width:38px;height:38px;font-size:20px;cursor:pointer;z-index:2;transition:.2s}
.lb-close:hover{background:var(--red);border-color:var(--red)}
/* ---- enhanced interactions ---- */
.kbd{display:inline-block;font-family:inherit;font-size:10px;font-weight:700;line-height:1;border:1px solid var(--line2);border-bottom-width:2px;border-radius:5px;padding:4px 6px;color:#c3c6cd;background:var(--raised)}
.search-wrap{position:relative}
.search-wrap .kbd{position:absolute;right:11px;top:11px;pointer-events:none}
.search input{padding-right:52px}
.note2{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11px;color:#5C5F67;margin-top:11px}
.note2 svg{width:13px;height:13px;flex:none;color:var(--red)}
/* stagger entrance + 3D tilt — element stays visible even if animation is cancelled */
.card{animation:cardIn .5s cubic-bezier(.22,1,.36,1) both;transform-style:preserve-3d}
@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(.985)}to{opacity:1;transform:none}}
.card .sheen{position:absolute;inset:0;pointer-events:none;opacity:0;background:radial-gradient(420px circle at var(--mx,50%) var(--my,50%),rgba(255,255,255,.13),transparent 45%);transition:opacity var(--ease,.2s);z-index:3;border-radius:16px}
.card:hover .sheen{opacity:1}
/* lightbox enhanced */
.lb-meta{color:#9aa0a8;font-size:12px;display:flex;gap:10px;flex-wrap:wrap;margin-top:2px}
.lb-meta b{color:var(--red2)}
.lb-prompt{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-left:2px solid var(--red);border-radius:8px;color:#c3c6cd;font-size:12px;line-height:1.6;padding:9px 12px;max-height:74px;overflow:auto;margin-top:6px}
.lb-prompt .pl{color:var(--red2);font-weight:700;margin-right:6px}
.lb-nav{position:fixed;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;width:46px;height:46px;border-radius:50%;font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.2s;z-index:2}
.lb-nav:hover{background:var(--red);border-color:var(--red);transform:translateY(-50%) scale(1.08)}
.lb-prev{left:18px}.lb-next{right:18px}
.lb-count{position:fixed;top:22px;left:50%;transform:translateX(-50%);color:#fff;font-size:12px;font-weight:700;letter-spacing:.06em;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:99px;padding:7px 15px;z-index:2}
.lb-progress{position:fixed;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.1);z-index:2}
.lb-progress i{display:block;height:100%;background:var(--red);transition:width .25s cubic-bezier(.22,1,.36,1);box-shadow:0 0 12px var(--red)}
/* command palette */
#cmd{position:fixed;inset:0;background:rgba(2,3,5,.8);backdrop-filter:blur(10px);display:none;align-items:flex-start;justify-content:center;z-index:115;padding:11vh 20px 20px;opacity:0;transition:opacity .18s}
#cmd.on{display:flex;opacity:1}
.cmdbox{width:min(680px,100%);background:#121418;border:1px solid var(--line2);border-radius:14px;box-shadow:0 30px 90px rgba(0,0,0,.7);overflow:hidden;transform:translateY(-12px);transition:transform .22s cubic-bezier(.22,1,.36,1)}
#cmd.on .cmdbox{transform:none}
.cmdinput{width:100%;background:transparent;border:none;border-bottom:1px solid var(--line);padding:17px 22px;font-size:18px;color:var(--ink);outline:none}
.cmdinput::placeholder{color:#5C5F67}
.cmdlist{max-height:48vh;overflow:auto;padding:8px}
.cmdrow{display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:8px;cursor:pointer;color:#c3c6cd}
.cmdrow:hover,.cmdrow.sel{background:var(--raised)}
.cmdrow img{width:56px;height:38px;object-fit:cover;border-radius:5px;flex:none;background:#111}
.cmdrow .cmd-tag{font-size:10px;font-weight:700;padding:3px 7px;border-radius:5px;background:rgba(255,77,46,.14);color:var(--red2);flex:none}
.cmdrow .cmd-text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
.cmdrow .cmd-text small{display:block;color:#5C5F67;font-size:10px;margin-top:2px}
.cmdrow .cmd-go{color:#5C5F67;font-size:11px}
.cmdhint{padding:9px 22px;border-top:1px solid var(--line);font-size:10px;color:#5C5F67;display:flex;gap:16px}
@media(max-width:720px){.hero{padding:26px 18px}.main{padding:14px 14px 36px}.stats{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}.meta{padding:10px}.title{font-size:13px}.scene{font-size:11px}.actions{display:none}.lb-nav{width:38px;height:38px;font-size:18px}.lb-prev{left:8px}.lb-next{right:8px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.lid.top{transform:translateY(-101%)}.lid.bot{transform:translateY(101%)}.eye-flash{opacity:0}}
</style>
</head>
<body>
<div class="bg-stage" aria-hidden="true">
<div class="eye-layer" id="eyeLayer"><div class="eye-img"></div></div>
<canvas id="stars"></canvas>
<div class="eye-scrim"></div>
<div class="vignette"></div>
<div class="eye-flash" id="eyeFlash"></div>
</div>
<div class="eye-curtain" id="eyeCurtain" aria-hidden="true">
<div class="lid top"></div><div class="lid bot"></div>
</div>
<button class="eye-replay" id="eyeReplay" title="重播睁眼动画">↻ 重播睁眼</button>
<header class="hero">
  <div class="wrap">
    <div class="eyebrow">Hongguo Short Drama / Visual Library</div>
    <h1>每一帧画面<br>都值得被<em>迭代</em>。</h1>
    <p>豆包 Seedream 5.5 出图 · 固定场景只换主体 · 所有迭代画面统一归档</p>
    <div class="stats">
      <div class="stat"><b id="s-total">0</b><span>入库画面</span></div>
      <div class="stat"><b id="s-subjects">0</b><span>主体</span></div>
      <div class="stat"><b id="s-scenes">0</b><span>场景</span></div>
      <div class="stat"><b id="s-today">0</b><span>今日新增</span></div>
    </div>
  </div>
</header>
<main class="main">
  <div class="hint"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;flex:none;margin-top:2px;color:var(--red)"><path d="M9 18h6M10 22h4M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 12 3.5a4.65 4.65 0 0 0-4.5 8c.76.76 1.23 1.52 1.41 2.5"/></svg><div>生图统一用 <b>Seedream 5.5</b>：<b>python promo/gen_image.py --tag A11_红狐 --subject "..."</b>，出图后自动入库。新图也可直接放进 <b>画面迭代库_收件箱</b>（可按场景建子目录），或运行 <b>python build_visual_library.py</b> 重建。</div></div>
  <section class="panel">
    <div class="toolbar">
      <div class="search search-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path></svg>
        <input id="q" type="search" placeholder="搜主体、编号、场景、文件名…">
        <span class="kbd" id="kbdHint">⌘ K</span>
      </div>
      <select id="scene"><option value="">全部场景</option></select>
      <select id="subject"><option value="">全部主体</option></select>
      <select id="model"><option value="">全部模型</option></select>
      <select id="sort">
        <option value="new">最新入库</option>
        <option value="old">最早入库</option>
        <option value="name">按编号</option>
      </select>
      <button class="act-btn primary" id="btn-add"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>新增</button>
      <button class="act-btn" id="btn-export"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>导出</button>
      <span class="mode-badge" id="mode">连接中…</span>
    </div>
    <div class="daterow">
      <b>日期</b>
      <input type="date" id="d-from"><span>至</span><input type="date" id="d-to">
      <button id="d-today">今天</button>
      <button id="d-week">近7天</button>
      <button id="d-month">近30天</button>
      <button id="d-clear">清除</button>
    </div>
    <div class="chips" id="chips"></div>
    <div class="note2"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>点卡片看大图 · <span class="kbd">/</span> 搜索 · <span class="kbd">N</span> 新增 · <span class="kbd">⌘K</span> 命令面板 · <span class="kbd">← →</span> 大图翻页 · <span class="kbd">Esc</span> 关闭</div>
  </section>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none">没有匹配的画面</div>
  <div class="footer" id="footer"></div>
</main>
<div class="lightbox" id="lb">
  <div class="lb-count" id="lb-count">IMAGE 01 / 166</div>
  <button class="lb-nav lb-prev" id="lb-prev" aria-label="上一张">‹</button>
  <button class="lb-nav lb-next" id="lb-next" aria-label="下一张">›</button>
  <button class="lb-close" id="lb-close" aria-label="关闭">×</button>
  <div class="lb-body">
    <img id="lb-img" alt="">
    <div class="lb-bar">
      <div class="lb-title" id="lb-title"></div>
      <div class="lb-btns">
        <button id="lb-copy-prompt">复制提示词</button>
        <button id="lb-copy">复制路径</button>
        <a id="lb-open" target="_blank">打开原图</a>
      </div>
    </div>
    <div class="lb-meta" id="lb-meta"></div>
    <div class="lb-prompt" id="lb-prompt"><span class="pl">提示词 /</span><span id="lb-prompt-text"></span></div>
  </div>
  <div class="lb-progress"><i id="lb-bar"></i></div>
</div>
<!-- Command palette -->
<div id="cmd" role="dialog" aria-label="命令面板">
<div class="cmdbox">
  <input class="cmdinput" id="cmd_input" placeholder="搜索画面：主体 / 场景 / 编号 / 提示词…" autocomplete="off">
  <div class="cmdlist" id="cmd_list"></div>
  <div class="cmdhint"><span>↑ ↓ 选择</span><span>↵ 打开大图</span><span>Esc 关闭</span></div>
</div>
</div>
<div class="toast" id="toast">已复制</div>
<div class="toast2" id="toast2"></div>
<div class="mask" id="mask" style="display:none"><div class="modal">
  <h3 id="m-title">新增画面</h3>
  <div class="sub">Visual Library / Editor</div>
  <label><span>图片路径（相对工作目录，文件需已存在）*</span><input id="f-path" placeholder="如 rabbit_iter/16x9/闹心花环_橘黄.jpg"></label>
  <div class="row">
    <label><span>标题</span><input id="f-title"></label>
    <label><span>编号</span><input id="f-tag"></label>
  </div>
  <div class="row">
    <label><span>主体</span><input id="f-subject"></label>
    <label><span>场景</span><input id="f-scene"></label>
  </div>
  <div class="row">
    <label><span>变体</span><input id="f-variant" placeholder="16:9 成图 / 收件箱 / 参考原图"></label>
    <label><span>线</span><input id="f-line"></label>
  </div>
  <div class="row">
    <label><span>模型</span><input id="f-model" placeholder="Seedream 5.5"></label>
    <label><span>日期</span><input id="f-date" type="date"></label>
  </div>
  <label><span>备注</span><input id="f-note"></label>
  <label><span>提示词</span><textarea id="f-prompt"></textarea></label>
  <div class="acts"><button class="act-btn" id="f-cancel">取消</button><button class="act-btn primary" id="f-save">保存</button></div>
</div></div>
<div class="mask" id="cmask" style="display:none"><div class="modal" style="width:min(420px,100%)">
  <h3>确认删除</h3>
  <p id="c-desc" style="font-size:14px;line-height:1.6;color:#444"></p>
  <div class="acts"><button class="act-btn" id="c-cancel">取消</button><button class="act-btn primary" id="c-ok" style="background:#dc2626;border-color:#dc2626">确认删除</button></div>
</div></div>
<script>
const DATA = __DATA__;
const grid = document.getElementById('grid');
const empty = document.getElementById('empty');
const chips = document.getElementById('chips');
const sceneSel = document.getElementById('scene');
const subjectSel = document.getElementById('subject');
const modelSel = document.getElementById('model');
const q = document.getElementById('q');
const sortSel = document.getElementById('sort');
const dFromEl = document.getElementById('d-from');
const dToEl = document.getElementById('d-to');
let activeType = 'all';
let current = [];
let dFromV = '', dToV = '';
let MODE = 'local', editId = null, delId = null;
const STAMP = '__STAMP__';
const $=id=>document.getElementById(id);
function dayStr(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
function daysAgo(n){const d=new Date();d.setDate(d.getDate()-n);return dayStr(d)}
function setDates(a,b){dFromV=a;dToV=b;dFromEl.value=a;dToEl.value=b;render()}
function toast2(m){const t=$('toast2');t.textContent=m;t.classList.add('on');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('on'),1800)}

/* ===== eye parallax + replay + starfield ===== */
(function(){
  const cv=document.getElementById('stars');if(!cv)return;
  const ctx=cv.getContext('2d'),au=document.getElementById('eyeLayer');
  const reduced=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  let W=0,H=0,dpr=1,stars=[],tx=0,ty=0,px=0,py=0;
  function fit(){
    dpr=Math.min(window.devicePixelRatio||1,2);
    W=window.innerWidth;H=window.innerHeight;
    cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+'px';cv.style.height=H+'px';
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const n=Math.min(160,Math.max(50,Math.floor(W*H/9000)));
    stars=Array.from({length:n},()=>({x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.3+.3,a:Math.random()*.55+.15,vy:Math.random()*.16+.03,tw:Math.random()*Math.PI*2,hue:Math.random()<.12?((Math.random()<.5)?'255,140,90':'150,190,255'):'255,255,255'}));
  }
  window.addEventListener('resize',fit);
  window.addEventListener('pointermove',e=>{tx=(e.clientX/W-.5);ty=(e.clientY/H-.5)},{passive:true});
  function frame(t){
    px+=(tx-px)*.04;py+=(ty-py)*.04;
    if(au)au.style.transform='translate('+(px*-26)+'px,'+(py*-18)+'px)';
    ctx.clearRect(0,0,W,H);
    for(const s of stars){
      if(!reduced){s.y-=s.vy;if(s.y<-3){s.y=H+3;s.x=Math.random()*W}}
      const a=s.a*(.65+.35*Math.sin(t*.0012+s.tw));
      const ox=px*s.r*14,oy=py*s.r*14;
      ctx.beginPath();ctx.arc(s.x+ox,s.y+oy,s.r,0,Math.PI*2);
      ctx.fillStyle='rgba('+s.hue+','+a.toFixed(3)+')';ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  fit();requestAnimationFrame(frame);
  const stage=document.getElementById('eyeCurtain'),btn=document.getElementById('eyeReplay');
  if(btn&&stage){
    btn.addEventListener('click',()=>{
      stage.classList.remove('lidClosing');void stage.offsetWidth;stage.classList.add('lidClosing');
      setTimeout(()=>{
        stage.classList.remove('lidClosing');void stage.offsetWidth;
        const fl=document.getElementById('eyeFlash');if(fl){fl.style.animation='none';void fl.offsetWidth;fl.style.animation=''}
      },540);
    });
  }
})();

function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function fmtSize(n){if(!n)return '';return n>1048576?(n/1048576).toFixed(1)+' MB':Math.round(n/1024)+' KB';}
function typeLabel(v){return v==='16:9 成图'?'16:9 成图':v==='参考原图'?'参考原图':v==='收件箱'?'收件箱':'原始出图';}
function typeClass(v){return v==='16:9 成图'?'v16':v==='收件箱'?'inbox':'raw';}

function render(){
  const term = q.value.trim().toLowerCase();
  let rows = DATA.items.filter(it=>{
    if(activeType!=='all' && it.variant!==activeType) return false;
    if(sceneSel.value && it.scene!==sceneSel.value) return false;
    if(subjectSel.value && it.subject!==subjectSel.value) return false;
    if(modelSel.value && (it.model||'')!==modelSel.value) return false;
    const day = (it.mtime||'').slice(0,10);
    if(dFromV && (!day || day<dFromV)) return false;
    if(dToV && (!day || day>dToV)) return false;
    if(term){
      const hay = [it.title,it.tag,it.subject,it.scene,it.path,it.variant,it.model,it.prompt].join(' ').toLowerCase();
      if(!hay.includes(term)) return false;
    }
    return true;
  });
  if(sortSel.value==='old') rows.sort((a,b)=>a.mtime.localeCompare(b.mtime));
  else if(sortSel.value==='name') rows.sort((a,b)=>(a.tag||'zz').localeCompare(b.tag||'zz',undefined,{numeric:true}));
  else rows.sort((a,b)=>b.mtime.localeCompare(a.mtime));
  current = rows;
  grid.innerHTML = rows.map((it,i)=>`
    <article class="card" data-i="${i}" data-id="${esc(it.id)}" style="animation-delay:${Math.min(i*26,650)}ms">
      <div class="sheen"></div>
      <div class="card-ops"><button data-act="edit">编辑</button><button data-act="del" class="del">删除</button></div>
      <span class="badge ${typeClass(it.variant)}">${esc(typeLabel(it.variant))}</span>
      <img class="thumb" loading="lazy" src="${esc(it.thumb)}" alt="${esc(it.title)}" onerror="this.src='${esc(it.path)}'">
      <div class="meta">
        <div class="title"><span>${esc(it.title)}</span><small>${esc(it.width&&it.height?it.width+'×'+it.height:'')}</small></div>
        <div class="scene" title="${esc(it.scene)}">${esc(it.scene)}</div>
        <div class="sub">${it.model?`<span class="tag model">${esc(it.model)}</span>`:''}<span class="tag">${esc(it.variant)}</span>${it.line?`<span class="tag">${esc(it.line)}线</span>`:''}<span class="tag">${esc(it.mtime.slice(0,10))}</span><span class="tag">${fmtSize(it.size)}</span></div>
        <div class="actions">
          <button data-copy="${esc(it.path)}">复制路径</button>
          <a href="${esc(it.path)}" target="_blank" onclick="event.stopPropagation()">原图</a>
        </div>
      </div>
    </article>`).join('');
  empty.style.display = rows.length ? 'none' : 'block';
  grid.querySelectorAll('.card').forEach(card=>card.addEventListener('click',e=>{
    if(e.target.closest('.card-ops')||e.target.closest('[data-copy]')||e.target.closest('a')) return;
    openLb(Number(card.dataset.i));
  }));
  grid.querySelectorAll('[data-copy]').forEach(btn=>btn.addEventListener('click',e=>{e.stopPropagation();copyText(btn.dataset.copy);}));
  grid.querySelectorAll('.card-ops button').forEach(btn=>btn.addEventListener('click',e=>{
    e.stopPropagation();
    const it=current[Number(btn.closest('.card').dataset.i)];if(!it)return;
    if(btn.dataset.act==='edit') openForm(it);
    else { delId=it.id; $('c-desc').textContent='确定从画面库移除这张图？\n\n'+it.title+'\n\n（只从库中移除，不会删除磁盘上的图片文件；重建后仍保持移除）'; $('cmask').style.display='flex'; }
  }));
  /* clear entrance animation so inline tilt transform can take over */
  grid.querySelectorAll('.card').forEach(card=>{
    card.addEventListener('animationend',ev=>{
      if(ev.animationName==='cardIn')card.style.animation='none';
    },{once:true});
  });
  bindTilt();
}
/* 3D tilt: card follows cursor + sheen highlight */
let _tiltBound=false;
function bindTilt(){
  if(window.matchMedia('(pointer:coarse)').matches||window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;
  if(_tiltBound) return; _tiltBound=true;
  grid.addEventListener('pointermove',e=>{
    const card=e.target.closest('.card');if(!card)return;
    const b=card.getBoundingClientRect();
    const rx=((e.clientY-b.top)/b.height-.5)*-7, ry=((e.clientX-b.left)/b.width-.5)*7;
    card.style.transform='perspective(700px) rotateX('+rx.toFixed(2)+'deg) rotateY('+ry.toFixed(2)+'deg)';
    card.style.setProperty('--mx',(((e.clientX-b.left)/b.width)*100).toFixed(1)+'%');
    card.style.setProperty('--my',(((e.clientY-b.top)/b.height)*100).toFixed(1)+'%');
  });
  grid.addEventListener('pointerleave',()=>{
    grid.querySelectorAll('.card').forEach(c=>c.style.transform='');
  },true);
  grid.addEventListener('pointerout',e=>{
    const card=e.target.closest('.card');if(card&&!card.contains(e.relatedTarget))card.style.transform='';
  });
}
function openLb(i){
  const it = current[i]; if(!it) return;
  document.getElementById('lb-img').src = it.path;
  document.getElementById('lb-img').alt = it.title;
  document.getElementById('lb-title').textContent = it.title;
  document.getElementById('lb-open').href = it.path;
  const bits=[];
  if(it.scene)bits.push('场景 <b>'+esc(it.scene)+'</b>');
  if(it.subject)bits.push('主体 <b>'+esc(it.subject)+'</b>');
  if(it.variant)bits.push(esc(it.variant));
  if(it.model)bits.push('<b>'+esc(it.model)+'</b>');
  if(it.width&&it.height)bits.push(it.width+'×'+it.height);
  if(it.mtime)bits.push(esc(it.mtime.slice(0,10)));
  document.getElementById('lb-meta').innerHTML=bits.join(' · ');
  const pt=(it.prompt||'').trim();
  document.getElementById('lb-prompt').style.display=pt?'block':'none';
  document.getElementById('lb-prompt-text').textContent=pt;
  document.getElementById('lb-copy-prompt').style.display=pt?'inline-flex':'none';
  const lb = document.getElementById('lb'); lb.classList.add('on'); lb.dataset.i = i;
  updateLbNav();
}
function updateLbNav(){
  const lb=document.getElementById('lb'),i=Number(lb.dataset.i||0),n=current.length;
  document.getElementById('lb-count').textContent='IMAGE '+String(i+1).padStart(2,'0')+' / '+String(n).padStart(2,'0');
  document.getElementById('lb-bar').style.width=((i+1)/n*100).toFixed(2)+'%';
}
function lbStep(dir){
  const lb=document.getElementById('lb');if(!lb.classList.contains('on'))return;
  const n=current.length;if(!n)return;
  let i=(Number(lb.dataset.i||0)+dir+n)%n;
  lb.dataset.i=i;openLb(i);
}
function closeLb(){document.getElementById('lb').classList.remove('on');}
function copyText(t){
  const done=()=>{const el=document.getElementById('toast');el.textContent='已复制：'+t;el.classList.add('on');setTimeout(()=>el.classList.remove('on'),1600);};
  if(navigator.clipboard && window.isSecureContext){navigator.clipboard.writeText(t).then(done).catch(()=>fallbackCopy(t,done));}
  else fallbackCopy(t,done);
}
function fallbackCopy(t,done){const ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(e){}ta.remove();}
document.getElementById('lb-close').addEventListener('click',closeLb);
document.getElementById('lb').addEventListener('click',e=>{if(e.target.id==='lb')closeLb();});
document.getElementById('lb-copy').addEventListener('click',()=>{const it=current[Number(document.getElementById('lb').dataset.i)];if(it)copyText(it.path);});
document.getElementById('lb-copy-prompt').addEventListener('click',()=>{const it=current[Number(document.getElementById('lb').dataset.i)];if(it&&it.prompt)copyText(it.prompt);});
document.getElementById('lb-prev').addEventListener('click',e=>{e.stopPropagation();lbStep(-1)});
document.getElementById('lb-next').addEventListener('click',e=>{e.stopPropagation();lbStep(1)});

/* ---- command palette ---- */
const cmd=document.getElementById('cmd'),cmdInput=document.getElementById('cmd_input'),cmdList=document.getElementById('cmd_list');
let cmdResults=[],cmdSel=0;
function renderCmd(){
  const kw=cmdInput.value.trim().toLowerCase();
  cmdResults=DATA.items.filter(it=>{
    if(!kw)return true;
    return [it.title,it.tag,it.subject,it.scene,it.variant,it.model,it.prompt,it.path].join(' ').toLowerCase().includes(kw);
  }).slice(0,40);
  if(cmdSel>=cmdResults.length)cmdSel=0;
  cmdList.innerHTML=cmdResults.map((it,i)=>`<div class="cmdrow ${i===cmdSel?'sel':''}" data-i="${i}"><img src="${esc(it.thumb)}" alt=""><span class="cmd-tag">${esc(it.variant==='16:9 成图'?'成图':it.variant)}</span><span class="cmd-text">${esc(it.title)}<small>${esc(it.scene)} · ${esc(it.subject||'')}</small></span><span class="cmd-go">↵</span></div>`).join('');
  cmdList.querySelectorAll('.cmdrow').forEach(r=>{
    r.addEventListener('mouseenter',()=>{cmdSel=Number(r.dataset.i);cmdList.querySelectorAll('.cmdrow').forEach(x=>x.classList.toggle('sel',x===r))});
    r.addEventListener('click',()=>openCmdSel());
  });
}
function openCmd(){cmd.classList.add('on');cmdInput.value='';cmdSel=0;renderCmd();setTimeout(()=>cmdInput.focus(),30)}
function closeCmd(){cmd.classList.remove('on')}
function openCmdSel(){
  const it=cmdResults[cmdSel];if(!it)return;
  closeCmd();
  const i=current.findIndex(x=>x.id===it.id);
  if(i>=0){openLb(i)}else{DATA.items=DATA.items;activeType='all';q.value='';sceneSel.value='';subjectSel.value='';modelSel.value='';setDates('','');render();const j=current.findIndex(x=>x.id===it.id);if(j>=0)openLb(j)}
}
cmdInput.addEventListener('input',()=>{cmdSel=0;renderCmd()});
cmd.addEventListener('click',e=>{if(e.target===cmd)closeCmd()});

/* ---- global keyboard shortcuts ---- */
document.addEventListener('keydown',e=>{
  const typing=/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if(e.key==='Escape'){
    if(cmd.classList.contains('on')){closeCmd();return}
    if(document.getElementById('lb').classList.contains('on')){closeLb();return}
    if(typing){document.activeElement.blur();return}
    $('mask').style.display='none';$('cmask').style.display='none';return;
  }
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();cmd.classList.contains('on')?closeCmd():openCmd();return}
  if(cmd.classList.contains('on')){
    if(e.key==='ArrowDown'){e.preventDefault();cmdSel=Math.min(cmdSel+1,cmdResults.length-1);renderCmd();cmdList.querySelector('.cmdrow.sel')?.scrollIntoView({block:'nearest'});return}
    if(e.key==='ArrowUp'){e.preventDefault();cmdSel=Math.max(cmdSel-1,0);renderCmd();cmdList.querySelector('.cmdrow.sel')?.scrollIntoView({block:'nearest'});return}
    if(e.key==='Enter'){e.preventDefault();openCmdSel();return}
    return;
  }
  if(typing)return;
  if(document.getElementById('lb').classList.contains('on')){
    if(e.key==='ArrowLeft'){e.preventDefault();lbStep(-1)}
    if(e.key==='ArrowRight'){e.preventDefault();lbStep(1)}
    return;
  }
  if(e.key==='/'){e.preventDefault();q.focus();return}
  if(e.key.toLowerCase()==='n'){e.preventDefault();openForm(null);return}
});
if(!window.matchMedia('(pointer:coarse)').matches)$('kbdHint').textContent='⌘ K';
q.addEventListener('input',render);
sceneSel.addEventListener('change',render);
subjectSel.addEventListener('change',render);
modelSel.addEventListener('change',render);
sortSel.addEventListener('change',render);
dFromEl.addEventListener('change',()=>{dFromV=dFromEl.value;render()});
dToEl.addEventListener('change',()=>{dToV=dToEl.value;render()});
document.getElementById('d-today').addEventListener('click',()=>setDates(dayStr(new Date()),dayStr(new Date())));
document.getElementById('d-week').addEventListener('click',()=>setDates(daysAgo(6),''));
document.getElementById('d-month').addEventListener('click',()=>setDates(daysAgo(29),''));
document.getElementById('d-clear').addEventListener('click',()=>setDates('',''));
document.getElementById('footer').innerHTML = `更新于 ${esc(DATA.generated_at.replace('T',' '))} · 生图模型：Seedream 5.5 · 库文件：画面迭代库.json · 收件箱：画面迭代库_收件箱/ · 重建：python build_visual_library.py`;

function openForm(it){
  editId = it ? it.id : null;
  $('m-title').textContent = it ? '编辑画面' : '新增画面';
  const f={path:it?it.path:'',title:it?it.title:'',tag:it?it.tag:'',subject:it?it.subject:'',
    scene:it?it.scene:'',variant:it?it.variant:'16:9 成图',line:it?it.line:'',
    model:it?(it.model||''):'Seedream 5.5',date:it?(it.mtime||'').slice(0,10):dayStr(new Date()),
    note:it?(it.note||''):'',prompt:it?(it.prompt||''):''};
  for(const k in f){const el=$('f-'+k); if(el) el.value=f[k];}
  $('f-path').disabled = !!it;
  $('mask').style.display='flex';
}
function payload(){
  return {path:$('f-path').value.trim(),title:$('f-title').value.trim(),tag:$('f-tag').value.trim(),
    subject:$('f-subject').value.trim(),scene:$('f-scene').value.trim(),variant:$('f-variant').value.trim(),
    line:$('f-line').value.trim(),model:$('f-model').value.trim(),date:$('f-date').value,
    note:$('f-note').value.trim(),prompt:$('f-prompt').value.trim()};
}
function saveLocal(){
  try{localStorage.setItem('hg_visual_lib',JSON.stringify({stamp:STAMP,items:DATA.items}));}catch(e){}
}
async function saveForm(){
  const p=payload();
  if(!editId && !p.path){toast2('图片路径不能为空');return;}
  try{
    if(MODE==='api'){
      const url=editId?('/api/items/'+encodeURIComponent(editId)):'/api/items';
      const r=await fetch(url,{method:editId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
      const j=await r.json(); if(!j.ok) throw new Error(j.error||'保存失败');
      const fresh=await (await fetch('/api/items',{cache:'no-store'})).json();
      DATA=fresh;
    }else{
      if(editId){const i=DATA.items.findIndex(x=>x.id===editId);if(i>=0)Object.assign(DATA.items[i],p);}
      else {DATA.items.unshift({id:'manual_'+Date.now(),...p,thumb:p.path,path:p.path,sources:[p.path],size:0});}
      DATA.total=DATA.items.length; saveLocal();
    }
    $('mask').style.display='none'; buildUI(); render(); toast2(editId?'已修改':'已新增');
  }catch(e){toast2('保存失败：'+e.message)}
}
async function doDel(){
  try{
    if(MODE==='api'){
      const r=await fetch('/api/items/'+encodeURIComponent(delId),{method:'DELETE'});
      const j=await r.json(); if(!j.ok) throw new Error(j.error||'删除失败');
      const fresh=await (await fetch('/api/items',{cache:'no-store'})).json(); DATA=fresh;
    }else{
      DATA.items=DATA.items.filter(x=>x.id!==delId); DATA.total=DATA.items.length; saveLocal();
    }
    $('cmask').style.display='none'; buildUI(); render(); toast2('已删除（仅从库中移除）');
  }catch(e){toast2('删除失败：'+e.message)}
}
function buildUI(){
  $('s-total').textContent=DATA.total;
  $('s-subjects').textContent=new Set(DATA.items.map(x=>x.subject).filter(Boolean)).size;
  $('s-scenes').textContent=new Set(DATA.items.map(x=>x.scene).filter(Boolean)).size;
  $('s-today').textContent=DATA.items.filter(x=>(x.mtime||'').slice(0,10)===dayStr(new Date())).length;
  const scenes=[...new Set(DATA.items.map(x=>x.scene).filter(Boolean))].sort();
  const subjects=[...new Set(DATA.items.map(x=>x.subject).filter(Boolean))].sort();
  const models=[...new Set(DATA.items.map(x=>x.model).filter(Boolean))].sort();
  const fill=(el,opts)=>{const v=el.value;el.innerHTML='<option value="">全部</option>'+opts.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join('');el.value=v;};
  fill($('scene'),scenes);fill($('subject'),subjects);fill($('model'),models);
  const types=['all',...new Set(DATA.items.map(x=>x.variant))];
  chips.innerHTML=types.map(t=>{
    const n=t==='all'?DATA.items.length:DATA.items.filter(x=>x.variant===t).length;
    return `<button class="chip ${t===activeType?'on':''}" data-t="${esc(t)}">${t==='all'?'全部':esc(t)}<small>${n}</small></button>`;
  }).join('');
  chips.querySelectorAll('.chip').forEach(ch=>ch.addEventListener('click',()=>{activeType=ch.dataset.t;chips.querySelectorAll('.chip').forEach(x=>x.classList.toggle('on',x===ch));render();}));
}
$('btn-add').onclick=()=>openForm(null);
$('f-cancel').onclick=()=>$('mask').style.display='none';
$('f-save').onclick=saveForm;
$('c-cancel').onclick=()=>$('cmask').style.display='none';
$('c-ok').onclick=doDel;
$('btn-export').onclick=()=>{
  const blob=new Blob([JSON.stringify(DATA,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='画面迭代库_当前.json';a.click();URL.revokeObjectURL(a.href);toast2('已导出');
};

async function boot(){
  try{
    const r=await fetch('/api/ping',{cache:'no-store'});
    if(r.ok&&(await r.json()).ok){
      MODE='api';
      DATA=await (await fetch('/api/items',{cache:'no-store'})).json();
    }
  }catch(e){}
  if(MODE==='local'){
    try{
      const s=JSON.parse(localStorage.getItem('hg_visual_lib')||'null');
      if(s&&s.stamp===STAMP)DATA.items=s.items,DATA.total=s.items.length;
      else localStorage.removeItem('hg_visual_lib');
    }catch(e){}
  }
  const m=$('mode');m.textContent=MODE==='api'?'已连接 · 自动存库':'离线 · 存浏览器';m.className='mode-badge '+MODE;
  buildUI();render();
  /* number roll */
  if(!window.matchMedia('(prefers-reduced-motion:reduce)').matches){
    ['s-total','s-subjects','s-scenes','s-today'].forEach(id=>{
      const el=$(id),target=+el.textContent||0;let start=null;
      function step(ts){if(!start)start=ts;const p=Math.min((ts-start)/900,1);const e=1-Math.pow(1-p,3);el.textContent=Math.round(target*e);if(p<1)requestAnimationFrame(step);else el.textContent=target}
      el.textContent='0';requestAnimationFrame(step);
    });
  }
}
boot();
</script>
</body>
</html>'''
    import base64 as _b64
    _eye = ROOT / 'assets' / 'eyes_bg.jpg'
    _eye_url = ('url("data:image/jpeg;base64,' + _b64.b64encode(_eye.read_bytes()).decode() + '")') if _eye.exists() else 'none'
    return (template
            .replace('__EYE_URL__', _eye_url)
            .replace('__DATA__', payload)
            .replace('__TOTAL__', str(data['total']))
            .replace('__STAMP__', datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')))


def rebuild():
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    INBOX.mkdir(parents=True, exist_ok=True)
    entries = apply_override(collect())
    data = build_data(entries)
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    HTML_PATH.write_text(render_html(data), encoding='utf-8')
    print('visual library: %d items, %d scenes, %d today' % (data['total'], len(data['scenes']), data['today_count']))
    print('  HTML:', HTML_PATH)
    print('  JSON:', JSON_PATH)
    return data


def signature():
    parts = []
    for _, directory, _, _, _, recursive in SOURCES:
        if not directory.exists():
            continue
        files = iter_source_files('x', directory, recursive)
        for p in files:
            try:
                st = p.stat()
                parts.append('%s|%d|%d' % (p, st.st_mtime_ns, st.st_size))
            except OSError:
                pass
    return hashlib.sha1('\n'.join(parts).encode('utf-8', 'ignore')).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--watch', action='store_true', help='每20秒检测一次，有新图自动重建')
    args = ap.parse_args()
    rebuild()
    if not args.watch:
        return
    last = signature()
    print('watching for new images... (Ctrl+C to stop)')
    while True:
        time.sleep(20)
        now = signature()
        if now != last:
            last = now
            print('change detected:', time.strftime('%H:%M:%S'))
            try:
                rebuild()
            except Exception as e:
                print('rebuild failed:', e)


if __name__ == '__main__':
    main()
