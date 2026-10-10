// Headless projectM renderer: EGL pbuffer + synthetic 128bpm music (or real audio, see below).
// usage: render preset.milk W H FRAMES  > raw rgb24 frames on stdout
#define _GNU_SOURCE
#include <dlfcn.h>
#include <time.h>
static double now(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec + ts.tv_nsec * 1e-9; }
#include <EGL/egl.h>
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <GL/glext.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <projectM-4/projectM.h>

static int failed = 0;
static void onfail(const char *f, const char *msg, void *u) {
    (void)u; fprintf(stderr, "PRESET FAIL %s: %s\n", f, msg); failed = 1;
}

// Interpose GL compile/link to surface shader errors (projectM swallows them).
int shader_errors = 0;
int shader_count = 0;
void glCompileShader(GLuint sh) {
    static void (*real)(GLuint);
    if (!real) real = dlsym(RTLD_NEXT, "glCompileShader");
    real(sh); shader_count++;
    if (getenv("TRACE")) {
        static char s[65536]; glGetShaderSource(sh, sizeof s, 0, s);
        fprintf(stderr, "==== SHADER %d ====\n%s\n", shader_count, s);
    }
    GLint ok = 0; glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[8192]; glGetShaderInfoLog(sh, sizeof log, 0, log);
        fprintf(stderr, "SHADER COMPILE ERROR:\n%s\n", log);
        if (getenv("DUMP_SRC")) {
            static char src[65536]; glGetShaderSource(sh, sizeof src, 0, src);
            fprintf(stderr, "---- source ----\n%s\n----\n", src);
        }
        shader_errors++;
    }
}
void glLinkProgram(GLuint p) {
    static void (*real)(GLuint);
    if (!real) real = dlsym(RTLD_NEXT, "glLinkProgram");
    real(p);
    GLint ok = 0; glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[8192]; glGetProgramInfoLog(p, sizeof log, 0, log);
        fprintf(stderr, "SHADER LINK ERROR:\n%s\n", log);
        shader_errors++;
    }
}

int trace_draw = 0; GLuint cur_prog = 0;
void glUseProgram(GLuint p) {
    static void (*real)(GLuint);
    if (!real) real = dlsym(RTLD_NEXT, "glUseProgram");
    real(p); cur_prog = p;
}
void glDrawArrays(GLenum m, GLint f, GLsizei c) {
    static void (*real)(GLenum, GLint, GLsizei);
    if (!real) real = dlsym(RTLD_NEXT, "glDrawArrays");
    if (trace_draw) { GLint fb; glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &fb);
        GLint au, t0b; glGetIntegerv(GL_ACTIVE_TEXTURE, &au); glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &t0b); glActiveTexture(au);
        GLint att = -1, rf; glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &rf);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, 6);
        glGetFramebufferAttachmentParameteriv(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME, &att);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, rf);
        GLint att7 = -1; glBindFramebuffer(GL_READ_FRAMEBUFFER, 7);
        glGetFramebufferAttachmentParameteriv(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME, &att7);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, rf);
        fprintf(stderr, "drawArrays prog=%u fb=%d n=%d tex0=%d activeunit=%d fb6tex=%d fb7tex=%d\n", cur_prog, fb, c, t0b, au - GL_TEXTURE0, att, att7); }
    real(m, f, c);
}
void glDrawElements(GLenum m, GLsizei c, GLenum t, const void *i) {
    static void (*real)(GLenum, GLsizei, GLenum, const void *);
    if (!real) real = dlsym(RTLD_NEXT, "glDrawElements");
    if (trace_draw) { GLint fb; glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &fb);
        fprintf(stderr, "drawElements prog=%u fb=%d n=%d err=%x\n", cur_prog, fb, c, glGetError());
        GLuint sh[4]; GLsizei ns = 0; glGetAttachedShaders(cur_prog, 4, &ns, sh);
        for (int k = 0; k < ns; k++) { static char s[65536]; glGetShaderSource(sh[k], sizeof s, 0, s);
            char *b = strstr(s, "void PS("); if (!b) b = strstr(s, "void main"); 
            fprintf(stderr, "  shader %u: %.300s\n", sh[k], b ? b : "?"); } }
    real(m, c, t, i);
    if (trace_draw) { unsigned char p4[4]; GLint vp[4], dfb, rfb; glGetIntegerv(GL_VIEWPORT, vp);
        glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &dfb); glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &rfb);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, dfb);
        glReadPixels(vp[2]/2, vp[3]/2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, p4);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, rfb);
        GLboolean bl = glIsEnabled(GL_BLEND), dt = glIsEnabled(GL_DEPTH_TEST), cf = glIsEnabled(GL_CULL_FACE);
        fprintf(stderr, "  after err=%x px=%d,%d,%d,%d vp=%d,%d blend=%d depth=%d cull=%d\n", glGetError(),
                p4[0], p4[1], p4[2], p4[3], vp[2], vp[3], bl, dt, cf); }
}

// ---- audio source -------------------------------------------------------
// Default: synthetic 128bpm track (backward compatible).
// AUDIO=/path/file.f32   raw f32le stereo 44.1kHz (e.g. ffmpeg -f f32le -ac 2 -ar 44100)
// AUDIO_START=<sec>      offset into that file
// FPS=<n>                pacing + projectm_set_fps + samples per frame (default 60)
// MESH=default           don't call projectm_set_mesh_size (default 96x72)
// FEED=full|aulos_old|last576
//     full      (default) every sample since the previous frame (chunked)
//     aulos_old only the most recent 240 stereo frames per render frame
//               (what Aulos fed before the fix: pcm_get_max_samples()=480 f32)
//     last576   only the most recent 576 stereo frames (= projectM's analysis window)
// GAIN=<x>               linear gain applied to the audio (loudness tests)
// FRAMEFILE=path         write 1 line/frame "idx wall_time_s" (pacing diagnostics)
#define SR 44100
static float *audio = NULL; static long audio_frames = 0;
static void synth(float *out, long t0, int n) {
    static unsigned rng = 1;  // sequential LCG, exactly as the original renderer
    double beat = 60.0 / 128.0;
    for (int i = 0; i < n; i++) {
        long t = t0 + i;
        double ts = (double)t / SR, bp = fmod(ts, beat), hp = fmod(ts + beat / 2, beat);
        double bar = fmod(ts, beat * 16);
        double kick = sin(2 * M_PI * (50 + 120 * exp(-bp * 30)) * bp) * exp(-bp * 8);
        rng = rng * 1103515245 + 12345;
        double hat = ((rng >> 16) / 32768.0 - 1) * exp(-hp * 40) * 0.3;
        double root = bar < beat * 8 ? 110 : 98;
        double pad = 0.15 * (sin(2 * M_PI * root * ts) + sin(2 * M_PI * root * 1.5 * ts) +
                             sin(2 * M_PI * root * 2.52 * ts) * (0.5 + 0.5 * sin(ts * 0.7)));
        double lead = 0.12 * sin(2 * M_PI * root * 4 * (1 + 0.25 * (((int)(ts / beat * 2)) % 4 == 3)) * ts)
                      * exp(-fmod(ts, beat / 2) * 6);
        double v = 0.6 * kick + hat + pad + lead;
        out[i * 2] = (float)(v + 0.05 * sin(ts * 3)); out[i * 2 + 1] = (float)v;
    }
}

int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: render preset.milk W H FRAMES  (env: AUDIO AUDIO_START FPS MESH FEED GAIN FRAMEFILE)\n"); return 1; }
    int W = atoi(argv[2]), H = atoi(argv[3]), N = atoi(argv[4]);
    int FPS = getenv("FPS") ? atoi(getenv("FPS")) : 60;
    if (FPS < 1) FPS = 60;
    const char *feed = getenv("FEED") ? getenv("FEED") : "full";
    double gain = getenv("GAIN") ? atof(getenv("GAIN")) : 1.0;
    long a_off = getenv("AUDIO_START") ? (long)(atof(getenv("AUDIO_START")) * SR) : 0;
    if (getenv("AUDIO")) {
        FILE *af = fopen(getenv("AUDIO"), "rb");
        if (!af) { perror("AUDIO"); return 1; }
        fseek(af, 0, SEEK_END); long sz = ftell(af); fseek(af, 0, SEEK_SET);
        audio_frames = sz / (2 * sizeof(float));
        audio = malloc(audio_frames * 2 * sizeof(float));
        if (fread(audio, 2 * sizeof(float), audio_frames, af) != (size_t)audio_frames) { fprintf(stderr, "short read\n"); return 1; }
        fclose(af);
    }
    FILE *ff = getenv("FRAMEFILE") ? fopen(getenv("FRAMEFILE"), "w") : NULL;
    EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    eglInitialize(d, 0, 0);
    EGLint ca[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
                   EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig cfg; EGLint n;
    if (!eglChooseConfig(d, ca, &cfg, 1, &n) || !n) { fprintf(stderr, "no cfg\n"); return 1; }
    EGLint pa[] = {EGL_WIDTH, W, EGL_HEIGHT, H, EGL_NONE};
    EGLSurface s = eglCreatePbufferSurface(d, cfg, pa);
    eglBindAPI(EGL_OPENGL_API);
    EGLint xa[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 3,
                   EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT, EGL_NONE};
    EGLContext c = eglCreateContext(d, cfg, EGL_NO_CONTEXT, xa);
    if (!c || !eglMakeCurrent(d, s, s, c)) { fprintf(stderr, "ctx fail\n"); return 1; }

    projectm_handle pm = projectm_create();
    if (!pm) { fprintf(stderr, "pm fail\n"); return 1; }
    projectm_set_preset_switch_failed_event_callback(pm, onfail, 0);
    projectm_set_window_size(pm, W, H);
    if (!getenv("MESH") || strcmp(getenv("MESH"), "default")) projectm_set_mesh_size(pm, 96, 72);
    projectm_set_fps(pm, FPS);
    projectm_set_preset_locked(pm, true);
    projectm_set_soft_cut_duration(pm, 0.0);
    projectm_set_preset_duration(pm, 100000.0);
    projectm_load_preset_file(pm, argv[1], false);
    if (failed) return 2;

    const int CAP = SR / FPS * 4 + 4096;
    float *buf = malloc(sizeof(float) * CAP * 2);
    unsigned char *px = malloc(W * H * 3);
    long pos = 0;  // stereo frames delivered so far
    double t0 = now();
    for (int f = 0; f < N; f++) {
        trace_draw = getenv("TRACEDRAW") && f == N - 1;
        { double target = t0 + (double)f / FPS, dl; while ((dl = target - now()) > 0) { struct timespec sl = {0, (long)(dl * 1e9)}; nanosleep(&sl, 0); } }
        if (ff) fprintf(ff, "%d %.4f\n", f, now() - t0);
        long end = (long)((f + 1) * (double)SR / FPS);
        long cnt = end - pos;
        long fstart = pos;
        if (!strcmp(feed, "aulos_old") && cnt > 240) { fstart = end - 240; cnt = 240; }
        else if (!strcmp(feed, "last576") && cnt > 576) { fstart = end - 576; cnt = 576; }
        pos = end;
        while (cnt > 0) {
            int k = cnt > CAP ? CAP : (int)cnt;
            if (audio) {
                for (int i = 0; i < k; i++) {
                    long idx = a_off + fstart + i;
                    if (idx < audio_frames) { buf[i * 2] = audio[idx * 2]; buf[i * 2 + 1] = audio[idx * 2 + 1]; }
                    else buf[i * 2] = buf[i * 2 + 1] = 0;
                }
            } else synth(buf, fstart, k);
            if (gain != 1.0) for (int i = 0; i < k * 2; i++) buf[i] *= (float)gain;
            projectm_pcm_add_float(pm, buf, k, PROJECTM_STEREO);
            fstart += k; cnt -= k;
        }
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        glViewport(0, 0, W, H);
        glClear(GL_COLOR_BUFFER_BIT);
        projectm_opengl_render_frame(pm);
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE, px);
        for (int y = 0; y < H / 2; y++) {  // flip
            unsigned char *a = px + y * W * 3, *b = px + (H - 1 - y) * W * 3;
            for (int k = 0; k < W * 3; k++) { unsigned char tmp = a[k]; a[k] = b[k]; b[k] = tmp; }
        }
        fwrite(px, 1, W * H * 3, stdout);
    }
    fprintf(stderr, "shaders compiled: %d, errors: %d\n", shader_count, shader_errors);
    if (failed) return 2;
    if (shader_errors) return 3;
    projectm_destroy(pm);
    return 0;
}
