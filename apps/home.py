# apps/home.py
# SCS home shell. Full viewport width and height.
# Run as: ?app=home
# Optional initial app override: ?app=home&initial_app=grapher
# The shell is DOM plus one iframe. The SCS canvas stays behind the shell
# and only carries the theme background. Each child app runs in its own
# SCS runtime inside the iframe, so child state never collides with home.
#
# MVC:
#   Model: APPS, THEME_CONFIG, DEFAULT_APP, HomeModel below
#   View: HomeView, built only from extensions.widgets
#   Controller: HomeController, wires DOM events to model changes
#
# Rules followed here:
#   - One window access point: SCS_WINDOW. Nothing else reads window.
#   - No timeouts, no polling, no silent fallbacks. Events only.
#   - If DEFAULT_APP is not in APPS, startup raises instead of picking
#     another app and pretending it was the default.

# ---------------------------------------------------------------------------
# CONFIG: edit here. Everything below reads from these two configs.
# ---------------------------------------------------------------------------

APPS = [
    {"id": "drone_control_theory", "label": "Drone Control Theory",
     "description": "Control theory with a flying drone",
     "app": "drone_control_theory"},
    {"id": "fourier_ear_lab", "label": "Fourier Ear Lab",
     "description": "Hear how the ear does a Fourier transform",
     "app": "fourier_ear_lab"},
    {"id": "ofdm", "label": "OFDM",
     "description": "Orthogonal frequency division multiplexing",
     "app": "ofdm"},
    {"id": "robot_training", "label": "Robot Training",
     "description": "OpenArm 2.0 teleop training lab",
     "app": "robot_training"},
    {"id": "grapher", "label": "Grapher",
     "description": "Graph functions and data",
     "app": "grapher"},
    {"id": "gorillas", "label": "Gorillas",
     "description": "Classic Gorillas artillery game",
     "app": "gorillas"},
    {"id": "pacman", "label": "Pac-Man",
     "description": "Pac-Man clone",
     "app": "pacman"},
    {"id": "spatial_audio", "label": "Spatial Audio",
     "description": "3D Spatial Audio",
     "app": "spatial_audio"},
]

THEME_CONFIG = {
    "name": "scs-dark",
    "bg": "#0f1115",
    "fg": "#e8eaf0",
    "bar_bg": "#171a21",
    "bar_fg": "#e8eaf0",
    "panel_bg": "#1c1f27",
    "panel_fg": "#e8eaf0",
    "frame_bg": "#000000",
    "border": "#2c303a",
    "button_bg": "#232733",
    "button_fg": "#e8eaf0",
    "button_hover": "#2f3542",
    "accent": "#4f7cff",
    "accent_fg": "#ffffff",
    "error": "#ff6b6b",
    "font": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    "radius": "8px",
}

# Default loaded app. Must be one of the ids in APPS above.
DEFAULT_APP = "drone_control_theory"

HOME_TITLE = "SCS Home"

# ---------------------------------------------------------------------------
# SCS plus the one window access point
# ---------------------------------------------------------------------------

from scs import *
from browser import window as SCS_WINDOW
from extensions.widgets import (
    Theme,
    apply_theme,
    HamburgerMenu,
    TopBar,
    AppFrame,
    FullscreenController,
    IconButton,
    FloatingImageButton,
    StatusBar,
)

# Document comes from the one window object, never from a second import.
DOCUMENT = SCS_WINDOW.document

# Guard so runApp running twice does not build two shells.
_HOME_STARTED = False


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class HomeModel:
    def __init__(self, apps, default_app):
        if not isinstance(apps, list) or not apps:
            raise ValueError("APPS must be a non empty list")
        self.apps = [dict(entry) for entry in apps]
        self.by_id = {}
        for entry in self.apps:
            for key in ("id", "label", "app"):
                if key not in entry:
                    raise ValueError("App entry is missing required key: " + key)
            if entry["id"] in self.by_id:
                raise ValueError("Duplicate app id in APPS: " + entry["id"])
            self.by_id[entry["id"]] = entry
        if default_app not in self.by_id:
            raise ValueError(
                "DEFAULT_APP %r is not in APPS. Fix the config, no fallback is applied."
                % default_app
            )
        self.default_app = default_app
        self.current_app_id = default_app

    def get(self, app_id):
        if app_id not in self.by_id:
            raise ValueError("Unknown app id: " + str(app_id))
        return self.by_id[app_id]

    def menu_items(self):
        items = []
        for entry in self.apps:
            items.append({
                "id": entry["id"],
                "label": entry["label"],
                "description": entry.get("description", ""),
            })
        return items


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class HomeView:
    def __init__(self, model, theme):
        self.model = model
        self.theme = theme
        self.shell = DOCUMENT.createElement("div")
        self.shell.className = "widgets-shell"
        self.topbar = TopBar(HOME_TITLE)
        self.hamburger = HamburgerMenu(self.topbar.left, items=model.menu_items())
        self.fullscreen_button = IconButton("\u26f6", "Fullscreen loaded app")
        self.topbar.right <= self.fullscreen_button.element
        self.app_frame = AppFrame()
        self.status = StatusBar("Ready")
        # Floating 96x96 image button, bottom right, above the status bar.
        # Image is /scs_logo_512.png at the repo root.
        # Href is updated by the controller to sandbox.html?app=<current app>.
        self.sandbox_button = FloatingImageButton(
            "/scs_logo_512.png",
            "Open source in sandbox.",
            href="#",
        )
        self.shell.appendChild(self.topbar.element)
        self.shell.appendChild(self.app_frame.element)
        self.shell.appendChild(self.status.element)
        self.shell.appendChild(self.sandbox_button.element)
        DOCUMENT.body.appendChild(self.shell)
        # Fullscreen target is resolved at click time from the app frame,
        # so it always acts on the currently loaded app.
        # Delegate to the child module wrapper, not the AppFrame wrapper,
        # so the child's own fullscreen handler scales its canvas.
        # This is what the restored ScsFullscreenSuppressor / ChildCanvasScaler
        # code in widgets.py is for. Fallback inside AppFrame handles non SCS modules.
        self.fullscreen = FullscreenController(
            lambda: self.app_frame.fullscreen_target,
            button=self.fullscreen_button,
            request_callback=self.app_frame.request_module_fullscreen,
            exit_callback=self.app_frame.exit_module_fullscreen,
            is_fullscreen_callback=self.app_frame.is_module_fullscreen,
        )

    def set_active(self, app_id):
        entry = self.model.get(app_id)
        self.hamburger.set_active(app_id)
        self.topbar.set_title(HOME_TITLE + "  |  " + entry["label"])
        return self

    def set_status(self, text, is_error=False):
        self.status.set_text(text, is_error=is_error)
        return self

    def set_sandbox_url(self, sandbox_url, logo_url=None):
        self.sandbox_button.set_href(sandbox_url)
        if logo_url:
            self.sandbox_button.set_image(logo_url)
        return self

    def destroy(self):
        self.fullscreen.destroy()
        self.hamburger.destroy()
        self.app_frame.destroy()
        if self.shell.parentNode is not None:
            self.shell.parentNode.removeChild(self.shell)
        return self


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class HomeController:
    def __init__(self, model, view, scs_app):
        self.model = model
        self.view = view
        self.scs_app = scs_app
        self.view.hamburger.on("select", self.on_menu_select)
        self.view.app_frame.on("loading", self.on_app_loading)
        self.view.app_frame.on("loaded", self.on_app_loaded)
        self.view.fullscreen.on("change", self.on_fullscreen_change)
        SCS_WINDOW.bind("resize", self.on_resize)
        SCS_WINDOW.bind("popstate", self.on_popstate)
        self.sync_from_url()
        self.load_current()

    # URL helpers. The child URL is built from the current page path,
    # so the shell works at /, /scs/, /scs/index.html, or any subpath.
    # Renderer is preserved when present, never invented.

    def _base_path(self):
        return SCS_WINDOW.location.pathname

    def _params(self):
        return SCS_WINDOW.URLSearchParams.new(SCS_WINDOW.location.search)

    def _child_url(self, app_id):
        entry = self.model.get(app_id)
        params = self._params()
        renderer = params.get("renderer")
        url = self._base_path() + "?app=" + entry["app"]
        if renderer:
            url = url + "&renderer=" + renderer
        return url

    def _base_dir(self):
        # Directory containing this page, with trailing slash.
        # Used only for child app URLs, which load through this same page.
        # Sandbox and logo are NOT here, they are at the repo root.
        path = SCS_WINDOW.location.pathname
        if path.endswith("/"):
            return path
        last = path.rsplit("/", 1)[-1]
        if "." in last:
            return path[: path.rfind("/") + 1]
        return path + "/"

    def _sandbox_url(self, app_id):
        # sandbox.html lives at the repo root, same place as scs_logo_512.png.
        # Leading slash, not _base_dir, so it stays at the repo root even
        # if Home is served from a subpath.
        entry = self.model.get(app_id)
        params = self._params()
        renderer = params.get("renderer")
        url = "/sandbox.html?app=" + entry["app"]
        if renderer:
            url = url + "&renderer=" + renderer
        return url

    def _logo_url(self):
        # scs_logo_512.png is at the repo root.
        return "/scs_logo_512.png"

    def _sync_sandbox_button(self):
        # Href must follow the current app, so the button always opens
        # the source of the app currently shown in the frame.
        self.view.set_sandbox_url(
            self._sandbox_url(self.model.current_app_id),
            logo_url=self._logo_url(),
        )
        return self

    def _initial_app_from_url(self):
        params = self._params()
        wanted = params.get("initial_app")
        if wanted is None or wanted == "":
            return self.model.default_app
        if wanted not in self.model.by_id:
            raise ValueError("initial_app %r is not in APPS" % wanted)
        return wanted

    def sync_from_url(self):
        wanted = self._initial_app_from_url()
        if wanted != self.model.current_app_id:
            self.model.current_app_id = wanted
        return self

    def sync_url_to_current(self):
        params = self._params()
        params.set("initial_app", self.model.current_app_id)
        query = "?" + params.toString()
        SCS_WINDOW.history.replaceState(None, "", self._base_path() + query)
        return self

    def load_current(self):
        app_id = self.model.current_app_id
        entry = self.model.get(app_id)
        self.view.set_active(app_id)
        self.view.app_frame.load(self._child_url(app_id), app_id, title=entry["label"])
        self._sync_sandbox_button()
        self.sync_url_to_current()
        return self

    def select_app(self, app_id):
        entry = self.model.get(app_id)
        if app_id == self.model.current_app_id:
            self.view.set_active(app_id)
            return self
        self.model.current_app_id = app_id
        self.view.set_active(app_id)
        self.view.app_frame.load(self._child_url(app_id), app_id, title=entry["label"])
        self._sync_sandbox_button()
        self.sync_url_to_current()
        return self

    # Event handlers. All state changes come from real DOM events.

    def on_menu_select(self, item):
        self.select_app(item["id"])

    def on_app_loading(self, app_id, url):
        entry = self.model.get(app_id)
        self.view.set_status("Loading " + entry["label"] + "...")

    def on_app_loaded(self, app_id, url):
        entry = self.model.get(app_id)
        self.view.set_status(entry["label"] + " ready")

    def on_fullscreen_change(self, is_fullscreen):
        if is_fullscreen:
            self.view.set_status(self.model.get(self.model.current_app_id)["label"] + " fullscreen")
        else:
            self.view.set_status(self.model.get(self.model.current_app_id)["label"] + " ready")

    def on_resize(self, event):
        width = int(SCS_WINDOW.innerWidth)
        height = int(SCS_WINDOW.innerHeight)
        self.scs_app.width = width
        self.scs_app.height = height

    def on_popstate(self, event):
        self.sync_from_url()
        self.load_current()


# ---------------------------------------------------------------------------
# SCS app entrypoints
# ---------------------------------------------------------------------------

def onAppStart(app):
    global _HOME_STARTED
    if _HOME_STARTED:
        return
    _HOME_STARTED = True
    theme = apply_theme(Theme(THEME_CONFIG))
    app.width = int(SCS_WINDOW.innerWidth)
    app.height = int(SCS_WINDOW.innerHeight)
    app.background = theme.get("bg")
    model = HomeModel(APPS, DEFAULT_APP)
    view = HomeView(model, theme)
    app.home_controller = HomeController(model, view, app)


def redrawAll(app):
    # The View is DOM plus iframe. The canvas only carries the background.
    # Nothing is drawn here on purpose.
    pass


runApp(width=int(SCS_WINDOW.innerWidth), height=int(SCS_WINDOW.innerHeight))
