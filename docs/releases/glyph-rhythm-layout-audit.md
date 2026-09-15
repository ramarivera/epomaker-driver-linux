# Glyph rhythm painter layout audit

Static audit of vendor rhythm painter geometry and sampling. No vendor code was executed; no audio, capture, HID, network, or hardware operation was attempted. Offsets are UTF-8 byte offsets in extracted bytes.

## Sources

| Source | Archive SHA-256 | Relevant JS and SHA-256 |
| --- | --- | --- |
| Windows `EPOMAKER_v4_setup_3.2.22_WIN2026071.zip` | `922f408edf79ca3186f749bed629ad2bd3fac425bfc170d81ddb00d2e3cbd483` | `resources/app/dist/js/57cfa1b3.js`, 130747 bytes, `9b9e81be794a543617eec5a125c9efd55004c78d6a4c17ea30318c5aa9a6cd22` |
| macOS `EPOMAKER_Driver_v43.2.22_MAC2026072.zip` | `659d2a2f6ceda45a0df72bccd9c83ffb4cb7b6a1472cb929b7d081067c3d45bc` | `Contents/Resources/app/dist/js/13da2307.js`, 130753 bytes, `e58f558ab99d02de0c74c7febed4e8624064106cd0dd55339b82c4f6ce583d31` |

Windows byte evidence: painter class/constructor 38401–38728; bounds helper 39090; `clampPosition` 39361; `setPos` 39673; `setSize` 39844; `setRotation` 40469; `moveToCenter` 40915; `resetLayout` 41315; `updateOutputs` 41508; `draw` 41733; `rotateDraw` 42067; `updateScreen` 43140. Renderers: `drawSpectrum` 9428, `drawCircle` 9829, `drawTripleCircle` 10134, `drawMatrix` 10839, `drawTriangle` 11100. Mac routines are equivalent (for example `DEFAULT_WIDTH=315` at 38963).

## Canvas and defaults

The painter output canvas starts with `cols=21`, `rows=6`; `setRank` can replace these, but this light-sync instance uses 21×6. The rhythm source is the separate shared `yt.canvas`; `init()` sets its bitmap width/height to `clientWidth`/`clientHeight`. Therefore 315×90 are painter defaults, not source-canvas dimensions.

```text
DEFAULT_X=0, DEFAULT_Y=0, DEFAULT_WIDTH=315, DEFAULT_HEIGHT=90
MIN_WIDTH=90, MIN_HEIGHT=60, DEFAULT_ROTATION_DEGREE=0
UI_PADDING_TOP=24, UI_PADDING_RIGHT=32
```

## Geometry formulas

Let `C,H` be source client width/height, `w,h` the unrotated painter size, and `θ` degrees:

```text
r=abs(cos(θ·π/180)); s=abs(sin(θ·π/180))
rotatedW=w·r+h·s; rotatedH=w·s+h·r
xMin=(rotatedW−w)/2
xMax=C−32−(rotatedW+w)/2
yMin=24+(rotatedH−h)/2
yMax=H−(rotatedH+h)/2
x=max(xMin,min(x,xMax)); y=max(yMin,min(y,yMax))
```

`setPos` applies those clamps and recomputes `s_hypotenuse=sqrt(w²+h²)`. `setSize` first applies minimums. With `availableW=C−32`, `availableH=H−24`, it keeps a rotated-fitting size or scales by `min(availableW/rotatedW,availableH/rotatedH,1)`, then stores `max(floor(requestW·scale),90)` and `max(floor(requestH·scale),60)`, recomputes the hypotenuse, and reclamps position. Minimums are applied after scaling, so tiny canvases can still fail to contain the minimum.

`setRotation` commits only if the current rotated AABB satisfies `rotatedW≤C−32` and `rotatedH≤H−24`; otherwise it silently leaves the prior angle. `moveToCenter` uses `sx=round((C−32)/2−w/2)` and `sy=round(24+(H−24)/2−h/2)`. `resetLayout` restores zero rotation, 315×90 through `setSize`, then centers. The normal UI limits angle input to −180…180; a zero-sized source canvas bypasses these checks.

## Sampling

At zero rotation, `draw()` performs `drawImage(sourceCanvas,sx,sy,w,h,0,0,21,6)`, reads row-major RGBA, and emits 378 RGB values. Each channel is alpha-premultiplied without rounding: `factor=alpha/255; [red·factor,green·factor,blue·factor]`.

At nonzero rotation, `rotateDraw()` allocates a square output canvas of side `q=sqrt(21²+6²)` and uses source square side `p=sqrt(w²+h²)`. It rotates around the square center by `(360−θ)` and draws:

```text
cx=sx+w/2; cy=sy+h/2
drawImage(sourceCanvas,cx−p/2,cy−p/2,p,p,−q/2,−q/2,q,q)
```

It center-crops the rotated square with source rectangle `((q−21)/2,(q−6)/2,21,6)` into `(0,0,21,6)`, then performs the same read/premultiplication. Rhythm updates choose this path when rotation is nonzero and schedule callbacks after 8 ms.

## Screen boundary and Glyph mapping

Rhythm renderers draw into `yt.canvas`; their `setScale` geometry (`dw=canvasWidth·scale`, `dh=canvasHeight·scale`, centered by `dx,dy`) is independent of painter layout. `updateScreen()` forwards the screen singleton's existing `outputs` directly and does not read `sx,sy,sw,sh,rotation`, so rhythm layout controls do not apply to screen mode.

No selected-keyboard Glyph offset/size map appears in this light-sync chunk. The fixed rhythm output geometry is only 21×6 row-major RGB. The repository's `src/epomaker_driver/data/glyph-key-layout.json` is a 788×277 key-editor geometry and is not referenced here.

Unknowns are the actual CSS/client dimensions, device-pixel-ratio behavior, `drawImage` interpolation, firmware interpretation, and empty-positive-set renderer behavior. Linux should expose the source canvas box explicitly and define zero-input behavior.
