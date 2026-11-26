# -*- coding: utf-8 -*-
"""下载今天16条精准素材里尚未转写口播的11条视频，用于ASR转写。"""
import json, os, time
from patchright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "douyin_state.json")
OUT = os.path.join(BASE, "video_audio")
os.makedirs(OUT, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 已有口播的 vid（build_oral.py 的 A-F）
ORAL_VIDS = {
    "7708462744537746751", "7707814134208859428", "7708575558841503017",
    "7707821959827983651", "7707907315453676863", "7708085532898676003",
}


def grab(pw, vid):
    media = []
    browser = pw.chromium.launch(headless=False, args=["--mute-audio"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    def on_resp(resp):
        try:
            u = resp.url
            ct = (resp.headers or {}).get("content-type", "")
            if "video" in ct or "douyinvod" in u or "mp4" in ct:
                if u not in media:
                    media.append(u)
        except Exception:
            pass

    page.on("response", on_resp)
    page.goto(f"https://www.douyin.com/video/{vid}", wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    try:
        page.mouse.click(640, 450)
    except Exception:
        pass
    time.sleep(5)
    try:
        src = page.evaluate("""() => {
            const v = document.querySelector('video'); if (!v) return [];
            const s = []; if (v.src) s.push(v.src);
            document.querySelectorAll('video source').forEach(x => x.src && s.push(x.src));
            return s;
        }""")
        for s in src:
            if s and s not in media:
                media.append(s)
    except Exception:
        pass
    browser.close()
    good = [u for u in media if "douyinvod" in u or ".mp4" in u or "video/tos" in u]
    return good or media


def download(url, path):
    import requests
    headers = {"User-Agent": UA, "Referer": "https://www.douyin.com/"}
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        size = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk); size += len(chunk)
    return size


def main():
    precise = json.load(open(os.path.join(BASE, "filtered_precise.json"), encoding="utf-8"))
    targets = [(str(a["id"]), a.get("desc", "")[:40]) for a in precise if str(a["id"]) not in ORAL_VIDS]
    print(f"待下载 {len(targets)} 条", flush=True)

    result = {}
    with sync_playwright() as pw:
        for i, (vid, desc) in enumerate(targets, 1):
            path = os.path.join(OUT, f"precise_{vid}.mp4")
            if os.path.exists(path) and os.path.getsize(path) > 100000:
                print(f"[{i}/{len(targets)}] 已存在，跳过 {vid}", flush=True)
                result[vid] = {"path": path, "size": os.path.getsize(path), "desc": desc}
                continue
            try:
                urls = grab(pw, vid)
                if urls:
                    size = download(urls[0], path)
                    print(f"[{i}/{len(targets)}] OK {vid} {size/1024/1024:.2f}MB | {desc}", flush=True)
                    result[vid] = {"path": path, "size": size, "desc": desc, "url": urls[0]}
                else:
                    print(f"[{i}/{len(targets)}] FAIL no-url {vid} | {desc}", flush=True)
                    result[vid] = {"error": "no media url", "desc": desc}
            except Exception as e:
                print(f"[{i}/{len(targets)}] FAIL {vid} {e}", flush=True)
                result[vid] = {"error": str(e), "desc": desc}
            time.sleep(2)

    json.dump(result, open(os.path.join(BASE, "precise_audio_map.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for v in result.values() if v.get("size"))
    print(f"下载完成 {ok}/{len(targets)}", flush=True)


if __name__ == "__main__":
    main()
