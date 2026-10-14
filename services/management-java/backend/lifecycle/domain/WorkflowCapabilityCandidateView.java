package dev.a2flow.management.lifecycle.domain;

import java.util.List;

/** Selection metadata only; execution reads the current trusted-environment contract. */
public record WorkflowCapabilityCandidateView(String abilityKey, String displayName,
        String description, String draftId, List<String> environments) { }
