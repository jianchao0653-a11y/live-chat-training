package com.conversationlens.ime;

import com.conversationlens.ime.ConversationContinuationPolicy.Binding;
import com.conversationlens.ime.ConversationContinuationPolicy.Code;
import com.conversationlens.ime.ConversationContinuationPolicy.Decision;
import com.conversationlens.ime.ConversationContinuationPolicy.Request;

public final class ConversationContinuationPolicyTest {
    private static int assertions;
    private static final Binding OWNER = new Binding("customer-id", "pair-id", "synthetic.host", "continuous-context", "connection-identity");
    private static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }
    private static void code(Decision decision, Code expected, String message) {
        check(decision.code == expected, message + ": " + decision.code);
        check(decision.canSend() == (expected == Code.NEW_REQUEST || expected == Code.RESUME_REQUEST || expected == Code.RETRY_REQUEST), message + " send permission");
        if (!decision.canSend()) check(decision.request == null, message + " cannot expose sendable payload");
    }
    private static ConversationContinuationPolicy started() {
        ConversationContinuationPolicy policy = new ConversationContinuationPolicy();
        check(policy.start(OWNER, 100), "explicit start accepted");
        return policy;
    }
    private static Decision prepare(ConversationContinuationPolicy policy, String fragment, String id, long now) {
        return policy.prepare(OWNER, fragment, "关心近况", "ticket-context", id, true, now);
    }
    private static String repeat(String value, int count) {
        StringBuilder text = new StringBuilder();
        for (int i = 0; i < count; i++) text.append(value);
        return text.toString();
    }

    public static void main(String[] args) {
        explicitLifecycle();
        approvedHistoryAndDeduplication();
        pendingAndRetryLedger();
        canonicalLedgerAlias();
        bindingAndTimeInvalidation();
        hardLimits();
        System.out.println("CONVERSATION_CONTINUATION_POLICY_PASS (" + assertions + " assertions)");
    }

    private static void explicitLifecycle() {
        ConversationContinuationPolicy policy = new ConversationContinuationPolicy();
        code(prepare(policy, "对方：合成片段", "r1", 100), Code.NOT_ACTIVE, "cannot silently enable");
        check(!policy.start(null, 100), "missing binding refused");
        check(!policy.start(new Binding("nickname", "", "host", "context", "connection"), 100), "nickname without pair ID refused");
        check(!policy.start(OWNER, -1), "negative elapsed time refused");
        check(policy.start(OWNER, 100), "explicit valid enable");
        check(!policy.start(OWNER, 101), "start cannot silently reset active request ledger");
        code(policy.prepare(OWNER, "对方：合成片段", "goal", "context", "r1", false, 101), Code.NOT_APPROVED, "unapproved fragment refused");
        code(prepare(policy, " \r\n ", "r1", 102), Code.EMPTY_FRAGMENT, "blank fragment refused");
        code(policy.prepare(OWNER, "对方：合成片段", "goal", "", "r1", true, 103), Code.INVALID_CONTEXT, "wire context required");
        code(prepare(policy, "对方：合成片段", "", 104), Code.INVALID_REQUEST_ID, "request ID required");
        Request old = prepare(policy, "对方：合成片段", "r1", 105).request;
        policy.stop();
        check(!policy.finish(OWNER, old, 106), "late result after stop cannot write history");
        check(policy.turns() == 0 && policy.characters() == 0, "stop clears temporary material");
        check(policy.start(OWNER, 107), "explicit restart accepted");
        Request next = prepare(policy, "对方：重新主动提供", "r2", 108).request;
        check(!policy.finish(OWNER, old, 109), "late old session response cannot commit into new session");
        check(policy.finish(OWNER, next, 110), "new active request still finishes");
        policy.stop();
        Binding other = new Binding("other-customer", "other-pair", OWNER.host, "other-scene", OWNER.connectionId);
        check(policy.start(other, 111), "explicit different-customer session starts");
        Request otherRequest = policy.prepare(other, "对方：另一客户合成片段", "goal", "context", "r3", true, 112).request;
        check(!policy.finish(OWNER, old, 113), "old customer callback rejected before touching current owner");
        check(!policy.retryRequired(OWNER, old, old.requestId, 114), "old customer error cannot change current ledger");
        check(policy.alive(other, 115) && policy.finish(other, otherRequest, 116), "stale callbacks do not cancel different current customer");
    }

    private static void approvedHistoryAndDeduplication() {
        ConversationContinuationPolicy policy = started();
        Decision first = prepare(policy, "对方：合成消息一\r\n我：合成消息二", "r1", 101);
        code(first, Code.NEW_REQUEST, "first approved fragment starts request");
        check(first.request.text.equals("对方：合成消息一\n我：合成消息二"), "line endings normalized without inventing speech");
        check(policy.turns() == 0, "pending fragment is not completed history");
        check(policy.hasPending() && policy.roundCount() == 0 && policy.approvedText().isEmpty(), "read-only status distinguishes pending from confirmed material");
        check(policy.finish(OWNER, first.request, 102), "validated response completes real fragment");
        check(!policy.hasPending() && policy.roundCount() == 1 && policy.approvedText().equals(first.request.text), "completion exposes only approved real material");
        check(!policy.finish(OWNER, first.request, 103), "duplicate asynchronous result cannot append twice");
        code(prepare(policy, " 对方：合成消息一\n我：合成消息二 ", "fresh-id", 104), Code.DUPLICATE, "normalized repeat cannot buy new request");
        check(policy.turns() == 1, "duplicate does not add a turn");
        Decision second = prepare(policy, "对方：主动补充的新片段", "r2", 105);
        code(second, Code.NEW_REQUEST, "next explicit fragment accepted");
        check(second.request.text.equals(first.request.text + "\n\n对方：主动补充的新片段"), "only supplied fragments accumulate; generated and inserted drafts have no append API");
        check(policy.finish(OWNER, second.request, 106), "second turn finishes");
        code(prepare(policy, second.request.text, "r3", 107), Code.DUPLICATE, "whole accumulated transcript cannot resubmit as new fragment");
        code(prepare(policy, "对方：第三段", "r1", 108), Code.INVALID_REQUEST_ID, "completed request ID cannot identify different text");
    }

    private static void pendingAndRetryLedger() {
        ConversationContinuationPolicy policy = started();
        Request first = prepare(policy, "对方：网络失败合成片段", "00000000-0000-4000-8000-000000000001", 101).request;
        // No completion callback models lost/uncertain network outcome. Nothing clears the ledger.
        Decision resume = policy.prepare(OWNER, first.fragment, first.goal, "changed-ticket-context", "fresh-id", true, 102);
        code(resume, Code.RESUME_REQUEST, "unknown network outcome resumes original request");
        check(resume.request == first && resume.request.requestId.equals(first.requestId) && resume.request.context.equals("ticket-context"), "resume keeps original object, content, request ID and wire context");
        code(prepare(policy, "对方：改过的片段", "fresh-id", 103), Code.PENDING_CHANGED, "pending cannot accept changed fragment");
        code(policy.prepare(OWNER, first.fragment, "changed-goal", "context", "fresh-id", true, 104), Code.PENDING_CHANGED, "pending cannot accept changed semantic goal");
        code(policy.explicitRetry(OWNER, first.fragment, first.goal, first.requestId, "retry-id", true, true, 105), Code.RETRY_MISMATCH, "caller cannot invent server permission to retry");
        check(!policy.retryRequired(OWNER, first, "unrelated-id", 106), "malformed server retry ID is rejected");
        check(policy.retryRequired(OWNER, first, first.requestId, 107), "matching server retry ledger recorded");
        check(policy.hasPending() && policy.retryRequired(), "read-only retry status retains pending request");
        code(prepare(policy, first.fragment, "ignored-new-id", 108), Code.RETRY_REQUIRED, "known possible charge requires explicit retry path");
        code(policy.explicitRetry(OWNER, first.fragment, first.goal, first.requestId, "retry-id", false, true, 109), Code.NOT_APPROVED, "retry requires current content approval");
        code(policy.explicitRetry(OWNER, first.fragment, first.goal, first.requestId, "retry-id", true, false, 110), Code.RETRY_NOT_APPROVED, "retry requires explicit possible charge approval");
        code(policy.explicitRetry(OWNER, "changed", first.goal, first.requestId, "retry-id", true, true, 111), Code.PENDING_CHANGED, "retry cannot change payload");
        code(policy.explicitRetry(OWNER, first.fragment, first.goal, "unrelated-id", "retry-id", true, true, 112), Code.RETRY_MISMATCH, "retry cannot change original ledger ID");
        code(policy.explicitRetry(OWNER, first.fragment, first.goal, first.requestId, first.requestId, true, true, 113), Code.INVALID_REQUEST_ID, "paid retry must use a distinct ID");
        Decision retry = policy.explicitRetry(OWNER, first.fragment, first.goal, first.requestId, "retry-id", true, true, 114);
        code(retry, Code.RETRY_REQUEST, "explicit matching ledger retry allowed");
        check(policy.hasPending() && !policy.retryRequired(), "accepted retry clears only prior retry confirmation requirement");
        check(retry.request.text.equals(first.text) && retry.request.goal.equals(first.goal) && retry.request.context.equals(first.context), "retry immutable payload preserved");
        check(retry.request.acknowledgePossibleCharge && retry.request.retryOf.equals(first.requestId), "retry carries original charge ledger acknowledgment");
        check(policy.turns() == 0, "paid retry is not a duplicate conversation turn");
        check(!policy.finish(OWNER, first, 115), "late original response cannot finish replacement retry");
        check(!policy.retryRequired(OWNER, first, first.requestId, 116), "late original failure cannot alter replacement ledger");
        Decision retryResume = prepare(policy, first.fragment, "do-not-use", 117);
        check(retryResume.request == retry.request && retryResume.request.acknowledgePossibleCharge && retryResume.request.retryOf.equals(first.requestId), "uncertain retry keeps same retry request and acknowledgment on recheck");
        check(policy.finish(OWNER, retry.request, 118), "retry success commits once");
        code(prepare(policy, first.fragment, "another-id", 119), Code.DUPLICATE, "successful retried fragment cannot charge again");
    }

    private static void canonicalLedgerAlias() {
        ConversationContinuationPolicy policy = started();
        String requestId = "00000000-0000-4000-8000-000000000010";
        String canonicalId = "00000000-0000-4000-8000-000000000009";
        String differentId = "00000000-0000-4000-8000-000000000008";
        String retryId = "00000000-0000-4000-8000-000000000011";
        Request request = prepare(policy, "对方：更早已失败请求的相同合成片段", requestId, 101).request;
        code(policy.explicitRetry(OWNER, request.fragment, request.goal, canonicalId, retryId, true, true, 102), Code.RETRY_MISMATCH, "unrecorded canonical ledger cannot authorize retry");
        check(policy.retryRequired(OWNER, request, canonicalId, 103), "active HTTP response may resolve semantic fingerprint to earlier canonical UUID");
        check(policy.retryRequired(OWNER, request, canonicalId, 104), "same canonical ledger response is idempotent");
        check(!policy.retryRequired(OWNER, request, differentId, 105), "same pending response cannot swap an already recorded ledger");
        code(policy.explicitRetry(OWNER, request.fragment, request.goal, differentId, retryId, true, true, 106), Code.RETRY_MISMATCH, "injected ledger still rejected after server record");
        code(policy.explicitRetry(OWNER, request.fragment, request.goal, requestId, retryId, true, true, 107), Code.RETRY_MISMATCH, "pending request ID cannot replace canonical server ledger");
        code(policy.explicitRetry(OWNER, request.fragment, request.goal, canonicalId, canonicalId, true, true, 108), Code.INVALID_REQUEST_ID, "new request ID must differ from canonical ledger even if not locally used");
        Decision retry = policy.explicitRetry(OWNER, request.fragment, request.goal, canonicalId, retryId, true, true, 109);
        code(retry, Code.RETRY_REQUEST, "explicit approved retry of canonical older task succeeds");
        check(retry.request.retryOf.equals(canonicalId) && retry.request.text.equals(request.text)
                && retry.request.context.equals(request.context) && retry.request.goal.equals(request.goal), "canonical retry changes only request ID and required ledger acknowledgment");
        check(!policy.finish(OWNER, request, 110), "alias original request cannot complete replacement");
        check(policy.finish(OWNER, retry.request, 111), "canonical retry commits real fragment exactly once");
    }

    private static void bindingAndTimeInvalidation() {
        Binding[] changed = {
            new Binding("different-customer", OWNER.pairId, OWNER.host, OWNER.contextId, OWNER.connectionId),
            new Binding(OWNER.customerId, "different-pair", OWNER.host, OWNER.contextId, OWNER.connectionId),
            new Binding(OWNER.customerId, OWNER.pairId, "different-host", OWNER.contextId, OWNER.connectionId),
            new Binding(OWNER.customerId, OWNER.pairId, OWNER.host, "different-scene", OWNER.connectionId),
            new Binding(OWNER.customerId, OWNER.pairId, OWNER.host, OWNER.contextId, "different-connection"),
            null
        };
        for (Binding other : changed) {
            ConversationContinuationPolicy policy = started();
            Request old = prepare(policy, "对方：合成片段", "r1", 101).request;
            code(policy.prepare(other, "对方：另一片段", "goal", "context", "r2", true, 102), Code.INVALID_BINDING, "customer/pair/host/scene/connection change invalidates");
            check(!policy.alive(OWNER, 103) && !policy.finish(OWNER, old, 104), "returning to old binding cannot resurrect session");
            check(policy.turns() == 0 && policy.characters() == 0, "invalid binding clears temporary data");
        }
        ConversationContinuationPolicy policy = started();
        Request request = prepare(policy, "对方：合成片段", "r1", 101).request;
        check(policy.alive(OWNER, 100 + ConversationContinuationPolicy.LIFETIME_MS - 1), "alive one millisecond before fixed deadline");
        code(prepare(policy, request.fragment, "r2", 100 + ConversationContinuationPolicy.LIFETIME_MS), Code.EXPIRED, "activity cannot slide the 15 minute deadline");
        check(!policy.finish(OWNER, request, 100 + ConversationContinuationPolicy.LIFETIME_MS), "expired response cannot commit");
        policy = started();
        prepare(policy, "对方：合成片段", "r1", 200);
        code(prepare(policy, "对方：合成片段", "r2", 199), Code.CLOCK_REVERSED, "elapsed clock rollback fails closed");
        check(!policy.alive(OWNER, 201), "time recovery cannot resurrect invalidated session");
    }

    private static void hardLimits() {
        ConversationContinuationPolicy policy = started();
        String firstText = repeat("字", 3997);
        Request first = prepare(policy, firstText, "r1", 101).request;
        check(policy.finish(OWNER, first, 102), "large valid fragment accepted");
        Decision exact = prepare(policy, "新", "r2", 103);
        code(exact, Code.NEW_REQUEST, "exact 4000 including separator allowed");
        check(exact.request.text.length() == 4000 && exact.request.text.endsWith("\n\n新"), "no truncation at exact character boundary");
        check(policy.finish(OWNER, exact.request, 104), "exact limit can finish");
        code(prepare(policy, "更多", "r3", 105), Code.LIMIT_REACHED, "next fragment must start a new session instead of truncating");
        check(policy.turns() == 2 && policy.characters() == 4000, "limit rejection preserves completed approved material");
        policy = started();
        code(prepare(policy, repeat("字", 4001), "r1", 101), Code.LIMIT_REACHED, "oversized first fragment rejected whole");
        check(policy.characters() == 0 && policy.turns() == 0, "oversized fragment never enters session");
        code(prepare(policy, repeat("\uD83D\uDE42", 2001), "r2", 102), Code.LIMIT_REACHED, "supplementary characters follow service UTF-16 limit");
        for (int i = 0; i < ConversationContinuationPolicy.MAX_TURNS; i++) {
            Decision next = prepare(policy, "对方：合成轮次" + i, "turn-" + i, 103 + 2 * i);
            code(next, Code.NEW_REQUEST, "bounded approved turn accepted");
            check(policy.finish(OWNER, next.request, 104 + 2 * i), "bounded turn completes");
        }
        code(prepare(policy, "对方：超出轮次", "excess", 200), Code.LIMIT_REACHED, "ninth turn requires explicit new session");
        check(policy.turns() == ConversationContinuationPolicy.MAX_TURNS, "turn limit never silently drops history");
    }
}
