from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, zipfile
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'HOTFIX146_V23_FINAL_CLOSURE_AUDIT_FINAL_VERIFIED.zip'
OUT=Path('/mnt/data/HOTFIX147_V23_SECURITY_REGRESSION_CLOSURE_FINAL_VERIFIED.zip')
PRESERVE={'conversation_store.py','conversation_persistence_v26.py','conversation_v25_runtime.py','providers.py','v23_final_closure_audit.py'}

def sha(p):
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def main():
    if not BASE.exists(): raise SystemExit(f'Missing baseline {BASE}')
    base_dir=ROOT.parent/'hf147_base_check'
    if base_dir.exists(): shutil.rmtree(base_dir)
    base_dir.mkdir()
    with zipfile.ZipFile(BASE) as z: z.extractall(base_dir)
    for rel in PRESERVE:
        if sha(ROOT/rel)!=sha(base_dir/rel): raise SystemExit(f'Forbidden persistence/provider drift: {rel}')
    env=dict(os.environ)
    r=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,env=env,text=True)
    if r.returncode: return r.returncode
    if OUT.exists(): OUT.unlink()
    members=sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '.pytest_cache' not in p.parts and '__pycache__' not in p.parts and p.name not in {'HOTFIX147_MANIFEST.json'})
    with zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED) as z:
        for rel in members: z.write(ROOT/rel,rel)
    check=ROOT.parent/'hf147_zip_check'
    if check.exists(): shutil.rmtree(check)
    check.mkdir()
    with zipfile.ZipFile(OUT) as z: z.extractall(check)
    r2=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=check,env=env,text=True)
    if r2.returncode: return r2.returncode
    manifest={'release':'HOTFIX147','version':'V23.0.0-HOTFIX147-V23-SECURITY-REGRESSION-CLOSURE','base_zip':BASE.name,'source_pytest_returncode':r.returncode,'zip_pytest_returncode':r2.returncode,'preserved_core_files_byte_identical':True,'canonical_persistence_changed':False,'message_request_contract_changed':False,'request_round_contract_changed':False,'round_sequence_changed':False,'hotfix123_2_preserved':True,'hotfix129_preserved':True,'hotfix130_preserved':True,'fail_closed':True,'release_scope':['raw payload security false-positive closure','HOTFIX130 regression API closure','UI/canonical counter semantic separation']}
    mp=ROOT/'HOTFIX147_MANIFEST.json'; mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(OUT,'a',zipfile.ZIP_DEFLATED) as z: z.write(mp,mp.name)
    digest=sha(OUT); Path(str(OUT)+'.sha256').write_text(digest+'  '+OUT.name+'\n')
    print('FINAL_ZIP='+str(OUT)); print('MEMBERS='+str(len(zipfile.ZipFile(OUT).namelist()))); print('SHA256='+digest); return 0
if __name__=='__main__': raise SystemExit(main())
