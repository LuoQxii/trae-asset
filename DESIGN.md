# 个人多账户资产管理系统 v3.1 设计文档

## 1. 项目概述

### 1.1 目标
为个人用户提供多账户资产统一管理工具，支持本金与收益双台账体系、资产内部划转、支出记录、资产走势追踪等完整记账功能。

### 1.2 技术栈
| 层级 | 技术 |
|------|------|
| 后端 | Python 3 + Flask + SQLite3 |
| 前端 | 原生 HTML5 + CSS3 + Vanilla JS |
| 图表 | ECharts 5 (CDN) |
| 数据存储 | SQLite (WAL 模式) |

---

## 2. 系统架构

### 2.1 目录结构
```
asset-demo/
├── app.py              # Flask 后端入口
├── static/
│   └── index.html      # 单页应用前端
├── data/
│   ├── asset.db        # SQLite 主数据库
│   └── *.json          # 旧版数据备份
└── DESIGN.md           # 本文档
```

### 2.2 架构模式
- **前后端分离**：RESTful API + 单页应用
- **数据持久化**：SQLite 数据库，WAL 模式支持并发
- **无外键级联**：应用层处理级联删除（兼容 SQLite 外键约束）

---

## 3. 数据库设计

### 3.1 实体关系

```
users (1) ───< accounts (N)
users (1) ───< principals (N)
users (1) ───< returns (N)
users (1) ───< transfers (N)
users (1) ───< snapshots (N)
users (1) ───< dict_items (N)
accounts (1) ───< principals (N)
accounts (1) ───< returns (N)
transfers: accounts (from) → accounts (to)
```

### 3.2 表结构

#### users（用户表）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| username | TEXT | UNIQUE, NOT NULL | 用户名 |
| password | TEXT | NOT NULL | SHA256 哈希 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

#### accounts（账户表）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| name | TEXT | NOT NULL | 账户名称 |
| type | TEXT | NOT NULL | bank/fund/stock/cash/debt |
| amount | REAL | NOT NULL DEFAULT 0 | 当前本金余额 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**账户类型说明**（通过数据字典自定义）：
- `bank`：银行卡
- `fund`：基金/理财产品
- `stock`：股票账户
- `cash`：现金/零钱
- `debt`：负债（金额自动取负）

#### principals（本金台账）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| account_id | TEXT | FK → accounts | 关联账户 |
| amount | REAL | NOT NULL | 金额（正数=收入，负数=支出） |
| source_type | TEXT | NOT NULL DEFAULT 'other' | 类型（关联数据字典） |
| note | TEXT | DEFAULT '' | 备注 |
| record_date | TEXT | DEFAULT '' | 记录日期 YYYY-MM-DD |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**本金收入类型**（dict_type=`principal_income`）：
- `initial`：初始存量
- `salary`：工资收入
- `side_income`：兼职收入
- `red_packet`：红包
- `gift`：馈赠
- `transfer`：账户划转
- `other`：其他

**本金支出类型**（dict_type=`principal_spend`）：
- `spend`：消费支出
- `transfer_out`：转账给他人
- `repay`：还信用卡
- `other`：其他

#### returns（收益台账）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| account_id | TEXT | FK → accounts | 关联账户 |
| amount | REAL | NOT NULL | 金额（正数=盈利，负数=亏损） |
| return_type | TEXT | NOT NULL DEFAULT '' | 收益类型（关联数据字典） |
| note | TEXT | DEFAULT '' | 备注 |
| record_date | TEXT | DEFAULT '' | 记录日期 YYYY-MM-DD |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**收益类型**（dict_type=`return_type`）：
- `fund_dividend`：基金分红
- `interest`：理财利息
- `stock_gain`：股票浮盈
- `deposit_interest`：存款利息
- `fund_loss`：理财亏损
- `stock_loss`：股票浮亏

#### transfers（资产划转表）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| from_account_id | TEXT | NOT NULL | 转出账户 |
| to_account_id | TEXT | NOT NULL | 转入账户 |
| amount | REAL | NOT NULL | 划转金额 |
| fee | REAL | NOT NULL DEFAULT 0 | 手续费 |
| transfer_type | TEXT | NOT NULL DEFAULT 'cash_transfer' | 划转类型 |
| note | TEXT | DEFAULT '' | 备注 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**划转类型**（dict_type=`transfer_type`）：
- `cash_transfer`：现金互转
- `cash_to_fund`：现金转理财
- `fund_to_cash`：理财转现金
- `fund_transfer`：理财互转

#### snapshots（资产快照表）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| date | TEXT | NOT NULL | 日期 YYYY-MM-DD |
| time | TEXT | NOT NULL | 时间 HH:MM:SS |
| total_principal | REAL | NOT NULL | 总本金 |
| total_return | REAL | NOT NULL | 累计收益 |
| total_assets | REAL | NOT NULL | 总资产 |
| total_debt | REAL | NOT NULL | 负债总额 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

#### dict_items（数据字典表）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| dict_type | TEXT | NOT NULL | 字典类型 |
| label | TEXT | NOT NULL | 显示名称 |
| value | TEXT | NOT NULL | 值（英文键） |
| sort_order | INTEGER | DEFAULT 0 | 排序权重 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**字典类型枚举**：
- `account_type`：账户类型
- `principal_income`：本金收入类型
- `principal_spend`：本金支出类型
- `return_type`：收益类型
- `transfer_type`：划转类型

### 3.3 索引
- `idx_accounts_user` on accounts(user_id)
- `idx_principals_user` on principals(user_id)
- `idx_principals_account` on principals(account_id)
- `idx_returns_user` on returns(user_id)
- `idx_returns_account` on returns(account_id)
- `idx_transfers_user` on transfers(user_id)
- `idx_snapshots_user` on snapshots(user_id)
- `idx_dicts_user_type` on dict_items(user_id, dict_type)

---

## 4. API 设计

### 4.1 认证模块

#### POST /api/register
注册新用户
- 请求：`{username, password}`
- 响应：`{success, message, user: {id, username}}`

#### POST /api/login
用户登录
- 请求：`{username, password}`
- 响应：`{success, message, user: {id, username}}`

### 4.2 账户管理

#### GET /api/accounts?user_id={id}
获取用户账户列表（含累计收益字段 `total_return`）
- 响应：`{success, accounts: [...]}`

#### POST /api/accounts
新增账户（初始余额为 0，本金通过台账录入）
- 请求：`{user_id, name, type, amount}`
- 响应：`{success, message, account}`

#### PUT /api/accounts/{id}
更新账户信息（不修改余额，余额由台账管理）
- 请求：`{name?, type?}`
- 响应：`{success, message, account}`

#### DELETE /api/accounts/{id}
删除账户（级联删除关联本金和收益记录）
- 响应：`{success, message}`

#### GET /api/accounts/{id}/history?user_id={id}
获取单个账户的资产历史走势
- 响应：`{success, dates:[], principal_balance:[], return_cumulative:[], total:[]}`

### 4.3 数据字典

#### GET /api/dicts?user_id={id}&dict_type={type}
获取指定类型的字典项（含系统默认 + 用户自定义）
- 响应：`{success, items: [...]}`

#### POST /api/dicts
新增字典项
- 请求：`{user_id, dict_type, label, value}`
- 响应：`{success, message, item}`

#### PUT /api/dicts/{id}
修改字典项
- 请求：`{label?, value?}`
- 响应：`{success, message}`

#### DELETE /api/dicts/{id}
删除字典项
- 响应：`{success, message}`

### 4.4 本金台账

#### GET /api/principals?user_id={id}&account_id={?}&source_type={?}&start_date={?}&end_date={?}
获取本金记录列表（支持按账户严格过滤）
- 响应：`{success, principals: [...]}`

#### POST /api/principals
新增本金/支出记录
- 请求：`{user_id, account_id, amount, source_type, note, record_date}`
- amount > 0：收入，amount < 0：支出
- record_date 默认当日
- 响应：`{success, message, principal}`

#### DELETE /api/principals/{id}
删除本金记录（余额回滚）
- 响应：`{success, message}`

### 4.5 收益台账

#### GET /api/returns?user_id={id}&account_id={?}
获取收益记录列表（支持按账户严格过滤）
- 响应：`{success, returns: [...]}`

#### POST /api/returns
新增收益/亏损记录
- 请求：`{user_id, account_id, amount, return_type, note, record_date}`
- record_date 默认当日
- 响应：`{success, message, return}`

#### DELETE /api/returns/{id}
删除收益记录
- 响应：`{success, message}`

### 4.6 资产划转

#### GET /api/transfers?user_id={id}
获取划转记录列表
- 响应：`{success, transfers: [...]}`

#### POST /api/transfers
执行资产划转
- 请求：`{user_id, from_account_id, to_account_id, amount, fee, transfer_type, note}`
- 响应：`{success, message, transfer}`

#### DELETE /api/transfers/{id}
删除划转记录（余额回滚）
- 响应：`{success, message}`

### 4.7 统计与快照

#### GET /api/stats?user_id={id}
获取资产统计
- 响应：`{success, stats: {...}}`

#### GET /api/snapshots?user_id={id}&period={day|week|month|year}
获取资产快照历史
- period 参数控制聚合粒度
- 响应：`{success, snapshots: [...]}`

### 4.8 数据管理

#### POST /api/reset-data
重置当前用户所有数据（保留用户账号和系统默认字典）
- 请求：`{user_id}`
- 响应：`{success, message}`

---

## 5. 业务逻辑

### 5.1 核心公式

```
总资产 = 总本金 + 累计收益
总本金 = 所有非负债账户本金总和
累计收益 = 所有收益记录金额总和
持有收益率 = 累计收益 / 持仓本金 × 100%
年化收益率 = 持有收益率 × (365 / 持有天数)
负债率 = 负债总额 / 总资产 × 100%
```

### 5.2 本金收入流程
1. 用户在本金台账页面选择目标账户
2. 点击「+ 收入」，选择收入类型、录入金额、日期、备注
3. 后端校验：金额 > 0，类型已选
4. 更新账户余额（增加收入金额）
5. 记录快照

### 5.3 本金支出流程
1. 用户在本金台账页面选择支出账户
2. 点击「- 支出」，选择支出类型、录入金额、日期、备注
3. 后端校验：金额 > 0，类型已选，余额充足
4. 将 amount 存为负数（支出）
5. 更新账户余额（减去支出金额）
6. 记录快照

### 5.4 资产划转流程
1. 选择划转类型 → 自动过滤匹配的转出/转入账户
2. 填写划转金额和可选手续费
3. 校验：转出账户余额 >= 划转金额 + 手续费
4. 转出账户减少（金额 + 手续费）
5. 转入账户增加（金额）
6. 记录快照

### 5.5 快照机制
每次发生以下操作时自动记录快照：
- 账户增删改
- 本金录入/删除/支出
- 收益录入/删除
- 资产划转/删除

快照数据用于生成资产走势折线图。折线图默认展示最近 7 天数据，不足 7 天按实际展示，仅 1 天时显示单个标记点。

### 5.6 级联删除策略
| 操作 | 级联影响 |
|------|----------|
| 删除账户 | 同步删除该账户的本金记录和收益记录 |
| 删除本金 | 账户余额回滚（减去本金金额） |
| 删除收益 | 无余额影响（收益不修改账户余额） |
| 删除划转 | 转出账户回滚（金额+手续费），转入账户回滚（金额） |

### 5.7 账户历史折线图
- 双击账户行触发
- 查询该账户所有本金和收益记录
- 按 record_date 逐日累加，无记录日期沿用前一天余额
- 返回本金余额、累计收益、总资产三条折线
- 最多展示最近 30 天

---

## 6. 前端设计

### 6.1 页面结构

```
登录页 → 总览 → 账户管理 / 本金台账 / 收益台账 / 资产划转 / 系统设置
```

### 6.2 页面清单

| 页面 | 路由 | 功能 |
|------|------|------|
| 总览 | dashboard | 统计卡片、资产结构饼图、资产走势折线图 |
| 账户管理 | accounts | 账户列表（含本金余额+累计收益）、增删改、双击查看历史折线图 |
| 本金台账 | principals | 按账户展示本金流水、收入/支出录入、日期筛选 |
| 收益台账 | returns | 按账户展示收益流水、收益/亏损录入 |
| 资产划转 | transfers | 划转记录、四种划转类型 |
| 系统设置 | settings | 数据字典管理、重置数据、关于信息 |

### 6.3 交互设计

- **资产走势折线图**：支持日/周/月/年聚合切换，默认最近 7 天
- **指标卡片点击**：弹出对应指标的独立趋势弹窗
- **账户管理双击**：展示该账户本金余额+累计收益+总资产三条折线
- **本金台账账户选择**：顶部按钮条切换账户，下方只展示该账户流水
- **数据字典管理**：系统设置页支持增删改自定义分类

### 6.4 颜色规范

**全局统一**：资金正向增加红色，负向减少绿色

| 元素 | 正向（增加/收入/盈利） | 负向（减少/支出/亏损） |
|------|:------:|:------:|
| 金额文本 | `var(--danger)` 红色 | `var(--success)` 绿色 |
| 类型标签背景 | `#FEE2E2` 浅红 | `#D1FAE5` 浅绿 |
| 类型标签文字 | `#DC2626` 深红 | `#065F46` 深绿 |

### 6.5 响应式断点
- 桌面端：侧边栏固定，2-3 列网格
- 移动端（< 768px）：侧边栏可收起，单列布局，`main-content` 增加 `padding-top:52px` 避免汉堡按钮遮挡标题

---

## 7. 数据安全

### 7.1 密码存储
- 使用 SHA256 哈希存储，无盐值（当前实现）

### 7.2 并发安全
- SQLite WAL 模式支持读写并发
- 每个请求独立数据库连接（Flask g 对象管理）

### 7.3 数据验证
- 所有 POST/PUT 请求校验必填字段
- 金额不能为 0（本金/收益/划转）
- 支出/划转时检查余额充足性
- 同账户划转被拒绝

---

## 8. 部署说明

### 8.1 启动命令
```bash
cd asset-demo
python app.py
```

### 8.2 访问地址
- 本地：http://localhost:5000
- 局域网：http://<ip>:5000

### 8.3 数据备份
SQLite 数据库为单文件 `data/asset.db`，直接复制即可备份。

---

## 9. 版本变更记录

### v3.1（当前版本）
- 新增数据字典系统（`dict_items` 表），支持自定义账户类型、本金收入/支出类型、收益类型、划转类型
- 本金/收益台账增加 `record_date` 字段，支持录入历史日期
- 本金收入与支出分用不同字典类型（`principal_income` / `principal_spend`）
- 本金/收益台账改为以账户为基准展示，严格按账户过滤
- 账户管理界面增加累计收益列，支持双击查看账户历史折线图
- 折线图默认展示最近 7 天
- 新增重置数据 API
- 全局颜色统一：正向增加红色，负向减少绿色
- 移动端汉堡按钮遮挡修复
- 去除账户初始本金输入框，余额完全由台账管理

### v3.0
- 本金与收益双台账体系
- 资产内部划转含手续费
- 资产快照与走势追踪
- 支出记录支持
- 负债账户支持（金额自动取负）
