#!/usr/bin/env python3
"""從 stockanalysis.com 抓 VOO、QQQM 的配息（除息日、每股金額、發放日），合併進 dividends.json。
規則：已有金額的項目不動；有「金額未公告」的預定項目（amount=null）且日期對得上時才補金額與發放日。
抓不到或格式變了就不動檔案。"""
import json, re, html, urllib.request, datetime

SYMS = ['VOO', 'QQQM']
URL = 'https://stockanalysis.com/etf/{}/dividend/'
TD = r'<td[^>]*>\s*([^<]*?)\s*</td>'
ROW = re.compile(r'<tr[^>]*>(?:(?!</tr>).)*?</tr>', re.S)
MON = {m: i + 1 for i, m in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split())}

def iso(s):
    m = re.match(r'([A-Z][a-z]{2}) (\d{1,2}), (\d{4})$', s.strip())
    return '%s-%02d-%02d' % (m.group(3), MON[m.group(1)], int(m.group(2))) if m else None

def fetch(sym):
    req = urllib.request.Request(URL.format(sym.lower()), headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')

def parse(raw):
    rows = []
    for tr in ROW.findall(raw):
        cells = [html.unescape(c) for c in re.findall(TD, tr, re.S)]
        if len(cells) < 4: continue
        ex, amt, rec, pay = iso(cells[0]), cells[1].replace('$', '').replace(',', ''), iso(cells[2]), iso(cells[3])
        try: amt = float(amt)
        except ValueError: continue
        if ex and pay and 0 < amt < 50 and pay >= ex:
            rows.append({'ex': ex, 'pay': pay, 'amount': amt, 'rec': rec})
    return rows

def dd(a, b):
    return abs((datetime.date.fromisoformat(a) - datetime.date.fromisoformat(b)).days)

def merge(lst, rows, src):
    changed = []
    cutoff = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()   # 太舊的歷史不補，只處理近期與未來
    for r in rows:
        if r['ex'] < cutoff:
            continue
        if any(x.get('ex') == r['ex'] and x.get('amount') for x in lst):
            continue
        ph = next((x for x in lst if not x.get('amount') and dd(x['ex'], r['ex']) <= 14), None)
        if ph is not None:
            ph.update({'ex': r['ex'], 'pay': r['pay'], 'amount': r['amount'], 'officialPay': True, 'amountEstimated': False})
            ph.pop('note', None)
            if r.get('rec'): ph['rec'] = r['rec']
            if src not in ph.setdefault('sources', []): ph['sources'].append(src)
            changed.append((r['ex'], '補上金額'))
        elif not any(x.get('ex') == r['ex'] for x in lst):
            e = {'ex': r['ex'], 'pay': r['pay'], 'amount': r['amount'], 'officialPay': True, 'amountEstimated': False, 'sources': [src]}
            if r.get('rec'): e['rec'] = r['rec']
            lst.append(e); changed.append((r['ex'], '新增'))
    lst.sort(key=lambda x: x.get('ex', ''), reverse=True)
    return changed

def main():
    path = 'dividends.json'
    data = json.load(open(path, encoding='utf-8'))
    allc = []
    for sym in SYMS:
        try: raw = fetch(sym)
        except Exception as e:
            print(sym, '抓取失敗', e); continue
        rows = parse(raw)
        print(sym, '解析到', len(rows), '筆', rows[:2])
        if not rows:
            print(sym, '解析不到任何一筆，頁面格式可能變了'); continue
        ch = merge(data['items'].setdefault(sym, []), rows, URL.format(sym.lower()))
        allc += [(sym,) + c for c in ch]
    if not allc:
        print('沒有變動'); return
    data['updatedAt'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(path, 'a').write('\n')
    print('變動：', allc)

if __name__ == '__main__':
    main()
