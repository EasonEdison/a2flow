package dev.a2flow.management.model;

import java.util.List;
import java.util.Map;
import java.util.Set;

import lombok.Builder;
import lombok.Value;

/**
 * 业务能力单版本的不可变执行计划。
 *
 * <p>该模型由已保存草稿或后续不可变 CapabilityActionVersion 编译得到，包含模型 Tool 契约、
 * 注册 Protobuf 描述与确定性字段映射。运行时只消费本对象，不重新推导响应 Demo，
 * 不接受模型覆盖服务、方法、目标配置键与可信 context。
 */
@Value
@Builder(toBuilder = true)
public class CapabilityActionExecutionPlan {

    private String sourceId;
    private String sourceDigest;
    private dev.a2flow.management.release.ReleaseEnvironment resolvedEnvironment;
    private String targetKey;
    private String serviceName;
    private String methodName;
    private String descriptorSetBase64;
    private String contextField;
    private String technicalOutputSchema;
    private int revision;
    private int capabilityVersion;
    /** 可信实际调用端，始终是 PC/APP；作者态 COMMON dry-run 时为 COMMON。 */
    private String clientType;
    /** 本次编译实际选择的发布契约键，用于读取模型示例等端内声明。 */
    private String contractClientType;
    private String actionCode;
    private String toolDescription;
    private String inputSchema;
    private List<Map<String, Object>> keyOutputFields;
    private String sourceType;
    /** 固定集群标识；实际环境地址在每次调用时读取最新 KConf。 */
    private String clusterCode;
    private String bindingType;
    private String registeredUrl;
    private String preReleaseUrl;
    private String productionUrl;
    private String path;
    private String httpMethod;
    private String contentType;
    private String authMode;
    private int timeoutMs;
    private int maxResponseBytes;
    private Set<Integer> successStatusCodes;
    private String idempotency;
    private String responsePolicy;
    private String sideEffectLevel;
    private List<String> modelArgumentFields;
    private List<String> requiredArgumentFields;
    private Map<String, String> argumentTypes;
    private Map<String, Map<String, Object>> argumentSchemas;
    private Map<String, List<Object>> allowedArgumentValues;
    private Map<String, String> staticHeaders;
    private Map<String, Map<String, String>> environmentHeaders;
    private Map<String, String> requestMappings;
    private Map<String, String> contextMappings;
    private Map<String, Map<String, String>> contextValueMappings;
    private Map<String, Object> constantMappings;
}
