// Bloom chain. Mode 0: soft-knee threshold + 13-tap downsample; 1: 13-tap downsample;
// 2: 9-tap tent upsample (added onto the next finer level by blending).
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_src;
uniform vec2 u_texel;        // 1 / source size
uniform int u_mode;
uniform float u_threshold;
uniform float u_knee;

vec3 down13(vec2 uv) {
    vec2 t = u_texel;
    vec3 a = texture(u_src, uv + t * vec2(-2, -2)).rgb;
    vec3 b = texture(u_src, uv + t * vec2(0, -2)).rgb;
    vec3 c = texture(u_src, uv + t * vec2(2, -2)).rgb;
    vec3 d = texture(u_src, uv + t * vec2(-2, 0)).rgb;
    vec3 e = texture(u_src, uv).rgb;
    vec3 f = texture(u_src, uv + t * vec2(2, 0)).rgb;
    vec3 g = texture(u_src, uv + t * vec2(-2, 2)).rgb;
    vec3 h = texture(u_src, uv + t * vec2(0, 2)).rgb;
    vec3 i = texture(u_src, uv + t * vec2(2, 2)).rgb;
    vec3 j = texture(u_src, uv + t * vec2(-1, -1)).rgb;
    vec3 k = texture(u_src, uv + t * vec2(1, -1)).rgb;
    vec3 l = texture(u_src, uv + t * vec2(-1, 1)).rgb;
    vec3 m = texture(u_src, uv + t * vec2(1, 1)).rgb;
    return e * 0.125 + (a + c + g + i) * 0.03125 + (b + d + f + h) * 0.0625 + (j + k + l + m) * 0.125;
}

vec3 up9(vec2 uv) {
    vec2 t = u_texel;
    vec3 s = texture(u_src, uv).rgb * 4.0;
    s += (texture(u_src, uv + t * vec2(-1, 0)).rgb + texture(u_src, uv + t * vec2(1, 0)).rgb
        + texture(u_src, uv + t * vec2(0, -1)).rgb + texture(u_src, uv + t * vec2(0, 1)).rgb) * 2.0;
    s += texture(u_src, uv + t * vec2(-1, -1)).rgb + texture(u_src, uv + t * vec2(1, -1)).rgb
        + texture(u_src, uv + t * vec2(-1, 1)).rgb + texture(u_src, uv + t * vec2(1, 1)).rgb;
    return s / 16.0;
}

void main() {
    if (u_mode == 2) {
        f_color = vec4(up9(v_uv), 1.0);
        return;
    }
    vec3 c = down13(v_uv);
    if (u_mode == 0) {
        float br = max(c.r, max(c.g, c.b));
        float soft = clamp(br - u_threshold + u_knee, 0.0, 2.0 * u_knee);
        soft = soft * soft / (4.0 * u_knee + 1e-5);
        float w = max(soft, br - u_threshold) / max(br, 1e-5);
        c *= w;
    }
    f_color = vec4(c, 1.0);
}
