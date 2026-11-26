#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文案库增删改查：命令行 + 本地 HTTP 服务（页面改动直接写回 文案库.json）。

用法：
  python 文案库管理.py serve                 # 启动服务，浏览器打开 http://127.0.0.1:8791
  python 文案库管理.py list  --q 连播 --limit 20
  python 文案库管理.py add   --text "新文案" --cat "情绪钩子" [--source 自写]
  python 文案库管理.py update <id> [--text ...] [--cat ...]
  python 文案库管理.py del   <id>
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = pathlib.Path(__file__).resolve().parent
LIB = BASE / '文案库.json'
HTML = BASE / '文案库.html'
OVERRIDE = BASE / '文案库_手工.json'
BUILDER = BASE / 'build_copy_library_html.py'
DEFAULT_PORT = 8791

# 文案库只允许这 5 类入库，其余分类一律拒绝
ALLOWED_CATS = {'短剧口播原版', '漫剧口播原版', '口播迭代', '口播成片', '多功能综述原版'}
CAT_ALIAS = {'口播·迭代': '口播迭代', '口播·成片': '口播成片', '口播·原版': '漫剧口播原版'}


def check_cat(cat):
    cat = CAT_ALIAS.get(cat, cat)
    if cat not in ALLOWED_CATS:
        raise ValueError('分类只允许：' + '/'.join(sorted(ALLOWED_CATS)))
    return cat


def make_id(text):
    """基于文案正文生成稳定 id，重建库后仍可对应。"""
    s = re.sub(r'\s+', '', text or '')
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]


def norm(text):
    return re.sub(r'\s+', '', text or '')


def load():
    d = json.loads(LIB.read_text(encoding='utf-8'))
    changed = False
    for it in d.get('items', []):
        if not it.get('id'):
            it['id'] = make_id(it.get('text', ''))
            changed = True
    if changed:
        _write_raw(d)
    return d


def _write_raw(d):
    d['built'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    counts = {}
    for it in d['items']:
        counts[it.get('cat', '其他话术')] = counts.get(it.get('cat', '其他话术'), 0) + 1
    d['stats'] = {
        'total': len(d['items']),
        'real': sum(1 for x in d['items'] if x.get('source') == '抓取'),
        'optimized': sum(1 for x in d['items'] if str(x.get('source', '')).startswith('优化')),
        'oral': sum(1 for x in d['items'] if ('口播' in str(x.get('cat', '')) or '原版' in str(x.get('cat', '')) or '综述' in str(x.get('cat', '')))),
        'cats': counts,
    }
    LIB.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')


def update_override(d, deleted_ids):
    """记录手工改动，重建基础库时可重新套用。"""
    ov = {'overrides': {}, 'deleted': []}
    if OVERRIDE.exists():
        try:
            ov = json.loads(OVERRIDE.read_text(encoding='utf-8'))
        except Exception:
            pass
    ov.setdefault('overrides', {})
    ov.setdefault('deleted', [])
    for i in deleted_ids:
        if i not in ov['deleted']:
            ov['deleted'].append(i)
    for it in d['items']:
        if it.get('id'):
            ov['overrides'][it['id']] = it
    OVERRIDE.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding='utf-8')


def save(d, deleted_ids=None, rebuild=True):
    _write_raw(d)
    update_override(d, deleted_ids or [])
    if rebuild:
        try:
            subprocess.run([sys.executable, str(BUILDER)], cwd=str(BASE),
                           check=True, capture_output=True, text=True)
        except Exception as e:
            print('HTML 重建失败（数据已保存）:', e, file=sys.stderr)


def add_item(d, data):
    text = (data.get('text') or '').strip()
    if not text:
        raise ValueError('文案内容不能为空')
    if any(norm(x.get('text')) == norm(text) for x in d['items']):
        raise ValueError('已存在相同文案')
    cat = check_cat((data.get('cat') or '短剧口播原版').strip())
    it = {
        'id': data.get('id') or make_id(text),
        'text': text,
        'cat': cat,
        'digg': int(data.get('digg') or 0),
        'author': data.get('author') or '自写',
        'date': data.get('date') or datetime.date.today().isoformat(),
        'vid': data.get('vid') or '',
        'source': data.get('source') or '手工新增',
        'note': data.get('note') or '',
    }
    d['items'].insert(0, it)
    return it


def update_item(d, item_id, data):
    for it in d['items']:
        if it.get('id') == item_id:
            # id 是条目的稳定身份，编辑正文时不改 id，保证删除/覆盖记录始终对应
            for k in ('text', 'cat', 'digg', 'author', 'date', 'vid', 'source', 'note'):
                if k in data and data[k] is not None:
                    it[k] = data[k]
            it['text'] = str(it.get('text', '')).strip()
            it['cat'] = check_cat(it.get('cat'))
            return it
    raise KeyError('未找到该文案：' + str(item_id))


def del_item(d, item_id):
    before = len(d['items'])
    d['items'] = [x for x in d['items'] if x.get('id') != item_id]
    if len(d['items']) == before:
        raise KeyError('未找到该文案：' + str(item_id))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/api/ping':
            return self._send(200, {'ok': True, 'mode': 'api'})
        if p == '/api/items':
            d = load()
            return self._send(200, {'items': d['items'], 'stats': d['stats'], 'built': d['built']})
        if p in ('/', '/index.html'):
            data = HTML.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path.split('?')[0] != '/api/items':
            return self._send(404, {'error': 'not found'})
        try:
            d = load()
            it = add_item(d, self._body())
            save(d)
            self._send(200, {'ok': True, 'item': it, 'stats': d['stats']})
        except Exception as e:
            self._send(400, {'error': str(e)})

    def do_PUT(self):
        m = re.match(r'^/api/items/([^/?]+)', self.path)
        if not m:
            return self._send(404, {'error': 'not found'})
        try:
            d = load()
            it = update_item(d, m.group(1), self._body())
            save(d)
            self._send(200, {'ok': True, 'item': it, 'stats': d['stats']})
        except Exception as e:
            self._send(400, {'error': str(e)})

    def do_DELETE(self):
        m = re.match(r'^/api/items/([^/?]+)', self.path)
        if not m:
            return self._send(404, {'error': 'not found'})
        try:
            d = load()
            del_item(d, m.group(1))
            save(d, [m.group(1)])
            self._send(200, {'ok': True, 'stats': d['stats']})
        except Exception as e:
            self._send(400, {'error': str(e)})


def serve(port):
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print('文案库服务已启动：http://127.0.0.1:%d' % port, flush=True)
    print('按 Ctrl+C 停止', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
        srv.server_close()


def main():
    ap = argparse.ArgumentParser(description='文案库增删改查')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('serve').add_argument('--port', type=int, default=DEFAULT_PORT)

    p = sub.add_parser('list')
    p.add_argument('--q', default='')
    p.add_argument('--cat', default='')
    p.add_argument('--limit', type=int, default=30)

    p = sub.add_parser('add')
    p.add_argument('--text', required=True)
    p.add_argument('--cat', default='短剧口播原版')
    p.add_argument('--source', default='手工新增')
    p.add_argument('--author', default='自写')
    p.add_argument('--note', default='')

    p = sub.add_parser('update')
    p.add_argument('id')
    for k in ('text', 'cat', 'source', 'author', 'note'):
        p.add_argument('--' + k)

    sub.add_parser('del').add_argument('id')

    a = ap.parse_args()
    if not a.cmd:
        a = argparse.Namespace(cmd='serve', port=DEFAULT_PORT)

    if a.cmd == 'serve':
        serve(a.port)
        return
    d = load()
    if a.cmd == 'list':
        rows = [x for x in d['items']
                if (not a.q or a.q.lower() in x.get('text', '').lower())
                and (not a.cat or x.get('cat') == a.cat)]
        print('共 %d 条（显示前 %d 条）' % (len(rows), min(a.limit, len(rows))))
        for x in rows[:a.limit]:
            print('%s  [%s]  %s' % (x.get('id'), x.get('cat'), x.get('text')[:70]))
    elif a.cmd == 'add':
        it = add_item(d, vars(a))
        save(d)
        print('已新增:', it['id'], it['text'][:50])
    elif a.cmd == 'update':
        it = update_item(d, a.id, {k: v for k, v in vars(a).items()
                                   if k not in ('cmd', 'id') and v is not None})
        save(d)
        print('已更新:', it['id'], it['text'][:50])
    elif a.cmd == 'del':
        del_item(d, a.id)
        save(d, [a.id])
        print('已删除:', a.id)


if __name__ == '__main__':
    main()
