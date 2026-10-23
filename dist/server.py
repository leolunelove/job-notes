#!/usr/bin/env python3
"""Job Notes: local job cache and scheduled source refresh. No CV endpoint or storage."""
import email.utils,xml.etree.ElementTree as ET
import concurrent.futures,datetime as dt,html,json,os,re,sqlite3,threading,time,urllib.request,urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('JOBNOTES_DB',str(ROOT/'.jobnotes.sqlite3')))
BOARDS=json.loads((ROOT/'sources.json').read_text())
BOARD_BY_KIND={b['kind']+':'+b['slug']:b for b in BOARDS}
SOURCES=[('Remotive','remotive',6*3600),('Arbeitnow','arbeitnow',6*3600),('Himalayas','himalayas',24*3600),('We Work Remotely','wwr',6*3600),('Startup Jobs','startup',6*3600),('Remote OK','remoteok',6*3600),('Jobicy','jobicy',6*3600)]+[(b['company']+' · '+{'greenhouse':'Greenhouse','ashby':'Ashby','lever':'Lever'}[b['kind']],b['kind']+':'+b['slug'],6*3600) for b in BOARDS]
SOURCE_URLS={'We Work Remotely':'https://weworkremotely.com/remote-job-rss-feed','Startup Jobs':'https://startup.jobs/api/','Remote OK':'https://remoteok.com','Jobicy':'https://jobicy.com/remote-jobs','Remotive':'https://remotive.com','Arbeitnow':'https://www.arbeitnow.com','Himalayas':'https://himalayas.app'}
LOCK=threading.Lock()
def iso(value=None):
 if value is None:return dt.datetime.now(dt.timezone.utc).isoformat()
 if isinstance(value,(int,float)):return dt.datetime.fromtimestamp(value/(1000 if value>1e11 else 1),dt.timezone.utc).isoformat()
 return str(value)
def plain(value):return re.sub(r'\s+',' ',re.sub('<[^>]*>',' ',html.unescape(str(value or '')))).strip()
def read(url):
 req=urllib.request.Request(url,headers={'User-Agent':'JobNotes/1.1 (+https://jobs.leolune.fun)','Accept':'application/json, application/rss+xml, text/xml'})
 with urllib.request.urlopen(req,timeout=25) as response:return response.read(32*1024*1024)
def get(url):return json.loads(read(url))
def feed_date(value):
 if not value:return None
 try:return email.utils.parsedate_to_datetime(value).isoformat()
 except (ValueError,TypeError,OverflowError):return value
def https_url(value):
 try:
  p=urllib.parse.urlsplit(value or '')
  return value if p.scheme=='https' and p.hostname and not p.username else ''
 except ValueError:return ''
def salary_range(low,high,currency='',period='year'):
 if low in (None,'',0) and high in (None,'',0):return ''
 return currency+' '+str(low or '')+('–'+str(high) if high else '')+' / '+period

def rss_jobs(data,source):
 root=ET.fromstring(data)
 if root.tag!='rss' or root.find('channel') is None:raise ValueError('Invalid RSS feed')
 result=[]
 for item in root.findall('./channel/item'):
  def value(key):return item.findtext(key) or ''
  title=plain(value('title'));description=value('description');url=value('link');company='Company not specified'
  if source=='We Work Remotely':
   company,sep,role=title.partition(': ')
   if sep:title=role
   else:company='Company not specified'
   location=plain(value('region')) or 'Location not specified';remote=True
  else:
   role,sep,employer=title.rpartition(' at ')
   if sep:title,company=role,employer
   # The RSS footer carries location/pay. Never turn an unspecified country into worldwide.
   footer=plain(description.strip().split('\n')[-1]);location=footer.split(' · ')[0] if len(footer)<250 else 'Location not specified'
   if not location:location='Location not specified'
   remote=bool(re.search(r'\bremote\b',location,re.I)) and not re.search(r'hybrid|on.?site',location,re.I)
  result.append(dict(id=value('guid') or url,title=title,company=company,url=url,location=location,remote=remote,type=plain(value('type')) or 'See listing',salary='',tags=[plain(e.text) for e in item.findall('category')],description=description,date=feed_date(value('pubDate')),expiresAt=feed_date(value('expires_at'))))
 return result
def closing_deadline(text):
 dates=[]
 for raw in re.findall(r'\b(?:application deadline|applications close|closing date|apply by|deadline)\s*(?:is|on|:|-)?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b',text or '',re.I):
  try:
   clean=re.sub(r'(\d)(st|nd|rd|th)',r'\1',raw,flags=re.I)
   value=dt.datetime.strptime(clean,'%Y-%m-%d' if re.match(r'^\d{4}-',clean) else '%d %B %Y').replace(hour=23,minute=59,second=59,tzinfo=dt.timezone.utc)
   dates.append(value.isoformat())
  except ValueError:pass
 return min(dates) if dates else None

def init():
 with sqlite3.connect(DB) as c:
  c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,source TEXT,data TEXT,seen REAL,missing INTEGER DEFAULT 0,state TEXT DEFAULT "active")')
  c.execute('CREATE TABLE IF NOT EXISTS sources(name TEXT PRIMARY KEY,attempt REAL,success REAL,error TEXT,complete INTEGER)')
def normal(j,source,kind,company=None):
 if kind=='remotive':
  v=dict(id=str(j['id']),title=j['title'],company=j['company_name'],url=j['url'],location=j.get('candidate_required_location') or 'Worldwide',remote=True,type=j.get('job_type',''),salary=j.get('salary',''),tags=j.get('tags',[]),description=j.get('description',''),date=j.get('publication_date'))
 elif kind=='arbeitnow':
  v=dict(id=j['slug'],title=j['title'],company=j['company_name'],url=j['url'],location=j.get('location',''),remote=j.get('remote',False),type=', '.join(j.get('job_types',[])),salary='',tags=j.get('tags',[]),description=j.get('description',''),date=iso(j['created_at']))
 elif kind=='himalayas':
  low,high=j.get('minSalary'),j.get('maxSalary');salary=(str(low) if low is not None else '')+('–'+str(high) if high is not None else '')
  v=dict(id=j['guid'],title=j['title'],company=j['companyName'],url=j['applicationLink'],location=', '.join(j.get('locationRestrictions') or []) or 'Worldwide',remote=True,type=j.get('employmentType',''),salary=(j.get('currency','')+' '+salary+' / '+j.get('salaryPeriod','annual')).strip() if salary else '',tags=j.get('categories',[]),description=j.get('description',''),date=iso(j['pubDate']) if j.get('pubDate') else None,expiresAt=iso(j['expiryDate']) if j.get('expiryDate') else None)
 elif kind=='greenhouse':
  loc=j.get('location',{}).get('name','');v=dict(id=str(j['id']),title=j['title'],company=company,url=j['absolute_url'],location=loc,remote=bool(re.search(r'\bremote\b',loc,re.I)) and not re.search(r'hybrid',loc,re.I),type='See listing',salary='',tags=[x['name'] for x in j.get('departments',[])],description=j.get('content',''),date=j.get('first_published'),expiresAt=j.get('application_deadline'),confirmedActive=True)
 elif kind=='ashby':
  locations=[j.get('location','')]+[x.get('location','') for x in j.get('secondaryLocations',[])];comp=j.get('compensation') or {}
  v=dict(id=j['id'],title=j['title'],company=company,url=j['jobUrl'],location='; '.join(x for x in locations if x),remote=j.get('isRemote',False),type=j.get('employmentType',''),salary=comp.get('scrapeableCompensationSalarySummary',''),tags=[j.get('department',''),j.get('team','')],description=j.get('descriptionPlain') or j.get('descriptionHtml',''),date=j.get('publishedAt'),confirmedActive=True)
 elif kind=='lever':
  cat=j.get('categories') or {};parts=[j.get('descriptionPlain','')]+[x.get('text','')+' '+x.get('content','') for x in j.get('lists',[])]+[j.get('additionalPlain','')];pay=j.get('salaryRange') or {}
  v=dict(id=j['id'],title=j['text'],company=company,url=j['hostedUrl'],location=cat.get('location',''),remote=j.get('workplaceType')=='remote',type=cat.get('commitment',''),salary=salary_range(pay.get('min'),pay.get('max'),pay.get('currency',''),pay.get('interval','year')),tags=[cat.get('department',''),cat.get('team','')],description=' '.join(parts),date=iso(j['createdAt']) if j.get('createdAt') else None,confirmedActive=True)
 elif kind=='remoteok':
  v=dict(id=str(j['id']),title=j['position'],company=j['company'],url=j['url'],location=j.get('location') or 'Location not specified',remote=True,type='See listing',salary=salary_range(j.get('salary_min'),j.get('salary_max'),'USD'),tags=j.get('tags',[]),description=j.get('description',''),date=j.get('date'))
 elif kind=='jobicy':
  v=dict(id=str(j['id']),title=j['jobTitle'],company=j['companyName'],url=j['url'],location=j.get('jobGeo') or 'Location not specified',remote=True,type=', '.join(j.get('jobType',[])),salary=salary_range(j.get('annualSalaryMin'),j.get('annualSalaryMax'),j.get('salaryCurrency','')),tags=j.get('jobIndustry',[]),description=j.get('jobDescription',''),date=j.get('pubDate'))
 elif kind=='rss':v=dict(j)
 else:raise ValueError('Unknown source adapter')
 v['id']=source+':'+v['id'];v['source']=source
 for k in ['title','company','location','type','salary','description']:v[k]=plain(v.get(k))
 if not v.get('expiresAt'):v['expiresAt']=closing_deadline(v['description'])
 v['tags']=[plain(x) for x in v['tags'] if x];v['url']=https_url(v.get('url'));v['sourceUrl']=SOURCE_URLS.get(source) or v['url']
 if not v['url'] or not v['title'] or not v['company']:raise ValueError('Incomplete job')
 return v
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
 elif kind in BOARD_BY_KIND:
  board=BOARD_BY_KIND[kind];slug=board['slug'];adapter=board['kind']
  if adapter=='greenhouse':raw=get('https://boards-api.greenhouse.io/v1/boards/'+slug+'/jobs?content=true')['jobs']
  elif adapter=='ashby':raw=[j for j in get('https://api.ashbyhq.com/posting-api/job-board/'+slug)['jobs'] if j.get('isListed',True)]
  else:
   # Bounded pagination is partial unless the final page is observed.
   for skip in range(0,5000,100):
    page=get('https://api.lever.co/v0/postings/'+slug+'?mode=json&limit=100&skip='+str(skip))
    if not isinstance(page,list):raise ValueError('Invalid Lever list')
    raw.extend(page)
    if len(page)<100:break
   else:complete=False
  if not isinstance(raw,list):raise ValueError('Invalid job list')
  return [normal(j,name,adapter,board['company']) for j in raw],complete
 elif kind in ('wwr','startup'):
  url='https://weworkremotely.com/remote-jobs.rss' if kind=='wwr' else 'https://startup.jobs/feeds/jobs'
  return [normal(j,name,'rss') for j in rss_jobs(read(url),name)],False
 elif kind=='remoteok':raw=[j for j in get('https://remoteok.com/api') if j.get('id')];complete=False
 elif kind=='jobicy':
  cursor=None
  for _ in range(5):
   d=get('https://jobicy.com/api/jobs?count=200'+('&cursor='+urllib.parse.quote(cursor,safe='') if cursor else ''));raw.extend(d['jobs']);cursor=d.get('nextCursor')
   if not cursor:break
  complete=False # recent-job window, never evidence that absent jobs are closed
 else:raise ValueError('Unknown source')
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
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda args:refresh_source(*args),due))

def scheduler():
 while True:
  try:refresh_due()
  except Exception as e:print('Refresh failed: '+type(e).__name__,flush=True)
  time.sleep(60)

def expired(j,now):
 try:return bool(j.get('expiresAt') and dt.datetime.fromisoformat(j['expiresAt'].replace('Z','+00:00')).timestamp()<now)
 except (ValueError,TypeError):return False

def canonical_url(url):
 p=urllib.parse.urlsplit(url)
 query=urllib.parse.urlencode(sorted((k,v) for k,v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(('utm_','ref')) and k.lower() not in ('source','gh_src','lever-source')))
 return urllib.parse.urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/'),query,''))
def deduplicate(items):
 # Prefer an employer's current board, retain all provenance links for attribution.
 result=[];by_url={};by_identity={}
 for j in sorted(items,key=lambda j:(j.get('availability')=='unverified',not j.get('confirmedActive',False),j['id'])):
  key=canonical_url(j['url']);identity=tuple(re.sub(r'[^a-z0-9]+',' ',j.get(k,'').lower()).strip() for k in ('company','title','location'))
  old=by_url.get(key) or by_identity.get(identity)
  attribution=dict(name=j['source'],url=j['url'])
  if old:
   if attribution not in old['alsoSeenOn']:old['alsoSeenOn'].append(attribution)
   continue
  j['alsoSeenOn']=[attribution];by_url[key]=j;by_identity[identity]=j;result.append(j)
 return result

def payload():
 now=time.time();items=[];configured={n for n,_,_ in SOURCES}
 with LOCK,sqlite3.connect(DB) as c:
  states={n:dict(name=n,url=SOURCE_URLS.get(n,''),attempt=iso(a),checkedAt=iso(s) if s else None,error=e,complete=bool(full)) for n,a,s,e,full in c.execute('SELECT * FROM sources')}
  for id,name,data,seen,missing,state in c.execute('SELECT * FROM jobs'):
   if name not in configured:continue
   j=json.loads(data)
   if not j.get('expiresAt'):j['expiresAt']=closing_deadline(j.get('description',''))
   if expired(j,now):c.execute('UPDATE jobs SET state="expired" WHERE id=?',(id,));continue
   if state in ('closed','expired') or now-seen>48*3600:continue
   source=states.get(name,{})
   j['availability']='unverified' if source.get('error') or state=='unverified' else 'returned_by_source'
   if j['availability']=='unverified':j['confirmedActive']=False
   items.append(j)
 return dict(jobs=deduplicate(items),sources=[v for n,v in states.items() if n in configured],refreshing=any(n not in states for n,_,_ in SOURCES),servedAt=iso())
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
