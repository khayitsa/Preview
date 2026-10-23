// READ-ONLY UI fixture. No authentication bypass and no access to real records.
// This script replaces network calls with fictional in-memory responses.
window.fetch=async function(url,options={}){
 window.assetUrl=a=>'/static/../../tests/browser-fixture/art'+(FIXTURE.assetMap[typeof a==='string'?a:a.id]??0)+'.svg';
 let value;
 if(options.method&&options.method!=='GET')return new Response(JSON.stringify({error:'This is a read-only fictional UI fixture. Run the main application to save changes.'}),{status:409,headers:{'Content-Type':'application/json'}});
 if(url==='/api/me')value=FIXTURE.me;
 else if(url==='/api/state')value=FIXTURE.state;
 else if(url.startsWith('/api/posts/'))value=FIXTURE.posts[url.split('/')[3]];
 else return new Response('{}',{status:404});
 // Static fixture images use data URIs so the main server never exposes test assets.
 window.assetUrl=a=>'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(FIXTURE_ART[FIXTURE.assetMap[typeof a==='string'?a:a.id]??0]);
 return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
};
