// decoded frame -> linear, premultiplied RGBA16F
in vec2 v_uv;
out vec4 f_color;

uniform int u_mode;          // 0 = NV12, 1 = RGBA8 straight alpha
uniform sampler2D u_y;       // NV12 luma (R8) or RGBA8
uniform sampler2D u_uv;      // NV12 chroma (RG8)
uniform mat3 u_matrix;       // Y'CbCr -> R'G'B'
uniform vec3 u_offset;       // subtracted before the matrix
uniform vec3 u_scale;        // range expansion before the matrix

void main() {
    vec2 uv = vec2(v_uv.x, v_uv.y);  // frames are uploaded top row first; v=0 is the top
    if (u_mode == 0) {
        vec3 yuv = vec3(texture(u_y, uv).r, texture(u_uv, uv).rg);
        vec3 rgb = u_matrix * ((yuv - u_offset) * u_scale);
        f_color = vec4(srgb_to_linear(clamp(rgb, 0.0, 1.0)), 1.0);
    } else {
        vec4 c = texture(u_y, uv);
        f_color = vec4(srgb_to_linear(c.rgb) * c.a, c.a);
    }
}
