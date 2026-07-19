import argparse
import json
import logging
import sys
from pathlib import Path

from src.models.package_manager import ModelPackageManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aimp-model",
        description="AI Middle Platform - Model Package Manager CLI",
    )
    parser.add_argument(
        "--store",
        default=str(Path.cwd() / "models" / "packages"),
        help="Package store directory (default: models/packages)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build a model package from directory")
    p_build.add_argument("model_dir", help="Path to model directory")
    p_build.add_argument("model_id", help="Model identifier")
    p_build.add_argument("--name", help="Human-readable name")
    p_build.add_argument("--version", default="1.0.0", help="Semantic version")
    p_build.add_argument("--backend", default="onnx", help="Runtime backend")
    p_build.add_argument("--tags", nargs="*", default=[], help="Tags")
    p_build.add_argument("--description", default="", help="Model description")
    p_build.add_argument(
        "--dep", nargs="*", default=[], help="Dependencies (key=value)"
    )

    p_extract = sub.add_parser("extract", help="Extract a package to directory")
    p_extract.add_argument("package", help="Path to .aimp package")
    p_extract.add_argument("output_dir", help="Output directory")

    p_install = sub.add_parser("install", help="Install a package to models directory")
    p_install.add_argument("package", help="Path to .aimp package")
    p_install.add_argument(
        "--target", help="Target installation directory (default: store/installed)"
    )

    p_list = sub.add_parser("list", help="List available packages")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    p_remove = sub.add_parser("remove", help="Remove a package")
    p_remove.add_argument("model_id", help="Model identifier")
    p_remove.add_argument("--version", default="1.0.0", help="Version")

    p_verify = sub.add_parser("verify", help="Verify package integrity")
    p_verify.add_argument("package", help="Path to .aimp package")

    args = parser.parse_args()
    mgr = ModelPackageManager(args.store)

    if args.command == "build":
        deps = {}
        for d in args.dep:
            if "=" in d:
                k, v = d.split("=", 1)
                deps[k] = v
        path = mgr.build_package(
            model_dir=args.model_dir,
            model_id=args.model_id,
            name=args.name or args.model_id,
            version=args.version,
            backend=args.backend,
            tags=args.tags,
            description=args.description,
            dependencies=deps,
        )
        print(f"Package created: {path}")
        print(f"  Size: {path.stat().st_size / 1024 / 1024:.1f} MB")

    elif args.command == "extract":
        manifest = mgr.extract_package(args.package, args.output_dir)
        print(f"Extracted: {manifest.model_id} v{manifest.version}")
        print(f"  Files: {len(manifest.files)}")

    elif args.command == "install":
        manifest = mgr.install_package(args.package, args.target)
        print(f"Installed: {manifest.model_id} v{manifest.version}")

    elif args.command == "list":
        packages = mgr.list_packages()
        if args.json:
            json.dump(packages, sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            if not packages:
                print("No packages found.")
                return
            print(f"{'Package':30s} {'Model':20s} {'Version':12s} {'Size':10s}")
            print("-" * 72)
            for p in packages:
                pkg_name = Path(p["package_path"]).name
                size_mb = p["package_size"] / 1024 / 1024
                print(
                    f"{pkg_name:30s} {p['model_id']:20s} {p['version']:12s} "
                    f"{size_mb:.1f} MB"
                )

    elif args.command == "remove":
        ok = mgr.remove_package(args.model_id, args.version)
        if ok:
            print(f"Removed: {args.model_id} v{args.version}")
        else:
            print(f"Not found: {args.model_id} v{args.version}")
            sys.exit(1)

    elif args.command == "verify":
        ok = mgr.verify_package(args.package)
        if ok:
            print(f"Verified OK: {args.package}")
        else:
            print(f"Verification FAILED: {args.package}")
            sys.exit(1)


if __name__ == "__main__":
    main()
