/* AGENTS HQ - office view.
 *
 * Isometric pixel office drawn on one canvas: painted office plate with a procedural fallback, robot
 * sprites (own sheet, then the shared sheet, then a drawn box robot), path-finding, idle activities,
 * speech bubbles, holograms, and sound.
 *
 * Everything in this file is cosmetic and local. It never talks to the server or to Codex: idle
 * wandering, group activities and casual lines cost nothing. Work states come in through sync(), which
 * the dashboard calls with the state the server reported.
 */
(function(){
var AHQ=window.AHQ=window.AHQ||{};
var $=function(i){return document.getElementById(i)};
function ls(k,v){return AHQ.util.ls(k,v)}
/* ?assets=noplate | nosprites | nosheet | none  simulates missing image files (for the fallback tests). */
var MISS=(function(){var m=/[?&]assets=([a-z,]+)/.exec(location.search),s=m?m[1].split(","):[],all=s.indexOf("none")>-1;return {plate:all||s.indexOf("noplate")>-1,sprites:all||s.indexOf("nosprites")>-1,sheet:all||s.indexOf("nosheet")>-1}})();

var IS={z:1,px:0,py:0,fit:1,moved:0,TW:20,TH:10,ZU:14,WX:25,WY:26,OX:0,OY:0,IW:0,IH:0,sc:1,ox:0,oy:0,on:false,timer:0,raf:0,last:0,cv:null,cx:null,floor:null,hover:"",s:{}};
var OFF={built:false,E:{},busy:{}};
IS.IW=(IS.WX+IS.WY)*IS.TW/2+10;IS.IH=(IS.WX+IS.WY)*IS.TH/2+60;IS.OX=IS.WY*IS.TW/2+5;IS.OY=46;
/* Seven permanent desks. The desk key is also the default character of that slot:
   Agent 1 = mgr, 2 = cap, 3 = in, 4 = sch, 5 = pack, 6 = ved, 7 = rvs. */
var SLOTS=["mgr","cap","in","sch","pack","ved","rvs"];
var SPRC={mgr:"#3fb27f",cap:"#5b8def","in":"#8a93a5",sch:"#8e7cf0",pack:"#d9758f",ved:"#f59632",rvs:"#96cd3c"};
var SPRE={mgr:"\u02d8 \u02d8",cap:"\u2022 \u2022","in":"\u2013 \u2013",sch:"^ ^",pack:"o o",ved:"\u2022 \u2022",rvs:"\u2022 \u2022"};
/* Procedural (fallback) office: three rooms, a hallway, two rooms, a hallway, two rooms. */
var RM=[{k:"in",n:"",c:"#8a93a5",x:1,y:1,w:7,d:6,wh:2.6},{k:"cap",n:"",c:"#4f7be0",x:9,y:1,w:7,d:6,wh:2.6},{k:"sch",n:"",c:"#7c6be0",x:17,y:1,w:7,d:6,wh:2.6},{k:"pack",n:"",c:"#d6708a",x:3,y:11,w:8,d:6,wh:1.1,gap:[6,8]},{k:"mgr",n:"",c:"#35a374",x:14,y:11,w:8,d:6,wh:1.1,gap:[18,20]},{k:"ved",n:"",c:"#e08a2c",x:3,y:19,w:8,d:6,wh:1.1,gap:[6,8]},{k:"rvs",n:"",c:"#7fb62f",x:14,y:19,w:8,d:6,wh:1.1,gap:[18,20]}];
var GH={"in":[4.8,2.9],cap:[12.9,2.9],sch:[20.6,2.9],mgr:[18.8,12.6],pack:[6.8,12.6],ved:[6.8,20.6],rvs:[18.8,20.6]};
var VISIT={"in":[4.8,6.5],cap:[12.9,6.5],sch:[20.6,6.5],pack:[6.8,11.8],mgr:[18.8,11.8],ved:[6.8,19.8],rvs:[18.8,19.8]},HALLOF={"in":9,cap:9,sch:9,pack:9,mgr:9,ved:18,rvs:18};
var BT=SLOTS.map(function(k,i){return {id:"agent-0"+(i+1),k:k,spr:k,nm:"Agent "+(i+1),c:SPRC[k],eyes:SPRE[k],home:GH[k].slice(),th:45,st:"idle",holo:"",flash:null}});
function botK(k){for(var i=0;i<BT.length;i++)if(BT[i].k===k)return BT[i];return null}
function botId(id){for(var i=0;i<BT.length;i++)if(BT[i].id===id)return BT[i];return null}

function officeCalm(){return (window.matchMedia&&matchMedia("(prefers-reduced-motion:reduce)").matches)||document.hidden}
function hexRgb(h){var n=parseInt(h.slice(1),16);return [n>>16&255,n>>8&255,n&255]}
function shade(h,f){var c=hexRgb(h);return "rgb("+[0,1,2].map(function(i){return Math.max(0,Math.min(255,Math.round(c[i]*f)))}).join(",")+")"}
function P(x,y,z){if(IS.pl)return [Math.round(x),Math.round(y-z*IS.ZU)];return [Math.round(IS.OX+(x-y)*IS.TW/2),Math.round(IS.OY+(x+y)*IS.TH/2-z*IS.ZU)]}
function poly(cx,pts,fill){cx.beginPath();cx.moveTo(pts[0][0],pts[0][1]);for(var i=1;i<pts.length;i++)cx.lineTo(pts[i][0],pts[i][1]);cx.closePath();cx.fillStyle=fill;cx.fill()}
function ibox(cx,x,y,z,w,d,h,c){poly(cx,[P(x,y+d,z),P(x+w,y+d,z),P(x+w,y+d,z+h),P(x,y+d,z+h)],shade(c,.8));poly(cx,[P(x+w,y,z),P(x+w,y+d,z),P(x+w,y+d,z+h),P(x+w,y,z+h)],shade(c,.58));poly(cx,[P(x,y,z+h),P(x+w,y,z+h),P(x+w,y+d,z+h),P(x,y+d,z+h)],c)}
function planeX(cx,x,y,z,fn,k){k=k||8;var o=P(x,y,z);cx.save();cx.setTransform(IS.TW/2/k,IS.TH/2/k,0,-IS.ZU/k,o[0],o[1]);fn();cx.restore()}
function planeY(cx,x,y,z,fn,k){k=k||8;var o=P(x,y,z);cx.save();cx.setTransform(-IS.TW/2/k,IS.TH/2/k,0,-IS.ZU/k,o[0],o[1]);fn();cx.restore()}
function roomOf(wx,wy){for(var i=0;i<RM.length;i++){var r=RM[i];if(wx>=r.x&&wx<r.x+r.w&&wy>=r.y&&wy<r.y+r.d)return r}return null}
function isoBuildFloor(){var cv=document.createElement("canvas");cv.width=IS.IW;cv.height=IS.IH;var cx=cv.getContext("2d");
 function zone(x,y){if(roomOf(x,y))return 1;if(y>=7&&y<11&&x>=1&&x<24)return 2;if(y>=17&&y<19&&x>=1&&x<24)return 2;if(x>=11&&x<14&&y>=11&&y<17)return 2;return 0}
 for(var y=0;y<IS.WY;y++)for(var x=0;x<IS.WX;x++){var z=zone(x,y);if(!z)continue;var c=z===1?((x+y)%2?"#c98a4b":"#bf7e42"):z===2?((x+y)%2?"#8f7048":"#85683f"):((x+y)%2?"#5b4a37":"#54442f");
  if(!zone(x+1,y))poly(cx,[P(x+1,y,0),P(x+1,y+1,0),P(x+1,y+1,-.45),P(x+1,y,-.45)],shade(c,.5));if(!zone(x,y+1))poly(cx,[P(x,y+1,0),P(x+1,y+1,0),P(x+1,y+1,-.45),P(x,y+1,-.45)],shade(c,.68));
  poly(cx,[P(x,y,0),P(x+1,y,0),P(x+1,y+1,0),P(x,y+1,0)],c)}
 IS.floor=cv}
function wallDrawables(L){RM.forEach(function(r){var H=r.wh,tall=H>2;
 for(var i=0;i<r.w;i++){var x=r.x+i;if(r.gap&&x>=r.gap[0]&&x<r.gap[1])continue;(function(x){L.push({d:x+r.y+.4,f:function(cx){poly(cx,[P(x,r.y,0),P(x+1,r.y,0),P(x+1,r.y,H),P(x,r.y,H)],tall?"#34345f":"#3e3f6c");poly(cx,[P(x,r.y,H-.28),P(x+1,r.y,H-.28),P(x+1,r.y,H),P(x,r.y,H)],r.c);poly(cx,[P(x,r.y,H),P(x+1,r.y,H),P(x+1,r.y-.18,H),P(x,r.y-.18,H)],shade(r.c,.7))}})})(x)}
 for(var j=0;j<r.d;j++){var y=r.y+j;(function(y){L.push({d:r.x+y+.4,f:function(cx){poly(cx,[P(r.x,y,0),P(r.x,y+1,0),P(r.x,y+1,H),P(r.x,y,H)],tall?"#2b2b52":"#35365c");poly(cx,[P(r.x,y,H-.28),P(r.x,y+1,H-.28),P(r.x,y+1,H),P(r.x,y,H)],shade(r.c,.8))}})})(y)}
 L.push({d:r.x+r.y+.2,f:function(cx){planeX(cx,r.x+.5,r.y,Math.max(.25,H-.9),function(){cx.fillStyle="#e9eef7";cx.font="bold 4.2px monospace";cx.textBaseline="top";cx.fillText(r.n,0,0)})}})})}
function furnDrawables(L){
 function box(x,y,w,d,h,c,z){z=z||0;L.push({d:x+y+(w+d)/2,f:function(cx){ibox(cx,x,y,z,w,d,h,c)}})}
 function plant(x,y){L.push({d:x+y+.7,f:function(cx){ibox(cx,x,y,0,.7,.7,.5,"#a8552b");ibox(cx,x+.05,y+.05,.5,.6,.6,.8,"#3f7a3a");ibox(cx,x+.18,y+.18,1.3,.34,.34,.45,"#4f9446")}})}
 function monitor(x,y,w,glow,dd){L.push({d:dd+.02,f:function(cx,t){ibox(cx,x,y,.85,w,.16,.62,"#d9d2bd");planeX(cx,x+.08,y+.16,.93,function(){var g=glow?"#2fe39a":"#1d5a40";cx.fillStyle="#0a1a12";cx.fillRect(0,0,w*8-1.3,4.4);cx.fillStyle=g;for(var i=0;i<3;i++){var ww=glow?(3+((Math.floor(t*6)+i*3)%5)):3;cx.fillRect(.6,.5+i*1.3,Math.min(ww,w*8-3),.7)}})}})}
 function lamp(x,y,dd){L.push({d:dd,f:function(cx){ibox(cx,x,y,.85,.18,.18,.55,"#c9a227");ibox(cx,x-.12,y-.12,1.4,.42,.42,.22,"#f5cf55")}})}
 function shelf(x,y,w,c){L.push({d:x+y+w/2+.4,f:function(cx){ibox(cx,x,y,0,w,.8,2.1,"#7a4a26");for(var i=0;i<Math.floor(w*2);i++){var cc=["#c0392b","#2e86c1","#d4ac0d","#27ae60","#8e44ad"][i%5];planeX(cx,x+i*.5+.08,y+.8,.35+(i%3)*.62,function(){cx.fillStyle=cc;cx.fillRect(0,0,3.2,4.6)})}}})}
 /* One generic workstation per room. The monitor glows only while that agent is really working. */
 RM.forEach(function(r,i){var b=botK(r.k),on=!!b&&b.st==="working",top=r.y===1,dy=top?2.9:2.7,dx=top?1.5:1.6,dw=top?4.4:4.4;
  box(r.x+dx,r.y+dy,dw,1.35,.85,"#a8632f");monitor(r.x+dx+.9,r.y+dy+.15,.9,on,r.x+dx+.9+r.y+dy+3.2);if(i%2===0)monitor(r.x+dx+2.7,r.y+dy+.15,.9,false,r.x+dx+2.7+r.y+dy+3.2);else lamp(r.x+dx+3.6,r.y+dy+.2,r.x+dx+3.6+r.y+dy+1.2);
  if(top)shelf(r.x+1,r.y+.15,i===1?3:4.5);plant(r.x+.4,r.y+r.d-1.2);plant(r.x+r.w-1.1,r.y+r.d-1.2)});
 /* Hallway rugs and plants */
 plant(1.4,8.1);plant(23,8.1);L.push({d:12+9,f:function(cx){ibox(cx,9,8.2,0,7,1.6,.04,"#8a3d3d");ibox(cx,9.2,8.35,.04,6.6,1.3,.02,"#a64848")}});
 plant(1.4,17.3);plant(23,17.3)}

function drawBotBox(cx,b,tm){var q=Math.round(b.th/45)*45*Math.PI/180,cs=Math.cos(q),sn=Math.sin(q),hw=.52,hh=1.2,fz=.55+.11*Math.sin(tm*2.3+b.ph)+(b.walk?.05:0);
 var sh=P(b.x,b.y,0);cx.fillStyle="rgba(0,0,0,.33)";cx.beginPath();cx.ellipse(sh[0],sh[1],7-fz*1.5,3.4-fz*.7,0,0,6.3);cx.fill();
 if(b.st==="waiting"){cx.strokeStyle="rgba(255,90,95,"+(.55+.35*Math.sin(tm*6))+")";cx.lineWidth=1.4;cx.beginPath();cx.ellipse(sh[0],sh[1],9,4.6,0,0,6.3);cx.stroke()}
 var loc=[[hw,-hw],[hw,hw],[-hw,hw],[-hw,-hw]],nrm=[[1,0],[0,1],[-1,0],[0,-1]];
 function W(c){return [b.x+c[0]*cs-c[1]*sn,b.y+c[0]*sn+c[1]*cs]}
 for(var i=0;i<4;i++){var n=nrm[i],nx=n[0]*cs-n[1]*sn,ny=n[0]*sn+n[1]*cs;if(nx+ny<=.01)continue;var A=W(loc[i]),B=W(loc[(i+1)%4]),f=Math.min(1,.5+.34*Math.max(0,ny)+.22*Math.max(0,nx));
  poly(cx,[P(A[0],A[1],fz),P(B[0],B[1],fz),P(B[0],B[1],fz+hh),P(A[0],A[1],fz+hh)],shade(b.c,f));
  if(i===0){var pa=P(A[0],A[1],fz),pb=P(B[0],B[1],fz);cx.save();cx.setTransform(pb[0]-pa[0],pb[1]-pa[1],0,-IS.ZU*hh,pa[0],pa[1]);cx.fillStyle="#0c1017";cx.fillRect(.1,.22,.8,.58);cx.fillStyle="#e9eef7";cx.strokeStyle="#e9eef7";cx.lineWidth=.07;var e=b.eyes.replace(/\s/g,"").charAt(0);
   [.33,.67].forEach(function(u){if(e==="•"){cx.fillRect(u-.06,.47,.12,.17)}else if(e==="^"){cx.beginPath();cx.moveTo(u-.1,.44);cx.lineTo(u,.58);cx.lineTo(u+.1,.44);cx.stroke()}else if(e==="˘"){cx.beginPath();cx.moveTo(u-.1,.52);cx.lineTo(u,.45);cx.lineTo(u+.1,.52);cx.stroke()}else if(e==="o"){cx.strokeRect(u-.07,.45,.14,.17)}else{cx.fillRect(u-.1,.52,.2,.07)}});cx.restore()}
  else if(i===2){var qa=P(A[0],A[1],fz),qb=P(B[0],B[1],fz);cx.save();cx.setTransform(qb[0]-qa[0],qb[1]-qa[1],0,-IS.ZU*hh,qa[0],qa[1]);cx.fillStyle="rgba(0,0,0,.25)";cx.fillRect(.25,.3,.5,.05);cx.fillRect(.25,.45,.5,.05);cx.fillRect(.25,.6,.5,.05);cx.restore()}}
 var T=[W(loc[0]),W(loc[1]),W(loc[2]),W(loc[3])].map(function(c){return P(c[0],c[1],fz+hh)});poly(cx,T,b.c);
 }
var SPR={ok:0,tint:{},fr:null};
(function(){var im=new Image();im.onload=function(){try{sprBuild(im)}catch(e){SPR.ok=0}};if(!MISS.sheet)im.src="assets/bots-sheet.webp"})();
function sprBuild(im){var W=im.width,H=im.height,cw=W/4,ch=H/3,c0=document.createElement("canvas");c0.width=W;c0.height=H;var x0=c0.getContext("2d");x0.drawImage(im,0,0);var all=x0.getImageData(0,0,W,H),d=all.data,i,n=W*H;
 for(i=0;i<n;i++){var r=d[i*4],g=d[i*4+1],b=d[i*4+2];if(r>g+30&&b>g+20)d[i*4+3]=0}
 x0.putImageData(all,0,0);var S=.22,fr=[];
 for(var k=0;k<12;k++){var cx0=Math.floor((k%4)*cw),cy0=Math.floor(Math.floor(k/4)*ch),w=Math.floor(cw),h=Math.floor(ch),id=x0.getImageData(cx0,cy0,w,h),dd=id.data,mnx=w,mny=h,mxx=0,mxy=0,x,y;
  for(y=0;y<h;y++)for(x=0;x<w;x++)if(dd[(y*w+x)*4+3]>40){if(x<mnx)mnx=x;if(x>mxx)mxx=x;if(y<mny)mny=y;if(y>mxy)mxy=y}
  var bw=mxx-mnx+1,bh=mxy-mny+1,sub=x0.getImageData(cx0+mnx,cy0+mny,bw,bh),sd=sub.data,dark=new Uint8Array(bw*bh);
  for(i=0;i<bw*bh;i++){var lu=sd[i*4]*.3+sd[i*4+1]*.59+sd[i*4+2]*.11;dark[i]=sd[i*4+3]>200&&lu<42?1:0}
  var ex0=bw,ey0=bh,ex1=-1,ey1=-1;
  for(y=3;y<bh-3;y++)for(x=3;x<bw-3;x++){var all4=1;for(var yy=-3;yy<=3&&all4;yy++)for(var xx=-3;xx<=3;xx++)if(!dark[(y+yy)*bw+x+xx]){all4=0;break}
   if(all4){if(x<ex0)ex0=x;if(x>ex1)ex1=x;if(y<ey0)ey0=y;if(y>ey1)ey1=y}}
  var cv=document.createElement("canvas");cv.width=bw;cv.height=bh;cv.getContext("2d").putImageData(sub,0,0);
  var sw=Math.max(1,Math.round(bw*S)),sh=Math.max(1,Math.round(bh*S)),sm=document.createElement("canvas");sm.width=sw;sm.height=sh;var sx=sm.getContext("2d");sx.imageSmoothingEnabled=true;sx.imageSmoothingQuality="high";sx.drawImage(cv,0,0,sw,sh);
  fr.push({c:sm,w:sw,h:sh,scr:ex1>0?[ex0*S,ey0*S,(ex1+1)*S,(ey1+1)*S]:null})}
 SPR.fr=fr;SPR.ok=1}
function sprTint(key,col,f,mir){var id=key+"|"+f+"|"+mir;if(SPR.tint[id])return SPR.tint[id];var fr=SPR.fr[f],c=document.createElement("canvas");c.width=fr.w;c.height=fr.h;var x=c.getContext("2d");
 if(mir){x.translate(fr.w,0);x.scale(-1,1)}x.drawImage(fr.c,0,0);x.setTransform(1,0,0,1,0,0);var im=x.getImageData(0,0,fr.w,fr.h),d=im.data,rgb=[parseInt(col.substr(1,2),16),parseInt(col.substr(3,2),16),parseInt(col.substr(5,2),16)];
 for(var i=0;i<d.length;i+=4){if(!d[i+3])continue;var lu=d[i]*.3+d[i+1]*.59+d[i+2]*.11;if(lu<48)continue;var k=lu/175;d[i]=Math.min(255,rgb[0]*k);d[i+1]=Math.min(255,rgb[1]*k);d[i+2]=Math.min(255,rgb[2]*k)}
 x.putImageData(im,0,0);var t={c:c,w:fr.w,h:fr.h,scr:fr.scr&&(mir?[fr.w-fr.scr[2],fr.scr[1],fr.w-fr.scr[0],fr.scr[3]]:fr.scr)};SPR.tint[id]=t;return t}
var SPRDIR=[[0,0],[1,0],[2,0],[3,1],[11,1],[7,0],[11,0],[3,0]],SPRSC=[[3,0],[0,0],[1,0],[2,0],[3,1],[11,1],[7,0],[11,0]];
function drawBotOld(cx,b,tm){if(!SPR.ok)return drawBotBox(cx,b,tm);var bs=IS.pl?1:.68,k=IS.pl?1.7:1,fz=.55+.11*Math.sin(tm*2.3+b.ph)+(b.walk?.05:0),sh=P(b.x,b.y,0),q=Math.round((((b.th%360)+360)%360)/45)%8,m=(IS.pl?SPRSC:SPRDIR)[q],t=sprTint(b.spr,b.c,m[0],m[1]);
 cx.fillStyle="rgba(0,0,0,.33)";cx.beginPath();cx.ellipse(sh[0],sh[1],(7-fz*1.5)*k,(3.4-fz*.7)*k,0,0,6.3);cx.fill();
 if(b.st==="waiting"){cx.strokeStyle="rgba(255,90,95,"+(.55+.35*Math.sin(tm*6))+")";cx.lineWidth=1.4;cx.beginPath();cx.ellipse(sh[0],sh[1],9*k,4.6*k,0,0,6.3);cx.stroke()}
 var p=P(b.x,b.y,fz),tw=t.w*bs,th=t.h*bs,dx=Math.round(p[0]-tw/2),dy=Math.round(p[1]-th+2);cx.drawImage(t.c,dx,dy,tw,th);
 if(t.scr){var sx0=dx+t.scr[0]*bs,sy0=dy+t.scr[1]*bs,sw=(t.scr[2]-t.scr[0])*bs,sh2=(t.scr[3]-t.scr[1])*bs,e=b.eyes.replace(/\s/g,"").charAt(0),ey=sy0+sh2*.5,u=[sx0+sw*.32,sx0+sw*.68],g=k;cx.fillStyle="#e9eef7";cx.strokeStyle="#e9eef7";cx.lineWidth=g*.8;
  u.forEach(function(ux){ux=Math.round(ux);if(e==="•"){cx.fillRect(ux-g,Math.round(ey-g),2*g,3*g)}else if(e==="^"){cx.beginPath();cx.moveTo(ux-2*g,ey+g);cx.lineTo(ux,ey-g);cx.lineTo(ux+2*g,ey+g);cx.stroke()}else if(e==="˘"){cx.beginPath();cx.moveTo(ux-2*g,ey-g);cx.lineTo(ux,ey+g);cx.lineTo(ux+2*g,ey-g);cx.stroke()}else if(e==="o"){cx.strokeRect(ux-1.5*g,ey-1.5*g,3*g,3*g)}else{cx.fillRect(ux-2*g,Math.round(ey),4*g,g)}})}}
var Z=.5;function zz(a){return a.map(function(n){return n*Z})}function zp(a){return a.map(function(q){return [q[0]*Z,q[1]*Z]})}
var SEATTH=333,PL={ok:0,c:null},PLH={in:[154.0,244.5],cap:[195.5,164.5],sch:[377.0,164.5],mgr:[524.5,176.5],pack:[497.0,254.5],ved:[-41.9,327.4],rvs:[8.4,304.3]},PLV={},PLR={drop:[23,153.5,192.5,155],cap:[100.5,78.5,165,135],sch:[253,78.5,165,115],mgr:[423,73.5,220,140],pack:[455.5,168.5,192.5,147.5]},
SPOTS=[[[189.0,329.5],225,"Need my coffee…","Ahh, that hits the spot.",3,"c"],[[207.0,321.5],225,"Espresso time.","Smells great.",3,"c"],[[225.0,313.5],225,"One cappuccino, please.","Perfect.",3,"c"],[[445.5,356.0],315,"One quick game.","Nice shot!"],[[503,318],333,"Just one round.","High score, almost.",0,"a0"],[[530,326],333,"My turn on the arcade.","New record!",0,"a1"],[[338.0,228.5],315,"Quick walk.","Fresh air, nice."],[[323.0,178.5],270,"Let me check the board.","Okay, got it."],[[293.0,311.0],27,"Sofa time.","Comfy.",4],[[369.0,318.5],166,"Taking the sofa.","Nice and soft.",4],[[251.0,333.5],356,"Beanbag break.","So comfy.",6],[[279.5,353.5],333,"Quick sit-down.","Five minutes, then back.",6],[[364.5,356.0],217,"Bean bag, please.","Ahh, relaxing.",6],[[399.5,341.0],190,"Short rest.","Okay, back soon.",6]],
CHAT=[["Anyone have a new task?","Not yet. I'm ready when it comes."],["Busy day today?","Quiet so far."],["My desk is suspiciously clean.","Enjoy it while it lasts."],["I wonder what we'll work on today.","Something good, I hope."],["Coffee later?","You read my mind."],["One more arcade game?","Okay, just one."],["Wake me up when there's work.","Deal."],["A day without errors. That's my dream.","Dream big."]],
NAVW=[zp([[431,499],[396,407],[506,347],[566,371],[786,371],[846,347],[911,395],[924,499],[1011,547],[1126,629],[686,869],[208,613]]),
 zp([[224,325],[366,253],[531,341],[406,429]]),
 zp([[546,337],[676,265],[828,337],[791,389],[566,389]]),
 zp([[856,307],[996,239],[1178,327],[986,405],[941,442],[866,432],[851,357]]),
 zp([[885,480],[986,427],[1288,527],[1128,631],[1006,552]]),
 zp([[44,512],[256,397],[436,502],[212,617]])],
NAVB=[["r"].concat(zz([81,367,205,185])),["r"].concat(zz([271,437,110,42])),["r"].concat(zz([201,157,170,150])),["r"].concat(zz([351,277,118,40])),["r"].concat(zz([581,282,118,52])),["r"].concat(zz([511,267,48,40])),["r"].concat(zz([721,273,112,40])),["r"].concat(zz([876,187,205,112])),["r"].concat(zz([1016,289,112,42])),["r"].concat(zz([1086,427,182,105])),["r"].concat(zz([1064,419,72,48])),["r"].concat(zz([961,447,108,38])),["r"].concat(zz([304,607,80,45])),["r"].concat(zz([384,579,70,36])),["r"].concat(zz([611,642,86,35])),["r"].concat(zz([826,602,136,70])),["r"].concat(zz([1004,596,52,30])),["r"].concat(zz([1044,614,54,32])),["r"].concat(zz([584,787,40,34])),["r"].concat(zz([710,787,44,34]))],
SUITENAV=[[[-64,340],[13,295],[58,288],[98.5,299.5],[110,313],[-1,376.5]],[[89.5,297],[117,288],[135,311],[107.5,324.5]]],
MON={in:[155.5,206.5,14,13],cap:[199.5,127.5,14,13],sch:[380.5,127.5,14,13],mgr:[526.5,134.0,14,13],pack:[500.5,214.0,14,13]};
SUITENAV.forEach(function(q){NAVW.push(q)});
function pip(x,y,poly){var c=false;for(var i=0,j=poly.length-1;i<poly.length;j=i++){var a=poly[i],b=poly[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])c=!c}return c}
var NAVBP=[[[136,301],[153.5,297],[156.5,332.5],[201.5,353],[240,363.5],[236,379],[132,336.5]],[[10,250],[106,282],[100,306],[58,298],[10,300]]];
function walk(x,y){var ok=false,M=3;for(var i=0;i<NAVW.length;i++)if(pip(x,y,NAVW[i])&&pip(x+M,y,NAVW[i])&&pip(x-M,y,NAVW[i])&&pip(x,y+M*.5,NAVW[i])&&pip(x,y-M*.5,NAVW[i])){ok=true;break}if(!ok)return false;for(i=0;i<NAVB.length;i++){var o=NAVB[i];if(x>o[1]-M&&x<o[1]+o[3]+M&&y>o[2]-M*.5&&y<o[2]+o[4]+M*.5)return false}for(i=0;i<NAVBP.length;i++){var q=NAVBP[i];if(pip(x,y,q)||pip(x+M,y,q)||pip(x-M,y,q)||pip(x,y+M*.5,q)||pip(x,y-M*.5,q))return false}return true}
var NAVC={};function nodeXY(i,j){return [289+(i-j)*8,12+(i+j)*4]}
function nodeOk(i,j){var k=i*1000+j;if(NAVC[k]===undefined){var p=nodeXY(i,j);NAVC[k]=i>=0&&j>=0&&i<110&&j<110&&walk(p[0],p[1])}return NAVC[k]}
function stepOk(a,b){if(!nodeOk(b[0],b[1]))return false;var p=nodeXY(a[0],a[1]),q=nodeXY(b[0],b[1]);return walk((p[0]+q[0])/2,(p[1]+q[1])/2)}
function snapNode(pt){var fi=(((pt[1]-12)/4)+((pt[0]-289)/8))/2,fj=(((pt[1]-12)/4)-((pt[0]-289)/8))/2,ci=Math.round(fi),cj=Math.round(fj),best=null,bd=1e9;for(var r=0;r<=16;r++){for(var di=-r;di<=r;di++)for(var dj=-r;dj<=r;dj++){if(Math.max(Math.abs(di),Math.abs(dj))!==r)continue;var i=ci+di,j=cj+dj;if(!nodeOk(i,j))continue;var p=nodeXY(i,j),d=Math.hypot(p[0]-pt[0],p[1]-pt[1]);if(d<bd){bd=d;best=[i,j]}}if(best&&r>=2)break}return best}
function route(a,b){var A=Array.isArray(a)?a:[a.x,a.y],s0=snapNode(A),g0=snapNode(b);if(!s0||!g0)return [b.slice()];var key=function(n){return n[0]*1000+n[1]},open=[s0],g={},from={},cl={};g[key(s0)]=0;var found=false;
 while(open.length){var bi=0,bf=1e9;for(var q=0;q<open.length;q++){var n=open[q],f=g[key(n)]+Math.abs(n[0]-g0[0])+Math.abs(n[1]-g0[1]);if(f<bf){bf=f;bi=q}}var cur=open.splice(bi,1)[0];if(cur[0]===g0[0]&&cur[1]===g0[1]){found=true;break}cl[key(cur)]=1;
  [[1,0],[-1,0],[0,1],[0,-1]].forEach(function(d){var nb=[cur[0]+d[0],cur[1]+d[1]],kk=key(nb);if(cl[kk]||!stepOk(cur,nb))return;var ng=g[key(cur)]+1;if(g[kk]===undefined||ng<g[kk]){g[kk]=ng;from[kk]=cur;if(!open.some(function(o){return key(o)===kk}))open.push(nb)}})}
 if(!found)return [b.slice()];var path=[],c=g0;while(c){path.unshift(c);c=from[key(c)]}var out=[],pd=null;for(var m=1;m<path.length;m++){var dd=[path[m][0]-path[m-1][0],path[m][1]-path[m-1][1]];if(pd&&(dd[0]!==pd[0]||dd[1]!==pd[1]))out.push(nodeXY(path[m-1][0],path[m-1][1]));pd=dd}out.push(nodeXY(g0[0],g0[1]));if(walk(b[0],b[1]))out.push(b.slice());return out}
IS.dbg=/[?&]nav=1/.test(location.search);
function monDraw(cx,tm){
 if(IS.dbg&&!IS.noov){cx.lineWidth=1;NAVW.forEach(function(pl){cx.strokeStyle="rgba(60,255,120,.9)";cx.beginPath();pl.forEach(function(q,i){i?cx.lineTo(q[0],q[1]):cx.moveTo(q[0],q[1])});cx.closePath();cx.stroke()});NAVB.forEach(function(o){cx.fillStyle="rgba(255,50,50,.35)";cx.fillRect(o[1],o[2],o[3],o[4])});NAVBP.forEach(function(q){cx.fillStyle="rgba(255,50,50,.35)";cx.beginPath();q.forEach(function(v,i){i?cx.lineTo(v[0],v[1]):cx.moveTo(v[0],v[1])});cx.closePath();cx.fill()})}}
(function(){var im=new Image();im.onload=function(){try{var W=im.width,H=im.height,c0=document.createElement("canvas");c0.width=W;c0.height=H;var x0=c0.getContext("2d");x0.drawImage(im,0,0);var id=x0.getImageData(0,0,W,H),d=id.data,N=W*H,gone=new Uint8Array(N),st=[],i,j;
 function mg(p){var r=d[p*4],g=d[p*4+1],b=d[p*4+2];return r>190&&b>190&&g<130}
 for(i=0;i<W;i++)for(j=0;j<6;j++){st.push(j*W+i,(H-1-j)*W+i)}for(j=0;j<H;j++)for(i=0;i<6;i++){st.push(j*W+i,j*W+W-1-i)}
 while(st.length){var p=st.pop();if(gone[p]||!mg(p))continue;gone[p]=1;var x=p%W,y=(p/W)|0;if(x>0)st.push(p-1);if(x<W-1)st.push(p+1);if(y>0)st.push(p-W);if(y<H-1)st.push(p+W)}
 for(var pass=0;pass<2;pass++){var add=[];for(i=0;i<N;i++){if(gone[i])continue;var x=i%W,y=(i/W)|0,nb=(x>0&&gone[i-1])||(x<W-1&&gone[i+1])||(y>0&&gone[i-W])||(y<H-1&&gone[i+W]);if(nb){var r=d[i*4],g=d[i*4+1],b=d[i*4+2];if(r>150&&r>g+50&&b>g+50)add.push(i)}}add.forEach(function(q){gone[q]=1})}
 for(i=0;i<N;i++){var ex=i%W,ey=(i/W)|0;if(gone[i]||ey<3||ex<3||ex>W-4||ey>H-4)d[i*4+3]=0}PL.doorDone=1;x0.putImageData(id,0,0);var c=document.createElement("canvas");c.width=1344;c.height=896;var x=c.getContext("2d");x.imageSmoothingEnabled=true;x.imageSmoothingQuality="high";x.drawImage(c0,0,0,1344,896);PL.c=c;PL.ok=1}catch(e){PL.ok=0}plDone()};im.onerror=plDone;if(MISS.plate)setTimeout(plDone,0);else im.src="assets/office-plate-door.webp"})();
function plDone(){PL.done=1;if(PL.cb){var f=PL.cb;PL.cb=null;f()}}
function plateOn(){IS.pl=1;IS.IW=672;IS.IH=448;IS.ZU=20;BT.forEach(function(b){b.home=PLH[b.k].slice()})}
/* Path for a hand-off walk from one desk to another (and back). */
function rt(k,to,back){var b=botK(k),o=botK(to),h=b.home;if(!IS.pl){var t=VISIT[to],ha=HALLOF[k],hb=HALLOF[to],fw=(ha===hb?[[h[0],ha],[t[0],ha]]:[[h[0],ha],[12.5,ha],[12.5,hb],[t[0],hb]]).concat([t]);return back?fw.slice(0,-1).reverse().concat([h.slice()]):fw}var t2=[o.home[0]+(o.home[0]>h[0]?-26:26),o.home[1]+4];return back?route(t2,h):route(b,t2)}
/* Own sprite sheets: five image files; the two extra characters are recoloured copies of one of them. */
var FS={n:0,ok:0,set:{}},FSR=1.5,FSKEYS=["in","cap","sch","mgr","pack"],FSTINT=[["ved",[245,150,50,120]],["rvs",[150,205,60,120]]];
function fsDone(){FS.n++;if(FS.n===FSKEYS.length)FS.ok=1}
function fsTint(im,tt){var c1=document.createElement("canvas");c1.width=im.width;c1.height=im.height;var x1=c1.getContext("2d");x1.drawImage(im,0,0);var kd=x1.getImageData(0,0,c1.width,c1.height),dd=kd.data;
 for(var q=0;q<dd.length;q+=4){var r=dd[q],g=dd[q+1],b=dd[q+2],m=Math.min(r,b);if(m>90&&g<m*.45&&Math.abs(r-b)<55)dd[q+3]=0;else{var lu=r*.3+g*.59+b*.11,mx=Math.max(r,g,b),sa=mx?(mx-Math.min(r,g,b))/mx:0;if(lu>=40&&sa>=.22&&b>r+20&&b>=g){var kk=Math.min(1.25,lu/tt[3]);dd[q]=Math.min(255,tt[0]*kk);dd[q+1]=Math.min(255,tt[1]*kk);dd[q+2]=Math.min(255,tt[2]*kk)}}}
 x1.putImageData(kd,0,0);return c1}
FSKEYS.forEach(function(k){if(MISS.sprites){setTimeout(fsDone,0);return}var im=new Image();im.onload=function(){try{fsBuild(k,im);if(k==="cap")FSTINT.forEach(function(h){fsBuild(h[0],fsTint(im,h[1]))})}catch(e){}fsDone()};im.onerror=fsDone;im.src="assets/bot-"+k+".webp"});

function fsBuild(k,im){var W=im.width,H=im.height,cw=Math.floor(W/5),ch=Math.floor(H/4),c0=document.createElement("canvas");c0.width=W;c0.height=H;var x0=c0.getContext("2d");x0.drawImage(im,0,0);var all=x0.getImageData(0,0,W,H),d=all.data,i,S=.2*FSR;
 for(i=0;i<W*H;i++){var r=d[i*4],g=d[i*4+1],b=d[i*4+2],m=Math.min(r,b),ex=i%W,ey=(i/W)|0;if((m>90&&g<m*.45&&Math.abs(r-b)<55)||ex<10||ey<10||ex>W-11||ey>H-11)d[i*4+3]=0}
 x0.putImageData(all,0,0);var rows=[];
 for(var rw=0;rw<4;rw++){var row=[];for(var cl=0;cl<5;cl++){var sub=x0.getImageData(cl*cw,rw*ch,cw,ch),sd=sub.data,mnx=cw,mny=ch,mxx=0,mxy=0,x,y;
   for(y=0;y<ch;y++)for(x=0;x<cw;x++)if(sd[(y*cw+x)*4+3]>40){if(x<mnx)mnx=x;if(x>mxx)mxx=x;if(y<mny)mny=y;if(y>mxy)mxy=y}
   var bw=mxx-mnx+1,bh=mxy-mny+1,cv=document.createElement("canvas");cv.width=bw;cv.height=bh;cv.getContext("2d").putImageData(x0.getImageData(cl*cw+mnx,rw*ch+mny,bw,bh),0,0);
   var sw=Math.max(1,Math.round(bw*S)),sh=Math.max(1,Math.round(bh*S)),mk=function(mir){var c=document.createElement("canvas");c.width=sw;c.height=sh;var x1=c.getContext("2d");x1.imageSmoothingEnabled=true;x1.imageSmoothingQuality="high";if(mir){x1.translate(sw,0);x1.scale(-1,1)}x1.drawImage(cv,0,0,sw,sh);return c};
   row.push([mk(0),mk(1)])}rows.push(row)}
 FS.set[k]=rows}
var FSM=[[2,0],[1,0],[0,0],[1,1],[2,1],[3,1],[4,0],[3,0]];
function drawBotSprite(cx,b,tm){var set=FS.ok&&FS.set[b.spr];if(!set)return drawBotOld(cx,b,tm);var k=IS.pl?1.7:1,fz=.55+.11*Math.sin(tm*2.3+b.ph)+(b.walk?.05:0),sh=P(b.x,b.y,0),q=Math.round((((b.th%360)+360)%360)/45)%8,e=OFF.E[b.k],emo=e&&e.txt?(e.bad?3:1):b.st==="working"?2:b.st==="waiting"?3:0,m=FSM[q],t=set[emo][m[0]][m[1]];
 cx.fillStyle="rgba(0,0,0,.33)";cx.beginPath();cx.ellipse(sh[0],sh[1],(7-fz*1.5)*k,(3.4-fz*.7)*k,0,0,6.3);cx.fill();
 if(b.st==="waiting"){cx.strokeStyle="rgba(255,90,95,"+(.55+.35*Math.sin(tm*6))+")";cx.lineWidth=1.4;cx.beginPath();cx.ellipse(sh[0],sh[1],9*k,4.6*k,0,0,6.3);cx.stroke()}
 var sk=(IS.pl&&b.sit&&!b.path.length)?b.sit:0;if(sk)fz=.15+.03*Math.sin(tm*1.5+b.ph);if(b.hopU&&performance.now()/1000<b.hopU)fz+=Math.abs(Math.sin(tm*11))*.55;var p=P(b.x,b.y,fz),bs=(IS.pl?.46:.8)/FSR,hd=b.hid&&!b.path.length;if(hd){cx.save();cx.globalAlpha=.42}cx.drawImage(t,Math.round(p[0]-t.width*bs/2),Math.round(p[1]-t.height*bs+2+sk),t.width*bs,t.height*bs);if(hd)cx.restore();if(IS.pl&&b.mug&&!b.path.length&&!b.cof&&atSeat(b))b.mug=0;if(IS.pl&&((b.cof&&!b.path.length)||b.mug))mugDraw(cx,Math.round(p[0]+8),Math.round(p[1]-9+sk),tm,b)}
/* Character plus its name tag and, for the agent whose workspace is open, an amber ring. */
function drawBot(cx,b,tm){var sh=P(b.x,b.y,0),k=IS.pl?1.7:1;
 if(OFF.sel===b.id){cx.save();cx.strokeStyle="#f5a300";cx.lineWidth=1.6;cx.shadowColor="rgba(245,163,0,.8)";cx.shadowBlur=5;cx.beginPath();cx.ellipse(sh[0],sh[1],10*k,5*k,0,0,6.3);cx.stroke();cx.restore()}
 drawBotSprite(cx,b,tm);if(b.hid&&!b.path.length)return;
 var fs=IS.pl?7:5;cx.save();cx.font="600 "+fs+"px system-ui,sans-serif";cx.textAlign="center";var nm=b.nm.length>14?b.nm.slice(0,13)+"\u2026":b.nm,w=cx.measureText(nm).width+fs,ly=Math.round(sh[1])+(IS.pl?5:3);cx.fillStyle="rgba(20,22,34,.82)";cx.fillRect(Math.round(sh[0]-w/2),ly,Math.round(w),fs+3);cx.fillStyle="#fff";cx.fillText(nm,Math.round(sh[0]),ly+fs+.4);cx.restore()}
/* Which sprite source is in use for a character (for the fallback tests and the status line). */
function spriteSource(b){return FS.ok&&FS.set[b.spr]?"individual":SPR.ok?"sheet":"box"}

/* ---- holograms: shown above the desk only for states the server reported. No percentages, no made-up text. */
var HOLO_COL={approval:[255,196,84],error:[255,110,104],done:[110,240,160]};
function holoKind(b){var now=performance.now();if(b.flash&&b.flash.until>now)return b.flash.k;if(b.st==="waiting")return "approval";if(b.st==="working")return b.holo||"thinking";return ""}
function holoOn(b){if(b.path.length||!atSeat(b))return false;return !!holoKind(b)}
function holoDraw(cx,tm){BT.forEach(function(b){if(!holoOn(b))return;var kind=holoKind(b),col=HOLO_COL[kind]||[140,245,255],rgb=col.join(","),p=P(b.x,b.y,0);cx.save();if(!IS.pl){cx.translate(p[0],p[1]);cx.scale(.55,.55);cx.translate(-p[0],-p[1])}if(b.st==="working"&&!HOLO_COL[kind])binDraw(cx,tm,b,p);var bob=Math.sin(tm*2.2+b.ph)*1.4,w=30,h=20,x0=Math.round(p[0]+4),y0=Math.round(p[1]-62+bob),fl=.82+.18*Math.sin(tm*9+b.ph*3),t=tm,i;
 cx.save();cx.globalAlpha=fl;
 cx.fillStyle="rgba("+rgb+",.13)";cx.beginPath();cx.moveTo(p[0]+3,p[1]-12);cx.lineTo(x0+4,y0+h);cx.lineTo(x0+w-4,y0+h);cx.closePath();cx.fill();
 cx.shadowColor="rgba("+rgb+",.9)";cx.shadowBlur=6;cx.fillStyle="rgba("+rgb+",.2)";cx.strokeStyle="rgba("+rgb+",.95)";cx.lineWidth=1;
 cx.beginPath();cx.rect(x0+.5,y0+.5,w,h);cx.fill();cx.stroke();cx.shadowBlur=0;
 cx.fillStyle="rgba("+rgb+",.10)";for(var k=(Math.floor(tm*12)%3);k<h;k+=3)cx.fillRect(x0+1,y0+k,w-1,1);
 cx.strokeStyle=cx.fillStyle=HOLO_COL[kind]?"rgba(255,255,255,.95)":"rgba(200,252,255,.95)";
 if(kind==="thinking"){for(i=0;i<3;i++){var a=.35+.65*Math.max(0,Math.sin(t*4-i*.9));cx.globalAlpha=fl*a;cx.beginPath();cx.arc(x0+9+i*6,y0+10,1.8,0,6.3);cx.fill()}}
 else if(kind==="typing"){var ws=[20,16,22,12],ph=(t*.8)%4;for(i=0;i<4;i++){var ww=i<Math.floor(ph)?ws[i]:i===Math.floor(ph)?ws[i]*(ph%1):0;cx.fillRect(x0+4,y0+4+i*4,Math.round(ww),1.6)}if(Math.floor(tm*3)%2)cx.fillRect(x0+4+Math.round(ws[Math.floor(ph)]*(ph%1)),y0+3+Math.floor(ph)*4,1,3.5)}
 else if(kind==="scroll"){var off=(t*5)%4,wl=[20,14,22,10,18,16];cx.save();cx.beginPath();cx.rect(x0+2,y0+2,w-3,h-3);cx.clip();for(i=0;i<6;i++)cx.fillRect(x0+4,y0+3+i*4-off,wl[(i+Math.floor(t*1.25))%6],1.5);cx.restore()}
 else if(kind==="terminal"){cx.beginPath();cx.moveTo(x0+4,y0+5);cx.lineTo(x0+7,y0+7.5);cx.lineTo(x0+4,y0+10);cx.stroke();var tw=((t*6)%14);cx.fillRect(x0+9,y0+7,Math.round(tw),1.5);if(Math.floor(tm*3)%2)cx.fillRect(x0+10+Math.round(tw),y0+6,1.5,3.5);cx.globalAlpha=fl*.6;cx.fillRect(x0+4,y0+13,16,1.2);cx.fillRect(x0+4,y0+16,11,1.2)}
 else if(kind==="file_read"){cx.strokeRect(x0+8.5,y0+3.5,13,14);for(i=0;i<3;i++)cx.fillRect(x0+11,y0+6.5+i*3.4,8,1.1);var sy=y0+4+((t*7)%13);cx.globalAlpha=fl*.9;cx.fillRect(x0+6,sy,18,1)}
 else if(kind==="document"){cx.strokeRect(x0+7.5,y0+3.5,13,14);var dn=Math.floor((t*1.6)%4);for(i=0;i<=Math.min(dn,3);i++)cx.fillRect(x0+10,y0+6+i*3,i===dn?4+((t*1.6)%1)*4:8,1.1);cx.beginPath();cx.moveTo(x0+26,y0+5);cx.lineTo(x0+22,y0+13);cx.lineTo(x0+21.4,y0+15.4);cx.lineTo(x0+23.4,y0+14);cx.lineTo(x0+27.4,y0+6);cx.closePath();cx.fill()}
 else if(kind==="coding"){cx.beginPath();cx.moveTo(x0+8,y0+5);cx.lineTo(x0+4,y0+10);cx.lineTo(x0+8,y0+15);cx.moveTo(x0+22,y0+5);cx.lineTo(x0+26,y0+10);cx.lineTo(x0+22,y0+15);cx.stroke();var cl=[6,9,5],cn=Math.floor((t*1.4)%4);for(i=0;i<3;i++)if(i<cn)cx.fillRect(x0+11+(i===1?2:0),y0+6.5+i*3.4,cl[i],1.3)}
 else if(kind==="database"){for(i=0;i<3;i++){var yy=y0+4+i*4.4,hi=Math.floor(t*2.5)%3===i;cx.globalAlpha=fl*(hi?1:.6);cx.beginPath();cx.ellipse(x0+15,yy+1,7.5,1.8,0,0,6.3);cx.stroke();cx.beginPath();cx.moveTo(x0+7.5,yy+1);cx.lineTo(x0+7.5,yy+4.4);cx.moveTo(x0+22.5,yy+1);cx.lineTo(x0+22.5,yy+4.4);cx.stroke();if(hi)cx.fillRect(x0+13,yy+2.8,4,1)}cx.beginPath();cx.ellipse(x0+15,y0+17.6,7.5,1.8,0,0,3.15);cx.stroke()}
 else if(kind==="research"){var mx=x0+12+Math.sin(t*1.4)*3,my=y0+9+Math.cos(t*1.1)*1.5;cx.beginPath();cx.arc(mx,my,4,0,6.3);cx.stroke();cx.beginPath();cx.moveTo(mx+3,my+3);cx.lineTo(mx+7,my+7);cx.lineWidth=1.6;cx.stroke();cx.lineWidth=1;cx.globalAlpha=fl*.55;cx.fillRect(x0+4,y0+4,8,1);cx.fillRect(x0+18,y0+15,8,1)}
 else if(kind==="test"){var n=Math.floor(t*1.2)%4;for(i=0;i<3;i++){var ty=y0+4+i*5.2;cx.strokeRect(x0+4.5,ty+.5,3.5,3.5);cx.fillRect(x0+11,ty+1.5,13-i*2,1.5);if(i<n){cx.beginPath();cx.moveTo(x0+5,ty+2.4);cx.lineTo(x0+6.3,ty+3.8);cx.lineTo(x0+8.6,ty+.6);cx.stroke()}}}
 else if(kind==="tool"){cx.save();cx.translate(x0+15,y0+10);cx.rotate(t*1.2);cx.beginPath();cx.arc(0,0,3.2,0,6.3);cx.stroke();for(i=0;i<6;i++){cx.rotate(Math.PI/3);cx.fillRect(-1,-6.2,2,2.6)}cx.restore()}
 else if(kind==="approval"){var pu=.6+.4*Math.abs(Math.sin(t*3));cx.globalAlpha=fl*pu;cx.font="bold 13px system-ui,sans-serif";cx.textAlign="center";cx.fillText("?",x0+15,y0+14.5);cx.globalAlpha=fl;cx.strokeRect(x0+5.5,y0+3.5,19,13)}
 else if(kind==="error"){cx.beginPath();cx.moveTo(x0+15,y0+3.5);cx.lineTo(x0+24,y0+16.5);cx.lineTo(x0+6,y0+16.5);cx.closePath();cx.stroke();cx.fillRect(x0+14.2,y0+8,1.6,4.6);cx.fillRect(x0+14.2,y0+13.6,1.6,1.6)}
 else if(kind==="done"){cx.lineWidth=2;cx.beginPath();cx.moveTo(x0+8,y0+10.5);cx.lineTo(x0+13,y0+15);cx.lineTo(x0+23,y0+5);cx.stroke()}
 cx.restore();cx.restore()})}

var STEAM=[169.0,293.5];
function steamDraw(cx,tm){if(!BT.some(function(b){return b.cof&&!b.path.length}))return;cx.save();for(var i=0;i<5;i++){var ph=((tm*.55+i/5)%1),x=STEAM[0]+Math.sin(tm*2+i*1.7)*2.2+ph*2,y=STEAM[1]-ph*18,r=1.6+ph*3.2;cx.globalAlpha=(1-ph)*.8;cx.fillStyle="#f4f6ff";cx.beginPath();cx.arc(x,y,r,0,6.3);cx.fill()}cx.restore()}
var ARCS=[[[508.6,285.6],[517.5,288],[516.9,295.6],[507.7,292.8]],[[528.5,295.6],[536.9,298],[536.2,305.6],[527.9,303]]];
function mugDraw(cx,x,y,tm,b){cx.fillStyle="#f4efe6";cx.fillRect(x,y,4,5);cx.fillStyle="#d9d0c2";cx.fillRect(x+4,y+1,1,3);cx.fillStyle="#6b3b1f";cx.fillRect(x,y,4,1);if(b.cof){cx.fillStyle="rgba(244,246,255,"+(.35+.25*Math.sin(tm*4+b.ph))+")";cx.fillRect(x+1,y-2-Math.round((tm*3)%2),1,1);cx.fillRect(x+2,y-4+Math.round((tm*3)%2),1,1)}}
function arcadeDraw(cx,tm){BT.forEach(function(b){if(!b.arc||b.path.length)return;var q=ARCS[b.arc-1],hue=(tm*140+b.arc*90)%360,fl=.45+.35*Math.abs(Math.sin(tm*7));cx.save();cx.beginPath();q.forEach(function(p,i){i?cx.lineTo(p[0],p[1]):cx.moveTo(p[0],p[1])});cx.closePath();cx.fillStyle="hsla("+hue+",95%,62%,"+fl+")";cx.shadowColor="hsla("+hue+",95%,62%,.9)";cx.shadowBlur=8;cx.fill();cx.shadowBlur=0;cx.clip();cx.fillStyle="rgba(255,255,255,.9)";for(var i=0;i<4;i++){var u=((tm*1.7+i*.27)%1),v=((tm*.9+i*.41)%1);cx.fillRect(Math.round(q[0][0]+u*8),Math.round(q[0][1]+1+v*6+u*2),1,1)}cx.restore();cx.save();for(var j=0;j<3;j++){var ph=(tm*1.2+j/3)%1;cx.globalAlpha=(1-ph)*.8;cx.fillStyle="hsl("+((hue+j*120)%360)+",95%,65%)";cx.fillRect(Math.round(q[1][0]+2+Math.sin(tm*3+j)*3),Math.round(q[1][1]-2-ph*10),1,1)}cx.restore()})}
function binDraw(cx,tm,b,p){cx.save();cx.font="bold 8px monospace";cx.shadowColor="rgba(90,255,200,.9)";cx.shadowBlur=4;for(var i=0;i<7;i++){var ph=((tm*.7+i/7+b.ph)%1),x=Math.round(p[0]-10+((i*9+Math.floor(b.ph*10))%40)),y=Math.round(p[1]-14-ph*30);cx.globalAlpha=Math.min(1,Math.sin(ph*Math.PI)*1.3);cx.fillStyle=i%2?"#7dffcf":"#7fe8ff";cx.fillText(((Math.floor(tm*3+i*5))%2)?"1":"0",x,y)}cx.restore()}
var NEON={im:new Image(),ok:0};if(!MISS.plate){NEON.im.onload=function(){NEON.ok=1};NEON.im.src="assets/neon-front.webp"}
function deskIdleDraw(cx,tm){BT.forEach(function(b){if(b.path.length||!atSeat(b)||holoOn(b)||b.st!=="idle")return;var p=P(b.x,b.y,0),bob=Math.sin(tm*1.6+b.ph)*1,x0=Math.round(p[0]+8),y0=Math.round(p[1]-52+bob),w=14,h=9,a=.32+.08*Math.sin(tm*2+b.ph);
 cx.save();cx.globalAlpha=a;cx.shadowColor="rgba(80,230,255,.8)";cx.shadowBlur=4;cx.fillStyle="rgba(30,170,230,.35)";cx.strokeStyle="rgba(150,245,255,.9)";cx.lineWidth=1;cx.beginPath();cx.rect(x0+.5,y0+.5,w,h);cx.fill();cx.stroke();cx.shadowBlur=0;
 cx.fillStyle="rgba(210,252,255,1)";cx.fillRect(x0+3,y0+3,6,1);if(Math.floor(tm*2+b.ph)%2)cx.fillRect(x0+3+6+1,y0+2,1,3);cx.fillRect(x0+3,y0+6,4,1);cx.restore();
 cx.save();for(var i=0;i<2;i++){var on=(Math.floor(tm*5+i*2+b.ph*7)%3)===0;if(!on)continue;cx.globalAlpha=.7;cx.fillStyle="#bff6ff";cx.fillRect(Math.round(p[0]+10+i*4),Math.round(p[1]-15-i),1,1)}cx.restore()})}
var PLT={k:0.8627,x:99.8,y:7.0};function plm(p){return IS.pl?[p[0]*PLT.k+PLT.x,p[1]*PLT.k+PLT.y]:p}
function isoDraw(tm){var cx=IS.cx,RR=IS.R||1;cx.setTransform(RR,0,0,RR,0,0);cx.imageSmoothingEnabled=true;cx.imageSmoothingQuality="medium";cx.clearRect(0,0,IS.IW,IS.IH);if(IS.pl){if(PL.cr!==RR){var pc=document.createElement("canvas");pc.width=672*RR;pc.height=448*RR;var px=pc.getContext("2d");px.imageSmoothingEnabled=true;px.imageSmoothingQuality="high";px.drawImage(PL.c,0,0,pc.width,pc.height);PL.cR=pc;PL.cr=RR}cx.setTransform(1,0,0,1,0,0);cx.drawImage(PL.cR,0,0);cx.setTransform(PLT.k*RR,0,0,PLT.k*RR,PLT.x*RR,PLT.y*RR);monDraw(cx,tm)}else cx.drawImage(IS.floor,0,0);
 var L=[];if(!IS.pl){wallDrawables(L);furnDrawables(L)}BT.forEach(function(b){L.push({d:IS.pl?b.y:b.x+b.y+.25,f:function(c,t){drawBot(c,b,t)}})});if(IS.pl&&NEON.ok)L.push({d:320,f:function(c){var k=1344/1340/2;c.save();c.setTransform(RR,0,0,RR,0,0);c.drawImage(NEON.im,376*k,484*k,62*k,88*k);c.restore()}});
 L.sort(function(a,b){return a.d-b.d});if(IS.pl)arcadeDraw(cx,tm);L.forEach(function(o){o.f(cx,tm)});if(IS.pl){deskIdleDraw(cx,tm);steamDraw(cx,tm)}holoDraw(cx,tm);
 BT.forEach(function(b){var e=OFF.E[b.k];if(!e)return;var hp=plm(P(b.x,b.y,b.z+1.15+1.35)),px=IS.ox+hp[0]*IS.sc,py=IS.oy+hp[1]*IS.sc,bw=$("board").clientWidth;if(e.eb.classList.contains("on")){var half=e.eb.offsetWidth/2+6;e.eb.style.left=Math.max(half,Math.min(bw-half,px))+"px";e.eb.style.top=py+"px"}})}
function atSeat(b){return Math.abs(b.x-b.home[0])<3&&Math.abs(b.y-b.home[1])<3}
var WAITS=[[[245.5,303.5],225,"",""],[[258.0,314.5],225,"",""]];
function spotTaken(s,self){return BT.some(function(o){return o!==self&&o.res===s})}
var GROUP_OFF=0;
var GLINES={arcInvite:[["Wanna play a round?","You're on!"],["Arcade break?","Let's go!"]],arc:[["I'm winning this time.","No way!"],["Combo!","Not fair, haha."],["One more round?","Okay, last one."]],
cofInvite:[["Coffee break, anyone?","Count me in.","Me too!"],["Who wants coffee?","Yes please.","Same here!"]],cof:[["This espresso is good.","Best part of the day."],["Long day so far.","Same, but we got this."]],
life:[["Do you ever wonder what we'd do on a beach?","Probably still check our inbox, haha."],["What's your dream?","A day with zero errors."],["I like working with you all.","Same here, team."],["If you could travel anywhere?","Somewhere with fast Wi-Fi."],["Weekend plans?","Charging and chilling."],["Do bots get tired?","Only when the Wi-Fi drops."]]};
function freeBots(ex){return BT.filter(function(o){return o!==ex&&!o.act&&OFF.busy[o.k]!==1&&o.st==="idle"&&!o.path.length&&atSeat(o)})}
function spotsBy(f){var r=[];SPOTS.forEach(function(s){if(f(s))r.push(s)});return r}
function pick(a){return a[Math.floor(Math.random()*a.length)]}
function groupGo(lead,kind){if(kind==="arc"&&SPOTS.some(function(s){return (s[5]==="a0"||s[5]==="a1")&&BT.some(function(o){return o!==lead&&o.res===s})}))return false;if(kind==="cof"&&SPOTS.filter(function(s){return s[5]==="c"&&!BT.some(function(o){return o!==lead&&o.res===s})}).length<2)return false;var others=freeBots(lead).sort(function(){return Math.random()-.5});if(!others.length)return false;var mem=[lead].concat(others.slice(0,kind==="arc"?1:2));
 mem.forEach(function(b){b.tok=(b.tok||0)+1;b._g=b.tok;b.act=1;OFF.busy[b.k]=2});
 function alive(b){return b.tok===b._g}
 function home(){mem.forEach(function(b){if(!alive(b))return;officeWalk(b.k,route(b,b.home),function(){if(!alive(b))return;b.home_th=SEATTH;b.act=0;OFF.busy[b.k]=0})})}
 function say(lines,done){var i=0;(function nx(){if(!mem.some(alive)){return}if(i>=lines.length){setTimeout(done,1200);return}var b=mem[i%mem.length];if(alive(b))ebSay(b.k,lines[i],2200);i++;setTimeout(nx,2300)})()}
 function goTo(spots,after){spots=spots.filter(function(s){return !BT.some(function(o){return mem.indexOf(o)<0&&o.res===s})});if(!spots.length){home();return}var n=0,started=false;function arrive(){n++;if(n>=mem.length&&!started){started=true;after()}}
  mem.forEach(function(b,i){var s=spots[i%spots.length];if(i>=spots.length){s=WAITS[(i-spots.length)%WAITS.length]}officeWalk(b.k,route(b,s[0]),function(){if(!alive(b)){arrive();return}b.home_th=s[1];b.sit=s[4]||0;b.cof=s[5]==="c";b.arc=s[5]==="a0"?1:s[5]==="a1"?2:0;arrive()});b.res=s});
  setTimeout(function(){if(!started){started=true;after()}},25000)}
 var inv=pick(kind==="arc"?GLINES.arcInvite:GLINES.cofInvite);ebSay(lead.k,inv[0],2000);setTimeout(function(){for(var j=1;j<mem.length;j++)(function(j){setTimeout(function(){if(alive(mem[j]))ebSay(mem[j].k,inv[Math.min(j,inv.length-1)],1800)},(j-1)*900)})(j)},1100);
 setTimeout(function(){
  if(kind==="arc"){goTo(spotsBy(function(s){return s[5]==="a0"||s[5]==="a1"}),function(){say(pick(GLINES.arc).concat(pick(GLINES.arc)),home)})}
  else{goTo(spotsBy(function(s){return s[5]==="c"}),function(){say(pick(GLINES.cof),function(){var seats=spotsBy(function(s){return (s[4]||0)>0&&s[5]!=="c"}).sort(function(){return Math.random()-.5});goTo(seats,function(){var a=pick(GLINES.life),b2=pick(GLINES.life);say(a.concat(b2===a?[]:b2),home)})})})}
 },2600);return true}
var TRAIN=[[254.5,220.5],[352,188],[449.5,228.5],[401,277.5],[287,277.5],[221.5,253]],LAUGHAT=[352,245],SEEK=[[323,178.5],270],
 HIDES=[[280.5,385],[389.5,391.5],[492,318],[132,171.5],[335.5,424],[519,257],[181,171.5],[563.5,171.5],[474,204]],
 FUN={trainIn:[["Train time! Who's in?","Choo choo!","Wait for me!","All aboard!"]],train:["Choo choo!","Next stop: the coffee machine!","Tickets, please!","Faster!","Woo woo!"],
 jokes:[["Why did the bot cross the road?","Why?","To get to the other site!","HAHAHA"],["What's a bot's favorite snack?","What?","Micro-chips!","Hahaha, stop!"],["I told my PC a joke.","And?","It didn't get it. No sense of humor.exe","LOL"],["I finished my to-do list!","Really?","It had one item.","HAHAHA"]],
 seekIn:[["Anyone up for hide-and-seek?","Okay! Hide!"],["Let's play hide and seek!","Not it!"]],count:["1… 2… 3…","…8… 9… 10!","Ready or not, here I come!"],
 found:["Found you!","Gotcha!","I see you!"],caught:["Aww!","No way!","Hehe, you got me.","How?!"]};
function faceTo(b,pt){return Math.round((Math.atan2(pt[1]-b.y,pt[0]-b.x)*180/Math.PI+360)%360)}
function hop(b,s){b.hopU=performance.now()/1000+(s||1.6)}
function groupFun(lead,kind){var need=kind==="laugh"?1:2,others=freeBots(lead).sort(function(){return Math.random()-.5});if(others.length<need)return false;
 var mem=[lead].concat(others.slice(0,kind==="laugh"?Math.min(2,others.length):kind==="hide"?Math.min(3,others.length):Math.min(4,others.length)));
 mem.forEach(function(b){b.tok=(b.tok||0)+1;b._g=b.tok;b.act=1;OFF.busy[b.k]=2});
 function alive(b){return b.tok===b._g}
 function goHome(b){if(!alive(b))return;b.hid=0;officeWalk(b.k,route(b,b.home),function(){if(!alive(b))return;b.home_th=SEATTH;b.act=0;OFF.busy[b.k]=0})}
 function home(){mem.forEach(goHome)}
 function at(b,pt,th,cb){officeWalk(b.k,route(b,pt),function(){if(!alive(b))return;if(th!=null)b.home_th=th;cb&&cb()})}
 function all(fn,done){var n=0;mem.forEach(function(b,i){fn(b,i,function(){if(++n===mem.length)done()})});setTimeout(function(){if(n<mem.length){n=mem.length;done()}},20000)}
 if(kind==="train"){var inv=pick(FUN.trainIn);ebSay(lead.k,inv[0],2000);sfx("toot",lead);
  setTimeout(function(){mem.slice(1).forEach(function(b,j){setTimeout(function(){if(alive(b))ebSay(b.k,inv[1+j%3],1600)},j*700)});
   var n=TRAIN.length,seat=function(dist){var k=0,cur=TRAIN[0];while(true){var pv=TRAIN[(n-1-k+n*9)%n],sl=Math.hypot(cur[0]-pv[0],cur[1]-pv[1]);if(dist<=sl){var f=dist/sl;return{pt:[cur[0]+(pv[0]-cur[0])*f,cur[1]+(pv[1]-cur[1])*f],k:k}}dist-=sl;cur=pv;k++}};all(function(b,i,ok){var q=seat(20*i);b._tr=q;at(b,q.pt,null,ok)},function(){var loop=[];for(var L=0;L<2;L++)for(var w=1;w<=n;w++)loop.push(TRAIN[w%n].slice());var arrived=0,ended=0;function trainEnd(){if(ended)return;ended=1;var line=mem.filter(alive);if(!line.length)return;
   // stop in line, then the lead turns around to face the others
   sfx("toot",lead);ebSay(lead.k,"Last stop!",1600);line.forEach(function(b,i){b.home_th=faceTo(b,i===0&&line[1]?[line[1].x,line[1].y]:[lead.x,lead.y])});
   setTimeout(function(){if(!alive(lead))return home();if(line[1])lead.home_th=faceTo(lead,[line[1].x,line[1].y]);hop(lead,1.2);
    if(Math.random()<.55){ebSay(lead.k,pick(["That was fun!","Best ride ever!","Again tomorrow?"]),1800);setTimeout(function(){line.forEach(function(b,i){if(!alive(b))return;setTimeout(function(){if(!alive(b))return;hop(b,2);ebSay(b.k,pick(["HAHAHA","Hahaha!","LOL","Hehehe"]),1700);sfx("giggle",b)},i*250)});setTimeout(home,2600)},1400)}
    else{ebSay(lead.k,pick(["Okay, back to work!","Break's over, team!","Back to our desks!"]),1800);setTimeout(function(){line.slice(1).forEach(function(b,i){if(alive(b))setTimeout(function(){if(alive(b))ebSay(b.k,pick(["On it!","Okay!","Aye aye!"]),1300)},i*300)});setTimeout(home,900)},1300)}},1500)}
  mem.forEach(function(b,i){if(!alive(b))return;var q=b._tr,pre=[];for(var m=q.k;m>=1;m--)pre.push(TRAIN[(n-m)%n].slice());pre.push(TRAIN[0].slice());b.x=q.pt[0];b.y=q.pt[1];
   // stop at your own spot in the line (same distance as at the start) instead of all piling onto the last point
   var full=pre.concat(loop),cut=full.slice(0,Math.max(1,full.length-(q.k+1)));cut.push(q.pt.slice());
   setTimeout(function(){if(!alive(b))return;officeWalk(b.k,cut,function(){if(!alive(b))return;if(++arrived>=mem.filter(alive).length)trainEnd()})},60)});
  setTimeout(trainEnd,60000);var said=0,iv=setInterval(function(){if(!mem.some(alive)||said>5){clearInterval(iv);return}var b=mem[said%mem.length];if(alive(b)&&b.path.length){ebSay(b.k,pick(FUN.train),1500);if(said%2===0)sfx("toot",b)}said++},2600)})},1500);return true}
 if(kind==="laugh"){var j=pick(FUN.jokes);ebSay(lead.k,"Guys, come here, I've got one!",2000);
  setTimeout(function(){all(function(b,i,ok){var an=(i/mem.length)*Math.PI*2+.6,pt=[LAUGHAT[0]+Math.cos(an)*22,LAUGHAT[1]+Math.sin(an)*12];at(b,pt,null,function(){b.home_th=faceTo(b,LAUGHAT);ok()})},function(){
   var i=0;(function nx(){if(!mem.some(alive))return;if(i>=j.length){mem.forEach(function(b){if(alive(b)){hop(b,2.2);ebSay(b.k,pick(["HAHAHA","Hahaha!","LOL","Hehehe"]),1800);sfx("giggle",b)}});setTimeout(home,2600);return}
    var b=i===1?mem[1]:mem[0];if(alive(b)){ebSay(b.k,j[i],2100);if(i===j.length-1){hop(b,2);sfx("giggle",b)}}i++;setTimeout(nx,2200)})()})},1200);return true}
 if(kind==="hide"){var seeker=lead,hiders=mem.slice(1),inv2=pick(FUN.seekIn),spots=HIDES.slice().sort(function(){return Math.random()-.5});ebSay(seeker.k,inv2[0],2000);
  setTimeout(function(){hiders.forEach(function(b,j){if(alive(b))setTimeout(function(){ebSay(b.k,inv2[1],1400)},j*500)});
   at(seeker,SEEK[0],SEEK[1],function(){var c=0;(function cnt(){if(!alive(seeker))return home();if(c<FUN.count.length){ebSay(seeker.k,FUN.count[c],2000);c++;setTimeout(cnt,2400);return}
     var order=hiders.filter(alive).sort(function(){return Math.random()-.5});(function nxt(){if(!alive(seeker))return home();var h=order.shift();if(!h){ebSay(seeker.k,"Found everyone! Again later?",2200);setTimeout(function(){goHome(seeker)},1500);return}
      if(!alive(h))return nxt();var pt=[h.x+(h.x<LAUGHAT[0]?14:-14),h.y+6];at(seeker,pt,null,function(){seeker.home_th=faceTo(seeker,[h.x,h.y]);h.hid=0;h.home_th=faceTo(h,[seeker.x,seeker.y]);ebSay(seeker.k,pick(FUN.found),1600);hop(h,1.2);
       setTimeout(function(){if(alive(h)){ebSay(h.k,pick(FUN.caught),1600);sfx("giggle",h)}setTimeout(function(){goHome(h);nxt()},1300)},900)})})()})()});
   hiders.forEach(function(b,j){var s=spots[j%spots.length];at(b,s,null,function(){b.hid=1;b.home_th=faceTo(b,SEEK[0])})})},1400);return true}
 return false}
function chatPick(){return pick(CHAT)}
function idleGo(b){if(IS.pl&&!GROUP_OFF&&Math.random()<.45&&freeBots(b).length){var r=Math.random(),kd=r<.25?"arc":r<.5?"cof":r<.67?"train":r<.84?"laugh":"hide";if(kd==="arc"||kd==="cof"?groupGo(b,kd):groupFun(b,kd))return}var tk=b.tok=(b.tok||0)+1,k=b.k;b.act=1;OFF.busy[k]=2;
 function back(){if(b.tok!==tk)return;officeWalk(k,route(b,b.home),function(){if(b.tok!==tk)return;b.home_th=SEATTH;b.act=0;OFF.busy[k]=0})}
 var others=freeBots(b);
 if(others.length&&Math.random()<.45){var o=others[Math.floor(Math.random()*others.length)],left=b.home[0]<o.home[0],sp=[o.home[0]+(left?-34:34),o.home[1]+8],ln=chatPick(b,o);o.act=2;b.pal=o;
  officeWalk(k,route(b,sp),function(){if(b.tok!==tk)return;b.home_th=left?0:180;o.home_th=left?180:0;ebSay(k,ln[0],2300);setTimeout(function(){if(b.tok===tk)ebSay(o.k,ln[1],2300)},1500);setTimeout(function(){if(o.act===2){o.home_th=SEATTH;o.act=0}b.pal=null;back()},4400)});return}
 var s2=pick(SPOTS);if(spotTaken(s2,b)){if(s2[5]==="c"){var fc=SPOTS.filter(function(s){return s[5]==="c"&&!spotTaken(s,b)});if(fc.length)s2=fc[0];else{coffeeQueue(b,tk,back);return}}else{var fr=SPOTS.filter(function(s){return !spotTaken(s,b)});if(!fr.length){back();return}s2=pick(fr)}}
 goSpot(b,tk,s2,back)}
function goSpot(b,tk,s2,back){var k=b.k;officeWalk(k,route(b,s2[0]),function(){if(b.tok!==tk)return;b.home_th=s2[1];b.sit=s2[4]||0;b.cof=s2[5]==="c";b.arc=s2[5]==="a0"?1:s2[5]==="a1"?2:0;ebSay(k,s2[2],2300);setTimeout(function(){if(b.tok===tk)ebSay(k,s2[3],2300)},2400);setTimeout(back,5000)});b.res=s2}
function coffeeQueue(b,tk,back){var w=WAITS.filter(function(s){return !spotTaken(s,b)})[0];if(!w){back();return}var k=b.k,t0=Date.now();
 officeWalk(k,route(b,w[0]),function(){if(b.tok!==tk)return;b.home_th=w[1];ebSay(k,pick(["I'll wait for a seat.","All full, I'll wait.","Save me a cup!"]),2300);var sitter=BT.filter(function(o){return o.cof&&!o.path.length})[0];if(sitter)setTimeout(function(){if(b.tok===tk)ebSay(sitter.k,pick(["Almost done!","Two more sips.","Pull up, we're talking."]),2200)},1600);
  (function poll(){if(b.tok!==tk)return;var fc=SPOTS.filter(function(s){return s[5]==="c"&&!spotTaken(s,b)});if(fc.length){goSpot(b,tk,fc[0],back);return}if(Date.now()-t0>30000){back();return}setTimeout(poll,1500)})()});b.res=w}
/* Only an agent that really has work goes back to its desk; everyone else keeps playing. An agent that
   gets work in the middle of a group activity leaves it alone (its token changes, so the group's
   timers skip it) and the others carry on. Nothing here waits for, or delays, the real work. */
function idleTick(dt){BT.forEach(function(b){if(OFF.busy[b.k]===1)return;
 if(b.st!=="idle"){if(b.act||OFF.busy[b.k]===2){b.act=0;b.tok=(b.tok||0)+1;OFF.busy[b.k]=0;b.path=[];b.done=null;b.hid=0;b.res=null;b.sit=0;b.cof=0;b.arc=0;if(b.pal&&b.pal.act===2){b.pal.act=0;b.pal.home_th=SEATTH}b.pal=null}if(!b.path.length&&!atSeat(b)){b.rush=1;officeWalk(b.k,route(b,b.home),function(){b.home_th=SEATTH;b.rush=0})}return}
 b.rush=0;if(b.act===2||b.act===1||b.path.length)return;if(!atSeat(b)){officeWalk(b.k,route(b,b.home),function(){b.home_th=SEATTH});return}
 b.idle=(b.idle===undefined?3+Math.random()*6:b.idle)-dt;if(b.idle>0)return;b.idle=7+Math.random()*9;OFF.idleStarts=(OFF.idleStarts||0)+1;idleGo(b)})}
function isoUpdate(dt){var moving=false;if(IS.pl)idleTick(dt);BT.forEach(function(b){b.z=0;if(b.path&&b.path.length){var t=b.path[0],dx=t[0]-b.x,dy=t[1]-b.y,d=Math.sqrt(dx*dx+dy*dy),st=(IS.pl?75:3.6)*dt*(b.rush?1.9:1);b.walk=true;moving=true;if(d>.02)b.tth=Math.atan2(dy,dx)*180/Math.PI;if(d<=st){b.x=t[0];b.y=t[1];b.path.shift();if(!b.path.length){b.walk=false;var f=b.done;b.done=null;if(f)f()}}else{b.x+=dx/d*st;b.y+=dy/d*st}}
  else{b.walk=false;b.tth=b.home_th}
  var diff=((b.tth-b.th+540)%360)-180;if(Math.abs(diff)>1)b.th+=Math.sign(diff)*Math.min(Math.abs(diff),620*dt)});return moving}
var SND={on:ls("snd")==="1",ac:null,m:null,fx:null,mu:null,nz:null,beat:0,nt:0,iv:0};
function sndInit(){if(SND.ac)return true;var A=window.AudioContext||window.webkitAudioContext;if(!A)return false;var a=SND.ac=new A();SND.m=a.createGain();SND.m.gain.value=.8;SND.m.connect(a.destination);SND.fx=a.createGain();SND.fx.gain.value=.9;SND.fx.connect(SND.m);SND.mu=a.createGain();SND.mu.gain.value=0;SND.mu.connect(SND.m);
 var n=a.sampleRate*2,bf=a.createBuffer(1,n,a.sampleRate),d=bf.getChannelData(0);for(var i=0;i<n;i++)d[i]=Math.random()*2-1;SND.nz=bf;return true}
function sndLive(){return SND.on&&SND.ac&&SND.ac.state==="running"&&IS.on&&!document.hidden}
function sndOut(pan,vol){var a=SND.ac,g=a.createGain();g.gain.value=vol;if(a.createStereoPanner){var p=a.createStereoPanner();p.pan.value=Math.max(-1,Math.min(1,pan||0));g.connect(p);p.connect(SND.fx)}else g.connect(SND.fx);return g}
function sndNoise(t,dur,type,f,q,vol,out,atk){var a=SND.ac,s=a.createBufferSource();s.buffer=SND.nz;var fl=a.createBiquadFilter();fl.type=type;fl.frequency.value=f;fl.Q.value=q||1;var g=a.createGain();g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(vol,t+(atk||.003));g.gain.exponentialRampToValueAtTime(.0001,t+dur);s.connect(fl);fl.connect(g);g.connect(out);s.start(t,Math.random()*1.5);s.stop(t+dur+.05);return fl}
function sndTone(t,dur,type,f0,f1,vol,out,atk){var a=SND.ac,o=a.createOscillator();o.type=type;o.frequency.setValueAtTime(f0,t);if(f1)o.frequency.exponentialRampToValueAtTime(f1,t+dur);var g=a.createGain();g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(vol,t+(atk||.004));g.gain.exponentialRampToValueAtTime(.0001,t+dur);o.connect(g);g.connect(out);o.start(t);o.stop(t+dur+.05)}
function sndWhere(b){var p=plm(P(b.x,b.y,0)),bw=$("board").clientWidth||1,sx=IS.ox+p[0]*IS.sc,vis=sx>-40&&sx<bw+40;return{pan:(sx/bw-.5)*1.4,vol:(vis?1:.35)*Math.min(1,.45+.55*IS.z)}}
var SFX={
 tpin:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.2),i;for(i=0;i<12;i++)sndTone(t+i*.024,.032,"square",1700*Math.pow(.86,i),0,.55,o,.002);sndNoise(t+.29,.07,"highpass",3200,1,.4,o);sndTone(t+.3,.1,"square",440,990,.55,o,.003);sndTone(t+.37,.24,"triangle",1320,0,.4,o);sndTone(t+.37,.18,"square",1760,0,.12,o)},
 tpout:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.2),i;sndTone(t,.1,"square",990,440,.45,o,.003);for(i=0;i<14;i++)sndTone(t+.1+i*.022,.03,"square",260*Math.pow(1.19,i),0,.5,o,.002);sndNoise(t+.12,.32,"bandpass",4200,2,.25,o,.04)},
 step:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.22);sndNoise(t,.06,"lowpass",420,1,1,o);sndTone(t,.05,"sine",140,70,.5,o)},
 key:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.14),n=2+Math.floor(Math.random()*4);for(var i=0;i<n;i++){var u=t+i*(.07+Math.random()*.06);sndNoise(u,.025,"bandpass",2600+Math.random()*1800,3,1,o);sndTone(u,.02,"square",180,0,.08,o)}},
 brew:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.3);sndTone(t,.35,"sawtooth",58,52,.18,o,.05);var f=sndNoise(t+.25,2.2,"bandpass",2400,.8,.55,o,.35);f.frequency.linearRampToValueAtTime(4200,t+2.4);for(var i=0;i<4;i++)sndTone(t+2.6+i*.32+Math.random()*.08,.09,"sine",1300-i*90,620,.35,o)},
 bleep:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.12),sc=[523,587,659,784,880,1047,1175],n=3+Math.floor(Math.random()*3),up=Math.random()<.5;for(var i=0;i<n;i++)sndTone(t+i*.075,.07,"square",sc[(up?i*2:6-i*2+7)%7]*(Math.random()<.2?2:1),0,.6,o,.002);if(Math.random()<.18)sndNoise(t+n*.075,.18,"highpass",1800,1,.5,o)},
 ding:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.22);sndTone(t,.7,"sine",1319,0,.6,o);sndTone(t+.11,.9,"sine",1760,0,.5,o);sndTone(t,.5,"triangle",2637,0,.08,o)},
 toot:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.16);sndTone(t,.22,"square",587,0,.5,o,.01);sndTone(t,.22,"square",740,0,.35,o,.01);sndTone(t+.26,.38,"square",587,0,.5,o,.01);sndTone(t+.26,.38,"square",740,0,.35,o,.01)},
 giggle:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.13),f=700+Math.random()*250;for(var i=0;i<5;i++)sndTone(t+i*.09,.07,"triangle",f*(1+(i%2)*.12),f*.85,.7,o,.003)},
 pop:function(w){var t=SND.ac.currentTime,o=sndOut(w.pan,w.vol*.13);sndTone(t,.07,"sine",520,1150,.8,o,.002)}
};
function sfx(k,b){if(!sndLive())return;try{SFX[k](b?sndWhere(b):{pan:0,vol:1})}catch(e){}}
function sndTick(dt){if(!sndLive())return;BT.forEach(function(b){b.sT=(b.sT||0)-dt;var mode=b.path.length?"walk":b.cof?"cof":b.arc?"arc":holoOn(b)?"key":"";if(mode!==b.sM){b.sM=mode;b.sT=mode==="cof"?.4:mode==="walk"?0:.2+Math.random()*.4}if(!mode||b.sT>0)return;
 if(mode==="walk"){b.sT=1}else if(mode==="key"){sfx("key",b);b.sT=.45+Math.random()*1.4}else if(mode==="arc"){sfx("bleep",b);b.sT=.5+Math.random()*.6}else if(mode==="cof"){sfx("brew",b);b.sT=9+Math.random()*6}})}
var MUS={ch:[[53,57,60,64],[52,55,59,62],[50,53,57,60],[48,52,55,59]],bpm:74};
function mf(n){return 440*Math.pow(2,(n-69)/12)}
function musSched(){if(!SND.ac)return;var a=SND.ac,live=sndLive();SND.mu.gain.setTargetAtTime(live?.11:0,a.currentTime,.6);if(!live){SND.nt=0;return}var sp=60/MUS.bpm/2;if(!SND.nt||SND.nt<a.currentTime)SND.nt=a.currentTime+.1;
 while(SND.nt<a.currentTime+.4){var t=SND.nt,s=SND.beat%32,c=MUS.ch[Math.floor(SND.beat/8)%4],o=SND.mu;
  if(s%8===0)c.forEach(function(n){var os=a.createOscillator(),f=a.createBiquadFilter(),g=a.createGain();os.type="triangle";os.frequency.value=mf(n);os.detune.value=(Math.random()-.5)*14;f.type="lowpass";f.frequency.value=900;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.16,t+.5);g.gain.linearRampToValueAtTime(.0001,t+sp*8);os.connect(f);f.connect(g);g.connect(o);os.start(t);os.stop(t+sp*8+.1)});
  if(s%8===0)sndTone(t,sp*7,"sine",mf(c[0]-12),0,.35,o,.02);
  if([0,3,4,6].indexOf(s%8)>=0&&Math.random()<.85)sndTone(t,.5,"sine",mf(c[(s+Math.floor(SND.beat/8))%4]+12),0,.16,o,.004);
  if(s%4===0)sndTone(t,.25,"sine",110,45,.5,o);if(s%4===2)sndNoise(t,.04,"highpass",7000,1,.12,o);if(s%8===4)sndNoise(t,.14,"bandpass",1800,.6,.18,o);
  SND.beat++;SND.nt+=sp*(s%2?.92:1.08)}}
function sndUI(){var b=$("zSnd");if(b){b.textContent=SND.on?"🔊":"🔇";b.title=SND.on?"Sound on (click to mute)":"Sound off (click for music and sounds)";b.classList.toggle("on",SND.on)}}
function sndSet(on){SND.on=on;ls("snd",on?"1":"0");if(on&&sndInit()){SND.ac.resume();if(!SND.iv)SND.iv=setInterval(musSched,120)}sndUI();if(on)setTimeout(function(){sfx("pop")},60)}
document.addEventListener("pointerdown",function(){if(SND.on&&sndInit()){if(SND.ac.state!=="running")SND.ac.resume();if(!SND.iv)SND.iv=setInterval(musSched,120)}},true);
function isoLoop(t){IS.raf=0;if(!IS.on||document.hidden)return;var dt=Math.min(.06,(t-IS.last)/1000||0);IS.last=t;var mv=isoUpdate(dt),q0=performance.now();isoDraw(t/1000);IS.ms=(IS.ms||0)*.9+(performance.now()-q0)*.1;sndTick(dt);var busy=mv||BT.some(function(b){return b.st==="working"||b.st==="waiting"||(b.flash&&b.flash.until>performance.now())});IS.timer=setTimeout(function(){IS.raf=requestAnimationFrame(isoLoop)},(busy||sndLive())?0:70)}
function isoStart(){if(IS.raf||IS.timer)return;IS.last=performance.now();isoLayout();IS.raf=requestAnimationFrame(isoLoop)}
function isoStop(){cancelAnimationFrame(IS.raf);clearTimeout(IS.timer);IS.raf=0;IS.timer=0}
function isoLayout(){var bd=$("board"),bw=bd.clientWidth,bh=bd.clientHeight;if(!bw||!bh)return;IS.fit=Math.min(bw/IS.IW,bh/IS.IH);IS.sc=IS.fit*IS.z;var w=IS.IW*IS.sc,h=IS.IH*IS.sc;IS.ox=(bw-w)/2+IS.px;IS.oy=(bh-h)/2+IS.py;if(w>bw)IS.ox=Math.max(bw-w,Math.min(0,IS.ox));else IS.ox=(bw-w)/2;if(h>bh)IS.oy=Math.max(bh-h,Math.min(0,IS.oy));else IS.oy=(bh-h)/2;IS.px=IS.ox-(bw-w)/2;IS.py=IS.oy-(bh-h)/2;var cv=IS.cv,nr=Math.max(1,Math.min(4,Math.ceil(IS.sc*(window.devicePixelRatio||1))));if(nr!==IS.R){IS.R=nr;cv.width=IS.IW*nr;cv.height=IS.IH*nr}cv.style.left=IS.ox+"px";cv.style.top=IS.oy+"px";cv.style.width=w+"px";cv.style.height=h+"px"}
function isoZoom(nz,cx,cy){var bd=$("board"),bw=bd.clientWidth,bh=bd.clientHeight;nz=Math.max(1,Math.min(4,nz));var ix=(cx-IS.ox)/IS.sc,iy=(cy-IS.oy)/IS.sc;IS.z=nz;var sc=IS.fit*nz;IS.px=cx-ix*sc-(bw-IS.IW*sc)/2;IS.py=cy-iy*sc-(bh-IS.IH*sc)/2;isoLayout();if(!IS.raf&&!IS.timer&&IS.on)isoStart()}
function isoWorld(e){var r=IS.cv.getBoundingClientRect(),ix=(e.clientX-r.left)/IS.sc,iy=(e.clientY-r.top)/IS.sc;if(IS.pl){ix=(ix-PLT.x)/PLT.k;iy=(iy-PLT.y)/PLT.k;return {wx:ix,wy:iy,ix:ix,iy:iy}}var a=(ix-IS.OX)/(IS.TW/2),b=(iy-IS.OY)/(IS.TH/2);return {wx:(a+b)/2,wy:(b-a)/2,ix:ix,iy:iy}}
/* Only characters are clickable. Empty floor does nothing. */
function isoPick(e){var w=isoWorld(e),best=null,bd=1e9;for(var i=0;i<BT.length;i++){var b=BT[i],pp=P(b.x,b.y,b.z+1.2),dx=Math.abs(w.ix-pp[0]),dy=Math.abs(w.iy-pp[1]);if(dx<9*(IS.pl?1.6:1)&&dy<13*(IS.pl?1.6:1)&&dx+dy<bd){bd=dx+dy;best=b}}return best?{bot:best.id}:{}}
function officeInit(){if(OFF.built)return;var o=$("office");o.innerHTML='<canvas id="officeCv"></canvas><div class="zc"><button id="zIn" type="button" title="Zoom in">+</button><button id="zOut" type="button" title="Zoom out">\u2212</button><button id="zRs" type="button" title="Reset view">\u27f2</button><button id="zSnd" type="button" title="Sound">\ud83d\udd07</button></div>'+BT.map(function(b){return '<div class="eb" id="eb-'+b.k+'"></div>'}).join("");
 if(PL.ok)plateOn();IS.cv=$("officeCv");IS.cv.width=IS.IW;IS.cv.height=IS.IH;IS.cx=IS.cv.getContext("2d");if(!IS.pl)isoBuildFloor();
 BT.forEach(function(b){b.x=b.home[0];b.y=b.home[1];b.z=0;b.th=b.home_th=b.tth=IS.pl?SEATTH:45;b.ph=Math.random()*6;b.path=[];OFF.E[b.k]={eb:$("eb-"+b.k),t:0,txt:false}});
 IS.cv.addEventListener("click",function(e){if(IS.moved){IS.moved=0;return}var p=isoPick(e);if(p.bot&&OFF.onPick)OFF.onPick(p.bot)});
 IS.cv.addEventListener("mousemove",function(e){var p=isoPick(e);IS.hover=p.bot||"";IS.cv.style.cursor=p.bot?"pointer":"default"});
 (function(){var bd=$("board"),dn=null;function ctr(){return [bd.clientWidth/2,bd.clientHeight/2]}
 $("office").addEventListener("wheel",function(e){e.preventDefault();var r=bd.getBoundingClientRect();isoZoom(IS.z*(e.deltaY<0?1.15:1/1.15),e.clientX-r.left,e.clientY-r.top)},{passive:false});
 IS.cv.addEventListener("mousedown",function(e){dn={x:e.clientX,y:e.clientY,px:IS.px,py:IS.py};IS.moved=0});
 window.addEventListener("mousemove",function(e){if(!dn)return;var dx=e.clientX-dn.x,dy=e.clientY-dn.y;if(Math.abs(dx)+Math.abs(dy)>4)IS.moved=1;if(IS.moved&&IS.z>1){IS.px=dn.px+dx;IS.py=dn.py+dy;isoLayout();if(!IS.raf&&!IS.timer&&IS.on)isoStart()}});
 window.addEventListener("mouseup",function(){dn=null;if(IS.moved)setTimeout(function(){IS.moved=0},0)});
 $("zIn").onclick=function(){var c=ctr();isoZoom(IS.z*1.4,c[0],c[1])};$("zOut").onclick=function(){var c=ctr();isoZoom(IS.z/1.4,c[0],c[1])};$("zSnd").onclick=function(e){e.stopPropagation();sndSet(!SND.on)};sndUI();$("zRs").onclick=function(){IS.z=1;IS.px=0;IS.py=0;isoLayout();if(!IS.raf&&!IS.timer&&IS.on)isoStart()}})();
 IS.cv.addEventListener("mouseleave",function(){IS.hover=""});
 window.addEventListener("resize",function(){if(IS.on)isoLayout()});document.addEventListener("visibilitychange",function(){if(IS.on&&!document.hidden)isoStart()});
 OFF.built=true}
/* The standing bubble of a character mirrors its real state. Queued agents are not shown as working. */
function ebRefresh(k){var e=OFF.E[k],b=botK(k);if(!e||e.txt)return;e.eb.classList.remove("bad","q");if(b.st==="working"){e.eb.innerHTML='<span class="d"></span><span class="d"></span><span class="d"></span>';e.eb.classList.add("on")}else if(b.st==="waiting"){e.eb.textContent=b.note||"I need you";e.eb.classList.add("on","bad")}else if(b.st==="queued"){e.eb.textContent=b.note||"In the queue";e.eb.classList.add("on","q")}else e.eb.classList.remove("on")}

function ebSay(k,text,ms,bad){var e=OFF.E[k];if(!e)return;if(!e.txt)sfx("pop",botK(k));e.eb.textContent=text.length>86?text.slice(0,84)+"…":text;e.eb.classList.remove("q");e.eb.classList.toggle("bad",!!bad);e.bad=!!bad;e.eb.classList.add("on");e.txt=true;clearTimeout(e.t);e.t=setTimeout(function(){e.txt=false;ebRefresh(k)},ms||4500);if(!IS.raf&&!IS.timer&&IS.on)isoStart()}
function officeWalk(k,pts,done){var b=botK(k);if(!b)return;if(b.cof)b.mug=1;b.sit=0;b.cof=0;b.arc=0;b.res=null;b.hid=0;if(officeCalm()||!IS.on){var l=pts[pts.length-1];b.x=l[0];b.y=l[1];b.path=[];if(done)done();return}b.path=pts.map(function(p){return p.slice()});b.done=done;if(!IS.raf&&!IS.timer)isoStart()}

/* ---- public interface used by the dashboard ---- */
/* Server status -> how the character behaves. Anything not listed is "idle" (free to play). */
var VIS={queued:"queued",starting:"working",running:"working",tool:"working",cancelling:"working",awaiting_approval:"waiting",unknown:"waiting"};
var HOLO={thinking:"thinking",typing:"typing",starting:"thinking",terminal:"terminal",file_read:"file_read",research:"research",test:"test",coding:"coding",document:"document",database:"database",tool:"tool",scroll:"scroll"};
function kick(){if(IS.on&&!IS.raf&&!IS.timer)isoStart()}
function sync(agents){(agents||[]).forEach(function(a){var b=botId(a.id);if(!b)return;var spr=SPRC[a.sprite]?a.sprite:b.k;if(spr!==b.spr){b.spr=spr;b.c=SPRC[spr];b.eyes=SPRE[spr]}
  b.nm=a.name||b.nm;var r=RM.filter(function(x){return x.k===b.k})[0];if(r)r.n=b.nm.toUpperCase().slice(0,15);
  var st=VIS[a.status]||"idle";b.note=a.status==="unknown"?"Please review":a.status==="awaiting_approval"?"Approval needed":a.status==="queued"?"In the queue":"";
  b.holo=a.status==="cancelling"?"thinking":(HOLO[a.activity]||"thinking");b.st=st;if(OFF.built)ebRefresh(b.k)});kick()}
function flash(id,kind,ms){var b=botId(id);if(!b)return;b.flash={k:kind,until:performance.now()+(ms||3500)};if(kind==="done")sfx("ding",b);kick()}
function say(id,text,ms,bad){var b=botId(id);if(!b||!OFF.built||!IS.on)return;ebSay(b.k,String(text),ms||4200,bad)}
/* A real hand-off reported by the server: the source walks to the destination's desk and back. */
function handoff(fromId,toId,l1,l2){var b=botId(fromId),o=botId(toId);if(!b||!o||!OFF.built||!IS.on||OFF.busy[b.k]===1||b.st!=="idle")return;var k=b.k;b.tok=(b.tok||0)+1;b.act=0;b.path=[];b.done=null;OFF.busy[k]=1;ebSay(k,l1||"Handing this over\u2026",2600);
 officeWalk(k,rt(k,o.k,0),function(){ebSay(k,l2||"All yours!",1800);sfx("ding",b);setTimeout(function(){officeWalk(k,rt(k,o.k,1),function(){b.home_th=IS.pl?SEATTH:45;OFF.busy[k]=0})},900)})}
function setOn(on){IS.on=!!on;if(on){officeInit();BT.forEach(function(b){ebRefresh(b.k)});isoLayout();isoStart()}else isoStop()}
function ready(cb){if(PL.done)cb();else PL.cb=cb}
function stats(){return {on:IS.on,built:OFF.built,mode:IS.pl?"painted":"procedural",fps_idle:Math.round(1000/70),idleStarts:OFF.idleStarts||0,sound:SND.on,
  bots:BT.map(function(b){return {id:b.id,desk:b.k,sprite:b.spr,source:spriteSource(b),name:b.nm,st:b.st,holo:OFF.built?holoKind(b):"",x:Math.round(b.x),y:Math.round(b.y),atDesk:atSeat(b),moving:!!(b.path&&b.path.length),activity:b.act?1:0,bubble:OFF.E[b.k]&&OFF.E[b.k].eb.classList.contains("on")?OFF.E[b.k].eb.textContent:""}})}}
/* Screen position of a character (so tests and the selection outline can find it). */
function screenPos(id){var b=botId(id);if(!b||!IS.cv)return null;var p=plm(P(b.x,b.y,b.z+1.2)),r=IS.cv.getBoundingClientRect();return [r.left+p[0]*r.width/IS.IW,r.top+p[1]*r.height/IS.IH]}
AHQ.office={sync:sync,flash:flash,say:say,handoff:handoff,setOn:setOn,ready:ready,stats:stats,screenPos:screenPos,layout:function(){if(IS.on)isoLayout()},
 select:function(id){OFF.sel=id||null;kick()},onPick:function(fn){OFF.onPick=fn},
 /* test hooks: advance the simulation, or start one group activity now */
 debug:{tick:function(n,dt){for(var i=0;i<n;i++)isoUpdate(dt||.05)},fun:function(id,kind){var b=botId(id);return kind==="arc"||kind==="cof"?groupGo(b,kind):groupFun(b,kind)},idleNow:function(){BT.forEach(function(b){b.idle=0})}}};
})();

