package com.conversationlens.ime;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** In-memory authority for explicitly enabled, user-supplied maintenance fragments.
 * No generated or inserted draft is accepted as sent chat history. The caller supplies
 * elapsed realtime and sends only the immutable Request returned by this policy.
 */
final class ConversationContinuationPolicy {
    static final long LIFETIME_MS = 15L * 60 * 1000;
    static final int MAX_TURNS = 8;
    // Java and the service's JavaScript both count UTF-16 code units.
    static final int MAX_CHARS = 4000;
    private static final String SEPARATOR = "\n\n";

    enum Code {
        NEW_REQUEST, RESUME_REQUEST, RETRY_REQUEST,
        NOT_ACTIVE, INVALID_BINDING, EXPIRED, CLOCK_REVERSED,
        NOT_APPROVED, EMPTY_FRAGMENT, DUPLICATE, PENDING_CHANGED,
        RETRY_NOT_APPROVED, RETRY_MISMATCH, RETRY_REQUIRED, LIMIT_REACHED,
        INVALID_REQUEST_ID, INVALID_CONTEXT
    }

    /** contextId is the stable temporary session ID, not a mutable result ticket context. */
    static final class Binding {
        final String customerId, pairId, host, contextId, connectionId;
        Binding(String customerId, String pairId, String host, String contextId, String connectionId) {
            this.customerId = customerId;
            this.pairId = pairId;
            this.host = host;
            this.contextId = contextId;
            this.connectionId = connectionId;
        }
        private boolean valid() {
            return present(customerId) && present(pairId) && present(host)
                    && present(contextId) && present(connectionId);
        }
        private boolean matches(Binding other) {
            return other != null && valid() && other.valid()
                    && customerId.equals(other.customerId) && pairId.equals(other.pairId)
                    && host.equals(other.host) && contextId.equals(other.contextId)
                    && connectionId.equals(other.connectionId);
        }
    }

    static final class Request {
        final String requestId, text, fragment, goal, context, retryOf;
        final boolean acknowledgePossibleCharge;
        private Request(String requestId, String text, String fragment, String goal,
                        String context, String retryOf) {
            this.requestId = requestId;
            this.text = text;
            this.fragment = fragment;
            this.goal = goal;
            this.context = context;
            this.retryOf = retryOf;
            this.acknowledgePossibleCharge = retryOf != null;
        }
    }

    static final class Decision {
        final Code code;
        final Request request;
        private Decision(Code code, Request request) { this.code = code; this.request = request; }
        boolean canSend() {
            return request != null && (code == Code.NEW_REQUEST
                    || code == Code.RESUME_REQUEST || code == Code.RETRY_REQUEST);
        }
    }

    private Binding owner;
    private long started, lastNow;
    private final List<String> fragments = new ArrayList<>();
    private final Set<String> usedRequestIds = new HashSet<>();
    private String committedText = "";
    private Request pending;
    private String serverRetryOf;

    /** Only invoke in response to the user's explicit enable action. Stop before restarting. */
    boolean start(Binding binding, long now) {
        if (owner != null || binding == null || !binding.valid() || now < 0) return false;
        owner = binding;
        started = lastNow = now;
        return true;
    }

    void stop() {
        owner = null;
        pending = null;
        serverRetryOf = null;
        committedText = "";
        fragments.clear();
        usedRequestIds.clear();
        started = lastNow = 0;
    }

    boolean alive(Binding binding, long now) { return invalidReason(binding, now) == null; }
    boolean hasPending() { return pending != null; }
    boolean retryRequired() { return serverRetryOf != null; }
    int roundCount() { return fragments.size(); }
    String approvedText() { return committedText; }
    int turns() { return fragments.size(); }
    int characters() { return pending == null ? committedText.length() : pending.text.length(); }

    Decision prepare(Binding binding, String fragment, String goal, String requestContext,
                     String newRequestId, boolean approved, long now) {
        Code invalid = invalidReason(binding, now);
        if (invalid != null) return denied(invalid);
        if (!approved) return denied(Code.NOT_APPROVED);
        String value = canonical(fragment);
        if (value.isEmpty()) return denied(Code.EMPTY_FRAGMENT);
        String purpose = goal == null ? "" : goal;
        if (pending != null) {
            if (!pending.fragment.equals(value) || !pending.goal.equals(purpose))
                return denied(Code.PENDING_CHANGED);
            if (serverRetryOf != null) return denied(Code.RETRY_REQUIRED);
            // Keep the entire original payload, including its ticket context and retry ledger.
            return new Decision(Code.RESUME_REQUEST, pending);
        }
        if (fragments.contains(value) || committedText.equals(value)) return denied(Code.DUPLICATE);
        if (fragments.size() >= MAX_TURNS) return denied(Code.LIMIT_REACHED);
        long size = (long) committedText.length() + (committedText.isEmpty() ? 0 : SEPARATOR.length()) + value.length();
        if (size > MAX_CHARS) return denied(Code.LIMIT_REACHED);
        if (!present(requestContext)) return denied(Code.INVALID_CONTEXT);
        if (!newRequestId(newRequestId)) return denied(Code.INVALID_REQUEST_ID);
        String fullText = committedText.isEmpty() ? value : committedText + SEPARATOR + value;
        pending = new Request(newRequestId, fullText, value, purpose, requestContext, null);
        usedRequestIds.add(newRequestId);
        return new Decision(Code.NEW_REQUEST, pending);
    }

    /** Record only a retry_of from the response to this exact current request. */
    boolean retryRequired(Binding binding, Request request, String retryOf, long now) {
        if (request == null || request != pending || invalidReason(binding, now) != null
                || !ledgerId(retryOf) || (serverRetryOf != null && !serverRetryOf.equals(retryOf))) return false;
        // The service may resolve the same semantic fingerprint to an earlier canonical task.
        serverRetryOf = retryOf;
        return true;
    }

    Decision explicitRetry(Binding binding, String fragment, String goal, String retryOf,
                           String newRequestId, boolean approved, boolean possibleChargeApproved,
                           long now) {
        Code invalid = invalidReason(binding, now);
        if (invalid != null) return denied(invalid);
        if (!approved) return denied(Code.NOT_APPROVED);
        if (!possibleChargeApproved) return denied(Code.RETRY_NOT_APPROVED);
        if (pending == null || serverRetryOf == null || !serverRetryOf.equals(retryOf))
            return denied(Code.RETRY_MISMATCH);
        if (!pending.fragment.equals(canonical(fragment)) || !pending.goal.equals(goal == null ? "" : goal))
            return denied(Code.PENDING_CHANGED);
        if (!newRequestId(newRequestId) || newRequestId.equals(serverRetryOf)) return denied(Code.INVALID_REQUEST_ID);
        pending = new Request(newRequestId, pending.text, pending.fragment, pending.goal,
                pending.context, retryOf);
        usedRequestIds.add(newRequestId);
        serverRetryOf = null;
        return new Decision(Code.RETRY_REQUEST, pending);
    }

    /** Call after a successful response has passed customer/host/context/task validation. */
    boolean finish(Binding binding, Request request, long now) {
        if (request == null || request != pending || invalidReason(binding, now) != null) return false;
        // Commit only the approved real fragment already in the request, never response/draft text.
        fragments.add(request.fragment);
        committedText = request.text;
        pending = null;
        serverRetryOf = null;
        return true;
    }

    private Code invalidReason(Binding binding, long now) {
        if (owner == null) return Code.NOT_ACTIVE;
        Code reason = null;
        if (!owner.matches(binding)) reason = Code.INVALID_BINDING;
        else if (now < lastNow) reason = Code.CLOCK_REVERSED;
        else if (now - started >= LIFETIME_MS) reason = Code.EXPIRED;
        if (reason != null) { stop(); return reason; }
        lastNow = now;
        return null;
    }

    private boolean newRequestId(String value) { return present(value) && !usedRequestIds.contains(value); }
    private static Decision denied(Code code) { return new Decision(code, null); }
    private static boolean present(String value) { return value != null && !value.trim().isEmpty(); }
    private static boolean ledgerId(String value) {
        return value != null && value.matches("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    }
    private static String canonical(String value) {
        return value == null ? "" : value.replace("\r\n", "\n").replace('\r', '\n').trim();
    }
}
