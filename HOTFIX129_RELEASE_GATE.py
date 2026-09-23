from __future__ import annotations
import hashlib, json, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
BASELINE_ZIP = Path('/mnt/data/HOTFIX128_PERSISTENCE_TEST_CONTRACT_FINAL_VERIFIED.zip')
OUTPUT = Path('/mnt/data/HOTFIX129_TWO_REAL_TURN_PERSISTENCE_EXECUTION_GATE_FINAL_VERIFIED.zip')
NEW = {
    'HOTFIX129_PERSISTENCE_TWO_TURN_CONTRACT.md',
    'HOTFIX129_RELEASE_GATE.py',
    'HOTFIX129_RELEASE_NOTES.md',
    'VERSION_HOTFIX129.txt',
    'tests/test_hotfix129_two_turn_persistence.py',
}

def members(path):
    with zipfile.ZipFile(path) as z: return {n for n in z.namelist() if not n.endswith('/')}

def current_members():
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}

def pytest(cwd):
    r=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=cwd,check=True,capture_output=True,text=True)
    return r.stdout.strip()

def validate(root=ROOT):
    text=(root/'HOTFIX129_PERSISTENCE_TWO_TURN_CONTRACT.md').read_text(encoding='utf-8')
    for s in ('MESSAGE_1 → REQUEST_1 → ROUND_1','MESSAGE_2 → REQUEST_2 → ROUND_2','REQUEST_2 → ROUND_1 = FALSE','two separate chat messages','one submission','NOT_PROVEN'):
        if s not in text: raise SystemExit('Missing active HOTFIX129 contract clause: '+s)
    if 'REQUEST_2 → ROUND_1 = PASS' in text or 'REQUEST_2 → ROUND_1 = TRUE' in text:
        raise SystemExit('Obsolete positive Request2→Round1 acceptance found')

def main():
    baseline=members(BASELINE_ZIP); cur=current_members()
    missing=sorted(baseline-cur)
    if missing: raise SystemExit(f'Baseline files removed: {missing}')
    if not NEW <= cur: raise SystemExit(f'New files missing: {sorted(NEW-cur)}')
    validate(); source=pytest(ROOT)
    if OUTPUT.exists(): OUTPUT.unlink()
    package=sorted(baseline|NEW)
    with zipfile.ZipFile(OUTPUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel in package: z.write(ROOT/rel,rel)
    with zipfile.ZipFile(OUTPUT) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(package): raise SystemExit('ZIP member integrity failure')
    with tempfile.TemporaryDirectory(prefix='hotfix129_verify_') as td:
        ex=Path(td)/'release'; ex.mkdir()
        with zipfile.ZipFile(OUTPUT) as z: z.extractall(ex)
        validate(ex); extracted=pytest(ex)
    digest=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest={
        'version':'V23.0.0-HOTFIX129-TWO-REAL-TURN-PERSISTENCE-EXECUTION-GATE',
        'base':BASELINE_ZIP.name,
        'provider_core':'V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE',
        'purpose':'Require two real user submissions to create the two-message canonical persistence state; no inference from one submission.',
        'baseline_member_count':len(baseline), 'file_count':len(package), 'new_members':sorted(NEW),
        'source_full_pytest':source, 'reextracted_full_pytest':extracted, 'sha256':digest,
        'positive_contract':'MESSAGE_1→REQUEST_1→ROUND_1; MESSAGE_2→REQUEST_2→ROUND_2',
        'negative_contract':'REQUEST_2→ROUND_1=FALSE',
        'one_submission_result':'NOT_PROVEN', 'fail_closed':True,
    }
    (ROOT/'HOTFIX129_FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with zipfile.ZipFile(OUTPUT,'a',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z: z.write(ROOT/'HOTFIX129_FILE_MANIFEST.json','HOTFIX129_FILE_MANIFEST.json')
    digest=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    Path(str(OUTPUT)+'.sha256').write_text(f'{digest}  {OUTPUT.name}\n',encoding='utf-8')
    print(json.dumps({'zip':str(OUTPUT),'members':len(package)+1,'sha256':digest,'source_pytest':source,'reextracted_pytest':extracted},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
