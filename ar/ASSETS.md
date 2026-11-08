# Cyberpunk assets and procedural geometry

## Restricted external pack

The active catalog is exclusively **Low Poly Cyberpunk Street Pack v1.0** by
reodesuxz (`https://reodesuxz.itch.io/low-poly-cyberpunk-pack`). The archive
discovered at `~/Downloads/LowPolyCyberpunkPack_v1.0.zip` contains 23 GLBs,
plus equivalent OBJ/FBX files and one Blender scene. GLB is used directly.

Copy the archive to `~/hackutd26_assets/` or pass that directory with
`--assets-dir`. `AssetManager` lazily extracts only requested GLBs to
`.cyberpunk-cache`, preserves authored flat materials/vertex colors, centers
the pivot at the bottom of the model, and normalizes to the per-placement
metric target. Raw assets are intentionally absent from Git. See
`assets/CYBERPUNK_ASSET_LICENSE.md`: use in projects is allowed, standalone
asset redistribution and AI training are prohibited.

`assets/manifest.json` lists the real inventory: android robot, arcade
cabinet, cable junction, delivery drone, dumpster, holographic billboard,
hover bike/car, hydrant pipe, jersey barrier, neon crate/signs, noodle shop,
power generator, ramen cart, rooftop AC, server rack, street lamp, tower,
traffic hologram, trash bin, and vending kiosk. `--scene asset-gallery`
previews all 23 with Tab/Shift+Tab.

## Procedural gameplay assets

No imported model is used as golf terrain. `src/golf_scene.py` creates:

- a 97×97 (Balanced; 65² Performance, 129² Quality) indexed continuous
  heightfield and beveled floating-island sides with cyan perimeter trim;
- a dark-teal fairway ribbon (9 cross-sections, exact rendered-triangle height)
  with bright cyan edges and lime direction dashes;
- irregular plasma pools with dark rims and bright halo rings (40 segments);
- an illuminated 22 mm sphere with a small cyan dot, and lime/cyan
  holographic target with beacon;
- neon-edged barriers and crystalline obstacles;
- a static Bullet triangle mesh from the exact visible terrain vertices.

`src/cyber_theme.py` owns the graphite, steel, cyan, magenta, lime, amber and
white palette (sRGB authored, linearized once) and reusable
metallic/emissive materials. Vertex-coloured terrain/ribbon use no
MaterialAttrib so vertex colours drive the light response; neon uses flat
colour with lights off and needs no bloom. Imported models are only sparse
environment detail (18–34 mm `max` sizing, upright, terrain-height placed)
and are loaded on demand; missing models produce a procedural cyber block,
never a legacy asset. Textures use linear-mag, trilinear-mip-min and about
8× anisotropic filtering; imported emission is scaled ×0.8 to avoid clipping
and oversized halos.

## Physical dimensions and scale

At the default 60×40 cm table the terrain occupies 54×34 cm (90%×85%). The
terrain is authored in course-local metres divided by `COURSE_SCALE`, then the
single existing `course-scale-root` restores final table-local metres. The
22 mm ball (configurable 20–43 mm) compensates for root scale exactly once.
Fairways are 12.0/9.0/6.5 cm (Easy/Medium/Hard) plus compact landing pads.
Imported scenery gets explicit per-placement metric targets divided by the
design scale. Physical obstacle footprints remain measured in table-local
metres and their virtual overlays query the generated terrain height without
changing measured XY. Hardware check 2026-11-08 (VITURE Luma Ultra, DP-1
1920×1200): Balanced mono renders at requested MSAA 4 / actual 8, sRGB on,
97² mesh, ~119 FPS sustained (~8.3 ms); Carina 6DoF locked, table anchor
APPROX conf 0.50 with reprojection ~0.3–1.0 px. Combiner appearance (true
black transparency, neon comfort) still needs a wearer’s eye check; stereo
bloom remains untested.

The removed Minigolf/Nature/pond archives and bundled models are not present
in the active manifest or scene. Original downloads outside this repository
are untouched.
