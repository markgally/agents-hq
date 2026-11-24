"""One-off migration step: build static/js/office.js from the original 24/7 Bots office engine.

The drawing, sprite, path-finding, idle-activity and sound code is carried over unchanged from the
checkpoint copy of static/index.html. The parts tied to the old video workflow are replaced by the
hand-written blocks below (seven agents, generic states and holograms, new dialogue, no room clicks).

Usage: py tools/port_office.py <path to the original index.html>
"""
import io
import os
import sys

SRC = sys.argv[1]
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js", "office.js")
with io.open(SRC, encoding="utf-8") as fh:
    LINES = fh.read().split("\n")


def L(a, b=None):
    return "\n".join(LINES[a - 1:(b or a)])


def sub(text, old, new, count=1):
    if text.count(old) < 1:
        raise SystemExit("pattern not found: %r" % old[:90])
    return text.replace(old, new) if count == 0 else text.replace(old, new, count)


def cut(text, start, end):
    """Remove from `start` up to and including `end`."""
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[:i] + text[j:]


out = []
out.append(r'''/* AGENTS HQ - office view.
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
''')

# ---- canvas state and sizes
out.append(sub(L(1014, 1016), "WY:22", "WY:26"))

out.append(r'''/* Seven permanent desks. The desk key is also the default character of that slot:
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
''')

# ---- helpers, floor, walls
out.append(L(1024, 1032))
floor = L(1033, 1038)
floor = sub(floor, "if(y>=7&&y<11&&x>=1&&x<24)return 2;if(y>=18&&y<22&&x>=1&&x<24)return 3;return 0",
            "if(y>=7&&y<11&&x>=1&&x<24)return 2;if(y>=17&&y<19&&x>=1&&x<24)return 2;if(x>=11&&x<14&&y>=11&&y<17)return 2;return 0")
out.append(floor)
out.append(L(1039, 1042))
out.append(L(1043, 1048))
out.append(r''' /* One generic workstation per room. The monitor glows only while that agent is really working. */
 RM.forEach(function(r,i){var b=botK(r.k),on=!!b&&b.st==="working",top=r.y===1,dy=top?2.9:2.7,dx=top?1.5:1.6,dw=top?4.4:4.4;
  box(r.x+dx,r.y+dy,dw,1.35,.85,"#a8632f");monitor(r.x+dx+.9,r.y+dy+.15,.9,on,r.x+dx+.9+r.y+dy+3.2);if(i%2===0)monitor(r.x+dx+2.7,r.y+dy+.15,.9,false,r.x+dx+2.7+r.y+dy+3.2);else lamp(r.x+dx+3.6,r.y+dy+.2,r.x+dx+3.6+r.y+dy+1.2);
  if(top)shelf(r.x+1,r.y+.15,i===1?3:4.5);plant(r.x+.4,r.y+r.d-1.2);plant(r.x+r.w-1.1,r.y+r.d-1.2)});
 /* Hallway rugs and plants */
 plant(1.4,8.1);plant(23,8.1);L.push({d:12+9,f:function(cx){ibox(cx,9,8.2,0,7,1.6,.04,"#8a3d3d");ibox(cx,9.2,8.35,.04,6.6,1.3,.02,"#a64848")}});
 plant(1.4,17.3);plant(23,17.3)}
''')

# ---- characters: box robot, shared sheet, own sheets
out.append(L(1077, 1088))
spr = L(1089, 1115)
spr = sub(spr, 'im.src="assets/bots-sheet.webp"})();', 'if(!MISS.sheet)im.src="assets/bots-sheet.webp"})();')
spr = sub(spr, "t=sprTint(b.k,b.c,m[0],m[1]);", "t=sprTint(b.spr,b.c,m[0],m[1]);")
out.append(spr)

consts = L(1116, 1128)
consts = sub(consts, "pack:[497.0,254.5]},PLV={}", "pack:[497.0,254.5],ved:[-41.9,327.4],rvs:[8.4,304.3]},PLV={}")
i = consts.index('CHAT=[["Any new videos?"')
j = consts.index("\n", i)
consts = consts[:i] + r'''CHAT=[["Anyone have a new task?","Not yet. I'm ready when it comes."],["Busy day today?","Quiet so far."],["My desk is suspiciously clean.","Enjoy it while it lasts."],["I wonder what we'll work on today.","Something good, I hope."],["Coffee later?","You read my mind."],["One more arcade game?","Okay, just one."],["Wake me up when there's work.","Deal."],["A day without errors. That's my dream.","Dream big."]],''' + consts[j:]
out.append(consts)
out.append("SUITENAV.forEach(function(q){NAVW.push(q)});")

nav = L(1130, 1141)
nav = sub(nav, "var NAVBP=!HASSUITE?[]:[[", "var NAVBP=[[")
out.append(nav)
out.append(L(1142, 1143))

plate = L(1144, 1149)
plate = sub(plate, "if(HASSUITE)PL.doorDone=1;", "PL.doorDone=1;")
plate = sub(plate, 'im.onerror=plDone;im.src="assets/office-plate-door.webp"})();',
            'im.onerror=plDone;if(MISS.plate)setTimeout(plDone,0);else im.src="assets/office-plate-door.webp"})();')
out.append(plate)
out.append(L(1150))
out.append(r'''function plateOn(){IS.pl=1;IS.IW=672;IS.IH=448;IS.ZU=20;BT.forEach(function(b){b.home=PLH[b.k].slice()})}
/* Path for a hand-off walk from one desk to another (and back). */
function rt(k,to,back){var b=botK(k),o=botK(to),h=b.home;if(!IS.pl){var t=VISIT[to],ha=HALLOF[k],hb=HALLOF[to],fw=(ha===hb?[[h[0],ha],[t[0],ha]]:[[h[0],ha],[12.5,ha],[12.5,hb],[t[0],hb]]).concat([t]);return back?fw.slice(0,-1).reverse().concat([h.slice()]):fw}var t2=[o.home[0]+(o.home[0]>h[0]?-26:26),o.home[1]+4];return back?route(t2,h):route(b,t2)}
/* Own sprite sheets: five image files; the two extra characters are recoloured copies of one of them. */
var FS={n:0,ok:0,set:{}},FSR=1.5,FSKEYS=["in","cap","sch","mgr","pack"],FSTINT=[["ved",[245,150,50,120]],["rvs",[150,205,60,120]]];
function fsDone(){FS.n++;if(FS.n===FSKEYS.length)FS.ok=1}
function fsTint(im,tt){var c1=document.createElement("canvas");c1.width=im.width;c1.height=im.height;var x1=c1.getContext("2d");x1.drawImage(im,0,0);var kd=x1.getImageData(0,0,c1.width,c1.height),dd=kd.data;
 for(var q=0;q<dd.length;q+=4){var r=dd[q],g=dd[q+1],b=dd[q+2],m=Math.min(r,b);if(m>90&&g<m*.45&&Math.abs(r-b)<55)dd[q+3]=0;else{var lu=r*.3+g*.59+b*.11,mx=Math.max(r,g,b),sa=mx?(mx-Math.min(r,g,b))/mx:0;if(lu>=40&&sa>=.22&&b>r+20&&b>=g){var kk=Math.min(1.25,lu/tt[3]);dd[q]=Math.min(255,tt[0]*kk);dd[q+1]=Math.min(255,tt[1]*kk);dd[q+2]=Math.min(255,tt[2]*kk)}}}
 x1.putImageData(kd,0,0);return c1}
FSKEYS.forEach(function(k){if(MISS.sprites){setTimeout(fsDone,0);return}var im=new Image();im.onload=function(){try{fsBuild(k,im);if(k==="cap")FSTINT.forEach(function(h){fsBuild(h[0],fsTint(im,h[1]))})}catch(e){}fsDone()};im.onerror=fsDone;im.src="assets/bot-"+k+".webp"});
''')
out.append(L(1155, 1164))

draw = L(1165, 1168)
draw = sub(draw, "function drawBot(cx,b,tm){var set=FS.ok&&FS.set[b.k];", "function drawBotSprite(cx,b,tm){var set=FS.ok&&FS.set[b.spr];")
out.append(draw)
out.append(r'''/* Character plus its name tag and, for the agent whose workspace is open, an amber ring. */
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
''')

out.append(L(1187, 1192))
out.append('var NEON={im:new Image(),ok:0};if(!MISS.plate){NEON.im.onload=function(){NEON.ok=1};NEON.im.src="assets/neon-front.webp"}')
desk = L(1221, 1224)
desk = sub(desk, 'if(b.fx||b.path.length||!atSeat(b)||holoOn(b)||b.st==="working")return;', 'if(b.path.length||!atSeat(b)||holoOn(b)||b.st!=="idle")return;')
out.append(desk)
out.append(L(1263))

iso = L(1264, 1269)
iso = sub(iso, "suiteDraw(cx,tm);monDraw(cx,tm)}", "monDraw(cx,tm)}")
iso = sub(iso, "if(IS.pl){deskIdleDraw(cx,tm);holoDraw(cx,tm);steamDraw(cx,tm)}", "if(IS.pl){deskIdleDraw(cx,tm);steamDraw(cx,tm)}holoDraw(cx,tm);")
iso = cut(iso, " var sel=null;RM.forEach(", "cx.closePath();cx.stroke()});\n")
iso = sub(iso, "if(IS.pl)TEASE.forEach(function(o){L.push({d:o.y,f:function(c,t){teaseDraw(c,t,o)}})});", "")
out.append(iso)

# ---- idle engine
idle = L(1270, 1333)
idle = sub(idle, 'function freeBots(ex){return BT.filter(function(o){return o!==ex&&!o.gone&&!o.tp&&!o.act&&OFF.busy[o.k]!==1&&o.st!=="working"&&o.st!=="waiting"&&!o.path.length&&atSeat(o)})}',
           'function freeBots(ex){return BT.filter(function(o){return o!==ex&&!o.act&&OFF.busy[o.k]!==1&&o.st==="idle"&&!o.path.length&&atSeat(o)})}')
idle = sub(idle, '["Do you ever wonder what we\'d do on a beach?","Probably still post videos, haha."]', '["Do you ever wonder what we\'d do on a beach?","Probably still check our inbox, haha."]')
idle = sub(idle, '["Our views went up 200%!","Really?","From 1 to 3.","HAHAHA"]', '["I finished my to-do list!","Really?","It had one item.","HAHAHA"]')
idle = sub(idle, '"Next stop: coffee!"', '"Next stop: the coffee machine!"')
idle = sub(idle, 'seekIn:[["Hide and seek? I\'ll count!","Okay! Hide!"]', 'seekIn:[["Anyone up for hide-and-seek?","Okay! Hide!"]')
out.append(idle)
out.append("function chatPick(){return pick(CHAT)}")
go = L(1342, 1352)
go = sub(go, 'var others=BT.filter(function(o){return o!==b&&!o.gone&&!o.tp&&!o.act&&OFF.busy[o.k]!==1&&o.st!=="working"&&o.st!=="waiting"&&!o.path.length&&atSeat(o)});',
         "var others=freeBots(b);")
go = sub(go, "ln=chatPick(b,o);o.act=2;", "ln=chatPick(b,o);o.act=2;b.pal=o;")
go = sub(go, "if(o.act===2){o.home_th=SEATTH;o.act=0}back()", "if(o.act===2){o.home_th=SEATTH;o.act=0}b.pal=null;back()")
out.append(go)
out.append(r'''/* Only an agent that really has work goes back to its desk; everyone else keeps playing. An agent that
   gets work in the middle of a group activity leaves it alone (its token changes, so the group's
   timers skip it) and the others carry on. Nothing here waits for, or delays, the real work. */
function idleTick(dt){BT.forEach(function(b){if(OFF.busy[b.k]===1)return;
 if(b.st!=="idle"){if(b.act||OFF.busy[b.k]===2){b.act=0;b.tok=(b.tok||0)+1;OFF.busy[b.k]=0;b.path=[];b.done=null;b.hid=0;b.res=null;b.sit=0;b.cof=0;b.arc=0;if(b.pal&&b.pal.act===2){b.pal.act=0;b.pal.home_th=SEATTH}b.pal=null}if(!b.path.length&&!atSeat(b)){b.rush=1;officeWalk(b.k,route(b,b.home),function(){b.home_th=SEATTH;b.rush=0})}return}
 b.rush=0;if(b.act===2||b.act===1||b.path.length)return;if(!atSeat(b)){officeWalk(b.k,route(b,b.home),function(){b.home_th=SEATTH});return}
 b.idle=(b.idle===undefined?3+Math.random()*6:b.idle)-dt;if(b.idle>0)return;b.idle=7+Math.random()*9;OFF.idleStarts=(OFF.idleStarts||0)+1;idleGo(b)})}''')
upd = L(1363, 1365)
upd = sub(upd, "(OFF.rush?1.9:1)", "(b.rush?1.9:1)")
out.append(upd)

# ---- sound
snd = L(1366, 1400)
snd = sub(snd, 'var SND={on:ls("smm-snd")==="1",', 'var SND={on:ls("snd")==="1",')
snd = sub(snd, 'ls("smm-snd",on?"1":"0")', 'ls("snd",on?"1":"0")')
out.append(snd)

# ---- loop, layout, zoom, picking
loop = L(1401, 1407)
loop = cut(loop, "\n RM.forEach(function(r){var an=$(\"rm-\"+r.k);", "an.style.height=((y1-y0)*IS.sc)+\"px\"})}")
loop = sub(loop, 'cv.style.height=h+"px";', 'cv.style.height=h+"px"}')
loop = sub(loop, 'b.st==="working"||b.st==="waiting"||b.tp})', 'b.st==="working"||b.st==="waiting"||(b.flash&&b.flash.until>performance.now())})')
out.append(loop)
out.append(r'''/* Only characters are clickable. Empty floor does nothing. */
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
''')
tail = L(1425) + "\n" + L(1427)
tail = sub(tail, "if(!e.txt)sfx(\"pop\",BT.filter(function(x){return x.k===k})[0]);", 'if(!e.txt)sfx("pop",botK(k));')
tail = sub(tail, 'e.eb.classList.toggle("bad",!!bad);', 'e.eb.classList.remove("q");e.eb.classList.toggle("bad",!!bad);')
tail = sub(tail, "function officeWalk(k,pts,done){var b=BT.filter(function(x){return x.k===k})[0];", "function officeWalk(k,pts,done){var b=botK(k);")
out.append(tail)

out.append(r'''
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
''')

text = "\n".join(out) + "\n"
for gone in ("HASSUITE", "CCL", "XHUE", "SHOP", "handActive", "vids", "openSuite", "openPanel", "toast(", "TEASE",
             "SUITE_ON", "suiteDraw", "xbTick", "hintUI", "closePanel", "lastRes", "plan.", "state()", "smm-",
             "24/7", "b.gone", "b.tp", "b.fx", "OFF.rush", "WHO[", "LOCK"):
    if gone in text:
        idx = text.index(gone)
        raise SystemExit("left-over reference %r near: %s" % (gone, text[max(0, idx - 80):idx + 80].replace("\n", " ")))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
print("wrote", OUT, len(text), "chars,", text.count("\n"), "lines")
