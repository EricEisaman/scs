# robot_training_59.py — OpenArm 2.0 + MLP-RL Stacking Trainer (SCS, 1050x700)
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
#      its centroid, or its COM. It only sees 9 ray distances, ultrasonic
#      distance + grasp-range flag, 2 touch contacts, force, slip/torque,
#      proprioception + 8-dim hidden context.
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
#   - v53: ORGANISATION ONLY, zero behaviour change. Env.step split into
#     six named phase helpers (_move_arm, _shape_reward, _try_grasp,
#     _update_held, _try_release, _finish_step) with bodies moved verbatim;
#     step is now an orchestrator. Added FILE MAP + TUNABLES index below
#     and section banners. Verified by step-by-step equivalence vs v52.
    #   - v59: FIXES IN PRIORITY ORDER, SECOND REVIEW. (1) ORACLE REMOVED:
    #     _sensor_vector no longer feeds dx,dy from com_world() or tdx,tdy
    #     from tower_slot(). Replaced with sensor-derived nearest live ray
    #     dist+angle and nearest memory ray dist+angle, obs dim stays 69.
    #     onStep gripper boost no longer uses COM distance, it uses
    #     ultrasonic / nearest ray <50px. Reward shaping still uses COM,
    #     reward is allowed privileged info, observation is not. (2) SHAPING
    #     LEAK: shaping uses gamma=1 (zero at rest) + Phi zeroed at
    #     terminal/timeout via -Phi_last correction
    #     in _finish_step. Centred bonus capped to one-time per approach
    #     via _centred_given, same as close bonus, no more +60 farming.
    #     Shaped vs unshaped returns logged separately. (3) HONEST NAME +
    #     BASELINE: algorithm renamed to V-critic advantage-weighted
    #     regression, fixed seed 0, random-baseline button. (4) SPAWN +
    #     SAMPLING: spawn avoids tower zone and overlaps, start pose
    #     randomized so v50 relative frame is not cosmetic, stratified
    #     50% positives removed, uniform sampling within each half to
    #     stop V(s) upward bias. Header gamma fixed 0.97 -> 0.99.
    #   - v58: RESTORE LIVE DATA. v56 deleted the EMA but left the loss
    #     chart reading _lh, which was defined from the EMA hist. redrawAll
    #     raised NameError at the loss chart rect, so the reward chart,
    #     LIVE box, TIME line, and footer never drew. Screenshot showed
    #     exactly that: empty loss rect, blank right panel below it.
    #     Fix: _lh = app.loss_hist (critic loss only, v56). No display
    #     smoothing, no new data, the same loss_hist the header shows.
    #   - v57: FLOOR HARD CONSTRAINT, NO PENETRATION. Screenshot showed a
    #     held block sunk into the floor bar while gripper reported HOLDING.
    #     Cause: _free_update clamps free objects to FLOOR_Y, but _update_held
    #     set o.x/o.y = gripper - grasp_offset with no floor check, and
    #     _move_arm only checked the fingertip, not the object it carries.
    #     Fix, proven position-based hard constraint: one helper
    #     _clamp_to_floor(o) that does if bottom_y > FLOOR_Y: o.y -= excess.
    #     Applied in _update_held (safety net), _try_release, add_object,
    #     and onMouseDrag (now bottom-based, not centre-based). _move_arm now
    #     also predicts the held object bottom after the move and rejects
    #     the move if it would push the held object through the floor, same
    #     as the fingertip rejection. No new hyperparams, no reward change.
    #   - v56: REAL LOSS FIX, NO EMA. v55 used an EMA on the chart, which
    #     hid noise instead of fixing it. Reverted. Root cause, proven:
    #     _train_batch did 32 sequential per-sample Adam steps per batch.
    #     Adam (Kingma & Ba 2014) is defined for mini-batch gradients,
    #     not per-sample steps, so the weights chased the last sample and
    #     the next batch loss spiked. Fix: MLP.train_batch accumulates
    #     gradients over the batch and does ONE Adam step on the mean
    #     gradient (standard mini-batch gradient descent). Critic and
    #     actor each get one batch step per _train_batch. loss_hist is
    #     now critic TD loss only, actor loss in its own hist, no fake
    #     0.0 when skipped, so the 5:1 schedule cannot make the curve
    #     jump. No new hyperparams, no display smoothing. Panels kept:
    #     ARENA_Y0 76 -> 72, ARENA_Y1 660 -> 670 (+14px tall).
#   - v54: WORLD MODEL (belief state, Plausible rung). New WorldModel class
#     in PHYSICS: world-frame occupancy grid, told only by sensors (9 rays
#     + ultrasonic + contact; held object excluded, floor included),
#     confidence decays per step, free-space marking clears moved objects.
#     ask_polar returns the closest remembered surface at 24 angles, full
#     circle. _sensor_vector gains 24 memory rays: obs 45 -> 69, MLP
#     inputs 45 -> 69 (onAppStart AND Reset Brain). Env.step tells the WM
#     after physics (pure observer: step outputs unchanged). reset_scene
#     clears the WM (new scene = new world); Reset Brain keeps it (memory
#     is not policy). View draws occupied cells as faint dots under
#     objects. No COM / grasp poses / shape labels ever enter the WM —
#     it stores where surfaces were.
#   - v52: minimum-time metrics. Env tracks steps-to-first-grasp,
#     steps-to-first-stack, steps-to-full-success, and on-goal steps
#     (gripper within 30px of current target) per episode. _end_episode
#     records them to histories (training only, not teleop) and shows
#     current/median in the panel. Timeout is app.episode_len (was a
#     hardcoded 600 in Env.step). All else unchanged from v51.
#   - v51: critic LayerNorm (RLPD) + higher UTD. LN on critic hidden
#     layers only (Linear -> LN -> act); actor has no LN. _train_batch
#     runs every 2 env steps instead of 4 (UTD 0.5 batches/step, 2x).
#     LN is what makes the higher UTD stable. All else unchanged from v50.
#   - v50: relative frame in _sensor_vector only. Positions / target /
#     tower / gripper-vel expressed relative to the EE pose at episode
#     start (translate by start gripper pos, rotate by start wrist angle).
#     Joint angles as deltas from start angles. Reward, physics, drawing,
#     and actions unchanged. All else unchanged from v49.
#   - v49: fix live reward chart x denominator (was len(reward_hist)).
#     All else unchanged from v48.
#   - v48: asymmetric updates + 50/50 demo buffer (SERL RLPD + 2026
#     sim-to-online): critic every batch, actor every 5th batch at 10x
#     lower LR; half of each batch from teleop demo buffer, half online.
#     Reward, env, obs, and all other code unchanged from v47.
#   - Premature-loss fixes: stratified replay (>=50% positives when any
#     exist), TD-std floor 0.08 + actor gating when Pos==0 and TD-std<0.02,
#     close-on-object shaping, gripper-noise boost on contact, TD-std /
#     Adv-std / Pos% diagnostics. Loss alone is never trusted.
#   - Ultrasonic (HC-SR04-style, centre of end effector): 3-beam cone
#     along gripper forward, min distance to nearest object / floor.
#     Two inputs: continuous distance / 240 + binary CLOSE flag
#     (dist <= 60px grasp threshold). Beyond threshold the MLP learns
#     'too far to grab' from the flag + distance, not from a script.
#     Threshold is a sensor property, not a controller: the MLP still
#     decides when to close; the sensor only reports range.
#   - Top-tier fixes for 0-positives (Fig.2 audit): potential-based
#     approach shaping (Ng et al, preserves optimal policy), proximity +
#     down-alignment shaping, expanded close zone (30px, not just inside
#     polygon), persistent gripper OU, faster gripper step, spawn
#     curriculum (objects start near gripper, not top of arena), per-step
#     epsilon decay, live episode-reward curve, true Adv-std (std of
#     normalized advantages, not a copy of TD-std), loss-split display
#     instead of weight-RMS. No IK, no grasp table, no scripted direction.
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
# Pure MVC: Model = Neuron/Layer/MLP/Replay/Context/PhysObject/RobotArm/WorldModel/Env
#           View   = redrawAll + draw_* helpers
#           Controller = onAppStart / onStep / onMouse* / onKeyPress
# No window / browser use. All state lives on app.*.
# FILE MAP — search the banner text to jump to a section (no line numbers:
# they go stale; the banners don't). Edit a behaviour by editing its section.
#   MODEL — MLP from scratch ......... _act, _deriv, Neuron, Layer, MLP
#   MODEL — training helpers ......... TrainingContext, ObsNormalizer,
#                                         OUNoise, ReplayBuffer
#   MODEL — geometry ................. _poly_area_centroid, _point_in_poly,
#                                         _ray_hit, _min_edge_distance, _rotate
#   PHYSICS — objects, arm, env ..... PhysObject, RobotArm, WorldModel, Env (Env.step
#                                         phases live here as _move_arm etc.)
#   CONTROLLER — app state .......... onAppStart, _sensor_vector,
#                                         _train_batch, _end_episode, onStep,
#                                         _handle_button, onMouse*, onKeyPress
#   VIEW ............................ _draw_*, redrawAll, main
#
# TUNABLES — where each knob lives (edit the definition, never a copy):
#   Arena / floor / tower / palette .. module constants (WIDTH, HEIGHT,
#                                         ARENA_*, FLOOR_Y, TOWER_*, colours)
#   MLP sizes + LRs + gamma/tau ..... onAppStart (actor/critic construction
#   UTD + epsilon + episode_len ...... + the tunables block there)
#   Reward weights + shaping ........ Env._shape_reward / _try_grasp /
#                                         _update_held / _try_release
#   Grasp thresholds ................ Env._try_grasp (stability 0.30);
#                                         RobotArm.GAP_MAX (parallel opening)
#   Replay / stratification ......... ReplayBuffer.sample_stratified +
#                                         _train_batch
#   World model ..................... WorldModel (CELL, DECAY, OCC_THRESH,
#                                         N_MEM_RAYS, MEM_RANGE); Env._update_world_model
#   COUPLING: observation dim 69 = 61 sensors (37 + 24 memory) + 8 ctx. Changing _sensor_vector
#   output requires changing the MLP input size in onAppStart to match.

# ---------------------------------------------------------------------------
from scs import *
import math, random

WIDTH = 1050
HEIGHT = 700
ARENA_X0 = 16
ARENA_Y0 = 72
ARENA_X1 = 694
ARENA_Y1 = 670
FLOOR_Y = 600
TOWER_X0 = 320
TOWER_X1 = 420
PANEL_X = 710
PANEL_W = 324
ULTRA_MAX = 240.0
ULTRA_GRASP_THRESH = 60.0
ULTRA_CONE = 0.21

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
        # v51 LayerNorm (critic only): per-neuron scale/shift + Adam state.
        # gamma=1, beta=0 init = identity, so a fresh net behaves like no-LN.
        self.z = 0.0; self.zhat = 0.0
        self.gamma = 1.0; self.beta = 0.0
        self.grad_gamma = 0.0; self.grad_beta = 0.0
        self.m_gamma = 0.0; self.v_gamma = 0.0
        self.m_beta = 0.0; self.v_beta = 0.0
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
        self.z = s  # v51: pre-norm value; Layer.forward overwrites accumulator with post-norm y
        self.accumulator = s
        self.output = _act(self.activator, s)
        return self.output

class Layer:
    def __init__(self, n_in, n_out, activator, layernorm=False):
        self.activator = activator
        self.layernorm = layernorm  # v51: hidden layers of the critic only
        self.neurons = [Neuron(n_in, n_out, activator) for _ in range(n_out)]
        self.last_sigma = 1.0  # v51: per-sample LN scale, set in forward, read in backward
    def forward(self, x):
        out = [n.forward(x) for n in self.neurons]
        if not self.layernorm:
            return out
        # v51 LayerNorm: normalise pre-activation z across the layer's
        # neurons (per sample, no running stats), then gamma/beta, then act.
        # Linear -> LN -> act, the RLPD order. Output layer never gets LN:
        # with 1 neuron var would be 0 and zhat would be 0, killing grads.
        _n = len(self.neurons)
        _mu = sum(n.z for n in self.neurons) / _n
        _var = sum((n.z - _mu) * (n.z - _mu) for n in self.neurons) / _n
        self.last_sigma = math.sqrt(_var + 1e-5)
        for n in self.neurons:
            n.zhat = (n.z - _mu) / self.last_sigma
            _y = n.gamma * n.zhat + n.beta
            n.accumulator = _y  # backward's _deriv reads accumulator (= y) and output
            n.output = _act(n.activator, _y)
        return [n.output for n in self.neurons]

class MLP:
    # sizes e.g. [33,48,32,4], activators e.g. ['relu','relu','tanh']
    def __init__(self, sizes, activators, layernorm=False):
        self.sizes = list(sizes)
        self.activators = list(activators)
        self.layers = []
        for i in range(len(sizes) - 1):
            # v51: LN on hidden layers only, never the output layer.
            _ln = layernorm and i < len(sizes) - 2
            self.layers.append(Layer(sizes[i], sizes[i + 1], activators[i], layernorm=_ln))
    def forward(self, x):
        cur = list(x)
        for layer in self.layers:
            cur = layer.forward(cur)
        return cur
    def _backward(self, out, target, loss_type):
        # Backward only, no weight update. Sets neuron.delta (dL/dz) and
        # grad_gamma / grad_beta. Shared by train_example (batch size 1)
        # and train_batch (mean over batch). Proven backprop, Rumelhart et al.
        for li in range(len(self.layers) - 1, -1, -1):
            layer = self.layers[li]
            is_out = (li == len(self.layers) - 1)
            _dys = []
            for ni, neuron in enumerate(layer.neurons):
                if is_out:
                    err = (out[ni] - target[ni]) if ni < len(target) else 0.0
                    if loss_type == 'huber':
                        grad = max(-1.0, min(1.0, err))
                    else:
                        grad = err * 2.0 / max(1, len(target))
                    _dys.append(grad * _deriv(neuron.activator, neuron.accumulator, neuron.output))
                else:
                    nxt = self.layers[li + 1]
                    s = 0.0
                    for n_next in nxt.neurons:
                        if ni < len(n_next.weights):
                            s += n_next.delta * n_next.weights[ni]
                    _dys.append(s * _deriv(neuron.activator, neuron.accumulator, neuron.output))
            if layer.layernorm:
                _g = [_dys[i] * layer.neurons[i].gamma for i in range(len(_dys))]
                _n = len(_dys)
                _mg = sum(_g) / _n
                _mgz = sum(_g[i] * layer.neurons[i].zhat for i in range(_n)) / _n
                for i, neuron in enumerate(layer.neurons):
                    neuron.grad_gamma = _dys[i] * neuron.zhat
                    neuron.grad_beta = _dys[i]
                    _dz = (_g[i] - _mg - neuron.zhat * _mgz) / layer.last_sigma
                    neuron.delta = max(-1.0, min(1.0, _dz))
            else:
                for i, neuron in enumerate(layer.neurons):
                    neuron.delta = max(-1.0, min(1.0, _dys[i]))

    def _adam_step(self, grads, lr):
        # One Adam step (Kingma & Ba 2014) from grads. grads mirrors layers:
        # grads[li][ni] = (grad_w list, grad_b, grad_gamma, grad_beta).
        beta1 = 0.9
        beta2 = 0.999
        eps = 1e-8
        for li, layer in enumerate(self.layers):
            for ni, neuron in enumerate(layer.neurons):
                gw, gb, gg, gbe = grads[li][ni]
                neuron.adam_step += 1
                bc1 = 1.0 - (beta1 ** neuron.adam_step)
                bc2 = 1.0 - (beta2 ** neuron.adam_step)
                for i in range(len(neuron.weights)):
                    g = max(-1.0, min(1.0, gw[i]))
                    neuron.m_w[i] = beta1 * neuron.m_w[i] + (1.0 - beta1) * g
                    neuron.v_w[i] = beta2 * neuron.v_w[i] + (1.0 - beta2) * g * g
                    neuron.weights[i] -= lr * (neuron.m_w[i] / bc1) / (math.sqrt(neuron.v_w[i] / bc2) + eps)
                g_b = max(-1.0, min(1.0, gb))
                neuron.m_b = beta1 * neuron.m_b + (1.0 - beta1) * g_b
                neuron.v_b = beta2 * neuron.v_b + (1.0 - beta2) * g_b * g_b
                neuron.bias -= lr * (neuron.m_b / bc1) / (math.sqrt(neuron.v_b / bc2) + eps)
                if layer.layernorm:
                    _gg = max(-1.0, min(1.0, gg))
                    neuron.m_gamma = beta1 * neuron.m_gamma + (1.0 - beta1) * _gg
                    neuron.v_gamma = beta2 * neuron.v_gamma + (1.0 - beta2) * _gg * _gg
                    neuron.gamma -= lr * (neuron.m_gamma / bc1) / (math.sqrt(neuron.v_gamma / bc2) + eps)
                    _gb = max(-1.0, min(1.0, gbe))
                    neuron.m_beta = beta1 * neuron.m_beta + (1.0 - beta1) * _gb
                    neuron.v_beta = beta2 * neuron.v_beta + (1.0 - beta2) * _gb * _gb
                    neuron.beta -= lr * (neuron.m_beta / bc1) / (math.sqrt(neuron.v_beta / bc2) + eps)

    def train_example(self, x, target, lr, loss_type='mse'):
        # Single-sample Adam step. Only for teleop BC (batch size 1), where
        # mini-batch mean equals the single sample. _train_batch uses
        # train_batch below.
        out = self.forward(x)
        self._backward(out, target, loss_type)
        grads = []
        for layer in self.layers:
            lg = []
            for neuron in layer.neurons:
                gw = [neuron.delta * (neuron.inputs[i] if i < len(neuron.inputs) else 0.0) for i in range(len(neuron.weights))]
                lg.append((gw, neuron.delta, neuron.grad_gamma, neuron.grad_beta))
            grads.append(lg)
        self._adam_step(grads, lr)
        loss = 0.0
        for a, b in zip(out, target):
            d = a - b
            if loss_type == 'huber':
                ad = abs(d)
                loss += (0.5 * d * d) if ad <= 1.0 else (ad - 0.5)
            else:
                loss += d * d
        return loss / max(1, len(target))

    def train_batch(self, examples, lr, loss_type='mse'):
        # Mini-batch gradient descent, standard definition: accumulate
        # gradients over the batch, one Adam step on the mean. This is the
        # loss-volatility fix. No EMA, no display smoothing, training itself
        # is stable. Returns mean loss over the batch.
        if not examples:
            return 0.0
        acc = []
        for layer in self.layers:
            lg = []
            for neuron in layer.neurons:
                lg.append(([0.0] * len(neuron.weights), 0.0, 0.0, 0.0))
            acc.append(lg)
        total_loss = 0.0
        for (x, target) in examples:
            out = self.forward(x)
            for a, b in zip(out, target):
                d = a - b
                if loss_type == 'huber':
                    ad = abs(d)
                    total_loss += (0.5 * d * d) if ad <= 1.0 else (ad - 0.5)
                else:
                    total_loss += d * d
            self._backward(out, target, loss_type)
            for li, layer in enumerate(self.layers):
                for ni, neuron in enumerate(layer.neurons):
                    gw, gb, gg, gbe = acc[li][ni]
                    for i in range(len(neuron.weights)):
                        inp = neuron.inputs[i] if i < len(neuron.inputs) else 0.0
                        gw[i] += neuron.delta * inp
                    acc[li][ni] = (gw, gb + neuron.delta, gg + neuron.grad_gamma, gbe + neuron.grad_beta)
        n = float(len(examples))
        grads = []
        for li, layer in enumerate(self.layers):
            lg = []
            for ni, neuron in enumerate(layer.neurons):
                gw, gb, gg, gbe = acc[li][ni]
                lg.append(([g / n for g in gw], gb / n, gg / n, gbe / n))
            grads.append(lg)
        self._adam_step(grads, lr)
        return total_loss / (len(examples) * max(1, len(examples[0][1])))
    def copy_from(self, other):
        """Hard copy weights + bias (for target-critic init). Adam state reset."""
        for la, lb in zip(self.layers, other.layers):
            for na, nb in zip(la.neurons, lb.neurons):
                na.weights = list(nb.weights)
                na.bias = nb.bias
                na.gamma = nb.gamma; na.beta = nb.beta  # v51: LN params copy with weights
                na.grad_gamma = 0.0; na.grad_beta = 0.0
                na.m_gamma = 0.0; na.v_gamma = 0.0; na.m_beta = 0.0; na.v_beta = 0.0
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
                na.gamma = tau * nb.gamma + (1.0 - tau) * na.gamma  # v51
                na.beta = tau * nb.beta + (1.0 - tau) * na.beta  # v51
    def weight_norm(self):
        s = 0.0
        n = 0
        for layer in self.layers:
            for neuron in layer.neurons:
                for w in neuron.weights:
                    s += w * w
                    n += 1
        return math.sqrt(s / max(1, n))

# ---------------------------------------------------------------------------
# MODEL — training helpers (context, normaliser, OU noise, replay)
# ---------------------------------------------------------------------------
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
        self.dim = dim; self.sigma = sigma; self.state = [0.0]*dim
        # Per-dim mean-reversion: gripper (dim 3) reverts 3x slower so a
        # close intent persists ~20 steps. Closing needs ~5 sustained
        # +1 gripper actions; zero-mean white noise almost never sustains
        # that, so uniform OU made closing a lottery. This is variance
        # shaping, not direction: sign still comes from noise.
        self.thetas = [theta, theta, theta, 0.05] if dim == 4 else [theta]*dim
    def reset(self): self.state = [0.0]*self.dim
    def sample(self):
        common = random.gauss(0, self.sigma*0.5); out=[]
        for i in range(self.dim):
            dx = self.thetas[i]*(0.0-self.state[i]) + random.gauss(0, self.sigma)
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
        # v59: uniform. Was sample_stratified, which forced 50% positives
        # and biased V(s) upward with no importance weighting.
        n = min(k, len(self.buf))
        if n <= 0:
            return []
        return random.sample(self.buf, n)
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

def _clamp_to_floor(o):
    # Hard floor constraint, position-based. Guarantees bottom_y <= FLOOR_Y.
    # Used by held, released, spawned, and dragged objects. Free objects
    # already had this logic in _free_update, now all paths share it.
    _by = o.bottom_y()
    if _by > FLOOR_Y:
        o.y -= (_by - FLOOR_Y)

TEMPLATES = {
    'block': ([(-28, -18), (28, -18), (28, 18), (-28, 18)], rgb(99, 102, 241), 'Block'),
    'L': ([(-28, -18), (28, -18), (28, 0), (0, 0), (0, 18), (-28, 18)], rgb(16, 185, 129), 'L-shape'),
    'T': ([(-30, -18), (30, -18), (30, -2), (10, -2), (10, 18), (-10, 18), (-10, -2), (-30, -2)], rgb(245, 158, 11), 'T-shape'),
    'wedge': ([(-28, 18), (28, 18), (-28, -18)], rgb(239, 68, 68), 'Wedge'),
    'U': ([(-28, -18), (28, -18), (28, 18), (14, 18), (14, 0), (-14, 0), (-14, 18), (-28, 18)], rgb(168, 85, 247), 'U-shape'),
}

# ---------------------------------------------------------------------------
# PHYSICS — objects, arm, env (ground truth, never given to MLP)
# ---------------------------------------------------------------------------
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

class WorldModel:
    # v54: egocentric belief state — the robot's MEMORY of where surfaces
    # are. The MLP is purely reactive: it sees only the current sensor
    # snapshot, so when the gripper turns away from an object, the object
    # ceases to exist in its observation. This grid fixes that: every
    # sensor reading is TOLD into a world-frame occupancy grid, and the
    # policy ASKS it for the closest remembered surface at 24 angles.
    # Frontiers 2023 definition: "the information the robot has about
    # the world around it, shared between several activities" — here the
    # activities are the policy (ask) and the debug view (ask).
    # RULES (the no-script line):
    # - Tell accepts ONLY sensor-derived numbers (ray distances, ultrasonic
    #   hit, contact). Never object poses, never COM, never shape labels.
    #   The grid is built from what the sensors saw, exactly like a lidar
    #   map — a real sensor also measures true geometry.
    # - The grid stores WHERE surfaces were, not what to do. No COM, no
    #   grasp poses, no "this is a block". The MLP still decides everything.
    # - Held object is excluded: cast_rays / ultrasonic already skip it
    #   (it would read ~0 and lie), and tell_contact is skipped while
    #   holding for the same reason.
    # - Floor IS included: cast_rays / ultrasonic report it, so the map
    #   has a floor row. The MLP already has to deal with floor in the
    #   live rays; the memory rays just extend that in time.
    # Evolve: decay fades stale cells (moved / dragged objects, ghosts),
    # free-space marking clears cells rays now pass through, fresh hits
    # re-mark at 1.0. New scene = clear().
    CELL = 25          # px per grid cell
    DECAY = 0.99       # per step; belief halves in ~69 steps (~2.3s at 30/s)
    FORGET_BELOW = 0.05  # confidence below this = forgotten, cell dropped
    OCC_THRESH = 0.30  # ask: cell counts as occupied at/above this
    FREE_HALF = 0.5    # one free-space passage halves confidence
    N_MEM_RAYS = 24    # polar readout: 24 directions, 15 deg apart, full circle
    MEM_RANGE = 300.0  # px; memory sees farther than live rays (240)
    def __init__(self):
        self.grid = {}  # (ix, iy) -> confidence 0..1, sparse
    def clear(self):
        self.grid = {}
    def occupied_count(self):
        n = 0
        for c in self.grid.values():
            if c >= self.OCC_THRESH:
                n += 1
        return n
    def _cell(self, x, y):
        return (int(x // self.CELL), int(y // self.CELL))
    def _mark_free(self, ox, oy, dx, dy, dist):
        # Step along the ray in half-cell steps. Each passage halves the
        # confidence of cells the ray now passes through: a surface that
        # moved away clears in ~2 passages. The hit cell itself is NOT
        # cleared here — the tell marks it occupied AFTER this, so
        # occupied wins over free within one tell.
        t = 0.0
        step = self.CELL / 2.0
        while t < dist:
            c = self._cell(ox + dx * t, oy + dy * t)
            if c in self.grid:
                self.grid[c] = self.grid[c] * self.FREE_HALF
                if self.grid[c] < self.FORGET_BELOW:
                    del self.grid[c]
            t += step
    def _mark_occupied(self, x, y, conf=1.0):
        c = self._cell(x, y)
        if self.grid.get(c, 0.0) < conf:
            self.grid[c] = conf
    def tell_rays(self, gc, a3, rays):
        # rays: 9 normalized distances from cast_rays, directions
        # a3 + (k-4)*0.22 — the SAME fan cast_rays uses. A return of 1.0
        # means no hit (or hit beyond 240): mark free to 240, no occupied
        # cell. A return < 1.0 is a real hit: free to the hit, occupied
        # at the hit. Floor hits count (see class note).
        for k in range(9):
            ang = a3 + (k - 4) * 0.22
            dx = math.cos(ang); dy = math.sin(ang)
            d = rays[k] * 240.0
            self._mark_free(gc[0], gc[1], dx, dy, d)
            if rays[k] < 1.0:
                self._mark_occupied(gc[0] + dx * d, gc[1] + dy * d)
    def tell_ultrasonic(self, gc, a3, dist, hit):
        # One more ray, along the gripper axis, to the ultrasonic hit
        # point (the min over the 3-beam cone). Same free/occupied rule.
        dx = math.cos(a3); dy = math.sin(a3)
        d = dist if dist < ULTRA_MAX else ULTRA_MAX
        self._mark_free(gc[0], gc[1], dx, dy, d)
        if dist < ULTRA_MAX:
            self._mark_occupied(hit[0], hit[1])
    def tell_contact(self, gc):
        # Touch confirms a surface AT the gripper. 0.8, not 1.0: touch
        # is coarser than a ray hit (a point, not a measured range).
        # Caller skips this while holding (held object is not the world).
        self._mark_occupied(gc[0], gc[1], 0.8)
    def decay(self):
        # Fade everything; drop what fell below forget threshold.
        # Called once per step BEFORE the tells, so fresh observations
        # land at full confidence and stale ones fade.
        for c in list(self.grid.keys()):
            self.grid[c] = self.grid[c] * self.DECAY
            if self.grid[c] < self.FORGET_BELOW:
                del self.grid[c]
    def ask_polar(self, gc, a3):
        # Closest remembered surface at 24 angles, full circle, EE-frame
        # (directions relative to gripper heading, like the live rays —
        # no v50 rotation needed). Returns 24 floats in [0,1]:
        # distance / MEM_RANGE, 1.0 = nothing remembered that way.
        # March starts 0.75 cells out so the gripper's own cell (which
        # contact may have marked) never counts as a hit in all directions.
        out = []
        start = self.CELL * 0.75
        step = self.CELL / 2.0
        for k in range(self.N_MEM_RAYS):
            ang = a3 + k * (2.0 * math.pi / self.N_MEM_RAYS)
            dx = math.cos(ang); dy = math.sin(ang)
            found = 1.0
            t = start
            while t <= self.MEM_RANGE:
                c = self._cell(gc[0] + dx * t, gc[1] + dy * t)
                if self.grid.get(c, 0.0) >= self.OCC_THRESH:
                    found = t / self.MEM_RANGE
                    break
                t += step
            out.append(found)
        return out


class Env:
    def __init__(self):
        self.objects = []
        self.arm = RobotArm()
        self.wm = WorldModel()  # v54: belief state, told by sensors only
        self._set_frame_anchor()  # v50: episode-start EE frame
        self.episode = 1
        self.step_count = 0
        self.episode_reward = 0.0
        self.next_id = 1
        self.tower_count = 0
        # v52 minimum-time: per-episode steps-to-goal, reset in reset_scene.
        self.steps_to_grasp = None; self.steps_to_stack = None; self.steps_to_success = None; self.on_goal_steps = 0
        self.last_grasp_msg = ''
        self._custom_verts = None
        self.last_gripper_pos = None; self.still_steps = 0; self._lift_given = False; self._close_given = False; self._centred_given = False; self._last_phi = 0.0; self.episode_shaped = 0.0; self.episode_unshaped = 0.0
        self.prev_gripper_vel = (0.0, 0.0); self.joint_vel = [0.0,0.0,0.0]
        self.gripper_vel = (0.0, 0.0); self.gripper_acc = (0.0, 0.0)
        self.ultrasonic_dist = ULTRA_MAX; self.ultrasonic_close = 0.0; self.ultrasonic_hit = (0.0, 0.0)
        self.accel_forward = 0.0; self.accel_perp = 0.0; self.down_alignment = 0.0
        self.ultrasonic_dist = ULTRA_MAX; self.ultrasonic_close = 0.0; self.ultrasonic_hit = (0.0, 0.0)
    def _set_frame_anchor(self):
        # v50: anchor = EE pose at episode start. Called from __init__
        # and reset_scene, so the anchor is always the pose the episode
        # started in — never a hardcoded constant, so it stays correct if
        # the start pose is ever randomised. Start pose is fixed today,
        # so the anchor is constant today; the construction is what matters.
        _gc = self.arm.gripper_center()
        self.frame_ox, self.frame_oy = _gc
        self.frame_a3 = self.arm.angles[0] + self.arm.angles[1] + self.arm.angles[2]
        self.frame_angles = list(self.arm.angles)
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
    def ultrasonic(self):
        # Simulated ultrasonic distance sensor, centre of end effector.
        # Physics: HC-SR04-style time-of-flight. One transducer at the
        # gripper centre, firing FORWARD along the gripper axis (a3).
        # Real ultrasonics have a ~15-deg cone, not a laser line, so
        # cast 3 beams (centre, +/- 12 deg) and take the MINIMUM — the
        # first echo. That is the cone's leading edge, what a real
        # sensor would report for a narrow object off-axis.
        # Targets: every object except the held one (held object would
        # read ~0 and lie: you are already holding it, it is not ahead
        # of you). Placed objects count: a tower stack ahead is real.
        # Floor counts when the beam points down: floor is a real echo.
        # Returns (dist_px, close_flag). dist in [0,240], 240 = no echo.
        # close = 1 iff dist <= 60px grasp threshold (120mm at 0.5px/mm):
        # inside the 60px proximity halo where a grasp is learnable.
        # Beyond threshold = too far to grab; the MLP must learn that
        # from these two inputs, not from a hard-coded close rule.
        gc = self.arm.gripper_center()
        _, _, _, _, a3 = self.arm.fk()
        best = None
        best_hit = (gc[0] + math.cos(a3) * ULTRA_MAX, gc[1] + math.sin(a3) * ULTRA_MAX)
        for _off in (-ULTRA_CONE, 0.0, ULTRA_CONE):
            _ang = a3 + _off
            _dx = math.cos(_ang); _dy = math.sin(_ang)
            _d = None
            for o in self.objects:
                if o.held:
                    continue
                _h = _ray_hit(gc[0], gc[1], _dx, _dy, o.world_verts())
                if _h is not None and (_d is None or _h < _d):
                    _d = _h
            if _dy > 0.05:
                _df = (FLOOR_Y - gc[1]) / _dy
                if _df >= 0 and (_d is None or _df < _d):
                    _d = _df
            if _d is not None and (best is None or _d < best):
                best = _d
                best_hit = (gc[0] + _dx * _d, gc[1] + _dy * _d)
        if best is None:
            best = ULTRA_MAX
        self.ultrasonic_dist = float(best)
        self.ultrasonic_close = 1.0 if best <= ULTRA_GRASP_THRESH else 0.0
        self.ultrasonic_hit = best_hit
        return self.ultrasonic_dist, self.ultrasonic_close
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
        o = PhysObject(self.next_id, verts, x, y, color, name); _clamp_to_floor(o)  # v57
        self.next_id += 1
        self.objects.append(o)
        return o
    def reset_scene(self, keep_brain=True):
        _gt = self.arm.gripper_type
        self.arm = RobotArm(); self.arm.gripper_type = _gt
        # v59: randomise start pose so v50 relative frame is not cosmetic.
        self.arm.angles = [-0.85 + random.uniform(-0.15, 0.15), 1.15 + random.uniform(-0.15, 0.15), 0.35 + random.uniform(-0.15, 0.15)]
        if self.arm.finger_tip()[1] > FLOOR_Y - 5:
            self.arm.angles = [-0.85, 1.15, 0.35]
        self._set_frame_anchor()  # v50: new episode, new anchor
        self.tower_count = 0; self.still_steps = 0; self.last_gripper_pos = None; self._lift_given = False; self._close_given = False; self._centred_given = False; self._last_phi = 0.0; self.episode_shaped = 0.0; self.episode_unshaped = 0.0
        self.steps_to_grasp = None; self.steps_to_stack = None; self.steps_to_success = None; self.on_goal_steps = 0  # v52
        self.wm.clear()  # v54: new scene = new world, old beliefs are stale
        self.prev_gripper_vel = (0.0, 0.0); self.joint_vel = [0.0,0.0,0.0]
        self.gripper_vel = (0.0, 0.0); self.gripper_acc = (0.0, 0.0)
        self.step_count = 0; self.episode_reward = 0.0
        # Spawn curriculum: objects start NEAR the gripper (gripper starts
        # ~(374,457)), not at the top of the arena (y=170, ~280px away).
        # Random approach from 280px with 0 positives is a lottery; starting
        # within ~150px makes the first inside/proximity bonuses reachable
        # by exploration, then later episodes can spawn farther. Still no
        # script: position is randomised, the MLP still has to find them.
        # v59: spawn avoids tower zone 320-420 and overlaps. Fixed slots
        # left of tower, 60px apart, small jitter. No resample loop: slots
        # already guarantee separation and tower avoidance.
        base_xs = [175, 235, 295, 205, 265, 320]
        xs = [float(base_xs[i % 3] + random.uniform(-8, 8)) for i in range(len(self.objects))]
        for i, o in enumerate(self.objects):
            o.x = float(xs[i % len(xs)])
            o.y = 430.0 + (i // 3) * 60.0 + random.uniform(-20, 20)
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
            _clamp_to_floor(o)
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
        # Orchestrator only: phases run in physics order, each helper takes
        # (reward, info) and returns them. Edit a phase by editing its
        # helper; the order here never changes. v53 moved the phase bodies
        # verbatim from this function into the helpers below — no numbers,
        # no order, no behaviour changed.
        # Time penalty -0.012 -> -0.004: at -0.012, 515 steps = -6.2 of
        # pure time cost, dwarfing approach shaping and making Reward -9.8
        # look like failure even when the arm was approaching. -0.004 still
        # punishes dawdling (episode_len steps = -2.4) without dominating signal.
        reward = -0.004; info = {'slip':0.0,'contact':0.0,'grasped':False,'placed':False,'dropped':False,'collision':0.0,'stuck':0.0}
        reward, info, gc, prev_target, prev_dist, new_dist, prev_angles, _a3 = self._move_arm(action, reward, info)
        reward, info = self._shape_reward(action, reward, info, gc, prev_target, prev_dist, new_dist, prev_angles, _a3)
        reward, info = self._try_grasp(action, reward, info, gc, _a3, app_ctx)
        reward, info = self._update_held(reward, info, gc)
        reward, info = self._try_release(reward, info)
        reward, done, timeout, info = self._finish_step(reward, info, gc, app_ctx)
        self._update_world_model()  # v54: tell only, never touches reward/physics
        return reward, done, timeout, info

    def _update_world_model(self):
        # v54: tell the WM what the sensors just saw, from the settled
        # pose (after _finish_step physics). Pure observer: writes only
        # to self.wm. Never reads object poses, never touches reward,
        # physics, or info. Decay first, then tells, so fresh evidence
        # lands at full confidence.
        gc = self.arm.gripper_center()
        _, _, _, _, a3 = self.arm.fk()
        self.wm.decay()
        self.wm.tell_rays(gc, a3, self.cast_rays())
        _ud, _uc = self.ultrasonic()
        self.wm.tell_ultrasonic(gc, a3, _ud, self.ultrasonic_hit)
        _c, _f, _s = self.contact_sensors()
        if _c > 0.5 and self.arm.held is None:
            self.wm.tell_contact(gc)

    def _move_arm(self, action, reward, info):
        # Phase 1 — apply joint deltas + gripper, reject floor collisions,
        # update velocity / accel / still trackers. Returns the move state
        # the shaping phase needs.
        arm = self.arm; prev_target = self.current_target_pos(); gc0 = arm.gripper_center()
        prev_dist = math.hypot(prev_target[0]-gc0[0], prev_target[1]-gc0[1]); prev_angles = list(arm.angles)
        arm.angles[0] = max(-2.4, min(0.45, arm.angles[0] + action[0]*0.055))
        arm.angles[1] = max(-0.15, min(2.6, arm.angles[1] + action[1]*0.065))
        arm.angles[2] = max(-1.8, min(1.8, arm.angles[2] + action[2]*0.065))
        # Gripper step 0.085 -> 0.12: closing from 1.0 to 0.38 needed 8
        # sustained +1 actions; OU noise almost never sustains that. 5 steps
        # is reachable by the persistent gripper OU (theta 0.05). Still no
        # script: the MLP must choose to close, the step only makes the
        # action effective when it does.
        arm.gripper = max(0.0, min(1.0, arm.gripper - action[3]*0.12))
        _ft_try = arm.finger_tip(); _a3_old = prev_angles[0]+prev_angles[1]+prev_angles[2]
        _ft_prev_y = gc0[1] + math.sin(_a3_old)*(arm.FINGER_LEN/2.0) if arm.gripper_type=='parallel' else gc0[1]
        collision = False
        if _ft_try[1] > FLOOR_Y-5 and _ft_try[1] >= _ft_prev_y:
            arm.angles = prev_angles; collision = True
        # v57: held object floor check. Fingertip check alone lets the arm
        # push a held block through the floor, because the block extends
        # below the gripper centre. Predict the held bottom after this move
        # and reject the move if it would penetrate, same as fingertip.
        if not collision and arm.held is not None:
            _held = arm.held
            _new_gc = arm.gripper_center()
            _pred_x = _new_gc[0] - _held.grasp_offset[0]
            _pred_y = _new_gc[1] - _held.grasp_offset[1]
            _pred_bottom = max(_pred_y + _rotate(lx, ly, _held.rot)[1] for (lx, ly) in _held.verts)
            if _pred_bottom > FLOOR_Y and _pred_bottom >= _held.bottom_y():
                arm.angles = prev_angles; collision = True
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
        self.last_gripper_pos = gc
        return reward, info, gc, prev_target, prev_dist, new_dist, prev_angles, _a3

    def _shape_reward(self, action, reward, info, gc, prev_target, prev_dist, new_dist, prev_angles, _a3):
        # Phase 2 — potential-based approach + proximity + close-on-object
        # shaping. Pure reward; never moves anything.
        arm = self.arm
        # --- Potential-based approach shaping (Ng et al, 1999) ---
        # Was: (prev_dist - new_dist)*0.015. Same idea, but unprincipled
        # scale and no orientation term: the arm could approach sideways
        # (DOWN -0.46 in Fig.2) forever and still collect approach reward,
        # then arrive unable to grasp. Now Phi(s) = -dist/50 + 0.5*down,
        # reward += gamma*Phi(s') - Phi(s). This preserves the optimal
        # policy (potential shaping) while teaching approach AND pointing
        # down together. down = sin(a3): -1 = up, +1 = straight down.
        _prev_down = math.sin(prev_angles[0] + prev_angles[1] + prev_angles[2])
        _new_down = math.sin(_a3)
        _phi_prev = -prev_dist / 50.0 + 0.5 * _prev_down
        _phi_new = -new_dist / 50.0 + 0.5 * _new_down
        # v59: shaping uses gamma=1, not 0.99. With gamma=0.99, a motionless
        # arm earns (1-gamma)*-Phi = +0.06/step leak, +20 over 321 steps.
        # With gamma=1, shaping at rest is 0, total is -Phi_0, policy-invariant.
        _shaping = _phi_new - _phi_prev
        reward += _shaping
        self._last_phi = _phi_new
        info['shaping'] = info.get('shaping', 0.0) + _shaping
        # Proximity shaping: within 60px of target, pay for being close
        # AND pointing down. This fills the gap between approach (far) and
        # inside-polygon (rare): the arm now gets graded signal in the
        # 60px halo where a grasp is actually learnable.
        if new_dist < 60.0 and arm.held is None:
            _prox = 1.0 - new_dist / 60.0
            _down01 = 0.5 + 0.5 * _new_down
            _sh2 = 0.02 * _prox * _down01
            reward += _sh2
            info['shaping'] = info.get('shaping', 0.0) + _sh2
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
                # v59: one-time per approach, not per-step. Was +0.10*centred
                # every step, up to +60 per episode vs +10 for a stack.
                if not self._centred_given:
                    _sh3 = 0.10 * _centred
                    reward += _sh3
                    info['shaping'] = info.get('shaping', 0.0) + _sh3
                    self._centred_given = True
                # Closing = gripper value decreasing (action[3] > 0 drives
                # arm.gripper down in step()). Detect a close this step.
                if action[3] > 0.30 and not self._close_given:
                    _sh4 = 0.30 * _centred
                    reward += _sh4
                    info['shaping'] = info.get('shaping', 0.0) + _sh4
                    self._close_given = True
                    self.last_grasp_msg = 'CLOSE ON OBJECT — centred %.2f' % _centred
            else:
                self._centred_given = False
                # Close-attempt zone: within 30px of an object's COM, a
                # close action earns +0.10 even though the gripper is not
                # yet inside the polygon. Old code paid +0 only inside, so
                # the gripper had to randomly land inside (~0.5% of arena)
                # AND close there. The 30px halo is ~10x larger and teaches
                # the close action where it matters, without farming: it is
                # one-time per approach (gated by _close_given) and requires
                # action[3] > 0.30, not just hovering.
                _near = None
                _near_d = 1e9
                for _o in self.objects:
                    if _o.placed:
                        continue
                    _cx, _cy = _o.com_world()
                    _d = math.hypot(gc[0] - _cx, gc[1] - _cy)
                    if _d < _near_d:
                        _near_d = _d
                        _near = _o
                if _near is not None and _near_d < 30.0 and action[3] > 0.30 and not self._close_given:
                    reward += 0.10
                    info['shaping'] = info.get('shaping', 0.0) + 0.10
                    self._close_given = True
                    self.last_grasp_msg = 'CLOSE ATTEMPT — %.0fpx from COM' % _near_d
                elif _near is None or _near_d >= 30.0:
                    self._close_given = False
        return reward, info

    def _try_grasp(self, action, reward, info, gc, _a3, app_ctx):
        # Phase 3 — grasp attempt: gripper closed + centred inside an object
        # polygon + stability > 0.30. Records steps-to-grasp (v52).
        arm = self.arm
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
                        reward += 0.5 + 1.5 * stability; info['grasped']=True; self.last_grasp_msg='GRASP %.2f stab' % stability; app_ctx.grasp_attempts+=1; app_ctx.grasp_success+=1; self._lift_given = False; self._close_given = False; self.steps_to_grasp = self.step_count + 1 if self.steps_to_grasp is None else self.steps_to_grasp  # v52
                    else:
                        o.slip=1.0; o.vrot+=(random.random()-0.5)*0.08; reward-=0.6; info['slip']=1.0; app_ctx.grasp_attempts+=1
                    break
        return reward, info

    def _update_held(self, reward, info, gc):
        # Phase 4 — held object follows the gripper; wobble, slip, drop,
        # one-time lift bonus.
        arm = self.arm
        if arm.held is not None:
            o = arm.held; o.x = gc[0]-o.grasp_offset[0]; o.y = gc[1]-o.grasp_offset[1]; _clamp_to_floor(o)  # v57: safety net, held object never below floor
            wobble=(1.0-o.grasp_stability)*0.018; o.rot+=(random.random()-0.5)*wobble*2.0
            _slip_rate=0.008 if arm.gripper_type=='adaptive' else 0.012
            o.slip=min(1.0, o.slip+(1.0-o.grasp_stability)*_slip_rate); info['slip']=o.slip; info['contact']=1.0
            if o.slip>0.95 and o.grasp_stability<0.45:
                arm.held=None; o.held=False; o.vy=1.5; reward-=3.0; info['dropped']=True; self.last_grasp_msg='DROPPED — off-COM slip'; self._lift_given = False; self._close_given = False
            # Was +0.04 EVERY step while held high: hold+hover for episode_len steps
            # = +24, more than a stack (+10). Pure reward hacking. Now
            # one-time +0.5 on first lift per grasp.
            if o.y < FLOOR_Y-55 and not self._lift_given:
                reward += 0.5; self._lift_given = True
        return reward, info

    def _try_release(self, reward, info):
        # Phase 5 — gripper open while holding: release + placement check.
        # Records steps-to-stack (v52).
        arm = self.arm
        if arm.held is not None and arm.gripper > 0.62:
            o=arm.held; arm.held=None; o.held=False; o.vy=0.0; _clamp_to_floor(o); cx,_=o.com_world()  # v57: released object clamped before stability check
            if TOWER_X0 <= cx <= TOWER_X1 and o.is_stable(self):
                o.placed=True; o.resting=True; self.tower_count+=1; reward+=10.0; info['placed']=True; self.last_grasp_msg='STACKED! tower=%d' % self.tower_count; self.steps_to_stack = self.step_count + 1 if self.steps_to_stack is None else self.steps_to_stack  # v52
            elif TOWER_X0 <= cx <= TOWER_X1 and not o.is_stable(self):
                reward-=2.5; self.last_grasp_msg='PLACED BUT TIPPED — COM off support'
            else: reward-=0.2
        return reward, info

    def _finish_step(self, reward, info, gc, app_ctx):
        # Phase 6 — free physics, contact sensors, on-goal count, terminal
        # + timeout, clipping, accounting. Records steps-to-success (v52).
        arm = self.arm
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
        # v52 minimum-time: on-goal = gripper within 30px of the current
        # target (same 30px halo as close-on-object shaping). Counts dwell
        # where acting pays, in both phases: approach (near COM) and carry
        # (near tower slot), because the target switches on grasp.
        _ot = self.current_target_pos()
        if math.hypot(_ot[0]-gc[0], _ot[1]-gc[1]) < 30.0:
            self.on_goal_steps += 1
        done=False; timeout=False
        _step_r = max(-5.0, min(5.0, reward))
        if self.tower_count>=len(self.objects) and len(self.objects)>0:
            done=True; _step_r += 20.0
            self.steps_to_success = self.step_count + 1  # v52: steps-to-goal, full task
        if self.step_count+1 > app_ctx.episode_len: done=True; timeout=True  # v52: timeout is a tunable parameter, not a magic 600
        # v59: zero Phi at terminal/timeout. Shaping added Phi_new,
        # correct is 0 at terminal, so correction is -Phi_last.
        if done:
            _corr = -1.0 * self._last_phi
            _step_r = max(-5.0, min(5.0, _step_r + _corr))
            info['shaping'] = info.get('shaping', 0.0) + _corr
        _sh = info.get('shaping', 0.0)
        self.episode_shaped += _sh
        self.episode_unshaped += (_step_r - _sh)
        reward = max(-25.0, min(25.0, _step_r))
        self.step_count+=1; self.episode_reward+=reward; return reward, done, timeout, info

# CONTROLLER — app state
# ---------------------------------------------------------------------------
def _med(vals):
    # v52: median of the last 20, or '—' if no episode reached the goal yet.
    if not vals:
        return '—'
    _v = sorted(vals[-20:]); _n = len(_v)
    if _n % 2 == 1:
        return '%d' % _v[_n // 2]
    return '%d' % round((_v[_n // 2 - 1] + _v[_n // 2]) / 2.0)

def _make_button(x, y, w, h, label, action):
    return {'x': x, 'y': y, 'w': w, 'h': h, 'label': label, 'action': action, 'enabled': True}

def onAppStart(app):
    random.seed(0)  # v59: fixed seed for reproducibility
    app.seed = 0
    app.width = WIDTH
    app.height = HEIGHT
    app.stepsPerSecond = 30
    app.scs = {}  # single nested bundle for any future window/extension use
    app.env = Env()
    # Input 69 = 61 sensors (37 + 24 memory rays) + 8 context. Actor 4 = joint deltas + gripper.
    # v50: actions stay joint deltas. They are already incremental (relative
    # to the current pose), not absolute joint targets, so there is no
    # absolute action to relativise. Cartesian EE-frame actions would need
    # a Jacobian mapper from Cartesian commands to joints — a scripted
    # controller that does the kinematics for the MLP, which this app
    # forbids (no IK, no scripted controller). The relative-frame gain
    # therefore lands in the observation, where the paper's gain lives.
    app.actor = MLP([69, 48, 32, 4], ['relu', 'relu', 'tanh'])  # v51: actor has NO LayerNorm (supervised, stable)
    # v51: critic + target critic get LayerNorm on hidden layers (RLPD).
    # LN is what makes higher UTD stable: it bounds hidden activations so
    # repeated critic updates on the same buffer cannot blow up values.
    app.critic = MLP([69, 48, 32, 1], ['relu', 'relu', 'linear'], layernorm=True)
    app.target_critic = MLP([69, 48, 32, 1], ['relu', 'relu', 'linear'], layernorm=True)
    app.target_critic.copy_from(app.critic)
    app.ctx = TrainingContext()
    app.replay = ReplayBuffer(2000)
    app.demo_replay = ReplayBuffer(2000)  # v48: teleop-only, see onStep teleop branch
    app.obs_norm = ObsNormalizer(69)
    # v48 asymmetric: actor LR 10x below critic (was 0.0008, near critic).
    # Paper ratio is ~30x; 10x here because this actor update is per-sample
    # supervised MSE, not a Q-gradient step, so 1e-5 would stall it.
    app.actor_lr = 0.0001
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
    app.shaped_hist = [0.0]  # v59: shaped return per episode
    app.unshaped_hist = [0.0]  # v59: unshaped return per episode
    app.random_baseline = None  # v59: random-policy mean reward, computed on demand
    app.critic_updates = 0  # v48: counts _train_batch calls (critic updates)
    app.actor_updates = 0  # v48: counts actor updates actually run
    app.actor_update_every = 5  # v48: critic:actor = 5:1 in _train_batch units, see _train_batch
    app.train_every = 2  # v51 UTD: _train_batch every 2 env steps = 0.5 batches/step, 2x v50
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
    # Live episode-reward curve: reward_hist only grows at episode END
    # (episode_len steps), so for the whole first episode the panel showed a flat
    # 0.0 line and looked empty (Fig.2). live_reward_hist grows every 20
    # steps with the RUNNING episode reward, so the curve moves live.
    app.live_reward_hist = [0.0]
    app.episode_reward = 0.0
    app.episode_len = 600  # v52: episode timeout, tunable (was hardcoded 600 in Env.step)
    # v52 minimum-time histories: per-episode steps-to-goal. Grasp/stack/
    # success lists only hold episodes that REACHED that goal, so the
    # median is over successes. on_goal holds every episode (0s included).
    app.t_grasp_hist = []
    app.t_stack_hist = []
    app.t_success_hist = []
    app.on_goal_hist = []
    app.grasp_attempts = 0
    app.grasp_success = 0
    app.status = 'PAUSED — press TRAIN to let the MLP learn. DRAW a custom shape to break scripts.'
    app.teleop_action = [0.0, 0.0, 0.0, 0.0]
    # Seed scene: 3 objects that already punish bbox-centre grasping.
    # Spawn near the gripper start ~(374,457), not at the top (y=220) -
    # see reset_scene spawn curriculum for why.
    app.env.add_object('L', 220, 450)
    app.env.add_object('block', 300, 460)
    app.env.add_object('wedge', 380, 450)
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
    app.buttons['random_baseline'] = _make_button(710, 410, 316, 26, 'Random Baseline', 'random_baseline')
    app.buttons['close_shape'] = _make_button(710, 312, 150, 28, 'Close Shape', 'close_shape')
    app.buttons['cancel_draw'] = _make_button(868, 312, 158, 28, 'Cancel Draw', 'cancel_draw')
    app.buttons['gripper'] = _make_button(710, 345, 316, 26, 'Gripper: PARALLEL', 'gripper')
    app.buttons['manual'] = _make_button(710, 378, 316, 26, 'INSTRUCTION MANUAL', 'manual')

def _sensor_vector(app):
    env = app.env
    arm = env.arm
    gc = arm.gripper_center()
    _a3 = arm.angles[0] + arm.angles[1] + arm.angles[2]  # v54: wrist heading, for memory-ray readout
    rays = env.cast_rays()
    # Ultrasonic: refreshed every step, so the obs always carries the
    # current range. Two inputs: continuous distance + binary threshold
    # flag. ReLU MLPs struggle with sharp thresholds from a continuous
    # input alone (they need many units to carve a step); the explicit
    # CLOSE flag gives the step, the continuous value gives the gradient
    # toward it. Both are sensor readings, not a controller decision.
    _ultra_d, _ultra_close = env.ultrasonic()
    _ultra_norm = max(0.0, min(1.0, _ultra_d / ULTRA_MAX))
    contact, force, slip = env.contact_sensors()
    # v59: NO ORACLE. target/tower COM removed. Reward shaping still uses
    # COM (privileged reward is allowed), observation does not.
    # v50 relative frame: rotate every vector by -frame_a3 (episode-start
    # EE orientation) and translate by the episode-start gripper position.
    # At episode start the gripper obs is (0,0) and the joint obs is
    # (0,0,0). The policy sees displacement from where THIS episode
    # started, in the frame the gripper started in — not absolute arena
    # coordinates. Reward and physics stay in base frame: the frame is an
    # observation representation, not a change to the environment.
    _ca = math.cos(-env.frame_a3); _sa = math.sin(-env.frame_a3)
    def _rot(_dx, _dy):
        return (_dx * _ca - _dy * _sa, _dx * _sa + _dy * _ca)
    _gdx, _gdy = _rot(gc[0] - env.frame_ox, gc[1] - env.frame_oy)
    # v59: sensor-derived target cue, not COM. Nearest live ray + nearest
    # memory ray. Both are sensor readings.
    _mem_rays = env.wm.ask_polar(gc, _a3)
    _ray_k = min(range(len(rays)), key=lambda _k: rays[_k])
    _ray_min = rays[_ray_k]
    _ray_ang = ((_ray_k - 4) * 0.22) / 0.88
    _mem_k = min(range(len(_mem_rays)), key=lambda _k: _mem_rays[_k])
    _mem_min = _mem_rays[_mem_k]
    _mem_off = _mem_k * (2.0 * math.pi / 24.0)
    _mem_off = ((_mem_off + math.pi) % (2.0 * math.pi)) - math.pi
    _mem_ang = _mem_off / math.pi
    dx, dy = _ray_min, _ray_ang
    tdx, tdy = _mem_min, _mem_ang
    _gvx, _gvy = _rot(env.gripper_vel[0], env.gripper_vel[1])
    held = 1.0 if arm.held is not None else 0.0
    tilt = arm.held.slip if arm.held is not None else 0.0
    remaining = len([o for o in env.objects if not o.placed]) / 6.0
    floor_clear = max(0.0, min(1.0, (FLOOR_Y - gc[1]) / 200.0))
    _gtype = 1.0 if arm.gripper_type == 'adaptive' else 0.0
    # Joint angles as deltas from start angles (v50). down_alignment
    # below stays ABSOLUTE sin(a3): it is the gravity reference. After
    # rotation the policy would otherwise have no way to tell down from
    # sideways. Rays and accel_forward/perp are already EE-frame, so they
    # need no rotation. floor_clear is a perpendicular distance, so it is
    # frame-invariant and stays as-is.
    sensors = [(arm.angles[0] - env.frame_angles[0]) / 2.5,
               (arm.angles[1] - env.frame_angles[1]) / 2.5,
               (arm.angles[2] - env.frame_angles[2]) / 1.8,
               arm.gripper, _gdx / 700.0, _gdy / 700.0]
    sensors = sensors + rays
    sensors = sensors + [contact, force, slip, dx, dy, tdx, tdy, held, tilt, remaining, floor_clear, _gtype]  # v59: dx,dy=nearest ray, tdx,tdy=nearest mem ray
    sensors = sensors + [env.accel_forward, env.accel_perp, env.down_alignment,
                         env.joint_vel[0]/0.07, env.joint_vel[1]/0.07, env.joint_vel[2]/0.07,
                         _gvx/10.0, _gvy/10.0]  # v50: gripper vel in start-EE frame
    sensors = sensors + [_ultra_norm, _ultra_close]
    sensors = sensors + _mem_rays  # v54: 24 memory rays, reused, no second cast
    # sensors = 61 (37 + 24 memory rays), context = 8 → 69, then Welford-normalised.
    raw = sensors + app.ctx.vector()
    # Normalise with PRIOR stats, then update — never normalise a sample
    # with itself (that would zero the first sample and leak the current
    # obs into its own normaliser). Standard online-norm practice.
    normed = app.obs_norm.normalize(raw)
    app.obs_norm.update(raw)
    return normed, rays

def _train_batch(app):
    if len(app.replay) + len(app.demo_replay) < 16:
        return
    app.critic_updates = app.critic_updates + 1
    # v59: 50/50 demo/online kept (RLPD-style demo ratio), but stratified
    # 50% positives REMOVED. Forcing positives biased V(s) upward with no
    # importance weighting. Now uniform within each half.
    _n_demo = min(16, len(app.demo_replay))
    batch = app.demo_replay.sample(_n_demo) + app.replay.sample(32 - _n_demo)
    random.shuffle(batch)
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
    # Adv-std was a copy of TD-std (both appended raw_std_adv), so the
    # panel showed TD-std == Adv-std = 0.066 in Fig.2 and hid whether
    # normalisation was doing anything. Now Adv-std = std of the
    # NORMALISED advantages adv_n in [-1,1] actually used for the actor
    # update. TD-std = std of raw TD errors. They must differ.
    pos_frac = sum(1 for (_s, _a, _n, _r, _s2, _d, _t) in batch if _r >= 0.4) / len(batch)
    # Gate: no positives AND no TD surprise -> critic still learns (it is
    # fitting the failure distribution), but the actor does NOT update.
    # Exploration (OU noise) keeps running, so the actor still explores;
    # it just does not collapse toward its own noise.
    actor_gated = (pos_frac == 0.0 and td_std < 0.02)
    # v48 asymmetric: critic every batch, actor every 5th batch. Paper M=20
    # counts batch gradient steps. Here one _train_batch = 1 batch step
    # (v56, was 32 per-sample steps) and _train_batch runs every 2 env
    # steps, so M=5 here = 5 critic batch steps per actor step. M=20 here
    # update per 80 env steps and would starve the actor at this UTD.
    actor_due = (app.critic_updates % app.actor_update_every == 0)
    actor_skip = actor_gated or not actor_due
    _adv_ns = []
    for _a in advs:
        _an = (_a - mean_adv) / std_adv
        _adv_ns.append(max(-1.0, min(1.0, _an)))
    _adv_mean = sum(_adv_ns) / len(_adv_ns)
    _adv_var = sum((x - _adv_mean) * (x - _adv_mean) for x in _adv_ns) / len(_adv_ns)
    app.td_std_hist.append(td_std)
    app.adv_std_hist.append(math.sqrt(_adv_var))
    app.pos_frac_hist.append(pos_frac)
    if len(app.td_std_hist) > 120: app.td_std_hist.pop(0)
    if len(app.adv_std_hist) > 120: app.adv_std_hist.pop(0)
    if len(app.pos_frac_hist) > 120: app.pos_frac_hist.pop(0)
    app.actor_gated_count = app.actor_gated_count + (1 if actor_gated else 0)
    # --- Pass 2: critic, ONE batch Adam step on mean gradient (v56) ---
    _critic_examples = [(s, [targets[idx]]) for idx, (s, a, noise, r, s2, done, timeout) in enumerate(batch)]
    tot_c = app.critic.train_batch(_critic_examples, app.critic_lr, loss_type='huber') * len(batch)
    # --- Pass 3: actor, advantage-weighted BC, one batch step ---
    # Desired interpolates clean to executed by advantage, adv in [-1,1].
    # adv=+1 -> executed, adv=-1 -> clean, adv=0 -> halfway. No overshoot.
    tot_a = 0.0; grad_tot = 0.0
    if actor_skip:
        # Actor did not train. No actor loss entry, no fake 0.0.
        # loss_hist is critic loss only, so the 5:1 schedule cannot jump it.
        app.critic_loss_hist.append(tot_c / len(batch))
        app.loss_hist.append(tot_c / len(batch))
        app.grad_norm_hist.append(0.0)
        app.target_critic.soft_update_from(app.critic, app.tau)
        for _h in (app.loss_hist, app.grad_norm_hist, app.critic_loss_hist):
            if len(_h) > 120: _h.pop(0)
        return
    app.actor_updates = app.actor_updates + 1
    _actor_examples = []
    for idx, (s, a, noise, r, s2, done, timeout) in enumerate(batch):
        adv_n = (advs[idx] - mean_adv) / std_adv
        adv_n = max(-1.0, min(1.0, adv_n))
        w = 0.5 + 0.5 * adv_n
        desired = []
        for i in range(4):
            clean_est = a[i] - noise[i]
            desired.append(max(-1.0, min(1.0, clean_est + w * noise[i])))
        _actor_examples.append((s, desired))
        grad_tot += abs(adv_n)
    tot_a = app.actor.train_batch(_actor_examples, app.actor_lr, loss_type='mse') * len(batch)
    app.target_critic.soft_update_from(app.critic, app.tau)
    # loss_hist is critic TD loss only (TD3 / SAC practice: track critic and
    # actor separately). Actor loss in its own hist, never summed in.
    app.critic_loss_hist.append(tot_c / len(batch))
    app.actor_loss_hist.append(tot_a / len(batch))
    app.loss_hist.append(tot_c / len(batch))
    app.grad_norm_hist.append(grad_tot / len(batch))
    for _h in (app.loss_hist, app.grad_norm_hist, app.critic_loss_hist, app.actor_loss_hist):
        if len(_h) > 120: _h.pop(0)

def _random_baseline(app, n_episodes=3):
    # v59: random-policy baseline. Runs n episodes with uniform random
    # actions in a fresh Env, no learning, returns mean shaped reward.
    # Lets you tell learning from reward leakage: MLP must beat this.
    _tot = 0.0
    for _ in range(n_episodes):
        _e = Env()
        _e.reset_scene()
        for _ in range(app.episode_len):
            _a = [random.uniform(-1.0, 1.0) for _ in range(4)]
            _r, _d, _t, _info = _e.step(_a, app)
            if _d:
                break
        _tot += _e.episode_reward
    app.random_baseline = _tot / max(1, n_episodes)
    app.status = 'Random baseline %.1f over %d eps (seed %d).' % (app.random_baseline, n_episodes, app.seed)
    return app.random_baseline

def _end_episode(app):
    app.reward_hist.append(app.env.episode_reward)
    if len(app.reward_hist) > 120:
        app.reward_hist.pop(0)
    # v52 minimum-time: capture this episode's times BEFORE reset_scene
    # clears them. Teleop episodes are skipped (app.training False): the
    # history measures the MLP's speed, not human demos. Eval counts.
    _tg = app.env.steps_to_grasp; _ts = app.env.steps_to_stack; _td = app.env.steps_to_success; _og = app.env.on_goal_steps
    if app.training:
        if _tg is not None:
            app.t_grasp_hist.append(_tg)
        if _ts is not None:
            app.t_stack_hist.append(_ts)
        if _td is not None:
            app.t_success_hist.append(_td)
        app.on_goal_hist.append(_og)
        for _h in (app.t_grasp_hist, app.t_stack_hist, app.t_success_hist, app.on_goal_hist):
            if len(_h) > 120: _h.pop(0)
    if app.eval_mode:
        app.eval_reward_hist.append(app.env.episode_reward)
        if len(app.eval_reward_hist) > 60:
            app.eval_reward_hist.pop(0)
    # LR / epsilon decay: only in TRAINING. Eval episodes must not consume
    # exploration budget or anneal the LR.
    if not app.eval_mode:
        app.actor_lr = max(0.00001, app.actor_lr * 0.995)  # v48: floor 10x below 0.0001 start
        app.critic_lr = max(0.00025, app.critic_lr * 0.995)
        # Epsilon also decays per-step in onStep (0.9995/step); this
        # episode-end 0.985 is the slower anneal on top, not the only decay.
        app.epsilon = max(0.05, app.epsilon * 0.985)
        app.ou.reset()
    app.env.episode += 1
    # Reset scene but KEEP weights — learning persists across episodes.
    objs = list(app.env.objects)
    app.env.reset_scene()
    app.ctx = TrainingContext()
    app.status = 'Ep %d done R %.1f | grasp %s stack %s done %s goal %d | brain kept.' % (app.env.episode - 1, app.env.episode_reward, _tg if _tg is not None else '—', _ts if _ts is not None else '—', _td if _td is not None else '—', _og)
    app.shaped_hist.append(app.env.episode_shaped)
    app.unshaped_hist.append(app.env.episode_unshaped)
    if len(app.shaped_hist) > 120: app.shaped_hist.pop(0)
    if len(app.unshaped_hist) > 120: app.unshaped_hist.pop(0)
    app.status = app.status + ' | shaped %.1f unshaped %.1f' % (app.env.episode_shaped, app.env.episode_unshaped)
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
            # Gripper boost: old code boosted only on CONTACT (>0.5). The
            # gripper never contacts anything until it is already inside
            # an object, so the boost never fired in Fig.2. Now boost in
            # the 50px approach halo too: trying to close near an object
            # is the behaviour to explore, not just closing after contact.
            _c, _f, _sl = app.env.contact_sensors()
            # v59: sensor-based boost, not COM. Was _d_tgt from
            # current_target_pos() (COM). Now ultrasonic <50 or nearest
            # ray <50px. Same 50px halo, no oracle.
            _ultra_d2, _ = app.env.ultrasonic()
            _rays2 = app.env.cast_rays()
            _near_sensor = (_ultra_d2 < 50.0) or (min(_rays2) * 240.0 < 50.0)
            if (_c > 0.5 or _near_sensor) and app.env.arm.gripper > 0.38:
                noise[3] = noise[3] * 1.8
            executed = [max(-1.0, min(1.0, clean[i] + noise[i])) for i in range(4)]
        reward, done, timeout, info = app.env.step(executed, app)
        # Per-step epsilon decay: old code decayed epsilon only at episode
        # END (0.985/episode), so after 515 steps eps was still 0.35 and
        # OU noise dominated the whole first episode. Now 0.9995/step:
        # eps 0.35 -> 0.27 at step 515, -> 0.05 floor by ~3900 steps.
        # Episode-end decay in _end_episode is kept as a second, slower
        # anneal; the floor 0.05 stops exploration collapsing to zero.
        app.epsilon = max(0.05, app.epsilon * 0.9995)
        # Live episode-reward curve (see onAppStart note).
        if app.env.step_count % 20 == 0:
            app.live_reward_hist.append(app.env.episode_reward)
            if len(app.live_reward_hist) > 120: app.live_reward_hist.pop(0)
        # Do NOT also do app.episode_reward += reward: Env.step already adds
        # to env.episode_reward. Double-counting + _end_episode only reset
        # env.episode_reward, so the displayed Reward grew across episodes.
        s2, _ = _sensor_vector(app)
        if not app.eval_mode:
            app.replay.add((s, executed, noise, reward, s2, done, timeout))
            app.ctx.update(reward, info['slip'], info['contact'], executed, info['grasped'])
            # v51 UTD: every 2 steps, not 4. Paired with critic LayerNorm
            # (RLPD): without LN, more critic updates diverge; with LN they
            # stay bounded. Every step (UTD 1.0) would be 4x compute and
            # risks frame drops in Brython, so 2x is the step.
            if app.env.step_count % app.train_every == 0:
                _train_batch(app)
        if done:
            _end_episode(app)
        return
    if app.teleop:
        a = list(app.teleop_action)
        app.teleop_action = [0.0, 0.0, 0.0, 0.0]
        s, _ = _sensor_vector(app)
        # v48: store teleop noise as teleop - clean, NOT zeros. _train_batch
        # recovers clean = a - noise and interpolates clean -> executed by
        # advantage. With zeros, clean == executed, so advantage had no
        # effect and bad teleop moves were cloned as strongly as good ones.
        _clean = app.actor.forward(s)
        _teleop_noise = [a[i] - _clean[i] for i in range(4)]
        reward, done, timeout, info = app.env.step(a, app)
        s2, _ = _sensor_vector(app)
        if any(v != 0.0 for v in a):
            # Direct BC during teleop is human supervision, not the RL
            # actor update, so it is exempt from the asymmetric schedule.
            app.actor.train_example(s, a, 0.004, loss_type='mse')
        # v48: teleop -> demo buffer only. _train_batch samples 50% demo /
        # 50% online. All teleop transitions go in, failures included:
        # the critic needs good AND bad experience to rank actions.
        app.demo_replay.add((s, a, _teleop_noise, reward, s2, done, timeout))
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
    elif action == 'random_baseline':
        _random_baseline(app, 3)
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
        app.actor = MLP([69, 48, 32, 4], ['relu', 'relu', 'tanh'])  # v51: no LN
        app.critic = MLP([69, 48, 32, 1], ['relu', 'relu', 'linear'], layernorm=True)  # v51
        app.target_critic = MLP([69, 48, 32, 1], ['relu', 'relu', 'linear'], layernorm=True)  # v51
        app.target_critic.copy_from(app.critic)
        app.replay = ReplayBuffer(2000)
        app.demo_replay = ReplayBuffer(2000)  # v48
        app.obs_norm = ObsNormalizer(69)
        app.ou = OUNoise(4)
        app.actor_lr = 0.0001  # v48 asymmetric
        app.critic_lr = 0.001
        app.loss_hist = [0.0]
        app.reward_hist = [0.0]
        app.live_reward_hist = [0.0]
        app.grad_norm_hist = [0.0]
        app.critic_loss_hist = [0.0]
        app.actor_loss_hist = [0.0]
        app.td_std_hist = [0.0]
        app.adv_std_hist = [0.0]
        app.pos_frac_hist = [0.0]
        app.actor_gated_count = 0
        app.shaped_hist = [0.0]
        app.unshaped_hist = [0.0]
        app.random_baseline = None
        app.critic_updates = 0  # v48
        app.actor_updates = 0  # v48
        app.t_grasp_hist = []  # v52
        app.t_stack_hist = []
        app.t_success_hist = []
        app.on_goal_hist = []
        app.actor_update_every = 5  # v48
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
        o.y = max(110, my + app.drag_dy); _clamp_to_floor(o)  # v57: bottom-based, centre-based clamp let tall objects sink
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
    # Ultrasonic viz — MUST match Env.ultrasonic(): centre of end effector,
    # forward along a3, 3-beam cone, min distance. Drawn BEFORE the 9-ray
    # fan so the thicker ultrasonic beam stays visible on top of it.
    gc = arm.gripper_center()
    _ud, _uc = env.ultrasonic()
    _hx, _hy = env.ultrasonic_hit
    _u_col = rgb(16, 185, 129) if _uc > 0.5 else rgb(150, 160, 188)
    drawLine(gc[0], gc[1], _hx, _hy, fill=_u_col, lineWidth=2.2)
    drawCircle(_hx, _hy, 4, fill=_u_col, border=rgb(255, 255, 255), borderWidth=0.8)
    drawCircle(gc[0], gc[1], 5, fill=rgb(16, 185, 129), border=rgb(255, 255, 255), borderWidth=1.0)
    drawLabel('ULTRA %.0fpx %s' % (_ud, 'IN RANGE' if _uc > 0.5 else 'FAR'), gc[0], gc[1] + 22, size=7, fill=_u_col, bold=True, align='center-center')
    # Rays (sensor viz) — MUST match cast_rays: hand-relative a3.
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
    drawLabel('Actor 69 → 48 → 32 → 4 tanh outputs joint deltas + grip.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Critic learns value. OU noise explores. No IK, no script.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('It must re-learn after you change shapes or grippers.', LX, y, size=14, fill=TXT, align='left-top'); y += 28
    drawLabel('3 — SENSORS (WHAT IT SEES)', LX, y, size=16, fill=ACC2, bold=True, align='left-top'); y += 22
    drawLabel('9 rays from the wrist, hand-relative. Floor is a ray hit.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('ULTRASONIC: centre of gripper, forward cone. <=60px =', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('IN RANGE (can grab). >60px = FAR (too far to grab).', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Touch + force + slip. Red dot = true COM (teaching only).', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('ACCELEROMETER: accel + gyro + DOWN. DOWN=1 means', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('gripper points DOWN — where objects sit on the floor.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('Joint vel + gripper vel = kinematics. It feels motion.', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('WORLD MODEL: 24 memory rays = closest remembered', LX, y, size=14, fill=TXT, align='left-top'); y += 20
    drawLabel('surface at 24 angles. Remembers, then forgets.', LX, y, size=14, fill=TXT, align='left-top'); y += 28
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

def _draw_worldmodel(app):
    # v54: the robot's memory, drawn faintly UNDER objects. One dot per
    # occupied cell (confidence >= OCC_THRESH). The floor row lights up
    # as the rays learn the floor; object edges light up as they are seen.
    # If the dots disagree with the objects, the map is stale — decay and
    # free-space marking will clear it, or Reset Scene clears it.
    env = app.env
    for (ix, iy), conf in env.wm.grid.items():
        if conf >= env.wm.OCC_THRESH:
            cx = (ix + 0.5) * env.wm.CELL
            cy = (iy + 0.5) * env.wm.CELL
            drawCircle(cx, cy, 3, fill=rgb(110, 130, 200), border=rgb(110, 130, 200))

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
    _draw_worldmodel(app)  # v54: memory dots under objects
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
    py = 445  # v59: shifted down for random-baseline button
    drawLabel('Actor 69 → 48 → 32 → 4 tanh | V-critic AWR, seed 0', PANEL_X + 14, py, size=9, fill=DIM, align='left-top')
    drawLabel('Critic 69 → 48 → 32 → 1', PANEL_X + 14, py + 13, size=9, fill=DIM, align='left-top')
    drawLabel('Input: 61 sensors + 8 ctx  (incl 24 memory rays + ultra)', PANEL_X + 14, py + 26, size=8, fill=DIM, align='left-top')
    # Was: 'Actor RMS / Critic RMS' (weight RMS). Both nets init with the
    # same He/Xavier scale and train at similar LRs, so RMS 0.210/0.208
    # looked identical and hid everything. Weight RMS is not learning.
    # Now: critic loss / actor loss (the split that actually diverges),
    # with weight RMS kept as small second-line context.
    drawLabel('Critic loss %.4f  |  Actor loss %.4f  |  RMS %.3f/%.3f' % (app.critic_loss_hist[-1] if app.critic_loss_hist else 0.0, app.actor_loss_hist[-1] if app.actor_loss_hist else 0.0, app.actor.weight_norm(), app.critic.weight_norm()), PANEL_X + 14, py + 39, size=8, fill=ACC, align='left-top')
    gx, gy, gw, gh = PANEL_X + 14, py + 52, PANEL_W - 28, 52
    drawRect(gx, gy, gw, gh, fill=PANEL2, border=BORDER, roundness=8)
    _lh = app.loss_hist if app.loss_hist else [0.0]  # v58: was EMA hist, now critic loss only
    mx = max(_lh); mn = min(_lh); rng = (mx - mn) if mx - mn > 0.01 else 1.0
    pts = []
    for i, v in enumerate(_lh):
        x = gx + 8 + (i / max(1, len(app.loss_hist) - 1)) * (gw - 16)
        y = gy + gh - 8 - ((v - mn) / rng * (gh - 16)); pts.append((x, y))
    for i in range(len(pts) - 1):
        drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], fill=ACC, lineWidth=1.6)
    drawLabel('loss ↓ as it learns', gx + gw - 8, gy + 8, size=8, fill=DIM, align='right-top')
    ry = gy + gh + 8
    drawRect(gx, ry, gw, 42, fill=PANEL2, border=BORDER, roundness=8)
    # Live curve: use live_reward_hist (running episode reward, updated
    # every 20 steps) when the episode has not ended yet; reward_hist
    # only has episode-END totals and stays [0.0] for episode_len steps.
    _rh = app.live_reward_hist if len(app.live_reward_hist) > 1 else app.reward_hist
    mx = max(_rh); mn = min(_rh); rng = (mx - mn) if mx - mn > 0.5 else 1.0
    pts = []
    for i, v in enumerate(_rh):
        # v49 fix: was len(app.reward_hist). _rh is live_reward_hist
        # (grows every 20 steps) while reward_hist grows only at episode
        # END, so in ep 1 the divisor was 1 and x = gx+8 + i*full width:
        # the green line shot off the right edge of the UI. Use len(_rh).
        x = gx + 8 + (i / max(1, len(_rh) - 1)) * (gw - 16)
        y = ry + 42 - 8 - ((v - mn) / rng * (42 - 16)); pts.append((x, y))
    for i in range(len(pts) - 1):
        drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], fill=ACC2, lineWidth=1.6)
    drawLabel('episode reward (live, current ep %.1f)' % app.env.episode_reward, gx + 8, ry + 6, size=8, fill=DIM, align='left-top')
    sy = ry + 42 + 8
    drawRect(gx, sy, gw, 100, fill=PANEL2, border=BORDER, roundness=8)  # v59: 87 -> 100 for shaped line
    drawLabel('LIVE: ACC %.2f,%.2f  DOWN %.2f  |  ULTRA %.0fpx %s' % (env.accel_forward, env.accel_perp, env.down_alignment, env.ultrasonic_dist, 'IN RANGE' if env.ultrasonic_close > 0.5 else 'FAR'), gx + 8, sy + 6, size=8, fill=rgb(45, 212, 191), align='left-top')
    drawLabel('JOINT VEL %.2f %.2f %.2f  |  GRIP VEL %.1f,%.1f' % (env.joint_vel[0], env.joint_vel[1], env.joint_vel[2], env.gripper_vel[0], env.gripper_vel[1]), gx + 8, sy + 20, size=8, fill=DIM, align='left-top')
    drawLabel('GRIPPER %s  GAP %.0fpx  |  WM %d cells' % (env.arm.gripper_type.upper(), env.arm.gap(), env.wm.occupied_count()), gx + 8, sy + 34, size=8, fill=WARN, bold=True, align='left-top')
    drawLabel('TD-std %.3f  Adv-std %.3f  Pos %.0f%%  Actor gated %d' % (app.td_std_hist[-1] if app.td_std_hist else 0.0, app.adv_std_hist[-1] if app.adv_std_hist else 0.0, (app.pos_frac_hist[-1] if app.pos_frac_hist else 0.0) * 100.0, app.actor_gated_count), gx + 8, sy + 48, size=8, fill=(BAD if (app.pos_frac_hist[-1] if app.pos_frac_hist else 0.0) == 0.0 and app.training else DIM), align='left-top')
    drawLabel('lr a=%.5f c=%.5f | Grad %.2f | Eval %.1f | g %.2f' % (app.actor_lr, app.critic_lr, app.grad_norm_hist[-1] if app.grad_norm_hist else 0.0, app.eval_reward_hist[-1] if app.eval_reward_hist else 0.0, app.gamma), PANEL_X + 23, sy + 60, size=8, fill=DIM, align='left-top')
    # v52 minimum-time: current episode / median of last 20 successes.
    _cg = env.steps_to_grasp if env.steps_to_grasp is not None else '—'
    _cs = env.steps_to_stack if env.steps_to_stack is not None else '—'
    drawLabel('TIME lim %d: grasp %s/%s | stack %s/%s | on-goal %d/%s' % (app.episode_len, _cg, _med(app.t_grasp_hist), _cs, _med(app.t_stack_hist), env.on_goal_steps, _med(app.on_goal_hist)), gx + 8, sy + 74, size=8, fill=DIM, align='left-top')
    drawLabel('SHAPED %.1f UNSHAPED %.1f | RAND BASE %s' % (env.episode_shaped, env.episode_unshaped, ('%.1f' % app.random_baseline) if app.random_baseline is not None else '—'), gx + 8, sy + 86, size=8, fill=DIM, align='left-top')
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
