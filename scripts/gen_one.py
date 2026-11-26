#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用豆包图生视频（平台调用）。
用法: python gen_one.py <tag> <subject_desc> <ref_abs_path> [account] [oral]
产出: promo/batch_out/raw/raw_<tag>.mp4，进度打印到 stdout（供平台解析）。
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PROMO = ROOT / 'promo'
KEY_FILE = PROMO / '.doubao_key.tmp'
TASKS = pathlib.Path(r'C:\Users\Administrator\AppData\Roaming\doubao-video-workspace\canvas-bridge-tasks.json')
GATEWAY = 'http://127.0.0.1:8788/v1/videos/generations'
CONFIRM_URL = 'http://127.0.0.1:8788/v1/videos/confirm'
CONFIRM_TEXT = '确认，请按上面的方案直接开始生成视频，不要再询问。'
BRIDGE_ACCOUNTS = 'http://127.0.0.1:3219/accounts'
ACCOUNT_ORDER = list(range(1, 8))  # 固定顺序：账号1 → 账号7
RAW = PROMO / 'batch_out' / 'raw'
RAW.mkdir(parents=True, exist_ok=True)

ORAL_DEFAULT = (
    '点一下屏幕，整部剧就能连续播下去。这是红果短剧的连播功能，'
    '点开自动接着播，不用手动反复点。画质高清，播放流畅，'
    '海量热门短剧汇集，修仙逆袭穿越都有，题材全，每天更新，随时点开就能看。'
)


def emit(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def available_accounts():
    try:
        with urllib.request.urlopen(BRIDGE_ACCOUNTS, timeout=3) as r:
            data = json.loads(r.read().decode('utf-8', 'ignore'))
        return {int(a['id']): a for a in data.get('accounts', [])}
    except Exception:
        return {}


def resolve_account(preferred=0, skip=()):
    """默认按 1→7 取第一个可用账号；显式指定账号时仍尊重指定值。"""
    if preferred and int(preferred) > 0:
        return int(preferred)
    statuses = available_accounts()
    for aid in ACCOUNT_ORDER:
        if aid in skip:
            continue
        a = statuses.get(aid)
        if not statuses:
            return aid
        if not a or not a.get('isLoggedIn') or not a.get('available') or a.get('health') != 'healthy':
            continue
        # 每个账号每天最多 4 条视频；用完后自动跳下一个账号
        if a.get('videoDailyUsed', 0) >= a.get('videoDailyLimit', 4):
            continue
        return aid
    return ACCOUNT_ORDER[0]


def snapshot():
    try:
        return json.loads(TASKS.read_text(encoding='utf-8'))
    except Exception:
        return []


def auto_confirm(task):
    """豆包弹出「视频生成参数确认」卡时自动放行，避免任务卡在 awaiting_confirmation。"""
    thread = task.get('gatewayThreadId')
    if not thread:
        return False
    try:
        key = KEY_FILE.read_text(encoding='utf-8').strip()
        payload = json.dumps({'threadId': thread, 'text': CONFIRM_TEXT}, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            CONFIRM_URL, data=payload,
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode('utf-8', 'ignore')
        emit('auto_confirm sent thread=%s reply=%s' % (str(thread)[:12], body[:60]))
        return True
    except Exception as e:
        emit('auto_confirm failed: %s' % e)
        return False


class SubmittedButUnconfirmed(RuntimeError):
    """消息已经发到豆包但结果没确认；此时不能再换号重发，否则会重复生成、白烧额度。"""


def gen_one(tag, subject, ref, account, oral):
    prompt = (
        '%s正面出镜，对着镜头说话，嘴巴随着每句话张开闭合，'
        '嘴型与口播文案逐字对齐，像真人配音一样自然。'
        '口播文案：%s' % (subject, oral)
    )
    body = {
        'model': 'Seedance 2.0 Mini',
        'prompt': prompt,
        'duration': 15,
        'aspect_ratio': '16:9',
        'account_id': account,
        'image': str(ref),
    }
    payload = json.dumps(body, ensure_ascii=False)
    key = KEY_FILE.read_text(encoding='utf-8').strip()
    before = {t.get('id') for t in snapshot()}
    emit('submit account=%d ref=%s' % (account, ref.name))
    subprocess.run([
        'curl', '-sS', '--max-time', '20', '-X', 'POST',
        '-H', 'Authorization: Bearer ' + key,
        '-H', 'Content-Type: application/json',
        '-d', payload, GATEWAY,
    ], capture_output=True, timeout=30)

    deadline = time.time() + 2400
    last = ''
    posted = False
    # 防重复生成（关键）：按会话 thread 去重，而不是按 task id。
    # 同一账号/会话重试会产生新的 task id，但仍是同一个豆包会话——
    # 若按 task id 去重就会对每个新任务再发一次"确认"，豆包把确认当成新指令，
    # 于是在同一会话里连生多个视频（截图里"已生成好了"后又冒出第二个视频）。
    confirmed_threads = set()
    # 已经看到"生成中/已生成好"等回复文本的会话，绝不再确认。
    started_threads = set()
    done_pattern = ('你的视频生成好了', '视频生成好了', '视频已生成', '生成完成',
                    '预计等待', '正在生成', '生成中', '正在排队', '排队中', '生成进度')
    while time.time() < deadline:
        time.sleep(8)
        new = [t for t in snapshot() if t.get('id') not in before]
        if not new:
            continue
        t = new[-1]
        st = t.get('status')
        thread = str(t.get('gatewayThreadId') or '')
        reply_text = '%s %s' % (t.get('latestReply') or '', t.get('statusText') or '')
        if st in ('awaiting_reply', 'generating'):
            posted = True
        if st != last:
            emit('task_status=%s text=%s' % (st, t.get('statusText')))
            last = st
        # 只要这个会话已经出现过"生成中/已生成好"的信号，就锁死不再确认。
        if st in ('generating', 'completed', 'downloading') or any(k in reply_text for k in done_pattern):
            if thread:
                started_threads.add(thread)
        # 豆包弹出参数确认卡时自动放行：同一会话只确认一次，且确认前必须确认
        # 该会话还没进入生成态（否则那条"确认"会被豆包当成新一轮生成指令）。
        if (st == 'awaiting_confirmation' and thread
                and thread not in confirmed_threads and thread not in started_threads):
            if auto_confirm(t):
                confirmed_threads.add(thread)
                emit('auto_confirm LOCK thread=%s（同会话不再二次确认）' % str(thread)[:12])
        elif st == 'awaiting_confirmation' and thread in (confirmed_threads | started_threads):
            emit('SKIP auto_confirm thread=%s（已确认或已生成，防重复）' % str(thread)[:12])
        if st == 'completed' and t.get('videoPath'):
            return pathlib.Path(t['videoPath'])
        if st in ('failed', 'error', 'needs_attention'):
            page = str(t.get('pageUrl') or '').rstrip('/')
            # 只要消息已经发出去（进入等待/生成），或者页面已落到具体会话，
            # 就按“可能已生成”处理：停止换号，交给人工收片，避免重复生成。
            likely_posted = posted or (page.startswith('https://www.doubao.com/chat/')
                                       and page != 'https://www.doubao.com/chat')
            msg = '%s: %s' % (st, t.get('error') or t.get('statusText'))
            if likely_posted:
                raise SubmittedButUnconfirmed(msg)
            raise RuntimeError(msg)
    raise TimeoutError('generation timeout')


def main():
    tag = sys.argv[1]
    subject = sys.argv[2]
    ref = pathlib.Path(sys.argv[3])
    account = int(sys.argv[4]) if len(sys.argv) > 4 else 0  # 0=自动，按1→7
    oral = sys.argv[5] if len(sys.argv) > 5 else ORAL_DEFAULT
    # single=1：指定账号失败后不重试（由 batch 层换号），避免同一账号被7次快速提交搞到页面劣化/cooling
    single = (len(sys.argv) > 6 and str(sys.argv[6]).strip() == '1')
    if not ref.exists():
        raise SystemExit('ref not found: %s' % ref)
    tried = []
    attempts = 1 if single else 7
    for attempt in range(1, attempts + 1):
        acct = resolve_account(account, tried)
        tried.append(acct)
        emit('using account=%d (order 1→7)' % acct)
        try:
            src = gen_one(tag, subject, ref, acct, oral)
            dst = RAW / ('raw_%s.mp4' % tag)
            shutil.copy2(src, dst)
            emit('SAVED %s size=%d' % (dst.name, dst.stat().st_size))
            # 时长兜底核对：桥接层档位可能没切过去导致默认 10s，出片后必须核对。
            try:
                out = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=nw=1:nk=1', str(dst)],
                    capture_output=True, text=True, timeout=20)
                dur = float(out.stdout.strip())
                emit('FFPROBE duration=%.2fs' % dur)
                if dur < 14:
                    emit('WARN 时长仅 %.2fs（<14s），豆包档位很可能没切到15s；此片不要直接发布，需重出。' % dur)
                    print('DURATION_WARN=%.2f' % dur, flush=True)
            except Exception as e:
                emit('FFPROBE 读取时长失败（不影响出片）: %s' % e)
            print('VIDEO_PATH=%s' % dst, flush=True)
            return
        except SubmittedButUnconfirmed as e:
            emit('attempt %d: 消息已提交但结果未确认，停止换号，避免重复生成（%s）' % (attempt, e))
            emit('请到账号 %d 的豆包页面确认/下载；不会自动重发。' % acct)
            sys.exit(2)
        except Exception as e:
            emit('attempt %d failed: %s' % (attempt, e))
            if single:
                sys.exit(1)
            time.sleep(8)
    sys.exit(1)


if __name__ == '__main__':
    main()
