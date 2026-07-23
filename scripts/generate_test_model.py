#!/usr/bin/env python3
"""Generate a minimal ONNX model for integration testing.

Produces a model that accepts a [1,3,640,640] float32 tensor (YOLO-compatible)
and outputs a single [1,84,1] tensor, so code paths expecting a detection
output survive shape verification.

Usage:
    python scripts/generate_test_model.py [output_path]
    # default: models/test_model.onnx
"""

import sys
from pathlib import Path

try:
    import onnx
except ImportError:
    onnx = None


def make_graph() -> onnx.GraphProto:
    from onnx import TensorProto, helper

    X = helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 640, 640])
    Y = helper.make_tensor_value_info("output0", TensorProto.FLOAT, [1, 84, 1])

    n = [
        helper.make_node("Identity", ["images"], ["output0"], name="pass_through"),
    ]

    return helper.make_graph(n, "test_model", [X], [Y])


def generate(path: str = "models/test_model.onnx") -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if onnx is None:
        print("  Skipped: onnx not available", file=sys.stderr)
        return dest

    graph = make_graph()
    model = onnx.helper.make_model(
        graph,
        producer_name="aimiddleplatform-test",
        opset_imports=[onnx.helper.make_opsetid("", 11)],
    )
    onnx.checker.check_model(model)
    onnx.save(model, str(dest))
    size = dest.stat().st_size
    print(f"  Generated test model: {dest} ({size / 1024:.1f} KB)", file=sys.stderr)
    return dest


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "models/test_model.onnx"
    generate(path)
