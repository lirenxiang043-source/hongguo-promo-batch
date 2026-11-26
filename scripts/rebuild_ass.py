#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 subs_<tag>.json 重新生成严格标黄的 ASS：
只在字幕明确出现完整「红果短剧」四字时标黄放大；单独「短剧」/口误「红果短期」不标黄。
logo 也只在同样条件出现（见 render_v2.py），保证标黄与 logo 同步。
用法: python rebuild_ass.py 01 [02 03 ...]
"""
import json
import os
import pathlib
import sys

BASE = pathlib.Path(os.environ.get('HGP_WORK') or pathlib.Path.cwd())
CJK_YELLOW = r'{\c&H0000FFFF&\fs52}'
CJK_RESET = r'{\c&H00FFFFFF&\fs44}'
# 右上角固定免责声明小字
DISCLAIMER = '*内容由ai生成 纯属虚构 请勿代入现实*'
DISCLAIM_END = 15.05


def fmt(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return '%d:%02d:%05.2f' % (h, m, s)


def decorate(text):
    # 严格：完整「红果短剧」或「红果漫剧」才标黄放大
    for word in ('红果短剧', '红果漫剧'):
        if word in text:
            return text.replace(word, CJK_YELLOW + word + CJK_RESET)
    return text


def main(tag):
    segs = json.loads((BASE / ('subs_%s.json' % tag)).read_text(encoding='utf-8'))
    lines = [
        '[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1280', 'PlayResY: 720',
        'WrapStyle: 2', 'ScaledBorderAndShadow: yes', '',
        '[V4+ Styles]',
        'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding',
        'Style: Default,Microsoft YaHei,44,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,1,2,40,40,36,1',
        # 右上角小字：Alignment=9(右上), 字号22, 白色描边, 靠右上留边
        'Style: Note,Microsoft YaHei,18,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1.5,0,9,22,22,20,1',
        '', '[Events]',
        'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text',
    ]
    for s in segs:
        lines.append('Dialogue: 0,%s,%s,Default,,0,0,0,,%s' % (
            fmt(s['start']), fmt(s['end']), decorate(s['text'])))
    # 右上角免责声明，贯穿全程（放在 Layer 0，不与主字幕抢占同一行）
    lines.append('Dialogue: 0,0:00:00.00,%s,Note,,0,0,0,,%s' % (fmt(DISCLAIM_END), DISCLAIMER))
    (BASE / ('subs_%s.ass' % tag)).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('rebuilt subs_%s.ass (%d lines)' % (tag, len(segs)))


if __name__ == '__main__':
    for t in sys.argv[1:]:
        main(t)
