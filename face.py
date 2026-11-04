"""Face module. Uses `face_recognition` if installed, else a basic image-hash fallback
(catches the same/near-identical photo reused, works with zero extra installs)."""
import io
from PIL import Image
try:
    import face_recognition, numpy as np
    MODE = "face_recognition"
    def embed(b):
        try:
            e = face_recognition.face_encodings(face_recognition.load_image_file(io.BytesIO(b)))
        except Exception:
            return None
        return [float(x) for x in e[0]] if e else None
    def same(a, b):
        return float(np.linalg.norm(np.array(a) - np.array(b))) < 0.5
except ImportError:
    MODE = "basic-hash"
    def embed(b):
        try:
            px = list(Image.open(io.BytesIO(b)).convert("L").resize((8, 8)).getdata())
        except Exception:
            return None
        m = sum(px) / 64
        return [1 if p > m else 0 for p in px]
    def same(a, b):
        return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) <= 5
