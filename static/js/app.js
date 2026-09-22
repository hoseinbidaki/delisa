/* DELISA v1.3 / progressive navigation; plain JavaScript, no build tools. */
(()=>{
'use strict';
const csrf=()=>document.querySelector('meta[name="csrf-token"]')?.content||'';
const main=document.querySelector('#page-root');
if('scrollRestoration' in history)history.scrollRestoration='manual';
const backdrop=document.querySelector('#backdrop');
const cartDrawer=document.querySelector('#cart-drawer');
const menuDrawer=document.querySelector('#menu-drawer');
const searchOverlay=document.querySelector('#search-overlay');
let navigating=0, searchTimer, toastTimer;
let pendingNavigation=null;
const pageCache=new Map(),inflightPrefetch=new Map(),pageScroll=new Map(),MAX_CACHED=18,CACHE_TTL=25000;
let loaderTimer=null,prefetchTimer=null,scrollTimer=null,backdropTimer=null;
const numeral=n=>new Intl.NumberFormat('fa-IR').format(n);
const currency=n=>numeral(n)+' تومان';
const escapeText=t=>String(t??'');
function toast(message){const el=document.querySelector('#toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),3200)}
function openOverlay(el){closeOverlays(true);el.classList.add('open');el.setAttribute('aria-hidden','false');backdrop.hidden=false;document.body.classList.add('lock');requestAnimationFrame(()=>backdrop.classList.add('show'))}
function closeOverlays(immediate=false){[cartDrawer,menuDrawer,searchOverlay].filter(Boolean).forEach(el=>{el.classList.remove('open');el.setAttribute('aria-hidden','true')});backdrop.classList.remove('show');clearTimeout(backdropTimer);if(immediate===true){backdrop.hidden=true}else{backdropTimer=setTimeout(()=>{if(!backdrop.classList.contains('show'))backdrop.hidden=true},280)}document.body.classList.remove('lock')}
backdrop.addEventListener('click',closeOverlays);
document.addEventListener('click',e=>{if(e.target.closest('[data-close]'))closeOverlays()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeOverlays()});
document.querySelector('#menu-toggle')?.addEventListener('click',()=>openOverlay(menuDrawer));
document.querySelector('#cart-toggle')?.addEventListener('click',()=>{openOverlay(cartDrawer);refreshCart()});
document.querySelector('#search-toggle')?.addEventListener('click',()=>{openOverlay(searchOverlay);setTimeout(()=>document.querySelector('#global-search-input').focus(),140)});
async function api(path,data){const response=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf(),'Accept':'application/json'},body:JSON.stringify(data)});let result={};try{result=await response.json()}catch{}if(!response.ok)throw new Error(result.error||'درخواست انجام نشد');return result}
function textNode(tag,text,cls=''){const n=document.createElement(tag);n.textContent=escapeText(text);if(cls)n.className=cls;return n}
function createCartLine(item){
const row=document.createElement('div');row.className='cart-line';
const img=document.createElement('img');img.src=item.image;img.alt=item.name;img.width=65;img.height=85;row.append(img);
const body=document.createElement('div');body.append(textNode('b',item.name));if(item.color)body.append(textNode('small','رنگ: '+item.color,'muted'));body.append(textNode('div',currency(item.price),'muted'));
const actions=document.createElement('div');actions.className='cart-actions';
const minus=textNode('button','−');minus.type='button';const plus=textNode('button','+');plus.type='button';
const qty=textNode('span',numeral(item.qty));actions.append(minus,qty,plus);body.append(actions);row.append(body);
const remove=textNode('button','حذف','remove');remove.type='button';row.append(remove);
const change=async diff=>{try{const state=await api('/api/cart',{product_id:item.product_id,color:item.color||'',qty:diff});paintCart(state)}catch(err){toast(err.message)}};
minus.addEventListener('click',()=>change(-1));plus.addEventListener('click',()=>change(1));
remove.addEventListener('click',async()=>{try{paintCart(await api('/api/cart/remove',{product_id:item.product_id,color:item.color||''}))}catch(err){toast(err.message)}});
return row;
}
function paintCart(data){
 document.querySelector('#cart-count').textContent=numeral(data.count||0);
 const content=document.querySelector('#cart-content'),foot=document.querySelector('#cart-foot');
 content.replaceChildren();foot.replaceChildren();
 if(!data.items.length){content.append(textNode('p','سبد خریدت هنوز خالیه.','muted'));const a=textNode('a','دیدن محصولات','btn');a.href='/shop';a.dataset.nav='';a.addEventListener('click',closeOverlays);foot.append(a);return}
 data.items.forEach(x=>content.append(createCartLine(x)));
 const summary=textNode('div','');summary.className='summary-line total';summary.append(textNode('span','جمع کل'),textNode('strong',currency(data.total)));foot.append(summary);
 const checkout=textNode('a','ادامه و ثبت سفارش ←','btn');checkout.href='/checkout';checkout.dataset.nav='';checkout.addEventListener('click',closeOverlays);foot.append(checkout);
}
async function refreshCart(){try{const r=await fetch('/api/cart',{credentials:'same-origin'});if(!r.ok)throw new Error();paintCart(await r.json())}catch{toast('دریافت سبد خرید ممکن نیست.')}}
refreshCart();
// Public catalog pages use soft navigation; auth, checkout, and admin are native URLs.
// A failed/slow request NEVER leaves an inert link: first click falls back to native.
const PUBLIC_PATH=/^(?:\/$|\/shop$|\/product\/[^/]+$)/;
function urlFor(href){try{return new URL(href,location.href)}catch{return null}}
function eligible(link,event){
 if(!link||event?.defaultPrevented||(event?.button!==undefined&&event.button!==0)||
   event?.metaKey||event?.ctrlKey||event?.altKey||event?.shiftKey||
   link.hasAttribute('download')||(link.target&&link.target!=='_self'))return false;
 const url=urlFor(link.href);
 return !!url && url.origin===location.origin && PUBLIC_PATH.test(url.pathname);
}
function keyOf(url){return url.pathname+url.search}
let activeKey=keyOf(new URL(location.href));
function remember(key,page){
 pageCache.delete(key);pageCache.set(key,{...page,at:Date.now()});
 while(pageCache.size>MAX_CACHED)pageCache.delete(pageCache.keys().next().value);
}
function cached(key){
 const item=pageCache.get(key);
 if(!item)return null;
 if(Date.now()-item.at>CACHE_TTL){pageCache.delete(key);return null}
 return item;
}
function currentPage(){return {markup:main.innerHTML,title:document.title,description:document.querySelector('meta[name="description"]')?.content||''}}
function rememberScroll(){
 history.replaceState({...history.state,scrollY:window.scrollY},'',location.href);
}
function restoreScroll(y=0){
 requestAnimationFrame(()=>requestAnimationFrame(()=>window.scrollTo({top:y,behavior:'instant'})));
}
function nativeNavigation(url,replace=false){
 clearTimeout(loaderTimer);document.documentElement.classList.remove('delisa-loading');
 if(replace)location.replace(url);else location.assign(url);
}
async function fetchPage(url,signal){
 const response=await fetch(keyOf(url),{
  headers:{'X-Partial-Nav':'1','Accept':'text/html'},credentials:'same-origin',
  cache:'no-store',signal
 });
 if(response.redirected){nativeNavigation(response.url);throw Error('redirect')}
 if(!response.ok||!response.headers.get('Content-Type')?.includes('text/html'))throw Error('Invalid page response');
 const html=await response.text();
 const doc=new DOMParser().parseFromString(html,'text/html');
 const next=doc.querySelector('main#page-root');
 if(!next||next.dataset.pagePath!==url.pathname)throw Error('Unexpected page content');
 return {markup:next.innerHTML,title:doc.title,description:doc.querySelector('meta[name="description"]')?.content||''};
}
function updateActiveLinks(pathAndSearch){
 // /shop and /shop?sort=newest are different destinations: never mark both active.
 const current=urlFor(pathAndSearch);
 document.querySelectorAll('.desktop-nav a,.mobile-quick-nav a,.mobile-nav a').forEach(a=>{
  const target=urlFor(a.href);
  let active=false;
  if(target&&current){
   if(target.pathname==='/shop'&&current.pathname==='/shop'){
    const newIn=current.searchParams.get('sort')==='newest';
    active=(target.searchParams.get('sort')==='newest')===newIn;
   }else if(target.pathname===current.pathname&&target.pathname!=='/'){
    active=target.search===current.search;
   }
  }
  if(active)a.setAttribute('aria-current','page');
  else a.removeAttribute('aria-current');
 });
}
function showPage(page,url,scroll){
 main.innerHTML=page.markup;
 main.dataset.pagePath=url.pathname;
 document.title=page.title;
 const desc=document.querySelector('meta[name="description"]');if(desc)desc.content=page.description;
 updateActiveLinks(url.pathname+url.search);
 main.classList.remove('page-enter');void main.offsetWidth;main.classList.add('page-enter');
 restoreScroll(scroll);
 if(url.hash)setTimeout(()=>document.getElementById(decodeURIComponent(url.hash.slice(1)))?.scrollIntoView(),90);
}
async function navigate(href,{push=true,scroll=0}={}){
 const url=urlFor(href);
 if(!url){return}
 if(url.hash&&url.pathname===location.pathname&&url.search===location.search){closeOverlays();location.hash=url.hash;return}
 if(!PUBLIC_PATH.test(url.pathname)||url.origin!==location.origin){nativeNavigation(url.href);return}
 if(push&&url.href===location.href){closeOverlays();restoreScroll(0);return}
 const token=++navigating;
 if(pendingNavigation)pendingNavigation.abort();
 const controller=new AbortController();pendingNavigation=controller;
 closeOverlays();
 clearTimeout(loaderTimer);
 loaderTimer=setTimeout(()=>{if(token===navigating)document.documentElement.classList.add('delisa-loading')},130);
 const timer=setTimeout(()=>controller.abort(),4200);
 const target=keyOf(url);
 try{
  const prefetched=cached(target);
  const page=prefetched||await (inflightPrefetch.get(target)||fetchPage(url,controller.signal));
  if(token!==navigating)return;
  const from=activeKey;
  // Popstate has already changed location; activeKey still identifies outgoing DOM.
  pageScroll.set(from,window.scrollY);
  remember(from,currentPage());
  if(push){rememberScroll();history.pushState({scrollY:0},'',url.href)}
  remember(target,page);
  showPage(page,url,push?scroll:(pageScroll.get(target)??scroll));
  activeKey=target;
  if(push)api('/api/track-view',{path:url.pathname}).catch(()=>{});
 }catch(err){
  if(token===navigating&&err.message!=='redirect')nativeNavigation(url.href,!push);
 }finally{
  clearTimeout(timer);clearTimeout(loaderTimer);
  if(token===navigating){pendingNavigation=null;document.documentElement.classList.remove('delisa-loading')}
 }
}
function startPrefetch(anchor){
 if(!eligible(anchor)||navigator.connection?.saveData||['slow-2g','2g'].includes(navigator.connection?.effectiveType))return;
 const url=urlFor(anchor.href),key=keyOf(url);
 if(cached(key)||inflightPrefetch.has(key)||key===keyOf(new URL(location.href)))return;
 // Prefetch HTML only; image requests still obey lazy loading after insertion.
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),3500);
 const promise=fetchPage(url,controller.signal).then(page=>{remember(key,page);return page})
  .catch(()=>null).finally(()=>{clearTimeout(timer);inflightPrefetch.delete(key)});
 inflightPrefetch.set(key,promise);
}
// First document is already server rendered: no blank client-side boot screen.
remember(keyOf(new URL(location.href)),currentPage());
updateActiveLinks(location.pathname+location.search);
// Save position for browser reload; soft Back/Forward uses history state.
window.addEventListener('scroll',()=>{
 clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>{
  try{sessionStorage.setItem('delisa-last-position',JSON.stringify({url:location.pathname+location.search,y:scrollY}))}catch{}
 },170);
},{passive:true});
window.addEventListener('pagehide',()=>{
 try{sessionStorage.setItem('delisa-last-position',JSON.stringify({url:location.pathname+location.search,y:scrollY}))}catch{}
});
try{
 if(performance.getEntriesByType('navigation')[0]?.type==='reload'){
  const saved=JSON.parse(sessionStorage.getItem('delisa-last-position')||'null');
  if(saved?.url===location.pathname+location.search&&Number.isFinite(saved.y))setTimeout(()=>restoreScroll(saved.y),100);
 }
}catch{}
// Delegated links keep working in newly inserted cards and filtered results.
document.addEventListener('click',event=>{
 const anchor=event.target.closest?.('a[data-nav]');
 if(!eligible(anchor,event))return;
 const url=urlFor(anchor.href);
 if(url.hash&&url.pathname===location.pathname&&url.search===location.search){closeOverlays();return}
 event.preventDefault();navigate(anchor.href);
});
document.addEventListener('mouseover',event=>{
 const anchor=event.target.closest?.('a[data-nav]');if(!eligible(anchor))return;
 clearTimeout(prefetchTimer);prefetchTimer=setTimeout(()=>startPrefetch(anchor),110);
},{passive:true});
document.addEventListener('touchstart',event=>{
 const anchor=event.target.closest?.('a[data-nav]');if(eligible(anchor))startPrefetch(anchor);
},{passive:true});
window.addEventListener('popstate',event=>{
 if(!PUBLIC_PATH.test(location.pathname)){nativeNavigation(location.href,true);return}
 navigate(location.href,{push:false,scroll:event.state?.scrollY||0});
});
// Products/cart actions: delegated so they keep working after partial navigation.
document.addEventListener('click',async e=>{
 const add=e.target.closest('#add-to-cart');if(add){const qty=Number(document.querySelector('#product-qty')?.value||1);try{paintCart(await api('/api/cart',{product_id:Number(add.dataset.productId),color:document.querySelector('.color-option.is-selected')?.dataset.selectColor||'',qty}));openOverlay(cartDrawer);toast('به سبد خرید اضافه شد.')}catch(err){toast(err.message)}return}
 const fav=e.target.closest('[data-favorite]');if(fav){try{const r=await api('/api/favorites',{product_id:Number(fav.dataset.favorite)});fav.textContent=r.saved?'♥':'♡';toast(r.saved?'به علاقه‌مندی‌ها اضافه شد.':'از علاقه‌مندی‌ها حذف شد.')}catch(err){toast(err.message+' — برای ذخیره محصول ابتدا وارد شو.')}}
});
// Shop filter behaves like a tiny SPA; URL is shareable and browser Back works.
document.addEventListener('submit',e=>{const form=e.target;if(form.id!=='shop-filter'&&form.id!=='global-search-form')return;e.preventDefault();const query=new URLSearchParams(new FormData(form)).toString();navigate('/shop?'+query)});
// Fast, abortable live search; no third-party library or page reload.
const search=document.querySelector('#global-search-input');
const searchResults=document.querySelector('#search-results');
const searchTips=document.querySelector('#search-suggestions');
const searchHeading=document.querySelector('#search-live-heading');
let searchRequest=null;
function searchState(query){
 searchTips.hidden=query.length>=2;
 searchHeading.hidden=query.length<2;
}
search.addEventListener('input',()=>{
 clearTimeout(searchTimer);
 searchRequest?.abort();searchRequest=null;
 const q=search.value.trim();searchResults.replaceChildren();searchState(q);
 if(q.length<2)return;
 const loading=textNode('p','در حال جستجو...','search-message');loading.setAttribute('role','status');searchResults.append(loading);
 searchTimer=setTimeout(async()=>{
  const controller=new AbortController();searchRequest=controller;
  try{
   const r=await fetch('/api/search?q='+encodeURIComponent(q),{signal:controller.signal,credentials:'same-origin'});
   if(!r.ok)throw Error('search');
   const data=await r.json();
   if(search.value.trim()!==q||controller.signal.aborted)return;
   searchResults.replaceChildren();
   if(!data.products.length){searchResults.append(textNode('p','محصولی پیدا نشد؛ عبارت دیگری امتحان کن.','search-message'));return}
   const fragment=document.createDocumentFragment();
   data.products.forEach(item=>{
    const a=document.createElement('a');a.href='/product/'+encodeURIComponent(item.slug);
    a.dataset.nav='';a.className='search-item';
    const img=document.createElement('img');img.src=item.image;img.alt='';img.loading='lazy';img.decoding='async';img.draggable=false;img.width=58;img.height=76;
    const copy=document.createElement('span');copy.className='search-result-copy';
    copy.append(textNode('b',item.name),textNode('small','مشاهده محصول ←'));
    a.append(img,copy,textNode('strong',currency(item.price)));
    a.addEventListener('click',closeOverlays);fragment.append(a);
   });searchResults.append(fragment);
  }catch(err){if(err.name!=='AbortError'&&search.value.trim()===q){searchResults.replaceChildren(textNode('p','جستجو در دسترس نیست؛ با دکمه جستجو امتحان کن.','search-message'))}}
 },180);
});
})();
