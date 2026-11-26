#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把三批抓取的真实话术 + 已有优化文案，聚合成统一文案库（JSON + HTML）。"""
import json
import re
import datetime
import pathlib
import html

BASE = pathlib.Path(__file__).resolve().parent

# ---------- 分类白名单：文案库只允许这 5 类入库 ----------
# 抓取话术/优化话术/口播卡片/投放话术/蹭话题内容一律不入，脚本层强制过滤。
ALLOWED_CATS = {'短剧口播原版', '漫剧口播原版', '口播迭代', '口播成片', '多功能综述原版'}
CAT_ALIAS = {'口播·原版': '漫剧口播原版', '口播·迭代': '口播迭代', '口播·成片': '口播成片'}

def norm_cat(c):
    return CAT_ALIAS.get(c, c)

# ---------- 1. 从抓取数据提取真实推广话术 ----------
def clean_desc(desc):
    s = desc or ''
    s = re.sub(r'#\S+', '', s)              # 话题标签
    s = re.sub(r'\d{4}-[A-Z]{2,4}-', '', s) # 素材编号
    s = re.sub(r'https?://\S+', '', s)      # 链接
    s = re.sub(r'@\S+', '', s)              # @提及
    s = re.sub(r'[【】《》\[\]「」]', '', s)
    return s.strip(' -—·,，。.')

# 卖点词白名单：命中才认为是推广话术，排除剧情标题/教程/财经
SELL = ('免费','全集','连播','续播','点开','点一下','点击','刷','追','看不完','停不下来',
        '资源','题材','更新','高清','流畅','会员','解锁','剧荒','上头','放松','一口气',
        '大结局','不愁','随便','海量','超多','不用','推荐','短剧','漫剧','搭子')
BAD = ('怎么赚钱','靠什么赚钱','教程','拆解','教学','安装','下载教程','怎么用','是什么',
       '推荐榜','排行榜','起诉','维权','回应','行业','收益','万播','崩的','开打','新闻',
       '总结和锐评','锐评','Minecraft','当我知道','当你以','你全责','神离我们','扛起了道德',
       '表情五官','全在乱飞','涨知识','时间杀手','付费模式','网友','评论','前夫','离婚',
       '重生','穿越护母','签到','系统','马甲','千金','剧情解说','第几集','全在乱飞')

def cat_of(text):
    if any(k in text for k in ('免费','会员','解锁','不用钱','不充')): return '免费无套路'
    if any(k in text for k in ('连播','续播','接着播','自动','点一下','点开','点击屏幕')): return '连播功能'
    if any(k in text for k in ('看不完','停不下来','海量','超多','不愁','多到','资源多','剧荒')): return '量感丰富'
    if any(k in text for k in ('上头','放松','解压','班味','通宵','凌晨')): return '情绪钩子'
    if any(k in text for k in ('通勤','午休','睡前','下班','等外卖','碎片时间')): return '场景化'
    if any(k in text for k in ('题材','修仙','逆袭','穿越','风格','类型')): return '题材齐全'
    if any(k in text for k in ('高清','流畅','画质')): return '体验画质'
    return '其他话术'

# 抓取三批
files = ['douyin_awemes_full.json', 'douyin_awemes_more.json', 'douyin_awemes_hot.json']
by = {}
for fn in files:
    try:
        for a in json.load(open(BASE / fn, encoding='utf-8')):
            k = a.get('id')
            if k and k not in by:
                by[k] = a
    except FileNotFoundError:
        pass

real = []
seen = set()
for a in by.values():
    desc = a.get('desc') or ''
    text = clean_desc(desc)
    if not (6 <= len(text) <= 40):
        continue
    if not any(k in desc for k in ('红果', '短剧', '漫剧')):
        continue
    if any(b in text for b in BAD):
        continue
    if not any(k in text for k in SELL):
        continue
    key = text
    if key in seen:
        continue
    seen.add(key)
    ts = a.get('create_time')
    dt = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts else ''
    real.append({
        'text': text,
        'cat': cat_of(text),
        'digg': a.get('digg_count', 0),
        'author': (a.get('author') or {}).get('nickname', '') if isinstance(a.get('author'), dict) else str(a.get('author') or ''),
        'date': dt,
        'vid': a.get('id', ''),
        'source': '抓取',
    })
real.sort(key=lambda x: -x['digg'])

# ---------- 2. 已有优化话术 ----------
opt = []
try:
    lines = (BASE / '优化话术库.txt').read_text(encoding='utf-8').splitlines()
    cur_dir = ''
    for i, ln in enumerate(lines):
        m = re.match(r'◆ (方向\S+?)(?:（|$)', ln)
        if m:
            cur_dir = m.group(1)
        m2 = re.match(r'\s*\d+\.\s+(.+?)（(\d+)\s*字）', ln)
        if m2:
            txt = m2.group(1).strip()
            # 下一行"手法："作为备注
            note = ''
            if i + 1 < len(lines) and lines[i+1].strip().startswith('手法：'):
                note = lines[i+1].strip().replace('手法：', '')
            opt.append({
                'text': txt,
                'cat': cat_of(txt),
                'digg': 0,
                'author': '优化迭代',
                'date': '2026-11-21',
                'vid': '',
                'source': '优化 · ' + cur_dir,
                'note': note,
            })
except FileNotFoundError:
    pass

# ---------- 3. 口播文案（原版 + 7 版 + slots）----------
oral = []
try:
    d = json.loads((BASE / '口播文案_优化版.json').read_text(encoding='utf-8'))
    for o in d.get('originals', []):
        oral.append({
            'text': o['text'], 'cat': '漫剧口播原版', 'digg': o.get('digg', 0),
            'author': o.get('author', ''), 'date': o.get('date') or '2026-11-21',
            'vid': o.get('vid', ''),
            'source': '口播原版 %s (%s)' % (o.get('tag',''), o.get('style','')),
        })
    for v in d.get('versions', []):
        oral.append({
            'text': ' '.join(v['lines']), 'cat': '口播迭代', 'digg': 0,
            'author': '优化迭代', 'date': v.get('date') or '2026-11-21', 'vid': '',
            'source': '口播 %s %s' % (v.get('no',''), v.get('name','')),
            'note': v.get('why', ''), 'name': v.get('name', ''),
        })
    for s in d.get('slots', []):
        for t in s['items']:
            oral.append({
                'text': t, 'cat': '口播·卡片', 'digg': 0, 'author': '优化迭代',
                'date': '', 'vid': '', 'source': s['name'], 'note': s.get('sub',''),
            })
except FileNotFoundError:
    pass

# ---------- 4. 每日新增（自写文案 / 成片口播，持续累积）----------
added = []
try:
    d = json.loads((BASE / '文案库_新增.json').read_text(encoding='utf-8'))
    for o in d:
        text = (o.get('text') or '').strip()
        if not text:
            continue
        added.append({
            'text': text,
            'cat': o.get('cat') or '口播·成片',
            'digg': o.get('digg', 0),
            'author': o.get('author') or '自写',
            'date': o.get('date') or datetime.date.today().isoformat(),
            'vid': o.get('vid', ''),
            'source': o.get('source') or '每日新增',
            'note': o.get('note', ''),
        })
except FileNotFoundError:
    pass

all_items = real + opt + oral + added
# 白名单过滤：只保留 5 类口播，其余分类（抓取/优化/卡片/投放/其他话术）一律不入
all_items = [it for it in all_items if norm_cat(it.get('cat')) in ALLOWED_CATS]
for it in all_items:
    it['cat'] = norm_cat(it['cat'])
# 全量去重（按 text）
uniq = {}
for it in all_items:
    k = re.sub(r'\s+', '', it['text'])
    if k not in uniq:
        uniq[k] = it
items = list(uniq.values())

library = {
    'built': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'stats': {
        'total': len(items),
        'real': len(real),
        'optimized': len(opt),
        'oral': len(oral) + len(added),
        'cats': {},
    },
    'items': items,
}
for it in items:
    library['stats']['cats'][it['cat']] = library['stats']['cats'].get(it['cat'], 0) + 1

(BASE / '文案库.json').write_text(json.dumps(library, ensure_ascii=False, indent=1), encoding='utf-8')
print('文案库条目', len(items))
print('来源统计 抓取', len(real), '优化', len(opt), '口播', len(oral), '每日新增', len(added))
for k, v in sorted(library['stats']['cats'].items(), key=lambda x: -x[1]):
    print('  ', k, v)
