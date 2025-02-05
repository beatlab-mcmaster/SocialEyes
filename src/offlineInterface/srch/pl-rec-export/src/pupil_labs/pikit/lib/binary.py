import io
import os
import pathlib

import numpy as np
import requests

from ..lib.util import cached_property


class URLFileReader(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        self.position = 0

    _size = None

    @property
    def filename(self):
        return self.path.split("/")[-1].split("?")[0]

    @cached_property
    def size(self):
        if self._size is None:
            range_header = "bytes=0-"
            response = requests.get(
                self.url, stream=True, headers={"range": range_header}
            )
            response.raise_for_status()
            if "content-range" in response.headers:
                content_range = response.headers["content-range"]
                self._size = int(content_range.split("/")[-1])
            elif "content-length" in response.headers:
                self._size = int(response.headers["content-length"])
        return self._size

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.position = offset
        elif whence == io.SEEK_CUR:
            self.position += offset
        elif whence == io.SEEK_END:
            self.position = self.size + offset
        else:
            raise ValueError(
                "invalid whence (%r, should be %d, %d, %d)"
                % (whence, io.SEEK_SET, io.SEEK_CUR, io.SEEK_END)
            )

        return self.position

    def seekable(self):
        return True

    def read(self, size=-1):
        if size == -1:
            # Read to the end of the file
            range_header = f"bytes={self.position}-"
            self.seek(offset=0, whence=io.SEEK_END)
        else:
            new_position = self.position + size

            # If we're going to read beyond the end of the object, return
            # the entire object.
            if new_position >= self.size:
                return self.read()

            range_header = "bytes=%d-%d" % (self.position, new_position - 1)
            self.seek(offset=size, whence=io.SEEK_CUR)
        response = requests.get(self.url, stream=True, headers={"range": range_header})
        data = response.raw
        if size >= 0:
            rv = data.read(size)
        else:
            rv = data.read()
        return rv

    def readable(self):
        return True


class FileObjectReader(io.RawIOBase):
    def __init__(self, file_handle, size):
        self.file_handle = file_handle
        self.size = size

    def tell(self):
        return self.file_handle.tell()

    def seek(self, offset, whence=io.SEEK_SET):
        return self.file_handle.seek(offset, whence)

    def seekable(self):
        return True

    def read(self, size=-1):
        return self.file_handle.read(size)

    def readable(self):
        return True


class LocalFileReader(FileObjectReader):
    def __init__(self, path, size=None):
        self.path = pathlib.Path(path)
        if size is not None:
            self._size = size

    @property
    def size(self):
        if hasattr(self, "_size"):
            return self._size
        self._size = os.stat(self.path).st_size
        return self._size

    @property
    def filename(self):
        return self.path.name

    @property
    def file_handle(self):
        if hasattr(self, "_file_handle"):
            return self._file_handle
        self._file_handle = open(self.path, "rb")
        return self._file_handle


class File(object):
    def __init__(self, name, size, open):
        self.name = name
        self.size = size
        self.open = open

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                f"{attr}={getattr(self, attr, '?')!r}" for attr in ["name", "size"]
            )
            + ">"
        )


class FileReader(io.BufferedReader):
    def __init__(self, file):
        self.file = file
        if isinstance(file, File):
            self.reader = FileObjectReader(file_handle=file.open("rb"), size=file.size)
        elif isinstance(file, pathlib.Path):
            self.reader = LocalFileReader(file)
        elif isinstance(file, str):
            if str(file).startswith("http"):
                self.reader = URLFileReader(file)
            else:
                self.reader = LocalFileReader(file)
        elif isinstance(file, FileObjectReader):
            self.reader = file
        elif isinstance(file, io.IOBase):
            self.reader = FileObjectReader(file)
        else:
            raise ValueError(f"{file} not readable")

    @property
    def size(self):
        return self.reader.size


class BinaryArrayReader(FileReader):
    """ A helper for reading binary array files """

    @classmethod
    def parse_bytes(cls, bytedata):
        return np.frombuffer(bytedata, cls.dtype)

    @property
    def entry_size(self):
        return self.dtype.itemsize

    def __iter__(self):
        previous_position = self.reader.tell()
        self.reader.seek(0)
        wanted_chunk_size = 16 * 1024
        chunk_size = int(wanted_chunk_size / self.entry_size) * self.entry_size
        while True:
            data = self.reader.read(chunk_size)
            if not data:
                break
            for value in self.parse_bytes(data):
                yield value
        self.reader.seek(previous_position)

    def iter_slice(self, start_index, end_index=None):
        previous_position = self.reader.tell()
        current = start_index * self.entry_size
        self.reader.seek(current)
        wanted_chunk_size = 16 * 1024
        chunk_size = int(wanted_chunk_size / self.entry_size) * self.entry_size
        while True:
            data = self.reader.read(chunk_size)
            current += chunk_size // self.entry_size
            if not data:
                break
            for value in self.parse_bytes(data):
                yield value
            if end_index and current >= end_index:
                break
        self.reader.seek(previous_position)

    def seek(self, pos):
        previous_position = self.reader.tell()
        seek_position = pos * self.entry_size
        seek_position = min(max(0, seek_position), self.reader.size)
        self.reader.seek(seek_position)
        data = self.reader.read(self.entry_size)
        self.reader.seek(previous_position)
        value = self.parse_bytes(data)[0]
        return value

    def __len__(self):
        return int(self.reader.size / self.entry_size)

    def __bool__(self):
        return self.reader.size > self.entry_size

    def __getitem__(self, key):
        if key == 0:
            return self.first
        if key == -1:
            return self.last
        return self.values[key]

    @cached_property
    def first(self):
        previous_position = self.reader.tell()
        self.reader.seek(0)
        data = self.reader.read(self.entry_size)
        self.reader.seek(previous_position)
        value = self.parse_bytes(data)[0]
        return value

    @cached_property
    def last(self):
        if self.reader.size is None or self.reader.size < self.entry_size:
            return None
        previous_position = self.reader.tell()
        self.reader.seek(self.reader.size - self.entry_size)
        data = self.reader.read(self.entry_size)
        self.reader.seek(previous_position)
        value = self.parse_bytes(data)[0]
        return value

    @cached_property
    def values(self):
        return np.array(self)

    @property
    def filename(self):
        return self.reader.filename

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(f"{attr}={getattr(self, attr, '?')!r}" for attr in ["first"])
            + ">"
        )
