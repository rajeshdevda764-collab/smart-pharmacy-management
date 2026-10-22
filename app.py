import os
import io
import csv
from collections import defaultdict
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_RIGHT
from flask import send_file, Response
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'development-only-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') or 'sqlite:///smart_pharmacy.db'  # Set DATABASE_URL in .env for existing MySQL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='admin')

class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False, default='General')
    manufacturer = db.Column(db.String(120), default='')
    batch = db.Column(db.String(80), nullable=False)
    expiry = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    reorder_level = db.Column(db.Integer, nullable=False, default=10)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), default='')

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    customer = db.relationship('Customer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    items = db.relationship('SaleItem', backref='sale', cascade='all, delete-orphan')

class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    medicine = db.relationship('Medicine')
    medicine_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_context():
    return {'today': date.today(), 'timedelta': timedelta, 'current_user': session.get('username')}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username', '')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password', '')):
            session.clear()
            session['user_id'], session['username'] = user.id, user.username
            return redirect(url_for('dashboard'))
        flash('Incorrect username or password.', 'error')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    medicines = Medicine.query.order_by(Medicine.name).all()
    sales = Sale.query.order_by(Sale.created_at.desc()).limit(6).all()
    revenue = db.session.query(func.coalesce(func.sum(Sale.total), 0)).scalar()
    low = [m for m in medicines if m.quantity <= m.reorder_level]
    expiring = [m for m in medicines if date.today() <= m.expiry <= date.today() + timedelta(days=30)]
    expired = [m for m in medicines if m.expiry < date.today()]
    return render_template('dashboard.html', count=len(medicines), stock=sum(m.quantity for m in medicines), revenue=revenue, low=low, expiring=expiring, expired=expired, sales=sales)

@app.route('/medicines')
@login_required
def medicines():
    q = request.args.get('q', '').strip()
    query = Medicine.query
    category = request.args.get('category', '').strip()
    status = request.args.get('status', '').strip()
    if category:
        query = query.filter(Medicine.category == category)
    if status == 'low':
        query = query.filter(Medicine.quantity <= Medicine.reorder_level)
    elif status == 'expired':
        query = query.filter(Medicine.expiry < date.today())
    elif status == 'expiring':
        query = query.filter(Medicine.expiry >= date.today(), Medicine.expiry <= date.today() + timedelta(days=30))
    elif status == 'available':
        query = query.filter(Medicine.quantity > 0, Medicine.expiry >= date.today())
    if q:
        query = query.filter(Medicine.name.ilike(f'%{q}%') | Medicine.batch.ilike(f'%{q}%'))
    return render_template('medicines.html', medicines=query.order_by(Medicine.name).all(), q=q, category=category, status=status, categories=[x[0] for x in db.session.query(Medicine.category).distinct().order_by(Medicine.category).all()])

@app.route('/medicines/add', methods=['POST'])
@login_required
def add_medicine():
    try:
        name = request.form['name'].strip()
        quantity, reorder = int(request.form['quantity']), int(request.form['reorder_level'])
        price = Decimal(request.form['price'])
        expiry = date.fromisoformat(request.form['expiry'])
        if not name or not request.form['batch'].strip() or quantity < 0 or reorder < 0 or price < 0:
            raise ValueError('Invalid medicine details')
        db.session.add(Medicine(name=name, category=request.form.get('category','General').strip() or 'General', manufacturer=request.form.get('manufacturer','').strip(), batch=request.form['batch'].strip(), expiry=expiry, quantity=quantity, reorder_level=reorder, price=price))
        db.session.commit()
        flash('Medicine added successfully.', 'success')
    except (ValueError, KeyError, ArithmeticError):
        db.session.rollback()
        flash('Please provide valid medicine details.', 'error')
    return redirect(url_for('medicines'))

@app.route('/medicines/<int:medicine_id>/edit', methods=['POST'])
@login_required
def edit_medicine(medicine_id):
    m = db.get_or_404(Medicine, medicine_id)
    try:
        name, batch = request.form['name'].strip(), request.form['batch'].strip()
        quantity, reorder = int(request.form['quantity']), int(request.form['reorder_level'])
        price, expiry = Decimal(request.form['price']), date.fromisoformat(request.form['expiry'])
        if not name or not batch or quantity < 0 or reorder < 0 or price < 0:
            raise ValueError()
        m.name, m.batch, m.quantity, m.reorder_level, m.price, m.expiry = name, batch, quantity, reorder, price, expiry
        m.category, m.manufacturer = request.form.get('category','General').strip() or 'General', request.form.get('manufacturer','').strip()
        db.session.commit()
        flash('Medicine updated.', 'success')
    except (ValueError, KeyError, ArithmeticError):
        db.session.rollback()
        flash('Invalid medicine details.', 'error')
    return redirect(url_for('medicines'))

@app.route('/medicines/<int:medicine_id>/delete', methods=['POST'])
@login_required
def delete_medicine(medicine_id):
    m = db.get_or_404(Medicine, medicine_id)
    if SaleItem.query.filter_by(medicine_id=medicine_id).first():
        flash('Cannot delete a medicine used in past invoices.', 'error')
    else:
        db.session.delete(m)
        db.session.commit()
        flash('Medicine deleted.', 'success')
    return redirect(url_for('medicines'))

@app.route('/customers', methods=['GET', 'POST'])
@login_required
def customers():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        if name:
            db.session.add(Customer(name=name, phone=request.form.get('phone','').strip()))
            db.session.commit()
            flash('Customer added.', 'success')
        else:
            flash('Customer name is required.', 'error')
        return redirect(url_for('customers'))
    return render_template('customers.html', customers=Customer.query.order_by(Customer.name).all())

@app.route('/billing', methods=['GET', 'POST'])
@login_required
def billing():
    if request.method == 'POST':
        ids = request.form.getlist('medicine_id[]')
        quantities = request.form.getlist('quantity[]')
        try:
            if not ids or len(ids) != len(quantities):
                raise ValueError('Add at least one medicine.')
            aggregated = {}
            for mid, qty in zip(ids, quantities):
                mid, qty = int(mid), int(qty)
                if qty <= 0:
                    raise ValueError('Quantities must be positive.')
                aggregated[mid] = aggregated.get(mid, 0) + qty
            if not aggregated:
                raise ValueError('Add at least one medicine.')
            customer_id = request.form.get('customer_id') or None
            if customer_id and not db.session.get(Customer, int(customer_id)):
                raise ValueError('Invalid customer.')
            # Lock medicine rows while checking and deducting stock (MySQL/InnoDB).
            inventory = {m.id: m for m in Medicine.query.filter(Medicine.id.in_(aggregated)).order_by(Medicine.id).with_for_update().all()}
            total = Decimal('0.00')
            entries = []
            for mid, qty in aggregated.items():
                m = inventory.get(mid)
                if not m or m.expiry < date.today() or m.quantity < qty:
                    raise ValueError(f'Medicine {mid} is unavailable, expired or has insufficient stock.')
                subtotal = m.price * qty
                total += subtotal
                entries.append((m, qty, subtotal))
            sale = Sale(customer_id=int(customer_id) if customer_id else None, total=total)
            db.session.add(sale)
            db.session.flush()
            for m, qty, subtotal in entries:
                m.quantity -= qty
                db.session.add(SaleItem(sale_id=sale.id, medicine_id=m.id, medicine_name=m.name, quantity=qty, unit_price=m.price, subtotal=subtotal))
            db.session.commit()
            flash('Invoice created successfully.', 'success')
            return redirect(url_for('invoice', sale_id=sale.id))
        except (ValueError, TypeError, ArithmeticError) as exc:
            db.session.rollback()
            flash(str(exc) or 'Invalid billing data.', 'error')
    return render_template('billing.html', medicines=Medicine.query.filter(Medicine.quantity > 0, Medicine.expiry >= date.today()).order_by(Medicine.name).all(), customers=Customer.query.order_by(Customer.name).all())

@app.route('/sales')
@login_required
def sales():
    return render_template('sales.html', sales=Sale.query.order_by(Sale.created_at.desc()).all())

@app.route('/invoice/<int:sale_id>')
@login_required
def invoice(sale_id):
    return render_template('invoice.html', sale=db.get_or_404(Sale, sale_id))

@app.route('/api/sales-chart')
@login_required
def sales_chart():
    days = [(date.today() - timedelta(days=n)) for n in range(6, -1, -1)]
    totals = {day.isoformat(): 0.0 for day in days}
    for sale in Sale.query.filter(Sale.created_at >= datetime.combine(days[0], datetime.min.time())).all():
        key = sale.created_at.date().isoformat()
        if key in totals:
            totals[key] += float(sale.total)
    return jsonify(labels=[d.strftime('%d %b') for d in days], values=list(totals.values()))


@app.route('/invoice/<int:sale_id>/pdf')
@login_required
def invoice_pdf(sale_id):
    sale = db.get_or_404(Sale, sale_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=(595, 842), rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [Paragraph('SMARTPHARM  |  INVOICE', styles['Title']), Spacer(1, 18),
             Paragraph(f'Invoice: INV-{sale.id:04d}', styles['Heading2']),
             Paragraph(f'Date: {sale.created_at.strftime("%d %B %Y, %H:%M")} UTC', styles['Normal']),
             Paragraph('Customer: ' + (sale.customer.name if sale.customer else 'Walk-in customer'), styles['Normal']), Spacer(1, 20)]
    rows = [['Medicine', 'Qty', 'Unit price (INR)', 'Amount (INR)']]
    for item in sale.items:
        rows.append([Paragraph(item.medicine_name, styles['Normal']), str(item.quantity), f'{item.unit_price:.2f}', f'{item.subtotal:.2f}'])
    rows.append(['TOTAL', '', '', f'{sale.total:.2f}'])
    t = Table(rows, colWidths=[240, 48, 105, 110], repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf2ff')),
        ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#f1f5f9')),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),10),
        ('LINEBELOW',(0,0),(-1,0),0.6,colors.HexColor('#dce5f1')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(1,1),(-1,-1),'RIGHT')]))
    story += [t, Spacer(1,24), Paragraph('Thank you for choosing SmartPharm. This is a computer-generated invoice.', styles['Normal'])]
    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=f'INV-{sale.id:04d}.pdf')

@app.route('/analytics')
@login_required
def analytics():
    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    total = sum((s.total for s in sales), Decimal('0'))
    today_total = sum((s.total for s in sales if s.created_at.date() == date.today()), Decimal('0'))
    month_total = sum((s.total for s in sales if s.created_at.year == date.today().year and s.created_at.month == date.today().month), Decimal('0'))
    per_day = defaultdict(lambda: Decimal('0'))
    per_month = defaultdict(lambda: Decimal('0'))
    products = defaultdict(lambda: {'units': 0, 'revenue': Decimal('0')})
    for sale in sales:
        per_day[sale.created_at.date().isoformat()] += sale.total
        per_month[sale.created_at.strftime('%Y-%m')] += sale.total
        for item in sale.items:
            products[item.medicine_name]['units'] += item.quantity
            products[item.medicine_name]['revenue'] += item.subtotal
    last_days = [date.today() - timedelta(days=i) for i in range(13,-1,-1)]
    top = sorted(products.items(), key=lambda x: x[1]['units'], reverse=True)[:8]
    months = sorted(per_month.keys())[-6:]
    return render_template('analytics.html', total=total, today_total=today_total, month_total=month_total,
        sales_count=len(sales), top=top, days_labels=[d.strftime('%d %b') for d in last_days],
        days_values=[float(per_day[d.isoformat()]) for d in last_days],
        months_labels=months, months_values=[float(per_month[m]) for m in months])

@app.route('/analytics/export.csv')
@login_required
def sales_export():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Invoice', 'Date (UTC)', 'Customer', 'Medicine', 'Quantity', 'Unit price INR', 'Subtotal INR', 'Invoice total INR'])
    for sale in Sale.query.order_by(Sale.created_at.desc()).all():
        for item in sale.items:
            writer.writerow([f'INV-{sale.id:04d}', sale.created_at.isoformat(sep=' '), sale.customer.name if sale.customer else 'Walk-in', item.medicine_name, item.quantity, item.unit_price, item.subtotal, sale.total])
    return Response('﻿' + output.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition':'attachment; filename="smartpharm_sales.csv"'})

@app.route('/alerts')
@login_required
def alerts():
    medicines = Medicine.query.order_by(Medicine.expiry, Medicine.name).all()
    expired = [m for m in medicines if m.expiry < date.today()]
    expiring = [m for m in medicines if date.today() <= m.expiry <= date.today() + timedelta(days=30)]
    low = [m for m in medicines if m.quantity <= m.reorder_level]
    return render_template('alerts.html', expired=expired, expiring=expiring, low=low)

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Database tables created.')

@app.cli.command('create-admin')
def create_admin():
    import getpass
    username = input('Admin username: ').strip()
    password = getpass.getpass('Admin password (minimum 8 characters): ')
    if not username or len(password) < 8:
        print('Username required; password must be at least 8 characters.')
        return
    if User.query.filter_by(username=username).first():
        print('Username already exists.')
        return
    db.session.add(User(username=username, password_hash=generate_password_hash(password)))
    db.session.commit()
    print('Admin created.')

@app.cli.command('seed-demo')
def seed_demo():
    if Medicine.query.first():
        print('Medicines already exist; skipping demo seed.')
        return
    samples = [('Paracetamol 500mg','Tablets','ABC Pharma','PAR-102',120,25,24.00,365),('Vitamin C 500mg','Supplements','Health Labs','VIT-230',45,15,95.00,220),('ORS Sachet','Wellness','Care Pharma','ORS-404',8,20,22.50,120),('Antiseptic Solution','First Aid','MedCare','ANT-502',32,10,68.00,25),('Cough Syrup','Syrup','Care Pharma','COU-600',14,15,85.00,180)]
    for name,cat,maker,batch,qty,reorder,price,days in samples:
        db.session.add(Medicine(name=name, category=cat, manufacturer=maker, batch=batch, quantity=qty, reorder_level=reorder, price=Decimal(str(price)), expiry=date.today()+timedelta(days=days)))
    db.session.commit()
    print('Demo medicines added.')

if __name__ == '__main__':
    app.run(debug=False)
