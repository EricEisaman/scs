"""
scs_presentation.py - Fullscreen / presentation for SCS (5 decisions).

Fullscreen is an ASYNCHRONOUS PRESENTATION MODE, not a canvas resize.

  * "Fills its container" / "fills the browser viewport" / "uses the
    browser Fullscreen API" are THREE SEPARATE MODES sharing sizing
    infrastructure. They are not three names for "big canvas".
  * The unit of fullscreen is a PRESENTATION CONTAINER (canvas + DOM
    UI), not necessarily the canvas. Controls outside that subtree
    do not accompany a fullscreened canvas.
  * CSS size, physical pixels, and rendering resolution are THREE
    SEPARATE NUMBERS. Fullscreen never means "render at max DPR".
  * Resizing is ONE coordinated renderer operation: drawing buffer,
    camera aspect, viewport, depth/MSAA, post targets, picking
    buffers update together, at a frame boundary, only when changed.
  * Mobile / embedding / cleanup are explicit: sensible defaults,
    no silent takeover of the host page, everything restored on exit.
"""

import math


# [STRIPPED 70 bytes]
# 3. CSS size vs physical pixels vs rendering resolution
# [STRIPPED 70 bytes]

class DisplayMetrics:
    """Published to effects + input code: BOTH display dimensions
    and drawing-buffer dimensions, never just one of them."""

    def __init__(self, css_width=0, css_height=0, dpr=1.0,
                 render_scale=1.0, pixel_ratio_cap=None, pixel_budget=None):
        self.css_width = int(css_width)
        self.css_height = int(css_height)
        self.dpr = float(dpr or 1.0)
        self.render_scale = float(render_scale or 1.0)
        # Caps: rendering at DPR 3 costs 9x the pixels of DPR 1 for the
        # same CSS area. Caps let apps trade sharpness for GPU cost
        # without changing layout.
        self.pixel_ratio_cap = pixel_ratio_cap  # e.g. 2.0 or None
        self.pixel_budget = pixel_budget        # e.g. 4_000_000 or None

    @property
    def effective_dpr(self):
        d = self.dpr * self.render_scale
        if self.pixel_ratio_cap is not None:
            d = min(d, float(self.pixel_ratio_cap))
        return d

    @property
    def backing_width(self):
        if self.css_width <= 0:
            return 0
        w = int(self.css_width * self.effective_dpr)
        return self._apply_budget(w, int(self.css_height * self.effective_dpr))[0]

    @property
    def backing_height(self):
        if self.css_height <= 0:
            return 0
        h = int(self.css_height * self.effective_dpr)
        return self._apply_budget(int(self.css_width * self.effective_dpr), h)[1]

    def _apply_budget(self, w, h):
        if self.pixel_budget is None or w <= 0 or h <= 0:
            return (w, h)
        pixels = w * h
        if pixels <= self.pixel_budget:
            return (w, h)
        # Scale down uniformly so aspect is preserved.
        s = math.sqrt(self.pixel_budget / float(pixels))
        return (max(1, int(w * s)), max(1, int(h * s)))

    @property
    def aspect(self):
        if self.css_height <= 0:
            return 1.0
        return self.css_width / float(self.css_height)

    @property
    def is_zero_sized(self):
        return self.css_width <= 0 or self.css_height <= 0

    def to_dict(self):
        return {
            'display': {'css_width': self.css_width,
                        'css_height': self.css_height,
                        'aspect': self.aspect},
            'drawing_buffer': {'width': self.backing_width,
                               'height': self.backing_height,
                               'effective_dpr': self.effective_dpr,
                               'dpr': self.dpr,
                               'render_scale': self.render_scale},
            'caps': {'pixel_ratio_cap': self.pixel_ratio_cap,
                     'pixel_budget': self.pixel_budget},
            'is_zero_sized': self.is_zero_sized,
        }

    def __eq__(self, other):
        if not isinstance(other, DisplayMetrics):
            return False
        return (self.css_width, self.css_height, self.effective_dpr,
                self.backing_width, self.backing_height) == \
               (other.css_width, other.css_height, other.effective_dpr,
                other.backing_width, other.backing_height)


def metrics_from_resize_observer(entry, render_scale=1.0,
                                 pixel_ratio_cap=None, pixel_budget=None):
    """Prefer devicePixelContentBoxSize (device pixels, directly
    observed) over CSS-size * DPR (derived). Fall back to the
    derived path when the browser does not provide it."""
    try:
        # devicePixelContentBoxSize: [{inlineSize, blockSize}] in device px.
        box = entry.get('devicePixelContentBoxSize')
        if box:
            bw = float(box[0].inlineSize)
            bh = float(box[0].blockSize)
            # Recover CSS size from contentBoxSize if present.
            css_box = entry.get('contentBoxSize')
            if css_box:
                cw = float(css_box[0].inlineSize)
                ch = float(css_box[0].blockSize)
            else:
                # No CSS box: infer from DPR.
                dpr = _device_pixel_ratio()
                cw, ch = bw / dpr, bh / dpr
            dpr = bw / cw if cw > 0 else _device_pixel_ratio()
            return DisplayMetrics(cw, ch, dpr, render_scale,
                                 pixel_ratio_cap, pixel_budget)
    except Exception:
        pass
    # Fallback: CSS size + DPR.
    try:
        rect = entry.get('contentRect')
        cw, ch = float(rect.width), float(rect.height)
    except Exception:
        cw, ch = 0.0, 0.0
    return DisplayMetrics(cw, ch, _device_pixel_ratio(), render_scale,
                          pixel_ratio_cap, pixel_budget)


def _device_pixel_ratio():
    try:
        from browser import window
        return float(getattr(window, 'devicePixelRatio', 1.0) or 1.0)
    except Exception:
        return 1.0


# [STRIPPED 70 bytes]
# Pointer conversion (Decision 4): current bounds + buffer scale
# [STRIPPED 70 bytes]

def client_to_canvas(client_x, client_y, rect, metrics):
    """Pointer -> canvas CSS coordinates, using the CURRENT bounds.
    Never screen dimensions, never a cached rect."""
    css_x = float(client_x) - float(rect.left)
    css_y = float(client_y) - float(rect.top)
    return (css_x, css_y)


def client_to_drawing_buffer(client_x, client_y, rect, metrics):
    """Pointer -> drawing-buffer pixels: CSS coords * buffer scale."""
    css_x, css_y = client_to_canvas(client_x, client_y, rect, metrics)
    if metrics.css_width <= 0 or metrics.css_height <= 0:
        return (css_x, css_y)
    sx = metrics.backing_width / float(metrics.css_width)
    sy = metrics.backing_height / float(metrics.css_height)
    return (css_x * sx, css_y * sy)


# [STRIPPED 70 bytes]
# 4. Coordinated resize: one path, coalesced, at a frame boundary
# [STRIPPED 70 bytes]

class ResizeCoordinator:
    """Coalesce repeated size notifications; apply the NEWEST at a
    defined frame boundary; reallocate only when dimensions change;
    zero-sized containers skip rendering without allocating."""

    def __init__(self, apply_fn):
        self._apply_fn = apply_fn  # fn(metrics) -> None
        self._pending = None
        self._current = None
        self._scheduled = False

    def notify(self, metrics):
        """Called by ResizeObserver / visualViewport / fullscreenchange.
        Stores the newest, schedules ONE application."""
        self._pending = metrics
        if not self._scheduled:
            self._scheduled = True
            try:
                from browser import window
                # Apply at the next frame boundary, not mid-frame.
                window.requestAnimationFrame(lambda _t: self.apply_pending())
            except Exception:
                self.apply_pending()

    def apply_pending(self):
        self._scheduled = False
        pending = self._pending
        self._pending = None
        if pending is None:
            return False
        if pending.is_zero_sized:
            # Zero-sized: do NOT attempt normal rendering, do NOT
            # allocate attachments. Remember it, skip the apply.
            self._current = pending
            return False
        if self._current is not None and pending == self._current:
            # Dimensions did not actually change: no reallocation.
            return False
        self._current = pending
        try:
            self._apply_fn(pending)
        except Exception:
            pass
        return True

    def current(self):
        return self._current

    def force_apply(self, metrics):
        self._current = None
        self._pending = metrics
        return self.apply_pending()


# [STRIPPED 70 bytes]
# 1+2+5. Presentation controller: async fullscreen, container, cleanup
# [STRIPPED 70 bytes]

MODE_EMBEDDED = 'embedded'      # fills its container
MODE_VIEWPORT = 'viewport'      # fills the browser viewport (CSS)
MODE_FULLSCREEN = 'fullscreen'  # browser Fullscreen API


class PresentationController:
    """Owns presentation mode, container, overlay, focus, observers.

    Rules:
    - State is DERIVED from document.fullscreenElement +
      fullscreenchange, never an optimistic Boolean.
    - enterFullscreen() is called DIRECTLY from a user gesture; it
      is never deferred behind asset loading. A rejected request
      reports the error and preserves embedded mode.
    - Fullscreen presents the CONTAINER (canvas + DOM UI), not the
      canvas alone. The overlay slot holds menus / captions / loading
      / exit button as semantic DOM, not canvas-redrawn controls.
    - Keyboard navigation + focus restoration are part of the contract.
    - Pointer / keyboard capture are separate, opt-in features.
    - The host owns page viewport config: this controller NEVER
      disables user zoom or writes <meta viewport>.
    - dispose() removes observers/listeners and restores styles,
      focus, and capture state. No global side effects left behind.
    """

    def __init__(self, canvas=None, container=None, overlay=None):
        self.canvas = canvas
        self.container = container if container is not None else canvas
        self.overlay = overlay  # DOM element for menus/captions/exit
        self.mode = MODE_EMBEDDED
        self._previous_focus = None
        self._saved_styles = {}  # element id -> {prop: value}
        self._resize_observer = None
        self._listeners = []     # (target, event, handler) for cleanup
        self._capture = None     # 'pointer' | 'keyboard' | None
        self.on_mode_change = None
        self.on_error = None
        self._resize_coordinator = None
        try:
            from browser import document
            self._doc = document
        except Exception:
            self._doc = None

    # -- feature detection + state (derived, not optimistic) --------
    def supports_fullscreen(self):
        try:
            if self._doc is None:
                return False
            return bool(getattr(self._doc, 'fullscreenEnabled', False))
        except Exception:
            return False

    def fullscreen_element(self):
        try:
            return getattr(self._doc, 'fullscreenElement', None)
        except Exception:
            return None

    def is_fullscreen(self):
        # Derived from the document, not from self.mode.
        el = self.fullscreen_element()
        if el is None:
            return False
        return el is self.container or el is self.canvas

    def current_mode(self):
        if self.is_fullscreen():
            return MODE_FULLSCREEN
        return self.mode

    # -- sizing observation (Decision 3+4) ----------------------------
    def observe_resize(self, coordinator):
        """Attach a ResizeObserver to the container. The coordinator
        coalesces notifications; this controller never resizes directly."""
        self._resize_coordinator = coordinator
        try:
            from browser import window
            RO = getattr(window, 'ResizeObserver', None)
            if RO is None:
                return False

            def _on_entries(entries, _obs):
                for entry in entries:
                    try:
                        m = metrics_from_resize_observer(
                            {'devicePixelContentBoxSize':
                                 getattr(entry, 'devicePixelContentBoxSize', None),
                             'contentBoxSize': getattr(entry, 'contentBoxSize', None),
                             'contentRect': entry.contentRect})
                        coordinator.notify(m)
                    except Exception:
                        pass

            obs = RO.new(_on_entries)
            obs.observe(self.container)
            self._resize_observer = obs
            self._listen('fullscreenchange', self._on_fullscreen_change)
            self._listen_visual_viewport()
            return True
        except Exception:
            return False

    def _listen_visual_viewport(self):
        # Mobile: visual viewport shrinks when an on-screen keyboard
        # appears. That is NOT a layout-viewport resize: do not treat
        # it as a layout change. We listen only to note it; the
        # coordinator applies a resize only when layout size changed.
        try:
            from browser import window
            vv = getattr(window, 'visualViewport', None)
            if vv is None:
                return
            def _on_vv(_ev=None):
                # Intentionally no coordinator.notify() here: visual
                # viewport changes do not change layout size. If an
                # app wants keyboard-aware layout, it reads
                # visualViewport.height itself.
                pass
            vv.addEventListener('resize', _on_vv)
            self._listeners.append((vv, 'resize', _on_vv))
        except Exception:
            pass

    def _listen(self, event, handler):
        try:
            target = self._doc if self._doc is not None else None
            if target is None:
                return
            target.addEventListener(event, handler)
            self._listeners.append((target, event, handler))
        except Exception:
            pass

    def _on_fullscreen_change(self, _ev=None):
        # State is re-derived here; a browser/user exit outside our
        # API still lands here, so UI and renderer cannot disagree.
        if self.is_fullscreen():
            self.mode = MODE_FULLSCREEN
            self._save_focus()
        else:
            if self.mode == MODE_FULLSCREEN:
                self.mode = MODE_EMBEDDED
                self._restore_focus()
        if self.on_mode_change is not None:
            try:
                self.on_mode_change(self.mode)
            except Exception:
                pass

    # -- fullscreen entry / exit (Decision 1) -------------------------
    def enter_fullscreen(self, element=None):
        """Returns a Promise. MUST be called directly from a user
        gesture (click / key). Never deferred behind asset loading.
        Rejection preserves embedded mode and reports the error."""
        target = element if element is not None else self.container
        if target is None:
            raise RuntimeError('No presentation container to fullscreen.')
        if not self.supports_fullscreen():
            # CSS viewport-filling fallback (Decision 5): still usable.
            self.enter_viewport_fallback()
            return _resolved(None)
        self._save_focus()
        try:
            from browser import window
            p = target.requestFullscreen()
            # requestFullscreen returns a Promise in modern browsers.
            try:
                p.then(lambda _v: self._on_fullscreen_change(),
                       lambda e: self._on_fullscreen_error(e))
            except Exception:
                pass
            return p
        except Exception as e:
            return self._on_fullscreen_error(e)

    def _on_fullscreen_error(self, err):
        # Rejected: preserve usable embedded mode, report, do not throw
        # into the caller or leave an optimistic "fullscreen" flag.
        self.mode = MODE_EMBEDDED
        if self.on_error is not None:
            try:
                self.on_error(err)
            except Exception:
                pass
        try:
            from browser import window
            return window.Promise.reject(err)
        except Exception:
            return None

    def exit_fullscreen(self):
        try:
            if self._doc is not None and self.is_fullscreen():
                return self._doc.exitFullscreen()
        except Exception:
            pass
        self.mode = MODE_EMBEDDED
        self._restore_focus()
        return _resolved(None)

    def enter_viewport_fallback(self):
        """CSS viewport-filling fallback when the Fullscreen API is
        unavailable: container fills the viewport via CSS, no API call."""
        self.mode = MODE_VIEWPORT
        try:
            self._save_style(self.container, 'position', 'fixed')
            self._save_style(self.container, 'inset', '0')
            self._save_style(self.container, 'width', '100vw')
            self._save_style(self.container, 'height', '100vh')
            self._save_style(self.container, 'zIndex', '1000')
            style = self.container.style
            style.position = 'fixed'
            style.inset = '0'
            style.width = '100vw'
            style.height = '100vh'
            style.zIndex = '1000'
        except Exception:
            pass

    def exit_viewport_fallback(self):
        self.mode = MODE_EMBEDDED
        self._restore_styles()

    # -- overlay slot (Decision 2) -------------------------------------
    def set_overlay(self, element):
        self.overlay = element

    def add_to_overlay(self, element):
        """Menus / captions / loading / exit button go here as DOM,
        not as canvas-redrawn controls."""
        if self.overlay is None:
            return False
        try:
            self.overlay.appendChild(element)
            return True
        except Exception:
            return False

    def make_exit_button(self, label='Exit fullscreen'):
        """Semantic DOM button (not a canvas-drawn control)."""
        try:
            from browser import document
            btn = document.createElement('button')
            btn.textContent = label
            btn.setAttribute('type', 'button')
            btn.setAttribute('aria-label', label)
            btn.bind('click', lambda _ev: self.exit_fullscreen())
            self.add_to_overlay(btn)
            return btn
        except Exception:
            return None

    # -- focus / styles / capture (Decision 2+5) ------------------------
    def _save_focus(self):
        try:
            self._previous_focus = self._doc.activeElement if self._doc else None
        except Exception:
            self._previous_focus = None

    def _restore_focus(self):
        try:
            el = self._previous_focus
            if el is not None and hasattr(el, 'focus'):
                el.focus()
        except Exception:
            pass
        self._previous_focus = None

    def _save_style(self, element, prop, _unused=None):
        try:
            key = id(element)
            if key not in self._saved_styles:
                self._saved_styles[key] = (element, {})
            _el, saved = self._saved_styles[key]
            if prop not in saved:
                saved[prop] = getattr(element.style, prop, '')
        except Exception:
            pass

    def _restore_styles(self):
        for _key, (element, saved) in list(self._saved_styles.items()):
            try:
                for prop, value in saved.items():
                    setattr(element.style, prop, value)
            except Exception:
                pass
        self._saved_styles.clear()

    def request_pointer_capture(self, element=None):
        """Opt-in, separate from fullscreen. Not implied by entering
        fullscreen."""
        try:
            el = element or self.canvas
            if el is not None and hasattr(el, 'setPointerCapture'):
                # Caller supplies a pointerId; this is the opt-in hook.
                self._capture = 'pointer'
                return True
        except Exception:
            pass
        return False

    def release_capture(self):
        self._capture = None

    # -- cleanup (Decision 5) -------------------------------------------
    def dispose(self):
        """Remove observers/listeners, restore styles/focus/capture.
        No global side effects left behind."""
        try:
            if self._resize_observer is not None:
                self._resize_observer.disconnect()
        except Exception:
            pass
        self._resize_observer = None
        for target, event, handler in list(self._listeners):
            try:
                target.removeEventListener(event, handler)
            except Exception:
                pass
        self._listeners.clear()
        self._restore_styles()
        self._restore_focus()
        self.release_capture()
        if self.mode == MODE_VIEWPORT:
            self.mode = MODE_EMBEDDED


def _resolved(value):
    try:
        from browser import window
        return window.Promise.resolve(value)
    except Exception:
        return value
