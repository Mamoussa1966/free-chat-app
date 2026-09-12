from pathlib import Path
import re


def test_release_metadata_has_single_current_version():
    root = Path(__file__).resolve().parents[1]
    version = (root / 'VERSION.txt').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'V22\.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX\d+-FINAL', version)
    main = (root / 'main.py').read_text(encoding='utf-8')
    providers = (root / 'providers.py').read_text(encoding='utf-8')
    release = (root / 'RELEASE_NOTES.md').read_text(encoding='utf-8')
    builder = (root / 'build_release.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = PROVIDER_VERSION' in main
    assert f'VERSION = "{version}"' in providers
    assert version in release
    assert 'HOTFIX27_FINAL.zip' in builder


def test_no_stale_release_identifiers_in_production_metadata():
    root = Path(__file__).resolve().parents[1]
    current = int(re.search(r'HOTFIX(\d+)(?:-FINAL)?$', (root / 'VERSION.txt').read_text(encoding='utf-8').strip()).group(1))
    forbidden = [re.compile(r'\bHOTFIX' + str(n) + r'\b') for n in range(1, current)]
    paths = [root / 'main.py', root / 'providers.py', root / 'README.md', root / 'RELEASE_NOTES.md', root / 'build_release.py', root / 'VERSION.txt']
    offenders = []
    for path in paths:
        text = path.read_text(encoding='utf-8', errors='replace')
        for marker in forbidden:
            if marker.search(text):
                offenders.append(f'{path.name}:{marker.pattern}')
    assert not offenders, 'Stale release identifiers found: ' + ', '.join(offenders)
