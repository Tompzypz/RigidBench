"""SI dimensions shared by collision geometry and imported visuals."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math,json
from pathlib import Path
EMPTY_BOTTLE_PROPERTIES=json.loads((_PCVE_ROOT / 'assets' / 'scenarios' / 'tennis_bottle_collision' / 'empty_bottle_properties.json').read_text(encoding='utf-8'))
BALL_RADIUS=.0335
BOTTLE_RADIUS=.041
BOTTLE_HEIGHT=.23
COM_HEIGHT=EMPTY_BOTTLE_PROPERTIES['com_height_m']
SIM_HZ=1440
KEYS=('tennis_ball','bottle_left','bottle_right','bottle_added')
BOTTLE_SPACING=.083
START_X=-.52
# Profile of the empty PET bottle, relative to its bottom.
PROFILE=[(0.,.025),(.0018,.034),(.008,.039),(.015,.0405),(.0395,.04095),(.1425,.04095),(.153,.0405),(.165,.0385),(.180,.032),(.194,.022),(.202,.016),(.213,.0177),(.23,.0177)]
def hull_vertices():
 return [(r*math.cos(i*math.tau/80),r*math.sin(i*math.tau/80),z-COM_HEIGHT) for z,r in PROFILE for i in range(80)]
def presence_index(key):
 """Slot of each bottle in the physics bottle_presence mask."""
 return {'bottle_left':0,'bottle_right':1,'bottle_added':2}[key]
def present(ph,key):
 return key=='tennis_ball' or bool(ph['bottle_presence'][presence_index(key)])
def layout(ph):
 d=BOTTLE_SPACING
 return {'tennis_ball':[START_X,0,BALL_RADIUS+.0001],
         'bottle_left':[0,-d/2,COM_HEIGHT+.0001],
         'bottle_right':[0,d/2,COM_HEIGHT+.0001],
         'bottle_added':list(ph['bottle_added_position'])}