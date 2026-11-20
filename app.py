import os, sys, math, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageOps, ImageTk
try:
    from pillow_heif import register_heif_opener
    register_heif_opener(thumbnails=False)
    HEIF = True
except ImportError:
    HEIF = False

DRAG_THRESHOLD = 5

def enable_high_dpi():
    if sys.platform != 'win32': return
    try:
        import ctypes
        if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except Exception: pass

def workarea(root):
    try:
        import ctypes
        from ctypes import wintypes
        rect=wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030,0,ctypes.byref(rect),0):
            return rect.right-rect.left,rect.bottom-rect.top
    except Exception: pass
    return root.winfo_screenwidth(),root.winfo_screenheight()

def is_drag(dx, dy, factor=1):
    return dx * dx + dy * dy >= (DRAG_THRESHOLD * factor) ** 2

def open_image(path):
    with Image.open(path) as im:
        # pillow-heif presents the primary image on opening.
        im = ImageOps.exif_transpose(im)
        if im.mode in ('I;16', 'I;16L', 'I;16B', 'I;16N'):
            # Map the full unsigned 16-bit range to 8-bit, without clipping
            # every sample above 255 to white or stretching each image.
            im = im.convert('I').point(lambda value: value / 257 + 0.5).convert('L')
        return im.convert('RGBA')

def valid_polygon(points):
    if len(points) < 3 or len(set(points)) < 3:
        return False
    area = abs(sum(points[i][0]*points[(i+1)%len(points)][1] - points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points))))
    if area <= 0.01: return False
    def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,c): return min(a[0],b[0]) <= c[0] <= max(a[0],b[0]) and min(a[1],b[1]) <= c[1] <= max(a[1],b[1])
    def intersects(a,b,c,d):
        o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
        if (o1>0)!=(o2>0) and (o3>0)!=(o4>0) and all(v != 0 for v in (o1,o2,o3,o4)): return True
        return (o1==0 and on(a,b,c)) or (o2==0 and on(a,b,d)) or (o3==0 and on(c,d,a)) or (o4==0 and on(c,d,b))
    n=len(points)
    for i in range(n):
        a,b,c=points[i-1],points[i],points[(i+1)%n]
        if orient(a,b,c)==0 and (a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])>0: return False
    if any(points[i]==points[(i+1)%n] for i in range(n)): return False
    for i in range(n):
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1): continue
            if intersects(points[i],points[(i+1)%n],points[j],points[(j+1)%n]): return False
    return True

def make_mask(size, points):
    # Rasterize in bounded tiles, then reduce by box averaging for stable antialiasing.
    w,h=size
    mask=Image.new('L',size,0)
    tile=512; factor=4
    for y in range(0,h,tile):
        for x in range(0,w,tile):
            tw,th=min(tile,w-x),min(tile,h-y)
            part=Image.new('L',(tw*factor,th*factor),0)
            p=[(int(px*factor)-x*factor,int(py*factor)-y*factor) for px,py in points]
            ImageDraw.Draw(part).polygon(p,fill=255)
            mask.paste(part.resize((tw,th),Image.Resampling.BOX),(x,y))
    return mask

def masked_images(image, points):
    if not valid_polygon(points):
        raise ValueError('请至少选择三个不在同一直线上的点，并闭合选区。')
    mask=make_mask(image.size,points)
    alpha=image.getchannel('A')
    # The two resulting alpha values sum to the original alpha at every pixel.
    from PIL import ImageChops
    inside_alpha=ImageChops.multiply(alpha,mask)
    outside_alpha=ImageChops.subtract(alpha,inside_alpha)
    inside=image.copy(); inside.putalpha(inside_alpha)
    outside=image.copy(); outside.putalpha(outside_alpha)
    return inside,outside

def unique_save(image, folder, stem):
    for n in range(10000):
        path=Path(folder)/(stem + (f'_{n}' if n else '') + '.png')
        try:
            with path.open('xb') as f:
                try: image.save(f,format='PNG')
                except Exception:
                    f.close(); path.unlink(missing_ok=True); raise
            return path
        except FileExistsError: continue
    raise OSError('无法生成不重复的文件名。')

def save_selection(image, points, folder, stem, mode):
    if mode not in ('inside', 'outside', 'both'):
        raise ValueError('未知的导出方式。')
    inside, outside = masked_images(image, points)
    saved = []
    try:
        if mode in ('inside', 'both'):
            saved.append(unique_save(inside, folder, stem+'_选区内'))
        if mode in ('outside', 'both'):
            saved.append(unique_save(outside, folder, stem+'_选区外'))
    except Exception as error:
        remaining = []
        for path in saved:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                remaining.append(path)
        if remaining:
            raise OSError(f'{error}\n\n以下本次输出未能清理，请检查后再重试：\n'
                          + '\n'.join(str(path) for path in remaining)) from error
        raise
    return saved


class App:
    def __init__(self,root):
        self.root=root; root.title('图片蒙版工具')
        self.dpi=max(1.0,root.winfo_fpixels('1i')/96.0)
        self.p=lambda n:max(1,round(n*self.dpi))
        sw,sh=workarea(root);root.geometry(f'{min(int(1180*self.dpi),sw-40)}x{min(int(760*self.dpi),sh-40)}');root.minsize(min(int(650*self.dpi),sw-40),min(int(460*self.dpi),sh-40))
        self.image=None; self.preview=None; self.path=None; self.points=[]; self.closed=False
        self.scale=1; self.ox=0; self.oy=0; self.press=None; self.dragging=False; self.photo=None; self.job=None; self.busy=False
        root.configure(bg='#f2f4f4');root.protocol('WM_DELETE_WINDOW',self.on_close)
        style=ttk.Style(); style.theme_use('clam')
        style.configure('TButton',font=('Microsoft YaHei UI',10),padding=(int(12*self.dpi),int(8*self.dpi)))
        style.configure('Accent.TButton',font=('Microsoft YaHei UI',10,'bold'),padding=(int(12*self.dpi),int(8*self.dpi)),background='#087f75',foreground='white')
        style.map('Accent.TButton',background=[('active','#06695f'),('disabled','#aebdbb')])
        top=tk.Frame(root,bg='#ffffff',padx=self.p(18),pady=self.p(12)); top.pack(fill='x')
        tk.Label(top,text='图片蒙版工具',font=('Microsoft YaHei UI',16,'bold'),fg='#193b3a',bg='#ffffff').pack(side='left')
        ttk.Button(top,text='打开图片',style='Accent.TButton',command=self.choose).pack(side='right')
        bar=tk.Frame(root,bg='#f2f4f4',padx=self.p(16),pady=self.p(10)); bar.pack(fill='x')
        first=tk.Frame(bar,bg='#f2f4f4');first.pack(fill='x')
        second=tk.Frame(bar,bg='#f2f4f4');second.pack(fill='x',pady=(self.p(6),0))
        for text,cmd in [('撤销节点',self.undo),('重新绘制',self.reset),('闭合选区',self.close_polygon)]:
            ttk.Button(first,text=text,command=cmd).pack(side='left',padx=(0,self.p(7)))
        for text,cmd in [('适配窗口',self.fit),('原始大小 100%',self.actual)]:
            ttk.Button(second,text=text,command=cmd).pack(side='left',padx=(0,self.p(7)))
        self.canvas=tk.Canvas(root,bg='#303b3b',highlightthickness=0,cursor='crosshair'); self.canvas.pack(fill='both',expand=True,padx=self.p(16))
        bottom=tk.Frame(root,bg='#f2f4f4',padx=self.p(16),pady=self.p(12)); bottom.pack(fill='x')
        self.status=tk.StringVar(value='打开图片后，单击添加节点；点击起点或按 Enter 闭合。')
        tk.Label(bottom,textvariable=self.status,bg='#f2f4f4',fg='#344e4d',anchor='w',font=('Microsoft YaHei UI',9)).pack(fill='x',pady=(0,self.p(7)))
        exports=tk.Frame(bottom,bg='#f2f4f4');exports.pack(fill='x')
        self.export_buttons=[]
        for label,mode in [('导出内部','inside'),('导出外部','outside'),('同时导出','both')]:
            b=ttk.Button(bottom,text=label,style='Accent.TButton',command=lambda m=mode:self.export(m)); b.pack(in_=exports,side='left',padx=(0,self.p(7)));self.export_buttons.append(b)
        self.set_buttons()
        self.canvas.bind('<Configure>',lambda e:self.schedule()); self.canvas.bind('<ButtonPress-1>',self.down); self.canvas.bind('<B1-Motion>',self.move); self.canvas.bind('<ButtonRelease-1>',self.up)
        self.canvas.bind('<MouseWheel>',self.wheel); root.bind('<Return>',lambda e:self.close_polygon()); root.bind('<Escape>',lambda e:self.reset()); root.bind('<BackSpace>',lambda e:self.undo()); root.bind('<Control-z>',lambda e:self.undo());root.bind('<Control-o>',lambda e:self.choose())
    def on_close(self):
        if self.busy: messagebox.showinfo('正在导出','请等待导出完成后再关闭。')
        else: self.root.destroy()
    def set_buttons(self):
        for b in self.export_buttons:b.configure(state='normal' if self.closed else 'disabled')
    def choose(self):
        if self.busy:return
        path=filedialog.askopenfilename(title='打开图片',filetypes=[('图片','*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.heic *.heif *.avif'),('所有文件','*.*')])
        if not path:return
        try:
            image=open_image(path)
            preview=image.copy();preview.thumbnail((4096,4096),Image.Resampling.LANCZOS)
        except Exception as e: messagebox.showerror('无法打开图片',f'请检查图片格式或文件是否完整。\n\n{e}');return
        self.image=image;self.preview=preview;self.path=Path(path);self.points=[];self.closed=False;self.set_buttons();self.fit()
        self.status.set(f'{self.path.name}  ·  {image.width} × {image.height} 像素  |  单击添加节点，拖动平移，滚轮缩放')
    def fit(self):
        if self.busy or not self.image:return
        w=max(self.canvas.winfo_width(),1);h=max(self.canvas.winfo_height(),1)
        self.scale=min((w-self.p(40))/self.image.width,(h-self.p(40))/self.image.height); self.scale=max(self.scale,0.0001)
        self.ox=(w-self.image.width*self.scale)/2;self.oy=(h-self.image.height*self.scale)/2;self.schedule()
    def actual(self):
        if self.busy or not self.image:return
        cx=self.canvas.winfo_width()/2;cy=self.canvas.winfo_height()/2
        px=(cx-self.ox)/self.scale;py=(cy-self.oy)/self.scale
        self.scale=1;self.ox=cx-px;self.oy=cy-py;self.schedule()
    def schedule(self):
        # Keep the pending frame: repeated input updates the state it will draw.
        if self.job is None:self.job=self.root.after(15,self.draw)
    def draw(self):
        self.job=None;c=self.canvas;c.delete('all')
        if not self.image:
            c.create_text(c.winfo_width()/2,c.winfo_height()/2,text='打开一张图片，开始绘制选区',fill='#d9e5e3',font=('Microsoft YaHei UI',15));return
        w,h=self.image.size;cw,ch=c.winfo_width(),c.winfo_height()
        left=max(0,int(math.floor(-self.ox/self.scale)));top=max(0,int(math.floor(-self.oy/self.scale)))
        right=min(w,int(math.ceil((cw-self.ox)/self.scale)));bottom=min(h,int(math.ceil((ch-self.oy)/self.scale)))
        if left<right and top<bottom:
            # Draw only the visible viewport from the cached preview.
            pw,ph=self.preview.size
            box=(left*pw/w,top*ph/h,right*pw/w,bottom*ph/h)
            dw=max(1,round((right-left)*self.scale));dh=max(1,round((bottom-top)*self.scale))
            if self.scale >= 1:
                patch=self.image.crop((left,top,right,bottom)).resize((dw,dh),Image.Resampling.NEAREST)
            else:
                patch=self.preview.resize((dw,dh),Image.Resampling.BILINEAR,box=box)
            # Checkerboard shows original transparency.
            bg=Image.new('RGB',(dw,dh),'#d6dede'); d=ImageDraw.Draw(bg); sq=self.p(12)
            for yy in range(0,dh,sq):
                for xx in range(0,dw,sq):
                    if ((xx//sq)+(yy//sq))%2:d.rectangle((xx,yy,xx+sq-1,yy+sq-1),fill='#b7c5c3')
            bg.paste(patch,(0,0),patch.getchannel('A'));self.photo=ImageTk.PhotoImage(bg)
            c.create_image(self.ox+left*self.scale,self.oy+top*self.scale,image=self.photo,anchor='nw')
        coords=[]
        for x,y in self.points:coords.extend((self.ox+x*self.scale,self.oy+y*self.scale))
        if len(coords)>=4:
            line=coords+coords[:2] if self.closed else coords
            c.create_line(*line,fill='#122f2d',width=self.p(5));c.create_line(*line,fill='#67f4dc',width=self.p(2))
        for i in range(len(self.points)):
            x,y=coords[2*i:2*i+2];r=(6 if i==0 else 4)*self.dpi
            c.create_oval(x-r,y-r,x+r,y+r,fill='#ffffff' if i else '#ffe690',outline='#005f57',width=self.p(2))
    def down(self,e):
        if self.busy:return
        self.press=(e.x,e.y);self.dragging=False;self.last=(e.x,e.y)
    def move(self,e):
        if not self.press:return
        if not self.dragging and is_drag(e.x-self.press[0],e.y-self.press[1],self.dpi):
            self.dragging=True
            self.last=self.press
        if self.dragging:
            self.ox+=e.x-self.last[0];self.oy+=e.y-self.last[1];self.schedule()
        self.last=(e.x,e.y)
    def up(self,e):
        if not self.press:return
        drag=self.dragging or is_drag(e.x-self.press[0],e.y-self.press[1],self.dpi)
        if drag:
            previous=self.last if self.dragging else self.press
            self.ox+=e.x-previous[0];self.oy+=e.y-previous[1]
            self.schedule()
        self.press=None
        if drag or not self.image or self.closed:return
        x=(e.x-self.ox)/self.scale;y=(e.y-self.oy)/self.scale
        if not (0<=x<=self.image.width and 0<=y<=self.image.height):return
        if len(self.points)>=3 and math.hypot(e.x-(self.ox+self.points[0][0]*self.scale),e.y-(self.oy+self.points[0][1]*self.scale))<=10*self.dpi:
            self.close_polygon();return
        self.points.append((x,y));self.status.set(f'已添加 {len(self.points)} 个节点  |  点击起点或按 Enter 闭合；Backspace 撤销');self.schedule()
    def wheel(self,e):
        if self.busy or not self.image:return
        old=self.scale;self.scale=max(0.0001,min(16,old*(1.2 if e.delta>0 else 1/1.2)))
        self.ox=e.x-(e.x-self.ox)*self.scale/old;self.oy=e.y-(e.y-self.oy)*self.scale/old;self.schedule()
    def undo(self):
        if self.busy:return
        if self.closed:self.closed=False
        elif self.points:self.points.pop()
        self.set_buttons();self.schedule();self.status.set(f'当前 {len(self.points)} 个节点  |  点击起点或按 Enter 闭合')
    def reset(self):
        if self.busy or not self.image:return
        self.points=[];self.closed=False;self.set_buttons();self.schedule();self.status.set('已清除选区。单击图片添加节点。')
    def close_polygon(self):
        if self.busy or self.closed or not self.image:return
        if not valid_polygon(self.points):messagebox.showinfo('无法闭合','请至少选择三个不在同一直线上的点，且边线不能相交。');return
        self.closed=True;self.set_buttons();self.schedule();self.status.set('选区已闭合，可以导出。撤销节点可继续修改。')
    def all_buttons(self, widget):
        for child in widget.winfo_children():
            if isinstance(child,ttk.Button): yield child
            yield from self.all_buttons(child)
    def export(self,mode):
        if self.busy or not self.closed or not valid_polygon(self.points):return
        folder=filedialog.askdirectory(title='选择导出文件夹')
        if not folder:return
        self.busy=True;self.canvas.configure(cursor='watch')
        for b in self.all_buttons(self.root):b.configure(state='disabled')
        self.status.set('正在生成原图尺寸的透明 PNG，请稍候…')
        result=queue.Queue(); image=self.image; points=list(self.points); stem=self.path.stem
        def worker():
            try:
                results=save_selection(image,points,folder,stem,mode)
                result.put((True,results))
            except Exception as e:result.put((False,str(e)))
        def poll():
            try:ok,value=result.get_nowait()
            except queue.Empty:self.root.after(100,poll);return
            self.busy=False;self.canvas.configure(cursor='crosshair')
            for b in self.all_buttons(self.root):b.configure(state='normal')
            self.set_buttons()
            if ok:
                self.status.set('导出完成：'+ '、'.join(p.name for p in value));messagebox.showinfo('导出完成','已保存：\n'+'\n'.join(str(p) for p in value))
            else:self.status.set('导出失败，请重试。');messagebox.showerror('导出失败',value)
        threading.Thread(target=worker,daemon=True).start();self.root.after(100,poll)

if __name__=='__main__':
    enable_high_dpi()
    root=tk.Tk();App(root);root.mainloop()
