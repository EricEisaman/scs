# extensions/widgets.py
# SCS extension. App agnostic DOM widgets for Brython.
# Builds on the ideas of brython-widgets (Menu, Dialog) with a fixed,
# event driven implementation: no timeouts, no polling, no silent fallbacks.
# Model layer only. This file never imports scs. Apps import it as:
#   from extensions.widgets import Theme, HamburgerMenu, AppFrame, FullscreenController
#
# Every widget is driven by DOM events: click, keydown, load,
# fullscreenchange, input, change. If a required capability is missing,
# the widget raises an explicit error instead of faking a result.

from browser import document, html, window

__all__ = [
    "Theme",
    "DEFAULT_THEME",
    "apply_theme",
    "WIDGETS_CSS",
    "EventEmitter",
    "Widget",
    "Button",
    "IconButton",
    "Menu",
    "HamburgerMenu",
    "TopBar",
    "AppFrame",
    "FullscreenController",
    "ScsFullscreenSuppressor",
    "hide_scs_fullscreen_buttons",
    "Dialog",
    "InfoDialog",
    "EntryDialog",
    "ConfirmDialog",
    "Select",
    "Slider",
    "Toggle",
    "TextInput",
    "StatusBar",
    "Panel",
]


# One window and document reference for this extension. All code below
# uses these two names, nothing else reaches for window or document.
_WINDOW = window
_DOCUMENT = document


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

WIDGETS_CSS = """
.widgets-shell{position:fixed;inset:0;left:0;top:0;right:0;bottom:0;width:100vw;width:100dvw;height:100vh;height:100dvh;max-width:100vw;max-width:100dvw;display:flex;flex-direction:column;overflow:hidden;background:var(--widgets-bg);color:var(--widgets-fg);font-family:var(--widgets-font);z-index:10;box-sizing:border-box}
.widgets-topbar{flex:0 0 48px;height:48px;width:100%;min-width:0;display:flex;align-items:center;gap:12px;padding:0 12px;background:var(--widgets-bar-bg);color:var(--widgets-bar-fg);border-bottom:1px solid var(--widgets-border);box-sizing:border-box}
.widgets-topbar-left{display:flex;align-items:center;gap:8px;min-width:48px}
.widgets-topbar-center{flex:1;display:flex;align-items:center;min-width:0}
.widgets-topbar-title{font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.widgets-topbar-right{display:flex;align-items:center;gap:8px}
.widgets-button{appearance:none;border:1px solid var(--widgets-border);background:var(--widgets-button-bg);color:var(--widgets-button-fg);border-radius:var(--widgets-radius);padding:6px 12px;font:inherit;font-size:14px;cursor:pointer}
.widgets-button:hover{background:var(--widgets-button-hover)}
.widgets-button:disabled{opacity:0.5;cursor:default}
.widgets-button.is-active{background:var(--widgets-accent);color:var(--widgets-accent-fg);border-color:var(--widgets-accent)}
.widgets-icon-button{appearance:none;border:1px solid var(--widgets-border);background:var(--widgets-button-bg);color:var(--widgets-button-fg);border-radius:var(--widgets-radius);width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;font-size:18px;line-height:1;cursor:pointer}
.widgets-icon-button:hover{background:var(--widgets-button-hover)}
.widgets-icon-button.is-active{background:var(--widgets-accent);color:var(--widgets-accent-fg)}
.widgets-hamburger{position:relative}
.widgets-hamburger-panel{position:absolute;top:44px;left:0;min-width:280px;max-width:min(92vw,360px);background:var(--widgets-panel-bg);color:var(--widgets-panel-fg);border:1px solid var(--widgets-border);border-radius:var(--widgets-radius);box-shadow:0 12px 32px rgba(0,0,0,0.35);padding:6px;display:none;z-index:50}
.widgets-hamburger-panel.is-open{display:block}
.widgets-menu{margin:0;padding:0;list-style:none}
.widgets-menu-item{width:100%;box-sizing:border-box;display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;background:transparent;border:0;color:inherit;font:inherit;font-size:14px;padding:10px 12px;border-radius:calc(var(--widgets-radius) - 2px);cursor:pointer}
.widgets-menu-item:hover,.widgets-menu-item:focus-visible{background:var(--widgets-button-hover);outline:none}
.widgets-menu-item.is-active{background:var(--widgets-accent);color:var(--widgets-accent-fg)}
.widgets-menu-item-desc{font-size:12px;opacity:0.75;font-weight:400}
.widgets-menu-submenu{margin:4px 0 4px 12px;padding-left:8px;border-left:1px solid var(--widgets-border);display:none}
.widgets-menu-submenu.is-open{display:block}
.widgets-app-frame{flex:1 1 auto;min-height:0;min-width:0;width:100%;position:relative;background:var(--widgets-frame-bg);overflow:hidden}
.widgets-app-frame iframe{width:100%;height:100%;min-width:0;min-height:0;border:0;display:block;background:var(--widgets-frame-bg)}
.widgets-app-loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:var(--widgets-frame-bg);color:var(--widgets-fg);font-size:14px;pointer-events:none}
.widgets-app-loading.is-hidden{display:none}
.widgets-statusbar{flex:0 0 28px;height:28px;width:100%;min-width:0;display:flex;align-items:center;padding:0 12px;font-size:12px;background:var(--widgets-bar-bg);color:var(--widgets-bar-fg);border-top:1px solid var(--widgets-border);box-sizing:border-box;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.widgets-statusbar.is-error{color:var(--widgets-error)}
/* SCS runtime fullscreen button: the runtime creates its own button for the SCS canvas. Home keeps only its top bar button, so hide any id or class with fullscreen in this document. Home's own button has no fullscreen in id or class, only in aria-label, so this rule leaves it alone. The JS suppressor below covers glyph only buttons and iframe documents. */
[id*="fullscreen"],[class*="fullscreen"]{display:none !important}
.widgets-dialog-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:100}
.widgets-dialog{position:fixed;min-width:280px;max-width:min(92vw,480px);background:var(--widgets-panel-bg);color:var(--widgets-panel-fg);border:1px solid var(--widgets-border);border-radius:var(--widgets-radius);box-shadow:0 16px 48px rgba(0,0,0,0.4);z-index:101}
.widgets-dialog-title{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid var(--widgets-border);cursor:move;font-weight:600}
.widgets-dialog-close{appearance:none;border:0;background:transparent;color:inherit;font-size:20px;line-height:1;cursor:pointer}
.widgets-dialog-panel{padding:12px}
.widgets-dialog-actions{display:flex;justify-content:center;gap:8px;padding:0 12px 12px}
.widgets-field{display:flex;flex-direction:column;gap:4px;font-size:14px}
.widgets-field input,.widgets-field select{font:inherit;padding:6px 8px;border:1px solid var(--widgets-border);border-radius:var(--widgets-radius);background:var(--widgets-button-bg);color:inherit}
.widgets-panel{border:1px solid var(--widgets-border);border-radius:var(--widgets-radius);padding:12px;background:var(--widgets-panel-bg)}
"""

DEFAULT_THEME = {
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

_THEME_REQUIRED_KEYS = [
    "name", "bg", "fg", "bar_bg", "bar_fg", "panel_bg", "panel_fg",
    "frame_bg", "border", "button_bg", "button_fg", "button_hover",
    "accent", "accent_fg", "error", "font", "radius",
]


class Theme:
    """Immutable theme tokens. Missing keys raise, they are never guessed."""

    def __init__(self, tokens):
        if not isinstance(tokens, dict):
            raise TypeError("Theme tokens must be a dict")
        missing = [k for k in _THEME_REQUIRED_KEYS if k not in tokens]
        if missing:
            raise ValueError("Theme is missing required keys: " + ", ".join(missing))
        self._tokens = dict(tokens)

    @classmethod
    def default(cls):
        return cls(dict(DEFAULT_THEME))

    @property
    def name(self):
        return self._tokens["name"]

    def get(self, key):
        return self._tokens[key]

    def as_dict(self):
        return dict(self._tokens)

    def to_css_variables(self):
        lines = [":root {"]
        mapping = {
            "bg": "--widgets-bg", "fg": "--widgets-fg",
            "bar_bg": "--widgets-bar-bg", "bar_fg": "--widgets-bar-fg",
            "panel_bg": "--widgets-panel-bg", "panel_fg": "--widgets-panel-fg",
            "frame_bg": "--widgets-frame-bg", "border": "--widgets-border",
            "button_bg": "--widgets-button-bg", "button_fg": "--widgets-button-fg",
            "button_hover": "--widgets-button-hover", "accent": "--widgets-accent",
            "accent_fg": "--widgets-accent-fg", "error": "--widgets-error",
            "font": "--widgets-font", "radius": "--widgets-radius",
        }
        for key, var in mapping.items():
            lines.append("  %s: %s;" % (var, self._tokens[key]))
        lines.append("}")
        return "\n".join(lines)


def _ensure_style_element():
    style = _DOCUMENT.select_one("style[data-widgets-theme]")
    if style is None:
        style = html.STYLE()
        style.attrs["data-widgets-theme"] = "true"
        _DOCUMENT <= style
    return style


def apply_theme(theme):
    """Apply a Theme or a full token dict. Returns the Theme used."""
    if isinstance(theme, dict):
        theme = Theme(theme)
    if not isinstance(theme, Theme):
        raise TypeError("apply_theme needs a Theme or a token dict")
    style = _ensure_style_element()
    style.text = theme.to_css_variables() + "\n" + WIDGETS_CSS
    return theme


# ---------------------------------------------------------------------------
# Events and base widget
# ---------------------------------------------------------------------------

class EventEmitter:
    """Synchronous callback registry. No timers, no polling."""

    def __init__(self):
        self._listeners = {}

    def on(self, event_name, callback):
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._listeners.setdefault(event_name, []).append(callback)
        return callback

    def off(self, event_name, callback):
        listeners = self._listeners.get(event_name, [])
        if callback in listeners:
            listeners.remove(callback)

    def emit(self, event_name, *args):
        for callback in list(self._listeners.get(event_name, [])):
            callback(*args)


class Widget(EventEmitter):
    def __init__(self, element):
        EventEmitter.__init__(self)
        self.element = element

    def mount(self, parent):
        parent <= self.element
        return self

    def unmount(self):
        if self.element.parent is not None:
            self.element.remove()
        return self

    def show(self):
        self.element.style.display = ""
        return self

    def hide(self):
        self.element.style.display = "none"
        return self

    def add_class(self, name):
        self.element.classList.add(name)
        return self

    def remove_class(self, name):
        self.element.classList.remove(name)
        return self


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

class Button(Widget):
    def __init__(self, label, on_click=None, variant="button", disabled=False):
        element = html.BUTTON(label, Class="widgets-button")
        Widget.__init__(self, element)
        self.label = label
        if on_click is not None:
            self.on("click", on_click)
        self.element.bind("click", self._on_click)
        self.set_disabled(disabled)

    def _on_click(self, event):
        self.emit("click", event)

    def set_label(self, label):
        self.label = label
        self.element.text = label
        return self

    def set_disabled(self, disabled):
        self.element.disabled = bool(disabled)
        return self


class IconButton(Widget):
    """Small square button with a text glyph and an accessible label."""

    def __init__(self, glyph, aria_label, on_click=None):
        element = html.BUTTON(glyph, Class="widgets-icon-button")
        Widget.__init__(self, element)
        self.glyph = glyph
        self.element.attrs["aria-label"] = aria_label
        self.element.attrs["title"] = aria_label
        if on_click is not None:
            self.on("click", on_click)
        self.element.bind("click", self._on_click)

    def _on_click(self, event):
        self.emit("click", event)

    def set_active(self, active):
        if active:
            self.element.classList.add("is-active")
        else:
            self.element.classList.remove("is-active")
        return self

    def set_glyph(self, glyph):
        self.glyph = glyph
        self.element.text = glyph
        return self


# ---------------------------------------------------------------------------
# Menu, in the spirit of brython-widgets Menu
# ---------------------------------------------------------------------------

class Menu(EventEmitter):
    """Vertical menu list. Supports items and submenus.

    Item API keeps the brython-widgets shape:
        @menu.add_item("Open")
        def open_item(event):
            ...
    A direct callback is also accepted: menu.add_item("Open", open_item).
    Submenus: submenu = menu.add_menu("More"), then submenu.add_item(...).
    """

    def __init__(self, container=None, parent=None):
        EventEmitter.__init__(self)
        self.parent = parent
        self.container = container if container is not None else _DOCUMENT.body
        self.element = html.DIV(Class="widgets-menu-wrap")
        self.list_element = html.UL(Class="widgets-menu")
        self.element <= self.list_element
        self.container <= self.element
        self._items = []
        self._submenus = []
        self._active_id = None

    def _make_item_element(self, name, item_id, description):
        item = html.LI()
        button = html.BUTTON(Class="widgets-menu-item")
        label = html.SPAN(name)
        button <= label
        if description:
            button <= html.SPAN(description, Class="widgets-menu-item-desc")
        button.attrs["data-menu-item-id"] = item_id
        button.attrs["type"] = "button"
        item <= button
        return item, button

    def add_item(self, name, callback=None, item_id=None, description=""):
        item_id = item_id if item_id is not None else name
        item, button = self._make_item_element(name, item_id, description)
        self.list_element <= item
        record = {"id": item_id, "name": name, "description": description,
                  "button": button, "item": item, "callback": callback}
        self._items.append(record)

        def _on_click(event):
            event.stopPropagation()
            if record["callback"] is not None:
                record["callback"](event)
            self.emit("select", record)

        button.bind("click", _on_click)

        def deco(func):
            record["callback"] = func
            return func

        if callback is not None:
            return callback
        return deco

    def add_menu(self, name, item_id=None):
        item_id = item_id if item_id is not None else name
        item, button = self._make_item_element(name + " ...", item_id, "")
        self.list_element <= item
        submenu = Menu(container=item, parent=self)
        submenu.element.classList.add("widgets-menu-submenu")
        self._submenus.append(submenu)

        def _toggle(event):
            event.stopPropagation()
            is_open = "is-open" in submenu.element.classList
            for other in self._submenus:
                other.element.classList.remove("is-open")
            if not is_open:
                submenu.element.classList.add("is-open")

        button.bind("click", _toggle)
        return submenu

    def set_active(self, item_id):
        self._active_id = item_id
        for record in self._items:
            if record["id"] == item_id:
                record["button"].classList.add("is-active")
            else:
                record["button"].classList.remove("is-active")
        for submenu in self._submenus:
            submenu.set_active(item_id)
        return self

    def clear(self):
        self.list_element.clear()
        self._items = []
        for submenu in self._submenus:
            submenu.element.remove()
        self._submenus = []
        self._active_id = None
        return self

    def hide_submenus(self):
        for submenu in self._submenus:
            submenu.element.classList.remove("is-open")
            submenu.hide_submenus()
        return self

    def destroy(self):
        self.clear()
        self.element.remove()
        return self


class HamburgerMenu(Widget):
    """Hamburger button plus a dropdown panel driven by an item list.

    Items are plain dicts: {"id": ..., "label": ..., "description": ...}.
    Selection is reported through on_select(item) and the "select" event.
    """

    def __init__(self, container, items=None, on_select=None):
        wrapper = html.DIV(Class="widgets-hamburger")
        Widget.__init__(self, wrapper)
        self.button = IconButton("\u2630", "Menu")
        self.panel = html.DIV(Class="widgets-hamburger-panel")
        self.panel.attrs["role"] = "menu"
        self.menu = Menu(container=self.panel)
        self.element <= self.button.element
        self.element <= self.panel
        if container is not None:
            container <= self.element
        self._items = []
        self._active_id = None
        self._is_open = False
        if on_select is not None:
            self.on("select", on_select)
        self.button.on("click", self._on_button_click)
        self.menu.on("select", self._on_menu_select)
        _DOCUMENT.bind("click", self._on_document_click)
        _DOCUMENT.bind("keydown", self._on_document_keydown)
        if items:
            self.set_items(items)

    def set_items(self, items):
        if not isinstance(items, list):
            raise TypeError("HamburgerMenu items must be a list")
        for item in items:
            for key in ("id", "label"):
                if key not in item:
                    raise ValueError("Menu item is missing required key: " + key)
        self._items = [dict(item) for item in items]
        self.menu.clear()
        for item in self._items:
            self.menu.add_item(item["label"], item_id=item["id"],
                               description=item.get("description", ""))
        if self._active_id is not None:
            self.menu.set_active(self._active_id)
        return self

    def set_active(self, item_id):
        self._active_id = item_id
        self.menu.set_active(item_id)
        return self

    def get_active(self):
        return self._active_id

    def open(self):
        self._is_open = True
        self.panel.classList.add("is-open")
        self.button.set_active(True)
        self.button.element.attrs["aria-expanded"] = "true"
        self.emit("open")
        return self

    def close(self):
        self._is_open = False
        self.panel.classList.remove("is-open")
        self.button.set_active(False)
        self.button.element.attrs["aria-expanded"] = "false"
        self.menu.hide_submenus()
        self.emit("close")
        return self

    def toggle(self):
        if self._is_open:
            self.close()
        else:
            self.open()
        return self

    def _on_button_click(self, event):
        event.stopPropagation()
        self.toggle()

    def _on_menu_select(self, record):
        matched = None
        for item in self._items:
            if item["id"] == record["id"]:
                matched = item
                break
        if matched is None:
            raise ValueError("Selected menu item is not in the item list: " + str(record["id"]))
        self.set_active(matched["id"])
        self.close()
        self.emit("select", matched)

    def _on_document_click(self, event):
        if not self._is_open:
            return
        target = event.target
        if target is None:
            return
        node = target
        while node is not None:
            if node is self.element:
                return
            node = node.parent
        self.close()

    def _on_document_keydown(self, event):
        if event.key == "Escape" and self._is_open:
            self.close()

    def destroy(self):
        _DOCUMENT.unbind("click", self._on_document_click)
        _DOCUMENT.unbind("keydown", self._on_document_keydown)
        self.menu.destroy()
        self.unmount()
        return self


# ---------------------------------------------------------------------------
# Top bar, app frame, fullscreen
# ---------------------------------------------------------------------------

class TopBar(Widget):
    def __init__(self, title=""):
        element = html.HEADER(Class="widgets-topbar")
        Widget.__init__(self, element)
        self.left = html.DIV(Class="widgets-topbar-left")
        self.center = html.DIV(Class="widgets-topbar-center")
        self.right = html.DIV(Class="widgets-topbar-right")
        self.title_element = html.DIV(title, Class="widgets-topbar-title")
        self.center <= self.title_element
        self.element <= self.left
        self.element <= self.center
        self.element <= self.right

    def set_title(self, title):
        self.title_element.text = title
        return self


# ---------------------------------------------------------------------------
# SCS fullscreen button suppression
# ---------------------------------------------------------------------------
# The SCS runtime creates its own fullscreen button for the SCS canvas,
# fixed at the bottom right. Home keeps only its top bar button, so the
# runtime button must be hidden, both in the top document and inside the
# loaded module iframe, which is same origin. This is done with a sweep
# plus a MutationObserver, so buttons created after home starts are also
# hidden. No polling, no timeouts. Home's own button is inside the shell,
# so it is excluded by exclude_root and never hidden.

_SCS_FULLSCREEN_GLYPHS = ("\u26f6", "\u2922", "\u26f6\ufe0f", "\u2197")


def _suppressor_attr(element, name):
    try:
        value = element.getAttribute(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    try:
        attrs = element.attrs
        if attrs is not None and name in attrs:
            return str(attrs[name])
    except Exception:
        pass
    try:
        value = getattr(element, name, None)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return ""


def _suppressor_text(element):
    try:
        value = element.textContent
        if value is not None:
            return str(value).strip()
    except Exception:
        pass
    try:
        return str(element.text).strip()
    except Exception:
        return ""


def _is_inside(element, root):
    if root is None:
        return False
    node = element
    while node is not None:
        if node is root:
            return True
        try:
            node = node.parent
        except Exception:
            try:
                node = node.parentNode
            except Exception:
                return False
    return False


def _is_scs_fullscreen_button(element, exclude_root):
    if element is None or exclude_root is not None and _is_inside(element, exclude_root):
        return False
    try:
        tag = str(element.tagName).lower()
    except Exception:
        tag = ""
    if tag in ("script", "style", "link", "meta", "title", "head", "html", "body"):
        return False
    hay = " ".join([
        _suppressor_attr(element, "id"),
        _suppressor_attr(element, "class"),
        _suppressor_attr(element, "title"),
        _suppressor_attr(element, "aria-label"),
    ]).lower()
    if "fullscreen" in hay:
        return True
    text = _suppressor_text(element)
    if text in _SCS_FULLSCREEN_GLYPHS:
        if tag in ("button", "div", "span", "a"):
            return True
    return False


def hide_scs_fullscreen_buttons(doc, exclude_root=None):
    """Hide SCS runtime fullscreen buttons in doc. Returns hidden count."""
    if doc is None:
        return 0
    try:
        nodes = doc.querySelectorAll("*")
    except Exception:
        try:
            nodes = doc.select("*")
        except Exception:
            return 0
    hidden = 0
    try:
        count = len(nodes)
    except Exception:
        count = 0
    for i in range(count):
        try:
            element = nodes[i]
        except Exception:
            continue
        if _is_scs_fullscreen_button(element, exclude_root):
            try:
                element.style.display = "none"
                try:
                    element.setAttribute("data-widgets-hidden-scs-fullscreen", "true")
                except Exception:
                    pass
                hidden += 1
            except Exception:
                continue
    return hidden


class ScsFullscreenSuppressor:
    """Sweep plus MutationObserver that hides SCS runtime fullscreen buttons."""

    def __init__(self, doc, exclude_root=None):
        if doc is None:
            raise ValueError("ScsFullscreenSuppressor needs a document")
        self.doc = doc
        self.exclude_root = exclude_root
        self._observer = None
        self.sweep()
        try:
            observer_cls = _WINDOW.MutationObserver
        except Exception:
            observer_cls = None
        if observer_cls is not None:
            try:
                self._observer = observer_cls.new(self._on_mutations)
                target = None
                try:
                    target = doc.body
                except Exception:
                    target = None
                if target is None:
                    try:
                        target = doc.documentElement
                    except Exception:
                        target = None
                if target is not None:
                    self._observer.observe(target, {"childList": True, "subtree": True, "attributes": True, "attributeFilter": ["id", "class", "title", "aria-label"]})
            except Exception:
                self._observer = None

    def sweep(self):
        return hide_scs_fullscreen_buttons(self.doc, self.exclude_root)

    def _on_mutations(self, mutations, observer):
        self.sweep()

    def destroy(self):
        if self._observer is not None:
            try:
                self._observer.disconnect()
            except Exception:
                pass
            self._observer = None
        return self


class AppFrame(Widget):
    """Single iframe that hosts one loaded app at a time.

    The iframe is same origin SCS content, so load is a real DOM event.
    No polling, no timeout. Fullscreen acts on the wrapper, not on the
    shell, so the loaded app fills the screen by itself.
    """

    def __init__(self, container=None):
        wrapper = html.DIV(Class="widgets-app-frame")
        Widget.__init__(self, wrapper)
        self.iframe = html.IFRAME()
        self.iframe.attrs["title"] = "Loaded SCS app"
        self.iframe.attrs["allow"] = "fullscreen; autoplay; gamepad; xr-spatial-tracking; clipboard-write"
        self.iframe.attrs["allowfullscreen"] = ""
        self.loading = html.DIV("Loading app...", Class="widgets-app-loading")
        self.element <= self.iframe
        self.element <= self.loading
        if container is not None:
            container <= self.element
        self._current_app_id = None
        self._current_url = None
        self._child_suppressor = None
        self.iframe.bind("load", self._on_load)

    @property
    def fullscreen_target(self):
        return self.element

    @property
    def current_app_id(self):
        return self._current_app_id

    @property
    def current_url(self):
        return self._current_url

    def load(self, url, app_id, title=""):
        if not url:
            raise ValueError("AppFrame.load needs a non empty url")
        if not app_id:
            raise ValueError("AppFrame.load needs a non empty app_id")
        self._current_app_id = app_id
        self._current_url = url
        if title:
            self.iframe.attrs["title"] = title
        self.loading.classList.remove("is-hidden")
        self.loading.text = "Loading " + app_id + "..."
        self.emit("loading", app_id, url)
        self.iframe.attrs["src"] = url
        return self

    def reload(self):
        if self._current_url is None:
            raise ValueError("AppFrame.reload has no loaded app to reload")
        self.load(self._current_url, self._current_app_id)
        return self

    def clear(self):
        if self._child_suppressor is not None:
            self._child_suppressor.destroy()
            self._child_suppressor = None
        self._current_app_id = None
        self._current_url = None
        if "src" in self.iframe.attrs:
            del self.iframe.attrs["src"]
        self.loading.classList.remove("is-hidden")
        self.loading.text = "No app loaded"
        self.emit("cleared")
        return self

    def suppress_child_fullscreen(self):
        """Hide the child SCS runtime button inside the iframe.

        Same origin only. If the iframe document cannot be read, emit
        child-fullscreen-suppression-unavailable and leave the child alone,
        never crash home.
        """
        if self._child_suppressor is not None:
            self._child_suppressor.destroy()
            self._child_suppressor = None
        try:
            child_doc = self.iframe.contentDocument
            if child_doc is None:
                try:
                    child_doc = self.iframe.contentWindow.document
                except Exception:
                    child_doc = None
        except Exception:
            child_doc = None
        if child_doc is None:
            self.emit("child-fullscreen-suppression-unavailable", self._current_app_id)
            return self
        try:
            self._child_suppressor = ScsFullscreenSuppressor(child_doc, exclude_root=None)
        except Exception:
            self.emit("child-fullscreen-suppression-unavailable", self._current_app_id)
        return self

    def _on_load(self, event):
        self.loading.classList.add("is-hidden")
        self.suppress_child_fullscreen()
        self.emit("loaded", self._current_app_id, self._current_url)


class FullscreenController(EventEmitter):
    """Fullscreen for a target resolved at click time.

    target_resolver is a callable returning the element to fullscreen,
    or an element itself. Resolving at click time is what makes the
    button act on the currently loaded app after a menu switch.
    """

    def __init__(self, target_resolver, button=None):
        EventEmitter.__init__(self)
        if callable(target_resolver):
            self._resolver = target_resolver
        else:
            self._resolver = lambda: target_resolver
        self.button = button
        if button is not None:
            button.on("click", self._on_button_click)
        _DOCUMENT.bind("fullscreenchange", self._on_fullscreen_change)

    def resolve_target(self):
        target = self._resolver()
        if target is None:
            raise ValueError("Fullscreen has no target element")
        return target

    def is_supported(self):
        target = self.resolve_target()
        return hasattr(target, "requestFullscreen") and _DOCUMENT.fullscreenEnabled is not False

    def is_fullscreen(self):
        return _DOCUMENT.fullscreenElement is not None

    def request(self):
        if not self.is_supported():
            raise RuntimeError("Fullscreen API is not supported for this target")
        target = self.resolve_target()
        target.requestFullscreen()
        return self

    def exit(self):
        if self.is_fullscreen():
            _DOCUMENT.exitFullscreen()
        return self

    def toggle(self):
        if self.is_fullscreen():
            self.exit()
        else:
            self.request()
        return self

    def _on_button_click(self, event):
        event.stopPropagation()
        self.toggle()

    def _on_fullscreen_change(self, event):
        active = self.is_fullscreen()
        if self.button is not None:
            self.button.set_active(active)
        self.emit("change", active)

    def destroy(self):
        _DOCUMENT.unbind("fullscreenchange", self._on_fullscreen_change)
        return self


# ---------------------------------------------------------------------------
# Dialogs, in the spirit of brython-widgets dialog
# ---------------------------------------------------------------------------

class Dialog(Widget):
    """Movable dialog. Drag is mousedown plus document mousemove and mouseup.

    There is no remove_after timer. Callers close on an explicit event:
    a button click, Escape, or their own event handler.
    """

    def __init__(self, title="", top=None, left=None, ok_cancel=False):
        overlay = html.DIV(Class="widgets-dialog-overlay")
        element = html.DIV(Class="widgets-dialog")
        Widget.__init__(self, element)
        self.overlay = overlay
        self._title_bar = html.DIV(Class="widgets-dialog-title")
        self._title_bar <= html.SPAN(title)
        close_button = html.SPAN("\u00d7", Class="widgets-dialog-close")
        self._title_bar <= close_button
        self.element <= self._title_bar
        self.panel = html.DIV(Class="widgets-dialog-panel")
        self.element <= self.panel
        self.ok_button = None
        self.cancel_button = None
        if ok_cancel:
            actions = html.DIV(Class="widgets-dialog-actions")
            self.ok_button = html.BUTTON("Ok", Class="widgets-button")
            self.cancel_button = html.BUTTON("Cancel", Class="widgets-button")
            actions <= self.ok_button
            actions <= self.cancel_button
            self.element <= actions
            self.cancel_button.bind("click", self._on_cancel_click)
        close_button.bind("click", self._on_close_click)
        self._title_bar.bind("mousedown", self._on_mousedown)
        _DOCUMENT.bind("keydown", self._on_keydown)
        _DOCUMENT <= self.overlay
        _DOCUMENT <= self.element
        if left is None:
            left = int((_WINDOW.innerWidth - 360) / 2)
        if top is None:
            top = int((_WINDOW.innerHeight - 200) / 2)
        self.left = left
        self.top = top
        self.element.style.left = str(left) + "px"
        self.element.style.top = str(top) + "px"
        self._is_moving = False
        self._offset = [0, 0]

    def close(self):
        _DOCUMENT.unbind("keydown", self._on_keydown)
        _DOCUMENT.unbind("mousemove", self._on_mousemove)
        _DOCUMENT.unbind("mouseup", self._on_mouseup)
        self.overlay.remove()
        self.element.remove()
        self.emit("close")
        return self

    def _on_close_click(self, event):
        self.close()

    def _on_cancel_click(self, event):
        self.emit("cancel")
        self.close()

    def _on_keydown(self, event):
        if event.key == "Escape":
            self.close()

    def _on_mousedown(self, event):
        self._is_moving = True
        self._offset = [self.left - event.x, self.top - event.y]
        event.preventDefault()
        _DOCUMENT.bind("mousemove", self._on_mousemove)
        _DOCUMENT.bind("mouseup", self._on_mouseup)

    def _on_mousemove(self, event):
        if not self._is_moving:
            return
        self.left = self._offset[0] + event.x
        self.top = self._offset[1] + event.y
        self.element.style.left = str(self.left) + "px"
        self.element.style.top = str(self.top) + "px"

    def _on_mouseup(self, event):
        self._is_moving = False
        _DOCUMENT.unbind("mousemove", self._on_mousemove)
        _DOCUMENT.unbind("mouseup", self._on_mouseup)


class InfoDialog(Dialog):
    def __init__(self, title="", message="", top=None, left=None):
        Dialog.__init__(self, title, top, left, ok_cancel=False)
        self.panel <= message


class EntryDialog(Dialog):
    """Input dialog. On Ok or Enter it dispatches an "entry" event."""

    def __init__(self, title="", message="", top=None, left=None):
        Dialog.__init__(self, title, top, left, ok_cancel=True)
        if message:
            self.panel <= message
        self.entry = html.INPUT()
        self.panel <= html.BR()
        self.panel <= self.entry
        self.entry.focus()
        self.entry.bind("keypress", self._on_keypress)
        self.ok_button.bind("click", self._on_ok_click)

    @property
    def value(self):
        return self.entry.value

    def _on_keypress(self, event):
        if event.keyCode == 13:
            self._dispatch_entry()

    def _on_ok_click(self, event):
        self._dispatch_entry()

    def _dispatch_entry(self):
        self.dispatchEvent(_WINDOW.CustomEvent.new("entry"))
        self.emit("entry", self.value)


class ConfirmDialog(Dialog):
    def __init__(self, title="", message="", top=None, left=None):
        Dialog.__init__(self, title, top, left, ok_cancel=True)
        if message:
            self.panel <= message
        self.ok_button.bind("click", self._on_ok_click)

    def _on_ok_click(self, event):
        self.emit("confirm")
        self.close()


# ---------------------------------------------------------------------------
# Small generic form widgets, all event driven
# ---------------------------------------------------------------------------

class Select(Widget):
    def __init__(self, label="", options=None, on_change=None):
        wrapper = html.DIV(Class="widgets-field")
        Widget.__init__(self, wrapper)
        if label:
            self.element <= html.LABEL(label)
        self.select = html.SELECT()
        self.element <= self.select
        if on_change is not None:
            self.on("change", on_change)
        self.select.bind("change", self._on_change)
        if options:
            self.set_options(options)

    def set_options(self, options):
        self.select.clear()
        for option in options:
            if isinstance(option, dict):
                self.select <= html.OPTION(option.get("label", option["value"]),
                                           value=option["value"])
            else:
                self.select <= html.OPTION(str(option), value=str(option))
        return self

    @property
    def value(self):
        return self.select.value

    def _on_change(self, event):
        self.emit("change", self.value, event)


class Slider(Widget):
    def __init__(self, label="", minimum=0, maximum=100, value=0, step=1, on_change=None):
        wrapper = html.DIV(Class="widgets-field")
        Widget.__init__(self, wrapper)
        if label:
            self.element <= html.LABEL(label)
        self.input = html.INPUT(Type="range")
        self.input.attrs["min"] = str(minimum)
        self.input.attrs["max"] = str(maximum)
        self.input.attrs["step"] = str(step)
        self.input.attrs["value"] = str(value)
        self.element <= self.input
        if on_change is not None:
            self.on("change", on_change)
        self.input.bind("input", self._on_input)
        self.input.bind("change", self._on_change)

    @property
    def value(self):
        return float(self.input.value)

    def _on_input(self, event):
        self.emit("input", self.value, event)

    def _on_change(self, event):
        self.emit("change", self.value, event)


class Toggle(Widget):
    def __init__(self, label="", checked=False, on_change=None):
        wrapper = html.LABEL(Class="widgets-field")
        Widget.__init__(self, wrapper)
        self.input = html.INPUT(Type="checkbox")
        self.input.checked = bool(checked)
        self.element <= self.input
        self.element <= html.SPAN(label)
        if on_change is not None:
            self.on("change", on_change)
        self.input.bind("change", self._on_change)

    @property
    def checked(self):
        return bool(self.input.checked)

    def _on_change(self, event):
        self.emit("change", self.checked, event)


class TextInput(Widget):
    def __init__(self, label="", value="", placeholder="", on_input=None, on_enter=None):
        wrapper = html.DIV(Class="widgets-field")
        Widget.__init__(self, wrapper)
        if label:
            self.element <= html.LABEL(label)
        self.input = html.INPUT(value=value)
        if placeholder:
            self.input.attrs["placeholder"] = placeholder
        self.element <= self.input
        if on_input is not None:
            self.on("input", on_input)
        if on_enter is not None:
            self.on("enter", on_enter)
        self.input.bind("input", self._on_input)
        self.input.bind("keydown", self._on_keydown)

    @property
    def value(self):
        return self.input.value

    def _on_input(self, event):
        self.emit("input", self.value, event)

    def _on_keydown(self, event):
        if event.key == "Enter":
            self.emit("enter", self.value, event)


class StatusBar(Widget):
    def __init__(self, text=""):
        element = html.DIV(text, Class="widgets-statusbar")
        Widget.__init__(self, element)

    def set_text(self, text, is_error=False):
        self.element.text = text
        if is_error:
            self.element.classList.add("is-error")
        else:
            self.element.classList.remove("is-error")
        return self


class Panel(Widget):
    def __init__(self, children=None):
        element = html.DIV(Class="widgets-panel")
        Widget.__init__(self, element)
        if children:
            for child in children:
                if isinstance(child, Widget):
                    self.element <= child.element
                else:
                    self.element <= child
