#!/usr/bin/env python3
"""Prepare a self-contained, same-origin static website release using stdlib only."""

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "deploy" / "dist"
EXAM_PAGES = (
    "index.html", "login.html", "guide.html", "auto-exam.html",
    "marketing-exam.html", "english-exam.html",
)
EXAM_FILES = EXAM_PAGES + (
    "access.css", "access.js", "brand.css", "brand.js", "site.js",
    "exam-brand.css", "english-exam.css", "english-exam.js",
    "english-exam-core.js", "whitelist.js", "data/english-bank.js",
)
RETURN_STYLE = """
<style id="ningyue-website-return-style">
.ny-website-return{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px max(18px,calc((100vw - 1280px)/2));background:#075b9d;color:#e7f2fc;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif}
.ny-website-return a{color:#fff;text-decoration:none;font-weight:600;padding:3px 0}
.ny-website-return a:hover{text-decoration:underline}
.ny-website-return a:focus-visible{outline:3px solid #f4bc68;outline-offset:4px}
@media print{.ny-website-return{display:none!important}}
</style>
"""
RETURN_LINK = '<div class="ny-website-return"><a href="../">返回宁跃官网</a><span>宁跃教育 · 在线考试</span></div>'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_assignment(path, name):
    source = path.read_text(encoding="utf-8")
    match = re.search(r"window\." + re.escape(name) + r"\s*=\s*", source)
    if not match:
        raise ValueError(f"Missing {name} assignment in {path.name}")
    value, end = json.JSONDecoder().raw_decode(source[match.end():])
    if source[match.end() + end:].strip() not in ("", ";"):
        raise ValueError(f"Unexpected executable suffix in {path.name}")
    return value


def validate_whitelist(path):
    value = read_assignment(path, "EXAM_WHITELISTS")
    if (value.get("version"), value.get("credential"), value.get("algorithm"), value.get("iterations")) != (3, "name-phone-last6", "PBKDF2-SHA-256", 600000):
        raise ValueError("Expected current hashed whitelist format; refusing to publish another format")
    allowed = {"version", "credential", "algorithm", "iterations", "sessionHours", "auto", "marketing", "english"}
    if set(value) - allowed:
        raise ValueError("Unexpected whitelist fields; review before publishing")
    count = 0
    salts = set()
    for subject in ("auto", "marketing", "english"):
        rows = value.get(subject)
        if not isinstance(rows, list):
            raise ValueError(f"Missing whitelist for {subject}")
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"salt", "hash", "enabled"}:
                raise ValueError("Whitelist contains unexpected fields; no plaintext identity is permitted")
            if not re.fullmatch(r"[0-9a-f]{32}", row.get("salt", "")) or not re.fullmatch(r"[0-9a-f]{64}", row.get("hash", "")):
                raise ValueError("Invalid whitelist hash or salt")
            if "enabled" in row and not isinstance(row["enabled"], bool):
                raise ValueError("Invalid whitelist enabled field")
            if row["salt"] in salts:
                raise ValueError("Duplicate whitelist salt")
            salts.add(row["salt"])
            count += 1
    return count


class HTMLResources(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.scripts = []
        self._script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attribute in ("src", "href", "poster"):
            if attrs.get(attribute):
                self.references.append(attrs[attribute])
        if tag == "script":
            self._script = [attrs, ""]

    def handle_data(self, data):
        if self._script is not None:
            self._script[1] += data

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append(self._script)
            self._script = None


def verify_reference(site, document, reference):
    target = urlsplit(reference)
    if target.scheme or target.netloc or not target.path:
        return
    path = (site / unquote(target.path).lstrip("/")) if target.path.startswith("/") else (document.parent / unquote(target.path))
    path = path.resolve()
    if site.resolve() not in (path, *path.parents):
        raise ValueError(f"Resource escapes website root: {reference}")
    if path.is_dir():
        path = path / "index.html"
    if not path.is_file():
        raise ValueError(f"Missing resource from {document.relative_to(site)}: {reference}")


def validate_site(site):
    parsed = []
    for path in sorted(site.rglob("*.html")):
        document = HTMLResources()
        document.feed(path.read_text(encoding="utf-8"))
        for reference in document.references:
            verify_reference(site, path, reference)
        for attrs, source in document.scripts:
            if attrs.get("type") == "application/json":
                json.loads(source)
            elif not attrs.get("src") and source.strip():
                parsed.append({"filename": str(path.relative_to(site)), "source": source})
    for path in sorted(site.rglob("*.css")):
        for reference in re.findall(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", path.read_text(encoding="utf-8")):
            verify_reference(site, path, reference.strip())
    bank = read_assignment(site / "exam/data/english-bank.js", "ENGLISH_BANK")
    images = set()

    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get("src"), str):
                images.add(value["src"])
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(bank)
    for reference in images:
        verify_reference(site, site / "exam/english-exam.html", reference)
    for path in sorted(site.rglob("*.js")):
        parsed.append({"filename": str(path.relative_to(site)), "source": path.read_text(encoding="utf-8")})
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Install Node.js to run the release JavaScript syntax checks; no npm packages are needed")
    check = "const vm=require('vm'),fs=require('fs');const items=JSON.parse(fs.readFileSync(0,'utf8'));for(const item of items)new vm.Script(item.source,{filename:item.filename});console.log(items.length);"
    result = subprocess.run([node, "-e", check], input=json.dumps(parsed), text=True, capture_output=True, check=True)
    return {"html_files": len(list(site.rglob("*.html"))), "javascript_blocks": int(result.stdout.strip()), "english_images": len(images), "english_questions": bank["totalQuestions"]}


def prepare(exam_source):
    exam_source = exam_source.resolve()
    required = [REPO / "home.html"] + [exam_source / name for name in EXAM_FILES]
    for path in required:
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"Missing or symbolic-link source file: {path}")
    validate_whitelist(exam_source / "whitelist.js")
    DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=DIST) as temporary:
        site = Path(temporary) / "site"
        site.mkdir()
        home = (REPO / "home.html").read_text(encoding="utf-8")
        home, replacements = re.subn(r'var EXAM_PRACTICE_URL = "[^"]+";', 'var EXAM_PRACTICE_URL = "exam/index.html#subjects";', home)
        if replacements != 1:
            raise ValueError("Expected exactly one EXAM_PRACTICE_URL in home.html")
        for name in ("index.html", "home.html"):
            (site / name).write_text(home, encoding="utf-8")
        for name in ("privacy.html", "boxIndex.html", "app-icon.png"):
            if (REPO / name).is_file():
                shutil.copyfile(REPO / name, site / name)
        for name in EXAM_FILES:
            target = site / "exam" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(exam_source / name, target)
        for source in sorted((exam_source / "assets").rglob("*")):
            if source.is_symlink():
                raise ValueError("Symbolic links are not allowed in exam assets")
            if source.is_file():
                if source.suffix.lower() not in {".webp", ".png", ".svg", ".jpg", ".jpeg", ".gif", ".woff", ".woff2"}:
                    raise ValueError(f"Unexpected exam asset type: {source.name}")
                target = site / "exam" / source.relative_to(exam_source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for name in EXAM_PAGES:
            page = site / "exam" / name
            html = page.read_text(encoding="utf-8")
            html, head_count = re.subn(r"</head>", RETURN_STYLE + "</head>", html, count=1, flags=re.I)
            html, body_count = re.subn(r"(<body\b[^>]*>)", lambda match: match[1] + RETURN_LINK, html, count=1, flags=re.I)
            if head_count != 1 or body_count != 1:
                raise ValueError(f"Expected one head and body in {name}")
            page.write_text(html, encoding="utf-8")
        if digest(site / "exam/whitelist.js") != digest(exam_source / "whitelist.js"):
            raise ValueError("Whitelist changed unexpectedly")
        checks = validate_site(site)
        files = sorted(path for path in site.rglob("*") if path.is_file())
        manifest = "".join(f"{digest(path)}  {path.relative_to(site).as_posix()}\n" for path in files)
        archive_path = Path(temporary) / "ningyue-site.tar.gz"
        with archive_path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in files:
                    info = archive.gettarinfo(str(path), arcname=path.relative_to(site).as_posix())
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    info.mode = 0o644
                    with path.open("rb") as source:
                        archive.addfile(info, source)
        current_site = DIST / "site"
        if current_site.exists():
            if not (DIST / "release.json").is_file():
                raise ValueError("Existing dist/site has no release marker; move it before rebuilding")
            shutil.rmtree(current_site)
        shutil.move(str(site), current_site)
        shutil.move(str(archive_path), DIST / archive_path.name)
        (DIST / "SITE-SHA256SUMS").write_text(manifest, encoding="utf-8")
        archive_hash = digest(DIST / archive_path.name)
        (DIST / "SHA256SUMS").write_text(f"{archive_hash}  {archive_path.name}\n", encoding="utf-8")
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
        metadata = {"built_at_utc": datetime.now(timezone.utc).isoformat(), "website_source_commit": revision,
                    "files": len(files), "archive_bytes": (DIST / archive_path.name).stat().st_size,
                    "archive_sha256": archive_hash, "checks": checks,
                    "entrypoints": {"website": "/", "website_alias": "/home.html", "exam": "/exam/index.html#subjects"}}
        (DIST / "release.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-source", type=Path, default=REPO / "local-backups" / "exam-practice")
    args = parser.parse_args()
    prepare(args.exam_source)
