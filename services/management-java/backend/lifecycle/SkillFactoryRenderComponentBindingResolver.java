package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import lombok.extern.slf4j.Slf4j;

/**
 * 从 Skill ONLINE 快照解析 render_component 可见的组件资产 ID。
 *
 * <p>直接组件来自 componentBindings；能力间接组件只读取
 * EXECUTION_AND_RENDER 绑定的 resultContract.presentationComponents。
 * 解析过程只读快照，不会把能力组件复制回 Skill 的直接绑定。
 */
@Component
@Slf4j
public class SkillFactoryRenderComponentBindingResolver {

    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_BIND_MODE = "bindMode";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_PRESENTATION_COMPONENTS = "presentationComponents";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String BIND_MODE_EXECUTION_AND_RENDER = "EXECUTION_AND_RENDER";

    /**
     * 按快照声明顺序返回去重后的组件资产 ID。
     */
    public List<Long> resolveAssetIds(Map<String, Object> skillSnapshot) {
        if (skillSnapshot == null || skillSnapshot.isEmpty()) {
            return Collections.emptyList();
        }
        Set<Long> assetIds = new LinkedHashSet<>();
        collectDirectBindings(list(skillSnapshot.get(FIELD_COMPONENT_BINDINGS)), assetIds);
        collectCapabilityBindings(list(skillSnapshot.get(FIELD_CAPABILITY_BINDINGS)), assetIds);
        List<Long> result = new ArrayList<>(assetIds);
        log.info("SkillFactory render_component解析Skill绑定完成, directCount:{}, capabilityCount:{}, "
                        + "assetCount:{}",
                list(skillSnapshot.get(FIELD_COMPONENT_BINDINGS)).size(),
                list(skillSnapshot.get(FIELD_CAPABILITY_BINDINGS)).size(), result.size());
        return result;
    }

    private void collectDirectBindings(List<?> bindings, Set<Long> assetIds) {
        for (Object value : bindings) {
            addAssetId(map(value), assetIds);
        }
    }

    private void collectCapabilityBindings(List<?> bindings, Set<Long> assetIds) {
        for (Object value : bindings) {
            Map<String, Object> binding = map(value);
            if (!StringUtils.equals(
                    BIND_MODE_EXECUTION_AND_RENDER, string(binding.get(FIELD_BIND_MODE)))) {
                continue;
            }
            Map<String, Object> clientVariants = map(binding.get(FIELD_CLIENT_VARIANTS));
            for (Object clientValue : list(binding.get(FIELD_SUPPORTED_CLIENTS))) {
                Map<String, Object> variant = map(clientVariants.get(string(clientValue)));
                Map<String, Object> resultContract = map(variant.get(FIELD_RESULT_CONTRACT));
                for (Object component : list(resultContract.get(FIELD_PRESENTATION_COMPONENTS))) {
                    addAssetId(map(component), assetIds);
                }
            }
        }
    }

    private void addAssetId(Map<String, Object> binding, Set<Long> assetIds) {
        Long assetId = positiveLong(binding.get(FIELD_ASSET_ID));
        if (assetId == null) {
            log.warn("SkillFactory render_component忽略非法组件绑定, assetId:{}",
                    binding.get(FIELD_ASSET_ID));
            return;
        }
        assetIds.add(assetId);
    }

    private Long positiveLong(Object value) {
        try {
            long parsed = value instanceof Number
                    ? ((Number) value).longValue() : Long.parseLong(string(value));
            return parsed > 0 ? parsed : null;
        } catch (Exception e) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private List<?> list(Object value) {
        return value instanceof List ? (List<?>) value : Collections.emptyList();
    }

    private String string(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }
}
