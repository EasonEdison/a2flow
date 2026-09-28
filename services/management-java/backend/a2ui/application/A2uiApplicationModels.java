package dev.a2flow.management.a2ui.application;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonInclude;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogSourceType;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.Value;
import lombok.experimental.Accessors;

/**
 * A2UI Application 作者态与编译态领域模型。
 *
 * <p>上游是 M 端 canonical draft，下游是 Artifact Runtime 和 Action Gateway。作者态模型允许在
 * ACTIVE change 中编辑；编译态模型使用只读 value object 和深冻结集合形成不可变 Build。本模型
 * 不负责数据库、发布指针、物理 HTTP/SSE 或 B Renderer。
 */
public final class A2uiApplicationModels {

    private static final String ERROR_UNKNOWN_RESULT_TRANSFORM_FIELD =
            "未知的ResultAdapter转换字段: ";

    private A2uiApplicationModels() {
    }

    public enum A2uiSideEffectLevel {
        READ_ONLY,
        WRITE,
        DESTRUCTIVE
    }

    /** Application 首屏成功后是否进入 Workflow 用户交互等待态。 */
    public enum A2uiInteractionMode {
        DISPLAY_ONLY,
        INTERACTIVE
    }

    public enum A2uiMappingSource {
        ACTION_CONTEXT,
        APP_PARAMS,
        TRUSTED_CONTEXT,
        CONSTANT,
        CAPABILITY_PREVIOUS_RESULT
    }

    /** 请求映射唯一允许的转换类型；不支持脚本、格式化或隐式类型转换。 */
    public enum A2uiRequestTransformType {
        STRING_PREFIX,
        ARRAY_FILTER_BY_BOOLEAN_MASK
    }

    /** 作者态请求转换；原始形态先校验，compiler 再核对来源及 schema，不执行业务请求。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiRequestTransform {
        private A2uiRequestTransformType type;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String prefix;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String maskSourcePath;
    }

    /**
     * Build 冻结的请求转换；供 Adviser 执行封闭的值转换，不持有作者态对象或业务逻辑。
     */
    @Value
    public static class A2uiCompiledRequestTransform {
        private A2uiRequestTransformType type;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String prefix;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String maskSourcePath;
    }

    public enum A2uiResultAdapterType {
        MESSAGE_TEMPLATE,
        A2UI_PASSTHROUGH
    }

    /** ResultAdapter 可读取的显式数据根；不包含历史完整 ToolResult 根。 */
    public enum A2uiResultSource {
        CAPABILITY_DATA,
        CAPABILITY_META,
        TRUSTED_CONTEXT,
        ACTION_CONTEXT,
        CONSTANT
    }

    /** ResultAdapter 值转换的封闭类型；不得扩展为脚本或业务专用格式化。 */
    public enum A2uiResultTransformType {
        MINOR_UNIT_TO_DECIMAL_STRING,
        ARRAY_TO_CHILDREN_PREFIX,
        BOOLEAN_ARRAY_TRUE_COUNT,
        PAGINATION_STATE,
        NUMBER_TO_STRING
    }

    /** 作者态结果值转换；compiler 负责校验参数并冻结为不可变 Build 配置。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiResultTransform {
        private A2uiResultTransformType type;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Number scale;
        @JsonInclude(JsonInclude.Include.NON_EMPTY)
        private List<String> componentIds;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Number pageSize;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Number pageNumber;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String actionPagePath;

        /** 作者态 JSON 出现未声明字段时直接失败，避免发布后产生不同解释。 */
        @JsonAnySetter
        public void rejectUnknownField(String fieldName, Object ignoredValue) {
            throw new IllegalArgumentException(ERROR_UNKNOWN_RESULT_TRANSFORM_FIELD + fieldName);
        }
    }

    /** Build 冻结的结果值转换；仅描述确定性转换，不执行运行时计算。 */
    @Value
    public static class A2uiCompiledResultTransform {
        private A2uiResultTransformType type;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Integer scale;
        @JsonInclude(JsonInclude.Include.NON_EMPTY)
        private List<String> componentIds;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Number pageSize;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Number pageNumber;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String actionPagePath;
    }

    public enum A2uiActionDeclarationSourceType {
        SHOW_TEMPLATE,
        MESSAGE_TEMPLATE,
        A2UI_PASSTHROUGH
    }

    public enum A2uiActionDeclarationStatus {
        BOUND,
        UNBOUND,
        UNREFERENCED,
        NEEDS_REVALIDATION,
        RESERVED
    }

    public enum A2uiResultOutcome {
        ADAPTER_PIPELINE,
        NO_UI_MESSAGES
    }

    /** 业务成功判定的封闭作者态条件；字段使用字符串以便 compiler 稳定拒绝未知值。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiBusinessPredicateClause {
        private String source;
        private String sourcePath;
        private String operator;
        private Object expectedValue;
    }

    /** transport 成功后选择 success/failure outcome 的版本化业务谓词。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiBusinessSuccessPredicate {
        private String version;
        private List<A2uiBusinessPredicateClause> allOf = new ArrayList<>();
    }

    public enum A2uiShowInputSource {
        APP_PARAMS,
        TRUSTED_CONTEXT,
        CONSTANT
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiApplicationCatalogRef {
        private String catalogId;
        private String revision;
        private String digest;
        private A2uiCatalogSourceType catalogSourceType;
        private Map<String, A2uiComponentOriginType> componentOrigins = new LinkedHashMap<>();
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiSurfaceDeclaration {
        private String surfaceId;
        private String rootComponentId;
        /** Workflow 操作区引用；必须为根容器的直接子组件，独立渲染时不移动。 */
        @JsonInclude(JsonInclude.Include.NON_EMPTY)
        private List<String> footerComponentIds = new ArrayList<>();
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiShowInputBinding {
        private int targetMessageIndex;
        private String targetPath;
        private A2uiShowInputSource source;
        private String sourcePath;
        private boolean required;
        private Object constantValue;
    }

    /** Application 私有 ShowTemplate；组件 action.event 是唯一可编辑 Action 真值。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiShowTemplate {
        private String templateCode;
        private Map<String, Object> paramsSchema = new LinkedHashMap<>();
        private List<A2uiSurfaceDeclaration> surfaceDeclarations = new ArrayList<>();
        private List<Map<String, Object>> messageTemplates = new ArrayList<>();
        private List<A2uiShowInputBinding> inputBindings = new ArrayList<>();
    }

    /** 作者态业务请求映射；转换交由 compiler 校验并冻结，不允许改变可信身份。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiRequestMapping {
        private A2uiMappingSource source;
        private String sourcePath;
        private String targetPath;
        private Object constantValue;
        private A2uiRequestTransform transform;
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiCapabilityActionRef {
        private String actionCode;
    }

    /**
     * 发布编译时读取的当前生效 CapabilityAction 契约。
     *
     * <p>该对象只作为 compiler 输入，用于校验 mapping、结果适配和副作用边界；
     * 它不会被编译进
     * 运行时路由引用，也不携带 Capability 版本、releaseId 或 digest。
     */
    @Value
    public static class A2uiCurrentCapabilityVariantContract {
        private String clientType;
        private Map<String, Object> modelContract;
        private Map<String, Object> resultContract;
    }

    /**
     * 发布能力声明的全部真实端契约；compiler 必须逐项校验，Runtime 仍按可信 client 选择。
     */
    @Value
    public static class A2uiCurrentCapabilityContract {
        private String actionCode;
        private Map<String, A2uiCurrentCapabilityVariantContract> clientVariants;
        private A2uiSideEffectLevel sideEffect;

        public A2uiCurrentCapabilityContract(String actionCode,
                Map<String, A2uiCurrentCapabilityVariantContract> clientVariants,
                A2uiSideEffectLevel sideEffect) {
            this.actionCode = actionCode;
            this.clientVariants = clientVariants == null ? null
                    : Collections.unmodifiableMap(new LinkedHashMap<>(clientVariants));
            this.sideEffect = sideEffect;
        }

        /** 兼容已有 COMMON fixture；仍进入统一 variants 校验，不保留旧单契约旁路。 */
        public A2uiCurrentCapabilityContract(String actionCode,
                Map<String, Object> modelContract,
                Map<String, Object> resultContract,
                A2uiSideEffectLevel sideEffect) {
            this(actionCode, Collections.singletonMap("COMMON",
                    new A2uiCurrentCapabilityVariantContract(
                            "COMMON", modelContract, resultContract)), sideEffect);
        }
    }

    /** 当前 Capability schema 的发布时审计结果；Runtime 不使用它选择执行版本。 */
    @Value
    public static class A2uiCapabilitySchemaAudit {
        private String actionCode;
        private String modelContractDigest;
        private String resultContractDigest;
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiMessageTemplateBinding {
        private String targetPath;
        private A2uiResultSource source;
        private String sourcePath;
        private boolean required;
        private Object constantValue;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private A2uiResultTransform transform;
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiEmittedActionDeclaration {
        private String surfaceId;
        private String sourceComponentId;
        private String actionCode;
        private Map<String, Object> contextSchema = new LinkedHashMap<>();
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiResultAdapter {
        private String adapterId;
        private int order;
        private A2uiResultAdapterType type;
        private String templateCode;
        private String templateRevision;
        private String templateDigest;
        private Map<String, Object> messageTemplate;
        private List<A2uiMessageTemplateBinding> bindings = new ArrayList<>();
        private A2uiResultSource source;
        private String sourcePath;
        private String cardinality;
        private boolean required;
        private List<A2uiEmittedActionDeclaration> emittedActionDeclarations = new ArrayList<>();
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiActionDeclarationSource {
        private A2uiActionDeclarationSourceType sourceType;
        private String path;
        private String bindingId;
        private String outcome;
        private String adapterId;
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiScannedActionDeclaration {
        private String eventName;
        private String surfaceId;
        private String sourceComponentId;
        private String actionCode;
        private String contextTemplateDigest;
        private Map<String, Object> contextSchema = new LinkedHashMap<>();
        private List<String> contextFields = new ArrayList<>();
        private List<A2uiActionDeclarationSource> discoveredFrom = new ArrayList<>();
        private A2uiActionDeclarationStatus status;
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiApplicationActionScanResult {
        private List<A2uiScannedActionDeclaration> actionDeclarations = new ArrayList<>();
        private List<String> validationErrors = new ArrayList<>();
        private List<String> releaseBlockers = new ArrayList<>();
        private String sourceDigest;
    }

    /**
     * 作者态成功分支；根业务谓词成功后按声明顺序选取首个命中的分支。
     * 上游提供条件与结果管线，下游 compiler 校验冻结；本对象不执行能力或完成 Workflow。
     */
    @Data
    @Accessors(chain = true)
    public static class A2uiSuccessBranch {
        private String branchId;
        private A2uiBusinessSuccessPredicate when;
        private A2uiResultOutcome outcome;
        private List<A2uiResultAdapter> resultAdapters = new ArrayList<>();
        private boolean completeWorkflowInteractionOnSuccess;
    }

    /** 作者态 Action 绑定；包含根成功、失败及有序成功分支，由 compiler 校验闭包并冻结。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiActionBinding {
        private String bindingId;
        private String surfaceId;
        private String sourceComponentId;
        private String actionCode;
        private String declarationDigest;
        private List<String> allowedSourceComponentIds = new ArrayList<>();
        private Map<String, Object> contextSchema = new LinkedHashMap<>();
        private A2uiCapabilityActionRef capability;
        private List<A2uiRequestMapping> requestMappings = new ArrayList<>();
        private A2uiResultOutcome successOutcome;
        private A2uiResultOutcome failureOutcome;
        private List<A2uiResultAdapter> resultAdapters = new ArrayList<>();
        private List<A2uiResultAdapter> failureResultAdapters = new ArrayList<>();
        private A2uiBusinessSuccessPredicate businessSuccessPredicate;
        private boolean completeWorkflowInteractionOnSuccess;
        @JsonInclude(JsonInclude.Include.NON_EMPTY)
        private List<A2uiSuccessBranch> successBranches = new ArrayList<>();
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiLoadBinding {
        private String bindingId;
        private A2uiCapabilityActionRef capability;
        private List<A2uiRequestMapping> requestMappings = new ArrayList<>();
        private A2uiResultOutcome successOutcome;
        private A2uiResultOutcome failureOutcome;
        private List<A2uiResultAdapter> resultAdapters = new ArrayList<>();
        private List<A2uiResultAdapter> failureResultAdapters = new ArrayList<>();
    }

    /** M 端保存的一份 canonical draft；derived ActionDeclaration 不允许作为输入字段存在。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiApplicationDraft {
        private String appCode;
        private String nameCn;
        private String description;
        private A2uiInteractionMode interactionMode = A2uiInteractionMode.DISPLAY_ONLY;
        private String catalogId;
        private String protocolVersion;
        private String protocolStatus;
        private String protocolSourceCommit;
        private Map<String, String> protocolSchemaDigests = new LinkedHashMap<>();
        private A2uiApplicationCatalogRef catalog;
        private A2uiShowTemplate showTemplate;
        private List<A2uiLoadBinding> loadBindings = new ArrayList<>();
        private List<A2uiActionBinding> actionBindings = new ArrayList<>();
    }

    @Value
    public static class A2uiCompiledCatalogRef {
        private String catalogId;
        private String revision;
        private String digest;
        private A2uiCatalogSourceType catalogSourceType;
        private Map<String, A2uiComponentOriginType> componentOrigins;
        private Map<String, Object> functionContract;
    }

    @Value
    public static class A2uiActionDeclaration {
        private String surfaceId;
        private String sourceComponentId;
        private String actionCode;
        private String contextTemplateDigest;
    }

    @Value
    public static class A2uiCompiledCapabilityActionRef {
        private String actionCode;
    }

    /** 不可变请求映射；省略空转换以保持旧 Build 的序列化形态与摘要输入。 */
    @Value
    @AllArgsConstructor
    public static class A2uiCompiledRequestMapping {
        private A2uiMappingSource source;
        private String sourcePath;
        private String targetPath;
        private Object constantValue;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private A2uiCompiledRequestTransform transform;

        /** 保留既有直接映射构造入口，未配置转换时保持原值语义。 */
        public A2uiCompiledRequestMapping(A2uiMappingSource source, String sourcePath,
                String targetPath, Object constantValue) {
            this(source, sourcePath, targetPath, constantValue, null);
        }
    }

    @Value
    @AllArgsConstructor
    public static class A2uiCompiledMessageTemplateBinding {
        private String targetPath;
        private A2uiResultSource source;
        private String sourcePath;
        private boolean required;
        private Object constantValue;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private A2uiCompiledResultTransform transform;

        /** 保留既有无转换构造入口，未配置 transform 时仍按原值复制。 */
        public A2uiCompiledMessageTemplateBinding(String targetPath, A2uiResultSource source,
                String sourcePath, boolean required, Object constantValue) {
            this(targetPath, source, sourcePath, required, constantValue, null);
        }
    }

    @Value
    public static class A2uiCompiledEmittedActionDeclaration {
        private String surfaceId;
        private String sourceComponentId;
        private String actionCode;
        private Map<String, Object> contextSchema;
    }

    /** 不可变 Build 中的单条封闭业务成功条件。 */
    @Value
    public static class A2uiCompiledBusinessPredicateClause {
        private String source;
        private String sourcePath;
        private String operator;
        private Object expectedValue;
    }

    /** 不可变 Build 中完整冻结的版本化业务成功谓词。 */
    @Value
    public static class A2uiCompiledBusinessSuccessPredicate {
        private String version;
        private List<A2uiCompiledBusinessPredicateClause> allOf;
    }

    @Value
    public static class A2uiCompiledResultAdapter {
        private String adapterId;
        private int order;
        private A2uiResultAdapterType type;
        private String templateCode;
        private String templateRevision;
        private String templateDigest;
        private Map<String, Object> messageTemplate;
        private List<A2uiCompiledMessageTemplateBinding> bindings;
        private A2uiResultSource source;
        private String sourcePath;
        private String cardinality;
        private boolean required;
        private List<A2uiCompiledEmittedActionDeclaration> emittedActionDeclarations;
    }

    /**
     * Build 冻结的成功分支；条件、结果管线和完成标记作为同一份选择结果交给 Adviser。
     * compiler 深冻结其集合，本对象不持有作者态引用，也不执行运行时选择或交互提交。
     */
    @Value
    public static class A2uiCompiledSuccessBranch {
        private String branchId;
        private A2uiCompiledBusinessSuccessPredicate when;
        private A2uiResultOutcome outcome;
        private List<A2uiCompiledResultAdapter> resultAdapters;
        private boolean completeWorkflowInteractionOnSuccess;
    }

    /** 不可变 Action 绑定；成功分支保持作者顺序，空分支不改变既有 Build 序列化形态。 */
    @Value
    public static class A2uiCompiledActionBinding {
        private String bindingId;
        private String surfaceId;
        private String sourceComponentId;
        private String actionCode;
        private String declarationDigest;
        private List<String> allowedSourceComponentIds;
        private Map<String, Object> contextSchema;
        private A2uiCompiledCapabilityActionRef capability;
        private List<A2uiCompiledRequestMapping> requestMappings;
        private A2uiResultOutcome successOutcome;
        private A2uiResultOutcome failureOutcome;
        private List<A2uiCompiledResultAdapter> resultAdapters;
        private List<A2uiCompiledResultAdapter> failureResultAdapters;
        private A2uiCompiledBusinessSuccessPredicate businessSuccessPredicate;
        private boolean completeWorkflowInteractionOnSuccess;
        @JsonInclude(JsonInclude.Include.NON_EMPTY)
        private List<A2uiCompiledSuccessBranch> successBranches;
    }

    @Value
    public static class A2uiCompiledLoadBinding {
        private String bindingId;
        private A2uiCompiledCapabilityActionRef capability;
        private List<A2uiCompiledRequestMapping> requestMappings;
        private A2uiResultOutcome successOutcome;
        private A2uiResultOutcome failureOutcome;
        private List<A2uiCompiledResultAdapter> resultAdapters;
        private List<A2uiCompiledResultAdapter> failureResultAdapters;
    }

    @Value
    public static class A2uiCompiledShowInputBinding {
        private int targetMessageIndex;
        private String targetPath;
        private A2uiShowInputSource source;
        private String sourcePath;
        private boolean required;
        private Object constantValue;
    }

    @Value
    @AllArgsConstructor
    public static class A2uiCompiledSurfaceDeclaration {
        private String surfaceId;
        private String rootComponentId;
        @JsonInclude(JsonInclude.Include.NON_EMPTY)
        private List<String> footerComponentIds;

        public A2uiCompiledSurfaceDeclaration(String surfaceId, String rootComponentId) {
            this(surfaceId, rootComponentId, Collections.emptyList());
        }
    }

    /**
     * 自包含不可变 Application Build。
     *
     * <p>所有集合和 JSON 节点在 compiler 中深冻结，不保留对 draft 的引用。Catalog、ShowTemplate
     * 和 ResultAdapter 均由 Build 固定；Capability 只保存稳定 actionCode，Runtime 按既有能力中心
     * 语义解析当前生效版本并重新校验 schema，不使用 schema audit 作为版本路由条件。
     */
    @Value
    public static class A2uiApplicationBuild {
        private String appBuildId;
        private String appCode;
        private String description;
        private String sourceDigest;
        private String protocolVersion;
        private String protocolStatus;
        private String protocolSourceCommit;
        private Map<String, String> protocolSchemaDigests;
        private String publicationEnvironment;
        private A2uiCompiledCatalogRef catalog;
        private String showTemplateCode;
        private String showTemplateDigest;
        private Map<String, Object> paramsSchema;
        private List<A2uiCompiledSurfaceDeclaration> surfaceDeclarations;
        private List<Map<String, Object>> initialMessages;
        private List<A2uiCompiledShowInputBinding> inputBindings;
        private List<String> componentTypes;
        private List<A2uiCapabilitySchemaAudit> capabilitySchemaAudits;
        private List<A2uiActionDeclaration> actionDeclarations;
        private List<A2uiCompiledLoadBinding> loadBindings;
        private List<A2uiCompiledActionBinding> actionBindings;
        private A2uiInteractionMode interactionMode;
    }
}
