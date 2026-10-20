import importlib.util,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
os.environ['JOBNOTES_DB']=str(ROOT/'.cache/jobs.sqlite3')
Path(os.environ['JOBNOTES_DB']).parent.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('jobs',ROOT/'dist/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
server.init();server.refresh_due();data=server.payload()
if not data['jobs']:raise SystemExit('No usable jobs: refusing an empty deployment')
site=ROOT/'site';site.mkdir(exist_ok=True)
for name in ['index.html','style.css','app.js','review.js','freshness.js']:
 shutil.copy2(ROOT/'dist'/name,site/name)
(site/'vendor').mkdir(exist_ok=True)
import urllib.request
for filename,url in {'pdf.min.js':'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js','pdf.worker.min.js':'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js','mammoth.browser.min.js':'https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js'}.items():
 local=ROOT/'dist/vendor'/filename
 if local.exists():shutil.copy2(local,site/'vendor'/filename)
 else:urllib.request.urlretrieve(url,site/'vendor'/filename)
(site/'api').mkdir(exist_ok=True)
(site/'api/jobs.json').write_text(json.dumps(data,separators=(',',':')))
(site/'CNAME').write_text('jobs.leolune.fun\n')
(site/'.nojekyll').touch()
print('Published feed:',len(data['jobs']),'jobs from',len(data['sources']),'sources')
