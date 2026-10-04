"""Build an allowlisted, deterministic source-only ZIP without network access."""
from __future__ import annotations

import hashlib
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = 'art-upscaler-v0.1.1-source.zip'
PREFIX = 'art-upscaler-v0.1.1'
DENIED_PARTS = {
    '.git', '.aws', '.codex', '.agents', 'node_modules', '__pycache__',
    'logs', 'runtime', 'engine', 'dist', 'build', 'vendor-downloads',
}
ALLOWED_SUFFIXES = {'.py', '.js', '.html', '.md', '.txt', '.cmd', '.ijg'}
SECRET_PATTERNS = (
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(rb'AKIA[0-9A-Z]{16}'),
    re.compile(rb'(?i)(?:access_token|api_key|client_secret)\s*[=:]\s*[\"\'][A-Za-z0-9_-]{24,}'),
)


def source_files(root=ROOT):
    """Only reviewed paths; never recursively package a working directory."""
    names = (root / 'SOURCE_FILES.txt').read_text('utf-8').splitlines()
    if names != sorted(set(names)):
        raise ValueError('SOURCE_FILES.txt must be sorted and contain no duplicates')
    result = []
    for name in names:
        rel = PurePosixPath(name)
        if not name or rel.is_absolute() or '..' in rel.parts or '\\' in name:
            raise ValueError(f'Unsafe source path: {name}')
        if any(part in DENIED_PARTS for part in rel.parts):
            raise ValueError(f'Excluded directory in source path: {name}')
        path = root.joinpath(*rel.parts)
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError(f'Symbolic link is not allowed: {name}')
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Missing or escaped source path: {name}')
        if path.suffix not in ALLOWED_SUFFIXES and name not in {'.gitignore', '.gitattributes', 'LICENSE'}:
            raise ValueError(f'Unexpected file type: {name}')
        data = path.read_bytes()
        data.decode('utf-8')
        if b'\x00' in data:
            raise ValueError(f'Binary content is not allowed: {name}')
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError(f'Possible credential in source file: {name}')
        result.append((name, data))
    return result


def build(root=ROOT):
    files = source_files(root)
    destination = root / 'dist'
    destination.mkdir(exist_ok=True)
    output = destination / ARCHIVE
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files:
            info = zipfile.ZipInfo(f'{PREFIX}/{name}', date_time=(2026, 10, 4, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP validation failed')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (destination / (ARCHIVE + '.sha256')).write_text(f'{digest}  {ARCHIVE}\n', encoding='utf-8')
    print(f'{output.name}: {len(files)} files, {output.stat().st_size} bytes, SHA-256 {digest}')
    return output


if __name__ == '__main__':
    build()
