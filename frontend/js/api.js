/* Centralised API client. Every call returns parsed JSON or throws ApiError. */
class ApiError extends Error {
  constructor(message, status, code) { super(message); this.status = status; this.code = code; }
}
const Api = (() => {
  async function request(method, path, body) {
    let res;
    try {
      res = await fetch(path, {
        method, headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) { throw new ApiError('Cannot reach the server. Is the backend running?', 0, 'network'); }
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) {
      const err = (data && data.error) || {};
      throw new ApiError(err.message || `Request failed (${res.status})`, res.status, err.code);
    }
    return data;
  }
  const qs = (o) => { const p = new URLSearchParams(); Object.entries(o || {}).forEach(([k, v]) => v && p.set(k, v)); const s = p.toString(); return s ? `?${s}` : ''; };
  return {
    getDashboard: () => request('GET', '/api/dashboard'),
    getEmails: (params) => request('GET', `/api/emails${qs(params)}`),
    getEmail: (id) => request('GET', `/api/emails/${id}`),
    syncEmails: () => request('POST', '/api/emails/sync'),
    analyzePending: () => request('POST', '/api/emails/analyze-pending'),
    analyzeEmail: (id) => request('POST', `/api/emails/${id}/analyze`),
    draftReply: (id, opts) => request('POST', `/api/emails/${id}/draft-reply`, opts || {}),
    getDrafts: (status) => request('GET', `/api/replies${qs({ status })}`),
    editReply: (id, body) => request('PATCH', `/api/replies/${id}`, { body }),
    approveReply: (id) => request('POST', `/api/replies/${id}/approve`),
    rejectReply: (id) => request('POST', `/api/replies/${id}/reject`),
    sendReply: (id) => request('POST', `/api/replies/${id}/send`, { confirm: true }),
    getSettings: () => request('GET', '/api/settings'),
    updateSettings: (patch) => request('PATCH', '/api/settings', patch),
    getActions: () => request('GET', '/api/actions'),
    disconnect: () => request('POST', '/api/auth/disconnect'),
  };
})();
