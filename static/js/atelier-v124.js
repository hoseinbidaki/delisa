/* DELISA v1.24 — accessible expanding header search and lazy real-category glass menu. */
(()=>{'use strict';
const header=document.querySelector('#site-header');
const searchButton=document.querySelector('#search-toggle');
const searchPane=document.querySelector('#search-overlay');
const searchInput=document.querySelector('#global-search-input');
const catButton=document.querySelector('#dl-category-toggle');
const catPanel=document.querySelector('#dl-category-panel');
const catLive=document.querySelector('#dl-live-categories');
if(!header||!searchButton||!searchPane||!catButton||!catPanel)return;
let catCloseTimer=0,catsRequested=false,searchFocusTimer=0,categoryPinned=false;
const searchOpen=()=>searchPane.classList.contains('open');
const catsOpen=()=>catPanel.classList.contains('is-open');
function reposition(){
 const h=header.getBoundingClientRect();
 const sb=searchButton.getBoundingClientRect();
 const cb=catButton.getBoundingClientRect();
 const panelWidth=Math.min(372,window.innerWidth-24);
 const openWidth=Math.min(610,window.innerWidth-24);
 const searchLeft=Math.max(12,Math.min(sb.left,window.innerWidth-56));
 const searchOpenLeft=Math.max(12,Math.min(searchLeft,window.innerWidth-openWidth-12));
 searchPane.style.setProperty('--dl-search-left',searchLeft+'px');
 searchPane.style.setProperty('--dl-search-open-left',searchOpenLeft+'px');
 searchPane.style.setProperty('--dl-search-top',Math.max(8,h.top+Math.max(0,(h.height-44)/2))+'px');
 catPanel.style.setProperty('--dl-cat-left',Math.max(12,Math.min(cb.left,window.innerWidth-panelWidth-12))+'px');
 catPanel.style.setProperty('--dl-header-bottom',Math.max(8,h.bottom+6)+'px');
}
function closeSearch(){
 clearTimeout(searchFocusTimer);
 if(!searchOpen())return;
 searchPane.classList.remove('open');
 searchPane.setAttribute('aria-hidden','true');
 searchButton.setAttribute('aria-expanded','false');
}
function openSearch(){
 closeCategories();reposition();
 searchPane.classList.add('open');
 searchPane.setAttribute('aria-hidden','false');
 searchButton.setAttribute('aria-expanded','true');
 searchFocusTimer=setTimeout(()=>{if(searchOpen())searchInput?.focus({preventScroll:true})},145);
}
// app.js binds a *bubble* click to open the old modal. Capture only this one
// trigger, while keeping app.js's existing form submit and live /api/search.
searchButton.setAttribute('aria-expanded','false');
searchButton.setAttribute('aria-controls','search-overlay');
searchButton.addEventListener('click',e=>{
 e.preventDefault();e.stopImmediatePropagation();
 searchOpen()?closeSearch():openSearch();
},true);
searchPane.addEventListener('click',e=>{
 if(e.target.closest('a[href]'))closeSearch();
 if(e.target.closest('[data-close]'))closeSearch();
});

function closeCategories(){
 categoryPinned=false;clearTimeout(catCloseTimer);
 if(!catsOpen())return;
 catPanel.classList.remove('is-open');
 catPanel.setAttribute('aria-hidden','true');
 catButton.setAttribute('aria-expanded','false');
}
function renderCategories(categories){
 catLive.replaceChildren();
 if(!categories.length){
  const notice=document.createElement('span');notice.className='dl-category-loading';notice.textContent='همه دسته‌ها در فروشگاه در دسترس‌اند.';
  catLive.append(notice);return;
 }
 const fragment=document.createDocumentFragment();
 categories.forEach(cat=>{
  const a=document.createElement('a');a.href='/shop?category='+encodeURIComponent(cat);a.dataset.nav='';
  a.append(document.createTextNode(cat+' '));
  const arrow=document.createElement('span');arrow.setAttribute('aria-hidden','true');arrow.textContent='←';a.append(arrow);
  fragment.append(a);
 });
 catLive.append(fragment);
}
function parseCategories(root){
 const unique=new Set();
 root.querySelectorAll('.shop-cat-chip[href]').forEach(a=>{
  try{
   const target=new URL(a.getAttribute('href'),document.baseURI);
   const cat=target.searchParams.get('category');
   if(cat&&cat.trim())unique.add(cat.trim());
  }catch{}
 });
 if(!unique.size){
  root.querySelectorAll('select[name="category"] option').forEach(opt=>{
   if(opt.value.trim())unique.add(opt.value.trim());
  });
 }
 return [...unique].slice(0,50);
}
async function loadCategories(){
 if(catsRequested)return;
 const current=parseCategories(document.querySelector('#page-root')||document);
 if(current.length){catsRequested=true;renderCategories(current);return}
 catsRequested=true;
 try{
  const response=await fetch('/shop',{credentials:'same-origin',headers:{'Accept':'text/html'}});
  if(!response.ok)throw Error('category request failed');
  const parsed=new DOMParser().parseFromString(await response.text(),'text/html');
  renderCategories(parseCategories(parsed));
 }catch{
  // Exact catalog is unknown; never invent categories. All-products link stays useful.
  renderCategories([]);catsRequested=false;
 }
}
function openCategories(){
 closeSearch();clearTimeout(catCloseTimer);reposition();
 catPanel.classList.add('is-open');
 catPanel.setAttribute('aria-hidden','false');
 catButton.setAttribute('aria-expanded','true');
 loadCategories();
}
function scheduleClose(){if(categoryPinned)return;clearTimeout(catCloseTimer);catCloseTimer=setTimeout(()=>{if(!catPanel.matches(':hover')&&!catButton.matches(':hover')&&!catPanel.contains(document.activeElement))closeCategories()},190)}
catButton.addEventListener('click',e=>{
 e.preventDefault();e.stopPropagation();
 if(catsOpen()&&categoryPinned){closeCategories();return;}
 categoryPinned=true;openCategories();
});
if(window.matchMedia('(hover:hover) and (pointer:fine)').matches){
 catButton.addEventListener('pointerenter',openCategories);
 catButton.addEventListener('pointerleave',scheduleClose);
 catPanel.addEventListener('pointerenter',()=>clearTimeout(catCloseTimer));
 catPanel.addEventListener('pointerleave',scheduleClose);
}
catPanel.addEventListener('click',e=>{if(e.target.closest('a[href]'))closeCategories()});
catPanel.addEventListener('focusout',scheduleClose);

document.addEventListener('pointerdown',e=>{
 if(searchOpen()&&!searchPane.contains(e.target)&&!searchButton.contains(e.target))closeSearch();
 if(catsOpen()&&!catPanel.contains(e.target)&&!catButton.contains(e.target))closeCategories();
},true);
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'){const wasOpen=searchOpen()||catsOpen();closeSearch();closeCategories();if(wasOpen)searchButton.blur()}
});
let raf=0;
function onMove(){if(!searchOpen()&&!catsOpen())return;if(raf)return;raf=requestAnimationFrame(()=>{raf=0;reposition()})}
window.addEventListener('resize',onMove,{passive:true});
window.addEventListener('scroll',onMove,{passive:true});
if('MutationObserver' in window){
 const main=document.querySelector('#page-root');
 if(main)new MutationObserver(()=>{closeSearch();closeCategories()}).observe(main,{childList:true,subtree:false});
}
})();
