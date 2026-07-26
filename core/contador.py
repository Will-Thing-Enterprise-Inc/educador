# core/contador.py
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

_lock = threading.Lock()


def _caminho(jardim: str) -> str:
    return os.path.join(DATA_DIR, f"contador_{jardim}.json")


def _ler(jardim: str) -> int:
    caminho = _caminho(jardim)
    if not os.path.exists(caminho):
        return 0
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f).get("visitas", 0)
    except (json.JSONDecodeError, OSError):
        return 0


def _escrever(jardim: str, valor: int) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_caminho(jardim), "w", encoding="utf-8") as f:
        json.dump({"jardim": jardim, "visitas": valor}, f)


def incrementar(jardim: str) -> int:
    """Incrementa e retorna o novo total do jardim informado. Thread-safe."""
    with _lock:
        novo = _ler(jardim) + 1
        _escrever(jardim, novo)
        return novo


def total(jardim: str) -> int:
    with _lock:
        return _ler(jardim)