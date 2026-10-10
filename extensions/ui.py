"""Small DOM-backed controls for SCS canvas applications."""

from browser import document, window


class TextArea:
    """A positioned textarea that can overlay a canvas input panel."""
    def __init__(self, parent, element_id, value='', placeholder='', aria_label=None):
        existing = document.getElementById(element_id)
        if existing:
            existing.parentNode.removeChild(existing)

        self.element = document.createElement('textarea')
        self.element.id = element_id
        self.element.value = value
        self.element.placeholder = placeholder
        self.element.setAttribute('aria-label', aria_label or placeholder or element_id)
        self.element.spellcheck = False
        self.element.style.cssText = (
            'position:absolute;z-index:2;box-sizing:border-box;display:block;'
            'padding:10px;resize:none;overflow:auto;'
            'background:rgba(17,20,27,0.97);color:#e6e6ee;'
            'border:1px solid #626c80;border-radius:4px;'
            'font:12px/1.45 ui-monospace,monospace;'
        )
        parent.appendChild(self.element)

    @property
    def value(self):
        return str(self.element.value)

    @value.setter
    def value(self, text):
        self.element.value = text

    @property
    def placeholder(self):
        return str(self.element.placeholder)

    @placeholder.setter
    def placeholder(self, text):
        self.element.placeholder = text

    def set_bounds(self, left, top, width, height):
        self.element.style.left = f'{left}px'
        self.element.style.top = f'{top}px'
        self.element.style.width = f'{width}px'
        self.element.style.height = f'{height}px'

    def bind(self, event_name, callback):
        self.element.bind(event_name, callback)


class Button:
    """A positioned HTML button for canvas-based app actions."""
    def __init__(self, parent, element_id, text, color='#2c82f2', aria_label=None):
        existing = document.getElementById(element_id)
        if existing:
            existing.parentNode.removeChild(existing)

        self.element = document.createElement('button')
        self.element.id = element_id
        self.element.type = 'button'
        self.element.textContent = text
        self.element.setAttribute('aria-label', aria_label or text)
        self.element.style.cssText = (
            'position:absolute;z-index:3;box-sizing:border-box;'
            'border:1px solid #ffffff;border-radius:6px;'
            'color:#ffffff;font: bold 12px ui-monospace,monospace;'
            'cursor:pointer;padding:0 10px;'
        )
        self.color = color
        parent.appendChild(self.element)

    @property
    def text(self):
        return str(self.element.textContent)

    @text.setter
    def text(self, value):
        self.element.textContent = value

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = value
        self.element.style.backgroundColor = value

    def set_bounds(self, left, top, width, height):
        self.element.style.left = f'{left}px'
        self.element.style.top = f'{top}px'
        self.element.style.width = f'{width}px'
        self.element.style.height = f'{height}px'

    def bind(self, event_name, callback):
        self.element.bind(event_name, callback)


class ImageInput:
    """Image preview with URL source, file browse, and drag/drop support."""
    def __init__(self, parent, element_id, on_change=None):
        existing = document.getElementById(element_id)
        if existing:
            existing.parentNode.removeChild(existing)

        self.on_change = on_change
        self._object_url = ''
        self.element = document.createElement('div')
        self.element.id = element_id
        self.element.setAttribute('aria-label', 'Image preview and file drop area')
        self.element.style.cssText = (
            'position:absolute;z-index:2;box-sizing:border-box;overflow:hidden;'
            'border:1px solid #626c80;border-radius:4px;background:#0f1115;'
        )

        self.preview = document.createElement('img')
        self.preview.alt = 'Selected image preview'
        self.preview.style.cssText = (
            'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;'
            'display:none;background:#0f1115;'
        )
        self.preview.bind('error', self._preview_error)

        self.hint = document.createElement('div')
        self.hint.textContent = 'Drop an image here or browse files'
        self.hint.style.cssText = (
            'position:absolute;inset:0;display:grid;place-items:center;'
            'padding:12px;color:#8994a8;text-align:center;'
            'font:12px ui-monospace,monospace;pointer-events:none;'
        )

        self.browse = document.createElement('button')
        self.browse.type = 'button'
        self.browse.textContent = 'Browse image'
        self.browse.setAttribute('aria-label', 'Browse for an image file')
        self.browse.style.cssText = (
            'position:absolute;right:8px;bottom:8px;z-index:2;'
            'height:30px;padding:0 10px;border:1px solid #ffffff;border-radius:4px;'
            'background:#2c82f2;color:#ffffff;font:12px ui-monospace,monospace;cursor:pointer;'
        )

        self.file_input = document.createElement('input')
        self.file_input.type = 'file'
        self.file_input.accept = 'image/*'
        self.file_input.style.display = 'none'

        self.element.appendChild(self.preview)
        self.element.appendChild(self.hint)
        self.element.appendChild(self.browse)
        self.element.appendChild(self.file_input)
        parent.appendChild(self.element)

        self.browse.bind('click', lambda event: self.file_input.click())
        self.file_input.bind('change', self._on_file_change)
        self.element.bind('dragover', self._on_drag_over)
        self.element.bind('dragleave', self._on_drag_leave)
        self.element.bind('drop', self._on_drop)

    def set_bounds(self, left, top, width, height):
        self.element.style.left = f'{left}px'
        self.element.style.top = f'{top}px'
        self.element.style.width = f'{width}px'
        self.element.style.height = f'{height}px'

    def show(self):
        self.element.style.display = 'block'

    def hide(self):
        self.element.style.display = 'none'

    def set_source(self, source):
        source = str(source or '')
        if self._object_url and self._object_url != source:
            try:
                window.URL.revokeObjectURL(self._object_url)
            except Exception:
                pass
            self._object_url = ''
        if source:
            self.preview.src = source
            self.preview.style.display = 'block'
            self.hint.style.display = 'none'
        else:
            self.preview.removeAttribute('src')
            self.preview.style.display = 'none'
            self.hint.textContent = 'Drop an image here or browse files'
            self.hint.style.display = 'grid'

    def _preview_error(self, event):
        self.preview.style.display = 'none'
        self.hint.textContent = 'Image preview failed. Check the URL or choose a file.'
        self.hint.style.display = 'grid'

    def _on_drag_over(self, event):
        event.preventDefault()
        self.element.style.borderColor = '#2c82f2'

    def _on_drag_leave(self, event):
        self.element.style.borderColor = '#626c80'

    def _on_drop(self, event):
        event.preventDefault()
        self.element.style.borderColor = '#626c80'
        files = event.dataTransfer.files
        if files.length:
            self._load_file(files[0])

    def _on_file_change(self, event):
        files = self.file_input.files
        if files.length:
            self._load_file(files[0])

    def _load_file(self, file):
        try:
            source = str(window.URL.createObjectURL(file))
        except Exception as error:
            self.hint.textContent = f'Could not open image: {error}'
            self.hint.style.display = 'grid'
            return
        self.set_source(source)
        self._object_url = source
        if self.on_change:
            self.on_change(source, str(file.name))
