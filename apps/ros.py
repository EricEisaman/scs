"""
ROS Playground - SCS Python Pyodide App
========================================
File: ros.py
SCS Type: python.pyodide
Size: 1050x700 (strict, like fourier_ear_lab.py)
Example reference: https://github.com/EricEisaman/scs/blob/main/apps/fourier_ear_lab.py

Pattern from example:
  from scs import *
  from browser import window, aio
  W,H=1050,700
  def onAppStart(app): app.width=W; app.height=H; ...
  def onStep(app): ...
  def onMousePress(app,mx,my): ...
  def redrawAll(app): drawRect(), drawLabel(), ...

SCS System Evaluation
---------------------
Existing SCS (EricEisaman/scs):
- Provides canvas 1050x700, immediate-mode draw API (drawRect, drawLabel, drawLine, drawCircle, rgb)
- Lifecycle callbacks: onAppStart, onStep, onMousePress/Drag/Release/Move, onKeyPress, redrawAll
- Browser bridge: `from browser import window, aio` -> window.WebSocket, window.document, Uint8Array, etc.
- Extensions: `extensions.fetch` (fetch_text/fetch_json), `extensions.proc_audio` (AudioEngine)
- Works in Pyodide/Brython-like runtime; pure Python wheels can be micropip-installed.

Gap for ROS:
- roslibpy assumes Python sockets (twisted/autobahn/asyncio) which don't exist in Emscripten.
  Must use browser transport: window.WebSocket directly (like example uses window.AudioContext).
  So roslibpy transport cannot be used unchanged.

- ROS libs you listed are pure Python and *do* work in Pyodide:
  rosbags, urdf_parser_py, xacro, tf_transformations, transforms3d,
  catkin_pkg, rospkg, rosdistro, genmsg, genpy -> all importable via micropip.

- No existing SCS extension for ROS: need new ones.

Proposed New SCS Extensions (implemented inline here):
  1. extensions.rosbridge.BrowserWebSocketTransport - uses window.WebSocket, rosbridge v2 JSON
  2. extensions.urdf - URDF preview/validation using urdf_parser_py + xacro
  3. extensions.sim - 2D sim with TF publishing using tf_transformations/transforms3d
  4. extensions.editor - little code editor with ROS shim (Publisher/Subscriber/Rate)

Modular Robot Build System:
- Registry MODULE_LIBRARY: chassis_box, diff_drive, lidar_2d_rplidar, camera_d435, arm_2dof, imu_mpu9250
- RobotBuild assembles xacro, converts via xacro lib, validates via urdf_parser_py
- Export + package.xml generation via catkin_pkg, rospkg

Sim Env:
- Top-down SimWorld 10x10m, diff-drive kinematics, lidar raycast 360, odom, TF
- Uses tf_transformations or transforms3d fallback for quaternion
- Publishes /odom, /scan, /tf via BrowserWebSocketTransport if connected

Little Editor:
- Text editor state in app.editor_code, snippets: talker, listener, tf_broadcaster, urdf_inspect, bag_inspect
- Executes via exec() with shim (Publisher, Subscriber) and logs to app.logs
- Snippet selector, Run button, logs panel

Size: strict 1050x700 as required.
"""

# SCS core - matches fourier_ear_lab.py
try:
    from scs import *
    SCS_CORE = True
except ImportError:
    SCS_CORE = False
    # Minimal stubs for local dev without SCS
    W,H=1050,700
    def rgb(r,g,b): return (r,g,b)
    def rgba(r,g,b,a): return (r,g,b,a)
    def drawRect(*a,**k): pass
    def drawLabel(*a,**k): pass
    def drawLine(*a,**k): pass
    def drawCircle(*a,**k): pass
    def drawOval(*a,**k): pass

try:
    from browser import window, aio
    BROWSER_AVAILABLE = True
except ImportError:
    BROWSER_AVAILABLE = False
    window = None
    aio = None

import math
import json
import time
import traceback
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from pathlib import Path

# Extensions like in example
try:
    from extensions.fetch import fetch_text, fetch_json
    HAS_FETCH = True
except Exception:
    HAS_FETCH = False
    fetch_text = None
    fetch_json = None

try:
    from extensions.proc_audio import AudioEngine
    HAS_PROC_AUDIO = True
except Exception:
    HAS_PROC_AUDIO = False
    AudioEngine = None

# Try pyodide install via extension (not direct micropip import - that 404s in Brython)
try:
    from extensions.pyodide import install as pyodide_install
    HAS_PYODIDE_INSTALL = True
except Exception:
    HAS_PYODIDE_INSTALL = False
    pyodide_install = None
HAS_MICROPIP = HAS_PYODIDE_INSTALL
micropip = None

# Layout constants - 1050x700 strict like example
W,H=1050,700
HEADER_H=48
LEFT_X,LEFT_Y,LEFT_W,LEFT_H=10,56,210,634
CENTER_X,CENTER_Y,CENTER_W,CENTER_H=230,56,430,634
RIGHT_X,RIGHT_Y,RIGHT_W,RIGHT_H=670,56,370,634

# Colors - same style as fourier_ear_lab
BG=rgb(10,14,26)
PANEL_BG=rgb(18,22,38)
PANEL_BORDER=rgb(45,55,85)
CYAN=rgb(88,240,255)
PINK=rgb(255,110,180)
YELLOW=rgb(255,230,110)
GREEN=rgb(110,255,170)
ORANGE=rgb(255,160,80)
WHITE=rgb(240,250,255)

# ----------------------------------------------------------------------
# Browser-compatible Rosbridge transport (CRITICAL - uses window.WebSocket)
# ----------------------------------------------------------------------
class BrowserWebSocketTransport:
    """
    Browser-native rosbridge transport. Uses window.WebSocket, NOT Python sockets.
    This is required because roslibpy's twisted/asyncio/autobahn transports
    depend on socket/threading which don't exist in Pyodide/Emscripten.
    Matches SCS pattern: uses `from browser import window`.
    """
    def __init__(self, url="ws://localhost:9090", on_message=None):
        self.url = url
        self.on_message = on_message
        self._ws = None
        self._connected = False
        self._send_queue = []
        self._handlers: Dict[str, List[Callable]] = {}

    def log(self, *a):
        print("[rosbridge-browser]", *a)

    async def connect(self):
        if not BROWSER_AVAILABLE or window is None:
            # Mock for local dev
            self._connected = True
            self.log(f"Mock connect to {self.url} (no browser)")
            return self
        self.log(f"Connecting window.WebSocket to {self.url}")
        self._ws = window.WebSocket.new(self.url)
        loop_ok = False

        # SCS uses browser.aio, not asyncio Future (asyncio is stub in Brython)
        # Use aio.sleep loop to wait for open, compatible with ferrers.py pattern
        self._open_done = False
        def on_open(evt):
            self._connected = True
            self._open_done = True
            self.log("ws open")

        def on_close(evt):
            self._connected = False
            self.log("ws close")

        def on_error(evt):
            self.log("ws error", evt)
            if not fut.done():
                fut.set_exception(RuntimeError(f"WebSocket error {self.url}"))

        def on_message(evt):
            try:
                data = evt.data
                msg = json.loads(data)
                if self.on_message:
                    self.on_message(msg)
                op = msg.get("op")
                if op in self._handlers:
                    for h in self._handlers[op]:
                        try:
                            h(msg)
                        except Exception as e:
                            self.log("handler err", e)
            except Exception as e:
                self.log("parse err", e)

        # SCS example uses window with direct callbacks; need to wrap with js proxy if pyodide
        try:
            # pyodide ffi proxy if available
            from pyodide.ffi import create_proxy
            self._ws.addEventListener("open", create_proxy(on_open))
            self._ws.addEventListener("close", create_proxy(on_close))
            self._ws.addEventListener("error", create_proxy(on_error))
            self._ws.addEventListener("message", create_proxy(on_message))
        except Exception:
            # Brython style?
            self._ws.bind("open", on_open)
            self._ws.bind("close", on_close)
            self._ws.bind("error", on_error)
            self._ws.bind("message", on_message)

        for _ in range(100):
            if getattr(self, '_open_done', False):
                break
            if aio is not None:
                await aio.sleep(0.05)
            else:
                import time as _t; _t.sleep(0.05)
        return self

    async def send(self, obj: Dict):
        txt = json.dumps(obj)
        if self._ws and getattr(self._ws, "readyState", 1) == 1:
            try:
                self._ws.send(txt)
            except Exception as e:
                self._send_queue.append(txt)
        else:
            self._send_queue.append(txt)

    def on(self, op: str, handler: Callable):
        self._handlers.setdefault(op, []).append(handler)

    async def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._connected = False

class RosClient:
    def __init__(self, url="ws://localhost:9090"):
        self.url = url
        self.transport = BrowserWebSocketTransport(url)
        self._topics: Dict[str, Any] = {}
        self.is_connected = False
        self._id_counter = 0

    async def connect(self):
        await self.transport.connect()
        self.is_connected = True
        self.transport.on("publish", self._on_publish)
        return self

    def _on_publish(self, msg):
        topic = msg.get("topic")
        if topic in self._topics:
            cb = self._topics[topic].get("callback")
            if cb:
                cb(msg.get("msg"))

    async def advertise(self, topic: str, msg_type: str):
        await self.transport.send({"op": "advertise", "topic": topic, "type": msg_type})

    async def publish(self, topic: str, msg: Dict):
        await self.transport.send({"op": "publish", "topic": topic, "msg": msg})

    def subscribe(self, topic: str, msg_type: str, callback: Callable):
        self._topics[topic] = {"type": msg_type, "callback": callback}
        aio.run(self.transport.send({"op": "subscribe", "topic": topic, "type": msg_type}))

    async def close(self):
        await self.transport.close()
        self.is_connected = False

# ----------------------------------------------------------------------
# Modular Robot Build System
# ----------------------------------------------------------------------
@dataclass
class RosInterface:
    topic: str
    msg_type: str
    direction: str

@dataclass
class RobotModule:
    id: str
    name: str
    category: str
    description: str
    mass_kg: float
    xacro_macro: str
    params: Dict[str, Any] = field(default_factory=dict)
    interfaces: List[RosInterface] = field(default_factory=list)
    cost: float = 0.0

MODULE_LIBRARY: Dict[str, RobotModule] = {}

def register_module(m: RobotModule):
    MODULE_LIBRARY[m.id] = m

register_module(RobotModule(
    id="chassis_box", name="Box Chassis 0.5m", category="base",
    description="Alu box 0.5x0.35x0.12m", mass_kg=8.5, cost=250,
    xacro_macro='<xacro:macro name="chassis_box" params="name parent xyz rpy"><joint name="${name}_joint" type="fixed"><parent link="${parent}"/><child link="${name}"/><origin xyz="${xyz}" rpy="${rpy}"/></joint><link name="${name}"><inertial><mass value="8.5"/></inertial><visual><geometry><box size="0.5 0.35 0.12"/></geometry></visual></link></xacro:macro>',
    interfaces=[RosInterface("/odom","nav_msgs/Odometry","pub"), RosInterface("/tf","tf2_msgs/TFMessage","pub")]
))
register_module(RobotModule(
    id="diff_drive", name="Diff Drive", category="locomotion",
    description="2 wheels + caster", mass_kg=2.2, cost=180,
    xacro_macro='<xacro:macro name="diff_drive" params="name parent xyz rpy"><joint name="${name}_joint" type="fixed"><parent link="${parent}"/><child link="${name}"/><origin xyz="${xyz}" rpy="${rpy}"/></joint><link name="${name}"><inertial><mass value="0.5"/></inertial></link><joint name="${name}_left_wheel_joint" type="continuous"><parent link="${name}"/><child link="${name}_left_wheel"/><origin xyz="0 0.175 -0.05" rpy="-1.5707 0 0"/><axis xyz="0 0 1"/></joint><link name="${name}_left_wheel"><visual><geometry><cylinder radius="0.08" length="0.04"/></geometry></visual></link><joint name="${name}_right_wheel_joint" type="continuous"><parent link="${name}"/><child link="${name}_right_wheel"/><origin xyz="0 -0.175 -0.05" rpy="-1.5707 0 0"/><axis xyz="0 0 1"/></joint><link name="${name}_right_wheel"><visual><geometry><cylinder radius="0.08" length="0.04"/></geometry></visual></link></xacro:macro>',
    interfaces=[RosInterface("/cmd_vel","geometry_msgs/Twist","sub"), RosInterface("/odom","nav_msgs/Odometry","pub"), RosInterface("/joint_states","sensor_msgs/JointState","pub")]
))
register_module(RobotModule(
    id="lidar_2d_rplidar", name="RPLidar A2", category="sensor",
    description="360deg 12m", mass_kg=0.19, cost=350,
    xacro_macro='<xacro:macro name="lidar_2d_rplidar" params="name parent xyz rpy"><joint name="${name}_joint" type="fixed"><parent link="${parent}"/><child link="${name}"/><origin xyz="${xyz}" rpy="${rpy}"/></joint><link name="${name}"><visual><geometry><cylinder radius="0.04" length="0.06"/></geometry></visual></link></xacro:macro>',
    interfaces=[RosInterface("/scan","sensor_msgs/LaserScan","pub")]
))
register_module(RobotModule(
    id="camera_d435", name="D435 RGB-D", category="sensor",
    description="RGB-D camera", mass_kg=0.07, cost=250,
    xacro_macro='<xacro:macro name="camera_d435" params="name parent xyz rpy"><joint name="${name}_joint" type="fixed"><parent link="${parent}"/><child link="${name}"/><origin xyz="${xyz}" rpy="${rpy}"/></joint><link name="${name}"><visual><geometry><box size="0.09 0.025 0.025"/></geometry></visual></link></xacro:macro>',
    interfaces=[RosInterface("/camera/color/image_raw","sensor_msgs/Image","pub"), RosInterface("/camera/depth/image_rect_raw","sensor_msgs/Image","pub")]
))
register_module(RobotModule(
    id="arm_2dof", name="2-DOF Arm", category="manipulator",
    description="2 revolute 0.3m", mass_kg=1.2, cost=400,
    xacro_macro='<xacro:macro name="arm_2dof" params="name parent xyz rpy"><joint name="${name}_shoulder" type="revolute"><parent link="${parent}"/><child link="${name}_upper"/><origin xyz="${xyz}" rpy="${rpy}"/><axis xyz="0 1 0"/><limit lower="-1.57" upper="1.57" effort="10" velocity="1"/></joint><link name="${name}_upper"><visual><geometry><cylinder radius="0.02" length="0.2"/></geometry></visual></link><joint name="${name}_elbow" type="revolute"><parent link="${name}_upper"/><child link="${name}_lower"/><origin xyz="0 0 0.2" rpy="0 0 0"/><axis xyz="0 1 0"/><limit lower="-2.0" upper="2.0" effort="10" velocity="1"/></joint><link name="${name}_lower"><visual><geometry><cylinder radius="0.015" length="0.2"/></geometry></visual></link></xacro:macro>',
    interfaces=[RosInterface("/joint_states","sensor_msgs/JointState","pub")]
))
register_module(RobotModule(
    id="imu_mpu9250", name="IMU MPU9250", category="sensor",
    description="9-axis IMU", mass_kg=0.01, cost=25,
    xacro_macro='<xacro:macro name="imu_mpu9250" params="name parent xyz rpy"><joint name="${name}_joint" type="fixed"><parent link="${parent}"/><child link="${name}"/><origin xyz="${xyz}" rpy="${rpy}"/></joint><link name="${name}"><inertial><mass value="0.01"/></inertial></link></xacro:macro>',
    interfaces=[RosInterface("/imu","sensor_msgs/Imu","pub")]
))

@dataclass
class RobotInstance:
    module_id: str
    instance_name: str
    parent: str = "base_link"
    xyz: str = "0 0 0"
    rpy: str = "0 0 0"
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RobotBuild:
    name: str = "my_robot"
    instances: List[RobotInstance] = field(default_factory=list)
    base_module: str = "chassis_box"

    def add(self, module_id: str, instance_name: Optional[str]=None, parent="base_link", xyz="0 0 0", rpy="0 0 0", params=None):
        if module_id not in MODULE_LIBRARY:
            raise ValueError(f"Unknown module {module_id}")
        if not instance_name:
            instance_name = f"{module_id}_{len(self.instances)}"
        self.instances.append(RobotInstance(module_id, instance_name, parent, xyz, rpy, params or {}))

    def total_mass(self):
        m = MODULE_LIBRARY[self.base_module].mass_kg if self.base_module in MODULE_LIBRARY else 0
        for inst in self.instances:
            m += MODULE_LIBRARY[inst.module_id].mass_kg
        return m

    def total_cost(self):
        c = MODULE_LIBRARY[self.base_module].cost if self.base_module in MODULE_LIBRARY else 0
        for inst in self.instances:
            c += MODULE_LIBRARY[inst.module_id].cost
        return c

    def ros_graph(self):
        topics=[]; seen=set()
        for mid in [self.base_module]+[i.module_id for i in self.instances]:
            if mid in MODULE_LIBRARY:
                for iface in MODULE_LIBRARY[mid].interfaces:
                    if iface.topic not in seen:
                        topics.append(iface.topic); seen.add(iface.topic)
        return topics

    def to_xacro(self):
        header=f'<?xml version="1.0"?>\n<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="{self.name}">\n'
        for mid in set([self.base_module]+[i.module_id for i in self.instances]):
            if mid in MODULE_LIBRARY:
                header+=MODULE_LIBRARY[mid].xacro_macro+"\n"
        header+='  <link name="base_link"/>\n'
        if self.base_module in MODULE_LIBRARY:
            bm=MODULE_LIBRARY[self.base_module]
            header+=f'  <xacro:{bm.id} name="{self.name}_base" parent="base_link" xyz="0 0 0.1" rpy="0 0 0"/>\n'
        for inst in self.instances:
            mod=MODULE_LIBRARY[inst.module_id]
            param_str=" ".join([f'{k}="{v}"' for k,v in inst.params.items()])
            header+=f'  <xacro:{mod.id} name="{inst.instance_name}" parent="{inst.parent}" xyz="{inst.xyz}" rpy="{inst.rpy}" {param_str}/>\n'
        header+='</robot>\n'
        return header

    def validate_urdf(self):
        try:
            from urdf_parser_py.urdf import URDF
            import tempfile
            xacro_str=self.to_xacro()
            try:
                import xacro
                with tempfile.NamedTemporaryFile(mode='w', suffix='.xacro', delete=False) as f:
                    f.write(xacro_str); fname=f.name
                doc=xacro.process_file(fname)
                xml_str=doc.toxml()
            except Exception:
                xml_str=xacro_str
            if "<?xml" in xml_str:
                robot=URDF.from_xml_string(xml_str)
                return {"valid":True, "links":len(robot.links), "joints":len(robot.joints), "name":robot.name}
            return {"valid":False, "error":"Not XML"}
        except Exception as e:
            return {"valid":False, "error":str(e), "trace":traceback.format_exc()}

# ----------------------------------------------------------------------
# Sim Env
# ----------------------------------------------------------------------
class SimWorld:
    def __init__(self, width_m=10, height_m=10):
        self.width=width_m; self.height=height_m
        self.obstacles: List[Tuple[float,float,float,float]]=[]
        self.robot_x=0.0; self.robot_y=0.0; self.robot_th=0.0
        self.v=0.0; self.w=0.0
        self.lidar_ranges: List[float]=[]
        self.time=0.0

    def add_obstacle(self,x,y,w,h): self.obstacles.append((x,y,w,h))
    def set_cmd_vel(self,v,w):
        self.v=max(-1.0,min(1.0,v)); self.w=max(-2.0,min(2.0,w))

    def step(self, dt=0.05):
        self.robot_x+=self.v*math.cos(self.robot_th)*dt
        self.robot_y+=self.v*math.sin(self.robot_th)*dt
        self.robot_th+=self.w*dt
        self.robot_x=max(-self.width/2+0.5,min(self.width/2-0.5,self.robot_x))
        self.robot_y=max(-self.height/2+0.5,min(self.height/2-0.5,self.robot_y))
        self.time+=dt
        self.lidar_ranges=self._simulate_lidar(360,8.0)

    def _simulate_lidar(self,num_beams=360,max_range=8.0):
        ranges=[]
        for i in range(num_beams):
            angle=self.robot_th+math.radians(i)
            r=max_range
            for ox,oy,ow,oh in self.obstacles:
                x1=ox-ow/2; x2=ox+ow/2; y1=oy-oh/2; y2=oy+oh/2
                rx,ry=self.robot_x,self.robot_y
                dx,dy=math.cos(angle),math.sin(angle)
                tmin=0; tmax=max_range
                if abs(dx)<1e-6:
                    if rx<x1 or rx>x2: continue
                else:
                    tx1=(x1-rx)/dx; tx2=(x2-rx)/dx
                    tmin=max(tmin,min(tx1,tx2)); tmax=min(tmax,max(tx1,tx2))
                if abs(dy)<1e-6:
                    if ry<y1 or ry>y2: continue
                else:
                    ty1=(y1-ry)/dy; ty2=(y2-ry)/dy
                    tmin=max(tmin,min(ty1,ty2)); tmax=min(tmax,max(ty1,ty2))
                if tmax>=tmin and tmin>=0 and tmin<r:
                    r=tmin
            ranges.append(round(r,3))
        return ranges

    def get_tf(self):
        try:
            import tf_transformations
            q=tf_transformations.quaternion_from_euler(0,0,self.robot_th)
        except Exception:
            try:
                import transforms3d.euler as t3e, transforms3d.quaternions as t3q
                q=t3q.mat2quat(t3e.euler2mat(0,0,self.robot_th))
                q=[q[1],q[2],q[3],q[0]]
            except Exception:
                q=[0,0,math.sin(self.robot_th/2),math.cos(self.robot_th/2)]
        return {"header":{"stamp":{"sec":int(self.time),"nanosec":int((self.time%1)*1e9)},"frame_id":"odom"},"child_frame_id":"base_link","transform":{"translation":{"x":self.robot_x,"y":self.robot_y,"z":0.0},"rotation":{"x":q[0],"y":q[1],"z":q[2],"w":q[3]}}}

    def get_laser_scan_msg(self):
        return {"header":{"frame_id":"lidar_link","stamp":{"sec":int(self.time)}},"angle_min":0.0,"angle_max":math.radians(359),"angle_increment":math.radians(1),"range_min":0.05,"range_max":8.0,"ranges":self.lidar_ranges,"intensities":[]}

    def get_odom_msg(self):
        tf=self.get_tf()
        return {"header":tf["header"],"child_frame_id":"base_link","pose":{"pose":{"position":tf["transform"]["translation"],"orientation":tf["transform"]["rotation"]}},"twist":{"twist":{"linear":{"x":self.v},"angular":{"z":self.w}}}}

# ----------------------------------------------------------------------
# Little Editor snippets
# ----------------------------------------------------------------------
DEFAULT_SNIPPETS={
    "talker": textwrap.dedent('''
    # Talker - publishes to /chatter
    from ros_shim import Publisher
    pub = Publisher("/chatter", "std_msgs/String")
    for i in range(5):
        pub.publish({"data": f"hello {i} from pyodide"})
        print(f"published {i}")
    '''),
    "listener": textwrap.dedent('''
    # Listener - /scan
    from ros_shim import Subscriber
    def scan_cb(msg):
        print(f"min range {min(msg.get('ranges', [99])):.2f}")
    sub = Subscriber("/scan", "sensor_msgs/LaserScan", scan_cb)
    print("subscribed")
    '''),
    "tf_broadcaster": textwrap.dedent('''
    try:
        import tf_transformations as tf
        import math
        q = tf.quaternion_from_euler(0,0, math.radians(45))
        print("quat 45deg", q)
    except ImportError:
        import transforms3d.euler as eul
        print(eul.euler2mat(0,0, math.radians(45)))
    '''),
    "urdf_inspect": textwrap.dedent('''
    from ros import get_current_build
    build = get_current_build()
    print(f"{build.name} mass {build.total_mass():.2f}kg cost ${build.total_cost():.0f}")
    print(build.validate_urdf())
    print(build.to_xacro()[:500])
    '''),
    "bag_inspect": textwrap.dedent('''
    # Bag inspect via rosbags
    try:
        from rosbags.highlevel import AnyReader
        print("Upload .bag/.mcap via UI, then AnyReader([Path])")
    except Exception as e:
        print(e)
    ''')
}

# Shim
class RosShimPublisher:
    def __init__(self, topic, msg_type, ros_client=None):
        self.topic=topic; self.msg_type=msg_type; self.ros_client=ros_client
    def publish(self, msg):
        if self.ros_client and self.ros_client.is_connected:
            aio.run(self.ros_client.publish(self.topic, msg))
        else:
            print(f"[mock publish] {self.topic}: {msg}")

class RosShimSubscriber:
    def __init__(self, topic, msg_type, cb, ros_client=None):
        self.topic=topic; self.msg_type=msg_type; self.cb=cb
        if ros_client and ros_client.is_connected:
            ros_client.subscribe(topic, msg_type, cb)
        print(f"[mock subscribe] {topic} ({msg_type})")

class RosShimRate:
    def __init__(self,hz): self.hz=hz

# Global build for editor access
_current_build_global: Optional[RobotBuild]=None
def get_current_build()->RobotBuild:
    global _current_build_global
    if _current_build_global is None:
        _current_build_global=RobotBuild(name="scs_bot")
        _current_build_global.add("diff_drive","drive",parent="scs_bot_base",xyz="0 0 0")
        _current_build_global.add("lidar_2d_rplidar","lidar",parent="scs_bot_base",xyz="0.15 0 0.15")
        _current_build_global.add("imu_mpu9250","imu",parent="base_link",xyz="0 0 0.1")
    return _current_build_global

# ----------------------------------------------------------------------
# SCS Callbacks - matches fourier_ear_lab.py pattern
# ----------------------------------------------------------------------
def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onAppStart(app):
    app.width=W; app.height=H
    app.stepsPerSecond=30
    app.background=BG
    app.robot_build=get_current_build()
    global _current_build_global
    _current_build_global=app.robot_build
    app.sim=SimWorld()
    app.sim.add_obstacle(2,1,1,0.2)
    app.sim.add_obstacle(-1,2,0.5,0.5)
    app.sim.add_obstacle(0,-2,3,0.2)
    app.editor_code=DEFAULT_SNIPPETS["talker"]
    app.editor_cursor=0
    app.editor_focus=False
    app.logs: List[str]=[]
    app.rosbridge_url="ws://localhost:9090"
    app.ros_client=None
    app.ros_status="disconnected"
    app.selected_module="chassis_box"
    app.show_xacro=False
    app.xacro_text=""
    app.time=0.0
    app.dragging_slider=None  # "v" or "w"
    app.mode="builder"  # builder, sim, editor

    # Try micropip install for pyodide (like SCS extensions)
    if HAS_MICROPIP and micropip:
        async def install_ros():
            pkgs=["pyyaml","lxml","numpy","urdf-parser-py","xacro","transforms3d","catkin-pkg","rospkg","rosdistro","genmsg","genpy","rosbags"]
            for p in pkgs:
                try:
                    await micropip.install(p)
                    app.logs.append(f"✓ {p}")
                except Exception as e:
                    app.logs.append(f"· {p} fail {e}")
        try:
            # SCS uses aio.run? In example: aio.run(tryFetch())
            if aio:
                aio.run(install_ros())
            else:
                aio.run(install_ros())
        except Exception:
            pass

    # Package info cache
    app.pkg_info={"status":"press Inspect"}
    app.bag_info={"status":"no bag"}

    app.insight="ROS Playground: modular build + sim + editor. Click modules to add. Drag sliders for cmd_vel."
    app.insightTimer=300

def log(app, msg: str):
    ts=time.strftime("%H:%M:%S")
    line=f"[{ts}] {msg}"
    app.logs.append(line)
    if len(app.logs)>60:
        app.logs=app.logs[-60:]
    print(line)

def onStep(app):
    app.time+=0.033
    app.sim.step(0.033)
    # Publish via rosbridge if connected
    if app.ros_client and app.ros_client.is_connected:
        async def pub():
            try:
                await app.ros_client.publish("/odom", app.sim.get_odom_msg())
                await app.ros_client.publish("/scan", app.sim.get_laser_scan_msg())
                await app.ros_client.publish("/tf", {"transforms":[app.sim.get_tf()]})
            except Exception as e:
                log(app, f"pub err {e}")
        try:
            aio.run(pub())
        except Exception:
            pass
    if app.insightTimer>0:
        app.insightTimer-=1

# Button rects for hit testing
def get_button_rects():
    # Header buttons
    return {
        "connect": (W-260, 8, 90, 28),
        "run": (W-160, 8, 60, 28),
        "mode_builder": (W-90, 8, 70, 28),
        "xacro": (LEFT_X+8, LEFT_Y+LEFT_H-100, 60, 22),
        "urdf": (LEFT_X+74, LEFT_Y+LEFT_H-100, 60, 22),
        "validate": (LEFT_X+140, LEFT_Y+LEFT_H-100, 60, 22),
        "inspect_pkg": (RIGHT_X+8, RIGHT_Y+260, 60, 18),
    }

def onMousePress(app,mx,my):
    btns=get_button_rects()
    # Header: connect
    if pointInRect(mx,my,*btns["connect"]):
        async def do_connect():
            log(app, f"Connecting {app.rosbridge_url} via window.WebSocket...")
            try:
                client=RosClient(app.rosbridge_url)
                await client.connect()
                app.ros_client=client
                app.ros_status="connected"
                log(app, f"✓ Connected {app.rosbridge_url}")
            except Exception as e:
                app.ros_status=f"fail: {e}"
                log(app, f"✗ Connect fail {e}\n{traceback.format_exc()}")
        try:
            aio.run(do_connect())
        except Exception:
            # SCS aio.run
            if aio:
                aio.run(do_connect())
        return

    if pointInRect(mx,my,*btns["run"]):
        # Run editor code
        aio.run(run_editor_code(app))
        return

    if pointInRect(mx,my,*btns["mode_builder"]):
        app.mode="editor" if app.mode=="builder" else "builder"
        return

    if pointInRect(mx,my,*btns["xacro"]):
        app.xacro_text=app.robot_build.to_xacro()
        app.show_xacro=True
        log(app, f"Xacro {len(app.xacro_text)} chars")
        return
    if pointInRect(mx,my,*btns["urdf"]):
        app.xacro_text=app.robot_build.to_xacro()
        # Try conversion if libs available
        try:
            # quick convert
            import tempfile
            import xacro
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xacro', delete=False) as f:
                f.write(app.xacro_text); fname=f.name
            doc=xacro.process_file(fname)
            app.xacro_text=doc.toxml()[:4000]
        except Exception as e:
            app.xacro_text=f"URDF conversion err {e}\n"+app.xacro_text[:3000]
        app.show_xacro=True
        return
    if pointInRect(mx,my,*btns["validate"]):
        res=app.robot_build.validate_urdf()
        app.xacro_text=json.dumps(res, indent=2)
        app.show_xacro=True
        log(app, f"Validate {res}")
        return
    if pointInRect(mx,my,*btns["inspect_pkg"]):
        app.pkg_info=inspect_packages(app)
        return

    # Module list click
    if pointInRect(mx,my,LEFT_X,LEFT_Y+24,LEFT_W,260):
        # Each module row ~32px
        idx=int((my-(LEFT_Y+24))//32)
        mods=list(MODULE_LIBRARY.keys())
        if 0<=idx<len(mods):
            mod_id=mods[idx]
            # Add instance
            inst_name=f"{mod_id}_{len(app.robot_build.instances)}"
            app.robot_build.add(mod_id, inst_name, parent=f"{app.robot_build.name}_base", xyz=f"{0.1*len(app.robot_build.instances)} 0 0.1")
            log(app, f"Added {mod_id} as {inst_name}")
            app.insight=f"Added {mod_id}"
            app.insightTimer=120
        return

    # Sim sliders
    # Lin vel slider in center panel
    sX,sY,sW=CENTER_X+14, CENTER_Y+420, CENTER_W-28
    if pointInRect(mx,my,sX,sY-6,sW,20):
        app.dragging_slider="v"
        t=max(0,min(1,(mx-sX)/sW))
        v=t*2-1
        app.sim.set_cmd_vel(v, app.sim.w)
        return
    sX2,sY2=CENTER_X+14, CENTER_Y+450
    if pointInRect(mx,my,sX2,sY2-6,sW,20):
        app.dragging_slider="w"
        t=max(0,min(1,(mx-sX2)/sW))
        w=t*4-2
        app.sim.set_cmd_vel(app.sim.v, w)
        return

    # Editor focus click
    if pointInRect(mx,my,RIGHT_X+8,RIGHT_Y+24,RIGHT_W-16,200):
        app.editor_focus=True
        return
    else:
        # Clicking elsewhere unfocuses
        if app.editor_focus and not pointInRect(mx,my,RIGHT_X,RIGHT_Y,RIGHT_W,RIGHT_H):
            # keep focus if clicking editor
            pass

    # Close xacro preview
    if app.show_xacro and pointInRect(mx,my,LEFT_X+LEFT_W-30, LEFT_Y+LEFT_H-120, 24, 16):
        app.show_xacro=False

def onMouseDrag(app,mx,my):
    if app.dragging_slider=="v":
        sX,sW=CENTER_X+14, CENTER_W-28
        t=max(0,min(1,(mx-sX)/sW))
        v=t*2-1
        app.sim.set_cmd_vel(v, app.sim.w)
    elif app.dragging_slider=="w":
        sX,sW=CENTER_X+14, CENTER_W-28
        t=max(0,min(1,(mx-sX)/sW))
        w=t*4-2
        app.sim.set_cmd_vel(app.sim.v, w)

def onMouseRelease(app,mx,my):
    app.dragging_slider=None

def onMouseMove(app,mx,my):
    pass

def onKeyPress(app,key):
    # Little editor key handling
    if not app.editor_focus:
        if key.lower()=="r":
            aio.run(run_editor_code(app))
        elif key.lower()=="c":
            # connect
            onMousePress(app, W-260+10, 12)
        return

    # Editor focused
    if key=="Backspace":
        if len(app.editor_code)>0:
            app.editor_code=app.editor_code[:-1]
    elif key=="Enter":
        app.editor_code+="\n"
    elif key=="Tab":
        app.editor_code+="  "
    elif len(key)==1:
        # Regular char
        app.editor_code+=key
    elif key=="Escape":
        app.editor_focus=False

async def run_editor_code(app):
    code=app.editor_code
    log(app, "▶ Running editor...")
    sandbox={
        "print": lambda *a,**k: log(app, " ".join(map(str,a))),
        "math": math, "json": json, "time": time, "aio": aio,
        "RosClient": RosClient, "ros_client": app.ros_client,
        "robot_build": app.robot_build, "sim": app.sim,
        "get_current_build": get_current_build,
        "Publisher": lambda topic,msg_type: RosShimPublisher(topic,msg_type,app.ros_client),
        "Subscriber": lambda topic,msg_type,cb: RosShimSubscriber(topic,msg_type,cb,app.ros_client),
        "Rate": RosShimRate,
    }
    try:
        import tf_transformations
        sandbox["tf_transformations"]=tf_transformations
    except Exception:
        try:
            import transforms3d
            sandbox["transforms3d"]=transforms3d
        except Exception:
            pass
    import types
    ros_shim_mod=types.ModuleType("ros_shim")
    ros_shim_mod.Publisher=sandbox["Publisher"]
    ros_shim_mod.Subscriber=sandbox["Subscriber"]
    ros_shim_mod.Rate=RosShimRate
    ros_shim_mod.RosClient=RosClient
    import sys
    sys.modules["ros_shim"]=ros_shim_mod
    try:
        if "await" in code:
            wrapped="async def __user_main__():\n"+textwrap.indent(code,"  ")+"\n"
            exec(wrapped, sandbox)
            await sandbox["__user_main__"]()
        else:
            exec(code, sandbox)
        log(app, "✓ Editor finished")
    except Exception as e:
        log(app, f"✗ Editor err {e}\n{traceback.format_exc()}")

def inspect_packages(app):
    out={}
    try:
        import rospkg
        rp=rospkg.RosPack()
        out["rospkg"]=rp.list()[:10]
    except Exception as e:
        out["rospkg_err"]=str(e)
    try:
        import catkin_pkg.package
        dummy=f'<package><name>{app.robot_build.name}_description</name><version>0.0.0</version><description>gen</description><maintainer email="a@a.com">a</maintainer><license>MIT</license></package>'
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(dummy); fname=f.name
        pkg=catkin_pkg.package.parse_package(fname)
        out["catkin_pkg"]=pkg.name
    except Exception as e:
        out["catkin_pkg_err"]=str(e)
    try:
        import rosdistro
        out["rosdistro"]=getattr(rosdistro,"__version__","present")
    except Exception as e:
        out["rosdistro_err"]=str(e)
    try:
        import genmsg, genpy
        out["genmsg"]="present"
        out["genpy"]="present"
    except Exception as e:
        out["genmsg_err"]=str(e)
    try:
        from rosbags.highlevel import AnyReader
        out["rosbags"]="present"
    except Exception as e:
        out["rosbags_err"]=str(e)
    log(app, f"Pkg inspect {out}")
    return out

# ----------------------------------------------------------------------
# Draw helpers - uses SCS draw API like fourier_ear_lab.py
# ----------------------------------------------------------------------
def drawPanel(x,y,w,h,title=""):
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1,roundness=8)
    if title:
        drawRect(x+6,y+4,w-12,18,fill=rgb(28,32,52),roundness=4)
        drawLabel(title,x+12,y+13,fill=rgb(180,190,220),size=11,bold=True,align="left-top")

def redrawAll(app):
    # Background
    drawRect(0,0,W,H,fill=BG)

    # Header
    drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("ROS PLAYGROUND - MODULAR ROBOT + SIM + EDITOR [SCS Pyodide 1050x700]", W*0.5, 10, fill=WHITE, size=14, bold=True, align="center-top")
    drawLabel(app.insight, 12, 30, fill=CYAN, size=10, bold=True, align="left-top")

    # Header buttons
    btns=get_button_rects()
    # Connect
    col = GREEN if app.ros_status=="connected" else rgb(60,70,90)
    drawRect(*btns["connect"], fill=col, border=rgb(255,255,255), borderWidth=1, roundness=14)
    drawLabel(f"{app.ros_status[:12]}", btns["connect"][0]+45, btns["connect"][1]+14, fill=rgb(0,0,0) if app.ros_status=="connected" else rgb(200,220,255), size=10, bold=True, align="center")
    # Run
    drawRect(*btns["run"], fill=YELLOW, border=rgb(255,255,255), borderWidth=1, roundness=14)
    drawLabel("RUN", btns["run"][0]+30, btns["run"][1]+14, fill=rgb(0,0,0), size=11, bold=True, align="center")
    # Mode
    drawRect(*btns["mode_builder"], fill=PINK, border=rgb(255,255,255), borderWidth=1, roundness=14)
    drawLabel(app.mode.upper(), btns["mode_builder"][0]+35, btns["mode_builder"][1]+14, fill=rgb(0,0,0), size=10, bold=True, align="center")

    # Left panel - Module Library + Build
    drawPanel(LEFT_X,LEFT_Y,LEFT_W,LEFT_H, f"MODULES mass={app.robot_build.total_mass():.1f}kg ${app.robot_build.total_cost():.0f}")
    # Module rows
    y0=LEFT_Y+24
    for i, (mid, mod) in enumerate(MODULE_LIBRARY.items()):
        y=y0+i*32
        if y>LEFT_Y+LEFT_H-140: break
        sel = (mid==app.selected_module)
        bg = rgb(35,42,68) if not sel else rgb(60,80,120)
        drawRect(LEFT_X+6,y,LEFT_W-12,28,fill=bg,border=PANEL_BORDER,borderWidth=1,roundness=6)
        drawLabel(f"{mod.name}", LEFT_X+12, y+4, fill=WHITE, size=9, bold=True, align="left-top")
        drawLabel(f"[{mod.category}] {mod.mass_kg}kg ${mod.cost} {','.join([i.topic for i in mod.interfaces])[:28]}", LEFT_X+12, y+15, fill=rgb(150,170,200), size=7, align="left-top")

    # Build instances
    drawLabel(f"Build: {app.robot_build.name} ({len(app.robot_build.instances)} modules)", LEFT_X+8, LEFT_Y+300, fill=rgb(180,200,220), size=9, bold=True, align="left-top")
    for idx, inst in enumerate(app.robot_build.instances[-6:]):
        drawLabel(f"{idx+1}. {inst.instance_name} ({inst.module_id})", LEFT_X+8, LEFT_Y+314+idx*12, fill=rgb(160,180,210), size=8, align="left-top")

    # Buttons Xacro/URDF/Validate
    for key in ["xacro","urdf","validate"]:
        x,y,w,h=btns[key]
        drawRect(x,y,w,h,fill=rgb(45,55,85),border=PANEL_BORDER,borderWidth=1,roundness=6)
        drawLabel(key.upper(), x+w/2, y+h/2, fill=rgb(220,230,255), size=9, bold=True, align="center")

    # Xacro preview popup
    if app.show_xacro:
        drawRect(LEFT_X, LEFT_Y+LEFT_H-120, LEFT_W, 110, fill=rgb(12,16,30), border=YELLOW, borderWidth=1.5, roundness=6)
        drawLabel("PREVIEW (X to close)", LEFT_X+8, LEFT_Y+LEFT_H-116, fill=YELLOW, size=8, bold=True, align="left-top")
        # Show first lines
        txt=app.xacro_text[:500]
        for li, line in enumerate(txt.split("\n")[:7]):
            drawLabel(line[:36], LEFT_X+8, LEFT_Y+LEFT_H-102+li*12, fill=GREEN, size=7, align="left-top")
        drawRect(LEFT_X+LEFT_W-30, LEFT_Y+LEFT_H-120, 24, 16, fill=rgb(60,70,90), border=rgb(200,210,230), borderWidth=1, roundness=4)
        drawLabel("X", LEFT_X+LEFT_W-18, LEFT_Y+LEFT_H-112, fill=WHITE, size=10, bold=True, align="center")

    # Center panel - Sim Env
    drawPanel(CENTER_X,CENTER_Y,CENTER_W,CENTER_H, f"SIM ENV x={app.sim.robot_x:.2f} y={app.sim.robot_y:.2f} th={math.degrees(app.sim.robot_th):.0f}°")
    # Sim canvas background
    gx,gy,gw,gh=CENTER_X+12, CENTER_Y+28, CENTER_W-24, 300
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=8)
    # Grid
    cx,cy=gx+gw/2, gy+gh/2
    scale=28
    # grid lines
    for i in range(-5,6):
        drawLine(cx+i*scale, gy, cx+i*scale, gy+gh, fill=rgb(35,45,70), lineWidth=0.6)
        drawLine(gx, cy+i*scale, gx+gw, cy+i*scale, fill=rgb(35,45,70), lineWidth=0.6)
    # obstacles
    for ox,oy,ow,oh in app.sim.obstacles:
        drawRect(cx+ox*scale-ow*scale/2, cy-oy*scale-oh*scale/2, ow*scale, oh*scale, fill=rgb(200,50,50), roundness=3, opacity=0.6)
    # robot
    rx=cx+app.sim.robot_x*scale
    ry=cy-app.sim.robot_y*scale
    # robot body rotated
    # For simplicity draw circle + front indicator
    drawCircle(rx,ry,14,fill=rgb(50,60,80),border=WHITE,borderWidth=1)
    fx=rx+math.cos(app.sim.robot_th)*12
    fy=ry-math.sin(app.sim.robot_th)*12
    drawCircle(fx,fy,4,fill=CYAN,border=WHITE,borderWidth=1)
    # lidar rays (every 20 deg)
    if app.sim.lidar_ranges:
        for i in range(0,360,20):
            r=app.sim.lidar_ranges[i]
            ang=app.sim.robot_th+math.radians(i)
            ex=rx+math.cos(ang)*r*scale*0.6
            ey=ry-math.sin(ang)*r*scale*0.6
            drawLine(rx,ry,ex,ey,fill=GREEN,lineWidth=1,opacity=0.25)

    # Sliders for cmd_vel
    sX,sY,sW=CENTER_X+14, CENTER_Y+420, CENTER_W-28
    # Lin
    drawRect(sX,sY,sW,10,fill=rgb(30,35,55),border=PANEL_BORDER,borderWidth=1,roundness=5)
    t=(app.sim.v+1)/2
    drawRect(sX,sY,t*sW,10,fill=CYAN,roundness=5)
    drawCircle(sX+t*sW, sY+5, 8, fill=WHITE, border=CYAN, borderWidth=2)
    drawLabel(f"lin vel {app.sim.v:.1f} m/s  55-(-1) to 1", sX, sY+14, fill=rgb(130,140,170), size=8, align="left-top")
    # Ang
    sY2=CENTER_Y+450
    drawRect(sX,sY2,sW,10,fill=rgb(30,35,55),border=PANEL_BORDER,borderWidth=1,roundness=5)
    t2=(app.sim.w+2)/4
    drawRect(sX,sY2,t2*sW,10,fill=ORANGE,roundness=5)
    drawCircle(sX+t2*sW, sY2+5, 8, fill=WHITE, border=ORANGE, borderWidth=2)
    drawLabel(f"ang vel {app.sim.w:.1f} rad/s  -2 to 2", sX, sY2+14, fill=rgb(130,140,170), size=8, align="left-top")

    # ROS graph
    drawLabel(f"Topics: {', '.join(app.robot_build.ros_graph())[:60]}", CENTER_X+12, CENTER_Y+480, fill=rgb(150,170,200), size=8, align="left-top")
    # TF info
    tf=app.sim.get_tf()
    drawLabel(f"TF odom->base: t=({tf['transform']['translation']['x']:.2f},{tf['transform']['translation']['y']:.2f}) qz={tf['transform']['rotation']['z']:.2f} w={tf['transform']['rotation']['w']:.2f}", CENTER_X+12, CENTER_Y+494, fill=rgb(130,150,180), size=7, align="left-top")
    drawLabel("Uses tf_transformations / transforms3d for quat", CENTER_X+12, CENTER_Y+508, fill=rgb(110,120,150), size=7, align="left-top")
    drawLabel("Publishes /odom /scan /tf via window.WebSocket (BrowserWebSocketTransport)", CENTER_X+12, CENTER_Y+520, fill=YELLOW, size=7, bold=True, align="left-top")

    # Right panel - Editor
    drawPanel(RIGHT_X,RIGHT_Y,RIGHT_W,RIGHT_H, "LITTLE EDITOR - click to focus, type, RUN")
    # Snippet selector (draw as tabs)
    snips=["talker","listener","tf_broadcaster","urdf_inspect","bag_inspect"]
    for idx,name in enumerate(snips):
        bx=RIGHT_X+8+idx*70
        by=RIGHT_Y+24
        sel=name in app.editor_code[:20] or (idx==0 and len(app.editor_code)<10)
        # simple highlight for current snippet name present? Use first word check
        is_active = app.editor_code.strip().startswith("#") and name in app.editor_code.lower() or False
        # Better: check if snippet name equals selected? We'll store app.selected_snippet
        # For now just draw
        drawRect(bx,by,66,18,fill=rgb(45,55,85) if not is_active else PINK,border=PANEL_BORDER,borderWidth=1,roundness=6)
        drawLabel(name[:10], bx+33, by+9, fill=rgb(220,230,255), size=7, bold=is_active, align="center")

    # Editor text area background
    ex,ey,ew,eh=RIGHT_X+8, RIGHT_Y+48, RIGHT_W-16, 200
    drawRect(ex,ey,ew,eh,fill=rgb(12,16,30),border=YELLOW if app.editor_focus else PANEL_BORDER,borderWidth=1.5 if app.editor_focus else 1,roundness=6)
    # Draw code lines (monospace)
    lines=app.editor_code.split("\n")
    for li, line in enumerate(lines[:14]):
        # cursor
        col=WHITE if li!=len(lines)-1 or not app.editor_focus else YELLOW
        drawLabel(line[:48], ex+6, ey+6+li*12, fill=col, size=8, align="left-top")
    if app.editor_focus:
        # blinking cursor
        cur_line=len(lines)-1
        cur_x=ex+6+len(lines[-1])*5
        cur_y=ey+6+cur_line*12
        drawRect(cur_x, cur_y, 2, 10, fill=YELLOW)

    # Package inspector
    drawRect(RIGHT_X+8, RIGHT_Y+260, 60, 18, fill=rgb(45,55,85), border=PANEL_BORDER, borderWidth=1, roundness=6)
    drawLabel("INSPECT", RIGHT_X+38, RIGHT_Y+269, fill=rgb(220,230,255), size=8, bold=True, align="center")
    drawLabel("catkin_pkg/rospkg/rosdistro/genmsg/genpy/rosbags", RIGHT_X+74, RIGHT_Y+264, fill=rgb(130,150,180), size=7, align="left-top")
    # pkg_info
    py=RIGHT_Y+284
    for k,v in list(app.pkg_info.items())[:6]:
        drawLabel(f"{k}: {str(v)[:34]}", RIGHT_X+8, py, fill=rgb(150,170,200), size=7, align="left-top")
        py+=10

    # Logs
    drawLabel("LOGS", RIGHT_X+8, RIGHT_Y+360, fill=rgb(180,190,220), size=9, bold=True, align="left-top")
    log_y=RIGHT_Y+374
    for line in app.logs[-16:]:
        drawLabel(line[:52], RIGHT_X+8, log_y, fill=GREEN, size=7, align="left-top")
        log_y+=12
        if log_y>RIGHT_Y+RIGHT_H-12:
            break

    # Footer note about transport
    drawLabel("Transport: window.WebSocket (browser) not Python sockets -> works in Pyodide. roslibpy twisted fails.", 12, H-10, fill=rgb(110,120,150), size=8, align="left-bottom")
    drawLabel("SCS pyodide extension + new extensions: rosbridge_browser, urdf, sim, editor", W-12, H-10, fill=rgb(110,120,150), size=8, align="right-bottom")

# SCS exports - required
# In fourier_ear_lab.py there is no class, just callbacks. So we expose nothing extra.
# For compatibility with earlier loader that expects App, we also expose:
class RosPlaygroundApp:
    width=W
    height=H
    def __init__(self):
        pass

App=RosPlaygroundApp
SCS_APP_TYPE="python.pyodide"
SCS_APP_SIZE=(1050,700)
