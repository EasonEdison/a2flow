package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseDigestUtils;

/**
 * Workflow 聚合草稿到确定性 compiledPlan 的编译器。
 *
 * <p>该类负责校验节点与边引用、唯一入口、唯一 Summary、无环、全图可达、节点出口类型、
 * Router 候选映射以及非嵌套 Fork/Join 分支闭合，并生成防御性不可变的 v1 执行计划。
 * digest 使用固定字段顺序的 canonical Map，经 JsonSupport.toJSON 后复用 ReleaseDigestUtils。
 *
 * <p>上游：WorkflowDefinitionService 和后续 WorkflowReleaseAssetAdapter。
 * <p>下游：CompiledPlan、发布快照和 Adviser compiledPlan Reader。
 * <p>不负责：Skill 专员关系校验、递归发布依赖、运行态调度和发布状态机。
 */
public final class WorkflowCompiledPlanBuilder {

    private static final Logger log = LoggerFactory.getLogger(WorkflowCompiledPlanBuilder.class);

    private static final int COMPILED_PLAN_CONTRACT_VERSION = 1;
    private static final int MIN_ROUTER_CANDIDATES = 2;
    private static final int MIN_PARALLEL_BRANCHES = 2;
    private static final int MAX_BRANCH_KEY_LENGTH = 62;
    private static final String SUMMARY_NODE_CODE = "__summary__";
    private static final String JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED = "ALL_SUCCESS_OR_SKIPPED";

    private static final String ERROR_AGGREGATE_REQUIRED = "WORKFLOW_AGGREGATE_REQUIRED";
    private static final String ERROR_NODE_ELEMENT_NULL = "NODE_ELEMENT_NULL";
    private static final String ERROR_NODE_CODE_MISSING = "NODE_CODE_MISSING";
    private static final String ERROR_NODE_TYPE_MISSING = "NODE_TYPE_MISSING";
    private static final String ERROR_EDGE_ELEMENT_NULL = "EDGE_ELEMENT_NULL";
    private static final String ERROR_EDGE_ID_MISSING = "EDGE_ID_MISSING";
    private static final String ERROR_EDGE_TYPE_MISSING = "EDGE_TYPE_MISSING";
    private static final String ERROR_DUPLICATE_NODE_CODE = "DUPLICATE_NODE_CODE";
    private static final String ERROR_DUPLICATE_EDGE_ID = "DUPLICATE_EDGE_ID";
    private static final String ERROR_NODE_REFERENCE_NOT_FOUND = "NODE_REFERENCE_NOT_FOUND";
    private static final String ERROR_MULTIPLE_ENTRY_NODES = "MULTIPLE_ENTRY_NODES";
    private static final String ERROR_ENTRY_NODE_NOT_FOUND = "ENTRY_NODE_NOT_FOUND";
    private static final String ERROR_CYCLE_DETECTED = "CYCLE_DETECTED";
    private static final String ERROR_ORPHAN_NODE = "ORPHAN_NODE";
    private static final String ERROR_SUMMARY_INVALID = "SUMMARY_INVALID";
    private static final String ERROR_SKILL_REQUIRED = "SKILL_NODE_REQUIRED";
    private static final String ERROR_NODE_OUTGOING_INVALID = "NODE_OUTGOING_INVALID";
    private static final String ERROR_ROUTER_CANDIDATE_INVALID = "ROUTER_CANDIDATE_INVALID";
    private static final String ERROR_FORK_JOIN_MISMATCH = "FORK_JOIN_MISMATCH";
    private static final String ERROR_PARALLEL_BRANCH_INVALID = "PARALLEL_BRANCH_INVALID";
    private static final String ERROR_NESTED_FORK = "NESTED_FORK_NOT_ALLOWED";
    private static final String ERROR_BRANCH_SCOPE_OVERLAP = "BRANCH_SCOPE_OVERLAP";
    private static final String ERROR_BRANCH_ESCAPE = "BRANCH_ESCAPE";
    private static final String ERROR_NODE_TYPE_MISMATCH = "NODE_TYPE_MISMATCH";
    private static final String ERROR_NODE_FIELD_INVALID = "NODE_FIELD_INVALID";
    private static final String ERROR_EDGE_FIELD_INVALID = "EDGE_FIELD_INVALID";

    private static final Comparator<WorkflowEdge> EDGE_ID_COMPARATOR =
            Comparator.comparing(WorkflowEdge::getEdgeId);
    private static final Comparator<CompiledRouterCandidate> ROUTE_KEY_COMPARATOR =
            Comparator.comparing(CompiledRouterCandidate::getRouteKey);
    private static final Comparator<CompiledOrderedBranch> BRANCH_COMPARATOR =
            Comparator.comparingInt(CompiledOrderedBranch::getBranchOrder)
                    .thenComparing(CompiledOrderedBranch::getBranchKey);

    private WorkflowCompiledPlanBuilder() {
    }

    /**
     * 校验完整 Workflow 聚合并构建确定性不可变执行计划。
     *
     * <p>编译失败时只记录 workflowCode、nodeCode、edgeId 或 cycle path，不记录 Prompt 和 payload。
     *
     * @param aggregate 已完成强类型解析的 Workflow 聚合草稿
     * @return compiledPlanContractVersion=1 的不可变执行计划
     * @throws WorkflowGraphCompilationException 任一图约束不满足
     */
    public static CompiledPlan build(WorkflowGraphAggregate aggregate) {
        if (aggregate == null || aggregate.getNodes() == null || aggregate.getEdges() == null) {
            throw failure(ERROR_AGGREGATE_REQUIRED, "Workflow聚合草稿不能为空", null, null, null);
        }
        log.info("开始编译Workflow执行计划, workflowCode:{}, nodeCount:{}, edgeCount:{}",
                aggregate.getWorkflowCode(), aggregate.getNodes().size(), aggregate.getEdges().size());

        Map<String, WorkflowNode> nodes = indexNodes(aggregate.getNodes());
        Map<String, WorkflowEdge> edges = indexEdges(aggregate.getEdges());
        GraphIndex graph = buildGraphIndex(nodes, aggregate.getEdges());
        WorkflowSummaryNode summary = validateSummary(aggregate, nodes, graph);
        String entryNodeCode = validateEntry(graph, summary.getNodeCode());
        validateAcyclic(nodes, graph.outgoing);
        validateReachability(nodes, graph, entryNodeCode, summary.getNodeCode());
        validateNodeSemantics(nodes, graph.outgoing, summary.getNodeCode());

        Map<String, String> fixedSuccessors = buildFixedSuccessors(nodes, graph.outgoing);
        List<CompiledRouterDefinition> routers = buildRouterDefinitions(nodes, graph.outgoing);
        List<CompiledParallelDefinition> parallels = buildParallelDefinitions(nodes, graph);
        Map<String, CompiledNode> compiledNodes = compileNodes(nodes);
        Map<String, CompiledEdge> compiledEdges = compileEdges(edges);
        String digest = calculateDigest(entryNodeCode, compiledNodes, compiledEdges,
                fixedSuccessors, routers, parallels, summary);

        log.info("Workflow执行计划编译成功, workflowCode:{}, entryNodeCode:{}, "
                        + "summaryNodeCode:{}, routerCount:{}, parallelCount:{}",
                aggregate.getWorkflowCode(), entryNodeCode, summary.getNodeCode(),
                routers.size(), parallels.size());
        return CompiledPlan.builder()
                .compiledPlanContractVersion(COMPILED_PLAN_CONTRACT_VERSION)
                .compiledPlanDigest(digest)
                .entryNodeCode(entryNodeCode)
                .nodeMap(compiledNodes)
                .edgeMap(compiledEdges)
                .fixedSuccessorByNode(fixedSuccessors)
                .routerDefinitions(routers)
                .parallelDefinitions(parallels)
                .summaryNodeCode(summary.getNodeCode())
                .summaryPrompt(summary.getPrompt())
                .build();
    }

    private static Map<String, WorkflowNode> indexNodes(List<WorkflowNode> nodeList) {
        Map<String, WorkflowNode> result = new TreeMap<>();
        for (int i = 0; i < nodeList.size(); i++) {
            WorkflowNode node = nodeList.get(i);
            String basePath = "nodes[" + i + "]";
            if (node == null) {
                throw fieldFailure(ERROR_NODE_ELEMENT_NULL, "节点元素不能为空", null, null,
                        basePath);
            }
            if (isBlank(node.getNodeCode())) {
                throw fieldFailure(ERROR_NODE_CODE_MISSING, "nodeCode缺失", null, null,
                        basePath + ".nodeCode");
            }
            if (node.getNodeType() == null) {
                throw fieldFailure(ERROR_NODE_TYPE_MISSING, "nodeType缺失", node.getNodeCode(),
                        null, basePath + ".nodeType");
            }
            validateRequiredNodeFields(node, basePath);
            if (result.put(node.getNodeCode(), node) != null) {
                throw fieldFailure(ERROR_DUPLICATE_NODE_CODE, "nodeCode重复", node.getNodeCode(),
                        null, basePath + ".nodeCode");
            }
        }
        return result;
    }

    private static void validateRequiredNodeFields(WorkflowNode node, String basePath) {
        boolean typeMatches;
        switch (node.getNodeType()) {
            case SKILL:
                typeMatches = node instanceof WorkflowSkillNode;
                break;
            case ROUTER:
                typeMatches = node instanceof WorkflowRouterNode;
                break;
            case PARALLEL_FORK:
                typeMatches = node instanceof WorkflowForkNode;
                break;
            case PARALLEL_JOIN:
                typeMatches = node instanceof WorkflowJoinNode;
                break;
            case SUMMARY:
                typeMatches = node instanceof WorkflowSummaryNode;
                break;
            default:
                typeMatches = false;
        }
        if (!typeMatches) {
            throw fieldFailure(ERROR_NODE_TYPE_MISMATCH, "节点实际类型与nodeType不匹配",
                    node.getNodeCode(), null, basePath + ".nodeType");
        }
        validateNodeFields(node, basePath);
    }

    private static void validateNodeFields(WorkflowNode node, String basePath) {
        if (node instanceof WorkflowSkillNode) {
            WorkflowSkillNode skill = (WorkflowSkillNode) node;
            requireNodeField(!isBlank(skill.getSkillCode()), node, basePath + ".skillCode",
                    "Skill节点skillCode缺失");
            requireNodeField(!isBlank(skill.getNodePrompt()), node, basePath + ".nodePrompt",
                    "Skill节点nodePrompt缺失");
            requireNodeField(skill.getControlPolicy() != null, node,
                    basePath + ".controlPolicy", "Skill节点controlPolicy缺失");
            requireNodeField(skill.getControlPolicy().getAllowSkip() != null, node,
                    basePath + ".controlPolicy.allowSkip", "Skill节点allowSkip缺失");
        } else if (node instanceof WorkflowRouterNode) {
            WorkflowRouterNode router = (WorkflowRouterNode) node;
            requireNodeField(!isBlank(router.getRouterPrompt()), node,
                    basePath + ".routerPrompt", "Router节点routerPrompt缺失");
            requireNodeField(router.getRouterContractVersion() == COMPILED_PLAN_CONTRACT_VERSION,
                    node, basePath + ".routerContractVersion", "Router契约版本不合法");
            requireNodeField(!isBlank(router.getRouterSchemaDigest()), node,
                    basePath + ".routerSchemaDigest", "Router节点routerSchemaDigest缺失");
            requireNodeField(router.getCandidates() != null, node, basePath + ".candidates",
                    "Router节点candidates缺失");
            for (int i = 0; i < router.getCandidates().size(); i++) {
                validateRouterCandidate(router.getCandidates().get(i), node,
                        basePath + ".candidates[" + i + "]");
            }
        } else if (node instanceof WorkflowForkNode) {
            WorkflowForkNode fork = (WorkflowForkNode) node;
            requireNodeField(!isBlank(fork.getMatchingNodeCode()), node,
                    basePath + ".matchingNodeCode", "Fork节点matchingNodeCode缺失");
            requireNodeField(!isBlank(fork.getJoinPolicy()), node, basePath + ".joinPolicy",
                    "Fork节点joinPolicy缺失");
            requireNodeField(fork.getMaxParallelism() >= MIN_PARALLEL_BRANCHES, node,
                    basePath + ".maxParallelism", "Fork节点maxParallelism不合法");
        } else if (node instanceof WorkflowJoinNode) {
            WorkflowJoinNode join = (WorkflowJoinNode) node;
            requireNodeField(!isBlank(join.getMatchingNodeCode()), node,
                    basePath + ".matchingNodeCode", "Join节点matchingNodeCode缺失");
            requireNodeField(!isBlank(join.getJoinPolicy()), node, basePath + ".joinPolicy",
                    "Join节点joinPolicy缺失");
        } else if (node instanceof WorkflowSummaryNode) {
            requireNodeField(!isBlank(((WorkflowSummaryNode) node).getPrompt()), node,
                    basePath + ".prompt", "Summary节点prompt为空");
        }
    }

    private static void validateRouterCandidate(WorkflowRouterCandidate candidate,
            WorkflowNode node, String basePath) {
        if (candidate == null) {
            throw fieldFailure(ERROR_ROUTER_CANDIDATE_INVALID, "Router候选不能为空",
                    node.getNodeCode(), null, basePath);
        }
        requireCandidateField(!isBlank(candidate.getRouteKey()), node, basePath + ".routeKey",
                "Router候选routeKey缺失");
        requireCandidateField(!isBlank(candidate.getDescription()), node,
                basePath + ".description", "Router候选description缺失");
        requireCandidateField(!isBlank(candidate.getTargetNodeCode()), node,
                basePath + ".targetNodeCode", "Router候选targetNodeCode缺失");
    }

    private static void requireCandidateField(boolean valid, WorkflowNode node, String fieldPath,
            String message) {
        if (!valid) {
            throw fieldFailure(ERROR_ROUTER_CANDIDATE_INVALID, message, node.getNodeCode(), null,
                    fieldPath);
        }
    }

    private static void requireNodeField(boolean valid, WorkflowNode node, String fieldPath,
            String message) {
        if (!valid) {
            throw fieldFailure(ERROR_NODE_FIELD_INVALID, message, node.getNodeCode(), null,
                    fieldPath);
        }
    }

    private static Map<String, WorkflowEdge> indexEdges(List<WorkflowEdge> edgeList) {
        Map<String, WorkflowEdge> result = new TreeMap<>();
        for (int i = 0; i < edgeList.size(); i++) {
            WorkflowEdge edge = edgeList.get(i);
            String basePath = "edges[" + i + "]";
            if (edge == null) {
                throw fieldFailure(ERROR_EDGE_ELEMENT_NULL, "Edge元素不能为空", null, null,
                        basePath);
            }
            if (isBlank(edge.getEdgeId())) {
                throw fieldFailure(ERROR_EDGE_ID_MISSING, "edgeId缺失", null, null,
                        basePath + ".edgeId");
            }
            if (edge.getEdgeType() == null) {
                throw fieldFailure(ERROR_EDGE_TYPE_MISSING, "edgeType缺失", null,
                        edge.getEdgeId(), basePath + ".edgeType");
            }
            validateRequiredEdgeFields(edge, basePath);
            if (result.put(edge.getEdgeId(), edge) != null) {
                throw fieldFailure(ERROR_DUPLICATE_EDGE_ID, "edgeId重复", null,
                        edge.getEdgeId(), basePath + ".edgeId");
            }
        }
        return result;
    }

    private static void validateRequiredEdgeFields(WorkflowEdge edge, String basePath) {
        requireEdgeField(!isBlank(edge.getSourceNodeCode()), edge,
                basePath + ".sourceNodeCode", "Edge sourceNodeCode缺失");
        requireEdgeField(!isBlank(edge.getTargetNodeCode()), edge,
                basePath + ".targetNodeCode", "Edge targetNodeCode缺失");
        switch (edge.getEdgeType()) {
            case NORMAL:
                rejectEdgeField(edge.getRouteKey(), edge, basePath + ".routeKey");
                rejectEdgeField(edge.getDescription(), edge, basePath + ".description");
                rejectEdgeField(edge.getBranchKey(), edge, basePath + ".branchKey");
                rejectEdgeField(edge.getBranchOrder(), edge, basePath + ".branchOrder");
                break;
            case ROUTING:
                requireEdgeField(!isBlank(edge.getRouteKey()), edge, basePath + ".routeKey",
                        "Routing Edge routeKey缺失");
                requireEdgeField(!isBlank(edge.getDescription()), edge,
                        basePath + ".description", "Routing Edge description缺失");
                rejectEdgeField(edge.getBranchKey(), edge, basePath + ".branchKey");
                rejectEdgeField(edge.getBranchOrder(), edge, basePath + ".branchOrder");
                break;
            case PARALLEL:
                requireEdgeField(!isBlank(edge.getBranchKey()), edge, basePath + ".branchKey",
                        "Parallel Edge branchKey缺失");
                requireEdgeField(edge.getBranchKey().length() <= MAX_BRANCH_KEY_LENGTH, edge,
                        basePath + ".branchKey", "Parallel Edge branchKey长度不能超过62个字符");
                requireEdgeField(edge.getBranchOrder() != null, edge,
                        basePath + ".branchOrder", "Parallel Edge branchOrder缺失");
                rejectEdgeField(edge.getRouteKey(), edge, basePath + ".routeKey");
                rejectEdgeField(edge.getDescription(), edge, basePath + ".description");
                break;
            default:
                throw fieldFailure(ERROR_EDGE_TYPE_MISSING, "edgeType缺失", null,
                        edge.getEdgeId(), basePath + ".edgeType");
        }
    }

    private static void requireEdgeField(boolean valid, WorkflowEdge edge, String fieldPath,
            String message) {
        if (!valid) {
            throw fieldFailure(ERROR_EDGE_FIELD_INVALID, message, edge.getSourceNodeCode(),
                    edge.getEdgeId(), fieldPath);
        }
    }

    private static void rejectEdgeField(Object value, WorkflowEdge edge, String fieldPath) {
        if (value != null) {
            throw fieldFailure(ERROR_EDGE_FIELD_INVALID, "Edge携带当前类型不允许的字段",
                    edge.getSourceNodeCode(), edge.getEdgeId(), fieldPath);
        }
    }

    private static GraphIndex buildGraphIndex(Map<String, WorkflowNode> nodes,
            List<WorkflowEdge> edges) {
        Map<String, List<WorkflowEdge>> outgoing = new TreeMap<>();
        Map<String, List<WorkflowEdge>> incoming = new TreeMap<>();
        for (String nodeCode : nodes.keySet()) {
            outgoing.put(nodeCode, new ArrayList<WorkflowEdge>());
            incoming.put(nodeCode, new ArrayList<WorkflowEdge>());
        }
        for (int i = 0; i < edges.size(); i++) {
            WorkflowEdge edge = edges.get(i);
            String basePath = "edges[" + i + "]";
            if (!nodes.containsKey(edge.getSourceNodeCode())) {
                throw fieldFailure(ERROR_NODE_REFERENCE_NOT_FOUND, "Edge源节点不存在",
                        edge.getSourceNodeCode(), edge.getEdgeId(), basePath + ".sourceNodeCode");
            }
            if (!nodes.containsKey(edge.getTargetNodeCode())) {
                throw fieldFailure(ERROR_NODE_REFERENCE_NOT_FOUND, "Edge目标节点不存在",
                        edge.getTargetNodeCode(), edge.getEdgeId(), basePath + ".targetNodeCode");
            }
            outgoing.get(edge.getSourceNodeCode()).add(edge);
            incoming.get(edge.getTargetNodeCode()).add(edge);
        }
        for (List<WorkflowEdge> value : outgoing.values()) {
            Collections.sort(value, EDGE_ID_COMPARATOR);
        }
        for (List<WorkflowEdge> value : incoming.values()) {
            Collections.sort(value, EDGE_ID_COMPARATOR);
        }
        return new GraphIndex(outgoing, incoming);
    }

    private static WorkflowSummaryNode validateSummary(WorkflowGraphAggregate aggregate,
            Map<String, WorkflowNode> nodes, GraphIndex graph) {
        WorkflowNode raw = nodes.get(SUMMARY_NODE_CODE);
        if (!(raw instanceof WorkflowSummaryNode)) {
            throw failure(ERROR_SUMMARY_INVALID, "必须存在唯一__summary__节点",
                    SUMMARY_NODE_CODE, null, null);
        }
        int summaryCount = 0;
        int skillCount = 0;
        for (WorkflowNode node : nodes.values()) {
            if (node.getNodeType() == WorkflowNodeType.SUMMARY) {
                summaryCount++;
            }
            if (node.getNodeType() == WorkflowNodeType.SKILL) {
                skillCount++;
            }
        }
        WorkflowSummaryNode summary = (WorkflowSummaryNode) raw;
        if (summaryCount != 1 || summary.isAllowSkip() || isBlank(summary.getPrompt())
                || aggregate.getSummaryConfig() == null
                || !summary.getPrompt().equals(aggregate.getSummaryConfig().getPrompt())
                || !graph.outgoing.get(SUMMARY_NODE_CODE).isEmpty()) {
            throw failure(ERROR_SUMMARY_INVALID, "Summary契约不合法", SUMMARY_NODE_CODE,
                    firstEdgeId(graph.outgoing.get(SUMMARY_NODE_CODE)), null);
        }
        if (skillCount == 0) {
            throw failure(ERROR_SKILL_REQUIRED, "Workflow至少需要一个Skill节点", null, null, null);
        }
        return summary;
    }

    private static String validateEntry(GraphIndex graph, String summaryNodeCode) {
        List<String> entries = new ArrayList<>();
        for (Map.Entry<String, List<WorkflowEdge>> entry : graph.incoming.entrySet()) {
            if (entry.getValue().isEmpty()) {
                entries.add(entry.getKey());
            }
        }
        if (entries.isEmpty()) {
            throw failure(ERROR_ENTRY_NODE_NOT_FOUND, "Workflow缺少零入度入口节点", null, null, null);
        }
        if (entries.size() != 1) {
            throw failure(ERROR_MULTIPLE_ENTRY_NODES, "Workflow存在多个零入度入口节点",
                    entries.get(0), null, entries);
        }
        if (summaryNodeCode.equals(entries.get(0))) {
            throw failure(ERROR_SUMMARY_INVALID, "Summary不能作为Workflow入口", summaryNodeCode,
                    null, null);
        }
        return entries.get(0);
    }

    private static void validateAcyclic(Map<String, WorkflowNode> nodes,
            Map<String, List<WorkflowEdge>> outgoing) {
        Map<String, Integer> colors = new HashMap<>();
        List<String> stack = new ArrayList<>();
        for (String nodeCode : nodes.keySet()) {
            if (!colors.containsKey(nodeCode)) {
                dfsCycle(nodeCode, outgoing, colors, stack);
            }
        }
    }

    private static void dfsCycle(String nodeCode, Map<String, List<WorkflowEdge>> outgoing,
            Map<String, Integer> colors, List<String> stack) {
        colors.put(nodeCode, 1);
        stack.add(nodeCode);
        for (WorkflowEdge edge : outgoing.get(nodeCode)) {
            String target = edge.getTargetNodeCode();
            Integer color = colors.get(target);
            if (Integer.valueOf(1).equals(color)) {
                int start = stack.indexOf(target);
                List<String> cycle = new ArrayList<>(stack.subList(start, stack.size()));
                cycle.add(target);
                throw failure(ERROR_CYCLE_DETECTED, "Workflow存在环路", target,
                        edge.getEdgeId(), cycle);
            }
            if (color == null) {
                dfsCycle(target, outgoing, colors, stack);
            }
        }
        stack.remove(stack.size() - 1);
        colors.put(nodeCode, 2);
    }

    private static void validateReachability(Map<String, WorkflowNode> nodes, GraphIndex graph,
            String entryNodeCode, String summaryNodeCode) {
        Set<String> fromEntry = collectReachable(entryNodeCode, graph.outgoing);
        Set<String> toSummary = collectReverseReachable(summaryNodeCode, graph.incoming);
        for (String nodeCode : nodes.keySet()) {
            if (!fromEntry.contains(nodeCode) || !toSummary.contains(nodeCode)) {
                throw failure(ERROR_ORPHAN_NODE, "节点不满足入口可达且可到Summary",
                        nodeCode, null, null);
            }
        }
    }

    private static void validateNodeSemantics(Map<String, WorkflowNode> nodes,
            Map<String, List<WorkflowEdge>> outgoing, String summaryNodeCode) {
        for (WorkflowNode node : nodes.values()) {
            List<WorkflowEdge> edges = outgoing.get(node.getNodeCode());
            switch (node.getNodeType()) {
                case SKILL:
                case PARALLEL_JOIN:
                    requireExactlyOneEdgeType(node.getNodeCode(), edges, WorkflowEdgeType.NORMAL);
                    break;
                case ROUTER:
                    requireOnlyEdgeType(node.getNodeCode(), edges, WorkflowEdgeType.ROUTING,
                            MIN_ROUTER_CANDIDATES);
                    break;
                case PARALLEL_FORK:
                    requireOnlyEdgeType(node.getNodeCode(), edges, WorkflowEdgeType.PARALLEL,
                            MIN_PARALLEL_BRANCHES);
                    break;
                case SUMMARY:
                    if (!summaryNodeCode.equals(node.getNodeCode()) || !edges.isEmpty()) {
                        throw failure(ERROR_SUMMARY_INVALID, "Summary必须是唯一terminal节点",
                                node.getNodeCode(), firstEdgeId(edges), null);
                    }
                    break;
                default:
                    throw failure(ERROR_NODE_OUTGOING_INVALID, "未知节点类型",
                            node.getNodeCode(), null, null);
            }
        }
    }

    private static void requireExactlyOneEdgeType(String nodeCode, List<WorkflowEdge> edges,
            WorkflowEdgeType edgeType) {
        if (edges.size() != 1 || edges.get(0).getEdgeType() != edgeType) {
            throw failure(ERROR_NODE_OUTGOING_INVALID, "节点出口数量或类型不合法", nodeCode,
                    firstEdgeId(edges), null);
        }
    }

    private static void requireOnlyEdgeType(String nodeCode, List<WorkflowEdge> edges,
            WorkflowEdgeType edgeType, int minCount) {
        if (edges.size() < minCount) {
            throw failure(ERROR_NODE_OUTGOING_INVALID, "节点出口数量不足", nodeCode,
                    firstEdgeId(edges), null);
        }
        for (WorkflowEdge edge : edges) {
            if (edge.getEdgeType() != edgeType) {
                throw failure(ERROR_NODE_OUTGOING_INVALID, "节点出口类型不合法", nodeCode,
                        edge.getEdgeId(), null);
            }
        }
    }

    private static Map<String, String> buildFixedSuccessors(Map<String, WorkflowNode> nodes,
            Map<String, List<WorkflowEdge>> outgoing) {
        Map<String, String> result = new TreeMap<>();
        for (WorkflowNode node : nodes.values()) {
            if (node.getNodeType() == WorkflowNodeType.SKILL
                    || node.getNodeType() == WorkflowNodeType.PARALLEL_JOIN) {
                result.put(node.getNodeCode(), outgoing.get(node.getNodeCode()).get(0)
                        .getTargetNodeCode());
            }
        }
        return result;
    }

    private static List<CompiledRouterDefinition> buildRouterDefinitions(
            Map<String, WorkflowNode> nodes, Map<String, List<WorkflowEdge>> outgoing) {
        List<CompiledRouterDefinition> result = new ArrayList<>();
        for (WorkflowNode node : nodes.values()) {
            if (node.getNodeType() != WorkflowNodeType.ROUTER) {
                continue;
            }
            WorkflowRouterNode router = (WorkflowRouterNode) node;
            Map<String, WorkflowRouterCandidate> candidates = new TreeMap<>();
            for (WorkflowRouterCandidate candidate : router.getCandidates()) {
                if (candidate == null || isBlank(candidate.getRouteKey())
                        || candidates.put(candidate.getRouteKey(), candidate) != null) {
                    throw failure(ERROR_ROUTER_CANDIDATE_INVALID,
                            "Router候选routeKey为空或重复", router.getNodeCode(), null, null);
                }
            }
            Map<String, WorkflowEdge> routingEdges = new TreeMap<>();
            for (WorkflowEdge edge : outgoing.get(router.getNodeCode())) {
                if (isBlank(edge.getRouteKey()) || isBlank(edge.getDescription())
                        || routingEdges.put(edge.getRouteKey(), edge) != null) {
                    throw failure(ERROR_ROUTER_CANDIDATE_INVALID,
                            "Routing Edge routeKey为空或重复", router.getNodeCode(),
                            edge.getEdgeId(), null);
                }
            }
            if (!candidates.keySet().equals(routingEdges.keySet())) {
                throw failure(ERROR_ROUTER_CANDIDATE_INVALID,
                        "Router candidates与Routing Edge不一一对应", router.getNodeCode(),
                        null, null);
            }
            List<CompiledRouterCandidate> compiledCandidates = new ArrayList<>();
            for (String routeKey : candidates.keySet()) {
                WorkflowRouterCandidate candidate = candidates.get(routeKey);
                WorkflowEdge edge = routingEdges.get(routeKey);
                if (!candidate.getTargetNodeCode().equals(edge.getTargetNodeCode())
                        || !candidate.getDescription().equals(edge.getDescription())) {
                    throw failure(ERROR_ROUTER_CANDIDATE_INVALID,
                            "Router候选与Routing Edge目标或说明不一致", router.getNodeCode(),
                            edge.getEdgeId(), null);
                }
                compiledCandidates.add(new CompiledRouterCandidate(routeKey,
                        candidate.getDescription(), candidate.getTargetNodeCode()));
            }
            Collections.sort(compiledCandidates, ROUTE_KEY_COMPARATOR);
            result.add(new CompiledRouterDefinition(router.getNodeCode(),
                    router.getRouterPrompt(), compiledCandidates, router.getRouterContractVersion(),
                    router.getRouterSchemaDigest()));
        }
        return result;
    }

    private static List<CompiledParallelDefinition> buildParallelDefinitions(
            Map<String, WorkflowNode> nodes, GraphIndex graph) {
        List<CompiledParallelDefinition> result = new ArrayList<>();
        for (WorkflowNode node : nodes.values()) {
            if (node.getNodeType() != WorkflowNodeType.PARALLEL_FORK) {
                continue;
            }
            WorkflowForkNode fork = (WorkflowForkNode) node;
            WorkflowNode joinRaw = nodes.get(fork.getMatchingNodeCode());
            if (!(joinRaw instanceof WorkflowJoinNode)) {
                throw failure(ERROR_FORK_JOIN_MISMATCH, "Fork匹配Join不存在",
                        fork.getNodeCode(), null, null);
            }
            WorkflowJoinNode join = (WorkflowJoinNode) joinRaw;
            if (!fork.getNodeCode().equals(join.getMatchingNodeCode())
                    || !JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED.equals(fork.getJoinPolicy())
                    || !fork.getJoinPolicy().equals(join.getJoinPolicy())) {
                throw failure(ERROR_FORK_JOIN_MISMATCH, "Fork/Join双向匹配或策略不合法",
                        fork.getNodeCode(), null, null);
            }
            result.add(buildParallelDefinition(fork, join, nodes, graph));
        }
        for (WorkflowNode node : nodes.values()) {
            if (node instanceof WorkflowJoinNode) {
                WorkflowNode fork = nodes.get(((WorkflowJoinNode) node).getMatchingNodeCode());
                if (!(fork instanceof WorkflowForkNode)
                        || !node.getNodeCode().equals(((WorkflowForkNode) fork).getMatchingNodeCode())) {
                    throw failure(ERROR_FORK_JOIN_MISMATCH, "Join未与Fork双向匹配",
                            node.getNodeCode(), null, null);
                }
            }
        }
        return result;
    }

    private static CompiledParallelDefinition buildParallelDefinition(WorkflowForkNode fork,
            WorkflowJoinNode join, Map<String, WorkflowNode> nodes, GraphIndex graph) {
        List<CompiledOrderedBranch> branches = new ArrayList<>();
        Set<String> branchKeys = new HashSet<>();
        Set<Integer> branchOrders = new HashSet<>();
        Set<String> targets = new HashSet<>();
        List<Set<String>> scopes = new ArrayList<>();
        for (WorkflowEdge edge : graph.outgoing.get(fork.getNodeCode())) {
            if (isBlank(edge.getBranchKey()) || edge.getBranchOrder() == null
                    || !branchKeys.add(edge.getBranchKey())
                    || !branchOrders.add(edge.getBranchOrder())
                    || !targets.add(edge.getTargetNodeCode())
                    || join.getNodeCode().equals(edge.getTargetNodeCode())) {
                throw failure(ERROR_PARALLEL_BRANCH_INVALID,
                        "Parallel分支键、顺序或目标不合法", fork.getNodeCode(),
                        edge.getEdgeId(), null);
            }
            Set<String> scope = collectBranchScope(edge.getTargetNodeCode(), fork.getNodeCode(),
                    join.getNodeCode(), nodes, graph.outgoing);
            validateBranchIncoming(scope, edge.getTargetNodeCode(), fork.getNodeCode(),
                    join.getNodeCode(), graph.incoming);
            for (Set<String> existing : scopes) {
                Set<String> overlap = new HashSet<>(scope);
                overlap.retainAll(existing);
                if (!overlap.isEmpty()) {
                    throw failure(ERROR_BRANCH_SCOPE_OVERLAP,
                            "并行分支在Join前提前汇合", overlap.iterator().next(),
                            edge.getEdgeId(), null);
                }
            }
            scopes.add(scope);
            branches.add(new CompiledOrderedBranch(edge.getBranchKey(),
                    edge.getTargetNodeCode(), edge.getBranchOrder()));
        }
        validateJoinIncoming(join.getNodeCode(), scopes, graph.incoming);
        Collections.sort(branches, BRANCH_COMPARATOR);
        return new CompiledParallelDefinition(fork.getNodeCode(), join.getNodeCode(), branches,
                fork.getJoinPolicy(), fork.getMaxParallelism());
    }

    private static Set<String> collectBranchScope(String branchRoot, String forkNodeCode,
            String joinNodeCode, Map<String, WorkflowNode> nodes,
            Map<String, List<WorkflowEdge>> outgoing) {
        Set<String> visited = new LinkedHashSet<>();
        List<String> pending = new ArrayList<>();
        pending.add(branchRoot);
        while (!pending.isEmpty()) {
            String current = pending.remove(pending.size() - 1);
            if (joinNodeCode.equals(current)) {
                continue;
            }
            if (!visited.add(current)) {
                continue;
            }
            WorkflowNode node = nodes.get(current);
            if (node == null || node.getNodeType() == WorkflowNodeType.SUMMARY
                    || node.getNodeType() == WorkflowNodeType.PARALLEL_JOIN
                    || current.equals(forkNodeCode)) {
                throw failure(ERROR_BRANCH_ESCAPE, "并行分支绕过或进入错误Join",
                        current, null, null);
            }
            if (node.getNodeType() == WorkflowNodeType.PARALLEL_FORK) {
                throw failure(ERROR_NESTED_FORK, "v1禁止嵌套Fork", current, null, null);
            }
            for (WorkflowEdge edge : outgoing.get(current)) {
                pending.add(edge.getTargetNodeCode());
            }
        }
        if (!allPathsReachJoin(branchRoot, joinNodeCode, outgoing, new HashMap<String, Boolean>())) {
            throw failure(ERROR_BRANCH_ESCAPE, "并行分支存在未闭合到匹配Join的路径",
                    branchRoot, null, null);
        }
        return visited;
    }

    private static boolean allPathsReachJoin(String nodeCode, String joinNodeCode,
            Map<String, List<WorkflowEdge>> outgoing, Map<String, Boolean> memo) {
        if (joinNodeCode.equals(nodeCode)) {
            return true;
        }
        if (memo.containsKey(nodeCode)) {
            return memo.get(nodeCode);
        }
        List<WorkflowEdge> edges = outgoing.get(nodeCode);
        if (edges == null || edges.isEmpty()) {
            memo.put(nodeCode, false);
            return false;
        }
        for (WorkflowEdge edge : edges) {
            if (!allPathsReachJoin(edge.getTargetNodeCode(), joinNodeCode, outgoing, memo)) {
                memo.put(nodeCode, false);
                return false;
            }
        }
        memo.put(nodeCode, true);
        return true;
    }

    private static void validateBranchIncoming(Set<String> scope, String branchRoot,
            String forkNodeCode, String joinNodeCode,
            Map<String, List<WorkflowEdge>> incoming) {
        for (String nodeCode : scope) {
            for (WorkflowEdge edge : incoming.get(nodeCode)) {
                boolean fromSameScope = scope.contains(edge.getSourceNodeCode());
                boolean forkToRoot = branchRoot.equals(nodeCode)
                        && forkNodeCode.equals(edge.getSourceNodeCode())
                        && edge.getEdgeType() == WorkflowEdgeType.PARALLEL;
                if (!fromSameScope && !forkToRoot) {
                    throw failure(ERROR_BRANCH_ESCAPE, "并行分支存在跨分支或外部入口",
                            nodeCode, edge.getEdgeId(), null);
                }
            }
            if (joinNodeCode.equals(nodeCode)) {
                throw failure(ERROR_BRANCH_ESCAPE, "Join不应包含在分支scope中", nodeCode,
                        null, null);
            }
        }
    }

    private static void validateJoinIncoming(String joinNodeCode, List<Set<String>> scopes,
            Map<String, List<WorkflowEdge>> incoming) {
        int[] arrivalsByScope = new int[scopes.size()];
        for (WorkflowEdge edge : incoming.get(joinNodeCode)) {
            if (edge.getEdgeType() != WorkflowEdgeType.NORMAL) {
                throw failure(ERROR_BRANCH_ESCAPE, "Join只允许接收NORMAL入边",
                        joinNodeCode, edge.getEdgeId(), null);
            }
            int matchedScope = -1;
            for (int i = 0; i < scopes.size(); i++) {
                if (scopes.get(i).contains(edge.getSourceNodeCode())) {
                    if (matchedScope >= 0) {
                        throw failure(ERROR_BRANCH_SCOPE_OVERLAP,
                                "Join入边源节点同时属于多个分支scope",
                                edge.getSourceNodeCode(), edge.getEdgeId(), null);
                    }
                    matchedScope = i;
                }
            }
            if (matchedScope < 0) {
                throw failure(ERROR_BRANCH_ESCAPE, "Join收到对应分支scope之外的入边",
                        joinNodeCode, edge.getEdgeId(), null);
            }
            arrivalsByScope[matchedScope]++;
            if (arrivalsByScope[matchedScope] > 1) {
                throw failure(ERROR_BRANCH_ESCAPE, "同一分支scope存在多条Join入边",
                        joinNodeCode, edge.getEdgeId(), null);
            }
        }
        for (int i = 0; i < arrivalsByScope.length; i++) {
            if (arrivalsByScope[i] != 1) {
                throw failure(ERROR_BRANCH_ESCAPE, "每个分支scope必须恰好一条Join入边",
                        joinNodeCode, null, null);
            }
        }
    }

    private static Map<String, CompiledNode> compileNodes(Map<String, WorkflowNode> nodes) {
        Map<String, CompiledNode> result = new LinkedHashMap<>();
        for (WorkflowNode node : nodes.values()) {
            String skillCode = null;
            String nodePrompt = null;
            boolean allowSkip = false;
            if (node instanceof WorkflowSkillNode) {
                WorkflowSkillNode skill = (WorkflowSkillNode) node;
                skillCode = skill.getSkillCode();
                nodePrompt = skill.getNodePrompt();
                allowSkip = skill.getControlPolicy().getAllowSkip().booleanValue();
            }
            result.put(node.getNodeCode(), CompiledNode.builder()
                    .nodeCode(node.getNodeCode())
                    .nodeType(node.getNodeType())
                    .displayName(node.getDisplayName())
                    .skillCode(skillCode)
                    .nodePrompt(nodePrompt)
                    .allowSkip(allowSkip)
                    .build());
        }
        return result;
    }

    private static Map<String, CompiledEdge> compileEdges(Map<String, WorkflowEdge> edges) {
        Map<String, CompiledEdge> result = new LinkedHashMap<>();
        for (WorkflowEdge edge : edges.values()) {
            result.put(edge.getEdgeId(), CompiledEdge.builder()
                    .edgeId(edge.getEdgeId())
                    .sourceNodeCode(edge.getSourceNodeCode())
                    .targetNodeCode(edge.getTargetNodeCode())
                    .edgeType(edge.getEdgeType())
                    .routeKey(edge.getRouteKey())
                    .description(edge.getDescription())
                    .branchKey(edge.getBranchKey())
                    .branchOrder(edge.getBranchOrder())
                    .build());
        }
        return result;
    }

    /**
     * 使用固定字段插入顺序构造完整 canonical plan，摘要不包含 compiledPlanDigest 自身。
     */
    private static String calculateDigest(String entryNodeCode,
            Map<String, CompiledNode> nodeMap, Map<String, CompiledEdge> edgeMap,
            Map<String, String> fixedSuccessors,
            List<CompiledRouterDefinition> routers,
            List<CompiledParallelDefinition> parallels, WorkflowSummaryNode summary) {
        Map<String, Object> canonical = new LinkedHashMap<>();
        canonical.put("compiledPlanContractVersion", COMPILED_PLAN_CONTRACT_VERSION);
        canonical.put("entryNodeCode", entryNodeCode);
        canonical.put("nodeMap", canonicalNodeMap(nodeMap));
        canonical.put("edgeMap", canonicalEdgeMap(edgeMap));
        canonical.put("fixedSuccessorByNode", new TreeMap<>(fixedSuccessors));
        canonical.put("routerDefinitions", canonicalRouterDefinitions(routers));
        canonical.put("parallelDefinitions", canonicalParallelDefinitions(parallels));
        canonical.put("summaryNodeCode", summary.getNodeCode());
        canonical.put("summaryPrompt", summary.getPrompt());
        return ReleaseDigestUtils.sha256(JsonSupport.toJSON(canonical));
    }

    private static Map<String, Object> canonicalNodeMap(Map<String, CompiledNode> nodeMap) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<String, CompiledNode> entry : new TreeMap<>(nodeMap).entrySet()) {
            CompiledNode node = entry.getValue();
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("nodeCode", node.getNodeCode());
            value.put("nodeType", node.getNodeType().name());
            if (node.getDisplayName() != null) {
                value.put("displayName", node.getDisplayName());
            }
            if (node.getNodeType() == WorkflowNodeType.SKILL) {
                value.put("skillCode", node.getSkillCode());
                value.put("nodePrompt", node.getNodePrompt());
                value.put("allowSkip", node.isAllowSkip());
            }
            result.put(entry.getKey(), value);
        }
        return result;
    }

    private static Map<String, Object> canonicalEdgeMap(Map<String, CompiledEdge> edgeMap) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<String, CompiledEdge> entry : new TreeMap<>(edgeMap).entrySet()) {
            CompiledEdge edge = entry.getValue();
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("edgeId", edge.getEdgeId());
            value.put("sourceNodeCode", edge.getSourceNodeCode());
            value.put("targetNodeCode", edge.getTargetNodeCode());
            value.put("edgeType", edge.getEdgeType().name());
            if (edge.getEdgeType() == WorkflowEdgeType.ROUTING) {
                value.put("routeKey", edge.getRouteKey());
                value.put("description", edge.getDescription());
            } else if (edge.getEdgeType() == WorkflowEdgeType.PARALLEL) {
                value.put("branchKey", edge.getBranchKey());
                value.put("branchOrder", edge.getBranchOrder());
            }
            result.put(entry.getKey(), value);
        }
        return result;
    }

    private static List<Object> canonicalRouterDefinitions(
            List<CompiledRouterDefinition> routers) {
        List<Object> result = new ArrayList<>();
        for (CompiledRouterDefinition router : routers) {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("routerNodeCode", router.getRouterNodeCode());
            value.put("routerPrompt", router.getRouterPrompt());
            List<Object> candidates = new ArrayList<>();
            List<CompiledRouterCandidate> sorted = new ArrayList<>(router.getCandidates());
            Collections.sort(sorted, ROUTE_KEY_COMPARATOR);
            for (CompiledRouterCandidate candidate : sorted) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("routeKey", candidate.getRouteKey());
                item.put("description", candidate.getDescription());
                item.put("targetNodeCode", candidate.getTargetNodeCode());
                candidates.add(item);
            }
            value.put("candidates", candidates);
            value.put("routerContractVersion", router.getRouterContractVersion());
            value.put("routerSchemaDigest", router.getRouterSchemaDigest());
            result.add(value);
        }
        return result;
    }

    private static List<Object> canonicalParallelDefinitions(
            List<CompiledParallelDefinition> parallels) {
        List<Object> result = new ArrayList<>();
        for (CompiledParallelDefinition parallel : parallels) {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("forkNodeCode", parallel.getForkNodeCode());
            value.put("joinNodeCode", parallel.getJoinNodeCode());
            List<Object> branches = new ArrayList<>();
            List<CompiledOrderedBranch> sorted = new ArrayList<>(parallel.getOrderedBranches());
            Collections.sort(sorted, BRANCH_COMPARATOR);
            for (CompiledOrderedBranch branch : sorted) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("branchKey", branch.getBranchKey());
                item.put("targetNodeCode", branch.getTargetNodeCode());
                item.put("branchOrder", branch.getBranchOrder());
                branches.add(item);
            }
            value.put("orderedBranches", branches);
            value.put("joinPolicy", parallel.getJoinPolicy());
            value.put("maxParallelism", parallel.getMaxParallelism());
            result.add(value);
        }
        return result;
    }

    private static Set<String> collectReachable(String start,
            Map<String, List<WorkflowEdge>> outgoing) {
        Set<String> result = new HashSet<>();
        List<String> pending = new ArrayList<>();
        pending.add(start);
        while (!pending.isEmpty()) {
            String current = pending.remove(pending.size() - 1);
            if (result.add(current)) {
                for (WorkflowEdge edge : outgoing.get(current)) {
                    pending.add(edge.getTargetNodeCode());
                }
            }
        }
        return result;
    }

    private static Set<String> collectReverseReachable(String start,
            Map<String, List<WorkflowEdge>> incoming) {
        Set<String> result = new HashSet<>();
        List<String> pending = new ArrayList<>();
        pending.add(start);
        while (!pending.isEmpty()) {
            String current = pending.remove(pending.size() - 1);
            if (result.add(current)) {
                for (WorkflowEdge edge : incoming.get(current)) {
                    pending.add(edge.getSourceNodeCode());
                }
            }
        }
        return result;
    }

    private static String firstEdgeId(List<WorkflowEdge> edges) {
        return edges == null || edges.isEmpty() ? null : edges.get(0).getEdgeId();
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private static WorkflowGraphCompilationException fieldFailure(String errorCode,
            String message, String nodeCode, String edgeId, String fieldPath) {
        log.warn("Workflow图编译字段校验失败, errorCode:{}, nodeCode:{}, edgeId:{}, fieldPath:{}",
                errorCode, nodeCode, edgeId, fieldPath);
        return new WorkflowGraphCompilationException(errorCode, message, nodeCode, edgeId,
                fieldPath, null);
    }

    private static WorkflowGraphCompilationException failure(String errorCode, String message,
            String nodeCode, String edgeId, List<String> cyclePath) {
        log.warn("Workflow图编译失败, errorCode:{}, nodeCode:{}, edgeId:{}, path:{}",
                errorCode, nodeCode, edgeId, cyclePath);
        return new WorkflowGraphCompilationException(errorCode, message, nodeCode, edgeId,
                cyclePath);
    }

    private static final class GraphIndex {
        private final Map<String, List<WorkflowEdge>> outgoing;
        private final Map<String, List<WorkflowEdge>> incoming;

        private GraphIndex(Map<String, List<WorkflowEdge>> outgoing,
                Map<String, List<WorkflowEdge>> incoming) {
            this.outgoing = outgoing;
            this.incoming = incoming;
        }
    }
}
