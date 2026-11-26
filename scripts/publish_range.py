#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐条发布指定编号成片（账号/任务ID/标题/话题/AI声明 与既有完全一致）。
用法: python publish_range.py 10 11
"""
import os
import requests, time, json, pathlib, sys

BASE = 'http://127.0.0.1:5199'
VIDEO_DIR = pathlib.Path(os.environ.get('HGP_VIDEO_DIR')
                         or r'C:\Users\Administrator\Downloads\红果短剧推广_10条成片')
TASK_ID = os.environ.get('HGP_TASK_ID', '7669632093152182308')
TITLE = os.environ.get('HGP_TITLE', '还得是红果短剧')
TOPICS = os.environ.get('HGP_TOPICS', '#红果短剧 #你的短剧搭子')
FNAME = '%s---%s---%s.mp4' % (TITLE, TOPICS, TASK_ID)
LOG = pathlib.Path(os.environ.get('HGP_WORK') or pathlib.Path.cwd()) / 'batch_out' / 'publish_range.log'


def log(msg):
    line = time.strftime('[%H:%M:%S] ') + str(msg)
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def state():
    return requests.get(BASE + '/api/state', timeout=10).json()


def find_item(item_id):
    for it in state().get('queue', {}).get('items', []):
        if it.get('id') == item_id:
            return it
    return None


def publish_one(tag):
    video = VIDEO_DIR / ('推广红果短剧_%02d.mp4' % tag)
    log('=== START #%02d ===' % tag)
    acc = requests.get(BASE + '/api/accounts', timeout=10).json()['accounts']
    active = acc['activeAccountId']
    name = next((a['displayName'] for a in acc['accounts'] if a['id'] == active), '?')
    log('account=%s' % name)
    if name != '西瓜撞地球':
        acc_id = next(a['id'] for a in acc['accounts'] if a['displayName'] == '西瓜撞地球')
        requests.post(BASE + '/api/accounts/%s/select' % acc_id, timeout=10)
        log('switched account -> 西瓜撞地球')

    with video.open('rb') as f:
        r = requests.post(BASE + '/api/files/import',
                          files={'video': (FNAME, f, 'video/mp4')},
                          data={'queueListNumber': '1'}, timeout=90)
    d = r.json()
    ids = d.get('importedItemIds') or []
    if not ids:
        log('IMPORT FAILED %s %s' % (r.status_code, json.dumps(d, ensure_ascii=False)[:300]))
        return False
    item_id = ids[-1]
    log('imported id=%s' % item_id)

    items = state().get('queue', {}).get('items', [])
    patched = False
    for it in items:
        if it.get('id') == item_id:
            it['declarationType'] = 'ai'
            it['isAiVideo'] = True
            patched = True
            break
    if patched:
        requests.post(BASE + '/api/queue/update', json={'items': items}, timeout=15)
        log('AI declaration enabled')

    r = requests.post(BASE + '/api/publish/single', json={'itemId': item_id}, timeout=30)
    log('publish trigger http=%s' % r.status_code)

    deadline = time.time() + 300
    last = ''
    while time.time() < deadline:
        it = find_item(item_id)
        st = it.get('status') if it else '?'
        sd = state()
        msg = sd.get('queue', {}).get('message')
        key = '%s/%s/%s' % (st, sd.get('queue', {}).get('state'), msg)
        if key != last:
            log('  status=%s queue=%s msg=%s' % (st, sd.get('queue', {}).get('state'), msg))
            last = key
        if st == 'published':
            log('=== PUBLISHED #%02d ===' % tag)
            return True
        if st in ('failed', 'error') or sd.get('publishFailure'):
            log('=== FAILED #%02d : %s ===' % (tag, json.dumps(sd.get('publishFailure'), ensure_ascii=False)[:300]))
            return False
        if st in ('cancelled', 'skipped'):
            log('=== SKIPPED #%02d (%s) ===' % (tag, st))
            return False
        time.sleep(6)
    log('=== TIMEOUT #%02d ===' % tag)
    return False


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text('', encoding='utf-8')
    tags = [int(x) for x in sys.argv[1:]]
    results = {}
    for t in tags:
        try:
            results[t] = publish_one(t)
        except Exception as e:
            log('EXCEPTION #%02d: %s' % (t, e))
            results[t] = False
        time.sleep(3)
    log('=== SUMMARY === ' + json.dumps(results))


if __name__ == '__main__':
    main()
