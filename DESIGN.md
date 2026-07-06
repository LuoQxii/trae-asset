# 个人多账户资产管理系统 v3.0 设计文档

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
| amount | REAL | NOT NULL DEFAULT 0 | 当前余额 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**账户类型说明**：
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
| source_type | TEXT | NOT NULL DEFAULT 'other' | 来源/用途类型 |
| note | TEXT | DEFAULT '' | 备注 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**source_type 枚举**：
- `initial`：初始存量
- `salary`：工资收入
- `side_income`：兼职收入
- `red_packet`：红包
- `gift`：馈赠
- `transfer`：账户划转
- `spend`：消费支出
- `other`：其他

#### returns（收益台账）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | UUID |
| user_id | TEXT | FK → users | 所属用户 |
| account_id | TEXT | FK → accounts | 关联账户 |
| amount | REAL | NOT NULL | 金额（正数=盈利，负数=亏损） |
| return_type | TEXT | NOT NULL DEFAULT '' | 收益类型 |
| note | TEXT | DEFAULT '' | 备注 |
| created_at | TEXT | NOT NULL | ISO8601 时间 |

**return_type 枚举**：
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

**transfer_type 枚举**：
- `cash_transfer`：现金互转（银行卡 ↔ 零钱）
- `cash_to_fund`：现金转理财（买入基金/股票）
- `fund_to_cash`：理财转现金（赎回回款）
- `fund_transfer`：理财互转（基金A → 基金B）

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

### 3.3 索引
- `idx_accounts_user` on accounts(user_id)
- `idx_principals_user` on principals(user_id)
- `idx_principals_account` on principals(account_id)
- `idx_returns_user` on returns(user_id)
- `idx_returns_account` on returns(account_id)
- `idx_transfers_user` on transfers(user_id)
- `idx_snapshots_user` on snapshots(user_id)

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
获取用户账户列表
- 响应：`{success, accounts: [...]}`

#### POST /api/accounts
新增账户（自动生成本金记录）
- 请求：`{user_id, name, type, amount}`
- 响应：`{success, message, account}`

#### PUT /api/accounts/{id}
更新账户信息
- 请求：`{name?, type?, amount?}`
- 响应：`{success, message, account}`

#### DELETE /api/accounts/{id}
删除账户（级联删除关联本金和收益记录）
- 响应：`{success, message}`

### 4.3 本金台账

#### GET /api/principals?user_id={id}&source_type={?}&start_date={?}&end_date={?}
获取本金记录列表
- 响应：`{success, principals: [...]}`

#### POST /api/principals
新增本金/支出记录
- 请求：`{user_id, account_id, amount, source_type, note}`
- amount > 0：收入，amount < 0：支出
- 响应：`{success, message, principal}`

#### DELETE /api/principals/{id}
删除本金记录（余额回滚）
- 响应：`{success, message}`

### 4.4 收益台账

#### GET /api/returns?user_id={id}&account_id={?}
获取收益记录列表
- 响应：`{success, returns: [...]}`

#### POST /api/returns
新增收益/亏损记录
- 请求：`{user_id, account_id, amount, return_type, note}`
- 响应：`{success, message, return}`

#### DELETE /api/returns/{id}
删除收益记录
- 响应：`{success, message}`

### 4.5 资产划转

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

### 4.6 统计与快照

#### GET /api/stats?user_id={id}
获取资产统计
- 响应：`{success, stats: {...}}`

#### GET /api/snapshots?user_id={id}&period={day|week|month|year}
获取资产快照历史
- period 参数控制聚合粒度
- 响应：`{success, snapshots: [...]}`

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

### 5.2 本金支出流程
1. 用户选择支出账户，输入支出金额
2. 后端将 amount 存为负数
3. 检查账户余额是否充足（amount + 当前余额 >= 0）
4. 更新账户余额（减去支出金额）
5. 记录快照

### 5.3 资产划转流程
1. 选择划转类型 → 自动过滤匹配的转出/转入账户
2. 填写划转金额和可选手续费
3. 校验：转出账户余额 >= 划转金额 + 手续费
4. 转出账户减少（金额 + 手续费）
5. 转入账户增加（金额）
6. 记录快照

### 5.4 快照机制
每次发生以下操作时自动记录快照：
- 账户增删改
- 本金录入/删除/支出
- 收益录入/删除
- 资产划转/删除

快照数据用于生成资产走势折线图。

### 5.5 级联删除策略
| 操作 | 级联影响 |
|------|----------|
| 删除账户 | 同步删除该账户的本金记录和收益记录 |
| 删除本金 | 账户余额回滚（减去本金金额） |
| 删除收益 | 无余额影响（收益不修改账户余额） |
| 删除划转 | 转出账户回滚（金额+手续费），转入账户回滚（金额） |

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
| 账户管理 | accounts | 账户列表、增删改、余额调整 |
| 本金台账 | principals | 本金记录、支出记录、来源筛选、统计汇总 |
| 收益台账 | returns | 收益/亏损记录、按账户筛选 |
| 资产划转 | transfers | 划转记录、四种划转类型 |
| 系统设置 | settings | 关于信息 |

### 6.3 交互设计

- **资产走势折线图**：支持日/周/月/年聚合切换
- **指标卡片点击**：弹出对应指标的独立趋势弹窗
- **本金颜色**：收入统一红色，支出统一绿色
- **划转类型联动**：选择划转类型自动过滤匹配的账户选项

### 6.4 响应式断点
- 桌面端：侧边栏固定，2-3 列网格
- 移动端（< 768px）：侧边栏可收起，单列布局

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
