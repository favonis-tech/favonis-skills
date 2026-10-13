# Writing Manim Community scenes (v0.22)

## Skeleton

```python
from manim import *

FONT = "Noto Sans CJK SC"


class Pythagoras(Scene):
    def construct(self):
        title = Text("勾股定理", font=FONT, font_size=48).to_edge(UP)
        formula = MathTex("a^2", "+", "b^2", "=", "c^2").next_to(title, DOWN, buff=0.6)
        self.play(Write(title))
        self.play(Write(formula))
        self.play(formula[4].animate.set_color(YELLOW))
        self.wait(1)
```

Use `Scene` by default, `MovingCameraScene` to zoom or pan, and `ThreeDScene` for 3D. Everything happens inside `construct`; `self.play(...)` animates, `self.add(...)` places without animation, `self.wait(seconds)` holds the frame.

## Frame and layout

- The 16:9 frame is 14.2 × 8 units with the origin at the centre: x runs from −7.1 to 7.1, y from −4 to 4. Keep content within about ±6.5 × ±3.5. A 9:16 render is 4.5 × 8 units, so design for that narrow width.
- Position relative to other objects: `VGroup(a, b, c).arrange(DOWN, buff=0.4, aligned_edge=LEFT)`, `b.next_to(a, RIGHT, buff=0.3)`, `to_edge(UP)`, `to_corner(UL)`, `align_to(a, LEFT)`, `move_to(point)`. Directions: `UP`, `DOWN`, `LEFT`, `RIGHT`, `UL`, `UR`, `DL`, `DR`, `ORIGIN`.
- Fit groups to the frame with `group.scale_to_fit_width(config.frame_width - 1)` or `.scale(0.8)`; check heights the same way.
- Reserve a title band at the top and a caption band at the bottom so they never collide with the diagram.
- Remove what the next beat does not need with `FadeOut`, or transform it into the next element. `self.play(FadeOut(*self.mobjects))` clears the stage.
- Layout helpers that recompute positions, such as `Graph.change_layout`, recentre on the origin; position the object again afterwards.
- Use `z_index` to keep labels above shapes, and seed randomness (`random.seed(0)`, `np.random.seed(0)`) so re-renders match.

## Text and formulas

| Need | Use |
| --- | --- |
| Plain text in any language | `Text("…", font=FONT, font_size=36)` (Pango, full Unicode) |
| Inline styling | `MarkupText("<b>重点</b> <span fgcolor='#FFD700'>高亮</span>", font=FONT)` |
| Several lines | `Paragraph("第一行", "第二行", font=FONT, alignment="left")` |
| Formula | `MathTex(r"\int_0^1 x^2\,dx = \frac{1}{3}")` (LaTeX math mode) |
| LaTeX text with inline math | `Tex(r"Area $= \pi r^2$")` (English only by default) |
| Source code | `Code(code_string=src, language="python", background="window")` |
| Changing number | `DecimalNumber(0, num_decimal_places=2)` with an updater, or `Variable` |

- Installed CJK fonts: Noto Sans CJK SC/TC/JP/KR, Noto Serif CJK SC/TC, WenQuanYi Micro Hei and Zen Hei. List them with `fc-list :lang=zh family`. Always pass `font=` for CJK text; otherwise Pango falls back unpredictably. A missing font appears in the render report's `warnings`.
- The default LaTeX template cannot typeset Chinese. Keep Chinese in `Text` and formulas in `MathTex`, side by side: `VGroup(Text("面积", font=FONT), MathTex(r"= \pi r^2")).arrange(RIGHT, buff=0.2)`. When Chinese must sit inside LaTeX, use this template:

  ```python
  CJK = TexTemplate(
      tex_compiler="xelatex",
      output_format=".xdv",
      preamble=r"\usepackage{amsmath}\usepackage{amssymb}\usepackage[UTF8]{ctex}",
  )
  label = Tex(r"勾股定理：$a^2+b^2=c^2$", tex_template=CJK)
  ```

  Do not use `TexTemplateLibrary.ctex`: it loads LaTeX packages that are not installed.
- These helpers render their labels through the default LaTeX template, so give them only Latin text or numbers: `Brace.get_text`, `axes.get_graph_label`, `Axes(..., axis_config={"include_numbers": True})`, `BarChart` names and values, and `Graph(..., labels=True)`. For Chinese labels, create `Text` objects and place them with `next_to` or `axes.c2p`.
- Write LaTeX in raw strings (`r"..."`). Split a formula into indexable parts with separate arguments (`MathTex("a^2", "+", "b^2")`) or double braces (`MathTex(r"{{a^2}} + {{b^2}}")`), colour parts with `set_color_by_tex("c^2", YELLOW)`, and morph between formulas with `TransformMatchingTex(old, new)`.
- Font sizes at 1080p: titles 44–56, body 30–36, labels 24–28, nothing below 20. Long sentences belong in narration or captions, not in the diagram.

## Animations

- **Bring in:** `Create` (strokes), `Write` (text and formulas), `DrawBorderThenFill`, `FadeIn(obj, shift=UP)`, `GrowFromCenter`, `GrowArrow`, `SpinInFromNothing`.
- **Change:** `obj.animate.shift(RIGHT).scale(1.2).set_color(RED)` chains changes into one animation. `Transform(a, b)` keeps `a` on screen in the shape of `b`; `ReplacementTransform(a, b)` puts `b` on screen, so use it when later code refers to `b`. Also `TransformMatchingTex`, `TransformMatchingShapes`, `MoveAlongPath`, `Rotate(obj, angle=PI / 2)`.
- **Emphasise:** `Indicate`, `Circumscribe`, `Flash`, `Wiggle`, `FocusOn`, `ApplyWave`, `ShowPassingFlash`. Dim the rest with `set_opacity(0.3)`.
- **Remove:** `FadeOut`, `Uncreate`, `Unwrite`, `ShrinkToCenter`.
- **Combine:** animations in one `self.play(...)` run together; use `LaggedStart(*animations, lag_ratio=0.2)`, `AnimationGroup` and `Succession` for staggering and sequences.
- **Timing:** set `run_time=` per `play` and `rate_func=` (`smooth` by default, `linear`, `there_and_back`, `rush_into`, `rush_from`). Typical values: 1–2 seconds per animation, a 0.5–1.5 second pause after a key reveal, and enough time to read each new line of text.
- **Motion driven by values:** `t = ValueTracker(0)` then `self.play(t.animate.set_value(5))`. `always_redraw(lambda: Dot(axes.c2p(t.get_value(), f(t.get_value()))))` rebuilds an object every frame; `obj.add_updater(lambda m: m.next_to(dot, UP))` keeps one attached; `clear_updaters()` stops it.

Old APIs from manimgl or older tutorials fail in Community 0.22. Replace `ShowCreation` with `Create`, `TextMobject`/`TexMobject` with `Tex`/`MathTex`, `GraphScene` and `get_graph` with `Axes` and `axes.plot`, `FadeInFrom` with `FadeIn(obj, shift=...)`, `ShowCreationThenDestruction` with `ShowPassingFlash`, class-level `CONFIG` dictionaries with constructor arguments, and `self.camera_frame` with `self.camera.frame` in a `MovingCameraScene`.

## Shapes, graphs and data

- **Geometry:** `Dot`, `Line`, `DashedLine`, `Arrow`, `DoubleArrow`, `Vector`, `Circle`, `Ellipse`, `Arc`, `Sector`, `Square`, `Rectangle`, `RoundedRectangle`, `Polygon`, `RegularPolygon`, `Triangle`, `Star`, `Angle(line1, line2)`, `RightAngle`, `Brace(obj, DOWN)`, `SurroundingRectangle`, `BackgroundRectangle`, `Cross`.
- **Coordinates:** `axes = Axes(x_range=[-3, 3, 1], y_range=[0, 9, 3], x_length=6, y_length=4)`; `curve = axes.plot(lambda x: x**2, x_range=[-3, 3])`; place objects with `axes.c2p(x, y)`; shade with `axes.get_area(curve, x_range=[0, 2])`; approximate with `axes.get_riemann_rectangles(curve, x_range=[0, 2], dx=0.25)`. Also `NumberPlane`, `NumberLine` and `ParametricFunction`.
- **Tables and matrices:** `Table([["甲", "乙"], ["丙", "丁"]], element_to_mobject_config={"font": FONT}, col_labels=[Text("列一", font=FONT), Text("列二", font=FONT)])`, `MathTable`, `Matrix([[1, 2], [3, 4]])`.
- **Charts:** `BarChart([3, 5, 2], y_range=[0, 6, 2])` for Latin bar names. With Chinese categories, build the chart from `Axes` and `Rectangle`s with `Text` labels.
- **Networks and trees:** `Graph(vertices, edges, layout="circular")` with `layout` set to `"spring"`, `"circular"` or `"tree"` (the last needs `root_vertex=`), and `DiGraph` for directed edges. Animate structure with `graph.animate.change_layout(...)`, `add_vertices` and `add_edges`.
- **Images and vectors:** `ImageMobject("assets/photo.png")` and `SVGMobject("assets/icon.svg")` with project-relative paths.
- **3D:** in a `ThreeDScene`, call `self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)`, use `ThreeDAxes` and `Surface(lambda u, v: axes.c2p(u, v, f(u, v)), u_range=[-2, 2], v_range=[-2, 2], resolution=(24, 24))`, and rotate with `self.begin_ambient_camera_rotation(rate=0.2)`. Keep titles flat with `self.add_fixed_in_frame_mobjects(title)`. The Cairo renderer draws 3D slowly: keep surfaces coarse and scenes short.
- **Camera:** in a `MovingCameraScene`, zoom with `self.play(self.camera.frame.animate.scale(0.5).move_to(target))`; call `self.camera.frame.save_state()` first and `self.play(Restore(self.camera.frame))` to return.

## Style

- The background is black and default strokes and text are white. For a light look set `self.camera.background_color = WHITE` and give every element a dark colour.
- Keep a small palette: one main colour, one highlight such as `YELLOW`, and neutrals. Named colours include `BLUE`, `TEAL`, `GREEN`, `YELLOW`, `GOLD`, `RED`, `MAROON`, `PURPLE`, `PINK`, `ORANGE` and `GREY`, with shades such as `BLUE_C` and `BLUE_E`; hex strings also work.
- Highlight what the viewer should look at now, and move or dim the rest.

## Performance and errors

- Draft at quality `l`. Render time grows with resolution, frame rate and the number of objects; 3D surfaces, many updaters and large LaTeX blocks are the slowest parts.
- A LaTeX failure shows the TeX error in the report's `error`. Check raw strings, matching braces, and Chinese inside the default template. Each distinct LaTeX string is compiled once and cached.
- A `NameError` on an animation or mobject usually means an old API; see the replacement list above.
