import type { WorkflowGraphValidationError, WorkflowValidationIssue } from './types';

export const graphErrorsToIssues = (
  errors: WorkflowGraphValidationError[],
): WorkflowValidationIssue[] =>
  errors.flatMap((error) => {
    const nodeCodes = error.graphPath?.length
      ? error.graphPath
      : [error.nodeCode].filter((value): value is string => Boolean(value));
    const graphPath = error.graphPath?.length ? `（${error.graphPath?.join?.(' → ')}）` : '';
    if (nodeCodes.length) {
      return nodeCodes.map((nodeCode) => ({
        path: error.fieldPath || error.errorCode,
        nodeCode,
        edgeId: error.edgeId,
        message: `${error.errorCode}: ${error.message}${graphPath}`,
      }));
    }
    return [
      {
        path: error.fieldPath || error.errorCode,
        edgeId: error.edgeId,
        message: `${error.errorCode}: ${error.message}`,
      },
    ];
  });
