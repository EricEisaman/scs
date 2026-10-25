
"""
ROS Playground - SCS Python Pyodide - PRO + DESIGNER EDITION
- Like ferrers.py: uses window.WebSocket + aio + run_python_async, no 404s, no fallbacks
- Toggle overlay: dynamic ROS pub/sub topic bus viewer that impresses ROS pros + UI designers
"""

from scs import *

try:
    from browser import window, aio
    BROWSER_AVAILABLE = True
except ImportError:
    BROWSER_AVAILABLE = False
    window = None
    aio = None

import math, json, random
from dataclasses import dataclass, field
from typing import Dict, List

try:
    from extensions.pyodide import install as pyodide_install, run_python_async
    HAS_PYODIDE = True
except Exception:
    HAS_PYODIDE = False
    pyodide_install = None
    run_python_async = None

W,H=1050,700
LEFT_X,LEFT_Y,LEFT_W,LEFT_H=10,56,210,634
CENTER_X,CENTER_Y,CENTER_W,CENTER_H=230,56,430,634
RIGHT_X,RIGHT_Y,RIGHT_W,RIGHT_H=670,56,370,634
BG=rgb(8,10,20)
PANEL_BG=rgb(16,20,36)
PANEL_BG2=rgb(22,28,48)
PANEL_BORDER=rgb(38,48,80)
CYAN=rgb(86,232,255)
PINK=rgb(255,105,180)
YELLOW=rgb(255,228,100)
GREEN=rgb(95,255,165)
ORANGE=rgb(255,158,80)
WHITE=rgb(242,246,255)
WHITE2=rgb(180,190,220)
DIM=rgb(90,100,130)

TYPE_COLORS={
    "sensor_msgs": CYAN,
    "nav_msgs": GREEN,
    "geometry_msgs": ORANGE,
    "tf2_msgs": YELLOW,
    "std_msgs": WHITE2,
}

def type_color(msg_type):
    for k,v in TYPE_COLORS.items():
        if k in msg_type:
            return v
    return WHITE2

class BrowserWebSocketTransport:
    def __init__(self, url="ws://localhost:9090", on_message=None):
        self.url=url; self.on_message=on_message; self._ws=None; self._connected=False; self._handlers={}; self._open_done=False
        self.published_counts={}
        self.bytes_sent=0
    async def connect(self):
        if not BROWSER_AVAILABLE or window is None:
            self._connected=True; self._open_done=True; return self
        self._ws=window.WebSocket.new(self.url)
        self._open_done=False
        def on_open(evt): self._connected=True; self._open_done=True
        def on_close(evt): self._connected=False
        def on_message(evt):
            try:
                import json as jsjson
                msg=jsjson.loads(evt.data)
                if self.on_message: self.on_message(msg)
                op=msg.get("op")
                if op in self._handlers:
                    for h in self._handlers[op]: h(msg)
            except Exception as e: print(e)
        try:
            from pyodide.ffi import create_proxy
            self._ws.addEventListener("open", create_proxy(on_open))
            self._ws.addEventListener("close", create_proxy(on_close))
            self._ws.addEventListener("message", create_proxy(on_message))
        except Exception:
            try:
                self._ws.onopen=on_open; self._ws.onclose=on_close; self._ws.onmessage=on_message
            except Exception: pass
        for _ in range(100):
            if self._open_done: break
            if aio: await aio.sleep(0.05)
        return self
    async def send(self, obj):
        txt=json.dumps(obj)
        self.bytes_sent+=len(txt)
        if self._ws and getattr(self._ws, "readyState", 1)==1:
            try: self._ws.send(txt)
            except Exception: pass
        if isinstance(obj, dict) and obj.get("op")=="publish":
            t=obj.get("topic","?")
            self.published_counts[t]=self.published_counts.get(t,0)+1
    @property
    def is_connected(self): return self._connected
    async def publish(self, topic, msg): await self.send({"op":"publish","topic":topic,"msg":msg})

async def pyodide_quaternion_from_euler(roll, pitch, yaw):
    if not HAS_PYODIDE or run_python_async is None:
        raise RuntimeError("pyodide required")
    await pyodide_install("transforms3d")
    c = "import json\nimport transforms3d.euler as eul\nimport transforms3d.quaternions as quat\nmat=eul.euler2mat(%s,%s,%s)\nq=quat.mat2quat(mat)\nout=[float(q[1]),float(q[2]),float(q[3]),float(q[0])]\njson.dumps(out)\n" % (roll, pitch, yaw)
    j = await run_python_async(c)
    return json.loads(j) if isinstance(j, str) else j

@dataclass
class RosInterface:
    topic: str; msg_type: str; direction: str; frame_id: str=""

@dataclass
class RobotModule:
    id: str; label: str; icon: str; mass_kg: float; cost: float; xacro_macro: str; interfaces: List[RosInterface] = field(default_factory=list)

MODULE_LIBRARY: Dict[str, RobotModule] = {
    "chassis_box": RobotModule(id="chassis_box", label="Chassis Box", icon="◫", mass_kg=8.5, cost=250, xacro_macro='<xacro:macro name="chassis_box" params="name"><link name="${name}"/></xacro:macro>', interfaces=[RosInterface("/odom","nav_msgs/Odometry","pub","odom"), RosInterface("/tf","tf2_msgs/TFMessage","pub","odom")]),
    "diff_drive": RobotModule(id="diff_drive", label="Diff Drive", icon="◉", mass_kg=2.2, cost=180, xacro_macro='<xacro:macro name="diff_drive" params="name"><link name="${name}"/></xacro:macro>', interfaces=[RosInterface("/cmd_vel","geometry_msgs/Twist","sub","base_link"), RosInterface("/joint_states","sensor_msgs/JointState","pub","base_link")]),
    "lidar_2d_rplidar": RobotModule(id="lidar_2d_rplidar", label="RPLidar A1", icon="◎", mass_kg=0.19, cost=350, xacro_macro='<xacro:macro name="lidar" params="name"><link name="${name}"/></xacro:macro>', interfaces=[RosInterface("/scan","sensor_msgs/LaserScan","pub","lidar_link"), RosInterface("/scan_filtered","sensor_msgs/LaserScan","pub","lidar_link")]),
    "camera_d435": RobotModule(id="camera_d435", label="RealSense D435", icon="◐", mass_kg=0.07, cost=250, xacro_macro='<xacro:macro name="cam" params="name"><link name="${name}"/></xacro:macro>', interfaces=[RosInterface("/camera/color/image_raw","sensor_msgs/Image","pub","camera_link"), RosInterface("/camera/depth/image_raw","sensor_msgs/Image","pub","camera_link")]),
    "imu_mpu9250": RobotModule(id="imu_mpu9250", label="IMU MPU9250", icon="⬡", mass_kg=0.01, cost=25, xacro_macro='<xacro:macro name="imu" params="name"><link name="${name}"/></xacro:macro>', interfaces=[RosInterface("/imu/data","sensor_msgs/Imu","pub","imu_link")]),
}

@dataclass
class ModuleInstance:
    module_id: str; instance_name: str; parent: str

class RobotBuild:
    def __init__(self, name="my_bot"):
        self.name=name; self.base_module="chassis_box"; self.instances=[]
    def add(self, module_id, parent="base_link"):
        if module_id not in MODULE_LIBRARY: return None
        inst=ModuleInstance(module_id=module_id, instance_name=f"{module_id}_{len(self.instances)}", parent=parent)
        self.instances.append(inst); return inst
    def total_mass(self):
        m=MODULE_LIBRARY[self.base_module].mass_kg
        for inst in self.instances: m+=MODULE_LIBRARY[inst.module_id].mass_kg
        return m
    def total_cost(self):
        c=MODULE_LIBRARY[self.base_module].cost
        for inst in self.instances: c+=MODULE_LIBRARY[inst.module_id].cost
        return c
    def to_xacro(self):
        h='<?xml version="1.0"?>\n<robot name="%s">\n' % self.name
        for mid in MODULE_LIBRARY: h+=MODULE_LIBRARY[mid].xacro_macro+"\n"
        h+='</robot>\n'
        return h
    def get_all_interfaces(self):
        ifaces=[]
        for mid in [self.base_module]+[i.module_id for i in self.instances]:
            mod=MODULE_LIBRARY.get(mid)
            if mod:
                for iface in mod.interfaces:
                    ifaces.append((mid, iface))
        return ifaces

class SimWorld:
    def __init__(self, width_m=10, height_m=10):
        self.width=width_m; self.height=height_m; self.obstacles=[(2,1,1,0.5),(-1,2,0.8,0.8),(0,-2,3,0.2)]; self.robot_x=0.0; self.robot_y=0.0; self.robot_th=0.0; self.v=0.0; self.w=0.0; self.lidar_ranges=[8.0]*360; self.time=0.0; self._py_quat=None
    def add_obstacle(self,x,y,w,h): self.obstacles.append((x,y,w,h))
    def set_cmd_vel(self,v,w):
        self.v=max(-1.0,min(1.0,v)); self.w=max(-2.0,min(2.0,w))
    def step(self, dt=0.05):
        self.robot_x+=self.v*math.cos(self.robot_th)*dt; self.robot_y+=self.v*math.sin(self.robot_th)*dt; self.robot_th+=self.w*dt; self.time+=dt
        self.lidar_ranges=[]
        for i in range(360):
            ang=self.robot_th+math.radians(i)
            r=8.0
            for ox,oy,ow,oh in self.obstacles:
                x1=ox-ow/2; x2=ox+ow/2; y1=oy-oh/2; y2=oy+oh/2
                rx,ry=self.robot_x,self.robot_y; dx,dy=math.cos(ang),math.sin(ang)
                tmin=0; tmax=8.0
                if abs(dx)<1e-6:
                    if rx<x1 or rx>x2: continue
                else:
                    tx1=(x1-rx)/dx; tx2=(x2-rx)/dx; tmin=max(tmin,min(tx1,tx2)); tmax=min(tmax,max(tx1,tx2))
                if abs(dy)<1e-6:
                    if ry<y1 or ry>y2: continue
                else:
                    ty1=(y1-ry)/dy; ty2=(y2-ry)/dy; tmin=max(tmin,min(ty1,ty2)); tmax=min(tmax,max(ty1,ty2))
                if tmax>=tmin and tmin>=0 and tmin<r: r=tmin
            self.lidar_ranges.append(round(r,3))
    def get_tf(self):
        half=self.robot_th*0.5
        q=self._py_quat if self._py_quat else [0,0,math.sin(half), math.cos(half)]
        return {"transform":{"translation":{"x":self.robot_x,"y":self.robot_y,"z":0.0},"rotation":{"x":q[0],"y":q[1],"z":q[2],"w":q[3]}}}
    async def update_quat_pyodide(self):
        q=await pyodide_quaternion_from_euler(0,0,self.robot_th); self._py_quat=q; return q

def update_bus_stat(app, topic, msg_type, direction, source, preview="", frame_id="", size=128):
    now=app.time
    stat=app.bus_stats.get(topic)
    if not stat:
        stat={
            "topic": topic, "msg_type": msg_type, "direction": direction,
            "publishers": set(), "subscribers": set(),
            "count": 0, "first_time": now, "last_time": now,
            "hz": 0.0, "hz_history": [], "last_preview": "", "frame_id": frame_id,
            "bw": 0.0, "size": size, "latched": False, "qos": "RELIABLE"
        }
        app.bus_stats[topic]=stat
    if direction=="pub":
        stat["publishers"].add(source)
    else:
        stat["subscribers"].add(source)
    stat["count"]+=1
    dt=now-stat["last_time"]
    if dt>0.05:
        elapsed=now-stat["first_time"]
        if elapsed>0:
            hz=stat["count"]/elapsed
            stat["hz"]=stat["hz"]*0.8+hz*0.2 if stat["hz"]>0 else hz
            stat["hz_history"].append(stat["hz"])
            if len(stat["hz_history"])>24: stat["hz_history"]=stat["hz_history"][-24:]
            stat["bw"]=stat["hz"]*stat["size"]
        stat["last_time"]=now
    if preview:
        stat["last_preview"]=str(preview)[:64]
    if frame_id:
        stat["frame_id"]=frame_id

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
    app.robot_build=RobotBuild("my_bot")
    app.sim=SimWorld(10,10)
    app.ros_client=BrowserWebSocketTransport("ws://localhost:9090")
    app.logs=["[00:00:00] ROS Playground PRO - pyodide like ferrers.py"]
    app.mode="builder"; app.selected_module=None; app.show_xacro=False
    app.show_bus_viewer=False
    app.bus_tab="TOPICS"
    app.bus_stats={}
    app.selected_bus_topic="/scan"
    app.time=0.0
    app.particles=[]
    for mod_id, iface in app.robot_build.get_all_interfaces():
        update_bus_stat(app, iface.topic, iface.msg_type, iface.direction, mod_id, "", iface.frame_id)
    async def install_ros():
        if not HAS_PYODIDE or pyodide_install is None: return
        for p in ["pyyaml","lxml","numpy","urdf-parser-py","xacro","transforms3d","catkin_pkg","rospkg"]:
            try: await pyodide_install(p); app.logs.append("YES %s" % p)
            except Exception: pass
    if HAS_PYODIDE and aio: aio.run(install_ros())
    async def init_quat(): await app.sim.update_quat_pyodide()
    if aio: aio.run(init_quat())

def onStep(app):
    app.time+=0.033; app.sim.step(0.033)
    if int(app.time*12)%12==0 and aio: aio.run(app.sim.update_quat_pyodide())
    if int(app.time*10)%2==0:
        update_bus_stat(app, "/odom", "nav_msgs/Odometry", "pub", "chassis_box", "x=%.2f y=%.2f th=%.0f deg" % (app.sim.robot_x, app.sim.robot_y, math.degrees(app.sim.robot_th)), "odom", 256)
        update_bus_stat(app, "/scan", "sensor_msgs/LaserScan", "pub", "lidar_2d_rplidar", "%d beams, %.1fm max" % (len(app.sim.lidar_ranges), max(app.sim.lidar_ranges) if app.sim.lidar_ranges else 0), "lidar_link", 1800)
        update_bus_stat(app, "/tf", "tf2_msgs/TFMessage", "pub", "chassis_box", "odom->base_link (%.2f,%.2f)" % (app.sim.robot_x, app.sim.robot_y), "odom", 180)
        update_bus_stat(app, "/tf_static", "tf2_msgs/TFMessage", "pub", "chassis_box", "static transforms", "map", 120)
        update_bus_stat(app, "/joint_states", "sensor_msgs/JointState", "pub", "diff_drive", "2 joints", "base_link", 96)
        update_bus_stat(app, "/cmd_vel", "geometry_msgs/Twist", "sub", "diff_drive", "v=%.2f w=%.2f" % (app.sim.v, app.sim.w), "base_link", 48)
        update_bus_stat(app, "/imu/data", "sensor_msgs/Imu", "pub", "imu_mpu9250", "orient qz=%.2f" % (app.sim.get_tf()["transform"]["rotation"]["z"]), "imu_link", 128)
        if random.random()<0.7:
            app.particles.append({"topic": "/scan" if random.random()<0.5 else "/odom", "progress": 0.0, "speed": random.uniform(0.02,0.05)})
    for p in app.particles[:]:
        p["progress"]+=p["speed"]
        if p["progress"]>=1.0:
            app.particles.remove(p)
    if len(app.particles)>60:
        app.particles=app.particles[-60:]

def onMousePress(app,mx,my):
    def in_rect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh
    if in_rect(mx,my,16,8,60,28): app.mode="builder"; return
    if in_rect(mx,my,86,8,40,28): app.mode="sim"; return
    if in_rect(mx,my,136,8,70,28):
        app.show_bus_viewer=not app.show_bus_viewer
        return
    if in_rect(mx,my,216,8,60,28):
        app.bus_tab="TF"
        app.show_bus_viewer=True
        return
    if in_rect(mx,my,W-180,8,70,28):
        async def do_connect(): await app.ros_client.connect()
        if aio: aio.run(do_connect())
        return
    if app.show_bus_viewer:
        px,py,pw,ph=40,54,970,612
        if in_rect(mx,my,px+pw-30, py+12, 22,22):
            app.show_bus_viewer=False; return
        tab_x=px+16
        for tab in ["TOPICS","GRAPH","TF","ECHO"]:
            if in_rect(mx,my,tab_x, py+48, 60,22):
                app.bus_tab=tab; return
            tab_x+=70
        if app.bus_tab=="TOPICS":
            ty=py+84
            for topic in sorted(app.bus_stats.keys()):
                if in_rect(mx,my,px+12, ty, pw-340, 20):
                    app.selected_bus_topic=topic; app.bus_tab="ECHO"; return
                ty+=22
                if ty>py+ph-30: break
        if not in_rect(mx,my,px,py,pw,ph):
            app.show_bus_viewer=False; return
        return
    if LEFT_X<=mx<=LEFT_X+LEFT_W and LEFT_Y<=my<=LEFT_Y+LEFT_H:
        y=LEFT_Y+36
        for mod_id in MODULE_LIBRARY:
            if y<=my<=y+20:
                app.selected_module=mod_id
                app.robot_build.add(mod_id)
                for m_id, iface in app.robot_build.get_all_interfaces():
                    update_bus_stat(app, iface.topic, iface.msg_type, iface.direction, m_id, "", iface.frame_id)
                app.logs.append("added %s" % mod_id)
                return
            y+=24
    if CENTER_X<=mx<=CENTER_X+CENTER_W and CENTER_Y<=my<=CENTER_Y+CENTER_H:
        sX=CENTER_X+16; sW=CENTER_W-32
        if CENTER_Y+390<=my<=CENTER_Y+400:
            t=(mx-sX)/sW; app.sim.set_cmd_vel(t*2-1, app.sim.w)
        if CENTER_Y+420<=my<=CENTER_Y+430:
            t=(mx-sX)/sW; app.sim.set_cmd_vel(app.sim.v, t*4-2)

def onKeyPress(app,key):
    if key.lower()=="b":
        app.show_bus_viewer=not app.show_bus_viewer
    elif key.lower()=="t":
        app.bus_tab="TF"; app.show_bus_viewer=True
    elif key.lower()=="g":
        app.bus_tab="GRAPH"; app.show_bus_viewer=True
    elif key.lower()=="e":
        app.bus_tab="ECHO"; app.show_bus_viewer=True

def drawPanel(x,y,w,h,title="", accent=None):
    drawRect(x+2,y+2,w,h,fill=rgb(0,0,0),opacity=0.3,roundness=12)
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1,roundness=12)
    if accent:
        drawRect(x,y,w,3,fill=accent,roundness=3)
    if title:
        drawRect(x+10,y+8,w-20,20,fill=PANEL_BG2,roundness=6)
        drawLabel(title,x+18,y+18,fill=WHITE2,size=11,bold=True,align="left-center")

def draw_bus_overlay(app):
    drawRect(0,0,W,H,fill=rgb(4,6,16),opacity=0.78)
    for i in range(0,W,40):
        drawLine(i,0,i,H,fill=rgb(20,24,40),lineWidth=0.5,opacity=0.3)
    for i in range(0,H,40):
        drawLine(0,i,W,i,fill=rgb(20,24,40),lineWidth=0.5,opacity=0.3)
    px,py,pw,ph=40,54,970,612
    drawRect(px-2,py-2,pw+4,ph+4,fill=CYAN,opacity=0.15,roundness=18)
    drawRect(px,py,pw,ph,fill=rgb(14,18,34),border=CYAN,borderWidth=1.5,roundness=16)
    drawRect(px+1,py+1,pw-2,48,fill=rgb(18,24,44),roundness=14)
    drawRect(px+1,py+40,pw-2,1,fill=PANEL_BORDER,opacity=0.6)
    drawLabel("ROS TOPIC BUS", px+20, py+20, fill=WHITE, size=18, bold=True, align="left-center")
    drawLabel("LIVE * rqt_graph * tf_tree * echo", px+20, py+34, fill=DIM, size=9, align="left-center")
    sx=px+pw-280
    conn=app.ros_client.is_connected
    drawRect(sx, py+12, 80,22, fill=rgb(22,36,28) if conn else rgb(36,28,22), border=GREEN if conn else ORANGE, borderWidth=1, roundness=11)
    drawCircle(sx+12, py+23, 4, fill=GREEN if conn else ORANGE)
    drawLabel("ROSBRIDGE" if conn else "OFFLINE", sx+40, py+23, fill=GREEN if conn else ORANGE, size=8, bold=True, align="center")
    sx+=90
    drawRect(sx, py+12, 90,22, fill=rgb(24,28,44), border=PANEL_BORDER, borderWidth=1, roundness=11)
    drawLabel("%d TOPICS" % len(app.bus_stats), sx+45, py+23, fill=CYAN, size=9, bold=True, align="center")
    sx+=100
    total_bw=sum(s["bw"] for s in app.bus_stats.values())
    drawRect(sx, py+12, 80,22, fill=rgb(24,28,44), border=PANEL_BORDER, borderWidth=1, roundness=11)
    try: bw_txt="%.1f KB/s" % (total_bw/1000.0)
    except: bw_txt="0 KB/s"
    drawLabel(bw_txt, sx+40, py+23, fill=YELLOW, size=8, bold=True, align="center")
    drawRect(px+pw-30, py+12, 22,22, fill=rgb(36,42,68), border=PANEL_BORDER, borderWidth=1, roundness=7)
    drawLabel("X", px+pw-19, py+23, fill=WHITE, size=11, bold=True, align="center")
    tab_x=px+16; tab_y=py+48
    for tab in ["TOPICS","GRAPH","TF","ECHO"]:
        sel=app.bus_tab==tab
        drawRect(tab_x, tab_y, 64,22, fill=CYAN if sel else rgb(28,36,60), border=CYAN if sel else PANEL_BORDER, borderWidth=1, roundness=8)
        drawLabel(tab, tab_x+32, tab_y+11, fill=rgb(0,0,0) if sel else WHITE2, size=9, bold=sel, align="center")
        tab_x+=72
    cx,cy,cw,ch=px+12, py+80, pw-24, ph-92
    if app.bus_tab=="TOPICS":
        drawRect(cx, cy, cw, 24, fill=rgb(24,30,52), roundness=8)
        headers=[("TOPIC",14),("TYPE",180),("DIR",300),("SRC",340),("Hz",430),("BW",480),("COUNT",530),("FRAME",580),("LAST",660)]
        for name,off in headers:
            drawLabel(name, cx+off, cy+12, fill=DIM, size=8, bold=True, align="left-center")
        y=cy+32
        for topic in sorted(app.bus_stats.keys()):
            stat=app.bus_stats[topic]
            if y>py+ph-30: break
            is_sel=topic==app.selected_bus_topic
            bg=rgb(24,32,56) if is_sel else (rgb(20,26,44) if (y//24)%2==0 else rgb(18,24,40))
            bdr=CYAN if is_sel else PANEL_BORDER
            drawRect(cx, y, cw, 22, fill=bg, border=bdr, borderWidth=1 if is_sel else 0.5, roundness=6)
            col=type_color(stat["msg_type"])
            drawCircle(cx+6, y+11, 3, fill=col)
            drawLabel(topic, cx+14, y+11, fill=WHITE if is_sel else WHITE2, size=9, bold=is_sel, align="left-center")
            drawLabel(stat["msg_type"][:26], cx+180, y+11, fill=col, size=8, align="left-center")
            dir_col=GREEN if stat["direction"]=="pub" else PINK
            drawLabel(stat["direction"].upper(), cx+300, y+11, fill=dir_col, size=7, bold=True, align="left-center")
            src=",".join(list(stat["publishers"] if stat["direction"]=="pub" else stat["subscribers"])[:1])
            drawLabel(src[:12], cx+340, y+11, fill=YELLOW, size=8, align="left-center")
            try: hz_txt="%.1f" % float(stat["hz"])
            except: hz_txt="0.0"
            drawLabel(hz_txt, cx+430, y+11, fill=CYAN, size=8, bold=True, align="left-center")
            try: bw_txt="%dB/s" % int(stat["bw"])
            except: bw_txt="0"
            drawLabel(bw_txt, cx+480, y+11, fill=DIM, size=7, align="left-center")
            drawLabel(str(stat["count"]), cx+530, y+11, fill=WHITE2, size=8, align="left-center")
            drawLabel(stat["frame_id"][:10], cx+580, y+11, fill=ORANGE, size=7, align="left-center")
            drawLabel(stat["last_preview"][:28], cx+660, y+11, fill=rgb(150,170,200), size=7, align="left-center")
            hist=stat["hz_history"]
            if len(hist)>1:
                sx=cx+cw-80; sy=y+4; sw=70; sh=14
                drawRect(sx,sy,sw,sh,fill=rgb(12,16,28),roundness=3)
                max_h=max(hist) if max(hist)>0 else 1
                for i in range(len(hist)-1):
                    x1=sx+i*sw/len(hist); x2=sx+(i+1)*sw/len(hist)
                    y1=sy+sh - hist[i]/max_h*sh; y2=sy+sh - hist[i+1]/max_h*sh
                    drawLine(x1,y1,x2,y2,fill=col,lineWidth=1.2,opacity=0.8)
            y+=24
    elif app.bus_tab=="GRAPH":
        gx,gy,gw,gh=cx,cy,cw,ch-20
        drawRect(gx,gy,gw,gh,fill=rgb(10,14,26),border=PANEL_BORDER,borderWidth=1,roundness=10)
        for i in range(0,gw,50):
            drawLine(gx+i,gy,gx+i,gy+gh,fill=rgb(22,28,44),lineWidth=0.5)
        for i in range(0,gh,50):
            drawLine(gx,gy+i,gx+gw,gy+i,fill=rgb(22,28,44),lineWidth=0.5)
        pubs=list(set().union(*[s["publishers"] for s in app.bus_stats.values()]))[:6]
        subs=list(set().union(*[s["subscribers"] for s in app.bus_stats.values()]))[:6]
        topics=list(app.bus_stats.keys())[:8]
        pub_pos={}
        for i,p in enumerate(pubs):
            x=gx+80; y=gy+60+i*70
            pub_pos[p]=(x,y)
            drawCircle(x,y,22,fill=PINK,opacity=0.12)
            drawRect(x-40,y-16,80,32,fill=rgb(36,28,44),border=PINK,borderWidth=1,roundness=8)
            drawLabel(p[:14], x, y, fill=PINK, size=8, bold=True, align="center")
        topic_pos={}
        for i,t in enumerate(topics):
            x=gx+gw//2 + (i%2*120-60); y=gy+40+i*60
            topic_pos[t]=(x,y)
            col=type_color(app.bus_stats[t]["msg_type"])
            hz=app.bus_stats[t]["hz"]
            pulse= (math.sin(app.time*3+i)+1)*0.15+0.2 if hz>5 else 0.15
            drawCircle(x,y,28,fill=col,opacity=pulse)
            drawRect(x-50,y-14,100,28,fill=rgb(18,26,44),border=col,borderWidth=1.5,roundness=9)
            drawLabel(t[:16], x, y-4, fill=WHITE, size=8, bold=True, align="center")
            try: drawLabel("%.1fHz" % float(hz), x, y+8, fill=col, size=7, align="center")
            except: pass
        sub_pos={}
        for i,s in enumerate(subs):
            x=gx+gw-80; y=gy+60+i*70
            sub_pos[s]=(x,y)
            drawCircle(x,y,22,fill=GREEN,opacity=0.12)
            drawRect(x-40,y-16,80,32,fill=rgb(28,36,32),border=GREEN,borderWidth=1,roundness=8)
            drawLabel(s[:14], x, y, fill=GREEN, size=8, bold=True, align="center")
        for topic, stat in app.bus_stats.items():
            if topic not in topic_pos: continue
            tx,ty=topic_pos[topic]
            for pub in stat["publishers"]:
                if pub not in pub_pos: continue
                px,py=pub_pos[pub]
                drawLine(px+40,py,tx-50,ty,fill=rgb(80,90,120),lineWidth=1,opacity=0.5)
            for sub in stat["subscribers"]:
                if sub not in sub_pos: continue
                sx,sy=sub_pos[sub]
                drawLine(tx+50,ty,sx-40,sy,fill=rgb(80,90,120),lineWidth=1,opacity=0.5)
        for part in app.particles:
            t=part["topic"]
            if t not in topic_pos: continue
            tx,ty=topic_pos[t]
            stat=app.bus_stats.get(t)
            if not stat or not stat["publishers"]: continue
            pub=list(stat["publishers"])[0]
            if pub not in pub_pos: continue
            px,py=pub_pos[pub]
            prog=part["progress"]
            x=px+40 + (tx-50-(px+40))*prog
            y=py + (ty-py)*prog
            col=type_color(stat["msg_type"])
            drawCircle(x,y,3,fill=col,border=WHITE,borderWidth=0.5)
    elif app.bus_tab=="TF":
        gx,gy,gw,gh=cx,cy,cw,ch
        drawRect(gx,gy,gw,gh,fill=rgb(10,14,26),border=PANEL_BORDER,borderWidth=1,roundness=10)
        drawLabel("TF TREE - map -> odom -> base_link", gx+20, gy+16, fill=YELLOW, size=12, bold=True, align="left-top")
        drawLabel("pyodide transforms3d quaternion from run_python_async", gx+20, gy+30, fill=DIM, size=8, align="left-top")
        nodes=[
            ("map", gx+100, gy+80, "static"),
            ("odom", gx+280, gy+80, "nav_msgs/Odometry"),
            ("base_link", gx+460, gy+80, "x=%.2f y=%.2f th=%.0fdeg" % (app.sim.robot_x, app.sim.robot_y, math.degrees(app.sim.robot_th))),
            ("lidar_link", gx+640, gy+50, "sensor_msgs/LaserScan"),
            ("camera_link", gx+640, gy+110, "sensor_msgs/Image"),
        ]
        for i in range(2):
            _,x1,y1,_=nodes[i]
            _,x2,y2,_=nodes[i+1]
            drawLine(x1+40,y1,x2-40,y2,fill=YELLOW,lineWidth=2)
            drawCircle(x2-40,y2,4,fill=YELLOW)
        drawLine(460+40,80+16, 640-40, 50+8, fill=rgb(80,90,120), lineWidth=1)
        drawLine(460+40,80+16, 640-40, 110+8, fill=rgb(80,90,120), lineWidth=1)
        for name,x,y,info in nodes:
            drawRect(x-50,y-16,100,40,fill=rgb(22,28,44),border=YELLOW if name in ["map","odom","base_link"] else CYAN,borderWidth=1.5,roundness=8)
            drawLabel(name, x, y, fill=WHITE, size=10, bold=True, align="center")
            drawLabel(info[:28], x, y+14, fill=DIM, size=7, align="center")
        tf=app.sim.get_tf()
        q=tf["transform"]["rotation"]
        drawRect(gx+20, gy+gh-90, gw-40, 80, fill=rgb(18,24,44), border=PANEL_BORDER, borderWidth=1, roundness=8)
        drawLabel("Current base_link transform (pyodide transforms3d):", gx+30, gy+gh-80, fill=CYAN, size=9, bold=True, align="left-top")
        drawLabel("translation: x=%.3f y=%.3f" % (app.sim.robot_x, app.sim.robot_y), gx+30, gy+gh-60, fill=WHITE2, size=8, align="left-top")
        drawLabel("rotation: x=%.3f y=%.3f z=%.3f w=%.3f" % (q["x"],q["y"],q["z"],q["w"]), gx+30, gy+gh-42, fill=YELLOW, size=8, align="left-top")
    elif app.bus_tab=="ECHO":
        topic=app.selected_bus_topic
        stat=app.bus_stats.get(topic)
        if not stat:
            drawLabel("Select a topic from TOPICS tab", cx+cw//2, cy+ch//2, fill=DIM, size=14, align="center")
        else:
            drawRect(cx, cy, cw//2-10, ch, fill=rgb(16,20,36), border=PANEL_BORDER, borderWidth=1, roundness=10)
            drawLabel(topic, cx+16, cy+20, fill=WHITE, size=14, bold=True, align="left-top")
            drawLabel(stat["msg_type"], cx+16, cy+36, fill=type_color(stat["msg_type"]), size=10, bold=True, align="left-top")
            y=cy+60
            rows=[
                ("Direction", stat["direction"]),
                ("Frame", stat["frame_id"]),
                ("Pubs", ",".join(stat["publishers"])),
                ("Subs", ",".join(stat["subscribers"])),
                ("Hz", "%.2f Hz" % float(stat["hz"]) if stat["hz"] else "0 Hz"),
                ("BW", "%d B/s" % int(stat["bw"])),
            ]
            for k,v in rows:
                drawLabel(k+":", cx+16, y, fill=DIM, size=8, bold=True, align="left-top")
                drawLabel(str(v)[:28], cx+70, y, fill=WHITE2, size=8, align="left-top")
                y+=18
            drawRect(cx+cw//2+10, cy, cw//2-10, ch, fill=rgb(10,14,26), border=PANEL_BORDER, borderWidth=1, roundness=10)
            drawLabel("LAST MESSAGE - rostopic echo %s" % topic, cx+cw//2+24, cy+16, fill=CYAN, size=9, bold=True, align="left-top")
            drawLabel(stat["last_preview"][:64], cx+cw//2+24, cy+32, fill=GREEN, size=8, align="left-top")
            # mock json
            lines=["{","  header: frame_id=%s" % stat["frame_id"],"  stamp: %.2f" % app.time,"  data: %s" % stat["last_preview"],"}"]
            ly=cy+56
            for line in lines:
                drawLabel(line[:52], cx+cw//2+24, ly, fill=rgb(180,200,220), size=8, align="left-top")
                ly+=14

def redrawAll(app):
    drawRect(0,0,W,H,fill=BG)
    drawRect(0,0,W,H,fill=rgb(0,0,0),opacity=0.15)
    drawRect(0,0,W,48,fill=rgb(14,18,32),border=PANEL_BORDER,borderWidth=1)
    drawRect(0,47,W,1,fill=CYAN,opacity=0.3)
    drawLabel("ROS PLAYGROUND", 18, 16, fill=WHITE, size=16, bold=True, align="left-top")
    drawLabel("PRO * rqt_bus * tf_tree * pyodide * window.WebSocket", 18, 32, fill=DIM, size=8, align="left-top")
    def pill(x,label,active,accent):
        bg=accent if active else rgb(26,32,52)
        txt=rgb(0,0,0) if active else (accent if label=="BUS" else WHITE2)
        bdr=accent if active or label=="BUS" else PANEL_BORDER
        drawRect(x,10,60 if len(label)<5 else 70,28,fill=bg,border=bdr,borderWidth=1.5 if active else 1,roundness=14)
        drawLabel(label, x+(30 if len(label)<5 else 35), 24, fill=txt, size=9, bold=True, align="center")
        return x+(70 if len(label)>=5 else 68)
    x=180
    pill(x,"BUILD",app.mode=="builder",CYAN); x+=68
    pill(x,"SIM",app.mode=="sim",GREEN); x+=58
    bx=x
    sel=app.show_bus_viewer
    drawRect(bx,10,70,28,fill=YELLOW if sel else rgb(38,36,24),border=YELLOW,borderWidth=2 if sel else 1,roundness=14)
    pulse=(math.sin(app.time*4)+1)*0.5
    drawCircle(bx+12,24,4+int(pulse*2),fill=YELLOW,opacity=0.2+pulse*0.5)
    drawCircle(bx+12,24,4,fill=YELLOW)
    drawLabel("BUS", bx+38, 24, fill=rgb(0,0,0) if sel else YELLOW, size=9, bold=True, align="center")
    x+=78
    pill(x,"TF",app.bus_tab=="TF" and app.show_bus_viewer,YELLOW); x+=68
    conn=app.ros_client.is_connected
    drawRect(W-100,10,88,28,fill=rgb(22,36,28) if conn else rgb(36,28,24),border=GREEN if conn else ORANGE,borderWidth=1.5,roundness=14)
    drawCircle(W-88,24,5,fill=GREEN if conn else ORANGE)
    drawLabel("LIVE" if conn else "CONNECT", W-56,24,fill=GREEN if conn else ORANGE,size=9,bold=True,align="center")
    drawPanel(LEFT_X,LEFT_Y,LEFT_W,LEFT_H, "ROBOT MODULES  %.1fkg  $%d" % (app.robot_build.total_mass(), app.robot_build.total_cost()), accent=CYAN)
    y=LEFT_Y+36
    for mod_id, mod in MODULE_LIBRARY.items():
        sel=app.selected_module==mod_id
        drawRect(LEFT_X+10, y, LEFT_W-20, 22, fill=rgb(30,36,62) if sel else rgb(22,28,48), border=PINK if sel else PANEL_BORDER, borderWidth=1.2 if sel else 0.8, roundness=8)
        drawLabel(mod.icon, LEFT_X+18, y+11, fill=PINK if sel else WHITE2, size=12, align="left-center")
        drawLabel(mod.label, LEFT_X+36, y+8, fill=WHITE if sel else WHITE2, size=8, bold=sel, align="left-top")
        drawLabel("%d topics" % len(mod.interfaces), LEFT_X+36, y+16, fill=DIM, size=6, align="left-top")
        y+=26
    drawPanel(CENTER_X,CENTER_Y,CENTER_W,CENTER_H, "SIM  x=%.2f y=%.2f th=%.0f deg  quat via pyodide" % (app.sim.robot_x, app.sim.robot_y, math.degrees(app.sim.robot_th)), accent=GREEN)
    gx,gy,gw,gh=CENTER_X+14, CENTER_Y+32, CENTER_W-28, 300
    drawRect(gx,gy,gw,gh,fill=rgb(10,14,26),border=PANEL_BORDER,borderWidth=1,roundness=10)
    cx,cy=gx+gw/2, gy+gh/2; scale=26
    for i in range(-6,7):
        drawLine(cx+i*scale, gy, cx+i*scale, gy+gh, fill=rgb(20,26,44), lineWidth=0.6, opacity=0.5)
        drawLine(gx, cy+i*scale, gx+gw, cy+i*scale, fill=rgb(20,26,44), lineWidth=0.6, opacity=0.5)
    for ox,oy,ow,oh in app.sim.obstacles:
        drawRect(cx+ox*scale-ow*scale/2+1, cy-oy*scale-oh*scale/2+1, ow*scale, oh*scale, fill=rgb(0,0,0), opacity=0.4, roundness=4)
        drawRect(cx+ox*scale-ow*scale/2, cy-oy*scale-oh*scale/2, ow*scale, oh*scale, fill=rgb(200,60,60), border=rgb(255,100,100), borderWidth=1, roundness=4, opacity=0.7)
    rx=cx+app.sim.robot_x*scale; ry=cy-app.sim.robot_y*scale
    drawCircle(rx+2,ry+2,16,fill=rgb(0,0,0),opacity=0.3)
    drawCircle(rx,ry,15,fill=rgb(50,60,84),border=WHITE,borderWidth=1.2)
    drawCircle(rx,ry,5,fill=CYAN,opacity=0.3)
    fx=rx+math.cos(app.sim.robot_th)*14; fy=ry-math.sin(app.sim.robot_th)*14
    drawCircle(fx,fy,5,fill=CYAN,border=WHITE,borderWidth=1)
    for i in range(0,360,18):
        r=app.sim.lidar_ranges[i] if i < len(app.sim.lidar_ranges) else 8.0
        ang=app.sim.robot_th+math.radians(i)
        ex=rx+math.cos(ang)*r*scale*0.6; ey=ry-math.sin(ang)*r*scale*0.6
        drawLine(rx,ry,ex,ey,fill=CYAN,lineWidth=1,opacity=0.18)
        if r<7.5:
            drawCircle(ex,ey,2,fill=YELLOW,opacity=0.6)
    sX,sY,sW=CENTER_X+16, CENTER_Y+390, CENTER_W-32
    drawRect(sX,sY,sW,12,fill=rgb(22,28,44),border=PANEL_BORDER,borderWidth=1,roundness=6)
    t=(app.sim.v+1)/2
    drawRect(sX,sY,t*sW,12,fill=CYAN,roundness=6)
    drawCircle(sX+t*sW, sY+6, 10, fill=rgb(18,22,36), border=CYAN, borderWidth=2)
    drawCircle(sX+t*sW, sY+6, 4, fill=CYAN)
    drawLabel("linear  %.2f m/s" % app.sim.v, sX, sY+18, fill=DIM, size=7, align="left-top")
    sY2=CENTER_Y+420
    drawRect(sX,sY2,sW,12,fill=rgb(22,28,44),border=PANEL_BORDER,borderWidth=1,roundness=6)
    t2=(app.sim.w+2)/4
    drawRect(sX,sY2,t2*sW,12,fill=ORANGE,roundness=6)
    drawCircle(sX+t2*sW, sY2+6, 10, fill=rgb(18,22,36), border=ORANGE, borderWidth=2)
    drawCircle(sX+t2*sW, sY2+6, 4, fill=ORANGE)
    drawLabel("angular  %.2f rad/s" % app.sim.w, sX, sY2+18, fill=DIM, size=7, align="left-top")
    drawRect(CENTER_X+16, CENTER_Y+452, CENTER_W-32, 48, fill=rgb(14,20,36), border=PANEL_BORDER, borderWidth=1, roundness=8)
    try:
        odom_hz=app.bus_stats.get("/odom",{}).get("hz",0)
        scan_hz=app.bus_stats.get("/scan",{}).get("hz",0)
        tf_hz=app.bus_stats.get("/tf",{}).get("hz",0)
        drawLabel("/odom %.1fHz  /scan %.1fHz  /tf %.1fHz" % (float(odom_hz), float(scan_hz), float(tf_hz)), CENTER_X+24, CENTER_Y+468, fill=WHITE2, size=8, align="left-top")
    except:
        drawLabel("/odom /scan /tf live", CENTER_X+24, CENTER_Y+468, fill=WHITE2, size=8, align="left-top")
    drawLabel("transforms3d via pyodide.run_python_async() - window.WebSocket", CENTER_X+24, CENTER_Y+482, fill=DIM, size=6, align="left-top")
    drawPanel(RIGHT_X,RIGHT_Y,RIGHT_W,RIGHT_H, "LIVE BUS  %d topics" % len(app.bus_stats), accent=YELLOW)
    y=RIGHT_Y+36
    for topic, stat in list(sorted(app.bus_stats.items(), key=lambda kv: -kv[1]["hz"]))[:9]:
        col=type_color(stat["msg_type"])
        sel=topic==app.selected_bus_topic
        drawRect(RIGHT_X+10, y, RIGHT_W-20, 22, fill=rgb(28,36,62) if sel else rgb(20,26,44), border=col if sel else PANEL_BORDER, borderWidth=1 if sel else 0.5, roundness=8)
        drawCircle(RIGHT_X+18, y+11, 3, fill=col)
        if stat["hz"]>3:
            pulse=(math.sin(app.time*6)+1)*0.5
            drawCircle(RIGHT_X+18, y+11, 3+int(pulse*3), fill=col, opacity=0.15)
        drawLabel(topic[:22], RIGHT_X+26, y+7, fill=WHITE if sel else WHITE2, size=8, bold=sel, align="left-top")
        drawLabel(stat["msg_type"].split("/")[-1][:16], RIGHT_X+26, y+15, fill=DIM, size=6, align="left-top")
        try: hz_txt="%.1fHz" % float(stat["hz"])
        except: hz_txt="0Hz"
        drawLabel(hz_txt, RIGHT_X+RIGHT_W-16, y+11, fill=col, size=8, bold=True, align="right-center")
        hist=stat["hz_history"]
        if len(hist)>1:
            sx=RIGHT_X+120; sy=y+14; sw=60; sh=8
            max_h=max(hist) if max(hist)>0 else 1
            for i in range(len(hist)-1):
                x1=sx+i*sw/len(hist); x2=sx+(i+1)*sw/len(hist)
                y1=sy+sh - hist[i]/max_h*sh; y2=sy+sh - hist[i+1]/max_h*sh
                drawLine(x1,y1,x2,y2,fill=col,lineWidth=1,opacity=0.7)
        y+=26
    drawRect(RIGHT_X+10, RIGHT_Y+RIGHT_H-110, RIGHT_W-20, 100, fill=rgb(10,14,26), border=PANEL_BORDER, borderWidth=1, roundness=8)
    ly=RIGHT_Y+RIGHT_H-100
    for line in app.logs[-6:]:
        drawLabel(line[:52], RIGHT_X+16, ly, fill=GREEN, size=7, align="left-top")
        ly+=14
    if app.show_bus_viewer:
        draw_bus_overlay(app)
    else:
        drawRect(W-210, H-28, 200,18, fill=rgb(24,28,44), border=YELLOW, borderWidth=1, roundness=9, opacity=0.9)
        drawLabel("Press [B] for BUS viewer", W-110, H-19, fill=YELLOW, size=8, bold=True, align="center")

class RosPlaygroundApp:
    width=W; height=H
    def __init__(self): pass
App=RosPlaygroundApp
SCS_APP_TYPE="python.pyodide"
SCS_APP_SIZE=(1050,700)
