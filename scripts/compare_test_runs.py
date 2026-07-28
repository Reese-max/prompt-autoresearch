#!/usr/bin/env python3
"""scripts/compare_test_runs.py - 比對兩次測試執行的結果、覆蓋率與產物雜湊

用法:
  python3 scripts/compare_test_runs.py <dir_a> <dir_b> [--artifact-globs GLOB ...]

比對項目:
  1. 覆蓋率 (coverage.xml) — line/branch rate、各 class 差異
  2. 產物雜湊 (SHA-256) — 指定檔案的內容差異

存在任一差異時輸出 JSON 差異報告 (stdout) 並 exit(1)。
完全相同時 exit(0) 並印出 "identical"。
"""

import glob as glob_module
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET


def parse_coverage(xml_path):
    root = ET.parse(xml_path).getroot()
    summary = {
        "lines_valid": int(root.get("lines-valid", 0)),
        "lines_covered": int(root.get("lines-covered", 0)),
        "line_rate": float(root.get("line-rate", 0)),
        "branches_valid": int(root.get("branches-valid", 0)),
        "branches_covered": int(root.get("branches-covered", 0)),
        "branch_rate": float(root.get("branch-rate", 0)),
        "timestamp": int(root.get("timestamp", 0)),
    }
    packages = {}
    for pkg in root.findall(".//package"):
        pkg_name = pkg.get("name", "")
        classes = []
        for cls in pkg.findall("classes/class"):
            classes.append({
                "name": cls.get("filename", cls.get("name", "")),
                "line_rate": float(cls.get("line-rate", 0)),
                "branch_rate": float(cls.get("branch-rate", 0)),
            })
        packages[pkg_name] = {
            "line_rate": float(pkg.get("line-rate", 0)),
            "branch_rate": float(pkg.get("branch-rate", 0)),
            "classes": classes,
        }
    return {"summary": summary, "packages": packages}


def compute_file_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_artifact_hashes(run_dir, globs):
    hashes = {}
    if not globs:
        return hashes
    for pattern in globs:
        matched = glob_module.glob(os.path.join(run_dir, pattern), recursive=True)
        for fp in sorted(matched):
            rel = os.path.relpath(fp, run_dir)
            hashes[rel] = compute_file_hash(fp)
    return hashes


def _class_key(c):
    return c["name"]


def compare_test_runs(dir_a, dir_b, artifact_globs=None):
    cov_a_path = os.path.join(dir_a, "coverage.xml")
    cov_b_path = os.path.join(dir_b, "coverage.xml")

    has_diff = False
    sections = {}

    cov_a_exists = os.path.exists(cov_a_path)
    cov_b_exists = os.path.exists(cov_b_path)

    if not cov_a_exists and not cov_b_exists:
        sections["coverage"] = {"error": "coverage.xml not found in either directory", "identical": True}
    elif not cov_a_exists:
        sections["coverage"] = {"error": f"coverage.xml not found in {dir_a}", "identical": False}
        has_diff = True
    elif not cov_b_exists:
        sections["coverage"] = {"error": f"coverage.xml not found in {dir_b}", "identical": False}
        has_diff = True
    else:
        cov_a = parse_coverage(cov_a_path)
        cov_b = parse_coverage(cov_b_path)
        coverage_diffs = {}
        identical = True

        for key in ("lines_valid", "lines_covered", "line_rate", "branches_valid", "branches_covered", "branch_rate"):
            va = cov_a["summary"][key]
            vb = cov_b["summary"][key]
            if va != vb:
                coverage_diffs[key] = {"a": va, "b": vb, "diff": vb - va}
                identical = False

        pkg_diffs = {}
        all_pkgs = set(cov_a["packages"]) | set(cov_b["packages"])
        for pkg in sorted(all_pkgs):
            pa = cov_a["packages"].get(pkg, {"line_rate": 0, "branch_rate": 0, "classes": []})
            pb = cov_b["packages"].get(pkg, {"line_rate": 0, "branch_rate": 0, "classes": []})
            pkg_line_diff = round(pb["line_rate"] - pa["line_rate"], 6)
            pkg_branch_diff = round(pb["branch_rate"] - pa["branch_rate"], 6)
            if pkg_line_diff != 0 or pkg_branch_diff != 0:
                pkg_diffs[pkg] = {
                    "line_rate": {"a": pa["line_rate"], "b": pb["line_rate"]},
                    "branch_rate": {"a": pa["branch_rate"], "b": pb["branch_rate"]},
                }
                identical = False

            class_diffs = []
            classes_a = {_class_key(c): c for c in pa.get("classes", [])}
            classes_b = {_class_key(c): c for c in pb.get("classes", [])}
            all_classes = set(classes_a) | set(classes_b)
            for cls in sorted(all_classes):
                ca = classes_a.get(cls, {"line_rate": 0, "branch_rate": 0})
                cb = classes_b.get(cls, {"line_rate": 0, "branch_rate": 0})
                if ca["line_rate"] != cb["line_rate"] or ca["branch_rate"] != cb["branch_rate"]:
                    class_diffs.append({
                        "name": cls,
                        "line_rate": {"a": ca["line_rate"], "b": cb["line_rate"]},
                        "branch_rate": {"a": ca["branch_rate"], "b": cb["branch_rate"]},
                    })
                    identical = False

        entry = {"identical": identical}
        if coverage_diffs:
            entry["summary_diffs"] = coverage_diffs
        if pkg_diffs:
            entry["package_diffs"] = pkg_diffs
        if identical:
            entry["message"] = "coverage identical"
        else:
            has_diff = True

        sections["coverage"] = entry

    artifact_hashes_a = collect_artifact_hashes(dir_a, artifact_globs or [])
    artifact_hashes_b = collect_artifact_hashes(dir_b, artifact_globs or [])

    hash_diffs = {}
    all_paths = set(artifact_hashes_a) | set(artifact_hashes_b)
    for p in sorted(all_paths):
        ha = artifact_hashes_a.get(p)
        hb = artifact_hashes_b.get(p)
        if ha != hb:
            hash_diffs[p] = {"a": ha, "b": hb}
            has_diff = True

    sections["artifacts"] = {
        "identical": len(hash_diffs) == 0,
        "diffs": hash_diffs,
    }

    report = {
        "dir_a": os.path.abspath(dir_a),
        "dir_b": os.path.abspath(dir_b),
        "has_differences": has_diff,
        "sections": sections,
    }
    return report


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    artifact_flag = "--artifact-globs"
    globs = []
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == artifact_flag:
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                globs.append(argv[i])
                i += 1
        else:
            rest.append(argv[i])
            i += 1

    if len(rest) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1

    dir_a, dir_b = rest[0], rest[1]

    if not os.path.isdir(dir_a):
        print(f"error: not a directory: {dir_a}", file=sys.stderr)
        return 1
    if not os.path.isdir(dir_b):
        print(f"error: not a directory: {dir_b}", file=sys.stderr)
        return 1

    report = compare_test_runs(dir_a, dir_b, artifact_globs=globs)

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if report["has_differences"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
