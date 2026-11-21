// Signed Cloudflare Access assertion verification. No trust in request email headers.
const utf8=new TextEncoder();const dec=new TextDecoder();
const b64=x=>Uint8Array.from(atob(x.replace(/-/g,'+').replace(/_/g,'/').padEnd(Math.ceil(x.length/4)*4,'=')),c=>c.charCodeAt(0));
export async function verifiedOwner(jwt,env,expectedAud,fetcher=fetch,now=Math.floor(Date.now()/1000)){
 if(!jwt || jwt.length<50 || jwt.length>16384 || typeof expectedAud!=='string'||expectedAud.length<8)throw Error('auth_absent');
 const parts=jwt.split('.');if(parts.length!==3 || parts.some(p=>!/^[A-Za-z0-9_-]+$/.test(p)))throw Error('bad_jwt');
 let h,c;try{h=JSON.parse(dec.decode(b64(parts[0])));c=JSON.parse(dec.decode(b64(parts[1])))}catch{throw Error('bad_json')}
 if(h?.alg!=='RS256'||!/^[\w.-]{1,128}$/.test(h.kid||''))throw Error('bad_header');
 let issuer;try{issuer=new URL(env.ACCESS_ISSUER)}catch{throw Error('issuer_unset')}
 if(issuer.protocol!=='https:'||issuer.pathname!=='/'||issuer.search||issuer.hash||!issuer.hostname.endsWith('.cloudflareaccess.com'))throw Error('issuer_invalid');
 if(c.iss!==issuer.origin||!(Array.isArray(c.aud)?c.aud:[c.aud]).includes(expectedAud)||
   !Number.isFinite(c.exp)||!Number.isFinite(c.iat)||c.exp<=now-30||c.iat>now+30||(c.nbf!==undefined&&(!Number.isFinite(c.nbf)||c.nbf>now+30))||
   (c.nbf!==undefined&&(!Number.isFinite(c.nbf)||c.nbf>now+30)))throw Error('jwt_claims');
 let allowed;try{allowed=JSON.parse(env.ACCESS_ALLOWED_EMAILS_JSON)}catch{throw Error('emails_unset')}
 if(!Array.isArray(allowed)||!allowed.length||allowed.length>20||!allowed.every(e=>typeof e==='string'&&e.includes('@')))throw Error('emails_invalid');
 if(typeof c.email!=='string'||!allowed.some(e=>e.trim().toLowerCase()===c.email.trim().toLowerCase()))throw Error('owner_rejected');
 const res=await fetcher(new URL('/cdn-cgi/access/certs',issuer.origin).toString(),{headers:{accept:'application/json'}});
 if(!res?.ok)throw Error('key_fetch');
 const jwks=await res.json();const jwk=jwks?.keys?.find(k=>k.kid===h.kid&&k.kty==='RSA'&&k.use!=='enc');if(!jwk)throw Error('key_unknown');
 const key=await crypto.subtle.importKey('jwk',jwk,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
 const good=await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,b64(parts[2]),utf8.encode(parts[0]+'.'+parts[1]));
 if(!good)throw Error('signature_bad');
 return {email:c.email.trim().toLowerCase(),aud:expectedAud};
}
