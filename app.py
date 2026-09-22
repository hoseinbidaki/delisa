#!/usr/bin/env python3
"""DELISA — minimal Python (stdlib-only) WSGI storefront and admin demo.

Python 3.10+; no pip dependencies. Dev: python app.py run.
Production: reverse-proxy static files and run app:application with a real WSGI server.
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import hmac
import html
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import time
import unicodedata
import uuid
from email.parser import BytesParser
from contextlib import closing
from email import policy
from http.cookies import SimpleCookie
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, quote, urlencode
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('DELISA_DATA_DIR', str(ROOT / 'data')))
DB = DATA / 'delisa.sqlite3'
STATIC = ROOT / 'static'
UPLOAD = STATIC / 'uploads'
TEMPLATES = ROOT / 'templates'
SECURE_COOKIE = os.environ.get('DELISA_SECURE_COOKIE', '0') == '1'
SITE_NAME = 'دلیسا | DELISA'
STATUS = {'pending': 'در انتظار بررسی', 'processing': 'در حال آماده‌سازی', 'shipped': 'ارسال شده', 'delivered': 'تحویل داده شده', 'cancelled': 'لغو شده'}
MAX_BODY = 32 * 1024 * 1024
MAX_IMAGE = 5 * 1024 * 1024


def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def money(n):
    return f'{int(n):,}'.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')) + ' تومان'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def db_connect():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    UPLOAD.mkdir(parents=True, exist_ok=True)
    with closing(db_connect()) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN ('customer','admin')),
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            id_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            csrf TEXT NOT NULL, created_at TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL CHECK(price>=0), compare_price INTEGER NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock>=0), image TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS carts (
            session_hash TEXT NOT NULL REFERENCES sessions(id_hash) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id), qty INTEGER NOT NULL CHECK(qty>0),
            PRIMARY KEY(session_hash,product_id));
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            PRIMARY KEY(user_id,product_id));
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            full_name TEXT NOT NULL, phone TEXT NOT NULL, city TEXT NOT NULL,
            address TEXT NOT NULL, postal_code TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '', total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_status TEXT NOT NULL DEFAULT 'not_connected', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            product_name TEXT NOT NULL, unit_price INTEGER NOT NULL, quantity INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS page_views (
            id INTEGER PRIMARY KEY, visitor_hash TEXT NOT NULL, path TEXT NOT NULL,
            created_day TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_page_views_date ON page_views(created_day);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_products_active ON products(active,category);
        CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE COLLATE NOCASE,
            kind TEXT NOT NULL CHECK(kind IN ('percent','fixed')),
            value INTEGER NOT NULL CHECK(value>0),
            min_total INTEGER NOT NULL DEFAULT 0 CHECK(min_total>=0),
            max_uses INTEGER NOT NULL DEFAULT 0 CHECK(max_uses>=0),
            used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count>=0),
            expires_on TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            body TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL);
        ''')
        # Non-destructive upgrade for databases created before DELISA v1.6.
        cols = {r['name'] for r in db.execute('PRAGMA table_info(orders)')}
        for name, definition in (
            ('subtotal', 'INTEGER NOT NULL DEFAULT 0'),
            ('discount_amount', 'INTEGER NOT NULL DEFAULT 0'),
            ('coupon_code', "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in cols:
                db.execute(f'ALTER TABLE orders ADD COLUMN {name} {definition}')
        # DELISA v1.7: non-destructive migration for galleries and color selections.
        product_columns = {r['name'] for r in db.execute('PRAGMA table_info(products)')}
        if 'colors' not in product_columns:
            db.execute("ALTER TABLE products ADD COLUMN colors TEXT NOT NULL DEFAULT '[]'")
        if 'primary_color' not in product_columns:
            db.execute("ALTER TABLE products ADD COLUMN primary_color TEXT NOT NULL DEFAULT ''")
        db.execute('''CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            image TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_product_images_product ON product_images(product_id,sort_order,id)')
        cart_columns = {r['name'] for r in db.execute('PRAGMA table_info(carts)')}
        if 'color' not in cart_columns:
            # Keep existing carts; a product can now appear once per selected color.
            db.executescript('''BEGIN IMMEDIATE;
            CREATE TABLE carts_v17 (
                session_hash TEXT NOT NULL REFERENCES sessions(id_hash) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                color TEXT NOT NULL DEFAULT '',
                qty INTEGER NOT NULL CHECK(qty>0),
                PRIMARY KEY(session_hash,product_id,color)
            );
            INSERT INTO carts_v17(session_hash,product_id,color,qty)
                SELECT session_hash,product_id,'',qty FROM carts;
            DROP TABLE carts;
            ALTER TABLE carts_v17 RENAME TO carts;
            COMMIT;''')
        item_columns = {r['name'] for r in db.execute('PRAGMA table_info(order_items)')}
        if 'color' not in item_columns:
            db.execute("ALTER TABLE order_items ADD COLUMN color TEXT NOT NULL DEFAULT ''")
        db.commit()


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310000)
    return 'pbkdf2_sha256$310000$' + salt.hex() + '$' + digest.hex()


def verify_password(password, stored):
    try:
        algorithm, count, salt, digest = stored.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        got = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(got, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def slugify(name):
    slug = re.sub(r'[^a-z0-9-]+', '-', unicodedata.normalize('NFKD', name).lower()).strip('-')
    return slug[:75] or uuid.uuid4().hex[:12]


class HTTPError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Request:
    def __init__(self, environ):
        self.env = environ
        self.method = environ.get('REQUEST_METHOD', 'GET').upper()
        self.path = environ.get('PATH_INFO', '/') or '/'
        self.query = {k: v[-1] for k, v in parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True).items()}
        self.headers = {k[5:].replace('_', '-').lower(): v for k, v in environ.items() if k.startswith('HTTP_')}
        self.cookie = SimpleCookie()
        try:
            self.cookie.load(environ.get('HTTP_COOKIE', ''))
        except Exception:
            pass
        self.form = {}
        self.files = {}
        self.body = b''
        self._json = {}
        if self.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            size = int(environ.get('CONTENT_LENGTH') or 0)
            if size > MAX_BODY:
                raise HTTPError(413, 'حجم درخواست زیاد است. حداکثر ۶ مگابایت.')
            if size < 0:
                raise HTTPError(400, 'درخواست نامعتبر')
            self.body = environ['wsgi.input'].read(size) if size else b''
            content_type = environ.get('CONTENT_TYPE', '')
            if content_type.startswith('application/json'):
                try:
                    self._json = json.loads(self.body or b'{}')
                    if not isinstance(self._json, dict): raise ValueError()
                except (ValueError, UnicodeDecodeError):
                    raise HTTPError(400, 'JSON نامعتبر')
            elif content_type.startswith('application/x-www-form-urlencoded'):
                self.form = {k: v[-1] for k, v in parse_qs(self.body.decode('utf-8'), keep_blank_values=True).items()}
            elif content_type.startswith('multipart/form-data'):
                prefix = b'MIME-Version: 1.0\r\nContent-Type: ' + content_type.encode('ascii', 'ignore') + b'\r\n\r\n'
                msg = BytesParser(policy=policy.default).parsebytes(prefix + self.body)
                if not msg.is_multipart(): raise HTTPError(400, 'فرم آپلود نامعتبر')
                for part in msg.iter_parts():
                    key = part.get_param('name', header='content-disposition')
                    if not key: continue
                    filename = part.get_filename()
                    data = part.get_payload(decode=True) or b''
                    if filename:
                        self.files[key] = (filename, data)
                    else:
                        self.form[key] = data.decode('utf-8', 'replace')

    def value(self, key, default=''):
        return self._json.get(key, self.form.get(key, default))


class Response:
    def __init__(self, body=b'', status=200, content_type='text/html; charset=utf-8', headers=None):
        if isinstance(body, str): body = body.encode('utf-8')
        self.body, self.status, self.headers = body, status, [('Content-Type', content_type)] + (headers or [])


def redirect(url):
    return Response('', 303, headers=[('Location', url), ('Cache-Control', 'no-store')])


def json_response(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False), status, 'application/json; charset=utf-8', [('Cache-Control', 'no-store')])


def raw_csv(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['شماره سفارش','تاریخ','مشتری','تلفن','شهر','مبلغ (تومان)','وضعیت'])
    for o in rows:
        writer.writerow([o['id'],o['created_at'],o['full_name'],o['phone'],o['city'],o['total'],STATUS.get(o['status'],o['status'])])
    return Response('\ufeff'+buf.getvalue(), 200, 'text/csv; charset=utf-8', [('Content-Disposition','attachment; filename="delisa-orders.csv"'),('Cache-Control','no-store')])


def read_template(filename, **variables):
    return Template((TEMPLATES / filename).read_text(encoding='utf-8')).safe_substitute(**variables)


def cookie_header(token, delete=False):
    cookie = f'delisa_session={"" if delete else token}; Path=/; HttpOnly; SameSite=Lax'
    if SECURE_COOKIE: cookie += '; Secure'
    if delete: cookie += '; Max-Age=0'
    else: cookie += '; Max-Age=1209600'
    return ('Set-Cookie', cookie)


def get_session(req, conn, create=True):
    cookie = req.cookie.get('delisa_session')
    token = cookie.value if cookie else ''
    id_hash = hashlib.sha256(token.encode()).hexdigest() if re.fullmatch(r'[0-9a-f]{64}', token) else ''
    row = conn.execute('SELECT s.*,u.id AS uid,u.name,u.email,u.role,u.phone FROM sessions s LEFT JOIN users u ON u.id=s.user_id WHERE s.id_hash=? AND s.expires_at>?', (id_hash, int(time.time()))).fetchone() if id_hash else None
    if row: return dict(row), None
    if not create: return None, None
    token = secrets.token_hex(32)
    csrf = secrets.token_urlsafe(32)
    key = hashlib.sha256(token.encode()).hexdigest()
    conn.execute('INSERT INTO sessions(id_hash,csrf,created_at,expires_at) VALUES(?,?,?,?)', (key,csrf,now(),int(time.time())+1209600))
    conn.commit()
    return {'id_hash':key,'csrf':csrf,'user_id':None,'uid':None,'name':'','email':'','role':'','phone':''},cookie_header(token)


def require_csrf(req, sess):
    supplied = req.headers.get('x-csrf-token','') or req.value('csrf','')
    if not sess or not supplied or not hmac.compare_digest(str(supplied),sess['csrf']):
        raise HTTPError(403,'نشست امنیتی نامعتبر است. صفحه را تازه‌سازی کنید.')


def require_user(sess, admin=False):
    if not sess or not sess.get('uid'):
        raise HTTPError(401,'برای ادامه وارد حساب شوید.')
    if admin and sess.get('role') != 'admin':
        raise HTTPError(403,'دسترسی مدیر لازم است.')


def row_dict(row):
    return dict(row) if row else None


def sale_info(product):
    old = int(product['compare_price'] or 0)
    price = int(product['price'])
    if old <= price or old <= 0:
        return None
    # Floor so the displayed percentage never overstates the actual discount.
    return {'old': old, 'percent': (100 * (old - price)) // old}


def parse_colors(text):
    """Accepted editor format: comma/newline separated color names, no HTML."""
    names = [x.strip() for x in str(text or '').replace('،', ',').replace('\n', ',').split(',')]
    colors = list(dict.fromkeys(x for x in names if x))
    if len(colors) > 12 or any(len(x) > 36 or any(ord(c) < 32 for c in x) for x in colors):
        raise HTTPError(400, 'حداکثر ۱۲ رنگ، هر نام حداکثر ۳۶ کاراکتر.')
    return colors


def product_colors(product):
    try:
        colors = json.loads(product['colors'] or '[]')
        return colors if isinstance(colors, list) else []
    except (ValueError, TypeError):
        return []


def color_allowed(product, color):
    colors = product_colors(product)
    return (not colors and not color) or (bool(colors) and color in colors)


COLOR_SWATCHES = {
    'مشکی':'#222222', 'سفید':'#ffffff', 'استخوانی':'#ede7dc',
    'شیری':'#f6f1e5','کرم':'#e5d2b3','بژ':'#d0b99b',
    'سرمه‌ای':'#172338','سرمه ای':'#172338','آبی':'#406a97',
    'طوسی':'#999995','خاکستری':'#888988','زرشکی':'#702c3b',
    'قهوه‌ای':'#76513c','سبز':'#566b55','صورتی':'#deabba',
}


def gallery_photo(image, color, index, active=False):
    """Trusted local image path and escaped color label to keep gallery safe."""
    return f'<button class="gallery-thumb {"is-active" if active else ""}" type="button" aria-pressed="{"true" if active else "false"}" data-gallery-index="{index}" data-gallery-color="{esc(color)}" aria-label="نمایش تصویر {index+1}"><img src="{esc(image)}" alt="نمای {index+1}" draggable="false" loading="lazy" decoding="async" width="90" height="112"></button>'


def coupon_for_total(conn, entered_code, subtotal):
    code = str(entered_code or '').strip().upper()
    if not code:
        return None, 0
    if not re.fullmatch(r'[A-Z0-9_-]{3,24}', code):
        raise HTTPError(400, 'فرمت کد تخفیف معتبر نیست.')
    coupon = conn.execute('SELECT * FROM coupons WHERE code=?', (code,)).fetchone()
    if not coupon or not coupon['active']:
        raise HTTPError(400, 'این کد تخفیف معتبر یا فعال نیست.')
    if coupon['expires_on'] and coupon['expires_on'] < today():
        raise HTTPError(400, 'مهلت استفاده از این کد تخفیف تمام شده است.')
    if coupon['max_uses'] and coupon['used_count'] >= coupon['max_uses']:
        raise HTTPError(400, 'ظرفیت استفاده از این کد تخفیف تکمیل شده است.')
    if subtotal < coupon['min_total']:
        raise HTTPError(400, 'حداقل مبلغ سفارش برای این کد ' + money(coupon['min_total']) + ' است.')
    amount = (subtotal * coupon['value'] // 100) if coupon['kind'] == 'percent' else coupon['value']
    return coupon, min(subtotal, amount)


def product_card(p, eager=False):
    loading = 'eager' if eager else 'lazy'
    image = esc(p['image'] or '/static/img/vest.svg')
    sale = sale_info(p)
    if sale:
        badge = f'<span class="sale-badge" aria-label="{sale["percent"]} درصد تخفیف">٪{sale["percent"]} تخفیف</span>'
        old_price = f'<del class="card-old-price">{money(sale["old"])}</del>'
    else:
        badge = ''
        old_price = ''
    unavailable = '<span class="sold-out">ناموجود</span>' if p['stock'] <= 0 else ''
    url = '/product/' + quote(p['slug'])
    return f'''<article class="product-card atelier-card">
      <a data-nav href="{url}" class="product-image atelier-card-image card-photo-link" aria-label="مشاهده محصول {esc(p['name'])}">
        <img src="{image}" loading="{loading}" decoding="async" draggable="false" width="480" height="612" alt="{esc(p['name'])}">
        <span class="card-badges">{badge}{unavailable}</span>
        <span class="card-discover" aria-hidden="true">مشاهده محصول <span>←</span></span>
      </a>
      <div class="product-info atelier-card-info">
        <span class="card-category">DELISA / {esc(p['category'])}</span>
        <a data-nav href="{url}" class="card-name">{esc(p['name'])}</a>
        <div class="card-pricing"><strong>{money(p['price'])}</strong>{old_price}</div>
        <a data-nav href="{url}" class="card-details-link" aria-label="مشاهده جزئیات {esc(p['name'])}">مشاهده جزئیات <span aria-hidden="true">←</span></a>
      </div>
    </article>'''


def nav_user(sess):
    if sess.get('uid'):
        return '<a href="/account" data-nav>حساب من</a>' + ('<a href="/admin">مدیریت</a>' if sess.get('role')=='admin' else '')
    return '<a href="/login" data-nav>ورود / عضویت</a>'


def layout(page, title, sess, path, description='فروشگاه آنلاین پوشاک دلیسا'):
    admin_link = ('<a class="admin-header-link" href="/admin" aria-label="پنل مدیریت" title="پنل مدیریت">'
                  '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="7" height="7" rx="1"/>'
                  '<rect x="13.5" y="3.5" width="7" height="7" rx="1"/>'
                  '<rect x="3.5" y="13.5" width="7" height="7" rx="1"/>'
                  '<rect x="13.5" y="13.5" width="7" height="7" rx="1"/></svg>'
                  '<span>مدیریت</span></a>') if sess.get('role') == 'admin' and sess.get('uid') else ''
    out = read_template('base.html', page=page, title=esc(title),description=esc(description),
                        account_nav=nav_user(sess),account_link='/account' if sess.get('uid') else '/login',admin_link=admin_link,csrf=esc(sess['csrf']),path=esc(path))
    return Response(out, headers=[('Cache-Control','private, no-cache, must-revalidate' if path=='/' or path=='/shop' or path.startswith('/product/') else 'private, no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','strict-origin-when-cross-origin'),('X-Frame-Options','DENY')])


def public_view(conn, sess, path):
    if not sess or not path.startswith(('/','/shop','/product')):return
    conn.execute('INSERT INTO page_views(visitor_hash,path,created_day,created_at) VALUES(?,?,?,?)',(sess['id_hash'],path[:180],today(),now()))
    conn.commit()


def cart_data(conn,sess):
    rows = conn.execute('SELECT c.product_id,c.color,c.qty,p.name,p.price,p.image,p.stock,p.active,p.slug FROM carts c JOIN products p ON p.id=c.product_id WHERE c.session_hash=? ORDER BY p.id DESC, c.color', (sess['id_hash'],)).fetchall()
    items = [dict(r) for r in rows]
    return {'items':items,'count':sum(x['qty'] for x in items),'total':sum(x['price']*x['qty'] for x in items)}


def write_upload(req, key='image'):
    file = req.files.get(key)
    if not file or not file[0]: return ''
    name, raw = file
    if len(raw) > MAX_IMAGE: raise HTTPError(400,'حداکثر حجم تصویر ۵ مگابایت است.')
    ext = Path(name).suffix.lower()
    detected = ''
    if raw.startswith(b'\xff\xd8\xff'):detected='.jpg'
    elif raw.startswith(b'\x89PNG\r\n\x1a\n'):detected='.png'
    elif len(raw)>12 and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':detected='.webp'
    if not detected or ext not in ('.jpg','.jpeg','.png','.webp'):
        raise HTTPError(400,'فقط عکس JPG، PNG یا WebP قابل بارگذاری است.')
    filename = uuid.uuid4().hex + detected
    UPLOAD.mkdir(parents=True,exist_ok=True)
    (UPLOAD/filename).write_bytes(raw)
    return '/static/uploads/'+filename


def delete_upload(path):
    if path.startswith('/static/uploads/'):
        target=(UPLOAD/Path(path).name)
        try:target.unlink(missing_ok=True)
        except OSError:pass


def home(conn,sess):
    featured=conn.execute('SELECT * FROM products WHERE active=1 ORDER BY id DESC LIMIT 4').fetchall()
    cards=''.join(product_card(p) for p in featured) or '<p>به‌زودی محصولات دلیسا را اینجا می‌بینید.</p>'
    body=read_template('home.html',cards=cards)
    return layout(body,'دلیسا | سادگی ماندگار',sess,'/')


def shop(conn,sess,req):
    q=req.query.get('q','').strip()[:70]
    category=req.query.get('category','').strip()[:60]
    sort=req.query.get('sort','newest')
    if sort not in ('newest','low','high','name'):sort='newest'
    sale=req.query.get('sale','')=='1'
    clauses=['active=1'];args=[]
    if q:clauses.append('(name LIKE ? OR description LIKE ?)');args += [f'%{q}%',f'%{q}%']
    if category:clauses.append('category=?');args.append(category)
    if sale:clauses.append('compare_price > price AND compare_price > 0')
    order={'newest':'id DESC','low':'price ASC','high':'price DESC','name':'name COLLATE NOCASE ASC'}[sort]
    try:page=max(1,min(10000,int(req.query.get('page','1'))))
    except ValueError:page=1
    total=conn.execute('SELECT COUNT(*) FROM products WHERE '+' AND '.join(clauses),args).fetchone()[0]
    page_size=24
    products=conn.execute('SELECT * FROM products WHERE '+' AND '.join(clauses)+' ORDER BY '+order+' LIMIT ? OFFSET ?', args+[page_size,(page-1)*page_size]).fetchall()
    cats=conn.execute('SELECT DISTINCT category FROM products WHERE active=1 ORDER BY category').fetchall()
    cat_opts='<option value="">همه دسته‌ها</option>'+''.join(f'<option value="{esc(c[0])}" {"selected" if category==c[0] else ""}>{esc(c[0])}</option>' for c in cats)
    sort_opts=''.join(f'<option value="{v}" {"selected" if sort==v else ""}>{label}</option>' for v,label in [('newest','جدیدترین'),('low','ارزان‌ترین'),('high','گران‌ترین'),('name','نام محصول')])
    cards=''.join(product_card(p,eager=i<4) for i,p in enumerate(products)) or '<div class="empty shop-empty"><strong>چیزی با این انتخاب پیدا نکردیم.</strong><p>فیلترها رو پاک کن یا دسته دیگه‌ای رو ببین.</p><a href="/shop" data-nav class="btn outline">دیدن همه محصولات ←</a></div>'
    pages=(total+page_size-1)//page_size
    links=''
    if pages>1:
        for n in range(max(1,page-2),min(pages,page+2)+1):
            qs=urlencode({'q':q,'category':category,'sort':sort,'sale':'1' if sale else '', 'page':n})
            links+=f'<a data-nav {"aria-current=page" if n==page else ""} class={"active" if n==page else ""} href="/shop?{esc(qs)}">{n}</a>'
    def shop_link(cat='', sale_flag=None):
        params={'sort':sort}
        if q:params['q']=q
        if cat:params['category']=cat
        if sale if sale_flag is None else sale_flag:params['sale']='1'
        return '/shop?'+esc(urlencode(params)) if params else '/shop'
    category_chips='<a data-nav class="shop-cat-chip'+(' active' if not category and not sale else '')+'" href="'+shop_link('',False)+'"'+(' aria-current="page"' if not category and not sale else '')+'>همه محصولات <span aria-hidden="true">↗</span></a>'
    for c in cats:
        active=category==c[0]
        category_chips+='<a data-nav class="shop-cat-chip'+(' active' if active else '')+'" href="'+shop_link(c[0])+'"'+(' aria-current="page"' if active else '')+'>'+esc(c[0])+'<span aria-hidden="true">↗</span></a>'
    category_chips+='<a data-nav class="shop-cat-chip shop-sale-chip'+(' active' if sale else '')+'" href="'+shop_link(category,not sale)+'"'+(' aria-current="page"' if sale else '')+'>تخفیف‌دارها <span aria-hidden="true">٪</span></a>'
    filters=[]
    if q:filters.append(('<span>جستجو: '+esc(q)+'</span>','/shop?'+esc(urlencode({'category':category,'sort':sort,'sale':'1' if sale else ''}))))
    if category:filters.append(('<span>دسته: '+esc(category)+'</span>',shop_link('',sale)))
    if sale:filters.append(('<span>تخفیف‌دار</span>',shop_link(category,False)))
    active_filters='<div class="shop-applied-filters" aria-label="فیلترهای فعال">'+''.join('<a data-nav href="'+href+'">'+label+' <b aria-hidden="true">×</b></a>' for label,href in filters)+'</div>' if filters else ''
    results_title=('نتایج «'+esc(q)+'»') if q else ('محصولات '+esc(category)) if category else 'همه محصولات'
    body=read_template('shop.html',cards=cards,query=esc(q),cat_options=cat_opts,sort_options=sort_opts,count=esc(total),pagination=links,category_chips=category_chips,results_title=results_title,sale_checked='checked' if sale else '',active_filters=active_filters)
    return layout(body,'فروشگاه | دلیسا',sess,'/shop')

def product_page(conn,sess,slug):
    p=conn.execute('SELECT * FROM products WHERE slug=? AND active=1',(slug,)).fetchone()
    if not p:raise HTTPError(404,'محصول پیدا نشد.')
    related=conn.execute('SELECT * FROM products WHERE active=1 AND id!=? ORDER BY (category=?) DESC,id DESC LIMIT 4',(p['id'],p['category'])).fetchall()
    related_cards=''.join(product_card(r) for r in related)
    colors=product_colors(p)
    default_color=p['primary_color'] if p['primary_color'] in colors else (colors[0] if colors else '')
    extra=conn.execute('SELECT id,image,color FROM product_images WHERE product_id=? ORDER BY sort_order,id',(p['id'],)).fetchall()
    images=[{'image':p['image'] or '/static/img/vest.svg','color':p['primary_color'] or ''}]
    images.extend({'image':r['image'],'color':r['color']} for r in extra)
    selected_image=next((i for i,v in enumerate(images) if v['color']==default_color),0)
    thumbs=''.join(gallery_photo(v['image'],v['color'],i,i==selected_image) for i,v in enumerate(images))
    gallery_json=esc(json.dumps(images,ensure_ascii=False))
    color_buttons=''.join(f'<button type="button" class="color-option {"is-selected" if c==default_color else ""}" data-select-color="{esc(c)}" aria-pressed="{"true" if c==default_color else "false"}"><span class="color-dot" style="--swatch:{COLOR_SWATCHES.get(c,"#ece8e1")}"></span><span>{esc(c)}</span></button>' for c in colors)
    colors_html=f'<div class="product-colors"><div class="color-head"><span>رنگ</span><strong id="current-color">{esc(default_color)}</strong></div><div class="color-options" role="group" aria-label="انتخاب رنگ">{color_buttons}</div></div>' if colors else ''
    sale=sale_info(p)
    sale_badge=f'<span class="sale-badge detail-sale-badge">٪{sale["percent"]} تخفیف</span>' if sale else ''
    old_price=f'<del class="detail-old-price">{money(sale["old"])}</del>' if sale else ''
    body=read_template('product.html',sale_badge=sale_badge,old_price=old_price,image=esc(images[selected_image]['image']),gallery_thumbs=thumbs,gallery_json=gallery_json,gallery_total=len(images),selected_index=selected_image+1,colors_html=colors_html,name=esc(p['name']),price=money(p['price']),description=esc(p['description']).replace('\n','<br>'),category=esc(p['category']),stock=esc(p['stock']),product_id=p['id'],button_disabled='disabled' if p['stock']<=0 else '',button_text='ناموجود' if p['stock']<=0 else 'افزودن به سبد خرید',related_cards=related_cards)
    return layout(body,esc(p['name'])+' | دلیسا',sess,'/product/'+slug,esc(p['description'][:140]))


def login_page(sess,error=''):
    return layout(read_template('login.html',error=f'<div class="alert">{esc(error)}</div>' if error else '',csrf=esc(sess['csrf'])),'ورود | دلیسا',sess,'/login')


def register_page(sess,error=''):
    return layout(read_template('register.html',error=f'<div class="alert">{esc(error)}</div>' if error else '',csrf=esc(sess['csrf'])),'عضویت | دلیسا',sess,'/register')


def account_page(conn,sess):
    require_user(sess)
    orders = conn.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 100',(sess['uid'],)).fetchall()
    order_count = len(orders)
    total_spent = sum(int(o['total']) for o in orders)
    favorites_rows = conn.execute('SELECT p.* FROM favorites f JOIN products p ON p.id=f.product_id WHERE f.user_id=? AND p.active=1 ORDER BY p.id DESC',(sess['uid'],)).fetchall()
    favorite_count = len(favorites_rows)
    order_cards = []
    for o in orders:
        items = conn.execute('SELECT oi.product_name,oi.quantity,oi.color,p.image FROM order_items oi LEFT JOIN products p ON p.id=oi.product_id WHERE oi.order_id=? ORDER BY oi.id',(o['id'],)).fetchall()
        thumbs = ''.join(f'<img src="{esc(i["image"] or "/static/img/vest.svg")}" alt="{esc(i["product_name"])}" loading="lazy" decoding="async" width="64" height="80">' for i in items[:4])
        line_names = ' · '.join(esc(i['product_name']) + (f' ({esc(i["color"])})' if i['color'] else '') for i in items[:2])
        if len(items) > 2:
            line_names += ' …'
        item_count = sum(int(i['quantity']) for i in items)
        order_cards.append(f'''<a class="order-showcase-card" href="/account/orders/{o['id']}" data-nav>
            <div class="order-showcase-media">
                <div class="bundle-stack">{thumbs or '<span class="bundle-empty">DELISA</span>'}</div>
                <div class="bundle-meta"><strong>{item_count}</strong><span>قلم</span></div>
            </div>
            <div class="order-showcase-body">
                <div class="order-meta-top"><span class="eyebrow ink">ORDER #{o['id']}</span><span>{esc(o['created_at'][:10])}</span></div>
                <strong>سفارش #{o['id']}</strong>
                <p>{line_names or 'بدون جزئیات ثبت شده'}</p>
                <div class="order-meta-bottom"><span class="pill status-{esc(o['status'])}">{STATUS.get(o['status'],'نامشخص')}</span><b>{money(o['total'])}</b></div>
            </div>
        </a>''')
    cards = ''.join(order_cards) or '<div class="empty-card"><strong>هنوز سفارشی ثبت نکرده‌ای.</strong><p class="muted">اولین خریدت از دلیسا همین‌جا نمایش داده می‌شود.</p><a href="/shop" data-nav class="btn btn-light">کشف محصولات</a></div>'
    body = read_template('account.html', name=esc(sess['name']), email=esc(sess['email']), csrf=esc(sess['csrf']), order_count=esc(order_count), total_spent=money(total_spent), favorite_count=esc(favorite_count), orders=cards, favorites=''.join(product_card(p) for p in favorites_rows) or '<div class="empty-card"><strong>هنوز چیزی ذخیره نکرده‌ای.</strong><p class="muted">محصولات موردعلاقه‌ات را برای بعد نگه دار.</p></div>')
    return layout(body,'حساب من | دلیسا',sess,'/account')


def order_detail(conn,sess,order_id):
    require_user(sess)
    order = conn.execute('SELECT * FROM orders WHERE id=? AND (user_id=? OR ?=1)',(order_id,sess['uid'],int(sess['role']=='admin'))).fetchone()
    if not order: raise HTTPError(404,'سفارش پیدا نشد.')
    items = conn.execute('SELECT oi.*, p.image, p.slug FROM order_items oi LEFT JOIN products p ON p.id=oi.product_id WHERE oi.order_id=? ORDER BY oi.id',(order_id,)).fetchall()
    rows = ''.join(f'<tr><td>{esc(i["product_name"])}{" · " + esc(i["color"]) if i["color"] else ""}</td><td>{i["quantity"]}</td><td>{money(i["unit_price"]*i["quantity"])}</td></tr>' for i in items)
    item_cards = ''.join(f'''<article class="order-item-card"><a href="/product/{esc(i['slug'])}" data-nav class="order-item-photo"><img src="{esc(i['image'] or '/static/img/vest.svg')}" alt="{esc(i['product_name'])}" loading="lazy" decoding="async" width="96" height="118"></a><div class="order-item-copy"><strong>{esc(i['product_name'])}</strong><span>{'رنگ: ' + esc(i['color']) if i['color'] else 'رنگ انتخاب نشده'}</span><span>{i['quantity']} عدد</span></div><b>{money(i['unit_price']*i['quantity'])}</b></article>''' for i in items)
    savings = ''
    if order['coupon_code'] and order['discount_amount']:
        savings = '<div class="summary-line coupon-savings"><span>کد تخفیف ' + esc(order['coupon_code']) + '</span><strong>− ' + money(order['discount_amount']) + '</strong></div>'
    body = read_template('order.html', coupon_savings=savings, number=order_id, status=STATUS.get(order['status'],'نامشخص'), name=esc(order['full_name']), phone=esc(order['phone']), city=esc(order['city']), address=esc(order['address']), total=money(order['total']), rows=rows, items_cards=item_cards or '<p class="muted">جزئیات اقلام ثبت نشده است.</p>', payment='درگاه پرداخت هنوز متصل نشده است؛ این سفارش آزمایشی است.')
    return layout(body,f'سفارش #{order_id} | دلیسا',sess,'/account/orders/'+str(order_id))


def checkout_page(conn,sess):
    require_user(sess)
    cart=cart_data(conn,sess)
    if not cart['items']:return redirect('/shop')
    items=''.join(f'<div class="summary-line"><span>{esc(i["name"])}{" · " + esc(i["color"]) if i["color"] else ""} × {i["qty"]}</span><strong>{money(i["price"]*i["qty"])}</strong></div>' for i in cart['items'])
    body=read_template('checkout.html',csrf=esc(sess['csrf']),items=items,total=money(cart['total']),name=esc(sess['name']),phone=esc(sess['phone'] or ''))
    return layout(body,'ثبت سفارش آزمایشی | دلیسا',sess,'/checkout')


def admin_layout(content,title,sess):
    menu='''<a href="/admin">داشبورد</a><a href="/admin/accounting">حسابداری</a><a href="/admin/products">محصولات</a><a href="/admin/orders">سفارش‌ها</a><a href="/admin/coupons">کدهای تخفیف</a><a href="/admin/users">کاربران</a><a href="/admin/export/orders">خروجی CSV</a>'''
    head=f'''<section class="admin-head admin-head-pro"><div><span class="eyebrow">DELISA CONTROL ROOM</span><h1>{esc(title)}</h1><p class="muted">کنترل کامل محصولات، سفارش‌ها، مشتری‌ها و تحلیل فروش در یک نگاه.</p></div><div class="admin-head-actions"><a class="btn btn-light" href="/">نمایش فروشگاه</a><a class="btn" href="/admin/products/new">محصول جدید</a></div></section><nav class="admin-nav">{menu}</nav>'''
    return layout(f'<div class="container admin-wrap">{head}{content}</div>',title+' | مدیریت دلیسا',sess,'/admin')


def admin_dashboard(conn,sess):
    stats={}
    for key, sql in {'products':'SELECT COUNT(*) FROM products WHERE active=1',
        'customers':"SELECT COUNT(*) FROM users WHERE role='customer'",
        'orders':'SELECT COUNT(*) FROM orders',
        'revenue':"SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'",
        'views':'SELECT COUNT(*) FROM page_views',
        'visitors':'SELECT COUNT(DISTINCT visitor_hash) FROM page_views',
        'low':'SELECT COUNT(*) FROM products WHERE active=1 AND stock<=3',
        'pending':"SELECT COUNT(*) FROM orders WHERE status='pending'",
        'discounts':"SELECT COALESCE(SUM(discount_amount),0) FROM orders",
        'avg':"SELECT COALESCE(AVG(total),0) FROM orders WHERE status!='cancelled'"}.items():
        stats[key]=conn.execute(sql).fetchone()[0]
    conversion = f"{(100*stats['orders']/stats['visitors']):.1f}٪" if stats['visitors'] else '۰٪'
    kpi_cards=[('درآمد کل',money(stats['revenue']),'ارزش کل سفارش‌های ثبت‌شده'),('میانگین سبد خرید',money(int(stats['avg'] or 0)),'میانگین مبلغ هر سفارش'),('مجموع تخفیف‌ها',money(stats['discounts']),'تخفیف محصول و کد'),('نرخ تبدیل تقریبی',conversion,'سفارش نسبت به بازدیدکننده'),('سفارش‌های در انتظار',stats['pending'],'نیازمند پیگیری'),('موجودی کم',stats['low'],'محصولات با موجودی ≤ ۳')]
    tiles_html=''.join(f'<article class="stat stat-pro"><small>{name}</small><strong>{val}</strong><span>{desc}</span></article>' for name,val,desc in kpi_cards)
    since=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=13)).date().isoformat()
    graph=conn.execute('SELECT created_day, COUNT(*) AS hits, COUNT(DISTINCT visitor_hash) AS visitors FROM page_views WHERE created_day>=? GROUP BY created_day ORDER BY created_day',(since,)).fetchall()
    max_hits=max((r['hits'] for r in graph),default=1)
    graph_html=''.join(f'<div class="barrow pro"><span>{esc(r["created_day"][5:])}</span><div class="bar-track"><div class="bar-fill" style="width:{int(100*r["hits"]/max_hits)}%"></div></div><small>{r["hits"]} بازدید · {r["visitors"]} نفر</small></div>' for r in graph) or '<p class="muted">هنوز داده‌ای نیست.</p>'
    status_rows=conn.execute('SELECT status, COUNT(*) AS count, COALESCE(SUM(total),0) AS total FROM orders GROUP BY status ORDER BY count DESC').fetchall()
    max_status=max((r['count'] for r in status_rows),default=1)
    status_html=''.join(f'<div class="barrow pro"><span>{esc(STATUS.get(r["status"],r["status"]))}</span><div class="bar-track"><div class="bar-fill is-soft" style="width:{int(100*r["count"]/max_status)}%"></div></div><small>{r["count"]} سفارش · {money(r["total"] )}</small></div>' for r in status_rows) or '<p class="muted">سفارشی ثبت نشده.</p>'
    top_products=conn.execute('SELECT oi.product_name, SUM(oi.quantity) AS qty, SUM(oi.quantity*oi.unit_price) AS revenue FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.status!=? GROUP BY oi.product_name ORDER BY qty DESC, revenue DESC LIMIT 6',('cancelled',)).fetchall()
    top_products_html=''.join(f'<div class="summary-line"><span>{esc(r["product_name"])} <small>× {r["qty"]}</small></span><strong>{money(r["revenue"] )}</strong></div>' for r in top_products) or '<p class="muted">فروشی ثبت نشده.</p>'
    low_stock=conn.execute('SELECT id,name,stock FROM products WHERE active=1 ORDER BY stock ASC, id DESC LIMIT 6').fetchall()
    low_stock_html=''.join(f'<div class="summary-line"><span>{esc(r["name"] )}</span><strong>{r["stock"]}</strong></div>' for r in low_stock) or '<p class="muted">محصولی وجود ندارد.</p>'
    promo_rows=conn.execute('SELECT code,used_count,kind,value FROM coupons ORDER BY used_count DESC, id DESC LIMIT 5').fetchall()
    promo_html=''.join(f'<div class="summary-line"><span><code dir="ltr">{esc(r["code"])} </code></span><strong>{r["used_count"]} استفاده</strong></div>' for r in promo_rows) or '<p class="muted">کد تخفیفی ساخته نشده.</p>'
    quick=f'''<section class="admin-quick-grid"><a class="quick-card" href="/admin/products"><strong>{stats['products']}</strong><span>مدیریت محصولات</span></a><a class="quick-card" href="/admin/orders"><strong>{stats['orders']}</strong><span>پیگیری سفارش‌ها</span></a><a class="quick-card" href="/admin/accounting"><strong>{money(stats['revenue'])}</strong><span>گزارش حسابداری</span></a><a class="quick-card" href="/admin/users"><strong>{stats['customers']}</strong><span>مشتری ثبت‌شده</span></a></section>'''
    body=f'<section class="stats stats-pro">{tiles_html}</section>{quick}<div class="admin-columns admin-columns-pro"><section class="panel glass-panel"><h2>روند بازدید ۱۴ روز اخیر</h2>{graph_html}</section><section class="panel glass-panel"><h2>وضعیت سفارش‌ها</h2>{status_html}</section></div><div class="admin-columns admin-columns-pro admin-columns-3"><section class="panel glass-panel"><h2>پرفروش‌ترین‌ها</h2>{top_products_html}</section><section class="panel glass-panel"><h2>نیازمند تأمین موجودی</h2>{low_stock_html}</section><section class="panel glass-panel"><h2>عملکرد کدهای تخفیف</h2>{promo_html}</section></div><p class="muted">آمار بازدید بدون ذخیره IP است. بازدیدکننده یکتا بر اساس نشست مرورگر شمارش می‌شود و با تعداد افراد واقعی یکسان نیست.</p>'
    return admin_layout(body,'داشبورد',sess)


def admin_accounting(conn,sess):
    require_user(sess,True)
    total_revenue = conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'").fetchone()[0]
    total_discounts = conn.execute('SELECT COALESCE(SUM(discount_amount),0) FROM orders').fetchone()[0]
    shipping_cities = conn.execute('SELECT city, COUNT(*) AS orders, COALESCE(SUM(total),0) AS total FROM orders GROUP BY city ORDER BY total DESC, orders DESC LIMIT 8').fetchall()
    top_products = conn.execute('SELECT oi.product_name, SUM(oi.quantity) AS qty, SUM(oi.quantity*oi.unit_price) AS revenue FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.status!=? GROUP BY oi.product_name ORDER BY revenue DESC, qty DESC LIMIT 8',('cancelled',)).fetchall()
    daily = conn.execute('SELECT substr(created_at,1,10) AS day, COUNT(*) AS orders, COALESCE(SUM(total),0) AS total FROM orders WHERE substr(created_at,1,10)>=? GROUP BY day ORDER BY day',((dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=29)).date().isoformat(),)).fetchall()
    max_total = max((r['total'] for r in daily), default=1)
    daily_html = ''.join(f'<div class="barrow pro"><span>{esc(r["day"][5:])}</span><div class="bar-track"><div class="bar-fill" style="width:{int(100*r["total"]/max_total) if max_total else 0}%"></div></div><small>{money(r["total"] )} · {r["orders"]} سفارش</small></div>' for r in daily) or '<p class="muted">هنوز سفارشی ثبت نشده.</p>'
    top_products_html = ''.join(f'<div class="summary-line"><span>{esc(r["product_name"])} <small>× {r["qty"]}</small></span><strong>{money(r["revenue"] )}</strong></div>' for r in top_products) or '<p class="muted">فروشی ثبت نشده.</p>'
    city_html = ''.join(f'<div class="summary-line"><span>{esc(r["city"] or "—")}</span><strong>{money(r["total"] )} <small>· {r["orders"]} سفارش</small></strong></div>' for r in shipping_cities) or '<p class="muted">هنوز داده‌ای وجود ندارد.</p>'
    coupon_rows = conn.execute('SELECT code,kind,value,used_count FROM coupons ORDER BY used_count DESC, id DESC LIMIT 8').fetchall()
    coupon_html = ''.join(f'<div class="summary-line"><span><code dir="ltr">{esc(r["code"])} </code></span><strong>{r["used_count"]} بار</strong></div>' for r in coupon_rows) or '<p class="muted">کد تخفیفی ندارید.</p>'
    recent = conn.execute('SELECT id,full_name,total,status,created_at FROM orders ORDER BY id DESC LIMIT 8').fetchall()
    recent_html = ''.join(f'<tr><td>#{r["id"]}</td><td>{esc(r["full_name"] )}</td><td>{money(r["total"] )}</td><td>{esc(STATUS.get(r["status"],r["status"]))}</td><td>{esc(r["created_at"][:10])}</td></tr>' for r in recent)
    body=f'''<section class="stats stats-pro accounting-kpis"><article class="stat stat-pro"><small>فروش کل</small><strong>{money(total_revenue)}</strong><span>بدون سفارش‌های لغوشده</span></article><article class="stat stat-pro"><small>تخفیف اعطا شده</small><strong>{money(total_discounts)}</strong><span>محصول + کد تخفیف</span></article><article class="stat stat-pro"><small>درآمد خالص تقریبی</small><strong>{money(max(total_revenue-total_discounts,0))}</strong><span>قبل از هزینه‌ها</span></article><article class="stat stat-pro"><small>تعداد شهرهای فعال</small><strong>{len(shipping_cities)}</strong><span>بر اساس سفارش‌های ثبت‌شده</span></article></section><div class="admin-columns admin-columns-pro"><section class="panel glass-panel"><h2>گردش فروش ۳۰ روز اخیر</h2>{daily_html}</section><section class="panel glass-panel"><h2>فروش به تفکیک شهر</h2>{city_html}</section></div><div class="admin-columns admin-columns-pro admin-columns-3"><section class="panel glass-panel"><h2>محصولات درآمدساز</h2>{top_products_html}</section><section class="panel glass-panel"><h2>کدهای تخفیف فعال</h2>{coupon_html}</section><section class="panel glass-panel"><h2>نکات حسابداری</h2><div class="summary-line"><span>اتصال درگاه</span><strong>فعال نیست</strong></div><div class="summary-line"><span>نوع فروش</span><strong>آزمایشی / دمو</strong></div><div class="summary-line"><span>تسویه</span><strong>دستی</strong></div><p class="muted tiny">این بخش برای تحلیل فروش و مدیریت داخلی آماده شده و تا پیش از اتصال درگاه، جنبه عملیاتی کامل ندارد.</p></section></div><section class="panel glass-panel"><h2>آخرین سفارش‌ها</h2><div class="table-wrap"><table><thead><tr><th>سفارش</th><th>مشتری</th><th>مبلغ</th><th>وضعیت</th><th>تاریخ</th></tr></thead><tbody>{recent_html}</tbody></table></div></section>'''
    return admin_layout(body,'حسابداری و تحلیل فروش',sess)


def admin_products(conn,sess):
    rows=conn.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
    items=''.join(f'''<tr><td><img class="table-thumb" src="{esc(p['image'])}" alt=""></td><td>{esc(p['name'])}<br><small>{esc(p['category'])}</small></td><td>{money(p['price'])}{f'<br><small class="admin-sale-note">٪{sale_info(p)["percent"]} تخفیف</small>' if sale_info(p) else ''}</td><td>{p['stock']}</td><td>{'فعال' if p['active'] else 'آرشیو'}</td><td><a href="/admin/products/{p['id']}/edit" class="small-link">ویرایش</a> <form class="inline" method="post" action="/admin/products/{p['id']}/toggle"><input type="hidden" name="csrf" value="{esc(sess['csrf'])}"><button class="small-link" type="submit">{'آرشیو' if p['active'] else 'فعال‌سازی'}</button></form></td></tr>''' for p in rows)
    body=f'''<a href="/admin/products/new" class="btn">+ محصول جدید</a><div class="table-wrap"><table><thead><tr><th>تصویر</th><th>محصول</th><th>قیمت</th><th>موجودی</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>{items}</tbody></table></div>'''
    return admin_layout(body,'محصولات',sess)


def admin_product_form(conn,sess,product_id=None,error=''):
    p=row_dict(conn.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()) if product_id else None
    if product_id and not p:raise HTTPError(404,'محصول پیدا نشد.')
    val=lambda k:esc(p.get(k,'') if p else '')
    current_colors=product_colors(p) if p else []
    existing_photos=conn.execute('SELECT id,image,color FROM product_images WHERE product_id=? ORDER BY sort_order,id',(product_id,)).fetchall() if p else []
    preview=f'<div class="admin-cover"><img class="edit-preview" src="{val("image")}" alt="تصویر اصلی"><span>عکس کاور فعلی</span></div>' if p and p['image'] else ''
    extra_html=''.join(f'<div class="admin-photo"><img src="{esc(x["image"])}" loading="lazy" alt="تصویر اضافه"><label>رنگ این عکس (اختیاری)<input name="photo_color_{x["id"]}" value="{esc(x["color"])}" placeholder="مثلاً سرمه‌ای"></label><label class="checkbox"><input type="checkbox" name="remove_img_{x["id"]}" value="1">حذف این عکس</label></div>' for x in existing_photos)
    upload_slots=''.join(f'<div class="photo-upload-row"><label>عکس {i} <input name="image_{i}" type="file" accept="image/png,image/jpeg,image/webp"></label><label>رنگ عکس (اختیاری) <input name="new_photo_color_{i}" maxlength="36" placeholder="نام یکی از رنگ‌های محصول"></label></div>' for i in range(1,6))
    body=f'''<div class="panel product-editor"><p class="muted">عکس‌های واقعی WebP ترجیحاً کمتر از ۳۰۰ کیلوبایت باشند. حداکثر هر فایل ۵ مگابایت؛ تا ۱۲ عکس اضافه برای هر محصول.</p>{f'<div class="alert">{esc(error)}</div>' if error else ''}<form method="post" enctype="multipart/form-data" action="/admin/products/{product_id if product_id else 'new'}/edit" class="form">
    <input type="hidden" name="csrf" value="{esc(sess['csrf'])}">
    <label>نام محصول <input name="name" required maxlength="120" value="{val('name')}"></label>
    <label>آدرس انگلیسی اختیاری (slug) <input dir="ltr" name="slug" maxlength="75" value="{val('slug')}"></label>
    <label>دسته‌بندی <input name="category" maxlength="70" required value="{val('category')}"></label>
    <div class="form-row"><label>قیمت (تومان) <input name="price" type="number" min="0" step="1" required value="{val('price')}"></label><label>قیمت قبلی (نمایش تخفیف) <input name="compare_price" type="number" min="0" step="1" value="{val('compare_price') if p else 0}"></label><label>موجودی کلی <input name="stock" type="number" min="0" step="1" required value="{val('stock') if p else 0}"></label></div>
    <label>توضیحات <textarea name="description" maxlength="3000" rows="5">{val('description')}</textarea></label>
    <section class="admin-editor-group"><h2>رنگ‌بندی</h2><p class="muted">اگر محصول رنگ‌بندی دارد، نام رنگ‌ها را با ویرگول جدا کن؛ مثل «سرمه‌ای، استخوانی، مشکی». موجودی در این نسخه بین تمام رنگ‌ها مشترک است.</p><label>رنگ‌های محصول <input name="colors" maxlength="550" value="{esc('، '.join(current_colors))}" placeholder="سرمه‌ای، استخوانی، مشکی"></label><label>رنگ عکس کاور <input name="primary_color" maxlength="36" value="{val('primary_color')}" placeholder="یکی از رنگ‌های بالا یا خالی"></label></section>
    <section class="admin-editor-group"><h2>گالری محصول</h2><label>عکس اصلی / کاور<input name="image" type="file" accept="image/png,image/jpeg,image/webp"></label>{preview}
    <div class="admin-photo-grid">{extra_html}</div><h3>افزودن عکس‌های جدید</h3>{upload_slots}<p class="muted tiny">فایل‌هایی که انتخاب نکنی، نادیده گرفته می‌شوند. برای عکس‌های مرتبط با هر رنگ، همان نام را وارد کن.</p></section>
    <label class="checkbox"><input type="checkbox" name="active" value="1" {'checked' if p is None or p['active'] else ''}> محصول فعال و قابل نمایش باشد</label>
    <button class="btn" type="submit">ذخیره محصول و گالری</button></form></div>'''
    return admin_layout(body,'ویرایش محصول' if p else 'افزودن محصول',sess)


def admin_coupons(conn,sess):
    rows = conn.execute('SELECT * FROM coupons ORDER BY id DESC LIMIT 250').fetchall()
    details = ''
    for c in rows:
        discount = (str(c['value']) + '٪') if c['kind'] == 'percent' else money(c['value'])
        used = str(c['used_count']) + (' / ' + str(c['max_uses']) if c['max_uses'] else ' / نامحدود')
        is_active = bool(c['active'])
        details += f'''<tr><td><code dir="ltr">{esc(c['code'])}</code></td><td>{esc(discount)}</td><td>{money(c['min_total'])}</td><td>{esc(used)}</td><td>{esc(c['expires_on']) or 'بدون تاریخ'}</td><td>{'فعال' if is_active else 'غیرفعال'}</td><td><form method="post" action="/admin/coupons/{c['id']}/toggle"><input type="hidden" name="csrf" value="{esc(sess['csrf'])}"><button type="submit" class="small-link">{'غیرفعال کن' if is_active else 'فعال کن'}</button></form></td></tr>'''
    listing = '<div class="table-wrap"><table><thead><tr><th>کد</th><th>میزان</th><th>حداقل خرید</th><th>استفاده</th><th>انقضا</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>' + details + '</tbody></table></div>' if rows else '<p class="muted">هنوز کدی ساخته نشده است.</p>'
    form = f'''<section class="panel coupon-admin-panel"><h2>ساخت کد تخفیف</h2><p class="muted">کد از ۳ تا ۲۴ کاراکتر انگلیسی، عدد، خط تیره یا زیرخط تشکیل شود. درصد باید بین ۱ تا ۹۰ باشد. کد فقط هنگام ثبت سفارش معتبر می‌شود.</p><form class="form" method="post" action="/admin/coupons/new"><input name="csrf" type="hidden" value="{esc(sess['csrf'])}"><div class="form-row"><label>کد (انگلیسی)<input name="code" required dir="ltr" pattern="[A-Za-z0-9_-]{{3,24}}" placeholder="DELISA10" maxlength="24"></label><label>نوع تخفیف<select name="kind"><option value="percent">درصدی</option><option value="fixed">مبلغ ثابت (تومان)</option></select></label><label>مقدار<input name="value" type="number" min="1" required placeholder="10"></label></div><div class="form-row"><label>حداقل سبد (تومان)<input name="min_total" type="number" min="0" value="0"></label><label>حداکثر دفعات استفاده (صفر = نامحدود)<input name="max_uses" type="number" min="0" value="0"></label><label>تاریخ پایان (اختیاری)<input name="expires_on" type="date"></label></div><button class="btn" type="submit">ساخت کد تخفیف</button></form></section>'''
    return admin_layout(form + listing,'کدهای تخفیف',sess)


def admin_orders(conn,sess):
    rows=conn.execute('SELECT o.*,u.email FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC LIMIT 200').fetchall()
    opts=lambda current:''.join(f'<option value="{esc(k)}" {"selected" if k==current else ""}>{esc(v)}</option>' for k,v in STATUS.items())
    body='''<p class="notice">نسخه آزمایشی: پرداخت اینترنتی انجام نمی‌شود و هیچ وجهی دریافت نمی‌گردد.</p><div class="table-wrap"><table><thead><tr><th>سفارش</th><th>مشتری</th><th>شهر</th><th>اقلام</th><th>مبلغ</th><th>تاریخ</th><th>وضعیت</th></tr></thead><tbody>'''
    for o in rows:
        count=conn.execute('SELECT COALESCE(SUM(quantity),0) FROM order_items WHERE order_id=?',(o['id'],)).fetchone()[0]
        body+=f'''<tr><td><a class="small-link" href="/account/orders/{o['id']}">#{o['id']}</a></td><td>{esc(o['full_name'])}<br><small>{esc(o['phone'])}</small></td><td>{esc(o['city'])}</td><td>{count}</td><td>{money(o['total'])}</td><td>{esc(o['created_at'][:10])}</td><td><form method="post" action="/admin/orders/{o['id']}/status" class="status-form"><input type="hidden" name="csrf" value="{esc(sess['csrf'])}"><select name="status">{opts(o['status'])}</select><button class="small-link">ثبت</button></form></td></tr>'''
    body+='</tbody></table></div>'
    return admin_layout(body,'سفارش‌ها',sess)


def admin_users(conn,sess):
    rows=conn.execute('SELECT u.id,u.name,u.email,u.phone,u.role,u.created_at,COUNT(o.id) AS orders FROM users u LEFT JOIN orders o ON o.user_id=u.id GROUP BY u.id ORDER BY u.id DESC LIMIT 200').fetchall()
    cells=''.join(f'<tr><td>{r["id"]}</td><td>{esc(r["name"])}</td><td dir="ltr">{esc(r["email"])}</td><td>{esc(r["phone"])}</td><td>{"مدیر" if r["role"]=="admin" else "مشتری"}</td><td>{r["orders"]}</td></tr>' for r in rows)
    return admin_layout(f'<div class="table-wrap"><table><thead><tr><th>کد</th><th>نام</th><th>ایمیل</th><th>موبایل</th><th>نقش</th><th>سفارش‌ها</th></tr></thead><tbody>{cells}</tbody></table></div>','کاربران',sess)


def error_page(status,message,sess):
    inner=f'<section class="container center-error"><h1>{status}</h1><p>{esc(message)}</p><a href="/" class="btn">بازگشت به فروشگاه</a></section>'
    if sess: return layout(inner,'خطا | دلیسا',sess,'/error')
    return Response('<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>خطا</title><body style="font:20px Tahoma;padding:40px"><h1>'+str(status)+'</h1><p>'+esc(message)+'</p><a href="/">خانه</a></body></html>',status)


def main_handler(req,conn,sess):
    p=req.path;m=req.method
    # Read-only pages -------------------------------------------------
    if m=='GET':
        if p=='/':return home(conn,sess)
        if p=='/shop':return shop(conn,sess,req)
        match=re.fullmatch(r'/product/([\w\-]+)',p)
        if match:return product_page(conn,sess,match[1])
        if p=='/login':return login_page(sess)
        if p=='/register':return register_page(sess)
        if p=='/account':return account_page(conn,sess) if sess.get('uid') else redirect('/login')
        if p=='/checkout':return checkout_page(conn,sess) if sess.get('uid') else redirect('/login')
        match=re.fullmatch(r'/account/orders/(\d+)',p)
        if match:return order_detail(conn,sess,int(match[1])) if sess.get('uid') else redirect('/login')
        if p=='/admin':require_user(sess,True);return admin_dashboard(conn,sess)
        if p=='/admin/products':require_user(sess,True);return admin_products(conn,sess)
        if p=='/admin/accounting':require_user(sess,True);return admin_accounting(conn,sess)
        if p=='/admin/coupons':require_user(sess,True);return admin_coupons(conn,sess)
        if p=='/admin/products/new':require_user(sess,True);return admin_product_form(conn,sess)
        match=re.fullmatch(r'/admin/products/(\d+)/edit',p)
        if match:require_user(sess,True);return admin_product_form(conn,sess,int(match[1]))
        if p=='/admin/orders':require_user(sess,True);return admin_orders(conn,sess)
        if p=='/admin/users':require_user(sess,True);return admin_users(conn,sess)
        if p=='/admin/export/orders':
            require_user(sess,True);return raw_csv(conn.execute('SELECT * FROM orders ORDER BY id DESC').fetchall())
        if p=='/api/cart':return json_response(cart_data(conn,sess))
        if p=='/api/search':
            q=req.query.get('q','').strip()[:60]
            if len(q)<2:return json_response({'products':[]})
            rows=conn.execute('SELECT id,slug,name,price,image,stock FROM products WHERE active=1 AND name LIKE ? ORDER BY id DESC LIMIT 8',(f'%{q}%',)).fetchall()
            return json_response({'products':[dict(r) for r in rows]})
    # All mutations (including authentication) require a CSRF token.
    if m=='POST':require_csrf(req,sess)
    if m=='POST' and p=='/login':
        email=str(req.value('email')).strip().lower()[:254]
        password=str(req.value('password'))
        # Per-process basic failure limiter: for MVP only, use proxy rate limiting in production.
        key=email+'|'+req.env.get('REMOTE_ADDR','')
        attempts=[t for t in LOGIN_FAILURES.get(key,[]) if time.time()-t<600]
        if len(attempts)>=7:raise HTTPError(429,'تلاش ناموفق زیاد است؛ ۱۰ دقیقه بعد امتحان کنید.')
        user=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if not user or not verify_password(password,user['password_hash']):
            LOGIN_FAILURES[key]=(attempts+[time.time()])
            return Response(login_page(sess,'ایمیل یا رمز عبور اشتباه است.').body,400)
        LOGIN_FAILURES.pop(key,None)
        # rotate session ID after authentication; move cart, prevent fixation
        return authenticate(conn,sess,user['id'],'/admin' if user['role']=='admin' else '/account')
    if m=='POST' and p=='/register':
        name=str(req.value('name')).strip()[:100]
        email=str(req.value('email')).strip().lower()[:254]
        phone=str(req.value('phone')).strip()[:30]
        password=str(req.value('password'))
        if len(name)<2 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(password)<8:
            return Response(register_page(sess,'نام معتبر، ایمیل و رمز حداقل ۸ کاراکتر لازم است.').body,400)
        if conn.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
            return Response(register_page(sess,'این ایمیل قبلاً ثبت شده است.').body,400)
        with conn:
            cursor=conn.execute("INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",(name,email,phone,password_hash(password),'customer',now()))
        return authenticate(conn,sess,cursor.lastrowid,'/account')
    if m=='POST' and p=='/logout':
        conn.execute('UPDATE sessions SET user_id=NULL WHERE id_hash=?',(sess['id_hash'],))
        conn.commit()
        return redirect('/')
    if m=='POST' and p=='/api/track-view':
        path=str(req.value('path','/'))[:180]
        if not (path=='/' or path=='/shop' or path.startswith('/product/')):raise HTTPError(400,'مسیر معتبر نیست.')
        public_view(conn,sess,path)
        return json_response({'ok':True})
    if m=='POST' and p=='/api/coupon/preview':
        require_user(sess)
        cart = cart_data(conn,sess)
        if not cart['items']:raise HTTPError(400, 'سبد خرید خالی است.')
        coupon, discount = coupon_for_total(conn,req.value('code',''),cart['total'])
        return json_response({'code':coupon['code'] if coupon else '', 'subtotal':cart['total'], 'discount':discount,'total':cart['total']-discount})
    if m=='POST' and p=='/api/cart':
        try:pid=int(req.value('product_id'));qty=int(req.value('qty',1))
        except (ValueError,TypeError):raise HTTPError(400,'محصول یا تعداد نامعتبر')
        color=str(req.value('color','')).strip()
        prod=conn.execute('SELECT id,stock,active,colors FROM products WHERE id=?',(pid,)).fetchone()
        if not prod or not prod['active']:raise HTTPError(404,'محصول ناموجود است.')
        if not color_allowed(prod,color):raise HTTPError(400,'رنگ انتخاب‌شده معتبر نیست.')
        current=conn.execute('SELECT qty FROM carts WHERE session_hash=? AND product_id=? AND color=?',(sess['id_hash'],pid,color)).fetchone()
        newqty=(current['qty'] if current else 0)+qty
        if newqty<0:raise HTTPError(400,'تعداد نامعتبر است.')
        with conn:
            if newqty==0:
                conn.execute('DELETE FROM carts WHERE session_hash=? AND product_id=? AND color=?',(sess['id_hash'],pid,color))
            else:
                combined=conn.execute('SELECT COALESCE(SUM(qty),0) FROM carts WHERE session_hash=? AND product_id=? AND NOT (product_id=? AND color=?)',(sess['id_hash'],pid,pid,color)).fetchone()[0]
                if combined+newqty>prod['stock']:raise HTTPError(409,f'فقط {prod["stock"]} عدد از این محصول موجود است.')
                conn.execute('INSERT INTO carts(session_hash,product_id,color,qty) VALUES(?,?,?,?) ON CONFLICT(session_hash,product_id,color) DO UPDATE SET qty=excluded.qty',(sess['id_hash'],pid,color,newqty))
        return json_response(cart_data(conn,sess))
    if m=='POST' and p=='/api/cart/remove':
        try:pid=int(req.value('product_id'))
        except (TypeError,ValueError):raise HTTPError(400,'محصول نامعتبر')
        color=str(req.value('color','')).strip()
        with conn:conn.execute('DELETE FROM carts WHERE session_hash=? AND product_id=? AND color=?',(sess['id_hash'],pid,color))
        return json_response(cart_data(conn,sess))
    if m=='POST' and p=='/api/favorites':
        require_user(sess)
        try:pid=int(req.value('product_id'))
        except (ValueError,TypeError):raise HTTPError(400,'محصول نامعتبر')
        if not conn.execute('SELECT id FROM products WHERE id=? AND active=1',(pid,)).fetchone():raise HTTPError(404,'محصول یافت نشد')
        with conn:
            found=conn.execute('SELECT 1 FROM favorites WHERE user_id=? AND product_id=?',(sess['uid'],pid)).fetchone()
            if found:conn.execute('DELETE FROM favorites WHERE user_id=? AND product_id=?',(sess['uid'],pid))
            else:conn.execute('INSERT INTO favorites(user_id,product_id) VALUES(?,?)',(sess['uid'],pid))
        return json_response({'saved':not bool(found)})
    if m=='POST' and p=='/checkout':
        require_user(sess)
        full_name=str(req.value('full_name')).strip()[:100]
        phone=str(req.value('phone')).strip()[:30]
        city=str(req.value('city')).strip()[:80]
        address=str(req.value('address')).strip()[:350]
        postal_code=str(req.value('postal_code')).strip()[:25]
        note=str(req.value('note')).strip()[:300]
        entered_code=str(req.value('coupon_code','')).strip()
        if not full_name or not re.fullmatch(r'(?:\+98|0)?9\d{9}',phone) or len(city)<2 or len(address)<8:
            raise HTTPError(400,'نام، شماره موبایل ایرانی، شهر و آدرس کامل را بررسی کنید.')
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            items=conn.execute('SELECT c.product_id,c.color,c.qty,p.name,p.price,p.stock,p.active,p.colors FROM carts c JOIN products p ON p.id=c.product_id WHERE c.session_hash=?',(sess['id_hash'],)).fetchall()
            if not items:raise HTTPError(400,'سبد خرید خالی است.')
            total=0
            combined={}
            for item in items:
                if not item['active'] or not color_allowed(item,item['color']):
                    raise HTTPError(409,'یک محصول یا رنگ انتخاب‌شده تغییر کرده؛ سبد خرید را بررسی کنید.')
                combined[item['product_id']]=combined.get(item['product_id'],0)+item['qty']
                total += item['price']*item['qty']
            for pid,quantity in combined.items():
                updated=conn.execute('UPDATE products SET stock=stock-?,updated_at=? WHERE id=? AND stock>=? AND active=1',(quantity,now(),pid,quantity))
                if updated.rowcount!=1:raise HTTPError(409,'موجودی یک یا چند محصول تغییر کرده است؛ سبد خرید را بررسی کنید.')
            subtotal=total
            coupon,discount=coupon_for_total(conn,entered_code,subtotal)
            total=subtotal-discount
            if coupon:
                used=conn.execute('UPDATE coupons SET used_count=used_count+1 WHERE id=? AND (max_uses=0 OR used_count<max_uses)',(coupon['id'],))
                if used.rowcount != 1:raise HTTPError(409,'ظرفیت این کد تخفیف تکمیل شده است.')
            cursor=conn.execute('INSERT INTO orders(user_id,full_name,phone,city,address,postal_code,note,total,status,payment_status,created_at,subtotal,discount_amount,coupon_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(sess['uid'],full_name,phone,city,address,postal_code,note,total,'pending','not_connected',now(),subtotal,discount,coupon['code'] if coupon else ''))
            oid=cursor.lastrowid
            for item in items:conn.execute('INSERT INTO order_items(order_id,product_id,product_name,unit_price,quantity,color) VALUES(?,?,?,?,?,?)',(oid,item['product_id'],item['name'],item['price'],item['qty'],item['color']))
            conn.execute('DELETE FROM carts WHERE session_hash=?',(sess['id_hash'],))
        return redirect('/account/orders/'+str(oid))
    if m=='POST' and p.startswith('/admin/'):
        require_user(sess,True)
        if p=='/admin/coupons/new':
            code=str(req.value('code','')).strip().upper()
            kind=str(req.value('kind',''))
            try:
                value=int(req.value('value',''))
                minimum=int(req.value('min_total',0) or 0)
                maximum=int(req.value('max_uses',0) or 0)
            except (ValueError,TypeError):raise HTTPError(400, 'مقادیر کد تخفیف باید عددی باشند.')
            expiry=str(req.value('expires_on','')).strip()
            if not re.fullmatch(r'[A-Z0-9_-]{3,24}',code) or kind not in ('percent','fixed'):
                raise HTTPError(400,'کد یا نوع تخفیف معتبر نیست.')
            if value<=0 or (kind=='percent' and value>90) or (kind=='fixed' and value>10**12) or minimum<0 or minimum>10**12 or maximum<0 or maximum>10**7:
                raise HTTPError(400,'مقدار تخفیف یا محدودیت استفاده معتبر نیست.')
            if expiry:
                try:dt.date.fromisoformat(expiry)
                except ValueError:raise HTTPError(400,'تاریخ انقضا معتبر نیست.')
                if expiry<today():raise HTTPError(400,'تاریخ پایان نمی‌تواند در گذشته باشد.')
            if conn.execute('SELECT 1 FROM coupons WHERE code=?',(code,)).fetchone():raise HTTPError(409,'این کد تخفیف قبلاً ثبت شده است.')
            with conn:
                conn.execute('INSERT INTO coupons(code,kind,value,min_total,max_uses,expires_on,active,created_at) VALUES(?,?,?,?,?,?,1,?)',(code,kind,value,minimum,maximum,expiry,now()))
            return redirect('/admin/coupons')
        coupon_match=re.fullmatch(r'/admin/coupons/(\d+)/toggle',p)
        if coupon_match:
            with conn:conn.execute('UPDATE coupons SET active=1-active WHERE id=?',(int(coupon_match[1]),))
            return redirect('/admin/coupons')
        match=re.fullmatch(r'/admin/products/(new|\d+)/edit',p)
        if match:
            pid=None if match[1]=='new' else int(match[1])
            existing=conn.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone() if pid else None
            if pid and not existing:raise HTTPError(404,'محصول پیدا نشد.')
            name=str(req.value('name')).strip()[:120]
            slug=slugify(str(req.value('slug')).strip() or name)
            category=str(req.value('category')).strip()[:70]
            description=str(req.value('description')).strip()[:3000]
            try:price=int(req.value('price'));compare=int(req.value('compare_price',0) or 0);stock=int(req.value('stock'))
            except (ValueError,TypeError):raise HTTPError(400,'قیمت و موجودی باید عدد باشند.')
            if not name or not category or price<0 or compare<0 or stock<0 or price>10**12 or compare>10**12 or stock>10**6:raise HTTPError(400,'نام، دسته، قیمت و موجودی را بررسی کنید.')
            if compare and compare <= price:
                raise HTTPError(400, 'قیمت قبلی باید بیشتر از قیمت فروش باشد؛ یا آن را صفر بگذارید.')
            duplicate=conn.execute('SELECT id FROM products WHERE slug=? AND id!=?',(slug,pid or -1)).fetchone()
            if duplicate:raise HTTPError(409,'این آدرس (slug) قبلاً استفاده شده است.')
            colors=parse_colors(req.value('colors',''))
            primary_color=str(req.value('primary_color','')).strip()
            if primary_color and primary_color not in colors:raise HTTPError(400,'رنگ عکس کاور باید یکی از رنگ‌های تعریف‌شده باشد.')
            if existing:
                old_images=conn.execute('SELECT id,image,color FROM product_images WHERE product_id=?',(pid,)).fetchall()
            else:old_images=[]
            kept=[x for x in old_images if req.value('remove_img_'+str(x['id']), '')!='1']
            removing=[x for x in old_images if req.value('remove_img_'+str(x['id']), '')=='1']
            photo_changes={}
            for x in kept:
                updated_color=str(req.value('photo_color_'+str(x['id']),x['color'])).strip()
                if updated_color and updated_color not in colors:
                    raise HTTPError(400,'رنگ عکس گالری باید یکی از رنگ‌های محصول باشد.')
                photo_changes[x['id']]=updated_color
            to_upload=[]
            for i in range(1,6):
                name_key='image_'+str(i)
                if req.files.get(name_key) and req.files[name_key][0]:
                    image_color=str(req.value('new_photo_color_'+str(i),'')).strip()
                    if image_color and image_color not in colors:
                        raise HTTPError(400,'رنگ عکس جدید باید با یکی از رنگ‌های محصول مطابقت داشته باشد.')
                    to_upload.append((name_key,image_color))
            if len(kept)+len(to_upload)>12:raise HTTPError(400,'حداکثر ۱۲ عکس اضافه برای هر محصول قابل ثبت است.')
            written=[]
            try:
                new_image=write_upload(req)
                if new_image:written.append(new_image)
                more=[]
                for key,image_color in to_upload:
                    src=write_upload(req,key)
                    if src:written.append(src);more.append((src,image_color))
                image=new_image or (existing['image'] if existing else '/static/img/vest.svg')
                with conn:
                    if existing:
                        conn.execute('UPDATE products SET slug=?,name=?,category=?,description=?,price=?,compare_price=?,stock=?,image=?,active=?,updated_at=?,colors=?,primary_color=? WHERE id=?',(slug,name,category,description,price,compare,stock,image,int(req.value('active','')=='1'),now(),json.dumps(colors,ensure_ascii=False),primary_color,pid))
                    else:
                        cursor=conn.execute('INSERT INTO products(slug,name,category,description,price,compare_price,stock,image,active,created_at,updated_at,colors,primary_color) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(slug,name,category,description,price,compare,stock,image,int(req.value('active','')=='1'),now(),now(),json.dumps(colors,ensure_ascii=False),primary_color))
                        pid=cursor.lastrowid
                    for x in removing:conn.execute('DELETE FROM product_images WHERE id=? AND product_id=?',(x['id'],pid))
                    for iid,color in photo_changes.items():conn.execute('UPDATE product_images SET color=? WHERE id=? AND product_id=?',(color,iid,pid))
                    for index,(src,color) in enumerate(more):
                        conn.execute('INSERT INTO product_images(product_id,image,color,sort_order) VALUES(?,?,?,?)',(pid,src,color,len(kept)+index))
            except Exception:
                for uploaded in written:delete_upload(uploaded)
                raise
            if existing and new_image and existing['image']!=new_image:delete_upload(existing['image'])
            for x in removing:delete_upload(x['image'])
            return redirect('/admin/products')
        match=re.fullmatch(r'/admin/products/(\d+)/toggle',p)
        if match:
            with conn:conn.execute('UPDATE products SET active=1-active,updated_at=? WHERE id=?',(now(),int(match[1])))
            return redirect('/admin/products')
        match=re.fullmatch(r'/admin/orders/(\d+)/status',p)
        if match:
            oid=int(match[1]);newstatus=str(req.value('status'))
            if newstatus not in STATUS:raise HTTPError(400,'وضعیت نامعتبر')
            with conn:
                order=conn.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()
                if not order:raise HTTPError(404,'سفارش پیدا نشد')
                if order['status']=='cancelled' and newstatus!='cancelled':raise HTTPError(409,'سفارش لغوشده قابل فعال‌سازی مجدد نیست؛ سفارش جدید ثبت کنید.')
                if order['status']=='delivered' and newstatus=='cancelled':raise HTTPError(409,'سفارش تحویل‌شده را از این پنل نمی‌توان لغو کرد.')
                if order['status']!='cancelled' and newstatus=='cancelled':
                    coupon_code=conn.execute('SELECT coupon_code FROM orders WHERE id=?',(oid,)).fetchone()['coupon_code']
                    if coupon_code:
                        conn.execute('UPDATE coupons SET used_count=MAX(0,used_count-1) WHERE code=?',(coupon_code,))
                    items=conn.execute('SELECT product_id,quantity FROM order_items WHERE order_id=?',(oid,)).fetchall()
                    for i in items:conn.execute('UPDATE products SET stock=stock+?,updated_at=? WHERE id=?',(i['quantity'],now(),i['product_id']))
                conn.execute('UPDATE orders SET status=? WHERE id=?',(newstatus,oid))
            return redirect('/admin/orders')
    raise HTTPError(404,'این صفحه پیدا نشد.')


# Threaded local development server: a slow image/API request must not block /login.
class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    request_queue_size = 64


LOGIN_FAILURES={}


def authenticate(conn,sess,user_id,target):
    token=secrets.token_hex(32)
    newhash=hashlib.sha256(token.encode()).hexdigest()
    with conn:
        conn.execute('INSERT INTO sessions(id_hash,user_id,csrf,created_at,expires_at) VALUES(?,?,?,?,?)',(newhash,user_id,secrets.token_urlsafe(32),now(),int(time.time())+1209600))
        conn.execute('UPDATE carts AS src SET session_hash=? WHERE session_hash=? AND NOT EXISTS (SELECT 1 FROM carts dst WHERE dst.session_hash=? AND dst.product_id=src.product_id AND dst.color=src.color)',(newhash,sess['id_hash'],newhash))
        conn.execute('DELETE FROM sessions WHERE id_hash=?',(sess['id_hash'],))
    response=redirect(target)
    response.headers.append(cookie_header(token))
    return response


def static_response(path):
    relative=path.removeprefix('/static/')
    file=(STATIC / relative).resolve()
    if not file.is_relative_to(STATIC.resolve()) or not file.is_file():raise HTTPError(404,'فایل پیدا نشد')
    content_type=mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
    # No user-uploaded SVG, HTML, or JS. SVGs are bundled trusted illustrations.
    if content_type.startswith('text/') or content_type=='image/svg+xml':content_type+='; charset=utf-8'
    return Response(file.read_bytes(),200,content_type,[('Cache-Control','public, max-age=86400'),('X-Content-Type-Options','nosniff')])


STATUSES={200:'OK',303:'See Other',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',409:'Conflict',413:'Content Too Large',429:'Too Many Requests',500:'Internal Server Error'}


def application(environ,start_response):
    conn=None;set_cookie=None;sess=None
    try:
        req=Request(environ)
        if req.path.startswith('/static/'):
            if req.method!='GET':raise HTTPError(405,'روش نامعتبر')
            response=static_response(req.path)
        else:
            conn=db_connect()
            sess,set_cookie=get_session(req,conn)
            response=main_handler(req,conn,sess)
            if req.method=='GET' and (req.path=='/' or req.path=='/shop' or req.path.startswith('/product/')) and not req.headers.get('x-partial-nav'):
                public_view(conn,sess,req.path)
    except HTTPError as exc:
        if 'req' in locals() and (req.path.startswith('/api/') or req.headers.get('accept','').startswith('application/json')):
            response=json_response({'error':exc.message},exc.status)
        else:
            response=error_page(exc.status,exc.message,sess)
            response.status=exc.status
    except Exception:
        import traceback
        traceback.print_exc()
        response=json_response({'error':'خطای داخلی سرور'},500) if 'req' in locals() and req.path.startswith('/api/') else error_page(500,'خطایی رخ داد. لطفاً دوباره تلاش کنید.',sess)
        response.status=500
    finally:
        if conn:conn.close()
    headers=response.headers+[('Content-Length',str(len(response.body)))]
    if set_cookie:headers.append(set_cookie)
    start_response(str(response.status)+' '+STATUSES.get(response.status,'OK'),headers)
    return [response.body]


def seed_demo():
    examples=[
      ('vest-navar','وست نوار کتان','وست','وست مینیمال با فرم آزاد و مناسب استایل‌های چندلایه. نمونه نمایشی است؛ مشخصات واقعی را جایگزین کنید.',1480000,1980000,8,'/static/img/vest.svg'),
      ('shirt-darya','شومیز دریا','شومیز','شومیز خوش‌فرم با خطوط ساده برای استایل روزمره و رسمی. این متن نمونه است.',1320000,0,12,'/static/img/shirt.svg'),
      ('trousers-mah','شلوار ماه','شلوار','شلوار خوش‌دوخت با فرم آزاد و استایل مینیمال. این متن نمونه است.',1280000,0,9,'/static/img/pants.svg'),
      ('set-lin','ست لین','ست','ست دو تکه برای استایل هماهنگ و مینیمال. تصویر و جزئیات نمونه هستند.',2450000,0,5,'/static/img/set.svg'),
      ('vest-saba','وست صبا','وست','یک انتخاب ساده برای لایه‌سازی استایل. این متن نمونه است.',1580000,0,7,'/static/img/vest2.svg'),
      ('shirt-hana','شومیز هانا','شومیز','طراحی مینیمال با تن‌خور آزاد. مشخصات پیش از فروش واقعی باید بازبینی شود.',1190000,0,4,'/static/img/shirt2.svg'),
    ]
    with closing(db_connect()) as conn:
        with conn:
            for p in examples:
                conn.execute('INSERT OR IGNORE INTO products(slug,name,category,description,price,compare_price,stock,image,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)',(*p,now(),now()))
    print('Demo products ready (existing products were not duplicated).')


def create_admin(email=None):
    import getpass
    email=(email or input('Admin email: ')).strip().lower()
    name=input('Admin name [Delisa Admin]: ').strip() or 'مدیر دلیسا'
    password=getpass.getpass('Admin password (minimum 12 characters): ')
    if len(password)<12 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
        sys.exit('Enter a valid email and a password of at least 12 characters.')
    with closing(db_connect()) as conn:
        if conn.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():sys.exit('This email already exists. Use another email for the new admin.')
        with conn:conn.execute('INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',(name,email,'',password_hash(password),'admin',now()))
    print('Admin account created. The password is not stored in plain text.')


def cli():
    parser=argparse.ArgumentParser(description='DELISA minimal storefront')
    parser.add_argument('command',choices=['run','init-db','seed-demo','create-admin','backup-db','cleanup'])
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--email',default=None)
    args=parser.parse_args()
    init_db()
    if args.command=='init-db':print('Database initialized:', DB)
    elif args.command=='seed-demo':seed_demo()
    elif args.command=='create-admin':create_admin(args.email)
    elif args.command=='backup-db':
        dest=DATA/'backups'/('delisa-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')+'.sqlite3')
        dest.parent.mkdir(parents=True,exist_ok=True)
        source=db_connect();target=sqlite3.connect(dest)
        try:source.backup(target)
        finally:target.close();source.close()
        print('Database backup created:', dest)
        print('Reminder: back up static/uploads separately.')
    elif args.command=='cleanup':
        with closing(db_connect()) as conn:
            with conn:
                removed=conn.execute('DELETE FROM sessions WHERE expires_at<?',(int(time.time()),)).rowcount
                conn.execute('DELETE FROM page_views WHERE created_day<?',((dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=365)).date().isoformat(),))
        print(f'Cleanup completed: {removed} expired sessions deleted; page views older than one year removed.')
    else:
        print(f'DELISA running: http://{args.host}:{args.port} (Ctrl+C to stop)')
        print('Development server only. See README_FA.md before public deployment.')
        with make_server(args.host, args.port, application, server_class=ThreadedWSGIServer) as server:
            server.serve_forever()


if __name__=='__main__':cli()
