# MSTU 做T监控与回测系统

## 项目定位
这个项目不是在 `MSTU` 自身上直接做技术分析，而是采用下面这套已经调整过的结构：

- `MSTR`：负责生成主信号
- `MSTU`：负责实际执行买卖、计算持仓、止盈止损和盈亏

这样做的原因很简单：

- `MSTU` 是 `MSTR` 的 2x 做多 ETF，日内波动会被放大，还有路径依赖和衰减噪音。
- 如果直接拿 `MSTU` 的 RSI / 布林带 / MACD 做主判断，容易把杠杆噪音误当成趋势。
- 用户真实被套和做T的标的是 `MSTU`，所以最终执行、止盈止损、PnL 仍然必须落在 `MSTU`。

当前版本已经统一成：

- 实时策略：`strategy.py` 用 `MSTR` 做参考信号，`MSTU` 给出交易价格
- 回测策略：`backtest.py` 的 `CombinedStrategy` 用 `MSTR` 做 signal feed，`MSTU` 做 execution feed

另外已经从 `moomoo` 指标体系中精简接入了 3 组高价值信号：

- `VWAP 突破 + 量比 + 假突破过滤`
- `短期/长期牛熊线`
- `RSI/KDJ 变盘加分`
- `早晨之星 / 黄昏之星 / 孕线突破` 形态确认

这里是“精简接入”，不是完整复刻图形公式。目的不是把看盘界面搬进代码，而是保留最能提升胜率的结构化条件。
当前权重上，系统已经进一步聚焦高命中信号：
- 主过滤：`VWAP / 牛熊线 / EMA-MACD / KDJ`
- 辅助提示：`早晨之星 / 黄昏之星 / 孕线突破`

牛熊线现在不是单一布尔值，而是两档结构：
- 弱结构：短线底轨在长线底轨上方，且价格站上长期牛线
- 强结构：在弱结构基础上，再要求牛熊线连续确认、短线底轨上行、长线底轨上行

当前默认用法：
- 低吸允许参考弱结构
- 追涨不再要求强结构硬门槛，而是以 `VWAP + 量能 + MACD/KDJ/RSI` 为主触发，牛熊线只给趋势偏置
- 追涨也不再只认“VWAP 上穿当根”，而是允许“上穿后继续站稳 VWAP 的启动段”参与，避免 momentum 腿只剩开盘缺口一种触发场景
- 实时 `strategy.py` 和回测 `backtest.py` 现在都遵循同一条 momentum 语义：`VWAP 上穿` 和 `VWAP 上方延续启动` 都算顺势触发，不要只改其中一边

## 手续费口径
当前系统已经接入统一费率模型，默认按 `MSTU` 这类 `NMS` 美股订单计费：

- 佣金：`0.03% * 交易金额`，最低 `$0.01`
- 平台使用费：`$0.99 / 单`
- 交收费：`$0.003 / 股`，最高不超过成交金额的 `1%`
- SEC fee：`0.0000206 * 成交金额`，最低 `$0.01`，仅卖出
- TAF：`$0.000195 / 股`，最低 `$0.01`、最高 `$9.79`，仅卖出

当前默认没有启用 `RM` 计价的印花税，因为 `MSTU` 属于美股 `NMS` 标的，而印花税是否适用以及 `USD/RM` 换算口径还需要和真实券商账单再核对一次。
如果你的券商账单确认需要算这项费用，可以通过环境变量开启：

```bash
export MSTU_STAMP_DUTY_ENABLED=true
export MSTU_STAMP_DUTY_USD_TO_RM_FX=4.70
```

说明：

- `MSTU_STAMP_DUTY_ENABLED`: 是否把印花税纳入统一费率模型
- `MSTU_STAMP_DUTY_USD_TO_RM_FX`: 把成交额从 `USD` 换算到 `RM` 的汇率

## 给 OpenClaw 的交接重点
如果你是接手这个仓库的 AI agent，请先理解下面 3 条，再改代码：

1. 不要轻易改回“直接在 MSTU 上做主信号”
`MSTU` 现在主要是执行层，不是主判断层。除非你有明确的新设计，否则不要把核心指标重新绑回 `MSTU`。

2. 保持实时和回测口径一致
如果你调了实盘阈值，请同步检查：
- `config.py`
- `strategy.py`
- `backtest.py`

3. 保持双标约定不变
在回测里：
- `data0 = MSTU`
- `data1 = MSTR`

这个顺序不要改。`CombinedStrategy` 默认按这个顺序读取数据。

4. 不要删除或覆盖 `data/archive/`
分钟级历史数据有滚动窗口限制，`data/archive/` 是项目的长期资产。
后续要做 `120d`、`360d` 这类长窗口回测，依赖这里持续积累的快照。
如果要刷新数据，请使用仓库脚本：

```bash
./scripts/refresh_market_data.sh 15m 60d
```

详细规则见 [data/README.md](data/README.md)。

## 当前策略结构
### 实时策略
`strategy.py`

核心思路：

- 盘前 / 夜盘：
  - 用 `MSTR` 判断是否低开低吸或高开追涨
  - 追涨时会额外检查 `VWAP`、量比、牛熊线结构，避免假突破
  - 在 `MSTU` 上生成实际买入股数、目标价、止损价
- 盘中：
  - 优先处理跨时段仓位的止盈止损
  - 新开仓时，量价、趋势、位置、增强指标优先参考 `MSTR`
  - 实时盘中现在也会额外检查 `MSTR` 的 `EMA9/EMA21 + MACD` 是否共振，尽量与双标回测的筛选方式一致
  - 同时会吸收 `moomoo` 精简指标：
    - `VWAP 上穿 + 放量` 主要强化追涨
    - `牛熊线结构` 主要过滤趋势太差的低吸
    - `RSI/KDJ 变盘` 只做加分，不单独触发买卖
    - `早晨之星 / 黄昏之星 / 孕线突破` 只做低权重形态确认和统计，不单独触发买卖
  - 真正展示给用户的成交参考价格仍然来自 `MSTU`

### 回测策略
`backtest.py`

核心约定：

- `CombinedStrategy`：
  - `MSTR` 负责 gap / RSI / MACD / EMA / ADX 等主信号
  - `MSTU` 负责实际买卖成交
  - 当前回测已经升级成 `底仓 + T仓` 模型：
    - `base_position`：长期底仓，只做背景仓位
    - `正向T`：低买高卖
    - `反向T`：高抛已有底仓，再低位买回
    - `跨天T`：允许 T 仓跨交易日持有
  - 当前默认版本里，`反向T` 已经做了“瘦身”：
    - 默认仓位比正向T更轻
    - 必须先出现 `VWAP 下破`
    - 还要叠加 `RSI` 或 `KDJ` 顶部转弱确认
    - 并且要求盘中先有一段明显拉升、随后从高位出现一定回落
    - 这样做是为了避免系统把高抛动作做得过多，拖累整体做T收益
- `DipBuyStrategy` / `MomentumStrategy` 目前仍可单独跑，主要用于局部比较
- 推荐重点看 `CombinedStrategy`，因为它已经切到了双标结构

### 参数搜索
`optimize_backtest.py`

用途：

- 对 `CombinedStrategy` 做参数网格搜索
- 输出结果到 `optimization_results.json`

## 当前推荐参数
当前默认参数已经对齐到双标回测后的较优区间，核心参数分布如下：

- `gap_down_pct = -0.04`
- `gap_up_pct = 0.012`
- `max_chase_pct = 0.04`
- `dip_profit_pct = 0.02`
- `dip_stop_pct = 0.018`
- `mom_profit_pct = 0.018`
- `mom_stop_pct = 0.01`
- `trade_amount = 250`
- `mom_trade_amount = 750`

实时配置里也同步了一套接近的阈值，主要在：
- `config.py`

如果要继续优化，建议先以这组为基线，而不是回退到旧版本参数。

## 关键文件说明
```text
mstu-trading/
├── mstu_trading/             # 主包：真实实现都在这里
│   ├── app_runtime.py        # 状态目录 / 路径管理
│   ├── config.py             # 运行配置
│   ├── strategy/             # 实时策略与指标
│   ├── backtest/             # 回测与参数搜索
│   ├── market_data/          # 行情获取与数据归档
│   ├── trading/              # proposal / 确认 / 消息处理
│   ├── integrations/         # 飞书、scheduler、webhook daemon/worker
│   ├── web/                  # Flask app 与 dashboard 聚合层
│   └── storage/              # sqlite 持久化
├── config.py                 # 兼容入口，转发到 mstu_trading.config
├── fetcher.py                # 兼容入口，转发到 mstu_trading.market_data.fetcher
├── strategy.py               # 兼容入口，转发到 mstu_trading.strategy.realtime
├── trade_confirmation.py     # 兼容入口，转发到 mstu_trading.trading.confirmation
├── trade_message_handler.py  # 兼容入口，转发到 mstu_trading.trading.message_handler
├── scheduler.py              # 兼容入口，转发到 mstu_trading.integrations.scheduler
├── backtest.py               # 兼容入口，转发到 mstu_trading.backtest.engine
├── optimize_backtest.py      # 兼容入口，转发到 mstu_trading.backtest.optimize
├── dashboard_service.py      # 兼容入口，转发到 mstu_trading.web.dashboard_service
├── web_app.py                # 兼容入口，转发到 mstu_trading.web.app
├── webhook_worker.py         # 兼容入口，转发到 mstu_trading.integrations.webhook_worker
├── webhook_daemon.py         # 兼容入口，转发到 mstu_trading.integrations.webhook_daemon
├── templates/dashboard.html  # Dashboard 页面模板
├── static/dashboard.css      # Dashboard 样式
├── static/dashboard.js       # Dashboard 前端轮询与渲染
├── tests/                    # 当前统一测试目录
├── requirements.txt          # 项目依赖
└── test_*.py                 # 已迁移进 tests/，根目录不再保留
```

## 包结构说明
当前仓库已经完成包化，真实实现统一收口在 `mstu_trading/` 下。

- `mstu_trading/...`：真实业务代码
- 根目录 `*.py`：兼容入口，保留旧命令和旧 import 路径
- `tests/`：统一测试目录，后续默认从这里跑测试发现

这意味着：

- 如果你在读代码，优先读 `mstu_trading/`
- 如果你在跑旧命令，例如 `python backtest.py`、`python web_app.py`，仍然可以继续使用
- `scheduler.py`、`webhook_worker.py`、`webhook_daemon.py` 这些旧入口也都还保留
- 如果你在新增模块，不要再把真实实现平铺回根目录

## 环境准备
建议使用项目内虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

推荐同时准备环境变量：

```bash
cp .env.example .env
export $(grep -v '^#' .env | xargs)
```

关键变量：

- `FEISHU_WEBHOOK` / `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_GROUP_ID`
- `ALPHA_VANTAGE_KEY`
- `MSTU_TRADING_STATE_DIR`

## 常用命令
### 1. 跑组合策略回测
```bash
.venv/bin/python backtest.py --strategy combined --download --interval 15m --period 60d
```

### 2. 跑低吸 / 追涨单策略对比
```bash
.venv/bin/python backtest.py --strategy dip --download --interval 15m --period 60d
.venv/bin/python backtest.py --strategy momentum --download --interval 15m --period 60d
```

### 3. 跑参数搜索
```bash
.venv/bin/python optimize_backtest.py --interval 15m --period 60d --limit 24 --top 8
```

### 4. 跑测试
```bash
export MSTU_TRADING_STATE_DIR=/tmp/mstu-trading-state
.venv/bin/python -m unittest discover -s tests -v
```

说明：

- 现在测试默认从 `tests/` 目录发现，不再以根目录 `test_*.py` 为主
- 建议显式设置 `MSTU_TRADING_STATE_DIR`，避免测试写入默认的 `~/.openclaw/workspace/mstu-trading`
- 如果你只是临时本地跑一次，也可以直接一行：

```bash
MSTU_TRADING_STATE_DIR=/tmp/mstu-trading-state .venv/bin/python -m unittest discover -s tests -v
```

### 5. 启动本地监控台
```bash
.venv/bin/python web_app.py
```

启动后打开：

- `http://127.0.0.1:5000`

当前 Dashboard 首版包含：

- 实时监控：`MSTU` 行情、`MSTR` 趋势与当前策略动作
- 持仓状态：股数、成本、止盈止损、可用现金
- 回测概览：推荐参数和 `optimization_results.json` 摘要

### 6. 独立执行一次 Webhook 推送扫描
```bash
.venv/bin/python webhook_worker.py --json
```

说明：

- `web_app.py` 现在只负责页面展示，不再因为页面刷新触发 webhook 推送
- `webhook_worker.py` 才是独立执行推送判断与发送的入口
- 如果要做定时推送，建议由外部 cron / scheduler 定时调用 `webhook_worker.py`

### 7. 运行兼容 scheduler 入口
```bash
.venv/bin/python scheduler.py --help
.venv/bin/python scheduler.py --mode morning
```

说明：

- `scheduler.py` 仍然是兼容入口，真实实现已经迁到 `mstu_trading.integrations.scheduler`
- `--mode` 支持 `scan`、`morning`、`overnight`、`evening`、`webhook`
- 如果你只是验证入口是否正常，优先跑 `--help`

### 8. 本地后台自动运行 Webhook Worker
```bash
.venv/bin/python webhook_daemon.py
```

默认行为：

- 每 `60` 秒执行一次 `webhook_worker`
- 页面刷新不会触发推送
- 推送判断只由后台 daemon / scheduler 负责

常用用法：

```bash
.venv/bin/python webhook_daemon.py --once
.venv/bin/python webhook_daemon.py --interval 120
.venv/bin/python backtest.py --help
.venv/bin/python optimize_backtest.py --help
```

### 9. 一键启动 / 停止本地服务
```bash
./start_all.sh
./stop_all.sh
```

说明：

- `start_all.sh` 会后台启动：
  - `web_app.py`
  - `webhook_daemon.py`
- 日志文件：
  - `web_app.log`
  - `webhook_daemon.log`

## Agent 运维接口
当前已经提供的后端接口：

- `GET /api/ops`：查看 pending proposals、最近事件、最近 outbound messages
- `POST /api/ops/recover`：执行一次恢复扫描，自动过期 stale pending proposals
- `GET /api/trades/<trade_id>`：查看单笔 trade 的 proposal、position、events、outbound messages
- `POST /api/trades/<trade_id>/expire`：手动将 pending proposal 标记为 expired

当前 dashboard 也已经接入了这些能力：

- 查看 `Action Required Trades`
- 在页面里点开单笔 trade 详情
- 手动执行恢复扫描
- 在页面里直接把 proposal 标记为 expired

## 多 Agent 约定
当前这套底座已经支持同时给 OpenClaw Agent 和 Hermes Agent 运行，建议遵循下面的约定：

- 所有服务层调用都带上 `agent_source`
  - 例如 `openclaw` / `hermes` / `scheduler` / `dashboard`
- proposal 进入执行前先 claim
  - 使用 `trade_service.claim_trade(...)`
  - 领取成功后再继续做解释、跟进或自动处理
- 完成后主动 release
  - 使用 `trade_service.release_trade(...)`
  - 避免另一个 Agent 长时间看见过期 claim

当前已经支持的多 Agent 追踪字段：

- `trade_records.agent_source`
- `trade_records.claimed_by / claimed_at / claim_expires_at`
- `message_events.agent_source`
- `outbound_messages.agent_source`

对应 API：

- `POST /api/trades/<trade_id>/claim`
- `POST /api/trades/<trade_id>/release`

## 用户回复状态
除了传统的 `confirmed_by_user` / `rejected_by_user`，当前 proposal 还支持更细的协作状态：

- `deferred_by_user`：用户明确表示稍后处理，例如“先等等”
- `modified_by_user`：用户提出改价、改股数、部分执行等修改要求
- `needs_clarification`：用户要求解释、澄清后再决策

这些状态都会进入 sqlite 的 `trade_records` 与 `message_events`，可以通过 `/api/ops` 和 `/api/trades/<trade_id>` 继续追踪。

## 已完成的重要修复
### 交易链路
- 统一了跨时段仓位来源枚举，避免盘中止盈止损漏触发
- 修复了确认消息处理，支持通过 `trade_id` 和回复原文确认
- 保留交易历史，不再每次只剩 pending 记录
- 用户确认成功后，会自动通过 webhook 回群发送“已记账成功”的执行回执

### 风控与状态
- 增加了自动跨天重置日内计数
- 增加了开盘后 / 收盘前禁新开仓窗口
- 增加了 `TIME_WINDOW_BLOCKED` 状态，区分“无信号”和“有信号但被风控拦截”

### 回测框架
- 从日线回测切到日内数据
- 新增 `MSTR` 信号 / `MSTU` 执行的双标回测
- 新增参数搜索脚本，避免只靠手调
- 实时策略已补齐 `MSTR` 趋势确认过滤，减少“回测严格、实盘宽松”的口径偏差

## 后续维护建议
### 如果你要继续调策略
- 优先调 `MSTR` 信号阈值
- 再检查 `MSTU` 执行层的止盈止损是否要跟着变
- 每次调完都重新跑 `CombinedStrategy` 回测

### 如果你要替换旧代码
请确保替换后仍满足：

- 实时策略里 `MSTR` 是主信号源
- 回测里 `data0=MSTU`、`data1=MSTR`
- `trade_message_handler.py` 仍然优先走 `trade_id`
- `trade_confirmation.py` 不会清空已确认历史
- `execution_notifier.py` 仍然在确认成功后回群发送执行回执，通知失败也不能阻断落账

## 人机交互闭环
当前推荐的人机闭环时序如下：

1. `scheduler.py` 扫描并生成买入/卖出建议
2. 信号写入 `trade_log.json`，生成 `trade_id`
3. 人类在群里回复“确认”/“已买入”/“已卖出”
4. OpenClaw 将群消息转给 `trade_message_handler.py`
5. `trade_confirmation.py` 更新 `position.json` 和交易日志
6. `execution_notifier.py` 再通过 webhook 回群发送“执行成功回执”

这样群里能同时看到：
- 原始交易建议
- 人类确认
- 系统落账成功回执

### 如果你发现实盘与回测不一致
优先检查这几件事：

- `config.py` 是否已经偏离 `backtest.py` 默认参数
- `fetcher.py` 是否仍然稳定返回 `mstr` 字段
- `strategy.py` 是否被改回用 `MSTU` 做主信号

## 结论
当前仓库已经不是最初那个“直接在 MSTU 上看指标”的版本了，而是一个更合理的双标结构：

- `MSTR` 负责判断
- `MSTU` 负责执行

后续无论是 OpenClaw 还是其他 agent 接手，都建议在这个结构上继续迭代，而不是退回旧思路。
