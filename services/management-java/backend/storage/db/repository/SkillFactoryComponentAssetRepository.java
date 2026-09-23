package dev.a2flow.management.storage.db.repository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.storage.db.entity.SkillFactoryComponentAssetDO;
import dev.a2flow.management.storage.db.mapper.SkillFactoryComponentAssetMapper;

import lombok.Data;
import lombok.experimental.Accessors;
import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 组件 Registry Repository。
 *
 * <p>该类是 `skill_component_registry` 的唯一数据访问和 DO 转换边界。上游只使用
 * {@link ComponentAsset} 领域对象；Mapper、DO、原生 JSON 列和查询 Wrapper 不向生命周期、
 * Authoring、发布或 RPC 层泄漏。本 Repository 不提供内存 seed、DB 异常降级或旧表双读。
 */
@Repository
@Slf4j
public class SkillFactoryComponentAssetRepository {

    private static final int ENABLED_TRUE = 1;
    private static final int ENABLED_FALSE = 0;
    private static final String ASSET_TYPE_CARD_COMPONENT = "CARD_COMPONENT";
    private static final String VALUE_ALL = "ALL";
    private static final String ERROR_INSERT_FAILED = "insert component asset failed";
    private static final String ERROR_UPDATE_FAILED = "update component asset failed";
    private static final String ERROR_SUPPORT_CLIENTS_INVALID = "supportClients is invalid JSON array";
    private static final String FIELD_PARAMS_SCHEMA_JSON = "paramsSchemaJson";
    private static final String FIELD_OFFICIAL_DEMO_JSON = "officialDemoJson";
    private static final String FIELD_MESSAGE_DEMO_JSON = "messageDemoJson";
    private static final String FIELD_ALLOWED_ACTIONS_JSON = "allowedActionsJson";
    private static final String FIELD_RUNTIME_CONFIG_JSON = "runtimeConfigJson";
    private static final String FIELD_A2UI_CONTRACT_JSON = "a2uiContractJson";
    private static final String FIELD_SUPPORT_CLIENTS = "supportClients";
    private static final String FIELD_ATTRIBUTE = "attribute";

    @Resource
    private SkillFactoryComponentAssetMapper componentAssetMapper;

    /**
     * 按管理面条件查询组件领域对象。
     */
    public List<ComponentAsset> list(ComponentAssetQuery query, boolean enabledOnly) {
        ComponentAssetQuery safeQuery = query == null ? new ComponentAssetQuery() : query;
        LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaQueryWrapper<>();
        if (specified(safeQuery.getAssetType())) {
            wrapper.eq(SkillFactoryComponentAssetDO::getAssetType, safeQuery.getAssetType());
        }
        if (specified(safeQuery.getDslType())) {
            wrapper.eq(SkillFactoryComponentAssetDO::getDslType, safeQuery.getDslType());
        }
        if (enabledOnly) {
            wrapper.eq(SkillFactoryComponentAssetDO::getEnabled, ENABLED_TRUE);
        }
        if (StringUtils.isNotBlank(safeQuery.getKeyword())) {
            String keyword = safeQuery.getKeyword();
            wrapper.and(condition -> condition
                    .like(SkillFactoryComponentAssetDO::getComponentName, keyword)
                    .or().like(SkillFactoryComponentAssetDO::getComponentNameCn, keyword)
                    .or().like(SkillFactoryComponentAssetDO::getAgentUiDsl, keyword)
                    .or().like(SkillFactoryComponentAssetDO::getOwner, keyword)
                    .or().like(SkillFactoryComponentAssetDO::getScene, keyword));
        }
        wrapper.orderByDesc(SkillFactoryComponentAssetDO::getUpdateTime)
                .orderByDesc(SkillFactoryComponentAssetDO::getId);
        List<SkillFactoryComponentAssetDO> rows = componentAssetMapper.selectList(wrapper);
        List<ComponentAsset> result = new ArrayList<>();
        if (rows != null) {
            rows.stream().map(this::toDomain).forEach(result::add);
        }
        log.info("SkillFactory组件Registry查询DB完成, keyword:{}, assetType:{}, dslType:{}, "
                        + "enabledOnly:{}, count:{}",
                safeQuery.getKeyword(), safeQuery.getAssetType(), safeQuery.getDslType(),
                enabledOnly, result.size());
        return result;
    }

    /**
     * 按主键读取组件领域对象。
     */
    public ComponentAsset get(Long id) {
        if (id == null) {
            return null;
        }
        ComponentAsset asset = toDomain(componentAssetMapper.selectById(id));
        log.info("SkillFactory组件Registry按ID查询DB完成, id:{}, found:{}", id, asset != null);
        return asset;
    }

    /**
     * 按 CARD_CONTAINER 稳定组件名精确读取 Registry 当前行。
     *
     * <p>该查询只负责稳定身份到资产 ID 的数据库定位；是否启用、当前环境发布指针是否有效以及
     * 模型可见字段裁剪均由上层组件 Tool 服务处理。
     */
    public ComponentAsset findCardComponentByName(String componentName) {
        if (StringUtils.isBlank(componentName)) {
            return null;
        }
        LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getAssetType, ASSET_TYPE_CARD_COMPONENT)
                .eq(SkillFactoryComponentAssetDO::getComponentName, StringUtils.trim(componentName));
        ComponentAsset asset = toDomain(componentAssetMapper.selectOne(wrapper));
        log.info("SkillFactory组件Registry按稳定名称查询DB完成, componentName:{}, found:{}",
                componentName, asset != null);
        return asset;
    }

    /**
     * 按稳定组件名精确读取共享 Registry 当前行。
     *
     * <p>该查询不预判组件的发布聚合类型；上游必须使用 Registry 类型化发布身份解析器决定
     * COMPONENT 或 A2UI_APPLICATION，并对不支持、缺失或歧义身份关闭处理。
     */
    public ComponentAsset findByComponentName(String componentName) {
        if (StringUtils.isBlank(componentName)) {
            return null;
        }
        LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getComponentName, StringUtils.trim(componentName));
        ComponentAsset asset = toDomain(componentAssetMapper.selectOne(wrapper));
        log.info("SkillFactory组件Registry按稳定名称精确查询DB完成, componentName:{}, found:{}",
                componentName, asset != null);
        return asset;
    }

    /**
     * 按 `(assetType, componentName)` 精确读取共享 Registry 当前行，供 A2UI Application/Catalog
     * release adapter 读取唯一事实源；不按旧协议字段猜测资产身份。
     */
    public ComponentAsset findByAssetTypeAndName(String assetType, String componentName) {
        if (StringUtils.isAnyBlank(assetType, componentName)) {
            return null;
        }
        LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getAssetType, StringUtils.trim(assetType))
                .eq(SkillFactoryComponentAssetDO::getComponentName, StringUtils.trim(componentName));
        ComponentAsset asset = toDomain(componentAssetMapper.selectOne(wrapper));
        log.info("SkillFactory组件Registry按资产类型和稳定名称查询DB完成, assetType:{}, componentName:{}, found:{}",
                assetType, componentName, asset != null);
        return asset;
    }

    /**
     * 新增组件 Registry 行。
     */
    public ComponentAsset save(ComponentAsset asset) {
        long now = System.currentTimeMillis();
        SkillFactoryComponentAssetDO assetDO = toDO(asset)
                .setId(null)
                .setCreateTime(now)
                .setUpdateTime(now);
        if (componentAssetMapper.insert(assetDO) <= 0) {
            log.warn("SkillFactory组件Registry写入DB失败, assetType:{}, componentName:{}",
                    asset.getAssetType(), asset.getComponentName());
            throw new IllegalStateException(ERROR_INSERT_FAILED);
        }
        log.info("SkillFactory组件Registry写入DB完成, id:{}, assetType:{}, dslType:{}, componentName:{}",
                assetDO.getId(), assetDO.getAssetType(), assetDO.getDslType(), assetDO.getComponentName());
        return toDomain(assetDO);
    }

    /**
     * 更新组件 Registry 行；创建时间由当前 DB 行保持。
     */
    public ComponentAsset update(ComponentAsset asset) {
        SkillFactoryComponentAssetDO current = asset == null || asset.getId() == null
                ? null : componentAssetMapper.selectById(asset.getId());
        if (current == null) {
            return null;
        }
        SkillFactoryComponentAssetDO assetDO = toDO(asset)
                .setCreateTime(current.getCreateTime())
                .setUpdateTime(System.currentTimeMillis());
        if (componentAssetMapper.updateById(assetDO) <= 0) {
            log.warn("SkillFactory组件Registry更新DB失败, id:{}, componentName:{}",
                    assetDO.getId(), assetDO.getComponentName());
            throw new IllegalStateException(ERROR_UPDATE_FAILED);
        }
        if (assetDO.getIntegrationPrompt() == null && current.getIntegrationPrompt() != null) {
            clearIntegrationPromptIfRequired(assetDO);
        }
        log.info("SkillFactory组件Registry更新DB完成, id:{}, dslType:{}, componentName:{}, enabled:{}",
                assetDO.getId(), assetDO.getDslType(), assetDO.getComponentName(), assetDO.getEnabled());
        return toDomain(assetDO);
    }

    /**
     * MyBatis-Plus 选择性更新默认跳过 null；这里显式清空已退役的组件接入提示词。
     */
    private void clearIntegrationPromptIfRequired(SkillFactoryComponentAssetDO assetDO) {
        if (assetDO.getIntegrationPrompt() != null) {
            return;
        }
        LambdaUpdateWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getId, assetDO.getId())
                .set(SkillFactoryComponentAssetDO::getIntegrationPrompt, null);
        if (componentAssetMapper.update(null, wrapper) <= 0) {
            log.warn("SkillFactory组件Registry清空接入提示词失败, id:{}", assetDO.getId());
            throw new IllegalStateException(ERROR_UPDATE_FAILED);
        }
        log.info("SkillFactory组件Registry接入提示词已清空, id:{}", assetDO.getId());
    }

    /**
     * 只更新 CARD_COMPONENT 基础信息列。
     *
     * <p>该写入不触碰 Schema、模板、示例、接入提示词或运行配置，避免基础信息保存覆盖并发的复杂配置修改。
     */
    public ComponentAsset updateCardBasicInfo(ComponentAsset asset) {
        if (asset == null || asset.getId() == null) {
            return null;
        }
        long now = System.currentTimeMillis();
        LambdaUpdateWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getId, asset.getId())
                .set(SkillFactoryComponentAssetDO::getComponentNameCn,
                        StringUtils.trimToNull(asset.getComponentNameCn()))
                .set(SkillFactoryComponentAssetDO::getInteractionMode,
                        StringUtils.trimToNull(asset.getInteractionMode()))
                .set(SkillFactoryComponentAssetDO::getBundleUrl,
                        StringUtils.trimToNull(asset.getBundleUrl()))
                .set(SkillFactoryComponentAssetDO::getAppBundleUrl,
                        StringUtils.trimToNull(asset.getAppBundleUrl()))
                .set(SkillFactoryComponentAssetDO::getScene,
                        StringUtils.trimToNull(asset.getScene()))
                .set(SkillFactoryComponentAssetDO::getOperator,
                        StringUtils.trimToNull(asset.getOperator()))
                .set(SkillFactoryComponentAssetDO::getUpdateTime, now);
        if (componentAssetMapper.update(null, wrapper) <= 0) {
            log.warn("SkillFactory组件Registry基础信息更新DB失败, id:{}, componentName:{}",
                    asset.getId(), asset.getComponentName());
            throw new IllegalStateException(ERROR_UPDATE_FAILED);
        }
        SkillFactoryComponentAssetDO updated = componentAssetMapper.selectById(asset.getId());
        log.info("SkillFactory组件Registry基础信息更新DB完成, id:{}, componentName:{}, interactionMode:{}",
                asset.getId(), asset.getComponentName(), asset.getInteractionMode());
        return toDomain(updated);
    }

    /**
     * 禁用组件 Registry 行；发布版本和环境生效状态由共享发布表独立维护。
     */
    public ComponentAsset offline(Long id, String operator) {
        SkillFactoryComponentAssetDO current = id == null ? null : componentAssetMapper.selectById(id);
        if (current == null) {
            return null;
        }
        current.setEnabled(ENABLED_FALSE)
                .setOperator(operator)
                .setUpdateTime(System.currentTimeMillis());
        if (componentAssetMapper.updateById(current) <= 0) {
            log.warn("SkillFactory组件Registry禁用DB失败, id:{}", id);
            throw new IllegalStateException(ERROR_UPDATE_FAILED);
        }
        log.info("SkillFactory组件Registry禁用DB完成, id:{}, componentName:{}, operator:{}",
                id, current.getComponentName(), operator);
        return toDomain(current);
    }

    /**
     * 校验管理身份 `(assetType, componentName)` 是否重复。
     */
    public boolean existsComponentIdentity(Long excludeId, String assetType, String componentName) {
        LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getAssetType, assetType)
                .eq(SkillFactoryComponentAssetDO::getComponentName, componentName);
        excludeId(wrapper, excludeId);
        return componentAssetMapper.selectCount(wrapper) > 0;
    }

    /**
     * 校验 BUSINESS_DSL 运行态身份 `(dslType, agentUiDsl)` 是否重复。
     */
    public boolean existsBusinessDslIdentity(Long excludeId, String dslType, String agentUiDsl) {
        if (StringUtils.isBlank(agentUiDsl)) {
            return false;
        }
        LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryComponentAssetDO::getDslType, dslType)
                .eq(SkillFactoryComponentAssetDO::getAgentUiDsl, agentUiDsl);
        excludeId(wrapper, excludeId);
        return componentAssetMapper.selectCount(wrapper) > 0;
    }

    private void excludeId(LambdaQueryWrapper<SkillFactoryComponentAssetDO> wrapper, Long excludeId) {
        if (excludeId != null) {
            wrapper.ne(SkillFactoryComponentAssetDO::getId, excludeId);
        }
    }

    private boolean specified(String value) {
        return StringUtils.isNotBlank(value) && !StringUtils.equalsIgnoreCase(value, VALUE_ALL);
    }

    private SkillFactoryComponentAssetDO toDO(ComponentAsset asset) {
        List<String> supportClients = asset.getSupportClients() == null
                ? Collections.emptyList() : asset.getSupportClients();
        String supportClientsJson = supportClients.isEmpty()
                ? null : JsonSupport.toJSON(supportClients);
        return new SkillFactoryComponentAssetDO()
                .setId(asset.getId())
                .setAssetType(asset.getAssetType())
                .setComponentName(asset.getComponentName())
                .setComponentNameCn(StringUtils.trimToNull(asset.getComponentNameCn()))
                .setA2uiComponentType(StringUtils.trimToNull(asset.getA2uiComponentType()))
                .setA2uiContractJson(SkillFactoryJsonColumnSupport.nullable(
                        asset.getA2uiContractJson(), FIELD_A2UI_CONTRACT_JSON))
                .setDslType(StringUtils.trimToNull(asset.getDslType()))
                .setAgentUiDsl(StringUtils.trimToNull(asset.getAgentUiDsl()))
                .setProtocolVersion(asset.getProtocolVersion())
                .setInteractionMode(StringUtils.trimToNull(asset.getInteractionMode()))
                .setBundleUrl(StringUtils.trimToNull(asset.getBundleUrl()))
                .setAppBundleUrl(StringUtils.trimToNull(asset.getAppBundleUrl()))
                .setOwner(StringUtils.trimToNull(asset.getOwner()))
                .setScene(StringUtils.trimToNull(asset.getScene()))
                .setParamsSchemaJson(SkillFactoryJsonColumnSupport.nullable(
                        asset.getParamsSchemaJson(), FIELD_PARAMS_SCHEMA_JSON))
                .setRenderTemplateJson(StringUtils.trimToNull(asset.getRenderTemplateJson()))
                .setOfficialDemoJson(SkillFactoryJsonColumnSupport.nullable(
                        asset.getOfficialDemoJson(), FIELD_OFFICIAL_DEMO_JSON))
                .setMessageDemoJson(SkillFactoryJsonColumnSupport.nullable(
                        asset.getMessageDemoJson(), FIELD_MESSAGE_DEMO_JSON))
                .setAllowedActionsJson(SkillFactoryJsonColumnSupport.nullable(
                        asset.getAllowedActionsJson(), FIELD_ALLOWED_ACTIONS_JSON))
                .setRuntimeConfigJson(SkillFactoryJsonColumnSupport.nullable(
                        asset.getRuntimeConfigJson(), FIELD_RUNTIME_CONFIG_JSON))
                .setIntegrationPrompt(StringUtils.trimToNull(asset.getIntegrationPrompt()))
                .setSupportClients(SkillFactoryJsonColumnSupport.nullable(
                        supportClientsJson, FIELD_SUPPORT_CLIENTS))
                .setEnabled(Boolean.TRUE.equals(asset.getEnabled()) ? ENABLED_TRUE : ENABLED_FALSE)
                .setAttribute(SkillFactoryJsonColumnSupport.nullable(asset.getAttribute(), FIELD_ATTRIBUTE))
                .setOperator(asset.getOperator())
                .setCreateTime(asset.getCreateTime())
                .setUpdateTime(asset.getUpdateTime());
    }

    private ComponentAsset toDomain(SkillFactoryComponentAssetDO assetDO) {
        if (assetDO == null) {
            return null;
        }
        return new ComponentAsset()
                .setId(assetDO.getId())
                .setAssetType(assetDO.getAssetType())
                .setComponentName(assetDO.getComponentName())
                .setComponentNameCn(assetDO.getComponentNameCn())
                .setA2uiComponentType(assetDO.getA2uiComponentType())
                .setA2uiContractJson(assetDO.getA2uiContractJson())
                .setDslType(assetDO.getDslType())
                .setAgentUiDsl(assetDO.getAgentUiDsl())
                .setProtocolVersion(assetDO.getProtocolVersion())
                .setInteractionMode(assetDO.getInteractionMode())
                .setBundleUrl(assetDO.getBundleUrl())
                .setAppBundleUrl(assetDO.getAppBundleUrl())
                .setOwner(assetDO.getOwner())
                .setScene(assetDO.getScene())
                .setParamsSchemaJson(assetDO.getParamsSchemaJson())
                .setRenderTemplateJson(assetDO.getRenderTemplateJson())
                .setOfficialDemoJson(assetDO.getOfficialDemoJson())
                .setMessageDemoJson(assetDO.getMessageDemoJson())
                .setAllowedActionsJson(assetDO.getAllowedActionsJson())
                .setRuntimeConfigJson(assetDO.getRuntimeConfigJson())
                .setIntegrationPrompt(assetDO.getIntegrationPrompt())
                .setSupportClients(parseSupportClients(assetDO.getSupportClients()))
                .setEnabled(ENABLED_TRUE == value(assetDO.getEnabled()))
                .setAttribute(assetDO.getAttribute())
                .setOperator(assetDO.getOperator())
                .setCreateTime(assetDO.getCreateTime())
                .setUpdateTime(assetDO.getUpdateTime());
    }

    @SuppressWarnings("unchecked")
    private List<String> parseSupportClients(String supportClientsJson) {
        if (StringUtils.isBlank(supportClientsJson)) {
            return new ArrayList<>();
        }
        try {
            List<Object> values = JsonSupport.fromJSON(supportClientsJson, List.class);
            List<String> result = new ArrayList<>();
            if (values != null) {
                values.forEach(value -> result.add(String.valueOf(value)));
            }
            return result;
        } catch (Exception exception) {
            throw new IllegalStateException(ERROR_SUPPORT_CLIENTS_INVALID, exception);
        }
    }

    private int value(Integer enabled) {
        return enabled == null ? ENABLED_FALSE : enabled;
    }

    /**
     * 组件管理面查询条件；不承载 DO 或表结构。
     */
    @Data
    @Accessors(chain = true)
    public static class ComponentAssetQuery {
        private String keyword;
        private String assetType;
        private String dslType;
    }
}
