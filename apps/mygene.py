"""
MyGene Explorer - SCS App 1050x700
Researcher & educator focused exploration of mygene.info v3 API
Panels: Query, Hits, Gene, GO, Pathways, Genomic Architecture, Statistics
Extensions: pyodide, procaudio, fetch
Font min 13, no superfluous UI text, errors logged to console only
"""

from scs import *
from browser import window, aio
import math

# --- extensions required ---
try:
    from extensions.fetch import fetch_json, fetch, FetchError
    HAS_FETCH = True
except Exception as e:
    HAS_FETCH = False
    try:
        window.console.log(f"fetch import error: {e}")
    except:
        pass
    fetch_json = None
    fetch = None

try:
    from extensions.proc_audio import AudioEngine
    HAS_PROC = True
except Exception as e:
    HAS_PROC = False
    try:
        window.console.log(f"proc_audio import error: {e}")
    except:
        pass
    AudioEngine = None

try:
    import extensions.pyodide as pyodide_ext
    HAS_PYODIDE = True
except Exception as e:
    HAS_PYODIDE = False
    pyodide_ext = None
    try:
        window.console.log(f"pyodide import error: {e}")
    except:
        pass
    try:
        from extensions.pyodide import Pyodide
        HAS_PYODIDE = True
    except Exception as e2:
        try:
            window.console.log(f"pyodide alt import error: {e2}")
        except:
            pass

# --- canvas ---
W, H = 1050, 700
HEADER_H = 64

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

def safe_get(d, k, default=None):
    try:
        return d.get(k, default)
    except:
        return default

def truncate(s, n):
    try:
        s = str(s)
        return s if len(s) <= n else s[:n-1] + "…"
    except:
        return ""

# --- pyodide stats ---
async def compute_stats_pyodide(app):
    # always compute local stats for display; pyodide is used additionally for heavy calc
    scores = []
    try:
        for h in app.hits:
            sc = h.get("_score")
            if sc is not None:
                scores.append(float(sc))
    except Exception as e:
        try:
            window.console.log(f"score collect error: {e}")
        except:
            pass
        scores = []

    # local calc
    try:
        if scores:
            mean = sum(scores)/len(scores)
            ssorted = sorted(scores)
            median = ssorted[len(ssorted)//2]
            mn = min(scores)
            mx = max(scores)
            var = sum((x-mean)**2 for x in scores)/len(scores)
            std = math.sqrt(var)
        else:
            mean = median = mn = mx = std = 0.0
        app.stats_local = {"mean": mean, "median": median, "min": mn, "max": mx, "std": std, "n": len(scores)}
    except Exception as e:
        try:
            window.console.log(f"local stats error: {e}")
        except:
            pass
        app.stats_local = {"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}

    # pyodide heavy path
    if HAS_PYODIDE and pyodide_ext is not None:
        try:
            # attempt various APIs
            if hasattr(pyodide_ext, "run_python"):
                code = f"""
import numpy as np
scores = {scores}
mean = float(np.mean(scores)) if scores else 0.0
median = float(np.median(scores)) if scores else 0.0
std = float(np.std(scores)) if scores else 0.0
result = {{"mean": mean, "median": median, "std": std, "n": len(scores)}}
result
"""
                res = await pyodide_ext.run_python(code)
                app.stats_py = res
            elif hasattr(pyodide_ext, "run"):
                code = f"import numpy as np; scores={scores}; {{'mean': float(np.mean(scores)) if scores else 0}}"
                res = await pyodide_ext.run(code)
                app.stats_py = res
            else:
                # try generic eval
                app.stats_py = app.stats_local
        except Exception as e:
            try:
                window.console.log(f"pyodide compute error: {e}")
            except:
                pass
            app.stats_py = app.stats_local
    else:
        # try window.pyodide if available
        try:
            if hasattr(window, "pyodide") and window.pyodide is not None:
                # not blocking - log use
                window.console.log("pyodide global present")
                app.stats_py = app.stats_local
            else:
                app.stats_py = app.stats_local
        except Exception as e:
            try:
                window.console.log(f"pyodide window check error: {e}")
            except:
                pass
            app.stats_py = app.stats_local

    # exon stats
    try:
        if app.selectedGene and "exons" in app.selectedGene:
            ex = app.selectedGene["exons"]
            lens = []
            for tr in ex:
                try:
                    pos = tr.get("position", [])
                    for p in pos:
                        try:
                            lens.append(int(p[1]) - int(p[0]))
                        except:
                            pass
                except:
                    pass
            app.exon_lengths = lens[:64]
            if lens:
                app.exon_stats = {"count": len(lens), "mean": sum(lens)/len(lens), "max": max(lens), "min": min(lens), "span": max(lens)-min(lens)}
            else:
                app.exon_stats = {"count":0,"mean":0,"max":0,"min":0,"span":0}
        else:
            app.exon_lengths = []
            app.exon_stats = {"count":0,"mean":0,"max":0,"min":0,"span":0}
    except Exception as e:
        try:
            window.console.log(f"exon stats error: {e}")
        except:
            pass
        app.exon_lengths = []
        app.exon_stats = {"count":0,"mean":0,"max":0,"min":0,"span":0}

    # GO stats
    try:
        if app.selectedGene and "go" in app.selectedGene:
            go = app.selectedGene["go"]
            bp = len(go.get("BP", [])) if isinstance(go, dict) else 0
            mf = len(go.get("MF", [])) if isinstance(go, dict) else 0
            cc = len(go.get("CC", [])) if isinstance(go, dict) else 0
            if isinstance(go, dict) is False and isinstance(go, list):
                # sometimes list
                bp = mf = cc = 0
            app.go_counts = {"BP": bp, "MF": mf, "CC": cc}
        else:
            app.go_counts = {"BP":0,"MF":0,"CC":0}
    except Exception as e:
        try:
            window.console.log(f"go stats error: {e}")
        except:
            pass
        app.go_counts = {"BP":0,"MF":0,"CC":0}

    # pathway stats
    try:
        if app.selectedGene and "pathway" in app.selectedGene:
            pw = app.selectedGene["pathway"]
            kegg = len(pw.get("kegg", [])) if isinstance(pw, dict) else 0
            reactome = len(pw.get("reactome", [])) if isinstance(pw, dict) else 0
            wikip = len(pw.get("wikipathways", [])) if isinstance(pw, dict) else 0
            pid = len(pw.get("pid", [])) if isinstance(pw, dict) else 0
            app.path_counts = {"KEGG": kegg, "Reactome": reactome, "Wiki": wikip, "PID": pid}
        else:
            app.path_counts = {"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}
    except Exception as e:
        try:
            window.console.log(f"path stats error: {e}")
        except:
            pass
        app.path_counts = {"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}

# --- fetch ---
async def fetch_gene_detail(app, gene_id):
    if not HAS_FETCH or fetch_json is None:
        try:
            window.console.log("fetch not available for gene detail")
        except:
            pass
        return
    try:
        app.loadingDetail = True
        url = f"https://mygene.info/v3/gene/{gene_id}?fields=all"
        data = await fetch_json(url)
        app.selectedGene = data
        app.selectedGeneId = gene_id
        await compute_stats_pyodide(app)
    except Exception as e:
        try:
            window.console.log(f"gene detail fetch error {gene_id}: {e}")
        except:
            pass
        app.selectedGene = None
    app.loadingDetail = False

async def query_mygene(app):
    if not HAS_FETCH or fetch_json is None:
        try:
            window.console.log("fetch not available for query")
        except:
            pass
        return
    try:
        app.loading = True
        app.errorMsg = ""
        q = app.queryText.strip()
        if not q:
            q = "BRCA1"
        # encode query
        # replace spaces with AND for mygene? keep simple
        # species param
        species = app.species
        size = int(app.size)
        from_ = int(app.fromOffset)
        # fields
        if app.fieldsAll:
            fields = "all"
        else:
            # comprehensive field set for researchers
            fields = "symbol,name,taxid,entrezgene,ensembl,summary,type_of_gene,genomic_pos,exons,go,pathway,refseq,accession,alias,uniprot,MIM,ec,interpro,panther,pfam,prosite,pharmgkb,reporter"
        # build url
        # use q with proper escaping - simple
        safe_q = q.replace(" ", "+")
        url = f"https://mygene.info/v3/query?q={safe_q}&species={species}&size={size}&from={from_}&fields={fields}&facets=taxid,type_of_gene&dotfield=false"
        data = await fetch_json(url)
        app.hits = safe_get(data, "hits", [])
        app.total = safe_get(data, "total", 0)
        app.facets = safe_get(data, "facets", {})
        app.selectedIdx = 0
        if app.hits:
            first_id = safe_get(app.hits[0], "_id") or safe_get(app.hits[0], "entrezgene")
            if first_id:
                await fetch_gene_detail(app, str(first_id))
        else:
            app.selectedGene = None
        await compute_stats_pyodide(app)
    except Exception as e:
        try:
            window.console.log(f"query error: {e}")
        except:
            pass
        app.errorMsg = str(e)[:120]
    app.loading = False

# --- audio ---
def init_audio(app):
    try:
        if HAS_PROC and AudioEngine is not None:
            app.audio = AudioEngine(quality="high", seed=90210)
        else:
            app.audio = None
    except Exception as e:
        try:
            window.console.log(f"audio init error: {e}")
        except:
            pass
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
            # map exon lengths to tones
            lens = getattr(app, "exon_lengths", [])
            if not lens:
                lens = [120, 250, 80, 300]
            for i, l in enumerate(lens[:12]):
                try:
                    # use generic preset, vary seed for pitch variation
                    freq_seed = int(l) % 1000 + i*17
                    app.audio.play("character.jump", seed=freq_seed, spatial=False, position={"x": 0, "y": 0})
                except Exception as e:
                    try:
                        window.console.log(f"audio play error idx {i}: {e}")
                    except:
                        pass
            # play GO chord
            try:
                gc = getattr(app, "go_counts", {})
                total_go = gc.get("BP",0)+gc.get("MF",0)+gc.get("CC",0)
                if total_go>0:
                    app.audio.play("ui.select", seed=total_go*7, spatial=True, position={"x": -0.5, "y": 0})
            except Exception as e:
                try:
                    window.console.log(f"go audio error: {e}")
                except:
                    pass
    except Exception as e:
        try:
            window.console.log(f"sonify error: {e}")
        except:
            pass

def play_score_sonification(app):
    try:
        if not app.audio:
            init_audio(app)
        if app.audio:
            try:
                app.audio.resume()
            except:
                pass
            scores = []
            try:
                for h in app.hits[:8]:
                    scores.append(float(h.get("_score", 0)))
            except:
                scores = [50, 80, 30]
            for i, sc in enumerate(scores):
                try:
                    seed = int(sc) + i*13
                    app.audio.play("coin.collect", seed=seed, spatial=True, position={"x": (i/8)-0.5, "y": 0})
                except Exception as e:
                    try:
                        window.console.log(f"score audio error: {e}")
                    except:
                        pass
    except Exception as e:
        try:
            window.console.log(f"score sonify error: {e}")
        except:
            pass

# --- drawing helpers ---
def draw_panel(x, y, w, h, title):
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
    # data_dict: label->value
    try:
        if not data_dict:
            drawLabel("no data", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        vals = list(data_dict.values())
        labels = list(data_dict.keys())
        if max_val is None:
            max_val = max(vals) if vals else 1
            if max_val < 1:
                max_val = 1
        bar_area_w = w - 70
        bar_h = (h - 20) / len(vals) - 6
        for i, (lbl, val) in enumerate(data_dict.items()):
            by = y + 10 + i*(bar_h+6)
            bw = (val / max_val) * bar_area_w if max_val else 0
            col = color_map.get(lbl, CYAN) if color_map else CYAN
            drawRect(x+60, by, bar_area_w, bar_h, fill=rgb(18,24,42), roundness=4)
            drawRect(x+60, by, bw, bar_h, fill=col, roundness=4)
            drawLabel(truncate(lbl, 12), x+2, by+bar_h/2, fill=WHITE, size=13, align="left-center")
            drawLabel(str(val), x+62+bar_area_w+4, by+bar_h/2, fill=MUTED, size=13, align="left-center")
            # value label inside
            if bw > 30:
                drawLabel(f"{val}", x+60+bw-4, by+bar_h/2, fill=rgb(0,0,0), size=13, bold=True, align="right-center")
    except Exception as e:
        try:
            window.console.log(f"bar chart error: {e}")
        except:
            pass

def draw_pie_chart(x, y, w, h, data_dict, color_map=None):
    try:
        if not data_dict:
            return
        vals = [v for v in data_dict.values() if v>0]
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
            if val <=0:
                continue
            ang = (val/total)*360
            col = color_map.get(lbl, colors[i%len(colors)]) if color_map else colors[i%len(colors)]
            # draw wedge as polygon approx
            # simple: draw arc via lines
            end_ang = start_ang + ang
            # draw filled wedge using polygon points
            pts = [(cx, cy)]
            steps = max(2, int(ang/6))
            for s in range(steps+1):
                a = math.radians(start_ang + (s/steps)*ang)
                pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
            # draw as filled polygon using drawPolygon if available else lines
            try:
                # construct polygon
                drawPolygon(*pts, fill=col, border=rgb(10,14,26), borderWidth=1)
            except:
                # fallback lines
                for j in range(1, len(pts)-1):
                    drawLine(pts[0][0], pts[0][1], pts[j][0], pts[j][1], fill=col, lineWidth=1)
            start_ang = end_ang
            i+=1
        # legend
        lx = x + w*0.78
        ly = y + 14
        j=0
        for lbl, val in data_dict.items():
            if val<=0:
                continue
            col = color_map.get(lbl, colors[j%len(colors)]) if color_map else colors[j%len(colors)]
            drawRect(lx, ly+j*22, 10, 10, fill=col, roundness=2)
            drawLabel(f"{lbl}:{val}", lx+14, ly+j*22+5, fill=WHITE, size=13, align="left-center")
            j+=1
    except Exception as e:
        try:
            window.console.log(f"pie chart error: {e}")
        except:
            pass

def draw_exon_map(x, y, w, h, gene):
    try:
        drawRect(x+8, y+30, w-16, h-44, fill=rgb(13,18,33), border=PANEL_BORDER, borderWidth=1, roundness=6)
        if not gene or "exons" not in gene:
            drawLabel("select gene", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        exons = gene.get("exons", [])
        if not exons:
            drawLabel("no exons", x+w/2, y+h/2, fill=MUTED, size=13, align="center")
            return
        # collect all genomic range
        try:
            all_starts = []
            all_ends = []
            for tr in exons:
                ps = tr.get("position", [])
                for p in ps:
                    all_starts.append(p[0])
                    all_ends.append(p[1])
            gmin = min(all_starts) if all_starts else 0
            gmax = max(all_ends) if all_ends else gmin+1000
            span = gmax - gmin
            if span ==0:
                span=1
        except Exception as e:
            try:
                window.console.log(f"exon range error: {e}")
            except:
                pass
            gmin=0
            gmax=1000
            span=1000
        # draw baseline
        base_y = y+44
        base_h = h-70
        gx = x+16
        gw = w-32
        # chromosome line
        drawLine(gx, base_y+base_h/2, gx+gw, base_y+base_h/2, fill=rgb(60,70,100), lineWidth=2)
        # draw each transcript
        colors = [CYAN, PINK, YELLOW, GREEN, PURPLE, ORANGE]
        for ti, tr in enumerate(exons[:5]):
            try:
                ty = base_y + 10 + ti*(base_h//6)
                tname = tr.get("transcript", f"tr{ti}")
                strand = tr.get("strand", 1)
                drawLabel(truncate(tname,14), gx, ty, fill=MUTED, size=13, align="left-center")
                pos = tr.get("position", [])
                for pi, p in enumerate(pos):
                    try:
                        s = p[0]; e = p[1]
                        rx = gx + ((s-gmin)/span)*gw
                        rw = ((e-s)/span)*gw
                        if rw < 2:
                            rw=2
                        col = colors[ti%len(colors)]
                        # cds vs utr distinction if cdsstart present
                        cds_s = tr.get("cdsstart")
                        cds_e = tr.get("cdsend")
                        if cds_s is not None and cds_e is not None and s >= cds_s and e <= cds_e:
                            # coding thicker
                            drawRect(rx, ty-6, rw, 12, fill=col, border=WHITE, borderWidth=0.8, roundness=3)
                        else:
                            drawRect(rx, ty-4, rw, 8, fill=col, opacity=0.7, border=col, borderWidth=1, roundness=2)
                    except Exception as e2:
                        try:
                            window.console.log(f"exon pos draw error: {e2}")
                        except:
                            pass
                # strand arrow
                arrow_x = gx+gw-10
                if strand == -1:
                    arrow_x = gx+10
                    drawLabel("<", arrow_x, base_y+base_h/2, fill=YELLOW, size=13, bold=True, align="center")
                else:
                    drawLabel(">", arrow_x, base_y+base_h/2, fill=YELLOW, size=13, bold=True, align="center")
            except Exception as e:
                try:
                    window.console.log(f"transcript draw error: {e}")
                except:
                    pass
        drawLabel(f"{gene.get('genomic_pos',{}).get('chr','?')}:{gmin}-{gmax}", gx, y+h-10, fill=MUTED, size=13, align="left-bottom")
        drawLabel(f"strand {exons[0].get('strand','?')}", gx+gw, y+h-10, fill=MUTED, size=13, align="right-bottom")
    except Exception as e:
        try:
            window.console.log(f"exon map error: {e}")
        except:
            pass

def draw_gene_detail(x, y, w, h, gene):
    try:
        if not gene:
            drawLabel("no gene", x+w/2, y+h/2, fill=MUTED, size=14, bold=True, align="center")
            return
        # core fields
        sy = y+30
        line_h = 20
        # symbol + name
        sym = gene.get("symbol","-")
        name = gene.get("name","-")
        drawLabel(f"{sym}", x+12, sy, fill=CYAN, size=16, bold=True, align="left-top")
        drawLabel(truncate(name, 32), x+12, sy+20, fill=WHITE, size=13, align="left-top")
        sy+=44
        # entrez, ensembl, taxid, type
        entrez = gene.get("entrezgene","-")
        ensembl_g = ""
        try:
            ensembl_g = gene.get("ensembl",{}).get("gene","")
        except:
            ensembl_g = ""
        tax = gene.get("taxid","")
        gtype = gene.get("type_of_gene","")
        drawLabel(f"Entrez: {entrez}  Tax: {tax}", x+12, sy, fill=MUTED, size=13, align="left-top")
        sy+=line_h
        drawLabel(f"Ensembl: {truncate(ensembl_g,22)}", x+12, sy, fill=MUTED, size=13, align="left-top")
        sy+=line_h
        drawLabel(f"Type: {gtype}", x+12, sy, fill=GREEN, size=13, bold=True, align="left-top")
        sy+=line_h+4
        # genomic pos
        try:
            gpos = gene.get("genomic_pos", {})
            if isinstance(gpos, dict):
                drawLabel(f"Chr {gpos.get('chr','?')} {gpos.get('start','?')}-{gpos.get('end','?')}", x+12, sy, fill=YELLOW, size=13, align="left-top")
            elif isinstance(gpos, list) and gpos:
                gp = gpos[0]
                drawLabel(f"Chr {gp.get('chr','?')} {gp.get('start','?')}-{gp.get('end','?')}", x+12, sy, fill=YELLOW, size=13, align="left-top")
        except Exception as e:
            try:
                window.console.log(f"gpos label error: {e}")
            except:
                pass
        sy+=line_h+4
        # summary truncated to 4 lines
        summary = gene.get("summary","")
        if summary:
            # wrap manually 44 chars per line
            words = summary.split()
            lines=[]
            cur=""
            for wd in words:
                if len(cur)+len(wd)+1 < 44:
                    cur = cur+" "+wd if cur else wd
                else:
                    lines.append(cur)
                    cur=wd
                if len(lines)>=4:
                    break
            if cur and len(lines)<4:
                lines.append(cur)
            for i, ln in enumerate(lines[:4]):
                drawLabel(truncate(ln,44), x+12, sy+i*16, fill=WHITE, size=13, align="left-top")
            sy+= len(lines[:4])*16 + 6
        # alias, MIM
        try:
            alias = gene.get("alias", [])
            if alias:
                drawLabel(f"Alias: {','.join(alias[:3])}", x+12, sy, fill=MUTED, size=13, align="left-top")
                sy+=line_h
            mim = gene.get("MIM","")
            if mim:
                drawLabel(f"MIM: {mim}", x+12, sy, fill=PINK, size=13, align="left-top")
                sy+=line_h
        except Exception as e:
            try:
                window.console.log(f"alias draw error: {e}")
            except:
                pass
    except Exception as e:
        try:
            window.console.log(f"gene detail draw error: {e}")
        except:
            pass

# --- app lifecycle ---
def onAppStart(app):
    app.width = W
    app.height = H
    app.stepsPerSecond = 30
    app.background = BG

    app.queryText = "BRCA1"
    app.species = "human"
    app.speciesOptions = ["human","mouse","rat","zebrafish","all"]
    app.size = 25
    app.fromOffset = 0
    app.fieldsAll = True
    app.selectedFields = ["symbol","name","summary","go","pathway","genomic_pos","exons"]
    app.hits = []
    app.total = 0
    app.facets = {}
    app.selectedIdx = 0
    app.selectedGene = None
    app.selectedGeneId = None
    app.loading = False
    app.loadingDetail = False
    app.errorMsg = ""
    app.focus = "query"
    app.stats_local = {"mean":0,"median":0,"min":0,"max":0,"std":0,"n":0}
    app.stats_py = {"mean":0}
    app.go_counts = {"BP":0,"MF":0,"CC":0}
    app.path_counts = {"KEGG":0,"Reactome":0,"Wiki":0,"PID":0}
    app.exon_lengths = []
    app.exon_stats = {"count":0,"mean":0,"max":0,"min":0,"span":0}
    app.vizMode = "bars"  # bars, pie, scatter
    app.dataTypeFilter = "all"
    app.scoreMin = 0
    app.draggingSize = False
    app.audio = None
    init_audio(app)

    # pyodide init attempt
    app.pyodide_runner = None
    if HAS_PYODIDE:
        try:
            # try to init if extension provides init
            if hasattr(pyodide_ext, "init"):
                aio.run(pyodide_ext.init())
            # store module as runner
            app.pyodide_runner = pyodide_ext
        except Exception as e:
            try:
                window.console.log(f"pyodide init error: {e}")
            except:
                pass

    # initial query
    try:
        aio.run(query_mygene(app))
    except Exception as e:
        try:
            window.console.log(f"initial query error: {e}")
        except:
            pass

def onStep(app):
    pass

def onMousePress(app, mx, my):
    # search box focus
    if pointInRect(mx, my, SEARCH_X+8, SEARCH_Y+28, SEARCH_W-16, 26):
        app.focus = "query"
        return
    else:
        if app.focus == "query" and not pointInRect(mx, my, SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H):
            app.focus = None

    # species buttons
    # layout: 5 buttons 56w
    sx = SEARCH_X+8
    sy = SEARCH_Y+62
    for i, sp in enumerate(app.speciesOptions):
        bx = sx + i*60
        if pointInRect(mx, my, bx, sy, 56, 22):
            app.species = sp
            return

    # search button
    if pointInRect(mx, my, SEARCH_X+8, SEARCH_Y+92, 90, 26):
        try:
            aio.run(query_mygene(app))
        except Exception as e:
            try:
                window.console.log(f"search button error: {e}")
            except:
                pass
        return

    # size - / + and slider
    if pointInRect(mx, my, SEARCH_X+110, SEARCH_Y+92, 32, 26):
        app.size = max(5, app.size-5)
        return
    if pointInRect(mx, my, SEARCH_X+146, SEARCH_Y+92, 32, 26):
        app.size = min(100, app.size+5)
        return
    if pointInRect(mx, my, SEARCH_X+8, SEARCH_Y+128, SEARCH_W-16, 18):
        # slider
        rel = (mx - (SEARCH_X+8)) / (SEARCH_W-16)
        rel = clamp(rel, 0, 1)
        app.size = int(5 + rel*95)
        app.draggingSize = True
        return

    # fields toggle
    if pointInRect(mx, my, SEARCH_X+190, SEARCH_Y+92, 60, 26):
        app.fieldsAll = not app.fieldsAll
        return

    # results pagination
    if pointInRect(mx, my, RESULTS_X+8, RESULTS_Y+28, 52, 22):
        # prev
        app.fromOffset = max(0, app.fromOffset - app.size)
        try:
            aio.run(query_mygene(app))
        except Exception as e:
            try:
                window.console.log(f"prev page error: {e}")
            except:
                pass
        return
    if pointInRect(mx, my, RESULTS_X+68, RESULTS_Y+28, 52, 22):
        app.fromOffset = app.fromOffset + app.size
        try:
            aio.run(query_mygene(app))
        except Exception as e:
            try:
                window.console.log(f"next page error: {e}")
            except:
                pass
        return

    # results list click
    if pointInRect(mx, my, RESULTS_X+8, RESULTS_Y+56, RESULTS_W-16, RESULTS_H-64):
        row_h = 28
        idx = int((my - (RESULTS_Y+56)) // row_h)
        if 0 <= idx < len(app.hits):
            app.selectedIdx = idx
            gid = app.hits[idx].get("_id") or app.hits[idx].get("entrezgene")
            if gid:
                try:
                    aio.run(fetch_gene_detail(app, str(gid)))
                except Exception as e:
                    try:
                        window.console.log(f"select gene error: {e}")
                    except:
                        pass
        return

    # viz mode buttons in GO panel
    if pointInRect(mx, my, GO_X+8, GO_Y+28, 48, 20):
        app.vizMode = "bars"
        return
    if pointInRect(mx, my, GO_X+62, GO_Y+28, 48, 20):
        app.vizMode = "pie"
        return
    if pointInRect(mx, my, GO_X+116, GO_Y+28, 64, 20):
        app.vizMode = "scatter"
        return

    # pathway panel sonify buttons
    if pointInRect(mx, my, PATH_X+8, PATH_Y+28, 72, 22):
        play_score_sonification(app)
        return
    if pointInRect(mx, my, PATH_X+88, PATH_Y+28, 72, 22):
        play_exon_sonification(app)
        return

    # exon panel click sonify
    if pointInRect(mx, my, EXON_X+8, EXON_Y+28, 72, 22):
        play_exon_sonification(app)
        return

    # stats panel detail toggle? click to recompute pyodide
    if pointInRect(mx, my, STATS_X+8, STATS_Y+28, 88, 22):
        try:
            aio.run(compute_stats_pyodide(app))
        except Exception as e:
            try:
                window.console.log(f"stats recompute error: {e}")
            except:
                pass
        return

def onMouseDrag(app, mx, my):
    if app.draggingSize:
        if pointInRect(mx, my, SEARCH_X+8, SEARCH_Y+118, SEARCH_W-16, 38):
            rel = (mx - (SEARCH_X+8)) / (SEARCH_W-16)
            rel = clamp(rel, 0, 1)
            app.size = int(5 + rel*95)

def onMouseRelease(app, mx, my):
    app.draggingSize = False

def onKeyPress(app, key):
    try:
        if app.focus == "query":
            if key == "Backspace":
                app.queryText = app.queryText[:-1]
            elif key == "Enter":
                try:
                    aio.run(query_mygene(app))
                except Exception as e:
                    try:
                        window.console.log(f"enter query error: {e}")
                    except:
                        pass
            elif key == "Escape":
                app.focus = None
            elif len(key) == 1 and key.isprintable():
                if len(app.queryText) < 42:
                    app.queryText += key
            return
        # global shortcuts
        if key == " ":
            try:
                aio.run(query_mygene(app))
            except Exception as e:
                try:
                    window.console.log(f"space query error: {e}")
                except:
                    pass
        elif key.lower() == "s":
            play_score_sonification(app)
        elif key.lower() == "e":
            play_exon_sonification(app)
        elif key.lower() == "n":
            # next hit
            if app.hits and app.selectedIdx < len(app.hits)-1:
                app.selectedIdx+=1
                gid = app.hits[app.selectedIdx].get("_id")
                if gid:
                    try:
                        aio.run(fetch_gene_detail(app, str(gid)))
                    except Exception as e:
                        try:
                            window.console.log(f"next hit error: {e}")
                        except:
                            pass
        elif key.lower() == "p":
            if app.hits and app.selectedIdx>0:
                app.selectedIdx-=1
                gid = app.hits[app.selectedIdx].get("_id")
                if gid:
                    try:
                        aio.run(fetch_gene_detail(app, str(gid)))
                    except Exception as e:
                        try:
                            window.console.log(f"prev hit error: {e}")
                        except:
                            pass
    except Exception as e:
        try:
            window.console.log(f"keypress error: {e}")
        except:
            pass

# --- redraw ---
def redrawAll(app):
    try:
        drawRect(0, 0, W, H, fill=BG)
        # header
        drawRect(0, 0, W, HEADER_H, fill=rgb(18, 24, 44), border=PANEL_BORDER, borderWidth=1)
        drawLabel("MyGene Explorer • v3 API", 20, 18, fill=WHITE, size=20, bold=True, align="left-top")
        drawLabel(f"Query:{truncate(app.queryText,18)}  Species:{app.species}  Hits:{app.total}  Size:{app.size}", 20, 40, fill=MUTED, size=13, align="left-top")
        if app.loading:
            drawLabel("loading", W-120, 18, fill=YELLOW, size=13, bold=True, align="left-top")
        if app.errorMsg:
            drawLabel(truncate(app.errorMsg,32), W-320, 40, fill=PINK, size=13, align="left-top")

        # SEARCH panel
        draw_panel(SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H, "QUERY")
        # input
        drawRect(SEARCH_X+8, SEARCH_Y+28, SEARCH_W-16, 26, fill=rgb(13,18,33), border=CYAN if app.focus=="query" else PANEL_BORDER, borderWidth=1.2, roundness=6)
        drawLabel(app.queryText if app.queryText else "BRCA1", SEARCH_X+14, SEARCH_Y+41, fill=WHITE if app.queryText else MUTED, size=13, align="left-center")
        # species buttons
        sx = SEARCH_X+8
        sy = SEARCH_Y+62
        for i, sp in enumerate(app.speciesOptions):
            active = sp==app.species
            draw_button(sx+i*60, sy, 56, 22, sp[:5], active=active, color=CYAN if active else None)
        # controls
        draw_button(SEARCH_X+8, SEARCH_Y+92, 90, 26, "SEARCH", active=True, color=GREEN)
        draw_button(SEARCH_X+110, SEARCH_Y+92, 32, 26, "-", active=False)
        draw_button(SEARCH_X+146, SEARCH_Y+92, 32, 26, "+", active=False)
        drawLabel(f"{app.size}", SEARCH_X+188, SEARCH_Y+105, fill=WHITE, size=13, align="left-center")
        draw_button(SEARCH_X+210, SEARCH_Y+92, 80, 26, "FIELDS:"+("ALL" if app.fieldsAll else "SET"), active=app.fieldsAll, color=PURPLE if app.fieldsAll else None)
        # size slider
        drawRect(SEARCH_X+8, SEARCH_Y+128, SEARCH_W-16, 10, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=5)
        rel = (app.size-5)/95 if 95 else 0
        drawRect(SEARCH_X+8, SEARCH_Y+128, rel*(SEARCH_W-16), 10, fill=ORANGE, roundness=5)
        drawCircle(SEARCH_X+8+rel*(SEARCH_W-16), SEARCH_Y+133, 7, fill=WHITE, border=ORANGE, borderWidth=1.5)
        drawLabel("5", SEARCH_X+8, SEARCH_Y+142, fill=MUTED, size=13, align="left-top")
        drawLabel("100", SEARCH_X+SEARCH_W-22, SEARCH_Y+142, fill=MUTED, size=13, align="right-top")

        # RESULTS panel
        draw_panel(RESULTS_X, RESULTS_Y, RESULTS_W, RESULTS_H, "HITS")
        draw_button(RESULTS_X+8, RESULTS_Y+28, 52, 22, "PREV", active=False)
        draw_button(RESULTS_X+68, RESULTS_Y+28, 52, 22, "NEXT", active=False)
        drawLabel(f"{app.fromOffset}-{app.fromOffset+len(app.hits)}/{app.total}", RESULTS_X+130, RESULTS_Y+39, fill=MUTED, size=13, align="left-center")
        # list
        ly = RESULTS_Y+56
        row_h = 28
        for i, hit in enumerate(app.hits[:6]):
            by = ly + i*row_h
            sel = i==app.selectedIdx
            fillc = rgb(34,42,68) if sel else rgb(18,24,42)
            drawRect(RESULTS_X+8, by, RESULTS_W-16, row_h-2, fill=fillc, border=CYAN if sel else PANEL_BORDER, borderWidth=1 if sel else 0.8, roundness=5)
            sym = hit.get("symbol","-")
            score = hit.get("_score",0)
            tax = hit.get("taxid","")
            drawLabel(truncate(sym,10), RESULTS_X+14, by+row_h/2, fill=CYAN if sel else WHITE, size=13, bold=sel, align="left-center")
            drawLabel(f"{score:.1f}", RESULTS_X+90, by+row_h/2, fill=YELLOW, size=13, align="left-center")
            drawLabel(f"{tax}", RESULTS_X+150, by+row_h/2, fill=MUTED, size=13, align="left-center")
            # name truncated
            nm = hit.get("name","")
            drawLabel(truncate(nm,18), RESULTS_X+190, by+row_h/2, fill=MUTED, size=13, align="left-center")

        # DETAIL panel
        draw_panel(DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H, "GENE")
        if app.loadingDetail:
            drawLabel("loading gene", DETAIL_X+DETAIL_W/2, DETAIL_Y+DETAIL_H/2, fill=YELLOW, size=13, align="center")
        else:
            draw_gene_detail(DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H, app.selectedGene)

        # GO panel
        draw_panel(GO_X, GO_Y, GO_W, GO_H, "GO TERMS")
        draw_button(GO_X+8, GO_Y+28, 48, 20, "BARS", active=app.vizMode=="bars")
        draw_button(GO_X+62, GO_Y+28, 48, 20, "PIE", active=app.vizMode=="pie")
        draw_button(GO_X+116, GO_Y+28, 64, 20, "SCATTER", active=app.vizMode=="scatter")
        # chart
        chart_x = GO_X+8
        chart_y = GO_Y+54
        chart_w = GO_W-16
        chart_h = GO_H-62
        if app.vizMode=="bars":
            cmap = {"BP": GREEN, "MF": PINK, "CC": CYAN}
            draw_bar_chart(chart_x, chart_y, chart_w, chart_h, app.go_counts, color_map=cmap)
        elif app.vizMode=="pie":
            cmap = {"BP": GREEN, "MF": PINK, "CC": CYAN}
            draw_pie_chart(chart_x, chart_y, chart_w, chart_h, app.go_counts, color_map=cmap)
        else:
            # scatter: plot GO counts vs pathway counts simple
            drawRect(chart_x, chart_y, chart_w, chart_h, fill=rgb(13,18,33), border=PANEL_BORDER, borderWidth=1, roundness=6)
            # axes
            drawLine(chart_x+30, chart_y+chart_h-20, chart_x+chart_w-10, chart_y+chart_h-20, fill=MUTED, lineWidth=1)
            drawLine(chart_x+30, chart_y+10, chart_x+30, chart_y+chart_h-20, fill=MUTED, lineWidth=1)
            # points: BP vs KEGG etc
            try:
                bp = app.go_counts.get("BP",0)
                mf = app.go_counts.get("MF",0)
                cc = app.go_counts.get("CC",0)
                pts = [(bp, app.path_counts.get("KEGG",0), CYAN), (mf, app.path_counts.get("Reactome",0), PINK), (cc, app.path_counts.get("Wiki",0), YELLOW)]
                for px, py, col in pts:
                    if px==0 and py==0:
                        continue
                    rx = chart_x+30 + (px/ max(1, max(bp,mf,cc,1)))*(chart_w-50)
                    ry = chart_y+chart_h-20 - (py/ max(1, max(app.path_counts.values(), default=1)))*(chart_h-30)
                    drawCircle(rx, ry, 6, fill=col, border=WHITE, borderWidth=1)
            except Exception as e:
                try:
                    window.console.log(f"scatter draw error: {e}")
                except:
                    pass

        # PATH panel
        draw_panel(PATH_X, PATH_Y, PATH_W, PATH_H, "PATHWAYS")
        draw_button(PATH_X+8, PATH_Y+28, 72, 22, "PLAY S", active=False, color=YELLOW)
        draw_button(PATH_X+88, PATH_Y+28, 72, 22, "PLAY E", active=False, color=ORANGE)
        drawLabel(f"Gene {app.selectedGeneId or '-'}", PATH_X+170, PATH_Y+39, fill=MUTED, size=13, align="left-center")
        chart_x = PATH_X+8
        chart_y = PATH_Y+56
        chart_w = PATH_W-16
        chart_h = PATH_H-64
        cmap2 = {"KEGG": CYAN, "Reactome": PINK, "Wiki": YELLOW, "PID": GREEN}
        draw_bar_chart(chart_x, chart_y, chart_w, chart_h, app.path_counts, color_map=cmap2)

        # EXON panel
        draw_panel(EXON_X, EXON_Y, EXON_W, EXON_H, "GENOMIC ARCHITECTURE")
        draw_button(EXON_X+8, EXON_Y+28, 72, 22, "SONIFY", active=False, color=CYAN)
        draw_exon_map(EXON_X, EXON_Y, EXON_W, EXON_H, app.selectedGene)

        # STATS panel
        draw_panel(STATS_X, STATS_Y, STATS_W, STATS_H, "STATISTICS")
        draw_button(STATS_X+8, STATS_Y+28, 88, 22, "RECOMPUTE", active=False, color=GREEN)
        # table
        tx = STATS_X+12
        ty = STATS_Y+58
        # headers
        drawLabel("Metric", tx, ty, fill=MUTED, size=13, bold=True, align="left-top")
        drawLabel("Value", tx+120, ty, fill=MUTED, size=13, bold=True, align="left-top")
        drawLabel("Detail", tx+220, ty, fill=MUTED, size=13, bold=True, align="left-top")
        ty+=18
        # rows from stats_local
        try:
            sl = app.stats_local
            rows = [
                ("n hits", f"{sl.get('n',0)}", f"total {app.total}"),
                ("mean score", f"{sl.get('mean',0):.2f}", f"median {sl.get('median',0):.2f}"),
                ("std", f"{sl.get('std',0):.2f}", f"min {sl.get('min',0):.1f} max {sl.get('max',0):.1f}"),
                ("exons", f"{app.exon_stats.get('count',0)}", f"mean len {app.exon_stats.get('mean',0):.0f}"),
                ("GO", f"{sum(app.go_counts.values())}", f"BP {app.go_counts.get('BP',0)} MF {app.go_counts.get('MF',0)}"),
                ("Path", f"{sum(app.path_counts.values())}", f"KEGG {app.path_counts.get('KEGG',0)} React {app.path_counts.get('Reactome',0)}"),
            ]
            for i, (k,v,d) in enumerate(rows):
                ry = ty + i*24
                drawRect(tx-4, ry-2, STATS_W-24, 20, fill=rgb(18,24,42) if i%2==0 else rgb(22,28,48), roundness=4)
                drawLabel(k, tx, ry, fill=WHITE, size=13, align="left-top")
                drawLabel(v, tx+120, ry, fill=YELLOW, size=13, bold=True, align="left-top")
                drawLabel(truncate(d,22), tx+220, ry, fill=MUTED, size=13, align="left-top")
            # pyodide indicator
            drawLabel(f"pyodide:{'on' if HAS_PYODIDE else 'off'}  proc:{'on' if HAS_PROC else 'off'}  fetch:{'on' if HAS_FETCH else 'off'}", tx, ty+6*24+4, fill=MUTED, size=13, align="left-top")
        except Exception as e:
            try:
                window.console.log(f"stats table draw error: {e}")
            except:
                pass

        # footer hint
        drawLabel("Keys: Enter search  n/p next/prev  s score audio  e exon audio  Click rows", W//2, H-10, fill=MUTED, size=13, align="center-bottom")

    except Exception as e:
        try:
            window.console.log(f"redrawAll error: {e}")
        except:
            pass

# ensure draw_panel alias
def draw_panel(x,y,w,h,title):
    drawPanel(x,y,w,h,title)
