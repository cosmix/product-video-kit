// A window on a plane: rounded mask, optional title bar and hairline border, content
// texture (trilinear + anisotropic), and a cursor with click ripples drawn in content space.
in vec2 v_p;
out vec4 f_color;

uniform vec2 u_size;           // window size in local px
uniform float u_radius;
uniform float u_titlebar;      // title bar height in local px (0 = no chrome)
uniform sampler2D u_content;
uniform vec4 u_view;           // content sub-rect in texture uv (u0, v0, u1, v1)
uniform float u_lod_bias;
uniform sampler2D u_bar;       // title bar overlay, premultiplied linear
uniform vec3 u_bar_color;
uniform vec3 u_border_color;
uniform float u_border_alpha;
uniform float u_opacity;
uniform float u_dim;           // 0..1 darkening of the content (used to push windows back)
uniform float u_sat;           // content saturation (1 = as captured)

uniform int u_cursor_on;
uniform sampler2D u_cursor;
uniform vec2 u_cursor_pos;     // content uv of the full capture
uniform vec2 u_cursor_size;    // sprite size in capture uv
uniform vec2 u_cursor_hot;     // hotspot inside the sprite, sprite uv
uniform vec4 u_ripples[4];     // (u, v, age s, strength)
uniform vec2 u_capture_px;     // capture viewport size in CSS px (for ripple radii)

vec4 over(vec4 top, vec4 under) { return top + under * (1.0 - top.a); }

vec4 cursor_layer(vec2 cuv) {
    vec4 acc = vec4(0.0);
    for (int i = 0; i < 4; ++i) {
        vec4 r = u_ripples[i];
        if (r.w <= 0.0) continue;
        float k = clamp(r.z / 0.6, 0.0, 1.0);
        float ease = 1.0 - pow(1.0 - k, 3.0);
        vec2 d = (cuv - r.xy) * u_capture_px;
        float dist = length(d);
        float radius = mix(5.0, 30.0, ease);
        float px = length(fwidth(cuv * u_capture_px));
        float ring = clamp(1.0 - abs(dist - radius) / (1.1 + px), 0.0, 1.0);
        float fill = clamp((12.0 - dist) / (1.0 + px), 0.0, 1.0) * (1.0 - smoothstep(0.0, 0.35, r.z));
        float a = (ring * 0.85 * (1.0 - k) * (1.0 - k) + fill * 0.28) * r.w;
        vec3 tint = srgb_to_linear(vec3(0.93, 0.91, 0.95));
        acc = over(vec4(tint * a, a), acc);
    }
    vec2 suv = (cuv - u_cursor_pos) / u_cursor_size + u_cursor_hot;
    if (all(greaterThanEqual(suv, vec2(0.0))) && all(lessThanEqual(suv, vec2(1.0)))) {
        acc = over(texture(u_cursor, suv), acc);
    }
    return acc;
}

void main() {
    float fw = max(length(fwidth(v_p)), 1e-4);
    float d = sd_round_rect(v_p - u_size * 0.5, u_size * 0.5, u_radius);
    float cov = clamp(0.5 - d / fw, 0.0, 1.0);
    if (cov <= 0.0) discard;

    vec4 col;
    if (v_p.y < u_titlebar) {
        vec2 buv = v_p / vec2(u_size.x, u_titlebar);
        col = over(texture(u_bar, buv), vec4(u_bar_color, 1.0));
    } else {
        vec2 local = (v_p - vec2(0.0, u_titlebar)) / vec2(u_size.x, u_size.y - u_titlebar);
        vec2 cuv = mix(u_view.xy, u_view.zw, local);
        col = texture(u_content, cuv, u_lod_bias);
        col.rgb = mix(vec3(dot(col.rgb, vec3(0.2126, 0.7152, 0.0722))), col.rgb, u_sat) * (1.0 - u_dim);
        if (u_cursor_on == 1) col = over(cursor_layer(cuv), col);
    }
    if (u_titlebar > 0.0) {
        float sep = clamp(1.0 - abs(v_p.y - u_titlebar) / fw, 0.0, 1.0);
        col.rgb = mix(col.rgb, u_border_color, sep * u_border_alpha);
        float edge = clamp(1.0 - abs(d / fw + 0.75), 0.0, 1.0);
        col.rgb = mix(col.rgb, u_border_color * 1.6, edge * u_border_alpha);
    }
    float a = cov * u_opacity;
    f_color = vec4(col.rgb, 1.0) * col.a * a;
}
