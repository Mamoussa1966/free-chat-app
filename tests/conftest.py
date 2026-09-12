from pathlib import Path
import sys
from types import ModuleType
import importlib.machinery

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    class _Stub(ModuleType):
        def __getattr__(self, name):
            if name == "session_state":
                value = {}
                setattr(self, name, value)
                return value
            if name == "sidebar":
                return self
            return lambda *args, **kwargs: None

    st_stub = _Stub("streamlit")
    st_stub.__spec__ = importlib.machinery.ModuleSpec("streamlit", loader=None)
    components_stub = ModuleType("streamlit.components")
    v1_stub = ModuleType("streamlit.components.v1")
    v1_stub.html = lambda *args, **kwargs: None
    components_stub.v1 = v1_stub
    st_stub.components = components_stub
    sys.modules["streamlit"] = st_stub
    sys.modules["streamlit.components"] = components_stub
    sys.modules["streamlit.components.v1"] = v1_stub
