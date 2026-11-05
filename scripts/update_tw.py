#!/usr/bin/env python3
"""從 Yahoo 奇摩股市抓台股三檔輪動 ETF 的配息（除息日、發放日、每股現金股利），合併進 dividends.json。
規則：只補空白或非官方的項目；已標 officialPay=true 的絕不覆蓋。抓不到或格式變了就不動檔案。"""
import json, re, sys, html, urllib.request, datetime

CODES = ['00919', '00878', '0056']
URL = 'https://tw.stock.yahoo.com/quote/{}.TW/dividend'
LATEST = re.compile(r'"latestDividend":\{[^{}]*"exDividend":\{"cash":"(\d+(?:\.\d+)?)","cashPayDate":"(\d{4}-\d{2}-\d{2})[^"]*"[^{}]*?"date":"(\d{4}-\d{2}-\d{2})')

def fetch(code):
    req = urllib.request.Request(URL.format(code), headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')

def parse(raw):
    """Yahoo 奇摩股市頁面內嵌的 latestDividend：最新一期的每股現金股利、發放日、除息日。"""
    rows = []
    m = LATEST.search(raw)
    if m:
        amt = float(m.group(1)); pay = m.group(2); ex = m.group(3)
        if 0 < amt < 10 and pay >= ex:
            rows.append({'ex': ex, 'pay': pay, 'amount': amt})
    return rows

def main():
    path = 'dividends.json'
    data = json.load(open(path, encoding='utf-8'))
    changed = []
    for code in CODES:
        try:
            raw = fetch(code)
        except Exception as e:
            print(code, '抓取失敗', e); continue
        rows = parse(raw)
        print(code, '解析到', len(rows), '筆', rows[:2])
        if not rows:
            print(code, '解析不到任何一筆，頁面格式可能變了；片段：', re.sub(r'\s+', ' ', raw)[:300]); continue
        src = URL.format(code)
        lst = data['items'].setdefault(code, [])
        for r in rows:
            cur = next((x for x in lst if x.get('ex') == r['ex']), None)
            if cur is None:
                lst.append({'ex': r['ex'], 'pay': r['pay'], 'amount': r['amount'], 'officialPay': False,
                            'amountEstimated': False, 'sources': [src], 'note': '取自 Yahoo 奇摩股市，未經發行商公告頁直接確認'})
                changed.append((code, r['ex'], '新增'))
            elif not cur.get('officialPay'):
                if cur.get('amount') != r['amount'] or cur.get('pay') != r['pay']:
                    cur['amount'] = r['amount']; cur['pay'] = r['pay']; cur['amountEstimated'] = False
                    if src not in cur.setdefault('sources', []): cur['sources'].append(src)
                    cur['note'] = '取自 Yahoo 奇摩股市，未經發行商公告頁直接確認'
                    changed.append((code, r['ex'], '更新'))
        lst.sort(key=lambda x: x.get('ex', ''), reverse=True)
    if not changed:
        print('沒有變動'); return
    data['updatedAt'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(path, 'a').write('\n')
    print('變動：', changed)

if __name__ == '__main__':
    main()
