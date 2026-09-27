"""Source-order safetensors layout and direct read primitives.

Generic, dependency-light helpers that map one or more safetensors files
onto a contiguous destination buffer in caller-declared source order and
then read file bytes directly into that buffer.  The module imports only
the standard library; callers supply per-file header specs parsed from the
safetensors JSON headers plus the destination itemsize.

File spec contract, keyed by the same file identities given in `files`:

    tensors          mapping of tensor name to {"dtype"?, "shape"?,
                     "numel"?, "data_offsets": [begin, end]}
    data_start       optional byte offset where the tensor data region
                     begins (safetensors: 8 + JSON header length); inferred
                     from the file itself when the identity is a path
    file_size        optional total file size; inferred from the file itself
                     when the identity is a path
    expected_dtype   optional single expected dtype for every tensor
    expected_dtypes  optional per-tensor expected dtype mapping

Tensor payloads are copied verbatim, so any tensor whose stored bytes do not
equal numel * itemsize (converted or dtype-mismatched), whose data offsets
fall outside its file data region, or whose destination would be misaligned
for the itemsize is ineligible for direct copy.  build_layout raises on
structural errors; per-tensor failures are reported by assess_eligibility.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Sequence, Tuple, Union

_ALIGNMENT = 512
_PREADV = hasattr(os, "preadv") and sys.platform.startswith("linux")
_preadv = getattr(os, "preadv", None)

_TORCH_ALIASES = {
    "float16": "f16",
    "bfloat16": "bf16",
    "float32": "f32",
    "float64": "f64",
    "int8": "i8",
    "int16": "i16",
    "int32": "i32",
    "int64": "i64",
    "uint8": "u8",
    "uint16": "u16",
    "uint32": "u32",
    "uint64": "u64",
}

_RESERVED_SPEC_KEYS = ("data_start", "file_size", "expected_dtype", "expected_dtypes")

__all__ = [
    "LayoutError",
    "ShortReadError",
    "SourceFileLayout",
    "SourceTensor",
    "SourceOrderLayout",
    "SourceBlock",
    "Eligibility",
    "build_layout",
    "assess_eligibility",
    "iter_blocks",
    "read_into",
]


class LayoutError(ValueError):
    pass


class ShortReadError(IOError):
    pass


@dataclass(frozen=True)
class SourceFileLayout:
    file: Any
    file_index: int
    gpu_base: int
    data_start: int
    data_bytes: int


@dataclass(frozen=True)
class SourceTensor:
    name: str
    file_index: int
    rel_offset: Optional[int]
    size: Optional[int]
    numel: int
    dest_offset: Optional[int]


@dataclass(frozen=True)
class SourceOrderLayout:
    files: Tuple[SourceFileLayout, ...]
    tensors: Tuple[SourceTensor, ...]
    itemsize: Any
    alignment: int
    storage_bytes: int


@dataclass(frozen=True)
class SourceBlock:
    file: Any
    file_index: int
    file_offset: int
    size: int
    gpu_offset: int


@dataclass(frozen=True)
class Eligibility:
    total: int
    direct: int
    fallback: int
    reasons: Tuple[Tuple[str, int], ...]
    failed: Tuple[SourceTensor, ...]

    @property
    def all_direct(self) -> bool:
        return self.fallback == 0

    @property
    def reason_counts(self) -> Dict[str, int]:
        return dict(self.reasons)


def build_layout(
    specs: Union[Mapping[Any, Any], Sequence[Any]],
    files: Iterable[Any],
    itemsize: Any,
) -> SourceOrderLayout:
    if isinstance(itemsize, int) and itemsize <= 0:
        raise LayoutError("itemsize must be a positive integer")
    file_list = list(files)
    if not file_list:
        raise LayoutError("no files provided")
    layout_files = []
    tensors = []
    gpu_end = 0
    for index, file in enumerate(file_list):
        spec = _spec_for(specs, file_list, index, file)
        tmap = _tensor_spec_map(spec)
        if tmap is None:
            raise LayoutError("file spec for %r has no tensor map" % (file,))
        data_start, file_size = _file_bounds(file, spec)
        if data_start < 0 or file_size < data_start:
            raise LayoutError("invalid bounds for %r" % (file,))
        data_bytes = file_size - data_start
        base = _align_up(gpu_end, _ALIGNMENT)
        layout_files.append(SourceFileLayout(file, index, base, data_start, data_bytes))
        for name, ts in tmap.items():
            if not isinstance(ts, Mapping):
                raise LayoutError("malformed tensor spec %r" % (name,))
            numel = _numel(ts)
            _itemsize_for(itemsize, ts, name)
            offs = _offsets(ts)
            if offs is None:
                tensors.append(SourceTensor(name, index, None, None, numel, None))
            else:
                begin, end = offs
                tensors.append(SourceTensor(name, index, begin, end - begin, numel, base + begin))
        gpu_end = base + data_bytes
    return SourceOrderLayout(
        tuple(layout_files),
        tuple(tensors),
        itemsize,
        _ALIGNMENT,
        _align_up(gpu_end, _ALIGNMENT),
    )


def assess_eligibility(
    specs: Union[Mapping[Any, Any], Sequence[Any]],
    layout: SourceOrderLayout,
    itemsize: Any,
) -> Eligibility:
    if not isinstance(layout, SourceOrderLayout):
        raise TypeError("layout must be a SourceOrderLayout")
    counts: Dict[str, int] = {}
    failed = []
    direct = 0
    for tensor in layout.tensors:
        reason = _tensor_failure(tensor, layout, specs, itemsize)
        if reason is None:
            direct += 1
        else:
            failed.append(tensor)
            counts[reason] = counts.get(reason, 0) + 1
    total = len(layout.tensors)
    return Eligibility(
        total=total,
        direct=direct,
        fallback=total - direct,
        reasons=tuple(counts.items()),
        failed=tuple(failed),
    )


def iter_blocks(layout: SourceOrderLayout, block_bytes: int) -> Iterator[SourceBlock]:
    if not isinstance(layout, SourceOrderLayout):
        raise TypeError("layout must be a SourceOrderLayout")
    if not isinstance(block_bytes, int) or block_bytes <= 0:
        raise ValueError("block_bytes must be a positive integer")
    for file_layout in layout.files:
        remaining = file_layout.data_bytes
        pos = 0
        while remaining > 0:
            size = block_bytes if remaining > block_bytes else remaining
            yield SourceBlock(
                file=file_layout.file,
                file_index=file_layout.file_index,
                file_offset=file_layout.data_start + pos,
                size=size,
                gpu_offset=file_layout.gpu_base + pos,
            )
            pos += size
            remaining -= size


def read_into(handle: Any, storage: Any, size: int, offset: int) -> int:
    """Read exactly `size` bytes from `handle` at absolute file `offset`
    into the first `size` bytes of `storage`.

    On Linux the read uses os.preadv against a zero-copy writable view of
    `storage`; a PyTorch uint8 CPU tensor via .numpy() is supported and is
    never copied.  Elsewhere (Windows, tests) a portable seek/readinto
    fallback is used.  Short reads raise ShortReadError.
    """
    if not isinstance(size, int) or size < 0:
        raise ValueError("size must be a non-negative integer")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if size == 0:
        return 0
    view = _writable_view(storage)
    if len(view) < size:
        raise ValueError("storage provides %d bytes; requested %d" % (len(view), size))
    buf = view[:size]
    if _PREADV:
        fd, owned = _acquire_fd(handle)
        try:
            _preadv_exact(fd, buf, offset, size)
        finally:
            if owned:
                os.close(fd)
        return size
    file_obj, owned = _acquire_file(handle)
    try:
        file_obj.seek(offset)
        _readinto_exact(file_obj, buf, offset, size)
    finally:
        if owned:
            file_obj.close()
    return size


def _spec_for(specs, files, index, file):
    if isinstance(specs, Mapping):
        spec = specs.get(file)
    else:
        if index >= len(specs):
            raise LayoutError("specs sequence too short")
        spec = specs[index]
    if spec is None or not isinstance(spec, Mapping):
        raise LayoutError("missing or invalid spec for file %r" % (file,))
    return spec


def _tensor_spec_map(spec):
    if "tensors" in spec:
        tmap = spec["tensors"]
        if isinstance(tmap, Mapping):
            return tmap
        return None
    if any(key in spec for key in _RESERVED_SPEC_KEYS):
        return None
    if spec and all(isinstance(value, Mapping) for value in spec.values()):
        return spec
    return None


def _file_bounds(file, spec):
    data_start = spec.get("data_start")
    file_size = spec.get("file_size")
    if data_start is not None:
        data_start = int(data_start)
    if file_size is not None:
        file_size = int(file_size)
    if data_start is None or file_size is None:
        if not isinstance(file, (str, os.PathLike)):
            raise LayoutError(
                "cannot infer bounds for non-path file %r; provide data_start and file_size" % (file,)
            )
        path = os.fspath(file)
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            raise LayoutError("cannot stat file %r" % (path,)) from exc
        if file_size is None:
            file_size = size
        if data_start is None:
            data_start = _read_header_length(path, file_size)
    return data_start, file_size


def _read_header_length(path, file_size):
    if file_size < 8:
        raise LayoutError("file %r too small to hold a safetensors header" % (path,))
    with open(path, "rb") as handle:
        raw = handle.read(8)
    if len(raw) != 8:
        raise LayoutError("cannot read header length from %r" % (path,))
    data_start = 8 + int.from_bytes(raw, "little")
    if data_start > file_size:
        raise LayoutError("header length of %r exceeds file size" % (path,))
    return data_start


def _numel(tensor_spec):
    if "numel" in tensor_spec:
        numel = tensor_spec["numel"]
        if isinstance(numel, bool) or not isinstance(numel, int) or numel < 0:
            raise LayoutError("invalid numel")
        return numel
    shape = tensor_spec.get("shape")
    if shape is None:
        raise LayoutError("tensor has neither shape nor numel")
    total = 1
    for dim in shape:
        dim = int(dim)
        if dim < 0:
            raise LayoutError("negative shape dimension")
        total *= dim
    return total


def _offsets(tensor_spec):
    raw = tensor_spec.get("data_offsets")
    if raw is None:
        return None
    try:
        begin = int(raw[0])
        end = int(raw[1])
    except (TypeError, IndexError, ValueError):
        return None
    if begin < 0 or end < begin:
        return None
    return begin, end


def _align_up(value, alignment):
    if alignment <= 0:
        raise LayoutError("alignment must be positive")
    return (value + alignment - 1) // alignment * alignment


def _tensor_failure(tensor, layout, specs, itemsize):
    file_layout = layout.files[tensor.file_index]
    tensor_itemsize = _itemsize_for(itemsize, _tensor_spec_for(specs, layout, tensor), tensor.name)
    if tensor.rel_offset is None or tensor.size is None:
        return "invalid-range"
    if tensor.rel_offset < 0 or tensor.size < 0:
        return "invalid-range"
    if tensor.rel_offset + tensor.size > file_layout.data_bytes:
        return "invalid-range"
    if tensor.size != tensor.numel * tensor_itemsize:
        return "dtype-mismatch"
    if tensor.rel_offset % tensor_itemsize != 0 or tensor.dest_offset % tensor_itemsize != 0:
        return "unsafe-alignment"
    if _declared_dtype_mismatch(tensor, specs, layout):
        return "dtype-mismatch"
    return None


def _declared_dtype_mismatch(tensor, specs, layout):
    tensor_spec = _tensor_spec_for(specs, layout, tensor)
    if not isinstance(tensor_spec, Mapping):
        return False
    actual = tensor_spec.get("dtype")
    file_spec = _spec_for(
        specs,
        layout.files,
        tensor.file_index,
        layout.files[tensor.file_index].file,
    )
    expected = _expected_dtype_for(tensor.name, file_spec)
    if expected is None:
        return False
    if actual is None:
        return True
    return _canon_dtype(actual) != _canon_dtype(expected)


def _tensor_spec_for(specs, layout, tensor):
    file_layout = layout.files[tensor.file_index]
    spec = _spec_for(specs, layout.files, tensor.file_index, file_layout.file)
    tmap = _tensor_spec_map(spec)
    return tmap.get(tensor.name) if tmap is not None else None


def _itemsize_for(itemsize, tensor_spec, name):
    if callable(itemsize):
        value = itemsize(tensor_spec)
    elif isinstance(itemsize, Mapping):
        value = itemsize.get(name)
    else:
        value = itemsize
    try:
        value = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise LayoutError("missing itemsize for tensor %r" % (name,))
    if value <= 0:
        raise LayoutError("itemsize must be positive for tensor %r" % (name,))
    return value


def _expected_dtype_for(name, spec):
    expected = spec.get("expected_dtypes")
    if isinstance(expected, Mapping):
        value = expected.get(name)
        if value is not None:
            return value
    value = spec.get("expected_dtype")
    if value is not None:
        return value
    return None


def _canon_dtype(value):
    text = value
    if not isinstance(text, str):
        text = str(text)
    text = text.strip().lower().replace("_", "").replace(" ", "")
    if text.startswith("torch."):
        text = text[len("torch."):]
    return _TORCH_ALIASES.get(text, text)


def _writable_view(storage):
    if isinstance(storage, memoryview):
        view = storage
    elif isinstance(storage, bytearray):
        view = memoryview(storage)
    else:
        obj = storage
        if hasattr(obj, "detach"):
            obj = obj.detach()
        if hasattr(obj, "numpy"):
            try:
                obj = obj.numpy()
            except Exception as exc:
                raise ValueError("storage must be a zero-copy CPU buffer") from exc
        elif hasattr(obj, "__array__"):
            obj = obj.__array__()
        try:
            view = memoryview(obj)
        except TypeError as exc:
            raise ValueError("unsupported storage type %r" % (type(storage).__name__,)) from exc
    if view.readonly:
        raise ValueError("storage is read-only")
    try:
        return view.cast("B")
    except TypeError as exc:
        raise ValueError("storage is not a contiguous writable buffer") from exc


def _acquire_fd(handle):
    if isinstance(handle, int):
        return handle, False
    if hasattr(handle, "fileno"):
        try:
            return handle.fileno(), False
        except (OSError, ValueError):
            pass
    if isinstance(handle, (str, os.PathLike)):
        return os.open(os.fspath(handle), os.O_RDONLY), True
    raise ValueError("handle is not a file descriptor, file object, or path")


def _preadv_exact(fd, buf, offset, size):
    preadv = _preadv
    if preadv is None:
        raise RuntimeError("os.preadv is not available on this platform")
    total = 0
    while total < size:
        try:
            read = preadv(fd, [buf[total:]], offset + total)
        except InterruptedError:
            continue
        if read <= 0:
            raise ShortReadError(
                "short read at file offset %d: got %d of %d bytes" % (offset, total, size)
            )
        total += read


def _acquire_file(handle):
    if hasattr(handle, "readinto") and hasattr(handle, "seek"):
        return handle, False
    if isinstance(handle, (str, os.PathLike)):
        return open(os.fspath(handle), "rb"), True
    if isinstance(handle, int):
        return os.fdopen(handle, "rb", closefd=False), True
    raise ValueError("handle is not a file object, path, or file descriptor")


def _readinto_exact(file_obj, buf, offset, size):
    total = 0
    while total < size:
        try:
            read = file_obj.readinto(buf[total:])
        except InterruptedError:
            continue
        if not read:
            raise ShortReadError(
                "short read at file offset %d: got %d of %d bytes" % (offset, total, size)
            )
        total += read
