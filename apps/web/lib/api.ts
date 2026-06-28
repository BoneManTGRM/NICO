export const API = process.env.NEXT_PUBLIC_NICO_API_URL || 'http://localhost:8000';
export async function getJSON(path: string) { const res = await fetch(`${API}${path}`, { cache: 'no-store' }); if (!res.ok) throw new Error(`${res.status} ${path}`); return res.json(); }
export async function postJSON(path: string, body: any = {}) { const res = await fetch(`${API}${path}`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) }); if (!res.ok) throw new Error(`${res.status} ${path}`); return res.json(); }
