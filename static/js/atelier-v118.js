/* DELISA v1.18 | Address studio. Neshan SDK loads ONLY on the map page. */
(()=>{'use strict';
let sdkPromise=null, map=null, lastTarget=null, aborter=null, debounce=null, requestId=0;
const url='https://static.neshan.org/sdk/openlayers/v8.1.0/neshan-sdk/v1.0.5/';
function loadSDK(){
 if(window.ol?.Map)return Promise.resolve(window.ol);
 if(sdkPromise)return sdkPromise;
 sdkPromise=new Promise((resolve,reject)=>{
  if(!document.querySelector('[data-neshan-css]')){
   const style=document.createElement('link');style.rel='stylesheet';style.href=url+'index.css';style.dataset.neshanCss='1';document.head.append(style);
  }
  const script=document.createElement('script');script.src=url+'index.js';script.async=true;
  script.onload=()=>window.ol?.Map?resolve(window.ol):reject(Error('Map SDK unavailable'));
  script.onerror=()=>reject(Error('Map SDK could not load'));
  document.head.append(script);
 }).catch(e=>{sdkPromise=null;throw e});return sdkPromise;
}
function init(){
 const root=document.getElementById('address-editor-v118');
 if(!root || root.dataset.bound==='1')return;
 root.dataset.bound='1';
 if(map && lastTarget && lastTarget!==root){map.setTarget(null);map=null;lastTarget=null}
 const $=id=>root.querySelector('#'+id);
 const mapWrap=$('neshan-address-map'),status=$('neshan-status'),display=$('neshan-selected-address'),next=$('neshan-next'),
  mapStep=$('address-map-step'),fieldsStep=$('address-fields-step'),latEl=$('address-lat'),lonEl=$('address-lon'),
  province=$('address-province'),city=$('address-city'),street=$('address-street');
 let picked=!!(latEl.value&&lonEl.value),dirty=false;
 next.disabled=!picked;
 function feedback(text,warning=false){status.textContent=text;status.classList.toggle('is-error',warning)}
 function step(n){mapStep.hidden=n!==1;fieldsStep.hidden=n!==2;root.querySelectorAll('[data-step-pill]').forEach(e=>e.classList.toggle('is-active',e.dataset.stepPill===String(n)));if(n===1&&map)requestAnimationFrame(()=>map.updateSize());}
 function applyAddress(data){
   if(data.state){let option=[...province.options].find(o=>o.value===data.state);if(!option){option=new Option(data.state,data.state);province.append(option)}province.value=data.state}
   if(data.city)city.value=data.city;
   if(data.formatted_address)street.value=data.formatted_address;
   else if(data.street)street.value=[data.neighbourhood,data.street].filter(Boolean).join('، ');
   display.textContent=[data.city,data.street].filter(Boolean).join('، ')||data.formatted_address||'موقعیت انتخاب شد؛ جزئیات را در مرحله بعد کامل کن.';
 }
 async function reverse(lat,lon){
  if(aborter)aborter.abort();aborter=new AbortController();const seq=++requestId;
  feedback('در حال پیدا کردن استان، شهر و خیابون...');
  try{
   const resp=await fetch('/api/neshan/reverse?lat='+lat.toFixed(6)+'&lng='+lon.toFixed(6),{credentials:'same-origin',signal:aborter.signal,headers:{Accept:'application/json','X-Delisa-Map':'1'}});
   const data=await resp.json();if(seq!==requestId||!root.isConnected)return;
   if(!resp.ok)throw Error(data.error||'نشانی پیدا نشد.');
   applyAddress(data);feedback('نشانی پیشنهادی آماده شد. می‌تونی ویرایشش کنی.');
  }catch(err){if(err.name==='AbortError')return;if(seq!==requestId||!root.isConnected)return;feedback(err.message||'خطا در دریافت نشانی',true);display.textContent='موقعیت ذخیره شد؛ استان، شهر و نشانی را دستی تکمیل کن.'}
 }
 function pick(coordinate){
  if(!map)return;
  const ll=window.ol.proj.toLonLat(coordinate);const lon=ll[0],lat=ll[1];
  if(!(lat>=24&&lat<=40&&lon>=43&&lon<=64)){feedback('لطفاً نقطه‌ای داخل ایران انتخاب کن.',true);return}
  latEl.value=lat.toFixed(6);lonEl.value=lon.toFixed(6);picked=true;dirty=true;next.disabled=false;
  if(debounce)clearTimeout(debounce);debounce=setTimeout(()=>reverse(lat,lon),480);
 }
 root.querySelector('#neshan-manual').addEventListener('click',()=>{
  if(!picked){latEl.value='';lonEl.value='';}
  step(2);root.querySelector('[name="title"]').focus({preventScroll:true});
 });
 next.addEventListener('click',()=>{if(picked)step(2)});
 root.querySelector('#neshan-previous').addEventListener('click',()=>step(1));
 root.querySelector('#neshan-my-location').addEventListener('click',()=>{
  if(!navigator.geolocation){feedback('موقعیت‌یاب روی این مرورگر در دسترس نیست.',true);return}
  if(!window.isSecureContext){feedback('«موقعیت من» به HTTPS نیاز داره؛ روی نقشه دستی انتخاب کن.',true);return}
  feedback('در حال دریافت موقعیت تو...');
  navigator.geolocation.getCurrentPosition(pos=>{
   if(!map)return;const coord=window.ol.proj.fromLonLat([pos.coords.longitude,pos.coords.latitude]);map.getView().animate({center:coord,zoom:16,duration:260});pick(coord);
  },()=>feedback('اجازه موقعیت‌یابی داده نشد؛ دستی انتخاب کن.',true),{enableHighAccuracy:false,timeout:8500,maximumAge:60000});
 });
 if(root.dataset.mapReady!=='1'){
  mapWrap.innerHTML='<div class="neshan-unavailable-v118"><strong>نقشه نشان هنوز فعال نشده</strong><p>برای نمایش نقشه و پیشنهاد خودکار شهر و خیابون، کلید «نقشه وب» و «سرویس» نشان باید روی سرور تنظیم بشه.</p><span>تا اون موقع می‌تونی اطلاعات رو دستی ثبت کنی.</span></div>';
  root.classList.add('map-failed-v118');feedback('امکان ورود دستی آدرس فراهمه.',true);return;
 }
 loadSDK().then(ol=>{
  if(!root.isConnected)return;
  let initial=[51.389,35.6892];
  if(picked){const lat=Number(latEl.value),lon=Number(lonEl.value);if(Number.isFinite(lat)&&Number.isFinite(lon))initial=[lon,lat]}
  map=new ol.Map({mapType:'neshan',target:'neshan-address-map',key:root.dataset.mapKey,poi:false,traffic:false,
   view:new ol.View({center:ol.proj.fromLonLat(initial),zoom:picked?16:12})});
  lastTarget=root;feedback(picked?'آدرس ثبت‌شده رو می‌تونی دوباره روی نقشه تنظیم کنی.':'نقشه آماده‌ست. نقشه رو حرکت بده یا روی محل موردنظرت بزن.');
  map.on('singleclick',event=>{
   map.getView().animate({center:event.coordinate,duration:200});pick(event.coordinate);
  });
  map.on('movestart',()=>{if(root.isConnected){clearTimeout(debounce);status.textContent='موقعیت رو تنظیم کن...'}});
  map.on('moveend',()=>{if(!root.isConnected||!map)return;const center=map.getView().getCenter();const cLat=Number(latEl.value),cLon=Number(lonEl.value);const [lon,lat]=ol.proj.toLonLat(center);
   if(!picked||Math.abs(cLat-lat)>0.00009||Math.abs(cLon-lon)>0.00009)pick(center);
  });
 }).catch(()=>{
  if(!root.isConnected)return;
  mapWrap.innerHTML='<div class="neshan-unavailable-v118"><strong>نقشه نشان بارگذاری نشد</strong><p>اتصال اینترنت و تنظیمات کلید نشان رو بررسی کن. برای ثبت آدرس منتظر نقشه نمون.</p></div>';
  root.classList.add('map-failed-v118');feedback('نقشه در دسترس نیست؛ آدرس رو دستی ثبت کن.',true);
 });
}
document.addEventListener('DOMContentLoaded',init);
document.addEventListener('delisa:pagechange',init);
})();
