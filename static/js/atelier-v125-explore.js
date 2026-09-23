/* DELISA v1.27 - Explore: release media on exit, bounded work per swipe. */
(()=>{
'use strict';
const numeral = n => new Intl.NumberFormat('fa-IR').format(n);
const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
const root=document.querySelector('[data-explore-page]');
if(root)document.body.classList.add('exp-mode');
const pageRoot=document.querySelector('#page-root');
// The cleanup observer is installed below, after media state has been initialized.
const upload=document.querySelector('[data-explore-upload]');
if(upload){
  const fileInput=upload.querySelector('input[name="video"]');
  const button=upload.querySelector('[data-upload-button]');
  const box=upload.querySelector('[data-upload-progress]');
  const bar=upload.querySelector('[data-upload-bar]');
  const label=upload.querySelector('[data-upload-label]');
  const error=upload.querySelector('[data-upload-error]');
  upload.addEventListener('submit',e=>{
    e.preventDefault();
    if(!upload.reportValidity())return;
    const file=fileInput.files?.[0];
    if(!file)return;
    if(file.size>20*1024*1024){error.textContent='ویدئو باید کمتر از ۲۰ مگابایت باشد.';error.hidden=false;return}
    if(!/\.mp4$/i.test(file.name)){error.textContent='فقط فایل MP4 قابل انتشار است.';error.hidden=false;return}
    error.hidden=true;box.hidden=false;button.disabled=true;
    const xhr=new XMLHttpRequest();
    xhr.open('POST',upload.action,true);
    xhr.withCredentials=true;
    xhr.setRequestHeader('Accept','application/json');
    xhr.setRequestHeader('X-CSRF-Token',csrf());
    xhr.upload.onprogress=ev=>{
      if(!ev.lengthComputable)return;
      const pct=Math.round(ev.loaded/ev.total*100);
      bar.value=pct;label.textContent=numeral(pct)+'٪';
    };
    const finish=(message)=>{button.disabled=false;box.hidden=true;error.textContent=message;error.hidden=false};
    xhr.onerror=()=>finish('اتصال قطع شد. دوباره تلاش کن.');
    xhr.onabort=()=>finish('ارسال لغو شد.');
    xhr.onload=()=>{
      if(xhr.status>=200&&xhr.status<400){location.href='/admin/explore?posted=1';return}
      let message='ویدئو منتشر نشد. فایل و اتصال را بررسی کن.';
      try{const data=JSON.parse(xhr.responseText);message=data.error||message}catch{}
      finish(message);
    };
    xhr.send(new FormData(upload));
  });
}
if(!root)return;
const viewer=root.querySelector('[data-explore-viewer]');
const initial=root.querySelector('[data-explore-initial]');
const end=root.querySelector('[data-explore-end]');
let posts=[],loading=false,nextCursor=null,hasLoaded=false,active=-1;
let disposed=false,mediaReleased=false,scrollFrame=0,wheelLocked=false,wheelTimer=0;
const loadedCards=new Set();
let feedController=null;
// Leaving is a fast, bounded action. Do NOT call video.load() synchronously
// on the click path: cancelling/decoding media there delays native and SPA nav.
function cleanupExplore(deep=false){
  if(!disposed){
    disposed=true;
    if(feedController){feedController.abort();feedController=null}
    if(scrollFrame){cancelAnimationFrame(scrollFrame);scrollFrame=0}
    if(wheelTimer){clearTimeout(wheelTimer);wheelTimer=0}
    // Two videos at most can have sources; pausing does not flush the decoder.
    for(const card of loadedCards)card._video.pause();
    active=-1;
  }
  if(deep&&!mediaReleased){
    mediaReleased=true;
    for(const card of Array.from(loadedCards))release(card);
  }
}
function deepCleanupAfterPaint(){
  // Let destination paint first. The browser also releases detached videos.
  if('requestIdleCallback' in window)requestIdleCallback(()=>cleanupExplore(true),{timeout:2500});
  else setTimeout(()=>cleanupExplore(true),500);
}
function navigationClick(event){
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.altKey||event.shiftKey)return;
  const target=event.target.closest?.('a[href],#mobile-nav-back');
  if(!target)return;
  let leaving=target.id==='mobile-nav-back';
  if(!leaving){
    try{const url=new URL(target.href,location.href);
      leaving=url.origin!==location.origin||url.pathname!==location.pathname||url.search!==location.search;
    }catch{return}
  }
  if(!leaving)return;
  cleanupExplore(false);
  if(target.closest('#mobile-bottom-nav')&&target.id!=='mobile-cart-toggle'){
    // Immediate visual feedback if a native account navigation needs network.
    document.body.classList.toggle('exp-going-account',target.dataset.bottomRoute==='account');
    document.body.classList.add('exp-route-leaving');
  }
}
document.addEventListener('click',navigationClick,true);
window.addEventListener('pagehide',()=>cleanupExplore(false),{once:true});
window.addEventListener('pageshow',event=>{
  if(event.persisted&&disposed&&location.pathname==='/explore')location.reload();
});
window.addEventListener('popstate',()=>{if(location.pathname!=='/explore')cleanupExplore(false)});
if(pageRoot&&'MutationObserver' in window){
  const observer=new MutationObserver(()=>{
    if(!root.isConnected||!pageRoot.querySelector('[data-explore-page]')){
      cleanupExplore(false);
      document.body.classList.remove('exp-mode','exp-route-leaving');
      deepCleanupAfterPaint();
      observer.disconnect();
    }
  });
  observer.observe(pageRoot,{childList:true});
}

// Start with audio requested. A browser can reject unmuted autoplay;
// then offer a one-tap explicit audio unlock rather than pretending it worked.
let soundPreference=true, soundBlocked=false;
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const canPreload=()=>{
  const c=navigator.connection;
  return !c?.saveData && !/2g/.test(c?.effectiveType||'');
};
function svg(path){const el=document.createElementNS('http://www.w3.org/2000/svg','svg');el.setAttribute('viewBox','0 0 24 24');el.setAttribute('aria-hidden','true');const p=document.createElementNS(el.namespaceURI,'path');p.setAttribute('d',path);el.append(p);return el}
function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node}
function makeCard(p,index){
  const card=el('article','exp-post');card.dataset.index=index;card.dataset.postId=p.id;
  card.setAttribute('aria-label','ویدئو: '+(p.caption||p.product_name));
  const stage=el('div','exp-stage');
  const backdrop=el('img','exp-backdrop');backdrop.src=p.poster;backdrop.alt='';backdrop.loading=index<2?'eager':'lazy';backdrop.decoding='async';
  const image=el('img','exp-media-poster');image.src=p.poster;image.alt='';image.loading=index<2?'eager':'lazy';image.decoding='async';
  const video=el('video','exp-video');video.muted=false;video.defaultMuted=false;video.playsInline=true;video.setAttribute('playsinline','');video.preload='none';video.loop=true;video.disablePictureInPicture=true;video.setAttribute('controlsList','nodownload noremoteplayback');
  const veil=el('div','exp-shade');
  const wait=el('div','exp-video-loading');const spinner=el('span','exp-spinner');const loadText=el('span','exp-loading-text','در حال بارگذاری');wait.append(spinner,loadText);wait.setAttribute('aria-label','در حال بارگذاری ویدئو');
  const tap=el('button','exp-play-toggle');tap.type='button';tap.setAttribute('aria-label','توقف یا پخش ویدئو');tap.append(svg('M9 6h2v12H9zM14 6h2v12h-2z'));
  const sidebar=el('div','exp-sidebar');
  const like=el('button','exp-action exp-like');like.type='button';like.setAttribute('aria-label','پسندیدن ویدئو');like.setAttribute('aria-pressed',p.liked?'true':'false');
  like.append(svg('M20.8 8.3c0 4.2-8.8 10.8-8.8 10.8S3.2 12.5 3.2 8.3a4.5 4.5 0 0 1 8.8-1.2 4.5 4.5 0 0 1 8.8 1.2Z'));
  const likeCount=el('small','',numeral(p.likes));like.append(likeCount);
  const mute=el('button','exp-action exp-mute');mute.type='button';mute.setAttribute('aria-label',soundPreference?'قطع صدا':'فعال‌کردن صدا');mute.append(svg(soundPreference?'M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12':'M4 9h4l5-4v14l-5-4H4zM17 9l4 6M21 9l-4 6'));
  const muteLabel=el('small','','');mute.append(muteLabel);
  const soundUnlock=el('button','exp-sound-unlock');soundUnlock.append(svg('M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12'),el('span','','پخش با صدا'));
  soundUnlock.type='button';soundUnlock.hidden=true;
  soundUnlock.setAttribute('aria-label','پخش ویدئو با صدا');
  sidebar.append(like,mute);
  const info=el('div','exp-info');const ey=el('span','exp-eyebrow','دلیسا / اکسپلور');
  const heading=el('h2','',p.product_name);const caption=el('p','',p.caption||'');
  const product=el('a','exp-product');product.href=p.product_url;const thumb=el('img');thumb.src=p.poster;thumb.alt='';thumb.loading='lazy';thumb.width=27;thumb.height=30;
  const ptitle=el('span');ptitle.append(el('strong','',p.product_name),el('small','',p.stock>0?'دیدن محصول و انتخاب رنگ':'مشاهده جزئیات محصول'));
  const arr=el('span','exp-product-arrow','←');product.append(thumb,ptitle,arr);
  info.append(ey,heading,caption,product);
  stage.append(backdrop,image,video,veil,wait,tap,sidebar,info,soundUnlock);
  card.append(stage);
  card._video=video;card._wait=wait;card._like=like;card._count=likeCount;card._mute=mute;card._soundUnlock=soundUnlock;
  let liked=p.liked;
  let busy=false;
  like.addEventListener('click',async()=>{
    if(busy)return;busy=true;like.disabled=true;
    try{
      const resp=await fetch('/api/explore/like',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf(),'Accept':'application/json'},body:JSON.stringify({post_id:p.id})});
      const data=await resp.json();
      if(!resp.ok)throw Error(data.error||'امکان ثبت پسند نیست.');
      liked=data.liked;like.setAttribute('aria-pressed',liked?'true':'false');likeCount.textContent=numeral(data.likes);
    }catch(err){message(err.message)}finally{busy=false;like.disabled=false}
  });
  mute.addEventListener('click',()=>{
    if(video.muted){unlockSound(card)}
    else{soundPreference=false;soundBlocked=false;video.muted=true;updateSoundUI(card)}
  });
  soundUnlock.addEventListener('click',()=>unlockSound(card));
  tap.addEventListener('click',()=>{
    if(video.paused){play(card)}else{video.pause();card.classList.add('is-paused')}
  });
  video.addEventListener('waiting',()=>card.classList.add('is-buffering'));
  video.addEventListener('loadstart',()=>card.classList.add('is-buffering'));
  video.addEventListener('canplay',()=>card.classList.remove('is-buffering'));
  video.addEventListener('playing',()=>{card.classList.remove('is-buffering','is-paused','is-error');card.classList.add('has-frame');tap.firstChild.querySelector('path').setAttribute('d','M9 6h2v12H9zM14 6h2v12h-2z')});
  video.addEventListener('pause',()=>{if(Number(card.dataset.index)===active){card.classList.add('is-paused');tap.firstChild.querySelector('path').setAttribute('d','M8 5.5 19 12 8 18.5z')}});
  video.addEventListener('error',()=>{card.classList.add('is-error');card.classList.remove('is-buffering');wait.replaceChildren(el('span','','پخش این ویدئو ممکن نیست.'))});
  return card;
}
function updateSoundUI(card){
  const muted=card._video.muted;
  card._mute.setAttribute('aria-label',muted?'فعال‌کردن صدا':'قطع صدا');
  card._mute.firstChild.querySelector('path').setAttribute('d',muted?'M4 9h4l5-4v14l-5-4H4zM17 9l4 6M21 9l-4 6':'M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12');
  card._soundUnlock.hidden=!muted||!soundPreference;
}
function unlockSound(card){
  soundPreference=true;soundBlocked=false;
  const video=card._video;
  video.muted=false;
  updateSoundUI(card);
  // Executed directly from click/tap so the browser sees user activation.
  if(video.paused){
    attach(card,false);
    const started=video.play();
    if(started?.catch)started.catch(err=>{
      if(err.name==='NotAllowedError'){
        soundBlocked=true;video.muted=true;updateSoundUI(card);
        video.play().catch(()=>{});
      }else if(err.name!=='AbortError'){card.classList.add('is-paused')}
    });
  }
}
function message(text){if(disposed||!root.isConnected)return;const box=el('div','exp-toast',text);root.append(box);setTimeout(()=>box.remove(),3200)}
function attach(card,preload){
  if(disposed||!card||!card.isConnected)return;
  const video=card._video;if(video.dataset.loaded==='1')return;
  video.dataset.loaded='1';loadedCards.add(card);
  video.preload=preload?'metadata':'auto';video.src='/explore/media/'+card.dataset.postId;
}
function release(card){
  if(!card)return;
  const video=card._video;
  video.pause();
  if(video.dataset.loaded==='1'){
    video.dataset.loaded='0';loadedCards.delete(card);
    video.removeAttribute('src');video.preload='none';
    // Only cards with active network media need load() to cancel their fetch/decoder.
    video.load();card.classList.remove('has-frame','is-paused','is-buffering','is-current');
  }
}
async function play(card){if(disposed||!root.isConnected||!card||document.hidden)return;
  attach(card,false);
  const video=card._video;
  const trySound=soundPreference&&!soundBlocked;
  video.muted=!trySound;
  updateSoundUI(card);
  card.classList.add('is-buffering');
  try{await video.play()}catch(err){
    if(disposed||!root.isConnected)return;
    // Chrome/Edge/Safari often block sound until the viewer has tapped once.
    // Keep the feed moving without sound, and expose a visible sound button.
    if(err.name==='NotAllowedError'&&trySound){
      soundBlocked=true;video.muted=true;updateSoundUI(card);
      try{await video.play()}catch(fallbackErr){
        card.classList.remove('is-buffering');
        if(fallbackErr.name!=='AbortError')card.classList.add('is-paused');
      }
    }else{
      card.classList.remove('is-buffering');
      if(err.name!=='AbortError')card.classList.add('is-paused');
    }
  }
}
function show(index){
  if(disposed||!root.isConnected||index<0||index>=posts.length||index===active)return;
  const previous=active;active=index;
  // At most 2 sources stay attached (current and next metadata). No O(n)
  // video src churn and no layout measurement on every swipe.
  for(const card of Array.from(loadedCards)){
    const distance=Number(card.dataset.index)-index;
    if(distance!==0&&distance!==1)release(card);
    else if(distance===1)card._video.pause();
  }
  if(previous>=0&&posts[previous]&&previous!==index){
    posts[previous].classList.remove('is-current');
    posts[previous]._video.pause();
  }
  const current=posts[index];current.classList.add('is-current');
  if(navigator.connection?.saveData)current.classList.add('is-paused');
  else play(current);
  const next=posts[index+1];
  if(next&&canPreload())attach(next,true);
  if(nextCursor&&posts.length-index<3)loadMore();
}
function currentIndex(){
  if(!posts.length||!viewer.clientHeight)return 0;
  return Math.max(0,Math.min(posts.length-1,Math.round(viewer.scrollTop/viewer.clientHeight)));
}
viewer.addEventListener('scroll',()=>{
  if(disposed||scrollFrame)return;
  scrollFrame=requestAnimationFrame(()=>{scrollFrame=0;if(!disposed)show(currentIndex())});
},{passive:true});
viewer.addEventListener('wheel',e=>{
  if(disposed||Math.abs(e.deltaY)<12||posts.length<2)return;
  e.preventDefault();
  if(wheelLocked)return;
  wheelLocked=true;
  const target=Math.max(0,Math.min(posts.length-1,(active<0?0:active)+(e.deltaY>0?1:-1)));
  viewer.scrollTo({top:target*viewer.clientHeight,behavior:reduced?'auto':'smooth'});
  show(target);
  wheelTimer=setTimeout(()=>{wheelLocked=false;wheelTimer=0},reduced?80:430);
},{passive:false});
root.addEventListener('pointerdown',e=>{
  if(disposed||!soundBlocked||active<0||e.target.closest('button,a'))return;
  unlockSound(posts[active]);
},{passive:true});
document.addEventListener('visibilitychange',()=>{
  if(disposed)return;
  if(document.hidden){for(const card of loadedCards)card._video.pause()}
  else if(active>=0&&!navigator.connection?.saveData)play(posts[active]);
});
async function loadMore(){
  if(disposed||loading||(hasLoaded&&!nextCursor))return;
  loading=true;
  const controller=new AbortController();feedController=controller;
  try{
    const resp=await fetch('/api/explore'+(nextCursor?'?after='+encodeURIComponent(nextCursor):''),{
      credentials:'same-origin',headers:{'Accept':'application/json'},signal:controller.signal
    });
    if(disposed||!root.isConnected)return;
    if(!resp.ok)throw Error('اکسپلور در دسترس نیست.');
    const data=await resp.json();
    if(disposed||!root.isConnected)return;
    initial?.remove();
    const fragment=document.createDocumentFragment();
    for(const p of data.posts){const card=makeCard(p,posts.length);posts.push(card);fragment.append(card)}
    viewer.append(fragment);
    nextCursor=data.next;hasLoaded=true;
    if(!posts.length){const empty=el('div','exp-empty');empty.append(el('h2','','اکسپلور دلیسا به‌زودی…'),el('p','','به‌زودی ویدئوهای تازه اینجا می‌بینی.'));viewer.append(empty)}
    if(!nextCursor&&posts.length)end.hidden=false;
    if(active<0&&posts.length)show(0);
  }catch(err){
    if(disposed||err.name==='AbortError')return;
    if(!hasLoaded&&initial){initial.replaceChildren(el('span','',err.message));const retry=el('button','','تلاش دوباره');retry.type='button';retry.onclick=loadMore;initial.append(retry)}
    else message(err.message);
  }finally{if(feedController===controller)feedController=null;loading=false}
}
loadMore();
})();
