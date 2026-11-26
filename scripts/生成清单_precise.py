# -*- coding: utf-8 -*-
"""精准版：带官方投放编号的红果推广素材 -> 分享口令清单（HTML + TXT + CSV）。"""
import os, json, html, csv, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PRECISE = os.path.join(BASE, "filtered_precise.json")
SHORT = os.path.join(BASE, "links_precise.json")

data = {a["id"]: a for a in json.load(open(PRECISE, encoding="utf-8"))}
short = json.load(open(SHORT, encoding="utf-8"))


def fmt_count(n):
    if not n:
        return "0"
    n = int(n)
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


items = []
for vid, link in short.items():
    a = data.get(vid)
    if not a:
        continue
    tpl = (a.get("share_link_desc") or "").strip()
    if "%s" in tpl:
        text = tpl.replace("%s", link)
    else:
        text = f"{tpl} {link} 复制此链接，打开Dou音搜索，直接观看视频！"
    items.append({
        "id": vid, "text": text, "desc": a.get("desc", ""),
        "author": a.get("author", ""), "digg": a.get("digg_count") or 0,
        "comment": a.get("comment_count") or 0, "share": a.get("share_count") or 0,
        "link": link, "create": a.get("create_time"),
    })

items.sort(key=lambda x: x["digg"], reverse=True)
print("口令条数:", len(items))

# TXT
with open(os.path.join(BASE, "红果短剧推广口令_精准.txt"), "w", encoding="utf-8") as f:
    f.write("红果短剧推广 · 官方投放素材分享口令（复制整行，打开抖音即可观看）\n")
    f.write("筛选口径：带官方投放编号 + 赞>=100 + 11月投放\n")
    f.write("=" * 60 + "\n\n")
    for i, it in enumerate(items, 1):
        f.write(f"[{i}] {it['text']}\n\n")

# CSV
with open(os.path.join(BASE, "红果短剧推广口令_精准.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["序号", "官方投放编号/话术", "分享口令全文", "发布账号", "点赞", "评论", "转发", "短链", "视频ID"])
    for i, it in enumerate(items, 1):
        w.writerow([i, it["desc"], it["text"], it["author"], it["digg"],
                    it["comment"], it["share"], it["link"], it["id"]])

# HTML
cards = []
for i, it in enumerate(items, 1):
    safe = html.escape(it["text"])
    date = ""
    if it["create"]:
        try:
            date = datetime.datetime.fromtimestamp(it["create"]).strftime("%Y-%m-%d")
        except Exception:
            pass
    cards.append(f'''<div class="card">
  <div class="card-head">
    <span class="num">#{i}</span>
    <span class="author">{html.escape(it['author'] or '抖音用户')}</span>
    <span class="stats">赞 {fmt_count(it['digg'])} · 评 {fmt_count(it['comment'])} · 转 {fmt_count(it['share'])}</span>
    <span class="date">{date}</span>
  </div>
  <div class="code">{html.escape(it['desc'])}</div>
  <div class="ptext" id="t{i}">{safe}</div>
  <div class="card-foot">
    <button class="copybtn" data-i="{i}">📋 复制口令</button>
    <a href="{html.escape(it['link'])}" target="_blank">▶ 打开视频</a>
  </div>
</div>''')

html_doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>红果短剧推广口令清单 · 精准投放素材</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a1a1a;padding:24px;line-height:1.6}}
.wrap{{max-width:900px;margin:0 auto}}
h1{{font-size:24px;margin-bottom:6px}}
.sub{{color:#666;font-size:13px;margin-bottom:12px}}
.tag{{display:inline-block;background:#fff0f3;color:#fe2c55;border:1px solid #ffccd5;border-radius:20px;padding:3px 12px;font-size:12px;margin-bottom:16px}}
.warn{{background:#f6ffed;border:1px solid #b7eb8f;color:#3f6600;padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:20px}}
.toolbar{{margin-bottom:16px;display:flex;gap:10px}}
.toolbar button{{background:#fe2c55;color:#fff;border:none;padding:9px 18px;border-radius:6px;cursor:pointer;font-size:14px}}
.card{{background:#fff;border:1px solid #e8e8e8;border-radius:10px;padding:16px 18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.card-head{{display:flex;align-items:center;gap:12px;font-size:12px;color:#888;margin-bottom:8px;flex-wrap:wrap}}
.num{{font-weight:700;color:#fe2c55;font-size:14px}}
.author{{color:#333;font-weight:600}}
.stats{{color:#888}}
.date{{margin-left:auto}}
.code{{font-size:13px;color:#0958d9;background:#f0f7ff;border-left:3px solid #0958d9;padding:6px 10px;border-radius:4px;margin-bottom:10px;word-break:break-all}}
.ptext{{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:12px 14px;font-size:14px;color:#222;word-break:break-all;user-select:all}}
.card-foot{{display:flex;gap:10px;margin-top:10px}}
.card-foot button{{background:#fff;color:#fe2c55;border:1px solid #fe2c55;padding:6px 14px;border-radius:5px;cursor:pointer;font-size:13px}}
.card-foot button:hover{{background:#fe2c55;color:#fff}}
.card-foot a{{color:#333;text-decoration:none;border:1px solid #ddd;padding:6px 14px;border-radius:5px;font-size:13px}}
.card-foot a:hover{{border-color:#333}}
#toast{{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:10px 22px;border-radius:6px;opacity:0;transition:opacity .25s;font-size:14px;z-index:99}}
</style></head><body>
<div class="wrap">
<h1>红果短剧推广 · 精准投放素材口令清单</h1>
<div class="sub">共 {len(items)} 条 · 全部带官方投放编号（日期-渠道码-话术）· 已剔除蹭话题的普通分享 · 生成于 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<div class="tag">✅ 筛选口径：带官方投放编号 + 赞≥100 + 11月投放</div>
<div class="warn">📌 用法：点「复制口令」→ 粘贴到微信/群/朋友圈 → 别人复制这行文字打开抖音，直接跳转到对应视频。短链为抖音官方实时生成并已校验视频ID，长期有效。</div>
<div class="toolbar"><button onclick="cpAll()">📋 复制全部口令</button></div>
{''.join(cards)}
</div>
<div id="toast">已复制 ✓</div>
<script>
function toast(){{var t=document.getElementById('toast');t.style.opacity=1;setTimeout(()=>t.style.opacity=0,1500)}}
function fbCopy(text){{var ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity=0;document.body.appendChild(ta);ta.select();try{{document.execCommand('copy')}}catch(e){{}}document.body.removeChild(ta)}}
function doCopy(text){{if(navigator.clipboard&&window.isSecureContext){{navigator.clipboard.writeText(text).then(toast).catch(()=>{{fbCopy(text);toast()}})}}else{{fbCopy(text);toast()}}}}
function cp(i){{var el=document.getElementById('t'+i);doCopy(el?el.innerText:'')}}
function cpAll(){{var all=Array.prototype.map.call(document.querySelectorAll('.ptext'),function(e){{return e.innerText}}).join('\\n\\n');doCopy(all)}}
document.querySelectorAll('.copybtn').forEach(function(btn){{btn.addEventListener('click',function(){{cp(btn.getAttribute('data-i'))}})}})
</script></body></html>'''
open(os.path.join(BASE, "红果短剧推广口令清单_精准.html"), "w", encoding="utf-8").write(html_doc)
print("HTML/TXT/CSV 已生成（精准版）")

# 预览截图
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 960, "height": 1200})
        pg.goto("file:///" + os.path.join(BASE, "红果短剧推广口令清单_精准.html").replace("\\", "/"))
        pg.screenshot(path=os.path.join(BASE, "红果短剧推广口令清单_精准_预览.png"), full_page=True)
        b.close()
    print("预览截图已生成")
except Exception as e:
    print("预览截图跳过:", e)
