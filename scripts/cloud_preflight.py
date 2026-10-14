"""Check portable skill files and optionally fetch one public PDF.

Never creates investment evidence or a claim that research coverage is complete.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents' / 'skills' / 'a-share-research'
PDF_URL = 'https://static.cninfo.com.cn/finalpage/2026-08-19/1225480327.PDF'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network', action='store_true')
    args = parser.parse_args()
    report = dict(python=sys.version.split()[0], skill_version='1.0.1-portable',
                  scope='Skill files and optional one-PDF connectivity only',
                  cloud_environment_verified=False, checks=[])
    failed = False
    needed = ['SKILL.md', 'agents/openai.yaml', 'references/workflow.md',
              'references/evidence.md', 'references/analysis.md', 'references/scoring.md',
              'references/validation.md', 'assets/research-plan.md', 'assets/report.md',
              'assets/research-memory.json', 'scripts/research_checks.py']
    missing = [p for p in needed if not (SKILL / p).is_file()]
    report['checks'].append(dict(name='skill_files', status='failed' if missing else 'passed', missing=missing))
    failed |= bool(missing)
    if not missing:
        text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
        absent = []
        import re
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if '://' not in link and not (SKILL / link.split('#')[0]).is_file():
                absent.append(link)
        report['checks'].append(dict(name='entrypoint_references', status='failed' if absent else 'passed', missing=absent))
        failed |= bool(absent)
        spec = importlib.util.spec_from_file_location('research_checks', SKILL / 'scripts/research_checks.py')
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            report['checks'].append(dict(name='validator_import', status='passed'))
        except Exception as exc:
            report['checks'].append(dict(name='validator_import', status='failed', error=type(exc).__name__ + ': ' + str(exc)))
            failed = True
    have_pypdf = importlib.util.find_spec('pypdf') is not None
    report['checks'].append(dict(name='pypdf_available', status='passed' if have_pypdf else 'failed'))
    failed |= not have_pypdf
    if args.network and have_pypdf:
        from pypdf import PdfReader
        try:
            req = urllib.request.Request(PDF_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                resolved = response.url
            if not data.startswith(b'%PDF'):
                raise ValueError('Response is not PDF')
            reader = PdfReader(io.BytesIO(data))
            first = reader.pages[0].extract_text() or ''
            if '天孚' not in first:
                raise ValueError('Issuer marker not found on the first PDF page')
            report['checks'].append(dict(name='cninfo_pdf_connectivity', status='passed',
                                         requested_url=PDF_URL, resolved_url=resolved,
                                         bytes=len(data), pages=len(reader.pages),
                                         sha256=hashlib.sha256(data).hexdigest(),
                                         tls_verification='enabled', financial_coverage='not_tested'))
        except Exception as exc:
            report['checks'].append(dict(name='cninfo_pdf_connectivity', status='failed',
                                         requested_url=PDF_URL, error=type(exc).__name__ + ': ' + str(exc)))
            failed = True
    else:
        report['checks'].append(dict(name='cninfo_pdf_connectivity', status='not_attempted',
                                     reason='--network not requested or pypdf missing'))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
