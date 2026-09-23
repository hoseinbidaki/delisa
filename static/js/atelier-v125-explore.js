/* DELISA v1.25.1 - Explore videos: lightweight, one playing video at a time. */
(()=>{
'use strict';
const numeral = n => new Intl.NumberFormat('fa-IR').format(n);
const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
const root=document.querySelector('[data-explore-page]');
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
// Start with audio requested. A browser can reject unmuted autoplay;
// then offer a one-tap explicit audio unlock rather than pretending it worked.
let soundPreference=true, soundBlocked=false;
const bottomNav=document.querySelector('#mobile-bottom-nav');
function fitViewer(){
  if(!viewer.isConnected)return;
  const screenHeight=window.visualViewport?.height||window.innerHeight;
  const navBox=bottomNav?.getBoundingClientRect();
  const navVisible=navBox&&navBox.width>0&&navBox.height>0;
  const navTop=navVisible?navBox.top:screenHeight-16;
  const viewerTop=viewer.getBoundingClientRect().top;
  const available=Math.floor(Math.min(screenHeight-12,navTop-12)-viewerTop);
  // On extremely short viewports let the page itself scroll rather than
  // letting the nav cover a full-size movie or collapsing the player.
  const height=Math.min(760,Math.max(225,available));
  const width=Math.max(1,Math.min(580,root.clientWidth,Math.floor(height*9/16)));
  viewer.style.setProperty('--exp-available-height',height+'px');
  viewer.style.height=height+'px';
  viewer.style.width=width+'px';
}
let fitFrame=0;
function requestFit(){
  if(fitFrame)return;
  fitFrame=requestAnimationFrame(()=>{fitFrame=0;fitViewer()});
}
window.addEventListener('resize',requestFit,{passive:true});
window.addEventListener('orientationchange',requestFit,{passive:true});
window.visualViewport?.addEventListener('resize',requestFit,{passive:true});
requestFit();

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
  const image=el('img','exp-poster');image.src=p.poster;image.alt='';image.loading=index<2?'eager':'lazy';image.decoding='async';
  const video=el('video','exp-video');video.muted=!soundPreference;video.playsInline=true;video.setAttribute('playsinline','');video.preload='none';video.loop=true;video.disablePictureInPicture=true;video.setAttribute('controlsList','nodownload noremoteplayback');
  const veil=el('div','exp-shade');
  const wait=el('div','exp-video-loading');const spinner=el('span','exp-spinner');wait.append(spinner);wait.setAttribute('aria-label','در حال بارگذاری ویدئو');
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
  const product=el('a','exp-product');product.href=p.product_url;const thumb=el('img');thumb.src=p.poster;thumb.alt='';thumb.loading='lazy';thumb.width=42;thumb.height=50;
  const ptitle=el('span');ptitle.append(el('strong','',p.product_name),el('small','',p.stock>0?'دیدن محصول و انتخاب رنگ':'مشاهده جزئیات محصول'));
  const arr=el('span','exp-product-arrow','←');product.append(thumb,ptitle,arr);
  info.append(ey,heading,caption,product);
  stage.append(image,video,veil,wait,tap,sidebar,info,soundUnlock);
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
function message(text){const box=el('div','exp-toast',text);root.append(box);setTimeout(()=>box.remove(),3200)}
function attach(card,preload){const video=card._video;if(video.dataset.loaded==='1')return;
  video.dataset.loaded='1';video.preload=preload?'metadata':'auto';video.src='/explore/media/'+card.dataset.postId;
}
function release(card){if(!card)return;const video=card._video;video.pause();if(video.dataset.loaded==='1'){
  video.removeAttribute('src');video.load();video.dataset.loaded='0';card.classList.remove('has-frame','is-paused','is-buffering')
}}
async function play(card){if(!card||document.hidden)return;
  attach(card,false);
  const video=card._video;
  const trySound=soundPreference&&!soundBlocked;
  video.muted=!trySound;
  updateSoundUI(card);
  card.classList.add('is-buffering');
  try{await video.play()}catch(err){
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
  if(index<0||index>=posts.length||index===active)return;
  const previous=active;active=index;
  posts.forEach((card,i)=>{
    if(Math.abs(i-index)>1)release(card);
    else if(i===index){if(navigator.connection?.saveData)card.classList.add('is-paused');else play(card)}
    else if(canPreload())attach(card,true);
    if(i!==index)card._video.pause();
  });
  if(previous!==index&&nextCursor&&posts.length-index<3)loadMore();
}
function currentIndex(){
  const center=viewer.getBoundingClientRect().top+viewer.clientHeight/2;
  let closest=0,diff=Infinity;
  posts.forEach((card,i)=>{const r=card.getBoundingClientRect();const delta=Math.abs((r.top+r.bottom)/2-center);if(delta<diff){diff=delta;closest=i}});
  return closest;
}
let scrollFrame=0;
viewer.addEventListener('scroll',()=>{if(scrollFrame)return;scrollFrame=requestAnimationFrame(()=>{scrollFrame=0;show(currentIndex())})},{passive:true});
document.addEventListener('visibilitychange',()=>{if(document.hidden){posts.forEach(c=>c._video.pause())}else if(active>=0&&!navigator.connection?.saveData)play(posts[active])});
async function loadMore(){
  if(loading||hasLoaded&&!nextCursor)return;
  loading=true;
  try{
    const resp=await fetch('/api/explore'+(nextCursor?'?after='+encodeURIComponent(nextCursor):''),{credentials:'same-origin',headers:{'Accept':'application/json'}});
    if(!resp.ok)throw Error('اکسپلور در دسترس نیست.');
    const data=await resp.json();
    initial?.remove();
    for(const p of data.posts){const card=makeCard(p,posts.length);posts.push(card);viewer.append(card)}
    nextCursor=data.next;hasLoaded=true;
    if(!posts.length){const empty=el('div','exp-empty');empty.append(el('h2','','اکسپلور دلیسا به‌زودی…'),el('p','','به‌زودی ویدئوهای تازه اینجا می‌بینی.'));viewer.append(empty)}
    if(!nextCursor&&posts.length)end.hidden=false;
    if(active<0&&posts.length)show(0);
  }catch(err){if(!hasLoaded&&initial){initial.replaceChildren(el('span','',err.message));const retry=el('button','','تلاش دوباره');retry.type='button';retry.onclick=loadMore;initial.append(retry)}else message(err.message)}
  finally{loading=false}
}
loadMore();
setTimeout(requestFit,120);
})();
