import json,sys,urllib.request
def search(kw,n=15):
    req=urllib.request.Request("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",data=json.dumps({"keyword":kw,"currentPage":1,"pageSize":n}).encode(),headers={'Content-Type':'application/json'})
    d=json.load(urllib.request.urlopen(req,timeout=30))['data']['componentPageInfo']['list'] or []
    return d
if __name__=='__main__':
    for kw in sys.argv[1:]:
        print('##',kw)
        for x in search(kw):
            if x['stockCount']>0:
                print(' ',x['componentCode'],x['componentModelEn'],'|',x['erpComponentName'][:40],'|',x['componentLibraryType'],x.get('preferredComponentFlag'),'stock',x['stockCount'],'|',x.get('componentSpecificationEn'),'|',x.get('describe','')[:80])
