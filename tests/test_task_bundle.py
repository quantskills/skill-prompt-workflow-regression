import hashlib
import importlib.util
from pathlib import Path
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    path = ROOT / 'scripts' / (name + '.py')
    assert path.exists(), 'fixed helper is missing'
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def bundle(tmp_path, names=None):
    path = tmp_path / 'input.zip'
    with zipfile.ZipFile(path, 'w') as z:
        for name in names or ['TASK.md', 'data/events.csv']:
            info = zipfile.ZipInfo('fixture')
            info.filename = name  # Preserve deliberately invalid Windows separators.
            z.writestr(info, 'fixture')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()

def test_prepare_pack_ignore_cwd_and_old_tasks(tmp_path, monkeypatch):
    m = module('task_bundle')
    z, digest = bundle(tmp_path)
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    run = m.prepare(tmp_path, z.name, digest, 'trial-1')
    assert (run/'inputs/TASK.md').read_text() == 'fixture'
    (tmp_path/'old').mkdir(); (tmp_path/'old/secret').write_text('DO NOT PACK')
    (run/'solve.py').write_text('pass')
    (run/'output').mkdir()
    (run/'output/result.json').write_text('{}')
    (run/'output/run_receipt.json').write_text('{}')
    out = m.pack(tmp_path, 'trial-1')
    assert out.parent == tmp_path
    with zipfile.ZipFile(out) as f:
        assert all(n.startswith('trial-1/') for n in f.namelist())
        assert not any('secret' in n for n in f.namelist())
    with pytest.raises(FileExistsError): m.prepare(tmp_path,z.name,digest,'trial-1')
    with pytest.raises(FileExistsError): m.pack(tmp_path,'trial-1')

@pytest.mark.parametrize('name', ['../outside','/outside','C:/outside','a/../../outside','a\\outside'])
def test_unsafe_zip_rejected_before_creating_run(tmp_path,name):
    m=module('task_bundle'); z,d=bundle(tmp_path,[name])
    with pytest.raises(ValueError): m.prepare(tmp_path,z.name,d,'trial')
    assert not (tmp_path/'trial').exists()

def test_bad_hash_and_changed_inputs_fail_closed(tmp_path):
    m=module('task_bundle'); z,d=bundle(tmp_path)
    with pytest.raises(ValueError): m.prepare(tmp_path,z.name,'0'*64,'trial')
    run=m.prepare(tmp_path,z.name,d,'trial')
    (run/'inputs/TASK.md').write_text('modified')
    with pytest.raises(ValueError): m.pack(tmp_path,'trial')
    assert not (tmp_path/'trial-results.zip').exists()

def test_business_ids_not_row_numbers():
    m=module('business_ids')
    rows=[dict(event='009',sku='X',direction='in',qty='10.5'),dict(event='009',sku='X',direction='in',qty='10.5'),dict(event='A7',sku='Y',direction='out',qty='')]
    assert m.summarize_movements(rows)==dict(status='ok',net_units={'X':'10.5'},valid_rows=1,duplicate_ids=['009'],missing_ids=['A7'])

@pytest.mark.parametrize('change', [{'qty':'2'},{'direction':'bad'},{'qty':'NaN'},{'event':''}])
def test_invalid_or_conflicting_events_stop(change):
    m=module('business_ids')
    first=dict(event='009',sku='X',direction='in',qty='10.5')
    with pytest.raises(ValueError): m.summarize_movements([first,dict(first,**change)])
