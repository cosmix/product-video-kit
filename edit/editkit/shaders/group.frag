// Composite a rendered group (one scene's layers) into the frame with its transition:
// opacity and a screen-space offset and zoom.
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_src;
uniform vec2 u_res;
uniform float u_opacity;
uniform vec2 u_offset;       // px
uniform float u_zoom;        // about the frame centre

void main() {
    vec2 px = v_uv * u_res;
    vec2 src_px = (px - u_offset - u_res * 0.5) / u_zoom + u_res * 0.5;
    vec4 c = texture(u_src, src_px / u_res);
    if (any(lessThan(src_px, vec2(0.0))) || any(greaterThan(src_px, u_res))) c = vec4(0.0);
    f_color = c * u_opacity;
}
