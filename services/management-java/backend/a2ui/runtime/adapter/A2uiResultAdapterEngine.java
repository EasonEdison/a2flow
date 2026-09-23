package dev.a2flow.management.a2ui.runtime.adapter;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.a2ui.runtime.ledger.A2uiMessageSnapshotReducer;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiRuntimeSurfaceLedger;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledMessageTemplateBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledResultAdapter;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultAdapterType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultOutcome;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledResultTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultTransformType;
import dev.a2flow.management.a2ui.runtime.show.A2uiJsonPointerValueMapper;
import dev.a2flow.management.a2ui.runtime.show.A2uiJsonPointerValueMapper.LookupValue;
import dev.a2flow.management.a2ui.runtime.capability.CapabilityExecutionResult;

import lombok.Value;

/**
 * A2Flow A2UI Capability ToolResult 显式数据根到消息批次的有序适配引擎。
 *
 * <p>上游 Load/Action runtime 选择已发布 success/failure outcome 与对应 adapter 列表；本类按 order
 * 执行 MESSAGE_TEMPLATE 和 A2UI_PASSTHROUGH，把全部候选消息组装完成后才在当前 Surface ledger 的
 * 隔离副本上一次性校验。下游只能拿到完整批次和新 ledger；任一 adapter 失败时不会暴露先前消息。
 * Capability 原始业务响应只从 ToolResult.data 进入 {@code CAPABILITY_DATA}，Tool 元数据复制后移除
 * data 再进入 {@code CAPABILITY_META}；不读取历史完整 ToolResult 根，也不猜测或重试替代路径。
 * 本类不执行 Capability、不做权限或幂等处理、不访问业务数据源，也不发送 SSE 或提交数据库。</p>
 */
@Component
public class A2uiResultAdapterEngine {

    private static final long MAX_SAFE_JSON_INTEGER = 9007199254740991L;
    private static final String PAGE_TOTAL = "total";
    private static final String PAGE_PAGE_SIZE = "pageSize";
    private static final String PAGE_PAGE_NUM = "pageNum";
    private static final String PAGE_TOTAL_PAGES = "totalPages";
    private static final String PAGE_PREV_PAGE = "prevPage";
    private static final String PAGE_NEXT_PAGE = "nextPage";
    private static final String PAGE_PREV_DISABLED = "prevDisabled";
    private static final String PAGE_NEXT_DISABLED = "nextDisabled";
    private static final String PAGE_DISPLAY = "display";
    private static final String ERROR_PAGING_NUMBER = "分页总数与页码必须是整数";
    private static final String ERROR_PAGING_RANGE = "分页参数超出有效范围";
    private static final String ERROR_PAGING_OVERFLOW = "请求页码超过末页";
    private static final String CARDINALITY_ONE = "ONE";
    private static final String CARDINALITY_MANY = "MANY";
    private static final String ROOT_PATH = "/";
    private static final String CONSTANT_VALUE_FIELD = "value";
    private static final String CONSTANT_VALUE_PATH = "/value";
    private static final String ERROR_REQUEST_INVALID = "A2UI ResultAdapter request is invalid";
    private static final String ERROR_ADAPTER_INVALID = "A2UI ResultAdapter configuration is invalid";
    private static final String ERROR_SOURCE_MISSING = "A2UI ResultAdapter required source is missing";
    private static final String ERROR_RESULT_INVALID = "A2UI ResultAdapter output batch is invalid";
    private static final String UPDATE_COMPONENTS_PATH_SEGMENT = "updateComponents";
    private static final String COMPONENTS_PATH_SEGMENT = "components";
    private static final String CHILDREN_PATH_SEGMENT = "children";
    private static final int MAX_CHILD_COMPONENT_IDS = 100;
    private static final int MINOR_UNIT_DECIMAL_SCALE = 2;

    private final A2uiJsonPointerValueMapper valueMapper;
    private final A2uiMessageSnapshotReducer messageReducer;

    public A2uiResultAdapterEngine() {
        this.valueMapper = new A2uiJsonPointerValueMapper();
        this.messageReducer = new A2uiMessageSnapshotReducer();
    }

    /**
     * 按发布顺序生成完整候选批次，并在 cloned ledger 上一次性校验全部 A2UI 消息。
     */
    public AdaptedBatch adapt(A2uiRuntimeSurfaceLedger currentLedger,
            A2uiResultOutcome outcome, List<A2uiCompiledResultAdapter> adapters,
            CapabilityExecutionResult capabilityResult, Map<String, Object> trustedContext,
            Map<String, Object> actionContext) {
        validateRequest(currentLedger, outcome, adapters, capabilityResult, trustedContext, actionContext);
        // 显式NO_UI_MESSAGES表示本次业务结果不更新界面，直接沿用现有Ledger。
        if (A2uiResultOutcome.NO_UI_MESSAGES == outcome) {
            return new AdaptedBatch(Collections.emptyList(), currentLedger);
        }

        // 将业务data、能力元信息、可信上下文和已校验Action输入拆成独立根，避免模板跨边界误取字段。
        ResultRoots roots = resultRoots(capabilityResult, trustedContext, actionContext);
        List<A2uiProtocolMessage> messages = new ArrayList<>();
        int previousOrder = 0;
        for (A2uiCompiledResultAdapter adapter : adapters) {
            // adapter order必须严格递增，保证同一个Build在每次运行时产生相同消息顺序。
            if (adapter == null || adapter.getOrder() <= previousOrder
                    || adapter.getType() == null || StringUtils.isBlank(adapter.getAdapterId())) {
                throw new AdapterException(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID);
            }
            previousOrder = adapter.getOrder();
            if (A2uiResultAdapterType.MESSAGE_TEMPLATE == adapter.getType()) {
                // MESSAGE_TEMPLATE复制完整消息模板，再把声明的业务返回字段写入目标Pointer。
                messages.add(renderTemplate(adapter, roots));
            } else if (A2uiResultAdapterType.A2UI_PASSTHROUGH == adapter.getType()) {
                // A2UI_PASSTHROUGH直接读取业务返回中的一条或多条标准A2UI消息。
                messages.addAll(readPassthrough(adapter, roots));
            } else {
                throw new AdapterException(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID);
            }
        }
        if (messages.isEmpty()) {
            return new AdaptedBatch(Collections.emptyList(), currentLedger);
        }
        try {
            // 所有adapter先生成候选批次，再一次性应用到cloned ledger；任一非法则整批不可见。
            A2uiRuntimeSurfaceLedger nextLedger = messageReducer.reduce(
                    currentLedger, A2uiProtocolMessage.toMaps(messages));
            return new AdaptedBatch(Collections.unmodifiableList(messages), nextLedger);
        } catch (RuntimeException exception) {
            throw new AdapterException(Code.RESULT_INVALID, ERROR_RESULT_INVALID, exception);
        }
    }

    private void validateRequest(A2uiRuntimeSurfaceLedger currentLedger,
            A2uiResultOutcome outcome, List<A2uiCompiledResultAdapter> adapters,
            CapabilityExecutionResult capabilityResult, Map<String, Object> trustedContext,
            Map<String, Object> actionContext) {
        if (currentLedger == null || outcome == null || adapters == null || capabilityResult == null
                || trustedContext == null || actionContext == null
                || (A2uiResultOutcome.NO_UI_MESSAGES == outcome && !adapters.isEmpty())
                || (A2uiResultOutcome.ADAPTER_PIPELINE == outcome && adapters.isEmpty())) {
            throw new AdapterException(Code.REQUEST_INVALID, ERROR_REQUEST_INVALID);
        }
    }

    private ResultRoots resultRoots(CapabilityExecutionResult capabilityResult,
            Map<String, Object> trustedContext, Map<String, Object> actionContext) {
        return new ResultRoots(capabilityResult.getData(),
                Collections.unmodifiableMap(capabilityResult.toMetadataMap()),
                Collections.unmodifiableMap(new LinkedHashMap<>(trustedContext)),
                Collections.unmodifiableMap(new LinkedHashMap<>(actionContext)));
    }

    private A2uiProtocolMessage renderTemplate(A2uiCompiledResultAdapter adapter,
            ResultRoots roots) {
        if (adapter.getMessageTemplate() == null || adapter.getMessageTemplate().isEmpty()
                || adapter.getBindings() == null) {
            throw new AdapterException(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID);
        }
        // 发布模板视为不可变输入，先深拷贝后再逐项应用Binding。
        Object copied = valueMapper.write(new LinkedHashMap<>(), ROOT_PATH,
                adapter.getMessageTemplate());
        if (!(copied instanceof Map)) {
            throw new AdapterException(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID);
        }
        Map<String, Object> message = castMap(copied);
        for (A2uiCompiledMessageTemplateBinding binding : adapter.getBindings()) {
            if (binding == null || StringUtils.isBlank(binding.getTargetPath())
                    || binding.getSource() == null) {
                throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                        adapter, binding == null ? null : binding.getSource(),
                        binding == null ? null : binding.getSourcePath());
            }
            LookupValue sourceValue = resolveTemplateSource(adapter, binding, roots);
            if (!sourceValue.isFound() || sourceValue.getValue() == null) {
                if (binding.isRequired()) {
                    throw adapterFailure(Code.SOURCE_MISSING, ERROR_SOURCE_MISSING,
                            adapter, binding.getSource(), binding.getSourcePath());
                }
                continue;
            }
            Object targetValue = transformValue(adapter, binding, sourceValue.getValue(), roots);
            try {
                Object rendered = valueMapper.write(
                        message, binding.getTargetPath(), targetValue);
                if (!(rendered instanceof Map)) {
                    throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                            adapter, binding.getSource(), binding.getSourcePath());
                }
                message = castMap(rendered);
            } catch (A2uiJsonPointerValueMapper.MappingException exception) {
                throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                        adapter, binding.getSource(), binding.getSourcePath(), exception);
            }
        }
        return parseMessage(adapter, message);
    }

    /** required 判定完成后执行已发布的封闭转换；配置和值不合法时均失败关闭。 */
    private Object transformValue(A2uiCompiledResultAdapter adapter, A2uiCompiledMessageTemplateBinding binding,
            Object sourceValue, ResultRoots roots) {
        A2uiCompiledResultTransform transform = binding.getTransform();
        if (transform == null) {
            return sourceValue;
        }
        if (transform.getType() == A2uiResultTransformType.NUMBER_TO_STRING) {
            if (!(sourceValue instanceof Number)) {
                throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                        adapter, binding.getSource(), binding.getSourcePath());
            }
            try {
                return new BigDecimal(sourceValue.toString()).stripTrailingZeros().toPlainString();
            } catch (NumberFormatException exception) {
                throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                        adapter, binding.getSource(), binding.getSourcePath(), exception);
            }
        }
        if (transform.getType() == A2uiResultTransformType.PAGINATION_STATE) {
            return paginationState(adapter, binding, sourceValue, roots);
        }
        if (transform.getType() == A2uiResultTransformType.ARRAY_TO_CHILDREN_PREFIX) {
            return childrenPrefixValue(adapter, binding, sourceValue, transform);
        }
        if (transform.getType() == A2uiResultTransformType.BOOLEAN_ARRAY_TRUE_COUNT) {
            return booleanArrayTrueCountValue(adapter, binding, sourceValue, transform);
        }
        if (transform.getType() != A2uiResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING
                || !isIntegralScaleTwo(transform.getScale())
                || transform.getComponentIds() != null) {
            throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath());
        }
        if (!(sourceValue instanceof Number)) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath());
        }
        try {
            BigDecimal minorUnits = new BigDecimal(sourceValue.toString());
            if (minorUnits.stripTrailingZeros().scale() > 0) {
                throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                        adapter, binding.getSource(), binding.getSourcePath());
            }
            return minorUnits.movePointLeft(MINOR_UNIT_DECIMAL_SCALE)
                    .setScale(MINOR_UNIT_DECIMAL_SCALE)
                    .toPlainString();
        } catch (NumberFormatException | ArithmeticException exception) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath(), exception);
        }
    }

    /** 成功结果统一派生分页状态；非法总数或越界页失败关闭，保留原页避免误报加载成功。 */
    private Map<String, Object> paginationState(A2uiCompiledResultAdapter adapter,
            A2uiCompiledMessageTemplateBinding binding, Object sourceValue, ResultRoots roots) {
        A2uiCompiledResultTransform transform = binding.getTransform();
        try {
            Object requestedPage = transform.getPageNumber();
            if (transform.getActionPagePath() != null) {
                LookupValue page = valueMapper.read(roots.getActionContext(), transform.getActionPagePath());
                requestedPage = page.isFound() ? page.getValue() : null;
            }
            if (!(sourceValue instanceof Number) || !(requestedPage instanceof Number)) {
                throw new IllegalArgumentException(ERROR_PAGING_NUMBER);
            }
            long total = new BigDecimal(sourceValue.toString()).longValueExact();
            int size = new BigDecimal(transform.getPageSize().toString()).intValueExact();
            int page = new BigDecimal(requestedPage.toString()).intValueExact();
            if (total < 0 || total > MAX_SAFE_JSON_INTEGER || size <= 0 || page <= 0) {
                throw new IllegalArgumentException(ERROR_PAGING_RANGE);
            }
            long pages = total / size + (total % size == 0 ? 0 : 1);
            if (total > 0 && page > pages) {
                throw new IllegalArgumentException(ERROR_PAGING_OVERFLOW);
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put(PAGE_TOTAL, total);
            result.put(PAGE_PAGE_SIZE, size);
            result.put(PAGE_PAGE_NUM, total == 0 ? 0 : page);
            result.put(PAGE_TOTAL_PAGES, pages);
            result.put(PAGE_PREV_PAGE, Math.max(1, page - 1));
            result.put(PAGE_NEXT_PAGE, total == 0 ? 1 : Math.min(pages, (long) page + 1));
            result.put(PAGE_PREV_DISABLED, total == 0 || page == 1);
            result.put(PAGE_NEXT_DISABLED, total == 0 || page >= pages);
            // Text 协议使用字符串；这里只提供中性数字值，文案、单位和布局由应用编排决定。
            result.put(PAGE_DISPLAY, Map.of(
                    PAGE_PAGE_NUM, String.valueOf(total == 0 ? 0 : page),
                    PAGE_TOTAL_PAGES, String.valueOf(pages),
                    PAGE_TOTAL, String.valueOf(total)));
            return result;
        } catch (IllegalArgumentException | ArithmeticException exception) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath(), exception);
        }
    }

    /** 布尔数组只统计严格等于 true 的元素；配置或元素类型不合法时失败关闭。 */
    private Object booleanArrayTrueCountValue(A2uiCompiledResultAdapter adapter,
            A2uiCompiledMessageTemplateBinding binding, Object sourceValue, A2uiCompiledResultTransform transform) {
        if (transform.getScale() != null || transform.getComponentIds() != null) {
            throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath());
        }
        if (!(sourceValue instanceof List)) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath());
        }
        int trueCount = 0;
        for (Object value : (List<?>) sourceValue) {
            if (!(value instanceof Boolean)) {
                throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                        adapter, binding.getSource(), binding.getSourcePath());
            }
            if (Boolean.TRUE.equals(value)) {
                trueCount++;
            }
        }
        return trueCount;
    }

    /** 数组只贡献数量，输出始终来自 Build 冻结的组件 ID 前缀。 */
    private Object childrenPrefixValue(A2uiCompiledResultAdapter adapter, A2uiCompiledMessageTemplateBinding binding,
            Object sourceValue, A2uiCompiledResultTransform transform) {
        if (transform.getScale() != null
                || !validChildComponentIds(transform.getComponentIds())
                || !validChildrenTargetPath(binding.getTargetPath())) {
            throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath());
        }
        if (!(sourceValue instanceof List)) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath());
        }
        int resultSize = Math.min(((List<?>) sourceValue).size(), transform.getComponentIds().size());
        return new ArrayList<>(transform.getComponentIds().subList(0, resultSize));
    }

    private boolean validChildComponentIds(List<String> componentIds) {
        if (componentIds == null || componentIds.isEmpty()
                || componentIds.size() > MAX_CHILD_COMPONENT_IDS) {
            return false;
        }
        return componentIds.stream().allMatch(StringUtils::isNotBlank)
                && componentIds.stream().distinct().count() == componentIds.size();
    }

    private boolean validChildrenTargetPath(String targetPath) {
        if (targetPath == null) {
            return false;
        }
        String[] segments = targetPath.split("/", -1);
        if (segments.length != 5
                || !segments[0].isEmpty()
                || !UPDATE_COMPONENTS_PATH_SEGMENT.equals(segments[1])
                || !COMPONENTS_PATH_SEGMENT.equals(segments[2])
                || !CHILDREN_PATH_SEGMENT.equals(segments[4])) {
            return false;
        }
        String indexSegment = segments[3];
        if (indexSegment.length() > 1 && indexSegment.charAt(0) == '0') {
            return false;
        }
        try {
            return Integer.parseInt(indexSegment) >= 0;
        } catch (NumberFormatException ignored) {
            return false;
        }
    }

    private boolean isIntegralScaleTwo(Object scale) {
        return (scale instanceof Byte || scale instanceof Short
                || scale instanceof Integer || scale instanceof Long
                || scale instanceof BigInteger)
                && new BigInteger(scale.toString()).equals(
                BigInteger.valueOf(MINOR_UNIT_DECIMAL_SCALE));
    }

    private LookupValue resolveTemplateSource(A2uiCompiledResultAdapter adapter,
            A2uiCompiledMessageTemplateBinding binding, ResultRoots roots) {
        try {
            if (A2uiResultSource.CONSTANT == binding.getSource()) {
                Map<String, Object> constantSource = new LinkedHashMap<>();
                constantSource.put(CONSTANT_VALUE_FIELD, binding.getConstantValue());
                return valueMapper.read(constantSource, CONSTANT_VALUE_PATH);
            }
            if (StringUtils.isBlank(binding.getSourcePath())) {
                throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                        adapter, binding.getSource(), binding.getSourcePath());
            }
            return valueMapper.read(sourceRoot(binding.getSource(), roots),
                    binding.getSourcePath());
        } catch (A2uiJsonPointerValueMapper.MappingException exception) {
            throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                    adapter, binding.getSource(), binding.getSourcePath(), exception);
        }
    }

    private List<A2uiProtocolMessage> readPassthrough(A2uiCompiledResultAdapter adapter,
            ResultRoots roots) {
        if (StringUtils.isBlank(adapter.getSourcePath())
                || !StringUtils.equalsAny(adapter.getCardinality(),
                CARDINALITY_ONE, CARDINALITY_MANY)
                || !EnumSet.of(A2uiResultSource.CAPABILITY_DATA,
                A2uiResultSource.CAPABILITY_META).contains(adapter.getSource())) {
            throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                    adapter, adapter.getSource(), adapter.getSourcePath());
        }
        LookupValue sourceValue;
        try {
            sourceValue = valueMapper.read(sourceRoot(adapter.getSource(), roots),
                    adapter.getSourcePath());
        } catch (A2uiJsonPointerValueMapper.MappingException exception) {
            throw adapterFailure(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID,
                    adapter, adapter.getSource(), adapter.getSourcePath(), exception);
        }
        if (!sourceValue.isFound() || sourceValue.getValue() == null) {
            if (adapter.isRequired()) {
                throw adapterFailure(Code.SOURCE_MISSING, ERROR_SOURCE_MISSING,
                        adapter, adapter.getSource(), adapter.getSourcePath());
            }
            return Collections.emptyList();
        }
        if (CARDINALITY_ONE.equals(adapter.getCardinality())) {
            return Collections.singletonList(copyMessage(adapter, sourceValue.getValue()));
        }
        if (!(sourceValue.getValue() instanceof List)) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, adapter.getSource(), adapter.getSourcePath());
        }
        List<A2uiProtocolMessage> messages = new ArrayList<>();
        for (Object value : (List<?>) sourceValue.getValue()) {
            messages.add(copyMessage(adapter, value));
        }
        return messages;
    }

    private Object sourceRoot(A2uiResultSource source, ResultRoots roots) {
        if (A2uiResultSource.CAPABILITY_DATA == source) {
            return roots.capabilityData;
        }
        if (A2uiResultSource.CAPABILITY_META == source) {
            return roots.capabilityMeta;
        }
        if (A2uiResultSource.TRUSTED_CONTEXT == source) {
            return roots.trustedContext;
        }
        if (A2uiResultSource.ACTION_CONTEXT == source) {
            return roots.actionContext;
        }
        throw new AdapterException(Code.ADAPTER_INVALID, ERROR_ADAPTER_INVALID);
    }

    private A2uiProtocolMessage copyMessage(A2uiCompiledResultAdapter adapter, Object value) {
        if (!(value instanceof Map)) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, adapter.getSource(), adapter.getSourcePath());
        }
        Object copied = valueMapper.write(new LinkedHashMap<>(), ROOT_PATH, value);
        if (!(copied instanceof Map)) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, adapter.getSource(), adapter.getSourcePath());
        }
        return parseMessage(adapter, castMap(copied));
    }

    private A2uiProtocolMessage parseMessage(A2uiCompiledResultAdapter adapter,
            Map<String, Object> message) {
        try {
            return A2uiProtocolMessage.fromMap(message);
        } catch (IllegalArgumentException exception) {
            throw adapterFailure(Code.RESULT_INVALID, ERROR_RESULT_INVALID,
                    adapter, adapter.getSource(), adapter.getSourcePath(), exception);
        }
    }

    private AdapterException adapterFailure(Code code, String message, A2uiCompiledResultAdapter adapter,
            A2uiResultSource source, String sourcePath) {
        return adapterFailure(code, message, adapter, source, sourcePath, null);
    }

    private AdapterException adapterFailure(Code code, String message, A2uiCompiledResultAdapter adapter,
            A2uiResultSource source, String sourcePath, Throwable cause) {
        return new AdapterException(code, message,
                adapter == null ? null : adapter.getAdapterId(), source, sourcePath, cause);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Object value) {
        return (Map<String, Object>) value;
    }

    public enum Code {
        REQUEST_INVALID,
        ADAPTER_INVALID,
        SOURCE_MISSING,
        RESULT_INVALID
    }

    /** Adapter 失败只携带稳定错误分类，不携带 CapabilityResult 或 Message 正文。 */
    public static class AdapterException extends RuntimeException {
        private final Code code;
        private final String adapterId;
        private final A2uiResultSource resultSource;
        private final String sourcePath;

        AdapterException(Code code, String message) {
            this(code, message, null, null, null, null);
        }

        AdapterException(Code code, String message, Throwable cause) {
            this(code, message, null, null, null, cause);
        }

        AdapterException(Code code, String message, String adapterId,
                A2uiResultSource resultSource, String sourcePath, Throwable cause) {
            super(message, cause);
            this.code = code;
            this.adapterId = adapterId;
            this.resultSource = resultSource;
            this.sourcePath = sourcePath;
        }

        public Code getCode() {
            return code;
        }

        public String getAdapterId() {
            return adapterId;
        }

        public A2uiResultSource getResultSource() {
            return resultSource;
        }

        public String getSourcePath() {
            return sourcePath;
        }
    }

    /** 单次适配固定的数据根；Action 输入仍是非权威业务值，不与 Tool 可信上下文互相回退。 */
    @Value
    private static class ResultRoots {
        private Object capabilityData;
        private Map<String, Object> capabilityMeta;
        private Map<String, Object> trustedContext;
        private Map<String, Object> actionContext;
    }

    /** 完整候选消息与 reducer 计算出的新 ledger；二者只能由上层一次性提交。 */
    @Value
    public static class AdaptedBatch {
        private List<A2uiProtocolMessage> messages;
        private A2uiRuntimeSurfaceLedger nextLedger;

        /** 仅供Snapshot、SSE与既有动态A2UI协议消费者使用。 */
        public List<Map<String, Object>> toWireMessages() {
            return A2uiProtocolMessage.toMaps(messages);
        }
    }
}
