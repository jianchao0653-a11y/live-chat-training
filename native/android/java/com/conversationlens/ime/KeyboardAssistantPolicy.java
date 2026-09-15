package com.conversationlens.ime;

/** Main-thread route authority. Opening a panel never falls back to the host editor. */
final class KeyboardAssistantPolicy {
    enum Mode { NORMAL, NEW, MAINTAIN }
    enum Segment {
        UNCLASSIFIED, NEW, MAINTAIN;
        static Segment parse(String value) {
            if ("NEW".equals(value)) return NEW;
            if ("MAINTAIN".equals(value)) return MAINTAIN;
            return UNCLASSIFIED;
        }
    }
    enum Target { HOST, INTERNAL, BLOCKED }
    static final class Route {
        final long epoch;
        final Target target;
        final int field;
        Route(long epoch, Target target, int field) { this.epoch=epoch; this.target=target; this.field=field; }
    }
    private long epoch;
    private Mode mode=Mode.NORMAL;
    private Target target=Target.HOST;
    private int field;

    Mode mode() { return mode; }
    Target target() { return target; }
    Route snapshot() { return new Route(epoch,target,field); }
    void open(Mode next, boolean allowed) {
        mode=allowed?next:Mode.NORMAL;
        target=mode==Mode.NORMAL?Target.HOST:Target.BLOCKED;
        field=0; epoch++;
    }
    void focus(int id) {
        if (mode==Mode.NORMAL || id==0) return;
        target=Target.INTERNAL; field=id; epoch++;
    }
    void blur(int id) {
        if (target!=Target.INTERNAL || field!=id) return;
        target=Target.BLOCKED; field=0; epoch++;
    }
    void invalidate() { epoch++; }
    void reset() { open(Mode.NORMAL,true); }
    boolean accepts(Route route) {
        return route!=null && route.epoch==epoch && route.target==target && route.field==field && target!=Target.BLOCKED;
    }
    static boolean visible(Mode mode, Segment segment) {
        return mode!=Mode.NORMAL && (segment==Segment.UNCLASSIFIED || (mode==Mode.NEW && segment==Segment.NEW) || (mode==Mode.MAINTAIN && segment==Segment.MAINTAIN));
    }
    static boolean selectable(Mode mode, Segment segment) { return segment!=Segment.UNCLASSIFIED && visible(mode,segment); }
}
