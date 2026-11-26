# -*- coding: utf-8 -*-
"""精准素材补链：复用已有短链，其余用 skill 补，并做视频ID级校验。"""
import os, sys, json, re, importlib.util
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
SKILL = r"C:\Users\Administrator\.workbuddy\skills\hongguo-douyin-material\scripts\dy_shortlink.py"
UA = ("Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")

PRECISE = os.path.join(BASE, "filtered_precise.json")
OLD_LINKS = os.path.join(BASE, "links_1124_all.json")
OUT = os.path.join(BASE, "links_precise.json")
AUDIT = os.path.join(BASE, "link_audit_precise.json")
TODO = os.path.join(BASE, "_precise_todo.json")   # 仅缺链目标，喂给 skill


def verify(url, target_id):
    m = re.search(r"v\.douyin\.com/([A-Za-z0-9_-]+)", url or "")
    if not m or len(m.group(1)) < 6:
        return False, ""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, allow_redirects=True, timeout=20)
        hit = re.search(r"/share/video/(\d{15,})/", r.url) or re.search(r"/video/(\d{15,})", r.url)
        real = hit.group(1) if hit else ""
        return (real == str(target_id)), real
    except Exception:
        return False, ""


def load_skill():
    spec = importlib.util.spec_from_file_location("dy_shortlink_skill", SKILL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    precise = json.load(open(PRECISE, encoding="utf-8"))
    old = json.load(open(OLD_LINKS, encoding="utf-8")) if os.path.exists(OLD_LINKS) else {}

    # 1) 先复用已有且校验通过的短链
    links, audit = {}, {}
    todo = []
    for a in precise:
        vid = str(a["id"])
        if vid in old and old[vid]:
            ok, real = verify(old[vid], vid)
            if ok:
                links[vid] = old[vid]
                audit[vid] = {"url": old[vid], "ok": True, "real_id": real, "source": "reuse"}
                continue
        todo.append(a)
    json.dump(todo, open(TODO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"复用已有 {len(links)} 条，待补 {len(todo)} 条 -> {TODO}", flush=True)

    if todo:
        mod = load_skill()
        orig_grab = mod.grab_one

        def grab_and_verify(ctx, vid):
            u = orig_grab(ctx, vid)
            if not u:
                audit[vid] = {"url": None, "ok": False, "reason": "未拿到短链"}
                return None
            ok, real = verify(u, vid)
            audit[vid] = {"url": u, "ok": ok, "real_id": real,
                          "reason": "ok" if ok else "ID不匹配或降级短码"}
            return u if ok else None

        mod.grab_one = grab_and_verify
        sys.argv = ["dy_shortlink.py", "--in", TODO,
                    "--out", OUT, "--state", os.path.join(BASE, "douyin_state.json"),
                    "--limit", "100", "--retry", "2"]
        mod.main()
        # skill 只把成功短链写进 OUT，读回来合并
        if os.path.exists(OUT):
            newlinks = json.load(open(OUT, encoding="utf-8"))
            for vid, u in newlinks.items():
                if vid not in links:
                    links[vid] = u
                    if vid not in audit:
                        audit[vid] = {"url": u, "ok": True, "source": "skill"}

    # 按精准清单顺序写最终 links
    ordered = {str(a["id"]): links[str(a["id"])] for a in precise if str(a["id"]) in links}
    json.dump(ordered, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(audit, open(AUDIT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    good = sum(1 for v in audit.values() if v.get("ok"))
    print(f"最终有效短链 {len(ordered)}/{len(precise)}，审计通过 {good}")
    for vid, v in audit.items():
        print(vid, "OK" if v.get("ok") else "FAIL", v.get("url") or "", v.get("reason", v.get("source", "")))


if __name__ == "__main__":
    main()
