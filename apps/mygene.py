from scs import *
from browser import aio, window
import math, random, json, traceback

try:
    from extensions.fetch import fetch_json as _ext_fetch_json, fetch as _ext_fetch
    EXT_FETCH_OK = True
except Exception:
    EXT_FETCH_OK = False
    _ext_fetch_json = None
    _ext_fetch = None

try:
    from extensions.proc_audio import AudioEngine
    PROC_OK = True
except Exception:
    PROC_OK = False
    AudioEngine = None

try:
    import extensions.pyodide as _py_ext
    PYODIDE_EXT_OK = True
    _py_candidates = ['run_python_async','run_python','run','exec','evaluate','run_code','execute','runPythonAsync']
except Exception:
    PYODIDE_EXT_OK = False
    _py_ext = None
    _py_candidates = []

W, H = 1050, 700
SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H = 16, 78, 310, 170
RESULTS_X, RESULTS_Y, RESULTS_W, RESULTS_H = 16, 258, 310, 200
DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H = 340, 78, 344, 230
GO_X, GO_Y, GO_W, GO_H = 700, 78, 334, 174
PATH_X, PATH_Y, PATH_W, PATH_H = 700, 262, 334, 196
EXON_X, EXON_Y, EXON_W, EXON_H = 16, 470, 514, 214
STATS_X, STATS_Y, STATS_W, STATS_H = 546, 470, 488, 214

BG = rgb(11, 15, 27)
PANEL_BG = rgb(20, 25, 42)
PANEL_BORDER = rgb(48, 58, 90)
PANEL_HEAD = rgb(30, 37, 63)
CYAN = rgb(88, 240, 255)
PINK = rgb(255, 110, 180)
YELLOW = rgb(255, 230, 110)
GREEN = rgb(110, 255, 170)
PURPLE = rgb(160, 120, 255)
ORANGE = rgb(255, 160, 80)
WHITE = rgb(235, 242, 255)
MUTED = rgb(150, 165, 195)

def pointInRect(px, py, rx, ry, rw, rh):
    return rx <= px <= rx+rw and ry <= py <= ry+rh

def clamp(v, a, b):
    return max(a, min(b, v))

def truncate(s, n):
    try:
        s = str(s)
        return s if len(s) <= n else s[:n-1] + "\u2026"
    except:
        return ""

def js_to_py(o):
    try:
        if o is None:
            return None
        if isinstance(o, (str, int, float, bool)):
            return o
        if isinstance(o, dict):
            return {k: js_to_py(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [js_to_py(v) for v in o]
        try:
            if window.Array.isArray(o):
                return [js_to_py(o[i]) for i in range(o.length)]
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
            d = {}
            for k in keys:
                ks = str(k)
                try:
                    d[ks] = js_to_py(o[k])
                except:
                    pass
            if d:
                return d
        except:
            pass
        return o
    except:
        return o

def safe_get(d, k, default=None):
    try:
        if isinstance(d, dict):
            return d.get(k, default)
        return default
    except:
        return default

def drawPanel(x, y, w, h, title):
    drawRect(x, y, w, h, fill=PANEL_BG, border=PANEL_BORDER, borderWidth=1.2, roundness=10)
    drawRect(x+1, y+1, w-2, 20, fill=PANEL_HEAD, roundness=8)
    drawLabel(title, x+12, y+11, fill=MUTED, size=13, bold=True, align="left-center")

def draw_button(x, y, w, h, label, active=False, color=None):
    fillc = color if color else (CYAN if active else rgb(38, 46, 74))
    borderc = WHITE if active else PANEL_BORDER
    drawRect(x, y, w, h, fill=fillc, border=borderc, borderWidth=1.2, roundness=7)
    fc = rgb(0,0,0) if active else WHITE
    drawLabel(label, x+w/2, y+h/2, fill=fc, size=13, bold=active, align="center")

def draw_bar_chart(x, y, w, h, data_dict, max_val=None, color_map=None):
    try:
        data_dict = js_to_py(data_dict)
        if not isinstance(data_dict, dict) or not data_dict:
            drawLabel("no data", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        vals = []
        for v in data_dict.values():
            try:
                vals.append(float(v))
            except:
                vals.append(0)
        if not vals:
            return
        if max_val is None:
            max_val = max(vals) if vals else 1
            if max_val < 1:
                max_val = 1
        bar_area_w = w - 70
        count = len(vals)
        bar_h = (h - 20) / count - 6 if count else 20
        if bar_h < 10:
            bar_h = 10
        i = 0
        for lbl, val in data_dict.items():
            try:
                fv = float(val)
            except:
                fv = 0
            by = y + 10 + i*(bar_h+6)
            bw = (fv / max_val) * bar_area_w if max_val else 0
            col = color_map.get(lbl, CYAN) if color_map else CYAN
            drawRect(x+60, by, bar_area_w, bar_h, fill=rgb(18,24,42), roundness=4)
            drawRect(x+60, by, bw, bar_h, fill=col, roundness=4)
            drawLabel(truncate(lbl, 12), x+2, by+bar_h/2, fill=WHITE, size=13, align="left-center")
            drawLabel(str(int(fv)), x+62+bar_area_w+4, by+bar_h/2, fill=MUTED, size=13, align="left-center")
            i+=1
    except Exception as e:
        window.console.log(f"bar chart error: {e}")

def draw_pie_chart(x, y, w, h, data_dict, color_map=None):
    try:
        data_dict = js_to_py(data_dict)
        if not isinstance(data_dict, dict):
            return
        vals = [float(v) for v in data_dict.values() if float(v)>0]
        if not vals:
            return
        total = sum(vals)
        cx = x + w*0.42
        cy = y + h*0.5 + 6
        r = min(w*0.36, h*0.38)
        start_ang = -90
        colors = [CYAN, PINK, YELLOW, GREEN, PURPLE, ORANGE]
        i = 0
        for lbl, val in data_dict.items():
            try:
                fv = float(val)
            except:
                continue
            if fv <=0:
                continue
            ang = (fv/total)*360
            col = color_map.get(lbl, colors[i%len(colors)]) if color_map else colors[i%len(colors)]
            pts = [(cx, cy)]
            steps = max(2, int(ang/6))
            for s in range(steps+1):
                a = math.radians(start_ang + (s/steps)*ang)
                pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
            try:
                drawPolygon(*pts, fill=col, border=rgb(10,14,26), borderWidth=1)
            except:
                pass
            start_ang += ang
            i+=1
        lx = x + w*0.78
        ly = y + 14
        j=0
        for lbl, val in data_dict.items():
            try:
                fv = float(val)
            except:
                continue
            if fv<=0:
                continue
            col = color_map.get(lbl, colors[j%len(colors)]) if color_map else colors[j%len(colors)]
            drawRect(lx, ly+j*22, 10, 10, fill=col, roundness=2)
            drawLabel(f"{lbl}:{int(fv)}", lx+14, ly+j*22+5, fill=WHITE, size=13, align="left-center")
            j+=1
    except Exception as e:
        window.console.log(f"pie error: {e}")

def draw_exon_map(x, y, w, h, gene):
    try:
        drawRect(x+8, y+30, w-16, h-44, fill=rgb(13,18,33), border=PANEL_BORDER, borderWidth=1, roundness=6)
        gene = js_to_py(gene)
        if not gene or "exons" not in gene:
            drawLabel("select gene", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        exons = gene.get("exons", [])
        if not exons:
            drawLabel("no exons", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        all_starts = []
        all_ends = []
        for tr in exons:
            if not isinstance(tr, dict):
                continue
            for p in tr.get("position", []):
                try:
                    all_starts.append(int(p[0])); all_ends.append(int(p[1]))
                except:
                    pass
        gmin = min(all_starts) if all_starts else 0
        gmax = max(all_ends) if all_ends else gmin+1000
        span = gmax - gmin if (gmax-gmin)!=0 else 1
        gx = x+16
        gw = w-32
        base_y = y+44
        base_h = h-70
        drawLine(gx, base_y+base_h/2, gx+gw, base_y+base_h/2, fill=rgb(60,70,100), lineWidth=2)
        colors = [CYAN, PINK, YELLOW, GREEN, PURPLE, ORANGE]
        for ti, tr in enumerate(exons[:5]):
            if not isinstance(tr, dict):
                continue
            ty = base_y + 10 + ti*(base_h//6)
            drawLabel(truncate(tr.get("transcript", f"tr{ti}"),14), gx, ty, fill=MUTED, size=13, align="left-center")
            for p in tr.get("position", []):
                try:
                    s = int(p[0]); e = int(p[1])
                    rx = gx + ((s-gmin)/span)*gw
                    rw = ((e-s)/span)*gw
                    if rw < 2:
                        rw=2
                    col = colors[ti%len(colors)]
                    drawRect(rx, ty-5, rw, 10, fill=col, border=WHITE if tr.get("cdsstart") else col, borderWidth=0.8, roundness=3)
                except:
                    pass
        drawLabel(f"{gmin}-{gmax}", gx, y+h-10, fill=MUTED, size=13, align="left-bottom")
    except Exception as e:
        window.console.log(f"exon map error: {e}")

def draw_gene_detail(x, y, w, h, gene):
    try:
        gene = js_to_py(gene)
        if not gene:
            drawLabel("no gene", x+w/2, y+h/2, fill=MUTED, size=14, bold=True, align="center")
            return
        sy = y+30
        sym = gene.get("symbol","-")
        name = gene.get("name","-")
        drawLabel(f"{sym}", x+12, sy, fill=CYAN, size=16, bold=True, align="left-top")
        drawLabel(truncate(name, 32), x+12, sy+20, fill=WHITE, size=13, align="left-top")
        sy+=44
        entrez = gene.get("entrezgene","-")
        tax = gene.get("taxid","")
        gtype = gene.get("type_of_gene","")
        ens = gene.get("ensembl",{})
        ens_g = ens.get("gene","") if isinstance(ens, dict) else ""
        drawLabel(f"Entrez: {entrez}  Tax: {tax}", x+12, sy, fill=MUTED, size=13, align="left-top")
        sy+=20
        drawLabel(f"Ensembl: {truncate(ens_g,22)}", x+12, sy, fill=MUTED, size=13, align="left-top")
        sy+=20
        drawLabel(f"Type: {gtype}", x+12, sy, fill=GREEN, size=13, bold=True, align="left-top")
        sy+=24
        gpos = gene.get("genomic_pos", {})
        if isinstance(gpos, dict):
            drawLabel(f"Chr {gpos.get('chr','?')} {gpos.get('start','?')}-{gpos.get('end','?')}", x+12, sy, fill=YELLOW, size=13, align="left-top")
        elif isinstance(gpos, list) and gpos:
            gp = gpos[0]
            if isinstance(gp, dict):
                drawLabel(f"Chr {gp.get('chr','?')} {gp.get('start','?')}-{gp.get('end','?')}", x+12, sy, fill=YELLOW, size=13, align="left-top")
        sy+=24
        summary = gene.get("summary","")
        if summary:
            words = summary.split()
            cur=""; lines=[]
            for wd in words:
                if len(cur)+len(wd)+1 < 44:
                    cur = cur+" "+wd if cur else wd
                else:
                    lines.append(cur); cur=wd
                if len(lines)>=4:
                    break
            if cur and len(lines)<4:
                lines.append(cur)
            for i, ln in enumerate(lines[:4]):
                drawLabel(truncate(ln,44), x+12, sy+i*16, fill=WHITE, size=13, align="left-top")
    except Exception as e:
        window.console.log(f"gene detail error: {e}")

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
    if PYODIDE_EXT_OK and _py_ext is not None:
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
        if PYODIDE_EXT_OK and _py_ext is not None and hasattr(_py_ext,'loadPackage'):
            try:
                await _py_ext.loadPackage("numpy")
                window.console.log("numpy loaded via ext.loadPackage")
                return True
            except Exception as e:
                window.console.log(f"ext.loadPackage fail {e}")
    except:
        pass
    try:
        if hasattr(window,'pyodide') and window.pyodide is not None and hasattr(window.pyodide,'loadPackage'):
            await window.pyodide.loadPackage("numpy")
            window.console.log("numpy loaded via window.pyodide")
            return True
    except Exception as e:
        window.console.log(f"window.pyodide.loadPackage fail {e}")
    return False

async def compute_stats_pyodide(app):
    scores=[]
    try:
        hits_py = js_to_py(app.hits)
        for h in hits_py:
            if isinstance(h, dict):
                sc=h.get("_score")
                if sc is not None:
                    scores.append(float(sc))
    except Exception as e:
        window.console.log(f"score collect error: {e}")
        scores=[]
    try:
        if scores:
            mean = sum(scores)/len(scores)
            ssorted = sorted(scores)
            median = ssorted[len(ssorted)//2]
            mn = min(scores); mx = max(scores)
            var = sum((x-mean)**2 for x in scores)/len(scores)
            std = math.sqrt(var)
        else:
            mean=median=mn=mx=std=0.0
        app.stats_local = {"mean": mean, "median": median, "min": mn, "max": mx, "std": std, "n": len(scores)}
    except Exception as e:
        window.console.log(f"local stats error: {e}")
        app.stats_local = {"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}

    try:
        await ensure_numpy()
        code = f"""
import numpy as np
scores = {scores}
if scores:
    mean = float(np.mean(scores))
    median = float(np.median(scores))
    std = float(np.std(scores))
else:
    mean = median = std = 0.0
{{"mean": mean, "median": median, "std": std, "n": len(scores)}}
"""
        res = await resilient_pyodide_run(code)
        res_py = js_to_py(res)
        if isinstance(res_py, dict):
            app.stats_py = res_py
        else:
            app.stats_py = app.stats_local
    except Exception as e:
        window.console.log(f"pyodide compute error: {e} {traceback.format_exc()[:120]}")
        app.stats_py = app.stats_local

    try:
        gene_py = js_to_py(app.selectedGene)
        if gene_py and "exons" in gene_py:
            lens=[]
            for tr in gene_py["exons"]:
                if not isinstance(tr, dict):
                    continue
                for p in tr.get("position", []):
                    try:
                        lens.append(int(p[1])-int(p[0]))
                    except:
                        pass
            app.exon_lengths = lens[:64]
            if lens:
                app.exon_stats = {"count": len(lens), "mean": sum(lens)/len(lens), "max": max(lens), "min": min(lens)}
            else:
                app.exon_stats = {"count":0,"mean":0,"max":0,"min":0}
        else:
            app.exon_lengths=[]; app.exon_stats={"count":0,"mean":0,"max":0,"min":0}
    except Exception as e:
        window.console.log(f"exon stats error: {e}")
        app.exon_lengths=[]; app.exon_stats={"count":0,"mean":0,"max":0,"min":0}

    try:
        gene_py = js_to_py(app.selectedGene)
        if gene_py and "go" in gene_py:
            go = gene_py["go"]
            if isinstance(go, dict):
                app.go_counts = {
                    "BP": len(go.get("BP",[])) if isinstance(go.get("BP",[]), list) else 0,
                    "MF": len(go.get("MF",[])) if isinstance(go.get("MF",[]), list) else 0,
                    "CC": len(go.get("CC",[])) if isinstance(go.get("CC",[]), list) else 0,
                }
            else:
                app.go_counts = {"BP":0,"MF":0,"CC":0}
        else:
            app.go_counts = {"BP":0,"MF":0,"CC":0}
    except:
        app.go_counts = {"BP":0,"MF":0,"CC":0}

    try:
        gene_py = js_to_py(app.selectedGene)
        if gene_py and "pathway" in gene_py:
            pw = gene_py["pathway"]
            if isinstance(pw, dict):
                app.path_counts = {
                    "KEGG": len(pw.get("kegg",[])) if isinstance(pw.get("kegg",[]), list) else 0,
                    "Reactome": len(pw.get("reactome",[])) if isinstance(pw.get("reactome",[]), list) else 0,
                    "Wiki": len(pw.get("wikipathways",[])) if isinstance(pw.get("wikipathways",[]), list) else 0,
                    "PID": len(pw.get("pid",[])) if isinstance(pw.get("pid",[]), list) else 0,
                }
            else:
                app.path_counts = {"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}
        else:
            app.path_counts = {"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}
    except:
        app.path_counts = {"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}

async def fetch_json_real(url):
    try:
        resp = await window.fetch(url)
        if not resp.ok:
            raise Exception(f"HTTP {resp.status}")
        txt = await resp.text()
        if hasattr(txt,'to_py'):
            try:
                txt=txt.to_py()
            except:
                pass
        txt=str(txt)
        parsed=json.loads(txt)
        return parsed
    except Exception as e:
        window.console.log(f"fetch_json_real error {url}: {e}")
        raise

async def fetch_gene_detail(app, gene_id):
    try:
        app.loadingDetail = True
        url = f"https://mygene.info/v3/gene/{gene_id}?fields=all"
        data = await fetch_json_real(url)
        data = js_to_py(data)
        app.selectedGene = data
        app.selectedGeneId = gene_id
        await compute_stats_pyodide(app)
    except Exception as e:
        window.console.log(f"gene detail error {gene_id}: {e}")
        app.selectedGene = None
    app.loadingDetail = False

async def query_mygene(app):
    try:
        app.loading = True
        app.errorMsg = ""
        q = app.queryText.strip() or "BRCA1"
        species = app.species
        size = int(app.size)
        from_ = int(app.fromOffset)
        fields = "all" if app.fieldsAll else "symbol,name,taxid,entrezgene,ensembl,summary,type_of_gene,genomic_pos,exons,go,pathway"
        safe_q = q.replace(" ", "+")
        url = f"https://mygene.info/v3/query?q={safe_q}&species={species}&size={size}&from={from_}&fields={fields}&facets=taxid,type_of_gene&dotfield=false"
        app.fetch_status = f"Fetching {q}..."
        data = await fetch_json_real(url)
        data = js_to_py(data)
        hits = safe_get(data, "hits", [])
        total = safe_get(data, "total", 0)
        hits = js_to_py(hits)
        if not isinstance(hits, list):
            hits=[]
        app.hits = hits
        app.total = int(total) if isinstance(total, (int,float)) else 0
        app.selectedIdx = 0
        if app.hits:
            first = js_to_py(app.hits[0])
            fid = first.get("_id") if isinstance(first, dict) else None
            if not fid and isinstance(first, dict):
                fid = first.get("entrezgene")
            if fid:
                await fetch_gene_detail(app, str(fid))
        else:
            app.selectedGene = None
        await compute_stats_pyodide(app)
        app.fetch_status = f"Ready {len(hits)}/{app.total}"
    except Exception as e:
        window.console.log(f"query error: {e} {traceback.format_exc()[:200]}")
        app.errorMsg = str(e)[:120]
        app.fetch_status = f"Failed {e}"
    app.loading = False

def init_audio(app):
    try:
        if PROC_OK and AudioEngine is not None:
            app.audio = AudioEngine(quality="high", seed=90210)
        else:
            app.audio = None
    except Exception as e:
        window.console.log(f"audio init error: {e}")
        app.audio = None

def play_exon_sonification(app):
    try:
        if not app.audio:
            init_audio(app)
        if app.audio:
            try:
                app.audio.resume()
            except:
                pass
            lens = getattr(app, "exon_lengths", [])
            if not lens:
                lens = [120, 250, 80, 300]
            for i, l in enumerate(lens[:12]):
                try:
                    app.audio.play("character.jump", seed=int(l)%1000 + i*17, spatial=False, position={"x":0,"y":0})
                except:
                    pass
    except Exception as e:
        window.console.log(f"sonify error: {e}")

def play_score_sonification(app):
    try:
        if not app.audio:
            init_audio(app)
        if app.audio:
            try:
                app.audio.resume()
            except:
                pass
            hits_py = js_to_py(app.hits)
            scores=[]
            for h in hits_py[:8]:
                if isinstance(h, dict):
                    scores.append(float(h.get("_score",0)))
            for i, sc in enumerate(scores):
                try:
                    app.audio.play("coin.collect", seed=int(sc)+i*13, spatial=True, position={"x":(i/8)-0.5,"y":0})
                except:
                    pass
    except Exception as e:
        window.console.log(f"score sonify error: {e}")

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30
    app.background=BG
    app.queryText="BRCA1"
    app.species="human"
    app.speciesOptions=["human","mouse","rat","zebrafish","all"]
    app.size=25
    app.fromOffset=0
    app.fieldsAll=True
    app.hits=[]; app.total=0
    app.selectedIdx=0; app.selectedGene=None; app.selectedGeneId=None
    app.loading=False; app.loadingDetail=False; app.errorMsg=""
    app.fetch_status="Fetching..."
    app.focus="query"
    app.stats_local={"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}
    app.stats_py={"mean":0}
    app.go_counts={"BP":0,"MF":0,"CC":0}
    app.path_counts={"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}
    app.exon_lengths=[]; app.exon_stats={"count":0,"mean":0}
    app.vizMode="bars"; app.draggingSize=False; app.audio=None
    init_audio(app)
    aio.run(query_mygene(app))

def onStep(app):
    pass

def onMousePress(app,mx,my):
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+28, SEARCH_W-16, 26):
        app.focus="query"; return
    else:
        if app.focus=="query" and not pointInRect(mx,my,SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H):
            app.focus=None
    sx=SEARCH_X+8; sy=SEARCH_Y+62
    for i, sp in enumerate(app.speciesOptions):
        if pointInRect(mx,my,sx+i*60,sy,56,22):
            app.species=sp; return
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+92, 90, 26):
        aio.run(query_mygene(app)); return
    if pointInRect(mx,my,SEARCH_X+110, SEARCH_Y+92, 32, 26):
        app.size=max(5,app.size-5); return
    if pointInRect(mx,my,SEARCH_X+146, SEARCH_Y+92, 32, 26):
        app.size=min(100,app.size+5); return
    if pointInRect(mx,my,SEARCH_X+8, SEARCH_Y+128, SEARCH_W-16, 18):
        rel=clamp((mx-(SEARCH_X+8))/(SEARCH_W-16),0,1)
        app.size=int(5+rel*95); app.draggingSize=True; return
    if pointInRect(mx,my,SEARCH_X+190, SEARCH_Y+92, 60, 26):
        app.fieldsAll=not app.fieldsAll; return
    if pointInRect(mx,my,RESULTS_X+8, RESULTS_Y+28, 52, 22):
        app.fromOffset=max(0,app.fromOffset-app.size); aio.run(query_mygene(app)); return
    if pointInRect(mx,my,RESULTS_X+68, RESULTS_Y+28, 52, 22):
        app.fromOffset+=app.size; aio.run(query_mygene(app)); return
    if pointInRect(mx,my,RESULTS_X+8, RESULTS_Y+56, RESULTS_W-16, RESULTS_H-64):
        idx=int((my-(RESULTS_Y+56))//28)
        hits_py=js_to_py(app.hits)
        if 0 <= idx < len(hits_py):
            app.selectedIdx=idx
            first=js_to_py(hits_py[idx])
            gid=first.get("_id") if isinstance(first, dict) else None
            if not gid and isinstance(first, dict):
                gid=first.get("entrezgene")
            if gid:
                aio.run(fetch_gene_detail(app,str(gid)))
        return
    if pointInRect(mx,my,GO_X+8, GO_Y+28, 48, 20):
        app.vizMode="bars"; return
    if pointInRect(mx,my,GO_X+62, GO_Y+28, 48, 20):
        app.vizMode="pie"; return
    if pointInRect(mx,my,GO_X+116, GO_Y+28, 64, 20):
        app.vizMode="scatter"; return
    if pointInRect(mx,my,PATH_X+8, PATH_Y+28, 72, 22):
        play_score_sonification(app); return
    if pointInRect(mx,my,PATH_X+88, PATH_Y+28, 72, 22):
        play_exon_sonification(app); return
    if pointInRect(mx,my,EXON_X+8, EXON_Y+28, 72, 22):
        play_exon_sonification(app); return
    if pointInRect(mx,my,STATS_X+8, STATS_Y+28, 88, 22):
        aio.run(compute_stats_pyodide(app)); return

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
                aio.run(query_mygene(app))
            elif key=="Escape":
                app.focus=None
            elif len(key)==1:
                if len(app.queryText)<42:
                    app.queryText+=key
            return
        if key==" ":
            aio.run(query_mygene(app))
        elif key.lower()=="s":
            play_score_sonification(app)
        elif key.lower()=="e":
            play_exon_sonification(app)
        elif key.lower()=="n":
            hits_py=js_to_py(app.hits)
            if hits_py and app.selectedIdx < len(hits_py)-1:
                app.selectedIdx+=1
                gid=js_to_py(hits_py[app.selectedIdx]).get("_id") if isinstance(js_to_py(hits_py[app.selectedIdx]), dict) else None
                if gid:
                    aio.run(fetch_gene_detail(app,str(gid)))
        elif key.lower()=="p":
            if app.selectedIdx>0:
                app.selectedIdx-=1
                hits_py=js_to_py(app.hits)
                if hits_py:
                    gid=js_to_py(hits_py[app.selectedIdx]).get("_id") if isinstance(js_to_py(hits_py[app.selectedIdx]), dict) else None
                    if gid:
                        aio.run(fetch_gene_detail(app,str(gid)))
    except Exception as e:
        window.console.log(f"keypress error: {e}")

def redrawAll(app):
    try:
        drawRect(0,0,W,H, fill=BG)
        drawRect(0,0,W,HEADER_H, fill=rgb(18,24,44), border=PANEL_BORDER, borderWidth=1)
        drawLabel("MyGene Explorer \u2022 v3 API", 20, 18, fill=WHITE, size=20, bold=True, align="left-top")
        drawLabel(f"Query:{truncate(app.queryText,18)} Species:{app.species} Hits:{app.total} Size:{app.size} {app.fetch_status}", 20, 40, fill=MUTED, size=13, align="left-top")
        if app.loading:
            drawLabel("loading", W-120, 18, fill=YELLOW, size=13, bold=True, align="left-top")
        if app.errorMsg:
            drawLabel(truncate(app.errorMsg,32), W-320, 40, fill=PINK, size=13, align="left-top")

        drawPanel(SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H, "QUERY")
        drawRect(SEARCH_X+8, SEARCH_Y+28, SEARCH_W-16, 26, fill=rgb(13,18,33), border=CYAN if app.focus=="query" else PANEL_BORDER, borderWidth=1.2, roundness=6)
        drawLabel(app.queryText if app.queryText else "BRCA1", SEARCH_X+14, SEARCH_Y+41, fill=WHITE if app.queryText else MUTED, size=13, align="left-center")
        sx=SEARCH_X+8; sy=SEARCH_Y+62
        for i, sp in enumerate(app.speciesOptions):
            active=sp==app.species
            draw_button(sx+i*60, sy, 56, 22, sp[:5], active=active, color=CYAN if active else None)
        draw_button(SEARCH_X+8, SEARCH_Y+92, 90, 26, "SEARCH", active=True, color=GREEN)
        draw_button(SEARCH_X+110, SEARCH_Y+92, 32, 26, "-", active=False)
        draw_button(SEARCH_X+146, SEARCH_Y+92, 32, 26, "+", active=False)
        drawLabel(f"{app.size}", SEARCH_X+188, SEARCH_Y+105, fill=WHITE, size=13, align="left-center")
        draw_button(SEARCH_X+210, SEARCH_Y+92, 80, 26, "FIELDS:"+("ALL" if app.fieldsAll else "SET"), active=app.fieldsAll, color=PURPLE if app.fieldsAll else None)
        drawRect(SEARCH_X+8, SEARCH_Y+128, SEARCH_W-16, 10, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=5)
        rel=(app.size-5)/95 if 95 else 0
        drawRect(SEARCH_X+8, SEARCH_Y+128, rel*(SEARCH_W-16), 10, fill=ORANGE, roundness=5)
        drawCircle(SEARCH_X+8+rel*(SEARCH_W-16), SEARCH_Y+133, 7, fill=WHITE, border=ORANGE, borderWidth=1.5)

        drawPanel(RESULTS_X, RESULTS_Y, RESULTS_W, RESULTS_H, "HITS")
        draw_button(RESULTS_X+8, RESULTS_Y+28, 52, 22, "PREV", active=False)
        draw_button(RESULTS_X+68, RESULTS_Y+28, 52, 22, "NEXT", active=False)
        drawLabel(f"{app.fromOffset}-{app.fromOffset+len(js_to_py(app.hits))}/{app.total}", RESULTS_X+130, RESULTS_Y+39, fill=MUTED, size=13, align="left-center")
        ly=RESULTS_Y+56
        hits_py=js_to_py(app.hits)
        for i, hit in enumerate(hits_py[:6]):
            by=ly+i*28
            sel=i==app.selectedIdx
            fillc=rgb(34,42,68) if sel else rgb(18,24,42)
            drawRect(RESULTS_X+8, by, RESULTS_W-16, 26, fill=fillc, border=CYAN if sel else PANEL_BORDER, borderWidth=1 if sel else 0.8, roundness=5)
            if isinstance(hit, dict):
                sym=hit.get("symbol","-"); score=hit.get("_score",0); tax=hit.get("taxid",""); nm=hit.get("name","")
            else:
                sym="-"; score=0; tax=""; nm=""
            try:
                sc_f=float(score)
            except:
                sc_f=0
            drawLabel(truncate(sym,10), RESULTS_X+14, by+13, fill=CYAN if sel else WHITE, size=13, bold=sel, align="left-center")
            drawLabel(f"{sc_f:.1f}", RESULTS_X+90, by+13, fill=YELLOW, size=13, align="left-center")
            drawLabel(f"{tax}", RESULTS_X+150, by+13, fill=MUTED, size=13, align="left-center")
            drawLabel(truncate(nm,18), RESULTS_X+190, by+13, fill=MUTED, size=13, align="left-center")

        drawPanel(DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H, "GENE")
        if app.loadingDetail:
            drawLabel("loading gene", DETAIL_X+DETAIL_W/2, DETAIL_Y+DETAIL_H/2, fill=YELLOW, size=13, align="center")
        else:
            draw_gene_detail(DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H, app.selectedGene)

        drawPanel(GO_X, GO_Y, GO_W, GO_H, "GO TERMS")
        draw_button(GO_X+8, GO_Y+28, 48, 20, "BARS", active=app.vizMode=="bars")
        draw_button(GO_X+62, GO_Y+28, 48, 20, "PIE", active=app.vizMode=="pie")
        draw_button(GO_X+116, GO_Y+28, 64, 20, "SCATTER", active=app.vizMode=="scatter")
        chart_x=GO_X+8; chart_y=GO_Y+54; chart_w=GO_W-16; chart_h=GO_H-62
        if app.vizMode=="bars":
            draw_bar_chart(chart_x, chart_y, chart_w, chart_h, app.go_counts, color_map={"BP": GREEN, "MF": PINK, "CC": CYAN})
        elif app.vizMode=="pie":
            draw_pie_chart(chart_x, chart_y, chart_w, chart_h, app.go_counts, color_map={"BP": GREEN, "MF": PINK, "CC": CYAN})
        else:
            drawRect(chart_x, chart_y, chart_w, chart_h, fill=rgb(13,18,33), border=PANEL_BORDER, borderWidth=1, roundness=6)
            drawLine(chart_x+30, chart_y+chart_h-20, chart_x+chart_w-10, chart_y+chart_h-20, fill=MUTED, lineWidth=1)
            drawLine(chart_x+30, chart_y+10, chart_x+30, chart_y+chart_h-20, fill=MUTED, lineWidth=1)
            try:
                gc=js_to_py(app.go_counts); pc=js_to_py(app.path_counts)
                bp=gc.get("BP",0) if isinstance(gc, dict) else 0; mf=gc.get("MF",0) if isinstance(gc, dict) else 0; cc=gc.get("CC",0) if isinstance(gc, dict) else 0
                max_go=max(bp,mf,cc,1); max_path=max(pc.values()) if isinstance(pc, dict) and pc else 1
                if max_path==0:
                    max_path=1
                pts=[(bp, pc.get("KEGG",0) if isinstance(pc, dict) else 0, CYAN), (mf, pc.get("Reactome",0) if isinstance(pc, dict) else 0, PINK), (cc, pc.get("Wiki",0) if isinstance(pc, dict) else 0, YELLOW)]
                for px,py,col in pts:
                    if px==0 and py==0:
                        continue
                    rx=chart_x+30 + (px/max_go)*(chart_w-50)
                    ry=chart_y+chart_h-20 - (py/max_path)*(chart_h-30)
                    drawCircle(rx, ry, 6, fill=col, border=WHITE, borderWidth=1)
            except:
                pass

        drawPanel(PATH_X, PATH_Y, PATH_W, PATH_H, "PATHWAYS")
        draw_button(PATH_X+8, PATH_Y+28, 72, 22, "PLAY S", active=False, color=YELLOW)
        draw_button(PATH_X+88, PATH_Y+28, 72, 22, "PLAY E", active=False, color=ORANGE)
        drawLabel(f"Gene {app.selectedGeneId or '-'}", PATH_X+170, PATH_Y+39, fill=MUTED, size=13, align="left-center")
        draw_bar_chart(PATH_X+8, PATH_Y+56, PATH_W-16, PATH_H-64, app.path_counts, color_map={"KEGG": CYAN, "Reactome": PINK, "Wiki": YELLOW, "PID": GREEN})

        drawPanel(EXON_X, EXON_Y, EXON_W, EXON_H, "GENOMIC ARCHITECTURE")
        draw_button(EXON_X+8, EXON_Y+28, 72, 22, "SONIFY", active=False, color=CYAN)
        draw_exon_map(EXON_X, EXON_Y, EXON_W, EXON_H, app.selectedGene)

        drawPanel(STATS_X, STATS_Y, STATS_W, STATS_H, "STATISTICS")
        draw_button(STATS_X+8, STATS_Y+28, 88, 22, "RECOMPUTE", active=False, color=GREEN)
        tx=STATS_X+12; ty=STATS_Y+58
        drawLabel("Metric", tx, ty, fill=MUTED, size=13, bold=True, align="left-top")
        drawLabel("Value", tx+120, ty, fill=MUTED, size=13, bold=True, align="left-top")
        drawLabel("Detail", tx+220, ty, fill=MUTED, size=13, bold=True, align="left-top")
        ty+=18
        try:
            sl=js_to_py(app.stats_local); gc=js_to_py(app.go_counts); pc=js_to_py(app.path_counts); es=js_to_py(app.exon_stats)
            if not isinstance(sl, dict):
                sl={"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}
            if not isinstance(gc, dict):
                gc={"BP":0,"MF":0,"CC":0}
            if not isinstance(pc, dict):
                pc={"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}
            if not isinstance(es, dict):
                es={"count":0,"mean":0}
            rows=[
                ("n hits", f"{sl.get('n',0)}", f"total {app.total}"),
                ("mean score", f"{sl.get('mean',0):.2f}", f"median {sl.get('median',0):.2f}"),
                ("std", f"{sl.get('std',0):.2f}", f"min {sl.get('min',0):.1f} max {sl.get('max',0):.1f}"),
                ("exons", f"{es.get('count',0)}", f"mean len {es.get('mean',0):.0f}"),
                ("GO", f"{sum(gc.values())}", f"BP {gc.get('BP',0)} MF {gc.get('MF',0)}"),
                ("Path", f"{sum(pc.values())}", f"KEGG {pc.get('KEGG',0)} React {pc.get('Reactome',0)}"),
            ]
            for i,(k,v,d) in enumerate(rows):
                ry=ty+i*24
                drawRect(tx-4, ry-2, STATS_W-24, 20, fill=rgb(18,24,42) if i%2==0 else rgb(22,28,48), roundness=4)
                drawLabel(k, tx, ry, fill=WHITE, size=13, align="left-top")
                drawLabel(v, tx+120, ry, fill=YELLOW, size=13, bold=True, align="left-top")
                drawLabel(truncate(d,22), tx+220, ry, fill=MUTED, size=13, align="left-top")
            drawLabel(f"pyodide:{'on' if PYODIDE_EXT_OK else 'off'} proc:{'on' if PROC_OK else 'off'} fetch:{'on' if EXT_FETCH_OK else 'off'} {app.fetch_status}", tx, ty+6*24+4, fill=MUTED, size=13, align="left-top")
        except Exception as e:
            window.console.log(f"stats error: {e}")

        drawLabel("Keys: Enter search  n/p next/prev  s score audio  e exon audio  Click rows", W//2, H-10, fill=MUTED, size=13, align="center-bottom")
    except Exception as e:
        window.console.log(f"redrawAll error: {e} {traceback.format_exc()[:200]}")
