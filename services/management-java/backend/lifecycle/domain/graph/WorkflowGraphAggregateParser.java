package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import dev.a2flow.management.support.JsonSupport;

/**
 * Workflow 聚合草稿 JSON 解析器与序列化工具（纯工具类，无 Spring 注解）。
 */
public final class WorkflowGraphAggregateParser {

    public static final String ERROR_CODE_JSON_SYNTAX_INVALID = "WORKFLOW_GRAPH_JSON_SYNTAX_INVALID";
    public static final String ERROR_CODE_UNKNOWN_FIELD = "WORKFLOW_GRAPH_UNKNOWN_FIELD";
    public static final String ERROR_CODE_FIELD_TYPE_INVALID = "WORKFLOW_GRAPH_FIELD_TYPE_INVALID";
    public static final String ERROR_CODE_REQUIRED_FIELD_MISSING = "WORKFLOW_GRAPH_REQUIRED_FIELD_MISSING";
    public static final String ERROR_CODE_DOMAIN_DATA_INVALID = "WORKFLOW_GRAPH_DOMAIN_DATA_INVALID";

    public static final int SNAPSHOT_CONTRACT_VERSION_V2 = 2;
    private static final int QUICK_TRIGGER_MESSAGE_MAX_LENGTH = 4096;
    private static final int DETAIL_SUMMARY_PROMPT_MAX_LENGTH = 4096;
    private static final int SUMMARY_HANDLING_SUGGESTION_MAX_COUNT = 10;
    private static final int SUMMARY_HANDLING_SUGGESTION_TEXT_MAX_LENGTH = 4096;
    private static final int ROUTER_SUPPORTED_CONTRACT_VERSION = 1;
    private static final int ROUTER_MIN_CANDIDATES = 2;
    private static final int FORK_MIN_MAX_PARALLELISM = 2;
    private static final String SUMMARY_NODE_CODE = "__summary__";
    private static final String JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED = "ALL_SUCCESS_OR_SKIPPED";

    private static final String ROOT_FIELD_PATH = "$";
    private static final String FIELD_SNAPSHOT_CONTRACT_VERSION = "snapshotContractVersion";
    private static final String FIELD_WORKFLOW_CODE = "workflowCode";
    private static final String FIELD_METADATA = "metadata";
    private static final String FIELD_NODES = "nodes";
    private static final String FIELD_EDGES = "edges";
    private static final String FIELD_SUMMARY_CONFIG = "summaryConfig";
    private static final String FIELD_PROMPT = "prompt";
    private static final String FIELD_DETAIL_SUMMARY_PROMPT = "detailSummaryPrompt";
    private static final String FIELD_HANDLING_SUGGESTIONS = "handlingSuggestions";
    private static final String FIELD_SUGGESTION_ID = "suggestionId";
    private static final String FIELD_ICON_URL = "iconUrl";
    private static final String FIELD_DISPLAY_TEXT = "displayText";
    private static final String FIELD_SEND_MESSAGE_TEXT = "sendMessageText";

    private static final String NODE_FIELD_NODE_CODE = "nodeCode";
    private static final String NODE_FIELD_NODE_TYPE = "nodeType";
    private static final String NODE_FIELD_DISPLAY_NAME = "displayName";
    private static final String NODE_FIELD_SKILL_CODE = "skillCode";
    private static final String NODE_FIELD_NODE_PROMPT = "nodePrompt";
    private static final String NODE_FIELD_QUICK_TRIGGER_MESSAGE = "quickTriggerMessage";
    private static final String NODE_FIELD_CONTROL_POLICY = "controlPolicy";
    private static final String NODE_FIELD_ALLOW_SKIP = "allowSkip";
    private static final String NODE_FIELD_ROUTER_PROMPT = "routerPrompt";
    private static final String NODE_FIELD_ROUTER_CONTRACT_VERSION = "routerContractVersion";
    private static final String NODE_FIELD_ROUTER_SCHEMA_DIGEST = "routerSchemaDigest";
    private static final String NODE_FIELD_CANDIDATES = "candidates";
    private static final String NODE_FIELD_ROUTE_KEY = "routeKey";
    private static final String NODE_FIELD_DESCRIPTION = "description";
    private static final String NODE_FIELD_TARGET_NODE_CODE = "targetNodeCode";
    private static final String NODE_FIELD_MATCHING_NODE_CODE = "matchingNodeCode";
    private static final String NODE_FIELD_JOIN_POLICY = "joinPolicy";
    private static final String NODE_FIELD_MAX_PARALLELISM = "maxParallelism";

    private static final String EDGE_FIELD_EDGE_ID = "edgeId";
    private static final String EDGE_FIELD_SOURCE_NODE_CODE = "sourceNodeCode";
    private static final String EDGE_FIELD_TARGET_NODE_CODE = "targetNodeCode";
    private static final String EDGE_FIELD_EDGE_TYPE = "edgeType";
    private static final String EDGE_FIELD_ROUTE_KEY = "routeKey";
    private static final String EDGE_FIELD_DESCRIPTION = "description";
    private static final String EDGE_FIELD_BRANCH_KEY = "branchKey";
    private static final String EDGE_FIELD_BRANCH_ORDER = "branchOrder";

    private static final Set<String> ROOT_V2_FIELDS = new HashSet<>(Arrays.asList(
            FIELD_SNAPSHOT_CONTRACT_VERSION, FIELD_WORKFLOW_CODE, FIELD_METADATA,
            FIELD_NODES, FIELD_EDGES, FIELD_SUMMARY_CONFIG));
    private static final Set<String> SKILL_NODE_FIELDS = new HashSet<>(Arrays.asList(
            NODE_FIELD_NODE_CODE, NODE_FIELD_NODE_TYPE, NODE_FIELD_DISPLAY_NAME, NODE_FIELD_SKILL_CODE,
            NODE_FIELD_NODE_PROMPT, NODE_FIELD_CONTROL_POLICY, NODE_FIELD_QUICK_TRIGGER_MESSAGE));
    private static final Set<String> ROUTER_NODE_FIELDS = new HashSet<>(Arrays.asList(
            NODE_FIELD_NODE_CODE, NODE_FIELD_NODE_TYPE, NODE_FIELD_DISPLAY_NAME, NODE_FIELD_ROUTER_PROMPT,
            NODE_FIELD_ROUTER_CONTRACT_VERSION, NODE_FIELD_ROUTER_SCHEMA_DIGEST,
            NODE_FIELD_CANDIDATES));
    private static final Set<String> FORK_NODE_FIELDS = new HashSet<>(Arrays.asList(
            NODE_FIELD_NODE_CODE, NODE_FIELD_NODE_TYPE, NODE_FIELD_DISPLAY_NAME, NODE_FIELD_MATCHING_NODE_CODE,
            NODE_FIELD_JOIN_POLICY, NODE_FIELD_MAX_PARALLELISM));
    private static final Set<String> JOIN_NODE_FIELDS = new HashSet<>(Arrays.asList(
            NODE_FIELD_NODE_CODE, NODE_FIELD_NODE_TYPE, NODE_FIELD_DISPLAY_NAME, NODE_FIELD_MATCHING_NODE_CODE,
            NODE_FIELD_JOIN_POLICY));
    private static final Set<String> SUMMARY_NODE_FIELDS = new HashSet<>(Arrays.asList(
            NODE_FIELD_NODE_CODE, NODE_FIELD_NODE_TYPE, NODE_FIELD_DISPLAY_NAME, FIELD_PROMPT, NODE_FIELD_ALLOW_SKIP));
    private static final Set<String> NORMAL_EDGE_FIELDS = new HashSet<>(Arrays.asList(
            EDGE_FIELD_EDGE_ID, EDGE_FIELD_SOURCE_NODE_CODE, EDGE_FIELD_TARGET_NODE_CODE,
            EDGE_FIELD_EDGE_TYPE));
    private static final Set<String> ROUTING_EDGE_FIELDS = new HashSet<>(Arrays.asList(
            EDGE_FIELD_EDGE_ID, EDGE_FIELD_SOURCE_NODE_CODE, EDGE_FIELD_TARGET_NODE_CODE,
            EDGE_FIELD_EDGE_TYPE, EDGE_FIELD_ROUTE_KEY, EDGE_FIELD_DESCRIPTION));
    private static final Set<String> PARALLEL_EDGE_FIELDS = new HashSet<>(Arrays.asList(
            EDGE_FIELD_EDGE_ID, EDGE_FIELD_SOURCE_NODE_CODE, EDGE_FIELD_TARGET_NODE_CODE,
            EDGE_FIELD_EDGE_TYPE, EDGE_FIELD_BRANCH_KEY, EDGE_FIELD_BRANCH_ORDER));
    private static final Set<String> SUMMARY_CONFIG_FIELDS = new HashSet<>(Arrays.asList(
            FIELD_PROMPT, FIELD_DETAIL_SUMMARY_PROMPT, FIELD_HANDLING_SUGGESTIONS));
    private static final Set<String> HANDLING_SUGGESTION_FIELDS = new HashSet<>(Arrays.asList(
            FIELD_SUGGESTION_ID, FIELD_ICON_URL, FIELD_DISPLAY_TEXT, FIELD_SEND_MESSAGE_TEXT));
    private static final Set<String> CONTROL_POLICY_FIELDS = new HashSet<>(Arrays.asList(NODE_FIELD_ALLOW_SKIP));
    private static final Set<String> CANDIDATE_FIELDS = new HashSet<>(Arrays.asList(
            NODE_FIELD_ROUTE_KEY, NODE_FIELD_DESCRIPTION, NODE_FIELD_TARGET_NODE_CODE));

    private WorkflowGraphAggregateParser() {
    }

    @SuppressWarnings("unchecked")
    public static WorkflowGraphAggregate parse(String draftPayloadJson) {
        if (draftPayloadJson == null || draftPayloadJson.trim().isEmpty()) {
            throw dataFailure(ERROR_CODE_JSON_SYNTAX_INVALID,
                    "Workflow聚合草稿JSON内容为空", ROOT_FIELD_PATH);
        }
        Map<String, Object> root;
        try {
            root = JsonSupport.mapper().readValue(draftPayloadJson, Map.class);
        } catch (UnrecognizedPropertyException exception) {
            throw dataFailure(ERROR_CODE_UNKNOWN_FIELD, "Workflow聚合草稿包含未知字段",
                    jacksonPath(exception), exception);
        } catch (JsonMappingException exception) {
            throw dataFailure(ERROR_CODE_FIELD_TYPE_INVALID, "Workflow聚合草稿字段类型错误",
                    jacksonPath(exception), exception);
        } catch (JsonProcessingException exception) {
            throw dataFailure(ERROR_CODE_JSON_SYNTAX_INVALID, "Workflow聚合草稿JSON语法错误",
                    ROOT_FIELD_PATH, exception);
        }
        if (root == null) {
            throw dataFailure(ERROR_CODE_JSON_SYNTAX_INVALID,
                    "Workflow聚合草稿必须是JSON对象", ROOT_FIELD_PATH);
        }

        requireNoUnknownFields(root, ROOT_V2_FIELDS, ROOT_FIELD_PATH);
        int contractVersion = requireInt(root, FIELD_SNAPSHOT_CONTRACT_VERSION,
                FIELD_SNAPSHOT_CONTRACT_VERSION);
        if (contractVersion != SNAPSHOT_CONTRACT_VERSION_V2) {
            throw domainFailure("snapshotContractVersion不支持当前版本", FIELD_SNAPSHOT_CONTRACT_VERSION);
        }
        String workflowCode = requireNonBlankString(root, FIELD_WORKFLOW_CODE, FIELD_WORKFLOW_CODE);

        Object metadataRaw = root.get(FIELD_METADATA);
        if (!root.containsKey(FIELD_METADATA) || metadataRaw == null) {
            throw requiredFailure("metadata字段缺失", FIELD_METADATA);
        }
        if (!(metadataRaw instanceof Map)) {
            throw typeFailure("metadata字段类型错误，期望Map", FIELD_METADATA);
        }
        Map<String, Object> metadata = (Map<String, Object>) metadataRaw;
        List<WorkflowNode> nodes = parseNodes(root);
        List<WorkflowEdge> edges = parseEdges(root);
        WorkflowSummaryConfig summaryConfig = parseSummaryConfig(root);
        WorkflowSummaryNode summaryNode = requireExactlyOneSummaryNode(nodes);
        if (!summaryConfig.getPrompt().equals(summaryNode.getPrompt())) {
            throw domainFailure("summaryConfig.prompt与SUMMARY节点prompt必须一致",
                    FIELD_SUMMARY_CONFIG + "." + FIELD_PROMPT);
        }

        return new WorkflowGraphAggregate()
                .setSnapshotContractVersion(contractVersion)
                .setWorkflowCode(workflowCode)
                .setMetadata(metadata)
                .setNodes(nodes)
                .setEdges(edges)
                .setSummaryConfig(summaryConfig);
    }

    public static String serialize(WorkflowGraphAggregate aggregate) {
        return JsonSupport.toJSON(aggregate);
    }

    @SuppressWarnings("unchecked")
    private static List<WorkflowNode> parseNodes(Map<String, Object> root) {
        Object nodesRaw = root.get(FIELD_NODES);
        if (nodesRaw == null) {
            throw requiredFailure("nodes字段缺失", FIELD_NODES);
        }
        if (!(nodesRaw instanceof List)) {
            throw typeFailure("nodes字段类型错误，期望List", FIELD_NODES);
        }
        List<Object> nodeList = (List<Object>) nodesRaw;
        List<WorkflowNode> result = new ArrayList<>(nodeList.size());
        for (int i = 0; i < nodeList.size(); i++) {
            String nodePath = FIELD_NODES + "[" + i + "]";
            Object item = nodeList.get(i);
            if (!(item instanceof Map)) {
                throw typeFailure(nodePath + "类型错误，期望JSON对象", nodePath);
            }
            result.add(parseNode((Map<String, Object>) item, nodePath));
        }
        return result;
    }

    private static WorkflowNode parseNode(Map<String, Object> nodeMap, String nodePath) {
        String nodeCode = requireNonBlankString(nodeMap, NODE_FIELD_NODE_CODE,
                childPath(nodePath, NODE_FIELD_NODE_CODE));
        String nodeTypeValue = requireNonBlankString(nodeMap, NODE_FIELD_NODE_TYPE,
                childPath(nodePath, NODE_FIELD_NODE_TYPE));
        String displayName = optionalString(nodeMap, NODE_FIELD_DISPLAY_NAME,
                childPath(nodePath, NODE_FIELD_DISPLAY_NAME));
        WorkflowNodeType nodeType = parseNodeType(nodeTypeValue, childPath(nodePath, NODE_FIELD_NODE_TYPE));
        validateQuickTriggerPlacement(nodeMap, nodeCode, nodeType);
        WorkflowNode node;
        switch (nodeType) {
            case SKILL:
                node = parseSkillNode(nodeMap, nodeCode, nodePath);
                break;
            case ROUTER:
                node = parseRouterNode(nodeMap, nodeCode, nodePath);
                break;
            case PARALLEL_FORK:
                node = parseForkNode(nodeMap, nodeCode, nodePath);
                break;
            case PARALLEL_JOIN:
                node = parseJoinNode(nodeMap, nodeCode, nodePath);
                break;
            case SUMMARY:
                node = parseSummaryNode(nodeMap, nodeCode, nodePath);
                break;
            default:
                throw domainFailure("未处理的节点类型", childPath(nodePath, NODE_FIELD_NODE_TYPE));
        }
        node.setDisplayName(displayName);
        return node;
    }

    @SuppressWarnings("unchecked")
    private static WorkflowSkillNode parseSkillNode(
            Map<String, Object> nodeMap, String nodeCode, String nodePath) {
        requireNoUnknownFields(nodeMap, SKILL_NODE_FIELDS, nodePath);
        String skillCode = requireNonBlankString(nodeMap, NODE_FIELD_SKILL_CODE,
                childPath(nodePath, NODE_FIELD_SKILL_CODE));
        String nodePrompt = requireNonBlankString(nodeMap, NODE_FIELD_NODE_PROMPT,
                childPath(nodePath, NODE_FIELD_NODE_PROMPT));
        String controlPolicyPath = childPath(nodePath, NODE_FIELD_CONTROL_POLICY);
        Object controlPolicyRaw = nodeMap.get(NODE_FIELD_CONTROL_POLICY);
        if (controlPolicyRaw == null) {
            throw requiredFailure("controlPolicy字段缺失", controlPolicyPath);
        }
        if (!(controlPolicyRaw instanceof Map)) {
            throw typeFailure("controlPolicy字段类型错误", controlPolicyPath);
        }
        Map<String, Object> controlPolicyMap = (Map<String, Object>) controlPolicyRaw;
        requireNoUnknownFields(controlPolicyMap, CONTROL_POLICY_FIELDS, controlPolicyPath);
        String allowSkipPath = childPath(controlPolicyPath, NODE_FIELD_ALLOW_SKIP);
        Object allowSkipRaw = controlPolicyMap.get(NODE_FIELD_ALLOW_SKIP);
        if (allowSkipRaw == null) {
            throw requiredFailure("allowSkip字段缺失", allowSkipPath);
        }
        if (!(allowSkipRaw instanceof Boolean)) {
            throw typeFailure("allowSkip字段类型错误", allowSkipPath);
        }
        WorkflowNodeControlPolicy controlPolicy = new WorkflowNodeControlPolicy()
                .setAllowSkip((Boolean) allowSkipRaw);
        WorkflowSkillNode node = new WorkflowSkillNode();
        node.setSkillCode(skillCode);
        node.setNodePrompt(nodePrompt);
        node.setControlPolicy(controlPolicy);
        node.setQuickTriggerMessage(optionalQuickTriggerMessage(nodeMap, nodeCode));
        node.setNodeCode(nodeCode);
        node.setNodeType(WorkflowNodeType.SKILL);
        return node;
    }

    /** quick trigger 是 graph v2 的通用 SKILL 展示字段，其他版本或节点类型一律失败关闭。 */
    private static void validateQuickTriggerPlacement(
            Map<String, Object> nodeMap, String nodeCode, WorkflowNodeType nodeType) {
        if (!nodeMap.containsKey(NODE_FIELD_QUICK_TRIGGER_MESSAGE)) {
            return;
        }
        String fieldPath = nodeFieldPath(nodeCode, NODE_FIELD_QUICK_TRIGGER_MESSAGE);
        if (nodeType != WorkflowNodeType.SKILL) {
            throw domainFailure("quickTriggerMessage仅允许出现在SKILL节点", fieldPath);
        }
    }

    private static String optionalQuickTriggerMessage(
            Map<String, Object> nodeMap, String nodeCode) {
        if (!nodeMap.containsKey(NODE_FIELD_QUICK_TRIGGER_MESSAGE)) {
            return null;
        }
        String fieldPath = nodeFieldPath(nodeCode, NODE_FIELD_QUICK_TRIGGER_MESSAGE);
        Object value = nodeMap.get(NODE_FIELD_QUICK_TRIGGER_MESSAGE);
        if (!(value instanceof String)) {
            throw typeFailure("quickTriggerMessage字段类型错误，期望String", fieldPath);
        }
        String normalized = ((String) value).trim();
        if (normalized.isEmpty()) {
            throw requiredFailure("quickTriggerMessage字段不能为空", fieldPath);
        }
        if (normalized.length() > QUICK_TRIGGER_MESSAGE_MAX_LENGTH) {
            throw domainFailure("quickTriggerMessage字段长度不能超过4096", fieldPath);
        }
        return normalized;
    }

    private static String nodeFieldPath(String nodeCode, String field) {
        return FIELD_NODES + "." + nodeCode + "." + field;
    }

    @SuppressWarnings("unchecked")
    private static WorkflowRouterNode parseRouterNode(
            Map<String, Object> nodeMap, String nodeCode, String nodePath) {
        requireNoUnknownFields(nodeMap, ROUTER_NODE_FIELDS, nodePath);
        String routerPrompt = requireNonBlankString(nodeMap, NODE_FIELD_ROUTER_PROMPT,
                childPath(nodePath, NODE_FIELD_ROUTER_PROMPT));
        String contractPath = childPath(nodePath, NODE_FIELD_ROUTER_CONTRACT_VERSION);
        int routerContractVersion = requireInt(nodeMap, NODE_FIELD_ROUTER_CONTRACT_VERSION, contractPath);
        if (routerContractVersion != ROUTER_SUPPORTED_CONTRACT_VERSION) {
            throw domainFailure("routerContractVersion仅支持1", contractPath);
        }
        String routerSchemaDigest = requireNonBlankString(nodeMap, NODE_FIELD_ROUTER_SCHEMA_DIGEST,
                childPath(nodePath, NODE_FIELD_ROUTER_SCHEMA_DIGEST));
        String candidatesPath = childPath(nodePath, NODE_FIELD_CANDIDATES);
        Object candidatesRaw = nodeMap.get(NODE_FIELD_CANDIDATES);
        if (candidatesRaw == null) {
            throw requiredFailure("candidates字段缺失", candidatesPath);
        }
        if (!(candidatesRaw instanceof List)) {
            throw typeFailure("candidates字段类型错误", candidatesPath);
        }
        List<Object> candidateList = (List<Object>) candidatesRaw;
        if (candidateList.size() < ROUTER_MIN_CANDIDATES) {
            throw domainFailure("Router节点candidates至少需要2条", candidatesPath);
        }
        List<WorkflowRouterCandidate> candidates = new ArrayList<>(candidateList.size());
        for (int i = 0; i < candidateList.size(); i++) {
            String candidatePath = candidatesPath + "[" + i + "]";
            Object candidateItem = candidateList.get(i);
            if (!(candidateItem instanceof Map)) {
                throw typeFailure("Router候选类型错误，期望JSON对象", candidatePath);
            }
            candidates.add(parseRouterCandidate((Map<String, Object>) candidateItem, candidatePath));
        }
        WorkflowRouterNode node = new WorkflowRouterNode();
        node.setRouterPrompt(routerPrompt);
        node.setRouterContractVersion(routerContractVersion);
        node.setRouterSchemaDigest(routerSchemaDigest);
        node.setCandidates(candidates);
        node.setNodeCode(nodeCode);
        node.setNodeType(WorkflowNodeType.ROUTER);
        return node;
    }

    private static WorkflowRouterCandidate parseRouterCandidate(
            Map<String, Object> candidateMap, String candidatePath) {
        requireNoUnknownFields(candidateMap, CANDIDATE_FIELDS, candidatePath);
        return new WorkflowRouterCandidate()
                .setRouteKey(requireNonBlankString(candidateMap, NODE_FIELD_ROUTE_KEY,
                        childPath(candidatePath, NODE_FIELD_ROUTE_KEY)))
                .setDescription(requireNonBlankString(candidateMap, NODE_FIELD_DESCRIPTION,
                        childPath(candidatePath, NODE_FIELD_DESCRIPTION)))
                .setTargetNodeCode(requireNonBlankString(candidateMap, NODE_FIELD_TARGET_NODE_CODE,
                        childPath(candidatePath, NODE_FIELD_TARGET_NODE_CODE)));
    }

    private static WorkflowForkNode parseForkNode(
            Map<String, Object> nodeMap, String nodeCode, String nodePath) {
        requireNoUnknownFields(nodeMap, FORK_NODE_FIELDS, nodePath);
        String matchingNodeCode = requireNonBlankString(nodeMap, NODE_FIELD_MATCHING_NODE_CODE,
                childPath(nodePath, NODE_FIELD_MATCHING_NODE_CODE));
        String joinPolicyPath = childPath(nodePath, NODE_FIELD_JOIN_POLICY);
        String joinPolicy = requireNonBlankString(nodeMap, NODE_FIELD_JOIN_POLICY, joinPolicyPath);
        if (!JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED.equals(joinPolicy)) {
            throw domainFailure("Fork节点joinPolicy不支持", joinPolicyPath);
        }
        String maxParallelismPath = childPath(nodePath, NODE_FIELD_MAX_PARALLELISM);
        int maxParallelism = requireInt(nodeMap, NODE_FIELD_MAX_PARALLELISM, maxParallelismPath);
        if (maxParallelism < FORK_MIN_MAX_PARALLELISM) {
            throw domainFailure("Fork节点maxParallelism必须大于等于2", maxParallelismPath);
        }
        WorkflowForkNode node = new WorkflowForkNode();
        node.setMatchingNodeCode(matchingNodeCode);
        node.setJoinPolicy(joinPolicy);
        node.setMaxParallelism(maxParallelism);
        node.setNodeCode(nodeCode);
        node.setNodeType(WorkflowNodeType.PARALLEL_FORK);
        return node;
    }

    private static WorkflowJoinNode parseJoinNode(
            Map<String, Object> nodeMap, String nodeCode, String nodePath) {
        requireNoUnknownFields(nodeMap, JOIN_NODE_FIELDS, nodePath);
        String matchingNodeCode = requireNonBlankString(nodeMap, NODE_FIELD_MATCHING_NODE_CODE,
                childPath(nodePath, NODE_FIELD_MATCHING_NODE_CODE));
        String joinPolicyPath = childPath(nodePath, NODE_FIELD_JOIN_POLICY);
        String joinPolicy = requireNonBlankString(nodeMap, NODE_FIELD_JOIN_POLICY, joinPolicyPath);
        if (!JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED.equals(joinPolicy)) {
            throw domainFailure("Join节点joinPolicy不支持", joinPolicyPath);
        }
        WorkflowJoinNode node = new WorkflowJoinNode();
        node.setMatchingNodeCode(matchingNodeCode);
        node.setJoinPolicy(joinPolicy);
        node.setNodeCode(nodeCode);
        node.setNodeType(WorkflowNodeType.PARALLEL_JOIN);
        return node;
    }

    private static WorkflowSummaryNode parseSummaryNode(
            Map<String, Object> nodeMap, String nodeCode, String nodePath) {
        requireNoUnknownFields(nodeMap, SUMMARY_NODE_FIELDS, nodePath);
        if (!SUMMARY_NODE_CODE.equals(nodeCode)) {
            throw domainFailure("Summary节点nodeCode必须为" + SUMMARY_NODE_CODE,
                    childPath(nodePath, NODE_FIELD_NODE_CODE));
        }
        String prompt = requireNonBlankString(nodeMap, FIELD_PROMPT, childPath(nodePath, FIELD_PROMPT));
        String allowSkipPath = childPath(nodePath, NODE_FIELD_ALLOW_SKIP);
        Object allowSkipRaw = nodeMap.get(NODE_FIELD_ALLOW_SKIP);
        if (allowSkipRaw == null) {
            throw requiredFailure("Summary节点allowSkip必须显式设置为false", allowSkipPath);
        }
        if (!(allowSkipRaw instanceof Boolean)) {
            throw typeFailure("Summary节点allowSkip字段类型错误", allowSkipPath);
        }
        if (Boolean.TRUE.equals(allowSkipRaw)) {
            throw domainFailure("Summary节点allowSkip固定为false", allowSkipPath);
        }
        WorkflowSummaryNode node = new WorkflowSummaryNode();
        node.setPrompt(prompt);
        node.setAllowSkip(false);
        node.setNodeCode(nodeCode);
        node.setNodeType(WorkflowNodeType.SUMMARY);
        return node;
    }

    private static WorkflowSummaryNode requireExactlyOneSummaryNode(List<WorkflowNode> nodes) {
        WorkflowSummaryNode found = null;
        for (WorkflowNode node : nodes) {
            if (node instanceof WorkflowSummaryNode) {
                if (found != null) {
                    throw domainFailure("Workflow必须恰好包含一个SUMMARY节点", FIELD_NODES);
                }
                found = (WorkflowSummaryNode) node;
            }
        }
        if (found == null) {
            throw domainFailure("Workflow必须恰好包含一个SUMMARY节点", FIELD_NODES);
        }
        return found;
    }

    @SuppressWarnings("unchecked")
    private static List<WorkflowEdge> parseEdges(Map<String, Object> root) {
        Object edgesRaw = root.get(FIELD_EDGES);
        if (edgesRaw == null) {
            throw requiredFailure("edges字段缺失", FIELD_EDGES);
        }
        if (!(edgesRaw instanceof List)) {
            throw typeFailure("edges字段类型错误，期望List", FIELD_EDGES);
        }
        List<Object> edgeList = (List<Object>) edgesRaw;
        List<WorkflowEdge> result = new ArrayList<>(edgeList.size());
        for (int i = 0; i < edgeList.size(); i++) {
            String edgePath = FIELD_EDGES + "[" + i + "]";
            Object item = edgeList.get(i);
            if (!(item instanceof Map)) {
                throw typeFailure(edgePath + "类型错误，期望JSON对象", edgePath);
            }
            result.add(parseEdge((Map<String, Object>) item, edgePath));
        }
        return result;
    }

    private static WorkflowEdge parseEdge(Map<String, Object> edgeMap, String edgePath) {
        String edgeId = requireNonBlankString(edgeMap, EDGE_FIELD_EDGE_ID,
                childPath(edgePath, EDGE_FIELD_EDGE_ID));
        String sourceNodeCode = requireNonBlankString(edgeMap, EDGE_FIELD_SOURCE_NODE_CODE,
                childPath(edgePath, EDGE_FIELD_SOURCE_NODE_CODE));
        String targetNodeCode = requireNonBlankString(edgeMap, EDGE_FIELD_TARGET_NODE_CODE,
                childPath(edgePath, EDGE_FIELD_TARGET_NODE_CODE));
        String edgeTypePath = childPath(edgePath, EDGE_FIELD_EDGE_TYPE);
        WorkflowEdgeType edgeType = parseEdgeType(
                requireNonBlankString(edgeMap, EDGE_FIELD_EDGE_TYPE, edgeTypePath), edgeTypePath);
        WorkflowEdge edge = new WorkflowEdge()
                .setEdgeId(edgeId)
                .setSourceNodeCode(sourceNodeCode)
                .setTargetNodeCode(targetNodeCode)
                .setEdgeType(edgeType);
        switch (edgeType) {
            case NORMAL:
                requireNoUnknownFields(edgeMap, NORMAL_EDGE_FIELDS, edgePath);
                break;
            case ROUTING:
                requireNoUnknownFields(edgeMap, ROUTING_EDGE_FIELDS, edgePath);
                edge.setRouteKey(requireNonBlankString(edgeMap, EDGE_FIELD_ROUTE_KEY,
                                childPath(edgePath, EDGE_FIELD_ROUTE_KEY)))
                        .setDescription(requireNonBlankString(edgeMap, EDGE_FIELD_DESCRIPTION,
                                childPath(edgePath, EDGE_FIELD_DESCRIPTION)));
                break;
            case PARALLEL:
                requireNoUnknownFields(edgeMap, PARALLEL_EDGE_FIELDS, edgePath);
                edge.setBranchKey(requireNonBlankString(edgeMap, EDGE_FIELD_BRANCH_KEY,
                                childPath(edgePath, EDGE_FIELD_BRANCH_KEY)))
                        .setBranchOrder(requireInt(edgeMap, EDGE_FIELD_BRANCH_ORDER,
                                childPath(edgePath, EDGE_FIELD_BRANCH_ORDER)));
                break;
            default:
                throw domainFailure("未处理的Edge类型", edgeTypePath);
        }
        return edge;
    }

    @SuppressWarnings("unchecked")
    private static WorkflowSummaryConfig parseSummaryConfig(Map<String, Object> root) {
        Object raw = root.get(FIELD_SUMMARY_CONFIG);
        if (raw == null) {
            throw requiredFailure("summaryConfig字段缺失", FIELD_SUMMARY_CONFIG);
        }
        if (!(raw instanceof Map)) {
            throw typeFailure("summaryConfig字段类型错误", FIELD_SUMMARY_CONFIG);
        }
        Map<String, Object> map = (Map<String, Object>) raw;
        requireNoUnknownFields(map, SUMMARY_CONFIG_FIELDS, FIELD_SUMMARY_CONFIG);
        return new WorkflowSummaryConfig()
                .setPrompt(requireNonBlankString(
                        map, FIELD_PROMPT, FIELD_SUMMARY_CONFIG + "." + FIELD_PROMPT).trim())
                .setDetailSummaryPrompt(parseDetailSummaryPrompt(map))
                .setHandlingSuggestions(parseHandlingSuggestions(map));
    }

    /** 严格解析可选详细总结提示词；字段存在时必须为非空字符串且长度不超过 4096。 */
    private static String parseDetailSummaryPrompt(Map<String, Object> summaryConfig) {
        if (!summaryConfig.containsKey(FIELD_DETAIL_SUMMARY_PROMPT)) {
            return null;
        }
        String fieldPath = FIELD_SUMMARY_CONFIG + "." + FIELD_DETAIL_SUMMARY_PROMPT;
        Object raw = summaryConfig.get(FIELD_DETAIL_SUMMARY_PROMPT);
        if (!(raw instanceof String)) {
            throw typeFailure("detailSummaryPrompt字段类型错误，期望String", fieldPath);
        }
        String normalized = ((String) raw).trim();
        if (normalized.isEmpty()) {
            throw requiredFailure("detailSummaryPrompt字段不能为空", fieldPath);
        }
        if (normalized.length() > DETAIL_SUMMARY_PROMPT_MAX_LENGTH) {
            throw domainFailure("detailSummaryPrompt字段长度不能超过4096", fieldPath);
        }
        return normalized;
    }

    /** 严格解析并归一化处理建议；缺失、类型错误、超限或重复 ID 均按稳定字段路径失败关闭。 */
    @SuppressWarnings("unchecked")
    private static List<WorkflowHandlingSuggestion> parseHandlingSuggestions(
            Map<String, Object> summaryConfig) {
        String suggestionsPath = FIELD_SUMMARY_CONFIG + "." + FIELD_HANDLING_SUGGESTIONS;
        Object raw = summaryConfig.get(FIELD_HANDLING_SUGGESTIONS);
        if (raw == null) {
            throw requiredFailure("handlingSuggestions字段缺失", suggestionsPath);
        }
        if (!(raw instanceof List)) {
            throw typeFailure("handlingSuggestions字段类型错误，期望List", suggestionsPath);
        }
        List<Object> items = (List<Object>) raw;
        if (items.size() > SUMMARY_HANDLING_SUGGESTION_MAX_COUNT) {
            throw domainFailure("handlingSuggestions不能超过10条", suggestionsPath);
        }
        List<WorkflowHandlingSuggestion> suggestions = new ArrayList<>(items.size());
        Set<String> suggestionIds = new HashSet<>();
        for (int index = 0; index < items.size(); index++) {
            String itemPath = suggestionsPath + "[" + index + "]";
            Object item = items.get(index);
            if (!(item instanceof Map)) {
                throw typeFailure("handlingSuggestion类型错误，期望JSON对象", itemPath);
            }
            Map<String, Object> itemMap = (Map<String, Object>) item;
            requireNoUnknownFields(itemMap, HANDLING_SUGGESTION_FIELDS, itemPath);
            String suggestionId = requireNonBlankString(
                    itemMap, FIELD_SUGGESTION_ID, childPath(itemPath, FIELD_SUGGESTION_ID)).trim();
            if (!suggestionIds.add(suggestionId)) {
                throw domainFailure("suggestionId不能重复",
                        childPath(itemPath, FIELD_SUGGESTION_ID));
            }
            String displayText = requireSummarySuggestionText(
                    itemMap, FIELD_DISPLAY_TEXT, itemPath);
            String sendMessageText = requireSummarySuggestionText(
                    itemMap, FIELD_SEND_MESSAGE_TEXT, itemPath);
            suggestions.add(new WorkflowHandlingSuggestion()
                    .setSuggestionId(suggestionId)
                    .setIconUrl(trimToNull(optionalString(
                            itemMap, FIELD_ICON_URL, childPath(itemPath, FIELD_ICON_URL))))
                    .setDisplayText(displayText)
                    .setSendMessageText(sendMessageText));
        }
        return suggestions;
    }

    private static String requireSummarySuggestionText(
            Map<String, Object> itemMap, String field, String itemPath) {
        String fieldPath = childPath(itemPath, field);
        String value = requireNonBlankString(itemMap, field, fieldPath).trim();
        if (value.length() > SUMMARY_HANDLING_SUGGESTION_TEXT_MAX_LENGTH) {
            throw domainFailure(field + "不能超过4096个字符", fieldPath);
        }
        return value;
    }

    private static String trimToNull(String value) {
        if (value == null || value.trim().isEmpty()) {
            return null;
        }
        return value.trim();
    }

    private static void requireNoUnknownFields(
            Map<String, Object> map, Set<String> allowedFields, String parentPath) {
        for (String key : map.keySet()) {
            if (!allowedFields.contains(key)) {
                String fieldPath = childPath(parentPath, key);
                throw dataFailure(ERROR_CODE_UNKNOWN_FIELD,
                        "v1协议包含未声明字段: " + fieldPath, fieldPath);
            }
        }
    }

    private static String requireNonBlankString(
            Map<String, Object> map, String field, String fieldPath) {
        Object value = map.get(field);
        if (value == null) {
            throw requiredFailure(field + "字段缺失", fieldPath);
        }
        if (!(value instanceof String)) {
            throw typeFailure(field + "字段类型错误，期望String", fieldPath);
        }
        if (((String) value).trim().isEmpty()) {
            throw requiredFailure(field + "字段不能为空", fieldPath);
        }
        return (String) value;
    }

    private static String optionalString(
            Map<String, Object> map, String field, String fieldPath) {
        Object value = map.get(field);
        if (value == null) {
            return null;
        }
        if (!(value instanceof String)) {
            throw typeFailure(field + "字段类型错误，期望String", fieldPath);
        }
        return (String) value;
    }

    private static int requireInt(Map<String, Object> map, String field, String fieldPath) {
        Object value = map.get(field);
        if (value == null) {
            throw requiredFailure(field + "字段缺失", fieldPath);
        }
        if (value instanceof Integer) {
            return (Integer) value;
        }
        if (value instanceof Long) {
            long longValue = (Long) value;
            if (longValue >= Integer.MIN_VALUE && longValue <= Integer.MAX_VALUE) {
                return (int) longValue;
            }
        }
        throw typeFailure(field + "字段类型错误，期望int", fieldPath);
    }

    private static WorkflowNodeType parseNodeType(String value, String fieldPath) {
        for (WorkflowNodeType type : WorkflowNodeType.values()) {
            if (type.name().equals(value)) {
                return type;
            }
        }
        throw domainFailure("未知的Workflow节点类型: " + value, fieldPath);
    }

    private static WorkflowEdgeType parseEdgeType(String value, String fieldPath) {
        for (WorkflowEdgeType type : WorkflowEdgeType.values()) {
            if (type.name().equals(value)) {
                return type;
            }
        }
        throw domainFailure("未知的Workflow Edge类型: " + value, fieldPath);
    }

    private static String jacksonPath(JsonMappingException exception) {
        StringBuilder path = new StringBuilder();
        for (JsonMappingException.Reference reference : exception.getPath()) {
            if (reference.getFieldName() != null) {
                if (path.length() > 0) {
                    path.append('.');
                }
                path.append(reference.getFieldName());
            } else if (reference.getIndex() >= 0) {
                path.append('[').append(reference.getIndex()).append(']');
            }
        }
        return path.length() == 0 ? ROOT_FIELD_PATH : path.toString();
    }

    private static String childPath(String parentPath, String field) {
        return parentPath == null || parentPath.isEmpty() ? field : parentPath + "." + field;
    }

    private static WorkflowGraphDataException requiredFailure(String message, String fieldPath) {
        return dataFailure(ERROR_CODE_REQUIRED_FIELD_MISSING, message, fieldPath);
    }

    private static WorkflowGraphDataException typeFailure(String message, String fieldPath) {
        return dataFailure(ERROR_CODE_FIELD_TYPE_INVALID, message, fieldPath);
    }

    private static WorkflowGraphDataException domainFailure(String message, String fieldPath) {
        return dataFailure(ERROR_CODE_DOMAIN_DATA_INVALID, message, fieldPath);
    }

    private static WorkflowGraphDataException dataFailure(
            String errorCode, String message, String fieldPath) {
        return new WorkflowGraphDataException(errorCode, message, fieldPath);
    }

    private static WorkflowGraphDataException dataFailure(
            String errorCode, String message, String fieldPath, Throwable cause) {
        return new WorkflowGraphDataException(errorCode, message, fieldPath, cause);
    }
}
