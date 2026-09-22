/* DELISA v1.16.3 mobile UX: internal Back + three-point cart sheet; no dependencies. */
(()=>{
'use strict';
const mobileNav=document.querySelector('#mobile-bottom-nav');
const back=document.querySelector('#mobile-nav-back');
const smallCart=document.querySelector('#mobile-cart-toggle');
const main=document.querySelector('#page-root');
const toast=document.querySelector('#toast');
const upload=document.querySelector('#delisa-upload-overlay');
const uploadTitle=document.querySelector('#upload-title');
const uploadDescription=document.querySelector('#upload-description');
const uploadProgress=document.querySelector('#upload-progress');
const uploadPercent=document.querySelector('#upload-percent');
const uploadCaption=document.querySelector('#upload-caption');
const uploadClose=document.querySelector('#upload-close');
let toastTimeout=0, busyControl=null, busyTimeout=0;
function alertUser(message){
 if(!toast)return;
 clearTimeout(toastTimeout);
 toast.textContent=message;
 toast.classList.add('show');
 toastTimeout=setTimeout(()=>toast.classList.remove('show'),3500);
}
function refreshMobileNav(){
 if(!mobileNav)return;
 const path=location.pathname;
  const chosen=path==='/'?'home':path==='/shop'?'shop':(path==='/account'||path.startsWith('/account/')||path==='/login'||path==='/register')?'account':'';
 mobileNav.querySelectorAll('[data-bottom-route]').forEach(link=>{
  if(link.dataset.bottomRoute===chosen)link.setAttribute('aria-current','page');
  else link.removeAttribute('aria-current');
 });
 const available=canGoBackWithinDelisa();
 mobileNav.classList.toggle('has-back',available);
 if(back)back.hidden=!available;
}
// Preserve SPA history depth across reloads; a direct visit never shows a fake Back.
const internalReferrer=(()=>{
 try{const from=new URL(document.referrer);return from.origin===location.origin&&from.pathname+from.search!==location.pathname+location.search}
 catch{return false}
})();
function canGoBackWithinDelisa(){
 if(location.pathname==='/'||history.length<=1)return false;
 return (Number(history.state?.delisaDepth)||0)>0||internalReferrer;
}
if(history.state?.delisaDepth==null){
 history.replaceState({...history.state,delisaDepth:0},'',location.href);
}
const originalPushState=history.pushState;
history.pushState=function(state,title,url){
 const depth=(Number(history.state?.delisaDepth)||0)+1;
 const next={...(state&&typeof state==='object'?state:{}),delisaDepth:depth};
 const result=originalPushState.call(this,next,title,url);
 requestAnimationFrame(refreshMobileNav);
 return result;
};
refreshMobileNav();
// The public-page router swaps only <main> and writes its data-page-path.
if(main&&'MutationObserver' in window){
 new MutationObserver(refreshMobileNav).observe(main,{attributes:true,attributeFilter:['data-page-path']});
}
window.addEventListener('popstate',()=>requestAnimationFrame(refreshMobileNav));
window.addEventListener('pageshow',refreshMobileNav);
if(back)back.addEventListener('click',()=>{
 if(canGoBackWithinDelisa())history.back();
});
if(smallCart)smallCart.addEventListener('click',()=>document.querySelector('#cart-toggle')?.click());
const cartCount=document.querySelector('#cart-count');
function mirrorCart(){
 const mirror=document.querySelector('.mobile-cart-count');
 if(mirror&&cartCount)mirror.textContent=cartCount.textContent.trim()||'0';
}
mirrorCart();
if(cartCount&&'MutationObserver' in window){new MutationObserver(mirrorCart).observe(cartCount,{childList:true,characterData:true,subtree:true});}
// The cart is a true three-point bottom sheet on touch devices: compact, middle,
// expanded. Dragging the top bar tracks the finger; releasing snaps to a detent.
const sheet=document.querySelector('#cart-drawer');
const sheetTop=sheet?.querySelector('.drawer-top');
const cartClose=sheet?.querySelector('[data-close]');
const mobileScreen=window.matchMedia('(max-width:760px)');
let sheetState='middle',gesture=null,drawFrame=0;
function sheetStops(){
 const viewport=window.visualViewport?.height||innerHeight;
 const max=Math.max(240,Math.floor(viewport-10));
 const compact=Math.min(max,Math.max(225,Math.round(viewport*.40)));
 const middle=Math.min(max,Math.max(compact+45,Math.round(viewport*.67)));
 const expanded=Math.min(max,Math.max(middle+40,Math.round(viewport*.92)));
 return {compact,middle,expanded};
}
function heightFor(state){return sheetStops()[state]||sheetStops().middle}
function setSheetHeight(height){
 if(sheet)sheet.style.setProperty('--delisa-sheet-height',Math.round(height)+'px');
}
function snapSheet(state){
 sheetState=state;
 sheet?.classList.remove('is-dragging');
 setSheetHeight(heightFor(state));
}
function nearestStop(height){
 const options=sheetStops();
 return Object.keys(options).reduce((best,k)=>Math.abs(options[k]-height)<Math.abs(options[best]-height)?k:best,'compact');
}
if(sheet&&sheetTop){
 // Only react when "open" changes. The drag class must not reset the gesture.
 let wasOpen=sheet.classList.contains('open');
 new MutationObserver(()=>{
  const isOpen=sheet.classList.contains('open');
  if(isOpen===wasOpen)return;
  wasOpen=isOpen;
  if(!mobileScreen.matches)return;
  if(isOpen){
   gesture=null;snapSheet('middle');
  }else{
   gesture=null;sheet.classList.remove('is-dragging');
  }
 }).observe(sheet,{attributes:true,attributeFilter:['class']});
 sheetTop.addEventListener('pointerdown',e=>{
  if(!mobileScreen.matches||!sheet.classList.contains('open')||e.target.closest('button,a')||!e.isPrimary)return;
  gesture={id:e.pointerId,startY:e.clientY,startHeight:sheet.getBoundingClientRect().height,lastY:e.clientY,lastTime:performance.now(),speed:0,currentHeight:sheet.getBoundingClientRect().height};
  sheet.classList.add('is-dragging');
  sheetTop.setPointerCapture(e.pointerId);
 });
 sheetTop.addEventListener('pointermove',e=>{
  if(!gesture||e.pointerId!==gesture.id)return;
  const now=performance.now(),dy=e.clientY-gesture.startY;
  const stops=sheetStops();
  const desired=Math.max(stops.compact*.47,Math.min(stops.expanded+22,gesture.startHeight-dy));
  const elapsed=Math.max(now-gesture.lastTime,1);
  gesture.speed=(e.clientY-gesture.lastY)/elapsed;
  gesture.lastY=e.clientY;gesture.lastTime=now;gesture.currentHeight=desired;
  if(drawFrame)cancelAnimationFrame(drawFrame);
  drawFrame=requestAnimationFrame(()=>setSheetHeight(desired));
  if(e.cancelable)e.preventDefault();
 });
 function finishGesture(e,cancelled=false){
  if(!gesture||e.pointerId!==gesture.id)return;
  if(drawFrame)cancelAnimationFrame(drawFrame);
  const g=gesture;gesture=null;sheet.classList.remove('is-dragging');
  const stops=sheetStops();
  const displacement=e.clientY-g.startY;
  if(!cancelled&&(g.currentHeight<stops.compact*.72||
      (g.startHeight<=stops.compact+16&&displacement>105&&g.speed>.35))){
   cartClose?.click();return;
  }
  const ordered=['compact','middle','expanded'];
  let next=nearestStop(g.currentHeight);
  if(!cancelled&&Math.abs(g.speed)>.55){
   const index=ordered.indexOf(nearestStop(g.currentHeight));
   next=ordered[Math.max(0,Math.min(2,index+(g.speed<0?1:-1)))];
  }
  snapSheet(next);
 }
 sheetTop.addEventListener('pointerup',e=>finishGesture(e));
 sheetTop.addEventListener('pointercancel',e=>finishGesture(e,true));
 window.addEventListener('resize',()=>{if(mobileScreen.matches&&sheet.classList.contains('open')&&!gesture)snapSheet(sheetState)},{passive:true});
 window.visualViewport?.addEventListener('resize',()=>{if(mobileScreen.matches&&sheet.classList.contains('open')&&!gesture)snapSheet(sheetState)},{passive:true});
}
// A spinner for actual asynchronous actions: cart, wishlist, and form requests.
function clearBusy(){
 if(busyControl){busyControl.classList.remove('is-busy');busyControl.removeAttribute('aria-busy');busyControl=null;}
 clearTimeout(busyTimeout);
}
function startBusy(control){
 clearBusy();
 if(!control)return;
 busyControl=control;control.classList.add('is-busy');control.setAttribute('aria-busy','true');
 busyTimeout=setTimeout(clearBusy,8500);
}
document.addEventListener('click',e=>{
 const actionable=e.target.closest?.('#add-to-cart,[data-favorite]');
 if(actionable){startBusy(actionable);return}
 const nativeButton=e.target.closest?.('button[type="submit"],input[type="submit"]');
 if(nativeButton&&nativeButton.form?.method?.toLowerCase()==='post'){
  // The product editor is handled by XHR below.
  if(nativeButton.form.closest('.product-editor'))return;
  setTimeout(()=>startBusy(nativeButton),140);
 }
},true);
// Existing cart/favourite code shows the toast on success or failure.
if(toast&&'MutationObserver' in window){
 new MutationObserver(()=>{
  if(toast.classList.contains('show'))clearBusy();
 }).observe(toast,{attributes:true,attributeFilter:['class']});
}
// Browser-native form submission remains intact for ordinary forms.
// Product photo submissions only are XHR-based, so real upload progress is available.
let uploading=false;
function showUpload(){
 if(!upload)return;
 upload.hidden=false;upload.setAttribute('aria-hidden','false');
 requestAnimationFrame(()=>upload.classList.add('open'));
}
function hideUpload(){
 if(!upload)return;
 upload.classList.remove('open');upload.setAttribute('aria-hidden','true');
 setTimeout(()=>{if(!upload.classList.contains('open'))upload.hidden=true},240);
}
if(uploadClose)uploadClose.addEventListener('click',hideUpload);
function uploadError(message){
 uploading=false;
 if(uploadTitle)uploadTitle.textContent='ذخیره انجام نشد';
 if(uploadDescription)uploadDescription.textContent='اطلاعات فرم حفظ شده؛ خطا را بررسی کن و دوباره تلاش کن.';
 if(uploadCaption)uploadCaption.textContent=message;
 if(uploadClose)uploadClose.hidden=false;
 clearBusy();alertUser(message);
}
document.addEventListener('submit',e=>{
 const form=e.target;
 if(!form?.matches?.('.product-editor form[enctype="multipart/form-data"]')){
  // Other POST forms stay native; show feedback only if they are still waiting.
  if(form?.method?.toLowerCase()==='post'){
   const submit=form.querySelector('button[type="submit"],input[type="submit"]');
   setTimeout(()=>{if(form.isConnected&&!e.defaultPrevented)startBusy(submit)},180);
  }
  return;
 }
 if(!form.checkValidity()){form.reportValidity();return}
 const files=Array.from(form.querySelectorAll('input[type="file"]')).flatMap(input=>Array.from(input.files||[]));
 if(!files.length){
  const submit=form.querySelector('button[type="submit"],input[type="submit"]');
  setTimeout(()=>{if(form.isConnected)startBusy(submit)},180);
  return; // Native POST when saving only product text/details.
 }
 e.preventDefault();
 if(uploading)return;
 const large=files.find(file=>file.size>5*1024*1024);
 if(large){alertUser('هر تصویر باید حداکثر ۵ مگابایت باشد.');return}
 const total=files.reduce((acc,file)=>acc+file.size,0);
 if(total>31*1024*1024){alertUser('حجم مجموع تصاویر زیاد است؛ در چند مرحله آپلود کن.');return}
 uploading=true;
 const submit=form.querySelector('button[type="submit"],input[type="submit"]');
 startBusy(submit);
 if(uploadClose)uploadClose.hidden=true;
 if(uploadTitle)uploadTitle.textContent='در حال ارسال تصاویر';
 if(uploadDescription)uploadDescription.textContent='لطفاً تا پایان ارسال این صفحه را نبند.';
 if(uploadProgress)uploadProgress.value=0;
 if(uploadPercent)uploadPercent.textContent='۰٪';
 if(uploadCaption)uploadCaption.textContent='اتصال و شروع ارسال فایل‌ها…';
 showUpload();
 const xhr=new XMLHttpRequest();
 xhr.open('POST',form.action,true);
 xhr.withCredentials=true;
 xhr.timeout=120000;
 xhr.upload.onprogress=ev=>{
  if(!ev.lengthComputable)return;
  const n=Math.max(0,Math.min(100,Math.round(ev.loaded*100/ev.total)));
  if(uploadProgress)uploadProgress.value=n;
  if(uploadPercent)uploadPercent.textContent=new Intl.NumberFormat('fa-IR').format(n)+'٪';
  if(uploadCaption)uploadCaption.textContent=n<100?'در حال ارسال فایل‌ها…':'فایل‌ها ارسال شدند؛ منتظر پاسخ سرور…';
 };
 xhr.upload.onload=()=>{
  if(uploadTitle)uploadTitle.textContent='در حال ذخیره محصول';
  if(uploadDescription)uploadDescription.textContent='ارسال تمام شد. پایتون در حال پردازش و ثبت تصاویر است.';
  if(uploadCaption)uploadCaption.textContent='لطفاً چند لحظه صبر کن…';
 };
 xhr.onload=()=>{
  if(xhr.status<200||xhr.status>=400){
   let msg='ذخیره نشد؛ اطلاعات محصول و اتصال سرور را بررسی کن.';
   try{const doc=new DOMParser().parseFromString(xhr.responseText,'text/html');msg=doc.querySelector('.center-error p,.alert')?.textContent?.trim()||msg}catch{}
   uploadError(msg);return;
  }
  // Success must end at the expected product listing, not a login/error page.
  let destination;
  try{destination=new URL(xhr.responseURL||'/admin/products',location.href)}
  catch{uploadError('پاسخ سرور معتبر نبود.');return}
  if(destination.origin!==location.origin||destination.pathname!=='/admin/products'){
   uploadError('ذخیره تأیید نشد. نشست مدیر یا خطای فرم را بررسی کن.');return;
  }
  uploading=false;
  if(uploadTitle)uploadTitle.textContent='محصول ثبت شد';
  if(uploadDescription)uploadDescription.textContent='در حال باز کردن پنل محصولات…';
  if(uploadProgress)uploadProgress.value=100;
  if(uploadPercent)uploadPercent.textContent='۱۰۰٪';
  try{sessionStorage.setItem('delisa-product-saved','1')}catch{}
  location.assign(destination.href);
 };
 xhr.onerror=()=>uploadError('ارتباط با سرور قطع شد. اتصال اینترنت را بررسی کن.');
 xhr.ontimeout=()=>uploadError('ارسال بیش از حد طول کشید؛ دوباره تلاش کن.');
 xhr.onabort=()=>uploadError('ارسال متوقف شد.');
 try{xhr.send(new FormData(form))}catch{uploadError('امکان شروع ارسال فایل وجود ندارد.');}
},true);
try{
 if(sessionStorage.getItem('delisa-product-saved')==='1'){
  sessionStorage.removeItem('delisa-product-saved');
  setTimeout(()=>alertUser('محصول و تصاویر با موفقیت ذخیره شدند.'),170);
 }
}catch{}
})();
