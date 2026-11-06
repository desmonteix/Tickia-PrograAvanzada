"""Check every pinned runtime version against PyPI's release advisory feed.

Fallback evidence when pip-audit installation is unavailable. This does not
resolve extra packages beyond requirements.txt or claim absence of unknown CVEs.
Official protocol: https://docs.pypi.org/api/json/#get-a-release
"""
import concurrent.futures
import datetime
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).parents[1]


def inspect_release(item):
    name, version = item
    result = {"name": name, "version": version, "vulnerabilities": []}
    try:
        url = "https://pypi.org/pypi/" + name + "/" + version + "/json"
        with urllib.request.urlopen(url, timeout=12) as response:
            data = json.load(response)
        result["vulnerabilities"] = [{
            "id": entry.get("id"), "aliases": entry.get("aliases", []),
            "fixed_in": entry.get("fixed_in", []), "link": entry.get("link"),
        } for entry in data.get("vulnerabilities", []) if not entry.get("withdrawn")]
    except Exception as error:
        result["error"] = type(error).__name__
    return result


def advisory_groups(packages):
    parents = {}
    def find(value):
        parents.setdefault(value, value)
        if parents[value] != value:
            parents[value] = find(parents[value])
        return parents[value]
    for package in packages:
        for item in package.get("vulnerabilities", []):
            ids = [item["id"]] + item.get("aliases", [])
            find(ids[0])
            for alias in ids[1:]:
                parents[find(alias)] = find(ids[0])
    groups = {}
    for value in list(parents):
        group = groups.setdefault(find(value), {"ids": set(), "packages": set()})
        group["ids"].add(value)
    for package in packages:
        for item in package.get("vulnerabilities", []):
            groups[find(item["id"])]["packages"].add(package["name"])
    return [{
        "id": sorted(group["ids"], key=lambda item: (not item.startswith("CVE-"), item))[0],
        "aliases": sorted(group["ids"]), "packages": sorted(group["packages"]),
    } for group in groups.values()]


def main():
    requirements = []
    raw = (ROOT / "requirements.txt").read_bytes()
    source = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+\-]+)", line)
        if not match:
            raise RuntimeError("Only exact pinned requirements can be audited by this fallback.")
        requirements.append(match.groups())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(inspect_release, requirements))
    report = {
        "source": "PyPI JSON release-specific vulnerability feed",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "checked": len(results), "errors": sum("error" in item for item in results),
        "vulnerabilities": sum(len(item["vulnerabilities"]) for item in results),
        "packages": results,
    }
    report["advisory_groups"] = advisory_groups(results)
    report["unique_vulnerabilities"] = len(report["advisory_groups"])
    (ROOT / "dependency-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("source", "checked", "errors", "vulnerabilities", "unique_vulnerabilities")}))
    for item in results:
        if item.get("error") or item["vulnerabilities"]:
            print(json.dumps(item))
    return 2 if report["errors"] else int(report["vulnerabilities"] > 0)


if __name__ == "__main__":
    sys.exit(main())
