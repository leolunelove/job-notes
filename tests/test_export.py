"""Check the published index against its full descriptions, not its encoder."""
import json,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class ExportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.site=ROOT/'site';cls.data=json.loads((cls.site/'api/jobs.json').read_text());cls.cache={}
 def details(self,job):
  path=job['detailUrl'];self.assertTrue(path.startswith('./api/details/'));self.assertNotIn('..',path.split('/'))
  if path not in self.cache:self.cache[path]=json.loads((self.site/path.removeprefix('./')).read_text())
  return self.cache[path][job['id']]
 def test_full_description_skill_matching_parity(self):
  text=(ROOT/'dist/app.js').read_text();vocabulary=json.loads(re.search(r'const vocabulary=(\[[^;]+\]);',text).group(1).replace("'",'"'))
  jobs=self.data['jobs']
  for job in jobs[::max(1,len(jobs)//40)]:
   full=job['title']+' '+' '.join(job['tags'])+' '+self.details(job)
   expected={s for s in vocabulary if re.search(r'(^|[^a-z0-9])'+re.escape(s)+r'(?=$|[^a-z0-9])',full,re.I)}
   self.assertEqual(expected,set(job['skillMatches']),job['id'])
 def test_every_detail_reference_and_excerpt(self):
  for job in self.data['jobs']:
   self.assertEqual(job['description'],self.details(job)[:650]);self.assertTrue(job['url'].startswith('https://'))
 def test_custom_skill_index(self):
  files=self.data['termFiles'];prefix=next(p for p in files if p.isalpha());terms=json.loads((self.site/files[prefix].removeprefix('./')).read_text())
  for word,ids in list(terms.items())[:20]:
   for index in ids[:3]:
    job=self.data['jobs'][index];full=job['title']+' '+' '.join(job['tags'])+' '+self.details(job)
    self.assertIn(word,set(re.findall('[a-z0-9]+',full.lower())))
if __name__=='__main__':unittest.main()
