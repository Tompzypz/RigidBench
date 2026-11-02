"""Clearly label display-only terrain guides without modifying simulated geometry."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pathlib import Path
import shutil
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import imageio.v2 as imageio

def caption(pixels,gt,index):
    picture=Image.fromarray(pixels).convert('RGBA');overlay=Image.new('RGBA',picture.size)
    draw=ImageDraw.Draw(overlay);width,height=picture.size;size=max(12,round(17*width/960))
    try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    except OSError:font=ImageFont.load_default()
    guide=gt['scenario']['render'].get('surface_guide','none')
    view=gt['scenario']['render'].get('view','terrain')
    text='2 cm relief contours | display guide; geometry unchanged' if guide=='contours' else 'Low raking sunlight | ground = simulated collision mesh'
    bar_height=max(30,round(36*width/960));draw.rectangle((0,0,width,bar_height),fill=(18,25,28,205))
    draw.text((14,8),text,font=font,fill=(245,235,211,255))
    time=gt['frames'][index]['time_sec'];slow=gt['slow_motion'];speed='real speed' if slow==1 else f'{slow}x slow'
    right=f't={time:.2f}s | {speed}';draw.text((width-draw.textbbox((0,0),right,font=font)[2]-14,8),right,font=font,fill=(236,196,124,255))
    return np.asarray(Image.alpha_composite(picture,overlay).convert('RGB'))

def label_outputs(out,gt,preview_frame,animation=False):
    out=Path(out);raw=out/'preview_unlabelled.png';shutil.copy2(out/'preview.png',raw)
    with Image.open(raw) as picture:Image.fromarray(caption(np.asarray(picture.convert('RGB')),gt,preview_frame-1)).save(out/'preview.png')
    if animation:
        reader=imageio.get_reader(out/'uneven_ground_ball.mp4')
        try:
            with imageio.get_writer(out/'video.mp4',fps=gt['fps'],codec='libx264',quality=8,macro_block_size=1) as writer:
                for i,pixels in enumerate(reader):writer.append_data(caption(pixels,gt,i))
        finally:reader.close()
