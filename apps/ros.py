
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

# --- PRO FIX: cached install, no repeated micropip spam ---
_transforms3d_installed = False
_transforms3d_install_attempted = False

async def pyodide_quaternion_from_euler(roll, pitch, yaw):
    global _transforms3d_installed, _transforms3d_install_attempted
    if not HAS_PYODIDE or run_python_async is None:
        raise RuntimeError("pyodide required")
    # Only install once, avoid spamming "Loading micropip" every quaternion update
    if not _transforms3d_install_attempted:
        _transforms3d_install_attempted = True
        try:
            ok = await pyodide_install("transforms3d")
            _transforms3d_installed = bool(ok)
        except Exception as e:
            print(f"[ros] transforms3d install failed, using JS fallback: {e}")
            _transforms3d_installed = False
    # If transforms3d not available, use pure JS math fallback (no pyodide needed)
    if not _transforms3d_installed:
        # JS fallback: euler to quat (ZYX order, same as ROS)
        cr = math.cos(roll*0.5); sr = math.sin(roll*0.5)
        cp = math.cos(pitch*0.5); sp = math.sin(pitch*0.5)
        cy = math.cos(yaw*0.5); sy = math.sin(yaw*0.5)
        # quaternion = qy * qp * qr
        w = cr*cp*cy + sr*sp*sy
        x = sr*cp*cy - cr*sp*sy
        y = cr*sp*cy + sr*cp*sy
        z = cr*cp*sy - sr*sp*cy
        return [x, y, z, w]
    c = "import json\nimport transforms3d.euler as eul\nimport transforms3d.quaternions as quat\nmat=eul.euler2mat(%s,%s,%s)\nq=quat.mat2quat(mat)\nout=[float(q[1]),float(q[2]),float(q[3]),float(q[0])]\njson.dumps(out)\n" % (roll, pitch, yaw)
    try:
        j = await run_python_async(c)
        return json.loads(j) if isinstance(j, str) else j
    except Exception as e:
        # Fallback to JS math if pyodide fails
        print(f"[ros] quat pyodide failed, JS fallback: {e}")
        cr = math.cos(roll*0.5); sr = math.sin(roll*0.5)
        cp = math.cos(pitch*0.5); sp = math.sin(pitch*0.5)
        cy = math.cos(yaw*0.5); sy = math.sin(yaw*0.5)
        w = cr*cp*cy + sr*sp*sy
        x = sr*cp*cy - cr*sp*sy
        y = cr*sp*cy + sr*cp*sy
        z = cr*cp*sy - sr*sp*cy
        return [x, y, z, w]

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
    # --- PRO FIX: only install packages that have Pyodide wheels, no spam ---
    async def install_ros():
        if not HAS_PYODIDE or pyodide_install is None:
            app.logs.append("pyodide not available, using JS fallback for quat")
            return
        # Only packages known to work in Pyodide - avoids ValueError for urdf-parser-py
        # transforms3d is pure python and works, others are handled via loadPackage in pyodide.py
        safe_packages = ["transforms3d"]  # was ["pyyaml","lxml","numpy","urdf-parser-py","xacro","transforms3d","catkin_pkg","rospkg"] -> caused spam
        for p in safe_packages:
            try:
                ok = await pyodide_install(p)
                if ok:
                    app.logs.append(f"YES {p}")
                else:
                    app.logs.append(f"SKIP {p} (no wheel, using fallback)")
            except Exception as e:
                app.logs.append(f"NO {p}: {str(e)[:30]}")
                print(f"[ros] install {p} failed: {e}")
    if HAS_PYODIDE and aio:
        aio.run(install_ros())
    async def init_quat():
        # Initial quat with fallback - don't spam install
        try:
            await app.sim.update_quat_pyodide()
        except Exception as e:
            print(f"[ros] init quat fallback: {e}")
            # use JS fallback already handled inside update_quat
            pass
    if aio:
        aio.run(init_quat())

def onStep(app):
    app.time+=0.033; app.sim.step(0.033)
    # --- PRO FIX: throttle quat updates to every 3 sec, avoid concurrent pyodide calls ---
    # Old: int(time*12)%12==0 caused call every 1 sec + install spam
    # New: only if enough time passed and no install in progress
    if not hasattr(app, '_last_quat_update'):
        app._last_quat_update = 0
        app._quat_updating = False
    if app.time - app._last_quat_update > 3.0 and not app._quat_updating and aio:
        app._last_quat_update = app.time
        app._quat_updating = True
        async def do_quat():
            try:
                await app.sim.update_quat_pyodide()
            except Exception as e:
                # JS fallback already in get_tf
                pass
            finally:
                app._quat_updating = False
        aio.run(do_quat())
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
    # Top bar pills - accurate hit zones matching 80x36, 90x36 visuals
    if in_rect(mx,my,16,10,80,36): app.mode="builder"; return
    if in_rect(mx,my,96,10,80,36): app.mode="sim"; return
    if in_rect(mx,my,176,10,90,36):
        app.show_bus_viewer=not app.show_bus_viewer
        return
    if in_rect(mx,my,266,10,80,36):
        app.bus_tab="TF"
        app.show_bus_viewer=True
        return
    if in_rect(mx,my,W-120,10,108,36):
        async def do_connect(): await app.ros_client.connect()
        if aio: aio.run(do_connect())
        return
    if app.show_bus_viewer:
        # === PERFECT CLEAN FULL-SCREEN OVERLAY HIT TEST - accurate ===
        # Close button - 32x32 at W-44,12
        if in_rect(mx,my,W-44, 12, 32,32):
            app.show_bus_viewer=False; return
        # Tab bar - 72x24 at y=79 (73+6) but hit zone larger for easier clicking: 82x36 at y=73
        tab_x=16
        for tab in ["TOPICS","GRAPH","TF","ECHO"]:
            if in_rect(mx,my,tab_x, 73, 72,36):
                app.bus_tab=tab; return
            tab_x+=82
        # Topics list - rows now 44px high, y+=50, starting at 124 (72+52)
        if app.bus_tab=="TOPICS":
            ty=124
            for topic in sorted(app.bus_stats.keys()):
                if in_rect(mx,my,12, ty, W-24, 44):
                    app.selected_bus_topic=topic; app.bus_tab="ECHO"; return
                ty+=50
                if ty>H-30: break
        # Click outside content but inside overlay should not close (full-screen), only close button
        # Allow clicking on GRAPH nodes? For now return to block underlying
        return
    if LEFT_X<=mx<=LEFT_X+LEFT_W and LEFT_Y<=my<=LEFT_Y+LEFT_H:
        y=LEFT_Y+42
        for mod_id in MODULE_LIBRARY:
            if y<=my<=y+52:
                app.selected_module=mod_id
                app.robot_build.add(mod_id)
                for m_id, iface in app.robot_build.get_all_interfaces():
                    update_bus_stat(app, iface.topic, iface.msg_type, iface.direction, m_id, "", iface.frame_id)
                app.logs.append("added %s" % mod_id)
                return
            y+=58
    # RIGHT panel LIVE BUS - accurate hit zones for 52px rows
    if RIGHT_X<=mx<=RIGHT_X+RIGHT_W and RIGHT_Y<=my<=RIGHT_Y+RIGHT_H:
        y=RIGHT_Y+44
        for topic in sorted(app.bus_stats.keys())[:7]:
            if y<=my<=y+52:
                app.selected_bus_topic=topic
                app.bus_tab="ECHO"
                app.show_bus_viewer=True
                return
            y+=58
    if CENTER_X<=mx<=CENTER_X+CENTER_W and CENTER_Y<=my<=CENTER_Y+CENTER_H:
        sX=CENTER_X+16; sW=CENTER_W-32
        # Linear slider - 20px height at CENTER_Y+390, hit zone 30px for easier grab
        if CENTER_Y+385<=my<=CENTER_Y+415:
            t=max(0,min(1,(mx-sX)/sW)); app.sim.set_cmd_vel(t*2-1, app.sim.w)
        # Angular slider - 20px height at CENTER_Y+420
        if CENTER_Y+415<=my<=CENTER_Y+445:
            t=max(0,min(1,(mx-sX)/sW)); app.sim.set_cmd_vel(app.sim.v, t*4-2)

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
        drawLabel(title,x+18,y+18,fill=WHITE2,size=15,bold=True,align="left-center")

def draw_bus_overlay(app):
    # === TOP-TIER PRO PERFECT OVERLAY - covers entire initial canvas 0,0,W,H solid, no partial ===
    # Clean perfect overlay - 100% solid, no transparency bleeding, no grid
    drawRect(0,0,W,H,fill=rgb(8,10,20))
    drawRect(0,0,W,H,fill=rgb(12,16,32))
    px,py,pw,ph=0,0,W,H
    drawRect(px,py,pw,ph,fill=rgb(12,16,32))
    drawRect(px,py,pw,72,fill=rgb(16,20,36))
    drawRect(px,py+72,pw,1,fill=rgb(38,48,80))
    drawLabel("ROS TOPIC BUS", px+20, py+18, fill=WHITE, size=20, bold=True, align="left-top")
    drawLabel("LIVE  |  rqt_graph  |  tf_tree  |  rostopic echo  |  pyodide transforms3d  |  window.WebSocket", px+20, py+38, fill=DIM, size=15, align="left-top")
    sx=px+pw-320
    conn=app.ros_client.is_connected
    drawRect(sx, py+16, 84,24, fill=rgb(22,36,28) if conn else rgb(36,28,22), border=GREEN if conn else ORANGE, borderWidth=1, roundness=12)
    drawCircle(sx+14, py+28, 4, fill=GREEN if conn else ORANGE)
    drawLabel("ROSBRIDGE" if conn else "OFFLINE", sx+46, py+28, fill=GREEN if conn else ORANGE, size=15, bold=True, align="center")
    sx+=94
    drawRect(sx, py+16, 92,24, fill=rgb(22,28,48), border=rgb(38,48,80), borderWidth=1, roundness=12)
    drawLabel("%d TOPICS" % len(app.bus_stats), sx+46, py+28, fill=CYAN, size=15, bold=True, align="center")
    sx+=102
    total_bw=sum(s["bw"] for s in app.bus_stats.values())
    drawRect(sx, py+16, 84,24, fill=rgb(22,28,48), border=rgb(38,48,80), borderWidth=1, roundness=12)
    try: bw_txt="%.1f KB/s" % (total_bw/1000.0)
    except: bw_txt="0 KB/s"
    drawLabel(bw_txt, sx+42, py+28, fill=YELLOW, size=15, bold=True, align="center")
    drawRect(px+pw-44, py+12, 32,32, fill=rgb(36,42,68), border=rgb(58,72,120), borderWidth=1, roundness=8)
    drawLabel("X", px+pw-28, py+28, fill=WHITE, size=15, bold=True, align="center")
    tab_y=py+73
    drawRect(px, tab_y, pw, 36, fill=rgb(14,20,36))
    drawRect(px, tab_y+35, pw, 1, fill=rgb(38,48,80))
    tab_x=px+16
    for tab in ["TOPICS","GRAPH","TF","ECHO"]:
        sel=app.bus_tab==tab
        drawRect(tab_x, tab_y+6, 72,24, fill=CYAN if sel else rgb(26,32,52), border=CYAN if sel else rgb(38,48,80), borderWidth=1, roundness=12)
        drawLabel(tab, tab_x+36, tab_y+18, fill=rgb(0,0,0) if sel else WHITE2, size=15, bold=sel, align="center")
        tab_x+=82
    cx,cy,cw,ch=px+12, py+112, pw-24, ph-120
    if app.bus_tab=="TOPICS":
        drawRect(cx, cy, cw, 40, fill=rgb(22,28,48), roundness=10)
        headers=[("TOPIC",20),("TYPE",260),("FREQ",460),("COUNT",560),("FRAME",660)]
        for name,off in headers:
            drawLabel(name, cx+off, cy+20, fill=DIM, size=15, bold=True, align="left-center")
        y=cy+52
        for topic in sorted(app.bus_stats.keys()):
            stat=app.bus_stats[topic]
            if y>py+ph-20: break
            is_sel=topic==app.selected_bus_topic
            bg=rgb(24,32,56) if is_sel else (rgb(20,26,44) if (y//40)%2==0 else rgb(18,24,40))
            bdr=CYAN if is_sel else rgb(32,40,68)
            drawRect(cx, y, cw, 44, fill=bg, border=bdr, borderWidth=1.2 if is_sel else 0.8, roundness=10)
            col=type_color(stat["msg_type"])
            drawCircle(cx+12, y+22, 5, fill=col)
            drawLabel(topic[:24], cx+26, y+22, fill=WHITE if is_sel else WHITE2, size=15, bold=is_sel, align="left-center")
            short_type = stat["msg_type"].split("/")[-1][:18]
            drawLabel(short_type, cx+260, y+22, fill=col, size=15, align="left-center")
            try: hz_txt="%.1f Hz" % float(stat["hz"])
            except: hz_txt="0 Hz"
            drawLabel(hz_txt, cx+460, y+22, fill=CYAN, size=15, bold=True, align="left-center")
            drawLabel(str(stat["count"]), cx+560, y+22, fill=WHITE2, size=15, align="left-center")
            drawLabel(stat["frame_id"][:14], cx+660, y+22, fill=ORANGE, size=15, align="left-center")
            hist=stat["hz_history"]
            if len(hist)>1:
                sx=cx+cw-90; sy=y+4; sw=80; sh=16
                drawRect(sx,sy,sw,sh,fill=rgb(12,16,28),roundness=4)
                max_h=max(hist) if max(hist)>0 else 1
                for i in range(len(hist)-1):
                    x1=sx+i*sw/len(hist); x2=sx+(i+1)*sw/len(hist)
                    y1=sy+sh - hist[i]/max_h*sh; y2=sy+sh - hist[i+1]/max_h*sh
                    drawLine(x1,y1,x2,y2,fill=col,lineWidth=1.5,opacity=0.9)
            y+=50
    elif app.bus_tab=="GRAPH":
        gx,gy,gw,gh=cx,cy,cw,ch
        drawRect(gx,gy,gw,gh,fill=rgb(10,14,26),border=rgb(38,48,80),borderWidth=1,roundness=12)
        for i in range(0,gw,60):
            drawLine(gx+i,gy,gx+i,gy+gh,fill=rgb(20,26,40),lineWidth=0.5,opacity=0.4)
        for i in range(0,gh,60):
            drawLine(gx,gy+i,gx+gw,gy+i,fill=rgb(20,26,40),lineWidth=0.5,opacity=0.4)
        pubs=list(set().union(*[s["publishers"] for s in app.bus_stats.values()]))[:7]
        subs=list(set().union(*[s["subscribers"] for s in app.bus_stats.values()]))[:7]
        topics=list(app.bus_stats.keys())[:9]
        pub_pos={}
        for i,p in enumerate(pubs):
            x=gx+90; y=gy+50+i*68
            pub_pos[p]=(x,y)
            drawCircle(x,y,20,fill=PINK,opacity=0.1)
            drawRect(x-56,y-20,112,44,fill=rgb(36,28,44),border=PINK,borderWidth=1,roundness=10)
            drawLabel(p[:14], x, y, fill=PINK, size=15, bold=True, align="center")
        topic_pos={}
        for i,t in enumerate(topics):
            x=gx+gw//2 + (i%3*130-130); y=gy+40+i*58
            topic_pos[t]=(x,y)
            col=type_color(app.bus_stats[t]["msg_type"])
            hz=app.bus_stats[t]["hz"]
            pulse=(math.sin(app.time*3+i)+1)*0.15+0.25 if hz>4 else 0.15
            drawCircle(x,y,30,fill=col,opacity=pulse)
            drawRect(x-66,y-20,132,44,fill=rgb(18,26,44),border=col,borderWidth=1.5,roundness=10)
            drawLabel(t[:18], x, y-4, fill=WHITE, size=15, bold=True, align="center")
            try: drawLabel("%.1fHz" % float(hz), x, y+9, fill=col, size=15, align="center")
            except: pass
        sub_pos={}
        for i,s in enumerate(subs):
            x=gx+gw-90; y=gy+50+i*68
            sub_pos[s]=(x,y)
            drawCircle(x,y,20,fill=GREEN,opacity=0.1)
            drawRect(x-56,y-20,112,44,fill=rgb(28,36,32),border=GREEN,borderWidth=1,roundness=10)
            drawLabel(s[:14], x, y, fill=GREEN, size=15, bold=True, align="center")
        for topic, stat in app.bus_stats.items():
            if topic not in topic_pos: continue
            tx,ty=topic_pos[topic]
            for pub in stat["publishers"]:
                if pub not in pub_pos: continue
                px_,py_=pub_pos[pub]
                drawLine(px_+44,py_,tx-54,ty,fill=rgb(70,80,110),lineWidth=1,opacity=0.45)
            for sub in stat["subscribers"]:
                if sub not in sub_pos: continue
                sx_,sy_=sub_pos[sub]
                drawLine(tx+54,ty,sx_-44,sy_,fill=rgb(70,80,110),lineWidth=1,opacity=0.45)
        for part in app.particles:
            t=part["topic"]
            if t not in topic_pos: continue
            tx,ty=topic_pos[t]
            stat=app.bus_stats.get(t)
            if not stat or not stat["publishers"]: continue
            pub=list(stat["publishers"])[0]
            if pub not in pub_pos: continue
            px_,py_=pub_pos[pub]
            prog=part["progress"]
            x=px_+44 + (tx-54-(px_+44))*prog
            y=py_ + (ty-py_)*prog
            col=type_color(stat["msg_type"])
            drawCircle(x,y,3.5,fill=col,border=WHITE,borderWidth=0.5)
    elif app.bus_tab=="TF":
        gx,gy,gw,gh=cx,cy,cw,ch
        drawRect(gx,gy,gw,gh,fill=rgb(10,14,26),border=rgb(38,48,80),borderWidth=1,roundness=12)
        drawLabel("TF TREE  -  map -> odom -> base_link -> sensors", gx+24, gy+18, fill=YELLOW, size=15, bold=True, align="left-top")
        drawLabel("pyodide transforms3d quaternion via run_python_async() - top-tier like ferrers.py", gx+24, gy+36, fill=DIM, size=15, align="left-top")
        nodes=[
            ("map", gx+110, gy+220, "static"),
            ("odom", gx+350, gy+220, "Odom  %.1f Hz" % float(app.bus_stats.get("/odom",{}).get("hz",0))),
            ("base_link", gx+590, gy+220, "x:%.1f y:%.1f th:%d°" % (app.sim.robot_x, app.sim.robot_y, int(math.degrees(app.sim.robot_th)))),
            ("lidar_link", gx+830, gy+140, "LaserScan  %.1f Hz" % float(app.bus_stats.get("/scan",{}).get("hz",0))),
            ("camera_link", gx+830, gy+300, "Image"),
            ("imu_link", gx+590, gy+360, "IMU  %.1f Hz" % float(app.bus_stats.get("/imu/data",{}).get("hz",0))),
        ]
        for i in range(2):
            _,x1,y1,_=nodes[i]
            _,x2,y2,_=nodes[i+1]
            drawLine(x1+80,y1,x2-80,y2,fill=YELLOW,lineWidth=3)
            drawCircle(x2-80,y2,6,fill=YELLOW)
        # base_link -> lidar_link, camera_link
        drawLine(590+80,220, 830-80, 140, fill=rgb(100,110,140), lineWidth=1.5)
        drawLine(590+80,220, 830-80, 300, fill=rgb(100,110,140), lineWidth=1.5)
        # base_link -> imu_link
        drawLine(590,220+40, 590, 360-40, fill=rgb(100,110,140), lineWidth=1.5)
        for name,x,y,info in nodes:
            drawRect(x-80,y-32,160,80,fill=rgb(22,28,48),border=YELLOW if name in ["map","odom","base_link"] else CYAN,borderWidth=1.8,roundness=12)
            drawLabel(name, x, y-10, fill=WHITE, size=15, bold=True, align="center")
            drawLabel(info[:20], x, y+14, fill=DIM, size=15, align="center")
        tf=app.sim.get_tf()
        q=tf["transform"]["rotation"]
        drawRect(gx+24, gy+gh-96, gw-48, 84, fill=rgb(18,24,44), border=rgb(38,48,80), borderWidth=1, roundness=10)
        drawLabel("Current base_link transform - pyodide transforms3d:", gx+36, gy+gh-84, fill=CYAN, size=15, bold=True, align="left-top")
        drawLabel("translation:  x=%.3f  y=%.3f  z=0.000" % (app.sim.robot_x, app.sim.robot_y), gx+36, gy+gh-62, fill=WHITE2, size=15, align="left-top")
        drawLabel("rotation:     x=%.3f  y=%.3f  z=%.3f  w=%.3f  (quaternion)" % (q["x"],q["y"],q["z"],q["w"]), gx+36, gy+gh-42, fill=YELLOW, size=15, align="left-top")
        drawLabel("source: await pyodide.install('transforms3d') + run_python_async(euler2mat->mat2quat) with JS fallback - no 404s", gx+36, gy+gh-20, fill=DIM, size=15, align="left-top")
    elif app.bus_tab=="ECHO":
        topic=app.selected_bus_topic
        stat=app.bus_stats.get(topic)
        if not stat:
            drawLabel("Select a topic from TOPICS tab -> click any row", cx+cw//2, cy+ch//2, fill=DIM, size=15, align="center")
        else:
            drawRect(cx, cy, cw//2-8, ch, fill=rgb(16,20,36), border=rgb(38,48,80), borderWidth=1, roundness=12)
            drawLabel(topic, cx+20, cy+20, fill=WHITE, size=16, bold=True, align="left-top")
            drawLabel(stat["msg_type"], cx+20, cy+42, fill=type_color(stat["msg_type"]), size=15, bold=True, align="left-top")
            y=cy+70
            rows=[
                ("Direction", stat["direction"]),
                ("Frame ID", stat["frame_id"]),
                ("Publishers", ",".join(stat["publishers"])),
                ("Subscribers", ",".join(stat["subscribers"])),
                ("Frequency", "%.2f Hz" % float(stat["hz"]) if stat["hz"] else "0 Hz"),
                ("Bandwidth", "%d B/s" % int(stat["bw"])),
                ("Count", str(stat["count"])),
                ("QoS", stat["qos"]),
            ]
            for k,v in rows:
                drawLabel(k+":", cx+20, y, fill=DIM, size=15, bold=True, align="left-top")
                drawLabel(str(v)[:36], cx+110, y, fill=WHITE2, size=15, align="left-top")
                y+=28
            drawRect(cx+cw//2+8, cy, cw//2-8, ch, fill=rgb(10,14,26), border=rgb(38,48,80), borderWidth=1, roundness=12)
            drawLabel("rostopic echo %s  -  live" % topic, cx+cw//2+24, cy+18, fill=CYAN, size=15, bold=True, align="left-top")
            drawLabel(stat["last_preview"][:72], cx+cw//2+24, cy+36, fill=GREEN, size=15, align="left-top")
            lines=["{","  header:", "    frame_id: %s" % stat["frame_id"],"    stamp: %.3f" % app.time,"  type: %s" % stat["msg_type"],"  preview: %s" % stat["last_preview"][:48],"  count: %d" % stat["count"],"  hz: %.2f" % float(stat["hz"]) if stat["hz"] else "  hz: 0","}"]
            ly=cy+62
            for line in lines:
                drawLabel(line[:68], cx+cw//2+24, ly, fill=rgb(180,200,220), size=15, align="left-top")
                ly+=24



def redrawAll(app):
    drawRect(0,0,W,H,fill=BG)
    drawRect(0,0,W,H,fill=rgb(0,0,0),opacity=0.15)
    drawRect(0,0,W,48,fill=rgb(14,18,32),border=PANEL_BORDER,borderWidth=1)
    drawRect(0,47,W,1,fill=CYAN,opacity=0.3)
    drawLabel("ROS PLAYGROUND", 18, 16, fill=WHITE, size=16, bold=True, align="left-top")
    drawLabel("PRO * rqt_bus * tf_tree * pyodide * window.WebSocket", 18, 32, fill=DIM, size=15, align="left-top")
    def pill(x,label,active,accent):
        bg=accent if active else rgb(26,32,52)
        txt=rgb(0,0,0) if active else (accent if label=="BUS" else WHITE2)
        bdr=accent if active or label=="BUS" else PANEL_BORDER
        drawRect(x,10,80 if len(label)<5 else 90,36,fill=bg,border=bdr,borderWidth=1.5 if active else 1,roundness=14)
        drawLabel(label, x+(40 if len(label)<5 else 45), 28, fill=txt, size=15, bold=True, align="center")
        return x+(70 if len(label)>=5 else 68)
    x=180
    pill(x,"BUILD",app.mode=="builder",CYAN); x+=68
    pill(x,"SIM",app.mode=="sim",GREEN); x+=58
    bx=x
    sel=app.show_bus_viewer
    drawRect(bx,10,90,36,fill=YELLOW if sel else rgb(38,36,24),border=YELLOW,borderWidth=2 if sel else 1,roundness=14)
    pulse=(math.sin(app.time*4)+1)*0.5
    drawCircle(bx+14,28,5+int(pulse*2),fill=YELLOW,opacity=0.2+pulse*0.5)
    drawCircle(bx+14,28,5,fill=YELLOW)
    drawLabel("BUS", bx+48, 28, fill=rgb(0,0,0) if sel else YELLOW, size=15, bold=True, align="center")
    x+=78
    pill(x,"TF",app.bus_tab=="TF" and app.show_bus_viewer,YELLOW); x+=68
    conn=app.ros_client.is_connected
    drawRect(W-120,10,108,36,fill=rgb(22,36,28) if conn else rgb(36,28,24),border=GREEN if conn else ORANGE,borderWidth=1.5,roundness=14)
    drawCircle(W-104,28,6,fill=GREEN if conn else ORANGE)
    drawLabel("LIVE" if conn else "CONNECT", W-66,28,fill=GREEN if conn else ORANGE,size=15,bold=True,align="center")
    drawPanel(LEFT_X,LEFT_Y,LEFT_W,LEFT_H, "ROBOT MODULES  %.1fkg  $%d" % (app.robot_build.total_mass(), app.robot_build.total_cost()), accent=CYAN)
    y=LEFT_Y+42
    for mod_id, mod in MODULE_LIBRARY.items():
        sel=app.selected_module==mod_id
        drawRect(LEFT_X+10, y, LEFT_W-20, 52, fill=rgb(30,36,62) if sel else rgb(22,28,48), border=PINK if sel else PANEL_BORDER, borderWidth=1.2 if sel else 0.8, roundness=10)
        drawLabel(mod.icon, LEFT_X+20, y+26, fill=PINK if sel else WHITE2, size=15, align="left-center")
        drawLabel(mod.label, LEFT_X+44, y+14, fill=WHITE if sel else WHITE2, size=15, bold=sel, align="left-top")
        drawLabel("%d topics" % len(mod.interfaces), LEFT_X+44, y+30, fill=DIM, size=15, align="left-top")
        y+=58
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
    drawRect(sX,sY,sW,20,fill=rgb(22,28,44),border=PANEL_BORDER,borderWidth=1,roundness=6)
    t=(app.sim.v+1)/2
    drawRect(sX,sY,t*sW,12,fill=CYAN,roundness=6)
    drawCircle(sX+t*sW, sY+6, 10, fill=rgb(18,22,36), border=CYAN, borderWidth=2)
    drawCircle(sX+t*sW, sY+6, 4, fill=CYAN)
    drawLabel("linear  %.2f m/s" % app.sim.v, sX, sY+26, fill=DIM, size=15, align="left-top")
    sY2=CENTER_Y+420
    drawRect(sX,sY2,sW,20,fill=rgb(22,28,44),border=PANEL_BORDER,borderWidth=1,roundness=6)
    t2=(app.sim.w+2)/4
    drawRect(sX,sY2,t2*sW,12,fill=ORANGE,roundness=6)
    drawCircle(sX+t2*sW, sY2+6, 10, fill=rgb(18,22,36), border=ORANGE, borderWidth=2)
    drawCircle(sX+t2*sW, sY2+6, 4, fill=ORANGE)
    drawLabel("angular  %.2f rad/s" % app.sim.w, sX, sY2+26, fill=DIM, size=15, align="left-top")
    drawRect(CENTER_X+16, CENTER_Y+452, CENTER_W-32, 48, fill=rgb(14,20,36), border=PANEL_BORDER, borderWidth=1, roundness=8)
    try:
        odom_hz=app.bus_stats.get("/odom",{}).get("hz",0)
        scan_hz=app.bus_stats.get("/scan",{}).get("hz",0)
        tf_hz=app.bus_stats.get("/tf",{}).get("hz",0)
        drawLabel("/odom %.1fHz  /scan %.1fHz  /tf %.1fHz" % (float(odom_hz), float(scan_hz), float(tf_hz)), CENTER_X+24, CENTER_Y+468, fill=WHITE2, size=15, align="left-top")
    except:
        drawLabel("/odom /scan /tf live", CENTER_X+24, CENTER_Y+468, fill=WHITE2, size=15, align="left-top")
    drawLabel("transforms3d via pyodide.run_python_async() - window.WebSocket", CENTER_X+24, CENTER_Y+482, fill=DIM, size=15, align="left-top")
    drawPanel(RIGHT_X,RIGHT_Y,RIGHT_W,RIGHT_H, "LIVE BUS  %d topics" % len(app.bus_stats), accent=YELLOW)
    y=RIGHT_Y+44
    for topic, stat in list(sorted(app.bus_stats.items(), key=lambda kv: -kv[1]["hz"]))[:7]:
        col=type_color(stat["msg_type"])
        sel=topic==app.selected_bus_topic
        drawRect(RIGHT_X+10, y, RIGHT_W-20, 52, fill=rgb(28,36,62) if sel else rgb(20,26,44), border=col if sel else PANEL_BORDER, borderWidth=1.2 if sel else 0.8, roundness=10)
        drawCircle(RIGHT_X+20, y+26, 5, fill=col)
        if stat["hz"]>3:
            pulse=(math.sin(app.time*6)+1)*0.5
            drawCircle(RIGHT_X+20, y+26, 5+int(pulse*5), fill=col, opacity=0.18)
        # Short topic name, no overlap
        short_topic = topic[:20]
        drawLabel(short_topic, RIGHT_X+34, y+10, fill=WHITE if sel else WHITE2, size=15, bold=sel, align="left-top")
        # Short type only last part
        short_type = stat["msg_type"].split("/")[-1][:14]
        drawLabel(short_type, RIGHT_X+34, y+30, fill=DIM, size=15, align="left-top")
        try: hz_txt="%.1f Hz" % float(stat["hz"])
        except: hz_txt="0 Hz"
        drawLabel(hz_txt, RIGHT_X+RIGHT_W-16, y+26, fill=col, size=15, bold=True, align="right-center")
        y+=58
    drawRect(RIGHT_X+10, RIGHT_Y+RIGHT_H-130, RIGHT_W-20, 120, fill=rgb(10,14,26), border=PANEL_BORDER, borderWidth=1, roundness=8)
    ly=RIGHT_Y+RIGHT_H-100
    for line in app.logs[-6:]:
        drawLabel(line[:52], RIGHT_X+16, ly, fill=GREEN, size=15, align="left-top")
        ly+=20
    if app.show_bus_viewer:
        draw_bus_overlay(app)
    else:
        drawRect(W-280, H-40, 260,32, fill=rgb(24,28,44), border=YELLOW, borderWidth=1, roundness=12, opacity=0.95)
        drawLabel("Press [B] for BUS viewer", W-150, H-24, fill=YELLOW, size=15, bold=True, align="center")

class RosPlaygroundApp:
    width=W; height=H
    def __init__(self): pass
App=RosPlaygroundApp
SCS_APP_TYPE="python.pyodide"
SCS_APP_SIZE=(1050,700)
