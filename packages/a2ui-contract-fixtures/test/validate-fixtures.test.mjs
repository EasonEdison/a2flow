import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { validateFixture } from "../validate-fixtures.mjs";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const validatorPath = fileURLToPath(new URL("../validate-fixtures.mjs", import.meta.url));
const fixturesDirectory = path.join(packageRoot, "fixtures");

function loadFixture(name) {
  const fixturePath = path.join(fixturesDirectory, name);
  return JSON.parse(readFileSync(fixturePath, "utf8"));
}

test("validates the two project-authored Application fixtures", () => {
  const result = spawnSync(
    process.execPath,
    [validatorPath, "--directory", fixturesDirectory],
    { encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(
    result.stdout,
    /validated 2 synthetic Application fixtures/,
  );
});

test("rejects an interactive fixture that drops an A2UI retry outcome", () => {
  const fixture = loadFixture(
    "interactive-selection-card.application.json",
  );
  fixture.retryPolicy.allowedReasons = ["RENDER_FAILED"];

  assert.throws(
    () => validateFixture(fixture, "mutated interactive fixture"),
    /INTERACTIVE retry reasons must exactly match the A2UI-only boundary/,
  );
});

test("rejects an inline success-condition DSL", () => {
  const fixture = loadFixture(
    "interactive-selection-card.application.json",
  );
  fixture.actionPolicies[0].outcomePolicy = {
    businessSuccessCondition: {
      schemaOwner: "packages/contracts",
      operator: "EQUALS",
      path: "/accepted",
      expected: true,
    },
    completeInteractionOnSuccess: true,
  };

  assert.throws(
    () => validateFixture(fixture, "inline success condition"),
    /business success condition must be an exact published reference/,
  );
});

const invalidCases = [
  {
    name: "embedded trusted environment",
    fixture: "display-only-result-card.application.json",
    mutate: (fixture) => { fixture.environment = "PRT"; },
    expected: /trusted runtime field embedded in fixture: environment/,
  },
  {
    name: "pinned protocol before cross-domain review",
    fixture: "display-only-result-card.application.json",
    mutate: (fixture) => { fixture.asset.protocolProfileRef = "v0.9.1"; },
    expected: /protocol version must remain pending cross-domain review/,
  },
  {
    name: "execution admission without a version comparison",
    fixture: "display-only-result-card.application.json",
    mutate: (fixture) => { fixture.versionAdmissionPolicy.compareBeforeExecution = false; },
    expected: /compareBeforeExecution must be true/,
  },
  {
    name: "continue admission without a version comparison",
    fixture: "interactive-selection-card.application.json",
    mutate: (fixture) => { fixture.versionAdmissionPolicy.compareBeforeContinue = false; },
    expected: /compareBeforeContinue must be true/,
  },
  {
    name: "action admission without a version comparison",
    fixture: "interactive-selection-card.application.json",
    mutate: (fixture) => { fixture.versionAdmissionPolicy.compareBeforeAction = false; },
    expected: /compareBeforeAction must be true/,
  },
  {
    name: "display-only pause",
    fixture: "display-only-result-card.application.json",
    mutate: (fixture) => { fixture.renderPolicy.requiresPause = true; },
    expected: /DISPLAY_ONLY must not pause/,
  },
  {
    name: "implicit interaction completion",
    fixture: "interactive-selection-card.application.json",
    mutate: (fixture) => {
      delete fixture.actionPolicies[0].outcomePolicy.completeInteractionOnSuccess;
    },
    expected: /completion behavior must be explicit/,
  },
  {
    name: "generic model retry",
    fixture: "interactive-selection-card.application.json",
    mutate: (fixture) => { fixture.retryPolicy.allowedReasons.push("MODEL_FAILED"); },
    expected: /retry reason is outside the A2UI-only boundary: MODEL_FAILED/,
  },
  {
    name: "Finalizer overriding business facts",
    fixture: "interactive-selection-card.application.json",
    mutate: (fixture) => { fixture.finalizerPolicy.mayOverrideBusinessFacts = true; },
    expected: /Finalizer must not override business facts/,
  },
];

for (const invalidCase of invalidCases) {
  test("rejects " + invalidCase.name, () => {
    const fixture = loadFixture(invalidCase.fixture);
    invalidCase.mutate(fixture);
    assert.throws(
      () => validateFixture(fixture, invalidCase.name),
      invalidCase.expected,
    );
  });
}
