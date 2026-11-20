#!/usr/bin/env python3
"""Build docs/method3d.html (the embedded 3D method schematic) from the authoring file.

The source is a standalone page ("Planning ahead of synthesis (3D).html", three.js, real output frames
embedded as base64). For the project page it is embedded in an iframe, so this script:
  * translates the Chinese UI to English and drops the paper figure label "(b)" and internal run IDs;
  * pins the dark theme and matches the page background;
  * lets plain wheel / vertical swipes scroll the page (pinch or Ctrl/Cmd+wheel zooms the 3D view);
  * pauses rendering while the parent page reports the iframe is off-screen (postMessage).
Every replacement must match exactly once, so changes in the source are caught instead of silently skipped.

Usage: python3 tools/make_method3d.py --src PATH [--out docs/method3d.html]
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEGEND_EN = '''<summary>Setup &amp; legend</summary>
      <div class="lg-sec">
        <h3><i class="sw plan"></i>Stage 1 · Planning stream</h3>
        <dl>
          <dt>Video</dt><dd>H/2 × W/2, f/2 (12 fps)</dd>
          <dt>1 chunk</dt><dd>8 latents ≈ 2.67 s = 4 video chunks</dd>
          <dt>KV</dt><dd>sink P<sub>0</sub> + the 3 most recent plan chunks</dd>
        </dl>
      </div>
      <div class="lg-sec">
        <h3><i class="sw vid"></i>Stage 2 · Synthesis stream</h3>
        <dl>
          <dt>Video</dt><dd>H × W, f (24 fps)</dd>
          <dt>1 chunk</dt><dd>4 latents ≈ 0.67 s</dd>
          <dt>KV</dt><dd>sink V<sub>0</sub> + the previous 3 video chunks</dd>
          <dt>Condition</dt><dd>a plan window covering past and future</dd>
        </dl>
      </div>
      <div class="lg-sec">
        <h3>Rolling</h3>
        <dl>
          <dt>Each period</dt><dd>Stage 2 synthesizes the 4 video chunks under P<sub>j</sub> while Stage 1 generates P<sub>j+2</sub> on another GPU; then everything advances by one plan chunk</dd>
          <dt>Middle</dt><dd>“⋯” marks omitted chunks; the sinks are always kept</dd>
        </dl>
      </div>
      <p class="lg-note">Each tile is one latent frame, drawn from real Plan2Stream output frames (Stage 1 = plan, Stage 2 = synthesized video). Audio bars show the real audio envelope of the synthesized video.</p>'''

REPLACEMENTS = [
    ('<html lang="zh-CN">', '<html lang="en" data-theme="dark">'),
    ('</style>\n</head>',
     '/* project-page embed: match the page background; no toolbar, no footer (legend / step status / hints) */\n'
     ':root[data-theme="dark"]{--bg:#0d1018;--bg2:#07080d;}\n'
     '.ctrl,.foot{display:none!important;}\n</style>\n</head>'),
    # lane labels: keep the name, subtitle and KV line; drop the video / audio spec lines
    ('<span class="spec"><span><i class="ic v"></i><em>video</em>H/2 × W/2, f/2 fps</span><span><i class="ic a"></i><em>audio</em>same media span</span><span><i class="ic k"></i><em>KV</em>sink + recent 3</span></span>',
     '<span class="spec"><span><i class="ic k"></i><em>KV</em>sink + recent 3</span></span>'),
    ('<span class="spec"><span><i class="ic v"></i><em>video</em>H × W, f fps</span><span><i class="ic a"></i><em>audio</em>same media span</span><span><i class="ic k"></i><em>KV</em>sink + history 3</span></span>',
     '<span class="spec"><span><i class="ic k"></i><em>KV</em>sink + history 3</span></span>'),
    # the stream is unbounded: the axis ends in "⋯ ∞" (as in the paper figure) and stays visible
    ("const endL=label('⋯ 32 s',", "const endL=label('⋯ ∞',"),
    ("  endL.vis=S.j<9;", "  endL.vis=true;"),
    # ---- unbounded rolling: never reach the end of the 32 s sample -------------------------------
    # Play periods j = 3..9 (Stage 1 always has a P_{j+2} to make). On arriving at j = 9 the view is
    # rebased to j = 4, which looks identical relative to the window; rolling tiles then show frames
    # 5 periods later (looping the clip), tick labels keep counting up, and sliders snap (no glide).
    ("const J0=3, J1=11;", "const J0=3, J1=9;"),
    ("function loadAtlas(key){",
     "const WRAP_FROM=9, WRAP_TO=4, WRAP_D=WRAP_FROM-WRAP_TO;\n"
     "let wraps=0;\n"
     "function latOff(key){return wraps*WRAP_D*(key==='s1'?8:16);}\n"
     "function atlasIdx(key,L){const A=REAL[key];return L<(key==='s1'?9:5)?Math.min(L,A.n-1):(L+latOff(key))%A.n;}  // sinks keep their frames\n"
     "function drawJobs(key){\n"
     "  const A=REAL[key], img=atlasImg[key]; if(!img)return;\n"
     "  for(const j of texJobs[key]){\n"
     "    const g=j.c.getContext('2d'), k=atlasIdx(key,j.k);\n"
     "    g.clearRect(0,0,A.w,A.h);\n"
     "    g.drawImage(img,(k%A.cols)*A.w,Math.floor(k/A.cols)*A.h,A.w,A.h,0,0,A.w,A.h);\n"
     "    j.t[0].needsUpdate=true; j.t[1].needsUpdate=true;\n"
     "  }\n"
     "}\n"
     "function loadAtlas(key){"),
    ("""    atlasImg[key]=img;
    for(const j of texJobs[key]){
      const g=j.c.getContext('2d'), k=Math.min(j.k,A.n-1);
      g.drawImage(img,(k%A.cols)*A.w,Math.floor(k/A.cols)*A.h,A.w,A.h,0,0,A.w,A.h);
      j.t[0].needsUpdate=true; j.t[1].needsUpdate=true;
    }
    refreshStrip();""",
     """    atlasImg[key]=img;
    drawJobs(key);
    refreshStrip();"""),
    ("i=Math.min(L,A.n-1);Tq.c", "i=atlasIdx(key,L);Tq.c"),
    # no footer in the embed: sit the scene lower so the top frame strip does not cover it
    ("renderer.setSize(w,h); camera.aspect=w/h; camera.updateProjectionMatrix();",
     "renderer.setSize(w,h); camera.aspect=w/h;\n"
     "  camera.setViewOffset(w,h,0,-Math.round(h*SCENE_DROP),w,h);  // shift the rendered view down (labels follow)\n"
     "  camera.updateProjectionMatrix();"),
    ("function resize(){", "const SCENE_DROP=0.15;  // fraction of the view height\nfunction resize(){"),
    ("i=Math.max(0,Math.min(e.length-1,Math.floor(t*REAL.envRate)));",
     "i=Math.max(0,Math.floor(t*REAL.envRate))%e.length;  // loop the envelope for unbounded rolling"),
    ("return {im:im,ln:ln,bars:bars,w:step*0.62,yc:yc,d:depth,last:-1};",
     "return {im:im,ln:ln,bars:bars,w:step*0.62,yc:yc,d:depth,last:-1,maxA:maxA};"),
    ("for(let c=1;c<=NP;c++)label(fs(c*8/3)+' s',4*c,-0.42,1.3,{cls:'ax',a:'t',sp:'r',m:0.05});",
     "const tickLab=[];\n"
     "for(let c=1;c<=NP;c++)tickLab[c]=label(fs(c*8/3)+' s',4*c,-0.42,1.3,{cls:'ax',a:'t',sp:'r',m:0.05});"),
    ("""      if(t>=slideDur(e)+DUR_V){if(k<NE-1){k++;t=0;}else{t=slideDur(e)+DUR_V;holdT=0;}}
    }
  }
  applyState();""",
     """      if(t>=slideDur(e)+DUR_V){if(k<NE-1){k++;t=0;}else{t=slideDur(e)+DUR_V;holdT=0;}}
    }
  }
  {const e=STEPS[k]; if(e.j===WRAP_FROM&&e.m===0&&t>=slideDur(e))rebase();}
  applyState();"""),
    ("function tick(now){\n  const dt=clamp((now-last)/1000,0,0.05); last=now;",
     "function rebase(){\n"
     "  wraps++;\n"
     "  k=STEPS.findIndex(function(s){return s.j===WRAP_TO&&s.m===0;});\n"
     "  t=slideDur(STEPS[k]);\n"
     "  for(const s of sliders)s.userData.init=false;   // snap windows / KV lids instead of gliding back\n"
     "  S.ke=-2;\n"
     "  drawJobs('s1'); drawJobs('s2');\n"
     "  for(let c=1;c<=NP;c++)setHtml(tickLab[c],fs((c+wraps*WRAP_D)*8/3)+' s');\n"
     "  const dx=wraps*WRAP_D*4;                         // audio bars follow the frames (same media time)\n"
     "  for(const ch of chunks){if(ch.g.parent!==roll)continue;for(const b of ch.aud.bars)b.h=Math.max(0.05,amp(b.x+dx))*ch.aud.maxA*2;ch.aud.last=-1;}\n"
     "  applyState();\n"
     "  for(const ch of chunks){if(ch.g.parent===roll&&ch.status==='done')setBars(ch.aud,1);}\n"
     "  guide.userData.x=guide.userData.tx;\n"
     "}\n"
     "function tick(now){\n  const dt=clamp((now-last)/1000,0,0.05); last=now;"),
    ('<h1>(b) Planning ahead of synthesis</h1>', '<h1>Planning ahead of synthesis</h1>'),
    ('aria-label="视图控制"', 'aria-label="View controls"'),
    ('aria-label="播放">\n        <span class="seg-l">播放</span>', 'aria-label="Playback">\n        <span class="seg-l">Play</span>'),
    ('aria-label="上一步"', 'aria-label="Previous step"'),
    ('<button type="button" id="play" aria-pressed="true">暂停</button>', '<button type="button" id="play" aria-pressed="true">Pause</button>'),
    ('aria-label="下一步"', 'aria-label="Next step"'),
    ('aria-label="播放速度"', 'aria-label="Playback speed"'),
    ('aria-label="视角">\n        <span class="seg-l">视角</span>', 'aria-label="View">\n        <span class="seg-l">View</span>'),
    ('aria-pressed="true">等轴</button>', 'aria-pressed="true">Iso</button>'),
    ('aria-pressed="false">正视</button>', 'aria-pressed="false">Front</button>'),
    ('aria-pressed="false">帧堆叠</button>', 'aria-pressed="false">Stack</button>'),
    ('aria-label="显示">\n        <span class="seg-l">显示</span>', 'aria-label="Show">\n        <span class="seg-l">Show</span>'),
    ('aria-pressed="true">音频</button>', 'aria-pressed="true">Audio</button>'),
    ('aria-pressed="true">窗口</button>', 'aria-pressed="true">Windows</button>'),
    ('aria-pressed="true">标注</button>', 'aria-pressed="true">Labels</button>'),
    ('id="replay">从头播放</button>', 'id="replay">Replay</button>'),
    ('aria-label="当前步骤"', 'aria-label="Current step"'),
    ('<div class="hint">空格 播放/暂停 · ←/→ 单步<br>拖拽旋转 · 滚轮缩放</div>',
     '<div class="hint">Space: play / pause · ←/→: step<br>Drag to rotate · pinch or Ctrl+scroll to zoom</div>'),
    ('<div id="err" hidden>无法加载 three.js，请检查网络后刷新页面。</div>',
     '<div id="err" hidden>Could not load three.js. Check your connection and reload.</div>'),
    ("renderer.domElement.setAttribute('aria-label','三维示意图：上方 Stage 1 planning stream，下方 Stage 2 synthesis stream；左侧 sink 固定，中间省略，右侧两个 stage 并行生成并一段段向前滚动');",
     "renderer.domElement.setAttribute('aria-label','3D schematic: the Stage 1 planning stream on top and the Stage 2 synthesis stream below; the sinks stay fixed on the left, the middle is omitted, and on the right both stages generate in parallel and roll forward chunk by chunk');"),
    ("  controls.minDistance=5; controls.maxDistance=90; controls.rotateSpeed=0.7;\n}",
     "  controls.minDistance=5; controls.maxDistance=90; controls.rotateSpeed=0.7;\n}\n"
     "/* embedded in a scrolling page: plain wheel / vertical swipe scroll the page; pinch or Ctrl/Cmd+wheel zooms */\n"
     "stage.addEventListener('wheel',function(e){controls.enableZoom=!!(e.ctrlKey||e.metaKey);},{capture:true,passive:true});\n"
     "renderer.domElement.style.touchAction='pan-y';"),
    ("stripH.innerHTML='真实帧 · 两个 stage 同时在生成';", "stripH.innerHTML='Real frames · both stages generating at once';"),
    ("""const pTxt=S.p!==null?'Stage 1 → P<sub>j+2</sub> <span class="abs">（P'+sub(S.p)+'）</span>':'Stage 1 <span class="abs">（plan 已全部完成）</span>';""",
     """const pTxt=S.p!==null?'Stage 1 → P<sub>j+2</sub> <span class="abs">(P'+sub(S.p)+')</span>':'Stage 1 <span class="abs">(all plans complete)</span>';"""),
    ("""hud1.innerHTML=pTxt+'<span class="par">‖</span>Stage 2 → V<sub>k</sub> <span class="abs">（V'+sub(v)+'，P<sub>j</sub> 下第 '+(r+1)+'/4 个）</span>';""",
     """hud1.innerHTML=pTxt+'<span class="par">‖</span>Stage 2 → V<sub>k</sub> <span class="abs">(V'+sub(v)+', chunk '+(r+1)+'/4 under P<sub>j</sub>)</span>';"""),
    ("""hud2.innerHTML='两个 stage 在不同 GPU 上同时运行：'+(S.p!==null?'Stage 1 用 sink P<sub>0</sub> + P<sub>j−1</sub>…P<sub>j+1</sub> 规划 P<sub>j+2</sub>；':'')+
    'Stage 2 用 plan 窗口（含已规划好的未来 P<sub>j+1</sub>）+ sink V<sub>0</sub> + 前 3 个 video chunk 合成 V<sub>k</sub>。';""",
     """hud2.innerHTML='Both stages run at the same time on separate GPUs. '+(S.p!==null?'Stage 1 plans P<sub>j+2</sub> from sink P<sub>0</sub> + P<sub>j−1</sub>…P<sub>j+1</sub>; ':'')+
    'Stage 2 synthesizes V<sub>k</sub> from the plan window (including the already planned future P<sub>j+1</sub>), sink V<sub>0</sub> and the previous 3 video chunks.';"""),
    ("progT.textContent='已生成 '+fs(Math.min(32,done))+' s';", "progT.textContent=fs(Math.min(32,done))+' s generated';"),
    ("playBtn.textContent=p?'暂停':'播放';", "playBtn.textContent=p?'Pause':'Play';"),
    ("function tick(now){\n  const dt=clamp((now-last)/1000,0,0.05); last=now;",
     "/* the parent page posts {p2s:'visibility', visible} so rendering pauses while scrolled away */\n"
     "let offscreen=false;\n"
     "window.addEventListener('message',function(e){if(e.data&&e.data.p2s==='visibility')offscreen=!e.data.visible;});\n"
     "function tick(now){\n  if(offscreen){last=now;requestAnimationFrame(tick);return;}\n"
     "  const dt=clamp((now-last)/1000,0,0.05); last=now;"),
]
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True, help='path to "Planning ahead of synthesis (3D).html"')
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "method3d.html")
    args = ap.parse_args()
    s = args.src.read_text(encoding="utf-8")

    a = s.index("<summary>配置与图例</summary>")
    end_note = "<code>vid1</code> 的真实音频包络。</p>"
    b = s.index(end_note, a) + len(end_note)
    s = s[:a] + LEGEND_EN + s[b:]

    for old, new in REPLACEMENTS:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"expected exactly one match, found {n}: {old[:90]!r}")
        s = s.replace(old, new)

    leftover = [(i + 1, line.strip()[:80]) for i, line in enumerate(s.splitlines())
                if len(line) < 20000 and CJK.search(line)]
    if leftover:
        raise SystemExit(f"untranslated text left: {leftover[:8]}")
    args.out.write_text(s, encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
