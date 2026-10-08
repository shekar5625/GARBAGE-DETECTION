"""Build a YOLOv5 train/val split from the photos in this folder.

Reads:
  fine tune/*.jpg                         the collected photos (left untouched)
  <labels-dir>/*.txt                      matching YOLO labels (default: the
                                          labelled copy in garbage-detection-sc)
Writes:
  fine tune/dataset/images/{train,val}/*.jpg
  fine tune/dataset/labels/{train,val}/*.txt
  fine tune/dataset/data.yaml

Stratified split: clean_* (no garbage) and the rest are split separately so
both sets keep the same clean:garbage ratio. Re-run anytime; it clears
dataset/ first. Same seed -> same split.

Usage:  python split_dataset.py [--val-frac 0.2] [--seed 42] [--labels-dir DIR]
"""
import argparse
import random
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dataset"
DEFAULT_LABELS = HERE.parents[1] / "garbage-detection-sc" / "data" / "labels" / "train"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS)
    args = ap.parse_args()

    images = sorted(HERE.glob("*.jpg"))
    missing = [i.name for i in images if not (args.labels_dir / f"{i.stem}.txt").exists()]
    if missing:
        raise SystemExit(f"{len(missing)} images have no label in {args.labels_dir}, e.g. {missing[:3]}")

    clean = [i for i in images if i.name.startswith("clean_")]
    garbage = [i for i in images if not i.name.startswith("clean_")]

    rng = random.Random(args.seed)
    split = {"train": [], "val": []}
    for group in (clean, garbage):
        group = group[:]
        rng.shuffle(group)
        n_val = round(len(group) * args.val_frac)
        split["val"] += group[:n_val]
        split["train"] += group[n_val:]

    shutil.rmtree(OUT, ignore_errors=True)
    for name, imgs in split.items():
        (OUT / "images" / name).mkdir(parents=True)
        (OUT / "labels" / name).mkdir(parents=True)
        boxes = 0
        for img in imgs:
            shutil.copy2(img, OUT / "images" / name / img.name)
            lbl = args.labels_dir / f"{img.stem}.txt"
            shutil.copy2(lbl, OUT / "labels" / name / lbl.name)
            boxes += sum(1 for line in lbl.read_text().splitlines() if line.strip())
        n_clean = sum(i.name.startswith("clean_") for i in imgs)
        print(f"{name:5s}: {len(imgs):3d} images ({len(imgs) - n_clean} garbage, {n_clean} clean), {boxes} boxes")

    (OUT / "data.yaml").write_text(
        f"path: {OUT.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "\n"
        "nc: 1\n"
        "names: ['garbage']\n"
    )
    print(f"wrote {OUT / 'data.yaml'}")


if __name__ == "__main__":
    main()
