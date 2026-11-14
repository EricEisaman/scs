"""
scs_wasm.py - Bulk-data ABI for WASM producers (Integration 2).

Contract: WASM and JS share TYPED-ARRAY RANGES with documented
layouts. Batch operations, never one JS object / call per entity.

  * Layouts are explicit: element type, alignment, stride, offsets,
    count. One layout, shared by producer and consumer.
  * Ownership is explicit: who allocated, who may grow, who frees.
  * Upload semantics are explicit: copy-now vs retain-until-upload.
  * A WASM producer hands over a VIEW of its linear memory -- JS
    never converts it into an object graph first.
  * Views are REFRESHED after memory growth: growing non-shared
    WASM memory detaches the previous buffer; shared memory behaves
    differently (its buffer is not detached, but the view length
    still needs re-checking).

What this is NOT: "zero-copy GPU access". A CPU-memory view and a
GPU upload are SEPARATE decisions. A view avoids a CPU copy; the
GPU upload still copies (or retains) by its own contract. This
module never advertises the first as the second.
"""

import math
import struct


ELEMENT_SIZES = {
    'float32': 4, 'float64': 8,
    'int32': 4, 'uint32': 4, 'int16': 2, 'uint16': 2,
    'int8': 1, 'uint8': 1, 'uint8clamped': 1,
}

# JS typed-array constructors, by element type (Brython: window.XxxArray).
_TYPED_CTORS = {
    'float32': 'Float32Array', 'float64': 'Float64Array',
    'int32': 'Int32Array', 'uint32': 'Uint32Array',
    'int16': 'Int16Array', 'uint16': 'Uint16Array',
    'int8': 'Int8Array', 'uint8': 'Uint8Array',
}


class ArrayLayout:
    """One authoritative layout for a bulk buffer.

    Example -- transforms, one per entity:
        ArrayLayout('transform', 'float32', count=N,
                    fields={'x': 0, 'y': 1, 'rotation': 2, 'scale': 3})
        stride = 4 floats (16 bytes), offsets are in ELEMENTS.
    """

    def __init__(self, name, element_type, count, fields, alignment=None):
        if element_type not in ELEMENT_SIZES:
            raise ValueError('Unknown element type %r' % element_type)
        self.name = name
        self.element_type = element_type
        self.element_size = ELEMENT_SIZES[element_type]
        self.count = int(count)
        self.fields = dict(fields)  # field -> element offset within record
        self.stride_elements = (max(fields.values()) + 1) if fields else 0
        self.alignment = alignment or self.element_size
        if (self.stride_elements * self.element_size) % self.alignment != 0:
            raise ValueError(
                'Layout %s: stride %d bytes is not %d-byte aligned'
                % (name, self.stride_elements * self.element_size, self.alignment))

    @property
    def stride_bytes(self):
        return self.stride_elements * self.element_size

    @property
    def total_bytes(self):
        return self.stride_bytes * self.count

    def byte_offset(self, index, field):
        return (index * self.stride_elements + self.fields[field]) * self.element_size

    def describe(self):
        return {
            'name': self.name, 'element_type': self.element_type,
            'element_size': self.element_size, 'count': self.count,
            'fields': dict(self.fields), 'stride_elements': self.stride_elements,
            'stride_bytes': self.stride_bytes, 'alignment': self.alignment,
        }


# Canonical SCS layouts (shared by every WASM producer).
TRANSFORM_LAYOUT = lambda count: ArrayLayout(
    'transform', 'float32', count,
    {'x': 0, 'y': 1, 'rotation': 2, 'scale': 3})
POSITION_LAYOUT = lambda count: ArrayLayout(
    'position', 'float32', count, {'x': 0, 'y': 1})
VERTEX_LAYOUT_WASM = lambda count: ArrayLayout(
    'vertex', 'float32', count, {'x': 0, 'y': 1, 'u': 2, 'v': 3})


class WasmMemoryView:
    """A view over a WASM linear-memory buffer, with ownership +
    growth handling.

    owner: 'wasm' (WASM allocated, WASM frees), 'js' (JS allocated),
           'shared' (SharedArrayBuffer -- growth does not detach).
    copy_on_upload: True  -> upload copies immediately, view may be
                    reused / freed after the call returns.
                    False -> upload retains the view until later;
                    caller must not mutate / free until upload done.
    """

    def __init__(self, buffer, layout, owner='wasm', copy_on_upload=True):
        self.buffer = buffer  # ArrayBuffer / SharedArrayBuffer
        self.layout = layout
        self.owner = owner
        self.copy_on_upload = copy_on_upload
        self._view = None
        self._buffer_id = id(buffer)
        self.refresh()

    def refresh(self):
        """Re-create the typed-array view after memory growth.
        Growing non-shared memory DETACHES the old buffer: the old
        view throws on access. Call this after any grow, before use."""
        try:
            from browser import window
            ctor = getattr(window, _TYPED_CTORS[self.layout.element_type])
            # Length in elements = total bytes / element size.
            self._view = ctor.new(
                self.buffer, 0, self.layout.total_bytes // self.layout.element_size)
        except Exception:
            # CPython tests: fall back to a real float32 array, not a
            # bytearray (which cannot hold float elements).
            import array as _array
            _code = {'float32': 'f', 'float64': 'd', 'int32': 'i',
                     'uint32': 'I', 'int16': 'h', 'uint16': 'H',
                     'int8': 'b', 'uint8': 'B'}.get(self.layout.element_type, 'f')
            n = self.layout.total_bytes // self.layout.element_size
            self._view = _array.array(_code, [0]) * n
        self._buffer_id = id(self.buffer)
        return self._view

    def is_detached(self, current_buffer):
        """True if the buffer object changed (growth detached it)."""
        return current_buffer is not self.buffer

    def check_fresh(self, current_buffer):
        if self.is_detached(current_buffer):
            self.buffer = current_buffer
            self.refresh()
            return False  # was stale, now refreshed
        return True

    @property
    def view(self):
        return self._view

    def read_record(self, index):
        """Read one record as a dict -- for debugging / tests only.
        Hot paths use the raw view, never per-record dicts."""
        base = index * self.layout.stride_elements
        return {f: float(self._view[base + off])
                for f, off in self.layout.fields.items()}

    def write_record(self, index, values):
        base = index * self.layout.stride_elements
        for f, v in values.items():
            if f in self.layout.fields:
                self._view[base + self.layout.fields[f]] = float(v)

    def write_batch(self, records):
        """Batch: 'update these transforms' in ONE call. records is a
        list of dicts, or a flat list of floats in layout order.
        This is the operation WASM producers should expose -- not
        one call per entity."""
        if records and isinstance(records[0], dict):
            for i, rec in enumerate(records):
                if i >= self.layout.count:
                    break
                self.write_record(i, rec)
        else:
            n = min(len(records), self.layout.count * self.layout.stride_elements)
            for i in range(n):
                self._view[i] = float(records[i])
        return len(records)


def update_transforms(memory_view, transforms):
    """Batch transform update: the canonical WASM -> SCS operation.
    `transforms` is a flat float list or list of dicts; the view is
    written in place, no object graph is built."""
    return memory_view.write_batch(transforms)


def upload_view(memory_view, upload_fn, copy=None):
    """GPU upload with explicit copy/retain semantics.
    copy=True (default from the view): upload_fn receives a copy,
    safe to free the view after return.
    copy=False: upload_fn receives the live view and must retain it
    until the GPU has consumed it; caller must not mutate/free."""
    do_copy = memory_view.copy_on_upload if copy is None else copy
    if do_copy:
        try:
            snapshot = list(memory_view.view)
        except Exception:
            snapshot = memory_view.view
        return upload_fn(snapshot, copied=True)
    return upload_fn(memory_view.view, copied=False)
