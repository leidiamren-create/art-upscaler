"""Local-only batch image processing. Original files are never written."""
from __future__ import annotations
import csv, io, json, math, os, subprocess, tempfile, threading, time, warnings
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable
from PIL import Image, ImageCms, ImageFilter, ImageMath, ImageOps

VERSION = '0.1.1'
SUPPORTED = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
MAX_PIXELS = 24_000_000
MAX_INTERMEDIATE_PIXELS = 36_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
class Cancelled(Exception): pass

def check_cancel(cancel):
    if cancel.is_set(): raise Cancelled('已取消')

@dataclass
class Settings:
    input: str
    output: str = ''
    recursive: bool = True
    target: int = 2048
    noise: int = 1
    device: str = 'gpu'
    model: str = 'cunet'
    tile: int = 128
    sample: bool = False
    def validate(self):
        root = Path(self.input).expanduser().resolve(strict=True)
        if not root.is_dir(): raise ValueError('输入必须是文件夹')
        if not isinstance(self.target, int) or not 64 <= self.target <= 8192: raise ValueError('长边应为64–8192的整数')
        if self.noise not in (-1,0,1,2,3): raise ValueError('降噪强度无效')
        if self.device not in ('cpu','gpu'): raise ValueError('设备选项无效')
        if self.model not in ('cunet','upconv'): raise ValueError('模型选项无效')
        if self.tile not in (64,128,256): raise ValueError('分块大小无效')
        parent = Path(self.output).expanduser().resolve(strict=True) if self.output else root.parent
        if not parent.is_dir(): raise ValueError('输出位置必须是已有文件夹')
        # Prevent re-ingestion of results on future recursive runs.
        if parent == root or root in parent.parents: raise ValueError('输出位置不能在输入文件夹内，请选择旁边或其他文件夹')
        return root, parent

def scan_files(root: Path, recursive=True, cancel=None):
    """Do not follow symlinks or Windows junctions; reject escapes from the source."""
    found=[]
    for folder, dirs, names in os.walk(root, followlinks=False):
        if cancel: check_cancel(cancel)
        dirs[:] = sorted(d for d in dirs if not (Path(folder)/d).is_symlink() and not getattr((Path(folder)/d),'is_junction',lambda:False)()) if recursive else []
        for name in sorted(names):
            p=Path(folder)/name
            if p.suffix.lower() not in SUPPORTED or p.is_symlink(): continue
            try:
                if not p.resolve().is_relative_to(root.resolve()): continue
            except OSError: continue
            found.append(p)
            if len(found) > 100_000: raise ValueError('文件超过100000张，请拆分文件夹')
    return found

def read_image(path):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(path) as im:
            high_depth=im.mode in ('I','F') or im.mode.startswith('I;16')
            if im.format=='PNG':
                with open(path,'rb') as header_file:header=header_file.read(26)
                high_depth=high_depth or (len(header)>24 and header[24]>8)
            if im.format=='TIFF':
                bits=im.tag_v2.get(258,(8,))
                if isinstance(bits,int):bits=(bits,)
                high_depth=high_depth or any(b>8 for b in bits)
            if high_depth:raise ValueError('暂不支持16位/HDR素材，请先导出8位sRGB PNG')
            if getattr(im,'n_frames',1)>1: raise ValueError('暂不处理动画/多页图像，以免丢失帧')
            if im.width*im.height > MAX_PIXELS: raise ValueError('单图超过2400万像素，请先分批缩小')
            im.load()
            im=ImageOps.exif_transpose(im)
            info=im.info.copy()
            alpha=im.convert('RGBA').getchannel('A')
            rgb=im.convert('RGB')
            note=''
            if info.get('icc_profile'):
                try:
                    rgb=ImageCms.profileToProfile(rgb,ImageCms.ImageCmsProfile(io.BytesIO(info['icc_profile'])),ImageCms.createProfile('sRGB'),outputMode='RGB')
                except Exception:
                    note='内嵌色彩配置无法转换，按sRGB处理'
            if im.mode in ('I','I;16','F'):
                raise ValueError('暂不支持16位/HDR素材，请先导出8位sRGB PNG')
            rgb.putalpha(alpha)
            return rgb, note

def target_size(size, target):
    w,h=size
    if w>=h: return target,max(1,round(h*target/w))
    return max(1,round(w*target/h)),target

def resize_rgba(im, size):
    if im.size==size: return im.copy()
    # Explicit premultiplied-alpha resampling avoids black fringes.
    return im.convert('RGBa').resize(size,Image.Resampling.LANCZOS).convert('RGBA')

def bleed_hidden_rgb(im):
    """Extend visible RGB through fully transparent pixels before the neural model.
    Alpha is never sent through denoising. PNG straight-alpha colors remain intact.
    """
    alpha=im.getchannel('A')
    rgb=im.convert('RGB')
    if alpha.getextrema()==(255,255): return rgb
    if alpha.getbbox() is None: return Image.new('RGB',im.size,(0,0,0))
    premul=im.convert('RGBa')
    blurred_a=alpha.filter(ImageFilter.GaussianBlur(32))
    filled=[]
    for channel in premul.split()[:3]:
        blurred=channel.filter(ImageFilter.GaussianBlur(32))
        val=ImageMath.lambda_eval(lambda a: a['c']*255/(a['a']+(a['a']==0)),c=blurred.convert('F'),a=blurred_a.convert('F')).convert('L')
        filled.append(val)
    extension=Image.merge('RGB',filled)
    visible=alpha.point(lambda x:255 if x else 0)
    return Image.composite(rgb,extension,visible)

def save_png_exclusive(image, dest):
    """Even a race or repeated name cannot overwrite a file."""
    dest.parent.mkdir(parents=True,exist_ok=True)
    suffix=0
    while True:
        out=dest if suffix==0 else dest.with_name(f'{dest.stem}_{suffix}{dest.suffix}')
        try:
            with out.open('xb') as f: image.save(f,'PNG',compress_level=6)
            return out
        except FileExistsError: suffix+=1
        except BaseException:
            try: out.unlink()
            except OSError: pass
            raise

def output_folder(parent, name):
    prefix=f'{name}_AI_{time.strftime("%Y%m%d_%H%M%S")}'
    for n in range(10000):
        p=parent/(prefix if n==0 else f'{prefix}_{n}')
        try: p.mkdir(); return p
        except FileExistsError: pass
    raise RuntimeError('无法创建新的输出目录')

class Waifu2x:
    def __init__(self,engine_dir):
        self.folder=Path(engine_dir).resolve()
        self.executable=self.folder/('waifu2x-ncnn-vulkan.exe' if os.name=='nt' else 'waifu2x-ncnn-vulkan')
    def verify(self,model):
        folder=self.folder/('models-cunet' if model=='cunet' else 'models-upconv_7_anime_style_art_rgb')
        if not self.executable.is_file(): raise ValueError('找不到AI引擎。请将AI引擎包解压到程序同一位置，保留engine文件夹')
        if not folder.is_dir() or not list(folder.glob('*.bin')): raise ValueError('找不到AI模型，请完整解压AI引擎包')
        return folder
    def self_test(self,settings,cancel):
        with tempfile.TemporaryDirectory(prefix='art-ai-check-') as tmp:
            source=Path(tmp)/'probe.png';result=Path(tmp)/'probe-out.png'
            Image.new('RGB',(32,32),(160,100,200)).save(source,'PNG')
            try:
                self.run(source,result,2,settings,cancel)
                with Image.open(result) as image:
                    image.load()
                    if image.size!=(64,64):raise ValueError('自检输出像素不正确')
            except Cancelled:raise
            except Exception as exc:
                raise RuntimeError('AI引擎自检未通过，尚未处理原图。当前测试版需要兼容Vulkan的GPU与驱动；CPU为实验选项，云端测试未通过。详情：'+str(exc)) from exc

    def run(self,src,dest,scale,settings,cancel,progress=lambda text:None):
        model=self.verify(settings.model)
        stem='scale2.0x_model' if settings.noise==-1 else f'noise{settings.noise}'+('_scale2.0x_model' if scale==2 else '_model')
        for extension in ('.param','.bin'):
            if not (model/(stem+extension)).is_file():
                raise ValueError(f'缺少AI模型 {model.name}/{stem}{extension}，请将三个ZIP完整解压到同一文件夹')
        # Each file is handled sequentially, with bounded tiles and threads.
        command=[str(self.executable),'-i',str(src),'-o',str(dest),'-n',str(settings.noise),'-s',str(scale),'-t',str(settings.tile),'-m',model.name,'-j','1:1:1','-f','png'] + ['-g','-1' if settings.device=='cpu' else '0'] # Never auto-fallback to CPU
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with tempfile.TemporaryFile() as log:
            p=subprocess.Popen(command,cwd=self.folder,stdout=log,stderr=log,creationflags=creationflags)
            try:
                while p.poll() is None:
                    if cancel.wait(.15):
                        p.terminate()
                        try:p.wait(timeout=5)
                        except subprocess.TimeoutExpired:p.kill();p.wait()
                        raise Cancelled('已停止当前AI进程')
                check_cancel(cancel)
                if p.returncode or not Path(dest).is_file():
                    log.seek(0);details=log.read()[-3000:].decode('utf-8','replace')
                    advice='，请检查显卡是否支持Vulkan及驱动是否正常' if settings.device=='gpu' else '，CPU为实验模式，存在兼容问题'
                    raise RuntimeError(f'AI引擎失败（代码{p.returncode}）{advice}\n{details}')
            finally:
                if p.poll() is None:p.kill();p.wait()

def process_image(source, settings, engine, cancel, progress=lambda text:None):
    check_cancel(cancel)
    original,note=read_image(source)
    target=target_size(original.size,settings.target)
    # Large originals need not create a huge neural intermediate just to shrink.
    working=resize_rgba(original,target) if max(original.size)>settings.target else original.copy()
    ratio=settings.target/max(working.size)
    scale=1 if ratio<=1 else 2**math.ceil(math.log2(ratio))
    if scale>32: raise ValueError('目标超过原图32倍，请使用更大的原图或降低长边')
    if working.width*working.height*scale*scale > MAX_INTERMEDIATE_PIXELS: raise ValueError('AI中间图超过3600万像素，请降低目标长边')
    check_cancel(cancel)
    # Fully transparent inputs cannot benefit from neural inference.
    if working.getchannel('A').getbbox() is None:
        return original, Image.new('RGBA',target,(0,0,0,0)), note, '全透明图片，保留透明通道并调整尺寸'
    if scale==1 and settings.noise==-1:
        return original,resize_rgba(working,target),note,'仅尺寸调整（已关闭降噪且无需AI放大）'
    with tempfile.TemporaryDirectory(prefix='art-ai-') as tmp:
        inp=Path(tmp)/'input.png';out=Path(tmp)/'output.png'
        bleed_hidden_rgb(working).save(inp,'PNG')
        check_cancel(cancel)
        current=inp
        actual=settings
        if scale==1 and settings.model=='upconv':
            actual=replace(settings,model='cunet')
            note=(note+'；' if note else '')+'1×降噪使用CUnet模型'
        passes=1 if scale==1 else int(math.log2(scale))
        step_scale=1 if scale==1 else 2
        for iteration in range(passes):
            out=Path(tmp)/f'output-{iteration}.png'
            actual=replace(actual,noise=settings.noise if iteration==0 else -1)
            engine.run(current,out,step_scale,actual,cancel,progress)
            current=out
        check_cancel(cancel)
        with Image.open(out) as result:
            result.load()
            expected=(working.width*scale,working.height*scale)
            if result.size != expected: raise ValueError(f'AI输出尺寸异常：{result.size}，应为{expected}')
            rgb=result.convert('RGB')
        # Exact original alpha for 1x; otherwise resample independently, never denoise.
        a=working.getchannel('A')
        if a.size!=rgb.size:a=a.resize(rgb.size,Image.Resampling.LANCZOS)
        rgb.putalpha(a)
        final=resize_rgba(rgb,target)
        if final.size!=target or max(final.size)!=settings.target:raise ValueError('最终像素核验失败')
        return original, final,note,f'waifu2x AI {scale}×，等比例长边{settings.target}'

class Batch:
    def __init__(self,engine_dir,logs_dir=None):
        self.logs_dir=Path(logs_dir).resolve() if logs_dir else Path(engine_dir).resolve().parent/'logs'
        self.engine=Waifu2x(engine_dir);self.cancel=threading.Event();self.lock=threading.RLock()
        self.state={'status':'idle','total':0,'done':0,'failed':0,'current':'','progress':0,'output':'','logs':'','log_warning':'','items':[],'message':'准备好后，先试一张'}
        self._thread=None
    def snapshot(self):
        with self.lock:return json.loads(json.dumps(self.state,ensure_ascii=False))
    def update(self,**values):
        with self.lock:self.state.update(values)
    def start(self,settings):
        with self.lock:
            if self.state['status']=='running' or (self._thread and self._thread.is_alive()):raise ValueError('正在处理或保存报告，请先等待完成或取消')
            root,parent=settings.validate();self.engine.verify(settings.model)
            self.cancel.clear()
            self.state={'status':'running','total':0,'done':0,'failed':0,'current':'扫描文件夹…','progress':0,'output':'','logs':'','log_warning':'','items':[],'message':'扫描中'}
            self._thread=threading.Thread(target=self._run,args=(settings,root,parent),daemon=True);self._thread.start()
        return self.snapshot()
    def stop(self):self.cancel.set()
    def _run(self,settings,root,parent):
        folder=None;log_folder=None
        try:
            files=scan_files(root,settings.recursive,self.cancel)
            if not files:raise ValueError('没有找到支持的图片')
            if settings.sample:files=files[:1]
            check_cancel(self.cancel)
            self.update(current='AI引擎小图自检…',message='先验证引擎可用，尚未处理原图')
            self.engine.self_test(settings,self.cancel)
            check_cancel(self.cancel)
            try:
                self.logs_dir.mkdir(parents=True,exist_ok=True)
                log_folder=output_folder(self.logs_dir,root.name)
            except OSError as exc:
                self.update(log_warning='工具内logs目录不可写，未保存报告；成品处理继续。'+str(exc))
            self.update(logs=str(log_folder) if log_folder else '')
            folder=output_folder(parent,root.name)
            self.update(total=len(files),output=str(folder),message='正在处理；首张图片可能需要较长时间')
            for index,src in enumerate(files):
                check_cancel(self.cancel)
                relative=src.relative_to(root);name=str(relative)
                self.update(current=name)
                started=time.monotonic()
                item={'name':name,'status':'error','error':''}
                try:
                    before,after,note,method=process_image(src,settings,self.engine,self.cancel)
                    check_cancel(self.cancel)
                    dest=folder/relative.parent/(relative.name+'_AI.png')
                    dest=save_png_exclusive(after,dest)
                    item.update(status='done',width=after.width,height=after.height,source_width=before.width,source_height=before.height,output=str(dest.relative_to(folder)),note=note,method=method)
                except Cancelled:raise
                except Exception as exc:
                    item['error']=str(exc)
                    with self.lock:self.state['failed']+=1
                item['seconds']=round(time.monotonic()-started,2)
                with self.lock:
                    self.state['items'].append(item);self.state['done']+=1;self.state['progress']=self.state['done']/len(files)*100
                self._safe_report(log_folder,settings)
            self.update(status='complete',current='',message=f'处理结束：成功{self.state["done"]-self.state["failed"]}张，失败{self.state["failed"]}张')
        except Cancelled:self.update(status='cancelled',current='',message='已取消，完成的图片已保留，可重新开始生成新目录')
        except Exception as exc:self.update(status='error',current='',message=str(exc))
        finally:
            self._safe_report(log_folder,settings)
            warning=self.state.get('log_warning','')
            if warning:self.update(message=self.state['message']+'；'+warning)
    def _safe_report(self,log_folder,settings):
        if not log_folder:return
        try:self._report(log_folder,settings)
        except Exception as exc:
            self.update(log_warning='报告未能保存；已生成的成品保留。'+str(exc))

    def _report(self,log_folder,settings):
        state=self.snapshot()
        report={'version':VERSION,'settings':asdict(settings),**state}
        # Reports live in a separate tool-local logs directory, never the result tree.
        temp=log_folder/'report.tmp'
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(log_folder/'report.json')
        with (log_folder/'处理报告.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['原文件','状态','输出','宽','高','耗时秒','错误','备注'])
            for i in state['items']:
                # Prevent spreadsheet formula injection when users open the CSV.
                def safe(v):
                    s=str(v);return "'"+s if s[:1] in '=+-@\t\r' else s
                w.writerow([safe(i.get(k,'')) for k in ['name','status','output','width','height','seconds','error','note']])
