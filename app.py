"""A portable localhost UI. No upload, telemetry, account, or outbound requests."""
from __future__ import annotations
import argparse, hmac, json, os, secrets, subprocess, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from core import Batch, Settings, scan_files

BASE=Path(__file__).resolve().parent

def choose_folder(kind):
    if os.name!='nt':raise ValueError('此系统请直接填写文件夹的绝对路径；Windows可使用选择按钮')
    title='选择原图文件夹' if kind=='input' else '选择输出位置（不能位于原图文件夹内）'
    script="""[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.FolderBrowserDialog; $f.Description='%s'; $f.ShowNewFolderButton=$true; if($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){[Console]::Write($f.SelectedPath)}; $f.Dispose()""" % title
    p=subprocess.run(['powershell.exe','-NoProfile','-STA','-Command',script],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=300)
    if p.returncode:raise ValueError('无法打开文件夹选择器，请直接填写路径')
    return p.stdout.decode('utf-8-sig').strip()

class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,address,engine_dir):
        self.batch=Batch(engine_dir);self.token=secrets.token_urlsafe(32);self.browse_lock=threading.Lock()
        super().__init__(address,Handler)
        self.origin=f'http://127.0.0.1:{self.server_address[1]}'
    def valid_host(self,host):return host==f'127.0.0.1:{self.server_address[1]}'

class Handler(BaseHTTPRequestHandler):
    server_version='ArtUpscaler/0.1'
    def log_message(self,*args):pass
    def reply(self,status,body,mime='application/json; charset=utf-8'):
        if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        elif isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Connection','close');self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def authorized(self,allow_query=False):
        if not self.server.valid_host(self.headers.get('Host','')):return False
        origin=self.headers.get('Origin')
        if origin and origin!=self.server.origin:return False
        token=self.headers.get('X-App-Token','')
        if not token and allow_query:token=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('token',[''])[0]
        return hmac.compare_digest(token,self.server.token)
    def do_GET(self):
        path=urllib.parse.urlsplit(self.path).path
        if not self.authorized(allow_query=True):return self.reply(403,{'error':'仅允许本程序打开的本地页面。请从启动窗口重新打开链接'})
        try:
            if path=='/':
                html=(BASE/'ui.html').read_text('utf-8').replace('__TOKEN__',self.server.token)
                return self.reply(200,html,'text/html; charset=utf-8')
            if path=='/api/status':return self.reply(200,self.server.batch.snapshot())
            return self.reply(404,{'error':'不存在的页面'})
        except Exception as exc:self.reply(500,{'error':str(exc)})
    def do_POST(self):
        if not self.authorized():return self.reply(403,{'error':'请求验证失败，请从启动窗口重新打开页面'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=32768:return self.reply(413,{'error':'请求过大'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'error':'需要JSON请求'})
            data=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data,dict):raise ValueError('请求格式无效')
            path=urllib.parse.urlsplit(self.path).path
            batch=self.server.batch
            if path=='/api/browse':
                if data.get('kind') not in ('input','output'):raise ValueError('选择类型无效')
                if not self.server.browse_lock.acquire(False):raise ValueError('已有文件夹选择窗口打开，请先关闭')
                try:result={'path':choose_folder(data['kind'])}
                finally:self.server.browse_lock.release()
            elif path=='/api/scan':
                root=Path(data.get('input','')).expanduser().resolve(strict=True)
                if not root.is_dir():raise ValueError('输入必须是文件夹')
                files=scan_files(root,bool(data.get('recursive',True)))
                result={'files':[{'index':i,'name':str(p.relative_to(root))} for i,p in enumerate(files[:10000])],'count':len(files)}
            elif path=='/api/start':
                allowed=set(Settings.__dataclass_fields__)
                if set(data)-allowed:raise ValueError('包含未知处理选项')
                result=batch.start(Settings(**data))
            elif path=='/api/cancel':batch.stop();result=batch.snapshot()
            elif path=='/api/open-output':
                folder=batch.snapshot()['output']
                if not folder or not Path(folder).is_dir():raise ValueError('还没有输出文件夹')
                if os.name=='nt':os.startfile(folder)
                else:raise ValueError('此系统请手动打开：'+folder)
                result={'ok':True}
            elif path=='/api/open-logs':
                folder=batch.snapshot().get('logs','')
                if not folder or not Path(folder).is_dir():raise ValueError('还没有处理报告')
                if os.name=='nt':os.startfile(folder)
                else:raise ValueError('此系统请手动打开：'+folder)
                result={'ok':True}
            elif path=='/api/shutdown':
                if batch.snapshot()['status']=='running':raise ValueError('正在处理，请先取消或等待完成')
                result={'ok':True}
                threading.Thread(target=self.server.shutdown,daemon=True).start()
            else:return self.reply(404,{'error':'未知操作'})
            self.reply(200,result)
        except (ValueError,TypeError,FileNotFoundError,PermissionError) as exc:self.reply(400,{'error':str(exc)})
        except Exception as exc:self.reply(500,{'error':str(exc)})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--port',type=int,default=0);parser.add_argument('--engine',default=str(BASE/'engine'));args=parser.parse_args()
    server=LocalServer(('127.0.0.1',args.port),args.engine)
    url=server.origin+'/?token='+server.token
    print('素材清晰工坊 v0.1.1 测试版 | 本地离线工具',flush=True)
    print('请保留此窗口；处理结束后在网页点“退出程序”，或关闭此窗口。',flush=True)
    print('如果没有自动打开网页，请复制下方整行到浏览器：\n'+url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:pass
    finally:
        server.batch.stop()
        if server.batch._thread:server.batch._thread.join(timeout=10)
        server.server_close()

if __name__=='__main__':main()
