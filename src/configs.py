import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)
