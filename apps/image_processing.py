from scs import *
from browser import document, window, aio
from extensions.file_loader import load_image
from extensions.pyodide import ndimage


WIDTH = 1050
HEIGHT = 300
MAX_IMAGE_DIMENSION = 384
BG = rgb(15, 20, 23)
INK = rgb(229, 238, 232)
MUTED = rgb(137, 157, 151)
MINT = rgb(102, 224, 177)
CYAN = rgb(95, 194, 226)
AMBER = rgb(244, 190, 92)
RED = rgb(244, 111, 104)
PANEL_ID = 'image-processing-controls'
OPERATIONS = {
    'gaussian': 'Gaussian blur',
    'sobel': 'Sobel edge magnitude',
    'opening': 'Binary opening'
}


def _set_status(app, message, error=None):
    app.status = message
    app.error = error
    status = document.getElementById('image-processing-status')
    if status:
        status.textContent = message if error is None else message + ': ' + str(error)
        status.style.color = '#f46f68' if error else '#899d97'


def _install_controls(app):
    existing = document.getElementById(PANEL_ID)
    if existing:
        existing.parentNode.removeChild(existing)

    panel = document.createElement('section')
    panel.id = PANEL_ID
    panel.style.cssText = (
        'box-sizing:border-box;width:1050px;max-width:95vw;padding:20px 24px 18px;'
        'margin:0 0 12px;background:#191f22;border:1px solid #34413e;color:#e5eee8;'
        'font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;'
    )
    panel.innerHTML = '''
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:14px">
        <strong style="font-size:18px;color:#66e0b1">IMAGE PROCESSING / SCIPY.NDIMAGE</strong>
        <span style="color:#899d97">384 px working limit · Pyodide worker</span>
      </div>
    <div id="image-process-controls" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr));gap:12px;align-items:end">
        <label style="display:grid;gap:6px;color:#b6c6bf">Image file
          <input id="image-file" type="file" accept="image/*" style="box-sizing:border-box;width:100%;color:#b6c6bf;font:12px ui-monospace,SFMono-Regular,Consolas,monospace">
        </label>
        <label style="display:grid;gap:6px;color:#b6c6bf">Image URL
          <input id="image-url" type="url" placeholder="https://..." style="box-sizing:border-box;width:100%;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace,SFMono-Regular,Consolas,monospace">
        </label>
        <button id="load-image-url" type="button" style="height:39px;padding:0 14px;border:1px solid #43524d;background:#202a2d;color:#e5eee8;font-weight:bold;font-family:inherit;cursor:pointer">Load URL</button>
        <label style="display:grid;gap:6px;color:#b6c6bf">Manipulation
          <select id="image-operation" style="box-sizing:border-box;width:100%;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace,SFMono-Regular,Consolas,monospace">
            <option value="gaussian">Gaussian blur · ndimage.gaussian_filter</option>
            <option value="sobel">Sobel edges · ndimage.sobel</option>
            <option value="opening">Morphology · ndimage.binary_opening</option>
          </select>
        </label>
                <button id="run-image-operation" type="button" style="height:39px;padding:0 18px;border:0;background:#66e0b1;color:#10201a;font-weight:bold;font-family:inherit;cursor:pointer">Process image</button>
            </div>
      <div id="image-processing-status" role="status" style="margin-top:10px;color:#899d97">Loading scs.jpg...</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:14px;margin-top:14px">
        <div>
          <div style="margin-bottom:6px;color:#5fc2e2">SOURCE <span id="source-image-size" style="color:#899d97"></span></div>
          <img id="source-image-preview" alt="Source image" style="display:block;width:100%;height:230px;object-fit:contain;background:#0f1417;border:1px solid #34413e">
        </div>
        <div>
          <div style="margin-bottom:6px;color:#f4be5c">PROCESSED <span id="processed-image-measure" style="color:#899d97"></span></div>
                    <div id="processed-image-empty" style="box-sizing:border-box;display:grid;place-items:center;width:100%;height:230px;background:#0f1417;border:1px solid #34413e;color:#899d97">Processing image...</div>
                    <img id="processed-image-preview" alt="Processed image" style="display:none;width:100%;height:230px;object-fit:contain;background:#0f1417;border:1px solid #34413e">
        </div>
      </div>
      <div style="margin-top:9px;color:#899d97;font-size:11px">Remote image hosts must allow CORS pixel access.</div>
    '''
    container = document.getElementById('canvas-container')
    container.parentNode.insertBefore(panel, container)

    def choose_file(event):
        files = document['image-file'].files
        if files.length:
            aio.run(_load_image(app, files[0]))

    def load_url(event):
        event.preventDefault()
        aio.run(_load_image(app, document['image-url'].value))

    def process_image(event):
        operation = document['image-operation'].value
        aio.run(_process_image(app, operation))

    document['image-file'].bind('change', choose_file)
    document['load-image-url'].bind('click', load_url)
    document['run-image-operation'].bind('click', process_image)


async def _load_image(app, source):
    app.loading = True
    _set_status(app, 'Loading image...')
    loaded = False
    try:
        image = await load_image(source, MAX_IMAGE_DIMENSION)
        app.pixels = image['pixels']
        app.imageWidth = image['width']
        app.imageHeight = image['height']
        app.originalWidth = image['originalWidth']
        app.originalHeight = image['originalHeight']
        app.imageName = str(getattr(source, 'name', source))
        app.operationResult = None
        document['source-image-preview'].src = image['previewUrl']
        document['processed-image-preview'].removeAttribute('src')
        document['processed-image-preview'].style.display = 'none'
        document['processed-image-empty'].style.display = 'grid'
        document['processed-image-empty'].textContent = 'Processing selected operation...'
        document['source-image-size'].textContent = (
            '{} x {} (from {} x {})'.format(
                app.imageWidth, app.imageHeight, app.originalWidth, app.originalHeight
            )
        )
        document['processed-image-measure'].textContent = ''
        _set_status(app, 'Image loaded: ' + app.imageName)
        loaded = True
    except Exception as error:
        _set_status(app, 'Image load failed', error)
    finally:
        app.loading = False
    if loaded:
        await _process_image(app, app.operation)


async def _process_image(app, operation):
    if not hasattr(app, 'pixels'):
        _set_status(app, 'Load an image first', 'No image is available')
        return
    app.busy = True
    _set_status(app, 'Starting Pyodide and processing image...')
    document['run-image-operation'].disabled = True
    try:
        result = await ndimage(
            app.pixels, app.imageWidth, app.imageHeight, operation
        )
        canvas = document.createElement('canvas')
        canvas.width = result['width']
        canvas.height = result['height']
        context = canvas.getContext('2d')
        output = context.createImageData(result['width'], result['height'])
        output.data.set(result['pixels'])
        context.putImageData(output, 0, 0)
        document['processed-image-preview'].src = canvas.toDataURL('image/png')
        document['processed-image-preview'].style.display = 'block'
        document['processed-image-empty'].style.display = 'none'
        app.operation = operation
        app.operationResult = result
        _set_status(app, OPERATIONS[operation] + ' complete')
        if operation == 'gaussian':
            measurement = 'sigma = {:.1f} px'.format(result['measurement'])
        elif operation == 'sobel':
            measurement = '{:.1f}% edge pixels'.format(result['measurement'])
        else:
            measurement = '{:.1f}% foreground area'.format(result['measurement'])
        document['processed-image-measure'].textContent = measurement
    except Exception as error:
        document['processed-image-empty'].style.display = 'grid'
        document['processed-image-empty'].textContent = 'Processing failed'
        _set_status(app, 'Processing failed', error)
    finally:
        app.busy = False
        document['run-image-operation'].disabled = False


def onAppStart(app):
    app.width = WIDTH
    app.height = HEIGHT
    app.stepsPerSecond = 15
    app.status = 'Loading scs.jpg...'
    app.busy = False
    app.loading = False
    app.error = None
    app.operation = 'gaussian'
    app.operationResult = None
    _install_controls(app)
    aio.run(_load_image(app, 'scs.jpg'))


def redrawAll(app):
    drawRect(0, 0, app.width, app.height, fill=BG)
    drawLabel('SCIPY.NDIMAGE', 54, 44, size=20, fill=INK, bold=True, align='left')
    drawLabel('MULTIDIMENSIONAL FILTERING  /  CONVOLUTION  /  MORPHOLOGY',
              54, 72, size=11, fill=MINT, align='left')
    drawLine(54, 99, 996, 99, fill=rgb(55, 69, 64), lineWidth=1)
    status_color = RED if app.error else AMBER if app.busy or app.loading else MINT
    drawLabel(app.status, 54, 129, size=14, fill=status_color, align='left')
    if app.error:
        drawLabel(app.error[:130], 54, 157, size=11, fill=RED, align='left')
    if app.operationResult:
        drawLabel('Operation: ' + OPERATIONS[app.operation], 54, 202,
                  size=13, fill=INK, align='left')
        drawLabel('RGBA array: {} x {} x 4'.format(app.imageHeight, app.imageWidth),
                  54, 232, size=12, fill=MUTED, align='left')
        drawLabel('Measured value: {:.3f}'.format(app.operationResult['measurement']),
                  430, 232, size=12, fill=AMBER, align='left')
    drawLabel('Source: ' + getattr(app, 'imageName', 'scs.jpg'), 54, 272,
              size=11, fill=MUTED, align='left')
