"""Independent v0.1.1 delta tests. FakeEngine validates file policy, not AI quality."""
import ast,hashlib,importlib.util,inspect,json,sys,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
NEW=ROOT
sys.path.insert(0,str(NEW));import core

class FakeEngine:
    def verify(self,model):pass
    def self_test(self,settings,cancel):pass
    def run(self,src,dest,scale,settings,cancel,progress):
        with Image.open(src) as im:im.resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST).save(dest)

class OutputsOnlyAudit(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.base=Path(self.t.name);self.src=self.base/'素材';self.src.mkdir();self.out_parent=self.base/'results';self.out_parent.mkdir();self.tool=self.base/'tool';self.tool.mkdir();self.engine=self.tool/'engine';self.engine.mkdir()
        old=self.out_parent/'old-run'/'_report';old.mkdir(parents=True);(old/'preview-before.png').write_bytes(b'existing user output do not modify')
        self.old_hash=hashlib.sha256((old/'preview-before.png').read_bytes()).hexdigest()
    def tearDown(self):self.t.cleanup()
    def image(self,name='a.png',size=(64,32)):
        p=self.src/name;p.parent.mkdir(parents=True,exist_ok=True);Image.new('RGBA',size,(20,120,210,100)).save(p);return p
    def source_hashes(self):return {str(p.relative_to(self.src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.src.rglob('*') if p.is_file()}
    def batch(self):
        sig=inspect.signature(core.Batch)
        kw={'logs_dir':self.tool/'logs'} if 'logs_dir' in sig.parameters else {'logs_root':self.tool/'logs'} if 'logs_root' in sig.parameters else {}
        b=core.Batch(self.engine,**kw);b.engine=FakeEngine();return b
    def settings(self):return core.Settings(str(self.src),str(self.out_parent),target=128)
    def run_batch(self,b=None):
        b=b or self.batch();b.start(self.settings());b._thread.join(10);self.assertFalse(b._thread.is_alive());return b,b.snapshot()
    def result_files(self,state):
        p=Path(state['output']);return sorted(f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file())
    def assert_logs_separate(self,state):
        logs=Path(state['logs']);self.assertTrue(logs.is_dir());self.assertTrue(logs.is_relative_to(self.tool));self.assertFalse(logs.is_relative_to(Path(state['output'])))
        files=list(logs.rglob('*'));self.assertTrue(any(p.suffix=='.json' for p in files));self.assertTrue(any(p.suffix=='.csv' for p in files));self.assertFalse(any(p.suffix.lower()=='.png' for p in files))
    def assert_old_untouched(self):self.assertEqual(hashlib.sha256((self.out_parent/'old-run/_report/preview-before.png').read_bytes()).hexdigest(),self.old_hash)
    def test_success_only_formal_pngs_preserves_subdirs_and_originals(self):
        self.image('same.png');self.image('same.jpg.png');self.image('角色/same.png');before=self.source_hashes();b,s=self.run_batch()
        self.assertEqual((s['status'],s['done'],s['failed']),('complete',3,0));self.assertEqual(self.result_files(s),['same.jpg.png_AI.png','same.png_AI.png','角色/same.png_AI.png']);self.assertEqual(before,self.source_hashes());self.assert_logs_separate(s);self.assert_old_untouched()
        self.assertFalse((Path(s['output'])/'_report').exists());self.assertTrue(all(not i.get('before') and not i.get('after') for i in s['items']))
        for p in Path(s['output']).rglob('*.png'):
            with Image.open(p) as im:self.assertEqual(im.size,(128,64));self.assertEqual(im.mode,'RGBA')
    def test_failure_continues_without_extra_result_files(self):
        self.image('a.png');(self.src/'b-broken.png').write_bytes(b'bad image');self.image('sub/z.png');before=self.source_hashes();b,s=self.run_batch()
        self.assertEqual((s['status'],s['done'],s['failed']),('complete',3,1));self.assertEqual(self.result_files(s),['a.png_AI.png','sub/z.png_AI.png']);self.assertEqual(before,self.source_hashes());self.assert_logs_separate(s);self.assert_old_untouched()
    def test_all_failures_create_no_artifact_files_in_results(self):
        (self.src/'broken.png').write_bytes(b'bad image');b,s=self.run_batch();self.assertEqual((s['status'],s['done'],s['failed']),('complete',1,1));self.assertEqual(self.result_files(s),[]);self.assert_logs_separate(s)
    def test_cancel_preserves_only_finished_pngs(self):
        self.image('a.png');self.image('b.png');self.image('sub/c.png');before=self.source_hashes();original=core.process_image;calls=0
        def processing(src,settings,engine,cancel,progress=lambda t:None):
            nonlocal calls
            calls+=1
            if calls==2:cancel.set();raise core.Cancelled('fixture cancel')
            return original(src,settings,engine,cancel,progress)
        with patch.object(core,'process_image',side_effect=processing):b,s=self.run_batch()
        self.assertEqual(s['status'],'cancelled');self.assertEqual(s['done'],1);self.assertEqual(self.result_files(s),['a.png_AI.png']);self.assertEqual(before,self.source_hashes());self.assert_logs_separate(s);self.assert_old_untouched()
    def test_repeat_run_distinct_outputs_and_logs(self):
        self.image('a.png');b,s1=self.run_batch();b,s2=self.run_batch(b);self.assertNotEqual(s1['output'],s2['output']);self.assertNotEqual(s1['logs'],s2['logs']);self.assertEqual(self.result_files(s1),['a.png_AI.png']);self.assertEqual(self.result_files(s2),['a.png_AI.png']);self.assert_logs_separate(s1);self.assert_logs_separate(s2);self.assert_old_untouched()
    def test_selfcheck_failure_leaves_source_and_old_results_untouched(self):
        self.image();before=self.source_hashes();b=self.batch();b.engine.self_test=lambda *args:(_ for _ in ()).throw(RuntimeError('selfcheck failure'))
        b,s=self.run_batch(b);self.assertEqual(s['status'],'error');self.assertFalse(s['output']);self.assertEqual(before,self.source_hashes());self.assertEqual([p.name for p in self.out_parent.iterdir()],['old-run']);self.assert_old_untouched()
    def test_report_write_failure_does_not_block_outputs_or_fallback(self):
        self.image('a.png');self.image('b.png');b=self.batch()
        with patch.object(b,'_report',side_effect=PermissionError('fixture read-only logs')):b,s=self.run_batch(b)
        self.assertEqual(s['status'],'complete');self.assertEqual(s['done'],2);self.assertEqual(self.result_files(s),['a.png_AI.png','b.png_AI.png']);self.assertFalse((Path(s['output'])/'_report').exists())
    def test_logs_directory_creation_failure_keeps_output_clean(self):
        self.image('a.png');self.image('b.png');(self.tool/'logs').write_text('fixture blocks directory')
        b,s=self.run_batch();self.assertEqual(s['status'],'complete');self.assertEqual(s['done'],2);self.assertFalse(s['logs']);self.assertTrue(s['log_warning']);self.assertEqual(self.result_files(s),['a.png_AI.png','b.png_AI.png']);self.assertFalse((Path(s['output'])/'_report').exists())
    def test_version(self):
        self.assertEqual(core.VERSION, '0.1.1')

if __name__=='__main__':unittest.main(verbosity=2)
