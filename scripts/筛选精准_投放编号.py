# -*- coding: utf-8 -*-
"""精准筛选：带红果官方投放编号（日期-渠道码-话术）的推广素材。
第5条 1118-LYT-不用逐集解锁漫剧 这种才是目标；蹭话题的高赞普通分享不算。
条件全部同时满足：带官方投放编号 + 点赞>=100 + 11月及以后投放。
"""
import os, json, re

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "douyin_awemes_1124_all.json")
OUT = os.path.join(BASE, "filtered_precise.json")

CODE = re.compile(r"\b(\d{4})-([A-Z]{2,6})-")


def main():
    arr = json.load(open(SRC, encoding="utf-8"))
    by = {}
    for a in arr:
        k = str(a.get("id") or "")
        if k and k not in by:
            by[k] = a

    passed = []
    stats = {"no_code": 0, "low_digg": 0, "old": 0}
    for a in by.values():
        d = (a.get("desc") or "").strip()
        m = CODE.search(d)
        if not m:
            stats["no_code"] += 1
            continue
        digg = a.get("digg_count") or 0
        if digg < 100:
            stats["low_digg"] += 1
            continue
        code_date = m.group(1)          # 1118 -> 11月18日投放
        if int(code_date[:2]) < 11:      # 过滤 10月及更早
            stats["old"] += 1
            continue
        passed.append(a)

    passed.sort(key=lambda x: -(x.get("digg_count") or 0))
    json.dump(passed, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"去重后 {len(by)} 条 | 无编号剔除 {stats['no_code']} | 低赞剔除 {stats['low_digg']} | 10月及更早剔除 {stats['old']}")
    print(f"=> 精准入选 {len(passed)} 条 -> filtered_precise.json\n")
    for i, a in enumerate(passed, 1):
        print(f"#{i:2d} 赞{a.get('digg_count'):>6} {a['id']} | {a['desc'][:72]}")


if __name__ == "__main__":
    main()
