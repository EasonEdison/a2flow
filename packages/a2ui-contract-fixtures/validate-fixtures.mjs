#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const ALLOWED_MODES = new Set(["DISPLAY_ONLY", "INTERACTIVE"]);
const ALLOWED_RETRY_REASONS = new Set([
  "RENDER_FAILED",
  "ACTION_CALL_FAILED",
  "ACTION_RESULT_NOT_SUCCESS",
]);
const FLOATING_RELEASE_VERSIONS = new Set(["default", "draft", "latest"]);
const INLINE_SUCCESS_POLICY_KEYS = new Set([
  "businessSuccessCondition",
  "businessSuccessConditionRef",
  "contractRevision",
  "defaultSuccessPolicyRef",
  "expectedLiteral",
  "jsonPointer",
  "operator",
  "outcomePolicy",
  "policyRef",
]);
const FORBIDDEN_KEYS = new Set([
  "credential",
  "credentials",
  "environment",
  "grayTarget",
  "html",
  "script",
  "secret",
  "sellerId",
  "userId",
]);

function fail(message) {
  throw new Error(message);
}

function assertCondition(condition, message) {
  if (!condition) {
    fail(message);
  }
}

function isExactNonFloatingReleaseRef(value) {
  if (typeof value !== "string") {
    return false;
  }
  const match = /^([^@\s]+)@([^@\s]+)$/.exec(value);
  return match !== null
    && !FLOATING_RELEASE_VERSIONS.has(match[2].toLowerCase());
}

function collectKeys(value, result = []) {
  if (Array.isArray(value)) {
    for (const item of value) {
      collectKeys(item, result);
    }
    return result;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      result.push(key);
      collectKeys(child, result);
    }
  }
  return result;
}

function componentChildren(component) {
  if (!Array.isArray(component.children)) {
    return [];
  }
  return component.children;
}

function validateGraph(fixture, label) {
  const template = fixture.surfaceTemplate;
  assertCondition(template && typeof template === "object", label + ": missing surfaceTemplate");
  assertCondition(Array.isArray(template.components), label + ": components must be an array");

  const byId = new Map();
  for (const component of template.components) {
    assertCondition(typeof component.id === "string" && component.id.length > 0, label + ": component id is required");
    assertCondition(!byId.has(component.id), label + ": duplicate component id " + component.id);
    byId.set(component.id, component);
  }

  assertCondition(template.rootId === "root", label + ": rootId must be root");
  assertCondition(byId.has("root"), label + ": root component is required");

  for (const component of byId.values()) {
    for (const childId of componentChildren(component)) {
      assertCondition(byId.has(childId), label + ": dangling child " + childId);
    }
  }

  const visiting = new Set();
  const visited = new Set();
  function visit(componentId) {
    assertCondition(!visiting.has(componentId), label + ": component graph contains a cycle");
    if (visited.has(componentId)) {
      return;
    }
    visiting.add(componentId);
    for (const childId of componentChildren(byId.get(componentId))) {
      visit(childId);
    }
    visiting.delete(componentId);
    visited.add(componentId);
  }
  visit("root");
  assertCondition(visited.size === byId.size, label + ": component graph contains unreachable nodes");
}

function actionEvents(fixture) {
  const result = new Map();
  for (const component of fixture.surfaceTemplate.components) {
    const event = component.action && component.action.event;
    if (event) {
      assertCondition(typeof event.name === "string" && event.name.length > 0, fixture.asset.applicationKey + ": action event name is required");
      assertCondition(!result.has(event.name), fixture.asset.applicationKey + ": duplicate action event " + event.name);
      result.set(event.name, component.id);
    }
  }
  return result;
}

export function validateFixture(fixture, label = "fixture") {
  assertCondition(fixture && typeof fixture === "object", label + ": fixture must be an object");
  assertCondition(fixture.fixtureMetadata?.synthetic === true, label + ": fixture must be explicitly synthetic");
  assertCondition(fixture.fixtureMetadata?.contractStatus === "PROVISIONAL", label + ": fixture contractStatus must be PROVISIONAL");
  assertCondition(fixture.fixtureMetadata?.baseline === "SW-P1-20260907.2", label + ": fixture baseline mismatch");
  assertCondition(fixture.asset?.kind === "APPLICATION", label + ": asset kind must be APPLICATION");
  assertCondition(fixture.asset?.protocolProfileRef === "PENDING_CROSS_DOMAIN_REVIEW", label + ": protocol version must remain pending cross-domain review");
  assertCondition(fixture.renderPolicy?.tool === "render_application", label + ": Application rendering must enter through render_application");

  const mode = fixture.renderPolicy?.interactionMode;
  assertCondition(ALLOWED_MODES.has(mode), label + ": unsupported interactionMode " + mode);
  assertCondition(fixture.versionAdmissionPolicy?.compareBeforeExecution === true, label + ": compareBeforeExecution must be true");
  assertCondition(fixture.versionAdmissionPolicy?.compareBeforeContinue === true, label + ": compareBeforeContinue must be true");
  assertCondition(fixture.versionAdmissionPolicy?.compareBeforeAction === true, label + ": compareBeforeAction must be true");
  assertCondition(fixture.versionAdmissionPolicy?.onMismatch === "RESET_REQUIRED", label + ": version mismatch must require reset");
  assertCondition(fixture.interactionPolicy?.ordinaryChatMayResume === false, label + ": ordinary chat must not resume an interaction");
  assertCondition(fixture.finalizerPolicy?.mayOverrideBusinessFacts === false, label + ": Finalizer must not override business facts");
  assertCondition(fixture.finalizerPolicy?.mayBypassRequiredInteraction === false, label + ": Finalizer must not bypass interaction");

  const forbidden = collectKeys(fixture).filter((key) => FORBIDDEN_KEYS.has(key));
  assertCondition(forbidden.length === 0, label + ": trusted runtime field embedded in fixture: " + forbidden.join(", "));

  const retryReasons = fixture.retryPolicy?.allowedReasons;
  assertCondition(Array.isArray(retryReasons), label + ": retryPolicy.allowedReasons is required");
  const uniqueRetryReasons = new Set(retryReasons);
  assertCondition(
    uniqueRetryReasons.size === retryReasons.length,
    label + ": retry reasons must not contain duplicates",
  );
  for (const reason of retryReasons) {
    assertCondition(ALLOWED_RETRY_REASONS.has(reason), label + ": retry reason is outside the A2UI-only boundary: " + reason);
  }

  validateGraph(fixture, label);
  const events = actionEvents(fixture);
  const policies = fixture.actionPolicies;
  assertCondition(Array.isArray(policies), label + ": actionPolicies must be an array");

  if (mode === "DISPLAY_ONLY") {
    assertCondition(fixture.renderPolicy.requiresPause === false, label + ": DISPLAY_ONLY must not pause");
    assertCondition(fixture.interactionPolicy.bindingScope === "NONE", label + ": DISPLAY_ONLY must not bind an interaction");
    assertCondition(policies.length === 0 && events.size === 0, label + ": DISPLAY_ONLY must not declare actions");
    assertCondition(retryReasons.length === 1 && retryReasons[0] === "RENDER_FAILED", label + ": DISPLAY_ONLY retry is render-only");
  } else {
    assertCondition(fixture.renderPolicy.requiresPause === true, label + ": INTERACTIVE must pause");
    assertCondition(fixture.interactionPolicy.bindingScope === "RUNTIME_NODE_CARD_FORM", label + ": INTERACTIVE must be node/card/form scoped");
    assertCondition(fixture.interactionPolicy.routeDirectlyWithoutAiReselection === true, label + ": configured choice must route without AI reselection");
    assertCondition(policies.length > 0, label + ": INTERACTIVE requires an action policy");
    assertCondition(
      uniqueRetryReasons.size === ALLOWED_RETRY_REASONS.size
        && [...ALLOWED_RETRY_REASONS].every((reason) => uniqueRetryReasons.has(reason)),
      label + ": INTERACTIVE retry reasons must exactly match the A2UI-only boundary",
    );

    const policiesByActionName = new Map();
    for (const policy of policies) {
      assertCondition(
        typeof policy.actionName === "string"
          && policy.actionName.trim().length > 0
          && typeof policy.sourceComponentId === "string"
          && policy.sourceComponentId.trim().length > 0,
        label + ": actionName and sourceComponentId must be non-empty",
      );
      assertCondition(
        !policiesByActionName.has(policy.actionName),
        label + ": duplicate action policy " + policy.actionName,
      );
      policiesByActionName.set(policy.actionName, policy);
      const inlinePolicyKeys = Object.keys(policy)
        .filter((key) => INLINE_SUCCESS_POLICY_KEYS.has(key));
      assertCondition(
        inlinePolicyKeys.length === 0,
        label + ": Action must not inline or reuse a superseded success-condition DSL",
      );
      assertCondition(events.get(policy.actionName) === policy.sourceComponentId, label + ": action policy must match its source component");
      assertCondition(
        isExactNonFloatingReleaseRef(policy.abilityReleaseRef),
        label + ": abilityReleaseRef must identify an exact non-floating release",
      );
      assertCondition(
        typeof policy.successPolicyRef === "string"
          && policy.successPolicyRef.length > 0,
        label + ": Action must select a named successPolicyRef",
      );
      assertCondition(typeof policy.completeInteractionOnSuccess === "boolean", label + ": completion behavior must be explicit");
      assertCondition(policy.controlRequestDedupeOnly === true, label + ": platform dedupe must be control-request only");
      assertCondition(policy.businessIdempotencyOwner === "CALLED_API_BACKEND", label + ": called API backend must own business idempotency");
    }
    assertCondition(
      policiesByActionName.size === events.size
        && [...events].every(([actionName, sourceComponentId]) =>
          policiesByActionName.get(actionName)?.sourceComponentId === sourceComponentId),
      label + ": every action event must have exactly one policy",
    );
  }
}

export function validateDirectory(directory) {
  const names = fs.readdirSync(directory)
    .filter((name) => name.endsWith(".application.json"))
    .sort();
  assertCondition(names.length === 2, "expected exactly two Application fixtures");

  for (const name of names) {
    const filePath = path.join(directory, name);
    const fixture = JSON.parse(fs.readFileSync(filePath, "utf8"));
    validateFixture(fixture, name);
  }
  return names;
}

function parseDirectoryArgument(argv) {
  const index = argv.indexOf("--directory");
  if (index === -1 || !argv[index + 1]) {
    fail("usage: node validate-fixtures.mjs --directory <fixtures-directory>");
  }
  return argv[index + 1];
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  try {
    const directory = parseDirectoryArgument(process.argv.slice(2));
    const names = validateDirectory(directory);
    process.stdout.write("validated " + names.length + " synthetic Application fixtures\n");
  } catch (error) {
    process.stderr.write(error.message + "\n");
    process.exitCode = 1;
  }
}
