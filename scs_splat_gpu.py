"""
scs_splat_gpu.py -- INTERNAL GPU LAYOUT, and ONLY GPU layout.

Architecture:
  SplatData --pack--> SplatGPUBuffer --upload--> GPU
                    (this file)

  * GPU_LAYOUT_VERSION = 1. It does NOT change when a new disk
    format (RAD, ...) is added. Disk parsers change; GPU layout
    stays. That is the whole point of the separation.
  * Layout (interleaved, float32, 56 bytes/splat):
      offset 0:  position  vec3 f32 (12B)
      offset 12: scale      vec3 f32 (12B)
      offset 24: rotation   vec4 f32 (16B, quat x,y,z,w)
      offset 40: color      vec3 f32 (12B, linear, 0..1)
      offset 52: opacity    f32    (4B)
    Stride = 56. SH coefficients (if any) live in a SEPARATE
    buffer (SH_BUFFER), same order, sh_len floats per splat.
    This layout is the same for WebGL2 and WebGPU -- the backends
    differ in how they upload it (bufferData vs GPUBuffer), not
    in what the bytes mean.
  * This file must not import scs_splat_formats (disk). It only
    consumes SplatData (the shared type, duck-typed: any object
    with .positions/.scales/.rotations/.colors/.opacities/.sh).
"""

import struct

GPU_LAYOUT_VERSION = 1
GPU_STRIDE = 56  # bytes per splat, interleaved
GPU_ATTRIBUTES = [
    {'name': 'position', 'offset': 0, 'components': 3, 'type': 'float32'},
    {'name': 'scale', 'offset': 12, 'components': 3, 'type': 'float32'},
    {'name': 'rotation', 'offset': 24, 'components': 4, 'type': 'float32'},
    {'name': 'color', 'offset': 40, 'components': 3, 'type': 'float32'},
    {'name': 'opacity', 'offset': 52, 'components': 1, 'type': 'float32'},
]

class SplatGPUBuffer:
    """Packed GPU bytes + metadata. The renderer uploads this, never SplatData."""
    def __init__(self, data_bytes=b'', sh_bytes=b'', count=0, sh_degree=0, sh_len=0):
        self.data = bytes(data_bytes)
        self.sh_data = bytes(sh_bytes)
        self.count = int(count)
        self.sh_degree = int(sh_degree)
        self.sh_len = int(sh_len)
        self.stride = GPU_STRIDE
        self.layout_version = GPU_LAYOUT_VERSION
    def describe(self):
        return {'layout_version': self.layout_version, 'stride': self.stride,
                'count': self.count, 'bytes': len(self.data),
                'sh_degree': self.sh_degree, 'sh_len': self.sh_len,
                'sh_bytes': len(self.sh_data),
                'attributes': [a['name'] for a in GPU_ATTRIBUTES]}
    def __len__(self):
        return self.count

def pack_gpu(splat_data):
    """SplatData -> SplatGPUBuffer. The ONLY place disk -> GPU happens.
    Deterministic: same SplatData in, same bytes out, regardless of
    which disk format it came from (PLY/SPZ/SOG all pack identically)."""
    count = splat_data.count
    buf = bytearray(count * GPU_STRIDE)
    sh_len = 0
    if getattr(splat_data, 'sh', None) and splat_data.sh:
        # sh is list of flat coeffs per splat
        sh_len = len(splat_data.sh[0]) if splat_data.sh and splat_data.sh[0] else 0
    sh_buf = bytearray(count * sh_len * 4) if sh_len else bytearray()
    for i in range(count):
        p = splat_data.positions[i] if i < len(splat_data.positions) else (0, 0, 0)
        s = splat_data.scales[i] if i < len(splat_data.scales) else (0.1, 0.1, 0.1)
        q = splat_data.rotations[i] if i < len(splat_data.rotations) else (0, 0, 0, 1)
        c = splat_data.colors[i] if i < len(splat_data.colors) else (1, 1, 1)
        a = splat_data.opacities[i] if i < len(splat_data.opacities) else 1.0
        off = i * GPU_STRIDE
        struct.pack_into('<3f', buf, off, p[0], p[1], p[2])
        struct.pack_into('<3f', buf, off+12, s[0], s[1], s[2])
        struct.pack_into('<4f', buf, off+24, q[0], q[1], q[2], q[3])
        struct.pack_into('<3f', buf, off+40, c[0], c[1], c[2])
        struct.pack_into('<f', buf, off+52, a)
        if sh_len:
            base = i * sh_len * 4
            coeffs = splat_data.sh[i] if i < len(splat_data.sh) else [0.0]*sh_len
            for j in range(sh_len):
                struct.pack_into('<f', sh_buf, base + j*4, float(coeffs[j]) if j < len(coeffs) else 0.0)
    return SplatGPUBuffer(data_bytes=bytes(buf), sh_bytes=bytes(sh_buf),
                          count=count, sh_degree=getattr(splat_data, 'sh_degree', 0),
                          sh_len=sh_len)

def unpack_gpu(gpu_buffer):
    """GPU bytes -> SplatData (for tests: pack -> unpack must round-trip)."""
    import math as _math
    from scs_splat_formats import SplatData
    positions, scales, rotations, colors, opacities = [], [], [], [], []
    for i in range(gpu_buffer.count):
        off = i * GPU_STRIDE
        p = struct.unpack_from('<3f', gpu_buffer.data, off)
        s = struct.unpack_from('<3f', gpu_buffer.data, off+12)
        q = struct.unpack_from('<4f', gpu_buffer.data, off+24)
        c = struct.unpack_from('<3f', gpu_buffer.data, off+40)
        a = struct.unpack_from('<f', gpu_buffer.data, off+52)[0]
        positions.append(p); scales.append(s); rotations.append(q); colors.append(c); opacities.append(a)
    sh = []
    if gpu_buffer.sh_len:
        for i in range(gpu_buffer.count):
            base = i * gpu_buffer.sh_len * 4
            coeffs = [struct.unpack_from('<f', gpu_buffer.sh_data, base + j*4)[0] for j in range(gpu_buffer.sh_len)]
            sh.append(coeffs)
    return SplatData(positions=positions, scales=scales, rotations=rotations,
                     colors=colors, opacities=opacities, sh=sh,
                     sh_degree=gpu_buffer.sh_degree, source_format='gpu')

def gpu_layout():
    """Describe the canonical GPU layout (for the pipeline / shaders)."""
    return {'version': GPU_LAYOUT_VERSION, 'stride': GPU_STRIDE,
            'attributes': list(GPU_ATTRIBUTES)}
