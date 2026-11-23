// Public disposable scratch Worker source, not deployed or configured.
// Must be staged by an independently admitted, account-pinned factory grant.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.pathname !== '/health')
      return new Response(null, {status: 404});
    return new Response(JSON.stringify({schema:'commandcenter.factory.scratch.v1',project:'alpha'}), {
      headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store'}
    });
  }
};
