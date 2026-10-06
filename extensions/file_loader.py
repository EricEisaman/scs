"""Browser image loading for SCS extensions and apps.

This Model-only utility accepts a URL/path or browser File, downsamples it,
and returns RGBA pixels plus a same-origin preview data URL. It has no SCS,
canvas-rendering, or Pyodide dependency.
"""

from browser import document, window


class FileLoaderError(Exception):
    """Raised when a browser image cannot be loaded or read safely."""


async def load_image(source, max_dimension=384):
    """Load an image into a bounded RGBA pixel buffer.

    ``source`` may be a URL/path string or a browser File object. Remote images
    must permit CORS access for pixel extraction.
    """
    max_dimension = int(max_dimension)
    if max_dimension < 1 or max_dimension > 1024:
        raise ValueError('max_dimension must be between 1 and 1024')

    should_revoke_url = False
    if isinstance(source, str):
        image_source = source.strip()
        if not image_source:
            raise ValueError('Image URL cannot be empty')
    elif getattr(source, 'type', '').startswith('image/'):
        image_source = str(window.URL.createObjectURL(source))
        should_revoke_url = True
    else:
        raise ValueError('Choose an image URL or an image file')

    image = window.Image.new()
    if image_source.startswith('http://') or image_source.startswith('https://'):
        image.crossOrigin = 'anonymous'

    def executor(resolve, reject):
        image.onload = lambda event: resolve(image)
        image.onerror = lambda event: reject(FileLoaderError(
            'Image could not be loaded. Remote images must allow CORS.'
        ))
        image.src = image_source

    try:
        await window.Promise.new(executor)
        original_width = int(getattr(image, 'naturalWidth', 0) or image.width)
        original_height = int(getattr(image, 'naturalHeight', 0) or image.height)
        if original_width < 1 or original_height < 1:
            raise FileLoaderError('Loaded image has invalid dimensions')

        scale = min(1.0, max_dimension / max(original_width, original_height))
        width = max(1, int(round(original_width * scale)))
        height = max(1, int(round(original_height * scale)))
        canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        context = canvas.getContext('2d')
        context.drawImage(image, 0, 0, width, height)
        image_data = context.getImageData(0, 0, width, height)
        preview_url = canvas.toDataURL('image/png')
        return {
            'pixels': image_data.data,
            'width': width,
            'height': height,
            'originalWidth': original_width,
            'originalHeight': original_height,
            'previewUrl': preview_url
        }
    except FileLoaderError:
        raise
    except Exception as error:
        raise FileLoaderError(
            'Unable to read image pixels. Check the image format and CORS permissions: ' + str(error)
        )
    finally:
        if should_revoke_url:
            window.URL.revokeObjectURL(image_source)


__all__ = ['load_image', 'FileLoaderError']
