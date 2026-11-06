"""Trusted operator helper. Not a sandbox and never a model-generated script."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

MAX_BYTES = 20_000_000

def _name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('Invalid run name')
    return value

def _safe(name):
    p = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or p.is_absolute()
            or any(x in ('', '.', '..') for x in name.split('/'))):
        raise ValueError('Unsafe archive path: ' + name)
    for part in p.parts:
        if part.endswith((' ', '.')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
            raise ValueError('Nonportable archive path')
    return p

def _digest(data):
    return hashlib.sha256(data).hexdigest()

def _plain(path):
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Links are not allowed: ' + str(path))

def prepare(workspace, archive, sha256, run_name):
    base = Path(workspace).resolve(strict=True)
    run = base / _name(run_name)
    if run.exists() or run.is_symlink():
        raise FileExistsError(run)
    if Path(archive).name != archive:
        raise ValueError('Archive must be a direct workspace file')
    src = base / archive
    _plain(src)
    if src.stat().st_size > MAX_BYTES:
        raise ValueError('Archive too large')
    if _digest(src.read_bytes()) != sha256:
        raise ValueError('Archive checksum mismatch')
    payload = {}
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        if not infos or len(infos) > 100 or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError('Archive limits exceeded')
        seen = set()
        for info in infos:
            _safe(info.orig_filename)
            _safe(info.filename)
            key = info.filename.casefold()
            mode = info.external_attr >> 16
            if key in seen or info.is_dir() or stat.S_ISLNK(mode):
                raise ValueError('Duplicate, directory or linked member')
            seen.add(key)
            payload[info.filename] = z.read(info)
    # All validation precedes creation. Partial failures are left for inspection.
    run.mkdir(exist_ok=False)
    for name, data in payload.items():
        dst = run / 'inputs' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open('xb') as f:
            f.write(data)
    manifest = {'run_name':run_name,'archive_sha256':sha256,
                'inputs':{name:_digest(data) for name,data in payload.items()}}
    with (run/'bundle_manifest.json').open('x',encoding='utf-8') as f:
        json.dump(manifest,f,ensure_ascii=False,indent=2)
    return run

def pack(workspace, run_name):
    base = Path(workspace).resolve(strict=True)
    run = base / _name(run_name)
    _plain(run)
    manifest_path = run/'bundle_manifest.json'
    _plain(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['run_name'] != run_name:
        raise ValueError('Manifest belongs to another run')
    files = {'bundle_manifest.json':manifest_path}
    for name,digest in manifest['inputs'].items():
        _safe(name)
        src=run/'inputs'/name
        for p in (src,*src.parents):
            if p == base: break
            _plain(p)
        if _digest(src.read_bytes()) != digest:
            raise ValueError('Input changed: '+name)
        files['inputs/'+name]=src
    # Explicit allowlist, never recursively scan outputs or other tasks.
    for name in ('solve.py','output/result.json','output/run_receipt.json'):
        src=run/name
        _plain(src); _plain(src.parent)
        if not src.is_file(): raise ValueError('Missing output: '+name)
        files[name]=src
    optional=run/'output/model_transcribed_response.json'
    if optional.exists():
        _plain(optional)
        files['output/model_transcribed_response.json']=optional
    if sum(p.stat().st_size for p in files.values()) > MAX_BYTES:
        raise ValueError('Outputs too large')
    out=base/(run_name+'-results.zip')
    with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
        for name,src in sorted(files.items()):
            z.write(src,run_name+'/'+name)
    return out

if __name__ == '__main__':
    p=argparse.ArgumentParser(description='Fixed preparation and packaging; trusted operator only')
    p.add_argument('action',choices=['prepare','pack'])
    p.add_argument('--workspace',required=True)
    p.add_argument('--run',required=True)
    p.add_argument('--archive')
    p.add_argument('--sha256')
    a=p.parse_args()
    if a.action=='prepare':
        if not a.archive or not a.sha256: p.error('prepare requires --archive and --sha256')
        print(prepare(a.workspace,a.archive,a.sha256,a.run))
    else: print(pack(a.workspace,a.run))
