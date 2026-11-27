"""Isolated imports for the supplied P4/P2 code, without changing its files."""
import ast
from functools import lru_cache
import hashlib
import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType

_LOCK = threading.RLock()
LOCAL_MODULES = {"config", "schemas", "json_utils", "llm_client", "agents"}


def fingerprint(folder):
    digest = hashlib.sha256()
    for path in sorted(Path(folder).glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _load_p2(folder, revision):
    namespace = "_fmcg_p2_" + hashlib.sha256((folder + revision).encode()).hexdigest()[:16]
    with _LOCK:
        package = ModuleType(namespace)
        package.__path__ = [folder]
        sys.modules[namespace] = package
        loaded = {}
        for name in ("config", "schemas", "json_utils", "llm_client", "agents"):
            path = Path(folder) / f"{name}.py"
            spec = importlib.util.spec_from_file_location(f"{namespace}.{name}", path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in LOCAL_MODULES:
                    node.level = 1
            exec(compile(tree, str(path), "exec"), module.__dict__)
            loaded[name] = module
        return loaded


def load_p2(folder):
    bundled = Path(__file__).resolve().parents[2] / "retrival/integration/p2_agents"
    if Path(folder).resolve() == bundled:
        from integration.p2_agents import agents, config, json_utils, llm_client, schemas
        return {"agents": agents, "config": config, "json_utils": json_utils,
                "llm_client": llm_client, "schemas": schemas}
    folder = str(Path(folder).resolve())
    return _load_p2(folder, fingerprint(folder))
