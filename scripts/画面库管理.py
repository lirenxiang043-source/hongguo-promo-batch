#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""画面迭代库增删改查：本地 HTTP 服务（页面改动直接写回覆盖层 + 重建库）。

用法：
  python 画面库管理.py serve                # 启动服务，打开 http://127.0.0.1:8792
  python 画面库管理.py list --q 花环 --limit 20
  python 画面库管理.py update <id> --title "新标题" --scene "新场景"
  python 画面库管理.py del <id>

说明：画面库由图片目录扫描生成，手工改动写入 画面迭代库_手工.json 覆盖层，
      重建 build_visual_library.py 时自动套用，不会被扫描结果冲掉。
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = pathlib.Path(__file__).resolve().parent
LIB = BASE / '画面迭代库.json'
HTML = BASE / '画面迭代库.html'
OVERRIDE = BASE / '画面迭代库_手工.json'
BUILDER = BASE / 'build_visual_library.py'
DEFAULT_PORT = 8792
EDITABLE = ('title', 'tag', 'subject', 'line', 'scene', 'variant', 'note', 'model', 'prompt')


def load_override():
    ov = {'deleted': [], 'overrides': {}, 'added': []}
    if OVERRIDE.exists():
        try:
            ov = json.loads(OVERRIDE.read_text(encoding='utf-8'))
        except Exception:
            pass
    for k, v in (('deleted', []), ('overrides', {}), ('added', [])):
        ov.setdefault(k, v)
    return ov


def save_override(ov):
    ov['deleted'] = list(dict.fromkeys(ov['deleted']))
    OVERRIDE.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding='utf-8')


def rebuild():
    try:
        p = subprocess.run([sys.executable, str(BUILDER)], cwd=str(BASE),
                           check=True, capture_output=True, text=True)
        return True, (p.stdout or '').strip()
    except Exception as e:
        return False, str(e)


def load():
    return json.loads(LIB.read_text(encoding='utf-8'))


def find_item(d, item_id):
    for it in d.get('items', []):
        if it.get('id') == item_id:
            return it
    return None


def add_item(d, data, ov):
    path = (data.get('path') or '').strip()
    if not path:
        raise ValueError('图片路径不能为空')
    # 接受相对工作目录路径或绝对路径，必须真实存在
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = BASE / p
    if not p.is_file():
        raise ValueError('图片文件不存在：' + path)
    rel = p.resolve().relative_to(BASE.resolve()).as_posix() if p.resolve().is_relative_to(BASE.resolve()) else str(p.resolve())
    if any(x.get('path') == rel for x in d['items']):
        raise ValueError('该图片已入库')
    # 用与扫描一致的自然 id（文件 sha1 前14位），否则重建后编辑/删除会对不上扫描条目
    digest = hashlib.sha1(p.read_bytes()).hexdigest()[:14]
    item_id = digest
    if find_item(d, item_id):
        raise ValueError('该图片已在覆盖层中')
    item = {
        'id': item_id, 'tag': data.get('tag', ''), 'subject': data.get('subject', ''),
        'title': data.get('title') or p.stem, 'line': data.get('line', ''),
        'scene': data.get('scene') or '手工登记', 'variant': data.get('variant') or '收件箱',
        'path': rel, 'thumb': rel, 'sources': [rel], 'width': 0, 'height': 0,
        'size': p.stat().st_size, 'mtime': data.get('date') or '',
        'model': data.get('model', ''), 'prompt': data.get('prompt', ''),
        'note': data.get('note', ''),
    }
    ov['added'].append(item)
    d['items'].insert(0, item)
    return item


def update_item(d, item_id, data, ov):
    it = find_item(d, item_id)
    if not it:
        raise KeyError('未找到该画面：' + str(item_id))
    src = ov['overrides'].setdefault(item_id, {})
    for k in EDITABLE:
        if k in data and data[k] is not None:
            it[k] = data[k]
            src[k] = data[k]
    return it


def del_item(d, item_id, ov):
    if not find_item(d, item_id):
        raise KeyError('未找到该画面：' + str(item_id))
    if item_id not in ov['deleted']:
        ov['deleted'].append(item_id)
    ov['overrides'].pop(item_id, None)
    ov['added'] = [a for a in ov['added'] if a.get('id') != item_id]
    d['items'] = [x for x in d['items'] if x.get('id') != item_id]


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
            return self._send(200, load())
        if p in ('/', '/index.html'):
            data = HTML.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        # 静态文件（缩略图 / 图片），限制在工作目录内，防止路径穿越
        import mimetypes
        from urllib.parse import unquote
        rel = unquote(p).lstrip('/')
        f = (BASE / rel).resolve()
        if f.is_file() and str(f).startswith(str(BASE.resolve())):
            data = f.read_bytes()
            ctype = mimetypes.guess_type(str(f))[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(404, {'error': 'not found'})

    def _mutate(self, method):
        ov = load_override()
        d = load()
        try:
            m = re.match(r'^/api/items/([^/?]+)', self.path)
            if method == 'POST' and self.path.split('?')[0] == '/api/items':
                item = add_item(d, self._body(), ov)
            elif method == 'PUT' and m:
                item = update_item(d, m.group(1), self._body(), ov)
            elif method == 'DELETE' and m:
                del_item(d, m.group(1), ov)
                item = {'id': m.group(1)}
            else:
                return self._send(404, {'error': 'not found'})
            save_override(ov)
            ok, msg = rebuild()
            return self._send(200, {'ok': True, 'item': item, 'rebuild': ok, 'msg': msg[:200]})
        except Exception as e:
            return self._send(400, {'error': str(e)})

    def do_POST(self):
        self._mutate('POST')

    def do_PUT(self):
        self._mutate('PUT')

    def do_DELETE(self):
        self._mutate('DELETE')


def serve(port):
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print('画面库服务已启动：http://127.0.0.1:%d' % port, flush=True)
    print('按 Ctrl+C 停止', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
        srv.server_close()


def main():
    ap = argparse.ArgumentParser(description='画面库增删改查')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('serve').add_argument('--port', type=int, default=DEFAULT_PORT)
    p = sub.add_parser('list')
    p.add_argument('--q', default='')
    p.add_argument('--limit', type=int, default=30)
    p = sub.add_parser('update')
    p.add_argument('id')
    for k in EDITABLE:
        p.add_argument('--' + k)
    sub.add_parser('del').add_argument('id')

    a = ap.parse_args()
    if not a.cmd:
        a = argparse.Namespace(cmd='serve', port=DEFAULT_PORT)
    if a.cmd == 'serve':
        serve(a.port)
        return
    ov = load_override()
    d = load()
    if a.cmd == 'list':
        rows = [x for x in d['items'] if not a.q or a.q.lower() in json.dumps(x, ensure_ascii=False).lower()]
        print('共 %d 条（显示前 %d 条）' % (len(rows), min(a.limit, len(rows))))
        for x in rows[:a.limit]:
            print('%s  [%s]  %s' % (x.get('id'), x.get('variant'), x.get('title')))
    elif a.cmd == 'update':
        update_item(d, a.id, {k: v for k, v in vars(a).items() if k in EDITABLE and v is not None}, ov)
        save_override(ov); rebuild(); print('已更新', a.id)
    elif a.cmd == 'del':
        del_item(d, a.id, ov); save_override(ov); rebuild(); print('已删除', a.id)


if __name__ == '__main__':
    main()
