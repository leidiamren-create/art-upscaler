import ast,io,json,sys,tempfile,threading,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import app,core
class Socket:
    def __init__(self,data):self.input=io.BytesIO(data);self.output=io.BytesIO()
    def makefile(self,*args):return self.input
    def sendall(self,data):self.output.write(data)
class RouteDeltaAudit(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.base=Path(self.t.name);self.logs=self.base/'logs';self.logs.mkdir()
        self.server=SimpleNamespace(server_address=('127.0.0.1',12345),origin='http://127.0.0.1:12345',token='synthetic-test-only',batch=core.Batch(self.base/'engine'),browse_lock=threading.Lock())
        self.server.valid_host=lambda h:h=='127.0.0.1:12345';self.server.batch.state['logs']=str(self.logs)
    def tearDown(self):self.t.cleanup()
    def req(self,method,path,headers=None,body=b''):
        h={'Host':'127.0.0.1:12345','X-App-Token':'synthetic-test-only'};h.update(headers or {})
        if method=='POST':h.setdefault('Content-Type','application/json');h['Content-Length']=str(len(body))
        s=Socket((f'{method} {path} HTTP/1.1\r\n'+''.join(f'{k}: {v}\r\n' for k,v in h.items())+'\r\n').encode()+body);app.Handler(s,('127.0.0.1',55),self.server);head,body=s.output.getvalue().split(b'\r\n\r\n',1);return int(head.split()[1]),body
    def test_removed_preview_route_always_404_even_with_token(self):
        for p in ['/api/preview/0-before','/api/preview/0-after','/api/preview/../../core.py']:
            self.assertEqual(self.req('GET',p)[0],404)
    def test_open_logs_requires_token_same_host_and_origin(self):
        fake_os=SimpleNamespace(name='nt',startfile=Mock())
        with patch.object(app,'os',fake_os):
            for h in [{'X-App-Token':''},{'Origin':'https://evil.example'},{'Host':'evil.example'}]:self.assertEqual(self.req('POST','/api/open-logs',h,b'{}')[0],403)
            fake_os.startfile.assert_not_called()
            self.assertEqual(self.req('POST','/api/open-logs',body=b'{}')[0],200);fake_os.startfile.assert_called_once_with(str(self.logs))
    def test_open_logs_uses_only_batch_path_not_caller_data(self):
        fake_os=SimpleNamespace(name='nt',startfile=Mock())
        with patch.object(app,'os',fake_os):
            self.assertEqual(self.req('POST','/api/open-logs',body=json.dumps({'path':'C:/arbitrary'}).encode())[0],200);fake_os.startfile.assert_called_once_with(str(self.logs))
    def test_missing_logs_returns_error_no_launch(self):
        self.server.batch.state['logs']='';fake_os=SimpleNamespace(name='nt',startfile=Mock())
        with patch.object(app,'os',fake_os):self.assertEqual(self.req('POST','/api/open-logs',body=b'{}')[0],400);fake_os.startfile.assert_not_called()
    def test_root_requires_token_and_substitutes_placeholder(self):
        self.assertEqual(self.req('GET','/',{'X-App-Token':''})[0],403)
        status,body=self.req('GET','/')
        self.assertEqual(status,200)
        self.assertNotIn(b'__TOKEN__',body)
        self.assertIn(b'synthetic-test-only',body)
    def test_arbitrary_file_route_not_exposed(self):
        for path in ['/core.py','/LICENSE','/../../core.py','/logs/report.json']:
            self.assertEqual(self.req('GET',path)[0],404)
    def test_oversize_json_rejected(self):
        self.assertEqual(self.req('POST','/api/scan',body=b' '*32769)[0],413)
if __name__=='__main__':unittest.main(verbosity=2)
