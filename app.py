"""
个人多账户资产管理系统 - 后端 Flask API v3.0
SQLite 数据库 + 本金/收益双台账体系
"""
import os
import uuid
import sqlite3
import hashlib
from datetime import datetime
from collections import OrderedDict
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'asset.db')

transfer_type_labels = {
    'cash_transfer': '现金互转',
    'cash_to_fund': '现金转理财',
    'fund_to_cash': '理财转现金',
    'fund_transfer': '理财互转'
}

# ========== 数据库连接 ==========
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            name TEXT NOT NULL, type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS principals (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            account_id TEXT NOT NULL, amount REAL NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'other',
            note TEXT DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );
        CREATE TABLE IF NOT EXISTS returns (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            account_id TEXT NOT NULL, amount REAL NOT NULL,
            return_type TEXT NOT NULL DEFAULT '', note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );
        CREATE TABLE IF NOT EXISTS transfers (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            from_account_id TEXT NOT NULL, to_account_id TEXT NOT NULL,
            amount REAL NOT NULL, fee REAL NOT NULL DEFAULT 0,
            transfer_type TEXT NOT NULL DEFAULT 'cash_transfer',
            note TEXT DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            date TEXT NOT NULL, time TEXT NOT NULL,
            total_principal REAL NOT NULL, total_return REAL NOT NULL,
            total_assets REAL NOT NULL, total_debt REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);
        CREATE INDEX IF NOT EXISTS idx_principals_user ON principals(user_id);
        CREATE INDEX IF NOT EXISTS idx_principals_account ON principals(account_id);
        CREATE INDEX IF NOT EXISTS idx_returns_user ON returns(user_id);
        CREATE INDEX IF NOT EXISTS idx_returns_account ON returns(account_id);
        CREATE INDEX IF NOT EXISTS idx_transfers_user ON transfers(user_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_user ON snapshots(user_id);
        CREATE TABLE IF NOT EXISTS dict_items (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            dict_type TEXT NOT NULL,
            label TEXT NOT NULL, value TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dict_items_user_type ON dict_items(user_id, dict_type);
    """)

    # ---- 迁移逻辑：为 principals / returns 添加 record_date 列 ----
    # 检查 principals 表是否有 record_date 列
    cols = [r[1] for r in db.execute("PRAGMA table_info(principals)").fetchall()]
    if 'record_date' not in cols:
        db.execute("ALTER TABLE principals ADD COLUMN record_date TEXT DEFAULT ''")
        db.execute("UPDATE principals SET record_date = substr(created_at, 1, 10) WHERE record_date = '' OR record_date IS NULL")
        db.commit()

    # 检查 returns 表是否有 record_date 列
    cols = [r[1] for r in db.execute("PRAGMA table_info(returns)").fetchall()]
    if 'record_date' not in cols:
        db.execute("ALTER TABLE returns ADD COLUMN record_date TEXT DEFAULT ''")
        db.execute("UPDATE returns SET record_date = substr(created_at, 1, 10) WHERE record_date = '' OR record_date IS NULL")
        db.commit()

    # ---- 插入默认字典数据（仅在表为空时） ----
    existing_dicts = db.execute("SELECT COUNT(*) FROM dict_items").fetchone()[0]
    if existing_dicts == 0:
        now_iso = datetime.now().isoformat()
        default_dicts = [
            # account_type
            ('account_type', 'bank', '银行存款', 1),
            ('account_type', 'fund', '基金理财', 2),
            ('account_type', 'stock', '股票账户', 3),
            ('account_type', 'cash', '现金零钱', 4),
            ('account_type', 'debt', '信贷负债', 5),
            # principal_source
            ('principal_source', 'initial', '初始存量', 1),
            ('principal_source', 'salary', '工资收入', 2),
            ('principal_source', 'side_income', '兼职收入', 3),
            ('principal_source', 'red_packet', '红包', 4),
            ('principal_source', 'gift', '馈赠', 5),
            ('principal_source', 'transfer', '账户划转', 6),
            ('principal_source', 'spend', '消费支出', 7),
            ('principal_source', 'other', '其他', 8),
            # return_type
            ('return_type', 'fund_dividend', '基金分红', 1),
            ('return_type', 'interest', '理财利息', 2),
            ('return_type', 'stock_gain', '股票浮盈', 3),
            ('return_type', 'deposit_interest', '存款利息', 4),
            ('return_type', 'fund_loss', '理财亏损', 5),
            ('return_type', 'stock_loss', '股票浮亏', 6),
            # transfer_type
            ('transfer_type', 'cash_transfer', '现金互转', 1),
            ('transfer_type', 'cash_to_fund', '现金转理财', 2),
            ('transfer_type', 'fund_to_cash', '理财转现金', 3),
            ('transfer_type', 'fund_transfer', '理财互转', 4),
        ]
        # 为系统默认字典使用固定 user_id '__system__'，与用户无关
        system_user = '__system__'
        for dict_type, value, label, sort_order in default_dicts:
            db.execute(
                "INSERT OR IGNORE INTO dict_items (id, user_id, dict_type, label, value, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), system_user, dict_type, label, value, sort_order, now_iso)
            )
        db.commit()

    db.commit()
    db.close()

# ========== 工具函数 ==========
def hash_password(pwd):
    return hashlib.sha256(pwd.encode('utf-8')).hexdigest()

def fmt(val):
    return round(float(val), 2)

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ========== 统计引擎 ==========
def calc_stats(user_id):
    db = get_db()
    accounts = db.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)).fetchall()
    principals = db.execute("SELECT * FROM principals WHERE user_id=?", (user_id,)).fetchall()
    returns = db.execute("SELECT * FROM returns WHERE user_id=?", (user_id,)).fetchall()

    total_principal = 0.0
    total_debt = 0.0
    structure = {}
    for a in accounts:
        amt = fmt(a['amount'])
        if a['type'] == 'debt':
            total_debt += abs(amt)
        else:
            total_principal += amt
            structure[a['type']] = fmt(structure.get(a['type'], 0) + amt)

    total_return = fmt(sum(r['amount'] for r in returns))
    total_assets = fmt(total_principal + total_return)

    holding_principal = 0.0
    for a in accounts:
        if a['type'] in ('fund', 'stock'):
            holding_principal += fmt(a['amount'])

    holding_rate = round((total_return / holding_principal) * 100, 2) if holding_principal > 0 else 0

    pos_returns = [r for r in returns if r['amount'] > 0]
    first_return = min((datetime.fromisoformat(r['created_at']) for r in pos_returns), default=None)
    if first_return and holding_principal > 0:
        days = max((datetime.now() - first_return).days, 1)
        annual_rate = round(holding_rate * (365 / days), 2)
    else:
        annual_rate = 0

    debt_ratio = round((total_debt / total_assets) * 100, 1) if total_assets > 0 else 0

    principal_by_source = {}
    for p in principals:
        key = p['source_type'] if p['source_type'] else 'other'
        principal_by_source[key] = fmt(principal_by_source.get(key, 0) + p['amount'])

    return_by_account = {}
    for r in returns:
        key = r['account_id']
        return_by_account[key] = fmt(return_by_account.get(key, 0) + r['amount'])

    acc_map = {a['id']: a['name'] for a in accounts}

    return {
        'total_principal': total_principal,
        'total_return': total_return,
        'total_assets': total_assets,
        'total_debt': fmt(total_debt),
        'holding_principal': fmt(holding_principal),
        'holding_rate': holding_rate,
        'annual_rate': annual_rate,
        'debt_ratio': debt_ratio,
        'account_count': len(accounts),
        'principal_count': len(principals),
        'return_count': len(returns),
        'structure': structure,
        'principal_by_source': principal_by_source,
        'return_by_account': {acc_map.get(k, '未知'): v for k, v in return_by_account.items()},
        'first_return_date': first_return.isoformat() if first_return else None
    }

# ========== 资产快照 ==========
def record_snapshot(user_id):
    stats = calc_stats(user_id)
    db = get_db()
    db.execute("""
        INSERT INTO snapshots (id, user_id, date, time, total_principal, total_return, total_assets, total_debt, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()), user_id,
        datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M:%S'),
        stats['total_principal'], stats['total_return'], stats['total_assets'],
        stats['total_debt'], datetime.now().isoformat()
    ))
    db.commit()

# ========== 用户 API ==========
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '用户名已存在'}), 409
    uid = str(uuid.uuid4())
    db.execute("INSERT INTO users (id, username, password, created_at) VALUES (?, ?, ?, ?)",
               (uid, username, hash_password(password), datetime.now().isoformat()))
    db.commit()
    return jsonify({'success': True, 'message': '注册成功', 'user': {'id': uid, 'username': username}})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    db = get_db()
    existing = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not existing:
        return jsonify({'success': False, 'message': '该用户未注册'}), 401
    if existing['password'] != hash_password(password):
        return jsonify({'success': False, 'message': '密码错误，请重新输入'}), 401
    return jsonify({'success': True, 'message': '登录成功',
                    'user': {'id': existing['id'], 'username': existing['username']}})

# ========== 账户 API ==========
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    user_id = request.args.get('user_id', '')
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400
    db = get_db()
    accounts = db.execute("SELECT * FROM accounts WHERE user_id=? ORDER BY created_at", (user_id,)).fetchall()
    return jsonify({'success': True, 'accounts': rows_to_list(accounts)})

@app.route('/api/accounts', methods=['POST'])
def add_account():
    data = request.get_json()
    user_id = data.get('user_id', '')
    name = data.get('name', '').strip()
    acc_type = data.get('type', 'bank')
    amount = fmt(data.get('amount', 0))
    if not user_id or not name:
        return jsonify({'success': False, 'message': '缺少必填字段'}), 400
    if acc_type == 'debt':
        amount = -abs(amount)
    acc_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("INSERT INTO accounts (id, user_id, name, type, amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
               (acc_id, user_id, name, acc_type, amount, now))
    # 自动生成初始存量本金记录
    if amount > 0:
        db.execute("INSERT INTO principals (id, user_id, account_id, amount, source_type, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (str(uuid.uuid4()), user_id, acc_id, amount, 'initial', '初始存量资金', now))
    db.commit()
    record_snapshot(user_id)
    return jsonify({'success': True, 'message': '账户添加成功',
                    'account': {'id': acc_id, 'user_id': user_id, 'name': name, 'type': acc_type, 'amount': amount, 'created_at': now}})

@app.route('/api/accounts/<acc_id>', methods=['PUT'])
def update_account(acc_id):
    data = request.get_json()
    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE id=?", (acc_id,)).fetchone()
    if not acc:
        return jsonify({'success': False, 'message': '账户不存在'}), 404
    updates = []
    params = []
    if 'name' in data:
        updates.append("name=?")
        params.append(data['name'])
    if 'type' in data:
        updates.append("type=?")
        params.append(data['type'])
    if 'amount' in data:
        amount = fmt(data['amount'])
        if data.get('type', acc['type']) == 'debt':
            amount = -abs(amount)
        updates.append("amount=?")
        params.append(amount)
    if updates:
        params.append(acc_id)
        db.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id=?", params)
        db.commit()
    acc = db.execute("SELECT * FROM accounts WHERE id=?", (acc_id,)).fetchone()
    return jsonify({'success': True, 'message': '更新成功', 'account': row_to_dict(acc)})

@app.route('/api/accounts/<acc_id>', methods=['DELETE'])
def delete_account(acc_id):
    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE id=?", (acc_id,)).fetchone()
    user_id = acc['user_id'] if acc else ''
    db.execute("DELETE FROM principals WHERE account_id=?", (acc_id,))
    db.execute("DELETE FROM returns WHERE account_id=?", (acc_id,))
    db.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
    db.commit()
    if user_id:
        record_snapshot(user_id)
    return jsonify({'success': True, 'message': '删除成功，关联本金和收益记录已同步清理'})

# ========== 本金台账 API ==========
@app.route('/api/principals', methods=['GET'])
def get_principals():
    user_id = request.args.get('user_id', '')
    source_type = request.args.get('source_type', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400

    db = get_db()
    query = "SELECT p.*, a.name as account_name FROM principals p LEFT JOIN accounts a ON p.account_id=a.id WHERE p.user_id=?"
    params = [user_id]
    if source_type:
        query += " AND p.source_type=?"
        params.append(source_type)
    if start_date:
        query += " AND p.record_date>=?"
        params.append(start_date)
    if end_date:
        query += " AND p.record_date<=?"
        params.append(end_date)
    query += " ORDER BY p.record_date DESC, p.created_at DESC"
    principals = db.execute(query, params).fetchall()
    return jsonify({'success': True, 'principals': rows_to_list(principals)})

@app.route('/api/principals', methods=['POST'])
def add_principal():
    data = request.get_json()
    user_id = data.get('user_id', '')
    account_id = data.get('account_id', '')
    amount = fmt(data.get('amount', 0))
    source_type = data.get('source_type', 'other')
    note = data.get('note', '').strip()
    if not user_id or not account_id:
        return jsonify({'success': False, 'message': '缺少必填字段'}), 400
    if amount == 0:
        return jsonify({'success': False, 'message': '金额不能为0'}), 400

    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (account_id, user_id)).fetchone()
    if acc and acc['type'] != 'debt':
        new_amount = fmt(acc['amount'] + amount)
        if new_amount < 0:
            return jsonify({'success': False, 'message': '账户余额不足，无法支出'}), 400
        db.execute("UPDATE accounts SET amount=? WHERE id=?", (new_amount, account_id))

    pid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    record_date = data.get('record_date', datetime.now().strftime('%Y-%m-%d'))
    db.execute("INSERT INTO principals (id, user_id, account_id, amount, source_type, note, created_at, record_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (pid, user_id, account_id, amount, source_type, note, now, record_date))
    db.commit()
    record_snapshot(user_id)
    return jsonify({'success': True, 'message': '本金录入成功',
                    'principal': {'id': pid, 'user_id': user_id, 'account_id': account_id,
                                  'amount': amount, 'source_type': source_type, 'note': note, 'created_at': now, 'record_date': record_date}})

@app.route('/api/principals/<p_id>', methods=['DELETE'])
def delete_principal(p_id):
    db = get_db()
    p = db.execute("SELECT * FROM principals WHERE id=?", (p_id,)).fetchone()
    if p:
        acc = db.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (p['account_id'], p['user_id'])).fetchone()
        if acc and acc['type'] != 'debt':
            db.execute("UPDATE accounts SET amount=? WHERE id=?", (fmt(acc['amount'] - p['amount']), p['account_id']))
        db.execute("DELETE FROM principals WHERE id=?", (p_id,))
        db.commit()
        record_snapshot(p['user_id'])
    return jsonify({'success': True, 'message': '删除成功'})

# ========== 收益台账 API ==========
@app.route('/api/returns', methods=['GET'])
def get_returns():
    user_id = request.args.get('user_id', '')
    account_id = request.args.get('account_id', '')
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400
    db = get_db()
    query = "SELECT r.*, a.name as account_name FROM returns r LEFT JOIN accounts a ON r.account_id=a.id WHERE r.user_id=?"
    params = [user_id]
    if account_id:
        query += " AND r.account_id=?"
        params.append(account_id)
    query += " ORDER BY r.record_date DESC, r.created_at DESC"
    returns = db.execute(query, params).fetchall()
    return jsonify({'success': True, 'returns': rows_to_list(returns)})

@app.route('/api/returns', methods=['POST'])
def add_return():
    data = request.get_json()
    user_id = data.get('user_id', '')
    account_id = data.get('account_id', '')
    amount = fmt(data.get('amount', 0))
    return_type = data.get('return_type', '')
    note = data.get('note', '').strip()
    if not user_id or not account_id:
        return jsonify({'success': False, 'message': '缺少必填字段'}), 400
    if amount == 0:
        return jsonify({'success': False, 'message': '收益金额不能为0'}), 400

    rid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    record_date = data.get('record_date', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()
    db.execute("INSERT INTO returns (id, user_id, account_id, amount, return_type, note, created_at, record_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (rid, user_id, account_id, amount, return_type, note, now, record_date))
    db.commit()
    record_snapshot(user_id)
    return jsonify({'success': True, 'message': '收益录入成功',
                    'return': {'id': rid, 'user_id': user_id, 'account_id': account_id,
                               'amount': amount, 'return_type': return_type, 'note': note, 'created_at': now, 'record_date': record_date}})

@app.route('/api/returns/<ret_id>', methods=['DELETE'])
def delete_return(ret_id):
    db = get_db()
    ret = db.execute("SELECT * FROM returns WHERE id=?", (ret_id,)).fetchone()
    if ret:
        db.execute("DELETE FROM returns WHERE id=?", (ret_id,))
        db.commit()
        record_snapshot(ret['user_id'])
    return jsonify({'success': True, 'message': '删除成功'})

# ========== 资产划转 API ==========
@app.route('/api/transfers', methods=['GET'])
def get_transfers():
    user_id = request.args.get('user_id', '')
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400
    db = get_db()
    transfers = db.execute("""
        SELECT t.*, fa.name as from_account_name, ta.name as to_account_name
        FROM transfers t
        LEFT JOIN accounts fa ON t.from_account_id=fa.id
        LEFT JOIN accounts ta ON t.to_account_id=ta.id
        WHERE t.user_id=?
        ORDER BY t.created_at DESC
    """, (user_id,)).fetchall()
    result = rows_to_list(transfers)
    for t in result:
        t['transfer_type_label'] = transfer_type_labels.get(t['transfer_type'], t['transfer_type'])
    return jsonify({'success': True, 'transfers': result})

@app.route('/api/transfers', methods=['POST'])
def add_transfer():
    data = request.get_json()
    user_id = data.get('user_id', '')
    from_account_id = data.get('from_account_id', '')
    to_account_id = data.get('to_account_id', '')
    amount = fmt(data.get('amount', 0))
    fee = fmt(data.get('fee', 0))
    transfer_type = data.get('transfer_type', 'cash_transfer')
    note = data.get('note', '').strip()

    if not user_id or not from_account_id or not to_account_id:
        return jsonify({'success': False, 'message': '缺少必填字段'}), 400
    if from_account_id == to_account_id:
        return jsonify({'success': False, 'message': '转出和转入账户不能相同'}), 400
    if amount <= 0:
        return jsonify({'success': False, 'message': '划转金额必须大于0'}), 400
    if fee < 0:
        return jsonify({'success': False, 'message': '手续费不能为负数'}), 400

    db = get_db()
    from_acc = db.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (from_account_id, user_id)).fetchone()
    to_acc = db.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (to_account_id, user_id)).fetchone()
    if not from_acc or not to_acc:
        return jsonify({'success': False, 'message': '账户不存在'}), 404

    total_out = amount + fee
    if from_acc['amount'] < total_out:
        return jsonify({'success': False, 'message': f'转出账户余额不足（需 ¥{total_out}，含手续费 ¥{fee}）'}), 400

    db.execute("UPDATE accounts SET amount=? WHERE id=?", (fmt(from_acc['amount'] - total_out), from_account_id))
    db.execute("UPDATE accounts SET amount=? WHERE id=?", (fmt(to_acc['amount'] + amount), to_account_id))

    tid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db.execute("INSERT INTO transfers (id, user_id, from_account_id, to_account_id, amount, fee, transfer_type, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (tid, user_id, from_account_id, to_account_id, amount, fee, transfer_type, note, now))
    db.commit()
    record_snapshot(user_id)
    return jsonify({'success': True, 'message': '划转成功',
                    'transfer': {'id': tid, 'user_id': user_id, 'from_account_id': from_account_id,
                                 'to_account_id': to_account_id, 'amount': amount, 'fee': fee,
                                 'transfer_type': transfer_type, 'note': note, 'created_at': now}})

@app.route('/api/transfers/<t_id>', methods=['DELETE'])
def delete_transfer(t_id):
    db = get_db()
    t = db.execute("SELECT * FROM transfers WHERE id=?", (t_id,)).fetchone()
    if not t:
        return jsonify({'success': False, 'message': '划转记录不存在'}), 404

    total_out = t['amount'] + t['fee']
    db.execute("UPDATE accounts SET amount=amount+? WHERE id=? AND user_id=?", (total_out, t['from_account_id'], t['user_id']))
    db.execute("UPDATE accounts SET amount=amount-? WHERE id=? AND user_id=?", (t['amount'], t['to_account_id'], t['user_id']))
    db.execute("DELETE FROM transfers WHERE id=?", (t_id,))
    db.commit()
    record_snapshot(t['user_id'])
    return jsonify({'success': True, 'message': '划转记录已删除，余额已回滚'})

# ========== 快照 API ==========
@app.route('/api/snapshots', methods=['GET'])
def get_snapshots():
    user_id = request.args.get('user_id', '')
    period = request.args.get('period', 'day')
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400
    db = get_db()
    snapshots = db.execute("SELECT * FROM snapshots WHERE user_id=? ORDER BY created_at", (user_id,)).fetchall()
    result = rows_to_list(snapshots)

    if period == 'day':
        aggregated = result
    else:
        grouped = OrderedDict()
        for s in result:
            dt = datetime.fromisoformat(s['created_at'])
            if period == 'week':
                key = dt.strftime('%Y-W%W')
            elif period == 'month':
                key = dt.strftime('%Y-%m')
            elif period == 'year':
                key = dt.strftime('%Y')
            else:
                key = dt.strftime('%Y-%m-%d')
            grouped[key] = s
        aggregated = list(grouped.values())
    return jsonify({'success': True, 'snapshots': aggregated})

# ========== 统计 API ==========
@app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get('user_id', '')
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400
    stats = calc_stats(user_id)
    return jsonify({'success': True, 'stats': stats})

# ========== 数据字典 API ==========
@app.route('/api/dicts', methods=['GET'])
def get_dicts():
    user_id = request.args.get('user_id', '')
    dict_type = request.args.get('dict_type', '')
    db = get_db()
    query = "SELECT * FROM dict_items WHERE 1=1"
    params = []
    # 字典查询支持系统默认 + 用户自定义，如果传了 user_id 则同时查系统默认和用户自定义
    if user_id:
        query += " AND (user_id=? OR user_id='__system__')"
        params.append(user_id)
    if dict_type:
        query += " AND dict_type=?"
        params.append(dict_type)
    query += " ORDER BY sort_order ASC, created_at ASC"
    items = db.execute(query, params).fetchall()
    return jsonify({'success': True, 'items': rows_to_list(items)})

@app.route('/api/dicts', methods=['POST'])
def add_dict():
    data = request.get_json()
    user_id = data.get('user_id', '')
    dict_type = data.get('dict_type', '')
    label = data.get('label', '').strip()
    value = data.get('value', '').strip()
    if not user_id or not dict_type or not label or not value:
        return jsonify({'success': False, 'message': '缺少必填字段'}), 400
    did = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("INSERT INTO dict_items (id, user_id, dict_type, label, value, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (did, user_id, dict_type, label, value, 0, now))
    db.commit()
    return jsonify({'success': True, 'message': '字典项添加成功',
                    'item': {'id': did, 'user_id': user_id, 'dict_type': dict_type, 'label': label, 'value': value, 'sort_order': 0, 'created_at': now}})

@app.route('/api/dicts/<did>', methods=['PUT'])
def update_dict(did):
    data = request.get_json()
    db = get_db()
    d = db.execute("SELECT * FROM dict_items WHERE id=?", (did,)).fetchone()
    if not d:
        return jsonify({'success': False, 'message': '字典项不存在'}), 404
    updates = []
    params = []
    if 'label' in data:
        updates.append("label=?")
        params.append(data['label'].strip())
    if 'value' in data:
        updates.append("value=?")
        params.append(data['value'].strip())
    if 'sort_order' in data:
        updates.append("sort_order=?")
        params.append(int(data['sort_order']))
    if updates:
        params.append(did)
        db.execute(f"UPDATE dict_items SET {', '.join(updates)} WHERE id=?", params)
        db.commit()
    d = db.execute("SELECT * FROM dict_items WHERE id=?", (did,)).fetchone()
    return jsonify({'success': True, 'message': '更新成功', 'dict': row_to_dict(d)})

@app.route('/api/dicts/<did>', methods=['DELETE'])
def delete_dict(did):
    db = get_db()
    d = db.execute("SELECT * FROM dict_items WHERE id=?", (did,)).fetchone()
    if not d:
        return jsonify({'success': False, 'message': '字典项不存在'}), 404
    db.execute("DELETE FROM dict_items WHERE id=?", (did,))
    db.commit()
    return jsonify({'success': True, 'message': '删除成功'})

# ========== 重置数据 API ==========
@app.route('/api/reset-data', methods=['POST'])
def reset_data():
    data = request.get_json()
    user_id = data.get('user_id', '').strip()
    if not user_id:
        return jsonify({'success': False, 'message': '缺少 user_id'}), 400
    db = get_db()
    # 后端二次确认：检查用户是否存在
    user = db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    # 记录重置操作日志（后端确认）
    print(f"[RESET] 用户 {user_id} 请求重置数据，已确认执行")
    # 删除所有账户、本金、收益、划转、快照数据，保留用户账号
    db.execute("DELETE FROM transfers WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM returns WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM principals WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM accounts WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM snapshots WHERE user_id=?", (user_id,))
    # 删除用户自定义字典（保留系统默认）
    db.execute("DELETE FROM dict_items WHERE user_id=? AND user_id != '__system__'", (user_id,))
    db.commit()
    return jsonify({'success': True, 'message': '数据重置成功，所有账户、本金、收益、划转、快照数据已清除'})

# ========== 单账户资产历史 API ==========
@app.route('/api/accounts/<acc_id>/history', methods=['GET'])
def get_account_history(acc_id):
    user_id = request.args.get('user_id', '')
    if not user_id or not acc_id:
        return jsonify({'success': False, 'message': '缺少 user_id 或 acc_id'}), 400
    db = get_db()
    # 验证账户存在
    acc = db.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (acc_id, user_id)).fetchone()
    if not acc:
        return jsonify({'success': False, 'message': '账户不存在'}), 404

    # 获取该账户所有本金记录，按 record_date 排序
    principals = db.execute(
        "SELECT record_date, amount FROM principals WHERE account_id=? AND user_id=? ORDER BY record_date ASC, created_at ASC",
        (acc_id, user_id)
    ).fetchall()

    # 获取该账户所有收益记录，按 record_date 排序
    returns = db.execute(
        "SELECT record_date, amount FROM returns WHERE account_id=? AND user_id=? ORDER BY record_date ASC, created_at ASC",
        (acc_id, user_id)
    ).fetchall()

    # 构建日期范围：从有记录的最早日期到今天，最多30天
    today = datetime.now().strftime('%Y-%m-%d')
    all_dates = set()
    for p in principals:
        if p['record_date']:
            all_dates.add(p['record_date'])
    for r in returns:
        if r['record_date']:
            all_dates.add(r['record_date'])
    all_dates.add(today)

    if not all_dates:
        return jsonify({'success': True, 'dates': [], 'principal_balance': [], 'return_cumulative': [], 'total': []})

    min_date = min(all_dates)
    max_date = min(today, max(all_dates))

    # 生成日期序列（最多30天）
    from datetime import timedelta
    start_dt = datetime.strptime(min_date, '%Y-%m-%d')
    end_dt = datetime.strptime(max_date, '%Y-%m-%d')
    date_list = []
    current = start_dt
    while current <= end_dt:
        date_list.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    # 只取最近30天
    if len(date_list) > 30:
        date_list = date_list[-30:]

    # 按日期聚合本金
    principal_by_date = {}
    for p in principals:
        d = p['record_date'] or ''
        if not d:
            continue
        principal_by_date[d] = principal_by_date.get(d, 0) + p['amount']

    # 按日期聚合收益
    return_by_date = {}
    for r in returns:
        d = r['record_date'] or ''
        if not d:
            continue
        return_by_date[d] = return_by_date.get(d, 0) + r['amount']

    # 逐日累加
    principal_balance_list = []
    return_cumulative_list = []
    total_list = []
    cum_principal = 0.0
    cum_return = 0.0
    for d in date_list:
        cum_principal += principal_by_date.get(d, 0)
        cum_return += return_by_date.get(d, 0)
        principal_balance_list.append(fmt(cum_principal))
        return_cumulative_list.append(fmt(cum_return))
        total_list.append(fmt(cum_principal + cum_return))

    return jsonify({
        'success': True,
        'dates': date_list,
        'principal_balance': principal_balance_list,
        'return_cumulative': return_cumulative_list,
        'total': total_list
    })

# ========== 静态文件 ==========
@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    init_db()
    print('=' * 50)
    print('  个人多账户资产管理系统 v3.0 (SQLite)')
    print('  访问 http://localhost:5000')
    print('=' * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)