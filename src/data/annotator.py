import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.data.collector import CollectedFrame

logger = logging.getLogger(__name__)


@dataclass
class Annotation:
    image_id: str
    file_name: str
    width: int
    height: int
    bboxes: list[dict[str, Any]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


class COCOExporter:
    def __init__(self, output_dir: str | Path):
        self._output = Path(output_dir)
        self._images_dir = self._output / "images"
        self._annotations_dir = self._output / "annotations"
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._annotations_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        frames: list[CollectedFrame],
        dataset_name: str = "dataset",
    ) -> Path:
        images: list[dict[str, Any]] = []
        annotations: list[dict[str, Any]] = []
        categories: dict[str, int] = {}
        ann_id = 1

        for img_id, frame in enumerate(frames, 1):
            h, w = frame.image.shape[:2]
            file_name = f"{img_id:08d}.jpg"
            dest = self._images_dir / file_name
            cv2.imwrite(str(dest), frame.image)

            images.append({
                "id": img_id,
                "file_name": file_name,
                "width": w,
                "height": h,
            })

            detections = frame.metadata.get("detections", [])
            for det in detections:
                label = det.get("label", "unknown")
                if label not in categories:
                    categories[label] = len(categories) + 1
                cat_id = categories[label]

                bbox = det.get("bbox", [0, 0, 0, 0])
                x1, y1, x2, y2 = bbox
                bw = max(0, x2 - x1)
                bh = max(0, y2 - y1)

                annotations.append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cat_id,
                    "bbox": [x1, y1, bw, bh],
                    "area": bw * bh,
                    "iscrowd": 0,
                    "confidence": det.get("confidence", 1.0),
                })
                ann_id += 1

        coco = {
            "info": {
                "description": dataset_name,
                "version": "1.0",
                "year": datetime.now().year,
                "date_created": datetime.now().isoformat(),
            },
            "images": images,
            "annotations": annotations,
            "categories": [
                {"id": cat_id, "name": name, "supercategory": "object"}
                for name, cat_id in sorted(categories.items(), key=lambda x: x[1])
            ],
        }

        json_path = self._annotations_dir / f"{dataset_name}.json"
        json_path.write_text(
            json.dumps(coco, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "COCO export: %d images, %d annotations, %d categories -> %s",
            len(images), len(annotations), len(categories), json_path,
        )
        return json_path


class YOLOExporter:
    def __init__(self, output_dir: str | Path):
        self._output = Path(output_dir)
        self._images_dir = self._output / "images"
        self._labels_dir = self._output / "labels"
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._labels_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        frames: list[CollectedFrame],
        dataset_name: str = "dataset",
    ) -> Path:
        class_names: list[str] = []
        class_map: dict[str, int] = {}

        for img_id, frame in enumerate(frames, 1):
            h, w = frame.image.shape[:2]
            file_name = f"{img_id:08d}.jpg"
            label_name = f"{img_id:08d}.txt"
            dest = self._images_dir / file_name
            cv2.imwrite(str(dest), frame.image)

            lines: list[str] = []
            detections = frame.metadata.get("detections", [])
            for det in detections:
                label = det.get("label", "unknown")
                if label not in class_map:
                    class_map[label] = len(class_map)
                    class_names.append(label)
                cls_id = class_map[label]

                bbox = det.get("bbox", [0, 0, 0, 0])
                x1, y1, x2, y2 = bbox
                cx = (x1 + x2) / 2 / w
                cy = (y1 + y2) / 2 / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

            label_path = self._labels_dir / label_name
            label_path.write_text("\n".join(lines), encoding="utf-8")

        names_path = self._output / f"{dataset_name}.names"
        names_path.write_text("\n".join(class_names), encoding="utf-8")

        data_yaml = {
            "path": str(self._output.resolve()),
            "train": "images",
            "val": "images",
            "names": {i: name for i, name in enumerate(class_names)},
        }
        yaml_path = self._output / f"{dataset_name}.yaml"
        yaml_path.write_text(
            json.dumps(data_yaml, ensure_ascii=False, indent=2).replace('"', "")
            .replace(": ", ": ").replace(", ", ", ").replace("{", "").replace("}", ""),
            encoding="utf-8",
        )

        logger.info(
            "YOLO export: %d images, %d classes -> %s",
            len(frames), len(class_names), yaml_path,
        )
        return yaml_path


class AnnotationPipeline:
    def __init__(self, output_dir: str | Path):
        self._coco = COCOExporter(output_dir / "coco")
        self._yolo = YOLOExporter(output_dir / "yolo")

    async def export_all(
        self,
        frames: list[CollectedFrame],
        dataset_name: str = "dataset",
        formats: list[str] | None = None,
    ) -> dict[str, Path]:
        fmts = formats or ["coco", "yolo"]
        results: dict[str, Path] = {}
        if "coco" in fmts:
            results["coco"] = self._coco.export(frames, dataset_name)
        if "yolo" in fmts:
            results["yolo"] = self._yolo.export(frames, dataset_name)
        return results
