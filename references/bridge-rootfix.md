# 豆包桥接报错根治（阶段 C 关键）

批量生视频反复失败的根因和补丁，本次对话逐一验证。按症状查。

## 症状 → 根因 → 修法

### 症状0：同一会话连续生成两个视频（视频已生成好又冒出第二个）

现象：豆包会话里"你的视频生成好了 + 视频1"之后，又出现一条
"确认，请按上面的方案直接开始生成视频，不要再询问"，然后豆包又生成视频2。
那条"确认"是 `gen_one.py` 的 `CONFIRM_TEXT`，被 auto_confirm 在视频1完成后又发了一次——
豆包把这条确认当成新一轮生成指令，于是同会话重复出片、白烧额度。

根因：auto_confirm 原来按 **task id** 去重（`confirmed_ids`）。同一账号/会话重试会产生
**新的 task id**，旧 id 拦不住 → 每个新任务都再发一次确认。叠加"症状1"的同账号7次重试，
重复确认必然发生。

修法（已在 scripts/gen_one.py 中，两道护栏）：
1. **按会话 thread 去重**（`confirmed_threads`），而不是 task id——同一会话只确认一次。
2. **生成态锁死**（`started_threads`）：一旦某会话的回复文本出现
   "你的视频生成好了/预计等待/正在生成/生成中/排队中"等，或状态进入 generating/completed/downloading，
   就永不再对该会话发确认。确认前同时检查两个集合。
主因仍是症状1的 single=1（同账号不再重试），此护栏是第二道保险。

### 症状1：连续7次提交同一账号，把窗口搞劣化 / 账号进 cooling

**根因**：`gen_one.py` 的 `resolve_account(preferred)` 见 preferred>0 就直接 `return preferred`，
不检查 tried。于是 for 循环 7 次都返回同一账号，同一账号被快速连发 7 次 → 页面 DOM 乱、
账号标记 cooling。

**修法（已在 scripts/gen_one.py 中）**：加第 6 参数 `single`。
```python
single = (len(sys.argv) > 6 and str(sys.argv[6]).strip() == '1')
attempts = 1 if single else 7
...
except Exception as e:
    if single: sys.exit(1)   # 失败即退出，由 batch 层换号
```
batch 的 `gen()` 调用必须传 `1`：`run(GEN_ONE, [tag, subject, ref, acct, ORAL, 1], ...)`。
验证：修完后单条账号一次成功，不再连发。

### 症状2：反复"未找到时长滑块"，每次复位只能跑 2-3 条

**根因**：`page-composer.js` 的 `openTrigger()` 用纯文字判断参数面板是否展开：
```js
return text.includes('比例') && (text.includes('时长') || text.includes('30s'));
```
复位后的会话历史里恰好残留这些词 → 误判"面板已打开" → 不点触发按钮 →
后面 `input[type=range]/[role=slider]` 找不到 → 抛"未找到时长滑块"。
每成功一条，历史多一条带这些词的记录，误判概率越来越高。

**修法（panelfix，在 asar 里，需打包重启）**：
```js
// 新增：检测真实控件，不能只看文字
const panelAlive = async () => view.webContents.executeJavaScript(`(() => {
  const vis = n => { try { const r=n.getBoundingClientRect(); return r.width>0&&r.height>0; } catch { return false; } };
  const slider = [...document.querySelectorAll('input[type=range],[role=slider]')].some(vis);
  const ratioBtn = [...document.querySelectorAll('button,[role=button],div,span')].some(n => {
    if (!vis(n)) return false;
    const t = (n.innerText||'').trim().replace(/\\s+/g,'').replace('：',':');
    return /^(16:9|9:16|1:1|4:3|3:4|2.39:1)$/.test(t);
  });
  return slider || ratioBtn;
})()`).catch(() => false);

const openTrigger = async () => {
  if (await panelAlive()) return true;         // 只有真控件存在才算打开
  ... 找触发按钮并点击 ...
  for (let i=0;i<12;i++){ await pause(250); if (await panelAlive()) return true; }
  return true;
};
```

### 症状3：15s 变成 10s

**根因**：JS 改 slider value 无效；豆包时长控件是 `div[role=slider]`，真实值在 `aria-valuenow/aria-valuetext`。
**修法**：用真实键盘事件驱动——读到滑块 max，目标达最大档时按 `End`，否则 `Home` + N 次 `ArrowRight`。
面板关闭前（Escape 前）捕获滑块值做校验。出片后 ffprobe 复核，**<14s 告警不要发布**。

### 症状4：页面一直弹首页 / 抓到旧视频

**修法（已在 asar）**：`isConversationUrl()/isHomeUrl()` 判定，跳到任意会话页不再拉回；
接受新会话页并同步 `task.pageUrl` 与 `replyBaseline.url`。按**12分钟时间窗**恢复（不是次数上限）。

### 症状5：参数确认卡卡住 `awaiting_confirmation`

**修法（已在 gen_one.py）**：轮询时检测到该状态，调 `CONFIRM_URL`(`/v1/videos/confirm`) 自动放行，
每个 task id 只确认一次。

## asar 打包与重启（改完 page-composer.js 必须做）

asar 源在 `<安装目录>/asar_diag/dist/main/main/page-composer.js`（改这里）。
网关 8788 + 桥接 3219 都跑在"傻逼豆包-多开版"主进程内，改 asar 必须**重启客户端**才生效。

```bash
# 1. 备份
cp resources/app.asar resources/app.asar.bak_before_xxx
cp asar_diag/dist/main/main/page-composer.js asar_diag/dist/main/main/page-composer.js.bak_before_xxx

# 2. 校验语法
cd asar_diag && node -c dist/main/main/page-composer.js

# 3. 打包（--unpack "*.node" 保留 better-sqlite3 原生模块）
cd asar_diag && npx asar pack . ../resources/app.asar.new --unpack "*.node"

# 4. 验证：文件列表应与旧 asar 一致，补丁字符串存在
npx asar list ../resources/app.asar.new | sort > /tmp/new.txt
npx asar list ../resources/app.asar     | sort > /tmp/old.txt
diff /tmp/old.txt /tmp/new.txt          # 应无差异
grep -a -o panelfix ../resources/app.asar.new | wc -l   # >0

# 5. 替换
cp ../resources/app.asar.new ../resources/app.asar
```

重启客户端：

```powershell
# 关闭所有进程（launcher + Doubao 子进程）
Get-Process | Where-Object {$_.ProcessName -match '傻逼豆包|Doubao'} | Stop-Process -Force

# 直接 Start-Process exe 无效（launcher 立即退出），必须经 explorer：
Start-Process explorer.exe -ArgumentList "D:\软件东东\doubao-video-workspace\傻逼豆包-多开版.exe"
```

重启后验证：`curl http://127.0.0.1:8788/health` 与 `:3219/accounts` 恢复，7 账号登录态保留。
再单跑一条确认 panelfix 生效（应一次成功，不再报"未找到时长滑块"）。

## 账号池与额度规则（硬性）

- 选账号按 **1→7 顺序**，第一个可用者中标；每账号每天**最多4条**视频，`videoDailyUsed>=4` 自动跳下一个；**图片不占额度**
- 每账号**固定同一会话**，绝不新建对话；会话 URL 存 `canvas-account-conversations.json`
- 账号状态看 `GET :3219/accounts`：`quota_exhausted`/used=4/4=今日无额度；`cooling`=刚提交过等冷却；
  `needs_attention 未出现输入框/未找到比例入口`=窗口停在非输入页需人工复位
- **桥接计数与页面实际额度可能不同步**：页面提示额度不足时以页面为准
- **"消息已提交但结果未确认"必须人工收片，绝不自动重发**（防重复烧额度）——gen_one 抛 `SubmittedButUnconfirmed` 即停止，退出码 2
