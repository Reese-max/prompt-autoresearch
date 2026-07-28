# -*- coding: utf-8 -*-
"""tests/test_compare_test_runs.py — scripts/compare_test_runs.py 單元測試"""
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET

import pytest

import scripts.compare_test_runs as ctr


SAMPLE_COVERAGE_XML = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="1000" lines-valid="100" lines-covered="80" line-rate="0.8" branches-valid="40" branches-covered="30" branch-rate="0.75" complexity="0">
  <sources>
    <source>/tmp/a</source>
  </sources>
  <packages>
    <package name="scripts" line-rate="0.8" branch-rate="0.75" complexity="0">
      <classes>
        <class name="foo.py" filename="foo.py" complexity="0" line-rate="0.9" branch-rate="0.8">
          <methods/><lines/>
        </class>
        <class name="bar.py" filename="bar.py" complexity="0" line-rate="0.7" branch-rate="0.5">
          <methods/><lines/>
        </class>
      </classes>
    </package>
    <package name="lib" line-rate="0.85" branch-rate="0.8" complexity="0">
      <classes>
        <class name="util.py" filename="util.py" complexity="0" line-rate="0.85" branch-rate="0.8">
          <methods/><lines/>
        </class>
      </classes>
    </package>
  </packages>
</coverage>"""


SAMPLE_COVERAGE_XML_V2 = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="2000" lines-valid="100" lines-covered="90" line-rate="0.9" branches-valid="40" branches-covered="35" branch-rate="0.875" complexity="0">
  <sources>
    <source>/tmp/b</source>
  </sources>
  <packages>
    <package name="scripts" line-rate="0.9" branch-rate="0.875" complexity="0">
      <classes>
        <class name="foo.py" filename="foo.py" complexity="0" line-rate="0.95" branch-rate="0.9">
          <methods/><lines/>
        </class>
        <class name="bar.py" filename="bar.py" complexity="0" line-rate="0.85" branch-rate="0.75">
          <methods/><lines/>
        </class>
      </classes>
    </package>
    <package name="lib" line-rate="0.85" branch-rate="0.8" complexity="0">
      <classes>
        <class name="util.py" filename="util.py" complexity="0" line-rate="0.85" branch-rate="0.8">
          <methods/><lines/>
        </class>
      </classes>
    </package>
  </packages>
</coverage>"""


# ---------- parse_coverage ----------

def test_parse_coverage_returns_summary_and_packages(tmp_path):
    p = tmp_path / "coverage.xml"
    p.write_text(SAMPLE_COVERAGE_XML, encoding="utf-8")
    result = ctr.parse_coverage(str(p))
    assert result["summary"]["lines_valid"] == 100
    assert result["summary"]["lines_covered"] == 80
    assert result["summary"]["line_rate"] == 0.8
    assert result["summary"]["branches_valid"] == 40
    assert result["summary"]["branches_covered"] == 30
    assert result["summary"]["branch_rate"] == 0.75
    assert result["summary"]["timestamp"] == 1000
    assert set(result["packages"]) == {"scripts", "lib"}
    assert len(result["packages"]["scripts"]["classes"]) == 2
    assert len(result["packages"]["lib"]["classes"]) == 1


def test_parse_coverage_empty_packages(tmp_path):
    xml = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="0" lines-valid="0" lines-covered="0" line-rate="1" branches-valid="0" branches-covered="0" branch-rate="1" complexity="0">
  <packages/>
</coverage>"""
    p = tmp_path / "coverage.xml"
    p.write_text(xml, encoding="utf-8")
    result = ctr.parse_coverage(str(p))
    assert result["summary"]["lines_valid"] == 0
    assert result["packages"] == {}


# ---------- compute_file_hash ----------

def test_compute_file_hash_consistency(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world")
    h1 = ctr.compute_file_hash(str(f))
    h2 = ctr.compute_file_hash(str(f))
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert h1 == h2 == expected


def test_compute_file_hash_differs_on_change(tmp_path):
    fa = tmp_path / "a.txt"
    fb = tmp_path / "b.txt"
    fa.write_text("same")
    fb.write_text("same")
    assert ctr.compute_file_hash(str(fa)) == ctr.compute_file_hash(str(fb))
    fb.write_text("different")
    assert ctr.compute_file_hash(str(fa)) != ctr.compute_file_hash(str(fb))


# ---------- collect_artifact_hashes ----------

def test_collect_artifact_hashes_no_globs(tmp_path):
    assert ctr.collect_artifact_hashes(str(tmp_path), []) == {}


def test_collect_artifact_hashes_by_glob(tmp_path):
    (tmp_path / "out.json").write_text("data")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "extra.log").write_text("log")
    result = ctr.collect_artifact_hashes(str(tmp_path), ["*.json", "sub/*.log"])
    assert "out.json" in result
    assert os.path.join("sub", "extra.log") in result
    assert len(result) == 2


# ---------- compare_test_runs ----------

def write_coverage(dirpath, xml_content):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "coverage.xml").write_text(xml_content, encoding="utf-8")


def test_compare_identical_coverage(tmp_path):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML)
    report = ctr.compare_test_runs(str(tmp_path / "a"), str(tmp_path / "b"))
    assert report["has_differences"] is False
    assert report["sections"]["coverage"]["identical"] is True


def test_compare_different_coverage(tmp_path):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML_V2)
    report = ctr.compare_test_runs(str(tmp_path / "a"), str(tmp_path / "b"))
    assert report["has_differences"] is True
    cov = report["sections"]["coverage"]
    assert cov["identical"] is False
    assert "summary_diffs" in cov
    assert cov["summary_diffs"]["line_rate"]["diff"] == pytest.approx(0.1)


def test_compare_different_package_coverage(tmp_path):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML_V2)
    report = ctr.compare_test_runs(str(tmp_path / "a"), str(tmp_path / "b"))
    pkg_diffs = report["sections"]["coverage"]["package_diffs"]
    assert "scripts" in pkg_diffs
    assert pkg_diffs["scripts"]["line_rate"]["a"] == 0.8
    assert pkg_diffs["scripts"]["line_rate"]["b"] == 0.9


def test_compare_different_class_coverage(tmp_path):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML_V2)
    report = ctr.compare_test_runs(str(tmp_path / "a"), str(tmp_path / "b"))
    class_diffs = [
        d for d in report["sections"]["coverage"].get("class_diffs", [])
    ] if "class_diffs" in report["sections"]["coverage"] else []
    cov = report["sections"]["coverage"]
    package_diffs = cov.get("package_diffs", {})
    foo_changed = any(
        c["name"] == "foo.py"
        for pkg in package_diffs.values()
        if "class_diffs" in pkg
        for c in pkg["class_diffs"]
    )
    assert not cov["identical"]


def test_compare_class_diffs_present_in_package_diffs(tmp_path):
    """class_diffs 經計算後應寫入 package_diffs 輸出，而非遺失。
    目前 class_diffs 在 compare_test_runs 中被計算但從未附加到 pkg_diffs[pkg]，
    導致比對結果不一致：coverage 判定為不一致（identical=False），
    但 class 層級差異無法從報告中觀察到——可重複的不一致案例。"""
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML_V2)
    report = ctr.compare_test_runs(str(tmp_path / "a"), str(tmp_path / "b"))
    cov = report["sections"]["coverage"]
    assert cov["identical"] is False
    pkg_diffs = cov.get("package_diffs", {})
    assert "scripts" in pkg_diffs
    scripts_pkg = pkg_diffs["scripts"]
    assert "class_diffs" in scripts_pkg, (
        "class_diffs 應出現在 package_diffs[\"scripts\"] 中，"
        "但目前被計算後未附加——觀察到不一致行為"
    )
    names = {c["name"] for c in scripts_pkg["class_diffs"]}
    assert "foo.py" in names
    assert "bar.py" in names


def test_compare_class_diffs_only_class_level(tmp_path):
    """即使 package 層級 rate 相同，class 層級差異仍應在輸出中可見。"""
    same_pkg_xml = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="3000" lines-valid="100" lines-covered="85" line-rate="0.85" branches-valid="40" branches-covered="32" branch-rate="0.8" complexity="0">
  <packages>
    <package name="lib" line-rate="0.85" branch-rate="0.8" complexity="0">
      <classes>
        <class name="a.py" filename="a.py" complexity="0" line-rate="0.9" branch-rate="0.8">
          <methods/><lines/>
        </class>
        <class name="b.py" filename="b.py" complexity="0" line-rate="0.8" branch-rate="0.8">
          <methods/><lines/>
        </class>
      </classes>
    </package>
  </packages>
</coverage>"""
    same_pkg_xml_v2 = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="3001" lines-valid="100" lines-covered="85" line-rate="0.85" branches-valid="40" branches-covered="32" branch-rate="0.8" complexity="0">
  <packages>
    <package name="lib" line-rate="0.85" branch-rate="0.8" complexity="0">
      <classes>
        <class name="a.py" filename="a.py" complexity="0" line-rate="0.7" branch-rate="0.8">
          <methods/><lines/>
        </class>
        <class name="b.py" filename="b.py" complexity="0" line-rate="1.0" branch-rate="0.8">
          <methods/><lines/>
        </class>
      </classes>
    </package>
  </packages>
</coverage>"""
    write_coverage(tmp_path / "a", same_pkg_xml)
    write_coverage(tmp_path / "b", same_pkg_xml_v2)
    report = ctr.compare_test_runs(str(tmp_path / "a"), str(tmp_path / "b"))
    cov = report["sections"]["coverage"]
    pkg_diffs = cov.get("package_diffs", {})
    assert "lib" in pkg_diffs
    lib_pkg = pkg_diffs["lib"]
    assert "class_diffs" in lib_pkg, (
        "package rate 相同但 class rate 不同時，class_diffs 應仍出現在輸出中"
    )
    names = {c["name"] for c in lib_pkg["class_diffs"]}
    assert "a.py" in names
    assert "b.py" in names


def test_compare_missing_coverage_in_one(tmp_path):
    tmp_path_a = tmp_path / "a"
    tmp_path_b = tmp_path / "b"
    tmp_path_a.mkdir()
    tmp_path_b.mkdir()
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    report = ctr.compare_test_runs(str(tmp_path_a), str(tmp_path_b))
    assert report["has_differences"] is True
    assert "error" in report["sections"]["coverage"]


def test_compare_missing_coverage_in_both(tmp_path):
    tmp_path_a = tmp_path / "a"
    tmp_path_b = tmp_path / "b"
    tmp_path_a.mkdir()
    tmp_path_b.mkdir()
    report = ctr.compare_test_runs(str(tmp_path_a), str(tmp_path_b))
    assert report["has_differences"] is False
    assert "error" in report["sections"]["coverage"]


def test_compare_artifact_hashes_identical(tmp_path):
    for d in ("a", "b"):
        p = tmp_path / d
        p.mkdir(parents=True)
        (p / "out.json").write_text("same data")
    report = ctr.compare_test_runs(
        str(tmp_path / "a"), str(tmp_path / "b"),
        artifact_globs=["*.json"],
    )
    assert report["sections"]["artifacts"]["identical"] is True


def test_compare_artifact_hashes_different(tmp_path):
    for d in ("a", "b"):
        p = tmp_path / d
        p.mkdir(parents=True)
        (p / "out.json").write_text("different" if d == "b" else "same")
    report = ctr.compare_test_runs(
        str(tmp_path / "a"), str(tmp_path / "b"),
        artifact_globs=["*.json"],
    )
    assert report["sections"]["artifacts"]["identical"] is False
    assert "out.json" in report["sections"]["artifacts"]["diffs"]


def test_compare_full_diff_report(tmp_path):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML_V2)
    (tmp_path / "a" / "report.txt").write_text("aaa")
    (tmp_path / "b" / "report.txt").write_text("bbb")
    report = ctr.compare_test_runs(
        str(tmp_path / "a"), str(tmp_path / "b"),
        artifact_globs=["report.txt"],
    )
    assert report["has_differences"] is True
    assert report["dir_a"] == os.path.abspath(str(tmp_path / "a"))
    assert report["dir_b"] == os.path.abspath(str(tmp_path / "b"))


# ---------- main() CLI ----------

def test_main_help(capsys):
    assert ctr.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "compare_test_runs" in out


def test_main_help_short(capsys):
    assert ctr.main(["-h"]) == 0


def test_main_no_args(capsys):
    assert ctr.main([]) == 0


def test_main_insufficient_args(capsys):
    rc = ctr.main(["/tmp/only"])
    assert rc == 1


def test_main_not_a_directory(tmp_path, capsys):
    rc = ctr.main([str(tmp_path / "nonexistent"), str(tmp_path)])
    assert rc == 1
    assert "not a directory" in capsys.readouterr().err


def test_main_identical_runs(tmp_path, capsys):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML)
    rc = ctr.main([str(tmp_path / "a"), str(tmp_path / "b")])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["has_differences"] is False
    assert rc == 0


def test_main_different_runs(tmp_path, capsys):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML_V2)
    rc = ctr.main([str(tmp_path / "a"), str(tmp_path / "b")])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["has_differences"] is True
    assert rc == 1


def test_main_with_artifact_globs(tmp_path, capsys):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML)
    (tmp_path / "a" / "out.txt").write_text("hello")
    (tmp_path / "b" / "out.txt").write_text("world")
    rc = ctr.main([
        str(tmp_path / "a"), str(tmp_path / "b"),
        "--artifact-globs", "*.txt",
    ])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["has_differences"] is True
    assert rc == 1
    assert "out.txt" in report["sections"]["artifacts"]["diffs"]


def test_main_with_multiple_artifact_globs(tmp_path, capsys):
    write_coverage(tmp_path / "a", SAMPLE_COVERAGE_XML)
    write_coverage(tmp_path / "b", SAMPLE_COVERAGE_XML)
    (tmp_path / "a" / "a.json").write_text("x")
    (tmp_path / "b" / "a.json").write_text("x")
    (tmp_path / "a" / "b.log").write_text("y")
    (tmp_path / "b" / "b.log").write_text("z")
    rc = ctr.main([
        str(tmp_path / "a"), str(tmp_path / "b"),
        "--artifact-globs", "*.json", "*.log",
    ])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["has_differences"] is True
    assert "b.log" in report["sections"]["artifacts"]["diffs"]
    assert "a.json" not in report["sections"]["artifacts"]["diffs"]
    assert rc == 1
