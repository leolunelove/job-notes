import importlib.util,sqlite3,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('jobs_server','dist/server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RefreshTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.executescript('CREATE TABLE jobs(id TEXT PRIMARY KEY,source TEXT,data TEXT,seen REAL,missing INTEGER DEFAULT 0,state TEXT DEFAULT "active"); CREATE TABLE sources(name TEXT PRIMARY KEY,attempt REAL,success REAL,error TEXT,complete INTEGER);');self.item={'id':'board:1','title':'Designer'}
 def state(self):return self.c.execute('SELECT state FROM jobs').fetchone()[0]
 def test_missing_requires_two_complete_refreshes(self):
  m.reconcile(self.c,'board',[self.item],True,1);m.reconcile(self.c,'board',[],True,2);self.assertEqual(self.state(),'unverified');m.reconcile(self.c,'board',[],True,3);self.assertEqual(self.state(),'closed')
 def test_partial_never_closes_missing_job(self):
  m.reconcile(self.c,'board',[self.item],True,1)
  for n in range(2,5):m.reconcile(self.c,'board',[],False,n)
  self.assertEqual(self.state(),'active')
 def test_reappearing_job_recovers(self):
  m.reconcile(self.c,'board',[self.item],True,1);m.reconcile(self.c,'board',[],True,2);m.reconcile(self.c,'board',[self.item],True,3);self.assertEqual(self.state(),'active');self.assertEqual(self.c.execute('SELECT missing FROM jobs').fetchone()[0],0)
 def test_explicit_expiry(self):
  self.assertTrue(m.expired({'expiresAt':'2026-01-01T00:00:00Z'},1800000000));self.assertFalse(m.expired({'expiresAt':'bad date'},1800000000))
 def test_timezone_normalization(self):self.assertEqual(m.iso(1770000000000),m.iso(1770000000))
class SourceTests(unittest.TestCase):
 def test_employer_identity_and_remote_constraints(self):
  j=m.normal({'id':1,'title':'Designer','absolute_url':'https://example.org/jobs/1','location':{'name':'Remote - UK'},'content':'Design systems','departments':[]},'Figma · Greenhouse','greenhouse','Figma')
  self.assertEqual(j['company'],'Figma');self.assertTrue(j['remote']);self.assertEqual(j['location'],'Remote - UK');self.assertTrue(j['confirmedActive'])
 def test_rolling_feeds_are_never_complete(self):
  data=[{'legal':'Attribution required'},{'id':1,'position':'Designer','company':'Test','url':'https://remoteok.com/jobs/1','location':'UK','description':'Figma','tags':[]}]
  with patch.object(m,'get',return_value=data):jobs,complete=m.fetch_source('Remote OK','remoteok')
  self.assertFalse(complete);self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['location'],'UK')
 def test_rss_metadata_does_not_invent_worldwide(self):
  xml=b'<rss><channel><item><title>Designer at Studio</title><link>https://startup.jobs/designer-1</link><guid>job1</guid><pubDate>Thu, 22 Oct 2026 12:00:00 +0000</pubDate><description>Design products.\n\nRemote, U.S. &#183; $100,000 per year</description><category>Design</category></item></channel></rss>'
  j=m.rss_jobs(xml,'Startup Jobs')[0];self.assertEqual(j['company'],'Studio');self.assertEqual(j['location'],'Remote, U.S.');self.assertTrue(j['remote']);self.assertIn('2026-10-22',j['date'])
 def test_bad_feed_and_unsafe_link_do_not_close_cache(self):
  with self.assertRaises(ValueError):m.rss_jobs(b'<html>Blocked</html>','Startup Jobs')
  self.assertEqual(m.https_url('javascript:alert(1)'),'');self.assertEqual(m.https_url('https://name:password@example.org'),'')
 def test_duplicates_prefer_employer_and_preserve_attribution(self):
  base={'title':'Designer','company':'Studio','location':'UK','description':'Figma'}
  feed=dict(base,id='feed:1',source='Startup Jobs',url='https://startup.jobs/designer-1')
  direct=dict(base,id='board:1',source='Studio · Ashby',url='https://jobs.ashbyhq.com/studio/1',confirmedActive=True)
  result=m.deduplicate([feed,direct]);self.assertEqual(len(result),1);self.assertEqual(result[0]['id'],'board:1');self.assertEqual(len(result[0]['alsoSeenOn']),2)
 def test_tracking_url_dedup_retains_job_id_parameters(self):
  self.assertEqual(m.canonical_url('https://example.org/jobs?id=1&utm_source=a#apply'),m.canonical_url('https://example.org/jobs?id=1'))
  self.assertNotEqual(m.canonical_url('https://example.org/jobs?id=1'),m.canonical_url('https://example.org/jobs?id=2'))
 def test_lever_pagination_does_not_treat_first_page_as_complete(self):
  board=m.BOARD_BY_KIND['lever:spotify'];row={'id':'1','text':'Designer','hostedUrl':'https://jobs.lever.co/spotify/1','categories':{},'lists':[]}
  with patch.object(m,'get',side_effect=[[dict(row,id=str(i)) for i in range(100)],[dict(row,id='last')]]) as fetch:
   jobs,complete=m.fetch_source('Spotify · Lever','lever:spotify')
  self.assertEqual(len(jobs),101);self.assertTrue(complete);self.assertIn('skip=100',fetch.call_args.args[0])
 def test_deadlines_survive_compact_index(self):
  self.assertEqual(m.closing_deadline('Applications close 22 October 2026.'),'2026-10-22T23:59:59+00:00')
  self.assertIsNone(m.closing_deadline('Deadline 2026-02-31'));self.assertIsNone(m.closing_deadline('Apply by 1 June'))
 def test_failed_source_keeps_jobs_unverified_then_ages_out(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'DB',Path(tmp)/'jobs.sqlite'),patch.object(m,'SOURCES',[('board','test',3600)]):
   m.init();now=m.time.time();job={'id':'board:1','source':'board','title':'Designer','company':'Studio','location':'UK','url':'https://example.org/1','confirmedActive':True}
   with sqlite3.connect(m.DB) as c:m.reconcile(c,'board',[job],True,now)
   with patch.object(m,'fetch_source',side_effect=ValueError('bad feed')):m.refresh_source('board','test')
   result=m.payload()['jobs'];self.assertEqual(len(result),1);self.assertEqual(result[0]['availability'],'unverified');self.assertFalse(result[0]['confirmedActive'])
   with patch.object(m.time,'time',return_value=now+49*3600):self.assertEqual(m.payload()['jobs'],[])

if __name__=='__main__':unittest.main()
