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

# ---- 國泰投信官網（官方）：00878（基金代號 CN）----
CATHAY = 'https://cwapi.cathaysite.com.tw/api/Fund/{}?FundCode=CN'
CATHAY_SRC = 'https://www.cathaysite.com.tw/ETF/detail/ECN?tab=etf5'

def cathay_json(ep):
    req = urllib.request.Request(CATHAY.format(ep), headers={
        'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.cathaysite.com.tw', 'Referer': 'https://www.cathaysite.com.tw/'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode('utf-8'))

def d8(v):
    return str(v).replace('/', '-')[:10] if v else None

def cathay_merge(data):
    changed = []
    lst = data['items'].setdefault('00878', [])
    try:
        hist = cathay_json('GetHistoryAllotInfo')['result']['fundAllotInfoList']
        near = cathay_json('GetNearAllotSchedule')['result']
    except Exception as e:
        print('國泰官網抓取失敗', e); return changed
    print('國泰官網：歷史', len(hist), '筆，下一次', near)
    def mark(ex, pay, amount, note):
        cur = next((x for x in lst if x.get('ex') == ex), None)
        if cur is None:
            cur = {'ex': ex, 'pay': pay, 'amount': amount, 'officialPay': True, 'amountEstimated': False, 'sources': [CATHAY_SRC]}
            lst.append(cur); changed.append(('00878', ex, '國泰新增')); return
        before = (cur.get('pay'), cur.get('amount'), cur.get('officialPay'))
        cur['pay'] = pay
        if amount: cur['amount'] = amount; cur['amountEstimated'] = False
        cur['officialPay'] = True
        if CATHAY_SRC not in cur.setdefault('sources', []): cur['sources'].append(CATHAY_SRC)
        if note: cur['note'] = note
        else: cur.pop('note', None)
        if before != (cur.get('pay'), cur.get('amount'), cur.get('officialPay')): changed.append(('00878', ex, '國泰確認'))
    for h in hist[:6]:
        ex, pay = d8(h.get('transDate')), d8(h.get('lendingDate'))
        if ex and pay and h.get('allotMoney'): mark(ex, pay, float(h['allotMoney']), None)
    nex, npay = d8(near.get('transDate')), d8(near.get('lendingDate'))
    if nex and npay and not any(x.get('ex') == nex and x.get('amount') and 'cathaysite' in ' '.join(x.get('sources', [])) and x.get('officialPay') and False for x in lst):
        has = next((x for x in lst if x.get('ex') == nex), None)
        note = '發放日經國泰投信官網確認；金額尚未見於官網，取自 Yahoo 奇摩股市' if (has and has.get('amount')) else '發放日經國泰投信官網確認；金額尚未公告'
        if not any(h for h in hist if d8(h.get('transDate')) == nex):
            mark(nex, npay, None, note)
    lst.sort(key=lambda x: x.get('ex', ''), reverse=True)
    return changed

# ---- 群益投信官網（官方）：00919（頁面伺服器端直接輸出配息表）----
CAPITAL_SRC = 'https://www.capitalfund.com.tw/etf/product/detail/195/interest'
CAP_ROW = re.compile(r'除息日\s*(\d{4}/\d{2}/\d{2})\s*發放日\s*(\d{4}/\d{2}/\d{2})\s*每單位分配金額\(元\)\s*(\d+(?:\.\d+)?)')

def capital_merge(data):
    changed = []
    try:
        req = urllib.request.Request(CAPITAL_SRC, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36', 'Accept-Language': 'zh-TW,zh;q=0.9'})
        raw = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
    except Exception as e:
        print('群益官網抓取失敗', e); return changed
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[\s\S]*?</\1>', ' ', raw))))
    if '00919' not in text:
        print('群益頁面看起來不是 00919，略過'); return changed
    rows = [(d8(a), d8(b), float(c)) for a, b, c in CAP_ROW.findall(text)]
    print('群益官網：解析到', len(rows), '筆', rows[:2])
    lst = data['items'].setdefault('00919', [])
    for ex, pay, amt in rows[:6]:
        if not (0 < amt < 10 and pay >= ex): continue
        cur = next((x for x in lst if x.get('ex') == ex), None)
        if cur is None:
            lst.append({'ex': ex, 'pay': pay, 'amount': amt, 'officialPay': True, 'amountEstimated': False, 'sources': [CAPITAL_SRC]})
            changed.append(('00919', ex, '群益新增')); continue
        before = (cur.get('pay'), cur.get('amount'), cur.get('officialPay'))
        cur.update({'pay': pay, 'amount': amt, 'officialPay': True, 'amountEstimated': False})
        if CAPITAL_SRC not in cur.setdefault('sources', []): cur['sources'].append(CAPITAL_SRC)
        if before != (cur['pay'], cur['amount'], cur['officialPay']): changed.append(('00919', ex, '群益確認'))
    lst.sort(key=lambda x: x.get('ex', ''), reverse=True)
    return changed

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
    changed += cathay_merge(data)
    changed += capital_merge(data)
    if not changed:
        print('沒有變動'); return
    data['updatedAt'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(path, 'a').write('\n')
    print('變動：', changed)

if __name__ == '__main__':
    main()
