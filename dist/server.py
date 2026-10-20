#!/usr/bin/env python3
"""Job Notes: local job cache and scheduled source refresh. No CV endpoint or storage."""
import concurrent.futures,datetime as dt,html,json,os,re,sqlite3,threading,time,urllib.request,urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('JOBNOTES_DB',str(ROOT/'.jobnotes.sqlite3')))
SOURCES=[('Remotive','remotive',6*3600),('Arbeitnow','arbeitnow',6*3600),('Himalayas','himalayas',24*3600),('GitLab · Greenhouse','greenhouse',6*3600),('Linear · Ashby','ashby',6*3600)]
LOCK=threading.Lock()
def iso(value=None):
 if value is None:return dt.datetime.now(dt.timezone.utc).isoformat()
 if isinstance(value,(int,float)):return dt.datetime.fromtimestamp(value/(1000 if value>1e11 else 1),dt.timezone.utc).isoformat()
 return str(value)
def plain(value):return re.sub(r'\s+',' ',re.sub('<[^>]*>',' ',html.unescape(str(value or '')))).strip()
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'JobNotes/1.0 (+local personal job shortlist)','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
def init():
 with sqlite3.connect(DB) as c:
  c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,source TEXT,data TEXT,seen REAL,missing INTEGER DEFAULT 0,state TEXT DEFAULT "active")')
  c.execute('CREATE TABLE IF NOT EXISTS sources(name TEXT PRIMARY KEY,attempt REAL,success REAL,error TEXT,complete INTEGER)')
def normal(j,source,kind):
 if kind=='remotive':
  v=dict(id=str(j['id']),title=j['title'],company=j['company_name'],url=j['url'],location=j.get('candidate_required_location') or 'Worldwide',remote=True,type=j.get('job_type',''),salary=j.get('salary',''),tags=j.get('tags',[]),description=j.get('description',''),date=j.get('publication_date'))
 elif kind=='arbeitnow':
  v=dict(id=j['slug'],title=j['title'],company=j['company_name'],url=j['url'],location=j.get('location',''),remote=j.get('remote',False),type=', '.join(j.get('job_types',[])),salary='',tags=j.get('tags',[]),description=j.get('description',''),date=iso(j['created_at']))
 elif kind=='himalayas':
  low,high=j.get('minSalary'),j.get('maxSalary');salary=(str(low) if low is not None else '')+('–'+str(high) if high is not None else '')
  v=dict(id=j['guid'],title=j['title'],company=j['companyName'],url=j['applicationLink'],location=', '.join(j.get('locationRestrictions') or []) or 'Worldwide',remote=True,type=j.get('employmentType',''),salary=(j.get('currency','')+' '+salary+' / '+j.get('salaryPeriod','annual')).strip() if salary else '',tags=j.get('categories',[]),description=j.get('description',''),date=iso(j['pubDate']) if j.get('pubDate') else None,expiresAt=iso(j['expiryDate']) if j.get('expiryDate') else None)
 elif kind=='greenhouse':
  loc=j.get('location',{}).get('name','');v=dict(id=str(j['id']),title=j['title'],company='GitLab',url=j['absolute_url'],location=loc,remote='remote' in loc.lower(),type='See listing',salary='',tags=[],description=j.get('content',''),date=j.get('first_published'),expiresAt=j.get('application_deadline'),confirmedActive=True)
 else:
  v=dict(id=j['id'],title=j['title'],company='Linear',url=j['jobUrl'],location=j.get('location',''),remote=j.get('isRemote',False),type=j.get('employmentType',''),salary='',tags=[],description=j.get('descriptionPlain') or j.get('descriptionHtml',''),date=j.get('publishedAt'),confirmedActive=True)
 v['id']=source+':'+v['id'];v['source']=source
 for k in ['title','company','location','type','salary','description']:v[k]=plain(v.get(k))
 v['tags']=[plain(x) for x in v['tags']];return v
def fetch_source(name,kind):
 complete=True;raw=[]
 if kind=='remotive':
  d=get('https://remotive.com/api/remote-jobs');raw=d['jobs'];complete=True
 elif kind=='arbeitnow':
  url='https://www.arbeitnow.com/api/job-board-api'
  for _ in range(8):
   d=get(url);raw.extend(d['data']);url=d.get('links',{}).get('next')
   if not url:break
   # Only follow the documented source host, never arbitrary response URLs.
   if urllib.parse.urlparse(url).netloc!='www.arbeitnow.com':raise ValueError('Unexpected pagination host')
  complete=not bool(url)
 elif kind=='himalayas':
  cursor=None
  for _ in range(5):
   url='https://himalayas.app/jobs/api?limit=20'+('&cursor='+urllib.parse.quote(str(cursor),safe='') if cursor else '')
   d=get(url);raw.extend(d['jobs']);cursor=d.get('nextCursor')
   if not cursor:break
  complete=not bool(cursor) # bounded daily slice: absence NEVER implies closure
 elif kind=='greenhouse':raw=get('https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true')['jobs']
 else:raw=[j for j in get('https://api.ashbyhq.com/posting-api/job-board/linear')['jobs'] if j.get('isListed',True)]
 if not isinstance(raw,list):raise ValueError('Invalid job list')
 return [normal(j,name,kind) for j in raw],complete

def reconcile(c,name,items,complete,now):
 ids={j['id'] for j in items}
 for j in items:
  j['checkedAt']=iso(now);c.execute('INSERT INTO jobs(id,source,data,seen,missing,state) VALUES(?,?,?,?,0,"active") ON CONFLICT(id) DO UPDATE SET data=excluded.data,seen=excluded.seen,missing=0,state="active"',(j['id'],name,json.dumps(j),now))
 if complete:
  for id,missing in c.execute('SELECT id,missing FROM jobs WHERE source=?',(name,)).fetchall():
   if id not in ids:c.execute('UPDATE jobs SET missing=?,state=? WHERE id=?',(missing+1,'closed' if missing+1>=2 else 'unverified',id))
 c.execute('INSERT INTO sources VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET attempt=excluded.attempt,success=excluded.success,error=NULL,complete=excluded.complete',(name,now,now,None,int(complete)))

def refresh_source(name,kind):
 try:
  items,complete=fetch_source(name,kind)
  with LOCK,sqlite3.connect(DB) as c:reconcile(c,name,items,complete,time.time())
  print(name+': '+str(len(items))+' jobs; '+('complete' if complete else 'partial feed'),flush=True)
 except Exception as error:
  with LOCK,sqlite3.connect(DB) as c:
   c.execute('INSERT INTO sources VALUES(?,?,NULL,?,0) ON CONFLICT(name) DO UPDATE SET attempt=excluded.attempt,error=excluded.error',(name,time.time(),type(error).__name__))
  print(name+': unavailable ('+type(error).__name__+')',flush=True)

def refresh_due():
 with sqlite3.connect(DB) as c:attempts=dict(c.execute('SELECT name,attempt FROM sources'))
 due=[(n,k) for n,k,interval in SOURCES if time.time()-attempts.get(n,0)>=interval]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda args:refresh_source(*args),due))

def scheduler():
 while True:
  try:refresh_due()
  except Exception as e:print('Refresh failed: '+type(e).__name__,flush=True)
  time.sleep(60)

def expired(j,now):
 try:return bool(j.get('expiresAt') and dt.datetime.fromisoformat(j['expiresAt'].replace('Z','+00:00')).timestamp()<now)
 except (ValueError,TypeError):return False

def payload():
 now=time.time();items=[]
 with LOCK,sqlite3.connect(DB) as c:
  states={n:dict(name=n,attempt=iso(a),checkedAt=iso(s) if s else None,error=e,complete=bool(full)) for n,a,s,e,full in c.execute('SELECT * FROM sources')}
  for id,name,data,seen,missing,state in c.execute('SELECT * FROM jobs'):
   j=json.loads(data)
   if expired(j,now):c.execute('UPDATE jobs SET state="expired" WHERE id=?',(id,));continue
   if state in ('closed','expired') or now-seen>48*3600:continue
   source=states.get(name,{})
   j['availability']='unverified' if source.get('error') or state=='unverified' else 'returned_by_source'
   if j['availability']=='unverified':j['confirmedActive']=False
   items.append(j)
 return dict(jobs=items,sources=list(states.values()),refreshing=any(n not in states for n,_,_ in SOURCES),servedAt=iso())
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
 def do_GET(self):
  path=urllib.parse.urlparse(self.path).path
  if path=='/api/jobs':
   data=json.dumps(payload()).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  if path.startswith('/api/') or any(p.startswith('.') for p in path.split('/') if p) or path.endswith(('.py','.sqlite3','.command')):self.send_error(404);return
  if path.endswith('/'):self.path='/index.html'
  super().do_GET()
 def do_POST(self):self.send_error(405)
if __name__=='__main__':
 init();threading.Thread(target=scheduler,daemon=True).start();port=int(os.environ.get('JOBNOTES_PORT','8842'));server=ThreadingHTTPServer(('127.0.0.1',port),Handler);print('Job notes: http://127.0.0.1:'+str(port),flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:server.server_close()
