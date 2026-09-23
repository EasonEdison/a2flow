package dev.a2flow.management.entry;

import java.util.LinkedHashMap;
import java.util.Map;

import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;
import dev.a2flow.management.access.ManagementIdentityProvider;
import dev.a2flow.management.model.SkillFactoryExecutionResult;
import dev.a2flow.management.support.JsonSupport;

/** Non-streaming manual entry. The host must authenticate and bind identity before calling. */
public final class ManualManagementExecuteService {
    private final SkillFactoryMethodDispatcher dispatcher;
    private final ManagementIdentityProvider identity;

    public ManualManagementExecuteService(SkillFactoryMethodDispatcher dispatcher, ManagementIdentityProvider identity) {
        this.dispatcher = dispatcher;
        this.identity = identity;
    }

    public SkillFactoryExecuteRuntimeResult execute(String method,
            Map<String, String> params, String traceId) {
        String userName = Long.toString(identity.userId());
        Map<String, String> values = params == null ? new LinkedHashMap<>() : new LinkedHashMap<>(params);
        values.put("userName", userName);
        values.put("userId", userName);
        values.put("operator", userName);
        values.put("traceId", traceId);
        SkillFactoryExecutionResult result = dispatcher.execute(userName, method, values);
        String data = result.getData() == null ? null : JsonSupport.toJSON(result.getData());
        return result.isSuccess() ? SkillFactoryExecuteRuntimeResult.success(data, result.isList())
                : SkillFactoryExecuteRuntimeResult.fail(result.getErrorMsg(), data);
    }
}
