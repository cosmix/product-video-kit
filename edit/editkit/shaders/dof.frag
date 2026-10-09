// Depth of field for one layer: a disc gather whose radius comes from the depth at which
// the view ray through this pixel meets the layer's plane (thin-lens circle of confusion),
// plus an optional uniform blur. Sampling a mip chain keeps large radii smooth.
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_src;
uniform vec2 u_res;
uniform int u_plane;          // 1 = derive CoC from the plane, 0 = uniform blur only
uniform mat4 u_inv_vp;        // inverse(proj * view), GL world
uniform vec3 u_eye;
uniform vec3 u_fwd;
uniform vec3 u_p0;            // a point on the layer plane, GL world
uniform vec3 u_n;             // plane normal, GL world
uniform float u_focus;        // focus distance along the view axis
uniform float u_aperture;     // CoC in px for an object at infinity
uniform float u_blur;         // extra uniform blur radius, px
uniform float u_max_radius;

const int N = 48;

float coc_at(vec2 uv) {
    if (u_plane == 0) return 0.0;
    vec2 ndc = vec2(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0);
    vec4 a = u_inv_vp * vec4(ndc, -1.0, 1.0);
    vec4 b = u_inv_vp * vec4(ndc, 1.0, 1.0);
    vec3 o = a.xyz / a.w;
    vec3 dir = normalize(b.xyz / b.w - o);
    float den = dot(u_n, dir);
    if (abs(den) < 1e-5) return 0.0;
    float t = dot(u_n, u_p0 - o) / den;
    vec3 hit = o + dir * t;
    float z = max(dot(hit - u_eye, u_fwd), 1.0);
    return u_aperture * abs(z - u_focus) / z;
}

void main() {
    float coc = coc_at(v_uv);
    float r = min(sqrt(coc * coc + u_blur * u_blur), u_max_radius);
    if (r < 0.35) {
        f_color = texture(u_src, v_uv);
        return;
    }
    float spacing = r * 1.7724539 / sqrt(float(N));
    float lod = max(log2(spacing) - 0.5, 0.0);
    vec4 acc = vec4(0.0);
    for (int i = 0; i < N; ++i) {
        float fi = float(i) + 0.5;
        float rr = sqrt(fi / float(N)) * r;
        float th = fi * 2.39996323;
        vec2 off = vec2(cos(th), sin(th)) * rr / u_res;
        acc += textureLod(u_src, v_uv + off, lod);
    }
    f_color = acc / float(N);
}
