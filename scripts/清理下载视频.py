#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理抓取下载到 video_audio/ 的临时视频（ASR 转写入库后不再需要）。

安全边界：
  - 只删 BASE/video_audio 目录下的 *.mp4，不递归、不碰任何子目录
  - 成片目录、promo/batch_out 的 raw/final_v2 等生成产物一律不动
  - 默认只列清单；加 --yes 才真正删除

用法：
  python 清理下载视频.py                 # 预览待清理清单
  python 清理下载视频.py --yes           # 清理全部
  python 清理下载视频.py --yes --hours 2 # 只清理 2 小时前下载的（防止误删刚下载未转写的）
"""
import argparse
import pathlib
import time

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / 'video_audio'


def main():
    ap = argparse.ArgumentParser(description='清理抓取下载的临时视频')
    ap.add_argument('--yes', action='store_true', help='确认执行删除')
    ap.add_argument('--hours', type=float, default=0.0,
                    help='只清理 N 小时前修改的文件（0=不限）')
    ap.add_argument('--dry-run', action='store_true', help='只列清单，不删')
    a = ap.parse_args()

    if not OUT.is_dir():
        print('目录不存在，无需清理:', OUT)
        return

    now = time.time()
    files = []
    for f in OUT.glob('*.mp4'):
        if not f.is_file():
            continue
        if a.hours > 0 and (now - f.stat().st_mtime) < a.hours * 3600:
            continue
        files.append(f)
    files.sort(key=lambda p: p.stat().st_mtime)

    if not files:
        print('没有需要清理的视频')
        return

    total = sum(f.stat().st_size for f in files)
    print('待清理 %d 个视频，共 %.1f MB（目录：%s）' % (len(files), total / 1024 / 1024, OUT))
    for f in files:
        print('  %8.2f MB  %s' % (f.stat().st_size / 1024 / 1024, f.name))

    if a.dry_run or not a.yes:
        print('\n未删除。确认后加 --yes 执行。')
        return

    freed = 0
    failed = []
    for f in files:
        try:
            freed += f.stat().st_size
            f.unlink()
        except Exception as e:
            failed.append((f.name, str(e)))
    print('\n已删除 %d 个，释放 %.1f MB' % (len(files) - len(failed), freed / 1024 / 1024))
    for n, e in failed:
        print('  删除失败:', n, e)


if __name__ == '__main__':
    main()
