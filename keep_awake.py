import ctypes
import sys


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def prevent_sleep():
    if sys.platform != 'win32':
        print('[keep_awake] skipped: not running on Windows', flush=True)
        return False

    result = ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    )
    if result == 0:
        print('[keep_awake] SetThreadExecutionState returned 0 (failed)', flush=True)
        return False

    print('[keep_awake] system sleep suppressed for this process', flush=True)
    return True
