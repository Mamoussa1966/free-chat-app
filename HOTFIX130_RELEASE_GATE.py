from __future__ import annotations
import hashlib, json, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
BASELINE_ZIP = Path('/mnt/data/files/HOTFIX129_TWO_REAL_TURN_PERSISTENCE_EXECUTION_GATE_FINAL_VERIFIED(2).zip')
OUTPUT = Path('/mnt/data/files/HOTFIX130_CANONICAL_PERSISTENCE_COUNTER_CONSISTENCY_FINAL_VERIFIED.zip')
NEW = {
    'HOTFIX130_COUNTER_CONSISTENCY_CONTRACT.md',
    'HOTFIX130_RELEASE_GATE.py',
    'HOTFIX130_RELEASE_NOTES.md',
    'VERSION_HOTFIX130.txt',
    'tests/test_hotfix130_counter_consistency.py',
}

def members(path):
    with zipfile.ZipFile(path) as z:
        return {n for n in z.namelist() if not n.endswith('/')}

def current_members():
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}

def run_pytest(cwd):
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=cwd, check=True, capture_output=True, text=True)
    return r.stdout.strip()

def validate(root=ROOT):
    c=(root/'HOTFIX130_COUNTER_CONSISTENCY_CONTRACT.md').read_text(encoding='utf-8')
    for s in ('persisted_message_count == canonical_message_count','persisted_request_count == canonical_request_count','persisted_round_count == canonical_round_count','Raw list length is never authoritative'):
        if s not in c: raise SystemExit('Missing HOTFIX130 invariant: '+s)
    if not (root/'conversation_persistence_v26.py').read_text(encoding='utf-8').count('CANONICAL_IDENTITY_RECORDS') == 1:
        raise SystemExit('Counter authority marker missing or duplicated')

def main():
    baseline=members(BASELINE_ZIP); cur=current_members()
    missing=sorted(baseline-cur)
    if missing: raise SystemExit(f'Baseline files removed: {missing}')
    if not NEW <= cur: raise SystemExit(f'New files missing: {sorted(NEW-cur)}')
    validate(); source=run_pytest(ROOT)
    if OUTPUT.exists(): OUTPUT.unlink()
    package=sorted(baseline | NEW)
    with zipfile.ZipFile(OUTPUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel in package: z.write(ROOT/rel, rel)
    with tempfile.TemporaryDirectory(prefix='hotfix130_verify_') as td:
        ex=Path(td)/'release'; ex.mkdir()
        with zipfile.ZipFile(OUTPUT) as z: z.extractall(ex)
        validate(ex); extracted=run_pytest(ex)
    digest=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest={
        'version':'V23.0.0-HOTFIX130-CANONICAL-PERSISTENCE-COUNTER-CONSISTENCY',
        'base':BASELINE_ZIP.name,
        'provider_core':'V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE',
        'purpose':'Unify persistence and authoritative historical counters on canonical identity records; raw list length is non-authoritative.',
        'baseline_member_count':len(baseline),
        'file_count':len(package),
        'new_members':sorted(NEW),
        'source_full_pytest':source,
        'reextracted_full_pytest':extracted,
        'sha256':digest,
        'counter_contract':'persisted counts == authoritative canonical identity counts',
        'fail_closed':True,
        'hotfix129_two_real_turn_contract_preserved':True,
    }
    with zipfile.ZipFile(OUTPUT,'a',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr('HOTFIX130_FILE_MANIFEST.json', json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    digest=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    Path(str(OUTPUT)+'.sha256').write_text(f'{digest}  {OUTPUT.name}\n',encoding='utf-8')
    print(json.dumps({'zip':str(OUTPUT),'members':len(package)+1,'sha256':digest,'source_pytest':source,'reextracted_pytest':extracted},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
