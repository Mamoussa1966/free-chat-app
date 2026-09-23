from __future__ import annotations
import hashlib, json, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
BASELINE_ZIP = Path("/mnt/data/HOTFIX127_AUTHORITATIVE_ROUND_CONTRACT_FINAL_VERIFIED.zip")
OUTPUT = Path("/mnt/data/HOTFIX128_PERSISTENCE_TEST_CONTRACT_FINAL_VERIFIED.zip")
NEW_MEMBERS = {"HOTFIX128_PERSISTENCE_TEST_CONTRACT.md","HOTFIX128_RELEASE_GATE.py","HOTFIX128_RELEASE_NOTES.md","VERSION_HOTFIX128.txt","tests/test_hotfix128_persistence_test_contract.py"}

def baseline_members():
    with zipfile.ZipFile(BASELINE_ZIP) as zf: return {n for n in zf.namelist() if not n.endswith('/')}

def current_members():
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}

def run_full_pytest(cwd):
    r=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=cwd,check=True,capture_output=True,text=True); return r.stdout.strip()

def validate_active_contract(root=ROOT):
    text=(root/'HOTFIX128_PERSISTENCE_TEST_CONTRACT.md').read_text(encoding='utf-8')
    for value in ['MESSAGE_1 → REQUEST_1 → ROUND_1','MESSAGE_2 → REQUEST_2 → ROUND_2','REQUEST_2 → ROUND_1 = FALSE','request_2_round_2_mapping = FALSE','canonical_round_sequence_proven = FALSE']:
        if value not in text: raise SystemExit(f'Missing active contract clause: {value}')
    if 'REQUEST_2 → ROUND_1 = PASS' in text or 'REQUEST_2 → ROUND_1 = TRUE' in text: raise SystemExit('Obsolete positive Request2→Round1 acceptance found')

def main():
    baseline=baseline_members(); current=current_members(); missing=sorted(baseline-current)
    if missing: raise SystemExit(f'HOTFIX127 members removed: {missing}')
    if not NEW_MEMBERS <= current: raise SystemExit(f'HOTFIX128 members missing: {sorted(NEW_MEMBERS-current)}')
    validate_active_contract(); source=run_full_pytest(ROOT)
    if OUTPUT.exists(): OUTPUT.unlink()
    package_members=sorted(baseline|NEW_MEMBERS)
    with zipfile.ZipFile(OUTPUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for rel in package_members: zf.write(ROOT/rel,rel)
    with zipfile.ZipFile(OUTPUT) as zf:
        names=zf.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(package_members): raise SystemExit('ZIP member integrity failure')
    with tempfile.TemporaryDirectory(prefix='hotfix128_verify_') as td:
        ex=Path(td)/'release'; ex.mkdir()
        with zipfile.ZipFile(OUTPUT) as zf: zf.extractall(ex)
        validate_active_contract(ex); release=run_full_pytest(ex)
    digest=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest={'version':'V23.0.0-HOTFIX128-PERSISTENCE-TEST-CONTRACT-FINAL','base':BASELINE_ZIP.name,'provider_core':'V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE','purpose':'Correct active V26.3 Persistence test contract: Request 2→Round 2 positive; Request 2→Round 1 negative only','baseline_file_members_preserved':True,'baseline_member_count':len(baseline),'file_count':len(package_members),'new_members':sorted(NEW_MEMBERS),'source_full_pytest':source,'reextracted_full_pytest':release,'sha256':digest,'active_positive_contract':'MESSAGE_1→REQUEST_1→ROUND_1; MESSAGE_2→REQUEST_2→ROUND_2','active_negative_contract':'REQUEST_2→ROUND_1=FALSE','historical_old_wording_preserved':True,'fail_closed':'MISSING_OR_AMBIGUOUS_OR_CONTRADICTORY_CANONICAL_IDENTITY => NOT_PROVEN/FAIL'}
    (ROOT/'HOTFIX128_FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (Path('/mnt/data')/(OUTPUT.name+'.sha256')).write_text(f'{digest}  {OUTPUT.name}\n',encoding='utf-8')
    print(json.dumps({'zip':str(OUTPUT),'members':len(package_members),'sha256':digest,'source_pytest':source,'reextracted_pytest':release},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
