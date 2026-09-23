package dev.a2flow.management.a2ui.application;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.apache.commons.lang3.StringUtils;

/**
 * Application 首屏与所有结果模板的组件依赖收集器。
 *
 * <p>上游 compiler 汇总根成功、失败、成功分支及 Load 管线模板；本类返回稳定类型闭包，
 * 交给既有 Catalog 准入规则校验。不对待绑定的占位字段执行实例 Schema 校验，
 * 不执行绑定或业务能力；绑定完成后的消息继续由运行态校验。
 */
final class A2uiApplicationComponentCollector {

    private static final String FIELD_UPDATE_COMPONENTS = "updateComponents";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_COMPONENT = "component";
    private static final String FIELD_ID = "id";
    /** 汇总静态组件类型；实例字段留到数据绑定后验证，避免误拒绝合法占位模板。 */
    List<String> collect(List<Map<String, Object>> messages) {
        Set<String> referencedTypes = new TreeSet<>();
        for (Map<String, Object> message : messages) {
            if (!message.containsKey(FIELD_UPDATE_COMPONENTS)) {
                continue;
            }
            Object update = message.get(FIELD_UPDATE_COMPONENTS);
            if (!(update instanceof Map)
                    || !(((Map<?, ?>) update).get(FIELD_COMPONENTS) instanceof List)) {
                throw invalid();
            }
            for (Object rawComponent : (List<?>) ((Map<?, ?>) update).get(FIELD_COMPONENTS)) {
                if (!(rawComponent instanceof Map)) {
                    throw invalid();
                }
                Map<?, ?> component = (Map<?, ?>) rawComponent;
                Object type = component.get(FIELD_COMPONENT);
                Object id = component.get(FIELD_ID);
                if (!(type instanceof String) || StringUtils.isBlank((String) type)
                        || !(id instanceof String) || StringUtils.isBlank((String) id)) {
                    throw invalid();
                }
                referencedTypes.add((String) type);
            }
        }
        return Collections.unmodifiableList(new ArrayList<>(referencedTypes));
    }

    private A2uiApplicationValidationException invalid() {
        return new A2uiApplicationValidationException(A2uiApplicationErrorCode.RESULT_ADAPTER_INVALID);
    }
}
