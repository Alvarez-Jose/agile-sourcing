# backend/chat/forms.py
# form destinations come from source records, never from generated model text.
import re
from urllib.parse import urlparse

from rules.provenance import DOCUMENTS


def form_links(answer):
    links = []
    for document_id, document in DOCUMENTS.items():
        if 'form' not in document_id and 'checklist' not in document_id:
            continue
        url = document.get('url')
        parsed = urlparse(url or '')
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            continue
        if not any(parsed.hostname == domain or parsed.hostname.endswith('.' + domain) for domain in ('ucsc.edu', 'ucop.edu')):
            continue
        aliases = [document['title']]
        if document_id == 'sspr-form':
            aliases += ['Source Selection & Price Reasonableness Justification Form',
                        'Source Selection and Price Reasonableness Justification Form', 'SSPR form', 'SSPR']
        if any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)' +
                         (r'(?!\s+(?:FAQ|frequently asked))' if alias == 'SSPR' else ''), answer, re.I) for alias in aliases):
            links.append({'title': document['title'], 'url': url, 'aliases': aliases})
    return links
