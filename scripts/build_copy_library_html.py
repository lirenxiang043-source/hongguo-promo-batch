#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 文案库.json 生成带搜索/筛选/增删改查的可视化 HTML 文案库。"""
import datetime
import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
lib = json.loads((BASE / '文案库.json').read_text(encoding='utf-8'))
items = lib['items']
st = lib['stats']

# 只保留用户指定的 5 类配色；暗黑系用亮霓虹色（配合下方半透明底色渲染）
CAT_COLORS = {
    '漫剧口播原版': '#FBBF24',   # amber
    '短剧口播原版': '#22D3EE',   # cyan
    '口播迭代': '#F472B6',       # pink
    '口播成片': '#4ADE80',       # green
    '多功能综述原版': '#A78BFA', # violet
}
cats = sorted(st['cats'].items(), key=lambda x: -x[1])

tpl = r'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>红果短剧推广 · 文案库</title>
<style>
/* Framer-inspired editorial dark: oversized type, hairline grid, single accent, windowed cards */
:root{
  --bg:#08090B;--surface:#101114;--surface2:#16181C;--raised:#1C1F24;
  --ink:#F7F7F8;--ink2:#D6D7DB;--muted:#8A8D95;--muted2:#5C5F67;
  --line:#23262C;--line2:#33373F;
  --accent:#FF4D2E;--accent2:#FF7A5C;--green:#4ADE80;--amber:#FBBF24;
  --danger:#FF4D4D;--radius:12px;
  --fs-xs:11px;--fs-sm:13px;--fs-md:14px;--fs-lg:18px;--fs-xl:30px;--fs-hero:clamp(34px,5vw,58px);
  --ease:200ms cubic-bezier(.22,1,.36,1);
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%;background:#06070A}
button,input,select,textarea{font-family:inherit;font-size:inherit}
body{
  background:transparent;color:var(--ink);
  font-family:"Inter","Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  font-size:var(--fs-md);line-height:1.6;padding-bottom:80px;-webkit-font-smoothing:antialiased;
}
/* ===== Eye-opening cinematic background ===== */
.bg-stage{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none;background:#030405}
.eye-layer{position:absolute;inset:-4%;z-index:0;will-change:transform;transition:transform .6s cubic-bezier(.22,1,.36,1)}
.eye-img{position:absolute;inset:0;background-image:__EYE_URL__;background-size:cover;background-position:center 40%;transform:scale(1.06);animation:eyeBreath 8s 2.2s ease-in-out infinite}
@keyframes eyeBreath{0%,100%{transform:scale(1.06)}50%{transform:scale(1.1)}}
#stars{position:absolute;inset:0;width:100%;height:100%;z-index:1}
.eye-scrim{position:absolute;inset:0;z-index:2;background:linear-gradient(180deg,rgba(3,4,5,.62),rgba(3,4,5,.12) 26%,rgba(3,4,5,.28) 62%,rgba(3,4,5,.72)),linear-gradient(90deg,rgba(3,4,5,.86),rgba(3,4,5,.18) 55%,transparent 80%)}
.vignette{position:absolute;inset:0;z-index:2;background:radial-gradient(ellipse 92% 78% at 50% 42%,transparent 22%,rgba(3,4,5,.82) 100%)}
/* eyelids: full-screen top layer, start closed, slide apart on load */
.eye-curtain{position:fixed;inset:0;z-index:500;pointer-events:none;overflow:hidden}
.lid{position:absolute;left:0;right:0;height:50.5%;background:#030405}
.lid.top{top:0;box-shadow:0 4px 0 rgba(255,32,32,.92),0 10px 34px rgba(255,0,0,.55);animation:lidTop 1.5s .3s cubic-bezier(.76,0,.24,1) forwards}
.lid.bot{bottom:0;box-shadow:0 -4px 0 rgba(255,32,32,.92),0 -10px 34px rgba(255,0,0,.55);animation:lidBot 1.5s .3s cubic-bezier(.76,0,.24,1) forwards}
@keyframes lidTop{to{transform:translateY(-101%)}}
@keyframes lidBot{to{transform:translateY(101%)}}
.eye-flash{position:absolute;inset:0;z-index:3;background:radial-gradient(ellipse 60% 40% at 50% 44%,rgba(255,30,30,.55),transparent 65%);opacity:0;animation:eyeFlash 1s .95s ease-out}
@keyframes eyeFlash{0%{opacity:0}22%{opacity:1}100%{opacity:0}}
.eye-replay{position:absolute;top:22px;right:30px;z-index:5;pointer-events:auto;background:rgba(255,77,46,.08);border:1px solid rgba(255,77,46,.35);color:var(--accent2);font-size:11px;font-weight:600;letter-spacing:.05em;padding:7px 13px;border-radius:99px;cursor:pointer;transition:all var(--ease)}
.eye-replay:hover{background:rgba(255,77,46,.18);border-color:var(--accent);color:#fff}
/* hide replay button whenever a floating overlay is open (avoid clashing with close button) */
body:has(#detail.on) .eye-replay,body:has(#cmd.on) .eye-replay,body:has(#mask[style*="flex"]) .eye-replay,body:has(#cmask[style*="flex"]) .eye-replay{opacity:0;pointer-events:none}
.lidClosing .lid.top{animation:lidTopClose .5s cubic-bezier(.76,0,.24,1) forwards}
.lidClosing .lid.bot{animation:lidBotClose .5s cubic-bezier(.76,0,.24,1) forwards}
@keyframes lidTopClose{from{transform:translateY(-101%)}to{transform:translateY(0)}}
@keyframes lidBotClose{from{transform:translateY(101%)}to{transform:translateY(0)}}
::selection{background:var(--accent);color:#fff}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:4px}
.wrap{max-width:1200px;margin:0 auto;padding:0 28px}
/* Hero — oversized editorial type */
header{position:relative;border-bottom:1px solid var(--line);padding:60px 0 34px;overflow:hidden}
header .wrap{position:relative;z-index:1}
.eyebrow{font-size:var(--fs-xs);font-weight:700;letter-spacing:.16em;color:var(--accent);text-transform:uppercase;margin-bottom:18px;display:flex;align-items:center;gap:10px}
.eyebrow::before{content:"";width:26px;height:1px;background:var(--accent)}
header h1{font-size:var(--fs-hero);font-weight:800;letter-spacing:-.045em;line-height:1.02;max-width:900px}
header h1 em{font-style:normal;color:var(--accent)}
header p{color:var(--muted);font-size:var(--fs-sm);margin-top:18px;max-width:620px;line-height:1.7}
.stats{display:flex;gap:0;margin-top:38px;border-top:1px solid var(--line)}
.stat{flex:1;border-right:1px solid var(--line);padding:18px 20px 4px 0}
.stat:not(:first-child){padding-left:22px}
.stat:last-child{border-right:none}
.stat b{display:block;font-size:var(--fs-xl);font-weight:800;letter-spacing:-.04em;line-height:1;font-variant-numeric:tabular-nums}
.stat span{font-size:var(--fs-xs);color:var(--muted);letter-spacing:.04em;margin-top:6px;display:block}
.stat:nth-child(2) b{color:var(--amber)}.stat:nth-child(3) b{color:var(--accent2)}.stat:nth-child(4) b{color:var(--green)}
/* Toolbar — hairline panels */
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:20px 0 14px}
.search{flex:1;min-width:250px;background:transparent;border:none;border-bottom:1px solid var(--line2);border-radius:0;padding:11px 2px;font-size:var(--fs-lg);color:var(--ink);outline:none;transition:border-color var(--ease)}
.search::placeholder{color:var(--muted2)}
.search:focus{border-color:var(--accent)}
.sel{background:var(--surface);border:1px solid var(--line2);border-radius:8px;padding:9px 11px;font-size:var(--fs-sm);color:var(--ink2);outline:none;max-width:160px;cursor:pointer;transition:border-color var(--ease)}
.sel:focus,.daterow input:focus,.modal input:focus,.modal textarea:focus{border-color:var(--accent)}
.btn{border:1px solid var(--line2);background:var(--surface);border-radius:8px;padding:9px 14px;font-size:var(--fs-sm);font-weight:600;cursor:pointer;color:var(--ink2);display:inline-flex;align-items:center;gap:7px;transition:all var(--ease);white-space:nowrap}
.btn svg{width:14px;height:14px;flex:none}
.btn:hover{border-color:var(--ink);color:var(--ink);background:var(--raised)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700}
.btn.primary:hover{background:var(--accent2);border-color:var(--accent2)}
.btn:active{transform:translateY(1px)}
.badge{font-size:var(--fs-xs);border:1px solid var(--line2);border-radius:99px;padding:6px 11px;color:var(--muted);font-weight:600;white-space:nowrap;display:inline-flex;align-items:center;gap:7px}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--muted2)}
.badge.api{color:var(--green);border-color:rgba(74,222,128,.3)}
.badge.api::before{background:var(--green)}
.badge.local{color:var(--amber);border-color:rgba(251,191,36,.3)}
.badge.local::before{background:var(--amber)}
/* Date row + slash chips */
.daterow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:var(--fs-xs);color:var(--muted);padding:10px 0;border-top:1px solid var(--line)}
.daterow .dl{font-weight:700;color:var(--ink);letter-spacing:.1em;text-transform:uppercase}
.daterow .sep{color:var(--muted2)}
.daterow input[type=date]{width:140px;background:var(--surface);border:1px solid var(--line2);border-radius:7px;padding:6px 9px;font-size:var(--fs-xs);color:var(--ink);outline:none;color-scheme:dark}
.daterow .btn{padding:6px 11px;font-size:var(--fs-xs)}
.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}
.chip{border:none;background:transparent;border-radius:0;padding:8px 12px;font-size:var(--fs-sm);font-weight:600;cursor:pointer;color:var(--muted);transition:color var(--ease);position:relative}
.chip::before{content:"/";color:var(--muted2);margin-right:7px;font-weight:400}
.chip small{font-size:var(--fs-xs);opacity:.55;margin-left:4px;font-variant-numeric:tabular-nums}
.chip:hover{color:var(--ink)}
.chip.on{color:var(--ink)}
.chip.on::before{color:var(--accent)}
.chip.on::after{content:"";position:absolute;left:12px;right:12px;bottom:2px;height:2px;background:var(--accent)}
.note{font-size:var(--fs-xs);color:var(--muted2);margin:12px 0 0;display:flex;align-items:center;gap:6px}
.note svg{width:13px;height:13px;flex:none;color:var(--accent)}
.count{font-size:var(--fs-xs);color:var(--muted);margin:22px 0 12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;border-top:1px solid var(--line);padding-top:16px}
/* Windowed cards */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.item{
  position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  overflow:hidden;transition:border-color var(--ease),transform var(--ease),background var(--ease);
  animation:cardIn .5s cubic-bezier(.22,1,.36,1) both;
}
@keyframes cardIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
.item:hover{border-color:var(--line2);transform:translateY(-4px);background:var(--surface2)}
/* window chrome bar */
.item::before{content:"";display:block;height:26px;background:var(--raised);border-bottom:1px solid var(--line);position:relative}
.item::after{content:"";position:absolute;top:9px;left:12px;width:6px;height:6px;border-radius:50%;background:#FF5F57;box-shadow:10px 0 0 #FEBC2E,20px 0 0 #28C840}
.win-label{position:absolute;top:5px;right:12px;font-size:9px;letter-spacing:.1em;color:var(--muted2);text-transform:uppercase;z-index:2}
.item .cat{display:inline-block;font-size:var(--fs-xs);font-weight:700;border-radius:4px;padding:3px 8px;margin:14px 0 10px;letter-spacing:.03em}
.item .txt{font-size:var(--fs-md);line-height:1.75;color:var(--ink2);word-break:break-word;padding:0 16px}
.item .meta{font-size:var(--fs-xs);color:var(--muted2);margin:14px 16px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding-top:11px;border-top:1px solid var(--line)}
.item .meta .digg{color:var(--green);font-weight:700;font-variant-numeric:tabular-nums}
.item .meta span::before{content:"·";color:var(--line2);margin-right:8px}
.item .meta span:first-child::before{display:none}
.item .note2{font-size:var(--fs-xs);color:var(--amber);background:rgba(251,191,36,.06);border-left:2px solid var(--amber);padding:7px 10px;margin:10px 16px 16px}
.ops{position:absolute;right:10px;top:3px;display:flex;gap:2px;opacity:0;transition:opacity var(--ease);z-index:3}
.item:hover .ops,.item:focus-within .ops{opacity:1}
.op{border:none;background:transparent;border-radius:5px;padding:3px 6px;cursor:pointer;color:var(--muted);transition:all var(--ease);display:inline-flex}
.op:hover{background:var(--raised);color:var(--ink)}
.op.del:hover{color:var(--danger)}
.empty{text-align:center;color:var(--muted);padding:70px 20px;border:1px dashed var(--line2);border-radius:var(--radius)}
/* Modal */
.mask{position:fixed;inset:0;background:rgba(0,0,0,.72);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;z-index:99;padding:20px}
.modal{background:var(--surface);border:1px solid var(--line2);border-radius:14px;width:min(620px,100%);max-height:90vh;overflow:auto;padding:26px 28px;box-shadow:0 30px 90px rgba(0,0,0,.8)}
.modal h3{font-size:24px;font-weight:800;letter-spacing:-.03em;margin-bottom:6px}
.modal .sub{font-size:var(--fs-xs);color:var(--muted);margin-bottom:20px;letter-spacing:.06em;text-transform:uppercase}
.modal label{display:block;font-size:var(--fs-xs);color:var(--muted);margin-bottom:12px}
.modal label span{display:block;margin-bottom:6px;font-weight:700;color:var(--ink2);letter-spacing:.03em}
.modal input,.modal textarea,.modal select{width:100%;background:var(--bg);border:1px solid var(--line2);border-radius:8px;padding:10px 12px;font-size:var(--fs-sm);color:var(--ink);outline:none;transition:border-color var(--ease);color-scheme:dark}
.modal textarea{min-height:92px;resize:vertical;line-height:1.7}
.row{display:flex;gap:12px}.row>label{flex:1;min-width:0}
.acts{display:flex;justify-content:flex-end;gap:10px;margin-top:12px;padding-top:18px;border-top:1px solid var(--line)}
#toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(10px);background:var(--ink);color:var(--bg);padding:11px 20px;border-radius:8px;font-size:var(--fs-sm);font-weight:700;opacity:0;pointer-events:none;transition:opacity var(--ease),transform var(--ease);z-index:120}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
/* ===== Interactive extras ===== */
/* search shortcut hint */
.kbd{display:inline-flex;align-items:center;gap:3px;font-size:10px;color:var(--muted2);border:1px solid var(--line2);border-radius:5px;padding:2px 6px;font-weight:600;letter-spacing:0}
.search-wrap{flex:1;min-width:250px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line2);transition:border-color var(--ease)}
.search-wrap:focus-within{border-color:var(--accent)}
.search-wrap .search{border:none;min-width:0}
/* 3D tilt cards */
.grid{perspective:1200px}
.item{transform-style:preserve-3d;will-change:transform}
.item .cat,.item .txt,.item .meta,.item .note2{transform:translateZ(18px)}
.item .sheen{position:absolute;inset:0;pointer-events:none;opacity:0;background:radial-gradient(420px circle at var(--mx,50%) var(--my,50%),rgba(255,255,255,.09),transparent 45%);transition:opacity var(--ease);z-index:1}
.item:hover .sheen{opacity:1}
/* immersive detail overlay */
#detail{position:fixed;inset:0;background:rgba(4,5,7,.94);backdrop-filter:blur(14px);display:none;flex-direction:column;align-items:center;justify-content:center;z-index:110;padding:32px;opacity:0;transition:opacity .22s ease}
#detail.on{display:flex;opacity:1}
.dt-close{position:fixed;top:24px;right:28px;background:var(--surface);border:1px solid var(--line2);color:var(--muted);width:42px;height:42px;border-radius:50%;font-size:22px;cursor:pointer;transition:all var(--ease)}
.dt-close:hover{color:var(--ink);border-color:var(--ink);transform:rotate(90deg)}
.dt-body{width:min(900px,100%);padding:20px 40px;transform:translateY(16px);transition:transform .3s cubic-bezier(.22,1,.36,1)}
#detail.on .dt-body{transform:none}
.dt-count{font-size:var(--fs-xs);color:var(--accent);letter-spacing:.14em;text-transform:uppercase;margin-bottom:18px}
.dt-cat{display:inline-block;font-size:var(--fs-xs);font-weight:700;border-radius:5px;padding:4px 10px;margin-bottom:20px}
.dt-text{font-size:clamp(22px,3.2vw,40px);font-weight:700;line-height:1.5;letter-spacing:-.02em;color:var(--ink);word-break:break-word}
.dt-meta{display:flex;gap:18px;flex-wrap:wrap;margin-top:30px;padding-top:20px;border-top:1px solid var(--line);font-size:var(--fs-xs);color:var(--muted)}
.dt-meta b{color:var(--ink2);font-weight:700}
.dt-actions{display:flex;gap:10px;margin-top:28px;flex-wrap:wrap}
.dt-nav{display:flex;align-items:center;gap:14px;margin-top:30px;color:var(--muted2);font-size:var(--fs-xs)}
.dt-nav button{background:transparent;border:1px solid var(--line2);color:var(--muted);border-radius:8px;padding:8px 14px;cursor:pointer;font-size:var(--fs-sm);transition:all var(--ease)}
.dt-nav button:hover{border-color:var(--accent);color:var(--accent)}
.dt-progress{flex:1;height:2px;background:var(--line);border-radius:2px;overflow:hidden;max-width:220px}
.dt-progress i{display:block;height:100%;background:var(--accent);transition:width var(--ease)}
/* command palette */
#cmd{position:fixed;inset:0;background:rgba(4,5,7,.8);backdrop-filter:blur(10px);display:none;align-items:flex-start;justify-content:center;z-index:115;padding:12vh 20px 20px;opacity:0;transition:opacity .18s ease}
#cmd.on{display:flex;opacity:1}
.cmdbox{width:min(640px,100%);background:var(--surface);border:1px solid var(--line2);border-radius:14px;box-shadow:0 30px 90px rgba(0,0,0,.8);overflow:hidden;transform:translateY(-12px);transition:transform .22s cubic-bezier(.22,1,.36,1)}
#cmd.on .cmdbox{transform:none}
.cmdinput{width:100%;background:transparent;border:none;border-bottom:1px solid var(--line);padding:18px 22px;font-size:var(--fs-lg);color:var(--ink);outline:none}
.cmdinput::placeholder{color:var(--muted2)}
.cmdlist{max-height:46vh;overflow:auto;padding:8px}
.cmdrow{display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:8px;cursor:pointer;color:var(--ink2)}
.cmdrow:hover,.cmdrow.sel{background:var(--raised)}
.cmdrow .cmd-tag{font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;flex:none}
.cmdrow .cmd-text{font-size:var(--fs-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.cmdrow .cmd-go{color:var(--muted2);font-size:11px}
.cmdhint{padding:9px 22px;border-top:1px solid var(--line);font-size:10px;color:var(--muted2);display:flex;gap:16px}
/* number roll */
.stat b{transition:color var(--ease)}
@media(max-width:760px){.wrap{padding:0 16px}header{padding:40px 0 26px}.stats{flex-wrap:wrap;gap:12px 0}.stat{min-width:45%;border:none;padding:12px 0!important}.grid{grid-template-columns:1fr}.row{flex-direction:column}.sel{max-width:none}.ops{opacity:1}.dt-text{font-size:22px}#cmd{padding-top:6vh}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.item{opacity:1!important;transform:none!important}.lid.top{transform:translateY(-101%)}.lid.bot{transform:translateY(101%)}.eye-flash{opacity:0}}
</style></head><body>
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
<header><div class="wrap">
<div class="eyebrow">Hongguo Short Drama / Copy Library</div>
<h1>每一句口播<br>都值得被<em>记住</em>。</h1>
<p>漫剧口播原版 · 短剧口播原版 · 迭代 / 成片 / 综述 —— 统一归档、检索与复用。生成于 __BUILT__</p>
<div class="stats">
<div class="stat"><b id="s_total">__TOTAL__</b><span>文案总数</span></div>
<div class="stat"><b id="s_mj">—</b><span>漫剧口播原版</span></div>
<div class="stat"><b id="s_dj">—</b><span>短剧口播原版</span></div>
<div class="stat"><b id="s_other">—</b><span>迭代 / 成片 / 综述</span></div>
</div></div></header>
<div class="wrap">
<div class="toolbar">
<div class="search-wrap">
<input class="search" id="q" placeholder="搜索文案关键词，或按 ⌘K 打开命令面板…">
<span class="kbd" id="kbdHint">⌘ K</span>
</div>
<select class="sel" id="src"><option value="">全部来源</option></select>
<select class="sel" id="sort">
<option value="default">默认排序</option><option value="digg">点赞最多</option>
<option value="date">日期最新</option><option value="az">文案 A→Z</option>
</select>
<button class="btn primary" id="add"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>新增</button>
<button class="btn" id="exp"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>导出</button>
<span class="badge" id="mode">连接中…</span>
</div>
<div class="daterow">
<span class="dl">日期</span>
<input type="date" id="d_from"><span class="sep">至</span><input type="date" id="d_to">
<button class="btn" id="d_today">今天</button>
<button class="btn" id="d_week">近7天</button>
<button class="btn" id="d_month">近30天</button>
<button class="btn" id="d_clear">清除</button>
</div>
<div class="chips" id="chips"></div>
<div class="note"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>点卡片看大图详情 · <span class="kbd">/</span> 搜索 · <span class="kbd">N</span> 新增 · <span class="kbd">⌘K</span> 命令面板 · <span class="kbd">← →</span> 详情翻页 · <span class="kbd">Esc</span> 关闭</div>
<div class="count" id="count"></div>
<div class="grid" id="grid"></div>
</div>

<div id="toast"></div>

<!-- Immersive detail -->
<div id="detail" role="dialog" aria-label="文案详情">
<button class="dt-close" id="dt_close" aria-label="关闭详情">×</button>
<div class="dt-body">
  <div class="dt-count" id="dt_count">COPY 01 / 47</div>
  <span class="dt-cat" id="dt_cat"></span>
  <div class="dt-text" id="dt_text"></div>
  <div class="dt-meta" id="dt_meta"></div>
  <div class="dt-actions">
    <button class="btn primary" id="dt_copy"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>复制文案</button>
    <button class="btn" id="dt_edit">编辑这条</button>
  </div>
  <div class="dt-nav">
    <button id="dt_prev">← 上一条</button>
    <div class="dt-progress"><i id="dt_bar"></i></div>
    <button id="dt_next">下一条 →</button>
  </div>
</div>
</div>

<!-- Command palette -->
<div id="cmd" role="dialog" aria-label="命令面板">
<div class="cmdbox">
  <input class="cmdinput" id="cmd_input" placeholder="输入关键词搜索全部文案…" autocomplete="off">
  <div class="cmdlist" id="cmd_list"></div>
  <div class="cmdhint"><span>↑ ↓ 选择</span><span>↵ 打开详情</span><span>Esc 关闭</span></div>
</div>
</div>

<div class="mask" id="mask" style="display:none"><div class="modal">
<h3 id="mtitle">新增文案</h3>
<div class="sub">Copy Library / Editor</div>
<label><span>文案内容 *</span><textarea id="f_text" placeholder="输入要入库的文案 / 口播原版"></textarea></label>
<label><span>分类</span><input id="f_cat" list="catlist" placeholder="如：情绪钩子 / 短剧口播原版"><datalist id="catlist"></datalist></label>
<div class="row">
<label><span>来源</span><input id="f_source" placeholder="如：手工新增 / ASR转写"></label>
<label><span>作者</span><input id="f_author" placeholder="如：自写"></label>
</div>
<div class="row">
<label><span>点赞数</span><input id="f_digg" type="number" value="0"></label>
<label><span>日期</span><input id="f_date" type="date"></label>
</div>
<div class="row">
<label><span>原视频 ID</span><input id="f_vid" placeholder="选填"></label>
<label><span>备注</span><input id="f_note" placeholder="选填"></label>
</div>
<div class="acts"><button class="btn" id="f_cancel">取消</button><button class="btn primary" id="f_save">保存</button></div>
</div></div>

<div class="mask" id="cmask" style="display:none"><div class="modal" style="width:min(420px,100%)">
<h3>确认删除</h3>
<p id="cdesc" style="font-size:14px;line-height:1.6;color:#444"></p>
<div class="acts"><button class="btn" id="c_cancel">取消</button><button class="btn primary" id="c_ok" style="background:#dc2626;border-color:#dc2626">确认删除</button></div>
</div></div>

<script>
const EMBED=__DATA__;
const COLORS=__COLORS__;
const ALLOWED=['短剧口播原版','漫剧口播原版','口播迭代','口播成片','多功能综述原版'];
const STAMP='__STAMP__';
let DATA=EMBED.slice(),MODE='local',cat='全部',kw='',src='',sort='default',dFrom='',dTo='',editId=null,delId=null;
function dayStr(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
function daysAgo(n){const d=new Date();d.setDate(d.getDate()-n);return dayStr(d)}
const $=id=>document.getElementById(id);
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function makeId(t){let h=0;const s=String(t||'').replace(/\s+/g,'');for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0}return 'local_'+(h>>>0).toString(16)}
function fmt(n){return n>=10000?(n/10000).toFixed(1)+'万':String(n||0)}
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),1800)}

async function boot(){
  try{
    const r=await fetch('/api/ping',{cache:'no-store'});
    if(r.ok&&(await r.json()).ok){
      MODE='api';
      const d=await (await fetch('/api/items',{cache:'no-store'})).json();
      DATA=d.items;
    }
  }catch(e){}
  if(MODE==='local'){
    try{
      const s=JSON.parse(localStorage.getItem('hg_copy_lib')||'null');
      if(s&&s.stamp===STAMP)DATA=s.items;
      else localStorage.removeItem('hg_copy_lib');
    }catch(e){}
  }
  const m=$('mode');m.textContent=MODE==='api'?'已连接 · 自动存文件':'离线 · 存浏览器';m.className='badge '+MODE;
  buildFilters();render();
}
function buildFilters(){
  const cmap={};DATA.forEach(x=>cmap[x.cat||'其他话术']=(cmap[x.cat||'其他话术']||0)+1);
  $('chips').innerHTML=['全部'].concat(Object.keys(cmap).sort((a,b)=>cmap[b]-cmap[a])).map(c=>
    '<span class="chip'+(c===cat?' on':'')+'" data-c="'+esc(c)+'">'+esc(c)+' <small>'+(c==='全部'?DATA.length:cmap[c])+'</small></span>').join('');
  document.querySelectorAll('.chip').forEach(el=>el.onclick=()=>{cat=el.dataset.c;buildFilters();render()});
  const sources=[...new Set(DATA.map(x=>x.source||'').filter(Boolean))].sort();
  $('src').innerHTML='<option value="">全部来源</option>'+sources.map(s=>'<option value="'+esc(s)+'"'+(s===src?' selected':'')+'>'+esc(s)+'</option>').join('');
  $('catlist').innerHTML=[...new Set(DATA.map(x=>x.cat).filter(Boolean))].map(c=>'<option value="'+esc(c)+'"></option>').join('');
  $('s_total').textContent=DATA.length;
  $('s_mj').textContent=DATA.filter(x=>x.cat==='漫剧口播原版').length;
  $('s_dj').textContent=DATA.filter(x=>x.cat==='短剧口播原版').length;
  $('s_other').textContent=DATA.filter(x=>['口播迭代','口播成片','多功能综述原版'].includes(x.cat)).length;
}
function render(){
  let list=DATA.filter(x=>
    (cat==='全部'||x.cat===cat)&&
    (!kw||String(x.text||'').toLowerCase().includes(kw))&&
    (!src||(x.source||'')===src)&&
    (!dFrom||(x.date&&x.date>=dFrom))&&
    (!dTo||(x.date&&x.date<=dTo)));
  if(sort==='digg')list=list.slice().sort((a,b)=>(b.digg||0)-(a.digg||0));
  if(sort==='date')list=list.slice().sort((a,b)=>String(b.date||'').localeCompare(String(a.date||'')));
  if(sort==='az')list=list.slice().sort((a,b)=>String(a.text||'').localeCompare(String(b.text||''),'zh'));
  $('count').textContent='共 '+list.length+' 条'+(cat!=='全部'?' · '+cat:'');
  const g=$('grid');
  if(!list.length){g.innerHTML='<div class="empty">没有匹配的文案</div>';return}
  const ICON={copy:'<path d="M9 9h10v10H9zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',edit:'<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/>',del:'<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'};
  function svgOp(act,label){return '<button class="op'+(act==='del'?' del':'')+'" data-act="'+act+'" aria-label="'+label+'" title="'+label+'"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICON[act]+'</svg></button>'}
  g.innerHTML=list.map((x,idx)=>{
    const id=x.id||makeId(x.text),c=COLORS[x.cat]||'#0F766E',meta=[];
    const delay=Math.min(idx*35,700); // stagger 入场，封顶避免长列表过慢
    if(x.digg)meta.push('<span class="digg">'+fmt(x.digg)+' 赞</span>');
    if(x.author)meta.push('<span>'+esc(x.author)+'</span>');
    if(x.date)meta.push('<span>'+esc(x.date)+'</span>');
    if(x.source)meta.push('<span>'+esc(x.source)+'</span>');
    const ops=svgOp('copy','复制')+svgOp('edit','编辑')+svgOp('del','删除');
    return '<div class="item" data-id="'+esc(id)+'" style="animation-delay:'+delay+'ms">'+
      '<span class="win-label">'+String(x.text||'').length+' chars'+(x.vid?' · video':'')+'</span>'+
      '<span class="sheen"></span>'+
      '<div class="ops">'+ops+'</div>'+
      '<span class="cat" style="color:'+c+';background:'+c+'14">/ '+esc(x.cat)+'</span>'+
      '<div class="txt">'+esc(x.text)+'</div>'+
      '<div class="meta">'+meta.join('')+'</div>'+
      (x.note?'<div class="note2">'+esc(x.note)+'</div>':'')+'</div>';
  }).join('');
  // 入场动画结束后清除 animation，让 3D tilt 的 inline transform 生效
  g.querySelectorAll('.item').forEach(el=>el.addEventListener('animationend',()=>{
    el.style.animation='none';el.style.opacity='1';el.style.transform='';
  },{once:true}));
}
function find(id){return DATA.find(x=>(x.id||makeId(x.text))===id)}
function copyText(t){
  const done=()=>toast('已复制');
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(done).catch(()=>fb(t,done))}
  else fb(t,done);
}
function fb(t,done){const ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done()}catch(e){toast('复制失败')}ta.remove()}
$('grid').onclick=e=>{
  const b=e.target.closest('.op');if(!b)return;
  const id=b.closest('.item').dataset.id,x=find(id);if(!x)return;
  const a=b.dataset.act;
  if(a==='copy')copyText(x.text);
  if(a==='edit')openForm(x);
  if(a==='del'){delId=id;$('cdesc').textContent='确定删除这条文案？\n\n'+String(x.text).slice(0,120)+(String(x.text).length>120?'…':'');$('cmask').style.display='flex'}
};
function openForm(x){
  editId=x?(x.id||makeId(x.text)):null;
  $('mtitle').textContent=x?'编辑文案':'新增文案';
  $('f_text').value=x?x.text:'';$('f_cat').value=x?x.cat:'短剧口播原版';
  $('f_source').value=x?(x.source||''):'手工新增';$('f_author').value=x?(x.author||'自写'):'自写';
  $('f_digg').value=x?(x.digg||0):0;$('f_date').value=x?(x.date||new Date().toISOString().slice(0,10)):new Date().toISOString().slice(0,10);
  $('f_vid').value=x?(x.vid||''):'';$('f_note').value=x?(x.note||''):'';
  $('mask').style.display='flex';setTimeout(()=>$('f_text').focus(),50);
}
function payload(){
  return {text:$('f_text').value.trim(),cat:$('f_cat').value.trim()||'其他话术',
    source:$('f_source').value.trim(),author:$('f_author').value.trim(),
    digg:parseInt($('f_digg').value||'0',10),date:$('f_date').value,
    vid:$('f_vid').value.trim(),note:$('f_note').value.trim()};
}
async function saveForm(){
  const p=payload();
  if(!p.text){toast('文案内容不能为空');return}
  if(!ALLOWED.includes(p.cat)){toast('分类只允许：'+ALLOWED.join(' / '));return}
  try{
    if(MODE==='api'&&editId){
      const r=await fetch('/api/items/'+encodeURIComponent(editId),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'保存失败');
      const i=DATA.findIndex(x=>(x.id||makeId(x.text))===editId);if(i>=0)DATA[i]=j.item;
    }else if(MODE==='api'){
      const r=await fetch('/api/items',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'新增失败');DATA.unshift(j.item);
    }else{
      if(editId){const i=DATA.findIndex(x=>(x.id||makeId(x.text))===editId);if(i>=0)DATA[i]=Object.assign({},DATA[i],p,{id:editId})}
      else DATA.unshift(Object.assign({id:makeId(p.text)},p));
      localStorage.setItem('hg_copy_lib',JSON.stringify({stamp:STAMP,items:DATA}));
    }
    $('mask').style.display='none';buildFilters();render();toast(editId?'已修改':'已新增');
  }catch(e){toast('保存失败：'+e.message)}
}
async function doDel(){
  try{
    if(MODE==='api'){
      const r=await fetch('/api/items/'+encodeURIComponent(delId),{method:'DELETE'});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'删除失败');
      DATA=DATA.filter(x=>(x.id||makeId(x.text))!==delId);
    }else{
      DATA=DATA.filter(x=>(x.id||makeId(x.text))!==delId);
      localStorage.setItem('hg_copy_lib',JSON.stringify({stamp:STAMP,items:DATA}));
    }
    $('cmask').style.display='none';buildFilters();render();toast('已删除');
  }catch(e){toast('删除失败：'+e.message)}
}
$('add').onclick=()=>openForm(null);
$('f_cancel').onclick=()=>$('mask').style.display='none';
$('f_save').onclick=saveForm;
$('c_cancel').onclick=()=>$('cmask').style.display='none';
$('c_ok').onclick=doDel;
$('q').oninput=e=>{kw=e.target.value.trim().toLowerCase();render()};
$('src').onchange=e=>{src=e.target.value;render()};
$('sort').onchange=e=>{sort=e.target.value;render()};
function setDates(a,b){dFrom=a;dTo=b;$('d_from').value=a;$('d_to').value=b;render()}
$('d_from').onchange=e=>{dFrom=e.target.value;render()};
$('d_to').onchange=e=>{dTo=e.target.value;render()};
$('d_today').onclick=()=>setDates(dayStr(new Date()),dayStr(new Date()));
$('d_week').onclick=()=>setDates(daysAgo(6),'');
$('d_month').onclick=()=>setDates(daysAgo(29),'');
$('d_clear').onclick=()=>setDates('','');
$('exp').onclick=()=>{
  const blob=new Blob([JSON.stringify({built:'__BUILT__',stats:stDyn(),items:DATA},null,1)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='文案库_当前.json';a.click();URL.revokeObjectURL(a.href);toast('已导出');
};
function stDyn(){const c={};DATA.forEach(x=>c[x.cat]=(c[x.cat]||0)+1);return {total:DATA.length,cats:c}}

/* ===== Immersive detail ===== */
let detailList=[],detailIdx=0;
function openDetail(id){
  detailList=visibleList();detailIdx=Math.max(0,detailList.findIndex(x=>(x.id||makeId(x.text))===id));
  paintDetail();$('detail').classList.add('on');document.body.style.overflow='hidden';
}
function closeDetail(){$('detail').classList.remove('on');document.body.style.overflow=''}
function paintDetail(){
  const x=detailList[detailIdx];if(!x)return;
  const c=COLORS[x.cat]||'#FF4D2E';
  $('dt_count').textContent='COPY '+String(detailIdx+1).padStart(2,'0')+' / '+String(detailList.length).padStart(2,'0');
  $('dt_cat').textContent='/ '+x.cat;$('dt_cat').style.color=c;$('dt_cat').style.background=c+'14';
  $('dt_text').textContent=x.text;
  const m=[];
  if(x.digg)m.push('<span><b>'+fmt(x.digg)+'</b> 赞</span>');
  if(x.author)m.push('<span>作者 <b>'+esc(x.author)+'</b></span>');
  if(x.date)m.push('<span>日期 <b>'+esc(x.date)+'</b></span>');
  if(x.source)m.push('<span>来源 <b>'+esc(x.source)+'</b></span>');
  $('dt_meta').innerHTML=m.join('')+(x.note?'<span style="flex-basis:100%;color:var(--amber)">'+esc(x.note)+'</span>':'');
  $('dt_bar').style.width=((detailIdx+1)/detailList.length*100)+'%';
}
function detailStep(n){if(!detailList.length)return;detailIdx=(detailIdx+n+detailList.length)%detailList.length;paintDetail()}
$('dt_close').onclick=closeDetail;
$('detail').onclick=e=>{if(e.target===$('detail'))closeDetail()};
$('dt_prev').onclick=()=>detailStep(-1);
$('dt_next').onclick=()=>detailStep(1);
$('dt_copy').onclick=()=>{const x=detailList[detailIdx];if(x)copyText(x.text)};
$('dt_edit').onclick=()=>{const x=detailList[detailIdx];if(x){closeDetail();openForm(x)}};

/* visible list (after all filters) — reuse for detail + command palette */
function visibleList(){
  return DATA.filter(x=>
    (cat==='全部'||x.cat===cat)&&
    (!kw||String(x.text||'').toLowerCase().includes(kw))&&
    (!src||(x.source||'')===src)&&
    (!dFrom||(x.date&&x.date>=dFrom))&&
    (!dTo||(x.date&&x.date<=dTo)));
}

/* ===== Command palette ===== */
let cmdRows=[],cmdSel=0;
function openCmd(){$('cmd').classList.add('on');$('cmd_input').value='';cmdSearch('');setTimeout(()=>$('cmd_input').focus(),40)}
function closeCmd(){$('cmd').classList.remove('on')}
function cmdSearch(q){
  const term=q.trim().toLowerCase();
  cmdRows=DATA.filter(x=>!term||String(x.text).toLowerCase().includes(term)||String(x.cat).toLowerCase().includes(term)).slice(0,8);
  cmdSel=0;paintCmd();
}
function paintCmd(){
  $('cmd_list').innerHTML=cmdRows.length?cmdRows.map((x,i)=>{
    const c=COLORS[x.cat]||'#FF4D2E';
    return '<div class="cmdrow'+(i===cmdSel?' sel':'')+'" data-i="'+i+'">'+
      '<span class="cmd-tag" style="color:'+c+';background:'+c+'18">'+esc(x.cat)+'</span>'+
      '<span class="cmd-text">'+esc(x.text)+'</span><span class="cmd-go">↵</span></div>';
  }).join(''):'<div style="padding:24px;text-align:center;color:var(--muted2);font-size:13px">没有匹配的文案</div>';
  document.querySelectorAll('.cmdrow').forEach(r=>r.onclick=()=>{const x=cmdRows[+r.dataset.i];if(x){closeCmd();openDetail(x.id||makeId(x.text))}});
}
$('cmd_input').oninput=e=>cmdSearch(e.target.value);
$('cmd_input').onkeydown=e=>{
  if(e.key==='ArrowDown'){e.preventDefault();cmdSel=Math.min(cmdSel+1,cmdRows.length-1);paintCmd()}
  if(e.key==='ArrowUp'){e.preventDefault();cmdSel=Math.max(cmdSel-1,0);paintCmd()}
  if(e.key==='Enter'&&cmdRows[cmdSel]){closeCmd();openDetail(cmdRows[cmdSel].id||makeId(cmdRows[cmdSel].text))}
};
$('cmd').onclick=e=>{if(e.target===$('cmd'))closeCmd()};

/* card click → detail (ignore action buttons) */
$('grid').addEventListener('click',e=>{
  if(e.target.closest('.op'))return;
  const card=e.target.closest('.item');if(card)openDetail(card.dataset.id);
},true);

/* 3D tilt on pointer devices */
if(window.matchMedia('(hover:hover) and (pointer:fine)').matches){
  document.addEventListener('pointermove',e=>{
    const card=e.target.closest('.item');if(!card)return;
    const r=card.getBoundingClientRect(),px=(e.clientX-r.left)/r.width,py=(e.clientY-r.top)/r.height;
    card.style.transform='perspective(900px) rotateX('+((.5-py)*7).toFixed(2)+'deg) rotateY('+((px-.5)*9).toFixed(2)+'deg) translateY(-3px)';
    card.style.setProperty('--mx',(px*100)+'%');card.style.setProperty('--my',(py*100)+'%');
  });
  document.addEventListener('pointerout',e=>{
    const card=e.target.closest('.item');if(card)card.style.transform='';
  });
}

/* number roll on load */
function roll(el,to){
  const from=0,t0=performance.now(),dur=900;
  function step(t){const p=Math.min((t-t0)/dur,1),ease=1-Math.pow(1-p,3);el.textContent=Math.round(from+(to-from)*ease);if(p<1)requestAnimationFrame(step)}
  requestAnimationFrame(step);
}
let rolled=false;

/* keyboard shortcuts */
document.addEventListener('keydown',e=>{
  const typing=/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCmd();return}
  if(e.key==='Escape'){
    closeCmd();closeDetail();
    $('mask').style.display='none';$('cmask').style.display='none';
    if(typing&&document.activeElement.blur)document.activeElement.blur();
    return;
  }
  if(typing)return;
  if(e.key==='/'){e.preventDefault();$('q').focus();return}
  if(e.key.toLowerCase()==='n'){e.preventDefault();openForm(null);return}
  if($('detail').classList.contains('on')){
    if(e.key==='ArrowLeft'){e.preventDefault();detailStep(-1)}
    if(e.key==='ArrowRight'){e.preventDefault();detailStep(1)}
  }
});
if(!window.matchMedia('(pointer:coarse)').matches) $('kbdHint').textContent='⌘ K';

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
    stars=Array.from({length:n},()=>({
      x:Math.random()*W,y:Math.random()*H,
      r:Math.random()*1.3+.3,a:Math.random()*.55+.15,
      vy:Math.random()*.16+.03,tw:Math.random()*Math.PI*2,
      hue:Math.random()<.12?((Math.random()<.5)?'255,140,90':'150,190,255'):'255,255,255'
    }));
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

  /* replay the eye-opening animation */
  const stage=document.getElementById('eyeCurtain'),btn=document.getElementById('eyeReplay');
  if(btn&&stage){
    btn.addEventListener('click',()=>{
      stage.classList.remove('lidClosing');
      void stage.offsetWidth;
      stage.classList.add('lidClosing');
      setTimeout(()=>{
        stage.classList.remove('lidClosing');
        void stage.offsetWidth;
        const fl=document.getElementById('eyeFlash');
        if(fl){fl.style.animation='none';void fl.offsetWidth;fl.style.animation=''}
      },540);
    });
  }
})();

boot().then(()=>{
  if(!rolled){rolled=true;
    ['s_total','s_mj','s_dj','s_other'].forEach(id=>{const el=$(id);if(el)roll(el,+el.textContent||0)});
  }
});
</script></body></html>'''

import datetime as _dt, base64 as _b64
_eye = BASE / 'assets' / 'eyes_bg.jpg'
_eye_url = ('url("data:image/jpeg;base64,' + _b64.b64encode(_eye.read_bytes()).decode() + '")') if _eye.exists() else 'none'
out = (tpl
    .replace('__EYE_URL__', _eye_url)
    .replace('__BUILT__', lib['built'])
    .replace('__STAMP__', _dt.datetime.now().strftime('%Y%m%d%H%M%S%f'))
    .replace('__TOTAL__', str(st['total']))
    .replace('__REAL__', str(st['real']))
    .replace('__OPT__', str(st['optimized']))
    .replace('__ORAL__', str(st['oral']))
    .replace('__DATA__', json.dumps(items, ensure_ascii=False))
    .replace('__COLORS__', json.dumps(CAT_COLORS, ensure_ascii=False)))
(BASE / '文案库.html').write_text(out, encoding='utf-8')
print('HTML生成', len(out), '字节', '· 条目', len(items))
