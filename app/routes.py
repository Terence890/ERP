from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort
from . import db
from functools import wraps
import datetime
from flask import Response

try:
    import pdfkit
except Exception:
    pdfkit = None

bp = Blueprint('app', __name__)


def get_current_user():
    return session.get('user')


def role_required(roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash('Please sign in', 'danger')
                return redirect(url_for('app.login'))
            allowed = roles if isinstance(roles, (list, tuple)) else [roles]
            if user.get('role') not in allowed:
                flash('Permission denied', 'danger')
                return redirect(url_for('app.dashboard'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def log_action(conn, user_id, action, details=None):
    conn.execute('INSERT INTO audit_log (user_id, action, details) VALUES (?,?,?)', (user_id, action, details))
    conn.commit()


@bp.route('/')
def index():
    if session.get('user'):
        return redirect(url_for('app.dashboard'))
    return redirect(url_for('app.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = db.get_db()
        user = conn.execute('SELECT * FROM users WHERE username=? AND password=?', (username, password)).fetchone()
        if user:
            session['user'] = {'id': user['id'], 'username': user['username'], 'role': user['role']}
            return redirect(url_for('app.dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('app.login'))


@bp.route('/dashboard')
def dashboard():
    conn = db.get_db()
    total_items = conn.execute('SELECT COUNT(*) AS cnt FROM items').fetchone()['cnt']
    total_value_row = conn.execute('SELECT SUM(quantity * unit_cost) AS sum FROM items').fetchone()
    total_value = total_value_row['sum'] or 0
    low_stock = conn.execute('SELECT COUNT(*) AS cnt FROM items WHERE quantity <= reorder_level').fetchone()['cnt']
    transactions_today = conn.execute("SELECT COUNT(*) AS cnt FROM transactions WHERE date(date)=date('now')").fetchone()['cnt']
    categories = conn.execute('SELECT IFNULL(category, "Uncategorized") as category, SUM(quantity) as total FROM items GROUP BY category').fetchall()
    category_labels = [r['category'] for r in categories]
    category_values = [r['total'] for r in categories]
    stock_trend = [10, 20, 15, 25, 18, 30, 22]
    # Financial KPIs: revenue, expenses, net profit
    try:
        revenue_row = conn.execute("SELECT IFNULL(SUM(j.amount),0) as total FROM journal_entries j JOIN accounts a ON a.id = j.credit_account_id WHERE a.type='Revenue'").fetchone()
        revenue = revenue_row['total'] or 0
    except Exception:
        revenue = 0
    try:
        expenses_row = conn.execute("SELECT IFNULL(SUM(j.amount),0) as total FROM journal_entries j JOIN accounts a ON a.id = j.debit_account_id WHERE a.type='Expense'").fetchone()
        expenses = expenses_row['total'] or 0
    except Exception:
        expenses = 0
    net_profit = revenue - expenses

    return render_template('dashboard.html',
                           total_items=total_items,
                           total_value=total_value,
                           low_stock=low_stock,
                           transactions_today=transactions_today,
                           category_labels=category_labels,
                           category_values=category_values,
                           stock_trend=stock_trend,
                           revenue=revenue,
                           expenses=expenses,
                           net_profit=net_profit)


@bp.route('/inventory')
def inventory():
    conn = db.get_db()
    items = conn.execute('SELECT * FROM items').fetchall()
    return render_template('inventory.html', items=items)


@bp.route('/inventory/add', methods=['POST'])
def add_item():
    name = request.form.get('name')
    category = request.form.get('category') or ''
    try:
        quantity = int(request.form.get('quantity') or 0)
    except ValueError:
        quantity = 0
    try:
        reorder_level = int(request.form.get('reorder_level') or 0)
    except ValueError:
        reorder_level = 0
    try:
        unit_cost = float(request.form.get('unit_cost') or 0)
    except ValueError:
        unit_cost = 0.0

    if not name:
        flash('Name is required', 'danger')
        return redirect(url_for('app.inventory'))

    conn = db.get_db()
    conn.execute('INSERT INTO items (name, category, quantity, reorder_level, unit_cost) VALUES (?,?,?,?,?)',
                 (name, category, quantity, reorder_level, unit_cost))
    conn.commit()
    flash('Item added', 'success')
    return redirect(url_for('app.inventory'))


@bp.route('/inventory/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    conn = db.get_db()
    conn.execute('DELETE FROM items WHERE id=?', (item_id,))
    conn.commit()
    flash('Item deleted', 'success')
    return redirect(url_for('app.inventory'))


@bp.route('/reports')
def reports():
    conn = db.get_db()
    items = conn.execute('SELECT * FROM items').fetchall()
    transactions = conn.execute('''
        SELECT t.id, i.name as item_name, t.type, t.quantity, t.date
        FROM transactions t
        JOIN items i ON t.item_id = i.id
        ORDER BY t.date DESC
        LIMIT 200
    ''').fetchall()
    return render_template('reports.html', items=items, transactions=transactions)


@bp.route('/inventory/<int:item_id>/get')
def get_item(item_id):
    conn = db.get_db()
    item = conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
    if not item:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(item))


@bp.route('/inventory/<int:item_id>/edit', methods=['POST'])
def edit_item(item_id):
    name = request.form.get('name')
    category = request.form.get('category') or ''
    try:
        quantity = int(request.form.get('quantity') or 0)
    except ValueError:
        quantity = 0
    try:
        reorder_level = int(request.form.get('reorder_level') or 0)
    except ValueError:
        reorder_level = 0
    try:
        unit_cost = float(request.form.get('unit_cost') or 0)
    except ValueError:
        unit_cost = 0.0

    conn = db.get_db()
    conn.execute('UPDATE items SET name=?, category=?, quantity=?, reorder_level=?, unit_cost=? WHERE id=?',
                 (name, category, quantity, reorder_level, unit_cost, item_id))
    conn.commit()
    user_id = session.get('user', {}).get('id')
    log_action(conn, user_id, 'item_edit', f'Edited item {item_id}')
    flash('Item updated', 'success')
    return redirect(url_for('app.inventory'))


@bp.route('/inventory/<int:item_id>/transaction', methods=['POST'])
def item_transaction(item_id):
    t_type = request.form.get('type')
    try:
        qty = int(request.form.get('quantity') or 0)
    except ValueError:
        qty = 0
    if qty <= 0:
        flash('Quantity must be greater than zero', 'danger')
        return redirect(url_for('app.inventory'))

    conn = db.get_db()
    item = conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
    if not item:
        flash('Item not found', 'danger')
        return redirect(url_for('app.inventory'))

    if t_type == 'IN':
        new_qty = item['quantity'] + qty
    else:
        new_qty = item['quantity'] - qty
        if new_qty < 0:
            flash('Insufficient stock', 'danger')
            return redirect(url_for('app.inventory'))

    cur = conn.execute('INSERT INTO transactions (item_id, type, quantity, date, created_by) VALUES (?,?,?,?,?)',
                       (item_id, t_type, qty, datetime.datetime.now().isoformat(), session.get('user', {}).get('id')))
    conn.execute('UPDATE items SET quantity=? WHERE id=?', (new_qty, item_id))
    conn.commit()
    user_id = session.get('user', {}).get('id')
    log_action(conn, user_id, f'stock_{t_type.lower()}', f'Item {item_id} {t_type} {qty}')
    flash('Transaction recorded', 'success')
    return redirect(url_for('app.inventory'))


@bp.route('/inventory/<int:item_id>/ledger')
def ledger(item_id):
    conn = db.get_db()
    item = conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
    if not item:
        flash('Item not found', 'danger')
        return redirect(url_for('app.inventory'))
    transactions = conn.execute('SELECT t.*, u.username as user FROM transactions t LEFT JOIN users u ON t.created_by = u.id WHERE item_id=? ORDER BY date DESC', (item_id,)).fetchall()
    return render_template('ledger.html', item=item, transactions=transactions)


@bp.route('/suppliers')
def suppliers():
    conn = db.get_db()
    suppliers = conn.execute('SELECT * FROM suppliers').fetchall()
    return render_template('suppliers.html', suppliers=suppliers)


@bp.route('/suppliers/add', methods=['POST'])
def add_supplier():
    name = request.form.get('name')
    contact_name = request.form.get('contact_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    address = request.form.get('address')
    notes = request.form.get('notes')
    if not name:
        flash('Name is required', 'danger')
        return redirect(url_for('app.suppliers'))
    conn = db.get_db()
    cur = conn.execute('INSERT INTO suppliers (name, contact_name, email, phone, address, notes) VALUES (?,?,?,?,?,?)',
                       (name, contact_name, email, phone, address, notes))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'supplier_add', f'Added supplier {cur.lastrowid}')
    flash('Supplier added', 'success')
    return redirect(url_for('app.suppliers'))


@bp.route('/suppliers/<int:supplier_id>/edit', methods=['POST'])
def edit_supplier(supplier_id):
    conn = db.get_db()
    conn.execute('UPDATE suppliers SET name=?, contact_name=?, email=?, phone=?, address=?, notes=? WHERE id=?', (
        request.form.get('name'), request.form.get('contact_name'), request.form.get('email'), request.form.get('phone'), request.form.get('address'), request.form.get('notes'), supplier_id
    ))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'supplier_edit', f'Edited supplier {supplier_id}')
    flash('Supplier updated', 'success')
    return redirect(url_for('app.suppliers'))


@bp.route('/suppliers/<int:supplier_id>/delete', methods=['POST'])
def delete_supplier(supplier_id):
    conn = db.get_db()
    conn.execute('DELETE FROM suppliers WHERE id=?', (supplier_id,))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'supplier_delete', f'Deleted supplier {supplier_id}')
    flash('Supplier deleted', 'success')
    return redirect(url_for('app.suppliers'))


@bp.route('/purchase_orders')
def purchase_orders():
    conn = db.get_db()
    orders = conn.execute('SELECT p.*, s.name as supplier_name FROM purchase_orders p LEFT JOIN suppliers s ON p.supplier_id = s.id ORDER BY p.created_at DESC').fetchall()
    suppliers = conn.execute('SELECT id, name FROM suppliers').fetchall()
    items = conn.execute('SELECT id, name FROM items').fetchall()
    return render_template('purchase_orders.html', orders=orders, suppliers=suppliers, items=items)


@bp.route('/purchase_orders/create', methods=['POST'])
def create_purchase_order():
    supplier_id = request.form.get('supplier_id')
    item_ids = request.form.getlist('item_id[]')
    quantities = request.form.getlist('quantity[]')
    unit_costs = request.form.getlist('unit_cost[]')
    conn = db.get_db()
    cur = conn.execute('INSERT INTO purchase_orders (supplier_id, created_by, status) VALUES (?,?,?)', (supplier_id, session.get('user', {}).get('id'), 'draft'))
    po_id = cur.lastrowid
    for i, item_id in enumerate(item_ids):
        try:
            qty = int(quantities[i])
        except Exception:
            qty = 0
        try:
            uc = float(unit_costs[i])
        except Exception:
            uc = 0.0
        if item_id:
            conn.execute('INSERT INTO purchase_order_items (po_id, item_id, quantity, unit_cost) VALUES (?,?,?,?)', (po_id, item_id, qty, uc))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'po_create', f'Created PO {po_id}')
    flash('Purchase order created', 'success')
    return redirect(url_for('app.purchase_orders'))


@bp.route('/purchase_orders/<int:po_id>')
def view_purchase_order(po_id):
    conn = db.get_db()
    po = conn.execute('SELECT p.*, s.name as supplier_name FROM purchase_orders p LEFT JOIN suppliers s ON p.supplier_id = s.id WHERE p.id=?', (po_id,)).fetchone()
    items = conn.execute('SELECT pi.*, i.name FROM purchase_order_items pi JOIN items i ON pi.item_id = i.id WHERE pi.po_id=?', (po_id,)).fetchall()
    return render_template('purchase_order_view.html', po=po, items=items)


@bp.route('/purchase_orders/<int:po_id>/approve', methods=['POST'])
@role_required(['admin', 'procurement'])
def approve_purchase_order(po_id):
    conn = db.get_db()
    conn.execute('UPDATE purchase_orders SET status=?, approved_by=?, approved_at=? WHERE id=?', ('approved', session.get('user', {}).get('id'), datetime.datetime.now().isoformat(), po_id))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'po_approve', f'Approved PO {po_id}')
    flash('PO approved', 'success')
    return redirect(url_for('app.purchase_orders'))


@bp.route('/purchase_orders/<int:po_id>/receive', methods=['POST'])
@role_required(['admin', 'procurement'])
def receive_purchase_order(po_id):
    conn = db.get_db()
    items = conn.execute('SELECT * FROM purchase_order_items WHERE po_id=?', (po_id,)).fetchall()
    for it in items:
        # update item quantity and create transactions
        conn.execute('UPDATE items SET quantity = quantity + ? WHERE id=?', (it['quantity'], it['item_id']))
        conn.execute('INSERT INTO transactions (item_id, type, quantity, date, created_by) VALUES (?,?,?,?,?)', (it['item_id'], 'IN', it['quantity'], datetime.datetime.now().isoformat(), session.get('user', {}).get('id')))
    conn.execute('UPDATE purchase_orders SET status=? WHERE id=?', ('received', po_id))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'po_receive', f'Received PO {po_id}')
    flash('PO received and stock updated', 'success')
    return redirect(url_for('app.purchase_orders'))


@bp.route('/sales')
def sales():
    conn = db.get_db()
    sales = conn.execute('SELECT * FROM sales_orders ORDER BY created_at DESC').fetchall()
    items = conn.execute('SELECT id, name FROM items').fetchall()
    return render_template('sales.html', sales=sales, items=items)


@bp.route('/sales/create', methods=['POST'])
def create_sale():
    customer_name = request.form.get('customer_name')
    item_ids = request.form.getlist('item_id[]')
    quantities = request.form.getlist('quantity[]')
    unit_prices = request.form.getlist('unit_price[]')
    conn = db.get_db()
    cur = conn.execute('INSERT INTO sales_orders (customer_name, created_by, status) VALUES (?,?,?)', (customer_name, session.get('user', {}).get('id'), 'confirmed'))
    sales_id = cur.lastrowid
    total = 0
    for i, item_id in enumerate(item_ids):
        try:
            qty = int(quantities[i])
        except Exception:
            qty = 0
        try:
            up = float(unit_prices[i])
        except Exception:
            up = 0.0
        if item_id and qty > 0:
            conn.execute('INSERT INTO sales_order_items (sales_id, item_id, quantity, unit_price) VALUES (?,?,?,?)', (sales_id, item_id, qty, up))
            # reduce stock
            conn.execute('UPDATE items SET quantity = quantity - ? WHERE id=?', (qty, item_id))
            conn.execute('INSERT INTO transactions (item_id, type, quantity, date, created_by) VALUES (?,?,?,?,?)', (item_id, 'OUT', qty, datetime.datetime.now().isoformat(), session.get('user', {}).get('id')))
            total += qty * up
    # create invoice
    conn.execute('INSERT INTO invoices (sales_id, amount, status) VALUES (?,?,?)', (sales_id, total, 'unpaid'))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'sale_create', f'Created sale {sales_id}')
    flash('Sale created and stock updated; invoice generated', 'success')
    return redirect(url_for('app.sales'))


@bp.route('/invoices')
def invoices():
    conn = db.get_db()
    invs = conn.execute('SELECT i.*, s.customer_name FROM invoices i LEFT JOIN sales_orders s ON i.sales_id = s.id ORDER BY i.issued_at DESC').fetchall()
    return render_template('invoices.html', invoices=invs)


@bp.route('/invoices/<int:inv_id>/pay', methods=['POST'])
def pay_invoice(inv_id):
    conn = db.get_db()
    conn.execute('UPDATE invoices SET status=?, paid_at=? WHERE id=?', ('paid', datetime.datetime.now().isoformat(), inv_id))
    conn.commit()
    log_action(conn, session.get('user', {}).get('id'), 'invoice_pay', f'Paid invoice {inv_id}')
    flash('Invoice marked as paid', 'success')
    return redirect(url_for('app.invoices'))


@bp.route('/invoices/<int:inv_id>/print')
def invoice_print(inv_id):
    conn = db.get_db()
    inv = conn.execute('SELECT * FROM invoices WHERE id=?', (inv_id,)).fetchone()
    if not inv:
        flash('Invoice not found', 'danger')
        return redirect(url_for('app.invoices'))
    sale = None
    items = []
    if inv['sales_id']:
        sale = conn.execute('SELECT * FROM sales_orders WHERE id=?', (inv['sales_id'],)).fetchone()
        items = conn.execute('SELECT soi.*, i.name, i.unit_cost FROM sales_order_items soi JOIN items i ON soi.item_id = i.id WHERE soi.sales_id=?', (inv['sales_id'],)).fetchall()
    return render_template('invoice_print.html', invoice=inv, sale=sale, items=items)


@bp.route('/invoices/<int:inv_id>/pdf')
def invoice_pdf(inv_id):
    conn = db.get_db()
    inv = conn.execute('SELECT * FROM invoices WHERE id=?', (inv_id,)).fetchone()
    if not inv:
        flash('Invoice not found', 'danger')
        return redirect(url_for('app.invoices'))
    sale = None
    items = []
    if inv['sales_id']:
        sale = conn.execute('SELECT * FROM sales_orders WHERE id=?', (inv['sales_id'],)).fetchone()
        items = conn.execute('SELECT soi.*, i.name, i.unit_cost FROM sales_order_items soi JOIN items i ON soi.item_id = i.id WHERE soi.sales_id=?', (inv['sales_id'],)).fetchall()

    # Render HTML first
    html = render_template('invoice_print.html', invoice=inv, sale=sale, items=items)
    if not pdfkit:
        flash('PDF generation not available on server. Use browser Print → Save as PDF.', 'warning')
        return redirect(url_for('app.invoice_print', inv_id=inv_id))

    try:
        # base_url so wkhtmltopdf can resolve static files
        pdf = pdfkit.from_string(html, False, options={'enable-local-file-access': ''}, css=None)
        return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename=invoice-{inv_id}.pdf'})
    except Exception as e:
        flash('PDF generation failed: ' + str(e), 'danger')
        return redirect(url_for('app.invoice_print', inv_id=inv_id))


@bp.route('/ledger')
def ledger_index():
    conn = db.get_db()
    transactions = conn.execute('''
        SELECT t.*, i.name as item_name, u.username as user
        FROM transactions t
        LEFT JOIN items i ON t.item_id = i.id
        LEFT JOIN users u ON t.created_by = u.id
        ORDER BY date DESC
        LIMIT 500
    ''').fetchall()
    return render_template('ledger.html', transactions=transactions)


@bp.route('/accounts', methods=['GET', 'POST'])
def accounts():
    conn = db.get_db()
    if request.method == 'POST':
        name = request.form.get('name')
        acc_type = request.form.get('type')
        if not name or not acc_type:
            flash('Name and type required', 'danger')
            return redirect(url_for('app.accounts'))
        conn.execute('INSERT INTO accounts (name, type) VALUES (?,?)', (name, acc_type))
        conn.commit()
        flash('Account added', 'success')
        return redirect(url_for('app.accounts'))
    accounts = conn.execute('SELECT * FROM accounts ORDER BY type, name').fetchall()
    return render_template('accounts.html', accounts=accounts)


@bp.route('/finance/transaction', methods=['GET', 'POST'])
def finance_transaction():
    conn = db.get_db()
    accounts = conn.execute('SELECT id, name, type FROM accounts ORDER BY name').fetchall()
    if request.method == 'POST':
        t_type = request.form.get('transaction_type')
        try:
            amount = float(request.form.get('amount') or 0)
        except ValueError:
            amount = 0
        description = request.form.get('description')
        debit_id = request.form.get('debit_account')
        credit_id = request.form.get('credit_account')
        if amount <= 0 or not debit_id or not credit_id or not t_type:
            flash('Please provide transaction type, accounts and positive amount', 'danger')
            return redirect(url_for('app.finance_transaction'))
        cur = conn.execute('INSERT INTO financial_transactions (transaction_type, amount, description, user_id) VALUES (?,?,?,?)', (t_type, amount, description, session.get('user', {}).get('id')))
        trans_id = cur.lastrowid
        conn.execute('INSERT INTO journal_entries (transaction_id, debit_account_id, credit_account_id, amount, description) VALUES (?,?,?,?,?)', (trans_id, int(debit_id), int(credit_id), amount, description))
        conn.commit()
        flash('Financial transaction recorded', 'success')
        return redirect(url_for('app.finance_transaction'))
    return render_template('finance_transaction.html', accounts=accounts)


@bp.route('/reports/trial_balance')
def trial_balance():
    conn = db.get_db()
    rows = conn.execute('''
        SELECT a.id, a.name, a.type,
          IFNULL((SELECT SUM(amount) FROM journal_entries j WHERE j.debit_account_id = a.id),0) AS total_debits,
          IFNULL((SELECT SUM(amount) FROM journal_entries j WHERE j.credit_account_id = a.id),0) AS total_credits
        FROM accounts a
        ORDER BY a.type, a.name
    ''').fetchall()
    # compute balance depending on account type
    tb = []
    total_debits = 0
    total_credits = 0
    for r in rows:
        dr = r['total_debits'] or 0
        cr = r['total_credits'] or 0
        balance = dr - cr
        tb.append({'id': r['id'], 'name': r['name'], 'type': r['type'], 'debits': dr, 'credits': cr, 'balance': balance})
        total_debits += dr
        total_credits += cr
    return render_template('trial_balance.html', rows=tb, total_debits=total_debits, total_credits=total_credits)


@bp.route('/reports/income_statement')
def income_statement():
    conn = db.get_db()
    # Revenues: credits - debits
    rev_row = conn.execute('''
        SELECT IFNULL(SUM(CASE WHEN a.type='Revenue' THEN (j.credit_account_id IS NOT NULL) * j.amount ELSE 0 END),0) as credits,
               IFNULL(SUM(CASE WHEN a.type='Revenue' THEN (j.debit_account_id IS NOT NULL) * j.amount ELSE 0 END),0) as debits
        FROM journal_entries j
        JOIN accounts a ON a.id = j.credit_account_id OR a.id = j.debit_account_id
        WHERE a.type='Revenue'
    ''').fetchone()
    # Expenses: debits - credits
    exp_row = conn.execute('''
        SELECT IFNULL(SUM(CASE WHEN a.type='Expense' THEN (j.debit_account_id IS NOT NULL) * j.amount ELSE 0 END),0) as debits,
               IFNULL(SUM(CASE WHEN a.type='Expense' THEN (j.credit_account_id IS NOT NULL) * j.amount ELSE 0 END),0) as credits
        FROM journal_entries j
        JOIN accounts a ON a.id = j.debit_account_id OR a.id = j.credit_account_id
        WHERE a.type='Expense'
    ''').fetchone()
    revenue = (rev_row['credits'] or 0) - (rev_row['debits'] or 0)
    expenses = (exp_row['debits'] or 0) - (exp_row['credits'] or 0)
    net = revenue - expenses
    return render_template('income_statement.html', revenue=revenue, expenses=expenses, net=net)


@bp.route('/reports/expense_summary')
def expense_summary():
    conn = db.get_db()
    rows = conn.execute('''
        SELECT a.id, a.name, IFNULL(SUM(j.amount),0) as total
        FROM journal_entries j
        JOIN accounts a ON a.id = j.debit_account_id
        WHERE a.type='Expense'
        GROUP BY a.id, a.name
        ORDER BY total DESC
    ''').fetchall()
    total = sum([r['total'] for r in rows])
    return render_template('expense_summary.html', rows=rows, total=total)
