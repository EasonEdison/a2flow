let nextRequestId = 0;

export function beginDependencyLoad(previous, identity) {
  return {
    identity,
    requestId: ++nextRequestId,
    loading: true,
    graph: previous?.identity === identity ? previous.graph : null,
    error: null,
    stale: previous?.identity === identity ? previous.stale : false,
    staleReason: previous?.identity === identity ? previous.staleReason : null,
  };
}

export function settleDependencyLoad(state, identity, requestId, graph, error, staleReason = null) {
  if (!state || state.identity !== identity || state.requestId !== requestId) return state;
  return {
    identity,
    requestId,
    loading: false,
    graph,
    error,
    stale: staleReason !== null,
    staleReason,
  };
}

export function staleDependencyState(state, reason) {
  if (!state) return state;
  return {
    ...state,
    requestId: ++nextRequestId,
    loading: false,
    stale: true,
    staleReason: reason,
  };
}
