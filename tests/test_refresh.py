import importlib.util,sqlite3,unittest
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
if __name__=='__main__':unittest.main()
