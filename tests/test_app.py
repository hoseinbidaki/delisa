"""No dependencies: python -m unittest discover -s tests -v"""
import io
import json
import os
import re
import sys
import tempfile
import struct
import zlib
import unittest
from pathlib import Path
from contextlib import closing
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=(app.DATA,app.DB,app.UPLOAD)
        app.DATA=Path(self.tmp.name);app.DB=app.DATA/'test.sqlite3';app.UPLOAD=app.DATA/'uploads'
        app.init_db();app.seed_demo()
        self.cookie='';self.csrf=''
        home=self.call('GET','/')
        self.assertEqual(home[0],200)
        self.csrf=re.search(rb'<meta name="csrf-token" content="([^"]+)"',home[2]).group(1).decode()
    def tearDown(self):
        app.DATA,app.DB,app.UPLOAD=self.old
        self.tmp.cleanup()
    def call(self,method,path,data=None,content_type='application/x-www-form-urlencoded',headers=None):
        query=''
        if '?' in path:path,query=path.split('?',1)
        if isinstance(data,dict):
            body=(json.dumps(data,ensure_ascii=False).encode() if content_type=='application/json' else urlencode(data).encode())
        else:body=data or b''
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':query,'wsgi.input':io.BytesIO(body),'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':content_type,'REMOTE_ADDR':'127.0.0.1','HTTP_COOKIE':self.cookie}
        if headers:
            for k,v in headers.items():env['HTTP_'+k.upper().replace('-','_')]=v
        state={}
        def start(s,h):state.update(status=s,headers=h)
        response=b''.join(app.application(env,start));state['body']=response
        for key,v in state['headers']:
            if key.lower()=='set-cookie':self.cookie=v.split(';')[0]
        return int(state['status'][:3]),dict(state['headers']),response
    def post(self,path,data,as_json=False,csrf=True):
        headers={'X-CSRF-Token':self.csrf} if csrf else {}
        if not as_json and csrf:data={'csrf':self.csrf,**data}
        return self.call('POST',path,data,'application/json' if as_json else 'application/x-www-form-urlencoded',headers)
    def register(self):
        st,headers,data=self.post('/register',{'name':'ناسر تست','email':'naser@example.test','password':'very-safe-password','phone':'09121234567'})
        self.assertEqual(st,303,data.decode())
        status,h,body=self.call('GET','/account')
        self.assertEqual(status,200)
        self.csrf=re.search(rb'<meta name="csrf-token" content="([^"]+)"',body).group(1).decode()
    def admin(self):
        with closing(app.db_connect()) as conn:
            with conn:conn.execute('INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',('مدیر','admin@delisa.test','',app.password_hash('a-very-long-password'),'admin',app.now()))
        st,_,body=self.post('/login',{'email':'admin@delisa.test','password':'a-very-long-password'})
        self.assertEqual(st,303,body.decode())
        _,_,body=self.call('GET','/admin')
        self.csrf=re.search(rb'<meta name="csrf-token" content="([^"]+)"',body).group(1).decode()
    def test_home_shop_product_and_refresh(self):
        for url in ['/','/shop','/product/vest-navar','/shop?category=%D9%88%D8%B3%D8%AA']:
            st,headers,body=self.call('GET',url)
            self.assertEqual(st,200,url)
            self.assertIn(b'id="page-root"',body)
        st,headers,body=self.call('GET','/product/not-real')
        self.assertEqual(st,404)
    def test_session_and_csrf(self):
        st,h,b=self.post('/api/cart',{'product_id':1,'qty':1},as_json=True,csrf=False)
        self.assertEqual(st,403)
        st,h,b=self.call('GET','/static/css/style.css')
        self.assertEqual(st,200)
        self.assertIn(b'font:',b)
        st,h,b=self.call('GET','/static/../../app.py')
        self.assertEqual(st,404)
    def test_cart_and_order_atomic(self):
        self.register()
        st,h,b=self.post('/api/cart',{'product_id':1,'qty':2},as_json=True)
        self.assertEqual(st,200,b.decode())
        self.assertEqual(json.loads(b)['total'],2960000)
        st,h,b=self.post('/checkout',{'full_name':'ناسر','phone':'09121234567','city':'تهران','address':'خیابان نمونه پلاک ده'})
        self.assertEqual(st,303,b.decode())
        self.assertTrue(h['Location'].startswith('/account/orders/'))
        with closing(app.db_connect()) as conn:
            self.assertEqual(conn.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM carts').fetchone()[0],0)
            oid=conn.execute('SELECT id FROM orders').fetchone()[0]
        st,h,b=self.call('GET','/account/orders/'+str(oid))
        self.assertEqual(st,200)
        self.assertIn('سفارش'.encode(),b)
    def test_user_is_not_admin(self):
        self.register()
        st,h,b=self.call('GET','/admin')
        self.assertEqual(st,403)
        st,h,b=self.post('/admin/products/1/toggle',{})
        self.assertEqual(st,403)
    def test_admin_product_order_cancel_review(self):
        self.admin()
        for url in ['/admin','/admin/products','/admin/orders','/admin/users','/admin/reviews','/admin/products/new']:
            st,h,b=self.call('GET',url);self.assertEqual(st,200,url)
        st,h,b=self.post('/admin/products/new/edit',{'name':'ژاکت تست','slug':'test-jacket','category':'ژاکت','description':'توضیحات تست','price':'123000','compare_price':'0','stock':'4','active':'1'})
        self.assertEqual(st,303,b.decode())
        st,h,b=self.call('GET','/product/test-jacket');self.assertEqual(st,200)
        with closing(app.db_connect()) as conn:
            pid=conn.execute("SELECT id FROM products WHERE slug='test-jacket'").fetchone()[0]
        st,h,b=self.post('/admin/products/'+str(pid)+'/toggle',{})
        self.assertEqual(st,303)
        st,h,b=self.call('GET','/product/test-jacket');self.assertEqual(st,404)
        st,h,b=self.call('GET','/admin/export/orders')
        self.assertEqual(st,200)
        self.assertTrue(b.startswith(b'\xef\xbb\xbf'))
    def test_price_stock_and_xss(self):
        self.admin()
        st,h,b=self.post('/admin/products/new/edit',{'name':'<script>alert(1)</script>','slug':'xss','category':'test','description':'<img src=x onerror=alert(1)>','price':'100','stock':'2','active':'1'})
        self.assertEqual(st,303)
        st,h,b=self.call('GET','/product/xss')
        self.assertNotIn(b'<script>alert(1)</script>',b)
        self.assertIn(b'&lt;script&gt;',b)
        st,h,b=self.post('/admin/products/new/edit',{'name':'بیشتر','category':'test','price':'-1','stock':'1'})
        self.assertEqual(st,400)
    def test_review_moderation_and_order_cancel_restocks_once(self):
        self.register()
        st,h,b=self.post('/api/cart',{'product_id':1,'qty':1},as_json=True)
        self.assertEqual(st,200)
        st,h,b=self.post('/checkout',{'full_name':'ناسر','phone':'09121234567','city':'تهران','address':'خیابان نمونه پلاک ده'})
        self.assertEqual(st,303)
        oid=int(h['Location'].split('/')[-1])
        st,h,b=self.post('/reviews',{'product_id':'1','rating':'5','body':'خیلی زیبا و خوش دوخت'})
        self.assertEqual(st,303)
        st,h,b=self.call('GET','/product/vest-navar')
        self.assertNotIn('خیلی زیبا و خوش دوخت'.encode(),b)
        with closing(app.db_connect()) as conn:
            rid=conn.execute('SELECT id FROM reviews').fetchone()[0]
            self.assertEqual(conn.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],7)
        st,h,b=self.post('/logout',{})
        self.assertEqual(st,303)
        self.admin()
        st,h,b=self.post('/admin/reviews/'+str(rid)+'/status',{'action':'approve'})
        self.assertEqual(st,303)
        st,h,b=self.call('GET','/product/vest-navar')
        self.assertIn('خیلی زیبا و خوش دوخت'.encode(),b)
        for _ in range(2):
            st,h,b=self.post('/admin/orders/'+str(oid)+'/status',{'status':'cancelled'})
            self.assertEqual(st,303)
        with closing(app.db_connect()) as conn:
            self.assertEqual(conn.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],8)
        st,h,b=self.post('/admin/orders/'+str(oid)+'/status',{'status':'processing'})
        self.assertEqual(st,409)

    def test_multipart_image_upload(self):
        self.admin()
        def chunk(tag,content):
            return struct.pack('>I',len(content))+tag+content+struct.pack('>I',zlib.crc32(tag+content)&0xffffffff)
        picture=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+
                 chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff'))+chunk(b'IEND',b''))
        boundary='DELISATESTBOUNDARY'
        fields={'csrf':self.csrf,'name':'وست آپلود','slug':'uploaded-vest','category':'وست','price':'100000','stock':'3','active':'1'}
        body=b''
        for key,val in fields.items():
            body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+val+'\r\n').encode()
        body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="image"; filename="photo.png"\r\nContent-Type: image/png\r\n\r\n').encode()+picture+b'\r\n'
        body+=('--'+boundary+'--\r\n').encode()
        st,h,resp=self.call('POST','/admin/products/new/edit',body,'multipart/form-data; boundary='+boundary)
        self.assertEqual(st,303,resp.decode())
        with closing(app.db_connect()) as conn:
            img=conn.execute("SELECT image FROM products WHERE slug='uploaded-vest'").fetchone()[0]
        self.assertTrue((app.UPLOAD/Path(img).name).is_file())

    def test_browsing_metrics(self):
        st,h,b=self.post('/api/track-view',{'path':'/shop'},as_json=True)
        self.assertEqual(st,200)
        with closing(app.db_connect()) as conn:
            self.assertGreaterEqual(conn.execute('SELECT COUNT(*) FROM page_views').fetchone()[0],2)

if __name__=='__main__':unittest.main()
