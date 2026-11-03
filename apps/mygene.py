
from scs import *
from browser import aio, window
import math, random, json

# extensions required per spec
try:
    from extensions.fetch import fetch_json as ext_fetch_json, fetch as ext_fetch
    EXT_FETCH_OK = True
except:
    EXT_FETCH_OK = False
    ext_fetch_json = None
    ext_fetch = None

try:
    from extensions.proc_audio import AudioEngine
    PROC_OK = True
except:
    PROC_OK = False
    AudioEngine = None

try:
    import extensions.pyodide as _py_ext
    PYODIDE_OK = True
    _py_candidates = ['run_python_async','run_python','run','exec','evaluate','run_code','execute','runPythonAsync']
except:
    PYODIDE_OK = False
    _py_ext = None
    _py_candidates = []

W, H = 1050, 700
HEADER_H = 64

SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H = 16, 78, 310, 170
RESULTS_X, RESULTS_Y, RESULTS_W, RESULTS_H = 16, 258, 310, 200
DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H = 340, 78, 344, 230
FACET_X, FACET_Y, FACET_W, FACET_H = 700, 78, 334, 174
TYPES_X, TYPES_Y, TYPES_W, TYPES_H = 700, 262, 334, 196
ARCH_X, ARCH_Y, ARCH_W, ARCH_H = 16, 470, 514, 214
STATS_X, STATS_Y, STATS_W, STATS_H = 546, 470, 488, 214

BG = rgb(11,15,27)
PANEL_BG = rgb(20,25,42)
PANEL_BORDER = rgb(48,58,90)
PANEL_HEAD = rgb(30,37,63)
CYAN = rgb(88,240,255)
PINK = rgb(255,110,180)
YELLOW = rgb(255,230,110)
GREEN = rgb(110,255,170)
PURPLE = rgb(160,120,255)
ORANGE = rgb(255,160,80)
WHITE = rgb(235,242,255)
MUTED = rgb(150,165,195)

def pointInRect(px,py,rx,ry,rw,rh):
    return rx <= px <= rx+rw and ry <= py <= ry+rh

def clamp(v,a,b):
    return max(a, min(b, v))

def truncate(s,n):
    try:
        s=str(s)
        return s if len(s)<=n else s[:n-1]+"…"
    except:
        return ""

def js_to_py(o, depth=0):
    if depth>15:
        return str(o)[:200] if o is not None else None
    try:
        if o is None:
            return None
        if isinstance(o, (str,int,float,bool)):
            return o
        if isinstance(o, dict):
            return {k: js_to_py(v, depth+1) for k,v in o.items()}
        if isinstance(o, (list,tuple)):
            return [js_to_py(v, depth+1) for v in o]
        try:
            if window.Array.isArray(o):
                return [js_to_py(o[i], depth+1) for i in range(o.length)]
        except:
            pass
        try:
            s = window.JSON.stringify(o)
            if s is not None and s != "undefined":
                return json.loads(s)
        except:
            pass
        try:
            keys = window.Object.keys(o)
            d={}
            for k in keys:
                ks=str(k)
                try:
                    d[ks]=js_to_py(o[k], depth+1)
                except:
                    pass
            if d:
                return d
        except:
            pass
        return o
    except:
        return o

def safe_get(d,k,default=None):
    try:
        if isinstance(d,dict):
            return d.get(k,default)
        return default
    except:
        return default

def drawPanel(x,y,w,h,title):
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1.2,roundness=10)
    drawRect(x+1,y+1,w-2,20,fill=PANEL_HEAD,roundness=8)
    drawLabel(title, x+12, y+11, fill=MUTED, size=13, bold=True, align="left-center")

def draw_button(x,y,w,h,label,active=False,color=None):
    fillc=color if color else (CYAN if active else rgb(38,46,74))
    borderc=WHITE if active else PANEL_BORDER
    drawRect(x,y,w,h,fill=fillc,border=borderc,borderWidth=1.2,roundness=7)
    fc=rgb(0,0,0) if active else WHITE
    drawLabel(label, x+w/2, y+h/2, fill=fc, size=13, bold=active, align="center")

def draw_bar_chart(x,y,w,h,data_dict,max_val=None,color_map=None):
    try:
        data_dict=js_to_py(data_dict)
        if not isinstance(data_dict, dict) or not data_dict:
            drawLabel("no data", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        vals=[]
        for v in data_dict.values():
            try:
                vals.append(float(v))
            except:
                vals.append(0)
        if not vals:
            return
        if max_val is None:
            max_val=max(vals) if vals else 1
            if max_val<1:
                max_val=1
        bar_area_w=w-80
        cnt=len(vals)
        bar_h=(h-16)/cnt-6 if cnt else 20
        if bar_h<8:
            bar_h=8
        i=0
        for lbl,val in data_dict.items():
            try:
                fv=float(val)
            except:
                fv=0
            by=y+8+i*(bar_h+6)
            bw=(fv/max_val)*bar_area_w if max_val else 0
            col=color_map.get(lbl, CYAN) if color_map else [CYAN,PINK,YELLOW,GREEN,PURPLE,ORANGE][i%6]
            drawRect(x+70, by, bar_area_w, bar_h, fill=rgb(18,24,42), roundness=4)
            drawRect(x+70, by, bw, bar_h, fill=col, roundness=4)
            drawLabel(truncate(str(lbl),12), x+2, by+bar_h/2, fill=WHITE, size=13, align="left-center")
            drawLabel(str(int(fv)) if fv==int(fv) else f"{fv:.1f}", x+72+bar_area_w+2, by+bar_h/2, fill=MUTED, size=13, align="left-center")
            i+=1
    except Exception as e:
        window.console.log(f"bar error {e}")

def draw_pie_chart(x,y,w,h,data_dict,color_map=None):
    try:
        data_dict=js_to_py(data_dict)
        if not isinstance(data_dict, dict):
            return
        vals=[float(v) for v in data_dict.values() if float(v)>0]
        if not vals:
            return
        total=sum(vals)
        cx=x+w*0.42
        cy=y+h*0.5+6
        r=min(w*0.36, h*0.38)
        start_ang=-90
        colors=[CYAN,PINK,YELLOW,GREEN,PURPLE,ORANGE]
        i=0
        for lbl,val in data_dict.items():
            try:
                fv=float(val)
            except:
                continue
            if fv<=0:
                continue
            ang=(fv/total)*360
            col=color_map.get(lbl, colors[i%len(colors)]) if color_map else colors[i%len(colors)]
            pts=[(cx,cy)]
            steps=max(2,int(ang/6))
            for s in range(steps+1):
                a=math.radians(start_ang + (s/steps)*ang)
                pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
            try:
                drawPolygon(*pts, fill=col, border=rgb(10,14,26), borderWidth=1)
            except:
                pass
            start_ang+=ang
            i+=1
        lx=x+w*0.78
        ly=y+14
        j=0
        for lbl,val in data_dict.items():
            try:
                fv=float(val)
            except:
                continue
            if fv<=0:
                continue
            col=color_map.get(lbl, colors[j%len(colors)]) if color_map else colors[j%len(colors)]
            drawRect(lx, ly+j*20, 10,10, fill=col, roundness=2)
            drawLabel(f"{truncate(str(lbl),10)}:{int(fv)}", lx+14, ly+j*20+5, fill=WHITE, size=13, align="left-center")
            j+=1
    except Exception as e:
        window.console.log(f"pie error {e}")

def flatten_for_inspector(obj, prefix="", depth=0, max_depth=4, limit=200):
    out=[]
    try:
        obj=js_to_py(obj)
        if depth>max_depth:
            return out
        if isinstance(obj, dict):
            for k,v in list(obj.items())[:limit]:
                path=f"{prefix}.{k}" if prefix else str(k)
                t="dict" if isinstance(v, dict) else "list" if isinstance(v, list) else type(v).__name__
                out.append((path, k, v, t, depth))
                if isinstance(v, (dict,list)) and depth<max_depth:
                    # for dict, expand one level inline
                    if isinstance(v, dict):
                        for kk,vv in list(v.items())[:30]:
                            sub_path=f"{path}.{kk}"
                            sub_t="dict" if isinstance(vv, dict) else "list" if isinstance(vv, list) else type(vv).__name__
                            out.append((sub_path, kk, vv, sub_t, depth+1))
                            if isinstance(vv, dict) and depth+1<max_depth:
                                for k3,v3 in list(vv.items())[:12]:
                                    out.append((f"{sub_path}.{k3}", k3, v3, type(v3).__name__ if not isinstance(v3,(dict,list)) else ("dict" if isinstance(v3,dict) else "list"), depth+2))
                    else:
                        # list
                        for i2, vv in enumerate(v[:12]):
                            sub_path=f"{path}[{i2}]"
                            sub_t="dict" if isinstance(vv, dict) else "list" if isinstance(vv, list) else type(vv).__name__
                            out.append((sub_path, f"[{i2}]", vv, sub_t, depth+1))
        elif isinstance(obj, list):
            for i,v in enumerate(obj[:30]):
                path=f"{prefix}[{i}]"
                t="dict" if isinstance(v, dict) else "list" if isinstance(v, list) else type(v).__name__
                out.append((path, f"[{i}]", v, t, depth))
    except Exception as e:
        window.console.log(f"flatten error {e}")
    return out

def draw_gene_inspector(x,y,w,h,gene_obj, scroll=0):
    try:
        drawRect(x+8, y+30, w-16, h-44, fill=rgb(13,18,33), border=PANEL_BORDER, borderWidth=1, roundness=6)
        gene=js_to_py(gene_obj)
        if not gene:
            drawLabel("no gene selected", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return []
        items=flatten_for_inspector(gene, "", 0, 4, 200)
        if not items:
            drawLabel("empty", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return []
        visible=items[scroll:scroll+14]
        sy=y+36
        for idx,(full_path, short_key, val, typ, dep) in enumerate(visible):
            indent=min(dep*10, 36)
            line_y=sy+idx*14
            if line_y>y+h-14:
                break
            drawLabel(truncate(short_key, 20), x+12+indent, line_y, fill=CYAN if dep==0 else WHITE, size=13, bold=dep==0, align="left-top")
            drawLabel(f"({typ})", x+112+indent, line_y, fill=MUTED, size=13, align="left-top")
            if isinstance(val, dict):
                prev=f"{{ {len(val)} keys }}"
            elif isinstance(val, list):
                # show first element hint
                if val and isinstance(val[0], dict):
                    prev=f"[ {len(val)} dicts ]"
                else:
                    prev=f"[ {len(val)} ]"
            elif isinstance(val, str):
                prev=truncate(val, 30)
            else:
                prev=truncate(str(val), 30)
            col=YELLOW if isinstance(val, (int,float)) else MUTED
            if isinstance(val, str) and len(val)>0 and val.startswith("ENS"):
                col=CYAN
            drawLabel(prev, x+170+indent, line_y, fill=col, size=13, align="left-top")
        drawLabel(f"{len(items)} paths — {scroll}/{max(0,len(items)-14)}", x+8, y+h-10, fill=MUTED, size=13, align="left-bottom")
        return items
    except Exception as e:
        window.console.log(f"inspector error {e}")
        return []

def draw_exon_map_generic(x,y,w,h,gene):
    try:
        drawRect(x+8, y+30, w-16, h-44, fill=rgb(13,18,33), border=PANEL_BORDER, borderWidth=1, roundness=6)
        gene=js_to_py(gene)
        if not gene:
            drawLabel("no data", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        if "exons" in gene and isinstance(gene["exons"], list) and gene["exons"]:
            exons=gene["exons"]
            all_starts=[]; all_ends=[]
            for tr in exons:
                if not isinstance(tr, dict):
                    continue
                for p in tr.get("position", []):
                    try:
                        all_starts.append(int(p[0])); all_ends.append(int(p[1]))
                    except:
                        pass
            if not all_starts:
                drawLabel("exons no pos", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
                return
            gmin=min(all_starts); gmax=max(all_ends)
            span=gmax-gmin if gmax!=gmin else 1
            gx=x+16; gw=w-32; base_y=y+44; base_h=h-70
            drawLine(gx, base_y+base_h/2, gx+gw, base_y+base_h/2, fill=rgb(60,70,100), lineWidth=2)
            colors=[CYAN,PINK,YELLOW,GREEN,PURPLE,ORANGE]
            for ti,tr in enumerate(exons[:6]):
                if not isinstance(tr, dict):
                    continue
                ty=base_y+10+ti*(base_h//7)
                drawLabel(truncate(tr.get("transcript",f"tr{ti}"),14), gx, ty, fill=MUTED, size=13, align="left-center")
                for p in tr.get("position", []):
                    try:
                        s=int(p[0]); e=int(p[1])
                        rx=gx+((s-gmin)/span)*gw
                        rw=((e-s)/span)*gw
                        if rw<2:
                            rw=2
                        col=colors[ti%len(colors)]
                        drawRect(rx, ty-5, rw, 10, fill=col, borderWidth=0.8, roundness=3)
                    except:
                        pass
            drawLabel(f"{gmin}-{gmax}", gx, y+h-10, fill=MUTED, size=13, align="left-bottom")
            return
        gpos=gene.get("genomic_pos")
        if not gpos:
            gpos=gene.get("genomic_pos_hg19")
        if gpos:
            if isinstance(gpos, list):
                gpos=gpos[0] if gpos else {}
            if isinstance(gpos, dict):
                drawLabel(f"chr {gpos.get('chr','?')} {gpos.get('start','?')}-{gpos.get('end','?')} strand {gpos.get('strand','?')}", x+16, y+50, fill=WHITE, size=13, align="left-top")
                gx=x+16; gw=w-32
                drawRect(gx, y+70, gw, 12, fill=rgb(30,40,65), roundness=6)
                drawRect(gx+gw*0.2, y+70, gw*0.6, 12, fill=CYAN, roundness=6)
                # try ensembl genomic
                ens=gene.get("ensembl")
                if isinstance(ens, dict) and "gene" in ens:
                    drawLabel(f"ensembl {truncate(str(ens.get('gene')),22)}", x+16, y+86, fill=MUTED, size=13, align="left-top")
                return
        # fallback: show any list field that looks like genomic intervals
        drawLabel("no exons/pos", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
    except Exception as e:
        window.console.log(f"arch error {e}")

async def resilient_pyodide_run(code_str):
    async def unwrap(res, max_depth=12):
        for _ in range(max_depth):
            if res is None:
                break
            if hasattr(res,'to_py'):
                try:
                    tmp=res.to_py()
                    if tmp is not None:
                        res=tmp
                except:
                    pass
            try:
                if hasattr(res,'__await__'):
                    res=await res
                    continue
                if hasattr(res,'then') and callable(getattr(res,'then')):
                    res=await res
                    continue
                s=str(res)
                if '<coroutine' in s.lower():
                    return None
            except:
                pass
            break
        return res
    if PYODIDE_OK and _py_ext is not None:
        for name in _py_candidates:
            try:
                fn=getattr(_py_ext, name, None)
                if fn is None:
                    continue
                raw=fn(code_str)
                res=await unwrap(raw)
                if res is None:
                    continue
                if isinstance(res,str) and '<coroutine' in res.lower():
                    continue
                return res
            except:
                continue
    try:
        if hasattr(window,'pyodide') and window.pyodide is not None:
            raw=await window.pyodide.runPythonAsync(code_str)
            res=await unwrap(raw)
            return res
    except:
        pass
    return None

async def ensure_numpy():
    try:
        if PYODIDE_OK and _py_ext is not None and hasattr(_py_ext,'loadPackage'):
            try:
                await _py_ext.loadPackage("numpy")
                return True
            except:
                pass
    except:
        pass
    try:
        if hasattr(window,'pyodide') and window.pyodide is not None and hasattr(window.pyodide,'loadPackage'):
            await window.pyodide.loadPackage("numpy")
            return True
    except:
        pass
    return False

async def fetch_json_real(url):
    try:
        resp=await window.fetch(url)
        if not resp.ok:
            raise Exception(f"HTTP {resp.status}")
        txt=await resp.text()
        if hasattr(txt,'to_py'):
            try:
                txt=txt.to_py()
            except:
                pass
        txt=str(txt)
        try:
            obj=window.JSON.parse(txt)
            return js_to_py(obj)
        except Exception as e:
            try:
                return json.loads(txt)
            except Exception as e2:
                window.console.log(f"both JSON parses failed {e} / {e2} len {len(txt)}")
                raise
    except Exception as e:
        window.console.log(f"fetch_json_real error {url}: {e}")
        raise

async def compute_dynamic_stats(app):
    scores=[]
    try:
        hits=js_to_py(app.hits)
        for h in hits:
            if isinstance(h, dict) and "_score" in h:
                try:
                    v=float(h["_score"])
                    if math.isfinite(v):
                        scores.append(v)
                except:
                    pass
    except Exception as e:
        window.console.log(f"scores collect {e}")

    try:
        if scores:
            mean=sum(scores)/len(scores)
            ssorted=sorted(scores)
            median=ssorted[len(ssorted)//2]
            mn=min(scores); mx=max(scores)
            var=sum((x-mean)**2 for x in scores)/len(scores)
            std=math.sqrt(var) if var>=0 else 0
        else:
            mean=median=mn=mx=std=0.0
        app.stats_local={"mean":mean,"median":median,"min":mn,"max":mx,"std":std,"n":len(scores)}
    except Exception as e:
        window.console.log(f"local stats {e}")
        app.stats_local={"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}

    try:
        gene=js_to_py(app.selectedGene)
        if isinstance(gene, dict):
            type_counts={}
            numeric_arrays={}
            for k,v in gene.items():
                t="list" if isinstance(v, list) else "dict" if isinstance(v, dict) else type(v).__name__
                type_counts[t]=type_counts.get(t,0)+1
                if isinstance(v, list) and v and len(v)>0:
                    # check if numeric list
                    try:
                        if all(isinstance(x,(int,float)) and math.isfinite(float(x)) for x in v[:20]):
                            numeric_arrays[k]=v[:100]
                    except:
                        pass
            app.field_type_counts=type_counts
            app.numeric_arrays=numeric_arrays
            app.discovered_keys=list(gene.keys())[:60]
        else:
            app.field_type_counts={}
            app.numeric_arrays={}
            app.discovered_keys=[]
    except Exception as e:
        window.console.log(f"type counts {e}")
        app.field_type_counts={}
        app.numeric_arrays={}
        app.discovered_keys=[]

    try:
        await ensure_numpy()
        all_nums=[float(x) for x in scores[:100] if math.isfinite(float(x))]
        try:
            for arr in list(app.numeric_arrays.values())[:1]:
                all_nums.extend([float(x) for x in arr[:50] if isinstance(x,(int,float)) and math.isfinite(float(x))])
        except:
            pass
        code=f"""
import numpy as np
arr = {all_nums}
arr = [x for x in arr if np.isfinite(x)]
if arr:
    m=float(np.mean(arr)); med=float(np.median(arr)); s=float(np.std(arr)); mn=float(np.min(arr)); mx=float(np.max(arr))
else:
    m=med=s=mn=mx=0.0
{{"mean":m,"median":med,"std":s,"min":mn,"max":mx,"n":len(arr)}}
"""
        res=await resilient_pyodide_run(code)
        res_py=js_to_py(res)
        if isinstance(res_py, dict):
            app.stats_py=res_py
        else:
            app.stats_py=app.stats_local
    except Exception as e:
        window.console.log(f"pyodide stats {e}")
        app.stats_py=app.stats_local

    try:
        facets=js_to_py(app.facets_raw)
        if isinstance(facets, dict):
            simple={}
            for fname,fdata in facets.items():
                if isinstance(fdata, dict) and "terms" in fdata:
                    terms=fdata["terms"]
                    if isinstance(terms, list):
                        d={}
                        for t in terms[:14]:
                            if isinstance(t, dict):
                                term=t.get("term"); cnt=t.get("count",0)
                                d[str(term)]=cnt
                        simple[fname]=d
            app.facets_simple=simple
        else:
            app.facets_simple={}
    except Exception as e:
        window.console.log(f"facets {e}")
        app.facets_simple={}

async def fetch_gene_detail(app, gene_id):
    try:
        app.loadingDetail=True
        # always use fields=all for full discovery - JS JSON.parse handles large payload
        url=f"https://mygene.info/v3/gene/{gene_id}?fields=all"
        data=await fetch_json_real(url)
        app.selectedGene=data
        app.selectedGeneId=str(gene_id)
        app.inspector_obj=data
        app.inspector_stack=[]
        app.inspector_scroll=0
        await compute_dynamic_stats(app)
    except Exception as e:
        window.console.log(f"detail error {gene_id}: {e}")
        app.selectedGene=None
    app.loadingDetail=False

async def query_mygene(app):
    try:
        app.loading=True
        q=app.queryText.strip() or "CDK2"
        species=app.species.strip() or "human"
        size=int(app.size)
        if size<1:
            size=10
        if size>100:
            size=100
        from_=int(app.fromOffset)
        fields=app.fieldsText.strip()
        if not fields:
            fields="symbol,name,taxid,entrezgene,ensembl.gene,type_of_gene,_score"
        # query must NOT use fields=all - use safe subset to avoid 64k blow
        if fields.strip()=="all":
            fields="symbol,name,taxid,entrezgene,ensembl.gene,type_of_gene,_score"
        facets=app.facetsText.strip() or "taxid,type_of_gene"
        sort=app.sortText.strip()
        # build url - FIX: fetch_all cannot be combined with from or sort per docs
        if app.fetchAll:
            # per docs: fetch_all ignores sort, and uses scroll_id, do not send from
            url=f"https://mygene.info/v3/query?q={q}&species={species}&size={size}&fields={fields}&facets={facets}&dotfield=false&fetch_all=true"
            if app.entrezonly:
                url+="&entrezonly=true"
            if app.ensemblonly:
                url+="&ensemblonly=true"
        else:
            url=f"https://mygene.info/v3/query?q={q}&species={species}&size={size}&from={from_}&fields={fields}&facets={facets}&dotfield=false"
            if sort:
                url+=f"&sort={sort}"
            if app.entrezonly:
                url+="&entrezonly=true"
            if app.ensemblonly:
                url+="&ensemblonly=true"
        data=await fetch_json_real(url)
        hits=safe_get(data,"hits",[])
        total=safe_get(data,"total",0)
        facets_raw=safe_get(data,"facets",{})
        max_score=safe_get(data,"max_score",0)
        scroll_id=safe_get(data,"_scroll_id",None)
        hits=js_to_py(hits)
        if not isinstance(hits, list):
            hits=[]
        app.hits=hits
        app.total=int(total) if isinstance(total,(int,float)) else 0
        app.facets_raw=js_to_py(facets_raw)
        app.max_score=max_score
        app.scroll_id=scroll_id
        app.selectedIdx=0
        try:
            all_keys=set()
            for h in hits:
                if isinstance(h, dict):
                    all_keys.update(h.keys())
            app.discovered_hit_keys=list(all_keys)[:30]
        except:
            app.discovered_hit_keys=[]
        if app.hits:
            first=js_to_py(app.hits[0])
            fid=first.get("_id") if isinstance(first, dict) else None
            if not fid and isinstance(first, dict):
                fid=first.get("entrezgene")
            if fid:
                await fetch_gene_detail(app, str(fid))
        else:
            app.selectedGene=None
        await compute_dynamic_stats(app)
    except Exception as e:
        window.console.log(f"query error {e}")
    app.loading=False

def init_audio(app):
    try:
        if PROC_OK and AudioEngine is not None:
            app.audio=AudioEngine(quality="high", seed=90210)
        else:
            app.audio=None
    except:
        app.audio=None

def play_any_sonification(app, arr=None):
    try:
        if not app.audio:
            init_audio(app)
        if app.audio:
            try:
                app.audio.resume()
            except:
                pass
            if arr is None:
                arr=app.numeric_arrays.get(next(iter(app.numeric_arrays), ""), []) if hasattr(app,'numeric_arrays') else []
                if not arr:
                    hits=js_to_py(app.hits)
                    arr=[h.get("_score",0) for h in hits[:12] if isinstance(h,dict)]
            for i,v in enumerate(arr[:14]):
                try:
                    fv=float(v)
                    if not math.isfinite(fv):
                        continue
                    app.audio.play("coin.collect", seed=int(abs(fv))+i*13, spatial=True, position={"x":(i/14)-0.5,"y":0})
                except:
                    try:
                        app.audio.play("character.jump", seed=i*37, spatial=False, position={"x":0,"y":0})
                    except:
                        pass
    except Exception as e:
        window.console.log(f"sonify {e}")

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=30; app.background=BG
    app.queryText="CDK2"
    app.species="human"
    app.speciesOptions=["human","mouse","rat","zebrafish","all"]
    app.size=25; app.fromOffset=0
    app.fieldsText="symbol,name,taxid,entrezgene,ensembl.gene,type_of_gene,_score"
    app.facetsText="taxid,type_of_gene"
    app.sortText="_score"
    app.entrezonly=False; app.ensemblonly=False; app.fetchAll=False
    app.hits=[]; app.total=0; app.facets_raw={}; app.facets_simple={}; app.max_score=0; app.scroll_id=None
    app.discovered_hit_keys=[]; app.discovered_keys=[]
    app.selectedIdx=0; app.selectedGene=None; app.selectedGeneId=None
    app.inspector_obj=None; app.inspector_stack=[]; app.inspector_items=[]
    app.loading=False; app.loadingDetail=False
    app.stats_local={"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}
    app.stats_py={"mean":0}
    app.field_type_counts={}; app.numeric_arrays={}
    app.inspector_scroll=0; app.vizMode="bars"; app.draggingSize=False; app.audio=None; app.focus=None
    init_audio(app)
    aio.run(query_mygene(app))

def onStep(app):
    pass

def onMousePress(app,mx,my):
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+28, SEARCH_W-16, 22):
        app.focus="query"; return
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+54, 90, 18):
        app.focus="species"; return
    if pointInRect(mx,my,SEARCH_X+104, SEARCH_Y+54, SEARCH_W-112, 18):
        app.focus="fields"; return
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+76, 90, 18):
        app.focus="facets"; return
    if pointInRect(mx,my,SEARCH_X+104, SEARCH_Y+76, 70, 18):
        app.focus="sort"; return
    if app.focus:
        if not (pointInRect(mx,my,SEARCH_X,SEARCH_Y,SEARCH_W,SEARCH_H) or pointInRect(mx,my,DETAIL_X,DETAIL_Y,DETAIL_W,DETAIL_H)):
            # keep focus only if click outside query area but not inspector navigation - clear
            if not pointInRect(mx,my,SEARCH_X,SEARCH_Y,SEARCH_W,SEARCH_H):
                # don't clear if clicking other panels for actions
                if pointInRect(mx,my,RESULTS_X,RESULTS_Y,RESULTS_W,RESULTS_H) or pointInRect(mx,my,FACET_X,FACET_Y,FACET_W,FACET_H):
                    pass
                else:
                    # delay clear, let other handlers run
                    pass

    sx=SEARCH_X+8; sy=SEARCH_Y+98
    for i,sp in enumerate(app.speciesOptions[:4]):
        if pointInRect(mx,my,sx+i*56,sy,52,18):
            app.species=sp; return
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+122, 64, 20):
        app.fromOffset=0
        aio.run(query_mygene(app)); return
    if pointInRect(mx,my,SEARCH_X+76, SEARCH_Y+122, 22, 20):
        app.size=max(5,app.size-5); return
    if pointInRect(mx,my,SEARCH_X+100, SEARCH_Y+122, 22, 20):
        app.size=min(100,app.size+5); return
    if pointInRect(mx,my,SEARCH_X+126, SEARCH_Y+122, 32, 18):
        app.entrezonly=not app.entrezonly; return
    if pointInRect(mx,my,SEARCH_X+162, SEARCH_Y+122, 32, 18):
        app.ensemblonly=not app.ensemblonly; return
    if pointInRect(mx,my,SEARCH_X+198, SEARCH_Y+122, 32, 18):
        app.fetchAll=not app.fetchAll; 
        if app.fetchAll:
            app.fromOffset=0
        return

    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+148, SEARCH_W-16, 10):
        rel=clamp((mx-(SEARCH_X+8))/(SEARCH_W-16),0,1)
        app.size=int(5+rel*95); app.draggingSize=True; return

    if pointInRect(mx,my,RESULTS_X+8, RESULTS_Y+28, 40, 18):
        app.fromOffset=max(0,app.fromOffset-app.size)
        if app.fetchAll:
            app.fetchAll=False
        aio.run(query_mygene(app)); return
    if pointInRect(mx,my,RESULTS_X+52, RESULTS_Y+28, 40, 18):
        app.fromOffset+=app.size
        if app.fetchAll:
            app.fetchAll=False
        aio.run(query_mygene(app)); return
    if pointInRect(mx,my,RESULTS_X+98, RESULTS_Y+28, 28, 18):
        app.inspector_scroll=max(0,app.inspector_scroll-14); return
    if pointInRect(mx,my,RESULTS_X+130, RESULTS_Y+28, 36, 18):
        app.inspector_scroll+=14; return

    if pointInRect(mx,my,RESULTS_X+8, RESULTS_Y+52, RESULTS_W-16, RESULTS_H-60):
        idx=int((my-(RESULTS_Y+52))//16)
        hits=js_to_py(app.hits)
        if 0 <= idx < len(hits):
            app.selectedIdx=idx
            first=js_to_py(hits[idx])
            gid=first.get("_id") if isinstance(first, dict) else None
            if not gid and isinstance(first, dict):
                gid=first.get("entrezgene")
            if gid:
                aio.run(fetch_gene_detail(app,str(gid)))
        return

    # inspector click to drill into ensembl etc
    if pointInRect(mx,my,DETAIL_X+8, DETAIL_Y+30, DETAIL_W-16, DETAIL_H-44):
        try:
            idx=int((my-(DETAIL_Y+36))//14)
            items=app.inspector_items
            if items and 0 <= idx < len(items):
                path, key, val, typ, dep = items[idx+app.inspector_scroll] if idx+app.inspector_scroll < len(items) else items[idx]
                if isinstance(val, (dict,list)) and len(str(val))>2:
                    # push current
                    if app.inspector_obj is not None:
                        app.inspector_stack.append((app.inspector_obj, app.inspector_scroll))
                    app.inspector_obj=val
                    app.inspector_scroll=0
        except Exception as e:
            window.console.log(f"inspector click {e}")
        return

    if pointInRect(mx,my,FACET_X+8, FACET_Y+28, 32, 16):
        app.vizMode="bars"; return
    if pointInRect(mx,my,FACET_X+44, FACET_Y+28, 32, 16):
        app.vizMode="pie"; return
    if pointInRect(mx,my,FACET_X+80, FACET_Y+28, 36, 16):
        app.vizMode="list"; return

    if pointInRect(mx,my,TYPES_X+8, TYPES_Y+28, 48, 18):
        play_any_sonification(app); return
    if pointInRect(mx,my,TYPES_X+60, TYPES_Y+28, 48, 18):
        aio.run(compute_dynamic_stats(app)); return

    if pointInRect(mx,my,ARCH_X+8, ARCH_Y+28, 48, 18):
        play_any_sonification(app); return
    if pointInRect(mx,my,DETAIL_X+8, DETAIL_Y+28, 40, 18):
        # back
        if app.inspector_stack:
            prev_obj, prev_scroll = app.inspector_stack.pop()
            app.inspector_obj=prev_obj
            app.inspector_scroll=prev_scroll
        else:
            app.inspector_obj=app.selectedGene
            app.inspector_scroll=0
        return
    if pointInRect(mx,my,DETAIL_X+52, DETAIL_Y+28, 40, 18):
        app.inspector_scroll=max(0,app.inspector_scroll-14); return
    if pointInRect(mx,my,DETAIL_X+96, DETAIL_Y+28, 40, 18):
        app.inspector_scroll+=14; return

    if pointInRect(mx,my,STATS_X+8, STATS_Y+28, 64, 18):
        aio.run(compute_dynamic_stats(app)); return

def onMouseDrag(app,mx,my):
    if app.draggingSize:
        rel=clamp((mx-(SEARCH_X+8))/(SEARCH_W-16),0,1)
        app.size=int(5+rel*95)

def onMouseRelease(app,mx,my):
    app.draggingSize=False

def onKeyPress(app,key):
    try:
        if app.focus=="query":
            if key=="Backspace":
                app.queryText=app.queryText[:-1]
            elif key=="Enter":
                app.fromOffset=0
                aio.run(query_mygene(app))
            elif key=="Escape":
                app.focus=None
            elif len(key)==1 and len(app.queryText)<60:
                app.queryText+=key
            return
        if app.focus=="species":
            if key=="Backspace":
                app.species=app.species[:-1]
            elif key=="Enter":
                app.focus=None; aio.run(query_mygene(app))
            elif key=="Escape":
                app.focus=None
            elif len(key)==1 and len(app.species)<30:
                app.species+=key
            return
        if app.focus=="fields":
            if key=="Backspace":
                app.fieldsText=app.fieldsText[:-1]
            elif key=="Enter":
                app.focus=None
            elif key=="Escape":
                app.focus=None
            elif len(key)==1 and len(app.fieldsText)<140:
                app.fieldsText+=key
            return
        if app.focus=="facets":
            if key=="Backspace":
                app.facetsText=app.facetsText[:-1]
            elif key=="Enter":
                app.focus=None
            elif key=="Escape":
                app.focus=None
            elif len(key)==1 and len(app.facetsText)<80:
                app.facetsText+=key
            return
        if app.focus=="sort":
            if key=="Backspace":
                app.sortText=app.sortText[:-1]
            elif key=="Enter":
                app.focus=None
            elif key=="Escape":
                app.focus=None
            elif len(key)==1 and len(app.sortText)<30:
                app.sortText+=key
            return
        if key==" ":
            app.fromOffset=0
            aio.run(query_mygene(app))
        elif key.lower()=="n":
            hits=js_to_py(app.hits)
            if hits and app.selectedIdx < len(hits)-1:
                app.selectedIdx+=1
                gid=js_to_py(hits[app.selectedIdx]).get("_id") if isinstance(js_to_py(hits[app.selectedIdx]), dict) else None
                if gid:
                    aio.run(fetch_gene_detail(app,str(gid)))
        elif key.lower()=="p":
            if app.selectedIdx>0:
                app.selectedIdx-=1
                hits=js_to_py(app.hits)
                if hits:
                    gid=js_to_py(hits[app.selectedIdx]).get("_id") if isinstance(js_to_py(hits[app.selectedIdx]), dict) else None
                    if gid:
                        aio.run(fetch_gene_detail(app,str(gid)))
        elif key.lower()=="s":
            play_any_sonification(app)
        elif key.lower()=="b":
            if app.inspector_stack:
                prev_obj, prev_scroll = app.inspector_stack.pop()
                app.inspector_obj=prev_obj
                app.inspector_scroll=prev_scroll
    except Exception as e:
        window.console.log(f"keypress {e}")

def redrawAll(app):
    try:
        drawRect(0,0,W,H,fill=BG)
        drawRect(0,0,W,HEADER_H,fill=rgb(18,24,44),border=PANEL_BORDER,borderWidth=1)
        # header - no error in UI
        drawLabel("MyGene Explorer • v3 • data discovery", 20, 14, fill=WHITE, size=18, bold=True, align="left-top")
        # status line - no error text, only ready info
        total_info=f"{len(js_to_py(app.hits))}/{app.total}" if app.total else f"{len(js_to_py(app.hits))}"
        drawLabel(f"{app.queryText} | {app.species} | {app.size} | {total_info}", 20, 36, fill=MUTED, size=13, align="left-top")
        if app.loading:
            drawLabel("loading", W-80, 16, fill=YELLOW, size=13, bold=True, align="left-top")

        drawPanel(SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H, "QUERY")
        drawRect(SEARCH_X+8, SEARCH_Y+28, SEARCH_W-16, 20, fill=rgb(13,18,33), border=CYAN if app.focus=="query" else PANEL_BORDER, borderWidth=1.2, roundness=6)
        drawLabel(app.queryText or "CDK2", SEARCH_X+12, SEARCH_Y+38, fill=WHITE if app.queryText else MUTED, size=13, align="left-center")
        drawRect(SEARCH_X+8, SEARCH_Y+54, 90, 18, fill=rgb(13,18,33), border=CYAN if app.focus=="species" else PANEL_BORDER, borderWidth=1, roundness=5)
        drawLabel(truncate(app.species,10), SEARCH_X+12, SEARCH_Y+63, fill=WHITE, size=13, align="left-center")
        drawRect(SEARCH_X+104, SEARCH_Y+54, SEARCH_W-112, 18, fill=rgb(13,18,33), border=CYAN if app.focus=="fields" else PANEL_BORDER, borderWidth=1, roundness=5)
        drawLabel(truncate(app.fieldsText,20), SEARCH_X+108, SEARCH_Y+63, fill=WHITE, size=13, align="left-center")
        drawRect(SEARCH_X+8, SEARCH_Y+76, 90, 18, fill=rgb(13,18,33), border=CYAN if app.focus=="facets" else PANEL_BORDER, borderWidth=1, roundness=5)
        drawLabel(truncate(app.facetsText,10), SEARCH_X+12, SEARCH_Y+85, fill=WHITE, size=13, align="left-center")
        drawRect(SEARCH_X+104, SEARCH_Y+76, 70, 18, fill=rgb(13,18,33), border=CYAN if app.focus=="sort" else PANEL_BORDER, borderWidth=1, roundness=5)
        drawLabel(truncate(app.sortText,8), SEARCH_X+108, SEARCH_Y+85, fill=WHITE, size=13, align="left-center")

        sx=SEARCH_X+8; sy=SEARCH_Y+98
        for i,sp in enumerate(app.speciesOptions[:4]):
            active=sp==app.species
            draw_button(sx+i*56, sy, 52, 18, sp[:5], active=active, color=CYAN if active else None)
        draw_button(SEARCH_X+8, SEARCH_Y+122, 64, 20, "SEARCH", active=True, color=GREEN)
        draw_button(SEARCH_X+76, SEARCH_Y+122, 22, 20, "-", active=False)
        draw_button(SEARCH_X+100, SEARCH_Y+122, 22, 20, "+", active=False)
        draw_button(SEARCH_X+126, SEARCH_Y+122, 32, 18, f"E:{'1' if app.entrezonly else '0'}", active=app.entrezonly, color=PURPLE if app.entrezonly else None)
        draw_button(SEARCH_X+162, SEARCH_Y+122, 32, 18, f"En:{'1' if app.ensemblonly else '0'}", active=app.ensemblonly, color=PURPLE if app.ensemblonly else None)
        draw_button(SEARCH_X+198, SEARCH_Y+122, 32, 18, f"All:{'1' if app.fetchAll else '0'}", active=app.fetchAll, color=ORANGE if app.fetchAll else None)
        drawRect(SEARCH_X+8, SEARCH_Y+148, SEARCH_W-16, 8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=5)
        rel=(app.size-5)/95 if 95 else 0
        drawRect(SEARCH_X+8, SEARCH_Y+148, rel*(SEARCH_W-16), 8, fill=ORANGE, roundness=5)
        drawCircle(SEARCH_X+8+rel*(SEARCH_W-16), SEARCH_Y+152, 5, fill=WHITE, border=ORANGE, borderWidth=1.2)

        drawPanel(RESULTS_X, RESULTS_Y, RESULTS_W, RESULTS_H, f"HITS {len(js_to_py(app.hits))}/{app.total}")
        draw_button(RESULTS_X+8, RESULTS_Y+28, 40, 18, "PREV", active=False)
        draw_button(RESULTS_X+52, RESULTS_Y+28, 40, 18, "NEXT", active=False)
        draw_button(RESULTS_X+98, RESULTS_Y+28, 28, 18, "UP", active=False)
        draw_button(RESULTS_X+130, RESULTS_Y+28, 36, 18, "DOWN", active=False)
        ly=RESULTS_Y+52
        hits=js_to_py(app.hits)
        for i,hit in enumerate(hits[:9]):
            by=ly+i*16
            if by>RESULTS_Y+RESULTS_H-8:
                break
            sel=i==app.selectedIdx
            fillc=rgb(34,42,68) if sel else rgb(18,24,42)
            drawRect(RESULTS_X+8, by, RESULTS_W-16, 14, fill=fillc, border=CYAN if sel else PANEL_BORDER, borderWidth=1 if sel else 0.6, roundness=4)
            if isinstance(hit, dict):
                sym=hit.get("symbol","-"); score=hit.get("_score",0)
                tax=hit.get("taxid","")
                try:
                    sc_f=float(score)
                except:
                    sc_f=0
                drawLabel(truncate(sym,9), RESULTS_X+10, by+7, fill=CYAN if sel else WHITE, size=13, bold=sel, align="left-center")
                drawLabel(f"{sc_f:.1f}", RESULTS_X+68, by+7, fill=YELLOW, size=13, align="left-center")
                # show type_of_gene and ensembl
                tgene=hit.get("type_of_gene","")
                ens=hit.get("ensembl",{})
                if isinstance(ens, dict):
                    ens_g=ens.get("gene","")
                else:
                    ens_g=""
                extra=truncate(tgene,8) if tgene else truncate(str(ens_g),10)
                drawLabel(extra, RESULTS_X+108, by+7, fill=MUTED, size=13, align="left-center")
                drawLabel(f"{tax}", RESULTS_X+168, by+7, fill=MUTED, size=13, align="left-center")
            else:
                drawLabel(truncate(str(hit),26), RESULTS_X+10, by+7, fill=WHITE, size=13, align="left-center")

        drawPanel(DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H, f"GENE {app.selectedGeneId or ''}")
        draw_button(DETAIL_X+8, DETAIL_Y+28, 40, 18, "BACK", active=len(app.inspector_stack)>0, color=PURPLE if app.inspector_stack else None)
        draw_button(DETAIL_X+52, DETAIL_Y+28, 40, 18, "UP", active=False)
        draw_button(DETAIL_X+96, DETAIL_Y+28, 40, 18, "DN", active=False)
        if app.loadingDetail:
            drawLabel("loading", DETAIL_X+DETAIL_W/2, DETAIL_Y+DETAIL_H/2, fill=YELLOW, size=13, align="center")
            app.inspector_items=[]
        else:
            obj_to_show = app.inspector_obj if app.inspector_obj is not None else app.selectedGene
            items=draw_gene_inspector(DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H, obj_to_show, app.inspector_scroll)
            app.inspector_items=items

        drawPanel(FACET_X, FACET_Y, FACET_W, FACET_H, "FACETS")
        draw_button(FACET_X+8, FACET_Y+28, 32, 16, "BAR", active=app.vizMode=="bars")
        draw_button(FACET_X+44, FACET_Y+28, 32, 16, "PIE", active=app.vizMode=="pie")
        draw_button(FACET_X+80, FACET_Y+28, 36, 16, "LIST", active=app.vizMode=="list")
        facet_to_show=None
        facet_name=""
        try:
            if app.facets_simple:
                facet_name=next(iter(app.facets_simple))
                facet_to_show=app.facets_simple[facet_name]
                drawLabel(facet_name, FACET_X+124, FACET_Y+36, fill=MUTED, size=13, align="left-center")
        except:
            pass
        if facet_to_show:
            chart_x=FACET_X+8; chart_y=FACET_Y+48; chart_w=FACET_W-16; chart_h=FACET_H-56
            if app.vizMode=="bars":
                draw_bar_chart(chart_x, chart_y, chart_w, chart_h, facet_to_show)
            elif app.vizMode=="pie":
                draw_pie_chart(chart_x, chart_y, chart_w, chart_h, facet_to_show)
            else:
                try:
                    sy=chart_y+6
                    for lbl,val in list(facet_to_show.items())[:8]:
                        drawLabel(f"{truncate(str(lbl),12)}: {int(val)}", chart_x+6, sy, fill=WHITE, size=13, align="left-top")
                        sy+=16
                except:
                    pass

        drawPanel(TYPES_X, TYPES_Y, TYPES_W, TYPES_H, "FIELD TYPES")
        draw_button(TYPES_X+8, TYPES_Y+28, 48, 18, "PLAY", active=False, color=CYAN)
        draw_button(TYPES_X+60, TYPES_Y+28, 48, 18, "CALC", active=False, color=GREEN)
        try:
            if app.field_type_counts:
                draw_bar_chart(TYPES_X+8, TYPES_Y+50, TYPES_W-16, TYPES_H-58, app.field_type_counts)
                if app.discovered_keys:
                    drawLabel(f"{len(app.discovered_keys)} keys", TYPES_X+8, TYPES_Y+TYPES_H-10, fill=MUTED, size=13, align="left-bottom")
        except Exception as e:
            window.console.log(f"types {e}")

        drawPanel(ARCH_X, ARCH_Y, ARCH_W, ARCH_H, "GENOMIC")
        draw_button(ARCH_X+8, ARCH_Y+28, 48, 18, "PLAY", active=False, color=YELLOW)
        draw_exon_map_generic(ARCH_X, ARCH_Y, ARCH_W, ARCH_H, app.selectedGene)

        drawPanel(STATS_X, STATS_Y, STATS_W, STATS_H, "STATISTICS")
        draw_button(STATS_X+8, STATS_Y+28, 56, 18, "CALC", active=False, color=GREEN)
        tx=STATS_X+12; ty=STATS_Y+50
        drawLabel("metric", tx, ty, fill=MUTED, size=13, bold=True, align="left-top")
        drawLabel("value", tx+90, ty, fill=MUTED, size=13, bold=True, align="left-top")
        drawLabel("detail", tx+170, ty, fill=MUTED, size=13, bold=True, align="left-top")
        ty+=14
        try:
            sl=js_to_py(app.stats_local); sp=js_to_py(app.stats_py)
            if not isinstance(sl, dict):
                sl={"mean":0,"n":0}
            if not isinstance(sp, dict):
                sp=sl
            rows=[
                ("n", f"{sl.get('n',0)}", f"total {app.total}"),
                ("mean", f"{sl.get('mean',0):.2f}", f"py {sp.get('mean',0):.2f}"),
                ("median", f"{sl.get('median',0):.2f}", f"py {sp.get('median',0):.2f}"),
                ("std", f"{sl.get('std',0):.2f}", f"min {sl.get('min',0):.1f}"),
                ("max", f"{sl.get('max',0):.1f}", f"max {app.max_score:.1f}" if isinstance(app.max_score,(int,float)) else ""),
                ("arrays", f"{len(app.numeric_arrays)}", f"keys {len(app.discovered_keys)}"),
            ]
            for i,(k,v,d) in enumerate(rows):
                ry=ty+i*16
                if ry>STATS_Y+STATS_H-12:
                    break
                drawRect(tx-4, ry-1, STATS_W-24, 14, fill=rgb(18,24,42) if i%2==0 else rgb(22,28,48), roundness=4)
                drawLabel(k, tx, ry+7, fill=WHITE, size=13, align="left-center")
                drawLabel(v, tx+90, ry+7, fill=YELLOW, size=13, bold=True, align="left-center")
                drawLabel(truncate(d,20), tx+170, ry+7, fill=MUTED, size=13, align="left-center")
        except Exception as e:
            window.console.log(f"stats {e}")

        drawLabel("click query to edit • n/p next/prev • s play • b back in inspector", W//2, H-10, fill=MUTED, size=13, align="center-bottom")
    except Exception as e:
        try:
            window.console.log(f"redrawAll error: {e}")
        except:
            pass
