import json, sys
sys.stdout.reconfigure(encoding='utf-8')
d = json.load(open('data/emoji_dataset.json', encoding='utf-8'))
miss    = [r for r in d if not r.get('zh','').strip()]
fallback= [r for r in d if r.get('zh','').startswith('(')]
normal  = [r for r in d if r.get('zh','') and not r['zh'].startswith('(')]
print(f'Total: {len(d)}')
print(f'Good zh: {len(normal)} ({len(normal)/len(d)*100:.1f}%)')
print(f'English fallback: {len(fallback)}')
print(f'Missing: {len(miss)}')
print()
print('Sample good zh:')
for r in normal[:8]:
    print(f'  {r["char"]}  {r["en"][:30]:30s}  ->  {r["zh"]}')
print()
print('Sample fallback:')
for r in fallback[:5]:
    print(f'  {r["char"]}  {r["en"][:30]:30s}  ->  {r["zh"]}')
