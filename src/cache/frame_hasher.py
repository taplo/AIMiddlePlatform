import cv2
import numpy as np


class FrameHasher:
    def __init__(self, hash_size: int = 8):
        self.hash_size = hash_size

    def _raw_to_gray(self, arr: np.ndarray) -> np.ndarray:
        n = len(arr)
        if n % 3 == 0:
            pixels = arr.reshape(-1, 3).mean(axis=1).astype(np.uint8)
        else:
            pixels = arr
        side = int(np.ceil(np.sqrt(len(pixels))))
        padded = np.zeros(side * side, dtype=np.uint8)
        padded[:len(pixels)] = pixels
        return padded.reshape(side, side)

    def compute(self, frame: bytes) -> str:
        arr = np.frombuffer(frame, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            img = self._raw_to_gray(arr)
        resized = cv2.resize(img, (self.hash_size, self.hash_size))
        resized_f = np.float32(resized)
        h, w = self.hash_size, self.hash_size
        gradient = (np.arange(h)[:, None] + np.arange(w)[None, :]).astype(np.float32) * 0.01
        resized_f += gradient * (resized_f / 255.0)
        dct = cv2.dct(resized_f)
        dct_low = dct[:self.hash_size, :self.hash_size]
        median = np.median(dct_low)
        bits = (dct_low > median).flatten()
        hex_str = "".join("1" if b else "0" for b in bits)
        return hex(int(hex_str, 2))[2:].zfill(16)

    def hamming_distance(self, a: str, b: str) -> int:
        if a == b:
            return 0
        int_a = int(a, 16)
        int_b = int(b, 16)
        return (int_a ^ int_b).bit_count()
