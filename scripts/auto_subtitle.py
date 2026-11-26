#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从整段转写文本自动生成字幕 + 语义 meta：
   python auto_subtitle.py <tag> "<整段转写文本>" <duration>
按标点分句，按字符数比例分配时间，标黄品牌词，标注 brand/drama/novel 贴图时段。
"""
import json
import os
import re
import sys
import pathlib

BASE = pathlib.Path(os.environ.get('HGP_WORK') or pathlib.Path.cwd())
CJK_YELLOW = r'{\c&H0000FFFF&\fs52}'
CJK_RESET = r'{\c&H00FFFFFF&\fs44}'


def fmt(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return '%d:%02d:%05.2f' % (h, m, s)


def split_sentences(text):
    parts = [p for p in re.findall(r'[^，。！？]+[，。！？]?', text) if p.strip()]
    merged = []
    for p in parts:
        clean = re.sub(r'[，。！？、]$', '', p.strip())
        if merged and len(clean) < 3:
            merged[-1] = merged[-1].rstrip('，。！？、') + '，' + clean
        else:
            merged.append(clean)
    return merged


BRAND_RE = re.compile(r'红果(?:短剧|漫剧)|短剧|漫剧')


def classify(text):
    if BRAND_RE.search(text) and not re.search(r'电影|电视剧|小说', text):
        return ['brand']
    tags = []
    if re.search(r'电影|电视剧', text) and not re.search(r'小说', text):
        tags.append('drama')
    if re.search(r'小说', text):
        tags.append('novel')
    return tags


def decorate(text):
    if '电影' in text or '电视剧' in text or '小说' in text:
        return text
    m = BRAND_RE.search(text)
    if m:
        word = m.group(0)
        return text[:m.start()] + CJK_YELLOW + word + CJK_RESET + text[m.end():]
    return text


def main():
    tag = sys.argv[1]
    text = sys.argv[2]
    total = float(sys.argv[3])
    parts = split_sentences(text)
    weights = [len(p) for p in parts]
    tw = sum(weights) or 1
    out = []
    cur = 0.0
    for p, w in zip(parts, weights):
        nxt = cur + total * w / tw
        out.append({'start': round(cur, 3), 'end': round(nxt, 3), 'text': p})
        cur = nxt
    ass = ['[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1280', 'PlayResY: 720',
           'WrapStyle: 2', 'ScaledBorderAndShadow: yes', '',
           '[V4+ Styles]',
           'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding',
           'Style: Default,Microsoft YaHei,44,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,1,2,40,40,36,1',
           '', '[Events]',
           'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text']
    meta = {'brand': [], 'drama': [], 'novel': []}
    brand_used = False
    for s in out:
        tags = classify(s['text'])
        text = s['text']
        if 'brand' in tags:
            if brand_used:
                tags = [t for t in tags if t != 'brand']  # 只保留第一个品牌句标黄+logo
            else:
                brand_used = True
        # 只有被确认为品牌句的那一行才标黄
        display = decorate(text) if 'brand' in tags else text
        ass.append('Dialogue: 0,%s,%s,Default,,0,0,0,,%s' % (fmt(s['start']), fmt(s['end']), display))
        for t in tags:
            meta[t].append({'start': s['start'], 'end': s['end'], 'text': s['text']})
    (BASE / ('subs_%s.ass' % tag)).write_text('\n'.join(ass) + '\n', encoding='utf-8')
    (BASE / ('meta_%s.json' % tag)).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    (BASE / ('subs_%s.json' % tag)).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print('TOTAL %d sent, meta:' % len(out))
    print(json.dumps({k: [(round(x['start'],2), round(x['end'],2), x['text']) for x in v] for k,v in meta.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
