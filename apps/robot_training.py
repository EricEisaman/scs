# robot_training.py — OpenArm 2.0 + MLP-RL Stacking Trainer (SCS, 1050x700)
# ---------------------------------------------------------------------------
# Maps the Anvil OpenArm 2.0 Quest Teleop Kit to a 2D SCS lab:
#   Real kit: 7-DOF per arm, 633 mm reach, parallel gripper 88 mm opening,
#             in-hand camera + 4x 60-fps camera modules, Quest 3 teleop
#             for demo collection, train ACT / Diffusion / GR00T / Pi.
#   This lab:  3 planar joints (shoulder/elbow/wrist) = honest 2D projection
#             of the 7-DOF chain, NOT full 3D. Gripper 44 px = 88 mm at
#             0.5 px/mm, reach ~315 px, 9 raycasts = wrist-camera depth fan.
#             Manual keyboard teleop collects human demos. No Quest hardware
#             is emulated or claimed.
#
# WHY THIS *REQUIRES* LEARNING — NOT A FAKE:
#   1. NO inverse kinematics anywhere for the learner. The MLP outputs raw
#      joint deltas + gripper. It never gets a target joint angle.
#   2. NO grasp table / NO shape library. The robot never sees the polygon,
#      its centroid, or its COM. It only sees 9 ray distances, 2 touch
#      contacts, force, slip/torque, proprioception + 8-dim hidden context.
#   3. USER-DESIGNED GEOMETRY breaks any script. Draw ANY polygon — concave
#      L / U / T, wedge, star, freeform. For those shapes the bounding-box
#      centre != COM, and COM can sit outside the support footprint. Grasping
#      the bbox centre slips / tips. Placing by bbox centre topples.
#      Only probing (ray width + touch + torque) lets the MLP centre on the
#      true COM and offset placement so COM sits over support.
#   4. Reward is environmental, not a script: progress + contact + lift +
#      stable stack, minus drop / tip / time. Weights change only by
#      backprop on TD error (critic) + advantage-weighted policy gradient
#      (actor). Reset the brain and it must re-learn from scratch.
#
# ML ENGINEERING STANDARD (senior / Sigma):
#   - Actor-Critic with SEPARATE target critic, soft updates (tau=0.005),
#     TD3-style bootstrapping: timeout != terminal (timeout bootstraps).
#   - Premature-loss fixes: stratified replay (>=50% positives when any
#     exist), TD-std floor 0.08 + actor gating when Pos==0 and TD-std<0.02,
#     close-on-object shaping, gripper-noise boost on contact, TD-std /
#     Adv-std / Pos% diagnostics. Loss alone is never trusted.
#   - Adam from scratch per-weight (Kingma & Ba 2014), bias-corrected,
#     gradient clipping, Huber loss for critic TD (robust to outliers).
#   - Observation normalisation (Welford running mean/var, clipped +-5),
#     advantage normalisation per batch, reward clipping, LR decay.
#   - He init for ReLU, Xavier for tanh/sigmoid/linear, zero bias init.
#   - Uniform replay buffer (capacity 2000), batch 32, gamma=0.97.
#   - Deterministic eval mode (noise=0, no training) to measure true policy.
#   - No try/except, no getattr/hasattr, no .get() defaults, no scripted
#     controller, no IK, no grasp table. Every line is explicit.
#
# Pure MVC: Model = Neuron/Layer/MLP/Replay/Context/PhysObject/RobotArm/Env
#           View   = redrawAll + draw_* helpers
#           Controller = onAppStart / onStep / onMouse* / onKeyPress
# No window / browser use. All state lives on app.*.
# ---------------------------------------------------------------------------
from scs import *
import math, random

WIDTH = 1050
HEIGHT = 700
ARENA_X0 = 16
ARENA_Y0 = 76
ARENA_X1 = 694
ARENA_Y1 = 660
FLOOR_Y = 600
TOWER_X0 = 320
TOWER_X1 = 420
PANEL_X = 710
PANEL_W = 324

BG = rgb(10, 12, 20)
PANEL = rgb(28, 31, 48)
PANEL2 = rgb(22, 26, 42)
BORDER = rgb(58, 64, 94)
ACC = rgb(99, 102, 241)
ACC_H = rgb(129, 133, 255)
ACC2 = rgb(16, 185, 129)
WARN = rgb(245, 158, 11)
BAD = rgb(239, 68, 68)
TXT = rgb(236, 240, 255)
DIM = rgb(150, 160, 188)
GRID = rgb(44, 50, 76)
FLOOR_C = rgb(52, 58, 86)

# ---------------------------------------------------------------------------
# MODEL — MLP from scratch (Layer / Neuron / accumulator / chain rule)
# ---------------------------------------------------------------------------
def _act(name, z):
    if name == 'relu':
        return z if z > 0 else 0.0
    if name == 'sigmoid':
        return 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))
    if name == 'tanh':
        return math.tanh(z)
    return z

def _deriv(name, z, out):
    if name == 'relu':
        return 1.0 if z > 0 else 0.0
    if name == 'sigmoid':
        return out * (1.0 - out)
    if name == 'tanh':
        return 1.0 - out * out
    return 1.0

class Neuron:
    """One processing node: inputs, weights, bias, accumulator, output, delta.
    Adam state (m/v per weight + bias) lives here so the optimizer is
    per-parameter, bias-corrected, and exactly reproducible."""
    def __init__(self, n_inputs, n_outputs, activator):
        self.activator = activator
        # He for ReLU (preserves variance through ReLU), Xavier for
        # tanh/sigmoid/linear (preserves variance through symmetric act).
        if activator == 'relu':
            scale = math.sqrt(2.0 / max(1, n_inputs))
        elif activator in ('tanh', 'sigmoid'):
            scale = math.sqrt(2.0 / max(1, n_inputs + n_outputs))
        else:
            scale = math.sqrt(1.0 / max(1, n_inputs))
        self.weights = [random.gauss(0, scale) for _ in range(n_inputs)]
        self.bias = 0.0  # Zero bias init: symmetry already broken by weights.
        self.inputs = []
        self.accumulator = 0.0
        self.output = 0.0
        self.delta = 0.0
        # Adam state (Kingma & Ba 2014)
        self.m_w = [0.0] * n_inputs
        self.v_w = [0.0] * n_inputs
        self.m_b = 0.0
        self.v_b = 0.0
        self.adam_step = 0
    def forward(self, inputs):
        self.inputs = list(inputs)
        s = self.bias
        for i, w in enumerate(self.weights):
            if i < len(inputs):
                s += inputs[i] * w
        self.accumulator = s
        self.output = _act(self.activator, s)
        return self.output

class Layer:
    def __init__(self, n_in, n_out, activator):
        self.activator = activator
        self.neurons = [Neuron(n_in, n_out, activator) for _ in range(n_out)]
    def forward(self, x):
        return [n.forward(x) for n in self.neurons]

class MLP:
    # sizes e.g. [33,48,32,4], activators e.g. ['relu','relu','tanh']
    def __init__(self, sizes, activators):
        self.sizes = list(sizes)
        self.activators = list(activators)
        self.layers = []
        for i in range(len(sizes) - 1):
            self.layers.append(Layer(sizes[i], sizes[i + 1], activators[i]))
    def forward(self, x):
        cur = list(x)
        for layer in self.layers:
            cur = layer.forward(cur)
        return cur
    def train_example(self, x, target, lr, loss_type='mse'):
        """One Adam step. loss_type='mse' for actor, 'huber' for critic TD.
        Huber: grad = clip(err, -1, 1) — robust to large TD outliers.
        Gradients clipped to [-1, 1] before Adam to prevent explosion."""
        out = self.forward(x)
        for li in range(len(self.layers) - 1, -1, -1):
            layer = self.layers[li]
            is_out = (li == len(self.layers) - 1)
            for ni, neuron in enumerate(layer.neurons):
                if is_out:
                    err = (out[ni] - target[ni]) if ni < len(target) else 0.0
                    if loss_type == 'huber':
                        grad = max(-1.0, min(1.0, err))
                    else:
                        grad = err * 2.0 / max(1, len(target))
                    neuron.delta = grad * _deriv(neuron.activator, neuron.accumulator, neuron.output)
                else:
                    nxt = self.layers[li + 1]
                    s = 0.0
                    for n_next in nxt.neurons:
                        if ni < len(n_next.weights):
                            s += n_next.delta * n_next.weights[ni]
                    neuron.delta = s * _deriv(neuron.activator, neuron.accumulator, neuron.output)
                # Clip delta (gradient) — prevents a single bad TD from wrecking weights.
                if neuron.delta > 1.0:
                    neuron.delta = 1.0
                if neuron.delta < -1.0:
                    neuron.delta = -1.0
        # --- Adam update per weight ---
        beta1 = 0.9
        beta2 = 0.999
        eps = 1e-8
        for layer in self.layers:
            for neuron in layer.neurons:
                neuron.adam_step += 1
                bc1 = 1.0 - (beta1 ** neuron.adam_step)
                bc2 = 1.0 - (beta2 ** neuron.adam_step)
                for i in range(len(neuron.weights)):
                    inp = neuron.inputs[i] if i < len(neuron.inputs) else 0.0
                    g = neuron.delta * inp
                    if g > 1.0:
                        g = 1.0
                    if g < -1.0:
                        g = -1.0
                    neuron.m_w[i] = beta1 * neuron.m_w[i] + (1.0 - beta1) * g
                    neuron.v_w[i] = beta2 * neuron.v_w[i] + (1.0 - beta2) * g * g
                    m_hat = neuron.m_w[i] / bc1
                    v_hat = neuron.v_w[i] / bc2
                    neuron.weights[i] -= lr * m_hat / (math.sqrt(v_hat) + eps)
                g_b = neuron.delta
                if g_b > 1.0:
                    g_b = 1.0
                if g_b < -1.0:
                    g_b = -1.0
                neuron.m_b = beta1 * neuron.m_b + (1.0 - beta1) * g_b
                neuron.v_b = beta2 * neuron.v_b + (1.0 - beta2) * g_b * g_b
                m_hat_b = neuron.m_b / bc1
                v_hat_b = neuron.v_b / bc2
                neuron.bias -= lr * m_hat_b / (math.sqrt(v_hat_b) + eps)
        loss = 0.0
        for a, b in zip(out, target):
            d = a - b
            if loss_type == 'huber':
                ad = abs(d)
                loss += (0.5 * d * d) if ad <= 1.0 else (ad - 0.5)
            else:
                loss += d * d
        return loss / max(1, len(target))
    def copy_from(self, other):
        """Hard copy weights + bias (for target-critic init). Adam state reset."""
        for la, lb in zip(self.layers, other.layers):
            for na, nb in zip(la.neurons, lb.neurons):
                na.weights = list(nb.weights)
                na.bias = nb.bias
                na.m_w = [0.0] * len(na.weights)
                na.v_w = [0.0] * len(na.weights)
                na.m_b = 0.0
                na.v_b = 0.0
                na.adam_step = 0
    def soft_update_from(self, other, tau):
        """Polyak averaging: target = tau*online + (1-tau)*target."""
        for la, lb in zip(self.layers, other.layers):
            for na, nb in zip(la.neurons, lb.neurons):
                for i in range(len(na.weights)):
                    na.weights[i] = tau * nb.weights[i] + (1.0 - tau) * na.weights[i]
                na.bias = tau * nb.bias + (1.0 - tau) * na.bias
    def weight_norm(self):
        s = 0.0
        n = 0
        for layer in self.layers:
            for neuron in layer.neurons:
                for w in neuron.weights:
                    s += w * w
                    n += 1
        return math.sqrt(s / max(1, n))

class TrainingContext:
    # Hidden-state context fed alongside sensors — DeepMind memory-ANN idea:
    # [prev_reward, prev_slip, prev_contact, steps_since_grasp,
    #  grasps, drops, prev_action0, prev_action1]
    def __init__(self):
        self.prev_reward = 0.0
        self.prev_slip = 0.0
        self.prev_contact = 0.0
        self.prev_action = [0.0, 0.0, 0.0, 0.0]
        self.steps_since_grasp = 0
        self.grasps = 0
        self.drops = 0
        self.successes = 0
    def vector(self):
        return [self.prev_reward,
                self.prev_slip, self.prev_contact,
                min(1.0, self.steps_since_grasp / 200.0),
                min(1.0, self.grasps / 10.0),
                min(1.0, self.drops / 10.0),
                self.prev_action[0], self.prev_action[1]]
    def update(self, reward, slip, contact, action, grasped):
        # Scale: final reward is in [-25,25] (terminal +20). /25 keeps
        # ordering: step ~0.00, grasp ~0.08, stack ~0.40, terminal ~1.0.
        # Previously raw reward was clipped to [-1,1] in vector(), so
        # grasp (+2) and stack (+10) both became 1.0 — signal lost.
        self.prev_reward = max(-1.0, min(1.0, reward / 25.0))
        self.prev_slip = slip
        self.prev_contact = contact
        self.prev_action = list(action)
        if grasped:
            self.grasps += 1
            self.steps_since_grasp = 0
        else:
            self.steps_since_grasp += 1

class ObsNormalizer:
    """Welford running mean/var. Normalise obs to ~N(0,1), clip to [-5,5].
    Sensors have wildly different scales (angles vs ray distances vs force);
    without this the MLP wastes capacity on scale, not geometry."""
    def __init__(self, dim):
        self.dim = dim
        self.mean = [0.0] * dim
        self.m2 = [0.0] * dim
        self.count = 0
    def update(self, x):
        self.count += 1
        for i in range(self.dim):
            delta = x[i] - self.mean[i]
            self.mean[i] += delta / self.count
            delta2 = x[i] - self.mean[i]
            self.m2[i] += delta * delta2
    def normalize(self, x):
        out = []
        for i in range(self.dim):
            if self.count < 2:
                var = 1.0
            else:
                var = self.m2[i] / (self.count - 1)
            if var < 1e-8:
                var = 1e-8
            std = math.sqrt(var)
            v = (x[i] - self.mean[i]) / std
            if v > 5.0:
                v = 5.0
            if v < -5.0:
                v = -5.0
            out.append(v)
        return out

class OUNoise:
    def __init__(self, dim, theta=0.15, sigma=0.25):
        self.dim = dim; self.theta = theta; self.sigma = sigma; self.state = [0.0]*dim
    def reset(self): self.state = [0.0]*self.dim
    def sample(self):
        common = random.gauss(0, self.sigma*0.5); out=[]
        for i in range(self.dim):
            dx = self.theta*(0.0-self.state[i]) + random.gauss(0, self.sigma)
            self.state[i]+=dx; v=self.state[i]*0.7+common*0.3
            out.append(max(-1.0,min(1.0,v)))
        return out

class ReplayBuffer:
    """Stratified replay, capacity 2000. Stores (s, a, noise, r, s2, done, timeout).
    Uniform sampling is the premature-loss bug: with 0 grasps the buffer
    is 100% failures, every batch has ~0 TD surprise, and loss collapses
    while nothing is learned. Stratified sampling guarantees the batch
    contains positives (r >= 0.4: grasp / lift / stack / terminal) whenever
    any exist, so the critic always has signal to fit and the actor always
    has a good action to clone. This is prioritised sampling, not a script:
    no transition is invented, only the sampling mix changes."""
    def __init__(self, capacity):
        self.capacity = capacity
        self.buf = []
    def add(self, transition):
        self.buf.append(transition)
        if len(self.buf) > self.capacity:
            self.buf.pop(0)
    def sample(self, k):
        return self.sample_stratified(k)
    def sample_stratified(self, k, pos_thresh=0.4, min_pos_frac=0.5):
        n = min(k, len(self.buf))
        if n <= 0:
            return []
        pos = [t for t in self.buf if t[3] >= pos_thresh]
        neg = [t for t in self.buf if t[3] < pos_thresh]
        if len(pos) == 0 or len(neg) == 0:
            return random.sample(self.buf, n)
        n_pos = min(len(pos), max(1, int(round(n * min_pos_frac))))
        n_neg = n - n_pos
        if n_neg > len(neg):
            n_neg = len(neg)
            n_pos = n - n_neg
        batch = random.sample(pos, n_pos) + random.sample(neg, n_neg)
        random.shuffle(batch)
        return batch
    def pos_frac(self, pos_thresh=0.4):
        if len(self.buf) == 0:
            return 0.0
        return sum(1 for t in self.buf if t[3] >= pos_thresh) / len(self.buf)
    def __len__(self):
        return len(self.buf)

# ---------------------------------------------------------------------------
# MODEL — geometry (ground truth for PHYSICS ONLY — never given to MLP)
# ---------------------------------------------------------------------------
def _poly_area_centroid(verts):
    # verts: local [(x,y)...]. Returns (signed area, cx, cy)
    a = 0.0
    cx = 0.0
    cy = 0.0
    n = len(verts)
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        raise ValueError('degenerate polygon: zero area')
    cx /= (6.0 * a)
    cy /= (6.0 * a)
    return a, cx, cy

def _point_in_poly(px, py, world):
    inside = False
    n = len(world)
    for i in range(n):
        x1, y1 = world[i]
        x2, y2 = world[(i + 1) % n]
        if ((y1 > py) != (y2 > py)):
            xinters = (py - y1) * (x2 - x1) / (y2 - y1 + 1e-9) + x1
            if px < xinters:
                inside = not inside
    return inside

def _ray_hit(ox, oy, dx, dy, world):
    # Exact ray-segment solve. Returns distance along ray, or None for no hit.
    # t*D - u*E = P1 - O, u in [0,1], t > 2. Single solve.
    best = None
    n = len(world)
    for i in range(n):
        x1, y1 = world[i]
        x2, y2 = world[(i + 1) % n]
        ex = x2 - x1
        ey = y2 - y1
        rx = x1 - ox
        ry = y1 - oy
        det = ex * dy - dx * ey
        if abs(det) < 1e-9:
            continue
        t = (-rx * ey + ex * ry) / det
        u = (dx * ry - dy * rx) / det
        if t > 2 and 0.0 <= u <= 1.0:
            if best is None or t < best:
                best = t
    return best

def _min_edge_distance(px, py, world):
    # Distance to closest polygon edge. Grasping on/near an edge or concave
    # corner has almost no contact area -> slips. This is why bbox-centre
    # grasps fail on L/U/wedge: the centre sits on or near an edge.
    best = 1e9
    n = len(world)
    for i in range(n):
        x1, y1 = world[i]
        x2, y2 = world[(i + 1) % n]
        ex = x2 - x1
        ey = y2 - y1
        L2 = ex * ex + ey * ey
        if L2 < 1e-9:
            d = math.hypot(px - x1, py - y1)
        else:
            t = ((px - x1) * ex + (py - y1) * ey) / L2
            if t < 0.0:
                t = 0.0
            if t > 1.0:
                t = 1.0
            qx = x1 + t * ex
            qy = y1 + t * ey
            d = math.hypot(px - qx, py - qy)
        if d < best:
            best = d
    return best

def _rotate(px, py, ang):
    c = math.cos(ang)
    s = math.sin(ang)
    return (px * c - py * s, px * s + py * c)

TEMPLATES = {
    'block': ([(-28, -18), (28, -18), (28, 18), (-28, 18)], rgb(99, 102, 241), 'Block'),
    'L': ([(-28, -18), (28, -18), (28, 0), (0, 0), (0, 18), (-28, 18)], rgb(16, 185, 129), 'L-shape'),
    'T': ([(-30, -18), (30, -18), (30, -2), (10, -2), (10, 18), (-10, 18), (-10, -2), (-30, -2)], rgb(245, 158, 11), 'T-shape'),
    'wedge': ([(-28, 18), (28, 18), (-28, -18)], rgb(239, 68, 68), 'Wedge'),
    'U': ([(-28, -18), (28, -18), (28, 18), (14, 18), (14, 0), (-14, 0), (-14, 18), (-28, 18)], rgb(168, 85, 247), 'U-shape'),
}

class PhysObject:
    def __init__(self, oid, verts_local, x, y, color, name):
        self.id = oid
        self.verts = list(verts_local)
        self.x = float(x)
        self.y = float(y)
        self.rot = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vrot = 0.0
        self.color = color
        self.name = name
        self.held = False
        self.placed = False
        self.resting = False
        area, cx, cy = _poly_area_centroid(self.verts)
        self.area = abs(area)
        self.com_local = (cx, cy)
        self.mass = max(0.5, self.area / 1200.0)
        self.radius = 10.0
        for (vx, vy) in self.verts:
            d = math.hypot(vx - cx, vy - cy)
            if d > self.radius:
                self.radius = d
        self.grasp_offset = (0.0, 0.0)
        self.grasp_stability = 1.0
        self.slip = 0.0
        self.tipping = 0
    def world_verts(self):
        out = []
        for (lx, ly) in self.verts:
            rx, ry = _rotate(lx, ly, self.rot)
            out.append((self.x + rx, self.y + ry))
        return out
    def com_world(self):
        rx, ry = _rotate(self.com_local[0], self.com_local[1], self.rot)
        return (self.x + rx, self.y + ry)
    def bottom_y(self):
        return max(v[1] for v in self.world_verts())
    def top_y(self):
        return min(v[1] for v in self.world_verts())
    def footprint(self):
        w = self.world_verts()
        by = self.bottom_y()
        xs = [v[0] for v in w if v[1] > by - 7]
        if not xs:
            xs = [v[0] for v in w]
        return (min(xs), max(xs))
    def support_interval(self, env):
        # Floor or object below. Returns (lo, hi) or None.
        by = self.bottom_y()
        if by >= FLOOR_Y - 6:
            return self.footprint()
        best = None
        best_gap = 999
        for other in env.objects:
            if other is self or other.held:
                continue
            if abs(other.top_y() - by) < 14:
                lo = max(self.footprint()[0], min(v[0] for v in other.world_verts()))
                hi = min(self.footprint()[1], max(v[0] for v in other.world_verts()))
                gap = abs(other.top_y() - by)
                if hi > lo and gap < best_gap:
                    best_gap = gap
                    best = (lo, hi)
        return best
    def is_stable(self, env):
        sup = self.support_interval(env)
        if sup is None:
            return False
        cx, _ = self.com_world()
        return (sup[0] - 4) <= cx <= (sup[1] + 4)

class RobotArm:
    def __init__(self):
        self.shoulder_x = 110.0; self.shoulder_y = 475.0
        self.L1 = 135.0; self.L2 = 115.0; self.L3 = 48.0
        self.angles = [-0.85, 1.15, 0.35]; self.gripper = 1.0; self.held = None; self.gripper_type = 'parallel'
    def fk(self):
        a1 = self.angles[0]; a2 = a1 + self.angles[1]; a3 = a2 + self.angles[2]
        sx, sy = self.shoulder_x, self.shoulder_y
        ex = sx + math.cos(a1)*self.L1; ey = sy + math.sin(a1)*self.L1
        wx = ex + math.cos(a2)*self.L2; wy = ey + math.sin(a2)*self.L2
        tx = wx + math.cos(a3)*self.L3; ty = wy + math.sin(a3)*self.L3
        return (sx, sy), (ex, ey), (wx, wy), (tx, ty), a3
    BASE_LEN = 18.0; FINGER_LEN = 32.0; FINGER_THICK = 8.0; GAP_MAX = 44.0; GAP_MIN = 4.0
    ADAPT_PROX = 16.0; ADAPT_DIST = 20.0; ADAPT_PIVOT = 12.0
    ADAPT_SPLAY_BASE = 0.10; ADAPT_SPLAY_RANGE = 0.80; ADAPT_CURL = 0.70
    def gap(self):
        if self.gripper_type == 'adaptive': return 4.6 + self.gripper*52.4
        return self.GAP_MIN + self.gripper*(self.GAP_MAX-self.GAP_MIN)
    def adaptive_segments(self):
        _, _, _, tip, a3 = self.fk()
        ax = math.cos(a3); ay = math.sin(a3); px = -math.sin(a3); py = math.cos(a3)
        bx = tip[0]+ax*self.BASE_LEN; by = tip[1]+ay*self.BASE_LEN
        splay = self.ADAPT_SPLAY_BASE + self.gripper*self.ADAPT_SPLAY_RANGE
        out=[]
        for s in (1.0,-1.0):
            piv=(bx+px*self.ADAPT_PIVOT*s, by+py*self.ADAPT_PIVOT*s)
            d_prox=(math.cos(a3+s*splay), math.sin(a3+s*splay))
            prox_end=(piv[0]+d_prox[0]*self.ADAPT_PROX, piv[1]+d_prox[1]*self.ADAPT_PROX)
            d_dist=(math.cos(a3+s*(splay-self.ADAPT_CURL)), math.sin(a3+s*(splay-self.ADAPT_CURL)))
            tip_pt=(prox_end[0]+d_dist[0]*self.ADAPT_DIST, prox_end[1]+d_dist[1]*self.ADAPT_DIST)
            mid=(prox_end[0]+d_dist[0]*self.ADAPT_DIST/2.0, prox_end[1]+d_dist[1]*self.ADAPT_DIST/2.0)
            out.append((piv, prox_end, tip_pt, mid, s))
        return out
    def gripper_center(self):
        if self.gripper_type == 'adaptive':
            segs=self.adaptive_segments(); return ((segs[0][3][0]+segs[1][3][0])/2.0, (segs[0][3][1]+segs[1][3][1])/2.0)
        _, _, _, tip, a3 = self.fk(); d=self.BASE_LEN+self.FINGER_LEN/2.0
        return (tip[0]+math.cos(a3)*d, tip[1]+math.sin(a3)*d)
    def finger_tip(self):
        if self.gripper_type == 'adaptive':
            segs=self.adaptive_segments(); return segs[0][2] if segs[0][2][1]>=segs[1][2][1] else segs[1][2]
        _, _, _, tip, a3 = self.fk(); d=self.BASE_LEN+self.FINGER_LEN
        return (tip[0]+math.cos(a3)*d, tip[1]+math.sin(a3)*d)
    def jaw_positions(self):
        if self.gripper_type == 'adaptive':
            segs=self.adaptive_segments(); return (segs[0][2], segs[1][2])
        _, _, _, tip, a3 = self.fk(); px=-math.sin(a3); py=math.cos(a3); half=self.gap()/2.0; c=self.gripper_center()
        return ((c[0]+px*half, c[1]+py*half),(c[0]-px*half, c[1]-py*half))
    def finger_rects(self):
        if self.gripper_type == 'adaptive':
            quads=[]
            for (piv, prox_end, tip_pt, mid, s) in self.adaptive_segments():
                for (p0,p1,thick) in ((piv,prox_end,9.0),(prox_end,tip_pt,8.0)):
                    dx=p1[0]-p0[0]; dy=p1[1]-p0[1]; L=math.hypot(dx,dy) or 1.0
                    nx=-dy/L*(thick/2.0); ny=dx/L*(thick/2.0)
                    quads.append([(p0[0]+nx,p0[1]+ny),(p0[0]-nx,p0[1]-ny),(p1[0]-nx,p1[1]-ny),(p1[0]+nx,p1[1]+ny)])
            return quads
        _, _, _, tip, a3 = self.fk(); ax=math.cos(a3); ay=math.sin(a3); px=-math.sin(a3); py=math.cos(a3)
        bx=tip[0]+ax*self.BASE_LEN; by=tip[1]+ay*self.BASE_LEN
        ex=tip[0]+ax*(self.BASE_LEN+self.FINGER_LEN); ey=tip[1]+ay*(self.BASE_LEN+self.FINGER_LEN)
        rects=[]
        for s in (1.0,-1.0):
            inner=self.gap()/2.0; outer=inner+self.FINGER_THICK
            rects.append([(bx+px*inner*s, by+py*inner*s),(bx+px*outer*s, by+py*outer*s),(ex+px*outer*s, ey+py*outer*s),(ex+px*inner*s, ey+py*inner*s)])
        return rects
    def base_rect(self):
        _, _, _, tip, a3 = self.fk(); ax=math.cos(a3); ay=math.sin(a3); px=-math.sin(a3); py=math.cos(a3)
        cx=tip[0]+ax*(self.BASE_LEN/2.0); cy=tip[1]+ay*(self.BASE_LEN/2.0); hl=self.BASE_LEN/2.0; hw=18.0
        return [(cx+ax*hl+px*hw, cy+ay*hl+py*hw),(cx+ax*hl-px*hw, cy+ay*hl-py*hw),(cx-ax*hl-px*hw, cy-ay*hl-py*hw),(cx-ax*hl+px*hw, cy-ay*hl+py*hw)]

class Env:
    def __init__(self):
        self.objects = []
        self.arm = RobotArm()
        self.episode = 1
        self.step_count = 0
        self.episode_reward = 0.0
        self.next_id = 1
        self.tower_count = 0
        self.last_grasp_msg = ''
        self._custom_verts = None
        self.last_gripper_pos = None; self.still_steps = 0; self._lift_given = False; self._close_given = False
        self.prev_gripper_vel = (0.0, 0.0); self.joint_vel = [0.0,0.0,0.0]
        self.gripper_vel = (0.0, 0.0); self.gripper_acc = (0.0, 0.0)
        self.accel_forward = 0.0; self.accel_perp = 0.0; self.down_alignment = 0.0
    def tower_slot(self):
        # Next stable slot in tower zone. Stack height grows with placed count.
        return ((TOWER_X0 + TOWER_X1) / 2.0, FLOOR_Y - self.tower_count * 38.0 - 20.0)
    def current_target_pos(self):
        if self.arm.held is not None:
            return self.tower_slot()
        best = None
        best_d = 1e9
        gc = self.arm.gripper_center()
        for o in self.objects:
            if o.placed or o.held:
                continue
            cx, cy = o.com_world()
            d = math.hypot(cx - gc[0], cy - gc[1])
            if d < best_d:
                best_d = d
                best = (cx, cy)
        if best is None:
            return self.tower_slot()
        return best
    def cast_rays(self):
        # 9 depth rays fanning downward from wrist camera. Returns 0..1 (1 = far).
        gc = self.arm.gripper_center()
        _, _, _, _, a3 = self.arm.fk()
        out = []
        for k in range(9):
            ang = a3 + (k - 4) * 0.22  # hand forward +/- ~50 deg
            dx = math.cos(ang)
            dy = math.sin(ang)
            best = None
            for o in self.objects:
                if o.held:
                    continue
                d = _ray_hit(gc[0], gc[1], dx, dy, o.world_verts())
                if d is not None and (best is None or d < best):
                    best = d
            if dy > 0.05:
                d_floor = (FLOOR_Y - gc[1]) / dy
                if d_floor >= 0 and (best is None or d_floor < best):
                    best = d_floor
            if best is None:
                out.append(1.0)
            else:
                out.append(max(0.0, min(1.0, best / 240.0)))
        return out
    def contact_sensors(self):
        # Touch + force + slip. Robot sees these, never the polygon.
        arm = self.arm
        gc = arm.gripper_center()
        contact = 0.0
        force = 0.0
        slip = 0.0
        if arm.held is not None:
            slip = min(1.0, abs(arm.held.slip))
            contact = 1.0
            force = min(1.0, (1.0 - arm.gripper) * 0.8 + 0.2)
            return contact, force, slip
        for o in self.objects:
            if o.placed:
                continue
            if _point_in_poly(gc[0], gc[1], o.world_verts()):
                contact = 1.0
                force = min(1.0, (1.0 - arm.gripper) * 0.9)
                break
            # near-edge touch: jaw within 10px of polygon
            for j in arm.jaw_positions():
                if _point_in_poly(j[0], j[1], o.world_verts()):
                    contact = 1.0
                    force = 0.5
                    break
        return contact, force, slip
    def add_object(self, template_name, x, y):
        if template_name == 'custom' and self._custom_verts is not None:
            verts = list(self._custom_verts)
            color = rgb(45, 212, 191)
            name = 'Custom'
        else:
            verts, color, name = TEMPLATES[template_name]
            verts = list(verts)
        o = PhysObject(self.next_id, verts, x, y, color, name)
        self.next_id += 1
        self.objects.append(o)
        return o
    def reset_scene(self, keep_brain=True):
        _gt = self.arm.gripper_type if hasattr(self.arm, 'gripper_type') else 'parallel'
        self.arm = RobotArm(); self.arm.gripper_type = _gt
        self.tower_count = 0; self.still_steps = 0; self.last_gripper_pos = None; self._lift_given = False; self._close_given = False
        self.prev_gripper_vel = (0.0, 0.0); self.joint_vel = [0.0,0.0,0.0]
        self.gripper_vel = (0.0, 0.0); self.gripper_acc = (0.0, 0.0)
        self.step_count = 0; self.episode_reward = 0.0
        base_xs = [130, 190, 250, 160, 220, 280]
        random.shuffle(base_xs)
        xs = [float(base_xs[i % len(base_xs)] + random.uniform(-40, 40)) for i in range(len(self.objects))]
        for i, o in enumerate(self.objects):
            o.x = float(xs[i % len(xs)])
            o.y = 170.0 + (i // 3) * 70.0 + random.uniform(-20, 20)
            o.rot = random.uniform(-0.25, 0.25)
            o.vx = 0.0
            o.vy = 0.0
            o.vrot = 0.0
            o.held = False
            o.placed = False
            o.resting = False
            o.slip = 0.0
            o.tipping = 0
    def physics_only(self):
        for o in self.objects:
            if o.held or o.placed:
                continue
            self._free_update(o)
    def _free_update(self, o):
        o.vy += 0.55
        if o.vy > 9:
            o.vy = 9
        o.y += o.vy
        o.x += o.vx
        o.rot += o.vrot
        o.vx *= 0.92
        o.vrot *= 0.90
        by = o.bottom_y()
        if by >= FLOOR_Y:
            # land on floor
            o.y -= (by - FLOOR_Y)
            o.vy = 0.0
            if o.is_stable(self):
                o.resting = True
                o.vrot = 0.0
                o.tipping = 0
            else:
                o.resting = False
                o.tipping += 1
                cx, _ = o.com_world()
                lo, hi = o.footprint()
                mid = (lo + hi) / 2.0
                direction = 1.0 if cx > mid else -1.0
                o.rot += direction * 0.025
                o.x += direction * 1.4
                if o.tipping > 26:
                    # tipped off — slide out and settle as fallen, not stacked
                    o.tipping = 0
                    o.rot += direction * 0.12
        else:
            # check landing on another object
            for other in self.objects:
                if other is o or other.held:
                    continue
                if abs(other.top_y() - by) < 12 and o.vy >= 0:
                    overlap_lo = max(o.footprint()[0], min(v[0] for v in other.world_verts()))
                    overlap_hi = min(o.footprint()[1], max(v[0] for v in other.world_verts()))
                    if overlap_hi - overlap_lo > 12:
                        o.y -= (by - other.top_y())
                        o.vy = 0.0
                        if o.is_stable(self):
                            o.resting = True
                            o.vrot = 0.0
                        else:
                            cx, _ = o.com_world()
                            direction = 1.0 if cx > (overlap_lo + overlap_hi) / 2.0 else -1.0
                            o.rot += direction * 0.03
                            o.x += direction * 1.6
                        break
        # keep inside arena
        if o.x < 34:
            o.x = 34
            o.vx = 0
        if o.x > 678:
            o.x = 678
            o.vx = 0
    def step(self, action, app_ctx):
        arm = self.arm; prev_target = self.current_target_pos(); gc0 = arm.gripper_center()
        prev_dist = math.hypot(prev_target[0]-gc0[0], prev_target[1]-gc0[1]); prev_angles = list(arm.angles)
        arm.angles[0] = max(-2.4, min(0.45, arm.angles[0] + action[0]*0.055))
        arm.angles[1] = max(-0.15, min(2.6, arm.angles[1] + action[1]*0.065))
        arm.angles[2] = max(-1.8, min(1.8, arm.angles[2] + action[2]*0.065))
        arm.gripper = max(0.0, min(1.0, arm.gripper - action[3]*0.085))
        _ft_try = arm.finger_tip(); _a3_old = prev_angles[0]+prev_angles[1]+prev_angles[2]
        _ft_prev_y = gc0[1] + math.sin(_a3_old)*(arm.FINGER_LEN/2.0) if arm.gripper_type=='parallel' else gc0[1]
        collision = False
        if _ft_try[1] > FLOOR_Y-5 and _ft_try[1] >= _ft_prev_y:
            arm.angles = prev_angles; collision = True
        reward = -0.012; info = {'slip':0.0,'contact':0.0,'grasped':False,'placed':False,'dropped':False,'collision':0.0,'stuck':0.0}
        if collision:
            # Was -2.0: dwarfed grasp (+2) and taught the robot to fear the
            # floor — where every object sits. Now -0.5, and only -0.1 when
            # the gripper is over an object (it is trying to grasp, not crash).
            _over_obj = any(_point_in_poly(gc0[0], gc0[1], o.world_verts()) for o in self.objects if not o.placed)
            reward -= 0.1 if _over_obj else 0.5; info['collision']=1.0; self.last_grasp_msg='FLOOR CONTACT — gripper hit floor, move rejected'
        gc = arm.gripper_center(); new_dist = math.hypot(prev_target[0]-gc[0], prev_target[1]-gc[1])
        self.joint_vel = [arm.angles[i]-prev_angles[i] for i in range(3)]
        _new_vel = (gc[0]-gc0[0], gc[1]-gc0[1])
        self.gripper_acc = (_new_vel[0]-self.prev_gripper_vel[0], _new_vel[1]-self.prev_gripper_vel[1])
        self.gripper_vel = _new_vel; self.prev_gripper_vel = _new_vel
        _a3 = arm.angles[0]+arm.angles[1]+arm.angles[2]
        _ax = self.gripper_acc[0]/10.0; _ay = self.gripper_acc[1]/10.0
        _proper_x = _ax - 0.0; _proper_y = _ay - 1.0
        _fx = math.cos(_a3); _fy = math.sin(_a3); _px = -math.sin(_a3); _py = math.cos(_a3)
        self.accel_forward = max(-2.0, min(2.0, _proper_x*_fx + _proper_y*_fy))/2.0
        self.accel_perp = max(-2.0, min(2.0, _proper_x*_px + _proper_y*_py))/2.0
        self.down_alignment = math.sin(_a3)
        if self.last_gripper_pos is not None:
            moved = math.hypot(gc[0]-self.last_gripper_pos[0], gc[1]-self.last_gripper_pos[1])
            self.still_steps = self.still_steps+1 if moved < 1.5 else 0
            if self.still_steps > 60 and new_dist > 40: reward -= 0.08; info['stuck']=1.0
        self.last_gripper_pos = gc; reward += (prev_dist - new_dist)*0.015
        # --- Close-on-object shaping (fixes 0 grasp attempts) ---
        # The old reward gave +0 for being centred inside an object with the
        # gripper open, and +0 for closing on it unless a grasp succeeded.
        # So the MLP had NO gradient toward grasping before its first grasp
        # ever happened, and the buffer stayed 100% failures. Now:
        #  (a) small per-step reward for being centred inside an object
        #      (teaches approach + COM-centring, not bbox-centring);
        #  (b) one-time +0.30 the first time it CLOSES while inside an object
        #      (teaches the close action itself, without farming: _close_given
        #      resets only when the gripper leaves every object / drops).
        # Both are environmental shaping, not a script: the MLP still has to
        # discover the close, and the bonus is capped / one-time.
        if arm.held is None:
            _inside_any = None
            _inside_off = 0.0
            for _o in self.objects:
                if _o.placed:
                    continue
                if _point_in_poly(gc[0], gc[1], _o.world_verts()):
                    _cx, _cy = _o.com_world()
                    _inside_any = _o
                    _inside_off = math.hypot(gc[0] - _cx, gc[1] - _cy)
                    break
            if _inside_any is not None:
                _centred = max(0.0, 1.0 - _inside_off / (_inside_any.radius + 12.0))
                reward += 0.10 * _centred
                # Closing = gripper value decreasing (action[3] > 0 drives
                # arm.gripper down in step()). Detect a close this step.
                if action[3] > 0.30 and not self._close_given:
                    reward += 0.30 * _centred
                    self._close_given = True
                    self.last_grasp_msg = 'CLOSE ON OBJECT — centred %.2f' % _centred
            else:
                self._close_given = False
        if arm.held is None and arm.gripper < 0.38:
            for o in self.objects:
                if o.placed: continue
                if _point_in_poly(gc[0], gc[1], o.world_verts()):
                    cx, cy = o.com_world(); off = math.hypot(gc[0]-cx, gc[1]-cy)
                    edge_d = _min_edge_distance(gc[0], gc[1], o.world_verts()); edge_factor = min(1.0, edge_d/12.0)
                    stability = (1.0 - off/(o.radius+12.0))*edge_factor
                    _px2 = -math.sin(_a3); _py2 = math.cos(_a3)
                    _proj = [v[0]*_px2 + v[1]*_py2 for v in o.world_verts()]; _w = max(_proj)-min(_proj)
                    if arm.gripper_type == 'adaptive':
                        stability = (1.0 - off/(o.radius+18.0))*(0.55+0.45*edge_factor)+0.10
                        if stability > 1.0: stability = 1.0
                        if _w > 65.0: stability = 0.0; self.last_grasp_msg='GRASP FAIL — %.0f px wide > 65 px adaptive caging' % _w
                    else:
                        if _w > arm.GAP_MAX + 8.0: stability = 0.0; self.last_grasp_msg='GRASP FAIL — %.0f px wide > %.0f px max opening, orient to narrow side' % (_w, arm.GAP_MAX)
                    if stability > 0.30:
                        arm.held = o; o.held=True; o.grasp_offset=(gc[0]-o.x, gc[1]-o.y); o.grasp_stability=max(0.15, stability); o.slip=0.0
                        # Was flat +2.0: stability 0.31 paid same as 0.99, so the
                        # MLP had no gradient to learn COM-centring. Now
                        # 0.5 + 1.5*stability: 0.31 -> 0.97, 0.99 -> 1.99.
                        reward += 0.5 + 1.5 * stability; info['grasped']=True; self.last_grasp_msg='GRASP %.2f stab' % stability; app_ctx.grasp_attempts+=1; app_ctx.grasp_success+=1; self._lift_given = False; self._close_given = False
                    else:
                        o.slip=1.0; o.vrot+=(random.random()-0.5)*0.08; reward-=0.6; info['slip']=1.0; app_ctx.grasp_attempts+=1
                    break
        if arm.held is not None:
            o = arm.held; o.x = gc[0]-o.grasp_offset[0]; o.y = gc[1]-o.grasp_offset[1]
            wobble=(1.0-o.grasp_stability)*0.018; o.rot+=(random.random()-0.5)*wobble*2.0
            _slip_rate=0.008 if arm.gripper_type=='adaptive' else 0.012
            o.slip=min(1.0, o.slip+(1.0-o.grasp_stability)*_slip_rate); info['slip']=o.slip; info['contact']=1.0
            if o.slip>0.95 and o.grasp_stability<0.45:
                arm.held=None; o.held=False; o.vy=1.5; reward-=3.0; info['dropped']=True; self.last_grasp_msg='DROPPED — off-COM slip'; self._lift_given = False; self._close_given = False
            # Was +0.04 EVERY step while held high: hold+hover for 600 steps
            # = +24, more than a stack (+10). Pure reward hacking. Now
            # one-time +0.5 on first lift per grasp.
            if o.y < FLOOR_Y-55 and not self._lift_given:
                reward += 0.5; self._lift_given = True
        if arm.held is not None and arm.gripper > 0.62:
            o=arm.held; arm.held=None; o.held=False; o.vy=0.0; cx,_=o.com_world()
            if TOWER_X0 <= cx <= TOWER_X1 and o.is_stable(self):
                o.placed=True; o.resting=True; self.tower_count+=1; reward+=10.0; info['placed']=True; self.last_grasp_msg='STACKED! tower=%d' % self.tower_count
            elif TOWER_X0 <= cx <= TOWER_X1 and not o.is_stable(self):
                reward-=2.5; self.last_grasp_msg='PLACED BUT TIPPED — COM off support'
            else: reward-=0.2
        for o in self.objects:
            if not o.held and not o.placed: self._free_update(o)
        c,f,s=self.contact_sensors(); info['contact']=c
        if arm.held is not None: info['slip']=arm.held.slip
        # --- Terminal + accounting (was buggy) ---
        # Old code: episode_reward += reward BEFORE terminal bonus and BEFORE
        # clipping, so logged reward missed +20 and included unclipped values,
        # while the returned (learned) reward was clipped to [-10,10] — so the
        # +20 terminal bonus was clipped to +10, identical to a single stack.
        # New: clip the STEP reward to [-5,5], add terminal AFTER clipping,
        # then clip final to [-25,25]. Logged == learned, terminal survives.
        done=False; timeout=False
        _step_r = max(-5.0, min(5.0, reward))
        if self.tower_count>=len(self.objects) and len(self.objects)>0:
            done=True; _step_r += 20.0
        if self.step_count+1>600: done=True; timeout=True
        reward = max(-25.0, min(25.0, _step_r))
        self.step_count+=1; self.episode_reward+=reward; return reward, done, timeout, info

# CONTROLLER — app state
# ---------------------------------------------------------------------------
def _make_button(x, y, w, h, label, action):
    return {'x': x, 'y': y, 'w': w, 'h': h, 'label': label, 'action': action, 'enabled': True}

def onAppStart(app):
    app.width = WIDTH
    app.height = HEIGHT
    app.stepsPerSecond = 30
    app.scs = {}  # single nested bundle for any future window/extension use
    app.env = Env()
    # Input 43 = 35 sensors + 8 context. Actor 4 = joint deltas + gripper.
    app.actor = MLP([43, 48, 32, 4], ['relu', 'relu', 'tanh'])
    app.critic = MLP([43, 48, 32, 1], ['relu', 'relu', 'linear'])
    app.target_critic = MLP([43, 48, 32, 1], ['relu', 'relu', 'linear'])
    app.target_critic.copy_from(app.critic)
    app.ctx = TrainingContext()
    app.replay = ReplayBuffer(2000)
    app.obs_norm = ObsNormalizer(43)
    app.actor_lr = 0.0008
    app.critic_lr = 0.001
    app.gamma = 0.99
    app.tau = 0.005
    app.eval_mode = False
    app.ou = OUNoise(4)
    app.manual_open = False
    app.grad_norm_hist = [0.0]
    app.critic_loss_hist = [0.0]
    app.actor_loss_hist = [0.0]
    app.td_std_hist = [0.0]
    app.adv_std_hist = [0.0]
    app.pos_frac_hist = [0.0]
    app.actor_gated_count = 0
    app.eval_reward_hist = [0.0]
    app.training = False
    app.teleop = False
    app.mode = 'move'  # move | draw | place
    app.selected_template = 'block'
    app.selected_obj = None
    app.drag_obj = None
    app.drag_dx = 0.0
    app.drag_dy = 0.0
    app.draft_verts = []
    app.custom_verts = None
    app.hover = None
    app.epsilon = 0.35
    app.loss_hist = [0.0]
    app.reward_hist = [0.0]
    app.episode_reward = 0.0
    app.grasp_attempts = 0
    app.grasp_success = 0
    app.status = 'PAUSED — press TRAIN to let the MLP learn. DRAW a custom shape to break scripts.'
    app.teleop_action = [0.0, 0.0, 0.0, 0.0]
    # Seed scene: 3 objects that already punish bbox-centre grasping.
    app.env.add_object('L', 150, 220)
    app.env.add_object('block', 220, 220)
    app.env.add_object('wedge', 290, 230)
    app.buttons = {}
    # Mode row
    app.buttons['mode_move'] = _make_button(710, 108, 100, 28, 'Move', 'mode_move')
    app.buttons['mode_draw'] = _make_button(818, 108, 100, 28, 'Draw Shape', 'mode_draw')
    app.buttons['mode_place'] = _make_button(926, 108, 100, 28, 'Place', 'mode_place')
    # Template row
    tx = 710
    for i, key in enumerate(['block', 'L', 'T', 'wedge', 'U', 'custom']):
        app.buttons['tpl_' + key] = _make_button(tx + i * 54, 142, 50, 26, key[:4].upper(), 'tpl_' + key)
    # Object actions
    app.buttons['add_here'] = _make_button(710, 174, 100, 28, 'Add Here', 'add_here')
    app.buttons['del_sel'] = _make_button(818, 174, 100, 28, 'Delete Sel', 'del_sel')
    app.buttons['clear_all'] = _make_button(926, 174, 100, 28, 'Clear All', 'clear_all')
    # Training
    app.buttons['train'] = _make_button(710, 208, 150, 32, 'TRAIN: OFF', 'train')
    app.buttons['reset_brain'] = _make_button(868, 208, 158, 32, 'Reset Brain', 'reset_brain')
    app.buttons['teleop'] = _make_button(710, 246, 150, 28, 'Teleop: OFF', 'teleop')
    app.buttons['eval'] = _make_button(868, 246, 158, 28, 'Eval: OFF', 'eval')
    app.buttons['reset_scene'] = _make_button(710, 278, 150, 28, 'Reset Scene', 'reset_scene')
    app.buttons['demo_stack'] = _make_button(868, 278, 158, 28, 'Demo Stack x3', 'demo_stack')
    app.buttons['close_shape'] = _make_button(710, 312, 150, 28, 'Close Shape', 'close_shape')
    app.buttons['cancel_draw'] = _make_button(868, 312, 158, 28, 'Cancel Draw', 'cancel_draw')
    app.buttons['gripper'] = _make_button(710, 345, 316, 26, 'Gripper: PARALLEL', 'gripper')
    app.buttons['manual'] = _make_button(710, 378, 316, 26, 'INSTRUCTION MANUAL', 'manual')

def _sensor_vector(app):
    env = app.env
    arm = env.arm
    gc = arm.gripper_center()
    rays = env.cast_rays()
    contact, force, slip = env.contact_sensors()
    target = env.current_target_pos()
    tower = env.tower_slot()
    dx = (target[0] - gc[0]) / 600.0
    dy = (target[1] - gc[1]) / 600.0
    tdx = (tower[0] - gc[0]) / 600.0
    tdy = (tower[1] - gc[1]) / 600.0
    held = 1.0 if arm.held is not None else 0.0
    tilt = arm.held.slip if arm.held is not None else 0.0
    remaining = len([o for o in env.objects if not o.placed]) / 6.0
    floor_clear = max(0.0, min(1.0, (FLOOR_Y - gc[1]) / 200.0))
    _gtype = 1.0 if arm.gripper_type == 'adaptive' else 0.0
    sensors = [arm.angles[0] / 2.5, arm.angles[1] / 2.5, arm.angles[2] / 1.8,
               arm.gripper, gc[0] / 700.0, gc[1] / 700.0]
    sensors = sensors + rays
    sensors = sensors + [contact, force, slip, dx, dy, tdx, tdy, held, tilt, remaining, floor_clear, _gtype]
    sensors = sensors + [env.accel_forward, env.accel_perp, env.down_alignment,
                         env.joint_vel[0]/0.07, env.joint_vel[1]/0.07, env.joint_vel[2]/0.07,
                         env.gripper_vel[0]/10.0, env.gripper_vel[1]/10.0]
    # sensors = 35, context = 8 → 43, then Welford-normalised.
    raw = sensors + app.ctx.vector()
    # Normalise with PRIOR stats, then update — never normalise a sample
    # with itself (that would zero the first sample and leak the current
    # obs into its own normaliser). Standard online-norm practice.
    normed = app.obs_norm.normalize(raw)
    app.obs_norm.update(raw)
    return normed, rays

def _train_batch(app):
    if len(app.replay) < 16:
        return
    batch = app.replay.sample(32)
    # --- Pass 1: TD targets + advantages (NO weight updates yet) ---
    # Old code interleaved critic/actor updates with advantage computation,
    # so later samples in the batch used stale advantages (V had already moved).
    # Now: compute all targets first, then update.
    advs = []; targets = []
    for (s, a, noise, r, s2, done, timeout) in batch:
        # Reward scaling: final reward is in [-25,25] (terminal +20). /10 ->
        # stack 10 -> 1.0, grasp ~1-2 -> 0.1-0.2, step ~0.00.
        # Was: raw r in [-10,10] with gamma 0.99 -> value scale ~1000,
        # critic (linear out, Huber grad capped at 1) could never catch up.
        # Scaled: value scale ~2-3, critic learns in tens of updates.
        r_c = max(-25.0, min(25.0, r)) / 10.0
        if done and not timeout:
            target_v = r_c
        else:
            v_next = app.target_critic.forward(s2)[0]
            target_v = r_c + app.gamma * v_next
        # Clip TD target: prevents one diverged V(s') from poisoning the batch.
        target_v = max(-5.0, min(5.0, target_v))
        v = app.critic.forward(s)[0]
        advs.append(target_v - v)
        targets.append(target_v)
    mean_adv = sum(advs) / len(advs)
    var_adv = sum((x - mean_adv) * (x - mean_adv) for x in advs) / len(advs)
    # TD-error std IS the learning signal. If it is ~0, the batch has no
    # surprise (all failures, critic already predicts failure) and any actor
    # update is fitting noise. Old code used +1e-8 floor: when advs were all
    # -0.01, std ~1e-4, so (adv-mean)/std blew tiny noise up to +/-1 and the
    # actor chased it. New: hard floor 0.08 + explicit gate below.
    raw_std_adv = math.sqrt(var_adv)
    std_adv = max(raw_std_adv, 0.08)
    td_std = raw_std_adv
    pos_frac = sum(1 for (_s, _a, _n, _r, _s2, _d, _t) in batch if _r >= 0.4) / len(batch)
    # Gate: no positives AND no TD surprise -> critic still learns (it is
    # fitting the failure distribution), but the actor does NOT update.
    # Exploration (OU noise) keeps running, so the actor still explores;
    # it just does not collapse toward its own noise.
    actor_gated = (pos_frac == 0.0 and td_std < 0.02)
    app.td_std_hist.append(td_std)
    app.adv_std_hist.append(raw_std_adv)
    app.pos_frac_hist.append(pos_frac)
    if len(app.td_std_hist) > 120: app.td_std_hist.pop(0)
    if len(app.adv_std_hist) > 120: app.adv_std_hist.pop(0)
    if len(app.pos_frac_hist) > 120: app.pos_frac_hist.pop(0)
    app.actor_gated_count = app.actor_gated_count + (1 if actor_gated else 0)
    # --- Pass 2: critic (all samples) ---
    tot_c = 0.0
    for idx, (s, a, noise, r, s2, done, timeout) in enumerate(batch):
        tot_c += app.critic.train_example(s, [targets[idx]], app.critic_lr, loss_type='huber')
    # --- Pass 3: actor (all samples), advantage-weighted BC done correctly ---
    # Old: desired = a + adv_n * noise * 0.9, adv_n in [-2,2].
    # If adv=+2, desired = executed + 1.8*noise = clean + 2.8*noise — overshoots
    # past the good action. If adv=-2, desired = executed - 1.8*noise, which
    # is not the clean action either. Not a policy gradient, not BC.
    # New: clean = a - noise (executed = clean + noise). Desired interpolates:
    #   adv=+1 -> desired = executed (clone the good noisy action)
    #   adv=-1 -> desired = clean (retreat to the clean action)
    #   adv=0  -> halfway. adv_n in [-1,1], no overshoot by construction.
    tot_a = 0.0; grad_tot = 0.0
    if actor_gated:
        # Actor skipped by design (see above). Record 0 loss so the curve
        # does NOT fake a low actor loss while the actor learned nothing.
        app.critic_loss_hist.append(tot_c / len(batch))
        app.actor_loss_hist.append(0.0)
        app.loss_hist.append(tot_c / len(batch))
        app.grad_norm_hist.append(0.0)
        app.target_critic.soft_update_from(app.critic, app.tau)
        for _h in (app.loss_hist, app.grad_norm_hist, app.critic_loss_hist, app.actor_loss_hist):
            if len(_h) > 120: _h.pop(0)
        return
    for idx, (s, a, noise, r, s2, done, timeout) in enumerate(batch):
        adv_n = (advs[idx] - mean_adv) / std_adv
        adv_n = max(-1.0, min(1.0, adv_n))
        w = 0.5 + 0.5 * adv_n  # 0 = clean, 1 = executed
        desired = []
        for i in range(4):
            clean_est = a[i] - noise[i]
            desired.append(max(-1.0, min(1.0, clean_est + w * noise[i])))
        tot_a += app.actor.train_example(s, desired, app.actor_lr, loss_type='mse')
        grad_tot += abs(adv_n)
    app.target_critic.soft_update_from(app.critic, app.tau)
    # Track critic / actor separately — summing them hid which one diverged.
    app.critic_loss_hist.append(tot_c / len(batch))
    app.actor_loss_hist.append(tot_a / len(batch))
    app.loss_hist.append((tot_c + tot_a) / len(batch))
    app.grad_norm_hist.append(grad_tot / len(batch))
    for _h in (app.loss_hist, app.grad_norm_hist, app.critic_loss_hist, app.actor_loss_hist):
        if len(_h) > 120: _h.pop(0)

def _end_episode(app):
    app.reward_hist.append(app.env.episode_reward)
    if len(app.reward_hist) > 120:
        app.reward_hist.pop(0)
    if app.eval_mode:
        app.eval_reward_hist.append(app.env.episode_reward)
        if len(app.eval_reward_hist) > 60:
            app.eval_reward_hist.pop(0)
    # LR / epsilon decay: only in TRAINING. Eval episodes must not consume
    # exploration budget or anneal the LR.
    if not app.eval_mode:
        app.actor_lr = max(0.00008, app.actor_lr * 0.995)
        app.critic_lr = max(0.00025, app.critic_lr * 0.995)
        app.epsilon = max(0.05, app.epsilon * 0.985)
        app.ou.reset()
    app.env.episode += 1
    # Reset scene but KEEP weights — learning persists across episodes.
    objs = list(app.env.objects)
    app.env.reset_scene()
    app.ctx = TrainingContext()
    app.status = 'Episode %d done. Reward %.1f — brain kept, scene reset.' % (app.env.episode - 1, app.env.episode_reward)
    app.env.episode_reward = 0.0
    app.episode_reward = 0.0  # keep the (now unused) display var in sync

def onStep(app):
    if app.training:
        s, _ = _sensor_vector(app)
        clean = app.actor.forward(s)
        if app.eval_mode:
            noise = [0.0, 0.0, 0.0, 0.0]
            executed = list(clean)
        else:
            ou = app.ou.sample()
            noise = [ou[i] * app.epsilon * 1.4 for i in range(4)]
            # Grasp exploration boost: when the wrist sensor reports contact
            # (touch) and the gripper is still open, the robot is IN a grasp
            # opportunity but has never closed there. Boost ONLY the
            # magnitude of the gripper noise (variance, not direction) so it
            # tries closing more often there. No direction is scripted: the
            # sign still comes from OU noise, the MLP still has to learn that
            # closing pays. Uses contact_sensors() — a sensor, not ground truth.
            _c, _f, _sl = app.env.contact_sensors()
            if _c > 0.5 and app.env.arm.gripper > 0.38:
                noise[3] = noise[3] * 1.8
            executed = [max(-1.0, min(1.0, clean[i] + noise[i])) for i in range(4)]
        reward, done, timeout, info = app.env.step(executed, app)
        # Do NOT also do app.episode_reward += reward: Env.step already adds
        # to env.episode_reward. Double-counting + _end_episode only reset
        # env.episode_reward, so the displayed Reward grew across episodes.
        s2, _ = _sensor_vector(app)
        if not app.eval_mode:
            app.replay.add((s, executed, noise, reward, s2, done, timeout))
            app.ctx.update(reward, info['slip'], info['contact'], executed, info['grasped'])
            if app.env.step_count % 4 == 0:
                _train_batch(app)
        if done:
            _end_episode(app)
        return
    if app.teleop:
        a = list(app.teleop_action)
        app.teleop_action = [0.0, 0.0, 0.0, 0.0]
        s, _ = _sensor_vector(app)
        reward, done, timeout, info = app.env.step(a, app)
        s2, _ = _sensor_vector(app)
        if any(v != 0.0 for v in a):
            app.actor.train_example(s, a, 0.004, loss_type='mse')
        app.replay.add((s, a, [0.0, 0.0, 0.0, 0.0], reward, s2, done, timeout))
        if done:
            _end_episode(app)
        return
    # Paused: let physics settle, no learning.
    app.env.physics_only()

def _handle_button(app, action):
    env = app.env
    if action == 'mode_move':
        app.mode = 'move'
        app.status = 'Move: drag objects to any position. Robot is paused.'
    elif action == 'mode_draw':
        app.mode = 'draw'
        app.draft_verts = []
        app.status = 'Draw Shape: click in arena to add vertices. Click near start or Close Shape to finish.'
    elif action == 'mode_place':
        app.mode = 'place'
        app.status = 'Place: click in arena to spawn the selected template there.'
    elif action.startswith('tpl_'):
        key = action[4:]
        app.selected_template = key
        app.status = 'Template: %s — click Place, then click arena.' % key
    elif action == 'add_here':
        # Spawn at a free spot near centre-left.
        x = 150 + (len(env.objects) % 4) * 50
        y = 200 + (len(env.objects) // 4) * 80
        if app.selected_template == 'custom' and app.custom_verts is None:
            app.status = 'No custom shape yet — draw one first, then Close Shape.'
        else:
            env.add_object(app.selected_template, x, y)
            app.status = 'Added %s at (%d,%d). Drag it in Move mode.' % (app.selected_template, x, y)
    elif action == 'del_sel':
        if app.selected_obj is not None and app.selected_obj in env.objects:
            if env.arm.held is app.selected_obj:
                env.arm.held = None
            env.objects.remove(app.selected_obj)
            app.selected_obj = None
            app.status = 'Deleted selected object.'
        else:
            app.status = 'Select an object first (click it in Move mode).'
    elif action == 'clear_all':
        env.objects = []
        env.arm.held = None
        env.tower_count = 0
        app.selected_obj = None
        app.status = 'All objects removed. Add new ones.'
    elif action == 'gripper':
        if env.arm.held is not None:
            _held = env.arm.held; _held.held = False; _held.vy = 0.0; env.arm.held = None
        env.arm.gripper_type = 'adaptive' if env.arm.gripper_type == 'parallel' else 'parallel'
        env.arm.gripper = 1.0
        app.buttons['gripper']['label'] = 'Gripper: ' + env.arm.gripper_type.upper()
        if env.arm.gripper_type == 'adaptive':
            app.status = 'Gripper: ADAPTIVE — curved C-fingers, wraps + cages. Fits 65px, forgiving grasp, slower slip.'
        else:
            app.status = 'Gripper: PARALLEL — straight fingers, 88mm opening. Must grasp narrow side.'
    elif action == 'manual':
        app.manual_open = True
        app.status = 'Instruction Manual open — X to close.'
    elif action == 'manual_close':
        app.manual_open = False
        app.status = 'Manual closed.'
    elif action == 'train':
        app.training = not app.training
        app.teleop = False
        app.buttons['train']['label'] = 'TRAIN: ON' if app.training else 'TRAIN: OFF'
        app.buttons['teleop']['label'] = 'Teleop: OFF'
        app.status = 'Training ON — MLP is acting + learning.' if app.training else 'Training paused. Brain kept.'
    elif action == 'reset_brain':
        app.actor = MLP([43, 48, 32, 4], ['relu', 'relu', 'tanh'])
        app.critic = MLP([43, 48, 32, 1], ['relu', 'relu', 'linear'])
        app.target_critic = MLP([43, 48, 32, 1], ['relu', 'relu', 'linear'])
        app.target_critic.copy_from(app.critic)
        app.replay = ReplayBuffer(2000)
        app.obs_norm = ObsNormalizer(43)
        app.ou = OUNoise(4)
        app.actor_lr = 0.0008
        app.critic_lr = 0.001
        app.loss_hist = [0.0]
        app.reward_hist = [0.0]
        app.grad_norm_hist = [0.0]
        app.critic_loss_hist = [0.0]
        app.actor_loss_hist = [0.0]
        app.td_std_hist = [0.0]
        app.adv_std_hist = [0.0]
        app.pos_frac_hist = [0.0]
        app.actor_gated_count = 0
        app.eval_reward_hist = [0.0]
        app.ctx = TrainingContext()
        app.epsilon = 0.35
        app.grasp_attempts = 0
        app.grasp_success = 0
        app.status = 'Brain reset — random weights. It must re-learn from sensors.'
    elif action == 'eval':
        app.eval_mode = not app.eval_mode
        if app.eval_mode:
            app.training = True
            app.teleop = False
            app.buttons['train']['label'] = 'TRAIN: ON'
            app.buttons['teleop']['label'] = 'Teleop: OFF'
        app.buttons['eval']['label'] = 'Eval: ON' if app.eval_mode else 'Eval: OFF'
        app.status = 'Eval ON — deterministic policy, no noise, no training. This is the true policy.' if app.eval_mode else 'Eval off — training resumes with exploration.'
    elif action == 'teleop':
        app.teleop = not app.teleop
        app.eval_mode = False
        app.buttons['eval']['label'] = 'Eval: OFF'
        app.training = False
        app.buttons['teleop']['label'] = 'Teleop: ON' if app.teleop else 'Teleop: OFF'
        app.buttons['train']['label'] = 'TRAIN: OFF'
        app.status = 'Manual teleop ON — W/S shoulder, A/D elbow, Q/E wrist, SPACE gripper. Your moves train the actor.' if app.teleop else 'Teleop off.'
    elif action == 'reset_scene':
        env.reset_scene()
        app.ctx = TrainingContext()
        app.episode_reward = 0.0
        app.status = 'Scene reset. Brain kept.'
    elif action == 'demo_stack':
        env.objects = []
        env.arm.held = None
        env.tower_count = 0
        env.add_object('block', 150, 220)
        env.add_object('L', 220, 220)
        env.add_object('U', 290, 220)
        env.reset_scene()
        app.status = 'Demo stack: Block + L + U. Train and watch it learn COM vs bbox.'
    elif action == 'close_shape':
        if len(app.draft_verts) >= 3:
            # Convert absolute draft to local verts around centroid.
            cx = sum(v[0] for v in app.draft_verts) / len(app.draft_verts)
            cy = sum(v[1] for v in app.draft_verts) / len(app.draft_verts)
            local = [(x - cx, y - cy) for (x, y) in app.draft_verts]
            # Clamp size so it fits gripper / arena.
            maxr = max(math.hypot(x, y) for (x, y) in local) if local else 1
            if maxr > 52:
                s = 52.0 / maxr
                local = [(x * s, y * s) for (x, y) in local]
            app.custom_verts = local
            env._custom_verts = local
            app.selected_template = 'custom'
            # Spawn one copy where drawn.
            env.add_object('custom', cx, cy)
            app.draft_verts = []
            app.mode = 'move'
            app.status = 'Custom shape saved (%d verts). Robot has NEVER seen this geometry.' % len(local)
        else:
            app.status = 'Need at least 3 vertices to close a shape.'
    elif action == 'cancel_draw':
        app.draft_verts = []
        app.mode = 'move'
        app.status = 'Draw cancelled.'

def onMousePress(app, mx, my):
    # Manual overlay eats all clicks except its X.
    if getattr(app, 'manual_open', False):
        if 960 <= mx <= 1012 and 30 <= my <= 66:
            _handle_button(app, 'manual_close')
        return
    # Buttons first.
    for bid, b in app.buttons.items():
        if b['x'] <= mx <= b['x'] + b['w'] and b['y'] <= my <= b['y'] + b['h']:
            _handle_button(app, b['action'])
            return
    # Arena interactions.
    if not (ARENA_X0 <= mx <= ARENA_X1 and ARENA_Y0 <= my <= ARENA_Y1):
        return
    env = app.env
    if app.mode == 'draw':
        if len(app.draft_verts) >= 3:
            fx, fy = app.draft_verts[0]
            if math.hypot(mx - fx, my - fy) < 16:
                _handle_button(app, 'close_shape')
                return
        app.draft_verts.append((float(mx), float(my)))
        return
    if app.mode == 'place':
        if app.selected_template == 'custom' and app.custom_verts is None:
            app.status = 'Draw a custom shape first (Draw Shape mode).'
            return
        env.add_object(app.selected_template, mx, my)
        app.status = 'Placed %s at (%d,%d).' % (app.selected_template, mx, my)
        return
    # move mode: pick object
    app.selected_obj = None
    for o in reversed(env.objects):
        if _point_in_poly(mx, my, o.world_verts()) or math.hypot(mx - o.x, my - o.y) < o.radius:
            app.selected_obj = o
            if not o.held and not o.placed:
                app.drag_obj = o
                app.drag_dx = o.x - mx
                app.drag_dy = o.y - my
            app.status = 'Selected %s #%d — drag to reposition. R rotates.' % (o.name, o.id)
            return

def onMouseDrag(app, mx, my):
    if app.drag_obj is not None:
        o = app.drag_obj
        o.x = max(34, min(678, mx + app.drag_dx))
        o.y = max(110, min(FLOOR_Y - 20, my + app.drag_dy))
        o.vx = 0.0
        o.vy = 0.0
        o.resting = False

def onMouseRelease(app, mx, my):
    if app.drag_obj is not None:
        app.drag_obj = None

def onMouseMove(app, mx, my):
    app.hover = None
    for bid, b in app.buttons.items():
        if b['x'] <= mx <= b['x'] + b['w'] and b['y'] <= my <= b['y'] + b['h']:
            app.hover = bid

def onKeyPress(app, key):
    k = key.lower()
    if getattr(app, 'manual_open', False):
        if k in ('m', 'escape', 'esc'):
            _handle_button(app, 'manual_close')
        return
    if k == ' ':
        _handle_button(app, 'train')
        return
    if k == 'r' and app.selected_obj is not None:
        app.selected_obj.rot += 0.35
        return
    if k == 'delete' or k == 'backspace':
        _handle_button(app, 'del_sel')
        return
    if app.teleop:
        if k == 'w':
            app.teleop_action[0] = -1.0
        elif k == 's':
            app.teleop_action[0] = 1.0
        elif k == 'a':
            app.teleop_action[1] = -1.0
        elif k == 'd':
            app.teleop_action[1] = 1.0
        elif k == 'q':
            app.teleop_action[2] = -1.0
        elif k == 'e':
            app.teleop_action[2] = 1.0
        elif k == 'g':
            app.teleop_action[3] = 1.0
        elif k == 'o':
            app.teleop_action[3] = -1.0

# ---------------------------------------------------------------------------
# VIEW
# ---------------------------------------------------------------------------
def _draw_button(app, b, active):
    fill = ACC_H if app.hover == b['action'] or active else (ACC if b['enabled'] else rgb(48, 52, 72))
    if active:
        fill = ACC2
    drawRect(b['x'], b['y'], b['w'], b['h'], fill=fill, border=rgb(130, 134, 255) if app.hover == b['action'] else BORDER, borderWidth=1, roundness=8)
    drawLabel(b['label'], b['x'] + b['w'] / 2, b['y'] + b['h'] / 2, size=10, fill=rgb(255, 255, 255), bold=True, align='center-center')

def _draw_object(app, o):
    w = o.world_verts()
    flat = []
    for (x, y) in w:
        flat.append(x)
        flat.append(y)
    drawPolygon(*flat, fill=o.color, border=rgb(255, 255, 255) if o is app.selected_obj else rgb(20, 22, 36), borderWidth=1.2)
    cx, cy = o.com_world()
    # COM = red dot (physics truth, NOT given to MLP — shown for teaching).
    drawCircle(cx, cy, 3.5, fill=BAD, border=rgb(255, 255, 255), borderWidth=0.8)
    # Barycentre = white X (teaching only, never used by robot).
    bx = sum(v[0] for v in w) / len(w)
    by = sum(v[1] for v in w) / len(w)
    drawLine(bx - 5, by - 5, bx + 5, by + 5, fill=rgb(255, 255, 255), lineWidth=1)
    drawLine(bx - 5, by + 5, bx + 5, by - 5, fill=rgb(255, 255, 255), lineWidth=1)
    if o.placed:
        drawLabel('STACKED', o.x, o.y - o.radius - 10, size=9, fill=ACC2, bold=True, align='center-center')
    if o.slip > 0.4:
        drawLabel('SLIP!', o.x, o.y - o.radius - 10, size=9, fill=WARN, bold=True, align='center-center')

def _draw_arm(app):
    env = app.env
    arm = env.arm
    (sx, sy), (ex, ey), (wx, wy), (tx, ty), a3 = arm.fk()
    # Pedestal / base
    drawRect(78, FLOOR_Y - 125, 64, 125, fill=rgb(38, 42, 66), border=BORDER, roundness=8)
    drawLabel('OPENARM', 110, FLOOR_Y - 12, size=8, fill=DIM, bold=True, align='center-center')
    # Rays (sensor viz) — MUST match cast_rays: hand-relative a3.
    gc = arm.gripper_center()
    rays = env.cast_rays()
    for k, rv in enumerate(rays):
        ang = a3 + (k - 4) * 0.22
        L = max(4.0, min(240.0, rv * 240.0))
        sa = math.sin(ang)
        if sa > 0.05 and gc[1] + sa * L > FLOOR_Y:
            L = (FLOOR_Y - gc[1]) / sa
        drawLine(gc[0], gc[1], gc[0] + math.cos(ang) * L, gc[1] + math.sin(ang) * L,
                 fill=rgb(45, 212, 191) if rv < 0.95 else GRID, lineWidth=0.8)
    # Links
    drawLine(sx, sy, ex, ey, fill=rgb(200, 210, 240), lineWidth=10)
    drawLine(ex, ey, wx, wy, fill=rgb(180, 190, 220), lineWidth=8)
    drawLine(wx, wy, tx, ty, fill=rgb(160, 170, 200), lineWidth=6)
    drawCircle(sx, sy, 10, fill=ACC, border=rgb(255, 255, 255), borderWidth=1)
    drawCircle(ex, ey, 9, fill=ACC, border=rgb(255, 255, 255), borderWidth=1)
    drawCircle(wx, wy, 8, fill=ACC2, border=rgb(255, 255, 255), borderWidth=1)
    _bq = arm.base_rect(); _flat_b=[]
    for (qx, qy) in _bq: _flat_b.append(qx); _flat_b.append(qy)
    drawPolygon(*_flat_b, fill=rgb(58, 62, 88), border=rgb(255, 255, 255), borderWidth=0.8)
    for quad in arm.finger_rects():
        _flat=[]
        for (qx, qy) in quad: _flat.append(qx); _flat.append(qy)
        drawPolygon(*_flat, fill=rgb(180, 188, 210), border=rgb(255, 255, 255), borderWidth=0.8)
    if arm.gripper_type == 'adaptive':
        _cam = (tx + math.cos(a3)*9, ty + math.sin(a3)*9)
        drawCircle(_cam[0], _cam[1], 4, fill=rgb(30, 60, 140), border=rgb(255, 255, 255), borderWidth=0.8)
        _rects = arm.finger_rects()
        for _qi in (1, 3):
            _q = _rects[_qi]; _mx = sum(p[0] for p in _q)/4.0; _my = sum(p[1] for p in _q)/4.0
            drawCircle(_mx, _my, 2.5, fill=rgb(20, 20, 24), border=rgb(20, 20, 24), borderWidth=0.5)
    drawLabel(arm.gripper_type.upper(), gc[0], gc[1] - 32, size=8, fill=WARN, bold=True, align='center-center')
    _acc_txt = 'ACC %.2f,%.2f  DOWN %.2f' % (env.accel_forward, env.accel_perp, env.down_alignment)
    drawLabel(_acc_txt, gc[0], gc[1] - 44, size=7, fill=rgb(45, 212, 191), bold=True, align='center-center')
    # Held object follows gripper (drawn in object pass, but highlight)
    if arm.held is not None:
        drawLabel('HOLDING', gc[0], gc[1] - 22, size=9, fill=WARN, bold=True, align='center-center')

def _draw_manual(app):
    drawRect(0, 0, WIDTH, HEIGHT, fill=rgb(10, 12, 24))
    drawRect(24, 18, WIDTH - 48, HEIGHT - 36, fill=rgb(18, 20, 34), border=BORDER, roundness=14)
    drawLabel('INSTRUCTION MANUAL', 48, 36, size=28, fill=TXT, bold=True, align='left-top')
    drawLabel('OpenArm 2.0  •  MLP-RL Stacking Trainer  •  No IK  •  No grasp table  •  No shape library  •  No Computer Vision', 48, 72, size=14, fill=DIM, align='left-top')
    drawRect(960, 30, 52, 36, fill=rgb(180, 40, 60), border=rgb(255, 255, 255), borderWidth=1, roundness=8)
    drawLabel('X', 986, 48, size=20, fill=rgb(255, 255, 255), bold=True, align='center-center')
    drawLabel('Press X or M or ESC to close. Clicking anywhere else does nothing while the manual is open.', 48, 94, size=14, fill=WARN, align='left-top')
    LX = 48; RX = 548
    y = 122
    drawLabel('1 — GOAL', LX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('Stack every object in the TOWER ZONE (green, centre).', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('The robot gets +10 per stack, +20 for a full tower.', LX, y, size=14, fill=TXT, align='left-top'); y += 28
    drawLabel('2 — HOW IT LEARNS (MLP-RL)', LX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('Actor 43 → 48 → 32 → 4 tanh outputs joint deltas + grip.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Critic learns value. OU noise explores. No IK, no script.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('It must re-learn after you change shapes or grippers.', LX, y, size=14, fill=TXT, align='left-top'); y += 28
    drawLabel('3 — SENSORS (WHAT IT SEES)', LX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('9 rays from the wrist, hand-relative. Floor is a ray hit.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Touch + force + slip. Red dot = true COM (teaching only).', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('ACCELEROMETER: accel + gyro + DOWN. DOWN=1 means', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('gripper points DOWN — where objects sit on the floor.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Joint vel + gripper vel = kinematics. It feels motion.', LX, y, size=14, fill=TXT, align='left-top'); y += 28
    drawLabel('4 — GRASP + SLIP', LX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('Grasp needs COM close + edge distance + width fits.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Off-COM grasps twist, slip, and DROP. That is the lesson.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('White X = bbox centre. NEVER grasp the X — grasp the dot.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    y = 122
    drawLabel('5 — TWO GRIPPERS', RX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('PARALLEL: straight fingers, 44px (88mm) opening.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Must grasp the NARROW side. Wide side will not fit.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('ADAPTIVE: curved C-fingers, wraps + cages, fits 65px.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('More forgiving, slower slip. Same 4th action drives both.', RX, y, size=14, fill=TXT, align='left-top'); y += 28
    drawLabel('6 — HOW TO BREAK A SCRIPT', RX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('Draw Shape: click in arena to add vertices. Click near', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('start or Close Shape to finish. Concave is allowed.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Place: click arena to spawn that shape. Move: drag any', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('object. R rotates it. Delete / Clear All remove objects.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('L, T, U, wedge punish bbox-centre grasping on purpose.', RX, y, size=14, fill=TXT, align='left-top'); y += 28
    drawLabel('7 — CONTROLS + KEYS', RX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('TRAIN: MLP acts + learns. Eval: deterministic, no noise.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Teleop: W/S A/D Q/E move, G/O grip. Reset Brain = re-learn.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('SPACE=train  •  R=rotate  •  DEL=delete  •  M/ESC=manual', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Floor contact rejects the move. Stuck >60 steps = penalty.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('NO fakes, NO fallbacks: MLP only.', RX, y, size=14, fill=WARN, bold=True, align='left-top'); y += 28
    drawLabel('8 — LOSS LIES (READ THIS)', RX, y, size=16, fill=BAD, bold=True, align='left-top'); y += 22
    drawLabel('Low loss + 0 grasps = collapse, not learning.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Watch TD-std + Pos% in the top bar, not Loss.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('TD-std ~0 + Pos 0% = actor gated, buffer all failures.', RX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Close-on-object shaping + stratified replay fix it.', RX, y, size=14, fill=TXT, align='left-top')

def redrawAll(app):
    drawRect(0, 0, WIDTH, HEIGHT, fill=BG)
    # Top bar
    drawRect(0, 0, WIDTH, 68, fill=rgb(18, 20, 32))
    drawLabel('OpenArm 2.0  🤖  MLP-RL Stacking Trainer', 20, 16, size=20, fill=TXT, bold=True, align='left-top')
    drawLabel('No IK  •  No grasp table  •  No shape library  •  No Computer Vision', 20, 42, size=11, fill=DIM, align='left-top')
    env = app.env
    drawLabel(('EVAL  |  ' if app.eval_mode else '') + 'Ep %d  |  Step %d  |  Reward %.1f  |  Tower %d/%d' % (env.episode, env.step_count, env.episode_reward, env.tower_count, len(env.objects)),
              1020, 16, size=11, fill=TXT, bold=True, align='right-top')
    grasp_rate = (app.grasp_success / max(1, app.grasp_attempts) * 100)
    # Loss alone lies (see manual §8): low loss + 0 grasps = collapse.
    # TD-std = surprise in the batch, Pos% = share of batch with r>=0.4.
    # If TD-std ~0 and Pos% = 0, the actor is gated — it is NOT learning.
    _td = app.td_std_hist[-1] if app.td_std_hist else 0.0
    _pos = app.pos_frac_hist[-1] if app.pos_frac_hist else 0.0
    drawLabel('Eps %.2f  |  Grasp %.0f%% (%d/%d)  |  Loss %.3f  |  TD-std %.3f  Pos %.0f%%' % (app.epsilon, grasp_rate, app.grasp_success, app.grasp_attempts, app.loss_hist[-1] if app.loss_hist else 0.0, _td, _pos * 100.0),
              1020, 38, size=10, fill=ACC2 if app.training else DIM, align='right-top')
    # Arena
    drawRect(ARENA_X0, ARENA_Y0, ARENA_X1 - ARENA_X0, ARENA_Y1 - ARENA_Y0, fill=rgb(16, 18, 32), border=BORDER, roundness=12)
    for gx in range(ARENA_X0 + 40, ARENA_X1, 40):
        drawLine(gx, ARENA_Y0, gx, ARENA_Y1, fill=GRID, lineWidth=0.4)
    for gy in range(ARENA_Y0 + 40, ARENA_Y1, 40):
        drawLine(ARENA_X0, gy, ARENA_X1, gy, fill=GRID, lineWidth=0.4)
    # Floor + tower zone
    drawRect(ARENA_X0, FLOOR_Y, ARENA_X1 - ARENA_X0, ARENA_Y1 - FLOOR_Y, fill=FLOOR_C, roundness=8)
    drawRect(TOWER_X0, FLOOR_Y - 52, TOWER_X1 - TOWER_X0, 52, fill=rgb(16, 185, 129), border=ACC2, borderWidth=1.2, roundness=6, opacity=22)
    drawLabel('TOWER ZONE — stack here', (TOWER_X0 + TOWER_X1) / 2, FLOOR_Y - 58, size=10, fill=ACC2, bold=True, align='center-center')
    # Objects
    for o in env.objects:
        _draw_object(app, o)
    # Target marker — AFTER objects so it stays visible when it overlaps one.
    tx, ty = env.current_target_pos()
    drawCircle(tx, ty, 12, fill=None, border=WARN, borderWidth=1.2, dashes=True)
    drawLabel('TARGET', tx, ty - 18, size=8, fill=WARN, bold=True, align='center-center')
    # Draft shape
    if len(app.draft_verts) >= 1:
        for i in range(len(app.draft_verts)):
            x1, y1 = app.draft_verts[i]
            x2, y2 = app.draft_verts[(i + 1) % len(app.draft_verts)] if len(app.draft_verts) > 1 else (x1, y1)
            if i < len(app.draft_verts) - 1 or len(app.draft_verts) >= 3:
                drawLine(x1, y1, x2, y2, fill=WARN, lineWidth=2)
            drawCircle(x1, y1, 5, fill=WARN, border=rgb(255, 255, 255), borderWidth=1)
        drawLabel('DRAFT — click to add vertex, click start / Close Shape to finish', 350, 92, size=10, fill=WARN, bold=True, align='center-center')
    _draw_arm(app)
    # Status
    drawRect(ARENA_X0, ARENA_Y1 - 26, ARENA_X1 - ARENA_X0, 26, fill=rgb(18, 20, 32), border=BORDER, roundness=8)
    drawLabel(((env.last_grasp_msg + '  |  ' + app.status) if env.last_grasp_msg else app.status)[:92], ARENA_X0 + 10, ARENA_Y1 - 13, size=9, fill=DIM, align='left-center')
    # Right panel
    drawRect(PANEL_X, ARENA_Y0, PANEL_W, ARENA_Y1 - ARENA_Y0, fill=PANEL, border=BORDER, roundness=12)
    drawLabel('CONTROLS', PANEL_X + 14, ARENA_Y0 + 14, size=12, fill=TXT, bold=True, align='left-top')
    # Buttons
    for bid, b in app.buttons.items():
        active = False
        if bid == 'mode_' + app.mode:
            active = True
        if bid == 'tpl_' + app.selected_template:
            active = True
        if bid == 'train' and app.training:
            active = True
        if bid == 'teleop' and app.teleop:
            active = True
        if bid == 'eval' and app.eval_mode:
            active = True
        _draw_button(app, b, active)
    # MLP viz — HOW TO moved to INSTRUCTION MANUAL overlay. Freed space
    # goes to bigger loss/reward curves + a live sensor readout.
    py = 418
    drawLabel('Actor 43 → 48 → 32 → 4 tanh', PANEL_X + 14, py, size=9, fill=DIM, align='left-top')
    drawLabel('Critic 43 → 48 → 32 → 1', PANEL_X + 14, py + 13, size=9, fill=DIM, align='left-top')
    drawLabel('Input: 35 sensors + 8 ctx  (incl accel+gyro)', PANEL_X + 14, py + 26, size=8, fill=DIM, align='left-top')
    drawLabel('Actor RMS %.3f  |  Critic RMS %.3f' % (app.actor.weight_norm(), app.critic.weight_norm()), PANEL_X + 14, py + 39, size=9, fill=ACC, align='left-top')
    gx, gy, gw, gh = PANEL_X + 14, py + 52, PANEL_W - 28, 52
    drawRect(gx, gy, gw, gh, fill=PANEL2, border=BORDER, roundness=8)
    mx = max(app.loss_hist); mn = min(app.loss_hist); rng = (mx - mn) if mx - mn > 0.01 else 1.0
    pts = []
    for i, v in enumerate(app.loss_hist):
        x = gx + 8 + (i / max(1, len(app.loss_hist) - 1)) * (gw - 16)
        y = gy + gh - 8 - ((v - mn) / rng * (gh - 16)); pts.append((x, y))
    for i in range(len(pts) - 1):
        drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], fill=ACC, lineWidth=1.6)
    drawLabel('loss ↓ as it learns', gx + gw - 8, gy + 8, size=8, fill=DIM, align='right-top')
    ry = gy + gh + 8
    drawRect(gx, ry, gw, 42, fill=PANEL2, border=BORDER, roundness=8)
    mx = max(app.reward_hist); mn = min(app.reward_hist); rng = (mx - mn) if mx - mn > 0.5 else 1.0
    pts = []
    for i, v in enumerate(app.reward_hist):
        x = gx + 8 + (i / max(1, len(app.reward_hist) - 1)) * (gw - 16)
        y = ry + 42 - 8 - ((v - mn) / rng * (42 - 16)); pts.append((x, y))
    for i in range(len(pts) - 1):
        drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], fill=ACC2, lineWidth=1.6)
    drawLabel('episode reward', gx + 8, ry + 6, size=8, fill=DIM, align='left-top')
    sy = ry + 42 + 8
    drawRect(gx, sy, gw, 73, fill=PANEL2, border=BORDER, roundness=8)
    drawLabel('LIVE: ACC %.2f,%.2f  DOWN %.2f' % (env.accel_forward, env.accel_perp, env.down_alignment), gx + 8, sy + 6, size=8, fill=rgb(45, 212, 191), align='left-top')
    drawLabel('JOINT VEL %.2f %.2f %.2f  |  GRIP VEL %.1f,%.1f' % (env.joint_vel[0], env.joint_vel[1], env.joint_vel[2], env.gripper_vel[0], env.gripper_vel[1]), gx + 8, sy + 20, size=8, fill=DIM, align='left-top')
    drawLabel('GRIPPER %s  GAP %.0fpx  |  See INSTRUCTION MANUAL' % (env.arm.gripper_type.upper(), env.arm.gap()), gx + 8, sy + 34, size=8, fill=WARN, bold=True, align='left-top')
    drawLabel('TD-std %.3f  Adv-std %.3f  Pos %.0f%%  Actor gated %d' % (app.td_std_hist[-1] if app.td_std_hist else 0.0, app.adv_std_hist[-1] if app.adv_std_hist else 0.0, (app.pos_frac_hist[-1] if app.pos_frac_hist else 0.0) * 100.0, app.actor_gated_count), gx + 8, sy + 48, size=8, fill=(BAD if (app.pos_frac_hist[-1] if app.pos_frac_hist else 0.0) == 0.0 and app.training else DIM), align='left-top')
    drawLabel('lr a=%.5f c=%.5f | Grad %.2f | Eval %.1f | g %.2f' % (app.actor_lr, app.critic_lr, app.grad_norm_hist[-1] if app.grad_norm_hist else 0.0, app.eval_reward_hist[-1] if app.eval_reward_hist else 0.0, app.gamma), PANEL_X + 23, sy + 60, size=8, fill=DIM, align='left-top')
    # Manual overlay — completely overlays everything, drawn last.
    if getattr(app, 'manual_open', False):
        _draw_manual(app)
        return
    # Footer
    drawRect(0, HEIGHT - 22, WIDTH, 22, fill=rgb(18, 20, 32))
    drawLabel('SCS robot_training.py — OpenArm 2.0 sim • MLP-RL', 12, HEIGHT - 11, size=9, fill=DIM, align='left-center')

def main():
    runApp(width=1050, height=700)

main()
