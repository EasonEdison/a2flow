package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Workflow 发布编译产物。
 *
 * <p>该对象防御性复制并冻结所有 Map/List，保存 v1 执行计划、入口、节点、边、固定后继、
 * Router、并行组、唯一 Summary 和完整 canonical plan 的 SHA-256 digest。通过 Builder
 * 一次性构造，避免大参数构造器，同时保持字段完整、只读和 Java 8 兼容。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：发布快照和 Adviser compiledPlan Reader。
 * <p>不负责：发布版本管理、运行调度和 Skill 内容解析。
 */
public final class CompiledPlan {

    private static final int COMPILED_PLAN_CONTRACT_VERSION = 1;
    private static final int MIN_ROUTER_CANDIDATES = 2;
    private static final int MIN_PARALLEL_BRANCHES = 2;
    private static final int MIN_PARALLELISM = 2;
    private static final String JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED =
            "ALL_SUCCESS_OR_SKIPPED";

    private final int compiledPlanContractVersion;
    private final String compiledPlanDigest;
    private final String entryNodeCode;
    private final Map<String, CompiledNode> nodeMap;
    private final Map<String, CompiledEdge> edgeMap;
    private final Map<String, String> fixedSuccessorByNode;
    private final List<CompiledRouterDefinition> routerDefinitions;
    private final List<CompiledParallelDefinition> parallelDefinitions;
    private final String summaryNodeCode;
    private final String summaryPrompt;

    private CompiledPlan(Builder builder) {
        this.compiledPlanContractVersion = builder.compiledPlanContractVersion;
        this.compiledPlanDigest = builder.compiledPlanDigest;
        this.entryNodeCode = builder.entryNodeCode;
        this.nodeMap = Collections.unmodifiableMap(new LinkedHashMap<>(builder.nodeMap));
        this.edgeMap = Collections.unmodifiableMap(new LinkedHashMap<>(builder.edgeMap));
        this.fixedSuccessorByNode = Collections.unmodifiableMap(
                new LinkedHashMap<>(builder.fixedSuccessorByNode));
        this.routerDefinitions = Collections.unmodifiableList(
                new ArrayList<>(builder.routerDefinitions));
        this.parallelDefinitions = Collections.unmodifiableList(
                new ArrayList<>(builder.parallelDefinitions));
        this.summaryNodeCode = builder.summaryNodeCode;
        this.summaryPrompt = builder.summaryPrompt;
    }

    static Builder builder() {
        return new Builder();
    }

    public int getCompiledPlanContractVersion() {
        return compiledPlanContractVersion;
    }

    public String getCompiledPlanDigest() {
        return compiledPlanDigest;
    }

    public String getEntryNodeCode() {
        return entryNodeCode;
    }

    public Map<String, CompiledNode> getNodeMap() {
        return nodeMap;
    }

    public Map<String, CompiledEdge> getEdgeMap() {
        return edgeMap;
    }

    public Map<String, String> getFixedSuccessorByNode() {
        return fixedSuccessorByNode;
    }

    public List<CompiledRouterDefinition> getRouterDefinitions() {
        return routerDefinitions;
    }

    public List<CompiledParallelDefinition> getParallelDefinitions() {
        return parallelDefinitions;
    }

    public String getSummaryNodeCode() {
        return summaryNodeCode;
    }

    public String getSummaryPrompt() {
        return summaryPrompt;
    }

    /**
     * CompiledPlan 构建器，仅在编译阶段收集字段，构造时由 CompiledPlan 防御性复制集合。
     */
    static final class Builder {
        private int compiledPlanContractVersion;
        private String compiledPlanDigest;
        private String entryNodeCode;
        private Map<String, CompiledNode> nodeMap;
        private Map<String, CompiledEdge> edgeMap;
        private Map<String, String> fixedSuccessorByNode;
        private List<CompiledRouterDefinition> routerDefinitions;
        private List<CompiledParallelDefinition> parallelDefinitions;
        private String summaryNodeCode;
        private String summaryPrompt;

        private Builder() {
        }

        Builder compiledPlanContractVersion(int value) {
            this.compiledPlanContractVersion = value;
            return this;
        }

        Builder compiledPlanDigest(String value) {
            this.compiledPlanDigest = value;
            return this;
        }

        Builder entryNodeCode(String value) {
            this.entryNodeCode = value;
            return this;
        }

        Builder nodeMap(Map<String, CompiledNode> value) {
            this.nodeMap = value;
            return this;
        }

        Builder edgeMap(Map<String, CompiledEdge> value) {
            this.edgeMap = value;
            return this;
        }

        Builder fixedSuccessorByNode(Map<String, String> value) {
            this.fixedSuccessorByNode = value;
            return this;
        }

        Builder routerDefinitions(List<CompiledRouterDefinition> value) {
            this.routerDefinitions = value;
            return this;
        }

        Builder parallelDefinitions(List<CompiledParallelDefinition> value) {
            this.parallelDefinitions = value;
            return this;
        }

        Builder summaryNodeCode(String value) {
            this.summaryNodeCode = value;
            return this;
        }

        Builder summaryPrompt(String value) {
            this.summaryPrompt = value;
            return this;
        }

        CompiledPlan build() {
            validateRequiredFields();
            validateNodes();
            validateEdges();
            validateFixedSuccessors();
            validateRouterDefinitions();
            validateParallelDefinitions();
            return new CompiledPlan(this);
        }

        private void validateRequiredFields() {
            if (compiledPlanContractVersion != COMPILED_PLAN_CONTRACT_VERSION
                    || isBlank(compiledPlanDigest)
                    || isBlank(entryNodeCode) || nodeMap == null || edgeMap == null
                    || fixedSuccessorByNode == null || routerDefinitions == null
                    || parallelDefinitions == null || isBlank(summaryNodeCode)
                    || isBlank(summaryPrompt)) {
                throw new IllegalStateException("CompiledPlan字段不完整");
            }
        }

        private void validateNodes() {
            for (Map.Entry<String, CompiledNode> entry : nodeMap.entrySet()) {
                CompiledNode node = entry.getValue();
                if (isBlank(entry.getKey()) || node == null
                        || !entry.getKey().equals(node.getNodeCode()) || node.getNodeType() == null) {
                    throw new IllegalStateException("CompiledPlan nodeMap不合法");
                }
            }
            CompiledNode entryNode = nodeMap.get(entryNodeCode);
            CompiledNode summaryNode = nodeMap.get(summaryNodeCode);
            if (entryNode == null || summaryNode == null
                    || entryNodeCode.equals(summaryNodeCode)
                    || entryNode.getNodeType() == WorkflowNodeType.SUMMARY
                    || summaryNode.getNodeType() != WorkflowNodeType.SUMMARY) {
                throw new IllegalStateException("CompiledPlan入口或Summary节点不合法");
            }
        }

        private void validateEdges() {
            for (Map.Entry<String, CompiledEdge> entry : edgeMap.entrySet()) {
                CompiledEdge edge = entry.getValue();
                if (isBlank(entry.getKey()) || edge == null
                        || !entry.getKey().equals(edge.getEdgeId())
                        || edge.getEdgeType() == null
                        || !nodeMap.containsKey(edge.getSourceNodeCode())
                        || !nodeMap.containsKey(edge.getTargetNodeCode())
                        || !isAllowedEdgeSource(edge)) {
                    throw new IllegalStateException("CompiledPlan edgeMap不合法");
                }
            }
        }

        private boolean isAllowedEdgeSource(CompiledEdge edge) {
            WorkflowNodeType sourceType = nodeMap.get(edge.getSourceNodeCode()).getNodeType();
            if (edge.getEdgeType() == WorkflowEdgeType.ROUTING) {
                return sourceType == WorkflowNodeType.ROUTER;
            }
            if (edge.getEdgeType() == WorkflowEdgeType.PARALLEL) {
                return sourceType == WorkflowNodeType.PARALLEL_FORK;
            }
            return sourceType == WorkflowNodeType.SKILL
                    || sourceType == WorkflowNodeType.PARALLEL_JOIN;
        }

        private void validateFixedSuccessors() {
            Set<String> expectedSources = new HashSet<>();
            for (CompiledNode node : nodeMap.values()) {
                if (node.getNodeType() == WorkflowNodeType.SKILL
                        || node.getNodeType() == WorkflowNodeType.PARALLEL_JOIN) {
                    expectedSources.add(node.getNodeCode());
                }
            }
            if (!expectedSources.equals(fixedSuccessorByNode.keySet())) {
                throw new IllegalStateException("CompiledPlan fixedSuccessorByNode覆盖不完整");
            }
            for (Map.Entry<String, String> entry : fixedSuccessorByNode.entrySet()) {
                CompiledNode source = nodeMap.get(entry.getKey());
                if (source == null || !nodeMap.containsKey(entry.getValue())
                        || (source.getNodeType() != WorkflowNodeType.SKILL
                        && source.getNodeType() != WorkflowNodeType.PARALLEL_JOIN)
                        || countOutgoingEdges(entry.getKey(), WorkflowEdgeType.NORMAL) != 1
                        || countMatchingEdges(entry.getKey(), entry.getValue(),
                        WorkflowEdgeType.NORMAL) != 1) {
                    throw new IllegalStateException("CompiledPlan fixedSuccessorByNode不合法");
                }
            }
        }

        private int countOutgoingEdges(String source, WorkflowEdgeType type) {
            int count = 0;
            for (CompiledEdge edge : edgeMap.values()) {
                if (edge.getEdgeType() == type && source.equals(edge.getSourceNodeCode())) {
                    count++;
                }
            }
            return count;
        }

        private int countMatchingEdges(String source, String target, WorkflowEdgeType type) {
            int count = 0;
            for (CompiledEdge edge : edgeMap.values()) {
                if (edge.getEdgeType() == type && source.equals(edge.getSourceNodeCode())
                        && target.equals(edge.getTargetNodeCode())) {
                    count++;
                }
            }
            return count;
        }

        private void validateRouterDefinitions() {
            Map<String, CompiledRouterDefinition> definitions = new HashMap<>();
            for (CompiledRouterDefinition router : routerDefinitions) {
                if (router == null || isBlank(router.getRouterNodeCode())
                        || isBlank(router.getRouterPrompt())
                        || router.getRouterContractVersion() != COMPILED_PLAN_CONTRACT_VERSION
                        || isBlank(router.getRouterSchemaDigest())
                        || definitions.put(router.getRouterNodeCode(), router) != null
                        || nodeMap.get(router.getRouterNodeCode()) == null
                        || nodeMap.get(router.getRouterNodeCode()).getNodeType()
                        != WorkflowNodeType.ROUTER || router.getCandidates() == null
                        || router.getCandidates().size() < MIN_ROUTER_CANDIDATES) {
                    throw new IllegalStateException("CompiledPlan routerDefinitions不合法");
                }
                validateRouterCandidates(router);
            }
            validateDefinitionCoverage(WorkflowNodeType.ROUTER, definitions.keySet(),
                    "CompiledPlan Router定义覆盖不完整");
        }

        private void validateRouterCandidates(CompiledRouterDefinition router) {
            Map<String, CompiledEdge> edges = indexEdges(router.getRouterNodeCode(),
                    WorkflowEdgeType.ROUTING, true);
            Set<String> candidates = new HashSet<>();
            for (CompiledRouterCandidate candidate : router.getCandidates()) {
                if (candidate == null || isBlank(candidate.getRouteKey())
                        || isBlank(candidate.getTargetNodeCode())
                        || isBlank(candidate.getDescription())
                        || !candidates.add(candidate.getRouteKey())) {
                    throw new IllegalStateException("CompiledPlan Router候选不合法");
                }
                CompiledEdge edge = edges.get(candidate.getRouteKey());
                if (edge == null || !candidate.getTargetNodeCode().equals(edge.getTargetNodeCode())
                        || !candidate.getDescription().equals(edge.getDescription())) {
                    throw new IllegalStateException("CompiledPlan Router候选与Edge不一致");
                }
            }
            if (candidates.size() != edges.size()) {
                throw new IllegalStateException("CompiledPlan Router候选与Edge集合不一致");
            }
        }

        private void validateParallelDefinitions() {
            Map<String, CompiledParallelDefinition> definitions = new HashMap<>();
            Set<String> joins = new HashSet<>();
            for (CompiledParallelDefinition parallel : parallelDefinitions) {
                if (parallel == null || isBlank(parallel.getForkNodeCode())
                        || isBlank(parallel.getJoinNodeCode())
                        || definitions.put(parallel.getForkNodeCode(), parallel) != null
                        || !joins.add(parallel.getJoinNodeCode())
                        || nodeMap.get(parallel.getForkNodeCode()) == null
                        || nodeMap.get(parallel.getJoinNodeCode()) == null
                        || nodeMap.get(parallel.getForkNodeCode()).getNodeType()
                        != WorkflowNodeType.PARALLEL_FORK
                        || nodeMap.get(parallel.getJoinNodeCode()).getNodeType()
                        != WorkflowNodeType.PARALLEL_JOIN
                        || parallel.getOrderedBranches() == null
                        || parallel.getOrderedBranches().size() < MIN_PARALLEL_BRANCHES
                        || !JOIN_POLICY_ALL_SUCCESS_OR_SKIPPED.equals(parallel.getJoinPolicy())
                        || parallel.getMaxParallelism() < MIN_PARALLELISM) {
                    throw new IllegalStateException("CompiledPlan parallelDefinitions不合法");
                }
                validateParallelBranches(parallel);
            }
            validateDefinitionCoverage(WorkflowNodeType.PARALLEL_FORK, definitions.keySet(),
                    "CompiledPlan Fork定义覆盖不完整");
            validateDefinitionCoverage(WorkflowNodeType.PARALLEL_JOIN, joins,
                    "CompiledPlan Join定义覆盖不完整");
        }

        private void validateParallelBranches(CompiledParallelDefinition parallel) {
            Map<String, CompiledEdge> edges = indexEdges(parallel.getForkNodeCode(),
                    WorkflowEdgeType.PARALLEL, false);
            Set<String> branches = new HashSet<>();
            Set<String> targets = new HashSet<>();
            Set<Integer> branchOrders = new HashSet<>();
            for (CompiledOrderedBranch branch : parallel.getOrderedBranches()) {
                CompiledNode target = branch == null ? null : nodeMap.get(branch.getTargetNodeCode());
                if (branch == null || isBlank(branch.getBranchKey())
                        || isBlank(branch.getTargetNodeCode()) || !branches.add(branch.getBranchKey())
                        || !targets.add(branch.getTargetNodeCode())
                        || !branchOrders.add(branch.getBranchOrder())
                        || parallel.getJoinNodeCode().equals(branch.getTargetNodeCode())
                        || target == null || target.getNodeType() == WorkflowNodeType.PARALLEL_FORK) {
                    throw new IllegalStateException("CompiledPlan并行分支不合法");
                }
                CompiledEdge edge = edges.get(branch.getBranchKey());
                if (edge == null || edge.getBranchOrder() == null
                        || !branch.getTargetNodeCode().equals(edge.getTargetNodeCode())
                        || branch.getBranchOrder() != edge.getBranchOrder()) {
                    throw new IllegalStateException("CompiledPlan并行分支与Edge不一致");
                }
            }
            if (branches.size() != edges.size()) {
                throw new IllegalStateException("CompiledPlan并行分支与Edge集合不一致");
            }
        }

        private Map<String, CompiledEdge> indexEdges(String sourceNodeCode,
                WorkflowEdgeType edgeType, boolean router) {
            Map<String, CompiledEdge> result = new HashMap<>();
            for (CompiledEdge edge : edgeMap.values()) {
                if (sourceNodeCode.equals(edge.getSourceNodeCode()) && edge.getEdgeType() == edgeType) {
                    String key = router ? edge.getRouteKey() : edge.getBranchKey();
                    if (isBlank(key) || result.put(key, edge) != null) {
                        throw new IllegalStateException("CompiledPlan定义Edge键为空或重复");
                    }
                }
            }
            return result;
        }

        private void validateDefinitionCoverage(WorkflowNodeType type, Set<String> definitions,
                String errorMessage) {
            Set<String> expected = new HashSet<>();
            for (CompiledNode node : nodeMap.values()) {
                if (node.getNodeType() == type) {
                    expected.add(node.getNodeCode());
                }
            }
            if (!expected.equals(definitions)) {
                throw new IllegalStateException(errorMessage);
            }
        }

        private boolean isBlank(String value) {
            return value == null || value.trim().isEmpty();
        }
    }
}
