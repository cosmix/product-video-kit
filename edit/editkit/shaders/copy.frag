// Weighted copy (shutter-sample accumulation).
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_src;
uniform float u_weight;

void main() {
    f_color = texture(u_src, v_uv) * u_weight;
}
