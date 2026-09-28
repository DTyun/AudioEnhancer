"""通过 Windows Core Audio API 获取默认播放设备。"""

import ctypes
import ctypes.wintypes as wt
import uuid


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wt.DWORD),
        ("Data2", wt.WORD),
        ("Data3", wt.WORD),
        ("Data4", wt.BYTE * 8),
    ]

    @classmethod
    def parse(cls, value: str) -> "GUID":
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wt.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", wt.USHORT),
        ("wReserved1", wt.WORD),
        ("wReserved2", wt.WORD),
        ("wReserved3", wt.WORD),
        ("data", ctypes.c_byte * 16),
    ]


CLSID_MMDeviceEnumerator = GUID.parse("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID.parse("A95664D2-9614-4F35-A746-DE8DB63617E6")
PKEY_Device_FriendlyName = PROPERTYKEY(
    GUID.parse("A45C254E-DF1C-4EFD-8020-67D146A850E0"), 14
)
VT_LPWSTR = 31


def _method(interface: ctypes.c_void_p, index: int, *argtypes):
    vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])


def _release(interface: ctypes.c_void_p) -> None:
    if interface.value:
        _method(interface, 2)(interface)


def get_default_playback_device() -> tuple[str | None, str | None]:
    """返回默认播放设备的 endpoint ID 和名称；失败时返回 (None, None)。"""
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.PropVariantClear.argtypes = [ctypes.POINTER(PROPVARIANT)]

    initialized = ole32.CoInitialize(None) >= 0
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    store = ctypes.c_void_p()
    endpoint_ptr = ctypes.c_void_p()
    try:
        if ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator), None, 1,
            ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(enumerator),
        ) < 0:
            return None, None

        get_default = _method(
            enumerator, 4, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        )
        if get_default(enumerator, 0, 0, ctypes.byref(device)) < 0:
            return None, None

        get_id = _method(device, 5, ctypes.POINTER(ctypes.c_void_p))
        if get_id(device, ctypes.byref(endpoint_ptr)) < 0 or not endpoint_ptr.value:
            return None, None
        endpoint_id = ctypes.wstring_at(endpoint_ptr.value)

        friendly_name = ""
        get_store = _method(device, 4, wt.DWORD, ctypes.POINTER(ctypes.c_void_p))
        if get_store(device, 0, ctypes.byref(store)) >= 0:
            get_value = _method(
                store, 5, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)
            )
            value = PROPVARIANT()
            if get_value(store, ctypes.byref(PKEY_Device_FriendlyName), ctypes.byref(value)) >= 0:
                try:
                    if value.vt == VT_LPWSTR:
                        ptr = ctypes.cast(ctypes.byref(value, 8), ctypes.POINTER(ctypes.c_void_p))
                        if ptr.contents.value:
                            friendly_name = ctypes.wstring_at(ptr.contents.value)
                finally:
                    ole32.PropVariantClear(ctypes.byref(value))
        return endpoint_id, friendly_name
    except (OSError, ValueError):
        return None, None
    finally:
        if endpoint_ptr.value:
            ole32.CoTaskMemFree(endpoint_ptr)
        _release(store)
        _release(device)
        _release(enumerator)
        if initialized:
            ole32.CoUninitialize()


if __name__ == "__main__":
    print(get_default_playback_device())
