// Cifrado de credenciales con AES-256-GCM. La clave maestra vive solo como secreto de Cloudflare (CRED_KEY, base64 de 32 bytes).
// El ID de la cuenta se usa como dato asociado: un texto cifrado no se puede mover a otra cuenta.
const enc = new TextEncoder(), dec = new TextDecoder();
const fromB64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const toB64 = (b) => btoa(String.fromCharCode(...new Uint8Array(b)));

async function key(env) {
  if (!env.CRED_KEY) throw new Error("Falta CRED_KEY");
  const raw = fromB64(env.CRED_KEY);
  if (raw.length !== 32) throw new Error("CRED_KEY debe tener 32 bytes");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function seal(env, cuentaId, obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: enc.encode(cuentaId) }, await key(env), enc.encode(JSON.stringify(obj)));
  return { ct: toB64(ct), iv: toB64(iv) };
}

export async function open(env, cuentaId, ct, iv) {
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromB64(iv), additionalData: enc.encode(cuentaId) }, await key(env), fromB64(ct));
  return JSON.parse(dec.decode(pt));
}
