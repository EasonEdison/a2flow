package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 编译后的不可变 Router 定义。
 *
 * <p>该对象冻结 Router Prompt、稳定排序候选和 Router Schema 契约，供运行时只按 routeKey 选路。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：CompiledPlan 和 Adviser Router Reader。
 * <p>不负责：模型调用、Schema 生成和运行态决策持久化。
 */
public final class CompiledRouterDefinition {

    private final String routerNodeCode;
    private final String routerPrompt;
    private final List<CompiledRouterCandidate> candidates;
    private final int routerContractVersion;
    private final String routerSchemaDigest;

    public CompiledRouterDefinition(String routerNodeCode, String routerPrompt,
            List<CompiledRouterCandidate> candidates, int routerContractVersion,
            String routerSchemaDigest) {
        if (candidates == null) {
            throw new IllegalArgumentException("Router候选集合不能为空");
        }
        this.routerNodeCode = routerNodeCode;
        this.routerPrompt = routerPrompt;
        this.candidates = Collections.unmodifiableList(new ArrayList<>(candidates));
        this.routerContractVersion = routerContractVersion;
        this.routerSchemaDigest = routerSchemaDigest;
    }

    public String getRouterNodeCode() {
        return routerNodeCode;
    }

    public String getRouterPrompt() {
        return routerPrompt;
    }

    public List<CompiledRouterCandidate> getCandidates() {
        return candidates;
    }

    public int getRouterContractVersion() {
        return routerContractVersion;
    }

    public String getRouterSchemaDigest() {
        return routerSchemaDigest;
    }
}
