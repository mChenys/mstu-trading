# MSTU Monitoring Dashboard Design

**Date:** 2026-04-23

## Goal

为当前 `mstu-trading` 仓库补一个本地可运行的前端监控台，让用户可以在浏览器里查看实时行情、策略建议、持仓状态和回测概览，而不改变现有策略核心职责。

## Context

当前工程已经完成一轮策略重构，关键约定已经明确：

- `MSTR` 负责主信号判断
- `MSTU` 负责执行、仓位、止盈止损和 PnL
- 实时逻辑与回测逻辑尽量保持口径一致
- `momentum` 语义已经升级成同时支持 `VWAP 上穿` 和 `VWAP 上方延续启动`

这次新增 UI 的目标是“可视化现有能力”，而不是“重写策略系统”。

## Chosen Approach

采用 `Flask + 单页 Dashboard` 的轻量方案。

原因：

- 当前仓库是纯 Python 工程，没有前端基础设施
- 首版重点是把策略和状态可视化，而不是做复杂前端工程化
- Flask 足够轻，适合快速加一个本地监控台
- 后续如果要升级为前后端分离，也可以先复用 API 口径

## Alternatives Considered

### 1. 纯静态 HTML 页面

优点：

- 实现最快
- 不需要新增后端依赖

缺点：

- 很难展示实时数据
- 必须把 Python 结果预生成成文件，扩展性差

### 2. Flask + 单页 Dashboard

优点：

- 可以直接复用当前 Python 模块
- API 边界清晰
- 首版实现成本合理

缺点：

- 需要新增一个轻量 Web 服务层

### 3. React/Vite 前后端分离

优点：

- 交互和可扩展性最好

缺点：

- 对当前仓库过重
- 首版投入大，收益不成比例

## Architecture

新增一个很薄的 Web 聚合层，不改现有策略主文件的职责：

- `fetcher.py` 继续负责行情与 `MSTR` 趋势快照
- `strategy.py` 继续负责交易建议分析
- `trade_confirmation.py` 和 `position.json` 继续负责持仓状态
- `optimization_results.json` 继续作为回测优化结果来源
- 新增的 Web 层只做聚合与展示

首版结构建议如下：

```text
mstu-trading/
├── web_app.py                  # Flask 应用入口
├── dashboard_service.py        # 聚合 quote / signal / position / backtest summary
├── templates/
│   └── dashboard.html          # Dashboard 页面
├── static/
│   ├── dashboard.css           # 页面样式
│   └── dashboard.js            # 前端轮询与渲染
└── test_dashboard_service.py   # 聚合层与 API 测试
```

## MVP Scope

首版只覆盖两块：

### 1. 实时监控

- 当前交易时段
- `MSTU` 当前价格、涨跌幅、日内高低
- `MSTR` 当前价格、涨跌幅、趋势确认状态
- 当前策略动作：`BUY / SELL / HOLD / TIME_WINDOW_BLOCKED / OFF`
- 策略理由与信号文本
- 当前持仓和可用现金

### 2. 回测概览

- 当前推荐参数摘要
- `optimization_results.json` 的摘要信息
- 现有双标结构说明：
  - 底仓
  - 正向T
  - 反向T
  - 跨天T

## Explicit Non-Goals

首版不做这些：

- 登录与权限控制
- WebSocket 实时推送
- 浏览器内触发完整回测
- K 线图和复杂图表库
- 历史信号数据库
- 改写现有策略逻辑

## Data Flow

页面加载或轮询时：

1. 前端请求 `/api/dashboard`
2. Web 层调用聚合服务
3. 聚合服务内部：
   - 调 `get_mstu_quote()`
   - 调 `TradingStrategy().analyze(quote)`
   - 读取 `position.json`
   - 读取 `optimization_results.json`
4. 返回统一 JSON
5. 前端更新行情、信号、持仓、回测卡片

统一聚合接口优先，避免前端并发请求多个端点造成状态时间不一致。

## API Design

首版建议提供：

- `GET /`
  - 返回 dashboard 页面
- `GET /api/dashboard`
  - 返回完整聚合结果
- `GET /api/health`
  - 返回服务健康状态

如果后续需要再拆成更细接口，可以在现有聚合服务基础上扩展，但首版以一个主接口为主。

## UI Design Direction

页面采用“交易终端 + 研究台”风格：

- 深石墨色背景，不走通用 SaaS 卡片风
- 用较强的数字排版突出价格与动作状态
- 明确展示 `MSTR -> Signal` 与 `MSTU -> Execution` 这条链路
- 回测区强调“底仓 / 正向T / 反向T / 跨天T”结构

视觉上要服务于信息层级，而不是装饰性地堆组件。

## Error Handling

需要明确区分几类失败：

- 行情获取失败：页面显示“行情暂不可用”，但保留最近能读到的本地状态
- 策略分析失败：显示错误消息，不让整个页面崩掉
- `position.json` 不存在：回退成空仓默认状态
- `optimization_results.json` 不存在或格式异常：回测区显示“暂无摘要”

服务层返回结构要稳定，即使部分字段失败也要给出 `error` 和 `status`。

## Testing Strategy

首版至少补这些测试：

- 聚合服务在成功路径下返回完整结构
- 聚合服务在 quote 失败时仍返回可渲染结果
- `position.json` 缺失时返回默认持仓结构
- Flask API `/api/dashboard` 返回 200 与基础 JSON 结构

不在首版追求前端像素级测试，但要保证资源能被正确服务。

## Compatibility Notes

新增 UI 不能破坏这些约定：

- `MSTR` 仍然是主信号源
- `MSTU` 仍然是执行标的
- 实时策略逻辑仍由 `strategy.py` 主导
- 回测摘要只读，不在 UI 层重算回测

## Implementation Notes

优先做“聚合层 + 单接口 + 单页渲染”：

- 先把数据链路打通
- 再补样式和轮询
- 保持依赖最小，避免引入重量级前端栈

## Approval Record

用户已确认：

- 使用带 Python 后端的监控台
- 首版采用“实时监控 + 回测概览”的轻量 MVP
- 当前任务由单 agent 完成即可
