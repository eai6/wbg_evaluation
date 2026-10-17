"""Trace the research pipeline stage by stage for one outcome (committed f33c0af vs current code). Run from q1_prototype/.
Needs the committed analysis module: git show f33c0af:q1_prototype/assistant/analysis.py > assistant/_analysis_committed.py"""
import os, sys, json, re, logging, time
sys.path.insert(0, os.getcwd())
os.environ["DJANGO_ALLOWED_HOSTS"]="testserver"; os.environ.setdefault("DJANGO_SETTINGS_MODULE","scorecard_explorer.settings")
import django; django.setup(); logging.disable(logging.WARNING)
from explorer import queries as q
from assistant import pcn, pipelines, prompts, llm, resolver
from assistant import _analysis_committed as old, analysis as new
oid=int(sys.argv[1]); out={}
Q="Based on the Scorecard data and the Bank's current operational footprint, which areas and countries would you suggest prioritizing in a three-year plan for your chosen thematic area? What does the data tell us about where the biggest gaps or opportunities are?"
# stage 0: routing
usage=[]; t=time.time(); r=pipelines.route(Q,{"outcome_id":None,"filters":{}},[],usage); out["route"]={"intent":r["intent"],"by":r["by"],"entities":r["entities"],"ms":int((time.time()-t)*1000)}
# stage 1: area choice
out["choose_area"]=[{"outcome":x["outcome"]["name"],"ind":x["ind_code"],"gap":x["gap"],"n_results":x["n_results"],"n_need":x["n_need"],"ok":x["ok"]} for x in old.choose_area()[:5]]
# stages 2-5 for both versions
FOCUS=["NGA","COD","IND","ETH","CHN","PAK","BGD","IDN","SSD","GIN","KEN","USA","DEU"]
for label,mod in (("committed",old),("current",new)):
    claims=pcn.Claims(); R=mod.research(oid,claims)
    rows={x["code"]:x for x in R["rows"]}
    out[label]={
      "indicator":R["indicator"]["ind_code"],"indicator_name":R["indicator"]["display_name"],
      "need":{"code":R["need"]["ind_code"],"name":R["need"]["display_name"],"unit":R["need"]["unit"],"higher_is_better":R["need"]["higher_is_better"]} ,
      "need_is_negative":R["need_is_negative"],"need_is_pop_share":R["need_is_pop_share"],"sector_pattern":R["sector_pattern"],
      "sources":R["sources"],"n_rows":len(R["rows"]),
      "sample_rows":{c:{k:rows[c][k] for k in rows[c] if k in("name","region","lending","achieved","expected","gap","ratio","need","need_year","population","people_in_need","projects","commitments","active_projects")} for c in FOCUS if c in rows},
      "excluded_focus":[c for c in FOCUS if c not in rows],
      "accelerate":[x["code"] for x in R["accelerate"]],"expand":[x["code"] for x in R["expand"]],"strong":[(x["code"],round(x["ratio"],3)) for x in R["strong"]],
      "overshoot":[(x["code"],round(x["ratio"],2)) for x in R["overshoot"][:8]],
      "regions":[{k:v for k,v in r.items()} for r in R["regions"]],"focus":R["focus"]["code"],
      "for_writer":R["for_writer"],
    }
    if label=="committed":
        # stage 6: writer (LLM) on the committed payload, raw output + per-claim check
        u=[]; msgs=[{"role":"system","content":prompts.RESEARCH_WRITER.format(question=Q,context=R["outcome"]["name"],outcome=R["outcome"]["name"])+"\n\nRAW TOOL RESULTS (JSON):\n"+json.dumps(R["for_writer"],default=str)[:24000]},{"role":"user","content":Q}]
        raw=llm.complete(msgs,max_tokens=3000,usage=u).content or ""
        html,stats=pcn.render(raw,claims)
        checks=[]
        for m in pcn.TAG.finditer(raw):
            c=claims.get(m.group(1)); i=m.start()
            sent=raw[max(0,raw.rfind("\n",0,i)):raw.find("\n",i) if raw.find("\n",i)>0 else len(raw)].strip()
            checks.append({"id":m.group(1),"shown":m.group(2),"verified":bool(c and pcn.check(m.group(2),c)),"claim_label":c and c["l"],"claim_source":c and c["s"],"source_value":c and c["v"],"context":re.sub(r'<claim id="[a-z0-9]+">([^<]*)</claim>',r"\1",sent)[:220]})
        out[label]["writer"]={"system_prompt_head":prompts.RESEARCH_WRITER[:2000],"raw":raw,"stats":stats,"checks":checks,"usage":u}
json.dump(out,open(sys.argv[2],"w"),indent=1,default=str)
print("ok", len(out["committed"]["writer"]["checks"]), "claims")
