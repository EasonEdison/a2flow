package dev.a2flow.management.release;

import java.util.List;
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.a2flow.management.access.UserIds;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.tool.TrustedToolContext;
import dev.a2flow.management.protobuf.InvokeRequest;

/** Precision and authority regression checks for the signed-Long/string identity boundary. */
public final class UserIdentityContractTest {
    public static void main(String[] args) throws Exception {
        for (long value : new long[] {Long.MIN_VALUE, -1, 0, 1, 9007199254740993L, Long.MAX_VALUE}) {
            check(UserIds.parseWire(UserIds.toWire(value)) == value, "identity roundtrip lost precision");
        }
        for (String invalid : new String[] {"", "+1", "-0", "01", " 1", "1.0", "1e3",
                "9223372036854775808", "-9223372036854775809"}) {
            mustFail(() -> UserIds.parseWire(invalid));
        }
        ReleaseModels.GrayReleaseRule rule = GrayReleaseRequestParser.rule(Map.of("percentage", "20",
                "userIdWhitelist", "9223372036854775807,-9223372036854775808,0,9007199254740993,0"));
        check(rule.getUserIdWhitelist().equals(List.of(Long.MIN_VALUE, 0L, 9007199254740993L, Long.MAX_VALUE)),
                "whitelist parsing changed identity values");
        ObjectMapper mapper = new ObjectMapper();
        String json = mapper.writeValueAsString(rule);
        check(mapper.readTree(json).get("userIdWhitelist").get(0).isTextual(), "identity array is JSON numeric");
        check(mapper.readTree(json).get("userIdWhitelist").get(3).asText().equals("9223372036854775807"),
                "serialized identity lost precision");
        mustFail(() -> GrayReleaseRequestParser.rule(Map.of("percentage", "20", "userIdWhitelist", "1,")));
        InvokeRequest request = mapper.readValue("{\"userId\":\"-9223372036854775808\"}", InvokeRequest.class);
        check(UserIds.parseWire(request.getUserId()) == Long.MIN_VALUE, "request identity lost precision");
        mustFail(() -> mapper.readValue("{\"userId\":9007199254740993}", InvokeRequest.class));
        mustFail(() -> mapper.readValue("{\"userId\":1.5}", InvokeRequest.class));
        AgentEngineContext engine = new AgentEngineContext();
        engine.setOwnerId("999");
        engine.setUserId(Long.MIN_VALUE);
        Map<String, Object> trusted = TrustedToolContext.build(engine, Map.of("userId", 1.5));
        check(trusted.get("userId") instanceof Long && trusted.get("userId").equals(Long.MIN_VALUE),
                "business parameters overrode trusted actor or owner became actor");
        System.out.println("USER_IDENTITY_PASS: signed Long limits, exact decimal wire, string whitelist serialization, "
                + "numeric JSON rejection, trusted actor isolation");
    }

    private interface Checked { void run() throws Exception; }

    private static void mustFail(Checked action) throws Exception {
        try {
            action.run();
        } catch (IllegalArgumentException | java.io.IOException expected) {
            return;
        }
        throw new AssertionError("Expected malformed identity rejection");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
