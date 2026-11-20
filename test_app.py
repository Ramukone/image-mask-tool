import sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import app
from PIL import Image
from pillow_heif import register_heif_opener
register_heif_opener()

def run():
    im=Image.new('RGBA',(43,37)); im.putdata([(x*5%256,y*7%256,123,(x*11+y*7)%256) for y in range(37) for x in range(43)])
    pts=[(3.2,4.3),(36.5,5.8),(20.1,32.9)]
    a,b=app.masked_images(im,pts)
    assert a.size==b.size==im.size
    assert all(aa+bb==o for aa,bb,o in zip(a.getchannel('A').getdata(),b.getchannel('A').getdata(),im.getchannel('A').getdata()))
    assert 0<a.getpixel((20,15))[3] and a.getpixel((0,0))[3]==0
    assert any(0<v<255 for v in app.make_mask(im.size,pts).getdata())
    assert not app.valid_polygon([(0,0),(1,1),(2,2)])
    assert not app.valid_polygon([(0,0),(7,7),(0,6),(6,0)])
    assert not app.is_drag(3,3) and app.is_drag(3,4)
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)
        im.save(p/'test.png'); assert app.open_image(p/'test.png').tobytes()==im.tobytes()
        exif=Image.Exif();exif[274]=6
        Image.new('RGB',(7,4),'red').save(p/'rotate.jpg',exif=exif)
        assert app.open_image(p/'rotate.jpg').size==(4,7)
        pa=app.unique_save(a,p,'result');pb=app.unique_save(b,p,'result');assert pa!=pb and pa.exists() and pb.exists()
        # Primary image is intentionally the second frame.
        first=Image.new('RGB',(9,7),'red'); second=Image.new('RGB',(9,7),'blue')
        first.save(p/'test.heif',save_all=True,append_images=[second],primary_index=1,quality=90)
        h=app.open_image(p/'test.heif'); r,g,bl,_=h.getpixel((4,3)); assert bl>r+50,(r,g,bl)
    root=app.tk.Tk();ui=app.App(root);root.update()
    ui.image=im;ui.preview=im.copy();ui.path=Path('sample.png');ui.fit();root.update()
    class E:pass
    def event(x,y):
        e=E();e.x=int(x);e.y=int(y);return e
    x=ui.ox+10*ui.scale;y=ui.oy+10*ui.scale
    ui.down(event(x,y));ui.move(event(x+6,y));ui.up(event(x+6,y));assert len(ui.points)==0
    x=ui.ox+10*ui.scale;y=ui.oy+10*ui.scale
    ui.down(event(x,y));ui.up(event(x,y));assert len(ui.points)==1
    assert abs(ui.points[0][0]-10)<1/ui.scale and abs(ui.points[0][1]-10)<1/ui.scale
    ev=event(x,y);ev.delta=120
    before=((ev.x-ui.ox)/ui.scale,(ev.y-ui.oy)/ui.scale);ui.wheel(ev)
    after=((ev.x-ui.ox)/ui.scale,(ev.y-ui.oy)/ui.scale);assert all(abs(a-b)<1e-9 for a,b in zip(before,after))
    ui.points=[(2,2),(35,2),(20,30)];ui.close_polygon();assert ui.closed
    ui.undo();assert not ui.closed and len(ui.points)==3
    root.destroy()
    print('PASS: alpha complement, original size, antialiasing, selection validity, coordinates, drag threshold, EXIF, HEIF primary, unique names, GUI smoke')
if __name__=='__main__':run()
