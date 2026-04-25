# OpenClaw Integration TODO

按价值和依赖顺序推进，默认从上到下执行。

- [x] 统一运行时状态目录与配置入口
- [x] 统一飞书消息网关
- [x] 统一 proposal / confirmation / manual execution 状态机
- [x] 引入 sqlite 结构化存储与消息事件审计
- [x] 入站 / 出站消息幂等保护
- [x] Dashboard 运维概览 `/api/ops`
- [x] 单笔 trade 全链路详情接口
- [x] 运维动作接口：手动过期 pending proposal
- [x] 自动恢复扫描：启动或巡检时批量过期 stale proposals
- [x] README 运行说明与环境变量模板更新
- [x] 将更多运维动作接入 dashboard 前端
- [x] 把 kv 镜像逐步收口到结构化表主读写
- [x] 增加更细的用户回复状态：deferred / modified / needs_clarification
- [x] 补齐多 Agent 追踪字段：`agent_source`
- [x] 增加 proposal claim / release 机制，支持 OpenClaw 与 Hermes 协作
- [x] 补充多 Agent API 与审计事件测试

## Trading Fee TODO

- [x] 抽离统一费率模块，覆盖佣金、平台使用费、交收费、SEC fee、TAF
- [x] 将手工成交确认 / proposal 确认流改成按净现金和净盈亏记账
- [x] 将实时策略买入股数改成“含手续费可买得起”的口径
- [x] 将 `CombinedStrategy` 回测净值切到真实费率口径
- [x] 为费率模型与确认链路补回归测试
- [x] 增加印花税开关与 `USD/RM` 汇率配置入口
- [ ] 根据你的真实券商账单，最终确认 `MSTU` / `NMS` 订单是否实际收取这项印花税
