package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

/** Fixed published ability identity; parameters are resolved by Runtime, never stored in the graph. */
@Data
@EqualsAndHashCode(callSuper = true)
@Accessors(chain = true)
public class WorkflowBusinessCapabilityNode extends WorkflowNode {
    private String abilityKey;
    private String nodePrompt;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getNodePrompt() { return nodePrompt; }
}
