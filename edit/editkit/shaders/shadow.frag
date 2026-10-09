// Layered soft drop shadow of a rounded rectangle, in the window's plane.
in vec2 v_p;
out vec4 f_color;

uniform vec2 u_size;
uniform float u_radius;
uniform float u_opacity;
uniform vec4 u_layers[3];   // (offset y, blur sigma, alpha, spread) in local px
uniform vec3 u_color;       // linear

void main() {
    float a = 0.0;
    for (int i = 0; i < 3; ++i) {
        vec4 L = u_layers[i];
        vec2 p = v_p - u_size * 0.5 - vec2(0.0, L.x);
        float d = sd_round_rect(p, u_size * 0.5 + L.w, u_radius + L.w);
        float s = 0.5 - 0.5 * erf_approx(d / (L.y * 1.41421356));
        a = a + L.z * s * (1.0 - a);
    }
    a *= u_opacity;
    f_color = vec4(u_color * a, a);
}
