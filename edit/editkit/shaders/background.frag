// The ground: one flat colour, the design file's background (editkit/design.py).
in vec2 v_uv;
out vec4 f_color;

uniform vec3 u_color;       // linear
uniform float u_level;      // overall level

void main() {
    f_color = vec4(u_color * u_level, 1.0);
}
