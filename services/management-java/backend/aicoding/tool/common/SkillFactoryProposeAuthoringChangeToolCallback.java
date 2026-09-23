package dev.a2flow.management.aicoding.tool.common;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadCodec;
import dev.a2flow.management.lifecycle.AuthoringDraftChangeService;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 结构化 Authoring 草稿修改 Tool。
 *
 * <p>模型只提供完整 draft 或 RFC 6902 风格 operations；`authoringDomain`、`draftId`、`revision`
 * 和当前草稿从可信 ToolContext 注入，模型不能覆盖。下游返回标准 runtime payload 供前端受控表单
 * 展示和人工应用，本 Tool 不保存草稿、不修改 Skill workspace，也不执行外部业务接口。
 */
@Component
@Slf4j
public class SkillFactoryProposeAuthoringChangeToolCallback implements ToolCallback {

    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String ERROR_TOOL_CONTEXT_MISSING = "toolContext not exists";
    private static final String ERROR_AGENT_CONTEXT_MISSING = "agentContext not exists";
    private static final String ERROR_TOOL_INPUT_INVALID = "toolInput 必须是合法 JSON 对象";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "changeType": {
                  "type": "string",
                  "enum": ["SNAPSHOT", "PATCH"],
                  "description": "首次完整生成使用 SNAPSHOT；基于当前表单修改使用 PATCH"
                },
                "draft": {
                  "type": "object",
                  "description": "SNAPSHOT 完整 canonical 草稿；basicInfo/governance 保持根级，技术契约只写入 supportedClients 对应的 clientVariants.PC/APP/COMMON",
                  "properties": {
                    "supportedClients": {
                      "type": "array",
                      "minItems": 1,
                      "maxItems": 2,
                      "uniqueItems": true,
                      "items": {"type": "string", "enum": ["PC", "APP", "COMMON"]},
                      "enum": [["PC"], ["APP"], ["PC", "APP"], ["COMMON"]],
                      "description": "四种互斥模式只能精确写为 [PC]、[APP]、[PC,APP] 或 [COMMON]；clientVariants key 必须与本数组完全一致"
                    },
                    "clientVariants": {
                      "type": "object",
                      "minProperties": 1,
                      "maxProperties": 2,
                      "propertyNames": {"enum": ["PC", "APP", "COMMON"]},
                      "description": "PC/APP/COMMON 独立完整技术契约；COMMON 与 PC/APP 互斥，禁止复制、继承或回退另一端配置",
                      "additionalProperties": {
                        "type": "object",
                        "properties": {
                          "modelContract": {
                            "type": "object",
                            "description": "当前端模型可见的业务参数契约",
                            "properties": {
                        "description": {"type": "string", "description": "能力何时调用及其业务用途"},
                        "inputFields": {
                          "type": "array",
                          "description": "入参字段；MODEL_INPUT 的闭集枚举必须使用 allowedValues",
                          "items": {
                            "type": "object",
                            "properties": {
                              "toolField": {"type": "string", "description": "英文 JSON 字段名"},
                              "type": {"type": "string", "enum": ["string", "number", "boolean", "array"]},
                              "items": {
                                "type": "object",
                                "description": "array 必填的递归 Schema；支持标量、object properties/required 与嵌套 array items",
                                "properties": {
                                  "type": {
                                    "type": "string",
                                    "enum": ["string", "number", "boolean", "object", "array"]
                                  },
                                  "description": {"type": "string"},
                                  "properties": {
                                    "type": "object",
                                    "description": "object 元素的字段名到子 Schema；每个子 Schema 使用相同的 type/items/properties/required 结构",
                                    "additionalProperties": {"type": "object"}
                                  },
                                  "required": {"type": "array", "items": {"type": "string"}},
                                  "items": {
                                    "type": "object",
                                    "description": "嵌套 array 的元素 Schema，继续使用相同结构"
                                  }
                                },
                                "required": ["type"]
                              },
                              "businessMeaning": {
                                "type": "string",
                                "description": "字段的业务语义，不在这里罗列枚举值"
                              },
                              "unit": {
                                "type": "string",
                                "description": "可选单位或格式说明，不承载枚举值且不参与执行"
                              },
                              "examples": {
                                "type": "string",
                                "description": "可选的单个示例字符串；不能填写枚举数组或枚举全集"
                              },
                              "allowedValues": {
                                "type": "array",
                                "description": "仅 string/number MODEL_INPUT 可选的闭集枚举；枚举只能写入 allowedValues，不能复制到 businessMeaning、unit 或 examples",
                                "items": {
                                  "type": "object",
                                  "properties": {
                                    "value": {
                                      "oneOf": [{"type": "string"}, {"type": "number"}],
                                      "description": "真实传给下游的枚举值，类型必须与字段 type 一致"
                                    },
                                    "label": {"type": "string", "description": "必填的中文含义"},
                                    "description": {"type": "string", "description": "可选的使用说明"}
                                  },
                                  "required": ["value", "label"]
                                }
                              },
                              "required": {"type": "boolean"},
                              "source": {
                                "type": "string",
                                "enum": ["MODEL_INPUT", "CONSTANT", "SYSTEM_VARIABLE"]
                              },
                              "constantValue": {
                                "oneOf": [
                                  {"type": "string"}, {"type": "number"},
                                  {"type": "boolean"}, {"type": "array"}
                                ],
                                "description": "仅 CONSTANT 使用，类型与字段 type 一致；boolean/array 必须是真实 JSON 值"
                              },
                              "systemVariable": {
                                "type": "string",
                                "enum": ["userId", "client"],
                                "description": "仅 SYSTEM_VARIABLE 使用"
                              },
                              "valueMapping": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                                "description": "仅 client 系统变量可配置的严格字符串映射"
                              }
                            },
                            "required": ["toolField", "type", "businessMeaning", "source"]
                          }
                        },
                              "inputExampleJson": {
                                "type": "string",
                                "description": "完整的 JSON 对象字符串；枚举字段示例值必须命中 allowedValues"
                              }
                            }
                          }
                        }
                      }
                    }
                  },
                  "required": ["supportedClients", "clientVariants"]
                },
                "operations": {
                  "type": "array",
                  "description": "PATCH 时必填的 RFC 6902 风格增量；端内技术字段必须修改 /clientVariants/{PC|APP|COMMON}/...",
                  "items": {
                    "type": "object",
                    "properties": {
                      "op": {"type": "string", "enum": ["add", "replace", "remove"]},
                      "path": {
                        "type": "string",
                        "description": "能力草稿内的 JSON Pointer；枚举路径使用 /clientVariants/{PC|APP|COMMON}/modelContract/inputFields/{index}/allowedValues"
                      },
                      "value": {
                        "description": "add/replace 的目标值；allowedValues 必须是 [{value,label,description?}]，examples 必须是单个字符串"
                      }
                    },
                    "required": ["op", "path"]
                  }
                },
                "summary": {"type": "string", "description": "给操作者看的本次修改摘要"},
                "reviewDelta": {
                  "type": "array",
                  "items": {"type": "string"},
                  "description": "仍需产品或研发人工确认的问题"
                }
              },
              "required": ["changeType"]
            }
            """;

    @Resource
    private AuthoringDraftChangeService authoringDraftChangeService;

    @Resource
    private AiCodingEventPayloadCodec aiCodingEventPayloadCodec;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(AuthoringDraftChangeService.TOOL_PROPOSE_AUTHORING_CHANGE)
                .description("Generate a reviewable structured authoring draft snapshot or patch. "
                        + "Use this instead of propose_patch for Capability Center forms. "
                        + "Keep common fields at root and write technical contracts only under exact "
                        + "supportedClients plus clientVariants.PC/APP/COMMON; never write root technical sections. "
                        + "Use boolean as JSON true/false and array with recursive items/properties; "
                        + "for string/number MODEL_INPUT enums, write structured allowedValues only; never copy enum options "
                        + "into businessMeaning、unit 或 examples. examples is one string example. "
                        + "The backend injects draftId and revision and does not persist until the operator saves.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 执行模型的结构化草稿提案并返回标准 payload JSON。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        Map<String, String> context = buildContext(agentContext);
        try {
            Map<String, Object> input = parseInput(toolInput);
            log.info("Authoring草稿修改Tool开始执行, authoringDomain={}, draftId={}, revision={}, sessionId={}",
                    context.get(FIELD_AUTHORING_DOMAIN), context.get(FIELD_DRAFT_ID), context.get(FIELD_REVISION),
                    context.get(FIELD_SESSION_ID));
            AiCodingEventPayload payload = authoringDraftChangeService.propose(context, input);
            return aiCodingEventPayloadCodec.toJson(payload);
        } catch (IllegalArgumentException e) {
            log.warn("Authoring草稿修改Tool参数校验失败, authoringDomain={}, draftId={}, revision={}, traceId={}, "
                            + "error={}",
                    context.get(FIELD_AUTHORING_DOMAIN), context.get(FIELD_DRAFT_ID), context.get(FIELD_REVISION),
                    context.get(FIELD_TRACE_ID), e.getMessage());
            throw new ToolException(e.getMessage(), e, ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseInput(String toolInput) {
        try {
            Map<String, Object> input = JsonSupport.fromJson(toolInput);
            if (input == null) {
                throw new IllegalArgumentException(ERROR_TOOL_INPUT_INVALID);
            }
            return input;
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException(ERROR_TOOL_INPUT_INVALID, e);
        }
    }

    private BaseAgentContext requireAgentContext(ToolContext toolContext) {
        if (Objects.isNull(toolContext)) {
            throw new ToolException(ERROR_TOOL_CONTEXT_MISSING, ToolException.ErrorCode.PERMISSION_DENIED);
        }
        BaseAgentContext agentContext = (BaseAgentContext) toolContext.getContext().get(FIELD_AGENT_CONTEXT);
        if (Objects.isNull(agentContext)) {
            throw new ToolException(ERROR_AGENT_CONTEXT_MISSING, ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return agentContext;
    }

    private Map<String, String> buildContext(BaseAgentContext agentContext) {
        Map<String, Object> extraBizParam = agentContext.getExtraBizParam() == null
                                            ? Collections.emptyMap() : agentContext.getExtraBizParam();
        Map<String, String> context = new LinkedHashMap<>();
        putString(context, extraBizParam, FIELD_AUTHORING_DOMAIN);
        putString(context, extraBizParam, FIELD_DRAFT_ID);
        putString(context, extraBizParam, FIELD_REVISION);
        putJson(context, extraBizParam, FIELD_CURRENT_DRAFT);
        putString(context, extraBizParam, FIELD_WORKSPACE_ID);
        putString(context, extraBizParam, FIELD_SESSION_ID);
        putString(context, extraBizParam, FIELD_MESSAGE_ID);
        putString(context, extraBizParam, FIELD_RUN_ID);
        putString(context, extraBizParam, FIELD_CONVERSATION_ID);
        putString(context, extraBizParam, FIELD_TRACE_ID);
        return context;
    }

    private void putString(Map<String, String> target, Map<String, Object> source, String field) {
        String value = MapUtils.getString(source, field);
        if (StringUtils.isNotBlank(value)) {
            target.put(field, value);
        }
    }

    private void putJson(Map<String, String> target, Map<String, Object> source, String field) {
        Object value = source.get(field);
        if (value == null) {
            return;
        }
        target.put(field, value instanceof String ? String.valueOf(value) : JsonSupport.toJSON(value));
    }
}
