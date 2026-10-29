import importlib.util,json,os,shutil,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
os.environ['JOBNOTES_DB']=str(ROOT/'.cache/jobs.sqlite3')
Path(os.environ['JOBNOTES_DB']).parent.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('jobs',ROOT/'dist/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
server.init();server.refresh_due();data=server.payload()
if not data['jobs']:raise SystemExit('No usable jobs: refusing an empty deployment')
site=ROOT/'site';site.mkdir(exist_ok=True)
for name in ['index.html','style.css','app.js','review.js','freshness.js','manifest.webmanifest']:
 shutil.copy2(ROOT/'dist'/name,site/name)
shutil.copytree(ROOT/'dist/icons',site/'icons',dirs_exist_ok=True)
(site/'vendor').mkdir(exist_ok=True)
import urllib.request
for filename,url in {'pdf.min.js':'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js','pdf.worker.min.js':'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js','mammoth.browser.min.js':'https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js'}.items():
 local=ROOT/'dist/vendor'/filename
 if local.exists():shutil.copy2(local,site/'vendor'/filename)
 else:urllib.request.urlretrieve(url,site/'vendor'/filename)
(site/'api').mkdir(exist_ok=True)
# Full descriptions load on demand; the index keeps exact built-in skill matches
# and distinct words for custom skill searches. No CV enters this build.
app=(ROOT/'dist/app.js').read_text()
vocabulary=json.loads(re.search(r"const vocabulary=(\[[^;]+\]);",app).group(1).replace("'",'"'))
skill_pattern=re.compile(r'(?<![a-z0-9])(?=('+('|'.join(re.escape(skill) for skill in vocabulary))+r')(?=$|[^a-z0-9]))',re.I)
skill_names={s.lower():s for s in vocabulary}
buckets={};index=[];term_buckets={}
for original in data['jobs']:
 job=dict(original);bucket=hashlib.sha256(job['id'].encode()).hexdigest()[:2]
 buckets.setdefault(bucket,{})[job['id']]=job['description']
 text=job['title']+' '+' '.join(job['tags'])+' '+job['description']
 job['skillMatches']=sorted({skill_names[match.group(1).lower()] for match in skill_pattern.finditer(text)})
 job['searchId']=len(index)
 for term in set(re.findall(r'[a-z0-9]+',text.lower())):
  term_buckets.setdefault(term[:2],{}).setdefault(term,[]).append(job['searchId'])
 job['description']=job['description'][:650];job['detailBucket']=bucket
 index.append(job)
# Rebuild only generated API files; content-addressed detail paths resist stale caches.
details=site/'api/details'
if details.exists():shutil.rmtree(details)
details.mkdir()
paths={}
for bucket,descriptions in buckets.items():
 content=json.dumps(descriptions,separators=(',',':'));digest=hashlib.sha256(content.encode()).hexdigest()[:16]
 name=bucket+'-'+digest+'.json';(details/name).write_text(content);paths[bucket]='./api/details/'+name
for job in index:job['detailUrl']=paths[job.pop('detailBucket')]
terms=site/'api/terms'
if terms.exists():shutil.rmtree(terms)
terms.mkdir();term_files={}
for prefix,mapping in term_buckets.items():
 content=json.dumps(mapping,separators=(',',':'));digest=hashlib.sha256(content.encode()).hexdigest()[:16]
 name=prefix+'-'+digest+'.json';(terms/name).write_text(content);term_files[prefix]='./api/terms/'+name
data['termFiles']=term_files
data['jobs']=index
(site/'api/jobs.json').write_text(json.dumps(data,separators=(',',':')))
(site/'CNAME').write_text('jobs.leolune.fun\n')
(site/'.nojekyll').touch()
print('Published feed:',len(data['jobs']),'jobs from',len(data['sources']),'sources')
