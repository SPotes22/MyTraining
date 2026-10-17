import json, sys
for l in open(sys.argv[1]):
    d = json.loads(l)
    if 'viewport' in d:
        print('### viewport', d['viewport']); continue
    print(d['page'], d['status'], d['url'], len(d['violations']))
    for v in d['violations']:
        print('   ', v['impact'], v['id'], v['n'], v['targets'][:3])
        for c in (v.get('colors') or [])[:12]:
            print('        ', c)
